#!/usr/bin/env python3
"""Fixed-root release-evidence gate for the documentation contracts.

The checkout and this output are audit evidence only. Production or Gate 0A
authority still requires the external signed/VCS identity named by the registry.
"""

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
import types
from pathlib import Path
from typing import Any

import python_runtime_guard_v1 as runtime_guard


GATE_REL = "docs/contracts/run-release-gate-v1.py"
VALIDATOR_REL = "docs/contracts/validate-contracts-v1.py"
SCRIPT_ABS = os.path.abspath(__file__)
MUTATION_RESULTS_DOMAIN = b"agent-quota:validation-mutation-results:v1\x00"
MUTATION_EXECUTOR_DOMAIN = b"agent-quota:validation-mutation-executor:v1\x00"
MUTATION_LOCATOR_STATE_DOMAIN = b"agent-quota:validation-mutation-locator-state:v1\x00"
MUTATION_PATH_SNAPSHOT_DOMAIN = b"agent-quota:validation-mutation-path-snapshot:v1\x00"
ROOT_IDENTITY_DOMAIN = b"agent-quota:release-gate-root:v1\x00"
INPUT_DOMAIN = b"agent-quota:release-gate-inputs:v1\x00"


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def open_root_nofollow(root_abs: str) -> int:
    require(os.path.isabs(root_abs) and os.path.normpath(root_abs) == root_abs, "--root must be canonical absolute after lexical normalization")
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    current_fd = os.open(os.path.sep, flags)
    try:
        for segment in root_abs.split(os.path.sep)[1:]:
            require(segment not in ("", ".", ".."), "--root contains an invalid component")
            next_fd = os.open(segment, flags, dir_fd=current_fd)
            os.close(current_fd)
            current_fd = next_fd
            require(stat.S_ISDIR(os.fstat(current_fd).st_mode), "--root component is not a directory")
        return current_fd
    except Exception:
        os.close(current_fd)
        raise


def read_relative_nofollow(root_fd: int, relative: str, maximum: int = 524288) -> tuple[bytes, os.stat_result]:
    segments = relative.split("/")
    require(all(segment not in ("", ".", "..") for segment in segments), "bootstrap path is not canonical")
    current_fd = os.dup(root_fd)
    try:
        for index, segment in enumerate(segments):
            final = index == len(segments) - 1
            flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
            if not final:
                flags |= getattr(os, "O_DIRECTORY", 0)
            next_fd = os.open(segment, flags, dir_fd=current_fd)
            os.close(current_fd)
            current_fd = next_fd
            require(stat.S_ISREG(os.fstat(current_fd).st_mode) if final else stat.S_ISDIR(os.fstat(current_fd).st_mode), "bootstrap input has an unexpected file type")
        before = os.fstat(current_fd)
        raw = bytearray()
        while True:
            chunk = os.read(current_fd, min(65536, maximum + 1 - len(raw)))
            if not chunk:
                break
            raw.extend(chunk)
            require(len(raw) <= maximum, "bootstrap input exceeds raw bound")
        after = os.fstat(current_fd)
        require((before.st_dev, before.st_ino, before.st_mode, before.st_size, before.st_mtime_ns, before.st_ctime_ns) == (after.st_dev, after.st_ino, after.st_mode, after.st_size, after.st_mtime_ns, after.st_ctime_ns), "bootstrap input changed while read")
        require(after.st_size == len(raw), "bootstrap input length changed while read")
        return bytes(raw), after
    finally:
        os.close(current_fd)


def bootstrap(root_arg: str) -> tuple[Any, Any, str]:
    root_abs = os.path.abspath(root_arg)
    require(os.getcwd() == root_abs, "calling cwd must exactly equal --root")
    expected_script = os.path.join(root_abs, GATE_REL)
    require(SCRIPT_ABS == expected_script, "release gate entry path is outside or aliased from the fixed root")
    script_stat = os.lstat(SCRIPT_ABS)
    require(stat.S_ISREG(script_stat.st_mode), "release gate entry must be a regular non-symlink file")
    root_fd = open_root_nofollow(root_abs)
    try:
        gate_raw, gate_stat = read_relative_nofollow(root_fd, GATE_REL)
        require((script_stat.st_dev, script_stat.st_ino, script_stat.st_mode, script_stat.st_size, script_stat.st_mtime_ns, script_stat.st_ctime_ns) == (gate_stat.st_dev, gate_stat.st_ino, gate_stat.st_mode, gate_stat.st_size, gate_stat.st_mtime_ns, gate_stat.st_ctime_ns), "executed release gate differs from fixed-root entry")
        validator_raw, _ = read_relative_nofollow(root_fd, VALIDATOR_REL)
        module_name = "agent_quota_release_gate_validator_v1"
        module = types.ModuleType(module_name)
        module.__file__ = os.path.join(root_abs, VALIDATOR_REL)
        sys.modules[module_name] = module
        exec(compile(validator_raw, module.__file__, "exec"), module.__dict__)
        reader = module.RepositoryReader(root_abs=root_abs, required_entry_rel=GATE_REL)
        root_stat = os.fstat(root_fd)
        require(reader.root_identity == (root_stat.st_dev, root_stat.st_ino, root_stat.st_mode), "bootstrap and validator fixed-root identities differ")
        return module, reader, root_abs
    finally:
        os.close(root_fd)


def complete_snapshot(validator: Any, reader: Any, maximum: int) -> dict[str, bytes]:
    manifest_raw = reader.read_bytes(validator.HISTORY_MANIFEST_REL, maximum)
    manifest = json.loads(manifest_raw)
    history_paths = validator.history_paths_from_manifest_document(manifest)
    paths = set(validator.BASE_ALLOWED_READ_PATHS) | set(history_paths)
    require(not (paths & (set(validator.HISTORY_PATH_UNIVERSE) - set(history_paths))), "snapshot history input set is wider than manifest-derived closure")
    output: dict[str, bytes] = {}
    for relative in sorted(paths, key=lambda value: value.encode("utf-8")):
        output[relative] = reader.read_bytes(relative, maximum)
    return output


def framed_digest(domain: bytes, values: dict[str, bytes]) -> str:
    state = hashlib.sha256(domain)
    for relative in sorted(values, key=lambda value: value.encode("utf-8")):
        name = relative.encode("utf-8")
        raw = values[relative]
        state.update(len(name).to_bytes(4, "big"))
        state.update(name)
        state.update(len(raw).to_bytes(8, "big"))
        state.update(raw)
    return state.hexdigest()


def copy_snapshot(snapshot: dict[str, bytes], target: Path) -> None:
    for relative, raw in snapshot.items():
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)


def run(command: list[str], cwd: Path, *, timeout: int, env: dict[str, str], stdin: str | None = None) -> str:
    completed = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        input=stdin,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        check=False,
        env=env,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"release gate command failed ({' '.join(command)}):\n{completed.stdout.rstrip()}")
    return completed.stdout.rstrip()


def run_expect_failure(command: list[str], cwd: Path, *, timeout: int, env: dict[str, str], expected: str) -> None:
    completed = subprocess.run(command, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout, check=False, env=env)
    require(completed.returncode != 0 and expected in completed.stdout, f"negative self-test did not fail closed ({' '.join(command)}):\n{completed.stdout.rstrip()}")


def formal_command(entry: str, *arguments: str) -> list[str]:
    return ["/bin/sh", "docs/contracts/runtime-bootstrap-v1.sh", entry, *arguments]


def recipe_path_snapshot(root: Path, repo_paths: list[str]) -> str:
    state = hashlib.sha256(MUTATION_PATH_SNAPSHOT_DOMAIN)
    for relative in sorted(repo_paths, key=lambda value: value.encode("utf-8")):
        path_state = _nofollow_path_state(root, relative)
        name = relative.encode("utf-8")
        if path_state["kind"] == "symlink":
            raw = path_state["target"].encode("utf-8")
            kind = b"symlink"
        elif path_state["kind"] == "regular":
            raw = _read_regular_nofollow(root, relative)
            kind = b"regular"
        elif path_state["kind"] == "directory":
            raw = b""
            kind = b"directory"
        elif path_state["kind"] == "missing":
            raw = b""
            kind = b"missing"
        else:
            raw = b""
            kind = b"other"
        for framed in (name, kind, str(path_state["mode"]).encode("ascii"), raw):
            state.update(len(framed).to_bytes(8, "big"))
            state.update(framed)
    return state.hexdigest()


def _canonical_repo_path(relative: str) -> None:
    require(
        re.fullmatch(r"(?:README\.md|docs(?:/[a-z0-9][a-z0-9_.-]*)+)", relative) is not None,
        f"mutation locator path is not a canonical RepoPath: {relative}",
    )


