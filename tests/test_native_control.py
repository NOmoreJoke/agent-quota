from __future__ import annotations

import base64
import json
import os
from pathlib import Path

import pytest

from agent_quota.native_control import NativeControlPlane


def reference(seed: int) -> str:
    return f"credential-00000000-0000-4000-8000-{seed:012x}"


def provider_body(document: object) -> str:
    return base64.b64encode(json.dumps(document).encode()).decode()


def test_create_persists_renderer_safe_account_and_permissions(tmp_path: Path) -> None:
    root = (tmp_path / "private").absolute()
    control = NativeControlPlane(root)
    commit = control.commit_credential(
        purpose="create-credential-reference",
        credential_reference=reference(1),
        principal_ref=None,
        expected_generation=None,
    )
    assert control.renderer_accounts() == [
        {
            "principal_ref": commit.principal_ref,
            "display_label": "DeepSeek",
            "lifecycle": "active",
        }
    ]
    assert "credential_reference" not in json.dumps(control.renderer_accounts())
    assert os.stat(root).st_mode & 0o777 == 0o700
    assert os.stat(root / "native-accounts-v1.json").st_mode & 0o777 == 0o600
    restored = NativeControlPlane(root)
    assert restored.renderer_accounts() == control.renderer_accounts()


def test_replace_generation_drift_and_duplicate_are_rejected(tmp_path: Path) -> None:
    control = NativeControlPlane((tmp_path / "private").absolute())
    created = control.commit_credential(
        purpose="create-credential-reference",
        credential_reference=reference(1),
        principal_ref=None,
        expected_generation=None,
    )
    _, generation = control.credential_reference(created.principal_ref)
    replaced = control.commit_credential(
        purpose="replace-credential-reference",
        credential_reference=reference(2),
        principal_ref=created.principal_ref,
        expected_generation=generation,
    )
    assert replaced.old_reference == reference(1)
    assert control.cleanup_pending() == [reference(1)]
    control.acknowledge_cleanup([reference(1)])
    assert control.cleanup_pending() == []
    with pytest.raises(ValueError, match="unknown cleanup"):
        control.acknowledge_cleanup([reference(1)])
    with pytest.raises(ValueError, match="generation drift"):
        control.commit_credential(
            purpose="replace-credential-reference",
            credential_reference=reference(3),
            principal_ref=created.principal_ref,
            expected_generation=generation,
        )
    with pytest.raises(ValueError, match="already committed"):
        control.commit_credential(
            purpose="create-credential-reference",
            credential_reference=reference(2),
            principal_ref=None,
            expected_generation=None,
        )


def test_provider_projection_persists_and_rotation_fences_old_observation(tmp_path: Path) -> None:
    root = (tmp_path / "private").absolute()
    control = NativeControlPlane(root)
    created = control.commit_credential(
        purpose="create-credential-reference",
        credential_reference=reference(1),
        principal_ref=None,
        expected_generation=None,
        provider_id="deepseek",
    )
    _, generation, provider = control.credential_context(created.principal_ref)
    error, retryable = control.commit_provider_response(
        principal_ref=created.principal_ref,
        expected_generation=generation,
        provider_id=provider,
        http_status=200,
        body_base64=provider_body(
            {
                "is_available": True,
                "balance_infos": [{"currency": "CNY", "total_balance": "9.5"}],
            }
        ),
    )
    assert (error, retryable) == (None, False)
    assert "CNY 9.5" in control.quota_projection("scope-all")["capability_rows"][0]["value_display"]
    successful_projection = control.quota_projection("scope-all")["capability_rows"]
    error, retryable = control.commit_provider_response(
        principal_ref=created.principal_ref,
        expected_generation=generation,
        provider_id=provider,
        http_status=500,
        body_base64="ignored",
    )
    assert (error, retryable) == ("provider-unavailable", True)
    assert control.quota_projection("scope-all")["capability_rows"] == successful_projection
    assert control.renderer_accounts()[0]["last_error_code"] == "provider-unavailable"
    restored = NativeControlPlane(root)
    assert restored.quota_projection("scope-all") == control.quota_projection("scope-all")

    restored.commit_credential(
        purpose="replace-credential-reference",
        credential_reference=reference(2),
        principal_ref=created.principal_ref,
        expected_generation=generation,
        provider_id="deepseek",
    )
    assert restored.quota_projection("scope-all")["capability_rows"] == []
    with pytest.raises(ValueError, match="generation drift"):
        restored.commit_provider_response(
            principal_ref=created.principal_ref,
            expected_generation=generation,
            provider_id="deepseek",
            http_status=200,
            body_base64=provider_body({}),
        )
    _, rotated_generation, _ = restored.credential_context(created.principal_ref)
    error, _ = restored.commit_provider_response(
        principal_ref=created.principal_ref,
        expected_generation=rotated_generation,
        provider_id="deepseek",
        http_status=401,
        body_base64="ignored",
    )
    assert error == "reauth-required"
    assert restored.renderer_accounts()[0]["lifecycle"] == "needs-reauth"


