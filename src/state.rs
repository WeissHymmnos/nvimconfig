use crate::lua::{self, RuntimeEntity};
use crate::model::{
    AddKeymapRequest, AddOptionRequest, AddPluginRequest, ApiError, BatchPatchRequest, ChangeEvent,
    DeleteEntityRequest, LuaValue, NvimStatus, PatchRequest, PatchResponse, RollbackRequest,
    RuntimeStatus, SettingNamespace, Snapshot,
};
use crate::nvim::{self, NvimClient};
use anyhow::{anyhow, Result};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;
use std::time::Duration;
use tokio::sync::{broadcast, Mutex, RwLock};

#[derive(Default)]
struct NvimRegistration {
    address: Option<String>,
    client: Option<NvimClient>,
}

pub struct AppState {
    pub token: String,
    config_root: RwLock<PathBuf>,
    snapshot: RwLock<Snapshot>,
    schema: RwLock<serde_json::Value>,
    nvim: Mutex<NvimRegistration>,
    events: broadcast::Sender<ChangeEvent>,
    patch_lock: Mutex<()>,
    debounce_generation: AtomicU64,
}

fn load_exported_schema() -> serde_json::Value {
    let cache = std::env::var_os("XDG_CACHE_HOME")
        .map(PathBuf::from)
        .or_else(|| std::env::var_os("HOME").map(|home| PathBuf::from(home).join(".cache")));
    cache
        .map(|path| path.join("nvim/ucdp-bridge/options.json"))
        .and_then(|path| std::fs::read(path).ok())
        .and_then(|contents| serde_json::from_slice(&contents).ok())
        .filter(serde_json::Value::is_object)
        .unwrap_or_else(|| serde_json::json!({}))
}

impl AppState {
    pub fn new(config_root: PathBuf, token: String) -> Self {
        let snapshot = Snapshot::empty(config_root.to_string_lossy().into_owned());
        let (events, _) = broadcast::channel(64);
        Self {
            token,
            config_root: RwLock::new(config_root),
            snapshot: RwLock::new(snapshot),
            schema: RwLock::new(load_exported_schema()),
            nvim: Mutex::new(NvimRegistration::default()),
            events,
            patch_lock: Mutex::new(()),
            debounce_generation: AtomicU64::new(0),
        }
    }

    pub fn subscribe(&self) -> broadcast::Receiver<ChangeEvent> {
        self.events.subscribe()
    }

    pub async fn snapshot(&self) -> Snapshot {
        self.snapshot.read().await.clone()
    }

    pub async fn schema(&self) -> serde_json::Value {
        self.schema.read().await.clone()
    }

    pub async fn config_root(&self) -> PathBuf {
        self.config_root.read().await.clone()
    }

    pub async fn nvim_status(&self) -> NvimStatus {
        let registration = self.nvim.lock().await;
        NvimStatus {
            connected: registration
                .client
                .as_ref()
                .is_some_and(NvimClient::is_connected),
            address: registration.address.clone(),
        }
    }

    pub async fn rescan(&self, reason: impl Into<String>) {
        let root = self.config_root().await;
        let snapshot = tokio::task::spawn_blocking(move || {
            let snap = lua::scan(&root).snapshot;
            let _ = lua::sync_state_file(&root, &snap);
            snap
        })
        .await
        .unwrap_or_else(|_| Snapshot::empty(String::new()));
        *self.snapshot.write().await = snapshot;
        self.emit(reason.into());
    }

    pub async fn register(
        &self,
        address: String,
        config: String,
        schema: rmpv::Value,
    ) -> Result<()> {
        let schema = match &schema {
            rmpv::Value::String(path) => {
                let path = path
                    .as_str()
                    .ok_or_else(|| anyhow!("ucdp_register schema path must be UTF-8"))?;
                let contents = tokio::fs::read(path)
                    .await
                    .map_err(|error| anyhow!("cannot read schema {path}: {error}"))?;
                serde_json::from_slice(&contents)
                    .map_err(|error| anyhow!("cannot parse schema {path}: {error}"))?
            }
            value => nvim::schema_to_json(value)?,
        };
        if !schema.is_object() {
            return Err(anyhow!(
                "ucdp_register schema must be an object or JSON file path"
            ));
        }
        let root = absolute_path(Path::new(&config))?;
        {
            let mut registration = self.nvim.lock().await;
            registration.address = Some(address.clone());
            registration.client = None;
        }
        *self.schema.write().await = schema;
        *self.config_root.write().await = root;
        self.rescan(format!("registered:{address}")).await;

        let client = NvimClient::connect(&address).await?;
        client.request("nvim_get_api_info", Vec::new()).await?;
        self.nvim.lock().await.client = Some(client);
        self.emit(format!("nvim_connected:{address}"));
        Ok(())
    }

