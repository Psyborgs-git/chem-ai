use serde::Serialize;
use std::{
    fs::{self, File, OpenOptions},
    io::{Read, Write},
    net::{SocketAddr, TcpListener, TcpStream},
    os::unix::fs::{OpenOptionsExt, PermissionsExt},
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc, Mutex,
    },
    thread,
    time::{Duration, Instant},
};
use tauri::Url;

const WORKSPACE: &str = env!("CHEMISTRY_WORKSPACE");
const BUILD_ID: &str = env!("CHEMISTRY_DESKTOP_BUILD_ID");
const PORTS: [u16; 2] = [8788, 8787];

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct RuntimeStatus {
    pub phase: String,
    pub message: String,
    pub error: Option<String>,
    pub origin: Option<String>,
    pub owned_backend: bool,
    pub log_path: Option<String>,
}

pub struct LocalRuntime {
    status: Mutex<RuntimeStatus>,
    child: Mutex<Option<Child>>,
    booting: AtomicBool,
    stopping: AtomicBool,
    frontend: PathBuf,
    log_path: PathBuf,
}

impl LocalRuntime {
    pub fn new(frontend: PathBuf) -> Self {
        let log_path = Path::new(WORKSPACE).join(".runtime/desktop/runtime.log");
        Self {
            status: Mutex::new(RuntimeStatus {
                phase: "checking".into(),
                message: "Preparing your local workspace…".into(),
                error: None,
                origin: None,
                owned_backend: false,
                log_path: Some(log_path.to_string_lossy().into()),
            }),
            child: Mutex::new(None),
            booting: AtomicBool::new(false),
            stopping: AtomicBool::new(false),
            frontend,
            log_path,
        }
    }

    pub fn status(&self) -> RuntimeStatus {
        self.status.lock().unwrap().clone()
    }

    pub fn record_open(&self) {
        self.log("Bundled startup UI verified the runtime and opened the local workspace.");
    }

    fn phase(&self, phase: &str, message: &str) {
        let mut status = self.status.lock().unwrap();
        status.phase = phase.into();
        status.message = message.into();
        status.error = None;
    }

    fn ready(&self, port: u16, owned: bool) {
        let mut status = self.status.lock().unwrap();
        status.phase = "ready".into();
        status.message = "Your workspace is ready.".into();
        status.error = None;
        status.origin = Some(origin(port));
        status.owned_backend = owned;
    }

    pub fn start(self: &Arc<Self>) {
        if self.stopping.load(Ordering::SeqCst)
            || self.status().phase == "ready"
            || self.booting.swap(true, Ordering::SeqCst)
        {
            return;
        }
        self.phase(
            "checking",
            "Opening your local workspace. If macOS asks, allow access to the Documents folder.",
        );
        let runtime = self.clone();
        thread::spawn(move || {
            runtime.stop_owned_backend();
            if let Err(message) = runtime.boot() {
                runtime.stop_owned_backend();
                let mut status = runtime.status.lock().unwrap();
                status.phase = "error".into();
                status.message = "Your workspace needs attention.".into();
                status.error = Some(message);
                status.origin = None;
                status.owned_backend = false;
            }
            runtime.booting.store(false, Ordering::SeqCst);
        });
    }

