use serde::Deserialize;
use serde_json::Value;
use std::fs;
use std::io::{Read, Write};
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::{Mutex, mpsc};
use std::thread;
use std::time::{Duration, Instant};

const MAX_REQUEST_BYTES: usize = 4096;
const MAX_RESPONSE_BYTES: u64 = 4096;
const CREDENTIAL_TIMEOUT: Duration = Duration::from_secs(120);
const DESTRUCTIVE_TIMEOUT: Duration = Duration::from_secs(60);
const CLEANUP_TIMEOUT: Duration = Duration::from_secs(5);
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
}

#[derive(Debug)]
struct DialogState {
    active: bool,
    next_allowed: Instant,
}

pub struct NativeHost {
    executable: Option<PathBuf>,
    gate: Mutex<DialogState>,
}

impl NativeHost {
    pub fn new(executable: Option<PathBuf>) -> Self {
        Self {
            executable,
            gate: Mutex::new(DialogState {
                active: false,
                next_allowed: Instant::now(),
            }),
        }
    }

    pub fn credential(&self, request: Value) -> Result<NativeResponse, NativeError> {
        self.run_gated(request, CREDENTIAL_TIMEOUT)
    }

    pub fn destructive(&self, request: Value) -> Result<NativeResponse, NativeError> {
        self.run_gated(request, DESTRUCTIVE_TIMEOUT)
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

    pub fn prune_references(&self, retained_references: &[&str]) -> Result<(), NativeError> {
        let response = self.run(
            serde_json::json!({
                "action": "keychain-prune",
                "retainedReferences": retained_references
            }),
            CLEANUP_TIMEOUT,
        )?;
        if response.status == "pruned" {
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
        check_executable(path)?;
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

pub fn helper_path(resource_dir: Option<PathBuf>) -> Option<PathBuf> {
    #[cfg(debug_assertions)]
    if let Some(path) = std::env::var_os("AQ_NATIVE_HELPER_EXECUTABLE") {
        return Some(PathBuf::from(path));
    }
    resource_dir.map(|directory| directory.join("agent-quota-native"))
}

fn check_executable(path: &Path) -> Result<(), NativeError> {
    if !path.is_absolute() {
        return Err(NativeError::Unavailable);
    }
    let metadata = fs::symlink_metadata(path).map_err(|_| NativeError::Unavailable)?;
    if metadata.file_type().is_symlink()
        || !metadata.is_file()
        || metadata.permissions().mode() & 0o111 == 0
    {
        return Err(NativeError::Unavailable);
    }
    Ok(())
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
    fn helper_supervisor_accepts_closed_prune_response() {
        let directory = tempfile::tempdir().unwrap();
        let executable = directory.path().join("fixture-helper");
        fs::write(
            &executable,
            "#!/bin/sh\nread request\nprintf '%s\\n' '{\"status\":\"pruned\"}'\n",
        )
        .unwrap();
        let mut permissions = fs::metadata(&executable).unwrap().permissions();
        permissions.set_mode(0o700);
        fs::set_permissions(&executable, permissions).unwrap();
        let host = NativeHost::new(Some(executable));
        host.prune_references(&["credential-00000000-0000-4000-8000-000000000001"])
            .unwrap();
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