    pub async fn patch(&self, request: PatchRequest) -> Result<PatchResponse, ApiError> {
        let _guard = self.patch_lock.lock().await;
        let root = self.config_root().await;
        let previous_snapshot = self.snapshot.read().await.clone();
        let req_clone = request.clone();
        let prev_clone = previous_snapshot.clone();
        let success = tokio::task::spawn_blocking(move || {
            lua::apply_patch_with_snapshot(&root, &req_clone, Some(&prev_clone))
        })
        .await
        .map_err(|err| ApiError::Internal(format!("blocking patch task failed: {err}")))??;
        let entity = success.entity;
        *self.snapshot.write().await = success.scan.snapshot;
        self.emit(format!("patch:{}", request.id));

        let client = self.nvim.lock().await.client.clone();
        let runtime = match client {
            Some(client) if client.is_connected() => {
                let snapshot = self.snapshot.read().await.clone();
                nvim::apply_entity(&client, &entity, &previous_snapshot, &snapshot).await
            }
            _ => runtime_not_connected(&entity),
        };
        Ok(PatchResponse {
            disk_saved: true,
            runtime,
        })
    }

    pub async fn patch_batch(
        &self,
        request: BatchPatchRequest,
    ) -> Result<PatchResponse, ApiError> {
        let _guard = self.patch_lock.lock().await;
        let root = self.config_root().await;
        let previous_snapshot = self.snapshot.read().await.clone();
        let prev_clone = previous_snapshot.clone();
        let default_file = request.file.unwrap_or_default();
        let default_rev = request.revision.unwrap_or_default();
        let patch_requests: Vec<PatchRequest> = request
            .patches
            .into_iter()
            .map(|item| PatchRequest {
                id: item.id,
                file: item.file.unwrap_or_else(|| default_file.clone()),
                revision: item.revision.unwrap_or_else(|| default_rev.clone()),
                value: item.value,
            })
            .collect();
        let batch_success = tokio::task::spawn_blocking(move || {
            lua::apply_batch_patch(&root, &patch_requests, Some(&prev_clone))
        })
        .await
        .map_err(|err| ApiError::Internal(format!("blocking batch patch task failed: {err}")))??;
        let entity = batch_success.entity;
        *self.snapshot.write().await = batch_success.scan.snapshot;
        self.emit("batch_patch".to_owned());

        let client = self.nvim.lock().await.client.clone();
        let runtime = match client {
            Some(client) if client.is_connected() => {
                let snapshot = self.snapshot.read().await.clone();
                nvim::apply_entity(&client, &entity, &previous_snapshot, &snapshot).await
            }
            _ => runtime_not_connected(&entity),
        };
        Ok(PatchResponse {
            disk_saved: true,
            runtime,
        })
    }