    fn boot(&self) -> Result<(), String> {
        fs::create_dir_all(self.log_path.parent().unwrap()).map_err(|_| "The local runtime folder could not be created. Check the workspace's permissions and available disk space.")?;
        let directory = self.log_path.parent().unwrap();
        let mode = fs::metadata(directory)
            .map_err(|_| {
                "The private runtime folder could not be checked. Check workspace permissions."
            })?
            .permissions()
            .mode()
            & 0o777;
        if mode != 0o700 {
            fs::set_permissions(directory, fs::Permissions::from_mode(0o700)).map_err(|_| {
                "The private runtime folder could not be secured. Check workspace permissions."
            })?;
        }
        self.log("Starting Chemistry Studio desktop runtime");
        for port in PORTS {
            if application_ready(port) {
                self.ready(port, false);
                self.log(&format!(
                    "Reusing verified Chemistry Studio at {}",
                    origin(port)
                ));
                return Ok(());
            }
        }
        let workspace = Path::new(WORKSPACE);
        let python = workspace.join(".venv/bin/python");
        let alembic = workspace.join(".venv/bin/alembic");
        if !python.is_file() || !alembic.is_file() {
            return Err("This local app needs its installed Python runtime. Restore the .venv folder in the Chemistry Studio workspace, then retry. See the desktop setup guide.".into());
        }
        if !self.frontend.join("index.html").is_file() {
            return Err("The packaged interface is missing. Rebuild or reinstall Chemistry Studio, then retry.".into());
        }
        let port = PORTS.into_iter().find(|port| port_available(*port))
            .ok_or("Both local app ports (8787 and 8788) are in use by another service. Quit the conflicting service, then retry.")?;
        self.check_running()?;
        self.phase("database", "Starting your local database…");
        let docker = docker_binary().ok_or("Docker Desktop is not installed in a supported location. Install or restore Docker Desktop, open it, then retry.")?;
        if !self.command_success(Command::new(&docker).arg("info"), Duration::from_secs(8))? {
            self.phase("database", "Opening Docker Desktop for the local database…");
            if !self.command_success(
                Command::new("/usr/bin/open").args(["-g", "-a", "Docker"]),
                Duration::from_secs(8),
            )? {
                return Err("Docker Desktop could not be opened. Open Docker Desktop from Applications, wait for its engine to start, then retry.".into());
            }
            let deadline = Instant::now() + Duration::from_secs(65);
            loop {
                self.check_running()?;
                if self
                    .command_success(Command::new(&docker).arg("info"), Duration::from_secs(5))?
                {
                    break;
                }
                if Instant::now() >= deadline {
                    return Err("Docker Desktop's engine is not ready. Open Docker Desktop and resolve its startup message, then retry. Your research data has not been changed.".into());
                }
                thread::sleep(Duration::from_secs(2));
            }
        }
        if !self.command_success(
            Command::new(&docker).args([
                "compose",
                "-f",
                "infra/local/compose.yaml",
                "up",
                "-d",
                "postgres",
            ]),
            Duration::from_secs(90),
        )? {
            return Err("The local database container could not start. Check Docker Desktop and available disk space, then retry. Details are in the runtime log.".into());
        }
        let deadline = Instant::now() + Duration::from_secs(40);
        loop {
            if self.command_success(
                Command::new(&docker).args([
                    "exec",
                    "chem-studio-postgres",
                    "pg_isready",
                    "-h",
                    "127.0.0.1",
                    "-U",
                    "studio",
                    "-d",
                    "studio",
                ]),
                Duration::from_secs(4),
            )? {
                break;
            }
            if Instant::now() >= deadline {
                return Err("The local database is still unavailable. Check Docker Desktop's chemistry database container, then retry.".into());
            }
            thread::sleep(Duration::from_secs(1));
        }
        self.phase("migrating", "Checking the research database schema…");
        if !self.command_success(
            Command::new(alembic).args([
                "-c",
                "services/studio-api/migrations/alembic.ini",
                "upgrade",
                "head",
            ]),
            Duration::from_secs(90),
        )? {
            return Err("The research database could not be prepared. Your existing data is retained. Check the runtime log and retry after resolving the reported migration error.".into());
        }
        self.check_running()?;
        self.phase("starting", "Opening the research service…");
        let mut command = Command::new(python);
        command
            .args([
                "-m",
                "uvicorn",
                "studio.api.app:create_app",
                "--factory",
                "--host",
                "127.0.0.1",
                "--port",
                &port.to_string(),
            ])
            .current_dir(workspace)
            .env("STUDIO_PORT", port.to_string())
            .env(
                "STUDIO_ALLOWED_ORIGINS",
                format!("{},http://localhost:{port}", origin(port)),
            )
            .env("STUDIO_DESKTOP_FRONTEND_DIR", &self.frontend)
            .env("STUDIO_DESKTOP_BUILD_ID", BUILD_ID)
            .env("STUDIO_VAULT_ROOT", workspace.join(".runtime/vault"))
            .env("PYTHONUNBUFFERED", "1");
        self.attach_log(&mut command)?;
        {
            let mut owned = self.child.lock().unwrap();
            self.check_running()?;
            let child = command.spawn().map_err(|_| "The Python research service could not start. Restore the installed .venv runtime, then retry.")?;
            *owned = Some(child);
        }
        let deadline = Instant::now() + Duration::from_secs(45);
        loop {
            self.check_running()?;
            if self
                .child
                .lock()
                .unwrap()
                .as_mut()
                .and_then(|child| child.try_wait().ok())
                .flatten()
                .is_some()
            {
                return Err("The research service stopped during startup. Check the runtime log, resolve the reported error, then retry.".into());
            }
            if application_ready(port) {
                self.ready(port, true);
                self.log(&format!("Owned backend ready at {}", origin(port)));
                return Ok(());
            }
            if Instant::now() >= deadline {
                return Err("The research service did not become ready. Check the runtime log and retry. No other running service has been stopped.".into());
            }
            thread::sleep(Duration::from_millis(350));
        }
    }

    fn check_running(&self) -> Result<(), String> {
        if self.stopping.load(Ordering::SeqCst) {
            Err("Startup cancelled because Chemistry Studio is closing.".into())
        } else {
            Ok(())
        }
    }

    fn log(&self, message: &str) {
        if let Ok(mut file) = self.open_log() {
            let _ = writeln!(file, "[desktop] {message}");
        }
    }

