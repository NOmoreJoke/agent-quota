mod contract;
pub mod protocol;
pub mod supervisor;

use contract::{safe_error, validate_request, validate_response};
use serde_json::{Value, json};
use std::path::PathBuf;
use std::sync::Mutex;
use supervisor::{SidecarSupervisor, SupervisorError};
use tauri::{Manager, State};

type CommandResult = Result<Value, String>;
const DEFAULT_BUDGET_NS: u64 = 2_000_000_000;
const REFRESH_BUDGET_NS: u64 = 9_000_000_000;

struct HostState {
    sidecar: Mutex<Option<SidecarSupervisor>>,
}

fn unavailable(command_id: &str, request: &Value, code: &str) -> Value {
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

fn call_sidecar(
    state: &State<'_, HostState>,
    command_id: &str,
    request: Value,
    budget_ns: u64,
) -> CommandResult {
    validate_request(command_id, &request).map_err(|_| "request rejected".to_owned())?;
    let response = match state.sidecar.lock() {
        Ok(mut guard) => match guard.as_mut() {
            Some(sidecar) => match sidecar.call(command_id, request.clone(), budget_ns) {
                Ok(response) => response,
                Err(SupervisorError::OutcomeUnknown) => {
                    *guard = None;
                    unavailable(command_id, &request, "outcome-unknown")
                }
                Err(_) => {
                    *guard = None;
                    unavailable(command_id, &request, "provider-unavailable")
                }
            },
            None => unavailable(command_id, &request, "provider-unavailable"),
        },
        Err(_) => unavailable(command_id, &request, "provider-unavailable"),
    };
    validate_response(command_id, response).map_err(|_| "response rejected".to_owned())
}

#[tauri::command]
fn bootstrap_state(state: State<'_, HostState>, request: Value) -> CommandResult {
    call_sidecar(&state, "bootstrap_state", request, DEFAULT_BUDGET_NS)
}

#[tauri::command]
fn accounts_read(state: State<'_, HostState>, request: Value) -> CommandResult {
    call_sidecar(&state, "accounts_read", request, DEFAULT_BUDGET_NS)
}

#[tauri::command]
fn quota_overview(state: State<'_, HostState>, request: Value) -> CommandResult {
    call_sidecar(&state, "quota_overview", request, DEFAULT_BUDGET_NS)
}

#[tauri::command]
fn refresh_scope(state: State<'_, HostState>, request: Value) -> CommandResult {
    call_sidecar(&state, "refresh_scope", request, REFRESH_BUDGET_NS)
}

#[tauri::command]
fn config_validate_apply(state: State<'_, HostState>, request: Value) -> CommandResult {
    call_sidecar(&state, "config_validate_apply", request, DEFAULT_BUDGET_NS)
}

#[tauri::command]
fn credential_dialog_open(request: Value) -> CommandResult {
    validate_request("credential_dialog_open", &request)
        .map_err(|_| "request rejected".to_owned())?;
    validate_response(
        "credential_dialog_open",
        unavailable("credential_dialog_open", &request, "not-authorized"),
    )
    .map_err(|_| "response rejected".to_owned())
}

#[tauri::command]
fn destructive_confirmation_open(request: Value) -> CommandResult {
    validate_request("destructive_confirmation_open", &request)
        .map_err(|_| "request rejected".to_owned())?;
    validate_response(
        "destructive_confirmation_open",
        unavailable("destructive_confirmation_open", &request, "not-authorized"),
    )
    .map_err(|_| "response rejected".to_owned())
}

#[tauri::command]
fn reauthenticate(state: State<'_, HostState>, request: Value) -> CommandResult {
    call_sidecar(&state, "reauthenticate", request, DEFAULT_BUDGET_NS)
}

#[tauri::command]
fn export_redacted(state: State<'_, HostState>, request: Value) -> CommandResult {
    call_sidecar(&state, "export_redacted", request, DEFAULT_BUDGET_NS)
}

#[tauri::command]
fn scheduler_state(state: State<'_, HostState>, request: Value) -> CommandResult {
    call_sidecar(&state, "scheduler_state", request, DEFAULT_BUDGET_NS)
}

fn sidecar_spec(app: &tauri::App) -> Option<(PathBuf, Vec<String>)> {
    #[cfg(debug_assertions)]
    if let Some(path) = std::env::var_os("AQ_SIDECAR_EXECUTABLE") {
        return Some((PathBuf::from(path), Vec::new()));
    }
    let path = app.path().resource_dir().ok()?.join("agent-quota-sidecar");
    Some((path, Vec::new()))
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .setup(|app| {
            let sidecar = sidecar_spec(app)
                .and_then(|(path, arguments)| SidecarSupervisor::spawn(&path, &arguments).ok());
            app.manage(HostState {
                sidecar: Mutex::new(sidecar),
            });
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            bootstrap_state,
            accounts_read,
            quota_overview,
            refresh_scope,
            config_validate_apply,
            credential_dialog_open,
            destructive_confirmation_open,
            reauthenticate,
            export_redacted,
            scheduler_state
        ])
        .run(tauri::generate_context!())
        .expect("failed to run Agent Quota desktop host");
}

#[cfg(test)]
mod tests {
    use super::*;

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
}