    pub async fn add_option(&self, request: AddOptionRequest) -> Result<PatchResponse, ApiError> {
        let _guard = self.patch_lock.lock().await;
        let schema = self.schema.read().await.clone();
        validate_native_option(&schema, &request)?;
        let previous_snapshot = self.snapshot.read().await.clone();
        if previous_snapshot.settings.iter().any(|setting| {
            matches!(setting.namespace, SettingNamespace::Opt) && setting.name == request.name
        }) {
            return Err(ApiError::Conflict(format!(
                "option {} is already present in the config",
                request.name
            )));
        }

        let root = self.config_root().await;
        let opt_name = request.name.clone();
        let opt_val = request.value.clone();
        let snapshot =
            tokio::task::spawn_blocking(move || lua::append_option(&root, &opt_name, &opt_val))
                .await
                .map_err(|err| ApiError::Internal(format!("blocking add_option failed: {err}")))??
                .snapshot;
        let id = snapshot
            .settings
            .iter()
            .find(|setting| {
                matches!(setting.namespace, SettingNamespace::Opt) && setting.name == request.name
            })
            .map(|setting| setting.field.id.clone())
            .ok_or_else(|| {
                ApiError::Internal(format!(
                    "option {} was not found after appending",
                    request.name
                ))
            })?;
        let entity = RuntimeEntity::Setting {
            namespace: SettingNamespace::Opt,
            name: request.name.clone(),
            id,
        };
        *self.snapshot.write().await = snapshot;
        self.emit(format!("option:{}", request.name));

        let client = self.nvim.lock().await.client.clone();
        let runtime = match client {
            Some(client) if client.is_connected() => {
                let snapshot = self.snapshot.read().await.clone();
                nvim::apply_entity(&client, &entity, &previous_snapshot, &snapshot).await
            }
            _ => runtime_not_connected(&entity),
        };
        Ok(PatchResponse {
            disk_saved: true,
            runtime,
        })
    }

    pub async fn add_keymap(&self, request: AddKeymapRequest) -> Result<PatchResponse, ApiError> {
        let _guard = self.patch_lock.lock().await;
        let previous_snapshot = self.snapshot.read().await.clone();
        let root = self.config_root().await;
        let (scan_result, prefix) = tokio::task::spawn_blocking(move || {
            lua::append_keymap(
                &root,
                &request.mode,
                &request.lhs,
                &request.rhs,
                &request.opts,
            )
        })
        .await
        .map_err(|err| ApiError::Internal(format!("blocking add_keymap failed: {err}")))??;
        let snapshot = scan_result.snapshot;
        let entity = RuntimeEntity::Keymap { prefix };
        *self.snapshot.write().await = snapshot;
        self.emit("keymap:added".to_owned());

        let client = self.nvim.lock().await.client.clone();
        let runtime = match client {
            Some(client) if client.is_connected() => {
                let snapshot = self.snapshot.read().await.clone();
                nvim::apply_entity(&client, &entity, &previous_snapshot, &snapshot).await
            }
            _ => runtime_not_connected(&entity),
        };
        Ok(PatchResponse {
            disk_saved: true,
            runtime,
        })
    }

    pub async fn add_plugin(&self, request: AddPluginRequest) -> Result<PatchResponse, ApiError> {
        let _guard = self.patch_lock.lock().await;
        let previous_snapshot = self.snapshot.read().await.clone();
        let root = self.config_root().await;
        let (scan_result, name, manager) =
            tokio::task::spawn_blocking(move || lua::append_plugin(&root, &request))
                .await
                .map_err(|err| ApiError::Internal(format!("blocking add_plugin failed: {err}")))??;
        let snapshot = scan_result.snapshot;
        let entity = RuntimeEntity::Plugin {
            name: name.clone(),
            manager,
        };
        *self.snapshot.write().await = snapshot;
        self.emit(format!("plugin:{name}"));

        let client = self.nvim.lock().await.client.clone();
        let runtime = match client {
            Some(client) if client.is_connected() => {
                let snapshot = self.snapshot.read().await.clone();
                nvim::apply_entity(&client, &entity, &previous_snapshot, &snapshot).await
            }
            _ => runtime_not_connected(&entity),
        };
        Ok(PatchResponse {
            disk_saved: true,
            runtime,
        })
    }

    pub async fn delete_entity(
        &self,
        request: DeleteEntityRequest,
    ) -> Result<PatchResponse, ApiError> {
        let _guard = self.patch_lock.lock().await;
        let root = self.config_root().await;
        let previous_snapshot = self.snapshot.read().await.clone();
        let delete_id = request.id.clone();
        let success = tokio::task::spawn_blocking(move || lua::delete_entity(&root, &request))
            .await
            .map_err(|err| ApiError::Internal(format!("blocking delete_entity failed: {err}")))??;
        let entity = success.entity;
        *self.snapshot.write().await = success.scan.snapshot;
        self.emit(format!("delete:{delete_id}"));

        let client = self.nvim.lock().await.client.clone();
        let runtime = match client {
            Some(client) if client.is_connected() => {
                let snapshot = self.snapshot.read().await.clone();
                nvim::apply_entity(&client, &entity, &previous_snapshot, &snapshot).await
            }
            _ => runtime_not_connected(&entity),
        };
        Ok(PatchResponse {
            disk_saved: true,
            runtime,
        })
    }

