use crate::lan_ip::{self, LanIp};
use serde::Serialize;
use serde_json::Value;
use std::{
    fs,
    io::{Read, Write},
    net::TcpStream,
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::Mutex,
    thread,
    time::{Duration, Instant},
};
use tauri::{AppHandle, Emitter, Manager, State};
use tauri_plugin_shell::ShellExt;

#[cfg(windows)]
use std::os::windows::process::CommandExt;

#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x0800_0000;

#[derive(Default)]
pub struct SidecarManager {
    inner: Mutex<Inner>,
}

#[derive(Default)]
struct Inner {
    child: Option<Child>,
    status: Status,
    port: Option<u16>,
    lan_ip: Option<String>,
    pair_token: Option<String>,
    error: Option<String>,
    selected_lan_ip: Option<String>,
}

#[derive(Clone, Default)]
enum Status {
    #[default]
    Stopped,
    Starting,
    Running,
    Error,
}

impl Status {
    fn as_str(&self) -> &'static str {
        match self {
            Self::Stopped => "stopped",
            Self::Starting => "starting",
            Self::Running => "running",
            Self::Error => "error",
        }
    }
}

#[derive(Clone, Serialize)]
pub struct PairInfo {
    token: Option<String>,
    lan_url: Option<String>,
}

#[derive(Clone, Serialize)]
pub struct SidecarState {
    status: String,
    port: Option<u16>,
    lan_url: Option<String>,
    pair_token: Option<String>,
    error: Option<String>,
    data_dir: String,
    log_dir: String,
    version: String,
}

#[tauri::command]
pub fn get_state(app: AppHandle, manager: State<'_, SidecarManager>) -> SidecarState {
    let mut inner = manager.inner.lock().expect("sidecar state lock poisoned");
    refresh_child_status(&mut inner);
    state_from_inner(&app, &inner)
}

#[tauri::command]
pub fn list_lan_ips() -> Vec<LanIp> {
    lan_ip::list_private_ipv4()
}

#[tauri::command]
pub fn select_lan_ip(
    app: AppHandle,
    manager: State<'_, SidecarManager>,
    ip: String,
) -> Result<SidecarState, String> {
    let mut inner = manager.inner.lock().map_err(|_| "State lock poisoned")?;
    if matches!(inner.status, Status::Running | Status::Starting) {
        return Err("Stop the server before changing LAN IP".to_string());
    }
    inner.selected_lan_ip = Some(ip);
    Ok(state_from_inner(&app, &inner))
}

#[tauri::command]
pub fn start_sidecar(
    app: AppHandle,
    manager: State<'_, SidecarManager>,
) -> Result<SidecarState, String> {
    {
        let mut inner = manager.inner.lock().map_err(|_| "State lock poisoned")?;
        refresh_child_status(&mut inner);
        if matches!(inner.status, Status::Running) {
            return Ok(state_from_inner(&app, &inner));
        }
        inner.status = Status::Starting;
        inner.error = None;
        emit_state(&app, &inner);
    }

    let data_dir = data_dir()?;
    let log_dir = log_dir()?;
    let runtime_dir = data_dir.join("runtime");
    fs::create_dir_all(&runtime_dir)
        .map_err(|error| format!("Could not create runtime dir: {error}"))?;
    fs::create_dir_all(&log_dir).map_err(|error| format!("Could not create log dir: {error}"))?;
    cleanup_stale_runtime(&runtime_dir);

    let lan_ip = {
        let inner = manager.inner.lock().map_err(|_| "State lock poisoned")?;
        inner
            .selected_lan_ip
            .clone()
            .or_else(lan_ip::first_private_ipv4)
            .ok_or_else(|| "No private LAN IPv4 address found".to_string())?
    };

    let sidecar = sidecar_exe(&app)?;
    let mut command = Command::new(sidecar);
    command
        .args([
            "--host",
            "0.0.0.0",
            "--port",
            "0",
            "--data-dir",
            &data_dir.display().to_string(),
            "--log-dir",
            &log_dir.display().to_string(),
        ])
        .env("TAGLEDGER_ALLOWED_HOSTS", &lan_ip)
        .stdout(Stdio::null())
        .stderr(Stdio::null());

    #[cfg(windows)]
    command.creation_flags(CREATE_NO_WINDOW);

    let child = command
        .spawn()
        .map_err(|error| format!("Could not start TagLedger server: {error}"))?;

    {
        let mut inner = manager.inner.lock().map_err(|_| "State lock poisoned")?;
        inner.child = Some(child);
        inner.lan_ip = Some(lan_ip.clone());
        emit_state(&app, &inner);
    }

    match wait_for_ready(&runtime_dir) {
        Ok((port, token)) => {
            let mut inner = manager.inner.lock().map_err(|_| "State lock poisoned")?;
            inner.status = Status::Running;
            inner.port = Some(port);
            inner.pair_token = token;
            inner.error = None;
            emit_state(&app, &inner);
            Ok(state_from_inner(&app, &inner))
        }
        Err(error) => {
            let mut inner = manager.inner.lock().map_err(|_| "State lock poisoned")?;
            inner.status = Status::Error;
            inner.error = Some(error.clone());
            stop_child(&mut inner);
            cleanup_runtime_files(&runtime_dir);
            emit_state(&app, &inner);
            Err(error)
        }
    }
}

