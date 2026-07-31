"""Generic fail-closed validator for the generated 29 renderer DTOs."""

from __future__ import annotations

import json
from importlib.resources import files
from typing import Any

from agent_quota.errors import ContractViolation


class RendererContract:
    def __init__(self) -> None:
        resource = files("agent_quota.resources").joinpath("renderer_contract_v1.json")
        self.document = json.loads(resource.read_text(encoding="utf-8"))
        self.schemas = {row["schema_ref"]: row for row in self.document["dto_schemas"]}
        self.commands = {row["command_id"]: row for row in self.document["commands"]}
        if (
            len(self.schemas) != 29
            or len(self.commands) != 10
            or list(self.commands) != self.document["command_ids"]
        ):
            raise ContractViolation("renderer contract closure mismatch")

    def validate_command_request(self, command_id: str, payload: object) -> dict[str, Any]:
        command = self.commands.get(command_id)
        if command is None:
            raise ContractViolation("unknown renderer command")
        return self.validate(command["request_schema_ref"], payload)

    def validate_command_response(self, command_id: str, payload: object) -> dict[str, Any]:
        command = self.commands.get(command_id)
        if command is None:
            raise ContractViolation("unknown renderer command")
        return self.validate(command["response_schema_ref"], payload)

    def validate(self, schema_ref: str, payload: object) -> dict[str, Any]:
        schema = self.schemas.get(schema_ref)
        if schema is None or not isinstance(payload, dict):
            raise ContractViolation(f"invalid DTO: {schema_ref}")
        fields = {row["name"]: row for row in schema["fields"]}
        required = {name for name, field in fields.items() if field["required"]}
        actual = set(payload)
        if actual - set(fields) or required - actual:
            raise ContractViolation(f"DTO field closure mismatch: {schema_ref}")
        output: dict[str, Any] = {}
        for name, value in payload.items():
            output[name] = self._validate_field(fields[name], value, name)
        return output

    def _validate_field(self, field: dict[str, Any], value: object, path: str) -> object:
        kind = field["type"]
        if kind == "string":
            if not isinstance(value, str):
                raise ContractViolation(f"{path}: expected string")
            if len(value.encode("utf-8")) > field["max_utf8_bytes"]:
                raise ContractViolation(f"{path}: string too large")
            allowed = field["allowed_values"]
            if allowed and value not in allowed:
                raise ContractViolation(f"{path}: enum mismatch")
            return value
        if kind == "integer":
            if isinstance(value, bool) or not isinstance(value, int):
                raise ContractViolation(f"{path}: expected integer")
            if not field["minimum"] <= value <= field["maximum"]:
                raise ContractViolation(f"{path}: integer out of bounds")
            return value
        if kind == "boolean":
            if not isinstance(value, bool):
                raise ContractViolation(f"{path}: expected boolean")
            return value
        if kind == "object":
            return self.validate(field["ref"], value)
        if kind == "array":
            if not isinstance(value, list) or len(value) > field["max_items"]:
                raise ContractViolation(f"{path}: invalid array")
            return [self.validate(field["ref"], item) for item in value]
        raise ContractViolation(f"{path}: unknown field type")
