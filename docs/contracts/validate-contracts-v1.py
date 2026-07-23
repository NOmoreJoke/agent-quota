#!/usr/bin/env python3
"""Read-only, reproducible gate for the Agent Quota documentation contracts.

This program never repairs, rewrites, or re-pins an input.  It opens a fixed
repository root once, rejects symlinks on every registered path component,
then runs the registry's validation order and semantic validators.
"""

from __future__ import annotations

import argparse
import ast
import base64
import copy
import hashlib
import heapq
import hmac
import json
import os
import posixpath
import re
import shutil
import stat
import subprocess
import sys
import time
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator

import python_runtime_guard_v1 as runtime_guard


ARTIFACT_DOMAIN = b"agent-quota:contract-artifact:v1\x00"
SCHEMA_DOMAIN = b"agent-quota:contract-schema:v1\x00"
REGISTRY_DOMAIN = b"agent-quota:contract-registry:v1\x00"
MUTATION_DOMAIN = b"agent-quota:validation-mutation:v1\x00"
MUTATION_RESULTS_DOMAIN = b"agent-quota:validation-mutation-results:v1\x00"
MUTATION_EXECUTOR_DOMAIN = b"agent-quota:validation-mutation-executor:v1\x00"
MUTATION_EXECUTOR_CLOSURE_DOMAIN = b"agent-quota:validation-mutation-executor-closure:v1\x00"
INT64_MIN = -(2**63)
INT64_MAX = 2**63 - 1
REPO_PATH_RE = re.compile(r"^(?:README\.md|docs(?:/[a-z0-9][a-z0-9_.-]*)+)$")
SEGMENT_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]*$")
DIRECTIVE_RE = re.compile(
    r"^persist:v1:([a-z][a-z0-9_]{0,63}):(create|delete|update|write):"
    r"(RET-[A-Z0-9]+(?:-[A-Z0-9]+)*)$"
)
ANY_DIRECTIVE_RE = re.compile(r"^persist:")

SCRIPT_ABS = os.path.abspath(__file__)
CONTRACTS_ABS = os.path.dirname(SCRIPT_ABS)
ROOT_ABS = os.path.dirname(os.path.dirname(CONTRACTS_ABS))
NODE_HELPER_REL = "docs/contracts/validate-json-schema-v1.mjs"
HISTORY_MANIFEST_REL = "docs/contracts/history-manifest-v1.json"
RUNTIME_BOOTSTRAP_REL = "docs/contracts/runtime-bootstrap-v1.sh"
RUNTIME_GUARD_REL = "docs/contracts/python_runtime_guard_v1.py"
OFFLINE_BUNDLE_PATHS = (
    "docs/contracts/offline-npm-bundle-v1/ajv-8.17.1.tgz",
    "docs/contracts/offline-npm-bundle-v1/fast-deep-equal-3.1.3.tgz",
    "docs/contracts/offline-npm-bundle-v1/fast-uri-3.1.3.tgz",
    "docs/contracts/offline-npm-bundle-v1/json-schema-traverse-1.0.0.tgz",
    "docs/contracts/offline-npm-bundle-v1/require-from-string-2.0.2.tgz",
)
MAX_AUDIT_ROUNDS = 20
HISTORY_PATH_UNIVERSE = tuple(
    [f"docs/audits/round-{round_number:02d}-audit.md" for round_number in range(1, MAX_AUDIT_ROUNDS + 1)]
    + [f"docs/audits/round-{round_number:02d}-resolution.md" for round_number in range(1, MAX_AUDIT_ROUNDS + 1)]
)

ARTIFACT_PATHS = (
    "docs/contracts/core-safety-contract-v1.json",
    "docs/contracts/lease-policy-v1.json",
    "docs/contracts/local-key-purpose-registry-v1.json",
    "docs/contracts/operation-contract-v1.json",
    "docs/contracts/retention-lint-v1.json",
)
SCHEMA_PATHS = (
    "docs/contracts/schemas/contract-registry-v1.schema.json",
    "docs/contracts/schemas/core-safety-contract-v1.schema.json",
    "docs/contracts/schemas/lease-policy-v1.schema.json",
    "docs/contracts/schemas/local-key-purpose-registry-v1.schema.json",
    "docs/contracts/schemas/operation-contract-v1.schema.json",
    "docs/contracts/schemas/retention-lint-v1.schema.json",
)
FIXTURE_PATHS = (
    "docs/contracts/fixtures/core-safety-v1.json",
    "docs/contracts/fixtures/retention-lint-malicious-v1.json",
)
LIVE_DOC_PATHS = (
    "README.md",
    "docs/design-proposal.md",
    "docs/provider-contract.md",
    "docs/security-model.md",
)
NORMATIVE_DECISION_PATHS = (
    "docs/audits/gui-product-decision-resolution.md",
)
REGISTRY_REL = "docs/contracts/contract-registry-v1.json"
CANONICALIZER_REL = "docs/contracts/canonicalize-registry-v1.py"
TOOL_PATHS = (
    CANONICALIZER_REL,
    "docs/contracts/validate-contracts-v1.py",
    "docs/contracts/run-release-gate-v1.py",
    "docs/contracts/run-validation-mutations-v1.py",
    NODE_HELPER_REL,
    "docs/contracts/package.json",
    "docs/contracts/package-lock.json",
    RUNTIME_BOOTSTRAP_REL,
    RUNTIME_GUARD_REL,
)
BASE_ALLOWED_READ_PATHS = frozenset(
    (REGISTRY_REL, HISTORY_MANIFEST_REL) + ARTIFACT_PATHS + SCHEMA_PATHS + FIXTURE_PATHS
    + LIVE_DOC_PATHS + NORMATIVE_DECISION_PATHS + TOOL_PATHS + OFFLINE_BUNDLE_PATHS
)
ALLOWED_READ_PATHS = BASE_ALLOWED_READ_PATHS | frozenset(HISTORY_PATH_UNIVERSE)


class ValidationError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def domain_hash(domain: bytes, value: Any) -> str:
    return sha256(domain + canonical_bytes(value))


def pointer_tokens(pointer: str) -> list[str]:
    if pointer == "":
        return []
    require(pointer.startswith("/"), f"invalid JSON pointer: {pointer}")
    return [token.replace("~1", "/").replace("~0", "~") for token in pointer[1:].split("/")]


def json_pointer(value: Any, pointer: str) -> Any:
    current = value
    for token in pointer_tokens(pointer):
        if isinstance(current, list):
            require(token.isascii() and token.isdigit(), f"non-canonical array pointer token: {pointer}")
            current = current[int(token)]
        else:
            current = current[token]
    return current


def reject_float(_: str) -> Any:
    raise ValidationError("JSON floats and non-finite numbers are forbidden")


def parse_int(text: str) -> int:
    value = int(text)
    require(INT64_MIN <= value <= INT64_MAX, f"JSON integer outside signed int64: {text}")
    return value


def reject_constant(text: str) -> Any:
    raise ValidationError(f"non-finite JSON number is forbidden: {text}")


def duplicate_rejector(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in output, f"duplicate JSON key: {key}")
        output[key] = value
    return output


def count_json(value: Any, depth: int, bounds: dict[str, Any]) -> int:
    require(depth <= bounds["json_depth_max"], "JSON depth bound exceeded")
    if isinstance(value, str):
        require(len(value.encode("utf-8")) <= bounds["string_utf8_bytes_max"], "JSON string byte bound exceeded")
        return 1
    if value is None or isinstance(value, bool) or isinstance(value, int):
        if isinstance(value, int) and not isinstance(value, bool):
            require(bounds["integer_min"] <= value <= bounds["integer_max"], "JSON integer registry bound exceeded")
        return 1
    if isinstance(value, list):
        require(len(value) <= bounds["array_items_max"], "JSON array item bound exceeded")
        return 1 + sum(count_json(item, depth + 1, bounds) for item in value)
    if isinstance(value, dict):
        return 1 + sum(count_json(key, depth + 1, bounds) + count_json(item, depth + 1, bounds) for key, item in value.items())
    raise ValidationError(f"unsupported JSON value type: {type(value).__name__}")


def validate_repo_path(path: str) -> None:
    require(isinstance(path, str), "RepoPath must be a string")
    require(path.isascii(), f"RepoPath must be ASCII: {path!r}")
    require(unicodedata.normalize("NFC", path) == path, f"RepoPath must already be NFC: {path!r}")
    require(REPO_PATH_RE.fullmatch(path) is not None, f"non-canonical RepoPath: {path!r}")
    if path != "README.md":
        for segment in path.split("/"):
            require(SEGMENT_RE.fullmatch(segment) is not None, f"invalid RepoPath segment: {path!r}")
            require(segment not in (".", ".."), f"dot segment forbidden: {path!r}")


def open_absolute_directory_nofollow(path: str) -> int:
    require(os.path.isabs(path), "repository root must be absolute")
    require(os.path.normpath(path) == path, "repository root must be lexically canonical")
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    current_fd = os.open(os.path.sep, flags)
    try:
        for segment in path.split(os.path.sep)[1:]:
            require(segment not in ("", ".", ".."), "repository root contains an invalid segment")
            next_fd = os.open(segment, flags, dir_fd=current_fd)
            os.close(current_fd)
            current_fd = next_fd
            require(stat.S_ISDIR(os.fstat(current_fd).st_mode), "repository root component is not a directory")
        return current_fd
    except Exception:
        os.close(current_fd)
        raise


class RepositoryReader:
    def __init__(self, root_abs: str = ROOT_ABS, required_entry_rel: str | None = None) -> None:
        script_stat = os.lstat(SCRIPT_ABS)
        require(stat.S_ISREG(script_stat.st_mode), "validator must not be invoked through a symlink")
        self.root_abs = root_abs
        self.root_fd = open_absolute_directory_nofollow(root_abs)
        require(stat.S_ISDIR(os.fstat(self.root_fd).st_mode), "repository root is not a directory")
        root_stat = os.fstat(self.root_fd)
        self.root_identity = (root_stat.st_dev, root_stat.st_ino, root_stat.st_mode)
        self.snapshots: dict[str, tuple[bytes, tuple[int, int, int, int, int, int]]] = {}
        if required_entry_rel is not None:
            entry_raw, entry_identity = self._read_once(required_entry_rel, 524288)
            entry_stat = os.lstat(os.path.join(root_abs, required_entry_rel))
            require(self._identity(entry_stat) == entry_identity, "release entry path identity differs from fixed-root entry")
            self.snapshots[required_entry_rel] = (entry_raw, entry_identity)

    def close(self) -> None:
        os.close(self.root_fd)

    @staticmethod
    def _identity(value: os.stat_result) -> tuple[int, int, int, int, int, int]:
        return (value.st_dev, value.st_ino, value.st_mode, value.st_size, value.st_mtime_ns, value.st_ctime_ns)

    def _read_once(self, rel: str, maximum: int) -> tuple[bytes, tuple[int, int, int, int, int, int]]:
        validate_repo_path(rel)
        require(rel in ALLOWED_READ_PATHS, f"path is not in the validator compile-time allowlist: {rel}")
        segments = rel.split("/")
        current_fd = os.dup(self.root_fd)
        try:
            for index, segment in enumerate(segments):
                final = index == len(segments) - 1
                flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
                if not final:
                    flags |= getattr(os, "O_DIRECTORY", 0)
                next_fd = os.open(segment, flags, dir_fd=current_fd)
                os.close(current_fd)
                current_fd = next_fd
                mode = os.fstat(current_fd).st_mode
                require(stat.S_ISREG(mode) if final else stat.S_ISDIR(mode), f"unexpected file type for {rel}")
            before = os.fstat(current_fd)
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = os.read(current_fd, min(65536, maximum + 1 - total))
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
                require(total <= maximum, f"raw byte bound exceeded: {rel}")
            raw = b"".join(chunks)
            after = os.fstat(current_fd)
            require(self._identity(before) == self._identity(after), f"input changed while being read: {rel}")
            require(after.st_size == len(raw), f"input length changed while being read: {rel}")
            return raw, self._identity(after)
        except OSError as error:
            raise ValidationError(f"no-follow open failed for {rel}: {error.strerror}") from error
        finally:
            os.close(current_fd)

    def read_bytes(self, rel: str, maximum: int) -> bytes:
        raw, identity = self._read_once(rel, maximum)
        prior = self.snapshots.get(rel)
        if prior is None:
            self.snapshots[rel] = (raw, identity)
        else:
            require(prior[1] == identity, f"input file identity/stat changed during validation: {rel}")
            require(hmac.compare_digest(prior[0], raw), f"input bytes changed during validation: {rel}")
        return raw

    def initial_bytes(self, rel: str) -> bytes:
        require(rel in self.snapshots, f"input was not loaded into immutable snapshot: {rel}")
        return self.snapshots[rel][0]

    def list_directory_nofollow(self, rel: str) -> list[str]:
        validate_repo_path(rel + "/sentinel")
        current_fd = os.dup(self.root_fd)
        try:
            for segment in rel.split("/"):
                next_fd = os.open(
                    segment,
                    os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
                    dir_fd=current_fd,
                )
                os.close(current_fd)
                current_fd = next_fd
                require(stat.S_ISDIR(os.fstat(current_fd).st_mode), f"bundle component is not a directory: {rel}")
            names = os.listdir(current_fd)
            require(all(isinstance(name, str) and name not in ("", ".", "..") for name in names), f"invalid directory entry: {rel}")
            return sorted(names, key=lambda value: value.encode("utf-8"))
        except OSError as error:
            raise ValidationError(f"no-follow directory open failed for {rel}: {error.strerror}") from error
        finally:
            os.close(current_fd)

    def verify_unchanged(self) -> None:
        for rel in sorted(self.snapshots, key=lambda value: value.encode("utf-8")):
            expected_raw, expected_identity = self.snapshots[rel]
            actual_raw, actual_identity = self._read_once(rel, max(2_000_000, len(expected_raw) + 1))
            require(expected_identity == actual_identity, f"input file identity/stat changed before success: {rel}")
            require(hmac.compare_digest(expected_raw, actual_raw), f"input bytes changed before success: {rel}")


@dataclass(frozen=True)
class LoadedJson:
    path: str
    raw: bytes
    document: dict[str, Any]


def decode_json(path: str, raw: bytes, bounds: dict[str, Any]) -> LoadedJson:
    require(not raw.startswith(b"\xef\xbb\xbf"), f"UTF-8 BOM forbidden: {path}")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValidationError(f"invalid UTF-8 in {path}: {error}") from error
    require(unicodedata.normalize("NFC", text) == text, f"non-NFC JSON text: {path}")
    try:
        document = json.loads(
            text,
            object_pairs_hook=duplicate_rejector,
            parse_int=parse_int,
            parse_float=reject_float,
            parse_constant=reject_constant,
        )
    except (json.JSONDecodeError, ValidationError) as error:
        raise ValidationError(f"strict JSON parse failed for {path}: {error}") from error
    require(isinstance(document, dict), f"JSON document root must be an object: {path}")
    require(count_json(document, 1, bounds) <= bounds["json_nodes_max"], f"JSON node bound exceeded: {path}")
    return LoadedJson(path, raw, document)


def stable_unique(values: Iterable[Any], label: str) -> list[Any]:
    output = list(values)
    encoded = [canonical_bytes(value) for value in output]
    require(len(encoded) == len(set(encoded)), f"duplicate {label}")
    return output


def utf8_sorted(values: Iterable[str], label: str) -> list[str]:
    output = list(values)
    require(output == sorted(output, key=lambda value: value.encode("utf-8")), f"{label} is not UTF-8 byte sorted")
    require(len(output) == len(set(output)), f"duplicate {label}")
    return output


@dataclass
class ContractSet:
    reader: RepositoryReader
    registry: LoadedJson
    schemas: dict[str, LoadedJson]
    artifacts: dict[str, LoadedJson]
    fixtures: dict[str, LoadedJson]
    docs: dict[str, str]
    normative_docs: dict[str, str]
    bounds: dict[str, Any]


def load_contract_set(reader: RepositoryReader) -> ContractSet:
    bootstrap_bounds = {
        "json_depth_max": 64,
        "json_nodes_max": 100000,
        "string_utf8_bytes_max": 16384,
        "array_items_max": 4096,
        "integer_min": INT64_MIN,
        "integer_max": INT64_MAX,
    }
    registry = decode_json(REGISTRY_REL, reader.read_bytes(REGISTRY_REL, 65536), bootstrap_bounds)
    bounds = registry.document["raw_bounds"]
    require(bounds["registry_raw_bytes_max"] == 65536, "registry raw bound bootstrap mismatch")
    require(len(registry.raw) <= bounds["registry_raw_bytes_max"], "registry raw bound exceeded")
    require(bounds["integer_min"] == INT64_MIN and bounds["integer_max"] == INT64_MAX, "signed int64 registry bounds changed")
    require(bounds["floats"] == "reject" and bounds["non_finite_numbers"] == "reject", "numeric reject policy changed")
    require(bounds["duplicate_keys"] == "reject_before_schema", "duplicate-key reject policy changed")

    schemas = {
        path: decode_json(path, reader.read_bytes(path, bounds["schema_raw_bytes_max"]), bounds)
        for path in SCHEMA_PATHS
    }
    artifacts = {
        path: decode_json(path, reader.read_bytes(path, bounds["artifact_raw_bytes_max"]), bounds)
        for path in ARTIFACT_PATHS
    }
    fixtures = {
        path: decode_json(path, reader.read_bytes(path, bounds["artifact_raw_bytes_max"]), bounds)
        for path in FIXTURE_PATHS
    }
    docs: dict[str, str] = {}
    for path in LIVE_DOC_PATHS:
        raw = reader.read_bytes(path, bounds["artifact_raw_bytes_max"])
        try:
            docs[path] = raw.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ValidationError(f"invalid UTF-8 in {path}: {error}") from error
        require(unicodedata.normalize("NFC", docs[path]) == docs[path], f"non-NFC Markdown: {path}")
    normative_docs: dict[str, str] = {}
    for path in NORMATIVE_DECISION_PATHS:
        raw = reader.read_bytes(path, bounds["artifact_raw_bytes_max"])
        try:
            normative_docs[path] = raw.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ValidationError(f"invalid UTF-8 in {path}: {error}") from error
        require(unicodedata.normalize("NFC", normative_docs[path]) == normative_docs[path], f"non-NFC Markdown: {path}")
    return ContractSet(reader, registry, schemas, artifacts, fixtures, docs, normative_docs, bounds)


def validate_registry_paths(contracts: ContractSet) -> None:
    registry = contracts.registry.document
    expected_inputs = tuple(sorted(ARTIFACT_PATHS + FIXTURE_PATHS + SCHEMA_PATHS, key=lambda value: value.encode("utf-8")))
    actual_inputs = tuple(registry["canonicalizer"]["input_paths"])
    require(actual_inputs == expected_inputs, "canonicalizer input_paths must equal the compile-time contract input allowlist")
    require(registry["canonicalizer"]["implementation_path"] == CANONICALIZER_REL, "canonicalizer path mismatch")
    registered_paths = [registry["schema_binding"]["schema_path"]]
    for row in registry["artifacts"]:
        registered_paths.extend((row["artifact_path"], row["schema_path"]))
    registered_paths.extend(row["fixture_path"] for row in registry["fixtures"])
    registered_paths.extend(row["path"] for row in registry["normative_decision_inputs"])
    registered_paths.extend(actual_inputs)
    for path in registered_paths:
        validate_repo_path(path)
        require(path in ALLOWED_READ_PATHS, f"registered path not in compile-time allowlist: {path}")


def validate_hash_pins(contracts: ContractSet) -> None:
    registry = contracts.registry.document
    schema_binding = registry["schema_binding"]
    registry_schema = contracts.schemas[schema_binding["schema_path"]]
    require(sha256(registry_schema.raw) == schema_binding["schema_raw_sha256"], "registry schema raw hash mismatch")
    require(domain_hash(SCHEMA_DOMAIN, registry_schema.document) == schema_binding["schema_canonical_sha256"], "registry schema canonical hash mismatch")

    rows = registry["artifacts"]
    utf8_sorted([row["artifact_id"] for row in rows], "registry artifact IDs")
    require({row["artifact_path"] for row in rows} == set(ARTIFACT_PATHS), "registry artifact path closure mismatch")
    require({row["schema_path"] for row in rows} == set(SCHEMA_PATHS[1:]), "registry artifact schema path closure mismatch")
    for row in rows:
        artifact = contracts.artifacts[row["artifact_path"]]
        schema = contracts.schemas[row["schema_path"]]
        require(artifact.document["artifact_id"] == row["artifact_id"], f"artifact ID mismatch: {row['artifact_id']}")
        require(artifact.document["$schema"] == row["artifact_schema_uri"], f"artifact schema URI mismatch: {row['artifact_id']}")
        require(schema.document["$id"] == row["artifact_schema_uri"], f"schema ID mismatch: {row['artifact_id']}")
        require(schema.document["$schema"] == registry["meta_schema_uri"], f"meta-schema mismatch: {row['schema_path']}")
        require(sha256(artifact.raw) == row["artifact_raw_sha256"], f"artifact raw hash mismatch: {row['artifact_id']}")
        require(domain_hash(ARTIFACT_DOMAIN, artifact.document) == row["artifact_canonical_sha256"], f"artifact canonical hash mismatch: {row['artifact_id']}")
        require(sha256(schema.raw) == row["schema_raw_sha256"], f"schema raw hash mismatch: {row['artifact_id']}")
        require(domain_hash(SCHEMA_DOMAIN, schema.document) == row["schema_canonical_sha256"], f"schema canonical hash mismatch: {row['artifact_id']}")

    fixture_rows = registry["fixtures"]
    utf8_sorted([row["fixture_id"] for row in fixture_rows], "registry fixture IDs")
    require({row["fixture_path"] for row in fixture_rows} == set(FIXTURE_PATHS), "registry fixture path closure mismatch")
    for row in fixture_rows:
        fixture = contracts.fixtures[row["fixture_path"]]
        require(sha256(fixture.raw) == row["raw_sha256"], f"fixture raw hash mismatch: {row['fixture_id']}")
        require(domain_hash(ARTIFACT_DOMAIN, fixture.document) == row["canonical_sha256"], f"fixture canonical hash mismatch: {row['fixture_id']}")
    decision_rows = registry["normative_decision_inputs"]
    require([row["path"] for row in decision_rows] == list(NORMATIVE_DECISION_PATHS), "normative decision input path closure mismatch")
    for row in decision_rows:
        require(sha256(contracts.reader.initial_bytes(row["path"])) == row["raw_sha256"], f"normative decision raw hash mismatch: {row['path']}")


def executable_evidence(command: str, expected_version: str, expected_sha256: str, version_args: list[str]) -> str:
    located = shutil.which(command)
    require(located is not None, f"required validation executable is unavailable: {command}")
    resolved = os.path.realpath(located)
    value = os.lstat(resolved)
    require(stat.S_ISREG(value.st_mode), f"validation executable is not a regular file: {command}")
    with open(resolved, "rb") as handle:
        require(sha256(handle.read()) == expected_sha256, f"validation executable digest mismatch: {command}")
    completed = subprocess.run(
        [resolved] + version_args,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={"PATH": os.environ.get("PATH", "")},
        timeout=10,
        check=False,
    )
    require(completed.returncode == 0, f"validation executable version probe failed: {command}")
    first_line = completed.stdout.splitlines()[0]
    require(first_line == expected_version, f"validation executable version mismatch: {command}: {first_line}")
    return resolved


def _sha_external_regular(path: str) -> str:
    handle = os.open(path, os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0))
    try:
        before = os.fstat(handle)
        require(stat.S_ISREG(before.st_mode), f"external launch tool is not regular: {path}")
        state = hashlib.sha256()
        while True:
            chunk = os.read(handle, 65536)
            if not chunk:
                break
            state.update(chunk)
        require(before == os.fstat(handle), f"external launch tool changed during read: {path}")
        return state.hexdigest()
    finally:
        os.close(handle)


