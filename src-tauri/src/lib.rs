mod contract;
mod instance;
mod native;
pub mod protocol;
#[cfg(any(feature = "production", test))]
mod resource;
pub mod supervisor;

#[cfg(all(feature = "production", feature = "development-overrides"))]
compile_error!("production and development-overrides are mutually exclusive");
#[cfg(not(any(feature = "production", feature = "development-overrides")))]
compile_error!("select exactly one Agent Quota runtime feature");
#[cfg(all(feature = "production", debug_assertions, not(any(test, doc))))]
compile_error!("production build must not enable debug assertions");

use base64::{Engine as _, engine::general_purpose::STANDARD as BASE64};
use contract::{safe_error, validate_request, validate_response};
use instance::{InstanceLease, InstanceLeaseError, fixed_app_data_root};
#[cfg(feature = "development-overrides")]
use native::helper_path;
use native::{NativeError, NativeHost};
#[cfg(feature = "production")]
use resource::ValidatedResources;
use serde_json::{Value, json};
use std::path::{Path, PathBuf};
use std::sync::Mutex;
use std::time::{Duration, Instant};
use supervisor::{SidecarSupervisor, SupervisorError};
use tauri::{AppHandle, Manager, State};

type CommandResult = Result<Value, String>;
const DEFAULT_BUDGET_NS: u64 = 2_000_000_000;
const REFRESH_DEADLINE: Duration = Duration::from_secs(30);

struct HostState {
    _instance_lease: InstanceLease,
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

fn restore_main_window(app: &AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
        let _ = window.unminimize();
        let _ = window.set_focus();
    }
}

fn validated(command_id: &str, response: Value) -> CommandResult {
    validate_response(command_id, response).map_err(|_| "response rejected".to_owned())
}

fn cleanup_references(state: &State<'_, HostState>, references: &Value) -> bool {
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

fn bounded_provider_error(code: Option<&str>) -> &'static str {
    match code {
        Some("keychain-locked") => "keychain-locked",
        Some("reauth-required") => "reauth-required",
        Some("contract-error") => "contract-error",
        Some("timeout") => "timeout",
        _ => "provider-unavailable",
    }
}

fn commit_provider_failure(
    state: &State<'_, HostState>,
    principal: &str,
    generation: u64,
    provider: &str,
    code: &'static str,
) {
    let _ = call_internal(
        state,
        "host_internal.provider_failure_commit",
        json!({
            "expected_generation": generation,
            "principal_ref": principal,
            "provider_id": provider,
            "safe_error_code": code
        }),
    );
}

fn refresh_principal(
    state: &State<'_, HostState>,
    principal: &str,
    timeout: Duration,
) -> Result<(), &'static str> {
    let context = call_internal(
        state,
        "host_internal.credential_context",
        json!({"principal_ref": principal}),
    )
    .map_err(|_| "provider-unavailable")?;
    let reference = context["credential_reference"]
        .as_str()
        .ok_or("contract-error")?;
    let generation = context["generation"].as_u64().ok_or("contract-error")?;
    let provider = context["provider_id"].as_str().ok_or("contract-error")?;
    let response = match state.native.provider_fetch(reference, provider, timeout) {
        Ok(response) => response,
        Err(error) => {
            let code = native_error_code(&error);
            commit_provider_failure(state, principal, generation, provider, code);
            return Err(code);
        }
    };
    if response.status != "provider-response" {
        let code = bounded_provider_error(response.error_code.as_deref());
        commit_provider_failure(state, principal, generation, provider, code);
        return Err(code);
    }
    if response.provider.as_deref() != Some(provider) {
        return Err("contract-error");
    }
    let committed = call_internal(
        state,
        "host_internal.provider_response_commit",
        json!({
            "body_base64": response.body_base64.ok_or("contract-error")?,
            "expected_generation": generation,
            "http_status": response.http_status.ok_or("contract-error")?,
            "principal_ref": principal,
            "provider_id": provider
        }),
    )
    .map_err(|_| "provider-unavailable")?;
    if committed["status"] == "committed" {
        Ok(())
    } else {
        Err(bounded_provider_error(
            committed["safe_error_code"].as_str(),
        ))
    }
}

