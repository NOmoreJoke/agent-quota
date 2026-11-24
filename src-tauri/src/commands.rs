use crate::contract::{safe_error, validate_request};
use crate::diagnostics::redacted_diagnostics;
use crate::refresh::{REFRESH_DEADLINE, refresh_principal, refresh_scope_inner};
use crate::supervisor::SupervisorError;
use crate::window::{restore_main_window, window_ready};
use crate::{
    CommandResult, DEFAULT_BUDGET_NS, HostState, call_internal, call_sidecar,
    cleanup_credential_candidate, cleanup_references, create_credential_candidate,
    native_error_code, unavailable, validated,
};
use base64::{Engine as _, engine::general_purpose::STANDARD as BASE64};
use serde_json::{Value, json};
use tauri::{AppHandle, Emitter, Manager};

async fn read_projection(app: AppHandle, command: &'static str, request: Value) -> CommandResult {
    // Waiting for the shared sidecar must not freeze dragging or hover on the UI thread.
    tauri::async_runtime::spawn_blocking(move || {
        call_sidecar(
            app.state::<HostState>().inner(),
            command,
            request,
            DEFAULT_BUDGET_NS,
        )
    })
    .await
    .map_err(|_| "projection task unavailable".to_owned())?
}

#[tauri::command]
pub(crate) async fn bootstrap_state(app: AppHandle, request: Value) -> CommandResult {
    read_projection(app, "bootstrap_state", request).await
}

#[tauri::command]
pub(crate) async fn accounts_read(app: AppHandle, request: Value) -> CommandResult {
    read_projection(app, "accounts_read", request).await
}

#[tauri::command]
pub(crate) async fn quota_overview(app: AppHandle, request: Value) -> CommandResult {
    read_projection(app, "quota_overview", request).await
}

#[tauri::command]
pub(crate) async fn scheduler_state(app: AppHandle, request: Value) -> CommandResult {
    read_projection(app, "scheduler_state", request).await
}

#[tauri::command]
pub(crate) async fn refresh_scope(window: tauri::WebviewWindow, request: Value) -> CommandResult {
    let app = window.app_handle().clone();
    let source = window.label().to_owned();
    tauri::async_runtime::spawn_blocking(move || {
        let response = refresh_scope_inner(app.state::<HostState>().inner(), request)?;
        if response["refresh_state"]["phase"] != "running" {
            let outcome = if response["safe_error"]["code"] == "outcome-unknown" {
                "unknown"
            } else if response["status"] == "ok" {
                "success"
            } else {
                "warning"
            };
            let _ = app.emit(
                "quota-projection-changed",
                json!({"source": source, "refreshOutcome": outcome}),
            );
        }
        Ok(response)
    })
    .await
    .map_err(|_| "refresh task unavailable".to_owned())?
}

#[tauri::command]
pub(crate) async fn config_validate_apply(app: AppHandle, request: Value) -> CommandResult {
    tauri::async_runtime::spawn_blocking(move || {
        let state = app.state::<HostState>();
        let Ok(_transaction) = state.credential_destructive_transaction.try_lock() else {
            return validated(
                "config_validate_apply",
                unavailable("config_validate_apply", &request, "not-authorized"),
            );
        };
        call_sidecar(
            state.inner(),
            "config_validate_apply",
            request,
            DEFAULT_BUDGET_NS,
        )
    })
    .await
    .map_err(|_| "config task unavailable".to_owned())?
}

#[tauri::command]
pub(crate) async fn credential_dialog_open(app: AppHandle, request: Value) -> CommandResult {
    validate_request("credential_dialog_open", &request)
        .map_err(|_| "request rejected".to_owned())?;
    let ready = window_ready(&app);
    tauri::async_runtime::spawn_blocking(move || {
        credential_dialog_open_inner(&app, app.state::<HostState>().inner(), request, ready)
    })
    .await
    .map_err(|_| "credential task unavailable".to_owned())?
}

