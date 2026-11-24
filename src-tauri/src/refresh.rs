use crate::contract::validate_request;
use crate::{
    CommandResult, DEFAULT_BUDGET_NS, HostState, call_internal, call_sidecar, native_error_code,
    unavailable, validated,
};
use serde_json::{Value, json};
use std::time::{Duration, Instant};

pub(crate) const REFRESH_DEADLINE: Duration = Duration::from_secs(30);

pub(crate) fn bounded_provider_error(code: Option<&str>) -> &'static str {
    match code {
        Some("keychain-locked") => "keychain-locked",
        Some("reauth-required") => "reauth-required",
        Some("contract-error") => "contract-error",
        Some("timeout") => "timeout",
        _ => "provider-unavailable",
    }
}

fn commit_provider_failure(
    state: &HostState,
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

pub(crate) fn refresh_principal(
    state: &HostState,
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
    // Local statusLine push accounts have no remote HTTP endpoint; preserve their latest local snapshot.
    if context["credential_type"].as_str() == Some("agy-statusline-stdin") {
        return Ok(());
    }
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

pub(crate) fn select_refresh_principals(
    accounts: &Value,
    scope: &str,
) -> Result<Vec<String>, &'static str> {
    let items = accounts["accounts"]
        .as_array()
        .map(Vec::as_slice)
        .unwrap_or(&[]);
    if scope != "scope-all" {
        let Some(target) = items
            .iter()
            .find(|account| account["principal_ref"].as_str() == Some(scope))
        else {
            return Err("contract-error");
        };
        return match target["lifecycle"].as_str() {
            Some("active") => Ok(vec![scope.to_owned()]),
            Some("needs-reauth") => Err("reauth-required"),
            Some("disabled") => Err("not-authorized"),
            _ => Err("contract-error"),
        };
    }
    Ok(items
        .iter()
        .filter(|account| account["lifecycle"].as_str() == Some("active"))
        .filter_map(|account| account["principal_ref"].as_str().map(str::to_owned))
        .collect())
}

pub(crate) fn refresh_accounts_error(accounts: &Value) -> Option<&str> {
    (accounts["status"].as_str() != Some("ok")).then(|| {
        accounts["safe_error"]["code"]
            .as_str()
            .unwrap_or("provider-unavailable")
    })
}

pub(crate) fn refresh_scope_inner(state: &HostState, request: Value) -> CommandResult {
    validate_request("refresh_scope", &request).map_err(|_| "request rejected".to_owned())?;
    let Ok(_refresh_guard) = state.refresh_transaction.try_lock() else {
        return validated(
            "refresh_scope",
            json!({"refresh_state": {"phase": "running"}, "status": "running"}),
        );
    };
    // Account generations must stay stable from fetch-plan through commit.
    // Native account dialogs use the same gate without blocking the UI thread.
    let Ok(_account_guard) = state.credential_destructive_transaction.try_lock() else {
        return validated(
            "refresh_scope",
            unavailable("refresh_scope", &request, "not-authorized"),
        );
    };
    let scope = request["scope_ref"].as_str().unwrap_or_default();
    let accounts = call_sidecar(
        state,
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
        if let Err(code) = refresh_principal(state, &principal, remaining) {
            first_error.get_or_insert(code);
        }
    }
    let response = match first_error {
        Some(code) => unavailable("refresh_scope", &request, code),
        None => json!({"refresh_state": {"phase": "completed"}, "status": "ok"}),
    };
    validated("refresh_scope", response)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::contract::validate_response;

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
    fn refresh_selection_classifies_needs_reauth_disabled_and_missing_scopes() {
        let accounts = json!({"accounts": [
            {"principal_ref": "active", "lifecycle": "active"},
            {"principal_ref": "reauth", "lifecycle": "needs-reauth"},
            {"principal_ref": "disabled", "lifecycle": "disabled"}
        ]});
        assert_eq!(
            select_refresh_principals(&accounts, "scope-all").unwrap(),
            ["active"]
        );
        assert_eq!(
            select_refresh_principals(&accounts, "reauth"),
            Err("reauth-required")
        );
        assert_eq!(
            select_refresh_principals(&accounts, "disabled"),
            Err("not-authorized")
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
    fn local_bridge_credential_type_is_distinguished_from_oauth() {
        let bridge_ctx = json!({
            "credential_reference": "credential-00000000-0000-4000-8000-616e74696772",
            "credential_type": "agy-statusline-stdin",
            "generation": 1,
            "provider_id": "antigravity",
            "status": "ok"
        });
        let oauth_ctx = json!({
            "credential_reference": "credential-00000000-0000-4000-8000-000000000001",
            "credential_type": "oauth-google-cloudcode",
            "generation": 2,
            "provider_id": "antigravity",
            "status": "ok"
        });
        assert_eq!(
            bridge_ctx["credential_type"].as_str(),
            Some("agy-statusline-stdin")
        );
        assert_ne!(
            oauth_ctx["credential_type"].as_str(),
            Some("agy-statusline-stdin")
        );
    }
}
