use anyhow::{anyhow, bail, Context, Result};
use clap::Parser;
use rand::RngCore;
use rmpv::Value;
use std::net::{IpAddr, Ipv4Addr, SocketAddr};
use std::os::unix::fs::FileTypeExt;
use std::path::{Path, PathBuf};
use std::sync::Arc;
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::{TcpListener, UnixListener, UnixStream};
use tokio::sync::mpsc;
use ucdp_daemon::nvim::decode_one;
use ucdp_daemon::state::{absolute_path, AppState};

#[derive(Debug, Parser)]
#[command(name = "ucdp-daemon", about = "Neovim configuration bridge daemon")]
struct Cli {
    #[arg(long)]
    config: Option<PathBuf>,
    #[arg(long)]
    listen: Option<SocketAddr>,
    #[arg(long)]
    daemon_socket: Option<PathBuf>,
}

#[tokio::main]
async fn main() -> Result<()> {
    let cli = Cli::parse();
    let config = match cli.config {
        Some(path) => path,
        None => default_config_root()?,
    };
    let config = absolute_path(&config)?;
    let listen = cli
        .listen
        .unwrap_or_else(|| SocketAddr::new(IpAddr::V4(Ipv4Addr::LOCALHOST), 0));
    if !listen.ip().is_loopback() {
        bail!("--listen must use a loopback address");
    }
    let daemon_socket = match cli.daemon_socket {
        Some(path) => absolute_path(&path)?,
        None => default_daemon_socket(),
    };
    prepare_daemon_socket(&daemon_socket).await?;

    let token = random_token();
    let state = Arc::new(AppState::new(config, token.clone()));
    state.rescan("startup").await;

    let http_listener = TcpListener::bind(listen)
        .await
        .with_context(|| format!("cannot bind HTTP listener {listen}"))?;
    let http_address = http_listener.local_addr()?;
    let daemon_listener = UnixListener::bind(&daemon_socket)
        .with_context(|| format!("cannot bind daemon socket {}", daemon_socket.display()))?;

    println!(
        "{}",
        serde_json::json!({
            "http": format!("http://{http_address}"),
            "token": token,
            "daemon_socket": daemon_socket.to_string_lossy(),
        })
    );
    use std::io::Write;
    std::io::stdout().flush()?;

    let http_state = state.clone();
    let http_task = tokio::spawn(async move {
        axum::serve(http_listener, ucdp_daemon::http::router(http_state))
            .await
            .map_err(anyhow::Error::from)
    });
    let daemon_state = state.clone();
    let daemon_task =
        tokio::spawn(async move { serve_daemon(daemon_listener, daemon_state).await });

    let result = tokio::select! {
        result = http_task => match result {
            Ok(result) => result,
            Err(error) => Err(anyhow!("HTTP task failed: {error}")),
        },
        result = daemon_task => match result {
            Ok(result) => result,
            Err(error) => Err(anyhow!("daemon socket task failed: {error}")),
        },
        signal = tokio::signal::ctrl_c() => {
            signal.context("cannot listen for Ctrl-C")?;
            Ok(())
        }
    };
    let _ = tokio::fs::remove_file(&daemon_socket).await;
    result
}

async fn serve_daemon(listener: UnixListener, state: Arc<AppState>) -> Result<()> {
    loop {
        let (stream, _) = listener.accept().await?;
        let state = state.clone();
        tokio::spawn(async move {
            if let Err(error) = handle_bridge(stream, state).await {
                eprintln!("Lua bridge connection failed: {error}");
            }
        });
    }
}

async fn handle_bridge(stream: UnixStream, state: Arc<AppState>) -> Result<()> {
    let (mut reader, mut writer) = stream.into_split();
    let (outgoing, mut receiver) = mpsc::channel::<Value>(16);
    let writer_task = tokio::spawn(async move {
        while let Some(value) = receiver.recv().await {
            let mut bytes = Vec::new();
            rmpv::encode::write_value(&mut bytes, &value)?;
            writer.write_all(&bytes).await?;
        }
        Ok::<_, anyhow::Error>(())
    });

    let mut buffer = Vec::new();
    let mut chunk = [0u8; 8192];
    loop {
        let read = reader.read(&mut chunk).await?;
        if read == 0 {
            break;
        }
        buffer.extend_from_slice(&chunk[..read]);
        while let Some((value, consumed)) = decode_one(&buffer)? {
            buffer.drain(..consumed);
            handle_bridge_message(value, state.clone(), outgoing.clone()).await;
        }
    }
    if !buffer.is_empty() {
        eprintln!("Lua bridge disconnected with an incomplete Msgpack-RPC message");
    }
    writer_task.abort();
    Ok(())
}