fn credential_dialog_open_inner(
    app: &AppHandle,
    state: &HostState,
    request: Value,
    ready: bool,
) -> CommandResult {
    if !ready || request["dialog_purpose"].as_str() != Some("create-credential-reference") {
        return validated(
            "credential_dialog_open",
            unavailable("credential_dialog_open", &request, "not-authorized"),
        );
    }
    let _transaction = match state.credential_destructive_transaction.try_lock() {
        Ok(transaction) => transaction,
        Err(_) => {
            return validated(
                "credential_dialog_open",
                unavailable("credential_dialog_open", &request, "not-authorized"),
            );
        }
    };
    let reference = match create_credential_candidate(state) {
        Ok(reference) => reference,
        Err(error) => {
            return validated(
                "credential_dialog_open",
                unavailable(
                    "credential_dialog_open",
                    &request,
                    if matches!(error, SupervisorError::OutcomeUnknown) {
                        "outcome-unknown"
                    } else {
                        "provider-unavailable"
                    },
                ),
            );
        }
    };
    let response = match state.native.credential(json!({
        "action": "credential",
        "dialogPurpose": "create-credential-reference",
        "opaqueReference": reference
    })) {
        Ok(response) if response.status == "cancelled" => {
            if cleanup_credential_candidate(state, &reference) {
                json!({"opaque_reference_status": "cancelled", "status": "cancelled"})
            } else {
                unavailable("credential_dialog_open", &request, "provider-unavailable")
            }
        }
        Ok(response) if response.status == "reference-created" => {
            let (Some(returned_reference), Some(provider)) =
                (response.opaque_reference, response.provider)
            else {
                let _ = cleanup_credential_candidate(state, &reference);
                restore_main_window(app);
                return validated(
                    "credential_dialog_open",
                    unavailable("credential_dialog_open", &request, "provider-unavailable"),
                );
            };
            if returned_reference != reference {
                let _ = cleanup_credential_candidate(state, &reference);
                restore_main_window(app);
                return validated(
                    "credential_dialog_open",
                    unavailable("credential_dialog_open", &request, "provider-unavailable"),
                );
            }
            match call_internal(
                state,
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
                    match refresh_principal(state, principal, REFRESH_DEADLINE) {
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
                    let _ = cleanup_credential_candidate(state, &reference);
                    unavailable("credential_dialog_open", &request, "provider-unavailable")
                }
            }
        }
        Ok(response) => {
            let _ = response.error_code;
            let code = if cleanup_credential_candidate(state, &reference) {
                "not-authorized"
            } else {
                "provider-unavailable"
            };
            unavailable("credential_dialog_open", &request, code)
        }
        Err(error) => {
            let code = if cleanup_credential_candidate(state, &reference) {
                native_error_code(&error)
            } else {
                "provider-unavailable"
            };
            unavailable("credential_dialog_open", &request, code)
        }
    };
    restore_main_window(app);
    let _ = app.emit("quota-projection-changed", json!({"source": "main"}));
    validated("credential_dialog_open", response)
}

#[tauri::command]
pub(crate) async fn destructive_confirmation_open(app: AppHandle, request: Value) -> CommandResult {
    validate_request("destructive_confirmation_open", &request)
        .map_err(|_| "request rejected".to_owned())?;
    let ready = window_ready(&app);
    tauri::async_runtime::spawn_blocking(move || {
        destructive_confirmation_open_inner(&app, app.state::<HostState>().inner(), request, ready)
    })
    .await
    .map_err(|_| "destructive task unavailable".to_owned())?
}

