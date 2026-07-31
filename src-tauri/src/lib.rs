mod contract;
mod native;
pub mod protocol;
pub mod supervisor;

use contract::{safe_error, validate_request, validate_response};
use native::{NativeError, NativeHost, helper_path};
use serde_json::{Value, json};
use std::path::PathBuf;
use std::sync::Mutex;
use supervisor::{SidecarSupervisor, SupervisorError};
use tauri::{AppHandle, Manager, State};

type CommandResult = Result<Value, String>;
const DEFAULT_BUDGET_NS: u64 = 2_000_000_000;
const REFRESH_BUDGET_NS: u64 = 9_000_000_000;

struct HostState {
    sidecar: Mutex<Option<SidecarSupervisor>>,
    native: NativeHost,
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

fn call_internal(
    state: &State<'_, HostState>,
    command_id: &str,
    request: Value,
) -> Result<Value, SupervisorError> {
    let mut guard = state
        .sidecar
        .lock()
        .map_err(|_| SupervisorError::Protocol)?;
    let sidecar = guard.as_mut().ok_or(SupervisorError::Spawn)?;
    match sidecar.call_internal(command_id, request, DEFAULT_BUDGET_NS) {
        Ok(response) => Ok(response),
        Err(error) => {
            *guard = None;
            Err(error)
        }
    }
}

fn native_error_code(error: &NativeError) -> &'static str {
    match error {
        NativeError::Timeout => "timeout",
        NativeError::Busy | NativeError::Unavailable => "not-authorized",
        NativeError::Protocol | NativeError::Process => "provider-unavailable",
    }
}

fn window_ready(app: &AppHandle) -> bool {
    let Some(window) = app.get_webview_window("main") else {
        return false;
    };
    window.is_visible().ok() == Some(true)
        && window.is_minimized().ok() == Some(false)
        && window.is_focused().ok() == Some(true)
}

fn validated(command_id: &str, response: Value) -> CommandResult {
    validate_response(command_id, response).map_err(|_| "response rejected".to_owned())
}

