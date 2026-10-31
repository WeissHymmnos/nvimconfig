use crate::lua::{keymap_field_id, RuntimeEntity};
use crate::model::{
    Keymap, LuaValue, PluginManagerKind, RuntimeStatus, SettingNamespace, Snapshot,
};
use anyhow::{anyhow, bail, Context, Result};
use rmpv::Value;
use std::collections::HashMap;
use std::io::Cursor;
use std::sync::atomic::{AtomicBool, AtomicU32, Ordering};
use std::sync::Arc;
use std::time::Duration;
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::UnixStream;
use tokio::sync::{mpsc, oneshot, Mutex as AsyncMutex};

#[derive(Clone)]
pub struct NvimClient {
    outgoing: mpsc::Sender<Value>,
    pending: PendingRequests,
    next_id: Arc<AtomicU32>,
    alive: Arc<AtomicBool>,
}

type PendingRequests = Arc<AsyncMutex<HashMap<u32, oneshot::Sender<Result<Value>>>>>;

impl NvimClient {
    pub async fn connect(address: &str) -> Result<Self> {
        let stream = UnixStream::connect(address)
            .await
            .with_context(|| format!("cannot connect to Neovim socket {address}"))?;
        let (mut reader, mut writer) = stream.into_split();
        let (outgoing, mut receiver) = mpsc::channel::<Value>(64);
        let pending = PendingRequests::default();
        let alive = Arc::new(AtomicBool::new(true));

        let writer_pending = pending.clone();
        let writer_alive = alive.clone();
        tokio::spawn(async move {
            while let Some(value) = receiver.recv().await {
                let mut bytes = Vec::new();
                if let Err(error) = rmpv::encode::write_value(&mut bytes, &value) {
                    eprintln!("failed to encode Neovim RPC message: {error}");
                    break;
                }
                if let Err(error) = writer.write_all(&bytes).await {
                    eprintln!("Neovim RPC write failed: {error}");
                    break;
                }
            }
            writer_alive.store(false, Ordering::Release);
            fail_pending(&writer_pending, "Neovim RPC writer disconnected").await;
        });

        let reader_pending = pending.clone();
        let reader_alive = alive.clone();
        let reader_outgoing = outgoing.clone();
        tokio::spawn(async move {
            let mut buffer = Vec::new();
            let mut chunk = [0u8; 8192];
            loop {
                match reader.read(&mut chunk).await {
                    Ok(0) => break,
                    Ok(read) => {
                        buffer.extend_from_slice(&chunk[..read]);
                        loop {
                            match decode_one(&buffer) {
                                Ok(Some((value, consumed))) => {
                                    buffer.drain(..consumed);
                                    handle_nvim_message(value, &reader_pending, &reader_outgoing)
                                        .await;
                                }
                                Ok(None) => break,
                                Err(error) => {
                                    eprintln!("invalid Neovim Msgpack-RPC message: {error}");
                                    reader_alive.store(false, Ordering::Release);
                                    fail_pending(&reader_pending, "invalid Neovim RPC message")
                                        .await;
                                    return;
                                }
                            }
                        }
                    }
                    Err(error) => {
                        eprintln!("Neovim RPC read failed: {error}");
                        break;
                    }
                }
            }
            reader_alive.store(false, Ordering::Release);
            fail_pending(&reader_pending, "Neovim RPC reader disconnected").await;
        });

        Ok(Self {
            outgoing,
            pending,
            next_id: Arc::new(AtomicU32::new(1)),
            alive,
        })
    }

    pub fn is_connected(&self) -> bool {
        self.alive.load(Ordering::Acquire)
    }

    pub async fn request(&self, method: &str, params: Vec<Value>) -> Result<Value> {
        if !self.is_connected() {
            bail!("Neovim is disconnected");
        }
        let id = self.next_id.fetch_add(1, Ordering::Relaxed);
        let (response, receiver) = oneshot::channel();
        self.pending.lock().await.insert(id, response);
        self.outgoing
            .send(Value::Array(vec![
                Value::from(0),
                Value::from(id),
                Value::from(method),
                Value::Array(params),
            ]))
            .await
            .map_err(|_| anyhow!("Neovim RPC connection is closed"))?;
        match tokio::time::timeout(Duration::from_secs(15), receiver).await {
            Ok(Ok(result)) => result,
            Ok(Err(_)) => bail!("Neovim RPC response channel closed"),
            Err(_) => {
                self.pending.lock().await.remove(&id);
                bail!("Neovim RPC request {method} timed out")
            }
        }
    }
}

