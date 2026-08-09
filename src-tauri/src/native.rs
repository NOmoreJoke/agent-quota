use serde::Deserialize;
use serde_json::Value;
use std::fs::{self, OpenOptions};
use std::io::{Read, Write};
use std::os::unix::fs::{MetadataExt, OpenOptionsExt, PermissionsExt};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::{Mutex, TryLockError, mpsc};
use std::thread;
use std::time::{Duration, Instant};

const MAX_REQUEST_BYTES: usize = 4096;
const MAX_RESPONSE_BYTES: u64 = 384 * 1024;
const CREDENTIAL_TIMEOUT: Duration = Duration::from_secs(120);
const DESTRUCTIVE_TIMEOUT: Duration = Duration::from_secs(60);
const CLEANUP_TIMEOUT: Duration = Duration::from_secs(5);
const PROVIDER_TIMEOUT: Duration = Duration::from_secs(25);
const DIALOG_COOLDOWN: Duration = Duration::from_millis(750);
const TERM_GRACE: Duration = Duration::from_millis(200);

#[derive(Debug, thiserror::Error)]
pub enum NativeError {
    #[error("native helper is unavailable")]
    Unavailable,
    #[error("native dialog is already active or cooling down")]
    Busy,
    #[error("native helper protocol failed")]
    Protocol,
    #[error("native helper timed out")]
    Timeout,
    #[error("native helper process failed")]
    Process,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct NativeResponse {
    pub status: String,
    pub opaque_reference: Option<String>,
    pub error_code: Option<String>,
    pub user_presence_token: Option<String>,
    pub provider: Option<String>,
    pub http_status: Option<u16>,
    pub body_base64: Option<String>,
}

#[derive(Debug)]
struct DialogState {
    active: bool,
    next_allowed: Instant,
}

pub struct NativeHost {
    executable: Option<PathBuf>,
    gate: Mutex<DialogState>,
    provider_gate: Mutex<()>,
}

impl NativeHost {
    pub fn new(executable: Option<PathBuf>) -> Self {
        Self {
            executable,
            gate: Mutex::new(DialogState {
                active: false,
                next_allowed: Instant::now(),
            }),
            provider_gate: Mutex::new(()),
        }
    }

    pub fn credential(&self, request: Value) -> Result<NativeResponse, NativeError> {
        self.run_gated(request, CREDENTIAL_TIMEOUT)
    }

    pub fn destructive(&self, request: Value) -> Result<NativeResponse, NativeError> {
        self.run_gated(request, DESTRUCTIVE_TIMEOUT)
    }

    pub fn provider_fetch(
        &self,
        reference: &str,
        provider: &str,
        timeout: Duration,
    ) -> Result<NativeResponse, NativeError> {
        // Provider helpers are separate processes. Serializing their full fetch path prevents
        // two expired Kimi OAuth bundles from rotating the same refresh token concurrently.
        let timeout = timeout.min(PROVIDER_TIMEOUT);
        let deadline = Instant::now() + timeout;
        let _provider_guard = loop {
            match self.provider_gate.try_lock() {
                Ok(guard) => break guard,
                Err(TryLockError::Poisoned(_)) => return Err(NativeError::Process),
                Err(TryLockError::WouldBlock) => {
                    if Instant::now() >= deadline {
                        return Err(NativeError::Timeout);
                    }
                    thread::sleep(Duration::from_millis(10));
                }
            }
        };
        let remaining = deadline.saturating_duration_since(Instant::now());
        if remaining.is_zero() {
            return Err(NativeError::Timeout);
        }
        self.run(
            serde_json::json!({
                "action": "provider-fetch",
                "opaqueReference": reference,
                "provider": provider
            }),
            remaining,
        )
    }

    pub fn delete_reference(&self, reference: &str) -> Result<(), NativeError> {
        let response = self.run(
            serde_json::json!({
                "action": "keychain-delete",
                "opaqueReference": reference
            }),
            CLEANUP_TIMEOUT,
        )?;
        if matches!(response.status.as_str(), "deleted" | "not-found") {
            Ok(())
        } else {
            Err(NativeError::Process)
        }
    }

    fn run_gated(&self, request: Value, timeout: Duration) -> Result<NativeResponse, NativeError> {
        {
            let mut state = self.gate.lock().map_err(|_| NativeError::Busy)?;
            if state.active || Instant::now() < state.next_allowed {
                return Err(NativeError::Busy);
            }
            state.active = true;
        }
        let result = self.run(request, timeout);
        if let Ok(mut state) = self.gate.lock() {
            state.active = false;
            state.next_allowed = Instant::now() + DIALOG_COOLDOWN;
        }
        result
    }