    fn open_log(&self) -> Result<File, String> {
        let file = OpenOptions::new().create(true).append(true).mode(0o600).open(&self.log_path)
            .map_err(|_| "The runtime log could not be written. Check available disk space and workspace permissions.")?;
        let mode = file
            .metadata()
            .map_err(|_| {
                "The private runtime log could not be checked. Check workspace permissions."
            })?
            .permissions()
            .mode()
            & 0o777;
        if mode != 0o600 {
            file.set_permissions(fs::Permissions::from_mode(0o600))
                .map_err(|_| {
                    "The private runtime log could not be secured. Check workspace permissions."
                })?;
        }
        Ok(file)
    }

    fn attach_log(&self, command: &mut Command) -> Result<(), String> {
        let file = self.open_log()?;
        command
            .stdout(Stdio::from(
                file.try_clone()
                    .map_err(|_| "The runtime log could not be opened.")?,
            ))
            .stderr(Stdio::from(file));
        Ok(())
    }

    fn command_success(&self, command: &mut Command, timeout: Duration) -> Result<bool, String> {
        self.check_running()?;
        command.current_dir(WORKSPACE);
        self.attach_log(command)?;
        let mut child = command.spawn().map_err(|_| "A required local runtime command could not start. Check the desktop setup guide and runtime log.")?;
        let deadline = Instant::now() + timeout;
        loop {
            if let Some(status) = child
                .try_wait()
                .map_err(|_| "Unable to check the local runtime process.")?
            {
                return Ok(status.success());
            }
            if self.stopping.load(Ordering::SeqCst) || Instant::now() >= deadline {
                let _ = child.kill();
                let _ = child.wait();
                self.check_running()?;
                return Ok(false);
            }
            thread::sleep(Duration::from_millis(150));
        }
    }

    pub fn ready_origin(&self) -> Result<Url, String> {
        let status = self.status();
        if status.phase != "ready" {
            return Err("The local workspace is not ready yet.".into());
        }
        let url = Url::parse(
            status
                .origin
                .as_deref()
                .ok_or("The local workspace has no verified address.")?,
        )
        .map_err(|_| "Invalid local workspace address.")?;
        let port = url.port().ok_or("Missing local workspace port.")?;
        if !PORTS.contains(&port) || !application_ready(port) {
            let mut state = self.status.lock().unwrap();
            state.phase = "error".into();
            state.error =
                Some("The local workspace is no longer responding. Please retry startup.".into());
            state.origin = None;
            return Err(
                "The local workspace is no longer responding. Please retry startup.".into(),
            );
        }
        Ok(url)
    }

    fn stop_owned_backend(&self) {
        if let Some(mut child) = self.child.lock().unwrap().take() {
            if child.try_wait().ok().flatten().is_none() {
                let _ = Command::new("/bin/kill")
                    .args(["-TERM", &child.id().to_string()])
                    .status();
                let deadline = Instant::now() + Duration::from_secs(3);
                while Instant::now() < deadline {
                    if child.try_wait().ok().flatten().is_some() {
                        return;
                    }
                    thread::sleep(Duration::from_millis(100));
                }
                let _ = child.kill();
            }
            let _ = child.wait();
        }
    }

    pub fn shutdown(&self) {
        self.stopping.store(true, Ordering::SeqCst);
        self.stop_owned_backend();
    }
}

fn origin(port: u16) -> String {
    format!("http://127.0.0.1:{port}")
}

fn port_available(port: u16) -> bool {
    TcpListener::bind(("127.0.0.1", port)).is_ok()
}

fn docker_binary() -> Option<PathBuf> {
    let mut paths = vec![
        PathBuf::from("/Applications/Docker.app/Contents/Resources/bin/docker"),
        PathBuf::from("/usr/local/bin/docker"),
        PathBuf::from("/opt/homebrew/bin/docker"),
    ];
    if let Some(home) = std::env::var_os("HOME") {
        paths.push(PathBuf::from(home).join(".docker/bin/docker"));
    }
    paths.into_iter().find(|path| path.is_file())
}

fn http_get(port: u16, path: &str) -> Option<(String, Vec<u8>)> {
    let address = SocketAddr::from(([127, 0, 0, 1], port));
    let mut stream = TcpStream::connect_timeout(&address, Duration::from_millis(500)).ok()?;
    stream.set_read_timeout(Some(Duration::from_secs(2))).ok()?;
    stream
        .set_write_timeout(Some(Duration::from_secs(1)))
        .ok()?;
    write!(
        stream,
        "GET {path} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nConnection: close\r\n\r\n"
    )
    .ok()?;
    let mut bytes = Vec::new();
    stream.take(32 * 1024).read_to_end(&mut bytes).ok()?;
    let boundary = bytes.windows(4).position(|window| window == b"\r\n\r\n")?;
    let headers = String::from_utf8(bytes[..boundary].to_vec()).ok()?;
    if !headers.starts_with("HTTP/1.1 200 ") && !headers.starts_with("HTTP/1.0 200 ") {
        return None;
    }
    Some((headers, bytes[boundary + 4..].to_vec()))
}

