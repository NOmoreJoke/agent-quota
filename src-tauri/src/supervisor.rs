use crate::contract::{validate_request, validate_response};
use crate::protocol::{Sequence, read_frame, write_frame};
use hmac::{Hmac, Mac};
use serde_json::{Value, json};
use sha2::Sha256;
use std::fs::{self, File, OpenOptions};
use std::io::{Read, Write};
use std::os::fd::AsRawFd;
use std::os::unix::fs::{MetadataExt, OpenOptionsExt, PermissionsExt};
use std::os::unix::net::UnixStream;
use std::os::unix::process::CommandExt;
use std::path::Path;
use std::process::{Child, ChildStdin, ChildStdout, Command, Stdio};
use std::sync::mpsc;
use std::time::{Duration, Instant};

const SECRET_FD: i32 = 3;
const SECRET_BYTES: usize = 32;
const TERM_GRACE: Duration = Duration::from_millis(200);

type HmacSha256 = Hmac<Sha256>;

#[derive(Debug, thiserror::Error)]
pub enum SupervisorError {
    #[error("sidecar path is not an absolute executable file")]
    InvalidExecutable,
    #[error("sidecar process could not be started")]
    Spawn,
    #[error("sidecar I/O failed")]
    Io,
    #[error("sidecar protocol failed")]
    Protocol,
    #[error("sidecar contract failed")]
    Contract,
    #[error("sidecar outcome is unknown")]
    OutcomeUnknown,
    #[error("sidecar process could not be reaped")]
    Reap,
}

fn proof(secret: &[u8], value: &Value) -> Result<String, SupervisorError> {
    let mut mac = HmacSha256::new_from_slice(secret).map_err(|_| SupervisorError::Protocol)?;
    let body = serde_json::to_vec(value).map_err(|_| SupervisorError::Protocol)?;
    mac.update(&body);
    Ok(mac
        .finalize()
        .into_bytes()
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect())
}

fn secret() -> Result<[u8; SECRET_BYTES], SupervisorError> {
    let mut value = [0_u8; SECRET_BYTES];
    File::open("/dev/urandom")
        .and_then(|mut file| file.read_exact(&mut value))
        .map_err(|_| SupervisorError::Io)?;
    Ok(value)
}

fn check_executable(path: &Path) -> Result<std::path::PathBuf, SupervisorError> {
    if !path.is_absolute() {
        return Err(SupervisorError::InvalidExecutable);
    }
    let path_metadata =
        fs::symlink_metadata(path).map_err(|_| SupervisorError::InvalidExecutable)?;
    let mode = path_metadata.permissions().mode() & 0o7777;
    let effective_uid = unsafe { libc::geteuid() };
    if path_metadata.file_type().is_symlink()
        || !path_metadata.is_file()
        || mode & 0o100 == 0
        || mode & 0o022 != 0
        || !matches!(path_metadata.uid(), 0) && path_metadata.uid() != effective_uid
    {
        return Err(SupervisorError::InvalidExecutable);
    }
    let canonical = path
        .canonicalize()
        .map_err(|_| SupervisorError::InvalidExecutable)?;
    let file = OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW)
        .open(&canonical)
        .map_err(|_| SupervisorError::InvalidExecutable)?;
    let opened_metadata = file
        .metadata()
        .map_err(|_| SupervisorError::InvalidExecutable)?;
    let final_metadata =
        fs::symlink_metadata(&canonical).map_err(|_| SupervisorError::InvalidExecutable)?;
    if path_metadata.dev() != opened_metadata.dev()
        || path_metadata.ino() != opened_metadata.ino()
        || opened_metadata.dev() != final_metadata.dev()
        || opened_metadata.ino() != final_metadata.ino()
        || opened_metadata.len() != final_metadata.len()
        || opened_metadata.mode() != final_metadata.mode()
        || opened_metadata.uid() != final_metadata.uid()
    {
        return Err(SupervisorError::InvalidExecutable);
    }
    Ok(canonical)
}

pub struct SidecarSupervisor {
    child: Child,
    stdin: ChildStdin,
    stdout: Option<ChildStdout>,
    sequence: Sequence,
    secret: [u8; SECRET_BYTES],
}