    fn run(&self, request: Value, timeout: Duration) -> Result<NativeResponse, NativeError> {
        let path = self.executable.as_deref().ok_or(NativeError::Unavailable)?;
        let path = check_executable(path)?;
        let mut body = serde_json::to_vec(&request).map_err(|_| NativeError::Protocol)?;
        if body.is_empty() || body.len() >= MAX_REQUEST_BYTES || body.contains(&b'\n') {
            return Err(NativeError::Protocol);
        }
        body.push(b'\n');
        let mut child = Command::new(path)
            .env_clear()
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .spawn()
            .map_err(|_| NativeError::Process)?;
        if let Some(mut stdin) = child.stdin.take() {
            if stdin.write_all(&body).is_err() {
                terminate(&mut child);
                return Err(NativeError::Process);
            }
        } else {
            terminate(&mut child);
            return Err(NativeError::Process);
        }
        let Some(stdout) = child.stdout.take() else {
            terminate(&mut child);
            return Err(NativeError::Process);
        };
        let (sender, receiver) = mpsc::sync_channel(1);
        thread::spawn(move || {
            let mut bytes = Vec::new();
            let result = stdout.take(MAX_RESPONSE_BYTES + 1).read_to_end(&mut bytes);
            let _ = sender.send((result, bytes));
        });
        let (read_result, bytes) = match receiver.recv_timeout(timeout) {
            Ok(result) => result,
            Err(_) => {
                terminate(&mut child);
                return Err(NativeError::Timeout);
            }
        };
        if read_result.is_err() {
            terminate(&mut child);
            return Err(NativeError::Process);
        }
        let status = child.wait().map_err(|_| NativeError::Process)?;
        if !status.success()
            || bytes.is_empty()
            || bytes.len() > MAX_RESPONSE_BYTES as usize
            || bytes.iter().filter(|byte| **byte == b'\n').count() != 1
            || bytes.last() != Some(&b'\n')
        {
            return Err(NativeError::Protocol);
        }
        serde_json::from_slice(&bytes[..bytes.len() - 1]).map_err(|_| NativeError::Protocol)
    }
}

#[cfg(feature = "development-overrides")]
pub fn helper_path(resource_dir: Option<PathBuf>) -> Option<PathBuf> {
    if let Some(path) = std::env::var_os("AQ_NATIVE_HELPER_EXECUTABLE") {
        return Some(PathBuf::from(path));
    }
    resource_dir.map(|directory| {
        directory
            .join("native-helper")
            .join("AgentQuotaNative.app")
            .join("Contents")
            .join("MacOS")
            .join("AgentQuotaNative")
    })
}

fn check_executable(path: &Path) -> Result<PathBuf, NativeError> {
    if !path.is_absolute() {
        return Err(NativeError::Unavailable);
    }
    let path_metadata = fs::symlink_metadata(path).map_err(|_| NativeError::Unavailable)?;
    let mode = path_metadata.permissions().mode() & 0o7777;
    let effective_uid = unsafe { libc::geteuid() };
    if path_metadata.file_type().is_symlink()
        || !path_metadata.is_file()
        || mode & 0o100 == 0
        || mode & 0o022 != 0
        || !matches!(path_metadata.uid(), 0) && path_metadata.uid() != effective_uid
    {
        return Err(NativeError::Unavailable);
    }
    let canonical = path.canonicalize().map_err(|_| NativeError::Unavailable)?;
    let file = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW)
        .open(&canonical)
        .map_err(|_| NativeError::Unavailable)?;
    let opened_metadata = file.metadata().map_err(|_| NativeError::Unavailable)?;
    let final_metadata = fs::symlink_metadata(&canonical).map_err(|_| NativeError::Unavailable)?;
    if path_metadata.dev() != opened_metadata.dev()
        || path_metadata.ino() != opened_metadata.ino()
        || opened_metadata.dev() != final_metadata.dev()
        || opened_metadata.ino() != final_metadata.ino()
        || opened_metadata.len() != final_metadata.len()
        || opened_metadata.mode() != final_metadata.mode()
        || opened_metadata.uid() != final_metadata.uid()
    {
        return Err(NativeError::Unavailable);
    }
    Ok(canonical)
}