fn application_ready(port: u16) -> bool {
    let Some((_, body)) = http_get(port, "/api/desktop/runtime") else {
        return false;
    };
    let Ok(identity) = serde_json::from_slice::<serde_json::Value>(&body) else {
        return false;
    };
    if !matching_identity(&identity) {
        return false;
    }
    let Some((headers, body)) = http_get(port, "/") else {
        return false;
    };
    headers
        .to_ascii_lowercase()
        .contains("content-type: text/html")
        && body.windows(5).any(|window| window == b"<html")
}

fn matching_identity(identity: &serde_json::Value) -> bool {
    identity["application"] == "chemistry-studio"
        && identity["buildId"] == BUILD_ID
        && identity["desktop"] == true
        && identity["frontendAvailable"] == true
        && identity["databaseReady"] == true
}

pub fn is_bootstrap_origin(url: &Url) -> bool {
    (url.scheme() == "tauri" && url.host_str() == Some("localhost"))
        || (url.scheme() == "http"
            && url.host_str() == Some("tauri.localhost")
            && url.port().is_none())
}

pub fn is_internal_navigation(url: &Url) -> bool {
    is_bootstrap_origin(url)
        || (url.scheme() == "http"
            && url.host_str() == Some("127.0.0.1")
            && url.port().is_some_and(|port| PORTS.contains(&port))
            && url.username().is_empty()
            && url.password().is_none())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn runtime_commands_are_limited_to_bundled_origin() {
        assert!(is_bootstrap_origin(
            &Url::parse("tauri://localhost/index.html?desktop=boot").unwrap()
        ));
        assert!(!is_bootstrap_origin(
            &Url::parse("http://127.0.0.1:8788/").unwrap()
        ));
        assert!(!is_bootstrap_origin(
            &Url::parse("https://tauri.localhost/").unwrap()
        ));
    }
    #[test]
    fn navigation_accepts_only_exact_loopback_ports_and_asset_origin() {
        assert!(is_internal_navigation(
            &Url::parse("http://127.0.0.1:8788/tasks/example").unwrap()
        ));
        for raw in [
            "https://127.0.0.1:8788/",
            "http://127.0.0.1:8790/",
            "http://localhost:8788/",
            "http://evil.example:8788/",
            "http://user:pass@127.0.0.1:8788/",
        ] {
            assert!(!is_internal_navigation(&Url::parse(raw).unwrap()), "{raw}");
        }
    }
    #[test]
    fn port_in_use_is_not_selected_for_an_owned_backend() {
        let listener = TcpListener::bind(("127.0.0.1", 0)).unwrap();
        assert!(!port_available(listener.local_addr().unwrap().port()));
    }

    #[test]
    fn only_this_bundles_build_identity_can_be_reused() {
        let mut identity = serde_json::json!({
            "application": "chemistry-studio", "desktop": true,
            "frontendAvailable": true, "databaseReady": true, "buildId": BUILD_ID
        });
        assert!(matching_identity(&identity));
        identity["buildId"] = serde_json::Value::String("older-desktop-release".into());
        assert!(!matching_identity(&identity));
        identity.as_object_mut().unwrap().remove("buildId");
        assert!(!matching_identity(&identity));
    }
    #[test]
    fn quitting_stops_only_the_backend_child_owned_by_this_app() {
        let mut unrelated = Command::new("/bin/sleep").arg("30").spawn().unwrap();
        let owned = Command::new("/bin/sleep").arg("30").spawn().unwrap();
        let runtime = LocalRuntime::new(PathBuf::new());
        *runtime.child.lock().unwrap() = Some(owned);
        runtime.shutdown();
        assert!(runtime.child.lock().unwrap().is_none());
        assert!(unrelated.try_wait().unwrap().is_none());
        unrelated.kill().unwrap();
        unrelated.wait().unwrap();
    }

    #[test]
    fn healthy_unrelated_http_server_is_never_accepted_as_the_app() {
        let listener = TcpListener::bind(("127.0.0.1", 0)).unwrap();
        let port = listener.local_addr().unwrap().port();
        let server = thread::spawn(move || {
            let (mut client, _) = listener.accept().unwrap();
            let mut request = [0_u8; 1024];
            let _ = client.read(&mut request);
            let body = r#"{"status":"ok","application":"another-app","desktop":true,"frontendAvailable":true,"databaseReady":true}"#;
            write!(client, "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}", body.len()).unwrap();
        });
        assert!(!application_ready(port));
        server.join().unwrap();
    }
}