def _nofollow_path_state(root: Path, relative: str) -> dict[str, Any]:
    """Read one locator path through an exact no-follow directory walk."""
    _canonical_repo_path(relative)
    root_fd = os.open(root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
    current_fd = root_fd
    try:
        segments = relative.split("/")
        for segment in segments[:-1]:
            next_fd = os.open(
                segment,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=current_fd,
            )
            if current_fd != root_fd:
                os.close(current_fd)
            current_fd = next_fd
            require(stat.S_ISDIR(os.fstat(current_fd).st_mode), f"mutation locator intermediate is not a directory: {relative}")
        name = segments[-1]
        try:
            metadata = os.stat(name, dir_fd=current_fd, follow_symlinks=False)
        except FileNotFoundError:
            return {"kind": "missing", "mode": 0}
        mode = stat.S_IMODE(metadata.st_mode)
        if stat.S_ISLNK(metadata.st_mode):
            return {"kind": "symlink", "mode": mode, "target": os.readlink(name, dir_fd=current_fd)}
        if stat.S_ISDIR(metadata.st_mode):
            return {"kind": "directory", "mode": mode}
        require(stat.S_ISREG(metadata.st_mode), f"mutation locator has unsupported filesystem kind: {relative}")
        file_fd = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=current_fd)
        try:
            before = os.fstat(file_fd)
            raw = bytearray()
            while True:
                chunk = os.read(file_fd, 65536)
                if not chunk:
                    break
                raw.extend(chunk)
                require(len(raw) <= 2_000_000, f"mutation locator file exceeds bound: {relative}")
            after = os.fstat(file_fd)
            require(
                (before.st_dev, before.st_ino, before.st_mode, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
                == (after.st_dev, after.st_ino, after.st_mode, after.st_size, after.st_mtime_ns, after.st_ctime_ns),
                f"mutation locator changed while read: {relative}",
            )
            return {
                "kind": "regular",
                "mode": mode,
                "size": len(raw),
                "raw_sha256": hashlib.sha256(raw).hexdigest(),
            }
        finally:
            os.close(file_fd)
    finally:
        if current_fd != root_fd:
            os.close(current_fd)
        os.close(root_fd)


def _read_regular_nofollow(root: Path, relative: str) -> bytes:
    state = _nofollow_path_state(root, relative)
    require(state["kind"] == "regular", f"mutation locator requires a regular file: {relative}")
    root_fd = os.open(root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0))
    current_fd = root_fd
    try:
        segments = relative.split("/")
        for segment in segments[:-1]:
            next_fd = os.open(
                segment,
                os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
                dir_fd=current_fd,
            )
            if current_fd != root_fd:
                os.close(current_fd)
            current_fd = next_fd
        fd = os.open(segments[-1], os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0), dir_fd=current_fd)
        before = os.fstat(fd)
        raw = bytearray()
        try:
            while True:
                chunk = os.read(fd, 65536)
                if not chunk:
                    break
                raw.extend(chunk)
            after = os.fstat(fd)
            require(
                (before.st_dev, before.st_ino, before.st_mode, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
                == (after.st_dev, after.st_ino, after.st_mode, after.st_size, after.st_mtime_ns, after.st_ctime_ns),
                f"mutation locator changed during exact read: {relative}",
            )
            require(hashlib.sha256(raw).hexdigest() == state["raw_sha256"], f"mutation locator bytes changed: {relative}")
            return bytes(raw)
        finally:
            os.close(fd)
    finally:
        if current_fd != root_fd:
            os.close(current_fd)
        os.close(root_fd)


def _extended_pointer(value: Any, pointer: str) -> Any:
    if pointer in ("", "/"):
        return value
    require(pointer.startswith("/"), "mutation JSON locator is not an absolute pointer")
    current = value
    raw_tokens = pointer[1:].split("/")
    for token_index, raw_token in enumerate(raw_tokens):
        token = raw_token.replace("~1", "/").replace("~0", "~")
        if token == "*":
            require(isinstance(current, list), "mutation wildcard pointer requires an array")
            remainder = "/" + "/".join(raw_tokens[token_index + 1:])
            return [_extended_pointer(item, remainder) for item in current]
        if isinstance(current, list):
            if token == "-":
                current = {"state": "array-end-absent", "array_length": len(current)}
                continue
            if "=" in token:
                key, expected = token.split("=", 1)
                matches = [row for row in current if isinstance(row, dict) and str(row.get(key)) == expected]
                require(len(matches) == 1, f"mutation selector pointer is not unique: {token}")
                current = matches[0]
                continue
            require(token.isdigit() and int(token) < len(current), f"mutation array pointer is out of bounds: {token}")
            current = current[int(token)]
            continue
        if isinstance(current, dict):
            if token not in current:
                return {"state": "absent", "missing_token": token}
            current = current[token]
            continue
        raise RuntimeError(f"mutation pointer traversed a scalar at: {token}")
    return current


def _tree_digest(root: Path) -> str:
    state = hashlib.sha256()
    for current, directories, files in os.walk(root, topdown=True, followlinks=False):
        directories.sort(key=lambda value: value.encode("utf-8"))
        files.sort(key=lambda value: value.encode("utf-8"))
        for name in directories:
            require(not (Path(current) / name).is_symlink(), "typed runtime tree contains a symlink directory")
        for name in files:
            path = Path(current) / name
            require(path.is_file() and not path.is_symlink(), "typed runtime tree contains a non-regular file")
            relative = path.relative_to(root).as_posix().encode("utf-8")
            raw = path.read_bytes()
            for framed in (relative, raw):
                state.update(len(framed).to_bytes(8, "big"))
                state.update(framed)
    return state.hexdigest()


def _result_payload_state(contract: dict[str, Any], root: Path, case_id: str, phase: str) -> dict[str, Any]:
    rows = [
        {
            "sequence": case["sequence"],
            "case_id": case["case_id"],
            "expected_success": case["expected_success"],
            "executor_id": case["mutation_spec"]["executor_id"],
            "executor_implementation_sha256": case["mutation_spec"]["executor_implementation_sha256"],
            "executor_closure_sha256": case["mutation_spec"]["executor_closure_sha256"],
            "expected_failure_class": case["mutation_spec"]["expected_failure_class"],
            "expected_repo_effect": case["mutation_spec"]["expected_repo_effect"],
            "verdict": "pass" if case["expected_success"] else "rejected",
        }
        for case in contract["cases"]
    ]
    payload: Any = {
        "contract_id": contract["contract_id"],
        "case_count": contract["case_count"],
        "result_required_fields": contract["result_required_fields"],
        "result_row_required_fields": contract["result_row_required_fields"],
        "field_value_bindings": {
            "actual_success": "must-equal-case.expected_success",
            "applied_recipe_sha256": "must-equal-case.mutation_sha256",
            "mutated_output_sha256": "gate-recomputed-recipe-path-snapshot-after",
            "mutation_sha256": "must-equal-case.mutation_sha256",
            "observed_failure_class": "gate-recomputed-command-outcome",
            "source_input_sha256": "gate-recomputed-recipe-path-snapshot-before",
        },
        "cases": rows,
        "source_bytes_unchanged": True,
        "status": "ok",
    }
    if phase == "after":
        if case_id == "mutation-result-missing-case":
            payload["cases"].pop()
        elif case_id == "mutation-result-empty-cases":
            payload["cases"] = []
        elif case_id == "mutation-result-fake-status":
            payload = {"status": "ok"}
        elif case_id == "mutation-result-duplicate-id":
            payload["cases"][1] = dict(payload["cases"][0])
        else:
            raise RuntimeError(f"unknown result-payload typed serializer case: {case_id}")
    return {
        "serializer": "aq-gate-owned-result-payload-state-v1",
        "phase": phase,
        "case_id": case_id,
        "case_ids_in_order": [row["case_id"] for row in payload.get("cases", [])] if isinstance(payload, dict) else [],
        "payload": payload,
    }


def _runtime_locator_state(root: Path, spec: dict[str, Any], phase: str) -> dict[str, Any]:
    operation = spec["operation"]
    case_id = spec["kind"]
    runtime = runtime_guard.verify_runtime(require_external_bootstrap=True)
    source_identity = {path: _nofollow_path_state(root, path) for path in spec["repo_paths"]}
    observed_entity: dict[str, Any] = {"target_source_identity": source_identity}
    if case_id == "npm-implementation-tree-drift":
        fake_root = root / "qa/npm-package"
        package_runtime = json.loads(_read_regular_nofollow(root, "docs/contracts/package.json"))["aqValidationRuntime"]
        observed_entity["npm_tree"] = {
            "kind": "mutated-copy" if fake_root.is_dir() else "pinned-host-runtime",
            "tree_sha256": _tree_digest(fake_root) if fake_root.is_dir() else package_runtime["npm_package_tree_sha256"],
        }
    elif case_id == "release-gate-root-substitution":
        observed_entity["entry_binding"] = "selected-root-entry" if phase == "before" else "different-root-entry"
    elif case_id == "retention-synonym-corpus":
        fixture = json.loads(_read_regular_nofollow(root, "docs/contracts/fixtures/retention-lint-malicious-v1.json"))
        observed_entity["fixture_oracle"] = [
            {"fixture_id": row["fixture_id"], "expected": row["expected"]}
            for row in fixture["cases"]
        ]
        observed_entity["observation"] = "expected-oracle" if phase == "before" else "validator-replay-completed"
    else:
        observed_entity["observation"] = "pre-command" if phase == "before" else "post-command"
    return {
        "serializer": "aq-gate-owned-runtime-state-v1",
        "phase": phase,
        "case_id": case_id,
        "observation_command": operation["observation_command"],
        "resolved_executable": runtime["resolved_executable"],
        "binary_sha256": runtime_guard.EXPECTED["executable_sha256"],
        "dependency_binary_sha256": runtime_guard.EXPECTED["framework_sha256"],
        "implementation_tree_sha256": runtime["stdlib_tree_sha256"],
        "observed_entity": observed_entity,
    }


def locator_state(root: Path, spec: dict[str, Any], contract: dict[str, Any] | None = None, phase: str = "before") -> dict[str, Any]:
    operation = spec["operation"]
    kind = operation["locator_kind"]
    target = operation["target_repo_path"]
    require(target in spec["repo_paths"], "mutation locator target is outside repo_paths")
    raw_path_states = {path: _nofollow_path_state(root, path) for path in spec["repo_paths"]}
    if kind in {"runtime", "result-payload", "json-pointer", "text-anchor"}:
        path_states = {path: {"kind": raw_path_states[path]["kind"]} for path in spec["repo_paths"]}
    else:
        path_states = raw_path_states
    state: dict[str, Any] = {
        "locator_kind": kind,
        "target_repo_path": target,
        "locator": operation["locator"],
        "repo_path_states": path_states,
    }
    if kind == "json-pointer":
        raw = _read_regular_nofollow(root, target)
        resolved = _extended_pointer(json.loads(raw), operation["locator"])
        if operation["operation_id"] == "array-reverse":
            require(isinstance(resolved, list) and all(isinstance(row, dict) and "artifact_id" in row for row in resolved), "array-reverse locator is not the artifact registry sequence")
            resolved = [row["artifact_id"] for row in resolved]
        state["resolved"] = resolved
    elif kind == "text-anchor":
        raw = _read_regular_nofollow(root, target)
        if operation["locator"].startswith("EOF:"):
            state["tail_sha256"] = hashlib.sha256(raw[-1024:]).hexdigest()
            state["size"] = len(raw)
        else:
            anchor = operation["locator"].encode("utf-8")
            offsets: list[int] = []
            start = 0
            while True:
                index = raw.find(anchor, start)
                if index < 0:
                    break
                offsets.append(index)
                start = index + len(anchor)
            contexts = [raw[max(0, index - 256):min(len(raw), index + len(anchor) + 512)] for index in offsets]
            state["anchor_occurrences"] = len(offsets)
            state["anchor_contexts_sha256"] = [hashlib.sha256(context).hexdigest() for context in contexts]
    elif kind == "filesystem":
        state["filesystem"] = raw_path_states[target]
    elif kind == "runtime":
        state = _runtime_locator_state(root, spec, phase)
    elif kind == "result-payload":
        require(contract is not None, "result-payload serializer requires the full machine contract")
        state = _result_payload_state(contract, root, spec["kind"], phase)
    else:
        raise RuntimeError(f"unknown mutation locator kind: {kind}")
    return state


def locator_state_sha256(root: Path, spec: dict[str, Any], contract: dict[str, Any] | None = None, phase: str = "before") -> str:
    return hashlib.sha256(MUTATION_LOCATOR_STATE_DOMAIN + canonical(locator_state(root, spec, contract, phase))).hexdigest()


def _assert_typed_state(operation: dict[str, Any], state: dict[str, Any]) -> None:
    require(sorted(state) == operation["state_required_fields"], "typed mutation state field closure mismatch")
    require(state["serializer"] == operation["state_serializer"], "typed mutation state serializer mismatch")
    if operation["locator_kind"] == "runtime":
        require(state["observation_command"] == operation["observation_command"], "typed mutation observation command mismatch")


def verify_typed_state_self_tests(contract: dict[str, Any], root: Path) -> int:
    typed = [row for row in contract["cases"] if row["mutation_spec"]["operation"]["locator_kind"] in {"runtime", "result-payload"}]
    require(len(typed) == 9, "typed mutation self-test case closure mismatch")
    runtime_case = next(row for row in typed if row["mutation_spec"]["operation"]["locator_kind"] == "runtime")
    result_case = next(row for row in typed if row["case_id"] == "mutation-result-fake-status")

    runtime_spec = runtime_case["mutation_spec"]
    runtime_operation = runtime_spec["operation"]
    runtime_before = locator_state(root, runtime_spec, contract, "before")
    _assert_typed_state(runtime_operation, runtime_before)
    wrong_field = dict(runtime_before)
    wrong_field.pop("binary_sha256")
    rejected = 0
    try:
        _assert_typed_state(runtime_operation, wrong_field)
    except RuntimeError:
        rejected += 1
    else:
        raise RuntimeError("typed-state missing-field self-test did not fail closed")

    wrong_descriptor = dict(runtime_operation)
    wrong_descriptor["state_required_fields"] = ["wrong_field"]
    try:
        _assert_typed_state(wrong_descriptor, runtime_before)
    except RuntimeError:
        rejected += 1
    else:
        raise RuntimeError("typed-state wrong-descriptor self-test did not fail closed")

    changed_entity = json.loads(json.dumps(runtime_before))
    changed_entity["observed_entity"] = {"same_descriptor_different_entity": True}
    require(
        hashlib.sha256(MUTATION_LOCATOR_STATE_DOMAIN + canonical(runtime_before)).digest()
        != hashlib.sha256(MUTATION_LOCATOR_STATE_DOMAIN + canonical(changed_entity)).digest(),
        "typed-state entity drift is not digest-bound",
    )

    result_spec = result_case["mutation_spec"]
    result_operation = result_spec["operation"]
    result_before = locator_state(root, result_spec, contract, "before")
    result_after = locator_state(root, result_spec, contract, "after")
    _assert_typed_state(result_operation, result_before)
    _assert_typed_state(result_operation, result_after)
    require(canonical(result_before) != canonical(result_after), "typed result payload before/after states are equal")
    alternate_malformed = json.loads(json.dumps(result_after))
    alternate_malformed["payload"] = {"status": "ok", "alternate_malformed_shape": True}
    require(
        hashlib.sha256(MUTATION_LOCATOR_STATE_DOMAIN + canonical(alternate_malformed)).digest()
        != hashlib.sha256(MUTATION_LOCATOR_STATE_DOMAIN + canonical(result_after)).digest(),
        "typed result evidence collapses alternate malformed payloads into one failure class",
    )
    require(rejected == 2, "typed-state negative self-test count mismatch")
    return 4


def verify_runner_executor_contract(raw: bytes, contract: dict[str, Any], validator: Any) -> None:
    source = raw.decode("utf-8")
    tree = ast.parse(source)
    lines = source.splitlines()
    function_digests: dict[str, str] = {}
    mappings: dict[str, dict[str, str]] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            segment = "\n".join(lines[node.lineno - 1:node.end_lineno]).encode("utf-8")
            function_digests[node.name] = hashlib.sha256(MUTATION_EXECUTOR_DOMAIN + segment).hexdigest()
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id in {"MUTATORS", "EXECUTOR_BY_CASE"}:
            require(isinstance(node.value, ast.Dict), f"runner {node.target.id} is not a literal map")
            parsed: dict[str, str] = {}
            for key_node, value_node in zip(node.value.keys, node.value.values):
                require(isinstance(key_node, ast.Constant) and isinstance(key_node.value, str), f"runner {node.target.id} has a nonliteral key")
                if node.target.id == "MUTATORS":
                    require(isinstance(value_node, ast.Name), "runner MUTATORS has an indirect value")
                    parsed[key_node.value] = value_node.id
                else:
                    require(isinstance(value_node, ast.Constant) and isinstance(value_node.value, str), "runner EXECUTOR_BY_CASE has a nonliteral value")
                    parsed[key_node.value] = value_node.value
            mappings[node.target.id] = parsed
    require(set(mappings) == {"MUTATORS", "EXECUTOR_BY_CASE"}, "runner executor maps are incomplete")
    expected = {row["case_id"]: row["mutation_spec"]["executor_id"] for row in contract["cases"]}
    require(mappings["EXECUTOR_BY_CASE"] == expected, "runner explicit executor map differs from independent machine contract")
    require(all(expected.get(case_id) == executor for case_id, executor in mappings["MUTATORS"].items()), "runner mutator map differs from independent machine contract")
    for row in contract["cases"]:
        spec = row["mutation_spec"]
        require(function_digests.get(spec["executor_id"]) == spec["executor_implementation_sha256"], f"runner executor digest differs from independent machine contract: {row['case_id']}")
    actual_closure = validator._runner_closure_document(source)
    require(actual_closure == contract["runner_implementation_closure"], "runner transitive implementation closure differs from independent machine contract")
    closure_by_executor = {row["executor_id"]: row["closure_sha256"] for row in actual_closure["executor_closures"]}
    for row in contract["cases"]:
        spec = row["mutation_spec"]
        require(closure_by_executor.get(spec["executor_id"]) == spec["executor_closure_sha256"], f"runner executor closure digest differs from independent machine contract: {row['case_id']}")


def _completed(command: list[str], cwd: Path, env: dict[str, str], *, stdin: str | None = None, timeout: int = 120) -> tuple[bool, str, int]:
    completed = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        input=stdin,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        check=False,
        env=env,
    )
    return completed.returncode == 0, completed.stdout, completed.returncode