def regular_file_tree_digest(root: str) -> tuple[str, dict[str, tuple[int, int, int, int, int, int]]]:
    require(os.path.isabs(root) and os.path.normpath(root) == root, "tool package root must be canonical absolute")
    digest_state = hashlib.sha256()
    identities: dict[str, tuple[int, int, int, int, int, int]] = {}
    for current, directories, files in os.walk(root, topdown=True, followlinks=False):
        directories.sort(key=lambda value: value.encode("utf-8"))
        files.sort(key=lambda value: value.encode("utf-8"))
        for name in directories:
            path = os.path.join(current, name)
            require(not stat.S_ISLNK(os.lstat(path).st_mode), f"tool package tree contains a symlink directory: {path}")
        for name in files:
            path = os.path.join(current, name)
            value = os.lstat(path)
            require(stat.S_ISREG(value.st_mode), f"tool package tree contains a non-regular file: {path}")
            relative = os.path.relpath(path, root).replace(os.path.sep, "/")
            with open(path, "rb") as handle:
                raw = handle.read()
            after = os.lstat(path)
            identity = RepositoryReader._identity(after)
            require(RepositoryReader._identity(value) == identity and after.st_size == len(raw), f"tool package file changed while read: {relative}")
            identities[relative] = identity
            encoded = relative.encode("utf-8")
            digest_state.update(len(encoded).to_bytes(4, "big"))
            digest_state.update(encoded)
            digest_state.update(stat.S_IMODE(after.st_mode).to_bytes(4, "big"))
            digest_state.update(len(raw).to_bytes(8, "big"))
            digest_state.update(raw)
    require(identities, "tool package tree is empty")
    return digest_state.hexdigest(), identities