def test_reauth_failure_preserves_lkg_but_forces_stale(tmp_path: Path) -> None:
    control = NativeControlPlane((tmp_path / "private").absolute())
    created = control.commit_credential(
        purpose="create-credential-reference",
        credential_reference=reference(1),
        principal_ref=None,
        expected_generation=None,
        provider_id="deepseek",
    )
    _, generation, provider = control.credential_context(created.principal_ref)
    control.commit_provider_response(
        principal_ref=created.principal_ref,
        expected_generation=generation,
        provider_id=provider,
        http_status=200,
        body_base64=provider_body(
            {"is_available": True, "balance_infos": [{"currency": "CNY", "total_balance": "9.5"}]}
        ),
    )
    assert control.quota_projection("scope-all")["freshness"] == "fresh"
    control.commit_provider_response(
        principal_ref=created.principal_ref,
        expected_generation=generation,
        provider_id=provider,
        http_status=401,
        body_base64="ignored",
    )
    projection = control.quota_projection("scope-all")
    assert projection["capability_rows"]
    assert projection["freshness"] == "stale"
    assert (
        NativeControlPlane((tmp_path / "private").absolute()).quota_projection("scope-all")[
            "freshness"
        ]
        == "stale"
    )


def test_account_projection_ids_are_unique_and_failures_preserve_rows(tmp_path: Path) -> None:
    control = NativeControlPlane((tmp_path / "private").absolute())
    created = [
        control.commit_credential(
            purpose="create-credential-reference",
            credential_reference=reference(seed),
            principal_ref=None,
            expected_generation=None,
            provider_id="deepseek",
        )
        for seed in (1, 2)
    ]
    for commit in created:
        _, generation, provider = control.credential_context(commit.principal_ref)
        control.commit_provider_response(
            principal_ref=commit.principal_ref,
            expected_generation=generation,
            provider_id=provider,
            http_status=200,
            body_base64=provider_body(
                {"is_available": True, "balance_infos": [{"currency": "CNY", "total_balance": "1"}]}
            ),
        )
    rows = control.quota_projection("scope-all")["capability_rows"]
    assert len(rows) == 2
    assert len({row["capability_ref"] for row in rows}) == 2
    assert all(row["capability_ref"].startswith("cap-deepseek-account-") for row in rows)
    _, generation, provider = control.credential_context(created[0].principal_ref)
    control.commit_provider_failure(
        principal_ref=created[0].principal_ref,
        expected_generation=generation,
        provider_id=provider,
        safe_error_code="keychain-locked",
    )
    assert control.renderer_accounts()[0]["last_error_code"] == "keychain-locked"
    assert len(control.quota_projection("scope-all")["capability_rows"]) == 2