#[tauri::command]
pub fn stop_sidecar(app: AppHandle, manager: State<'_, SidecarManager>) -> Result<(), String> {
    let runtime = data_dir()?.join("runtime");
    let mut inner = manager.inner.lock().map_err(|_| "State lock poisoned")?;
    stop_child(&mut inner);
    cleanup_runtime_files(&runtime);
    emit_state(&app, &inner);
    Ok(())
}

#[tauri::command]
pub fn restart_sidecar(
    app: AppHandle,
    manager: State<'_, SidecarManager>,
) -> Result<SidecarState, String> {
    stop_sidecar(app.clone(), manager.clone())?;
    start_sidecar(app, manager)
}

#[tauri::command]
pub fn regenerate_pair_token(
    app: AppHandle,
    manager: State<'_, SidecarManager>,
) -> Result<PairInfo, String> {
    let (port, lan_ip) = {
        let inner = manager.inner.lock().map_err(|_| "State lock poisoned")?;
        (
            inner
                .port
                .ok_or_else(|| "TagLedger server is not running".to_string())?,
            inner.lan_ip.clone(),
        )
    };
    let (status, body) = http_request("POST", port, "/api/pairing/regenerate", Some("{}"))?;
    if status != 200 {
        return Err(format!("Pair token regenerate failed with HTTP {status}"));
    }
    let payload: Value =
        serde_json::from_str(&body).map_err(|error| format!("Invalid JSON: {error}"))?;
    let token = payload
        .get("token")
        .and_then(Value::as_str)
        .map(ToString::to_string);
    let mut inner = manager.inner.lock().map_err(|_| "State lock poisoned")?;
    inner.pair_token = token.clone();
    emit_state(&app, &inner);
    Ok(PairInfo {
        lan_url: lan_url(lan_ip.as_deref(), inner.port, token.as_deref()),
        token,
    })
}

#[tauri::command]
pub fn open_data_dir(app: AppHandle) -> Result<(), String> {
    open_path(&app, data_dir()?)
}

#[tauri::command]
pub fn open_log_dir(app: AppHandle) -> Result<(), String> {
    let path = log_dir()?;
    fs::create_dir_all(&path).map_err(|error| format!("Could not create log dir: {error}"))?;
    open_path(&app, path)
}

pub fn stop_on_exit(app: &AppHandle) {
    let manager = app.state::<SidecarManager>();
    let locked = manager.inner.lock();
    if let Ok(mut inner) = locked {
        stop_child(&mut inner);
        if let Ok(runtime) = data_dir().map(|path| path.join("runtime")) {
            cleanup_runtime_files(&runtime);
        }
    }
}