async fn handle_nvim_message(
    value: Value,
    pending: &PendingRequests,
    outgoing: &mpsc::Sender<Value>,
) {
    let Value::Array(items) = value else {
        eprintln!("ignoring non-array Neovim RPC message");
        return;
    };
    match items.first().and_then(Value::as_u64) {
        Some(1) if items.len() == 4 => {
            let Some(id) = items[1].as_u64().and_then(|id| u32::try_from(id).ok()) else {
                eprintln!("Neovim RPC response has an invalid id");
                return;
            };
            let sender = pending.lock().await.remove(&id);
            if let Some(sender) = sender {
                let result = if items[2].is_nil() {
                    Ok(items[3].clone())
                } else {
                    Err(anyhow!("Neovim RPC error: {}", display_value(&items[2])))
                };
                let _ = sender.send(result);
            }
        }
        Some(0) if items.len() == 4 => {
            let id = items[1].clone();
            let method = items[2].as_str().unwrap_or("<invalid>").to_owned();
            let response = Value::Array(vec![
                Value::from(1),
                id,
                Value::from(format!("daemon cannot handle Neovim request {method}")),
                Value::Nil,
            ]);
            let _ = outgoing.send(response).await;
        }
        Some(2) => {}
        _ => eprintln!("ignoring malformed Neovim RPC message"),
    }
}

async fn fail_pending(pending: &PendingRequests, message: &str) {
    let senders = std::mem::take(&mut *pending.lock().await);
    for (_, sender) in senders {
        let _ = sender.send(Err(anyhow!(message.to_owned())));
    }
}

pub fn decode_one(buffer: &[u8]) -> Result<Option<(Value, usize)>> {
    if buffer.is_empty() {
        return Ok(None);
    }
    let mut cursor = Cursor::new(buffer);
    match rmpv::decode::read_value(&mut cursor) {
        Ok(value) => Ok(Some((value, cursor.position() as usize))),
        Err(rmpv::decode::Error::InvalidMarkerRead(error))
        | Err(rmpv::decode::Error::InvalidDataRead(error))
            if error.kind() == std::io::ErrorKind::UnexpectedEof =>
        {
            Ok(None)
        }
        Err(error) => Err(anyhow!(error)),
    }
}