def test_destructive_two_phase_cancel_drift_replay_and_commit(tmp_path: Path) -> None:
    control = NativeControlPlane((tmp_path / "private").absolute())
    control.commit_credential(
        purpose="create-credential-reference",
        credential_reference=reference(1),
        principal_ref=None,
        expected_generation=None,
    )
    cancelled = control.prepare_destructive(
        operation_intent="purge",
        opaque_selection_handle="selection-all-local-data",
    )
    assert control.cancel_destructive(cancelled.plan_id)
    with pytest.raises(ValueError, match="unknown or consumed"):
        control.commit_destructive(
            plan_id=cancelled.plan_id,
            digest=cancelled.digest,
            generation=cancelled.generation,
            nonce=cancelled.nonce,
            user_presence_token="00000000-0000-4000-8000-000000000001",
        )
    drifted = control.prepare_destructive(
        operation_intent="purge",
        opaque_selection_handle="selection-all-local-data",
    )
    control.commit_credential(
        purpose="create-credential-reference",
        credential_reference=reference(2),
        principal_ref=None,
        expected_generation=None,
    )
    with pytest.raises(ValueError, match="drift"):
        control.commit_destructive(
            plan_id=drifted.plan_id,
            digest=drifted.digest,
            generation=drifted.generation,
            nonce=drifted.nonce,
            user_presence_token="00000000-0000-4000-8000-000000000002",
        )
    committed = control.prepare_destructive(
        operation_intent="purge",
        opaque_selection_handle="selection-all-local-data",
    )
    token = "00000000-0000-4000-8000-000000000003"
    control.commit_destructive(
        plan_id=committed.plan_id,
        digest=committed.digest,
        generation=committed.generation,
        nonce=committed.nonce,
        user_presence_token=token,
    )
    assert control.renderer_accounts() == []
    assert control.cleanup_pending() == [reference(1), reference(2)]
    with pytest.raises(ValueError, match="replay|unknown or consumed"):
        control.commit_destructive(
            plan_id=committed.plan_id,
            digest=committed.digest,
            generation=committed.generation,
            nonce=committed.nonce,
            user_presence_token=token,
        )


def test_unknown_state_fields_and_symlink_fail_closed(tmp_path: Path) -> None:
    root = (tmp_path / "private").absolute()
    control = NativeControlPlane(root)
    control.commit_credential(
        purpose="create-credential-reference",
        credential_reference=reference(1),
        principal_ref=None,
        expected_generation=None,
    )
    state = json.loads(control.path.read_text())
    state["extra"] = True
    control.path.write_text(json.dumps(state))
    with pytest.raises(ValueError, match="shape"):
        NativeControlPlane(root)
    control.path.unlink()
    control.path.symlink_to(tmp_path / "outside")
    with pytest.raises(ValueError, match="regular"):
        NativeControlPlane(root)


def test_invalid_roots_state_bounds_and_credential_inputs_fail_closed(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="absolute"):
        NativeControlPlane(Path("relative"))
    file_root = (tmp_path / "file-root").absolute()
    file_root.write_text("not a directory")
    with pytest.raises((FileExistsError, ValueError)):
        NativeControlPlane(file_root)
    root = (tmp_path / "private").absolute()
    control = NativeControlPlane(root)
    control.path.write_bytes(b"x" * (64 * 1024 + 1))
    control.path.chmod(0o600)
    with pytest.raises(ValueError, match="oversized"):
        NativeControlPlane(root)
    control.path.unlink()
    control.path.write_text(
        '{"schema":"wrong","generation":0,"accounts":[],"pending_keychain_deletions":[]}'
    )
    control.path.chmod(0o600)
    with pytest.raises(ValueError, match="schema"):
        NativeControlPlane(root)
    control.path.unlink()
    control = NativeControlPlane(root)
    control.path.write_text(
        '{"schema":"aq-native-account-state-v1","generation":0,"accounts":[],"pending_keychain_deletions":[]}'
    )
    with pytest.raises(ValueError, match="permissions"):
        NativeControlPlane(root)
    control.path.unlink()
    control = NativeControlPlane(root)
    with pytest.raises(ValueError, match="invalid credential reference"):
        control.commit_credential(
            purpose="create-credential-reference",
            credential_reference="bad",
            principal_ref=None,
            expected_generation=None,
        )
    with pytest.raises(ValueError, match="invalid credential reference"):
        control.commit_credential(
            purpose="create-credential-reference",
            credential_reference="credential-000000000-000-4000-8000-000000000001",
            principal_ref=None,
            expected_generation=None,
        )
    with pytest.raises(ValueError, match="context"):
        control.commit_credential(
            purpose="create-credential-reference",
            credential_reference=reference(1),
            principal_ref="principal-000000000000000000000000",
            expected_generation=0,
        )
    with pytest.raises(ValueError, match="unknown credential purpose"):
        control.commit_credential(
            purpose="other",
            credential_reference=reference(1),
            principal_ref=None,
            expected_generation=None,
        )
    with pytest.raises(ValueError, match="missing"):
        control.commit_credential(
            purpose="replace-credential-reference",
            credential_reference=reference(1),
            principal_ref=None,
            expected_generation=None,
        )
    with pytest.raises(ValueError, match="invalid principal"):
        control.credential_reference("bad")