fn wait_for_ready(runtime_dir: &Path) -> Result<(u16, Option<String>), String> {
    let port = wait_for_file(runtime_dir.join("port"), Duration::from_secs(15))
        .and_then(|value| value.parse::<u16>().ok())
        .ok_or_else(|| "Server did not write runtime port within 15 seconds".to_string())?;

    let token_file = wait_for_file(runtime_dir.join("pair_token"), Duration::from_secs(3));
    let (status, body) = wait_for_status(port, Duration::from_secs(15))?;
    if status != 200 {
        return Err(format!("Pairing status returned HTTP {status}"));
    }
    let payload: Value =
        serde_json::from_str(&body).map_err(|error| format!("Invalid pairing status JSON: {error}"))?;
    let token = payload
        .get("token")
        .and_then(Value::as_str)
        .map(ToString::to_string)
        .or(token_file);
    if token.is_none() {
        return Err("Server did not provide a pair token".to_string());
    }
    Ok((port, token))
}

fn wait_for_status(port: u16, deadline: Duration) -> Result<(u16, String), String> {
    let start = Instant::now();
    let mut last_error = "Server did not answer pairing status".to_string();
    while start.elapsed() < deadline {
        match http_request("GET", port, "/api/pairing/status", None) {
            Ok(response) => return Ok(response),
            Err(error) => last_error = error,
        }
        thread::sleep(Duration::from_millis(250));
    }
    Err(last_error)
}

fn wait_for_file(path: PathBuf, deadline: Duration) -> Option<String> {
    let start = Instant::now();
    while start.elapsed() < deadline {
        if let Ok(value) = fs::read_to_string(&path) {
            let trimmed = value.trim().to_string();
            if !trimmed.is_empty() {
                return Some(trimmed);
            }
        }
        thread::sleep(Duration::from_millis(200));
    }
    None
}

fn http_request(
    method: &str,
    port: u16,
    path: &str,
    body: Option<&str>,
) -> Result<(u16, String), String> {
    let body = body.unwrap_or("");
    let mut stream = TcpStream::connect(("127.0.0.1", port))
        .map_err(|error| format!("Could not connect to sidecar: {error}"))?;
    stream
        .set_read_timeout(Some(Duration::from_secs(5)))
        .map_err(|error| format!("Could not set read timeout: {error}"))?;
    let request = format!(
        "{method} {path} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}",
        body.len()
    );
    stream
        .write_all(request.as_bytes())
        .map_err(|error| format!("Could not write request: {error}"))?;
    let mut response = String::new();
    stream
        .read_to_string(&mut response)
        .map_err(|error| format!("Could not read response: {error}"))?;
    let status = response
        .lines()
        .next()
        .and_then(|line| line.split_whitespace().nth(1))
        .and_then(|code| code.parse::<u16>().ok())
        .ok_or_else(|| "Invalid HTTP response from sidecar".to_string())?;
    let body = response
        .split("\r\n\r\n")
        .nth(1)
        .unwrap_or_default()
        .to_string();
    Ok((status, body))
}

fn sidecar_exe(app: &AppHandle) -> Result<PathBuf, String> {
    let resource = app
        .path()
        .resource_dir()
        .map_err(|error| format!("Could not resolve resource dir: {error}"))?
        .join("tagledger-server")
        .join("tagledger_server.exe");
    if resource.exists() {
        return Ok(resource);
    }

    let manifest = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let dev = manifest
        .parent()
        .and_then(Path::parent)
        .ok_or_else(|| "Could not resolve repository root".to_string())?
        .join("dist")
        .join("tagledger-server")
        .join("tagledger_server.exe");
    if dev.exists() {
        return Ok(dev);
    }

    Err(format!(
        "Missing sidecar executable. Run M2 first; checked {} and {}",
        resource.display(),
        dev.display()
    ))
}

