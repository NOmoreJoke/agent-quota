mod commands;
mod contract;
mod diagnostics;
mod instance;
mod native;
pub mod protocol;
mod refresh;
#[cfg(any(feature = "production", test))]
mod resource;
pub mod supervisor;
mod window;

#[cfg(all(feature = "production", feature = "development-overrides"))]
compile_error!("production and development-overrides are mutually exclusive");
#[cfg(not(any(feature = "production", feature = "development-overrides")))]
compile_error!("select exactly one Agent Quota runtime feature");
#[cfg(all(feature = "production", debug_assertions, not(any(test, doc))))]
compile_error!("production build must not enable debug assertions");

use contract::{safe_error, validate_request, validate_response};
use instance::{InstanceLease, InstanceLeaseError, fixed_app_data_root};
#[cfg(feature = "development-overrides")]
use native::helper_path;
use native::{NativeError, NativeHost};
#[cfg(feature = "production")]
use resource::ValidatedResources;
use serde_json::{Value, json};
use std::fs::File;
use std::io::Read;
use std::path::{Path, PathBuf};
use std::sync::Mutex;
use std::time::{Duration, Instant};
use supervisor::{SidecarSupervisor, SupervisorError};
use tauri::Manager;
use window::{
    CLOSE_WINDOW_MENU_ID, application_menu, handle_window_event, position_and_show_floating,
    restore_main_window,
};

pub(crate) type CommandResult = Result<Value, String>;
pub(crate) const DEFAULT_BUDGET_NS: u64 = 2_000_000_000;
const SIDECAR_RESPAWN_COOLDOWN: Duration = Duration::from_millis(250);
const SIDECAR_SPAWN_FAILURE_BACKOFF: Duration = Duration::from_secs(1);

pub(crate) struct SidecarLaunchSpec {
    pub executable: PathBuf,
    pub arguments: Vec<String>,
}

pub(crate) struct SidecarSlot {
    pub active: Option<SidecarSupervisor>,
    pub spec: Option<SidecarLaunchSpec>,
    pub next_respawn_at: Instant,
}

impl SidecarSlot {
    fn new(spec: Option<SidecarLaunchSpec>, native: &NativeHost) -> Self {
        let mut active = spec
            .as_ref()
            .and_then(|item| SidecarSupervisor::spawn(&item.executable, &item.arguments).ok());
        if let Some(supervisor) = active.as_mut() {
            reconcile_pending_cleanup(supervisor, native);
        }
        Self {
            active,
            spec,
            next_respawn_at: Instant::now(),
        }
    }

    fn ensure_connected(&mut self, native: &NativeHost) -> Option<&mut SidecarSupervisor> {
        if self.active.is_none()
            && let Some(spec) = self.spec.as_ref()
            && Instant::now() >= self.next_respawn_at
        {
            match SidecarSupervisor::spawn(&spec.executable, &spec.arguments) {
                Ok(mut supervisor) => {
                    reconcile_pending_cleanup(&mut supervisor, native);
                    self.active = Some(supervisor);
                }
                Err(_) => {
                    self.next_respawn_at = Instant::now() + SIDECAR_SPAWN_FAILURE_BACKOFF;
                }
            }
        }
        self.active.as_mut()
    }

    fn invalidate(&mut self) {
        self.active = None;
        self.next_respawn_at = Instant::now() + SIDECAR_RESPAWN_COOLDOWN;
    }
}

pub(crate) struct HostState {
    pub _instance_lease: InstanceLease,
    pub credential_destructive_transaction: Mutex<()>,
    pub refresh_transaction: Mutex<()>,
    pub sidecar: Mutex<SidecarSlot>,
    pub native: NativeHost,
}

fn reconcile_pending_cleanup(sidecar: &mut SidecarSupervisor, native: &NativeHost) {
    if let Ok(pending) = sidecar.call_internal(
        "host_internal.cleanup_pending",
        json!({}),
        DEFAULT_BUDGET_NS,
    ) && let Some(references) = pending["references"].as_array()
    {
        let acknowledged: Vec<&str> = references
            .iter()
            .filter_map(Value::as_str)
            .filter(|reference| native.delete_reference(reference).is_ok())
            .collect();
        if !acknowledged.is_empty() {
            let _ = sidecar.call_internal(
                "host_internal.cleanup_ack",
                json!({"references": acknowledged}),
                DEFAULT_BUDGET_NS,
            );
        }
    }
}

