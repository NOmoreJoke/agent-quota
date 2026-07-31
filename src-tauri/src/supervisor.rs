use crate::contract::{validate_request, validate_response};
use crate::protocol::{ProtocolError, Sequence, read_frame, write_frame};
use hmac::{Hmac, Mac};
use serde_json::{Value, json};
use sha2::Sha256;
use std::fs::File;
use std::io::{Read, Write};
use std::os::fd::AsRawFd;
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

fn check_executable(path: &Path) -> Result<(), SupervisorError> {
    if !path.is_absolute() || !path.is_file() {
        return Err(SupervisorError::InvalidExecutable);
    }
    Ok(())
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
        check_executable(executable)?;
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
        validate_request(command_id, &payload).map_err(|_| SupervisorError::Contract)?;
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

        let mut stdout = self.stdout.take().ok_or(SupervisorError::Protocol)?;
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
        let response = response.map_err(|error| match error {
            ProtocolError::Io(_) => SupervisorError::Io,
            _ => SupervisorError::Protocol,
        })?;
        let object = response.as_object().ok_or(SupervisorError::Protocol)?;
        if object.len() != 3
            || !object.contains_key("request_id")
            || !object.contains_key("response")
            || !object.contains_key("session_proof")
            || object["request_id"].as_u64() != Some(request_id)
        {
            return Err(SupervisorError::Protocol);
        }
        let unsigned_response = json!({
            "request_id": request_id,
            "response": object["response"]
        });
        let expected = proof(&self.secret, &unsigned_response)?;
        if object["session_proof"].as_str() != Some(expected.as_str()) {
            return Err(SupervisorError::Protocol);
        }
        validate_response(command_id, object["response"].clone())
            .map_err(|_| SupervisorError::Contract)
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
        let mut supervisor =
            SidecarSupervisor::spawn(Path::new(&executable), &[]).expect("spawn real sidecar");
        let response = supervisor
            .call("bootstrap_state", json!({}), 2_000_000_000)
            .expect("sidecar response");
        assert_eq!(response["status"], "ok");
        supervisor.terminate_and_reap().expect("reap real sidecar");
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