fn data_dir() -> Result<PathBuf, String> {
    #[cfg(windows)]
    {
        let base = std::env::var_os("APPDATA")
            .map(PathBuf::from)
            .or_else(|| dirs::home_dir().map(|home| home.join("AppData").join("Roaming")))
            .ok_or_else(|| "Could not resolve %APPDATA%".to_string())?;
        return Ok(base.join("TagLedger"));
    }

    #[cfg(not(windows))]
    {
        let base = dirs::data_dir()
            .or_else(dirs::home_dir)
            .ok_or_else(|| "Could not resolve user data dir".to_string())?;
        Ok(base.join("TagLedger"))
    }
}

fn log_dir() -> Result<PathBuf, String> {
    Ok(data_dir()?.join("logs"))
}

fn state_from_inner(app: &AppHandle, inner: &Inner) -> SidecarState {
    let data = data_dir().unwrap_or_else(|_| PathBuf::from("TagLedger"));
    let logs = log_dir().unwrap_or_else(|_| data.join("logs"));
    SidecarState {
        status: inner.status.as_str().to_string(),
        port: inner.port,
        lan_url: lan_url(inner.lan_ip.as_deref(), inner.port, inner.pair_token.as_deref()),
        pair_token: inner.pair_token.clone(),
        error: inner.error.clone(),
        data_dir: data.display().to_string(),
        log_dir: logs.display().to_string(),
        version: app.package_info().version.to_string(),
    }
}

fn lan_url(lan_ip: Option<&str>, port: Option<u16>, token: Option<&str>) -> Option<String> {
    Some(format!(
        "http://{}:{}/pair?t={}",
        lan_ip?,
        port?,
        token?
    ))
}

fn emit_state(app: &AppHandle, inner: &Inner) {
    let _ = app.emit("sidecar_state_changed", state_from_inner(app, inner));
}

fn refresh_child_status(inner: &mut Inner) {
    if let Some(child) = inner.child.as_mut() {
        if let Ok(Some(status)) = child.try_wait() {
            inner.child = None;
            inner.status = Status::Error;
            inner.port = None;
            inner.pair_token = None;
            inner.error = Some(format!("TagLedger server exited with {status}"));
        }
    }
}

fn cleanup_stale_runtime(runtime: &Path) {
    if let Ok(pid) = fs::read_to_string(runtime.join("pid")) {
        if let Ok(pid) = pid.trim().parse::<u32>() {
            kill_pid(pid, true);
        }
    }
    cleanup_runtime_files(runtime);
}

fn cleanup_runtime_files(runtime: &Path) {
    for name in ["port", "pid", "pair_token"] {
        let _ = fs::remove_file(runtime.join(name));
    }
}

fn stop_child(inner: &mut Inner) {
    if let Some(mut child) = inner.child.take() {
        kill_pid(child.id(), false);
        let start = Instant::now();
        while start.elapsed() < Duration::from_secs(3) {
            if matches!(child.try_wait(), Ok(Some(_))) {
                break;
            }
            thread::sleep(Duration::from_millis(100));
        }
        if matches!(child.try_wait(), Ok(None)) {
            let _ = child.kill();
            let _ = child.wait();
        }
    }
    inner.status = Status::Stopped;
    inner.port = None;
    inner.pair_token = None;
    inner.error = None;
}

#[cfg(windows)]
fn kill_pid(pid: u32, force: bool) {
    let mut command = Command::new("taskkill");
    command.args(["/PID", &pid.to_string(), "/T"]);
    if force {
        command.arg("/F");
    }
    let _ = command
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status();
}

#[cfg(not(windows))]
fn kill_pid(pid: u32, force: bool) {
    let signal = if force { "-9" } else { "-TERM" };
    let _ = Command::new("kill")
        .args([signal, &pid.to_string()])
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status();
}

fn open_path(app: &AppHandle, path: PathBuf) -> Result<(), String> {
    let path = path.display().to_string();
    app.shell()
        .open(path, None)
        .map_err(|error| format!("Could not open path: {error}"))
}