def test_destructive_intents_require_exact_scope_and_apply(tmp_path: Path) -> None:
    control = NativeControlPlane((tmp_path / "private").absolute())
    created = control.commit_credential(
        purpose="create-credential-reference",
        credential_reference=reference(1),
        principal_ref=None,
        expected_generation=None,
    )
    with pytest.raises(ValueError, match="unknown destructive"):
        control.prepare_destructive(
            operation_intent="unknown",
            opaque_selection_handle="selection-all-local-data",
        )
    with pytest.raises(ValueError, match="scope mismatch"):
        control.prepare_destructive(
            operation_intent="purge",
            opaque_selection_handle=created.principal_ref,
        )
    with pytest.raises(ValueError, match="unknown destructive selection"):
        control.prepare_destructive(
            operation_intent="delete",
            opaque_selection_handle="principal-000000000000000000000000",
        )
    disabled = control.prepare_destructive(
        operation_intent="disable",
        opaque_selection_handle=created.principal_ref,
    )
    control.commit_destructive(
        plan_id=disabled.plan_id,
        digest=disabled.digest,
        generation=disabled.generation,
        nonce=disabled.nonce,
        user_presence_token="00000000-0000-4000-8000-000000000010",
    )
    assert control.renderer_accounts()[0]["lifecycle"] == "disabled"
    config = control.prepare_destructive(
        operation_intent="destructive-config-diff",
        opaque_selection_handle="config-all",
    )
    control.commit_destructive(
        plan_id=config.plan_id,
        digest=config.digest,
        generation=config.generation,
        nonce=config.nonce,
        user_presence_token="00000000-0000-4000-8000-000000000011",
    )
    deleted = control.prepare_destructive(
        operation_intent="delete",
        opaque_selection_handle=created.principal_ref,
    )
    control.commit_destructive(
        plan_id=deleted.plan_id,
        digest=deleted.digest,
        generation=deleted.generation,
        nonce=deleted.nonce,
        user_presence_token="00000000-0000-4000-8000-000000000012",
    )
    assert control.renderer_accounts() == []


def test_expired_plan_bad_presence_and_generation_overflow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    control = NativeControlPlane((tmp_path / "private").absolute())
    control.commit_credential(
        purpose="create-credential-reference",
        credential_reference=reference(1),
        principal_ref=None,
        expected_generation=None,
    )
    with pytest.raises(ValueError, match="invalid user presence"):
        plan = control.prepare_destructive(
            operation_intent="purge",
            opaque_selection_handle="selection-all-local-data",
        )
        control.commit_destructive(
            plan_id=plan.plan_id,
            digest=plan.digest,
            generation=plan.generation,
            nonce=plan.nonce,
            user_presence_token="bad",
        )
    with pytest.raises(ValueError, match="invalid user presence"):
        plan = control.prepare_destructive(
            operation_intent="purge",
            opaque_selection_handle="selection-all-local-data",
        )
        control.commit_destructive(
            plan_id=plan.plan_id,
            digest=plan.digest,
            generation=plan.generation,
            nonce=plan.nonce,
            user_presence_token="000000000-000-4000-8000-000000000001",
        )
    plan = control.prepare_destructive(
        operation_intent="purge",
        opaque_selection_handle="selection-all-local-data",
    )
    monkeypatch.setattr(
        "agent_quota.native_control.time.monotonic_ns",
        lambda: plan.expires_at_ns,
    )
    with pytest.raises(ValueError, match="expired"):
        control.commit_destructive(
            plan_id=plan.plan_id,
            digest=plan.digest,
            generation=plan.generation,
            nonce=plan.nonce,
            user_presence_token="00000000-0000-4000-8000-000000000020",
        )
    control._state["generation"] = 2**63 - 1
    with pytest.raises(OverflowError, match="overflow"):
        control.commit_credential(
            purpose="create-credential-reference",
            credential_reference=reference(2),
            principal_ref=None,
            expected_generation=None,
        )