pub(crate) fn unavailable(command_id: &str, request: &Value, code: &str) -> Value {
    let error = safe_error(code, code == "provider-unavailable");
    match command_id {
        "bootstrap_state" => json!({
            "application_state": {"launch_state": "error", "offline": true},
            "safe_error": error,
            "status": "error"
        }),
        "accounts_read" => json!({"accounts": [], "safe_error": error, "status": "error"}),
        "quota_overview" => json!({
            "projection": {
                "capability_rows": [],
                "freshness": "stale",
                "scope_ref": request.get("scope_ref").and_then(Value::as_str).unwrap_or("")
            },
            "safe_error": error,
            "status": "error"
        }),
        "refresh_scope" => json!({
            "refresh_state": {"phase": "failed"},
            "safe_error": error,
            "status": "error"
        }),
        "config_validate_apply" => json!({
            "classification": "rejected",
            "safe_error": error,
            "status": "error"
        }),
        "credential_dialog_open" => json!({
            "opaque_reference_status": "cancelled",
            "safe_error": error,
            "status": "cancelled"
        }),
        "destructive_confirmation_open" => {
            json!({"safe_error": error, "status": "cancelled"})
        }
        "reauthenticate" => json!({
            "reauth_state": "failed",
            "safe_error": error,
            "status": "error"
        }),
        "export_redacted" => json!({
            "export_status": "failed",
            "safe_error": error,
            "status": "error"
        }),
        "scheduler_state" => json!({
            "scheduler_state": {"health": "unhealthy", "installed": false},
            "safe_error": error,
            "status": "error"
        }),
        _ => json!({}),
    }
}

pub(crate) fn call_sidecar(
    state: &HostState,
    command_id: &str,
    request: Value,
    budget_ns: u64,
) -> CommandResult {
    validate_request(command_id, &request).map_err(|_| "request rejected".to_owned())?;
    let response = match state.sidecar.lock() {
        Ok(mut slot) => match slot.ensure_connected(&state.native) {
            Some(sidecar) => match sidecar.call(command_id, request.clone(), budget_ns) {
                Ok(response) => response,
                Err(SupervisorError::OutcomeUnknown) => {
                    slot.invalidate();
                    unavailable(command_id, &request, "outcome-unknown")
                }
                Err(_) => {
                    slot.invalidate();
                    unavailable(command_id, &request, "provider-unavailable")
                }
            },
            None => unavailable(command_id, &request, "provider-unavailable"),
        },
        Err(_) => unavailable(command_id, &request, "provider-unavailable"),
    };
    validate_response(command_id, response).map_err(|_| "response rejected".to_owned())
}

pub(crate) fn call_internal(
    state: &HostState,
    command_id: &str,
    request: Value,
) -> Result<Value, SupervisorError> {
    let mut slot = state
        .sidecar
        .lock()
        .map_err(|_| SupervisorError::Protocol)?;
    let sidecar = slot
        .ensure_connected(&state.native)
        .ok_or(SupervisorError::Spawn)?;
    match sidecar.call_internal(command_id, request, DEFAULT_BUDGET_NS) {
        Ok(response) => Ok(response),
        Err(error) => {
            slot.invalidate();
            Err(error)
        }
    }
}

pub(crate) fn native_error_code(error: &NativeError) -> &'static str {
    match error {
        NativeError::Timeout => "timeout",
        NativeError::Busy | NativeError::Unavailable => "not-authorized",
        NativeError::Protocol | NativeError::Process => "provider-unavailable",
    }
}

pub(crate) fn validated(command_id: &str, response: Value) -> CommandResult {
    validate_response(command_id, response).map_err(|_| "response rejected".to_owned())
}

pub(crate) fn cleanup_references(state: &HostState, references: &Value) -> bool {
    let Some(references) = references.as_array() else {
        return false;
    };
    let acknowledged: Vec<&str> = references
        .iter()
        .filter_map(Value::as_str)
        .filter(|reference| state.native.delete_reference(reference).is_ok())
        .collect();
    if acknowledged.len() != references.len() {
        if !acknowledged.is_empty() {
            let _ = call_internal(
                state,
                "host_internal.cleanup_ack",
                json!({"references": acknowledged}),
            );
        }
        return false;
    }
    if acknowledged.is_empty() {
        return true;
    }
    call_internal(
        state,
        "host_internal.cleanup_ack",
        json!({"references": acknowledged}),
    )
    .is_ok()
}