pub async fn apply_entity(
    client: &NvimClient,
    entity: &RuntimeEntity,
    previous_snapshot: &Snapshot,
    snapshot: &Snapshot,
) -> RuntimeStatus {
    let primary = match entity {
        RuntimeEntity::Setting {
            namespace,
            name,
            id,
        } => match namespace {
            SettingNamespace::Opt => {
                let field = snapshot
                    .settings
                    .iter()
                    .find(|setting| setting.field.id == *id)
                    .map(|setting| setting.field.value.as_ref());
                match field.flatten() {
                    Some(value) => match to_msgpack(value) {
                        Ok(value) => {
                            client
                                .request(
                                    "nvim_set_option_value",
                                    vec![Value::from(name.as_str()), value, Value::Map(Vec::new())],
                                )
                                .await
                                .map(|_| "option applied".to_owned())
                        }
                        Err(error) => Err(error),
                    },
                    None => {
                        if previous_snapshot
                            .settings
                            .iter()
                            .any(|setting| setting.field.id == *id)
                        {
                            client
                                .request(
                                    "nvim_exec_lua",
                                    vec![
                                        Value::from(
                                            "local name = ...; pcall(vim.cmd, 'set ' .. name .. '&')",
                                        ),
                                        Value::Array(vec![Value::from(name.as_str())]),
                                    ],
                                )
                                .await
                                .map(|_| "option reset to default".to_owned())
                        } else {
                            Err(anyhow!("updated option was not found in the snapshot"))
                        }
                    }
                }
            }
            SettingNamespace::G | SettingNamespace::Env => {
                let setting = snapshot
                    .settings
                    .iter()
                    .find(|setting| setting.field.id == *id);
                match setting.and_then(|setting| setting.field.value.as_ref()) {
                    Some(value) => match to_msgpack(value) {
                        Ok(value) => {
                            let code = if matches!(namespace, SettingNamespace::G) {
                                "local name, value = ...; vim.g[name] = value"
                            } else {
                                "local name, value = ...; vim.env[name] = value"
                            };
                            client
                                .request(
                                    "nvim_exec_lua",
                                    vec![
                                        Value::from(code),
                                        Value::Array(vec![Value::from(name.as_str()), value]),
                                    ],
                                )
                                .await
                                .map(|_| format!("{} setting applied", namespace_name(namespace)))
                        }
                        Err(error) => Err(error),
                    },
                    None => {
                        if previous_snapshot
                            .settings
                            .iter()
                            .any(|setting| setting.field.id == *id)
                        {
                            let code = if matches!(namespace, SettingNamespace::G) {
                                "local name = ...; vim.g[name] = nil"
                            } else {
                                "local name = ...; vim.env[name] = nil"
                            };
                            client
                                .request(
                                    "nvim_exec_lua",
                                    vec![
                                        Value::from(code),
                                        Value::Array(vec![Value::from(name.as_str())]),
                                    ],
                                )
                                .await
                                .map(|_| format!("{} setting deleted", namespace_name(namespace)))
                        } else {
                            Err(anyhow!("updated setting was not found in the snapshot"))
                        }
                    }
                }
            }
        },
        RuntimeEntity::Keymap { prefix } => {
            let old_km = find_keymap(previous_snapshot, prefix);
            let new_km = find_keymap(snapshot, prefix).or_else(|| {
                let old = old_km?;
                if snapshot.keymaps.len() != previous_snapshot.keymaps.len() {
                    return None;
                }
                snapshot
                    .keymaps
                    .iter()
                    .find(|km| km.mode.file == old.mode.file && km.mode.line == old.mode.line)
            });
            match new_km {
                Some(keymap) => match keymap_params(keymap) {
                    Ok((params, rhs_expr)) => {
                        let (old_mode, old_lhs, old_buffer, warning) =
                            keymap_delete_args(old_km, keymap);
                        let mut args = vec![old_mode, old_lhs, old_buffer];
                        args.extend(params);
                        args.push(warning.map_or(Value::Nil, Value::from));
                        let lua_code = if let Some(expr) = rhs_expr {
                            args.push(Value::from(expr));
                            "local old_mode, old_lhs, old_buffer, mode, lhs, rhs, opts, warning, rhs_expr = ...; if (rhs == nil or rhs == vim.NIL) and type(rhs_expr) == 'string' and rhs_expr ~= '' then local loader = loadstring or load; if loader then local fn = loader('return (' .. rhs_expr .. ')'); if fn then local ok, evaluated = pcall(fn); if ok and evaluated ~= nil then rhs = evaluated end end end; if (rhs == nil or rhs == vim.NIL) and vim and vim.fn and vim.fn.maparg then local m = type(mode) == 'table' and mode[1] or mode; local l = (old_lhs ~= nil and old_lhs ~= vim.NIL) and old_lhs or lhs; local ok_m, existing = pcall(vim.fn.maparg, l, m, false, true); if ok_m and type(existing) == 'table' and existing.callback then rhs = existing.callback end end end; if old_mode ~= nil and old_mode ~= vim.NIL then local del_opts = {}; if old_buffer ~= nil and old_buffer ~= vim.NIL then del_opts.buffer = old_buffer end; local ok, err = pcall(vim.keymap.del, old_mode, old_lhs, del_opts); if not ok then warning = tostring(err) end end; if rhs ~= nil and rhs ~= vim.NIL then vim.keymap.set(mode, lhs, rhs, opts or {}) end; return warning"
                        } else {
                            "local old_mode, old_lhs, old_buffer, mode, lhs, rhs, opts, warning = ...; if old_mode ~= nil and old_mode ~= vim.NIL then local del_opts = {}; if old_buffer ~= nil and old_buffer ~= vim.NIL then del_opts.buffer = old_buffer end; local ok, err = pcall(vim.keymap.del, old_mode, old_lhs, del_opts); if not ok then warning = tostring(err) end end; vim.keymap.set(mode, lhs, rhs, opts or {}); return warning"
                        };
                        client
                            .request(
                                "nvim_exec_lua",
                                vec![Value::from(lua_code), Value::Array(args)],
                            )
                            .await
                            .map(|result| match result.as_str() {
                                Some(warning) => {
                                    format!("keymap applied; old keymap cleanup warning: {warning}")
                                }
                                None => "keymap applied".to_owned(),
                            })
                    }
                    Err(error) => Err(error),
                },
                None => match old_km {
                    Some(old) => {
                        let old_mode = old
                            .mode
                            .value
                            .as_ref()
                            .and_then(|value| to_msgpack(value).ok())
                            .unwrap_or(Value::Nil);
                        let old_lhs = old
                            .lhs
                            .value
                            .as_ref()
                            .and_then(|value| to_msgpack(value).ok())
                            .unwrap_or(Value::Nil);
                        let old_buffer = old
                            .opts
                            .value
                            .as_ref()
                            .and_then(|value| match value {
                                LuaValue::Table { entries } => {
                                    entries.iter().find(|entry| entry.key == "buffer")
                                }
                                _ => None,
                            })
                            .and_then(|entry| to_msgpack(&entry.value).ok())
                            .unwrap_or(Value::Nil);
                        client
                            .request(
                                "nvim_exec_lua",
                                vec![
                                    Value::from(
                                        "local old_mode, old_lhs, old_buffer = ...; if old_mode ~= nil and old_mode ~= vim.NIL and old_lhs ~= nil and old_lhs ~= vim.NIL then local del_opts = {}; if old_buffer ~= nil and old_buffer ~= vim.NIL then del_opts.buffer = old_buffer end; pcall(vim.keymap.del, old_mode, old_lhs, del_opts) end; return 'keymap deleted'",
                                    ),
                                    Value::Array(vec![old_mode, old_lhs, old_buffer]),
                                ],
                            )
                            .await
                            .map(|_| "keymap deleted".to_owned())
                    }
                    None => Err(anyhow!("updated keymap was not found in the snapshot")),
                },
            }
        }
        RuntimeEntity::Plugin { name, manager } => match manager {
            PluginManagerKind::Lazy => {
                let lua_code = r#"
local name = ...
local ok, lazy = pcall(require, 'lazy')
if not ok or type(lazy) ~= 'table' then
    return 'lazy.nvim is not loaded in Neovim; live reload skipped'
end
if type(lazy.reload) ~= 'function' then
    return 'lazy.nvim reload() is not available; live reload skipped'
end
local rel_ok, rel_err = pcall(lazy.reload, { plugins = { name }, show = false })
if not rel_ok then
    return 'lazy.nvim reload warning: ' .. tostring(rel_err)
end
return 'lazy.nvim reload applied for ' .. name
"#;
                client
                    .request(
                        "nvim_exec_lua",
                        vec![
                            Value::from(lua_code),
                            Value::Array(vec![Value::from(name.as_str())]),
                        ],
                    )
                    .await
                    .map(|result| {
                        result
                            .as_str()
                            .map(str::to_owned)
                            .unwrap_or_else(|| "lazy.nvim reload completed".to_owned())
                    })
            }
            PluginManagerKind::Packer => {
                let lua_code = r#"
local name = ...
pcall(function()
    if vim and vim.notify then
        vim.notify(
            string.format("Config updated for '%s' (packer.nvim). Run :PackerCompile or restart Neovim to apply.", name),
            vim.log.levels.INFO
        )
    end
end)
return string.format("packer.nvim configuration for '%s' saved; run :PackerCompile or restart Neovim", name)
"#;
                client
                    .request(
                        "nvim_exec_lua",
                        vec![
                            Value::from(lua_code),
                            Value::Array(vec![Value::from(name.as_str())]),
                        ],
                    )
                    .await
                    .map(|result| {
                        result
                            .as_str()
                            .map(str::to_owned)
                            .unwrap_or_else(|| {
                                format!(
                                    "packer.nvim configuration for '{name}' saved; run :PackerCompile or restart Neovim"
                                )
                            })
                    })
            }
            PluginManagerKind::Plug => {
                let lua_code = r#"
local name = ...
pcall(function()
    if vim and vim.notify then
        vim.notify(
            string.format("Config updated for '%s' (vim-plug). Re-source configuration or restart Neovim to apply.", name),
            vim.log.levels.INFO
        )
    end
end)
return string.format("vim-plug configuration for '%s' saved; re-source config or restart Neovim", name)
"#;
                client
                    .request(
                        "nvim_exec_lua",
                        vec![
                            Value::from(lua_code),
                            Value::Array(vec![Value::from(name.as_str())]),
                        ],
                    )
                    .await
                    .map(|result| {
                        result
                            .as_str()
                            .map(str::to_owned)
                            .unwrap_or_else(|| {
                                format!(
                                    "vim-plug configuration for '{name}' saved; re-source config or restart Neovim"
                                )
                            })
                    })
            }
        },
    };

    let checktime = client
        .request("nvim_command", vec![Value::from("checktime")])
        .await;
    match (primary, checktime) {
        (Ok(message), Ok(_)) => RuntimeStatus {
            applied: true,
            message,
        },
        (Ok(message), Err(error)) => RuntimeStatus {
            applied: true,
            message: format!("{message}; checktime failed: {error}"),
        },
        (Err(error), Ok(_)) => RuntimeStatus {
            applied: false,
            message: format!("runtime apply failed: {error}; checktime succeeded"),
        },
        (Err(error), Err(checktime_error)) => RuntimeStatus {
            applied: false,
            message: format!(
                "runtime apply failed: {error}; checktime also failed: {checktime_error}"
            ),
        },
    }
}

