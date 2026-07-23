#!/usr/bin/env python3
"""Run isolated contract mutations without changing repository source bytes."""

from __future__ import annotations

import argparse
import ast
import hashlib
import hmac
import json
import os
import re
import select
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

import python_runtime_guard_v1 as runtime_guard


SCRIPT_ABS = os.path.abspath(__file__)
ROOT = Path.cwd()
CONTRACTS = Path("docs/contracts")
ARTIFACT_DOMAIN = b"agent-quota:contract-artifact:v1\x00"
SCHEMA_DOMAIN = b"agent-quota:contract-schema:v1\x00"
REGISTRY_DOMAIN = b"agent-quota:contract-registry:v1\x00"
MUTATION_DOMAIN = b"agent-quota:validation-mutation:v1\x00"
MUTATION_RESULTS_DOMAIN = b"agent-quota:validation-mutation-results:v1\x00"
MUTATION_EXECUTOR_DOMAIN = b"agent-quota:validation-mutation-executor:v1\x00"
MUTATION_EXECUTOR_CLOSURE_DOMAIN = b"agent-quota:validation-mutation-executor-closure:v1\x00"
MUTATION_PATH_SNAPSHOT_DOMAIN = b"agent-quota:validation-mutation-path-snapshot:v1\x00"


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def digest(domain: bytes, value: Any) -> str:
    return hashlib.sha256(domain + canonical(value)).hexdigest()


def load(root: Path, relative: str) -> dict[str, Any]:
    return json.loads((root / relative).read_text(encoding="utf-8"))