fn format_credential_candidate(mut bytes: [u8; 16]) -> String {
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    let hex = bytes
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect::<String>();
    format!(
        "credential-{}-{}-{}-{}-{}",
        &hex[0..8],
        &hex[8..12],
        &hex[12..16],
        &hex[16..20],
        &hex[20..32]
    )
}

fn host_credential_candidate() -> Result<String, SupervisorError> {
    let mut bytes = [0_u8; 16];
    File::open("/dev/urandom")
        .and_then(|mut source| source.read_exact(&mut bytes))
        .map_err(|_| SupervisorError::Protocol)?;
    Ok(format_credential_candidate(bytes))
}

fn bind_credential_candidate(reference: &str, result: &Value) -> Result<(), SupervisorError> {
    if result["status"] != "prepared" || result["credential_reference"].as_str() != Some(reference)
    {
        return Err(SupervisorError::Protocol);
    }
    Ok(())
}

pub(crate) fn create_credential_candidate(state: &HostState) -> Result<String, SupervisorError> {
    let reference = host_credential_candidate()?;
    let result = call_internal(
        state,
        "host_internal.credential_candidate_create",
        json!({"credential_reference": reference}),
    )?;
    if let Err(error) = bind_credential_candidate(&reference, &result) {
        let _ = cleanup_credential_candidate(state, &reference);
        return Err(error);
    }
    Ok(reference)
}

pub(crate) fn cleanup_credential_candidate(state: &HostState, reference: &str) -> bool {
    cleanup_references(state, &json!([reference]))
}

fn app_data_root() -> Result<PathBuf, InstanceLeaseError> {
    #[cfg(feature = "development-overrides")]
    if let Some(data_root) = std::env::var_os("AQ_DATA_ROOT") {
        return Ok(PathBuf::from(data_root));
    }
    fixed_app_data_root()
}

fn sidecar_spec(executable: Option<PathBuf>, data_root: &Path) -> Option<SidecarLaunchSpec> {
    let arguments = vec![
        "--data-root".to_owned(),
        data_root.to_string_lossy().into_owned(),
    ];
    #[cfg(feature = "development-overrides")]
    if let Some(path) = std::env::var_os("AQ_SIDECAR_EXECUTABLE") {
        return Some(SidecarLaunchSpec {
            executable: PathBuf::from(path),
            arguments,
        });
    }
    executable.map(|executable| SidecarLaunchSpec {
        executable,
        arguments,
    })
}

#[cfg(feature = "development-overrides")]
fn runtime_resources(app: &tauri::App) -> (Option<PathBuf>, Option<PathBuf>) {
    let resource_dir = app.path().resource_dir().ok();
    let sidecar = resource_dir
        .as_ref()
        .map(|directory| directory.join("sidecar").join("agent-quota-sidecar"));
    (sidecar, helper_path(resource_dir))
}