fn find_keymap<'a>(snapshot: &'a Snapshot, prefix: &str) -> Option<&'a Keymap> {
    let mode_id = keymap_field_id(prefix, "mode");
    snapshot
        .keymaps
        .iter()
        .find(|keymap| keymap.mode.id == mode_id)
}

fn keymap_params(keymap: &Keymap) -> Result<(Vec<Value>, Option<String>)> {
    let mode = keymap
        .mode
        .value
        .as_ref()
        .ok_or_else(|| anyhow!("keymap field {} is missing", keymap.mode.id))
        .and_then(to_msgpack)?;
    let lhs = keymap
        .lhs
        .value
        .as_ref()
        .ok_or_else(|| anyhow!("keymap field {} is missing", keymap.lhs.id))
        .and_then(to_msgpack)?;
    let (rhs, rhs_expr) = match keymap.rhs.value.as_ref() {
        Some(LuaValue::Unsupported { source }) => (Value::Nil, Some(source.clone())),
        Some(other) => (to_msgpack(other)?, None),
        None => return Err(anyhow!("keymap field {} is missing", keymap.rhs.id)),
    };
    let opts = keymap
        .opts
        .value
        .as_ref()
        .ok_or_else(|| anyhow!("keymap field {} is missing", keymap.opts.id))
        .and_then(to_msgpack)?;
    Ok((vec![mode, lhs, rhs, opts], rhs_expr))
}