def npm_runtime_evidence(runtime: dict[str, Any]) -> tuple[str, str, str]:
    mutation_root = os.environ.get("AQ_VALIDATION_NPM_PACKAGE_ROOT")
    if mutation_root is not None:
        require(os.environ.get("AQ_VALIDATION_MUTATION_TEST") == "1", "npm package-root override is test-only")
        require(os.path.isabs(mutation_root) and os.path.normpath(mutation_root) == mutation_root, "npm package-root override is not canonical absolute")
        require(os.path.realpath(mutation_root) == mutation_root, "npm package-root override contains a symlink")
        package_root = mutation_root
        resolved = os.path.join(package_root, runtime["npm_package_entry"])
    else:
        located = shutil.which("npm")
        require(located is not None, "required validation executable is unavailable: npm")
        resolved = os.path.realpath(located)
        package_root = os.path.dirname(os.path.dirname(resolved))
    value = os.lstat(resolved)
    require(stat.S_ISREG(value.st_mode), "npm launcher is not a regular file")
    with open(resolved, "rb") as handle:
        require(sha256(handle.read()) == runtime["npm_cli_sha256"], "npm launcher digest mismatch")
    entry = os.path.relpath(resolved, package_root).replace(os.path.sep, "/")
    require(entry == runtime["npm_package_entry"], "npm resolved entry differs from pinned package entry")
    tree_before, identities_before = regular_file_tree_digest(package_root)
    require(tree_before == runtime["npm_package_tree_sha256"], "npm implementation package tree digest mismatch")
    completed = subprocess.run(
        [resolved, "--version"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={"PATH": os.environ.get("PATH", "")},
        timeout=10,
        check=False,
    )
    require(completed.returncode == 0, "npm version probe failed")
    require(completed.stdout.splitlines()[0] == runtime["npm_version_exact"], "npm version mismatch")
    tree_after, identities_after = regular_file_tree_digest(package_root)
    require(tree_after == tree_before and identities_after == identities_before, "npm implementation package tree changed during verification")
    return resolved, package_root, tree_before


def _absolute_runtime_file_metadata(path: str) -> os.stat_result:
    require(os.path.isabs(path) and os.path.normpath(path) == path, f"runtime image path is not canonical absolute: {path}")
    current = os.path.sep
    for segment in path.split(os.path.sep)[1:]:
        current = os.path.join(current, segment)
        metadata = os.lstat(current)
        require(not stat.S_ISLNK(metadata.st_mode), f"runtime image path contains a symlink: {current}")
    metadata = os.lstat(path)
    require(stat.S_ISREG(metadata.st_mode) and os.path.realpath(path) == path, f"runtime image is not a resolved regular file: {path}")
    return metadata


def _canonical_loaded_image_path(path: str) -> tuple[str, bool]:
    """Apply the shared exact-build system/non-system image classifier."""
    require(os.path.isabs(path) and os.path.normpath(path) == path, f"loaded image path is not canonical absolute: {path}")
    resolved = os.path.realpath(path)
    require(os.path.isabs(resolved) and os.path.normpath(resolved) == resolved, f"loaded image path cannot canonicalize: {path}")
    is_system = resolved.startswith("/System/") or resolved.startswith("/usr/lib/")
    if is_system:
        return resolved, True
    _absolute_runtime_file_metadata(resolved)
    require(resolved == path, f"non-system loaded image path is not canonical: {path}")
    return resolved, False


def _parse_vmmap_file_backed_images(raw: str) -> list[str]:
    """Extract every Mach-O file-backed image from vmmap's fixed segment rows.

    Discovery deliberately has no registry or installation-prefix input.  The
    `__SEGMENT ... SM=... /absolute/path` shape identifies image mappings; all
    classification and fail-closed path checks happen afterwards.
    """
    images: set[str] = set()
    segment_row = re.compile(
        r"^__[A-Za-z0-9_]+\s+[0-9a-fA-F]+-[0-9a-fA-F]+\s+\[[^\]]+\]\s+\S+/\S+\s+SM=[A-Z]+(?:\s+\S+)?\s{2,}(/.*)$"
    )
    mapped_row = re.compile(
        r"^mapped file\s+[0-9a-fA-F]+-[0-9a-fA-F]+\s+\[[^\]]+\]\s+\S+/\S+\s+SM=[A-Z]+(?:\s+\S+)?\s{2,}(/.*)$"
    )
    for line in raw.splitlines():
        match = segment_row.match(line) or mapped_row.match(line)
        if match is None:
            continue
        path = match.group(1).rstrip()
        require(path and "\x00" not in path and "*" not in path, "vmmap loaded-image path is malformed")
        images.add(path)
    require(images, "vmmap did not expose any file-backed loaded image")
    return sorted(images, key=lambda value: value.encode("utf-8"))


def _is_macho_regular_file(path: str) -> bool:
    handle = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0))
    try:
        before = os.fstat(handle)
        require(stat.S_ISREG(before.st_mode), f"loaded image candidate is not a regular file: {path}")
        magic = os.read(handle, 4)
        after = os.fstat(handle)
        require(
            (before.st_dev, before.st_ino, before.st_mode, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
            == (after.st_dev, after.st_ino, after.st_mode, after.st_size, after.st_mtime_ns, after.st_ctime_ns),
            f"loaded image candidate changed while classified: {path}",
        )
        return magic in {
            b"\xfe\xed\xfa\xce", b"\xce\xfa\xed\xfe", b"\xfe\xed\xfa\xcf", b"\xcf\xfa\xed\xfe",
            b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca", b"\xca\xfe\xba\xbf", b"\xbf\xba\xfe\xca",
        }
    finally:
        os.close(handle)


def _non_system_images_from_vmmap(raw: str) -> list[str]:
    observed: set[str] = set()
    for path in _parse_vmmap_file_backed_images(raw):
        resolved, is_system = _canonical_loaded_image_path(path)
        if not is_system and _is_macho_regular_file(resolved):
            observed.add(resolved)
    return sorted(observed, key=lambda value: value.encode("utf-8"))


def _require_exact_observed_image_closure(runtime_id: str, observed: list[str], registered: list[str]) -> None:
    unknown = set(observed) - set(registered)
    missing = set(registered) - set(observed)
    require(not unknown, f"unregistered non-system loaded image: {sorted(unknown)[0] if unknown else runtime_id}")
    require(not missing, f"required non-system loaded image missing: {sorted(missing)[0] if missing else runtime_id}")


def _otool_non_system_dependencies(path: str) -> list[str]:
    completed = subprocess.run(
        ["/usr/bin/otool", "-L", path], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env={"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"}, timeout=30, check=False,
    )
    require(completed.returncode == 0, f"otool dependency probe failed: {path}")
    dependencies: set[str] = set()
    for line in completed.stdout.splitlines()[1:]:
        candidate = line.strip().split(" (", 1)[0]
        if not candidate.startswith("/"):
            continue
        resolved = os.path.realpath(candidate)
        if resolved.startswith("/System/") or resolved.startswith("/usr/lib/") or resolved == path:
            continue
        dependencies.add(resolved)
    return sorted(dependencies, key=lambda value: value.encode("utf-8"))


def _probe_process_non_system_images(command: list[str]) -> list[str]:
    process = subprocess.Popen(
        command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        env={"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"},
    )
    try:
        time.sleep(0.1)
        require(process.poll() is None, f"loaded-image probe exited before observation: {command[0]}")
        completed = subprocess.run(
            ["/usr/bin/vmmap", str(process.pid)], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env={"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"}, timeout=30, check=False,
        )
        require(completed.returncode == 0, f"loaded-image vmmap probe failed: {command[0]}")
        return _non_system_images_from_vmmap(completed.stdout)
    finally:
        if process.stdin is not None:
            process.stdin.close()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.terminate()
            process.wait(timeout=10)


def validate_dependency_runtime(contracts: ContractSet) -> dict[str, Any]:
    package_loaded = decode_json(
        "docs/contracts/package.json",
        contracts.reader.read_bytes("docs/contracts/package.json", contracts.bounds["artifact_raw_bytes_max"]),
        contracts.bounds,
    )
    lock_loaded = decode_json(
        "docs/contracts/package-lock.json",
        contracts.reader.read_bytes("docs/contracts/package-lock.json", contracts.bounds["artifact_raw_bytes_max"]),
        contracts.bounds,
    )
    package = package_loaded.document
    lock = lock_loaded.document
    require(set(package) == {"name", "version", "private", "description", "scripts", "dependencies", "aqValidationRuntime"}, "package manifest field closure mismatch")
    require(package["name"] == "agent-quota-contract-validation" and package["version"] == "1.0.0" and package["private"] is True, "package manifest identity mismatch")
    require(package["name"] == lock["name"] and package["version"] == lock["version"], "package/lock identity mismatch")
    require(lock["lockfileVersion"] == 3 and lock["requires"] is True, "package lock format mismatch")
    require(lock["packages"][""]["name"] == package["name"] and lock["packages"][""]["version"] == package["version"], "package/lock root mismatch")
    expected_dependencies = {
        "ajv": "file:offline-npm-bundle-v1/ajv-8.17.1.tgz",
        "fast-deep-equal": "file:offline-npm-bundle-v1/fast-deep-equal-3.1.3.tgz",
        "fast-uri": "file:offline-npm-bundle-v1/fast-uri-3.1.3.tgz",
        "json-schema-traverse": "file:offline-npm-bundle-v1/json-schema-traverse-1.0.0.tgz",
        "require-from-string": "file:offline-npm-bundle-v1/require-from-string-2.0.2.tgz",
    }
    require(package["dependencies"] == expected_dependencies, "manifest dependencies must be the exact local offline bundle")
    require(lock["packages"][""]["dependencies"] == package["dependencies"], "manifest/lock dependency parity mismatch")
    expected_scripts = {
        "validate": "cd ../.. && /bin/sh docs/contracts/runtime-bootstrap-v1.sh docs/contracts/run-release-gate-v1.py --root .",
        "validate:contracts": "cd ../.. && /bin/sh docs/contracts/runtime-bootstrap-v1.sh docs/contracts/validate-contracts-v1.py",
        "verify-projections": "cd ../.. && /bin/sh docs/contracts/runtime-bootstrap-v1.sh docs/contracts/canonicalize-registry-v1.py",
        "test:mutations": "cd ../.. && /bin/sh docs/contracts/runtime-bootstrap-v1.sh docs/contracts/run-validation-mutations-v1.py --root .",
        "release-gate": "cd ../.. && /bin/sh docs/contracts/runtime-bootstrap-v1.sh docs/contracts/run-release-gate-v1.py --root .",
    }
    require(package["scripts"] == expected_scripts, "validation script closure mismatch")
    runtime = package["aqValidationRuntime"]
    require(set(runtime) == {
        "authority", "launch_proof_policy", "launch_evidence_semantics", "bootstrap_entry", "bootstrap_raw_sha256",
        "runtime_guard_raw_sha256", "launch_entry_raw_sha256", "shell_trust_boundary", "shell_external_trust_roots",
        "shell_resolved_executable", "shell_binary_sha256",
        "python_implementation", "python_version_exact", "python_abi", "python_platform", "python_resolved_executable", "python_binary_sha256",
        "python_framework_binary", "python_framework_sha256", "python_stdlib_root", "python_stdlib_tree_count", "python_stdlib_tree_sha256",
        "os", "os_release", "os_build", "architecture", "system_image_policy", "entry_allowlist", "opt_link_bindings",
        "non_system_image_closures", "non_system_images", "node_version_exact", "node_binary_sha256", "npm_version_exact", "npm_cli_sha256",
        "npm_package_entry", "npm_package_tree_sha256", "pandoc_version_exact", "pandoc_binary_sha256", "ajv_version_exact",
        "offline_bundle", "package_tree_sha256",
    }, "runtime profile field closure mismatch")
    require(runtime["authority"] == "audit-evidence-only-not-a-release-authority", "runtime profile overstates release authority")
    require(runtime["launch_proof_policy"] == "local-checker-never-proves-launch-repository-external-existing-trust-root-attestation-required", "local checker launch-proof boundary is overstated")
    require(runtime["launch_evidence_semantics"] == "local-opened-fd-integrity-evidence-never-authentication-or-fixed-launch-proof", "local integrity evidence is misclassified as authentication")
    require(runtime["bootstrap_entry"] == RUNTIME_BOOTSTRAP_REL, "runtime bootstrap entry mismatch")
    require(sha256(contracts.reader.read_bytes(RUNTIME_BOOTSTRAP_REL, 131072)) == runtime["bootstrap_raw_sha256"], "runtime bootstrap raw digest mismatch")
    require(sha256(contracts.reader.read_bytes(RUNTIME_GUARD_REL, 524288)) == runtime["runtime_guard_raw_sha256"], "runtime guard raw digest mismatch")
    require(runtime_guard.__file__ == RUNTIME_GUARD_REL, "runtime guard was not loaded from the inherited exact descriptor")
    expected_entries = sorted((CANONICALIZER_REL, "docs/contracts/run-release-gate-v1.py", "docs/contracts/run-validation-mutations-v1.py", "docs/contracts/validate-contracts-v1.py"), key=lambda value: value.encode("utf-8"))
    require(runtime["entry_allowlist"] == expected_entries, "runtime entry allowlist is not the exact closed tool set")
    expected_launch_entries = {path: sha256(contracts.reader.read_bytes(path, 2_000_000)) for path in expected_entries}
    require(runtime["launch_entry_raw_sha256"] == expected_launch_entries, "launch entry raw-pin allowlist mismatch")
    require(runtime["shell_trust_boundary"] == "darwin-kernel-process-image-plus-fixed-bin-sh-ps-shasum-awk-initial-root", "shell trust boundary is not explicit")
    require(runtime["shell_resolved_executable"] == "/bin/sh", "shell executable path mismatch")
    expected_shell_tools = {
        "/bin/ps": "472992c470606d28f577590decfecd7f4a20f832fd92c671bebc6d44790b5d02",
        "/bin/pwd": "ff2c9704307a064566ae9835ff0becf3a765481580c0abe28c8654e2a3045639",
        "/bin/rm": "0e7aa0987cecc8d8ca629e1c61857321e8e281a6c1d0711b21163a15e454dc9d",
        "/bin/sh": "ad5c194b05f83bc5e793c1cd67b148a4b680467b5a5730ab1a31fe4e6460ee9f",
        "/bin/sleep": "a2be9ba33f4fbf10a4f2702cd9b687ac98274ad28de509109ee86f2f4b0e2beb",
        "/usr/bin/awk": "3693175058d0be720f941a8e9c645756f7d38848f3457abd938d8e27ba35f8ab",
        "/usr/bin/env": "6e506aec3c0cff703ac1e66cedc6f1945354ad41339a38db4425c7c88227128f",
        "/usr/bin/find": "cbab4ddd20b57c5090196f79b1c969e8a17fc48b4bb8e4a18765d0bbc714481e",
        "/usr/bin/grep": "569588bf23c56895f046b63b029285217e442d46bec1b18498b58fefb50d8f1f",
        "/usr/bin/mktemp": "7bb3299fdb41f16ea5d9f7748cb5cb654b93208e0a1d1d78360145dcbbfb21fe",
        "/usr/bin/otool": "179301dcb41ea78accc3fa0048a7e6f6710d891945a751a34addd622020c1818",
        "/usr/bin/readlink": "934656def5cfb8e85b2e4d983bb59ba97479cec49b63b4ea2fa42d067c569242",
        "/usr/bin/shasum": "0812595f981a26f813d98dc380af14d4af427626c9339eda29eb849ae13de1e3",
        "/usr/bin/sort": "e595f29543691f7355d16035f71992512c6a23804f9447b73e6d484b7887d731",
        "/usr/bin/stat": "934656def5cfb8e85b2e4d983bb59ba97479cec49b63b4ea2fa42d067c569242",
        "/usr/bin/sw_vers": "f4704a35bc196e6dd101a7de40f9e9ce51dd17bdba7ef29ce465a00d123f2ec5",
        "/usr/bin/tr": "1ddc659c4c983056863cad854384c35d78d004dd2c53cc63ea3b3b380e76233a",
        "/usr/bin/uname": "c189136263d277786f29a16eb3137de7bcf4512d2282d0036f440022f325bfc4",
        "/usr/bin/wc": "48afbe8af0942865f6ee7b5bfface7d9f3ec2b6ab71e81deb3ae47b8644b804f",
    }
    require(runtime["shell_external_trust_roots"] == expected_shell_tools, "shell external trust-root closure mismatch")
    require(all(_sha_external_regular(path) == digest for path, digest in expected_shell_tools.items()), "shell external trust-root digest mismatch")
    shell_stat = os.lstat("/bin/sh")
    require(stat.S_ISREG(shell_stat.st_mode), "external shell trust root is not a regular file")
    with open("/bin/sh", "rb") as handle:
        require(sha256(handle.read()) == runtime["shell_binary_sha256"], "external shell trust-root digest mismatch")
    secondary = runtime_guard.verify_runtime(require_external_bootstrap=True)
    require(secondary["external_launch_attestation"] == "absent" and secondary["launch_authority"] == "local-audit-evidence-only-not-fixed-launch-proof", "local runtime guard falsely claims launch authority")
    require(runtime["python_implementation"] == secondary["implementation"], "Python implementation profile mismatch")
    require(runtime["python_version_exact"] == secondary["version"], "Python exact version profile mismatch")
    require(runtime["python_abi"] == secondary["abi"], "Python ABI profile mismatch")
    require(runtime["python_platform"] == secondary["platform"], "Python platform profile mismatch")
    require(runtime["python_resolved_executable"] == secondary["resolved_executable"], "Python resolved executable profile mismatch")
    require(runtime["python_binary_sha256"] == runtime_guard.EXPECTED["executable_sha256"], "Python binary profile mismatch")
    require(runtime["python_framework_binary"] == runtime_guard.EXPECTED["framework_binary"] and runtime["python_framework_sha256"] == runtime_guard.EXPECTED["framework_sha256"], "Python dependency implementation profile mismatch")
    require(runtime["python_stdlib_root"] == runtime_guard.EXPECTED["stdlib_root"], "Python stdlib root profile mismatch")
    require(runtime["python_stdlib_tree_count"] == secondary["stdlib_tree_count"] and runtime["python_stdlib_tree_sha256"] == secondary["stdlib_tree_sha256"], "Python stdlib implementation tree profile mismatch")
    require((runtime["os"], runtime["os_release"], runtime["architecture"]) == (secondary["system"], secondary["system_release"], secondary["machine"]), "Python OS/architecture profile mismatch")
    os_build = subprocess.run(["/usr/bin/sw_vers", "-buildVersion"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env={"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"}, timeout=10, check=False)
    require(os_build.returncode == 0 and os_build.stdout.strip() == runtime["os_build"] == runtime_guard.EXPECTED["os_build"], "Darwin OS build trust boundary mismatch")
    require(runtime["system_image_policy"] == "absolute-System-or-usr-lib-images-covered-by-exact-Darwin-build-all-other-loaded-images-individually-pinned", "system/non-system loaded-image policy mismatch")
    expected_opt_links = {
        "/opt/homebrew/opt/gmp": "../Cellar/gmp/6.3.0",
        "/opt/homebrew/opt/openssl@3": "../Cellar/openssl@3/3.6.2",
        "/opt/homebrew/opt/xz": "../Cellar/xz/5.8.3",
    }
    require({row["path"]: row["target"] for row in runtime["opt_link_bindings"]} == expected_opt_links, "runtime opt-link binding set mismatch")
    for path, target in expected_opt_links.items():
        require(stat.S_ISLNK(os.lstat(path).st_mode) and os.readlink(path) == target, f"runtime opt-link target drift: {path}")
    image_rows = runtime["non_system_images"]
    require(isinstance(image_rows, list) and [row["path"] for row in image_rows] == sorted((row["path"] for row in image_rows), key=lambda value: value.encode("utf-8")), "non-system image rows are not exact/sorted")
    require(len({row["path"] for row in image_rows}) == len(image_rows), "duplicate non-system image row")
    image_by_path = {row["path"]: row for row in image_rows}
    for row in image_rows:
        require(set(row) == {"path", "kind", "owner_uid", "owner_gid", "mode", "size", "raw_sha256", "dependencies"}, f"non-system image row field closure mismatch: {row.get('path')}")
        metadata = _absolute_runtime_file_metadata(row["path"])
        require(row["kind"] == "regular", f"non-system image kind mismatch: {row['path']}")
        require((metadata.st_uid, metadata.st_gid, f"{stat.S_IMODE(metadata.st_mode):04o}", metadata.st_size) == (row["owner_uid"], row["owner_gid"], row["mode"], row["size"]), f"non-system image metadata mismatch: {row['path']}")
        require(runtime_guard._sha(Path(row["path"])) == row["raw_sha256"], f"non-system image raw digest mismatch: {row['path']}")
        require(row["dependencies"] == _otool_non_system_dependencies(row["path"]), f"non-system image dependency edge mismatch: {row['path']}")
    closures = runtime["non_system_image_closures"]
    require(set(closures) == {"python", "pandoc", "node"}, "native loaded-image closure ID mismatch")
    for closure_id, paths in closures.items():
        require(paths == sorted(paths, key=lambda value: value.encode("utf-8")) and len(paths) == len(set(paths)), f"native loaded-image closure is not sorted/unique: {closure_id}")
        require(set(paths).issubset(image_by_path), f"native loaded-image closure has an unregistered row: {closure_id}")
        require(all(set(image_by_path[path]["dependencies"]).issubset(paths) for path in paths), f"native loaded-image closure is not recursively closed: {closure_id}")
    guard_images = runtime_guard.EXPECTED_NON_SYSTEM_IMAGES
    require(set(guard_images) == set(closures["python"]), "Python guard/profile loaded-image closure mismatch")
    require(all(image_by_path[path]["raw_sha256"] == digest for path, digest in guard_images.items()), "Python guard/profile loaded-image digest mismatch")
    require(set(secondary["loaded_non_system_images"]).issubset(closures["python"]), "actual Python loaded-image set escapes the registered closure")
    bundle_rows = runtime["offline_bundle"]
    require([row["package"] for row in bundle_rows] == sorted(expected_dependencies, key=lambda value: value.encode("utf-8")), "offline bundle rows are not exact/sorted")
    require({row["path"] for row in bundle_rows} == set(OFFLINE_BUNDLE_PATHS), "offline bundle path closure mismatch")
    require(contracts.reader.list_directory_nofollow("docs/contracts/offline-npm-bundle-v1") == [path.rsplit("/", 1)[1] for path in OFFLINE_BUNDLE_PATHS], "offline bundle directory has a missing or extra entry")
    for row in bundle_rows:
        require(set(row) == {"package", "version", "path", "raw_sha256"}, f"offline bundle row closure mismatch: {row.get('package')}")
        require(row["path"] == f"docs/contracts/{expected_dependencies[row['package']][5:]}", f"offline bundle package/path mismatch: {row['package']}")
        require(sha256(contracts.reader.read_bytes(row["path"], 2_000_000)) == row["raw_sha256"], f"offline bundle tarball digest mismatch: {row['package']}")
    expected_packages = runtime["package_tree_sha256"]
    require(list(expected_packages) == sorted(expected_packages, key=lambda value: value.encode("utf-8")), "runtime dependency tree IDs are not UTF-8 sorted")
    require(set(lock["packages"]) == {""} | {f"node_modules/{name}" for name in expected_packages}, "lock dependency closure differs from runtime profile")
    require(lock["packages"]["node_modules/ajv"]["version"] == runtime["ajv_version_exact"] == "8.17.1", "AJV lock/runtime version mismatch")
    for name in expected_packages:
        row = lock["packages"][f"node_modules/{name}"]
        require(re.fullmatch(r"sha512-[A-Za-z0-9+/=]+", row["integrity"]) is not None, f"lock integrity missing/invalid: {name}")
        require(row["resolved"] == expected_dependencies[name], f"lock must resolve only to the fixed offline bundle: {name}")
    node_path = executable_evidence("node", runtime["node_version_exact"], runtime["node_binary_sha256"], ["--version"])
    npm_path, npm_package_root, npm_package_tree_sha256 = npm_runtime_evidence(runtime)
    pandoc_path = executable_evidence("pandoc", f"pandoc {runtime['pandoc_version_exact']}", runtime["pandoc_binary_sha256"], ["--version"])
    for runtime_id, observed in (
        ("pandoc", _probe_process_non_system_images([pandoc_path, "-f", "markdown", "-t", "json"])),
        ("node", _probe_process_non_system_images([node_path, "-e", "process.stdin.resume()"])),
    ):
        _require_exact_observed_image_closure(runtime_id, observed, closures[runtime_id])
    return {"package": package, "lock": lock, "runtime": runtime, "node_path": node_path, "npm_path": npm_path, "npm_package_root": npm_package_root, "npm_package_tree_sha256": npm_package_tree_sha256, "pandoc_path": pandoc_path}


def run_ajv(contracts: ContractSet, tooling: dict[str, Any]) -> dict[str, Any]:
    schema_rows = [{"path": item.path, "document": item.document} for item in contracts.schemas.values()]
    instances = [{
        "path": contracts.registry.path,
        "schema_uri": contracts.registry.document["schema_binding"]["schema_uri"],
        "document": contracts.registry.document,
    }]
    for row in contracts.registry.document["artifacts"]:
        instances.append({"path": row["artifact_path"], "schema_uri": row["artifact_schema_uri"], "document": contracts.artifacts[row["artifact_path"]].document})
    for row in contracts.registry.document["fixtures"]:
        instances.append({"path": row["fixture_path"], "schema_uri": row["schema_uri"], "document": contracts.fixtures[row["fixture_path"]].document})
    helper_source = contracts.reader.read_bytes(NODE_HELPER_REL, contracts.bounds["artifact_raw_bytes_max"])
    try:
        helper_program = helper_source.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValidationError(f"invalid UTF-8 in {NODE_HELPER_REL}: {error}") from error
    payload = {
        "schemas": schema_rows,
        "instances": instances,
        "local_key_artifact": contracts.artifacts["docs/contracts/local-key-purpose-registry-v1.json"].document,
        "expected_package_names": list(tooling["runtime"]["package_tree_sha256"]),
    }
    completed = subprocess.run(
        [tooling["node_path"], "--input-type=module", "--eval", helper_program],
        input=json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=CONTRACTS_ABS,
        env={"PATH": os.environ.get("PATH", "")},
        timeout=30,
        check=False,
    )
    require(completed.returncode == 0, f"Draft 2020-12 AJV gate failed: {completed.stderr.strip()}")
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise ValidationError("AJV helper emitted invalid JSON") from error
    require({key: result[key] for key in ("meta_validated", "instances_validated", "golden_crypto")} == {"meta_validated": 6, "instances_validated": 8, "golden_crypto": "ok"}, "AJV helper result mismatch")
    runtime = result["runtime"]
    require(runtime["node_version"] == tooling["runtime"]["node_version_exact"], "AJV helper Node version mismatch")
    require(runtime["node_exec_path"] == tooling["node_path"], "AJV helper Node executable path mismatch")
    require(runtime["node_binary_sha256"] == tooling["runtime"]["node_binary_sha256"], "AJV helper Node executable digest mismatch")
    require(runtime["ajv_version"] == tooling["runtime"]["ajv_version_exact"], "loaded AJV version mismatch")
    expected_node_modules = os.path.realpath(os.path.join(CONTRACTS_ABS, "node_modules"))
    require(runtime["node_modules_root"] == expected_node_modules, "AJV resolved outside the fixed dependency root")
    require(runtime["ajv_package_path"] == os.path.join(expected_node_modules, "ajv", "package.json"), "AJV package resolution path mismatch")
    require(runtime["ajv_entry_path"] == os.path.join(expected_node_modules, "ajv", "dist", "2020.js"), "AJV implementation resolution path mismatch")
    require(runtime["package_tree_sha256"] == tooling["runtime"]["package_tree_sha256"], "installed dependency implementation digest mismatch")
    expected_versions = {name: tooling["lock"]["packages"][f"node_modules/{name}"]["version"] for name in tooling["runtime"]["package_tree_sha256"]}
    require(runtime["package_versions"] == expected_versions, "installed dependency version differs from lock closure")
    return result


def iter_schema_objects(value: Any, pointer: str = "") -> Iterator[tuple[str, dict[str, Any]]]:
    if isinstance(value, dict):
        yield pointer, value
        for key, child in value.items():
            token = key.replace("~", "~0").replace("/", "~1")
            yield from iter_schema_objects(child, pointer + "/" + token)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from iter_schema_objects(child, pointer + "/" + str(index))


def order_key(item: Any, pointers: list[str], label: str) -> tuple[bytes, ...]:
    projected = [json_pointer(item, pointer) for pointer in pointers]
    encoded: list[bytes] = []
    for value in projected:
        if isinstance(value, str):
            encoded.append(b"s" + value.encode("utf-8"))
        elif isinstance(value, int) and not isinstance(value, bool):
            require(INT64_MIN <= value <= INT64_MAX, f"utf8_key integer outside signed int64: {label}")
            encoded.append(b"i" + (value - INT64_MIN).to_bytes(8, "big"))
        else:
            raise ValidationError(f"utf8_key projection must contain strings or signed integers: {label}")
    return tuple(encoded)


def validate_array_value(items: list[Any], policy: str, key_pointers: list[str], label: str) -> None:
    if policy == "utf8_key":
        keys = [order_key(item, key_pointers, label) for item in items]
        require(keys == sorted(keys), f"utf8_key array is not byte sorted: {label}")
        require(len(keys) == len(set(keys)), f"utf8_key array has duplicate keys: {label}")
    else:
        require(policy == "sequence_exact", f"unknown array-order policy at {label}")


def split_ref(reference: str, current_root: dict[str, Any], schema_by_uri: dict[str, dict[str, Any]]) -> tuple[dict[str, Any], str]:
    if reference.startswith("#"):
        return current_root, reference[1:]
    if "#" in reference:
        uri, fragment = reference.split("#", 1)
        require(uri in schema_by_uri, f"external schema reference is not locally registered: {reference}")
        return schema_by_uri[uri], fragment
    require(reference in schema_by_uri, f"external schema reference is not locally registered: {reference}")
    return schema_by_uri[reference], ""


def schema_type_matches(schema: dict[str, Any], instance: Any) -> bool:
    expected = schema.get("type")
    if expected is None:
        return True
    options = [expected] if isinstance(expected, str) else expected
    actual = (
        "null" if instance is None else
        "boolean" if isinstance(instance, bool) else
        "integer" if isinstance(instance, int) else
        "array" if isinstance(instance, list) else
        "object" if isinstance(instance, dict) else
        "string" if isinstance(instance, str) else "unknown"
    )
    return actual in options or (actual == "integer" and "number" in options)


def walk_instance_arrays(
    instance: Any,
    schema: dict[str, Any],
    schema_root: dict[str, Any],
    schema_pointer: str,
    schema_by_uri: dict[str, dict[str, Any]],
    policies_by_uri: dict[str, tuple[str, dict[str, tuple[str, list[str]]]]],
    instance_pointer: str = "",
    seen: set[tuple[int, int, str]] | None = None,
) -> None:
    if seen is None:
        seen = set()
    identity = (id(instance), id(schema_root), schema_pointer)
    if identity in seen:
        return
    seen.add(identity)
    if "$ref" in schema:
        target_root, target_pointer = split_ref(schema["$ref"], schema_root, schema_by_uri)
        target = json_pointer(target_root, target_pointer)
        walk_instance_arrays(instance, target, target_root, target_pointer, schema_by_uri, policies_by_uri, instance_pointer, seen)
        return
    if not schema_type_matches(schema, instance):
        return
    root_uri = schema_root["$id"]
    if isinstance(instance, list) and schema.get("type") == "array":
        default, overrides = policies_by_uri[root_uri]
        policy, keys = overrides.get(schema_pointer, (default, []))
        validate_array_value(instance, policy, keys, f"{root_uri}{schema_pointer} -> {instance_pointer or '/'}")
        if "prefixItems" in schema:
            for index, child_schema in enumerate(schema["prefixItems"]):
                if index < len(instance):
                    walk_instance_arrays(instance[index], child_schema, schema_root, schema_pointer + f"/prefixItems/{index}", schema_by_uri, policies_by_uri, instance_pointer + f"/{index}", seen)
        if isinstance(schema.get("items"), dict):
            for index, item in enumerate(instance):
                walk_instance_arrays(item, schema["items"], schema_root, schema_pointer + "/items", schema_by_uri, policies_by_uri, instance_pointer + f"/{index}", seen)
    elif isinstance(instance, dict):
        properties = schema.get("properties", {})
        for key, value in instance.items():
            if key in properties:
                token = key.replace("~", "~0").replace("/", "~1")
                walk_instance_arrays(value, properties[key], schema_root, schema_pointer + "/properties/" + token, schema_by_uri, policies_by_uri, instance_pointer + "/" + token, seen)
            elif isinstance(schema.get("additionalProperties"), dict):
                walk_instance_arrays(value, schema["additionalProperties"], schema_root, schema_pointer + "/additionalProperties", schema_by_uri, policies_by_uri, instance_pointer + "/" + key, seen)
    for branch_name in ("allOf", "anyOf", "oneOf"):
        for index, branch in enumerate(schema.get(branch_name, [])):
            if schema_type_matches(branch, instance):
                walk_instance_arrays(instance, branch, schema_root, schema_pointer + f"/{branch_name}/{index}", schema_by_uri, policies_by_uri, instance_pointer, seen)


def validate_array_order(contracts: ContractSet) -> int:
    registry_schema_uri = contracts.schemas[SCHEMA_PATHS[0]].document["$id"]
    metadata_uri = registry_schema_uri + "#/$defs/arrayOrderMetadata"
    registry_dialect = contracts.registry.document["array_order_dialect"]
    require(registry_dialect == {
        "dialect": "aq-array-order-v1",
        "version": 1,
        "meta_schema_uri": metadata_uri,
        "default_policy": "sequence_exact",
        "override_policy": "utf8_key",
    }, "registry array-order dialect mismatch")
    schema_by_uri = {loaded.document["$id"]: loaded.document for loaded in contracts.schemas.values()}
    policies: dict[str, tuple[str, dict[str, tuple[str, list[str]]]]] = {}
    array_count = 0
    for loaded in contracts.schemas.values():
        schema = loaded.document
        metadata = schema.get("x-aq-array-order")
        require(isinstance(metadata, dict), f"missing x-aq-array-order: {loaded.path}")
        require(metadata["$schema"] == metadata_uri and metadata["dialect"] == "aq-array-order-v1" and metadata["version"] == 1, f"array-order metadata mismatch: {loaded.path}")
        require(metadata["default"] == "sequence_exact", f"array-order default mismatch: {loaded.path}")
        overrides = metadata["overrides"]
        utf8_sorted([row["schema_pointer"] for row in overrides], f"array-order overrides in {loaded.path}")
        override_map: dict[str, tuple[str, list[str]]] = {}
        for row in overrides:
            pointer = row["schema_pointer"]
            require(pointer not in override_map, f"duplicate array-order override: {loaded.path}{pointer}")
            target = json_pointer(schema, pointer)
            require(isinstance(target, dict) and target.get("type") == "array", f"dangling/non-array order override: {loaded.path}{pointer}")
            require(row["policy"] == "utf8_key", f"unknown array-order policy: {loaded.path}{pointer}")
            stable_unique(row["key_json_pointers"], f"array-order key pointer in {loaded.path}{pointer}")
            override_map[pointer] = (row["policy"], row["key_json_pointers"])
        schema_arrays = [pointer for pointer, item in iter_schema_objects(schema) if item.get("type") == "array"]
        array_count += len(schema_arrays)
        require(set(override_map).issubset(set(schema_arrays)), f"array-order override coverage mismatch: {loaded.path}")
        policies[schema["$id"]] = (metadata["default"], override_map)

    require(array_count == 134, f"schema array policy count must be 134, got {array_count}")
    registry_schema = contracts.schemas[SCHEMA_PATHS[0]].document
    walk_instance_arrays(contracts.registry.document, registry_schema, registry_schema, "", schema_by_uri, policies)
    artifact_rows = {row["artifact_path"]: row for row in contracts.registry.document["artifacts"]}
    for path, loaded in contracts.artifacts.items():
        row = artifact_rows[path]
        schema = schema_by_uri[row["artifact_schema_uri"]]
        walk_instance_arrays(loaded.document, schema, schema, "", schema_by_uri, policies)
    for row in contracts.registry.document["fixtures"]:
        schema_root, fragment = split_ref(row["schema_uri"], registry_schema, schema_by_uri)
        schema = json_pointer(schema_root, fragment)
        walk_instance_arrays(contracts.fixtures[row["fixture_path"]].document, schema, schema_root, fragment, schema_by_uri, policies)
    return array_count


def validate_renderer_command_contract_document(contract: dict[str, Any]) -> None:
    command_ids = [
        "bootstrap_state", "accounts_read", "quota_overview", "refresh_scope",
        "config_validate_apply", "credential_dialog_open", "destructive_confirmation_open",
        "reauthenticate", "export_redacted", "scheduler_state",
    ]
    host_reconstructs = ["local_actor", "requested_operation", "account_scope"]
    forbidden = [
        "path", "url", "header", "sql", "credential_ref", "provider_selector",
        "secret_value", "secret_length", "secret_buffer", "plan_digest", "nonce",
        "user_presence_token",
    ]
    shapes = {
        "bootstrap_state": ([], ["application_state", "safe_error", "status"], "redacted-no-secret-material", "none", "read-only"),
        "accounts_read": (["scope_ref"], ["accounts", "safe_error", "status"], "redacted-no-secret-material", "none", "read-only"),
        "quota_overview": (["scope_ref"], ["projection", "safe_error", "status"], "redacted-no-secret-material", "none", "read-only"),
        "refresh_scope": (["scope_ref"], ["refresh_state", "safe_error", "status"], "redacted-no-secret-material", "none", "application-service-after-host-reconstruction"),
        "config_validate_apply": (["config_change_set"], ["classification", "safe_error", "status"], "redacted-no-secret-material", "core-classified-nondestructive-only", "direct-commit-only-after-core-nondestructive-classification"),
        "credential_dialog_open": (["dialog_purpose"], ["opaque_reference_status", "safe_error", "status"], "trusted-host-dialog-request-no-secret-payload", "none", "host-owned-native-dialog-only"),
        "destructive_confirmation_open": (["operation_intent", "opaque_selection_handle"], ["safe_error", "status"], "redacted-no-secret-material", "trusted-surface-only-no-renderer-commit", "host-owned-confirmation-core-commit-only"),
        "reauthenticate": (["principal_ref"], ["reauth_state", "safe_error", "status"], "redacted-no-secret-material", "none", "application-service-after-host-reconstruction"),
        "export_redacted": (["export_profile", "scope_ref"], ["export_status", "safe_error", "status"], "redacted-no-secret-material", "none", "read-only-redacted-export"),
        "scheduler_state": ([], ["safe_error", "scheduler_state", "status"], "redacted-no-secret-material", "none", "read-only"),
    }
    require(set(contract) == {
        "schema", "command_order_policy", "command_ids", "host_reconstruction_fields",
        "forbidden_renderer_fields", "unknown_field_policy", "dto_schema_policy", "dto_schemas", "commands",
    }, "renderer command contract field closure mismatch")
    require(contract["schema"] == "aq-renderer-command-contract-v1", "renderer command contract identity mismatch")
    require(contract["command_order_policy"] == "exact-sequence-no-missing-unknown-duplicate-or-reorder", "renderer command ordering policy mismatch")
    require(contract["command_ids"] == command_ids, "renderer command allowlist/order mismatch")
    require(contract["host_reconstruction_fields"] == host_reconstructs, "renderer host reconstruction field closure mismatch")
    require(contract["forbidden_renderer_fields"] == forbidden, "renderer forbidden field closure mismatch")
    require(contract["unknown_field_policy"] == "reject-before-application-service", "renderer unknown field policy mismatch")
    require(contract["dto_schema_policy"] == "all-command-and-nested-refs-resolve-once-in-this-closed-table-no-free-object-or-unbounded-string", "renderer DTO schema policy mismatch")
    expected_dto_refs = [
        *(f"aq-renderer-dto://v1/{command_id.replace('_', '-')}-{direction}" for command_id in command_ids for direction in ("request", "response")),
        "aq-renderer-dto://v1/shared-account-summary",
        "aq-renderer-dto://v1/shared-application-state",
        "aq-renderer-dto://v1/shared-capability-row",
        "aq-renderer-dto://v1/shared-nondestructive-config-change",
        "aq-renderer-dto://v1/shared-nondestructive-config-change-set",
        "aq-renderer-dto://v1/shared-quota-projection",
        "aq-renderer-dto://v1/shared-refresh-state",
        "aq-renderer-dto://v1/shared-safe-error",
        "aq-renderer-dto://v1/shared-scheduler-state",
    ]
    dto_schemas = contract["dto_schemas"]
    require([row.get("schema_ref") for row in dto_schemas] == expected_dto_refs, "renderer DTO schema set/order mismatch")
    dto_by_ref = {row["schema_ref"]: row for row in dto_schemas}
    require(len(dto_by_ref) == len(dto_schemas), "duplicate renderer DTO schema ref")
    for schema_row in dto_schemas:
        require(set(schema_row) == {"schema_ref", "role", "additional_properties", "fields"}, f"renderer DTO schema field closure mismatch: {schema_row.get('schema_ref')}")
        require(schema_row["additional_properties"] is False, f"renderer DTO schema is not closed: {schema_row['schema_ref']}")
        expected_role = "shared" if "/shared-" in schema_row["schema_ref"] else ("request" if schema_row["schema_ref"].endswith("-request") else "response")
        require(schema_row["role"] == expected_role, f"renderer DTO schema role mismatch: {schema_row['schema_ref']}")
        field_names = [field.get("name") for field in schema_row["fields"]]
        require(len(field_names) == len(set(field_names)), f"duplicate renderer DTO field: {schema_row['schema_ref']}")
        for field in schema_row["fields"]:
            require(field["name"] not in forbidden, f"renderer DTO contains a forbidden field: {schema_row['schema_ref']}.{field['name']}")
            require(field["redaction"] in {"renderer-safe-redacted", "opaque-local-ref"}, f"renderer DTO redaction class mismatch: {schema_row['schema_ref']}.{field['name']}")
            if field["type"] == "string":
                require(1 <= field["max_utf8_bytes"] <= 1024 and len(field["allowed_values"]) == len(set(field["allowed_values"])), f"renderer string DTO bounds mismatch: {schema_row['schema_ref']}.{field['name']}")
            elif field["type"] == "integer":
                require(field["minimum"] <= field["maximum"], f"renderer integer DTO bounds mismatch: {schema_row['schema_ref']}.{field['name']}")
            elif field["type"] == "array":
                require(1 <= field["max_items"] <= 4096 and field["ref"] in dto_by_ref and dto_by_ref[field["ref"]]["role"] == "shared", f"renderer array DTO ref/bounds mismatch: {schema_row['schema_ref']}.{field['name']}")
            elif field["type"] == "object":
                require(field["ref"] in dto_by_ref and dto_by_ref[field["ref"]]["role"] == "shared", f"renderer object DTO ref mismatch: {schema_row['schema_ref']}.{field['name']}")
            else:
                require(field["type"] == "boolean", f"renderer DTO field type mismatch: {schema_row['schema_ref']}.{field['name']}")
    commands = contract["commands"]
    require(len(commands) == 10 and [row.get("command_id") for row in commands] == command_ids, "renderer command rows are missing, unknown, duplicate, or reordered")
    request_refs: list[str] = []
    response_refs: list[str] = []
    for row in commands:
        require(set(row) == {"command_id", "request_schema_ref", "request_fields", "response_schema_ref", "response_fields", "host_reconstructs", "secret_class", "destructive_class", "commit_policy"}, f"renderer command row field closure mismatch: {row.get('command_id')}")
        command_id = row["command_id"]
        expected = shapes[command_id]
        slug = command_id.replace("_", "-")
        require(row["request_schema_ref"] == f"aq-renderer-dto://v1/{slug}-request", f"renderer request DTO ref mismatch: {command_id}")
        require(row["response_schema_ref"] == f"aq-renderer-dto://v1/{slug}-response", f"renderer response DTO ref mismatch: {command_id}")
        require(row["request_fields"] == expected[0] and row["response_fields"] == expected[1], f"renderer DTO shape mismatch: {command_id}")
        require([field["name"] for field in dto_by_ref[row["request_schema_ref"]]["fields"]] == row["request_fields"], f"renderer request DTO projection mismatch: {command_id}")
        require([field["name"] for field in dto_by_ref[row["response_schema_ref"]]["fields"]] == row["response_fields"], f"renderer response DTO projection mismatch: {command_id}")
        require(row["host_reconstructs"] == host_reconstructs, f"renderer host reconstruction mismatch: {command_id}")
        require((row["secret_class"], row["destructive_class"], row["commit_policy"]) == expected[2:], f"renderer secret/destructive classification mismatch: {command_id}")
        require(not (set(row["request_fields"]) | set(row["response_fields"])) & set(forbidden), f"renderer sensitive field injection: {command_id}")
        request_refs.append(row["request_schema_ref"])
        response_refs.append(row["response_schema_ref"])
    require(len(set(request_refs)) == len(request_refs) and len(set(response_refs)) == len(response_refs), "renderer DTO refs are not unique")


def validate_sidecar_budget_contract_document(contract: dict[str, Any]) -> None:
    expected = {
        "schema": "aq-sidecar-remaining-budget-v1",
        "wire_budget_field": "remaining_budget_ns",
        "forbidden_wire_fields": ["deadline_monotonic_ns"],
        "minimum_remaining_budget_ns": 1,
        "maximum_remaining_budget_ns": 9000000000,
        "host_hard_cap_ns": 9000000000,
        "sidecar_receipt_sample": "sample-sidecar-monotonic-after-complete-legal-frame-validation",
        "sidecar_rebase": "checked-add-receipt-monotonic-now-plus-remaining-budget-ns",
        "effective_limit": "host-original-hard-cap-and-sidecar-local-rebased-deadline-both-enforced-no-cross-process-clock-comparison",
        "transport_delay_rule": "naturally-consumed-by-host-original-hard-cap-never-restored-by-sidecar-rebase",
        "expiry_boundary": "now-greater-than-or-equal-to-local-deadline-is-expired",
        "overflow_policy": "reject-frame-terminate-session-zero-writes-zero-provider-io",
        "pre_dispatch_rejection_effects": "invalid-out-of-range-expired-or-overflow-frame-is-rejected-before-application-service-with-writes-zero-provider-io-zero",
        "timeout_supervision": "host-timeout-term-then-after-500000000ns-kill-then-reap",
        "dispatched_timeout_effects": "outcome-unknown-no-automatic-replay-orphans-zero-existing-idempotency-and-transaction-recovery-decide-write-state",
        "session_rule": "every-launch-restart-and-u64-overflow-session-gets-new-budget-no-carry-or-reuse",
    }
    require(contract == expected, "sidecar remaining-budget contract mismatch")


def validate_core_closure(contracts: ContractSet) -> None:
    core = contracts.artifacts["docs/contracts/core-safety-contract-v1.json"].document
    desktop = core["desktop_product_contract"]
    validate_renderer_command_contract_document(desktop["renderer_command_contract"])
    validate_sidecar_budget_contract_document(desktop["sidecar_budget_contract"])
    roots = core["codex_schema_bundle"]["descriptor_roots"]
    require([row["path"] for row in roots] == ["codex_app_server_protocol.v2.schemas.json", "v1/InitializeResponse.json"], "Codex descriptor root set mismatch")
    root_paths = {row["path"] for row in roots}
    require({row["root_path"] for row in core["codex_schema_bundle"]["wire_schema_references"]} == root_paths, "Codex wire reference/root closure mismatch")
    bootstrap = core["identity_bootstrap"]
    plan = bootstrap["request_plan_contract"]
    require(set(plan["required_fields"]).isdisjoint(plan["forbidden_fields"]), "request plan required/forbidden overlap")
    require("reservation_receipt" in plan["forbidden_fields"], "request plans must forbid reservation receipts")
    for name in ("identity_and_fetch_context", "identity_and_discovery_context"):
        require("reservation_receipt" in bootstrap[name]["required_fields"], f"final context missing receipt: {name}")
    for name in ("identity_and_fetch_response", "identity_and_discovery_response"):
        response = bootstrap[name]
        require(response["reservation_cardinality"] == response["response_cardinality"] == response["provider_read_cardinality"] == "exactly_one", f"joint response cardinality mismatch: {name}")
        require(response["acceptance_order"][-1] == "atomic_accept", f"joint response acceptance must end atomically: {name}")
    policies = core["budget_policies"]
    policy_ids = utf8_sorted([row["policy_id"] for row in policies], "core budget policy IDs")
    groups = core["endpoint_budget_groups"]
    group_ids = utf8_sorted([row["group_id"] for row in groups], "core endpoint budget group IDs")
    for row in groups:
        require(row["budget_policy_id"] in policy_ids, f"dangling budget policy: {row['group_id']}")
        utf8_sorted(row["endpoint_ids"], f"endpoint IDs in {row['group_id']}")
    for row in core["profile_budget_bindings"]:
        require(row["endpoint_budget_group_id"] in group_ids, f"dangling profile budget group: {row['profile_id']}")
    retry_contract = core["budget_ledger_contract"]["retry_after_aggregation"]
    require(retry_contract["contract_id"] == "aq-rate-retry-after-aggregation-v1", "retry-after aggregation contract identity mismatch")
    require(retry_contract["transaction_mode"] == "BEGIN_IMMEDIATE" and retry_contract["clock_sample"] == "one_db_utc_seconds_sample_per_reservation_transaction", "retry-after transaction/clock sample mismatch")
    require(retry_contract["scope"] == "endpoint_budget_group_and_verified_cohort_union", "retry-after scope is not the group/cohort union")
    require(retry_contract["boundary_sources"] == ["blocked_until", "floor", "hour", "reservation"], "retry-after boundary source closure mismatch")
    require(retry_contract["active_predicate"] == "now_utc_seconds_lt_boundary_utc_seconds" and retry_contract["expired_predicate"] == "now_utc_seconds_gte_boundary_utc_seconds", "retry-after active boundary predicate mismatch")
    require(retry_contract["aggregation"] == "clamp_max_active_boundary_minus_now" and retry_contract["hard_max_seconds"] == 86400, "retry-after maximum aggregation mismatch")
    require(retry_contract["no_active_result"] == "retry_after_seconds_null_and_reserve_allowed" and retry_contract["active_result"] == "deferred_without_reservation_row", "retry-after disposition mismatch")
    require(retry_contract["determinism"] == "independent_of_input_order_primary_reason_process_scheduling", "retry-after determinism contract mismatch")
    vectors = retry_contract["test_vectors"]
    utf8_sorted([row["vector_id"] for row in vectors], "retry-after vector IDs")
    for vector in vectors:
        retry_after, disposition = aggregate_retry_after(vector["now_utc_seconds"], vector["boundaries"], retry_contract)
        require((retry_after, disposition) == (vector["expected_retry_after_seconds"], vector["expected_disposition"]), f"retry-after vector mismatch: {vector['vector_id']}")
        reversed_retry, reversed_disposition = aggregate_retry_after(vector["now_utc_seconds"], list(reversed(vector["boundaries"])), retry_contract)
        require((reversed_retry, reversed_disposition) == (retry_after, disposition), f"retry-after input order changed result: {vector['vector_id']}")
    clock = retry_contract["dual_process_virtual_clock"]
    clock_boundaries = [
        {"scope": "group", "reason": "floor", "boundary_utc_seconds": boundary}
        for boundary in clock["active_boundaries_utc_seconds"]
    ]
    first_retry = aggregate_retry_after(clock["first_retry_utc_seconds"], clock_boundaries, retry_contract)
    all_clear = aggregate_retry_after(clock["all_clear_utc_seconds"], clock_boundaries, retry_contract)
    require(first_retry[1] == clock["first_retry_disposition"] and first_retry[0] == 50, "dual-process first retry must remain deferred until the maximum boundary")
    require(all_clear == (None, clock["all_clear_disposition"]) and clock["process_order_invariant"] is True, "dual-process all-clear boundary mismatch")
    migration = core["migration_graph"]
    require(set(migration["execution_dependency_kinds"]).isdisjoint(migration["forbidden_dependency_kinds"]), "migration allowed/forbidden dependency overlap")
    require(migration["delete_rule"] == "child_delete_to_parent_delete_only", "migration delete direction mismatch")
    require(migration["cascade_parent_action_id"] == "forbidden", "cascade must not create execution order")
    repository = core["repository_path_contract"]
    require(repository["symlink_verdict"] == "reject" and "openat_each_segment_o_nofollow" in repository["loader_steps"], "core repository no-follow contract mismatch")
    probe = core["probe_result_contract"]
    require(probe["schema"] == "aq-probe-result-contract-v1" and probe["discriminator"] == "kind", "ProbeResult contract identity mismatch")
    branches = probe["branches"]
    require([row["kind"] for row in branches] == ["failure", "http_success", "official_cli_success", "offline_result"], "ProbeResult branch set/order mismatch")
    require(next(row for row in branches if row["kind"] == "official_cli_success")["identity_evidence_cardinality"] == "exactly_one", "official CLI success must carry exactly one evidence object")
    require(all(row["identity_evidence_cardinality"] == "forbidden" for row in branches if row["kind"] != "official_cli_success"), "non-official ProbeResult branch permits evidence")
    require(probe["acceptance_order"][-1] == "identity_derive", "ProbeResult validation must complete before identity derivation")
    require(probe["adapter_forbidden_fields"] == ["access_identity", "assurance", "cache_identity", "rate_limit_cohort"], "ProbeResult derived identity field ban mismatch")
    mutation_contract = core["validation_mutation_contract"]
    mutation_cases = mutation_contract["cases"]
    require(mutation_contract["case_count"] == len(mutation_cases), "mutation contract count mismatch")
    require([row["sequence"] for row in mutation_cases] == list(range(1, len(mutation_cases) + 1)), "mutation case sequence is not contiguous and exact")
    require(len({row["case_id"] for row in mutation_cases}) == len(mutation_cases), "duplicate mutation case ID")
    require(all(row["mutation_spec"]["kind"] == row["case_id"] for row in mutation_cases), "mutation case identity/spec mismatch")
    for row in mutation_cases:
        require(domain_hash(MUTATION_DOMAIN, row["mutation_spec"]) == row["mutation_sha256"], f"mutation identity digest mismatch: {row['case_id']}")
        spec = row["mutation_spec"]
        require(spec["recipe_version"] == 1 and spec["executor_id"], f"mutation recipe identity is incomplete: {row['case_id']}")
        require(spec["expected_failure_class"] == ("none" if row["expected_success"] else spec["expected_failure_class"]), f"successful mutation has a failure class: {row['case_id']}")
        require((not row["expected_success"]) or spec["expected_failure_class"] == "none", f"successful mutation has non-none failure class: {row['case_id']}")
        for repo_path in spec["repo_paths"]:
            validate_repo_path(repo_path)
        operation = spec["operation"]
        validate_repo_path(operation["target_repo_path"])
        require(operation["target_repo_path"] in spec["repo_paths"], f"mutation locator target is outside repo_paths: {row['case_id']}")
        require(operation["operation_id"] == row["case_id"], f"mutation operation ID mismatch: {row['case_id']}")
        require(
            (operation["locator_kind"] in {"runtime", "result-payload"}) == ("evidence_descriptor" in operation),
            f"mutation locator discriminator closure mismatch: {row['case_id']}",
        )
        typed = operation["locator_kind"] in {"runtime", "result-payload"}
        require(typed == all(field in operation for field in ("state_serializer", "observation_command", "state_required_fields")), f"mutation typed-state field closure mismatch: {row['case_id']}")
        if typed:
            expected_serializer = "aq-gate-owned-runtime-state-v1" if operation["locator_kind"] == "runtime" else "aq-gate-owned-result-payload-state-v1"
            expected_fields = (
                ["binary_sha256", "case_id", "dependency_binary_sha256", "implementation_tree_sha256", "observation_command", "observed_entity", "phase", "resolved_executable", "serializer"]
                if operation["locator_kind"] == "runtime"
                else ["case_id", "case_ids_in_order", "payload", "phase", "serializer"]
            )
            require(operation["state_serializer"] == expected_serializer and operation["state_required_fields"] == expected_fields, f"mutation typed-state serializer contract mismatch: {row['case_id']}")
            require(operation["observation_command"] and all(isinstance(item, str) and item for item in operation["observation_command"]), f"mutation observation command missing: {row['case_id']}")
            require(operation["expected_before_state_sha256"] != operation["expected_after_state_sha256"], f"typed mutation before/after state must differ: {row['case_id']}")
        require(
            all(re.fullmatch(r"[0-9a-f]{64}", operation[field]) is not None for field in ("expected_before_state_sha256", "expected_after_state_sha256")),
            f"mutation locator exact state digest mismatch: {row['case_id']}",
        )
    schema_const = next(row for row in mutation_cases if row["case_id"] == "schema-const")["mutation_spec"]["operation"]
    require(
        schema_const["target_repo_path"] == "docs/contracts/schemas/core-safety-contract-v1.schema.json"
        and schema_const["locator_kind"] == "json-pointer"
        and schema_const["locator"] == "/properties/artifact_id/const"
        and schema_const["expected_before"] == "core-safety-contract-v1"
        and schema_const["expected_after"] == "wrong-artifact-id",
        "schema-const exact JSON pointer transition contract drifted",
    )
    require(mutation_contract["result_required_fields"] == ["case_count", "cases", "contract_id", "results_sha256", "source_bytes_unchanged", "status"], "mutation result field closure mismatch")
    require(mutation_contract["result_row_required_fields"] == ["actual_success", "applied_recipe_sha256", "case_id", "executor_closure_sha256", "executor_id", "executor_implementation_sha256", "expected_success", "mutated_output_sha256", "mutation_sha256", "observed_failure_class", "sequence", "source_input_sha256", "verdict"], "mutation result row field closure mismatch")
    validate_mutation_executor_contract(contracts, mutation_contract)
    fixture_row = core["fixture_artifacts"][0]
    fixture = contracts.fixtures[fixture_row["path"]].document
    require(domain_hash(ARTIFACT_DOMAIN, fixture) == fixture_row["canonical_sha256"], "core fixture reference mismatch")


def _runner_call_target(node: ast.AST) -> str | None:
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
        return "method-expression:" + ast.dump(node, annotate_fields=True, include_attributes=False)
    return None


def _runner_closure_document(raw: str) -> dict[str, Any]:
    tree = ast.parse(raw)
    lines = raw.splitlines()
    function_nodes = {
        node.name: node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    imports: set[str] = set()
    mutator_targets: set[str] = set()
    executor_ids: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            imports.update(alias.asname or alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.update(alias.asname or alias.name for alias in node.names)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id in {"MUTATORS", "EXECUTOR_BY_CASE"}:
            require(isinstance(node.value, ast.Dict), f"mutation runner {node.target.id} must be a literal dict")
            for value_node in node.value.values:
                if node.target.id == "MUTATORS":
                    require(isinstance(value_node, ast.Name) and value_node.id in function_nodes, "MUTATORS contains an unresolved callable")
                    mutator_targets.add(value_node.id)
                else:
                    require(isinstance(value_node, ast.Constant) and isinstance(value_node.value, str), "EXECUTOR_BY_CASE contains a nonliteral executor")
                    executor_ids.add(value_node.value)
    builtin_names = set(dir(__builtins__)) if not isinstance(__builtins__, dict) else set(__builtins__)
    source_digests: dict[str, str] = {}
    local_edges: dict[str, set[str]] = {name: set() for name in function_nodes}
    external_targets: dict[str, set[str]] = {name: set() for name in function_nodes}
    for name, node in function_nodes.items():
        segment = "\n".join(lines[node.lineno - 1:node.end_lineno]).encode("utf-8")
        source_digests[name] = sha256(MUTATION_EXECUTOR_DOMAIN + segment)
        nested_names = {
            candidate.name for candidate in ast.walk(node)
            if isinstance(candidate, (ast.FunctionDef, ast.AsyncFunctionDef)) and candidate is not node
        }
        for call in (candidate for candidate in ast.walk(node) if isinstance(candidate, ast.Call)):
            if isinstance(call.func, ast.Subscript):
                require(isinstance(call.func.value, ast.Name) and call.func.value.id == "MUTATORS", f"unresolved dynamic callable in {name}")
                local_edges[name].update(mutator_targets)
                external_targets[name].add("literal-dispatch:MUTATORS")
                continue
            target = _runner_call_target(call.func)
            require(target is not None, f"unresolved dynamic callable in {name}")
            if target in function_nodes:
                local_edges[name].add(target)
            elif target in nested_names:
                external_targets[name].add(f"nested-source-contained:{name}.{target}")
            elif target.startswith("method-expression:") or target.split(".", 1)[0] in imports or target.split(".", 1)[0] in builtin_names or "." in target:
                external_targets[name].add(target)
            else:
                raise ValidationError(f"unknown call target in {name}: {target}")
    closures = []
    mandatory_roots = {"main", "execute_case", "recipe_path_snapshot", "observed_failure_class", "result_sha256"}
    for executor_id in sorted(executor_ids, key=lambda value: value.encode("utf-8")):
        roots = mandatory_roots | {executor_id}
        require(roots.issubset(function_nodes), f"executor closure has an unknown root: {executor_id}")
        members: set[str] = set()
        pending = list(roots)
        while pending:
            current = pending.pop()
            if current in members:
                continue
            members.add(current)
            pending.extend(local_edges[current] - members)
        member_ids = sorted(members, key=lambda value: value.encode("utf-8"))
        digest_payload = {
            "executor_id": executor_id,
            "root_function_ids": sorted(roots, key=lambda value: value.encode("utf-8")),
            "member_source_digests": [
                {"function_id": member, "source_sha256": source_digests[member]}
                for member in member_ids
            ],
            "local_call_edges": [
                {"caller": caller, "callee": callee}
                for caller in member_ids
                for callee in sorted(local_edges[caller] & members, key=lambda value: value.encode("utf-8"))
            ],
            "external_call_targets": [
                {"caller": caller, "target": target}
                for caller in member_ids
                for target in sorted(external_targets[caller], key=lambda value: value.encode("utf-8"))
            ],
        }
        closures.append({
            "executor_id": executor_id,
            "root_function_ids": digest_payload["root_function_ids"],
            "member_function_ids": member_ids,
            "closure_sha256": sha256(MUTATION_EXECUTOR_CLOSURE_DOMAIN + canonical_bytes(digest_payload)),
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
    document["closure_sha256"] = sha256(MUTATION_EXECUTOR_CLOSURE_DOMAIN + canonical_bytes(document))
    return document


def validate_mutation_executor_contract(contracts: ContractSet, mutation_contract: dict[str, Any]) -> None:
    mutation_cases = mutation_contract["cases"]
    raw = contracts.reader.read_bytes("docs/contracts/run-validation-mutations-v1.py", contracts.bounds["artifact_raw_bytes_max"]).decode("utf-8")
    tree = ast.parse(raw)
    lines = raw.splitlines()
    function_digests: dict[str, str] = {}
    mappings: dict[str, dict[str, str]] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            segment = "\n".join(lines[node.lineno - 1:node.end_lineno]).encode("utf-8")
            function_digests[node.name] = sha256(MUTATION_EXECUTOR_DOMAIN + segment)
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id in {"MUTATORS", "EXECUTOR_BY_CASE"}:
            require(isinstance(node.value, ast.Dict), f"mutation runner {node.target.id} must be a literal dict")
            parsed: dict[str, str] = {}
            for key_node, value_node in zip(node.value.keys, node.value.values):
                require(isinstance(key_node, ast.Constant) and isinstance(key_node.value, str), f"mutation runner {node.target.id} key is not a string literal")
                if node.target.id == "MUTATORS":
                    require(isinstance(value_node, ast.Name), "MUTATORS value must be a direct function name")
                    parsed[key_node.value] = value_node.id
                else:
                    require(isinstance(value_node, ast.Constant) and isinstance(value_node.value, str), "EXECUTOR_BY_CASE value must be a string literal")
                    parsed[key_node.value] = value_node.value
            mappings[node.target.id] = parsed
    require(set(mappings) == {"MUTATORS", "EXECUTOR_BY_CASE"}, "mutation runner executor maps are missing")
    expected = {row["case_id"]: row["mutation_spec"]["executor_id"] for row in mutation_cases}
    require(mappings["EXECUTOR_BY_CASE"] == expected, "mutation runner explicit executor map differs from machine contract")
    require(all(expected[case_id] == executor_id for case_id, executor_id in mappings["MUTATORS"].items()), "mutation runner mutator dispatch differs from machine contract")
    actual_closure = _runner_closure_document(raw)
    require(actual_closure == mutation_contract["runner_implementation_closure"], "mutation runner transitive implementation closure mismatch")
    closure_by_executor = {row["executor_id"]: row["closure_sha256"] for row in actual_closure["executor_closures"]}
    for row in mutation_cases:
        spec = row["mutation_spec"]
        require(function_digests.get(spec["executor_id"]) == spec["executor_implementation_sha256"], f"mutation executor implementation digest mismatch: {row['case_id']}")
        require(closure_by_executor.get(spec["executor_id"]) == spec["executor_closure_sha256"], f"mutation executor closure digest mismatch: {row['case_id']}")


def parse_edge(text: str) -> tuple[str, str, str]:
    match = re.fullmatch(r"([^>:]+)>([^:]+):([a-z_]+)", text)
    require(match is not None, f"invalid fixture edge: {text}")
    return match.group(1), match.group(2), match.group(3)


def run_probe_fixture_case(data: dict[str, Any], contract: dict[str, Any]) -> str:
    context = data["context"]
    result = data["result"]
    branch_map = {row["kind"]: row for row in contract["branches"]}
    branch = branch_map.get(result["kind"])
    if branch is None or result["extra_fields"] or result["derived_identity_fields"]:
        return "reject"
    if result["mode"] != context["mode"] or result["mode"] not in branch["mode"] or result["compatibility"] not in branch["compatibility"]:
        return "reject"
    evidence = result["identity_evidence"]
    if branch["identity_evidence_cardinality"] == "forbidden":
        return "accept" if evidence is None else "reject"
    if evidence is None or evidence["source"] != "official_protocol" or evidence["extra_fields"]:
        return "reject"
    try:
        material = decode_base64url(evidence["access_generation_material"])
    except ValidationError:
        return "reject"
    limits = contract["official_protocol_identity_evidence"]["access_generation_material_bytes"]
    if not limits["minimum"] <= len(material) <= limits["maximum"]:
        return "reject"
    binding = evidence["authorization_binding"]
    for field in ("principal_id", "profile_id", "rpc_endpoint_id", "source_contract_id", "source_generation"):
        if binding[field] != context[field]:
            return "reject"
    now = context["now_monotonic_ns"]
    if not now < evidence["expires_monotonic_ns"] <= now + 60_000_000_000:
        return "reject"
    return "accept"


def aggregate_retry_after(now_utc_seconds: int, boundaries: list[dict[str, Any]], contract: dict[str, Any]) -> tuple[int | None, str]:
    """Apply the one machine-authoritative multi-blocker aggregation rule."""
    active = [row["boundary_utc_seconds"] for row in boundaries if now_utc_seconds < row["boundary_utc_seconds"]]
    if not active:
        return None, "reserve_allowed"
    return min(contract["hard_max_seconds"], max(0, max(active) - now_utc_seconds)), "deferred"


def run_renderer_command_fixture_case(data: dict[str, Any], contract: dict[str, Any]) -> str:
    candidate = copy.deepcopy(contract)
    mutation = data["mutation"]
    commands = candidate["commands"]

    def command_index(command_id: str | None) -> int:
        require(command_id is not None, "renderer fixture command target is missing")
        matches = [index for index, row in enumerate(commands) if row["command_id"] == command_id]
        require(len(matches) == 1, "renderer fixture command target is not unique")
        return matches[0]

    if mutation == "unknown-command":
        commands[0]["command_id"] = data["target_command_id"]
    elif mutation == "missing-command":
        commands.pop(command_index(data["target_command_id"]))
    elif mutation == "duplicate-command":
        commands[command_index(data["secondary_command_id"])] = copy.deepcopy(commands[command_index(data["target_command_id"])])
    elif mutation == "reorder-command":
        first = command_index(data["target_command_id"])
        second = command_index(data["secondary_command_id"])
        commands[first], commands[second] = commands[second], commands[first]
    elif mutation == "dto-ref-swap":
        first = command_index(data["target_command_id"])
        second = command_index(data["secondary_command_id"])
        commands[first]["response_schema_ref"], commands[second]["response_schema_ref"] = commands[second]["response_schema_ref"], commands[first]["response_schema_ref"]
    elif mutation == "sensitive-field-injection":
        nested = next(row for row in candidate["dto_schemas"] if row["schema_ref"] == "aq-renderer-dto://v1/shared-nondestructive-config-change")
        nested["fields"].append({
            "name": data["field_name"],
            "type": "string",
            "required": False,
            "max_utf8_bytes": 1024,
            "allowed_values": [],
            "redaction": "renderer-safe-redacted",
        })
    elif mutation == "destructive-direct-commit":
        commands[command_index(data["target_command_id"])]["commit_policy"] = "direct-commit"
    else:
        require(mutation == "none", "unknown renderer fixture mutation")
    try:
        validate_renderer_command_contract_document(candidate)
    except (ValidationError, KeyError, TypeError, ValueError):
        return "reject"
    return "accept"


def run_sidecar_budget_fixture_case(data: dict[str, Any], contract: dict[str, Any]) -> str:
    validate_sidecar_budget_contract_document(contract)
    minimum = contract["minimum_remaining_budget_ns"]
    maximum = contract["maximum_remaining_budget_ns"]
    host_cap = contract["host_hard_cap_ns"]
    session_invalid = data["budget_reused"] or (
        data["prior_session_generation"] is not None
        and data["session_generation"] == data["prior_session_generation"]
    )
    budget_invalid = not minimum <= data["remaining_budget_ns"] <= maximum
    local_deadline = data["sidecar_receipt_ns"] + data["remaining_budget_ns"]
    arithmetic_invalid = local_deadline > data["arithmetic_max_ns"] or local_deadline < -(2**63)
    boundary_expired = not arithmetic_invalid and data["sidecar_observed_now_ns"] >= local_deadline
    if session_invalid or budget_invalid or arithmetic_invalid or boundary_expired:
        if data["dispatch_state"] == "pre-dispatch" and data["write_outcome"] == "zero" and data["orphan_count"] == 0 and data["host_timeout_action"] == "none":
            return "pre_dispatch_reject_zero_effects"
        return "reject"
    if data["host_elapsed_ns"] >= host_cap:
        if data["dispatch_state"] == "dispatched" and data["host_timeout_action"] == "term-kill-reap" and data["write_outcome"] == "unknown" and data["orphan_count"] == 0:
            return "dispatched_timeout_outcome_unknown_reaped"
        if data["dispatch_state"] == "pre-dispatch" and data["write_outcome"] == "zero" and data["orphan_count"] == 0:
            return "pre_dispatch_reject_zero_effects"
        return "reject"
    accepted = (
        data["dispatch_state"] == "pre-dispatch"
        and data["host_timeout_action"] == "none"
        and data["write_outcome"] == "zero"
        and data["orphan_count"] == 0
    )
    return "accept" if accepted else "reject"


def run_core_fixture_case(case: dict[str, Any], core: dict[str, Any]) -> str:
    domain = case["domain"]
    data = case["input"]
    if domain == "budget_policy":
        accepted = data["mutation"] == "none" and len(set(data["group_policy_ids"])) == 1 and data["expected_reservation_rows"] == 1
        return "accept" if accepted else "reject"
    if domain == "codex_bundle":
        expected_roots = [row["path"] for row in core["codex_schema_bundle"]["descriptor_roots"]]
        mutation = data["mutation"]
        if data["descriptor_roots"] != expected_roots:
            return "reject"
        if mutation == "none":
            return "accept" if set(data["runtime_open_paths"]).issubset(set(expected_roots)) else "reject"
        if mutation == "bit-flip" and data["target_path"] in expected_roots:
            return "hash_changed"
        if mutation == "delete-root" and data["target_path"] in expected_roots:
            return "reject"
        if mutation == "runtime-open-unlisted":
            return "reject"
        if mutation == "change-unreferenced" and data["target_path"] not in expected_roots:
            return "hash_unchanged"
        return "reject"
    if domain == "migration_graph":
        actions = data["action_ids"]
        if len(actions) != len(set(actions)) or data["mutation"] != "none":
            return "reject"
        allowed = set(core["migration_graph"]["execution_dependency_kinds"])
        edges = [parse_edge(value) for value in data["execution_edges"]]
        if any(parent not in actions or child not in actions or kind not in allowed or parent == child for parent, child, kind in edges):
            return "reject"
        indegree = {item: 0 for item in actions}
        children: dict[str, list[str]] = defaultdict(list)
        for parent, child, _ in edges:
            indegree[child] += 1
            children[parent].append(child)
        heap = [item for item, count in indegree.items() if count == 0]
        heapq.heapify(heap)
        visited = 0
        while heap:
            parent = heapq.heappop(heap)
            visited += 1
            for child in children[parent]:
                indegree[child] -= 1
                if indegree[child] == 0:
                    heapq.heappush(heap, child)
        return "accept" if visited == len(actions) else "reject"
    if domain == "repo_path":
        try:
            validate_repo_path(data["path"])
            accepted = not data["symlink_components"] and data["path"] in ALLOWED_READ_PATHS
        except ValidationError:
            accepted = False
        return "accept" if accepted else "reject"
    if domain == "probe_result":
        return run_probe_fixture_case(data, core["probe_result_contract"])
    if domain == "renderer_command":
        return run_renderer_command_fixture_case(data, core["desktop_product_contract"]["renderer_command_contract"])
    if domain == "installation_registry":
        accepted = (
            data["mutation"] == "none"
            and data["keyring_generation"] == data["registry_generation"] == data["db_floor"]
            and not data["bundle_digest_changed"]
            and not data["plan_digest_changed"]
        )
        return "accept" if accepted else "reject"
    if domain == "retry_after":
        contract = core["budget_ledger_contract"]["retry_after_aggregation"]
        retry_after, disposition = aggregate_retry_after(data["now_utc_seconds"], data["boundaries"], contract)
        accepted = (
            data["runner"] == contract["contract_id"].replace("aq-rate-", "")
            and retry_after == data["expected_retry_after_seconds"]
            and disposition == data["expected_disposition"]
        )
        return "accept" if accepted else "reject"
    if domain == "sidecar_budget":
        return run_sidecar_budget_fixture_case(data, core["desktop_product_contract"]["sidecar_budget_contract"])
    raise ValidationError(f"unknown core fixture domain: {domain}")


def validate_core_fixtures(contracts: ContractSet) -> int:
    core = contracts.artifacts["docs/contracts/core-safety-contract-v1.json"].document
    fixture = contracts.fixtures["docs/contracts/fixtures/core-safety-v1.json"].document
    utf8_sorted([case["fixture_id"] for case in fixture["cases"]], "core fixture IDs")
    for case in fixture["cases"]:
        actual = run_core_fixture_case(case, core)
        require(actual == case["expected"], f"core fixture verdict mismatch: {case['fixture_id']} expected={case['expected']} actual={actual}")
        renamed = dict(case)
        renamed["fixture_id"] = "diagnostic-name-does-not-drive-behavior"
        require(run_core_fixture_case(renamed, core) == actual, f"fixture_id changed behavior: {case['fixture_id']}")
    return len(fixture["cases"])


def decode_base64url(value: str, expected_length: int | None = None) -> bytes:
    require(isinstance(value, str) and "=" not in value and re.fullmatch(r"[A-Za-z0-9_-]*", value) is not None, "invalid base64url without padding")
    padding = "=" * ((4 - len(value) % 4) % 4)
    try:
        decoded = base64.urlsafe_b64decode(value + padding)
    except Exception as error:
        raise ValidationError("base64url decode failed") from error
    if expected_length is not None:
        require(len(decoded) == expected_length, f"decoded base64url length must be {expected_length}")
    return decoded


def u16be(value: int) -> bytes:
    require(0 <= value <= 65535, "u16 value out of range")
    return value.to_bytes(2, "big")


def u64be(value: int) -> bytes:
    require(0 <= value <= INT64_MAX, "u64 contract value out of range")
    return value.to_bytes(8, "big")


def recompute_key_id(installation_id: str, entry: dict[str, Any]) -> str:
    install = installation_id.encode("utf-8")
    purpose = entry["purpose"].encode("utf-8")
    public_salt = decode_base64url(entry["public_salt"], 16)
    key_material = decode_base64url(entry["key_material"], 32)
    digest = hashlib.sha256(
        b"agent-quota:local-key-id:v1\x00"
        + u16be(len(install)) + install
        + u16be(len(purpose)) + purpose
        + u64be(entry["generation"])
        + public_salt + key_material
    ).hexdigest()
    return "aqk_" + digest


def validate_local_key_semantics(contracts: ContractSet) -> None:
    artifact = contracts.artifacts["docs/contracts/local-key-purpose-registry-v1.json"].document
    purposes = artifact["purposes"]
    purpose_ids = utf8_sorted([row["purpose"] for row in purposes], "LocalKey purposes")
    purpose_map = {row["purpose"]: row for row in purposes}
    consumers = artifact["consumers"]
    consumer_ids = utf8_sorted([row["consumer_id"] for row in consumers], "LocalKey consumer IDs")
    consumer_map = {row["consumer_id"]: row for row in consumers}
    coverage: Counter[str] = Counter()
    policy_map = {row["policy_id"]: row for row in artifact["verification_lookup_policies"]}
    require(len(policy_map) == len(artifact["verification_lookup_policies"]), "duplicate verification lookup policy")
    for consumer in consumers:
        purpose = consumer["purpose"]
        require(purpose in purpose_map, f"consumer has dangling purpose: {consumer['consumer_id']}")
        coverage[purpose] += 1
        require(consumer["new_value_policy"] == "active_generation_only", f"consumer may issue with verify-only key: {consumer['consumer_id']}")
        require(consumer["verification_lookup_policy"] in policy_map, f"consumer has unknown lookup policy: {consumer['consumer_id']}")
        if purpose_map[purpose]["verify_only_allowed"]:
            require(policy_map[consumer["verification_lookup_policy"]]["max_generations"] <= 4, f"unbounded verify-only lookup: {consumer['consumer_id']}")
        else:
            require(consumer["verification_lookup_policy"] == "active_only", f"replace-generation purpose permits old-key lookup: {consumer['consumer_id']}")
    require(set(coverage) == set(purpose_ids) and all(coverage[item] > 0 for item in purpose_ids), "purpose-to-consumer closure mismatch")

    surfaces = artifact["persistent_surfaces"]
    utf8_sorted([row["surface_id"] for row in surfaces], "LocalKey persistent surface IDs")
    for surface in surfaces:
        utf8_sorted(surface["consumer_ids"], f"consumer IDs for surface {surface['surface_id']}")
        require(all(item in consumer_map for item in surface["consumer_ids"]), f"surface has dangling consumer: {surface['surface_id']}")
        product = 1
        for consumer_id in surface["consumer_ids"]:
            product *= policy_map[consumer_map[consumer_id]["verification_lookup_policy"]]["max_generations"]
        require(product <= surface["max_candidate_combinations"], f"surface candidate combination bound too small: {surface['surface_id']}")

    golden = artifact["local_keyring_wire"]["golden_payload_envelope"]
    payload = golden["payload"]
    entries = payload["key_entries"]
    require([row["purpose"] for row in entries] == purpose_ids, "golden payload purpose set/order mismatch")
    tuples = [(row["purpose"], row["generation"]) for row in entries]
    require(tuples == sorted(tuples, key=lambda row: (row[0].encode("utf-8"), row[1])) and len(tuples) == len(set(tuples)), "golden key entry tuple order/uniqueness mismatch")
    active: Counter[str] = Counter()
    for entry in entries:
        require(entry["purpose"] in purpose_map, f"golden payload has unknown purpose: {entry['purpose']}")
        require(hmac.compare_digest(recompute_key_id(payload["installation_id"], entry), entry["key_id"]), f"golden key ID mismatch: {entry['purpose']}")
        if entry["state"] == "active":
            active[entry["purpose"]] += 1
        elif entry["state"] == "verify_only":
            require(purpose_map[entry["purpose"]]["verify_only_allowed"], f"forbidden verify-only key: {entry['purpose']}")
        else:
            raise ValidationError(f"unknown key state: {entry['state']}")
    require(active == Counter({purpose: 1 for purpose in purpose_ids}), "golden payload must have exactly one active generation per purpose")
    envelope = golden["envelope"]
    require(envelope["installation_id"] == payload["installation_id"], "golden payload/envelope installation mismatch")
    require(envelope["aead_generation"] == payload["aead_generation"] and envelope["envelope_sequence"] == payload["envelope_sequence"], "golden payload/envelope generation mismatch")


@dataclass(frozen=True)
class LeaseSignature:
    value_type: str
    unit: str
    clock_domain: str | None

    def document(self) -> dict[str, Any]:
        return {"value_type": self.value_type, "unit": self.unit, "clock_domain": self.clock_domain}


def infer_lease_expression(
    expression: dict[str, Any],
    artifact: dict[str, Any],
    formula_map: dict[str, dict[str, Any]],
    operand_map: dict[str, dict[str, Any]],
    operator_map: dict[str, dict[str, Any]],
    stack: tuple[str, ...],
    used_operands: set[str],
    used_operators: set[str],
    used_formulas: set[str],
) -> LeaseSignature:
    unit_by_type = {
        "boolean": "boolean",
        "int64_ms": "milliseconds",
        "int64_ns": "nanoseconds",
        "not_applicable": "none",
        "takeover_pair": "structured",
        "uint63": "dimensionless",
    }
    if "operand" in expression:
        operand_id = expression["operand"]
        require(operand_id in operand_map, f"dangling lease operand: {operand_id}")
        used_operands.add(operand_id)
        operand = operand_map[operand_id]
        return LeaseSignature(operand["type"], unit_by_type[operand["type"]], operand["clock_id"])
    if "formula_ref" in expression:
        formula_id = expression["formula_ref"]
        require(formula_id in formula_map, f"dangling lease formula: {formula_id}")
        require(formula_id not in stack, f"lease formula cycle: {' -> '.join(stack + (formula_id,))}")
        used_formulas.add(formula_id)
        formula = formula_map[formula_id]
        actual = infer_lease_expression(formula["expression"], artifact, formula_map, operand_map, operator_map, stack + (formula_id,), used_operands, used_operators, used_formulas)
        expected = LeaseSignature(formula["result_type"], formula["result_unit"], formula["result_clock_domain"])
        require(actual == expected, f"formula result signature mismatch: {formula_id}: expected={expected.document()} actual={actual.document()}")
        return actual
    if "convert" in expression:
        rule = artifact["conversion_rule"]
        require(expression["convert"] == rule["conversion_id"], f"unknown clock conversion: {expression['convert']}")
        deadline = infer_lease_expression(expression["deadline"], artifact, formula_map, operand_map, operator_map, stack, used_operands, used_operators, used_formulas)
        expected_input = LeaseSignature(rule["input_type"], rule["input_unit"], rule["input_clock_domain"])
        require(deadline == expected_input, f"clock conversion input signature mismatch: expected={expected_input.document()} actual={deadline.document()}")
        return LeaseSignature(rule["result_type"], rule["result_unit"], rule["result_clock_domain"])
    if "literal" in expression:
        literal = expression["literal"]
        value = literal["value"]
        require(not isinstance(value, bool), "bool must not satisfy lease integer literal")
        if isinstance(value, int):
            require(INT64_MIN <= value <= INT64_MAX, "lease literal outside signed int64")
        require(literal["unit"] == unit_by_type[literal["type"]], "lease literal unit/type mismatch")
        return LeaseSignature(literal["type"], literal["unit"], None)
    if "op" in expression:
        operator_id = expression["op"]
        require(operator_id in operator_map, f"unknown lease operator: {operator_id}")
        used_operators.add(operator_id)
        operator = operator_map[operator_id]
        args = expression["args"]
        require(operator["min_args"] <= len(args) <= operator["max_args"], f"lease operator arity mismatch: {operator_id}")
        arg_signatures = [infer_lease_expression(arg, artifact, formula_map, operand_map, operator_map, stack, used_operands, used_operators, used_formulas) for arg in args]
        arg_types = [item.value_type for item in arg_signatures]
        expected = operator["input_type"]
        if expected == "same_scalar_pair":
            require(len(arg_types) == 2 and arg_types[0] == arg_types[1], f"lease scalar pair mismatch: {operator_id}")
        elif expected.endswith("[]"):
            require(all(item == expected[:-2] for item in arg_types), f"lease operator input type mismatch: {operator_id}")
        elif expected.endswith("_pair"):
            require(len(arg_types) == 2 and arg_types[0] == arg_types[1] == expected[:-5], f"lease pair operator input type mismatch: {operator_id}")
        else:
            require(len(arg_types) == 1 and arg_types[0] == expected, f"lease operator input type mismatch: {operator_id}")
        if expected == "same_scalar_pair":
            require(arg_signatures[0].unit == arg_signatures[1].unit and arg_signatures[0].clock_domain == arg_signatures[1].clock_domain, f"lease comparison unit/clock mismatch: {operator_id}")
            return LeaseSignature("boolean", "boolean", None)
        if operator_id == "and":
            require(all(item.unit == "boolean" and item.clock_domain is None for item in arg_signatures), "boolean operator received clocked/non-boolean input")
            return LeaseSignature("boolean", "boolean", None)
        if operator_id == "checked_add":
            require(all(item.unit == "milliseconds" for item in arg_signatures), "checked_add unit mismatch")
            domains = [item.clock_domain for item in arg_signatures if item.clock_domain is not None]
            require(len(set(domains)) <= 1 and len(domains) <= 1, "checked_add may contain at most one clock-domain timestamp")
            return LeaseSignature("int64_ms", "milliseconds", domains[0] if domains else None)
        if operator_id == "min":
            require(all(item.unit == "milliseconds" for item in arg_signatures), "min unit mismatch")
            domains = {item.clock_domain for item in arg_signatures}
            require(len(domains) == 1, "min may not mix duration and clock-domain timestamps")
            return LeaseSignature("int64_ms", "milliseconds", arg_signatures[0].clock_domain)
        if operator_id == "min_int64_ns":
            require(all(item.unit == "nanoseconds" for item in arg_signatures), "min_int64_ns unit mismatch")
            domains = {item.clock_domain for item in arg_signatures}
            require(len(domains) == 1, "min_int64_ns clock-domain mismatch")
            return LeaseSignature("int64_ns", "nanoseconds", arg_signatures[0].clock_domain)
        if operator_id == "subtract_nonnegative":
            require(arg_signatures[0].unit == arg_signatures[1].unit == "milliseconds", "subtract_nonnegative unit mismatch")
            require(arg_signatures[0].clock_domain is not None and arg_signatures[1].clock_domain is None, "subtract_nonnegative requires timestamp minus duration")
            return LeaseSignature("int64_ms", "milliseconds", arg_signatures[0].clock_domain)
        if operator_id == "subtract_clamped_zero_int64_ns":
            require(arg_signatures[0].unit == arg_signatures[1].unit == "nanoseconds", "nanosecond subtraction unit mismatch")
            require(arg_signatures[0].clock_domain is not None and arg_signatures[0].clock_domain == arg_signatures[1].clock_domain, "nanosecond subtraction clock-domain mismatch")
            return LeaseSignature("int64_ns", "nanoseconds", None)
        if operator_id == "floor_div_ns_to_ms":
            require(arg_signatures[0] == LeaseSignature("int64_ns", "nanoseconds", None), "ns-to-ms conversion requires an unclocked duration")
            return LeaseSignature("int64_ms", "milliseconds", None)
        if operator_id == "checked_increment_u63":
            require(arg_signatures[0] == LeaseSignature("uint63", "dimensionless", None), "fencing increment signature mismatch")
            return LeaseSignature("uint63", "dimensionless", None)
        raise ValidationError(f"lease operator lacks signature propagation rule: {operator_id}")
    if set(expression) == {"eligible", "next_fencing_token", "transaction"}:
        require(expression["transaction"] == "BEGIN IMMEDIATE", "takeover formula transaction mismatch")
        require(infer_lease_expression(expression["eligible"], artifact, formula_map, operand_map, operator_map, stack, used_operands, used_operators, used_formulas) == LeaseSignature("boolean", "boolean", None), "takeover eligibility signature mismatch")
        require(infer_lease_expression(expression["next_fencing_token"], artifact, formula_map, operand_map, operator_map, stack, used_operands, used_operators, used_formulas) == LeaseSignature("uint63", "dimensionless", None), "takeover fence signature mismatch")
        return LeaseSignature("takeover_pair", "structured", None)
    raise ValidationError(f"unrecognized lease expression: {expression}")


def validate_lease_semantics(contracts: ContractSet) -> None:
    artifact = contracts.artifacts["docs/contracts/lease-policy-v1.json"].document
    operators = artifact["operators"]
    operands = artifact["operand_definitions"]
    formulas = artifact["formula_definitions"]
    policies = artifact["policies"]
    utf8_sorted([row["op"] for row in operators], "lease operator IDs")
    utf8_sorted([row["operand_id"] for row in operands], "lease operand IDs")
    utf8_sorted([row["formula_id"] for row in formulas], "lease formula IDs")
    utf8_sorted([row["policy_id"] for row in policies], "lease policy IDs")
    operator_map = {row["op"]: row for row in operators}
    operand_map = {row["operand_id"]: row for row in operands}
    formula_map = {row["formula_id"]: row for row in formulas}
    clock_map = {row["clock_id"]: row for row in artifact["clock_domains"]}
    require(len(clock_map) == len(artifact["clock_domains"]), "duplicate lease clock domain")
    unit_by_type = {"int64_ms": "milliseconds", "int64_ns": "nanoseconds", "uint63": "dimensionless"}
    for operand in operands:
        require(operand["clock_id"] is None or operand["clock_id"] in clock_map, f"lease operand has unknown clock domain: {operand['operand_id']}")
        if operand["clock_id"] is not None:
            require(clock_map[operand["clock_id"]]["unit"] == unit_by_type[operand["type"]], f"lease operand type/clock unit mismatch: {operand['operand_id']}")
        if "constant" in operand:
            require(operand["constant"]["type"] == operand["type"] and operand["constant"]["unit"] == unit_by_type[operand["type"]], f"lease typed constant signature mismatch: {operand['operand_id']}")
    used_operands: set[str] = set()
    used_operators: set[str] = set()
    used_formulas: set[str] = set()
    for formula in formulas:
        result = infer_lease_expression(formula["expression"], artifact, formula_map, operand_map, operator_map, (formula["formula_id"],), used_operands, used_operators, used_formulas)
        expected = LeaseSignature(formula["result_type"], formula["result_unit"], formula["result_clock_domain"])
        require(result == expected, f"lease formula result mismatch: {formula['formula_id']}")
    conversion_result = infer_lease_expression(artifact["conversion_rule"]["expression"], artifact, formula_map, operand_map, operator_map, ("conversion_rule",), used_operands, used_operators, used_formulas)
    conversion = artifact["conversion_rule"]
    require(conversion_result == LeaseSignature(conversion["result_type"], conversion["result_unit"], conversion["result_clock_domain"]), "lease conversion result signature mismatch")
    for policy in policies:
        for field in ("duration_ms", "renew_before_ms", "max_lifetime_ms"):
            value = policy[field]
            require(isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= INT64_MAX, f"invalid lease policy integer: {policy['policy_id']}.{field}")
        require(0 < policy["duration_ms"] <= policy["max_lifetime_ms"], f"lease duration/max mismatch: {policy['policy_id']}")
        require(0 <= policy["renew_before_ms"] < policy["duration_ms"], f"lease renew boundary mismatch: {policy['policy_id']}")
        for field in ("expiry_formula_id", "parent_deadline_formula_id"):
            require(policy[field] in formula_map, f"lease policy has dangling formula: {policy['policy_id']}.{field}")
            used_formulas.add(policy[field])
            formula = formula_map[policy[field]]
            actual = LeaseSignature(formula["result_type"], formula["result_unit"], formula["result_clock_domain"])
            expected_field = field.removesuffix("_id") + "_expected"
            require(policy[expected_field] == actual.document(), f"lease policy formula signature mismatch: {policy['policy_id']}.{field}")
        require(policy["expiry_formula_expected"] == LeaseSignature("int64_ms", "milliseconds", "db_utc_ms").document(), f"lease expiry formula must return a DB UTC timestamp: {policy['policy_id']}")
    for field in ("boundary_formula_id", "renew_formula_id", "takeover_formula_id", "provider_io_deadline_formula_id"):
        require(artifact[field] in formula_map, f"dangling top-level lease formula: {field}")
        used_formulas.add(artifact[field])
    top_level_expected = {
        "boundary_formula_id": LeaseSignature("boolean", "boolean", None),
        "renew_formula_id": LeaseSignature("boolean", "boolean", None),
        "takeover_formula_id": LeaseSignature("takeover_pair", "structured", None),
        "provider_io_deadline_formula_id": LeaseSignature("int64_ns", "nanoseconds", "process_monotonic_ns"),
    }
    for field, expected in top_level_expected.items():
        formula = formula_map[artifact[field]]
        actual = LeaseSignature(formula["result_type"], formula["result_unit"], formula["result_clock_domain"])
        require(actual == expected, f"top-level lease formula signature mismatch: {field}")
    constant = operand_map["crash_grace_ms"]["constant"]
    require(constant == {"type": "int64_ms", "unit": "milliseconds", "value": 2000}, "crash grace typed constant mismatch")
    require(used_operands == set(operand_map), f"unused lease operands: {sorted(set(operand_map) - used_operands)}")
    require(used_operators == set(operator_map), f"unused lease operators: {sorted(set(operator_map) - used_operators)}")
    require(used_formulas == set(formula_map), f"unused lease formulas: {sorted(set(formula_map) - used_formulas)}")


def evaluate_predicate_expression(expression: dict[str, Any], inputs: dict[str, Any], declared: set[str]) -> bool:
    def term(value: dict[str, Any]) -> Any:
        require(set(value) in ({"input"}, {"literal"}), "predicate term field closure mismatch")
        if "input" in value:
            require(value["input"] in declared and value["input"] in inputs, "predicate expression has a missing/undeclared input")
            return inputs[value["input"]]
        return value["literal"]

    op = expression.get("op")
    if op == "literal":
        require(set(expression) == {"op", "value"} and isinstance(expression["value"], bool), "predicate literal AST mismatch")
        return expression["value"]
    if op == "or":
        require(set(expression) == {"op", "args"} and 2 <= len(expression["args"]) <= 8, "predicate or AST mismatch")
        return any(evaluate_predicate_expression(item, inputs, declared) for item in expression["args"])
    require(op in {"equal", "not_equal"} and set(expression) == {"op", "left", "right"}, "predicate operator is outside the restricted AST")
    equal = term(expression["left"]) == term(expression["right"])
    return equal if op == "equal" else not equal


def validate_operation_semantics(contracts: ContractSet) -> None:
    artifact = contracts.artifacts["docs/contracts/operation-contract-v1.json"].document
    stages = set(utf8_sorted(artifact["stages"], "operation stages"))
    operations = set(utf8_sorted(artifact["operations"], "operation names"))
    modes = set(utf8_sorted(artifact["modes"], "operation modes"))
    error_codes = set(utf8_sorted(artifact["error_codes"], "operation error codes"))
    request_kinds = set(utf8_sorted(artifact["request_kinds"], "operation request kinds"))
    io_classes = set(utf8_sorted(artifact["io_classes"], "operation I/O classes"))
    predicate_ids = set(utf8_sorted(artifact["predicate_ids"], "predicate IDs"))

    predicate_defs = artifact["predicate_definitions"]
    utf8_sorted([row["predicate_id"] for row in predicate_defs], "predicate definition IDs")
    require({row["predicate_id"] for row in predicate_defs} == predicate_ids, "predicate definition/ID set mismatch")
    for row in predicate_defs:
        names = [item["name"] for item in row["inputs"]]
        utf8_sorted(names, f"predicate inputs for {row['predicate_id']}")
        declared = set(names)
        for item in row["inputs"]:
            if "allowed_values" in item:
                utf8_sorted(item["allowed_values"], f"predicate allowed values for {row['predicate_id']}.{item['name']}")
        control = row["control_flow"]
        require(set(control) == {"true", "false", "missing", "error"}, f"predicate control-flow closure mismatch: {row['predicate_id']}")
        vectors = row["semantic_vectors"]
        stable_unique([item["vector_id"] for item in vectors], f"predicate vectors for {row['predicate_id']}")
        for vector in vectors:
            status = vector["input_status"]
            if status == "complete":
                require(set(vector["inputs"]) == declared, f"predicate complete vector input closure mismatch: {vector['vector_id']}")
                for input_def in row["inputs"]:
                    if input_def["type"] == "enum":
                        require(vector["inputs"][input_def["name"]] in input_def["allowed_values"], f"predicate enum vector is outside allowed values: {vector['vector_id']}")
                result = evaluate_predicate_expression(row["expression"], vector["inputs"], declared)
                branch = "true" if result else "false"
                require(vector["predicate_result"] is result, f"predicate truth result mismatch: {vector['vector_id']}")
            elif status in {"missing", "invalid"}:
                branch = "missing"
                require(vector["predicate_result"] is None, f"predicate fail-closed vector must have null result: {vector['vector_id']}")
            else:
                require(status == "evaluation_error", f"predicate vector status is unknown: {vector['vector_id']}")
                branch = "error"
                require(vector["predicate_result"] is None, f"predicate error vector must have null result: {vector['vector_id']}")
            require(
                {"action": vector["action"], "typed_result": vector["typed_result"]} == control[branch],
                f"predicate vector/control-flow mismatch: {vector['vector_id']}",
            )

    consent = next(row for row in predicate_defs if row["predicate_id"] == "consent-required-for-status-projection")
    require(consent["expression"] == {"op": "equal", "left": {"input": "audience"}, "right": {"literal": "llm_minimal"}}, "LLM consent predicate semantic oracle mismatch")
    consent_vectors = {row["vector_id"]: row for row in consent["semantic_vectors"]}
    require(set(consent_vectors) == {"consent-evaluation-error", "consent-feishu-private", "consent-llm-minimal", "consent-local-detail", "consent-missing", "consent-unknown"}, "LLM consent vector closure mismatch")
    require(consent_vectors["consent-llm-minimal"]["predicate_result"] is True and consent_vectors["consent-llm-minimal"]["action"] == "execute_stage", "llm_minimal must execute consent validation")
    for vector_id in ("consent-feishu-private", "consent-local-detail"):
        require(consent_vectors[vector_id]["predicate_result"] is False and consent_vectors[vector_id]["action"] == "skip_stage", f"non-LLM audience must skip only LLM consent: {vector_id}")
    for vector_id in ("consent-missing", "consent-unknown", "consent-evaluation-error"):
        require(consent_vectors[vector_id]["action"] == "reject_operation", f"invalid consent predicate input must fail closed: {vector_id}")

    safe_schemas = artifact["safe_param_schemas"]
    utf8_sorted([row["schema_id"] for row in safe_schemas], "safe param schema IDs")
    safe_map = {row["schema_id"]: row for row in safe_schemas}
    for schema in safe_schemas:
        utf8_sorted([field["name"] for field in schema["fields"]], f"safe param fields for {schema['schema_id']}")
        for field in schema["fields"]:
            values = field.get("allowed_values", [])
            if values:
                utf8_sorted(values, f"safe enum values for {schema['schema_id']}.{field['name']}")

    paths = artifact["paths"]
    utf8_sorted([row["path_id"] for row in paths], "operation path IDs")
    path_map = {row["path_id"]: row for row in paths}
    require(len({(row["operation"], row["mode"]) for row in paths}) == len(paths), "duplicate operation/mode path")
    used_predicates: set[str] = set()
    used_stages: set[str] = set()
    provider_steps: dict[tuple[str, int], dict[str, Any]] = {}
    for path in paths:
        require(path["operation"] in operations and path["mode"] in modes, f"path enum reference mismatch: {path['path_id']}")
        for ordinal, step in enumerate(path["steps"], 1):
            require(step["stage"] in stages, f"path has unknown stage: {path['path_id']}#{ordinal}")
            require(step["predicate_id"] in predicate_ids, f"path has unknown predicate: {path['path_id']}#{ordinal}")
            require(step["io_class"] in io_classes, f"path has unknown I/O class: {path['path_id']}#{ordinal}")
            require(step["request_kind"] is None or step["request_kind"] in request_kinds, f"path has unknown request kind: {path['path_id']}#{ordinal}")
            used_predicates.add(step["predicate_id"])
            used_stages.add(step["stage"])
            if step["io_class"] == "provider_io":
                require(step["request_kind"] is not None, f"Provider I/O lacks request kind: {path['path_id']}#{ordinal}")
                provider_steps[(path["path_id"], ordinal)] = step
            if "predicate_branch" in step:
                require(path["path_id"] == "status-none-v1" and step["stage"] == "consent_validate" and step["predicate_id"] == "consent-required-for-status-projection", "conditional predicate branch appears outside the status consent node")
                require(step["predicate_branch"] == {"node_type":"conditional_stage","on_true":"execute_stage","on_false":"skip_stage","on_missing":"reject_operation","on_error":"reject_operation","typed_result_source":"predicate_control_flow"}, "status consent path AST branch mismatch")
    require(used_predicates == predicate_ids, f"unused predicates: {sorted(predicate_ids - used_predicates)}")
    require(used_stages == stages, f"unused operation stages: {sorted(stages - used_stages)}")
    status_consent_steps = [step for path in paths for step in path["steps"] if "predicate_branch" in step]
    require(len(status_consent_steps) == 1, "status consent conditional path AST must occur exactly once")
    for path_id in ("doctor-http-v1", "doctor-official-cli-v1", "doctor-offline-v1"):
        path = path_map[path_id]
        step_stages = [step["stage"] for step in path["steps"]]
        require(step_stages.count("probe_result_validate") == 1, f"doctor path lacks exactly one ProbeResult validation: {path_id}")
        probe_index = step_stages.index("probe")
        validate_index = step_stages.index("probe_result_validate")
        require(validate_index == probe_index + 1, f"ProbeResult validation must immediately follow probe: {path_id}")
        require(path["steps"][validate_index]["predicate_id"] == "probe-result-contract-v1", f"ProbeResult path uses wrong predicate: {path_id}")
        if path_id == "doctor-official-cli-v1":
            require(validate_index < step_stages.index("identity_derive"), "official CLI evidence reaches identity_derive before ProbeResult validation")

    io_defs = artifact["io_step_definitions"]
    io_keys = [(row["path_id"], row["step_ordinal"]) for row in io_defs]
    require(len(io_keys) == len(set(io_keys)), "duplicate Provider I/O step definition")
    require(set(io_keys) == set(provider_steps), "Provider I/O step/definition bijection mismatch")
    for row in io_defs:
        key = (row["path_id"], row["step_ordinal"])
        require(row["path_id"] in path_map, f"I/O definition has unknown path: {row['path_id']}")
        require(provider_steps[key]["request_kind"] == row["request_kind"], f"I/O definition request-kind mismatch: {key}")
        require(row["reservation_cardinality"] == "exactly_one", f"I/O definition reservation cardinality mismatch: {key}")

    dependencies = artifact["provider_io_data_dependencies"]
    utf8_sorted([row["path_id"] for row in dependencies], "Provider I/O dependency path IDs")
    require({row["path_id"] for row in dependencies} == {path_id for path_id, _ in provider_steps}, "Provider I/O dependency/path bijection mismatch")
    for row in dependencies:
        path = path_map[row["path_id"]]
        step_stages = [step["stage"] for step in path["steps"]]
        indices = [step_stages.index(row[field]) for field in ("request_plan_stage", "reserve_stage", "commit_stage", "final_context_stage", "provider_io_stage")]
        require(indices == sorted(indices) and len(indices) == len(set(indices)), f"Provider I/O dependency order mismatch: {row['path_id']}")
        require(row["timing_rule"] == "receipt_produced_at<context_created_at<first_provider_byte_at", f"Provider I/O timing rule mismatch: {row['path_id']}")
        provider_step = path["steps"][indices[-1]]
        reserve_step = path["steps"][indices[1]]
        commit_step = path["steps"][indices[2]]
        require(provider_step["io_class"] == "provider_io", f"dependency terminal step is not Provider I/O: {row['path_id']}")
        require(reserve_step["request_kind"] == commit_step["request_kind"] == provider_step["request_kind"], f"dependency request-kind mismatch: {row['path_id']}")

    rows = artifact["error_rows"]
    primary = [(row["code"], row["operation"], row["stage"]) for row in rows]
    require(len(primary) == len(set(primary)), "duplicate operation error primary key")
    used_errors: set[str] = set()
    used_safe_schemas: set[str] = set()
    for row in rows:
        require(row["code"] in error_codes and row["operation"] in operations and row["stage"] in stages, f"dangling error row reference: {row}")
        require(row["safe_param_schema_id"] in safe_map, f"dangling safe param schema: {row}")
        require(isinstance(row["retryable"], bool), f"error retryable must be boolean: {row}")
        used_errors.add(row["code"])
        used_safe_schemas.add(row["safe_param_schema_id"])
    require(used_errors == error_codes, f"unused error codes: {sorted(error_codes - used_errors)}")

    rate_contract = artifact["rate_reserve_result_contract"]
    provider_path_ids = rate_contract["provider_path_ids"]
    utf8_sorted(provider_path_ids, "rate-reserve provider path IDs")
    require(set(provider_path_ids).issubset(path_map), "rate-reserve result has unknown path")
    success_path_counts = rate_contract["success_path_counts"]
    require(list(success_path_counts) == provider_path_ids, "rate-reserve success map must exactly follow provider_path_ids")
    for path_id in provider_path_ids:
        path = path_map[path_id]
        steps = path["steps"]
        actual_counts = {
            "credential_resolution_count": sum(step["stage"] == "credential_resolve" for step in steps),
            "credential_source_call_count": sum(step["stage"] == "credential_resolve" for step in steps),
            "provider_attempt_count": sum(step["io_class"] == "provider_io" for step in steps),
            "reservation_row_count": sum(step["stage"] == "rate_ledger_reserve" for step in steps),
        }
        require(success_path_counts[path_id] == actual_counts, f"rate-reserve success path counts differ from step closure: {path_id}")
        if path["mode"] == "official_cli_zero_binding":
            require(actual_counts["credential_source_call_count"] == 0, f"official CLI path called Credential Source: {path_id}")
        else:
            require(path["mode"] == "http" and actual_counts["credential_source_call_count"] == 1, f"HTTP path credential resolution count mismatch: {path_id}")
    reasons = rate_contract["reason_map"]
    utf8_sorted([row["reason"] for row in reasons], "rate-reserve reason IDs")
    for row in reasons:
        require(row["code"] in error_codes and row["safe_param_schema_id"] in safe_map, f"rate-reserve result has dangling reference: {row['reason']}")
        schema_fields = safe_map[row["safe_param_schema_id"]]["fields"]
        require(len(schema_fields) == 1 and row["safe_value"] in schema_fields[0]["allowed_values"], f"rate-reserve safe value mismatch: {row['reason']}")
    require(rate_contract["provider_byte_count_on_any_rejection"] == rate_contract["credential_read_count_before_reserve"] == rate_contract["cache_write_count_on_any_rejection"] == 0, "rate-reserve rejection is not zero side-effect")
    require(rate_contract["fatal_fallback"] == "forbidden", "rate-reserve rejection permits fatal fallback")


def projection_inner(artifact: dict[str, Any], pointers: list[str]) -> str:
    projected = {pointer: json_pointer(artifact, pointer) for pointer in pointers}
    return "\n```json\n" + canonical_bytes(projected).decode("utf-8") + "\n```\n"


def marker_inner(text: str, marker: str) -> str:
    pattern = re.compile(rf"<!-- {re.escape(marker)}:BEGIN -->(.*?)<!-- {re.escape(marker)}:END -->", re.DOTALL)
    matches = pattern.findall(text)
    require(len(matches) == 1, f"generated marker must occur exactly once: {marker}")
    return matches[0]


def validate_normative_decision_input(contracts: ContractSet) -> None:
    path = NORMATIVE_DECISION_PATHS[0]
    source = contracts.normative_docs[path]
    row = contracts.registry.document["normative_decision_inputs"][0]
    require(path not in HISTORY_PATH_UNIVERSE and re.fullmatch(r"docs/audits/round-[0-9]{2}-(?:audit|resolution)\.md", path) is None, "normative decision input is disguised as round history")
    require(row == {
        "path": path,
        "category": "non-history-normative-decision-input",
        "record_kind": "normative-product-decision-non-history",
        "decision_status": "confirmed-current-pending-independent-r20",
        "history_membership": "forbidden-not-audit-not-resolution",
        "first_line": "# GUI 产品决策处置记录（非审计轮次）",
        "projection_marker": "AQ-NORMATIVE-PRODUCT-DECISION-V1",
        "raw_sha256": row["raw_sha256"],
    }, "normative decision registry row field/value closure mismatch")
    require(source.splitlines()[0] == row["first_line"], "normative decision first line mismatch")
    require(row["raw_sha256"] not in source, "normative decision embeds its own raw digest")
    inner = marker_inner(source, row["projection_marker"])
    match = re.fullmatch(r"\n```json\n([^\n]+)\n```\n", inner)
    require(match is not None, "normative decision marker has unstable Markdown shape")
    try:
        actual = json.loads(match.group(1), object_pairs_hook=duplicate_rejector, parse_int=parse_int, parse_float=reject_float, parse_constant=reject_constant)
    except Exception as error:
        raise ValidationError(f"normative decision marker is not strict JSON: {error}") from error
    live_links = {
        "README.md": "docs/audits/gui-product-decision-resolution.md",
        "docs/design-proposal.md": "audits/gui-product-decision-resolution.md",
        "docs/provider-contract.md": "audits/gui-product-decision-resolution.md",
        "docs/security-model.md": "audits/gui-product-decision-resolution.md",
    }
    desktop = contracts.artifacts["docs/contracts/core-safety-contract-v1.json"].document["desktop_product_contract"]
    openrouter = contracts.artifacts["docs/contracts/core-safety-contract-v1.json"].document["openrouter_adapter_contract"]
    require(desktop["product_name"] == "Agent Quota Desktop" and desktop["primary_surface"] == "local_desktop_gui" and desktop["mvp_platforms"] == ["macos"], "normative product projection source mismatch")
    require(desktop["cli_role"] == "maintenance-diagnostics-accessibility-and-automation-auxiliary", "normative CLI projection source mismatch")
    require(desktop["codex_disposition"] == "experimental-incompatible-default-off-no-mvp-count-no-fetch-no-persistent-cache-until-approved-stable-identity-source", "normative Codex projection source mismatch")
    require(openrouter["lifecycle"] == "supported-candidate" and openrouter["endpoint_id"] == "openrouter-current-key-v1" and openrouter["method"] == "GET" and openrouter["path"] == "/api/v1/key", "normative OpenRouter projection source mismatch")
    expected = {
        "schema": "aq-normative-product-decision-v1",
        "record_kind": row["record_kind"],
        "decision_status": row["decision_status"],
        "history_membership": row["history_membership"],
        "product": {"product_name": desktop["product_name"], "primary_surface": desktop["primary_surface"], "mvp_platform": desktop["mvp_platforms"][0], "cli_role": "auxiliary"},
        "codex": {"disposition": "experimental-incompatible-parser-only", "real_cli": "forbidden", "account_read": "forbidden", "runtime_fetch": "forbidden", "persistent_cache": "forbidden"},
        "openrouter": {"target": "get-current-api-key", "lifecycle": openrouter["lifecycle"], "mvp_count_rule": "only-after-real-opt-in-gate"},
        "live_document_links": live_links,
    }
    require(actual == expected and match.group(1).encode("utf-8") == canonical_bytes(expected), "normative decision machine projection mismatch")
    for live_path, link in live_links.items():
        live_source = contracts.docs[live_path]
        require(live_source.count(f"<!-- AQ-NORMATIVE-DECISION-LINK-V1:{link} -->") == 1, f"normative decision link marker mismatch: {live_path}")
        require(f"]({link})" in live_source, f"normative decision Markdown link mismatch: {live_path}")


def artifact_pin_projection(registry: dict[str, Any]) -> tuple[dict[str, Any], str]:
    pins = [{"artifact_id": row["artifact_id"], "canonical_sha256": row["artifact_canonical_sha256"]} for row in registry["artifacts"]]
    payload = {"artifact_pins": pins}
    digest = sha256(canonical_bytes(payload))
    return {"artifact_pins": pins, "projection_sha256": digest}, digest


def validate_detached_history_no_self_reference(
    resolution_raw: bytes,
    manifest_raw: bytes,
    resolution_digest: str,
    manifest_digest: str,
) -> None:
    require(resolution_digest.encode("ascii") not in resolution_raw, "resolution contains its own raw digest")
    require(
        manifest_digest.encode("ascii") not in resolution_raw and manifest_digest.encode("ascii") not in manifest_raw,
        "history manifest has a digest self-reference",
    )


def history_paths_from_manifest_document(manifest: dict[str, Any]) -> tuple[str, ...]:
    require(set(manifest) == {"schema", "max_rounds", "detached_two_phase_policy", "entries", "latest"}, "history manifest field closure mismatch")
    require(manifest["schema"] == "aq-history-manifest-v1", "history manifest schema mismatch")
    require(manifest["max_rounds"] == MAX_AUDIT_ROUNDS, "history manifest maximum round mismatch")
    require(manifest["detached_two_phase_policy"] == "finalize-audit-and-resolution-bytes-first-then-generate-manifest-resolution-must-not-contain-self-hash-or-manifest-hash", "history manifest detached policy mismatch")
    entries = manifest["entries"]
    require(isinstance(entries, list) and entries, "history manifest entries must be a non-empty array")
    pairs: list[tuple[int, str]] = []
    paths: list[str] = []
    for row in entries:
        require(isinstance(row, dict) and set(row) == {"round", "kind", "path", "raw_sha256"}, "history manifest entry field closure mismatch")
        require(isinstance(row["round"], int) and not isinstance(row["round"], bool) and 1 <= row["round"] <= MAX_AUDIT_ROUNDS, "history manifest round is outside 1..20")
        require(row["kind"] in {"audit", "resolution"}, "history manifest kind mismatch")
        expected_path = f"docs/audits/round-{row['round']:02d}-{row['kind']}.md"
        require(row["path"] == expected_path and expected_path in HISTORY_PATH_UNIVERSE, "history manifest path/round relation mismatch")
        require(re.fullmatch(r"[0-9a-f]{64}", row["raw_sha256"]) is not None, "history manifest raw digest shape mismatch")
        pairs.append((row["round"], row["kind"]))
        paths.append(row["path"])
    require(len(pairs) == len(set(pairs)) and len(paths) == len(set(paths)), "history manifest has duplicate round/kind/path")
    latest_round = max(round_number for round_number, _ in pairs)
    require({round_number for round_number, _ in pairs} == set(range(1, latest_round + 1)), "history manifest rounds are not continuous from 1")
    for round_number in range(1, latest_round):
        require({kind for value, kind in pairs if value == round_number} == {"audit", "resolution"}, f"completed history round is not an audit/resolution pair: {round_number}")
    require((latest_round, "audit") in pairs, "history latest audit is missing")
    expected_order = [
        (round_number, kind)
        for round_number in range(1, latest_round + 1)
        for kind in ("audit", "resolution")
        if (round_number, kind) in set(pairs)
    ]
    require(pairs == expected_order, "history manifest entries are not in round/kind order")
    return tuple(paths)


def history_paths_from_manifest(contracts: ContractSet) -> tuple[str, ...]:
    raw = contracts.reader.read_bytes(HISTORY_MANIFEST_REL, contracts.bounds["artifact_raw_bytes_max"])
    manifest = decode_json(HISTORY_MANIFEST_REL, raw, contracts.bounds).document
    return history_paths_from_manifest_document(manifest)


def validate_history_manifest(contracts: ContractSet, current_status: dict[str, Any]) -> None:
    manifest_raw = contracts.reader.read_bytes(HISTORY_MANIFEST_REL, contracts.bounds["artifact_raw_bytes_max"])
    manifest = decode_json(HISTORY_MANIFEST_REL, manifest_raw, contracts.bounds).document
    history_paths = history_paths_from_manifest_document(manifest)
    entries = manifest["entries"]
    require(tuple(row["path"] for row in entries) == history_paths, "history actual path set differs from manifest-derived closure")
    for row in entries:
        raw = contracts.reader.read_bytes(row["path"], contracts.bounds["artifact_raw_bytes_max"])
        require(sha256(raw) == row["raw_sha256"], f"protected history raw digest mismatch: {row['path']}")

    latest = manifest["latest"]
    require(isinstance(latest, dict) and latest.get("round") == max(row["round"] for row in entries), "history latest round mismatch")
    round_number = latest["round"]
    audit = latest.get("audit")
    require(isinstance(audit, dict) and set(audit) == {"path", "raw_sha256", "first_line", "verdict", "issue_ids"}, "history latest audit field closure mismatch")
    require(audit["path"] == f"docs/audits/round-{round_number:02d}-audit.md", "history latest audit path relation mismatch")
    audit_raw = contracts.reader.read_bytes(audit["path"], contracts.bounds["artifact_raw_bytes_max"])
    audit_text = audit_raw.decode("utf-8")
    issue_ids = re.findall(rf"^## (AQ-R{round_number}-\d{{3}})\b", audit_text, re.MULTILINE)
    require(audit["raw_sha256"] == sha256(audit_raw), "history latest audit raw digest mismatch")
    require(audit["first_line"] == audit_text.splitlines()[0] == f"# {audit['verdict']}", "history audit first-line/verdict mismatch")
    require(audit["issue_ids"] == issue_ids == [f"AQ-R{round_number}-{number:03d}" for number in range(1, len(issue_ids) + 1)], "history audit issue set/order mismatch")

    state = latest.get("state")
    if state == "ISSUES_OPEN":
        require(set(latest) in (
            {"round", "state", "audit", "resolution", "gate_status"},
            {"round", "state", "audit", "resolution", "blocker", "gate_status"},
        ), "open history latest field closure mismatch")
        require(issue_ids and audit["verdict"] == f"FAIL_WITH_{len(issue_ids)}_ISSUES", "open history audit verdict/count mismatch")
        resolution = latest.get("resolution")
        require(isinstance(resolution, dict) and set(resolution) == {"path", "raw_sha256", "first_line", "statuses"}, "history latest resolution field closure mismatch")
        require(resolution["path"] == f"docs/audits/round-{round_number:02d}-resolution.md", "history latest resolution path relation mismatch")
        resolution_raw = contracts.reader.read_bytes(resolution["path"], contracts.bounds["artifact_raw_bytes_max"])
        resolution_text = resolution_raw.decode("utf-8")
        statuses = [
            {"issue_id": issue_id, "status": status}
            for issue_id, status in re.findall(rf"^## (AQ-R{round_number}-\d{{3}}) — ([A-Z_]+)$", resolution_text, re.MULTILINE)
        ]
        require(resolution["raw_sha256"] == sha256(resolution_raw), "history latest resolution raw digest mismatch")
        require(resolution["first_line"] == resolution_text.splitlines()[0] and resolution["statuses"] == statuses, "history resolution first-line/status mismatch")
        require([row["issue_id"] for row in statuses] == issue_ids, "history resolution issue set/order mismatch")
        require(all(row["status"] in {"FIXED", "BLOCKED_USER_DECISION", "REJECTED_NOT_VALID"} for row in statuses), "history resolution status vocabulary mismatch")
        blockers = [row for row in statuses if row["status"] == "BLOCKED_USER_DECISION"]
        if blockers:
            require(len(blockers) == 1 and latest.get("blocker") == blockers[0], "history blocker relation mismatch")
        else:
            require("blocker" not in latest, "history blocker must be absent without a blocked resolution")
        require(latest["gate_status"] == "ISSUES_OPEN_NOT_GATE_0A", "open history gate status mismatch")
        expected_current = {
            "status_kind": "ISSUES_OPEN",
            "design_version": current_status.get("design_version"),
            "revision_round": round_number,
            "latest_audit_path": audit["path"],
            "latest_audit_verdict": audit["verdict"],
            "latest_issue_ids": issue_ids,
            "latest_resolution_path": resolution["path"],
            "latest_resolution_statuses": statuses,
            "gate_status": latest["gate_status"],
        }
        if blockers:
            expected_current.update({"current_blocker_id": blockers[0]["issue_id"], "current_blocker_status": blockers[0]["status"]})
        require(current_status == expected_current, "current open status/history projection mismatch")
        validate_detached_history_no_self_reference(resolution_raw, manifest_raw, sha256(resolution_raw), sha256(manifest_raw))
    elif state == "ZERO_ISSUES":
        require(set(latest) == {"round", "state", "audit", "gate_status"}, "zero history latest field closure mismatch")
        require(audit["verdict"] == "PASS_ZERO_ISSUES" and issue_ids == [] and audit["issue_ids"] == [], "zero history audit must have PASS_ZERO_ISSUES and an empty issue set")
        require((round_number, "resolution") not in {(row["round"], row["kind"]) for row in entries}, "zero history round must not have a resolution")
        require(latest["gate_status"] == "ZERO_ISSUES_AUDIT_CONFIRMED", "zero history gate status mismatch")
        expected_current = {
            "status_kind": "ZERO_ISSUES",
            "design_version": current_status.get("design_version"),
            "revision_round": round_number,
            "latest_audit_path": audit["path"],
            "latest_audit_verdict": "PASS_ZERO_ISSUES",
            "latest_issue_ids": [],
            "gate_status": latest["gate_status"],
        }
        require(current_status == expected_current, "current zero status/history projection mismatch")
        validate_detached_history_no_self_reference(b"", manifest_raw, sha256(b""), sha256(manifest_raw))
    else:
        raise ValidationError("history latest state discriminator mismatch")


def validate_projections(contracts: ContractSet) -> None:
    design = contracts.docs["docs/design-proposal.md"]
    current_status = contracts.artifacts["docs/contracts/core-safety-contract-v1.json"].document["current_design_status"]
    validate_history_manifest(contracts, current_status)
    status_inner = "\n```json\n" + canonical_bytes(current_status).decode("utf-8") + "\n```\n"
    for path in LIVE_DOC_PATHS:
        require(
            marker_inner(contracts.docs[path], "AQ-GENERATED-CURRENT-STATUS-V1") == status_inner,
            f"current design status projection mismatch: {path}",
        )
    for path in ("docs/contracts/core-safety-contract-v1.json", "docs/contracts/operation-contract-v1.json"):
        artifact = contracts.artifacts[path].document
        contract = artifact["projection_contract"]
        expected = projection_inner(artifact, contract["source_json_pointers"])
        require(marker_inner(design, contract["markdown_marker"]) == expected, f"Markdown projection mismatch: {contract['markdown_marker']}")
        require(sha256(unicodedata.normalize("NFC", expected).encode("utf-8")) == contract["projection_sha256"], f"projection hash mismatch: {contract['projection_id']}")
    expected_pin_projection, _ = artifact_pin_projection(contracts.registry.document)
    pin_inner = marker_inner(design, "AQ-GENERATED-ARTIFACT-PINS-V1")
    match = re.fullmatch(r"\n```json\n([^\n]+)\n```\n", pin_inner)
    require(match is not None, "artifact pin projection has unstable Markdown shape")
    try:
        actual_pin_projection = json.loads(match.group(1), object_pairs_hook=duplicate_rejector, parse_int=parse_int, parse_float=reject_float, parse_constant=reject_constant)
    except Exception as error:
        raise ValidationError(f"artifact pin projection is not strict JSON: {error}") from error
    require(actual_pin_projection == expected_pin_projection, "design artifact pin projection differs from registry rows")
    require(match.group(1).encode("utf-8") == canonical_bytes(expected_pin_projection), "artifact pin projection is not canonical JSON")
    anchor = domain_hash(REGISTRY_DOMAIN, contracts.registry.document)
    matches = re.findall(r"registry canonical 摘要为 `([0-9a-f]{64})`", design)
    require(matches == [anchor], "design registry anchor mismatch or duplicate")


def _markdown_slug(text: str) -> str:
    text = re.sub(r"[`*_~]", "", unicodedata.normalize("NFC", text).casefold())
    kept = "".join(character for character in text if character.isalnum() or character in {"_", "-"} or character.isspace())
    return re.sub(r"\s", "-", kept)


def _markdown_headings(source: str) -> list[tuple[int, str, int]]:
    output: list[tuple[int, str, int]] = []
    fence: str | None = None
    for line_number, line in enumerate(source.splitlines(), 1):
        fence_match = re.match(r"^\s*(`{3,}|~{3,})", line)
        if fence_match:
            marker = fence_match.group(1)[0]
            if fence is None:
                fence = marker
            elif marker == fence:
                fence = None
            continue
        if fence is not None:
            continue
        match = re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", line)
        if match:
            output.append((len(match.group(1)), match.group(2), line_number))
    require(fence is None, "Markdown heading lint found an unclosed fence")
    return output


def validate_heading_numbers_and_anchors(contracts: ContractSet) -> int:
    anchors: dict[str, set[str]] = {}
    numbered_count = 0
    for path, source in contracts.docs.items():
        headings = _markdown_headings(source)
        slug_counts: Counter[str] = Counter()
        path_anchors: set[str] = set()
        seen_numbers: set[tuple[int, ...]] = set()
        last_sibling: dict[tuple[int, ...], int] = {}
        for level, text, line_number in headings:
            base = _markdown_slug(text)
            require(base, f"empty Markdown heading anchor: {path}:{line_number}")
            suffix = slug_counts[base]
            slug_counts[base] += 1
            slug = base if suffix == 0 else f"{base}-{suffix}"
            require(slug not in path_anchors, f"duplicate Markdown anchor: {path}#{slug}")
            path_anchors.add(slug)
            number_match = re.match(r"^(\d+(?:\.\d+)*)\.?\s+", text)
            if number_match is None:
                continue
            number = tuple(int(part) for part in number_match.group(1).split("."))
            require(len(number) == level - 1, f"numbered heading depth/level mismatch: {path}:{line_number}")
            require(number not in seen_numbers, f"duplicate numbered heading: {path}:{line_number}")
            parent = number[:-1]
            require(not parent or parent in seen_numbers, f"numbered heading lacks its parent: {path}:{line_number}")
            prior = last_sibling.get(parent)
            require(prior is None or number[-1] > prior, f"numbered headings are not strictly monotonic: {path}:{line_number}")
            last_sibling[parent] = number[-1]
            seen_numbers.add(number)
            numbered_count += 1
        anchors[path] = path_anchors

    link_pattern = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
    for source_path, source in contracts.docs.items():
        for target in link_pattern.findall(source):
            if target.startswith(("http://", "https://", "mailto:")) or "#" not in target:
                continue
            file_part, anchor = target.split("#", 1)
            if not anchor:
                continue
            resolved = source_path if file_part == "" else posixpath.normpath(posixpath.join(posixpath.dirname(source_path), file_part))
            require(resolved in anchors, f"Markdown link points outside the live document set: {source_path}->{target}")
            require(anchor in anchors[resolved], f"Markdown anchor is missing: {source_path}->{target}")
    return numbered_count


def _contracts_with_artifact(contracts: ContractSet, path: str, document: dict[str, Any]) -> ContractSet:
    artifacts = dict(contracts.artifacts)
    loaded = artifacts[path]
    artifacts[path] = LoadedJson(path=loaded.path, raw=loaded.raw, document=document)
    return ContractSet(
        reader=contracts.reader,
        registry=contracts.registry,
        schemas=contracts.schemas,
        artifacts=artifacts,
        fixtures=contracts.fixtures,
        docs=contracts.docs,
        bounds=contracts.bounds,
    )


def _contracts_with_doc(contracts: ContractSet, path: str, source: str) -> ContractSet:
    docs = dict(contracts.docs)
    docs[path] = source
    return ContractSet(
        reader=contracts.reader,
        registry=contracts.registry,
        schemas=contracts.schemas,
        artifacts=contracts.artifacts,
        fixtures=contracts.fixtures,
        docs=docs,
        bounds=contracts.bounds,
    )


def validate_semantic_negative_qa(contracts: ContractSet) -> int:
    """Prove the new semantic oracles reject adversarial, independently mutated values."""

    operation_path = "docs/contracts/operation-contract-v1.json"
    operation = contracts.artifacts[operation_path].document
    consent_index = next(
        index for index, row in enumerate(operation["predicate_definitions"])
        if row["predicate_id"] == "consent-required-for-status-projection"
    )
    consent_mutants: list[tuple[str, dict[str, Any]]] = []

    def operation_mutant() -> dict[str, Any]:
        return copy.deepcopy(operation)

    mutant = operation_mutant()
    mutant["predicate_definitions"][consent_index]["expression"]["right"]["literal"] = "feishu_private"
    consent_mutants.append(("consent-literal-substitution", mutant))
    mutant = operation_mutant()
    mutant["predicate_definitions"][consent_index]["expression"]["op"] = "not_equal"
    consent_mutants.append(("consent-operator-substitution", mutant))
    mutant = operation_mutant()
    mutant["predicate_definitions"][consent_index]["control_flow"]["false"] = {
        "action": "execute_stage", "typed_result": "llm_consent_required"
    }
    consent_mutants.append(("consent-false-branch-executes", mutant))
    mutant = operation_mutant()
    mutant["predicate_definitions"][consent_index]["semantic_vectors"] = [
        row for row in mutant["predicate_definitions"][consent_index]["semantic_vectors"]
        if row["vector_id"] != "consent-missing"
    ]
    consent_mutants.append(("consent-missing-vector-removed", mutant))
    mutant = operation_mutant()
    unknown = next(
        row for row in mutant["predicate_definitions"][consent_index]["semantic_vectors"]
        if row["vector_id"] == "consent-unknown"
    )
    unknown["input_status"] = "complete"
    unknown["predicate_result"] = False
    unknown["action"] = "skip_stage"
    unknown["typed_result"] = "llm_consent_not_applicable"
    consent_mutants.append(("consent-unknown-audience-accepted", mutant))
    mutant = operation_mutant()
    feishu = next(
        row for row in mutant["predicate_definitions"][consent_index]["semantic_vectors"]
        if row["vector_id"] == "consent-feishu-private"
    )
    feishu["predicate_result"] = True
    consent_mutants.append(("consent-audience-truth-table-drift", mutant))
    mutant = operation_mutant()
    status_step = next(
        step for path in mutant["paths"] if path["path_id"] == "status-none-v1"
        for step in path["steps"] if step["stage"] == "consent_validate"
    )
    status_step["predicate_branch"]["on_false"] = "execute_stage"
    consent_mutants.append(("consent-path-false-branch-drift", mutant))

    rejected = 0
    for qa_id, document in consent_mutants:
        try:
            validate_operation_semantics(_contracts_with_artifact(contracts, operation_path, document))
        except (ValidationError, KeyError, TypeError, ValueError):
            rejected += 1
        else:
            raise ValidationError(f"semantic consent negative QA did not fail closed: {qa_id}")

    core_path = "docs/contracts/core-safety-contract-v1.json"
    core = contracts.artifacts[core_path].document
    for qa_id, mutate in (
        ("typed-state-wrong-required-field", lambda operation: operation["state_required_fields"].append("wrong_field")),
        ("typed-state-equal-before-after", lambda operation: operation.__setitem__("expected_after_state_sha256", operation["expected_before_state_sha256"])),
    ):
        document = copy.deepcopy(core)
        case = next(
            row for row in document["validation_mutation_contract"]["cases"]
            if row["mutation_spec"]["operation"]["locator_kind"] == "runtime"
        )
        mutate(case["mutation_spec"]["operation"])
        case["mutation_sha256"] = domain_hash(MUTATION_DOMAIN, case["mutation_spec"])
        try:
            validate_core_closure(_contracts_with_artifact(contracts, core_path, document))
        except (ValidationError, KeyError, TypeError, ValueError):
            rejected += 1
        else:
            raise ValidationError(f"semantic typed-state negative QA did not fail closed: {qa_id}")

    heading_path = "docs/provider-contract.md"
    heading_source = contracts.docs[heading_path]
    heading_mutants = (
        ("heading-duplicate-number", heading_source.replace("## 2. ", "## 1. ", 1)),
        ("heading-reverse-order", heading_source.replace("## 2. ", "## 0. ", 1)),
        ("heading-missing-parent", heading_source + "\n\n### 99.1 Orphan QA heading\n"),
        ("heading-missing-anchor", heading_source + "\n\n[Missing QA anchor](#aq-r17-anchor-does-not-exist)\n"),
    )
    for qa_id, source in heading_mutants:
        require(source != heading_source, f"semantic heading QA mutation anchor missing: {qa_id}")
        try:
            validate_heading_numbers_and_anchors(_contracts_with_doc(contracts, heading_path, source))
        except (ValidationError, KeyError, TypeError, ValueError):
            rejected += 1
        else:
            raise ValidationError(f"semantic heading negative QA did not fail closed: {qa_id}")

    try:
        validate_detached_history_no_self_reference(
            b"resolution embeds " + b"a" * 64,
            b"detached manifest",
            "a" * 64,
            "b" * 64,
        )
    except ValidationError:
        rejected += 1
    else:
        raise ValidationError("history self-reference QA did not fail closed")

    require(rejected == 14, f"semantic negative QA count mismatch: {rejected}")
    return rejected


def validate_fixture_references(contracts: ContractSet) -> None:
    bindings = (
        ("docs/contracts/core-safety-contract-v1.json", "docs/contracts/fixtures/core-safety-v1.json"),
        ("docs/contracts/retention-lint-v1.json", "docs/contracts/fixtures/retention-lint-malicious-v1.json"),
    )
    for artifact_path, fixture_path in bindings:
        rows = contracts.artifacts[artifact_path].document["fixture_artifacts"]
        require(len(rows) == 1 and rows[0]["path"] == fixture_path, f"fixture reference path mismatch: {artifact_path}")
        require(rows[0]["canonical_sha256"] == domain_hash(ARTIFACT_DOMAIN, contracts.fixtures[fixture_path].document), f"fixture reference digest mismatch: {artifact_path}")


@dataclass(frozen=True)
class MarkdownLeaf:
    text: str
    code_spans: tuple[str, ...]
    table_headers: tuple[str, ...] = ()
    table_column: int | None = None


def inline_parts(value: Any) -> tuple[str, list[str]]:
    text_parts: list[str] = []
    code_spans: list[str] = []

    def visit(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                visit(item)
            return
        if not isinstance(node, dict) or "t" not in node:
            return
        kind = node["t"]
        content = node.get("c")
        if kind == "Str":
            text_parts.append(content)
        elif kind in ("Space", "SoftBreak", "LineBreak"):
            text_parts.append(" ")
        elif kind == "Code":
            value = content[1]
            text_parts.append(value)
            code_spans.append(value)
        elif kind == "RawInline":
            value = content[1]
            if not (content[0] == "html" and re.fullmatch(r"</?[A-Za-z][^>]*>", value)):
                text_parts.append(value)
        elif kind == "Math":
            text_parts.append(content[1])
        else:
            visit(content)
    visit(value)
    return "".join(text_parts), code_spans


def cell_blocks(cell: list[Any]) -> list[dict[str, Any]]:
    return cell[4]


def table_rows(table: dict[str, Any]) -> list[list[list[Any]]]:
    content = table["c"]
    rows: list[list[list[Any]]] = []
    rows.extend(row[1] for row in content[3][1])
    for body in content[4]:
        rows.extend(row[1] for row in body[2])
        rows.extend(row[1] for row in body[3])
    rows.extend(row[1] for row in content[5][1])
    return rows


def blocks_plain_text(blocks: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for block in blocks:
        if block.get("t") in ("Para", "Plain", "Header"):
            text, _ = inline_parts(block.get("c", [])[-1] if block["t"] == "Header" else block.get("c", []))
            parts.append(text)
        elif block.get("t") == "CodeBlock":
            parts.append(block["c"][1])
    return " ".join(parts).strip()


def pandoc_ast(source: str, parser: dict[str, Any], pandoc_path: str) -> dict[str, Any]:
    completed = subprocess.run(
        [pandoc_path, "-f", parser["reader"], "-t", "json"],
        input=source,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={"PATH": os.environ.get("PATH", "")},
        timeout=15,
        check=False,
    )
    require(completed.returncode == 0, f"Pandoc parse failed: {completed.stderr.strip()}")
    try:
        ast = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise ValidationError("Pandoc emitted invalid JSON") from error
    require(ast["pandoc-api-version"] == parser["pandoc_api_version"], "Pandoc API version mismatch")
    return ast


def markdown_leaves(ast: dict[str, Any]) -> list[MarkdownLeaf]:
    leaves: list[MarkdownLeaf] = []

    def visit(node: Any, table_headers: tuple[str, ...] = (), table_column: int | None = None) -> None:
        if isinstance(node, list):
            for item in node:
                visit(item, table_headers, table_column)
            return
        if not isinstance(node, dict) or "t" not in node:
            return
        kind = node["t"]
        content = node.get("c")
        if kind in ("Para", "Plain"):
            text, codes = inline_parts(content)
            leaves.append(MarkdownLeaf(text, tuple(codes), table_headers, table_column))
            return
        if kind == "Header":
            text, codes = inline_parts(content[2])
            leaves.append(MarkdownLeaf(text, tuple(codes), table_headers, table_column))
            return
        if kind == "CodeBlock":
            leaves.append(MarkdownLeaf(content[1], (content[1],), table_headers, table_column))
            return
        if kind == "RawBlock":
            leaves.append(MarkdownLeaf(content[1], (), table_headers, table_column))
            return
        if kind == "Table":
            rows = table_rows(node)
            if not rows:
                return
            headers = tuple(blocks_plain_text(cell_blocks(cell)) for cell in rows[0])
            for row in rows:
                for index, cell in enumerate(row):
                    visit(cell_blocks(cell), headers, index)
            return
        visit(content, table_headers, table_column)

    visit(ast["blocks"])
    return leaves


def _table_headers(table: dict[str, Any]) -> list[str]:
    rows = table_rows(table)
    require(rows, "located Markdown table is empty")
    return [blocks_plain_text(cell_blocks(cell)) for cell in rows[0]]


def _normalized_heading(block: dict[str, Any]) -> tuple[str, str]:
    text, _ = inline_parts(block["c"][2])
    normalized = " ".join(unicodedata.normalize("NFC", text).split())
    return normalized, block["c"][1][0]


def _heading_paths(ast: dict[str, Any]) -> list[tuple[int, dict[str, Any], tuple[tuple[int, int, str, str], ...]]]:
    output: list[tuple[int, dict[str, Any], tuple[tuple[int, int, str, str], ...]]] = []
    stack: list[tuple[int, tuple[tuple[int, int, str, str], ...]]] = []
    sibling_counts: dict[tuple[tuple[tuple[int, int, str, str], ...], int], int] = defaultdict(int)
    for index, block in enumerate(ast["blocks"]):
        if block.get("t") != "Header":
            continue
        level = block["c"][0]
        while stack and stack[-1][0] >= level:
            stack.pop()
        parent = stack[-1][1] if stack else ()
        key = (parent, level)
        sibling_counts[key] += 1
        text, identifier = _normalized_heading(block)
        path = parent + ((level, sibling_counts[key], text, identifier),)
        stack.append((level, path))
        output.append((index, block, path))
    return output


def _locate_exact_table(ast: dict[str, Any], locator: dict[str, Any], expected_headers: list[str], label: str) -> dict[str, Any]:
    expected_path = tuple((row["level"], row["sibling_ordinal"], row["normalized_text"], row["identifier"]) for row in locator["heading_path"])
    headings = _heading_paths(ast)
    matches = [(index, block) for index, block, path in headings if path == expected_path]
    require(len(matches) == 1, f"{label} heading path must resolve exactly once")
    for segment in expected_path:
        same_text = [block for _, block, _ in headings if block["c"][0] == segment[0] and _normalized_heading(block) == (segment[2], segment[3])]
        require(len(same_text) == 1, f"{label} exact heading text/identifier is duplicated or ambiguous: {segment[2]}")
    heading_index, heading = matches[0]
    heading_level = heading["c"][0]
    section_end = len(ast["blocks"])
    for index in range(heading_index + 1, len(ast["blocks"])):
        block = ast["blocks"][index]
        if block.get("t") == "Header" and block["c"][0] <= heading_level:
            section_end = index
            break
    section_tables = [
        block for block in ast["blocks"][heading_index + 1:section_end]
        if block.get("t") == "Table"
    ]
    ordinal = locator["table_ordinal"]
    require(1 <= ordinal <= len(section_tables), f"{label} table ordinal is out of range")
    selected = section_tables[ordinal - 1]
    require(_table_headers(selected) == expected_headers, f"{label} table headers differ at the exact locator")
    exact_tables = [block for block in ast["blocks"] if block.get("t") == "Table" and _table_headers(block) == expected_headers]
    require(len(exact_tables) == 1 and exact_tables[0] is selected, f"{label} table is duplicated, moved, or ambiguous")
    for block in ast["blocks"]:
        if block.get("t") != "Table" or block is selected:
            continue
        headers = _table_headers(block)
        overlap = sum(1 for index, expected in enumerate(expected_headers) if index < len(headers) and headers[index] == expected)
        require(overlap < 2, f"{label} has a confusing similar-header table")
    return selected


def _exact_code_cell(cell: list[Any], label: str) -> str:
    blocks = cell_blocks(cell)
    require(len(blocks) == 1 and blocks[0].get("t") in {"Plain", "Para"}, f"{label} must be one inline-code cell")
    text, codes = inline_parts(blocks[0]["c"])
    require(len(codes) == 1 and text == codes[0], f"{label} must contain exactly one code span and no prose")
    return codes[0]


def extract_retention_registry_and_inventory(ast: dict[str, Any], artifact: dict[str, Any]) -> tuple[dict[str, list[str]], frozenset[str]]:
    registry_contract = artifact["retention_entry_registry"]
    retention_locator = artifact["locations"]["retention_table_ttl_cells"]
    retention_table = _locate_exact_table(
        ast,
        retention_locator,
        registry_contract["expected_headers"],
        "retention registry",
    )
    require(retention_locator["column_ordinal"] == 3, "retention TTL column ordinal drifted")
    require(registry_contract["id_column_ordinal"] == 1, "retention ID column ordinal drifted")
    ret_ids: list[str] = []
    for row in table_rows(retention_table)[1:]:
        require(len(row) == len(registry_contract["expected_headers"]), "retention registry row width mismatch")
        ret_id = _exact_code_cell(row[registry_contract["id_column_ordinal"] - 1], "retention entry ID")
        require(re.fullmatch(registry_contract["id_pattern"], ret_id) is not None, f"invalid retention entry ID: {ret_id}")
        ret_ids.append(ret_id)
    require(ret_ids and len(ret_ids) == len(set(ret_ids)), "retention entry IDs are empty or duplicated")

    inventory_contract = artifact["inventory"]
    inventory_table = _locate_exact_table(
        ast,
        inventory_contract,
        inventory_contract["expected_headers"],
        "persistence inventory",
    )
    owners: dict[str, list[str]] = defaultdict(list)
    for row in table_rows(inventory_table)[1:]:
        require(len(row) == len(inventory_contract["expected_headers"]), "inventory table row width mismatch")
        surface = _exact_code_cell(row[inventory_contract["surface_id_column"] - 1], "inventory surface ID")
        owner = _exact_code_cell(row[inventory_contract["owner_column"] - 1], "inventory owner ID")
        require(re.fullmatch(r"[a-z][a-z0-9_]{0,63}", surface) is not None, f"invalid persistence surface ID: {surface}")
        require(owner in ret_ids, f"inventory owner is not a byte-exact retention entry ID: {owner}")
        owners[surface].append(owner)
    require(owners and all(len(values) == 1 for values in owners.values()), "persistence inventory owner is empty or not unique")
    actual_joins = [
        {"surface_id": surface, "owner_id": owners[surface][0]}
        for surface in sorted(owners, key=lambda value: value.encode("utf-8"))
    ]
    require(actual_joins == inventory_contract["expected_owner_joins"], "persistence inventory owner join projection drifted")
    return dict(owners), frozenset(ret_ids)


def has_duration(text: str) -> bool:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    ascii_duration = re.search(
        r"(?<![A-Za-z0-9_])(?:[0-9]{1,9}(?:\.[0-9]{1,9})?[e][+-]?[0-9]{1,3}|[0-9]{1,9})\s*(?:milliseconds?|seconds?|minutes?|hours?|days?|weeks?|months?|years?|ms|sec|mins?|[smhd]|毫秒|分钟|小时|星期|个月|秒|天|日|周|月|年)(?![A-Za-z0-9_])",
        normalized,
    )
    word_duration = re.search(
        r"(?<![\w])(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand)(?:\s+(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|twenty|thirty|hundred|thousand))*\s+(?:milliseconds?|seconds?|minutes?|hours?|days?|weeks?|months?|years?)(?![\w])",
        normalized,
    )
    chinese_duration = re.search(r"[零〇一二两三四五六七八九十百千万亿]{1,16}(?:毫秒|秒|分钟|小时|天|日|周|星期|个月|月|年)", normalized)
    return ascii_duration is not None or word_duration is not None or chinese_duration is not None


def persistence_signal(text: str, grammar: dict[str, Any]) -> bool:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    lexer = grammar["persistence_signal_lexer"]

    require(lexer["grammar_id"] == "aq-persistence-signal-grammar-v3" and lexer["version"] == 3, "unknown persistence signal grammar")

    def spans(terms: list[str]) -> list[tuple[int, int]]:
        candidates: list[tuple[int, int]] = []
        for raw_term in sorted(terms, key=lambda value: (-len(value), value.encode("utf-8"))):
            term = unicodedata.normalize("NFKC", raw_term).casefold()
            if term.isascii():
                pattern = r"(?<![\w])" + re.escape(term).replace(r"\ ", r"\s+") + r"(?![\w])"
                candidates.extend(match.span() for match in re.finditer(pattern, normalized))
            else:
                start = 0
                while True:
                    index = normalized.find(term, start)
                    if index < 0:
                        break
                    candidates.append((index, index + len(term)))
                    start = index + len(term)
        candidates.sort(key=lambda item: (item[0], -(item[1] - item[0]), item[1]))
        output: list[tuple[int, int]] = []
        for candidate in candidates:
            if any(existing[0] <= candidate[0] and existing[1] >= candidate[1] for existing in output):
                continue
            output.append(candidate)
        return output

    class_spans = {name: spans(terms) for name, terms in lexer["token_classes"].items()}
    require(set(class_spans) == {"medium", "sensitive_object", "write_action"}, "persistence token class closure mismatch")
    for rule in lexer["phrase_rules"]:
        required = set(rule["required_classes"])
        require(all(set(order) == required and len(order) == len(required) for order in rule["accepted_orders"]), f"persistence phrase order/class mismatch: {rule['rule_id']}")
        for order in rule["accepted_orders"]:
            combinations: list[list[tuple[int, int]]] = [[]]
            for class_name in order:
                combinations = [prefix + [span] for prefix in combinations for span in class_spans[class_name]]
            for combination in combinations:
                if any(left[1] > right[0] for left, right in zip(combination, combination[1:])):
                    continue
                intervening = " ".join(normalized[left[1]:right[0]] for left, right in zip(combination, combination[1:]))
                tokens = re.findall(r"[A-Za-z0-9_]+|[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]", intervening)
                if len(tokens) <= rule["max_intervening_tokens"]:
                    return True
    return False


def evaluate_retention_ast(
    ast: dict[str, Any],
    grammar: dict[str, Any],
    owners: dict[str, list[str]],
    retention_ids: frozenset[str],
    allowed_leaf_digests: frozenset[str] = frozenset(),
) -> tuple[str, list[tuple[str, str, str]], set[str]]:
    leaves = markdown_leaves(ast)
    directives: list[tuple[str, str, str]] = []
    used_exceptions: set[str] = set()
    retention_terms = [term.casefold() for term in grammar["retention_context"]["before_or_after_terms"]]
    runtime_terms = [term.casefold() for term in grammar["allowed_duration_contexts"][2]["required_terms"]]
    for leaf in leaves:
        normalized = unicodedata.normalize("NFKC", leaf.text).casefold()
        exact_in_leaf: list[tuple[str, str, str]] = []
        prose_without_records = leaf.text
        for code in leaf.code_spans:
            if code == "persist:v1:<surface_id>:<operation>:<owner_id>":
                continue
            match = DIRECTIVE_RE.fullmatch(code)
            if match:
                surface, operation, owner = match.groups()
                if surface not in owners or len(owners[surface]) != 1:
                    return "reject", directives, used_exceptions
                if owners[surface][0] != owner:
                    return "reject", directives, used_exceptions
                if owner not in retention_ids:
                    return "reject", directives, used_exceptions
                exact_in_leaf.append((surface, operation, owner))
                directives.append((surface, operation, owner))
                if prose_without_records.count(code) != 1:
                    return "reject", directives, used_exceptions
                prose_without_records = prose_without_records.replace(code, "", 1)
            elif ANY_DIRECTIVE_RE.match(code):
                return "reject", directives, used_exceptions
        if len(exact_in_leaf) != len(set(exact_in_leaf)):
            return "reject", directives, used_exceptions
        leaf_payload = {
            "text": leaf.text,
            "code_spans": list(leaf.code_spans),
            "table_headers": list(leaf.table_headers),
            "table_column": leaf.table_column,
        }
        leaf_digest = sha256(canonical_bytes(leaf_payload))
        exception_allowed = leaf_digest in allowed_leaf_digests
        # A record is the complete normative persistence declaration.  It is
        # never a leaf-wide permit for adjacent prose: after removing exact
        # records, any persistence signal remains independently rejectable.
        # This makes a legal A record plus an unregistered B statement fail
        # closed, including cross-sentence and multi-signal variants.
        if persistence_signal(prose_without_records, grammar):
            if not exception_allowed:
                return "reject", directives, used_exceptions
            used_exceptions.add(leaf_digest)
        if has_duration(leaf.text):
            retention_signal = any(term in normalized for term in retention_terms)
            allowed_retention_owner = (
                leaf.table_headers[:4] == ("条目 ID", "数据", "保存期限与起点", "到期动作")
                and leaf.table_column == 2
            )
            allowed_action_owner = any(code.startswith("ACTION_TTL =") for code in leaf.code_spans)
            named_constant = any(re.fullmatch(r"[A-Z][A-Z0-9_]{1,63}\s*=\s*.+", code) for code in leaf.code_spans)
            runtime = any(term in normalized for term in runtime_terms)
            if retention_signal and not (allowed_retention_owner or allowed_action_owner):
                if not exception_allowed:
                    return "reject", directives, used_exceptions
                used_exceptions.add(leaf_digest)
            if not retention_signal and not (runtime or named_constant or allowed_retention_owner or allowed_action_owner):
                # A duration without retention language is descriptive, not a new TTL owner.
                pass
    return "accept", directives, used_exceptions


def validate_retention_structural_qa(
    security_source: str,
    artifact: dict[str, Any],
    parser: dict[str, Any],
    pandoc_path: str,
) -> int:
    inventory_row = "| `subject_metadata_observed` | SQLite subject metadata | `RET-SUBJECT-METADATA-OBSERVED` |"
    require(security_source.count(inventory_row) == 1, "retention QA inventory anchor is not unique")
    unknown_inventory_row = inventory_row.replace("RET-SUBJECT-METADATA-OBSERVED", "RET-UNKNOWN-OWNER")
    duplicate_inventory = """

#### 10.1.2 QA copied inventory

| surface_id | owner/介质 | 唯一生命周期源 |
| --- | --- | --- |
| `subject_metadata_observed` | SQLite subject metadata | `RET-SUBJECT-METADATA-OBSERVED` |
| `migration_temp_claim` | SQLite claim | `RET-MIGRATION-TEMP-CLAIM` |
| `migration_temp_file` | config 父目录 regular file | `RET-MIGRATION-TEMP-CLAIM` |
"""
    duplicate_retention = security_source.replace("| `RET-LOG` |", "| `RET-SNAPSHOT` |", 1)
    both_unknown = security_source.replace(inventory_row, unknown_inventory_row, 1).replace(
        "persist:v1:subject_metadata_observed:update:RET-SUBJECT-METADATA-OBSERVED",
        "persist:v1:subject_metadata_observed:update:RET-UNKNOWN-OWNER",
        1,
    )
    wrong_locator_artifact = json.loads(json.dumps(artifact))
    wrong_locator_artifact["inventory"]["heading_path"][-1]["sibling_ordinal"] += 1
    renamed_heading = security_source.replace("### 10.1 唯一保存期限表", "### 10.1 唯一保存期限清单", 1)
    synonym_heading = security_source.replace("### 10.1 唯一保存期限表", "### 10.1 权威保存期限表", 1)
    same_position_copy = security_source.replace("### 10.1 唯一保存期限表", "### 10.1 唯一保存期限表\n\n### 10.1 唯一保存期限表", 1)
    preceding_heading = security_source.replace("### 10.1 唯一保存期限表", "### 10.0 前置结构探针\n\n### 10.1 唯一保存期限表", 1)
    cross_heading_move = security_source.replace("### 10.1 唯一保存期限表", "## 10.1 唯一保存期限表", 1)
    duplicate_exact_heading = security_source + "\n\n### 10.1 唯一保存期限表\n\nDuplicate heading probe.\n"
    qa_inputs = [
        ("unknown-owner", security_source.replace(inventory_row, unknown_inventory_row, 1), artifact),
        ("copied-inventory", security_source + duplicate_inventory, artifact),
        ("wrong-heading-ordinal", security_source, wrong_locator_artifact),
        ("duplicate-retention-id", duplicate_retention, artifact),
        ("inventory-and-record-unknown-owner", both_unknown, artifact),
        ("renamed-heading", renamed_heading, artifact),
        ("synonym-heading", synonym_heading, artifact),
        ("same-position-heading-copy", same_position_copy, artifact),
        ("preceding-heading-insert", preceding_heading, artifact),
        ("cross-heading-move", cross_heading_move, artifact),
        ("duplicate-exact-heading", duplicate_exact_heading, artifact),
    ]
    for qa_id, source, qa_artifact in qa_inputs:
        rejected = False
        try:
            extract_retention_registry_and_inventory(pandoc_ast(source, parser, pandoc_path), qa_artifact)
        except (ValidationError, KeyError, IndexError, TypeError, ValueError):
            rejected = True
        require(rejected, f"retention structural QA did not fail closed: {qa_id}")
    return len(qa_inputs)


def validate_retention(contracts: ContractSet, tooling: dict[str, Any]) -> tuple[int, int, int]:
    artifact = contracts.artifacts["docs/contracts/retention-lint-v1.json"].document
    parser = artifact["parser"]
    lexer = artifact["detector_grammar"]["persistence_signal_lexer"]
    require(lexer["grammar_id"] == "aq-persistence-signal-grammar-v3" and lexer["version"] == 3, "persistence grammar version mismatch")
    require(set(lexer["token_classes"]) == {"medium", "sensitive_object", "write_action"}, "persistence token class set mismatch")
    for class_name, terms in lexer["token_classes"].items():
        stable_unique(terms, f"persistence {class_name} terms")
    require([row["rule_id"] for row in lexer["phrase_rules"]] == ["sensitive-write-medium", "write-medium"], "persistence phrase rule order/set mismatch")
    directive_ast = artifact["detector_grammar"]["persistence_directive_ast"]
    require(directive_ast["exact_pattern"] == "persist:v1:<surface_id>:<operation>:<owner_id>", "persistence directive pattern mismatch")
    require(directive_ast["segment_order"] == ["literal:persist", "literal:v1", "capture:surface_id", "enum:operation", "capture:owner_id"], "persistence directive segment order mismatch")
    require(directive_ast["operation_enum"] == ["create", "delete", "update", "write"], "persistence operation enum mismatch")
    require(directive_ast["owner_join_key"] == ["surface_id", "owner_id"] and directive_ast["inventory_owner_cardinality"] == 1, "persistence owner join contract mismatch")
    require(directive_ast["record_boundary"] == "one-exact-Pandoc-Code-span" and directive_ast["adjacent_prose_authorization"] == "forbidden", "persistence record boundary mismatch")
    require(parser["version_exact"] == tooling["runtime"]["pandoc_version_exact"], "retention parser/runtime Pandoc version mismatch")
    require(parser["reader"] == parser["base_reader"] + "+" + "+".join(parser["extension_set"]), "Pandoc reader/extension closure mismatch")
    require(tuple(artifact["inputs"]) == LIVE_DOC_PATHS, "retention live input list mismatch")
    require(set(artifact["excluded_fixture_files"]).isdisjoint(artifact["inputs"]), "retention fixture leaked into live inputs")
    exceptions = artifact["live_leaf_exceptions"]
    exception_keys = [(row["path"], row["leaf_sha256"]) for row in exceptions]
    require(exception_keys == sorted(exception_keys, key=lambda row: (row[0].encode("utf-8"), row[1].encode("ascii"))), "live retention exceptions are not deterministically sorted")
    require(len(exception_keys) == len(set(exception_keys)), "duplicate live retention exception")
    require(all(row["path"] in LIVE_DOC_PATHS for row in exceptions), "live retention exception has unknown input path")
    exceptions_by_path: dict[str, frozenset[str]] = {
        path: frozenset(row["leaf_sha256"] for row in exceptions if row["path"] == path)
        for path in LIVE_DOC_PATHS
    }
    security_ast = pandoc_ast(contracts.docs["docs/security-model.md"], parser, tooling["pandoc_path"])
    owners, retention_ids = extract_retention_registry_and_inventory(security_ast, artifact)
    require(
        validate_retention_structural_qa(
            contracts.docs["docs/security-model.md"], artifact, parser, tooling["pandoc_path"]
        ) == 11,
        "retention structural QA count mismatch",
    )
    live_directives: list[tuple[str, str, str]] = []
    for path in LIVE_DOC_PATHS:
        ast = security_ast if path == "docs/security-model.md" else pandoc_ast(contracts.docs[path], parser, tooling["pandoc_path"])
        verdict, directives, used_exceptions = evaluate_retention_ast(ast, artifact["detector_grammar"], owners, retention_ids, exceptions_by_path[path])
        require(verdict == "accept", f"retention live scan rejected: {path}")
        require(used_exceptions == set(exceptions_by_path[path]), f"live retention exception is dangling or no longer required: {path}")
        live_directives.extend(directives)
    require(len(live_directives) == 9, f"expected 9 live persistence directives, got {len(live_directives)}")
    require(set(surface for surface, _, _ in live_directives) == set(owners), "inventory surface lacks live directive or live directive lacks inventory owner")

    fixture_path = artifact["fixture_artifacts"][0]["path"]
    fixture = contracts.fixtures[fixture_path].document
    utf8_sorted([case["fixture_id"] for case in fixture["cases"]], "retention fixture IDs")
    required_synonym_cases = {
        "persist-cache-file-without-surface-id", "persist-chinese-config-directory-without-surface-id",
        "persist-chinese-keychain-without-surface-id", "persist-chinese-keystore-without-surface-id",
        "persist-chinese-local-file-without-surface-id", "persist-config-directory-without-surface-id",
        "persist-data-file-without-surface-id", "persist-directory-without-surface-id",
        "persist-file-without-surface-id", "persist-keychain-without-surface-id",
        "persist-keystore-without-surface-id", "persist-local-file-without-surface-id",
    }
    require(required_synonym_cases.issubset({case["fixture_id"] for case in fixture["cases"]}), "retention synonym corpus is incomplete")
    required_record_boundary_cases = {
        "persist-legal-a-plus-unregistered-b-same-leaf",
        "persist-record-cross-sentence-does-not-authorize",
        "persist-record-same-sentence-multiple-surfaces",
        "persist-record-does-not-authorize-chinese-synonym",
        "persist-one-record-cannot-cover-two-signals",
    }
    require(required_record_boundary_cases.issubset({case["fixture_id"] for case in fixture["cases"]}), "retention record-boundary corpus is incomplete")
    for case in fixture["cases"]:
        ast = pandoc_ast(case["source"], parser, tooling["pandoc_path"])
        actual, _, _ = evaluate_retention_ast(ast, artifact["detector_grammar"], owners, retention_ids)
        require(actual == case["expected"], f"retention fixture verdict mismatch: {case['fixture_id']} expected={case['expected']} actual={actual}")
        renamed = dict(case)
        renamed["fixture_id"] = "diagnostic-name-does-not-drive-behavior"
        renamed_actual, _, _ = evaluate_retention_ast(pandoc_ast(renamed["source"], parser, tooling["pandoc_path"]), artifact["detector_grammar"], owners, retention_ids)
        require(renamed_actual == actual, f"retention fixture_id changed behavior: {case['fixture_id']}")
    return len(fixture["cases"]), len(live_directives), 11


def validate_tool_contract(contracts: ContractSet) -> None:
    canonicalizer = contracts.registry.document["canonicalizer"]
    require(canonicalizer["execution_mode"] == "read-only-verifier", "canonicalizer must be read-only")
    require(canonicalizer["trust_status"] == "audit-evidence-only-not-a-release-authority", "canonicalizer trust status is overstated")
    require(canonicalizer["production_authority"] == "externally-pinned-signed-release-or-vcs-commit-plus-tool-raw-sha256-and-prior-root-authorization", "canonicalizer production authority statement mismatch")
    require(canonicalizer["self_pin_update"] == "forbidden", "canonicalizer may self-authorize a tool pin")
    require(canonicalizer["validator_path"] == "docs/contracts/validate-contracts-v1.py", "validator path mismatch")
    require(canonicalizer["validator_version"] == "aq-contract-validator-v1", "validator version mismatch")
    for path in (CANONICALIZER_REL, "docs/contracts/validate-contracts-v1.py", NODE_HELPER_REL):
        raw = contracts.reader.read_bytes(path, contracts.bounds["artifact_raw_bytes_max"])
        require((b"write" + b"_text") not in raw and (b"--" + b"write") not in raw, f"read-only validation tool contains a mutation API/flag: {path}")
    for path in ("docs/contracts/run-release-gate-v1.py", "docs/contracts/run-validation-mutations-v1.py", "docs/contracts/package.json", "docs/contracts/package-lock.json"):
        contracts.reader.read_bytes(path, contracts.bounds["artifact_raw_bytes_max"])


def input_digest(contracts: ContractSet) -> str:
    paths = tuple(BASE_ALLOWED_READ_PATHS) + history_paths_from_manifest(contracts)
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda value: value.encode("utf-8")):
        raw = contracts.reader.initial_bytes(path)
        encoded = path.encode("utf-8")
        digest.update(len(encoded).to_bytes(2, "big"))
        digest.update(encoded)
        digest.update(len(raw).to_bytes(8, "big"))
        digest.update(raw)
    return digest.hexdigest()


def run_all(contracts: ContractSet, quiet: bool = False) -> dict[str, Any]:
    expected_order = [
        "registry_raw_bounds",
        "utf8_decode_and_nfc",
        "strict_json_parse",
        "registry_schema_hash",
        "registry_schema_validate",
        "artifact_raw_bounds",
        "artifact_raw_hash",
        "schema_raw_bounds",
        "schema_raw_and_canonical_hash",
        "schema_meta_validate",
        "artifact_schema_validate",
        "semantic_closure_validate",
    ]
    require(contracts.registry.document["validation_order"] == expected_order, "registry validation_order mismatch")
    validate_registry_paths(contracts)
    validate_hash_pins(contracts)
    tooling = validate_dependency_runtime(contracts)
    ajv = run_ajv(contracts, tooling)
    array_count = validate_array_order(contracts)
    validate_core_closure(contracts)
    core_fixture_count = validate_core_fixtures(contracts)
    validate_local_key_semantics(contracts)
    validate_lease_semantics(contracts)
    validate_operation_semantics(contracts)
    validate_fixture_references(contracts)
    validate_normative_decision_input(contracts)
    validate_projections(contracts)
    heading_number_count = validate_heading_numbers_and_anchors(contracts)
    semantic_qa_count = validate_semantic_negative_qa(contracts)
    retention_fixture_count, live_directive_count, retention_structural_qa_count = validate_retention(contracts, tooling)
    validate_tool_contract(contracts)
    validator_ids = [row["validator_id"] for row in contracts.registry.document["semantic_validators"]]
    require(validator_ids == sorted(validator_ids, key=lambda value: value.encode("utf-8")), "semantic validator IDs are not UTF-8 sorted")
    require(set(validator_ids) == {
        "array-order-dialect-v1",
        "core-safety-closure-v1",
        "core-safety-fixture-runner-v1",
        "heading-number-and-anchor-v1",
        "key-entry-semantics-v1",
        "lease-formula-closure-v1",
        "normative-decision-input-v1",
        "operation-reference-closure-v1",
        "probe-result-closure-v1",
        "purpose-consumer-closure-v1",
        "repo-path-v1",
        "retention-detector-closure-v1",
        "schema-array-order-coverage-v1",
        "strict-integer-type-v1",
        "validation-mutation-contract-v1",
    }, "registry semantic validator implementation set mismatch")
    pause_ms = os.environ.get("AQ_VALIDATION_TEST_PAUSE_BEFORE_FINAL_VERIFY_MS")
    if pause_ms is not None:
        require(os.environ.get("AQ_VALIDATION_MUTATION_TEST") == "1", "validation pause hook is test-only")
        pause_value = int(pause_ms)
        require(1 <= pause_value <= 5000, "validation pause hook is out of bounds")
        time.sleep(pause_value / 1000)
    final_tooling = validate_dependency_runtime(contracts)
    require(final_tooling["runtime"] == tooling["runtime"], "validation runtime profile changed during validation")
    for path_key in ("node_path", "npm_path", "pandoc_path"):
        require(final_tooling[path_key] == tooling[path_key], f"validation executable resolution changed during validation: {path_key}")
    contracts.reader.verify_unchanged()
    result = {
        "array_schema_objects": array_count,
        "core_fixtures": core_fixture_count,
        "retention_fixtures": retention_fixture_count,
        "retention_structural_qa": retention_structural_qa_count,
        "semantic_negative_qa": semantic_qa_count,
        "live_persistence_directives": live_directive_count,
        "numbered_headings": heading_number_count,
        "meta_schemas": ajv["meta_validated"],
        "schema_instances": ajv["instances_validated"],
        "semantic_validators": len(validator_ids),
        "registry_anchor": domain_hash(REGISTRY_DOMAIN, contracts.registry.document),
        "input_sha256": input_digest(contracts),
        "node_version": tooling["runtime"]["node_version_exact"],
        "npm_version": tooling["runtime"]["npm_version_exact"],
        "pandoc_version": tooling["runtime"]["pandoc_version_exact"],
        "ajv_version": tooling["runtime"]["ajv_version_exact"],
        "source_bytes_unchanged": True,
    }
    if not quiet:
        for key in (
            "meta_schemas", "schema_instances", "array_schema_objects", "semantic_validators",
            "core_fixtures", "retention_fixtures", "retention_structural_qa", "live_persistence_directives",
            "numbered_headings", "semantic_negative_qa",
            "node_version", "npm_version", "pandoc_version", "ajv_version",
            "registry_anchor", "input_sha256", "source_bytes_unchanged",
        ):
            value = result[key]
            print(f"{key}={str(value).lower() if isinstance(value, bool) else value}")
        print("status=ok")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate all Agent Quota documentation contracts without mutation.")
    parser.add_argument("--quiet", action="store_true", help="emit only failures")
    args = parser.parse_args()
    reader: RepositoryReader | None = None
    try:
        runtime_guard.verify_runtime(require_external_bootstrap=True)
        reader = RepositoryReader()
        contracts = load_contract_set(reader)
        ready_fd = os.environ.get("AQ_VALIDATION_TEST_READY_FD")
        if ready_fd is not None:
            require(os.environ.get("AQ_VALIDATION_MUTATION_TEST") == "1", "validation ready hook is test-only")
            descriptor = int(ready_fd)
            require(3 <= descriptor <= 4, "validation ready descriptor is outside the reserved pipe range")
            require(os.write(descriptor, b"ready") == 5, "validation ready signal was incomplete")
            os.close(descriptor)
        run_all(contracts, quiet=args.quiet)
        return 0
    except (ValidationError, KeyError, IndexError, OSError, TypeError, ValueError, subprocess.TimeoutExpired) as error:
        print(f"validation_error={error}", file=sys.stderr)
        return 1
    finally:
        if reader is not None:
            reader.close()


if __name__ == "__main__":
    raise SystemExit(main())
