use std::ffi::CStr;
use std::fs::{self, File, OpenOptions};
use std::io;
use std::os::fd::AsRawFd;
use std::os::unix::ffi::OsStrExt;
use std::os::unix::fs::{DirBuilderExt, MetadataExt, OpenOptionsExt};
use std::path::{Path, PathBuf};

const LOCK_NAME: &str = ".agent-quota-host-instance.lock";

#[derive(Debug, thiserror::Error)]
pub enum InstanceLeaseError {
    #[error("another Agent Quota host is already running")]
    AlreadyRunning,
    #[error("instance lease path is unsafe")]
    UnsafePath,
    #[error("instance lease I/O failed")]
    Io(#[from] io::Error),
}

pub struct InstanceLease {
    _file: File,
}

pub fn fixed_app_data_root() -> Result<PathBuf, InstanceLeaseError> {
    let euid = current_euid();
    // SAFETY: sysconf has no pointer arguments. An indeterminate result uses a conservative
    // initial buffer and getpwuid_r is retried on ERANGE.
    let configured = unsafe { libc::sysconf(libc::_SC_GETPW_R_SIZE_MAX) };
    let mut capacity = if configured > 0 {
        usize::try_from(configured).unwrap_or(16 * 1024)
    } else {
        16 * 1024
    }
    .clamp(1024, 1024 * 1024);

    loop {
        let mut record = std::mem::MaybeUninit::<libc::passwd>::uninit();
        let mut result = std::ptr::null_mut();
        let mut buffer = vec![0_u8; capacity];
        // SAFETY: record and buffer are valid writable allocations for the duration of the call.
        let code = unsafe {
            libc::getpwuid_r(
                euid,
                record.as_mut_ptr(),
                buffer.as_mut_ptr().cast(),
                buffer.len(),
                &mut result,
            )
        };
        if code == libc::ERANGE && capacity < 1024 * 1024 {
            capacity = (capacity * 2).min(1024 * 1024);
            continue;
        }
        if code != 0 {
            return Err(InstanceLeaseError::Io(io::Error::from_raw_os_error(code)));
        }
        if result.is_null() {
            return Err(InstanceLeaseError::UnsafePath);
        }
        // SAFETY: getpwuid_r succeeded and returned a non-null record whose strings live in
        // buffer until this scope ends.
        let record = unsafe { record.assume_init() };
        if record.pw_dir.is_null() {
            return Err(InstanceLeaseError::UnsafePath);
        }
        // SAFETY: POSIX guarantees pw_dir is NUL-terminated on a successful lookup.
        let home = PathBuf::from(std::ffi::OsStr::from_bytes(unsafe {
            CStr::from_ptr(record.pw_dir).to_bytes()
        }));
        if !home.is_absolute() || home.as_os_str().is_empty() {
            return Err(InstanceLeaseError::UnsafePath);
        }
        return Ok(home
            .join("Library")
            .join("Application Support")
            .join("com.agentquota.desktop"));
    }
}

impl InstanceLease {
    pub fn acquire(data_root: &Path) -> Result<Self, InstanceLeaseError> {
        let mut builder = fs::DirBuilder::new();
        builder.recursive(true).mode(0o700);
        builder.create(data_root)?;
        validate_private_directory(data_root)?;

        // Keep the singleton lock outside the replaceable application-state directory. A
        // restore that renames/recreates the data root must still contend on the same inode.
        let lock_path = data_root
            .parent()
            .ok_or(InstanceLeaseError::UnsafePath)?
            .join(LOCK_NAME);
        let file = OpenOptions::new()
            .read(true)
            .write(true)
            .create(true)
            .mode(0o600)
            .custom_flags(libc::O_CLOEXEC | libc::O_NOFOLLOW)
            .open(&lock_path)?;
        validate_lock_file(&file)?;

        // SAFETY: flock only observes the valid owned file descriptor. The descriptor remains
        // open in HostState for the full host lifetime and is not inherited across exec.
        let result = unsafe { libc::flock(file.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) };
        if result != 0 {
            let error = io::Error::last_os_error();
            return match error.raw_os_error() {
                Some(code) if code == libc::EWOULDBLOCK || code == libc::EAGAIN => {
                    Err(InstanceLeaseError::AlreadyRunning)
                }
                _ => Err(InstanceLeaseError::Io(error)),
            };
        }
        Ok(Self { _file: file })
    }
}

fn validate_private_directory(path: &Path) -> Result<(), InstanceLeaseError> {
    if !path.is_absolute() {
        return Err(InstanceLeaseError::UnsafePath);
    }
    let euid = current_euid();
    for component in path.ancestors().collect::<Vec<_>>().into_iter().rev() {
        let metadata = fs::symlink_metadata(component)?;
        if metadata.file_type().is_symlink()
            || !metadata.is_dir()
            || (metadata.uid() != 0 && metadata.uid() != euid)
            || metadata.mode() & 0o022 != 0
        {
            return Err(InstanceLeaseError::UnsafePath);
        }
    }
    let metadata = fs::symlink_metadata(path)?;
    if metadata.uid() != euid || metadata.mode() & 0o077 != 0 {
        return Err(InstanceLeaseError::UnsafePath);
    }
    Ok(())
}

fn validate_lock_file(file: &File) -> Result<(), InstanceLeaseError> {
    let metadata = file.metadata()?;
    if !metadata.is_file()
        || metadata.uid() != current_euid()
        || metadata.mode() & 0o777 != 0o600
        || metadata.nlink() != 1
    {
        return Err(InstanceLeaseError::UnsafePath);
    }
    Ok(())
}

fn current_euid() -> u32 {
    // SAFETY: geteuid has no preconditions and no side effects.
    unsafe { libc::geteuid() }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::PathBuf;
    use std::process::{Child, Command};
    use std::thread;
    use std::time::{Duration, Instant};

    const CHILD_ROOT: &str = "AQ_INSTANCE_LEASE_TEST_ROOT";
    const CHILD_READY: &str = "AQ_INSTANCE_LEASE_TEST_READY";
    const CHILD_STOP: &str = "AQ_INSTANCE_LEASE_TEST_STOP";
    const HOME_OUTPUT: &str = "AQ_FIXED_APP_DATA_ROOT_TEST_OUTPUT";

    #[test]
    fn lease_subprocess_helper() {
        let Some(root) = std::env::var_os(CHILD_ROOT).map(PathBuf::from) else {
            return;
        };
        let ready = PathBuf::from(std::env::var_os(CHILD_READY).expect("ready path"));
        let stop = PathBuf::from(std::env::var_os(CHILD_STOP).expect("stop path"));
        let _lease = InstanceLease::acquire(&root).expect("child lease");
        fs::write(&ready, b"ready").expect("write readiness marker");
        let deadline = Instant::now() + Duration::from_secs(15);
        while !stop.exists() && Instant::now() < deadline {
            thread::sleep(Duration::from_millis(10));
        }
    }

    #[test]
    fn fixed_app_data_root_subprocess_helper() {
        let Some(output) = std::env::var_os(HOME_OUTPUT).map(PathBuf::from) else {
            return;
        };
        let root = fixed_app_data_root().expect("fixed app data root");
        fs::write(output, root.as_os_str().as_bytes()).expect("write app data root");
    }

    fn spawn_lease_holder(root: &Path, marker: &str) -> (Child, PathBuf, PathBuf) {
        let ready = root.with_extension(format!("{marker}.ready"));
        let stop = root.with_extension(format!("{marker}.stop"));
        let child = Command::new(std::env::current_exe().expect("test executable"))
            .args(["lease_subprocess_helper", "--nocapture", "--test-threads=1"])
            .env(CHILD_ROOT, root)
            .env(CHILD_READY, &ready)
            .env(CHILD_STOP, &stop)
            .spawn()
            .expect("spawn lease holder");
        let deadline = Instant::now() + Duration::from_secs(5);
        while !ready.exists() && Instant::now() < deadline {
            thread::sleep(Duration::from_millis(10));
        }
        assert!(ready.exists(), "child did not acquire instance lease");
        (child, ready, stop)
    }

    #[test]
    fn second_app_process_is_rejected_and_lease_recovers_after_exit() {
        let temporary = tempfile::tempdir().expect("temporary directory");
        let root = fs::canonicalize(temporary.path())
            .expect("canonical temporary directory")
            .join("app-data");

        let (mut clean_child, _ready, stop) = spawn_lease_holder(&root, "clean");
        assert!(matches!(
            InstanceLease::acquire(&root),
            Err(InstanceLeaseError::AlreadyRunning)
        ));
        fs::write(stop, b"stop").expect("stop child");
        assert!(clean_child.wait().expect("wait clean child").success());
        drop(InstanceLease::acquire(&root).expect("lease after clean exit"));

        let (mut killed_child, _ready, _stop) = spawn_lease_holder(&root, "killed");
        assert!(matches!(
            InstanceLease::acquire(&root),
            Err(InstanceLeaseError::AlreadyRunning)
        ));
        killed_child.kill().expect("kill child");
        let _ = killed_child.wait();
        drop(InstanceLease::acquire(&root).expect("lease after forced exit"));
    }

    #[test]
    fn replacing_data_root_does_not_create_a_second_lock_inode() {
        let temporary = tempfile::tempdir().expect("temporary directory");
        let root = fs::canonicalize(temporary.path())
            .expect("canonical temporary directory")
            .join("app-data");
        let moved = root.with_extension("moved");
        let (mut child, _ready, stop) = spawn_lease_holder(&root, "swap");
        fs::rename(&root, &moved).expect("move active data root");
        let mut replacement = fs::DirBuilder::new();
        replacement
            .mode(0o700)
            .create(&root)
            .expect("replace data root");
        assert!(matches!(
            InstanceLease::acquire(&root),
            Err(InstanceLeaseError::AlreadyRunning)
        ));
        fs::write(stop, b"stop").expect("stop child");
        assert!(child.wait().expect("wait child").success());
        drop(InstanceLease::acquire(&root).expect("lease after holder exit"));
    }

    #[test]
    fn unsafe_data_root_permissions_are_rejected() {
        let temporary = tempfile::tempdir().expect("temporary directory");
        let root = fs::canonicalize(temporary.path())
            .expect("canonical temporary directory")
            .join("shared-data");
        fs::create_dir(&root).expect("create data root");
        let mut permissions = fs::metadata(&root).expect("metadata").permissions();
        std::os::unix::fs::PermissionsExt::set_mode(&mut permissions, 0o770);
        fs::set_permissions(&root, permissions).expect("set permissions");
        assert!(matches!(
            InstanceLease::acquire(&root),
            Err(InstanceLeaseError::UnsafePath)
        ));
    }

    #[test]
    fn production_data_root_is_independent_of_home_environment() {
        let temporary = tempfile::tempdir().expect("temporary directory");
        let cases = [
            "/tmp/attacker-home-a",
            "/tmp/attacker-home-b",
            "",
            "relative-attacker-home",
        ];
        let outputs: Vec<PathBuf> = (0..cases.len())
            .map(|index| temporary.path().join(format!("root-{index}.txt")))
            .collect();
        for (home, output) in cases.into_iter().zip(&outputs) {
            let status = Command::new(std::env::current_exe().expect("test executable"))
                .args([
                    "fixed_app_data_root_subprocess_helper",
                    "--nocapture",
                    "--test-threads=1",
                ])
                .env("HOME", home)
                .env(HOME_OUTPUT, output)
                .status()
                .expect("spawn fixed-root helper");
            assert!(status.success());
        }
        let roots: Vec<String> = outputs
            .into_iter()
            .map(|output| fs::read_to_string(output).expect("fixed root"))
            .collect();
        let first = &roots[0];
        assert!(roots.iter().all(|root| root == first));
        assert!(first.ends_with("/Library/Application Support/com.agentquota.desktop"));
        assert!(!first.contains("attacker-home"));
    }
}