fn select_refresh_principals(accounts: &Value, scope: &str) -> Result<Vec<String>, &'static str> {
    let principals: Vec<String> = accounts["accounts"]
        .as_array()
        .into_iter()
        .flatten()
        .filter(|account| account["lifecycle"].as_str() == Some("active"))
        .filter_map(|account| account["principal_ref"].as_str().map(str::to_owned))
        .filter(|principal| scope == "scope-all" || principal == scope)
        .collect();
    if scope != "scope-all" && principals.is_empty() {
        return Err("contract-error");
    }
    Ok(principals)
}

fn refresh_accounts_error(accounts: &Value) -> Option<&str> {
    (accounts["status"].as_str() != Some("ok")).then(|| {
        accounts["safe_error"]["code"]
            .as_str()
            .unwrap_or("provider-unavailable")
    })
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
    validate_request("refresh_scope", &request).map_err(|_| "request rejected".to_owned())?;
    let scope = request["scope_ref"].as_str().unwrap_or_default();
    let accounts = call_sidecar(
        &state,
        "accounts_read",
        json!({"scope_ref": "scope-all"}),
        DEFAULT_BUDGET_NS,
    )?;
    if let Some(code) = refresh_accounts_error(&accounts) {
        return validated(
            "refresh_scope",
            unavailable("refresh_scope", &request, code),
        );
    }
    let principals = match select_refresh_principals(&accounts, scope) {
        Ok(principals) => principals,
        Err(code) => {
            return validated(
                "refresh_scope",
                unavailable("refresh_scope", &request, code),
            );
        }
    };
    let deadline = Instant::now() + REFRESH_DEADLINE;
    let mut first_error = None;
    for principal in principals {
        let remaining = deadline.saturating_duration_since(Instant::now());
        if remaining.is_zero() {
            first_error.get_or_insert("timeout");
            break;
        }
        if let Err(code) = refresh_principal(&state, &principal, remaining) {
            first_error.get_or_insert(code);
        }
    }
    let response = match first_error {
        Some(code) => unavailable("refresh_scope", &request, code),
        None => json!({"refresh_state": {"phase": "completed"}, "status": "ok"}),
    };
    validated("refresh_scope", response)
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
            let (Some(reference), Some(provider)) = (response.opaque_reference, response.provider)
            else {
                restore_main_window(&app);
                return validated(
                    "credential_dialog_open",
                    unavailable("credential_dialog_open", &request, "provider-unavailable"),
                );
            };
            let prepared = call_internal(
                &state,
                "host_internal.credential_prepare",
                json!({"credential_reference": reference}),
            );
            if !matches!(prepared, Ok(ref result) if result["status"] == "prepared") {
                let _ = state.native.delete_reference(&reference);
                restore_main_window(&app);
                return validated(
                    "credential_dialog_open",
                    unavailable("credential_dialog_open", &request, "outcome-unknown"),
                );
            }
            match call_internal(
                &state,
                "host_internal.credential_commit",
                json!({
                    "credential_reference": reference,
                    "expected_generation": null,
                    "principal_ref": null,
                    "provider_id": provider,
                    "purpose": "create-credential-reference"
                }),
            ) {
                Ok(result) if result["status"] == "committed" => {
                    let principal = result["principal_ref"].as_str().unwrap_or_default();
                    match refresh_principal(&state, principal, REFRESH_DEADLINE) {
                        Ok(()) => json!({
                            "opaque_reference_status": "reference-created",
                            "status": "ok"
                        }),
                        Err(code) => json!({
                            "opaque_reference_status": "reference-created",
                            "safe_error": safe_error(code, code == "provider-unavailable"),
                            "status": "error"
                        }),
                    }
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
    restore_main_window(&app);
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
    restore_main_window(&app);
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
                restore_main_window(&app);
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
                    if cleanup_references(&state, &result["cleanup_references"]) {
                        json!({"status": "committed"})
                    } else {
                        unavailable(
                            "destructive_confirmation_open",
                            &request,
                            "provider-unavailable",
                        )
                    }
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
        "dialogPurpose": "replace-credential-reference",
        "provider": context["provider_id"]
    }));
    restore_main_window(&app);
    let response = match native_response {
        Ok(response) if response.status == "cancelled" => {
            json!({"reauth_state": "cancelled", "status": "ok"})
        }
        Ok(response) if response.status == "reference-replaced" => {
            let Some(reference) = response.opaque_reference else {
                restore_main_window(&app);
                return validated(
                    "reauthenticate",
                    unavailable("reauthenticate", &request, "provider-unavailable"),
                );
            };
            let prepared = call_internal(
                &state,
                "host_internal.credential_prepare",
                json!({"credential_reference": reference}),
            );
            if !matches!(prepared, Ok(ref result) if result["status"] == "prepared") {
                let _ = state.native.delete_reference(&reference);
                return validated(
                    "reauthenticate",
                    unavailable("reauthenticate", &request, "outcome-unknown"),
                );
            }
            match call_internal(
                &state,
                "host_internal.credential_commit",
                json!({
                    "credential_reference": reference,
                    "expected_generation": context["generation"],
                    "principal_ref": principal,
                    "provider_id": context["provider_id"],
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
                    match refresh_principal(&state, principal, REFRESH_DEADLINE) {
                        Ok(()) => json!({"reauth_state": "succeeded", "status": "ok"}),
                        Err(code) => json!({
                            "reauth_state": "failed",
                            "safe_error": safe_error(code, code == "provider-unavailable"),
                            "status": "error"
                        }),
                    }
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
    validate_request("export_redacted", &request).map_err(|_| "request rejected".to_owned())?;
    let accounts = call_sidecar(
        &state,
        "accounts_read",
        json!({"scope_ref": request["scope_ref"]}),
        DEFAULT_BUDGET_NS,
    )?;
    let quota = call_sidecar(
        &state,
        "quota_overview",
        json!({"scope_ref": request["scope_ref"]}),
        DEFAULT_BUDGET_NS,
    )?;
    let scheduler = call_sidecar(&state, "scheduler_state", json!({}), DEFAULT_BUDGET_NS)?;
    let response = if [&accounts, &quota, &scheduler]
        .iter()
        .any(|value| value["status"].as_str() != Some("ok"))
    {
        unavailable("export_redacted", &request, "provider-unavailable")
    } else {
        let diagnostics = redacted_diagnostics(&accounts, &quota, &scheduler);
        let content = serde_json::to_vec_pretty(&diagnostics).map_err(|_| "export failed")?;
        match state.native.export_redacted(json!({
            "action": "export-redacted",
            "exportContentBase64": BASE64.encode(content),
            "exportFilename": "agent-quota-diagnostics.json"
        })) {
            Ok(native) if native.status == "exported" => {
                json!({"export_status": "completed", "status": "ok"})
            }
            Ok(native) if native.status == "cancelled" => {
                json!({"export_status": "cancelled", "status": "ok"})
            }
            Ok(_) => unavailable("export_redacted", &request, "provider-unavailable"),
            Err(error) => unavailable("export_redacted", &request, native_error_code(&error)),
        }
    };
    validated("export_redacted", response)
}

fn redacted_diagnostics(accounts: &Value, quota: &Value, scheduler: &Value) -> Value {
    let summaries = accounts["accounts"]
        .as_array()
        .map(Vec::as_slice)
        .unwrap_or(&[]);
    let lifecycle_count = |lifecycle: &str| {
        summaries
            .iter()
            .filter(|account| account["lifecycle"].as_str() == Some(lifecycle))
            .count()
    };
    json!({
        "account_count": summaries.len(),
        "lifecycle_counts": {
            "active": lifecycle_count("active"),
            "disabled": lifecycle_count("disabled"),
            "needs_reauth": lifecycle_count("needs-reauth")
        },
        "quota": {
            "freshness": quota["projection"]["freshness"],
            "row_count": quota["projection"]["capability_rows"]
                .as_array()
                .map(Vec::len)
                .unwrap_or(0)
        },
        "scheduler": scheduler["scheduler_state"],
        "schema": "agent-quota-redacted-diagnostics-v1",
        "security": {
            "credential_backend": "macOS Keychain",
            "renderer_secret_material": false
        }
    })
}

#[tauri::command]
fn scheduler_state(state: State<'_, HostState>, request: Value) -> CommandResult {
    call_sidecar(&state, "scheduler_state", request, DEFAULT_BUDGET_NS)
}

fn app_data_root() -> Result<PathBuf, InstanceLeaseError> {
    #[cfg(feature = "development-overrides")]
    if let Some(data_root) = std::env::var_os("AQ_DATA_ROOT") {
        return Ok(PathBuf::from(data_root));
    }
    fixed_app_data_root()
}

fn sidecar_spec(executable: Option<PathBuf>, data_root: &Path) -> Option<(PathBuf, Vec<String>)> {
    let arguments = vec![
        "--data-root".to_owned(),
        data_root.to_string_lossy().into_owned(),
    ];
    #[cfg(feature = "development-overrides")]
    if let Some(path) = std::env::var_os("AQ_SIDECAR_EXECUTABLE") {
        return Some((PathBuf::from(path), arguments));
    }
    executable.map(|path| (path, arguments))
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
        .setup(move |app| {
            let (sidecar_executable, native_executable) = runtime_resources(app);
            let mut sidecar = sidecar_spec(sidecar_executable, &data_root)
                .and_then(|(path, arguments)| SidecarSupervisor::spawn(&path, &arguments).ok());
            let native = NativeHost::new(native_executable);
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
            app.manage(HostState {
                _instance_lease: instance_lease,
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

    #[test]
    fn keychain_locked_refresh_remains_actionable_and_non_retryable() {
        let response = unavailable(
            "refresh_scope",
            &json!({"scope_ref": "scope"}),
            bounded_provider_error(Some("keychain-locked")),
        );
        assert_eq!(response["safe_error"]["code"], "keychain-locked");
        assert_eq!(response["safe_error"]["retryable"], false);
        validate_response("refresh_scope", response).unwrap();
    }

    #[test]
    fn refresh_selection_skips_disabled_and_rejects_unknown_scope() {
        let accounts = json!({"accounts": [
            {"principal_ref": "active", "lifecycle": "active"},
            {"principal_ref": "disabled", "lifecycle": "disabled"}
        ]});
        assert_eq!(
            select_refresh_principals(&accounts, "scope-all").unwrap(),
            ["active"]
        );
        assert_eq!(
            select_refresh_principals(&accounts, "disabled"),
            Err("contract-error")
        );
        assert_eq!(
            select_refresh_principals(&accounts, "missing"),
            Err("contract-error")
        );
    }

    #[test]
    fn refresh_rejects_failed_accounts_snapshot() {
        let unavailable_accounts = unavailable(
            "accounts_read",
            &json!({"scope_ref": "scope-all"}),
            "provider-unavailable",
        );
        assert_eq!(
            refresh_accounts_error(&unavailable_accounts),
            Some("provider-unavailable")
        );
        assert_eq!(
            refresh_accounts_error(&json!({"accounts": [], "status": "ok"})),
            None
        );
    }

    #[test]
    fn diagnostics_export_contains_counts_without_identifiers() {
        let document = redacted_diagnostics(
            &json!({"accounts": [
                {"principal_ref": "secret-ref", "display_label": "private", "lifecycle": "active"},
                {"principal_ref": "other", "display_label": "private", "lifecycle": "needs-reauth"}
            ], "status": "ok"}),
            &json!({"projection": {"capability_rows": [{"capability_ref": "secret-cap"}], "freshness": "stale"}, "status": "ok"}),
            &json!({"scheduler_state": {"health": "absent", "installed": false}, "status": "ok"}),
        );
        let encoded = serde_json::to_string(&document).unwrap();
        assert_eq!(document["account_count"], 2);
        assert_eq!(document["quota"]["row_count"], 1);
        assert_eq!(document["lifecycle_counts"]["needs_reauth"], 1);
        assert!(!encoded.contains("secret-ref"));
        assert!(!encoded.contains("secret-cap"));
        assert!(!encoded.contains("private"));
    }
}