def _failure_class(success: bool, output: str) -> str:
    if success:
        return "none"
    if "release_gate_error=" in output:
        return "release-gate-rejection"
    if "validation_error=" in output:
        return "validator-rejection"
    if "runtime_bootstrap_error=" in output:
        return "release-gate-rejection"
    return "process-rejection"


def _concurrent_validator_failure(case_root: Path, env: dict[str, str]) -> tuple[bool, str, int]:
    child_env = dict(env)
    child_env["AQ_VALIDATION_MUTATION_TEST"] = "1"
    child_env["AQ_VALIDATION_TEST_PAUSE_BEFORE_FINAL_VERIFY_MS"] = "3000"
    ready_read, ready_write = os.pipe()
    child_env["AQ_VALIDATION_TEST_READY_FD"] = str(ready_write)
    try:
        process = subprocess.Popen(
            formal_command("docs/contracts/validate-contracts-v1.py"),
            cwd=case_root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=child_env,
            pass_fds=(ready_write,),
        )
        os.close(ready_write)
        ready_write = -1
        readable, _, _ = select.select([ready_read], [], [], 90)
        require(readable and os.read(ready_read, 5) == b"ready", "gate-owned validation input-change barrier was not reached")
        readme = case_root / "README.md"
        readme.write_text(readme.read_text(encoding="utf-8") + "\nGate-owned concurrent source-change probe.\n", encoding="utf-8")
        output, _ = process.communicate(timeout=90)
    finally:
        os.close(ready_read)
        if ready_write >= 0:
            os.close(ready_write)
    return process.returncode == 0, output, process.returncode or 0


def _concurrent_gate_failure(case_root: Path, env: dict[str, str]) -> tuple[bool, str, int]:
    child_env = dict(env)
    child_env["AQ_RELEASE_GATE_MUTATION_TEST"] = "1"
    child_env["AQ_RELEASE_GATE_TEST_PAUSE_BEFORE_FINAL_VERIFY_MS"] = "3000"
    ready_read, ready_write = os.pipe()
    child_env["AQ_RELEASE_GATE_TEST_READY_FD"] = str(ready_write)
    try:
        process = subprocess.Popen(
            formal_command("docs/contracts/run-release-gate-v1.py", "--root", ".", "--self-test-preflight"),
            cwd=case_root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=child_env,
            pass_fds=(ready_write,),
        )
        os.close(ready_write)
        ready_write = -1
        readable, _, _ = select.select([ready_read], [], [], 90)
        require(readable and os.read(ready_read, 5) == b"ready", "gate-owned release input-change barrier was not reached")
        readme = case_root / "README.md"
        readme.write_text(readme.read_text(encoding="utf-8") + "\nGate-owned concurrent gate probe.\n", encoding="utf-8")
        output, _ = process.communicate(timeout=90)
    finally:
        os.close(ready_read)
        if ready_write >= 0:
            os.close(ready_write)
    return process.returncode == 0, output, process.returncode or 0


def _synthetic_results(contract: dict[str, Any], case_root: Path) -> dict[str, Any]:
    rows = []
    for case in contract["cases"]:
        spec = case["mutation_spec"]
        source_digest = recipe_path_snapshot(case_root, spec["repo_paths"])
        rows.append({
            "sequence": case["sequence"],
            "case_id": case["case_id"],
            "expected_success": case["expected_success"],
            "actual_success": case["expected_success"],
            "mutation_sha256": case["mutation_sha256"],
            "source_input_sha256": source_digest,
            "applied_recipe_sha256": case["mutation_sha256"],
            "executor_id": spec["executor_id"],
            "executor_implementation_sha256": spec["executor_implementation_sha256"],
            "executor_closure_sha256": spec["executor_closure_sha256"],
            "mutated_output_sha256": source_digest if spec["expected_repo_effect"] == "unchanged" else "0" * 64,
            "observed_failure_class": spec["expected_failure_class"],
            "verdict": "pass" if case["expected_success"] else "rejected",
        })
    payload = {
        "contract_id": contract["contract_id"],
        "case_count": contract["case_count"],
        "cases": rows,
        "source_bytes_unchanged": True,
        "status": "ok",
    }
    payload["results_sha256"] = hashlib.sha256(MUTATION_RESULTS_DOMAIN + canonical(payload)).hexdigest()
    return payload