fn terminate(child: &mut Child) {
    if child.try_wait().ok().flatten().is_some() {
        return;
    }
    // SAFETY: the PID is owned by this Child and SIGTERM is a valid signal.
    unsafe {
        libc::kill(child.id() as i32, libc::SIGTERM);
    }
    let deadline = Instant::now() + TERM_GRACE;
    while Instant::now() < deadline {
        if child.try_wait().ok().flatten().is_some() {
            return;
        }
        thread::sleep(Duration::from_millis(10));
    }
    let _ = child.kill();
    let _ = child.wait();
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn executable_must_be_absolute_regular_and_executable() {
        assert!(check_executable(Path::new("relative")).is_err());
        assert!(check_executable(Path::new("/definitely/missing")).is_err());
        assert!(check_executable(Path::new("/bin/sh")).is_ok());
    }

    #[test]
    fn executable_rejects_symlink_and_writable_mode() {
        use std::os::unix::fs::symlink;

        let directory = tempfile::tempdir().unwrap();
        let executable = directory.path().join("helper");
        fs::write(&executable, "#!/bin/sh\nexit 0\n").unwrap();
        let mut permissions = fs::metadata(&executable).unwrap().permissions();
        permissions.set_mode(0o755);
        fs::set_permissions(&executable, permissions).unwrap();
        let link = directory.path().join("helper-link");
        symlink(&executable, &link).unwrap();
        assert!(check_executable(&link).is_err());

        let mut permissions = fs::metadata(&executable).unwrap().permissions();
        permissions.set_mode(0o757);
        fs::set_permissions(&executable, permissions).unwrap();
        assert!(check_executable(&executable).is_err());
    }

    #[test]
    fn gate_rejects_overlap_and_cooldown() {
        let host = NativeHost::new(None);
        {
            let mut state = host.gate.lock().unwrap();
            state.active = true;
        }
        assert!(matches!(
            host.credential(serde_json::json!({})),
            Err(NativeError::Busy)
        ));
        {
            let mut state = host.gate.lock().unwrap();
            state.active = false;
            state.next_allowed = Instant::now() + Duration::from_secs(1);
        }
        assert!(matches!(
            host.destructive(serde_json::json!({})),
            Err(NativeError::Busy)
        ));
    }

    #[test]
    fn native_response_rejects_unknown_fields() {
        let invalid = br#"{"status":"cancelled","opaqueReference":null,"errorCode":null,"userPresenceToken":null,"extra":true}"#;
        assert!(serde_json::from_slice::<NativeResponse>(invalid).is_err());
    }

    #[test]
    fn helper_supervisor_accepts_one_closed_bounded_response() {
        let directory = tempfile::tempdir().unwrap();
        let executable = directory.path().join("fixture-helper");
        fs::write(
            &executable,
            "#!/bin/sh\nread request\nprintf '%s\\n' '{\"status\":\"reference-created\",\"opaqueReference\":\"credential-00000000-0000-4000-8000-000000000001\"}'\n",
        )
        .unwrap();
        let mut permissions = fs::metadata(&executable).unwrap().permissions();
        permissions.set_mode(0o700);
        fs::set_permissions(&executable, permissions).unwrap();
        let host = NativeHost::new(Some(executable));
        let response = host
            .credential(serde_json::json!({
                "action": "credential",
                "dialogPurpose": "create-credential-reference"
            }))
            .unwrap();
        assert_eq!(response.status, "reference-created");
        assert_eq!(
            response.opaque_reference.as_deref(),
            Some("credential-00000000-0000-4000-8000-000000000001")
        );
    }

    #[test]
    fn provider_fetches_are_single_flight_across_helper_processes() {
        use std::sync::{Arc, Barrier};

        let directory = tempfile::tempdir().unwrap();
        let executable = directory.path().join("fixture-helper");
        let active = directory.path().join("active");
        let overlap = directory.path().join("overlap");
        fs::write(
            &executable,
            format!(
                "#!/bin/sh\nread request\nif ! /bin/mkdir '{}'; then /usr/bin/touch '{}'; fi\n/bin/sleep 1\n/bin/rmdir '{}' 2>/dev/null || true\nprintf '%s\\n' '{{\"status\":\"provider-response\",\"provider\":\"deepseek\",\"httpStatus\":200,\"bodyBase64\":\"e30=\"}}'\n",
                active.display(),
                overlap.display(),
                active.display()
            ),
        )
        .unwrap();
        let mut permissions = fs::metadata(&executable).unwrap().permissions();
        permissions.set_mode(0o700);
        fs::set_permissions(&executable, permissions).unwrap();

        let host = Arc::new(NativeHost::new(Some(executable)));
        let barrier = Arc::new(Barrier::new(3));
        let mut threads = Vec::new();
        for _ in 0..2 {
            let host = Arc::clone(&host);
            let barrier = Arc::clone(&barrier);
            threads.push(thread::spawn(move || {
                barrier.wait();
                host.provider_fetch(
                    "credential-00000000-0000-4000-8000-000000000001",
                    "deepseek",
                    Duration::from_secs(5),
                )
                .unwrap();
            }));
        }
        barrier.wait();
        for thread in threads {
            thread.join().unwrap();
        }
        assert!(!overlap.exists());
    }

    #[test]
    fn provider_gate_wait_respects_the_caller_deadline() {
        let host = NativeHost::new(None);
        let _guard = host.provider_gate.lock().unwrap();
        let started = Instant::now();
        let result = host.provider_fetch(
            "credential-00000000-0000-4000-8000-000000000001",
            "deepseek",
            Duration::from_millis(20),
        );
        assert!(matches!(result, Err(NativeError::Timeout)));
        assert!(started.elapsed() < Duration::from_millis(250));
    }

    #[test]
    fn helper_timeout_uses_term_kill_and_reap() {
        let directory = tempfile::tempdir().unwrap();
        let executable = directory.path().join("hanging-helper");
        fs::write(&executable, "#!/bin/sh\ntrap '' TERM\nsleep 5\n").unwrap();
        let mut permissions = fs::metadata(&executable).unwrap().permissions();
        permissions.set_mode(0o700);
        fs::set_permissions(&executable, permissions).unwrap();
        let host = NativeHost::new(Some(executable));
        let result = host.run(
            serde_json::json!({"action": "test"}),
            Duration::from_millis(10),
        );
        assert!(matches!(result, Err(NativeError::Timeout)));
    }
}