#[cfg(feature = "production")]
fn runtime_resources(app: &tauri::App) -> (Option<PathBuf>, Option<PathBuf>) {
    const MANIFEST_SHA256: &str = env!("AQ_RESOURCE_MANIFEST_SHA256");
    let validated: Option<ValidatedResources> = app
        .path()
        .resource_dir()
        .ok()
        .and_then(|directory| resource::validate(&directory, MANIFEST_SHA256).ok());
    match validated {
        Some(resources) => (Some(resources.sidecar), Some(resources.native)),
        None => (None, None),
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let data_root = match app_data_root() {
        Ok(data_root) => data_root,
        Err(error) => {
            eprintln!("Agent Quota data boundary unavailable: {error}");
            return;
        }
    };
    // Resolve the installation-wide boundary before creating Tauri's event loop. Returning
    // here keeps a normal second launch from becoming a non-unwinding setup-hook panic.
    let instance_lease = match InstanceLease::acquire(&data_root) {
        Ok(instance_lease) => instance_lease,
        Err(InstanceLeaseError::AlreadyRunning) => return,
        Err(error) => {
            eprintln!("Agent Quota instance boundary unavailable: {error}");
            return;
        }
    };
    tauri::Builder::default()
        .menu(application_menu)
        .on_menu_event(|app, event| {
            if event.id().as_ref() == CLOSE_WINDOW_MENU_ID {
                for label in ["main", "floating"] {
                    if let Some(window) = app.get_webview_window(label)
                        && window.is_focused().ok() == Some(true)
                    {
                        let _ = window.close();
                        break;
                    }
                }
            }
        })
        .setup(move |app| {
            let (sidecar_executable, native_executable) = runtime_resources(app);
            let native = NativeHost::new(native_executable);
            let sidecar = SidecarSlot::new(sidecar_spec(sidecar_executable, &data_root), &native);
            app.manage(HostState {
                _instance_lease: instance_lease,
                credential_destructive_transaction: Mutex::new(()),
                refresh_transaction: Mutex::new(()),
                sidecar: Mutex::new(sidecar),
                native,
            });
            position_and_show_floating(app);
            Ok(())
        })
        .on_window_event(handle_window_event)
        .invoke_handler(tauri::generate_handler![
            commands::bootstrap_state,
            commands::accounts_read,
            commands::quota_overview,
            commands::refresh_scope,
            commands::config_validate_apply,
            commands::credential_dialog_open,
            commands::destructive_confirmation_open,
            commands::reauthenticate,
            commands::export_redacted,
            commands::scheduler_state
        ])
        .build(tauri::generate_context!())
        .expect("failed to build Agent Quota desktop host")
        .run(|app, event| {
            #[cfg(target_os = "macos")]
            if let tauri::RunEvent::Reopen { .. } = event {
                restore_main_window(app);
            }
            #[cfg(not(target_os = "macos"))]
            let _ = (app, event);
        });
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn credential_candidate_format_is_host_owned_uuid_v4() {
        let reference = format_credential_candidate([0xff; 16]);
        assert_eq!(reference, "credential-ffffffff-ffff-4fff-bfff-ffffffffffff");
    }

    #[test]
    fn credential_candidate_binding_rejects_sidecar_selected_reference() {
        let host_reference = "credential-00000000-0000-4000-8000-000000000001";
        let active_reference = "credential-00000000-0000-4000-8000-000000000002";
        assert!(
            bind_credential_candidate(
                host_reference,
                &json!({"credential_reference": host_reference, "status": "prepared"})
            )
            .is_ok()
        );
        assert!(matches!(
            bind_credential_candidate(
                host_reference,
                &json!({"credential_reference": active_reference, "status": "prepared"})
            ),
            Err(SupervisorError::Protocol)
        ));
    }

    #[test]
    fn unavailable_responses_remain_inside_all_command_contracts() {
        let requests = [
            ("bootstrap_state", json!({})),
            ("accounts_read", json!({"scope_ref": "scope"})),
            ("quota_overview", json!({"scope_ref": "scope"})),
            ("refresh_scope", json!({"scope_ref": "scope"})),
            (
                "config_validate_apply",
                json!({"config_change_set": {"changes": [], "expected_generation": 0}}),
            ),
            (
                "credential_dialog_open",
                json!({"dialog_purpose": "create-credential-reference"}),
            ),
            (
                "destructive_confirmation_open",
                json!({"operation_intent": "purge", "opaque_selection_handle": "selection"}),
            ),
            ("reauthenticate", json!({"principal_ref": "principal"})),
            (
                "export_redacted",
                json!({"export_profile": "redacted-diagnostics", "scope_ref": "scope"}),
            ),
            ("scheduler_state", json!({})),
        ];
        for (command_id, request) in requests {
            validate_response(
                command_id,
                unavailable(command_id, &request, "provider-unavailable"),
            )
            .unwrap();
        }
    }

    #[test]
    fn sidecar_slot_recovers_on_subsequent_request_without_replaying_failed_call() {
        let Some(executable) = std::env::var_os("AQ_SIDECAR_TEST_EXECUTABLE") else {
            return;
        };
        let temporary = tempfile::tempdir().expect("temp dir");
        let root = std::fs::canonicalize(temporary.path())
            .expect("canonical root")
            .join("app-data");
        let lease = InstanceLease::acquire(&root).expect("instance lease");
        let native = NativeHost::new(None);
        let spec = SidecarLaunchSpec {
            executable: PathBuf::from(executable),
            arguments: vec![
                "--data-root".to_owned(),
                root.to_string_lossy().into_owned(),
            ],
        };
        let state = HostState {
            _instance_lease: lease,
            credential_destructive_transaction: Mutex::new(()),
            refresh_transaction: Mutex::new(()),
            sidecar: Mutex::new(SidecarSlot::new(Some(spec), &native)),
            native,
        };
        // Simulate a terminated/timed-out sidecar session.
        state.sidecar.lock().unwrap().active = None;
        state.sidecar.lock().unwrap().next_respawn_at = Instant::now();
        let recovered = call_sidecar(&state, "bootstrap_state", json!({}), DEFAULT_BUDGET_NS)
            .expect("on-demand respawn");
        assert_eq!(recovered["status"], "ok");
    }
}