def save(root: Path, relative: str, value: dict[str, Any]) -> None:
    (root / relative).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def source_snapshot() -> dict[str, str]:
    output: dict[str, str] = {}
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in {".git", "node_modules", "__pycache__"} for part in path.parts):
            continue
        relative = path.relative_to(ROOT).as_posix()
        output[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return output


def executor_implementation_digests() -> dict[str, str]:
    raw = Path(SCRIPT_ABS).read_text(encoding="utf-8")
    tree = ast.parse(raw)
    lines = raw.splitlines()
    output: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            segment = "\n".join(lines[node.lineno - 1:node.end_lineno]).encode("utf-8")
            output[node.name] = hashlib.sha256(MUTATION_EXECUTOR_DOMAIN + segment).hexdigest()
    return output


def _call_target(node: ast.AST) -> str | None:
    """Return a stable symbolic call target; opaque computed callables reject."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parts = [node.attr]
        current = node.value
        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            parts.append(current.id)
            return ".".join(reversed(parts))
        # Receiver expressions such as mapping[index].append are still an
        # explicit method callsite.  The full AST is pinned in the caller
        # source segment; only the callable selector itself may not be a Call.
        return "method-expression:" + ast.dump(node, annotate_fields=True, include_attributes=False)
    return None


def runner_implementation_closure_document(raw: str) -> dict[str, Any]:
    """Describe every executor's complete local call closure from source.

    The only computed dispatcher allowed is the literal MUTATORS map.  All
    other computed callables fail closed.  Explicit external/builtin/method
    callsites are source-pinned as symbolic targets; local functions are
    followed transitively and every member carries its own source digest.
    """
    tree = ast.parse(raw)
    lines = raw.splitlines()
    function_nodes = {
        node.name: node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    imports: set[str] = set()
    mutator_targets: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            imports.update(alias.asname or alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.update(alias.asname or alias.name for alias in node.names)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "MUTATORS":
            if not isinstance(node.value, ast.Dict):
                raise RuntimeError("MUTATORS must remain a literal dict")
            for value_node in node.value.values:
                if not isinstance(value_node, ast.Name) or value_node.id not in function_nodes:
                    raise RuntimeError("MUTATORS contains an unresolved callable")
                mutator_targets.add(value_node.id)

    builtin_names = set(dir(__builtins__)) if not isinstance(__builtins__, dict) else set(__builtins__)
    source_digests: dict[str, str] = {}
    local_edges: dict[str, set[str]] = {name: set() for name in function_nodes}
    external_targets: dict[str, set[str]] = {name: set() for name in function_nodes}
    for name, node in function_nodes.items():
        segment = "\n".join(lines[node.lineno - 1:node.end_lineno]).encode("utf-8")
        source_digests[name] = hashlib.sha256(MUTATION_EXECUTOR_DOMAIN + segment).hexdigest()
        nested_names = {
            candidate.name for candidate in ast.walk(node)
            if isinstance(candidate, (ast.FunctionDef, ast.AsyncFunctionDef)) and candidate is not node
        }
        for call in (candidate for candidate in ast.walk(node) if isinstance(candidate, ast.Call)):
            if isinstance(call.func, ast.Subscript):
                if isinstance(call.func.value, ast.Name) and call.func.value.id == "MUTATORS":
                    local_edges[name].update(mutator_targets)
                    external_targets[name].add("literal-dispatch:MUTATORS")
                    continue
                raise RuntimeError(f"unresolved dynamic callable in {name}")
            target = _call_target(call.func)
            if target is None:
                raise RuntimeError(f"unresolved dynamic callable in {name}")
            if target in function_nodes:
                local_edges[name].add(target)
            elif target in nested_names:
                external_targets[name].add(f"nested-source-contained:{name}.{target}")
            elif target.startswith("method-expression:") or target.split(".", 1)[0] in imports or target.split(".", 1)[0] in builtin_names or "." in target:
                external_targets[name].add(target)
            else:
                raise RuntimeError(f"unknown call target in {name}: {target}")

    executor_ids = sorted(set(EXECUTOR_BY_CASE.values()), key=lambda value: value.encode("utf-8"))
    mandatory_roots = {"main", "execute_case", "recipe_path_snapshot", "observed_failure_class", "result_sha256"}
    closures = []
    for executor_id in executor_ids:
        roots = mandatory_roots | {executor_id}
        if not roots.issubset(function_nodes):
            raise RuntimeError(f"executor closure has an unknown root: {executor_id}")
        members: set[str] = set()
        pending = list(roots)
        while pending:
            current = pending.pop()
            if current in members:
                continue
            members.add(current)
            pending.extend(local_edges[current] - members)
        member_ids = sorted(members, key=lambda value: value.encode("utf-8"))
        edge_rows = [
            {"caller": caller, "callee": callee}
            for caller in member_ids
            for callee in sorted(local_edges[caller] & members, key=lambda value: value.encode("utf-8"))
        ]
        external_rows = [
            {"caller": caller, "target": target}
            for caller in member_ids
            for target in sorted(external_targets[caller], key=lambda value: value.encode("utf-8"))
        ]
        digest_payload = {
            "executor_id": executor_id,
            "root_function_ids": sorted(roots, key=lambda value: value.encode("utf-8")),
            "member_source_digests": [
                {"function_id": member, "source_sha256": source_digests[member]}
                for member in member_ids
            ],
            "local_call_edges": edge_rows,
            "external_call_targets": external_rows,
        }
        closures.append({
            "executor_id": executor_id,
            "root_function_ids": digest_payload["root_function_ids"],
            "member_function_ids": member_ids,
            "closure_sha256": hashlib.sha256(
                MUTATION_EXECUTOR_CLOSURE_DOMAIN + canonical(digest_payload)
            ).hexdigest(),
        })
    document: dict[str, Any] = {
        "version": 1,
        "source_path": "docs/contracts/run-validation-mutations-v1.py",
        "dynamic_callable_policy": "reject-except-literal-MUTATORS-dispatch",
        "external_call_policy": "exact-symbolic-callsite-source-pinned-and-runtime-tool-identity-pinned",
        "function_source_digests": [
            {"function_id": name, "source_sha256": source_digests[name]}
            for name in sorted(source_digests, key=lambda value: value.encode("utf-8"))
        ],
        "local_call_edges": [
            {"caller": caller, "callee": callee}
            for caller in sorted(local_edges, key=lambda value: value.encode("utf-8"))
            for callee in sorted(local_edges[caller], key=lambda value: value.encode("utf-8"))
        ],
        "external_call_targets": [
            {"caller": caller, "target": target}
            for caller in sorted(external_targets, key=lambda value: value.encode("utf-8"))
            for target in sorted(external_targets[caller], key=lambda value: value.encode("utf-8"))
        ],
        "executor_closures": closures,
    }
    document["closure_sha256"] = hashlib.sha256(
        MUTATION_EXECUTOR_CLOSURE_DOMAIN + canonical(document)
    ).hexdigest()
    return document


def recipe_path_snapshot(root: Path, repo_paths: list[str]) -> str:
    state = hashlib.sha256(MUTATION_PATH_SNAPSHOT_DOMAIN)
    for relative in sorted(repo_paths, key=lambda value: value.encode("utf-8")):
        path = root / relative
        name = relative.encode("utf-8")
        try:
            metadata = os.lstat(path)
        except FileNotFoundError:
            metadata = None
        if metadata is None:
            raw = b""
            kind = b"missing"
            mode = b"0"
        elif stat.S_ISLNK(metadata.st_mode):
            raw = os.readlink(path).encode("utf-8")
            kind = b"symlink"
            mode = str(stat.S_IMODE(metadata.st_mode)).encode("ascii")
        elif stat.S_ISREG(metadata.st_mode):
            raw = path.read_bytes()
            kind = b"regular"
            mode = str(stat.S_IMODE(metadata.st_mode)).encode("ascii")
        elif stat.S_ISDIR(metadata.st_mode):
            raw = b""
            kind = b"directory"
            mode = str(stat.S_IMODE(metadata.st_mode)).encode("ascii")
        else:
            raw = b""
            kind = b"other"
            mode = str(stat.S_IMODE(metadata.st_mode)).encode("ascii")
        for framed in (name, kind, mode, raw):
            state.update(len(framed).to_bytes(8, "big"))
            state.update(framed)
    return state.hexdigest()


def repin(root: Path) -> None:
    def pointer(value: Any, path: str) -> Any:
        current = value
        for token in path[1:].split("/") if path else []:
            current = current[int(token)] if isinstance(current, list) else current[token.replace("~1", "/").replace("~0", "~")]
        return current

    fixture_paths = {
        "docs/contracts/core-safety-contract-v1.json": "docs/contracts/fixtures/core-safety-v1.json",
        "docs/contracts/retention-lint-v1.json": "docs/contracts/fixtures/retention-lint-malicious-v1.json",
    }
    for artifact_path, fixture_path in fixture_paths.items():
        artifact = load(root, artifact_path)
        artifact["fixture_artifacts"][0]["canonical_sha256"] = digest(ARTIFACT_DOMAIN, load(root, fixture_path))
        save(root, artifact_path, artifact)

    projections: list[tuple[str, str]] = []
    for artifact_path in ("docs/contracts/core-safety-contract-v1.json", "docs/contracts/operation-contract-v1.json"):
        artifact = load(root, artifact_path)
        contract = artifact["projection_contract"]
        projected = {path: pointer(artifact, path) for path in contract["source_json_pointers"]}
        inner = "\n```json\n" + canonical(projected).decode("utf-8") + "\n```\n"
        contract["projection_sha256"] = hashlib.sha256(inner.encode("utf-8")).hexdigest()
        save(root, artifact_path, artifact)
        projections.append((contract["markdown_marker"], inner))

    registry_path = "docs/contracts/contract-registry-v1.json"
    registry = load(root, registry_path)
    schema_path = registry["schema_binding"]["schema_path"]
    schema_raw = (root / schema_path).read_bytes()
    registry["schema_binding"]["schema_raw_sha256"] = hashlib.sha256(schema_raw).hexdigest()
    registry["schema_binding"]["schema_canonical_sha256"] = digest(SCHEMA_DOMAIN, json.loads(schema_raw))
    for row in registry["artifacts"]:
        artifact_raw = (root / row["artifact_path"]).read_bytes()
        schema_raw = (root / row["schema_path"]).read_bytes()
        row["artifact_raw_sha256"] = hashlib.sha256(artifact_raw).hexdigest()
        row["artifact_canonical_sha256"] = digest(ARTIFACT_DOMAIN, json.loads(artifact_raw))
        row["schema_raw_sha256"] = hashlib.sha256(schema_raw).hexdigest()
        row["schema_canonical_sha256"] = digest(SCHEMA_DOMAIN, json.loads(schema_raw))
    for row in registry["fixtures"]:
        raw = (root / row["fixture_path"]).read_bytes()
        row["raw_sha256"] = hashlib.sha256(raw).hexdigest()
        row["canonical_sha256"] = digest(ARTIFACT_DOMAIN, json.loads(raw))
    for row in registry["normative_decision_inputs"]:
        raw = (root / row["path"]).read_bytes()
        row["raw_sha256"] = hashlib.sha256(raw).hexdigest()
    save(root, registry_path, registry)

    pins = [{"artifact_id": row["artifact_id"], "canonical_sha256": row["artifact_canonical_sha256"]} for row in registry["artifacts"]]
    payload = {"artifact_pins": pins}
    projection = {"artifact_pins": pins, "projection_sha256": hashlib.sha256(canonical(payload)).hexdigest()}
    anchor = digest(REGISTRY_DOMAIN, registry)
    design_path = root / "docs/design-proposal.md"
    design = design_path.read_text(encoding="utf-8")
    for marker, inner in projections:
        begin_marker = f"<!-- {marker}:BEGIN -->"
        end_marker = f"<!-- {marker}:END -->"
        marker_prefix, marker_remainder = design.split(begin_marker, 1)
        _, marker_suffix = marker_remainder.split(end_marker, 1)
        design = marker_prefix + begin_marker + inner + end_marker + marker_suffix
    begin = "<!-- AQ-GENERATED-ARTIFACT-PINS-V1:BEGIN -->\n```json\n"
    end = "\n```\n<!-- AQ-GENERATED-ARTIFACT-PINS-V1:END -->"
    prefix, remainder = design.split(begin, 1)
    _, suffix = remainder.split(end, 1)
    design = prefix + begin + canonical(projection).decode("utf-8") + end + suffix
    design = re.sub(r"registry canonical 摘要为 `[0-9a-f]{64}`", f"registry canonical 摘要为 `{anchor}`", design, count=1)
    design_path.write_text(design, encoding="utf-8")
    current_status = load(root, "docs/contracts/core-safety-contract-v1.json")["current_design_status"]
    status_inner = "\n```json\n" + canonical(current_status).decode("utf-8") + "\n```\n"
    for relative in ("README.md", "docs/design-proposal.md", "docs/provider-contract.md", "docs/security-model.md"):
        path = root / relative
        source = path.read_text(encoding="utf-8")
        begin_marker = "<!-- AQ-GENERATED-CURRENT-STATUS-V1:BEGIN -->"
        end_marker = "<!-- AQ-GENERATED-CURRENT-STATUS-V1:END -->"
        prefix, remainder = source.split(begin_marker, 1)
        _, suffix = remainder.split(end_marker, 1)
        path.write_text(prefix + begin_marker + status_inner + end_marker + suffix, encoding="utf-8")


def mutate_schema_const(root: Path) -> None:
    path = "docs/contracts/schemas/core-safety-contract-v1.schema.json"
    value = load(root, path)
    value["properties"]["artifact_id"]["const"] = "wrong-artifact-id"
    save(root, path, value)
    repin(root)


def mutate_artifact_unknown(root: Path) -> None:
    path = "docs/contracts/core-safety-contract-v1.json"
    value = load(root, path)
    value["unexpected_field"] = True
    save(root, path, value)
    repin(root)


def mutate_array_duplicate(root: Path) -> None:
    path = "docs/contracts/core-safety-contract-v1.json"
    value = load(root, path)
    value["budget_policies"].append(value["budget_policies"][0])
    save(root, path, value)
    repin(root)


def mutate_array_dangling(root: Path) -> None:
    path = "docs/contracts/schemas/core-safety-contract-v1.schema.json"
    value = load(root, path)
    value["x-aq-array-order"]["overrides"][0]["schema_pointer"] = "/$defs/notAnArray"
    save(root, path, value)
    repin(root)


def mutate_array_reverse(root: Path) -> None:
    path = "docs/contracts/contract-registry-v1.json"
    value = load(root, path)
    value["artifacts"].reverse()
    save(root, path, value)
    repin(root)


def mutate_fixture_ids_only(root: Path) -> None:
    path = "docs/contracts/fixtures/core-safety-v1.json"
    value = load(root, path)
    for case in value["cases"]:
        case["fixture_id"] = "diag-" + case["fixture_id"]
    save(root, path, value)
    repin(root)


def mutate_fixture_input(root: Path) -> None:
    path = "docs/contracts/fixtures/core-safety-v1.json"
    value = load(root, path)
    case = next(item for item in value["cases"] if item["fixture_id"] == "budget-multi-endpoint-profile-no-expansion")
    case["input"]["expected_reservation_rows"] = 2
    save(root, path, value)
    repin(root)


def mutate_repo_alias(root: Path) -> None:
    path = "docs/contracts/contract-registry-v1.json"
    value = load(root, path)
    value["canonicalizer"]["input_paths"][0] = "docs/contracts/./core-safety-contract-v1.json"
    save(root, path, value)


def mutate_repo_symlink(root: Path) -> None:
    target = root / "docs/contracts/lease-policy-v1.json"
    saved = target.with_suffix(".saved")
    target.rename(saved)
    target.symlink_to(saved.name)


def mutate_local_key_missing(root: Path) -> None:
    path = "docs/contracts/local-key-purpose-registry-v1.json"
    value = load(root, path)
    value["purposes"].pop(0)
    save(root, path, value)
    repin(root)


def mutate_lease_overflow(root: Path) -> None:
    path = "docs/contracts/lease-policy-v1.json"
    value = load(root, path)
    value["policies"][0]["duration_ms"] = 2**63
    save(root, path, value)
    repin(root)


def mutate_operation_dangling(root: Path) -> None:
    path = "docs/contracts/operation-contract-v1.json"
    value = load(root, path)
    value["paths"][0]["steps"][0]["predicate_id"] = "dangling-predicate"
    save(root, path, value)
    repin(root)


def mutate_old_persistence(root: Path) -> None:
    path = root / "docs/security-model.md"
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace("persist:v1:subject_metadata_observed:update:RET-SUBJECT-METADATA-OBSERVED", "persist:subject_metadata_observed:update", 1), encoding="utf-8")


def mutate_tool_write_flag(root: Path) -> None:
    path = root / "docs/contracts/canonicalize-registry-v1.py"
    path.write_text(path.read_text(encoding="utf-8") + "\n# forbidden test flag: --write\n", encoding="utf-8")


def append_live_probe(root: Path, relative: str, source: str) -> None:
    path = root / relative
    path.write_text(path.read_text(encoding="utf-8") + "\n\n" + source + "\n", encoding="utf-8")


def mutate_design_new_ttl(root: Path) -> None:
    append_live_probe(root, "docs/design-proposal.md", "R13 probe retention 777 days.")


def mutate_design_untagged_persistence(root: Path) -> None:
    append_live_probe(root, "docs/design-proposal.md", "R13 probe writes credential material into the database.")


def mutate_provider_new_ttl(root: Path) -> None:
    append_live_probe(root, "docs/provider-contract.md", "R13 probe retention 777 days.")


def mutate_provider_untagged_persistence(root: Path) -> None:
    append_live_probe(root, "docs/provider-contract.md", "R13 probe writes credential material into the database.")


def mutate_security_new_ttl(root: Path) -> None:
    append_live_probe(root, "docs/security-model.md", "R13 probe retention 777 days.")


def mutate_security_untagged_persistence(root: Path) -> None:
    append_live_probe(root, "docs/security-model.md", "R13 probe writes credential material into the database.")


def mutate_design_local_file_persistence(root: Path) -> None:
    append_live_probe(root, "docs/design-proposal.md", "The implementation MUST store API tokens in a local file.")


def mutate_provider_local_file_persistence(root: Path) -> None:
    append_live_probe(root, "docs/provider-contract.md", "The implementation MUST store API tokens in a local file.")


def mutate_security_local_file_persistence(root: Path) -> None:
    path = root / "docs/security-model.md"
    text = path.read_text(encoding="utf-8")
    record = "`persist:v1:subject_metadata_observed:update:RET-SUBJECT-METADATA-OBSERVED`"
    replacement = record + " The implementation MUST store API tokens in a local file."
    if text.count(record) < 1:
        raise RuntimeError("R15 same-leaf record anchor is missing")
    path.write_text(text.replace(record, replacement, 1), encoding="utf-8")


def no_mutation(_: Path) -> None:
    return


def mutate_rate_success_count(root: Path) -> None:
    path = "docs/contracts/operation-contract-v1.json"
    value = load(root, path)
    value["rate_reserve_result_contract"]["success_path_counts"]["doctor-official-cli-v1"]["credential_source_call_count"] = 1
    save(root, path, value)
    repin(root)


def mutate_projected_error_row(root: Path) -> None:
    design_path = root / "docs/design-proposal.md"
    original_design = design_path.read_text(encoding="utf-8")
    begin = "<!-- AQ-GENERATED-OPERATION-PROJECTION-V1:BEGIN -->"
    end = "<!-- AQ-GENERATED-OPERATION-PROJECTION-V1:END -->"
    original_inner = original_design.split(begin, 1)[1].split(end, 1)[0]
    path = "docs/contracts/operation-contract-v1.json"
    value = load(root, path)
    value["error_rows"][0]["retryable"] = True
    save(root, path, value)
    repin(root)
    updated_design = design_path.read_text(encoding="utf-8")
    prefix, remainder = updated_design.split(begin, 1)
    _, suffix = remainder.split(end, 1)
    design_path.write_text(prefix + begin + original_inner + end + suffix, encoding="utf-8")


def mutate_lease_boolean_expiry(root: Path) -> None:
    path = "docs/contracts/lease-policy-v1.json"
    value = load(root, path)
    value["policies"][0]["expiry_formula_id"] = "is-expired-v1"
    value["policies"][0]["expiry_formula_expected"] = {"value_type": "boolean", "unit": "boolean", "clock_domain": None}
    save(root, path, value)
    repin(root)


def mutate_lease_clock_domain(root: Path) -> None:
    path = "docs/contracts/lease-policy-v1.json"
    value = load(root, path)
    operand = next(row for row in value["operand_definitions"] if row["operand_id"] == "parent_deadline_monotonic_ns")
    operand["clock_id"] = "db_utc_ms"
    save(root, path, value)
    repin(root)


def mutate_lease_invalid_conversion(root: Path) -> None:
    path = "docs/contracts/lease-policy-v1.json"
    value = load(root, path)
    formula = next(row for row in value["formula_definitions"] if row["formula_id"] == "min-parent-and-transport-plus-2000ms-crash-grace")
    formula["expression"]["args"][0]["deadline"]["formula_ref"] = "db-now-plus-duration-capped-by-max-lifetime"
    save(root, path, value)
    repin(root)


def mutate_package_lock_parity(root: Path) -> None:
    path = "docs/contracts/package-lock.json"
    value = load(root, path)
    value["packages"][""]["dependencies"]["ajv"] = "8.17.0"
    save(root, path, value)


def mutate_runtime_binary_digest(root: Path) -> None:
    path = "docs/contracts/package.json"
    value = load(root, path)
    value["aqValidationRuntime"]["node_binary_sha256"] = "0" * 64
    save(root, path, value)


def decision_path(root: Path) -> Path:
    return root / "docs/audits/gui-product-decision-resolution.md"


def mutate_decision_delete(root: Path) -> None:
    decision_path(root).unlink()


def mutate_decision_bit_flip(root: Path) -> None:
    path = decision_path(root)
    path.write_bytes(path.read_bytes() + b"\nPRE20 decision bit drift.\n")


def mutate_decision_status(root: Path) -> None:
    path = decision_path(root)
    source = path.read_text(encoding="utf-8")
    path.write_text(source.replace("confirmed-current-pending-independent-r20", "draft-unconfirmed", 1), encoding="utf-8")
    repin(root)


def mutate_decision_record_kind(root: Path) -> None:
    path = decision_path(root)
    source = path.read_text(encoding="utf-8")
    path.write_text(source.replace("normative-product-decision-non-history", "round-resolution-history", 1), encoding="utf-8")
    repin(root)


def mutate_decision_history_disguise(root: Path) -> None:
    path = decision_path(root)
    source = path.read_text(encoding="utf-8")
    source = source.replace("# GUI 产品决策处置记录（非审计轮次）", "# PASS_ZERO_ISSUES", 1)
    source = source.replace("forbidden-not-audit-not-resolution", "round-audit-history", 1)
    path.write_text(source, encoding="utf-8")
    repin(root)


def mutate_live_decision_link(root: Path, relative: str, expected: str) -> None:
    path = root / relative
    source = path.read_text(encoding="utf-8")
    replacement = expected.replace("gui-product-decision-resolution.md", "wrong-product-decision.md")
    if expected not in source:
        raise RuntimeError(f"decision link mutation anchor missing: {relative}")
    path.write_text(source.replace(expected, replacement), encoding="utf-8")


def mutate_readme_decision_link(root: Path) -> None:
    mutate_live_decision_link(root, "README.md", "docs/audits/gui-product-decision-resolution.md")


def mutate_design_decision_link(root: Path) -> None:
    mutate_live_decision_link(root, "docs/design-proposal.md", "audits/gui-product-decision-resolution.md")


def mutate_provider_decision_link(root: Path) -> None:
    mutate_live_decision_link(root, "docs/provider-contract.md", "audits/gui-product-decision-resolution.md")


def mutate_security_decision_link(root: Path) -> None:
    mutate_live_decision_link(root, "docs/security-model.md", "audits/gui-product-decision-resolution.md")


MUTATORS: dict[str, Callable[[Path], None]] = {
    "schema-const": mutate_schema_const,
    "artifact-unknown": mutate_artifact_unknown,
    "array-duplicate": mutate_array_duplicate,
    "array-dangling": mutate_array_dangling,
    "array-reverse": mutate_array_reverse,
    "fixture-id-diagnostic-only": mutate_fixture_ids_only,
    "fixture-input": mutate_fixture_input,
    "repo-path-alias": mutate_repo_alias,
    "repo-path-symlink": mutate_repo_symlink,
    "local-key-missing-purpose": mutate_local_key_missing,
    "lease-int64-overflow": mutate_lease_overflow,
    "operation-dangling": mutate_operation_dangling,
    "persistence-old-two-part": mutate_old_persistence,
    "tool-write-flag": mutate_tool_write_flag,
    "live-design-new-ttl": mutate_design_new_ttl,
    "live-design-untagged-persistence": mutate_design_untagged_persistence,
    "live-provider-new-ttl": mutate_provider_new_ttl,
    "live-provider-untagged-persistence": mutate_provider_untagged_persistence,
    "live-security-new-ttl": mutate_security_new_ttl,
    "live-security-untagged-persistence": mutate_security_untagged_persistence,
    "live-design-local-file-persistence": mutate_design_local_file_persistence,
    "live-provider-local-file-persistence": mutate_provider_local_file_persistence,
    "live-security-local-file-persistence": mutate_security_local_file_persistence,
    "retention-synonym-corpus": no_mutation,
    "rate-success-path-count": mutate_rate_success_count,
    "projected-error-row": mutate_projected_error_row,
    "lease-boolean-as-expiry": mutate_lease_boolean_expiry,
    "lease-clock-domain-mix": mutate_lease_clock_domain,
    "lease-invalid-conversion": mutate_lease_invalid_conversion,
    "package-lock-parity": mutate_package_lock_parity,
    "runtime-binary-digest": mutate_runtime_binary_digest,
    "decision-file-delete": mutate_decision_delete,
    "decision-bit-drift": mutate_decision_bit_flip,
    "decision-status-drift": mutate_decision_status,
    "decision-record-kind-drift": mutate_decision_record_kind,
    "decision-history-disguise": mutate_decision_history_disguise,
    "decision-readme-link-drift": mutate_readme_decision_link,
    "decision-design-link-drift": mutate_design_decision_link,
    "decision-provider-link-drift": mutate_provider_decision_link,
    "decision-security-link-drift": mutate_security_decision_link,
}

# This explicit map is intentionally redundant with the dispatcher.  The
# machine contract pins every value and the release gate parses this source
# independently, so redirecting a case to a different valid failing executor
# is itself a gate failure.
EXECUTOR_BY_CASE: dict[str, str] = {
    "schema-const": "mutate_schema_const",
    "artifact-unknown": "mutate_artifact_unknown",
    "array-duplicate": "mutate_array_duplicate",
    "array-dangling": "mutate_array_dangling",
    "array-reverse": "mutate_array_reverse",
    "fixture-id-diagnostic-only": "mutate_fixture_ids_only",
    "fixture-input": "mutate_fixture_input",
    "repo-path-alias": "mutate_repo_alias",
    "repo-path-symlink": "mutate_repo_symlink",
    "local-key-missing-purpose": "mutate_local_key_missing",
    "lease-int64-overflow": "mutate_lease_overflow",
    "operation-dangling": "mutate_operation_dangling",
    "persistence-old-two-part": "mutate_old_persistence",
    "tool-write-flag": "mutate_tool_write_flag",
    "live-design-new-ttl": "mutate_design_new_ttl",
    "live-design-untagged-persistence": "mutate_design_untagged_persistence",
    "live-provider-new-ttl": "mutate_provider_new_ttl",
    "live-provider-untagged-persistence": "mutate_provider_untagged_persistence",
    "live-security-new-ttl": "mutate_security_new_ttl",
    "live-security-untagged-persistence": "mutate_security_untagged_persistence",
    "rate-success-path-count": "mutate_rate_success_count",
    "projected-error-row": "mutate_projected_error_row",
    "lease-boolean-as-expiry": "mutate_lease_boolean_expiry",
    "lease-clock-domain-mix": "mutate_lease_clock_domain",
    "lease-invalid-conversion": "mutate_lease_invalid_conversion",
    "package-lock-parity": "mutate_package_lock_parity",
    "runtime-binary-digest": "mutate_runtime_binary_digest",
    "validation-input-changed": "execute_concurrent_validation",
    "live-design-local-file-persistence": "mutate_design_local_file_persistence",
    "live-provider-local-file-persistence": "mutate_provider_local_file_persistence",
    "live-security-local-file-persistence": "mutate_security_local_file_persistence",
    "retention-synonym-corpus": "no_mutation",
    "release-gate-entry-symlink": "execute_case",
    "release-gate-root-substitution": "execute_case",
    "release-gate-source-symlink": "execute_case",
    "release-gate-concurrent-replacement": "execute_gate_concurrent_replacement",
    "npm-implementation-tree-drift": "execute_case",
    "mutation-result-missing-case": "execute_case",
    "mutation-result-empty-cases": "execute_case",
    "mutation-result-fake-status": "execute_case",
    "mutation-result-duplicate-id": "execute_case",
    "decision-file-delete": "mutate_decision_delete",
    "decision-bit-drift": "mutate_decision_bit_flip",
    "decision-status-drift": "mutate_decision_status",
    "decision-record-kind-drift": "mutate_decision_record_kind",
    "decision-history-disguise": "mutate_decision_history_disguise",
    "decision-readme-link-drift": "mutate_readme_decision_link",
    "decision-design-link-drift": "mutate_design_decision_link",
    "decision-provider-link-drift": "mutate_provider_decision_link",
    "decision-security-link-drift": "mutate_security_decision_link",
}


def mutation_sha256(spec: dict[str, Any]) -> str:
    return hashlib.sha256(MUTATION_DOMAIN + canonical(spec)).hexdigest()


def result_sha256(payload_without_digest: dict[str, Any]) -> str:
    return hashlib.sha256(MUTATION_RESULTS_DOMAIN + canonical(payload_without_digest)).hexdigest()


def synthetic_results(contract: dict[str, Any], root: Path) -> dict[str, Any]:
    rows = []
    for case in contract["cases"]:
        source_digest = recipe_path_snapshot(root, case["mutation_spec"]["repo_paths"])
        mutated_digest = source_digest if case["mutation_spec"]["expected_repo_effect"] == "unchanged" else "0" * 64
        rows.append({
            "sequence": case["sequence"],
            "case_id": case["case_id"],
            "expected_success": case["expected_success"],
            "actual_success": case["expected_success"],
            "mutation_sha256": case["mutation_sha256"],
            "source_input_sha256": source_digest,
            "applied_recipe_sha256": case["mutation_sha256"],
            "executor_id": case["mutation_spec"]["executor_id"],
            "executor_implementation_sha256": case["mutation_spec"]["executor_implementation_sha256"],
            "executor_closure_sha256": case["mutation_spec"]["executor_closure_sha256"],
            "mutated_output_sha256": mutated_digest,
            "observed_failure_class": case["mutation_spec"]["expected_failure_class"],
            "verdict": "pass" if case["expected_success"] else "rejected",
        })
    payload = {
        "contract_id": contract["contract_id"],
        "case_count": contract["case_count"],
        "cases": rows,
        "source_bytes_unchanged": True,
        "status": "ok",
    }
    payload["results_sha256"] = result_sha256(payload)
    return payload


def copy_case_root(dependency: Path) -> tuple[tempfile.TemporaryDirectory[str], Path]:
    temporary = tempfile.TemporaryDirectory(prefix="aq-contract-mutation-")
    target = Path(temporary.name) / "repo"
    shutil.copytree(ROOT, target, ignore=shutil.ignore_patterns(".git", "node_modules", "__pycache__"))
    (target / "docs/contracts/node_modules").symlink_to(dependency, target_is_directory=True)
    return temporary, target


def subprocess_success(command: list[str], target: Path, env: dict[str, str], *, stdin: str | None = None, timeout: int = 120) -> tuple[bool, str, int]:
    completed = subprocess.run(
        command,
        cwd=target,
        text=True,
        input=stdin,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        check=False,
        env=env,
    )
    return completed.returncode == 0, completed.stdout, completed.returncode


def formal_command(entry: str, *arguments: str) -> list[str]:
    return ["/bin/sh", "docs/contracts/runtime-bootstrap-v1.sh", entry, *arguments]


def execute_concurrent_validation(target: Path, env: dict[str, str]) -> tuple[bool, str, int]:
    child_env = dict(env)
    child_env["AQ_VALIDATION_MUTATION_TEST"] = "1"
    child_env["AQ_VALIDATION_TEST_PAUSE_BEFORE_FINAL_VERIFY_MS"] = "3000"
    ready_read, ready_write = os.pipe()
    child_env["AQ_VALIDATION_TEST_READY_FD"] = str(ready_write)
    try:
        process = subprocess.Popen(
            formal_command("docs/contracts/validate-contracts-v1.py"),
            cwd=target,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=child_env,
            pass_fds=(ready_write,),
        )
        os.close(ready_write)
        ready_write = -1
        readable, _, _ = select.select([ready_read], [], [], 90)
        if not readable or os.read(ready_read, 5) != b"ready":
            process.kill()
            output, _ = process.communicate(timeout=10)
            raise RuntimeError(f"validation input-change barrier was not reached: {output.rstrip()}")
        readme = target / "README.md"
        readme.write_text(readme.read_text(encoding="utf-8") + "\nConcurrent source-change probe.\n", encoding="utf-8")
        output, _ = process.communicate(timeout=90)
    finally:
        os.close(ready_read)
        if ready_write >= 0:
            os.close(ready_write)
    rejected_as_expected = process.returncode != 0 and "changed before success: README.md" in output
    return (False if rejected_as_expected else True), output, process.returncode or 0


def execute_gate_concurrent_replacement(target: Path, env: dict[str, str]) -> tuple[bool, str, int]:
    child_env = dict(env)
    child_env["AQ_RELEASE_GATE_MUTATION_TEST"] = "1"
    child_env["AQ_RELEASE_GATE_TEST_PAUSE_BEFORE_FINAL_VERIFY_MS"] = "3000"
    ready_read, ready_write = os.pipe()
    child_env["AQ_RELEASE_GATE_TEST_READY_FD"] = str(ready_write)
    try:
        process = subprocess.Popen(
            formal_command("docs/contracts/run-release-gate-v1.py", "--root", ".", "--self-test-preflight"),
            cwd=target,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=child_env,
            pass_fds=(ready_write,),
        )
        os.close(ready_write)
        ready_write = -1
        readable, _, _ = select.select([ready_read], [], [], 90)
        if not readable or os.read(ready_read, 5) != b"ready":
            process.kill()
            output, _ = process.communicate(timeout=10)
            raise RuntimeError(f"release-gate input-change barrier was not reached: {output.rstrip()}")
        readme = target / "README.md"
        readme.write_text(readme.read_text(encoding="utf-8") + "\nConcurrent gate source-change probe.\n", encoding="utf-8")
        output, _ = process.communicate(timeout=90)
    finally:
        os.close(ready_read)
        if ready_write >= 0:
            os.close(ready_write)
    rejected_as_expected = process.returncode != 0 and "changed before success: README.md" in output
    return (False if rejected_as_expected else True), output, process.returncode or 0


def execute_case(
    case: dict[str, Any],
    contract: dict[str, Any],
    dependency: Path,
    base_env: dict[str, str],
    evidence_root: Path | None = None,
) -> tuple[bool, str, int, str, str]:
    kind = case["mutation_spec"]["kind"]
    temporary, target = copy_case_root(dependency)
    try:
        env = dict(base_env)
        source_input_sha256 = recipe_path_snapshot(target, case["mutation_spec"]["repo_paths"])

        def finish(result: tuple[bool, str, int]) -> tuple[bool, str, int, str, str]:
            return (*result, source_input_sha256, recipe_path_snapshot(target, case["mutation_spec"]["repo_paths"]))

        if kind in MUTATORS:
            MUTATORS[kind](target)
            if kind == "npm-implementation-tree-drift":
                raise AssertionError("npm tree drift must use its dedicated executor")
            success, output, returncode = subprocess_success(formal_command("docs/contracts/validate-contracts-v1.py"), target, env)
            success = success and output.rstrip().endswith("status=ok")
            return finish((success, output, returncode))
        if kind == "validation-input-changed":
            return finish(execute_concurrent_validation(target, env))
        if kind == "npm-implementation-tree-drift":
            actual_launcher = os.path.realpath(shutil.which("npm") or "")
            actual_root = Path(actual_launcher).parent.parent
            fake_root = target / "qa/npm-package"
            shutil.copytree(actual_root, fake_root)
            changed = fake_root / "lib/cli.js"
            changed.write_text(changed.read_text(encoding="utf-8") + "\n// mutation identity: npm implementation tree drift\n", encoding="utf-8")
            fake_bin = target / "qa/bin"
            fake_bin.mkdir(parents=True)
            (fake_bin / "npm").symlink_to(fake_root / "bin/npm-cli.js")
            env["PATH"] = str(fake_bin) + os.pathsep + env["PATH"]
            env["AQ_VALIDATION_MUTATION_TEST"] = "1"
            env["AQ_VALIDATION_NPM_PACKAGE_ROOT"] = str(fake_root.resolve())
            return finish(subprocess_success(formal_command("docs/contracts/validate-contracts-v1.py"), target, env))
        gate_command = formal_command("docs/contracts/run-release-gate-v1.py", "--root", ".", "--self-test-preflight")
        env["AQ_RELEASE_GATE_MUTATION_TEST"] = "1"
        if kind == "release-gate-entry-symlink":
            gate = target / "docs/contracts/run-release-gate-v1.py"
            saved = gate.with_suffix(".saved")
            gate.rename(saved)
            gate.symlink_to(saved.name)
            return finish(subprocess_success(gate_command, target, env))
        if kind == "release-gate-root-substitution":
            command = formal_command("docs/contracts/run-release-gate-v1.py", "--root", str(target), "--self-test-preflight")
            return finish(subprocess_success(command, ROOT, env))
        if kind == "release-gate-source-symlink":
            source = target / "docs/contracts/validate-contracts-v1.py"
            saved = source.with_suffix(".saved")
            source.rename(saved)
            source.symlink_to(saved.name)
            return finish(subprocess_success(gate_command, target, env))
        if kind == "release-gate-concurrent-replacement":
            return finish(execute_gate_concurrent_replacement(target, env))
        if kind.startswith("mutation-result-"):
            payload: Any = synthetic_results(contract, target)
            if kind == "mutation-result-missing-case":
                payload["cases"].pop()
                payload["results_sha256"] = result_sha256({key: value for key, value in payload.items() if key != "results_sha256"})
            elif kind == "mutation-result-empty-cases":
                payload["cases"] = []
                payload["results_sha256"] = result_sha256({key: value for key, value in payload.items() if key != "results_sha256"})
            elif kind == "mutation-result-fake-status":
                payload = {"status": "ok"}
            elif kind == "mutation-result-duplicate-id":
                payload["cases"][1] = dict(payload["cases"][0])
                payload["results_sha256"] = result_sha256({key: value for key, value in payload.items() if key != "results_sha256"})
            command = formal_command("docs/contracts/run-release-gate-v1.py", "--root", ".", "--self-test-verify-mutation-results")
            return finish(subprocess_success(command, target, env, stdin=canonical(payload).decode("utf-8")))
        raise RuntimeError(f"mutation contract kind has no executor: {kind}")
    finally:
        if evidence_root is not None and target.exists():
            destination = evidence_root / case["case_id"]
            if destination.exists():
                raise RuntimeError(f"duplicate evidence destination: {case['case_id']}")
            shutil.copytree(target, destination, symlinks=True)
        temporary.cleanup()


def observed_failure_class(actual_success: bool, output: str) -> str:
    if actual_success:
        return "none"
    if "release_gate_error=" in output:
        return "release-gate-rejection"
    if "validation_error=" in output:
        return "validator-rejection"
    if "runtime_bootstrap_error=" in output:
        return "release-gate-rejection"
    return "process-rejection"


def main() -> int:
    global ROOT
    parser = argparse.ArgumentParser(description="Run the fixed Agent Quota validation mutation contract.")
    parser.add_argument("--root", required=True)
    parser.add_argument("--self-test-redirect-executor")
    parser.add_argument("--evidence-root")
    args = parser.parse_args()
    try:
        runtime_guard.verify_runtime(require_external_bootstrap=True)
    except RuntimeError as error:
        print(f"mutation_runner_error={error}", file=sys.stderr)
        return 1
    root_abs = os.path.abspath(args.root)
    if os.getcwd() != root_abs or SCRIPT_ABS != os.path.join(root_abs, "docs/contracts/run-validation-mutations-v1.py"):
        print("mutation_runner_error=cwd/root/entry mismatch", file=sys.stderr)
        return 1
    if not stat.S_ISREG(os.lstat(SCRIPT_ABS).st_mode):
        print("mutation_runner_error=runner entry must be a regular file", file=sys.stderr)
        return 1
    ROOT = Path(root_abs)
    evidence_root: Path | None = None
    if args.evidence_root is not None:
        if os.environ.get("AQ_RELEASE_GATE_EVIDENCE") != "1":
            print("mutation_runner_error=evidence export is release-gate-only", file=sys.stderr)
            return 1
        evidence_abs = os.path.abspath(args.evidence_root)
        evidence_root = Path(evidence_abs)
        if not evidence_root.is_dir() or any(evidence_root.iterdir()):
            print("mutation_runner_error=evidence root must be an existing empty directory", file=sys.stderr)
            return 1
    before = source_snapshot()
    dependency = ROOT / "docs/contracts/node_modules"
    if not dependency.is_dir():
        print("mutation_runner_error=run npm ci in docs/contracts before the mutation suite", file=sys.stderr)
        return 1
    contract = load(ROOT, "docs/contracts/core-safety-contract-v1.json")["validation_mutation_contract"]
    raw_runner = Path(SCRIPT_ABS).read_text(encoding="utf-8")
    actual_closure_document = runner_implementation_closure_document(raw_runner)
    if actual_closure_document != contract["runner_implementation_closure"]:
        print("mutation_runner_error=runner implementation closure mismatch", file=sys.stderr)
        return 1
    closure_by_executor = {
        row["executor_id"]: row["closure_sha256"]
        for row in actual_closure_document["executor_closures"]
    }
    cases = contract["cases"]
    if contract["case_count"] != len(cases) or [row["sequence"] for row in cases] != list(range(1, len(cases) + 1)):
        print("mutation_runner_error=machine contract count/order mismatch", file=sys.stderr)
        return 1
    if len({row["case_id"] for row in cases}) != len(cases):
        print("mutation_runner_error=duplicate machine contract case ID", file=sys.stderr)
        return 1
    active_executor_map = dict(EXECUTOR_BY_CASE)
    if args.self_test_redirect_executor is not None:
        if os.environ.get("AQ_MUTATION_RECIPE_SELF_TEST") != "1" or args.self_test_redirect_executor != "schema-const=artifact-unknown":
            print("mutation_runner_error=executor redirect self-test is not authorized", file=sys.stderr)
            return 1
        active_executor_map["schema-const"] = active_executor_map["artifact-unknown"]
    executor_digests = executor_implementation_digests()
    for row in cases:
        spec = row["mutation_spec"]
        if row["case_id"] != spec["kind"] or not hmac.compare_digest(row["mutation_sha256"], mutation_sha256(spec)):
            print(f"mutation_runner_error=machine contract identity mismatch:{row['case_id']}", file=sys.stderr)
            return 1
        if active_executor_map.get(row["case_id"]) != spec["executor_id"]:
            print(f"mutation_runner_error=executor mapping mismatch:{row['case_id']}", file=sys.stderr)
            return 1
        actual_executor_digest = executor_digests.get(spec["executor_id"])
        if actual_executor_digest is None or not hmac.compare_digest(actual_executor_digest, spec["executor_implementation_sha256"]):
            print(f"mutation_runner_error=executor implementation mismatch:{row['case_id']}", file=sys.stderr)
            return 1
        if closure_by_executor.get(spec["executor_id"]) != spec["executor_closure_sha256"]:
            print(f"mutation_runner_error=executor closure mismatch:{row['case_id']}", file=sys.stderr)
            return 1

    if args.self_test_redirect_executor is not None:
        print("mutation_runner_error=executor redirect self-test unexpectedly accepted", file=sys.stderr)
        return 1

    base_env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
        "PYTHONHASHSEED": "0",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    result_rows = []
    for case in cases:
        try:
            actual_success, output, returncode, source_input_sha256, mutated_output_sha256 = execute_case(
                case, contract, dependency, base_env, evidence_root
            )
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
            print(f"mutation_runner_error={case['case_id']}:{error}", file=sys.stderr)
            return 1
        if actual_success != case["expected_success"]:
            print(f"mutation_runner_error={case['case_id']}:expected_success={case['expected_success']}:actual_success={actual_success}:returncode={returncode}", file=sys.stderr)
            print(output.rstrip(), file=sys.stderr)
            return 1
        failure_class = observed_failure_class(actual_success, output)
        spec = case["mutation_spec"]
        if failure_class != spec["expected_failure_class"]:
            print(f"mutation_runner_error={case['case_id']}:failure_class={failure_class}:expected={spec['expected_failure_class']}", file=sys.stderr)
            print(output.rstrip(), file=sys.stderr)
            return 1
        if (source_input_sha256 == mutated_output_sha256) != (spec["expected_repo_effect"] == "unchanged"):
            print(f"mutation_runner_error={case['case_id']}:repo effect mismatch", file=sys.stderr)
            return 1
        result_rows.append({
            "sequence": case["sequence"],
            "case_id": case["case_id"],
            "expected_success": case["expected_success"],
            "actual_success": actual_success,
            "mutation_sha256": case["mutation_sha256"],
            "source_input_sha256": source_input_sha256,
            "applied_recipe_sha256": case["mutation_sha256"],
            "executor_id": spec["executor_id"],
            "executor_implementation_sha256": spec["executor_implementation_sha256"],
            "executor_closure_sha256": spec["executor_closure_sha256"],
            "mutated_output_sha256": mutated_output_sha256,
            "observed_failure_class": failure_class,
            "verdict": "pass" if actual_success else "rejected",
        })
    if source_snapshot() != before:
        print("mutation_runner_error=source bytes changed", file=sys.stderr)
        return 1
    payload = {
        "contract_id": contract["contract_id"],
        "case_count": contract["case_count"],
        "cases": result_rows,
        "source_bytes_unchanged": True,
        "status": "ok",
    }
    payload["results_sha256"] = result_sha256(payload)
    print(canonical(payload).decode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