impl SidecarSupervisor {
    pub fn spawn(executable: &Path, arguments: &[String]) -> Result<Self, SupervisorError> {
        let executable = check_executable(executable)?;
        let secret = secret()?;
        let (mut parent_secret, child_secret) =
            UnixStream::pair().map_err(|_| SupervisorError::Io)?;
        let child_secret_fd = child_secret.as_raw_fd();
        let mut command = Command::new(executable);
        command
            .args(arguments)
            .env_clear()
            .env("AQ_SESSION_SECRET_FD", SECRET_FD.to_string())
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null());
        // SAFETY: only async-signal-safe libc calls run between fork and exec.
        unsafe {
            command.pre_exec(move || {
                if child_secret_fd != SECRET_FD && libc::dup2(child_secret_fd, SECRET_FD) == -1 {
                    return Err(std::io::Error::last_os_error());
                }
                if libc::fcntl(SECRET_FD, libc::F_SETFD, 0) == -1 {
                    return Err(std::io::Error::last_os_error());
                }
                Ok(())
            });
        }
        let mut child = command.spawn().map_err(|_| SupervisorError::Spawn)?;
        drop(child_secret);
        parent_secret
            .write_all(&secret)
            .map_err(|_| SupervisorError::Io)?;
        parent_secret
            .shutdown(std::net::Shutdown::Write)
            .map_err(|_| SupervisorError::Io)?;
        let stdin = child.stdin.take().ok_or(SupervisorError::Spawn)?;
        let stdout = child.stdout.take().ok_or(SupervisorError::Spawn)?;
        Ok(Self {
            child,
            stdin,
            stdout: Some(stdout),
            sequence: Sequence::default(),
            secret,
        })
    }

    pub fn call(
        &mut self,
        command_id: &str,
        payload: Value,
        remaining_budget_ns: u64,
    ) -> Result<Value, SupervisorError> {
        self.call_checked(command_id, payload, remaining_budget_ns, true)
    }

    pub fn call_internal(
        &mut self,
        command_id: &str,
        payload: Value,
        remaining_budget_ns: u64,
    ) -> Result<Value, SupervisorError> {
        if !command_id.starts_with("host_internal.") {
            return Err(SupervisorError::Contract);
        }
        self.call_checked(command_id, payload, remaining_budget_ns, false)
    }

    fn call_checked(
        &mut self,
        command_id: &str,
        payload: Value,
        remaining_budget_ns: u64,
        renderer_contract: bool,
    ) -> Result<Value, SupervisorError> {
        if renderer_contract {
            validate_request(command_id, &payload).map_err(|_| SupervisorError::Contract)?;
        }
        let request_id = self
            .sequence
            .next_request(
                remaining_budget_ns,
                command_id.to_owned(),
                payload.clone(),
                String::new(),
            )
            .map_err(|_| SupervisorError::Protocol)?
            .request_id;
        let unsigned = json!({
            "command_id": command_id,
            "payload": payload,
            "remaining_budget_ns": remaining_budget_ns,
            "request_id": request_id
        });
        let request = json!({
            "command_id": command_id,
            "payload": unsigned["payload"],
            "remaining_budget_ns": remaining_budget_ns,
            "request_id": request_id,
            "session_proof": proof(&self.secret, &unsigned)?
        });
        write_frame(&mut self.stdin, &request).map_err(|_| SupervisorError::Io)?;

        let mut stdout = self.stdout.take().ok_or(SupervisorError::OutcomeUnknown)?;
        let (sender, receiver) = mpsc::sync_channel(1);
        std::thread::spawn(move || {
            let result = read_frame(&mut stdout);
            let _ = sender.send((result, stdout));
        });
        let timeout = Duration::from_nanos(remaining_budget_ns);
        let received = receiver.recv_timeout(timeout);
        let (response, stdout) = match received {
            Ok(value) => value,
            Err(_) => {
                self.terminate_and_reap()?;
                return Err(SupervisorError::OutcomeUnknown);
            }
        };
        self.stdout = Some(stdout);
        let response = response.map_err(|_| SupervisorError::OutcomeUnknown)?;
        let object = response
            .as_object()
            .ok_or(SupervisorError::OutcomeUnknown)?;
        if object.len() != 3
            || !object.contains_key("request_id")
            || !object.contains_key("response")
            || !object.contains_key("session_proof")
            || object["request_id"].as_u64() != Some(request_id)
        {
            return Err(SupervisorError::OutcomeUnknown);
        }
        let unsigned_response = json!({
            "request_id": request_id,
            "response": object["response"]
        });
        let expected =
            proof(&self.secret, &unsigned_response).map_err(|_| SupervisorError::OutcomeUnknown)?;
        if object["session_proof"].as_str() != Some(expected.as_str()) {
            return Err(SupervisorError::OutcomeUnknown);
        }
        if renderer_contract {
            validate_response(command_id, object["response"].clone())
                .map_err(|_| SupervisorError::OutcomeUnknown)
        } else {
            object["response"]
                .as_object()
                .ok_or(SupervisorError::OutcomeUnknown)?;
            Ok(object["response"].clone())
        }
    }

    pub fn terminate_and_reap(&mut self) -> Result<(), SupervisorError> {
        if self
            .child
            .try_wait()
            .map_err(|_| SupervisorError::Reap)?
            .is_some()
        {
            return Ok(());
        }
        // SAFETY: the PID is owned by this Child and SIGTERM is a valid signal.
        unsafe {
            libc::kill(self.child.id() as i32, libc::SIGTERM);
        }
        let deadline = Instant::now() + TERM_GRACE;
        while Instant::now() < deadline {
            if self
                .child
                .try_wait()
                .map_err(|_| SupervisorError::Reap)?
                .is_some()
            {
                return Ok(());
            }
            std::thread::sleep(Duration::from_millis(10));
        }
        self.child.kill().map_err(|_| SupervisorError::Reap)?;
        self.child.wait().map_err(|_| SupervisorError::Reap)?;
        Ok(())
    }
}