fn keymap_delete_args(old: Option<&Keymap>, new: &Keymap) -> (Value, Value, Value, Option<String>) {
    if old.is_some_and(|old| old.mode.value == new.mode.value && old.lhs.value == new.lhs.value) {
        return (Value::Nil, Value::Nil, Value::Nil, None);
    }
    let Some(old) = old else {
        return (
            Value::Nil,
            Value::Nil,
            Value::Nil,
            Some("previous keymap was not available for static deletion".to_owned()),
        );
    };
    let mode = old
        .mode
        .value
        .as_ref()
        .and_then(|value| to_msgpack(value).ok());
    let lhs = old
        .lhs
        .value
        .as_ref()
        .and_then(|value| to_msgpack(value).ok());
    let (Some(mode), Some(lhs)) = (mode, lhs) else {
        return (
            Value::Nil,
            Value::Nil,
            Value::Nil,
            Some("previous mode/lhs is dynamic; old mapping was not deleted".to_owned()),
        );
    };
    let old_buffer = old.opts.value.as_ref().and_then(|value| match value {
        LuaValue::Table { entries } => entries.iter().find(|entry| entry.key == "buffer"),
        _ => None,
    });
    let buffer = match old_buffer {
        Some(entry) => match to_msgpack(&entry.value) {
            Ok(value) => value,
            Err(_) => {
                return (
                    Value::Nil,
                    Value::Nil,
                    Value::Nil,
                    Some(
                        "previous buffer option is dynamic; old mapping was not deleted".to_owned(),
                    ),
                );
            }
        },
        None => Value::Nil,
    };
    (mode, lhs, buffer, None)
}