fn cleanup_references(state: &State<'_, HostState>, references: &Value) {
    let Some(references) = references.as_array() else {
        return;
    };
    let acknowledged: Vec<&str> = references
        .iter()
        .filter_map(Value::as_str)
        .filter(|reference| state.native.delete_reference(reference).is_ok())
        .collect();
    if !acknowledged.is_empty() {
        let _ = call_internal(
            state,
            "host_internal.cleanup_ack",
            json!({"references": acknowledged}),
        );
    }
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
fn credential_dialog_open(
    app: AppHandle,
    state: State<'_, HostState>,
    request: Value,
) -> CommandResult {
    validate_request("credential_dialog_open", &request)
        .map_err(|_| "request rejected".to_owned())?;
    if !window_ready(&app)
        || request["dialog_purpose"].as_str() != Some("create-credential-reference")
    {
        return validated(
            "credential_dialog_open",
            unavailable("credential_dialog_open", &request, "not-authorized"),
        );
    }
    let response = match state.native.credential(json!({
        "action": "credential",
        "dialogPurpose": "create-credential-reference"
    })) {
        Ok(response) if response.status == "cancelled" => {
            json!({"opaque_reference_status": "cancelled", "status": "cancelled"})
        }
        Ok(response) if response.status == "reference-created" => {
            let Some(reference) = response.opaque_reference else {
                return validated(
                    "credential_dialog_open",
                    unavailable("credential_dialog_open", &request, "provider-unavailable"),
                );
            };
            match call_internal(
                &state,
                "host_internal.credential_commit",
                json!({
                    "credential_reference": reference,
                    "expected_generation": null,
                    "principal_ref": null,
                    "purpose": "create-credential-reference"
                }),
            ) {
                Ok(result) if result["status"] == "committed" => {
                    json!({"opaque_reference_status": "reference-created", "status": "ok"})
                }
                Err(SupervisorError::OutcomeUnknown) => {
                    unavailable("credential_dialog_open", &request, "outcome-unknown")
                }
                _ => {
                    let _ = state.native.delete_reference(&reference);
                    unavailable("credential_dialog_open", &request, "provider-unavailable")
                }
            }
        }
        Ok(response) => {
            let _ = response.error_code;
            unavailable("credential_dialog_open", &request, "not-authorized")
        }
        Err(error) => unavailable(
            "credential_dialog_open",
            &request,
            native_error_code(&error),
        ),
    };
    validated("credential_dialog_open", response)
}

#[tauri::command]
fn destructive_confirmation_open(
    app: AppHandle,
    state: State<'_, HostState>,
    request: Value,
) -> CommandResult {
    validate_request("destructive_confirmation_open", &request)
        .map_err(|_| "request rejected".to_owned())?;
    if !window_ready(&app) {
        return validated(
            "destructive_confirmation_open",
            unavailable("destructive_confirmation_open", &request, "not-authorized"),
        );
    }
    let plan = match call_internal(&state, "host_internal.destructive_prepare", request.clone()) {
        Ok(plan) => plan,
        Err(_) => {
            return validated(
                "destructive_confirmation_open",
                unavailable(
                    "destructive_confirmation_open",
                    &request,
                    "provider-unavailable",
                ),
            );
        }
    };
    let plan_id = plan["plan_id"].as_str().unwrap_or_default().to_owned();
    let native_response = state.native.destructive(json!({
        "action": "destructive",
        "operationIntent": plan["operation_intent"],
        "planSummary": plan["summary"],
        "planDigest": plan["digest"],
        "generation": plan["generation"],
        "nonce": plan["nonce"]
    }));
    let response = match native_response {
        Ok(response) if response.status == "cancelled" => {
            let _ = call_internal(
                &state,
                "host_internal.destructive_cancel",
                json!({"plan_id": plan_id}),
            );
            json!({"status": "cancelled"})
        }
        Ok(response) if response.status == "confirmed" => {
            let Some(token) = response.user_presence_token else {
                return validated(
                    "destructive_confirmation_open",
                    unavailable(
                        "destructive_confirmation_open",
                        &request,
                        "provider-unavailable",
                    ),
                );
            };
            match call_internal(
                &state,
                "host_internal.destructive_commit",
                json!({
                    "digest": plan["digest"],
                    "generation": plan["generation"],
                    "nonce": plan["nonce"],
                    "plan_id": plan_id,
                    "user_presence_token": token
                }),
            ) {
                Ok(result) if result["status"] == "committed" => {
                    cleanup_references(&state, &result["cleanup_references"]);
                    json!({"status": "committed"})
                }
                Err(SupervisorError::OutcomeUnknown) => {
                    unavailable("destructive_confirmation_open", &request, "outcome-unknown")
                }
                _ => unavailable(
                    "destructive_confirmation_open",
                    &request,
                    "provider-unavailable",
                ),
            }
        }
        Ok(_) => {
            let _ = call_internal(
                &state,
                "host_internal.destructive_cancel",
                json!({"plan_id": plan_id}),
            );
            unavailable("destructive_confirmation_open", &request, "not-authorized")
        }
        Err(error) => {
            let _ = call_internal(
                &state,
                "host_internal.destructive_cancel",
                json!({"plan_id": plan_id}),
            );
            unavailable(
                "destructive_confirmation_open",
                &request,
                native_error_code(&error),
            )
        }
    };
    validated("destructive_confirmation_open", response)
}

#[tauri::command]
fn reauthenticate(app: AppHandle, state: State<'_, HostState>, request: Value) -> CommandResult {
    validate_request("reauthenticate", &request).map_err(|_| "request rejected".to_owned())?;
    if !window_ready(&app) {
        return validated(
            "reauthenticate",
            unavailable("reauthenticate", &request, "not-authorized"),
        );
    }
    let principal = request["principal_ref"].as_str().unwrap_or_default();
    let context = match call_internal(
        &state,
        "host_internal.credential_context",
        json!({"principal_ref": principal}),
    ) {
        Ok(context) => context,
        Err(_) => {
            return validated(
                "reauthenticate",
                unavailable("reauthenticate", &request, "not-authorized"),
            );
        }
    };
    let native_response = state.native.credential(json!({
        "action": "credential",
        "dialogPurpose": "replace-credential-reference"
    }));
    let response = match native_response {
        Ok(response) if response.status == "cancelled" => {
            json!({"reauth_state": "cancelled", "status": "ok"})
        }
        Ok(response) if response.status == "reference-replaced" => {
            let Some(reference) = response.opaque_reference else {
                return validated(
                    "reauthenticate",
                    unavailable("reauthenticate", &request, "provider-unavailable"),
                );
            };
            match call_internal(
                &state,
                "host_internal.credential_commit",
                json!({
                    "credential_reference": reference,
                    "expected_generation": context["generation"],
                    "principal_ref": principal,
                    "purpose": "replace-credential-reference"
                }),
            ) {
                Ok(result) if result["status"] == "committed" => {
                    if let Some(old) = result["old_reference"].as_str() {
                        if state.native.delete_reference(old).is_ok() {
                            let _ = call_internal(
                                &state,
                                "host_internal.cleanup_ack",
                                json!({"references": [old]}),
                            );
                        }
                    }
                    json!({"reauth_state": "succeeded", "status": "ok"})
                }
                Err(SupervisorError::OutcomeUnknown) => {
                    unavailable("reauthenticate", &request, "outcome-unknown")
                }
                _ => {
                    let _ = state.native.delete_reference(&reference);
                    unavailable("reauthenticate", &request, "provider-unavailable")
                }
            }
        }
        Ok(_) => unavailable("reauthenticate", &request, "not-authorized"),
        Err(error) => unavailable("reauthenticate", &request, native_error_code(&error)),
    };
    validated("reauthenticate", response)
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
    let data_root = std::env::var_os("AQ_DATA_ROOT")
        .map(PathBuf::from)
        .or_else(|| app.path().app_data_dir().ok())?;
    #[cfg(not(debug_assertions))]
    let data_root = app.path().app_data_dir().ok()?;
    let arguments = vec![
        "--data-root".to_owned(),
        data_root.to_string_lossy().into_owned(),
    ];
    #[cfg(debug_assertions)]
    if let Some(path) = std::env::var_os("AQ_SIDECAR_EXECUTABLE") {
        return Some((PathBuf::from(path), arguments));
    }
    let path = app.path().resource_dir().ok()?.join("agent-quota-sidecar");
    Some((path, arguments))
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .setup(|app| {
            let mut sidecar = sidecar_spec(app)
                .and_then(|(path, arguments)| SidecarSupervisor::spawn(&path, &arguments).ok());
            let native = NativeHost::new(helper_path(app.path().resource_dir().ok()));
            if let Some(active) = sidecar.as_mut()
                && let Ok(pending) = active.call_internal(
                    "host_internal.cleanup_pending",
                    json!({}),
                    DEFAULT_BUDGET_NS,
                )
                && let Some(references) = pending["references"].as_array()
            {
                let acknowledged: Vec<&str> = references
                    .iter()
                    .filter_map(Value::as_str)
                    .filter(|reference| native.delete_reference(reference).is_ok())
                    .collect();
                if !acknowledged.is_empty() {
                    let _ = active.call_internal(
                        "host_internal.cleanup_ack",
                        json!({"references": acknowledged}),
                        DEFAULT_BUDGET_NS,
                    );
                }
            }
            if let Some(active) = sidecar.as_mut()
                && let Ok(retained) = active.call_internal(
                    "host_internal.credential_references",
                    json!({}),
                    DEFAULT_BUDGET_NS,
                )
                && let Some(references) = retained["references"].as_array()
            {
                let retained: Vec<&str> = references.iter().filter_map(Value::as_str).collect();
                let _ = native.prune_references(&retained);
            }
            app.manage(HostState {
                sidecar: Mutex::new(sidecar),
                native,
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