fn destructive_confirmation_open_inner(
    app: &AppHandle,
    state: &HostState,
    request: Value,
    ready: bool,
) -> CommandResult {
    if !ready {
        return validated(
            "destructive_confirmation_open",
            unavailable("destructive_confirmation_open", &request, "not-authorized"),
        );
    }
    let _transaction = match state.credential_destructive_transaction.try_lock() {
        Ok(transaction) => transaction,
        Err(_) => {
            return validated(
                "destructive_confirmation_open",
                unavailable("destructive_confirmation_open", &request, "not-authorized"),
            );
        }
    };
    let plan = match call_internal(state, "host_internal.destructive_prepare", request.clone()) {
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
    restore_main_window(app);
    let response = match native_response {
        Ok(response) if response.status == "cancelled" => {
            let _ = call_internal(
                state,
                "host_internal.destructive_cancel",
                json!({"plan_id": plan_id}),
            );
            json!({"status": "cancelled"})
        }
        Ok(response) if response.status == "confirmed" => {
            let Some(token) = response.user_presence_token else {
                restore_main_window(app);
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
                state,
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
                    if cleanup_references(state, &result["cleanup_references"]) {
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
                state,
                "host_internal.destructive_cancel",
                json!({"plan_id": plan_id}),
            );
            unavailable("destructive_confirmation_open", &request, "not-authorized")
        }
        Err(error) => {
            let _ = call_internal(
                state,
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
    let _ = app.emit("quota-projection-changed", json!({"source": "main"}));
    validated("destructive_confirmation_open", response)
}

#[tauri::command]
pub(crate) async fn reauthenticate(app: AppHandle, request: Value) -> CommandResult {
    validate_request("reauthenticate", &request).map_err(|_| "request rejected".to_owned())?;
    let ready = window_ready(&app);
    tauri::async_runtime::spawn_blocking(move || {
        reauthenticate_inner(&app, app.state::<HostState>().inner(), request, ready)
    })
    .await
    .map_err(|_| "reauth task unavailable".to_owned())?
}

fn reauthenticate_inner(
    app: &AppHandle,
    state: &HostState,
    request: Value,
    ready: bool,
) -> CommandResult {
    if !ready {
        return validated(
            "reauthenticate",
            unavailable("reauthenticate", &request, "not-authorized"),
        );
    }
    let _transaction = match state.credential_destructive_transaction.try_lock() {
        Ok(transaction) => transaction,
        Err(_) => {
            return validated(
                "reauthenticate",
                unavailable("reauthenticate", &request, "not-authorized"),
            );
        }
    };
    let principal = request["principal_ref"].as_str().unwrap_or_default();
    let context = match call_internal(
        state,
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
    if context["provider_id"].as_str() == Some("antigravity") {
        return validated(
            "reauthenticate",
            unavailable("reauthenticate", &request, "not-authorized"),
        );
    }
    let reference = match create_credential_candidate(state) {
        Ok(reference) => reference,
        Err(error) => {
            return validated(
                "reauthenticate",
                unavailable(
                    "reauthenticate",
                    &request,
                    if matches!(error, SupervisorError::OutcomeUnknown) {
                        "outcome-unknown"
                    } else {
                        "provider-unavailable"
                    },
                ),
            );
        }
    };
    let native_response = state.native.credential(json!({
        "action": "credential",
        "dialogPurpose": "replace-credential-reference",
        "opaqueReference": reference,
        "provider": context["provider_id"]
    }));
    restore_main_window(app);
    let response = match native_response {
        Ok(response) if response.status == "cancelled" => {
            if cleanup_credential_candidate(state, &reference) {
                json!({"reauth_state": "cancelled", "status": "ok"})
            } else {
                unavailable("reauthenticate", &request, "provider-unavailable")
            }
        }
        Ok(response) if response.status == "reference-replaced" => {
            let Some(returned_reference) = response.opaque_reference else {
                let _ = cleanup_credential_candidate(state, &reference);
                restore_main_window(app);
                return validated(
                    "reauthenticate",
                    unavailable("reauthenticate", &request, "provider-unavailable"),
                );
            };
            if returned_reference != reference {
                let _ = cleanup_credential_candidate(state, &reference);
                return validated(
                    "reauthenticate",
                    unavailable("reauthenticate", &request, "provider-unavailable"),
                );
            }
            match call_internal(
                state,
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
                    if let Some(old) = result["old_reference"].as_str()
                        && state.native.delete_reference(old).is_ok()
                    {
                        let _ = call_internal(
                            state,
                            "host_internal.cleanup_ack",
                            json!({"references": [old]}),
                        );
                    }
                    match refresh_principal(state, principal, REFRESH_DEADLINE) {
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
                    let _ = cleanup_credential_candidate(state, &reference);
                    unavailable("reauthenticate", &request, "provider-unavailable")
                }
            }
        }
        Ok(_) => {
            let code = if cleanup_credential_candidate(state, &reference) {
                "not-authorized"
            } else {
                "provider-unavailable"
            };
            unavailable("reauthenticate", &request, code)
        }
        Err(error) => {
            let code = if cleanup_credential_candidate(state, &reference) {
                native_error_code(&error)
            } else {
                "provider-unavailable"
            };
            unavailable("reauthenticate", &request, code)
        }
    };
    let _ = app.emit("quota-projection-changed", json!({"source": "main"}));
    validated("reauthenticate", response)
}

#[tauri::command]
pub(crate) async fn export_redacted(app: AppHandle, request: Value) -> CommandResult {
    validate_request("export_redacted", &request).map_err(|_| "request rejected".to_owned())?;
    tauri::async_runtime::spawn_blocking(move || {
        export_redacted_inner(app.state::<HostState>().inner(), request)
    })
    .await
    .map_err(|_| "export task unavailable".to_owned())?
}

fn export_redacted_inner(state: &HostState, request: Value) -> CommandResult {
    let accounts = call_sidecar(
        state,
        "accounts_read",
        json!({"scope_ref": request["scope_ref"]}),
        DEFAULT_BUDGET_NS,
    )?;
    let quota = call_sidecar(
        state,
        "quota_overview",
        json!({"scope_ref": request["scope_ref"]}),
        DEFAULT_BUDGET_NS,
    )?;
    let scheduler = call_sidecar(state, "scheduler_state", json!({}), DEFAULT_BUDGET_NS)?;
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
