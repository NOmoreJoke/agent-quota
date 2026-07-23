#!/usr/bin/env python3
"""Read-only verifier for registry pins and generated Markdown projections.

The misleading historical name is retained because it is a registered path.
This tool only calculates expected bytes and compares them with the checkout.
Reviewed patches are the only supported way to update projections or pins.
"""

from __future__ import annotations

import importlib.util
import os
import stat
import sys

import python_runtime_guard_v1 as runtime_guard


SCRIPT_ABS = os.path.abspath(__file__)
VALIDATOR_ABS = os.path.join(os.path.dirname(SCRIPT_ABS), "validate-contracts-v1.py")


def main() -> int:
    runtime_guard.verify_runtime(require_external_bootstrap=True)
    try:
        if not stat.S_ISREG(os.lstat(SCRIPT_ABS).st_mode):
            raise RuntimeError("canonicalizer must not be invoked through a symlink")
        if not stat.S_ISREG(os.lstat(VALIDATOR_ABS).st_mode):
            raise RuntimeError("validator must be a regular non-symlink file")
        spec = importlib.util.spec_from_file_location("agent_quota_contract_validator_v1", VALIDATOR_ABS)
        if spec is None or spec.loader is None:
            raise RuntimeError("unable to load the fixed validator")
        validator = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = validator
        spec.loader.exec_module(validator)
        reader = validator.RepositoryReader()
        try:
            contracts = validator.load_contract_set(reader)
            result = validator.run_all(contracts, quiet=True)
            _, projection_digest = validator.artifact_pin_projection(contracts.registry.document)
            reader.verify_unchanged()
        finally:
            reader.close()
        print("mode=read-only-verifier")
        print(f"artifact_pin_projection_sha256={projection_digest}")
        print(f"registry_anchor={result['registry_anchor']}")
        print("source_bytes_unchanged=true")
        print("projection_status=verified")
        return 0
    except Exception as error:
        print(f"projection_error={error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