impl Drop for SidecarSupervisor {
    fn drop(&mut self) {
        let _ = self.terminate_and_reap();
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn executable_must_be_absolute_and_existing() {
        assert!(check_executable(Path::new("python")).is_err());
        assert!(check_executable(Path::new("/definitely/not/here")).is_err());
        assert!(check_executable(Path::new("/bin/sh")).is_ok());
    }

    #[test]
    fn executable_rejects_symlink_and_writable_mode() {
        use std::os::unix::fs::symlink;

        let directory = tempfile::tempdir().unwrap();
        let executable = directory.path().join("sidecar");
        fs::write(&executable, "#!/bin/sh\nexit 0\n").unwrap();
        let mut permissions = fs::metadata(&executable).unwrap().permissions();
        permissions.set_mode(0o755);
        fs::set_permissions(&executable, permissions).unwrap();
        let link = directory.path().join("sidecar-link");
        symlink(&executable, &link).unwrap();
        assert!(check_executable(&link).is_err());

        let mut permissions = fs::metadata(&executable).unwrap().permissions();
        permissions.set_mode(0o775);
        fs::set_permissions(&executable, permissions).unwrap();
        assert!(check_executable(&executable).is_err());
    }

    #[test]
    fn proof_is_stable_and_sensitive() {
        let secret = [7_u8; SECRET_BYTES];
        assert_eq!(
            proof(&secret, &json!({"b": 2, "a": 1})).unwrap(),
            proof(&secret, &json!({"a": 1, "b": 2})).unwrap()
        );
        assert_ne!(
            proof(&secret, &json!({"a": 1})).unwrap(),
            proof(&secret, &json!({"a": 2})).unwrap()
        );
    }

    #[test]
    fn real_python_sidecar_round_trip_when_test_executable_is_available() {
        let Some(executable) = std::env::var_os("AQ_SIDECAR_TEST_EXECUTABLE") else {
            return;
        };
        let data_root = tempfile::tempdir().expect("temporary data root");
        let canonical_root = data_root
            .path()
            .canonicalize()
            .expect("canonical data root");
        let arguments = vec![
            "--data-root".to_owned(),
            canonical_root.to_string_lossy().into_owned(),
        ];
        let mut supervisor = SidecarSupervisor::spawn(Path::new(&executable), &arguments)
            .expect("spawn real sidecar");
        let response = supervisor
            .call("bootstrap_state", json!({}), 2_000_000_000)
            .expect("sidecar response");
        assert_eq!(response["status"], "ok");
        supervisor.terminate_and_reap().expect("reap real sidecar");
    }

    #[test]
    fn real_python_sidecar_persists_native_account_and_commits_purge() {
        let Some(executable) = std::env::var_os("AQ_SIDECAR_TEST_EXECUTABLE") else {
            return;
        };
        let data_root = tempfile::tempdir().expect("temporary data root");
        let canonical_root = data_root
            .path()
            .canonicalize()
            .expect("canonical data root");
        let arguments = vec![
            "--data-root".to_owned(),
            canonical_root.to_string_lossy().into_owned(),
        ];
        {
            let mut supervisor = SidecarSupervisor::spawn(Path::new(&executable), &arguments)
                .expect("spawn real sidecar");
            let committed = supervisor
                .call_internal(
                    "host_internal.credential_commit",
                    json!({
                        "credential_reference":
                            "credential-00000000-0000-4000-8000-000000000001",
                        "expected_generation": null,
                        "principal_ref": null,
                        "purpose": "create-credential-reference"
                    }),
                    2_000_000_000,
                )
                .expect("commit credential reference");
            assert_eq!(committed["status"], "committed");
            supervisor.terminate_and_reap().expect("reap sidecar");
        }
        let mut supervisor = SidecarSupervisor::spawn(Path::new(&executable), &arguments)
            .expect("restart real sidecar");
        let accounts = supervisor
            .call(
                "accounts_read",
                json!({"scope_ref": "scope-all"}),
                2_000_000_000,
            )
            .expect("read persisted accounts");
        assert_eq!(accounts["accounts"].as_array().unwrap().len(), 1);
        let plan = supervisor
            .call_internal(
                "host_internal.destructive_prepare",
                json!({
                    "operation_intent": "purge",
                    "opaque_selection_handle": "selection-all-local-data"
                }),
                2_000_000_000,
            )
            .expect("prepare purge");
        let purge = supervisor
            .call_internal(
                "host_internal.destructive_commit",
                json!({
                    "digest": plan["digest"],
                    "generation": plan["generation"],
                    "nonce": plan["nonce"],
                    "plan_id": plan["plan_id"],
                    "user_presence_token": "00000000-0000-4000-8000-000000000001"
                }),
                2_000_000_000,
            )
            .expect("commit purge");
        assert_eq!(purge["status"], "committed");
        assert_eq!(purge["cleanup_references"].as_array().unwrap().len(), 1);
        let acknowledged = supervisor
            .call_internal(
                "host_internal.cleanup_ack",
                json!({"references": purge["cleanup_references"]}),
                2_000_000_000,
            )
            .expect("acknowledge Keychain cleanup");
        assert_eq!(acknowledged["status"], "acknowledged");
        let empty = supervisor
            .call(
                "accounts_read",
                json!({"scope_ref": "scope-all"}),
                2_000_000_000,
            )
            .expect("read empty accounts");
        assert!(empty["accounts"].as_array().unwrap().is_empty());
        supervisor.terminate_and_reap().expect("reap sidecar");
    }

    #[test]
    fn hanging_child_times_out_and_is_reaped_when_python_is_available() {
        let Some(python) = std::env::var_os("AQ_PYTHON_TEST_EXECUTABLE") else {
            return;
        };
        let fixture = Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("tests/fixtures/hanging_sidecar.py")
            .to_string_lossy()
            .into_owned();
        let mut supervisor =
            SidecarSupervisor::spawn(Path::new(&python), &[fixture]).expect("spawn hanging child");
        assert!(matches!(
            supervisor.call("bootstrap_state", json!({}), 20_000_000),
            Err(SupervisorError::OutcomeUnknown)
        ));
        assert!(supervisor.child.try_wait().expect("child state").is_some());
    }
}