def _gate_owned_case_outcome(
    case: dict[str, Any],
    contract: dict[str, Any],
    case_root: Path,
    clean_root: Path,
    tooling: dict[str, Any],
    base_env: dict[str, str],
) -> tuple[bool, str]:
    kind = case["case_id"]
    if kind == "validation-input-changed":
        success, output, _ = _concurrent_validator_failure(case_root, base_env)
        return success, _failure_class(success, output)
    if kind == "release-gate-concurrent-replacement":
        success, output, _ = _concurrent_gate_failure(case_root, base_env)
        return success, _failure_class(success, output)
    if kind == "npm-implementation-tree-drift":
        with tempfile.TemporaryDirectory(prefix="aq-gate-owned-npm-drift-") as temporary:
            actual_launcher = os.path.realpath(tooling["npm_path"])
            actual_root = Path(actual_launcher).parent.parent
            fake_root = Path(temporary) / "npm-package"
            shutil.copytree(actual_root, fake_root)
            changed = fake_root / "lib/cli.js"
            changed.write_text(changed.read_text(encoding="utf-8") + "\n// gate-owned npm tree drift\n", encoding="utf-8")
            fake_bin = Path(temporary) / "bin"
            fake_bin.mkdir()
            (fake_bin / "npm").symlink_to(fake_root / "bin/npm-cli.js")
            env = dict(base_env)
            env["PATH"] = str(fake_bin) + os.pathsep + env["PATH"]
            env["AQ_VALIDATION_MUTATION_TEST"] = "1"
            env["AQ_VALIDATION_NPM_PACKAGE_ROOT"] = str(fake_root.resolve())
            success, output, _ = _completed(formal_command("docs/contracts/validate-contracts-v1.py"), case_root, env)
            return success, _failure_class(success, output)
    if kind in {"release-gate-entry-symlink", "release-gate-source-symlink"}:
        env = dict(base_env)
        env["AQ_RELEASE_GATE_MUTATION_TEST"] = "1"
        success, output, _ = _completed(
            formal_command("docs/contracts/run-release-gate-v1.py", "--root", ".", "--self-test-preflight"),
            case_root,
            env,
        )
        return success, _failure_class(success, output)
    if kind == "release-gate-root-substitution":
        env = dict(base_env)
        env["AQ_RELEASE_GATE_MUTATION_TEST"] = "1"
        success, output, _ = _completed(
            formal_command("docs/contracts/run-release-gate-v1.py", "--root", str(case_root), "--self-test-preflight"),
            clean_root,
            env,
        )
        return success, _failure_class(success, output)
    if kind.startswith("mutation-result-"):
        payload: Any = _synthetic_results(contract, case_root)
        if kind == "mutation-result-missing-case":
            payload["cases"].pop()
        elif kind == "mutation-result-empty-cases":
            payload["cases"] = []
        elif kind == "mutation-result-fake-status":
            payload = {"status": "ok"}
        elif kind == "mutation-result-duplicate-id":
            payload["cases"][1] = dict(payload["cases"][0])
        if isinstance(payload, dict) and set(payload) != {"status"}:
            projected = {key: value for key, value in payload.items() if key != "results_sha256"}
            payload["results_sha256"] = hashlib.sha256(MUTATION_RESULTS_DOMAIN + canonical(projected)).hexdigest()
        env = dict(base_env)
        env["AQ_RELEASE_GATE_MUTATION_TEST"] = "1"
        success, output, _ = _completed(
            formal_command("docs/contracts/run-release-gate-v1.py", "--root", ".", "--self-test-verify-mutation-results"),
            case_root,
            env,
            stdin=canonical(payload).decode("utf-8"),
        )
        return success, _failure_class(success, output)
    success, output, _ = _completed(formal_command("docs/contracts/validate-contracts-v1.py"), case_root, base_env)
    success = success and output.rstrip().endswith("status=ok")
    return success, _failure_class(success, output)