async fn handle_bridge_message(value: Value, state: Arc<AppState>, outgoing: mpsc::Sender<Value>) {
    let Value::Array(items) = value else {
        eprintln!("ignoring non-array Lua bridge RPC message");
        return;
    };
    match items.first().and_then(Value::as_u64) {
        Some(2) if items.len() == 3 => {
            let method = items[1].as_str().unwrap_or("<invalid>");
            let params = &items[2];
            match method {
                "ucdp_register" => match register_params(params) {
                    Ok((socket, config, schema)) => {
                        if let Err(error) = state.register(socket, config, schema).await {
                            eprintln!("ucdp_register failed: {error:#}");
                        }
                    }
                    Err(error) => eprintln!("invalid ucdp_register notification: {error:#}"),
                },
                "ucdp_buf_written" => {
                    let path = params
                        .as_array()
                        .and_then(|params| params.first())
                        .and_then(Value::as_str)
                        .map(str::to_owned);
                    match path {
                        Some(path) => state.schedule_rescan(path).await,
                        None => eprintln!(
                            "invalid ucdp_buf_written notification: expected [absolute_lua_path]"
                        ),
                    }
                }
                _ => eprintln!("unknown Lua bridge notification method {method}"),
            }
        }
        Some(0) if items.len() == 4 => {
            let id = items[1].clone();
            let method = items[2].as_str().unwrap_or("<invalid>");
            let response = Value::Array(vec![
                Value::from(1),
                id,
                Value::from(format!("daemon does not support request method {method}")),
                Value::Nil,
            ]);
            let _ = outgoing.send(response).await;
        }
        Some(1) => eprintln!("unexpected RPC response on Lua bridge connection"),
        _ => eprintln!("malformed Lua bridge RPC message"),
    }
}

fn register_params(params: &Value) -> Result<(String, String, Value)> {
    let params = params
        .as_array()
        .ok_or_else(|| anyhow!("parameters must be an array"))?;
    let registration = params
        .first()
        .and_then(Value::as_map)
        .ok_or_else(|| anyhow!("first parameter must be a map"))?;
    let socket = map_string(registration, "socket")?;
    let config = map_string(registration, "config")?;
    let schema = registration
        .iter()
        .find(|(key, _)| key.as_str() == Some("schema"))
        .map(|(_, value)| value.clone())
        .ok_or_else(|| anyhow!("missing schema"))?;
    Ok((socket, config, schema))
}

fn map_string(map: &[(Value, Value)], key: &str) -> Result<String> {
    map.iter()
        .find(|(candidate, _)| candidate.as_str() == Some(key))
        .and_then(|(_, value)| value.as_str())
        .map(str::to_owned)
        .ok_or_else(|| anyhow!("missing or non-string {key}"))
}

fn default_config_root() -> Result<PathBuf> {
    let home = std::env::var_os("HOME")
        .ok_or_else(|| anyhow!("HOME is not set; provide --config PATH explicitly"))?;
    Ok(PathBuf::from(home).join(".config").join("nvim"))
}

fn default_daemon_socket() -> PathBuf {
    match std::env::var_os("XDG_RUNTIME_DIR") {
        Some(directory) if !directory.is_empty() => PathBuf::from(directory)
            .join("ucdp-bridge")
            .join("daemon.sock"),
        _ => PathBuf::from("/tmp")
            .join(format!("ucdp-bridge-{}", unsafe { libc::getuid() }))
            .join("daemon.sock"),
    }
}

async fn prepare_daemon_socket(path: &Path) -> Result<()> {
    let parent = path
        .parent()
        .ok_or_else(|| anyhow!("daemon socket has no parent directory"))?;
    tokio::fs::create_dir_all(parent)
        .await
        .with_context(|| format!("cannot create daemon socket directory {}", parent.display()))?;
    match tokio::fs::symlink_metadata(path).await {
        Ok(metadata) => {
            if !metadata.file_type().is_socket() {
                bail!("refusing to replace non-socket path {}", path.display());
            }
            tokio::fs::remove_file(path)
                .await
                .with_context(|| format!("cannot remove old daemon socket {}", path.display()))?;
        }
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
        Err(error) => return Err(error.into()),
    }
    Ok(())
}

fn random_token() -> String {
    let mut bytes = [0u8; 32];
    rand::rngs::OsRng.fill_bytes(&mut bytes);
    hex::encode(bytes)
}