pub fn to_msgpack(value: &LuaValue) -> Result<Value> {
    match value {
        LuaValue::Boolean { value } => Ok(Value::from(*value)),
        LuaValue::Number { value } => {
            if let Some(value) = value.as_i64() {
                Ok(Value::from(value))
            } else if let Some(value) = value.as_u64() {
                Ok(Value::from(value))
            } else if let Some(value) = value.as_f64() {
                Ok(Value::from(value))
            } else {
                bail!("number cannot be represented by Msgpack")
            }
        }
        LuaValue::String { value } => Ok(Value::from(value.as_str())),
        LuaValue::Array { values } => Ok(Value::Array(
            values.iter().map(to_msgpack).collect::<Result<_>>()?,
        )),
        LuaValue::Table { entries } => Ok(Value::Map(
            entries
                .iter()
                .map(|entry| Ok((Value::from(entry.key.as_str()), to_msgpack(&entry.value)?)))
                .collect::<Result<_>>()?,
        )),
        LuaValue::Unsupported { .. } => bail!("unsupported Lua value cannot be sent to Neovim"),
    }
}

pub fn schema_to_json(value: &Value) -> Result<serde_json::Value> {
    match value {
        Value::Nil => Ok(serde_json::Value::Null),
        Value::Boolean(value) => Ok(serde_json::Value::from(*value)),
        Value::Integer(value) => {
            if let Some(value) = value.as_i64() {
                Ok(serde_json::Value::from(value))
            } else if let Some(value) = value.as_u64() {
                Ok(serde_json::Value::from(value))
            } else {
                bail!("schema integer is out of range")
            }
        }
        Value::F32(value) => serde_json::Number::from_f64(*value as f64)
            .map(serde_json::Value::Number)
            .ok_or_else(|| anyhow!("schema contains a non-finite float")),
        Value::F64(value) => serde_json::Number::from_f64(*value)
            .map(serde_json::Value::Number)
            .ok_or_else(|| anyhow!("schema contains a non-finite float")),
        Value::String(value) => value
            .as_str()
            .map(serde_json::Value::from)
            .ok_or_else(|| anyhow!("schema contains a non-UTF-8 string")),
        Value::Binary(value) => Ok(serde_json::Value::from(value.clone())),
        Value::Array(values) => Ok(serde_json::Value::Array(
            values
                .iter()
                .map(schema_to_json)
                .collect::<Result<Vec<_>>>()?,
        )),
        Value::Map(entries) => {
            let mut map = serde_json::Map::new();
            for (key, value) in entries {
                let key = key
                    .as_str()
                    .ok_or_else(|| anyhow!("schema map key is not a string"))?;
                map.insert(key.to_owned(), schema_to_json(value)?);
            }
            Ok(serde_json::Value::Object(map))
        }
        Value::Ext(_, _) => bail!("schema contains an unsupported Msgpack extension value"),
    }
}

pub fn display_value(value: &Value) -> String {
    match value.as_str() {
        Some(value) => value.to_owned(),
        None => format!("{value:?}"),
    }
}

fn namespace_name(namespace: &SettingNamespace) -> &'static str {
    match namespace {
        SettingNamespace::Opt => "opt",
        SettingNamespace::G => "g",
        SettingNamespace::Env => "env",
    }
}
