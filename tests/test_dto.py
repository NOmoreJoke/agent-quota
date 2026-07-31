from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from agent_quota.dto import RendererContract
from agent_quota.errors import ContractViolation


def sample(contract: RendererContract, schema_ref: str) -> dict[str, Any]:
    schema = contract.schemas[schema_ref]
    payload: dict[str, Any] = {}
    for field in schema["fields"]:
        if not field["required"]:
            continue
        kind = field["type"]
        if kind == "string":
            payload[field["name"]] = field["allowed_values"][0] if field["allowed_values"] else "x"
        elif kind == "integer":
            payload[field["name"]] = field["minimum"]
        elif kind == "boolean":
            payload[field["name"]] = False
        elif kind == "object":
            payload[field["name"]] = sample(contract, field["ref"])
        elif kind == "array":
            payload[field["name"]] = []
        else:
            raise AssertionError(kind)
    return payload


def test_generated_resource_matches_machine_contract() -> None:
    root = Path(__file__).resolve().parents[1]
    source = json.loads((root / "docs/contracts/core-safety-contract-v1.json").read_text())
    expected = source["desktop_product_contract"]["renderer_command_contract"]
    assert RendererContract().document == expected


def test_all_29_dtos_accept_minimum_closed_value() -> None:
    contract = RendererContract()
    assert len(contract.schemas) == 29
    for schema_ref in contract.schemas:
        value = sample(contract, schema_ref)
        assert contract.validate(schema_ref, value) == value


def test_all_10_commands_resolve_request_and_response() -> None:
    contract = RendererContract()
    assert len(contract.commands) == 10
    for command_id, command in contract.commands.items():
        contract.validate_command_request(
            command_id,
            sample(contract, command["request_schema_ref"]),
        )
        contract.validate_command_response(
            command_id,
            sample(contract, command["response_schema_ref"]),
        )


@pytest.mark.parametrize("schema_ref", [f"aq-renderer-dto://v1/{value}" for value in ["nope", ""]])
def test_unknown_schema_rejected(schema_ref: str) -> None:
    with pytest.raises(ContractViolation):
        RendererContract().validate(schema_ref, {})


def test_unknown_command_and_extra_field_rejected() -> None:
    contract = RendererContract()
    with pytest.raises(ContractViolation):
        contract.validate_command_request("unknown", {})
    with pytest.raises(ContractViolation):
        contract.validate_command_request("bootstrap_state", {"extra": True})


def test_nested_extra_field_rejected() -> None:
    contract = RendererContract()
    payload = sample(contract, "aq-renderer-dto://v1/bootstrap-state-response")
    payload["application_state"]["extra"] = True
    with pytest.raises(ContractViolation):
        contract.validate("aq-renderer-dto://v1/bootstrap-state-response", payload)


def test_longest_classification_enum_is_constructible() -> None:
    contract = RendererContract()
    payload = {
        "classification": "destructive-trusted-surface-required",
        "status": "ok",
    }
    assert (
        contract.validate(
            "aq-renderer-dto://v1/config-validate-apply-response",
            payload,
        )
        == payload
    )


@given(st.text(min_size=129, max_size=256))
def test_opaque_scope_ref_utf8_bound(value: str) -> None:
    contract = RendererContract()
    if len(value.encode()) <= 128:
        return
    with pytest.raises(ContractViolation):
        contract.validate(
            "aq-renderer-dto://v1/accounts-read-request",
            {"scope_ref": value},
        )


@given(st.text(min_size=1, max_size=20).filter(lambda value: value != "scope_ref"))
def test_property_unknown_fields_fail_closed(key: str) -> None:
    with pytest.raises(ContractViolation):
        RendererContract().validate(
            "aq-renderer-dto://v1/accounts-read-request",
            {"scope_ref": "x", key: "unexpected"},
        )
