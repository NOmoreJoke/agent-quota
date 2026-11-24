use serde_json::{Value, json};

pub(crate) fn redacted_diagnostics(accounts: &Value, quota: &Value, scheduler: &Value) -> Value {
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

#[cfg(test)]
mod tests {
    use super::*;

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