    pub async fn rollback(&self, request: RollbackRequest) -> Result<PatchResponse, ApiError> {
        let _guard = self.patch_lock.lock().await;
        let root = self.config_root().await;
        let restored = request.file.clone().unwrap_or_else(|| "latest".to_owned());
        let scan = tokio::task::spawn_blocking(move || {
            lua::rollback_backup(
                &root,
                request.file.as_deref(),
                request.target_revision.as_deref(),
            )
        })
        .await
        .map_err(|err| ApiError::Internal(format!("blocking rollback failed: {err}")))??;
        *self.snapshot.write().await = scan.snapshot;
        self.emit(format!("rollback:{restored}"));
        Ok(PatchResponse {
            disk_saved: true,
            runtime: RuntimeStatus {
                applied: true,
                message: format!("restored backup for {restored}"),
            },
        })
    }

    pub async fn schedule_rescan(self: Arc<Self>, file: String) {
        let path = PathBuf::from(&file);
        let is_supported = path
            .extension()
            .is_some_and(|ext| ext == "lua" || ext == "vim");
        if !path.is_absolute() || !is_supported {
            return;
        }
        let root = self.config_root().await;
        let resolved_path = absolute_path(&path).unwrap_or_else(|_| path.clone());
        if !resolved_path.starts_with(&root) && !path.starts_with(&root) {
            return;
        }
        let generation = self.debounce_generation.fetch_add(1, Ordering::AcqRel) + 1;
        tokio::spawn(async move {
            tokio::time::sleep(Duration::from_millis(200)).await;
            if self.debounce_generation.load(Ordering::Acquire) == generation {
                self.rescan(format!("buf_written:{file}")).await;
            }
        });
    }

    fn emit(&self, reason: String) {
        let _ = self.events.send(ChangeEvent { reason });
    }
}

fn validate_native_option(
    schema: &serde_json::Value,
    request: &AddOptionRequest,
) -> Result<(), ApiError> {
    let options = schema.get("options").unwrap_or(schema);
    let info = match options {
        serde_json::Value::Array(options) => options.iter().find(|option| {
            option.get("name").and_then(serde_json::Value::as_str) == Some(request.name.as_str())
        }),
        serde_json::Value::Object(options) => options.get(&request.name),
        _ => None,
    };
    let expected = info
        .and_then(|info| info.get("type"))
        .and_then(serde_json::Value::as_str)
        .ok_or_else(|| {
            ApiError::BadRequest(format!(
                "option {} is not present in the registered native schema",
                request.name
            ))
        })?;
    let actual = match &request.value {
        LuaValue::Boolean { .. } => "boolean",
        LuaValue::Number { .. } => "number",
        LuaValue::String { .. } => "string",
        LuaValue::Array { .. } => "array",
        LuaValue::Table { .. } => "table",
        LuaValue::Unsupported { .. } => "unsupported",
    };
    if expected != actual {
        return Err(ApiError::BadRequest(format!(
            "option {} expects {expected}, received {actual}",
            request.name
        )));
    }
    Ok(())
}

fn runtime_not_connected(entity: &RuntimeEntity) -> RuntimeStatus {
    let target = match entity {
        RuntimeEntity::Setting { .. } => "setting".to_owned(),
        RuntimeEntity::Keymap { .. } => "keymap".to_owned(),
        RuntimeEntity::Plugin { name, manager } => {
            format!("plugin '{name}' ({})", manager.display_name())
        }
    };
    RuntimeStatus {
        applied: false,
        message: format!("disk saved; Neovim is not connected, {target} was not applied"),
    }
}

pub fn absolute_path(path: &Path) -> Result<PathBuf> {
    let absolute = if path.is_absolute() {
        path.to_path_buf()
    } else {
        std::env::current_dir()?.join(path)
    };
    if absolute.exists() {
        Ok(absolute.canonicalize()?)
    } else {
        Ok(absolute)
    }
}