def verify_helper_closure_fail_closed(clean_root: Path, dependency: Path, base_env: dict[str, str]) -> None:
    helpers = ["save", "repin", "subprocess_success", "observed_failure_class", "recipe_path_snapshot"]
    for helper in helpers:
        with tempfile.TemporaryDirectory(prefix=f"aq-helper-closure-{helper}-") as temporary:
            target = Path(temporary) / "repo"
            shutil.copytree(clean_root, target, symlinks=True)
            node_modules = target / "docs/contracts/node_modules"
            if node_modules.is_symlink() or node_modules.exists():
                if node_modules.is_symlink():
                    node_modules.unlink()
                else:
                    shutil.rmtree(node_modules)
            node_modules.symlink_to(dependency, target_is_directory=True)
            runner = target / "docs/contracts/run-validation-mutations-v1.py"
            source = runner.read_text(encoding="utf-8")
            tree = ast.parse(source)
            node = next(
                candidate for candidate in tree.body
                if isinstance(candidate, (ast.FunctionDef, ast.AsyncFunctionDef)) and candidate.name == helper
            )
            lines = source.splitlines(keepends=True)
            insertion = node.body[0].lineno - 1
            lines.insert(insertion, "    _aq_helper_closure_probe = None\n")
            runner.write_text("".join(lines), encoding="utf-8")
            package_path = target / "docs/contracts/package.json"
            package = json.loads(package_path.read_text(encoding="utf-8"))
            package["aqValidationRuntime"]["launch_entry_raw_sha256"]["docs/contracts/run-validation-mutations-v1.py"] = hashlib.sha256(
                runner.read_bytes()
            ).hexdigest()
            package_path.write_text(json.dumps(package, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            success, output, _ = _completed(formal_command("docs/contracts/validate-contracts-v1.py"), target, base_env)
            require(
                not success and "mutation runner transitive implementation closure mismatch" in output,
                f"helper-only closure mutation did not fail closed: {helper}\n{output.rstrip()}",
            )


def verify_external_negative_self_tests(
    validator: Any,
    snapshot: dict[str, bytes],
    base_env: dict[str, str],
) -> int:
    """Exercise runtime, bootstrap, offline-bundle, and dynamic-history fail-closed paths."""

    def save_json(path: Path, value: dict[str, Any]) -> None:
        path.write_bytes(canonical(value) + b"\n")

    def mutate_json(root: Path, relative: str, edit: Any) -> None:
        path = root / relative
        value = json.loads(path.read_bytes())
        edit(value)
        save_json(path, value)

    def run_section(root: Path, section: str) -> tuple[bool, str]:
        case_reader = None
        try:
            case_reader = validator.RepositoryReader(root_abs=str(root))
            case_contracts = validator.load_contract_set(case_reader)
            if section == "runtime":
                validator.validate_dependency_runtime(case_contracts)
            elif section == "history":
                current = case_contracts.artifacts["docs/contracts/core-safety-contract-v1.json"].document["current_design_status"]
                validator.validate_history_manifest(case_contracts, current)
            elif section == "projections":
                validator.validate_projections(case_contracts)
            else:
                raise RuntimeError(f"unknown external self-test section: {section}")
            return True, ""
        except (RuntimeError, OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
            return False, str(error)
        finally:
            if case_reader is not None:
                case_reader.close()

    cases: list[tuple[str, str, str, Any]] = []

    def runtime_field(field: str, value: Any) -> Any:
        return lambda root: mutate_json(root, "docs/contracts/package.json", lambda document: document["aqValidationRuntime"].__setitem__(field, value))

    cases.extend([
        ("python-profile-unregistered-3.12", "runtime", "Python exact version profile mismatch", runtime_field("python_version_exact", "3.12.0")),
        ("python-profile-wrong-3.11-patch", "runtime", "Python exact version profile mismatch", runtime_field("python_version_exact", "3.11.14")),
        ("python-binary-drift", "runtime", "Python binary profile mismatch", runtime_field("python_binary_sha256", "0" * 64)),
        ("python-stdlib-drift", "runtime", "Python stdlib implementation tree profile mismatch", runtime_field("python_stdlib_tree_sha256", "0" * 64)),
        ("python-abi-drift", "runtime", "Python ABI profile mismatch", runtime_field("python_abi", "cpython-311-unregistered")),
        ("python-platform-drift", "runtime", "Python platform profile mismatch", runtime_field("python_platform", "macosx-99.0-arm64")),
        ("python-resolved-launcher-drift", "runtime", "Python resolved executable profile mismatch", runtime_field("python_resolved_executable", "/tmp/unregistered-python3.11")),
    ])

    def edit_image_digest(path: str) -> Any:
        def edit(root: Path) -> None:
            def mutate(document: dict[str, Any]) -> None:
                row = next(item for item in document["aqValidationRuntime"]["non_system_images"] if item["path"] == path)
                row["raw_sha256"] = "0" * 64
            mutate_json(root, "docs/contracts/package.json", mutate)
        return edit

    def edit_closure(closure_id: str, edit: Any) -> Any:
        return lambda root: mutate_json(
            root,
            "docs/contracts/package.json",
            lambda document: edit(document["aqValidationRuntime"]["non_system_image_closures"][closure_id]),
        )

    def opt_target_switch(root: Path) -> None:
        def edit(document: dict[str, Any]) -> None:
            row = next(item for item in document["aqValidationRuntime"]["opt_link_bindings"] if item["path"] == "/opt/homebrew/opt/openssl@3")
            row["target"] = "../Cellar/openssl@3/unregistered"
        mutate_json(root, "docs/contracts/package.json", edit)

    def add_python_extra_image(paths: list[str]) -> None:
        paths.append("/opt/homebrew/Cellar/gmp/6.3.0/lib/libgmp.10.dylib")
        paths.sort(key=lambda value: value.encode("utf-8"))

    cases.extend([
        ("openssl-opt-target-switch", "runtime", "runtime opt-link binding set mismatch", opt_target_switch),
        ("libcrypto-bit-drift", "runtime", "non-system image raw digest mismatch", edit_image_digest("/opt/homebrew/Cellar/openssl@3/3.6.2/lib/libcrypto.3.dylib")),
        ("gmp-bit-drift", "runtime", "non-system image raw digest mismatch", edit_image_digest("/opt/homebrew/Cellar/gmp/6.3.0/lib/libgmp.10.dylib")),
        ("pandoc-extra-dependency-closure", "runtime", "native loaded-image closure is not recursively closed", edit_closure("pandoc", lambda paths: paths.remove("/opt/homebrew/Cellar/gmp/6.3.0/lib/libgmp.10.dylib"))),
        ("python-same-executable-different-image-set", "runtime", "Python guard/profile loaded-image closure mismatch", edit_closure("python", add_python_extra_image)),
    ])

    def bundle_extra(root: Path) -> None:
        (root / "docs/contracts/offline-npm-bundle-v1/extra-1.0.0.tgz").write_bytes(b"external-qa-extra")

    def bundle_missing(root: Path) -> None:
        (root / "docs/contracts/offline-npm-bundle-v1/ajv-8.17.1.tgz").unlink()

    def bundle_bit_drift(root: Path) -> None:
        path = root / "docs/contracts/offline-npm-bundle-v1/ajv-8.17.1.tgz"
        path.write_bytes(path.read_bytes() + b"external-qa-drift")

    def bundle_registry_url(root: Path) -> None:
        mutate_json(root, "docs/contracts/package.json", lambda document: document["dependencies"].__setitem__("ajv", "https://registry.npmjs.org/ajv/-/ajv-8.17.1.tgz"))

    def bundle_manifest_digest(root: Path) -> None:
        def edit(document: dict[str, Any]) -> None:
            document["aqValidationRuntime"]["offline_bundle"][0]["raw_sha256"] = "0" * 64
        mutate_json(root, "docs/contracts/package.json", edit)

    cases.extend([
        ("offline-bundle-extra-entry", "runtime", "offline bundle directory has a missing or extra entry", bundle_extra),
        ("offline-bundle-missing-entry", "runtime", "offline bundle directory has a missing or extra entry", bundle_missing),
        ("offline-bundle-bit-drift", "runtime", "offline bundle tarball digest mismatch", bundle_bit_drift),
        ("offline-bundle-registry-url", "runtime", "manifest dependencies must be the exact local offline bundle", bundle_registry_url),
        ("offline-bundle-manifest-digest", "runtime", "offline bundle tarball digest mismatch", bundle_manifest_digest),
    ])

    manifest_rel = "docs/contracts/history-manifest-v1.json"
    baseline_manifest = json.loads(snapshot[manifest_rel])
    baseline_latest = baseline_manifest["latest"]
    latest_round = baseline_latest["round"]
    audit_rel = baseline_latest["audit"]["path"]
    resolution_rel = baseline_latest.get("resolution", {}).get("path")
    latest_state = baseline_latest.get("state")
    require(latest_state in {"ISSUES_OPEN", "ZERO_ISSUES"}, "external history QA latest state mismatch")
    require((latest_state == "ISSUES_OPEN") == isinstance(resolution_rel, str), "external history QA resolution/state mismatch")

    def history_delete_audit(root: Path) -> None:
        (root / audit_rel).unlink()

    def history_replace_audit(root: Path) -> None:
        path = root / audit_rel
        path.write_bytes(path.read_bytes() + b"\nhistory-replacement\n")

    def history_fake_first_line(root: Path) -> None:
        audit_path = root / audit_rel
        source = audit_path.read_text(encoding="utf-8")
        replacement = "# PASS_ZERO_ISSUES" if latest_state == "ISSUES_OPEN" else "# FAIL_WITH_1_ISSUES"
        audit_path.write_text(source.replace(baseline_latest["audit"]["first_line"], replacement, 1), encoding="utf-8")
        raw_digest = hashlib.sha256(audit_path.read_bytes()).hexdigest()
        def edit(document: dict[str, Any]) -> None:
            next(row for row in document["entries"] if row["path"] == audit_rel)["raw_sha256"] = raw_digest
            document["latest"]["audit"]["raw_sha256"] = raw_digest
        mutate_json(root, manifest_rel, edit)

    def history_latest_rollback(root: Path) -> None:
        mutate_json(root, manifest_rel, lambda document: document["latest"].__setitem__("round", latest_round - 1))

    def history_projection_drift(root: Path) -> None:
        path = root / "README.md"
        source = path.read_text(encoding="utf-8")
        path.write_text(source.replace(f'"revision_round":{latest_round}', f'"revision_round":{latest_round - 1}', 1), encoding="utf-8")

    history_cases: list[tuple[str, str, str, Any]] = [
        ("history-delete-latest-audit", "history", "no-follow open failed", history_delete_audit),
        ("history-replace-latest-audit", "history", "history raw digest mismatch", history_replace_audit),
        ("history-fake-first-line", "history", "history audit first-line/verdict mismatch", history_fake_first_line),
        ("history-latest-round-rollback", "history", "history latest round mismatch", history_latest_rollback),
        ("history-current-projection-drift", "projections", "current design status projection mismatch", history_projection_drift),
    ]
    if latest_state == "ISSUES_OPEN":
        def history_delete_resolution(root: Path) -> None:
            require(isinstance(resolution_rel, str), "open history resolution path disappeared")
            (root / resolution_rel).unlink()
        history_cases.append(("history-delete-latest-resolution", "history", "no-follow open failed", history_delete_resolution))
    else:
        def history_inject_resolution(root: Path) -> None:
            injected_rel = f"docs/audits/round-{latest_round:02d}-resolution.md"
            raw = f"# 第 {latest_round} 轮非法终态处置\n".encode("utf-8")
            (root / injected_rel).write_bytes(raw)
            def edit(document: dict[str, Any]) -> None:
                document["entries"].append({
                    "round": latest_round,
                    "kind": "resolution",
                    "path": injected_rel,
                    "raw_sha256": hashlib.sha256(raw).hexdigest(),
                })
            mutate_json(root, manifest_rel, edit)
        history_cases.append(("history-zero-injected-resolution", "history", "zero history round must not have a resolution", history_inject_resolution))
    cases.extend(history_cases)

    rejected = 0
    for qa_id, section, expected, mutate in cases:
        with tempfile.TemporaryDirectory(prefix=f"aq-external-{qa_id}-") as temporary:
            root = Path(os.path.realpath(temporary)) / "repo"
            root.mkdir()
            copy_snapshot(snapshot, root)
            mutate(root)
            success, output = run_section(root, section)
            require(not success and expected in output, f"external negative self-test did not fail closed: {qa_id}: {output}")
            rejected += 1

    with tempfile.TemporaryDirectory(prefix="aq-python-launchers-") as temporary:
        temporary_root = Path(os.path.realpath(temporary))
        root = temporary_root / "repo"
        root.mkdir()
        copy_snapshot(snapshot, root)
        direct_env = dict(base_env)
        direct_env.update({"LANG": "C", "LC_ALL": "C", "PYTHONHASHSEED": "0", "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1"})
        success, output, _ = _completed(["/usr/bin/python3", "docs/contracts/validate-contracts-v1.py"], root, direct_env)
        require(not success and "Python runtime identity mismatch" in output, f"unregistered Python 3.9/PATH launcher did not fail at runtime identity: {output.rstrip()}")
        rejected += 1
        python312 = "/Users/kyle/.local/bin/python3.12"
        require(os.path.isfile(python312), "registered Python 3.12 rejection probe is unavailable")
        success, output, _ = _completed([python312, "docs/contracts/validate-contracts-v1.py"], root, direct_env)
        require(not success and "Python runtime identity mismatch" in output, f"unregistered Python 3.12 launcher did not fail at runtime identity: {output.rstrip()}")
        rejected += 1
        copied = temporary_root / "unregistered-python3.11"
        shutil.copy2(sys.executable, copied)
        success, output, _ = _completed([str(copied), "docs/contracts/validate-contracts-v1.py"], root, direct_env)
        require(not success and "Python runtime identity mismatch" in output, f"unregistered Python 3.11 binary copy did not fail at runtime identity: {output.rstrip()}")
        rejected += 1

        injected_env = dict(direct_env)
        injected_env["DYLD_INSERT_LIBRARIES"] = "/opt/homebrew/Cellar/gmp/6.3.0/lib/libgmp.10.dylib"
        success, output, _ = _completed(
            [sys.executable, "-I", "-B", "-c", "import sys;sys.path.insert(0,'docs/contracts');import python_runtime_guard_v1 as g;g.verify_runtime(require_external_bootstrap=True)"],
            root,
            injected_env,
        )
        require(not success and ("unregistered loader/Python environment" in output or "unregistered non-system loaded image" in output), f"loader injection did not fail closed: {output.rstrip()}")
        rejected += 1

    require(rejected == 27, f"external runtime/history negative self-test count mismatch: {rejected}")
    return rejected


def verify_loaded_image_collector_self_tests(validator: Any) -> int:
    """Prove discovery is prefix-independent and path failures are closed."""
    verified = 0
    with tempfile.TemporaryDirectory(prefix="aq-loaded-image-fixture-") as temporary:
        root = Path(os.path.realpath(temporary))
        dylib = root / "liboutside-prefix.dylib"
        shutil.copy2("/opt/homebrew/Cellar/gmp/6.3.0/lib/libgmp.10.dylib", dylib)
        dylib.chmod(0o600)
        fixture_paths = [
            "/opt/homebrew/Cellar/gmp/6.3.0/lib/libgmp.10.dylib",
            "/usr/local/bin/node",
            "/Library/AgentQuota/liboutside-library.dylib",
            "/Applications/Agent Quota.app/Contents/MacOS/Agent Quota",
            "/Users/fixture/AgentQuota/liboutside-users.dylib",
            str(dylib),
            "/System/Library/Frameworks/Fixture.framework/Versions/A/Fixture",
            "/usr/lib/libFixture.dylib",
        ]
        vmmap = "\n".join(
            f"__TEXT 1000-2000 [  4K   4K   0K   0K] r-x/r-x SM=COW          {path}"
            for path in fixture_paths
        )
        parsed = validator._parse_vmmap_file_backed_images(vmmap)
        require(set(parsed) == set(fixture_paths), "loaded-image parser retained an installation-prefix filter")
        verified += len(fixture_paths)

        observed = validator._non_system_images_from_vmmap("\n".join(
            f"__TEXT 1000-2000 [  4K   4K   0K   0K] r-x/r-x SM=COW          {path}"
            for path in (
                "/opt/homebrew/Cellar/gmp/6.3.0/lib/libgmp.10.dylib",
                "/usr/local/bin/node",
                str(dylib),
                "/System/Library/Frameworks/Fixture.framework/Versions/A/Fixture",
                "/usr/lib/libFixture.dylib",
            )
        ))
        require(set(observed) == {
            "/opt/homebrew/Cellar/gmp/6.3.0/lib/libgmp.10.dylib", "/usr/local/bin/node", str(dylib)
        }, "loaded-image system/non-system classifier mismatch")
        verified += 1

        validator._require_exact_observed_image_closure("fixture", observed, observed)
        for qa_id, actual, expected, failure in (
            ("unknown", observed + [str(root / "unknown.dylib")], observed, "unregistered non-system loaded image"),
            ("missing", observed[:-1], observed, "required non-system loaded image missing"),
        ):
            try:
                validator._require_exact_observed_image_closure(qa_id, actual, expected)
            except RuntimeError as error:
                require(failure in str(error), f"loaded-image set rejection class mismatch: {qa_id}: {error}")
            else:
                raise RuntimeError(f"loaded-image set mismatch was accepted: {qa_id}")
            verified += 1

        before_digest = runtime_guard._sha(dylib)
        dylib.write_bytes(dylib.read_bytes() + b"drift")
        require(runtime_guard._sha(dylib) != before_digest, "loaded-image bytes drift was not observable")
        verified += 1

        symlink_path = root / "symlink-image.dylib"
        symlink_path.symlink_to(dylib.name)
        directory_path = root / "directory-image.dylib"
        directory_path.mkdir()
        missing_path = root / "missing-image.dylib"
        for qa_id, path in (("symlink", symlink_path), ("non-regular", directory_path), ("canonicalize", missing_path)):
            try:
                validator._canonical_loaded_image_path(str(path))
            except (RuntimeError, OSError):
                verified += 1
            else:
                raise RuntimeError(f"loaded-image invalid path was accepted: {qa_id}")

        clean_dylib = root / "libend-to-end.dylib"
        shutil.copy2("/opt/homebrew/Cellar/gmp/6.3.0/lib/libgmp.10.dylib", clean_dylib)
        command = [
            sys.executable, "-I", "-B", "-c",
            "import ctypes,sys;ctypes.CDLL(sys.argv[1]);sys.stdin.buffer.read(1)", str(clean_dylib),
        ]
        end_to_end = validator._probe_process_non_system_images(command)
        require(str(clean_dylib) in end_to_end, "real temporary-directory dylib was invisible to loaded-image discovery")
        verified += 1
    return verified


def verify_retry_after_dual_process_self_test(contracts: Any) -> int:
    """Evaluate the frozen virtual clock in two independent local processes."""
    contract = contracts.artifacts["docs/contracts/core-safety-contract-v1.json"].document["budget_ledger_contract"]["retry_after_aggregation"]
    clock = contract["dual_process_virtual_clock"]
    base_boundaries = [
        {"scope": "group", "reason": "floor", "boundary_utc_seconds": value}
        for value in clock["active_boundaries_utc_seconds"]
    ]
    code = (
        "import json,sys;d=json.loads(sys.argv[1]);h=d['hard_max_seconds'];"
        "out=[];"
        "[(lambda a,n:out.append([min(h,max(a)-n),'deferred'] if a else [None,'reserve_allowed']))"
        "([r['boundary_utc_seconds'] for r in d['boundaries'] if n<r['boundary_utc_seconds']],n) for n in d['times']];"
        "print(json.dumps(out,separators=(',',':')))"
    )
    outputs: list[str] = []
    for boundaries, primary_reason in ((base_boundaries, "floor"), (list(reversed(base_boundaries)), "hour")):
        payload = {
            "hard_max_seconds": contract["hard_max_seconds"],
            "boundaries": boundaries,
            "primary_reason": primary_reason,
            "times": [clock["initial_now_utc_seconds"], clock["first_retry_utc_seconds"], clock["all_clear_utc_seconds"]],
        }
        completed = subprocess.run(
            [sys.executable, "-I", "-B", "-c", code, canonical(payload).decode("utf-8")],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"},
            timeout=30,
            check=False,
        )
        require(completed.returncode == 0, f"retry-after virtual-clock process failed: {completed.stderr.strip()}")
        outputs.append(completed.stdout.strip())
    expected = canonical([[60, "deferred"], [50, "deferred"], [None, "reserve_allowed"]]).decode("utf-8")
    require(outputs == [expected, expected], "retry-after result changed with process order or primary reason")
    return 2


def verify_bootstrap_negative_self_tests(snapshot: dict[str, bytes], base_env: dict[str, str]) -> int:
    """Prove local launch integrity without manufacturing fixed-launch authority."""

    def fresh_root(parent: Path) -> Path:
        root = parent / "repo"
        root.mkdir()
        copy_snapshot(snapshot, root)
        return root

    rejected = 0
    with tempfile.TemporaryDirectory(prefix="aq-bootstrap-direct-env-") as temporary:
        root = fresh_root(Path(os.path.realpath(temporary)))
        env = dict(base_env)
        env.update({"LANG": "C", "LC_ALL": "C", "PYTHONHASHSEED": "0", "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1"})
        success, output, _ = _completed(
            [
                sys.executable,
                "-I",
                "-B",
                "-c",
                "import json,sys;sys.path.insert(0,'docs/contracts');import python_runtime_guard_v1 as g;print(json.dumps(g.verify_runtime(require_external_bootstrap=True),sort_keys=True))",
            ],
            root,
            env,
        )
        require(success and '\"external_launch_attestation\": \"absent\"' in output and '\"launch_authority\": \"local-audit-evidence-only-not-fixed-launch-proof\"' in output, f"direct fixed Python did not remain explicitly local-only: {output}")
        rejected += 1

    with tempfile.TemporaryDirectory(prefix="aq-bootstrap-bash-") as temporary:
        root = fresh_root(Path(os.path.realpath(temporary)))
        success, output, _ = _completed(
            ["/bin/bash", "docs/contracts/runtime-bootstrap-v1.sh", "docs/contracts/validate-contracts-v1.py", "--quiet"],
            root,
            base_env,
        )
        require(not success and "actual shell executable mismatch" in output, f"alternate shell did not fail with the interpreter class: {output}")
        rejected += 1

    with tempfile.TemporaryDirectory(prefix="aq-bootstrap-unregistered-") as temporary:
        root = fresh_root(Path(os.path.realpath(temporary)))
        (root / "docs/contracts/unregistered-tool.py").write_text("raise SystemExit(0)\n", encoding="utf-8")
        success, output, _ = _completed(
            formal_command("docs/contracts/unregistered-tool.py"),
            root,
            base_env,
        )
        require(not success and "entry is not in the exact launch allowlist" in output, f"unregistered entry did not fail with the allowlist class: {output}")
        rejected += 1

    with tempfile.TemporaryDirectory(prefix="aq-bootstrap-drift-") as temporary:
        root = fresh_root(Path(os.path.realpath(temporary)))
        bootstrap_path = root / "docs/contracts/runtime-bootstrap-v1.sh"
        bootstrap_path.write_bytes(bootstrap_path.read_bytes() + b"\n# bootstrap drift probe\n")
        success, output, _ = _completed(formal_command("docs/contracts/validate-contracts-v1.py", "--quiet"), root, base_env)
        require(not success and "bootstrap raw digest mismatch" in output, f"bootstrap drift did not fail with the raw-digest class: {output}")
        rejected += 1

    with tempfile.TemporaryDirectory(prefix="aq-bootstrap-intermediate-symlink-") as temporary:
        root = fresh_root(Path(os.path.realpath(temporary)))
        docs = root / "docs"
        saved = root / "real-docs"
        docs.rename(saved)
        docs.symlink_to(saved.name, target_is_directory=True)
        success, output, _ = _completed(formal_command("docs/contracts/validate-contracts-v1.py", "--quiet"), root, base_env)
        require(not success and "repository path component is a symlink: docs" in output, f"intermediate symlink did not fail with the no-follow class: {output}")
        rejected += 1

    with tempfile.TemporaryDirectory(prefix="aq-bootstrap-entry-toctou-") as temporary:
        temporary_root = Path(os.path.realpath(temporary))
        root = fresh_root(temporary_root)
        ready = temporary_root / "ready"
        continue_file = temporary_root / "continue"
        env = dict(base_env)
        env["AQ_BOOTSTRAP_MUTATION_TEST"] = "1"
        env["AQ_BOOTSTRAP_TEST_READY_FILE"] = str(ready)
        env["AQ_BOOTSTRAP_TEST_CONTINUE_FILE"] = str(continue_file)
        process = subprocess.Popen(
            formal_command("docs/contracts/validate-contracts-v1.py", "--quiet"),
            cwd=root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
        )
        deadline = time.monotonic() + 30
        while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.05)
        require(ready.exists(), "entry TOCTOU probe did not reach the post-open barrier")
        entry = root / "docs/contracts/validate-contracts-v1.py"
        saved = entry.with_suffix(".toctou-saved")
        entry.rename(saved)
        entry.write_bytes(saved.read_bytes())
        continue_file.write_text("continue\n", encoding="utf-8")
        output, _ = process.communicate(timeout=30)
        require(process.returncode != 0 and "entry path changed after open" in output, f"entry TOCTOU did not fail with the identity class: {output}")
        rejected += 1

    with tempfile.TemporaryDirectory(prefix="aq-bootstrap-opened-inode-swap-") as temporary:
        root = fresh_root(Path(os.path.realpath(temporary)))
        (root / "docs/contracts/node_modules").symlink_to(
            (Path(SCRIPT_ABS).parent / "node_modules").resolve(), target_is_directory=True
        )
        bootstrap = root / "docs/contracts/runtime-bootstrap-v1.sh"
        clean = root / "docs/contracts/runtime-bootstrap-v1.clean"
        clean.write_bytes(bootstrap.read_bytes())
        source = bootstrap.read_text(encoding="utf-8")
        injected = source.replace("set -eu\n", "set -eu\n/bin/mv docs/contracts/runtime-bootstrap-v1.clean docs/contracts/runtime-bootstrap-v1.sh\n", 1)
        require(injected != source, "opened-inode swap probe insertion failed")
        bootstrap.write_text(injected, encoding="utf-8")
        success, output, _ = _completed(formal_command("docs/contracts/validate-contracts-v1.py", "--quiet"), root, base_env)
        require(success and "external_launch_attestation=absent" in output and "launch_authority=local-audit-evidence-only-not-fixed-launch-proof" in output, f"opened-inode/path swap escaped the local-only authority boundary: {output}")
        rejected += 1

    require(rejected == 7, f"bootstrap negative self-test count mismatch: {rejected}")
    return rejected


def verify_dynamic_history_state_machine(validator: Any, snapshot: dict[str, bytes]) -> int:
    """Verify legal progress, terminal fixed points, and the round-20 budget."""

    def transition_mode(round_number: int, state: str) -> str:
        require(1 <= round_number <= validator.MAX_AUDIT_ROUNDS, "dynamic history transition round is outside budget")
        require(state in {"ISSUES_OPEN", "ZERO_ISSUES"}, "dynamic history transition state mismatch")
        if round_number == validator.MAX_AUDIT_ROUNDS:
            return "terminal-fixed-point" if state == "ZERO_ISSUES" else "round-budget-exhausted"
        return "advance-allowed" if state == "ISSUES_OPEN" else "terminal-fixed-point"

    def save_json(path: Path, value: dict[str, Any]) -> None:
        path.write_bytes(canonical(value) + b"\n")

    def update_markers(root: Path, status: dict[str, Any]) -> None:
        marker_inner = "\n```json\n" + canonical(status).decode("utf-8") + "\n```\n"
        pattern = re.compile(r"(<!-- AQ-GENERATED-CURRENT-STATUS-V1:BEGIN -->).*?(<!-- AQ-GENERATED-CURRENT-STATUS-V1:END -->)", re.DOTALL)
        for relative in validator.LIVE_DOC_PATHS:
            path = root / relative
            updated, count = pattern.subn(r"\1" + marker_inner + r"\2", path.read_text(encoding="utf-8"))
            require(count == 1, f"synthetic terminal marker update failed: {relative}")
            path.write_text(updated, encoding="utf-8")

    def validate_state(root: Path) -> str:
        reader = None
        try:
            reader = validator.RepositoryReader(root_abs=str(root))
            contracts = validator.load_contract_set(reader)
            current = contracts.artifacts["docs/contracts/core-safety-contract-v1.json"].document["current_design_status"]
            validator.validate_history_manifest(contracts, current)
            validator.validate_projections(contracts)
            validator.validate_core_closure(contracts)
            reader.verify_unchanged()
            return hashlib.sha256(canonical(current)).hexdigest()
        finally:
            if reader is not None:
                reader.close()

    def expect_rejected(base: Path, qa_id: str, expected: str, mutate: Any) -> None:
        case_root = base.parent / qa_id
        shutil.copytree(base, case_root)
        mutate(case_root)
        try:
            validate_state(case_root)
        except (RuntimeError, OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
            require(expected in str(error), f"dynamic history rejection class mismatch: {qa_id}: {error}")
            return
        raise RuntimeError(f"dynamic history invalid state was accepted: {qa_id}")

    baseline_manifest = json.loads(snapshot[validator.HISTORY_MANIFEST_REL])
    baseline_latest = baseline_manifest["latest"]
    baseline_round = baseline_latest["round"]
    baseline_state = baseline_latest["state"]
    actual_mode = transition_mode(baseline_round, baseline_state)
    if actual_mode == "round-budget-exhausted":
        raise RuntimeError("dynamic history state QA: round-budget-exhausted")

    verified = 0
    with tempfile.TemporaryDirectory(prefix="aq-history-terminal-") as temporary:
        terminal_root = Path(os.path.realpath(temporary)) / "terminal"
        terminal_root.mkdir()
        copy_snapshot(snapshot, terminal_root)
        manifest_path = terminal_root / validator.HISTORY_MANIFEST_REL
        manifest = json.loads(manifest_path.read_bytes())

        if actual_mode == "advance-allowed":
            next_round = baseline_round + 1
            audit_rel = f"docs/audits/round-{next_round:02d}-audit.md"
            audit_raw = (
                "# PASS_ZERO_ISSUES\n\n"
                "Synthetic terminal-state QA only. No executable issue headings are present.\n"
            ).encode("utf-8")
            (terminal_root / audit_rel).write_bytes(audit_raw)
            audit_sha = hashlib.sha256(audit_raw).hexdigest()
            manifest["entries"].append({"round": next_round, "kind": "audit", "path": audit_rel, "raw_sha256": audit_sha})
            manifest["latest"] = {
                "round": next_round,
                "state": "ZERO_ISSUES",
                "audit": {
                    "path": audit_rel,
                    "raw_sha256": audit_sha,
                    "first_line": "# PASS_ZERO_ISSUES",
                    "verdict": "PASS_ZERO_ISSUES",
                    "issue_ids": [],
                },
                "gate_status": "ZERO_ISSUES_AUDIT_CONFIRMED",
            }
            save_json(manifest_path, manifest)
            core_path = terminal_root / "docs/contracts/core-safety-contract-v1.json"
            core = json.loads(core_path.read_bytes())
            core["current_design_status"] = {
                "status_kind": "ZERO_ISSUES",
                "design_version": core["current_design_status"]["design_version"],
                "revision_round": next_round,
                "latest_audit_path": audit_rel,
                "latest_audit_verdict": "PASS_ZERO_ISSUES",
                "latest_issue_ids": [],
                "gate_status": "ZERO_ISSUES_AUDIT_CONFIRMED",
            }
            save_json(core_path, core)
            update_markers(terminal_root, core["current_design_status"])
            verified += 1

        terminal_manifest = json.loads(manifest_path.read_bytes())
        terminal_round = terminal_manifest["latest"]["round"]
        require(transition_mode(terminal_round, "ZERO_ISSUES") == "terminal-fixed-point", "zero-issue state is not terminal")
        first_digest = validate_state(terminal_root)
        second_digest = validate_state(terminal_root)
        require(first_digest == second_digest, "terminal history validation replay is not deterministic")
        verified += 2

        audit_rel = terminal_manifest["latest"]["audit"]["path"]

        def mutate_manifest(root: Path, edit: Any) -> None:
            path = root / validator.HISTORY_MANIFEST_REL
            document = json.loads(path.read_bytes())
            edit(document)
            save_json(path, document)

        def inject_resolution(root: Path) -> None:
            resolution_rel = f"docs/audits/round-{terminal_round:02d}-resolution.md"
            raw = f"# 第 {terminal_round} 轮非法终态处置\n".encode("utf-8")
            (root / resolution_rel).write_bytes(raw)
            mutate_manifest(root, lambda document: document["entries"].append({
                "round": terminal_round, "kind": "resolution", "path": resolution_rel,
                "raw_sha256": hashlib.sha256(raw).hexdigest(),
            }))

        def nonempty_issue(root: Path) -> None:
            path = root / audit_rel
            raw = path.read_bytes() + f"\n## AQ-R{terminal_round}-001 — synthetic issue\n".encode("utf-8")
            path.write_bytes(raw)
            digest = hashlib.sha256(raw).hexdigest()
            def edit(document: dict[str, Any]) -> None:
                next(row for row in document["entries"] if row["path"] == audit_rel)["raw_sha256"] = digest
                document["latest"]["audit"]["raw_sha256"] = digest
                document["latest"]["audit"]["issue_ids"] = [f"AQ-R{terminal_round}-001"]
            mutate_manifest(root, edit)

        def add_blocker(root: Path) -> None:
            mutate_manifest(root, lambda document: document["latest"].__setitem__("blocker", {
                "issue_id": f"AQ-R{terminal_round}-001", "status": "BLOCKED_USER_DECISION"
            }))

        def fail_first_line(root: Path) -> None:
            path = root / audit_rel
            raw = path.read_bytes().replace(b"# PASS_ZERO_ISSUES", b"# FAIL_WITH_1_ISSUES", 1)
            path.write_bytes(raw)
            digest = hashlib.sha256(raw).hexdigest()
            def edit(document: dict[str, Any]) -> None:
                next(row for row in document["entries"] if row["path"] == audit_rel)["raw_sha256"] = digest
                document["latest"]["audit"].update({"raw_sha256": digest, "first_line": "# FAIL_WITH_1_ISSUES", "verdict": "FAIL_WITH_1_ISSUES"})
            mutate_manifest(root, edit)

        def add_round_21(root: Path) -> None:
            raw = b"# PASS_ZERO_ISSUES\n"
            path = root / "docs/audits/round-21-audit.md"
            path.write_bytes(raw)
            mutate_manifest(root, lambda document: document["entries"].append({
                "round": 21, "kind": "audit", "path": "docs/audits/round-21-audit.md",
                "raw_sha256": hashlib.sha256(raw).hexdigest(),
            }))

        def rollback_latest(root: Path) -> None:
            mutate_manifest(root, lambda document: document["latest"].__setitem__("round", terminal_round - 1))

        def self_reference_attempt(root: Path) -> None:
            digest = hashlib.sha256((root / validator.HISTORY_MANIFEST_REL).read_bytes()).hexdigest()
            mutate_manifest(root, lambda document: document.__setitem__("self_digest", digest))

        def marker_drift(root: Path) -> None:
            path = root / "README.md"
            source = path.read_text(encoding="utf-8")
            path.write_text(source.replace(f'"revision_round":{terminal_round}', f'"revision_round":{terminal_round - 1}', 1), encoding="utf-8")

        invalid_cases = [
            ("inject-resolution", "zero history round must not have a resolution", inject_resolution),
            ("nonempty-issue", "zero history audit must have PASS_ZERO_ISSUES and an empty issue set", nonempty_issue),
            ("blocker", "zero history latest field closure mismatch", add_blocker),
            ("fail-first-line", "zero history audit must have PASS_ZERO_ISSUES and an empty issue set", fail_first_line),
            ("round-21", "history manifest round is outside 1..20", add_round_21),
            ("rollback", "history latest round mismatch", rollback_latest),
            ("self-reference", "history manifest field closure mismatch", self_reference_attempt),
            ("marker-drift", "current design status projection mismatch", marker_drift),
        ]
        for qa_id, expected, mutate in invalid_cases:
            expect_rejected(terminal_root, qa_id, expected, mutate)
            verified += 1

        require(transition_mode(validator.MAX_AUDIT_ROUNDS, "ISSUES_OPEN") == "round-budget-exhausted", "round-20 open state did not exhaust the budget")
        verified += 1
        for relative in ("docs/contracts/validate-contracts-v1.py", "docs/contracts/run-release-gate-v1.py"):
            require((terminal_root / relative).read_bytes() == snapshot[relative], f"dynamic history QA modified tool bytes: {relative}")
    return verified


def verify_mutation_results(
    payload: Any,
    contract: dict[str, Any],
    case_root: Path,
    evidence_root: Path | None = None,
    tooling: dict[str, Any] | None = None,
    base_env: dict[str, str] | None = None,
) -> str:
    required = contract["result_required_fields"]
    require(isinstance(payload, dict) and sorted(payload) == required, "mutation result top-level field closure mismatch")
    require(payload["contract_id"] == contract["contract_id"], "mutation result contract ID mismatch")
    require(payload["case_count"] == contract["case_count"], "mutation result case count mismatch")
    require(payload["source_bytes_unchanged"] is True and payload["status"] == "ok", "mutation result completion status mismatch")
    rows = payload["cases"]
    require(isinstance(rows, list) and len(rows) == contract["case_count"], "mutation result case list is incomplete")
    expected_fields = contract["result_row_required_fields"]
    seen: set[str] = set()
    for expected, actual in zip(contract["cases"], rows):
        require(isinstance(actual, dict) and sorted(actual) == expected_fields, "mutation result row field closure mismatch")
        require(actual["case_id"] not in seen, "duplicate mutation result case ID")
        seen.add(actual["case_id"])
        for field in ("sequence", "case_id", "expected_success", "mutation_sha256"):
            require(actual[field] == expected[field], f"mutation result metadata mismatch: {expected['case_id']}.{field}")
        spec = expected["mutation_spec"]
        require(actual["applied_recipe_sha256"] == expected["mutation_sha256"], f"mutation applied recipe mismatch: {expected['case_id']}")
        require(actual["executor_id"] == spec["executor_id"] and actual["executor_implementation_sha256"] == spec["executor_implementation_sha256"], f"mutation executor evidence mismatch: {expected['case_id']}")
        require(actual["executor_closure_sha256"] == spec["executor_closure_sha256"], f"mutation executor closure evidence mismatch: {expected['case_id']}")
        require(actual["source_input_sha256"] == recipe_path_snapshot(case_root, spec["repo_paths"]), f"mutation source input digest mismatch: {expected['case_id']}")
        require(isinstance(actual["mutated_output_sha256"], str) and re.fullmatch(r"[0-9a-f]{64}", actual["mutated_output_sha256"]) is not None, f"mutation output digest shape mismatch: {expected['case_id']}")
        require((actual["mutated_output_sha256"] == actual["source_input_sha256"]) == (spec["expected_repo_effect"] == "unchanged"), f"mutation output effect mismatch: {expected['case_id']}")
        require(actual["observed_failure_class"] == spec["expected_failure_class"], f"mutation failure class mismatch: {expected['case_id']}")
        require(actual["actual_success"] is expected["expected_success"], f"mutation verdict drift: {expected['case_id']}")
        expected_verdict = "pass" if expected["expected_success"] else "rejected"
        require(actual["verdict"] == expected_verdict, f"mutation verdict label mismatch: {expected['case_id']}")
        if evidence_root is not None:
            require(tooling is not None and base_env is not None, "gate-owned mutation evidence runtime is missing")
            isolated_root = evidence_root / expected["case_id"]
            require(isolated_root.is_dir(), f"isolated mutation evidence root is missing: {expected['case_id']}")
            operation = spec["operation"]
            before_document = locator_state(case_root, spec, contract, "before")
            after_document = locator_state(isolated_root, spec, contract, "after")
            if operation["locator_kind"] in {"runtime", "result-payload"}:
                _assert_typed_state(operation, before_document)
                _assert_typed_state(operation, after_document)
            before_state = hashlib.sha256(MUTATION_LOCATOR_STATE_DOMAIN + canonical(before_document)).hexdigest()
            after_state = hashlib.sha256(MUTATION_LOCATOR_STATE_DOMAIN + canonical(after_document)).hexdigest()
            require(before_state == operation["expected_before_state_sha256"], f"mutation locator before-state mismatch: {expected['case_id']}")
            require(after_state == operation["expected_after_state_sha256"], f"mutation locator after-state mismatch: {expected['case_id']}")
            require(actual["mutated_output_sha256"] == recipe_path_snapshot(isolated_root, spec["repo_paths"]), f"mutation output digest differs from gate-owned isolated root: {expected['case_id']}")
            if expected["case_id"] == "schema-const":
                before_resolved = locator_state(case_root, spec, contract, "before")["resolved"]
                after_resolved = locator_state(isolated_root, spec, contract, "after")["resolved"]
                require(before_resolved == operation["expected_before"] and after_resolved == operation["expected_after"], "schema-const exact JSON pointer transition mismatch")
            gate_success, gate_failure = _gate_owned_case_outcome(expected, contract, isolated_root, case_root, tooling, base_env)
            require(gate_success is expected["expected_success"], f"gate-owned mutation verdict drift: {expected['case_id']}")
            require(gate_failure == spec["expected_failure_class"], f"gate-owned failure class mismatch: {expected['case_id']}")
    require(seen == {row["case_id"] for row in contract["cases"]}, "mutation result case set mismatch")
    projected = dict(payload)
    claimed = projected.pop("results_sha256")
    actual_digest = hashlib.sha256(MUTATION_RESULTS_DOMAIN + canonical(projected)).hexdigest()
    require(isinstance(claimed, str) and hmac.compare_digest(claimed, actual_digest), "mutation result canonical digest mismatch")
    return actual_digest


def root_identity(root_abs: str, reader: Any) -> tuple[dict[str, Any], str]:
    device, inode, mode = reader.root_identity
    document = {"canonical_path": root_abs, "device": device, "inode": inode, "mode": stat.S_IMODE(mode)}
    return document, hashlib.sha256(ROOT_IDENTITY_DOMAIN + canonical(document)).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run fixed-root Agent Quota contract release evidence gate.")
    parser.add_argument("--root", required=True, help="externally selected repository root; cwd must equal this path")
    parser.add_argument("--self-test-preflight", action="store_true")
    parser.add_argument("--self-test-verify-mutation-results", action="store_true")
    args = parser.parse_args()
    reader = None
    try:
        runtime_guard.verify_runtime(require_external_bootstrap=True)
        validator, reader, root_abs = bootstrap(args.root)
        snapshot = complete_snapshot(validator, reader, 2_000_000)
        contracts = validator.load_contract_set(reader)
        ready_fd = os.environ.get("AQ_RELEASE_GATE_TEST_READY_FD")
        if ready_fd is not None:
            require(os.environ.get("AQ_RELEASE_GATE_MUTATION_TEST") == "1", "release gate ready hook is test-only")
            descriptor = int(ready_fd)
            require(3 <= descriptor <= 4, "release gate ready descriptor is outside the reserved pipe range")
            require(os.write(descriptor, b"ready") == 5, "release gate ready signal was incomplete")
            os.close(descriptor)
        tooling = validator.validate_dependency_runtime(contracts)
        mutation_contract = contracts.artifacts["docs/contracts/core-safety-contract-v1.json"].document["validation_mutation_contract"]
        verify_runner_executor_contract(snapshot["docs/contracts/run-validation-mutations-v1.py"], mutation_contract, validator)
        typed_state_self_test_count = verify_typed_state_self_tests(mutation_contract, Path(root_abs))
        retry_after_process_count = verify_retry_after_dual_process_self_test(contracts)

        if args.self_test_preflight or args.self_test_verify_mutation_results:
            require(os.environ.get("AQ_RELEASE_GATE_MUTATION_TEST") == "1", "release gate self-test mode is test-only")
            if args.self_test_verify_mutation_results:
                verify_mutation_results(json.loads(sys.stdin.read()), mutation_contract, Path(root_abs))
            pause_ms = os.environ.get("AQ_RELEASE_GATE_TEST_PAUSE_BEFORE_FINAL_VERIFY_MS")
            if pause_ms is not None:
                pause_value = int(pause_ms)
                require(1 <= pause_value <= 5000, "release gate test pause is out of bounds")
                time.sleep(pause_value / 1000)
            reader.verify_unchanged()
            print("self_test_preflight=accepted")
            print("release_authority=test-only-preflight-not-release-evidence")
            return 0

        reader.verify_unchanged()
        source_digest = framed_digest(INPUT_DOMAIN, snapshot)
        identity_document, identity_digest = root_identity(root_abs, reader)
        with tempfile.TemporaryDirectory(prefix="aq-contract-release-") as temporary:
            empty_home = Path(temporary) / "empty-home"
            empty_cache = Path(temporary) / "empty-npm-cache"
            empty_home.mkdir()
            empty_cache.mkdir()
            tool_dirs = {
                os.path.dirname(tooling["node_path"]),
                os.path.dirname(tooling["npm_path"]),
                os.path.dirname(tooling["pandoc_path"]),
                "/usr/bin",
                "/bin",
            }
            for executable_name in ("node", "npm", "pandoc"):
                launcher = shutil.which(executable_name)
                require(launcher is not None, f"validation launcher disappeared before clean replay: {executable_name}")
                tool_dirs.add(os.path.dirname(launcher))
            clean_env = {
                "PATH": os.pathsep.join(sorted(tool_dirs, key=lambda value: value.encode("utf-8"))),
                "HOME": str(empty_home),
                "LANG": "C",
                "LC_ALL": "C",
                "npm_config_cache": str(empty_cache),
                "npm_config_audit": "false",
                "npm_config_fund": "false",
                "npm_config_ignore_scripts": "true",
                "npm_config_offline": "true",
                "PYTHONHASHSEED": "0",
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONUTF8": "1",
            }
            bootstrap_self_test_count = verify_bootstrap_negative_self_tests(snapshot, clean_env)
            external_self_test_count = verify_external_negative_self_tests(validator, snapshot, clean_env)
            loaded_image_qa_count = verify_loaded_image_collector_self_tests(validator)
            dynamic_history_qa_count = verify_dynamic_history_state_machine(validator, snapshot)
            target = Path(temporary) / "repo"
            target.mkdir()
            copy_snapshot(snapshot, target)
            contracts_dir = target / "docs/contracts"
            run([tooling["npm_path"], "ci", "--ignore-scripts", "--offline", "--no-audit", "--no-fund", "--cache", str(empty_cache)], contracts_dir, timeout=120, env=clean_env)
            validate_command = formal_command("docs/contracts/validate-contracts-v1.py")
            first = run(validate_command, target, timeout=120, env=clean_env)
            second = run(validate_command, target, timeout=120, env=clean_env)
            require(first == second, "two clean validation replays emitted different output")
            projection_command = formal_command("docs/contracts/canonicalize-registry-v1.py")
            first_projection = run(projection_command, target, timeout=120, env=clean_env)
            second_projection = run(projection_command, target, timeout=120, env=clean_env)
            require(first_projection == second_projection, "two clean projection replays emitted different output")
            redirect_env = dict(clean_env)
            redirect_env["AQ_MUTATION_RECIPE_SELF_TEST"] = "1"
            run_expect_failure(
                formal_command("docs/contracts/run-validation-mutations-v1.py", "--root", ".", "--self-test-redirect-executor", "schema-const=artifact-unknown"),
                target,
                timeout=120,
                env=redirect_env,
                expected="mutation_runner_error=executor mapping mismatch:schema-const",
            )
            verify_helper_closure_fail_closed(target, target / "docs/contracts/node_modules", clean_env)
            evidence_root = Path(temporary) / "mutation-evidence"
            evidence_root.mkdir()
            evidence_env = dict(clean_env)
            evidence_env["AQ_RELEASE_GATE_EVIDENCE"] = "1"
            mutation_raw = run(
                formal_command(
                    "docs/contracts/run-validation-mutations-v1.py",
                    "--root",
                    ".",
                    "--evidence-root",
                    str(evidence_root),
                ),
                target,
                timeout=1800,
                env=evidence_env,
            )
            mutation_lines = mutation_raw.splitlines()
            require(
                mutation_lines[:3] == [
                    "local_runtime_checker=preflight-verified",
                    "external_launch_attestation=absent",
                    "launch_authority=local-audit-evidence-only-not-fixed-launch-proof",
                ] and len(mutation_lines) == 4,
                "mutation suite bootstrap evidence/result framing mismatch",
            )
            mutation_result_raw = mutation_lines[3]
            try:
                mutation_payload = json.loads(mutation_result_raw)
            except json.JSONDecodeError as error:
                raise RuntimeError("mutation suite did not emit one canonical JSON result") from error
            require(mutation_result_raw.encode("utf-8") == canonical(mutation_payload), "mutation suite output is not canonical JSON")
            mutation_digest = verify_mutation_results(
                mutation_payload,
                mutation_contract,
                target,
                evidence_root,
                tooling,
                clean_env,
            )

        reader.verify_unchanged()
        require(framed_digest(INPUT_DOMAIN, {path: reader.initial_bytes(path) for path in snapshot}) == source_digest, "release input digest changed")
        print(first)
        print(f"canonical_root_identity={canonical(identity_document).decode('utf-8')}")
        print(f"canonical_root_identity_sha256={identity_digest}")
        print(f"release_input_sha256={source_digest}")
        print(f"mutation_case_count={mutation_contract['case_count']}")
        print(f"mutation_results_sha256={mutation_digest}")
        print("clean_install=verified")
        print("validation_replay_deterministic=true")
        print("projection_replay_deterministic=true")
        print("mutation_suite=exact-contract-match")
        print("mutation_executor_redirect_self_test=verified-rejected")
        print("mutation_helper_closure_self_tests=5-verified-rejected")
        print(f"mutation_typed_state_self_tests={typed_state_self_test_count}-verified")
        print(f"retry_after_virtual_clock_processes={retry_after_process_count}-verified")
        print(f"external_negative_self_tests={external_self_test_count}-verified-rejected")
        print(f"bootstrap_negative_self_tests={bootstrap_self_test_count}-verified-rejected")
        print(f"loaded_image_collector_qa={loaded_image_qa_count}-verified")
        print(f"dynamic_history_state_qa={dynamic_history_qa_count}-verified")
        print("mutation_locator_and_failure_evidence=gate-owned-exactly-recomputed")
        print("release_authority=audit-evidence-only-not-a-release-authority")
        print("source_bytes_unchanged=true")
        print("status=ok")
        return 0
    except (RuntimeError, OSError, ValueError, KeyError, TypeError, json.JSONDecodeError, subprocess.TimeoutExpired) as error:
        print(f"release_gate_error={error}", file=sys.stderr)
        return 1
    finally:
        if reader is not None:
            reader.close()


if __name__ == "__main__":
    raise SystemExit(main())
