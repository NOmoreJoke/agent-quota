#!/usr/bin/env python3
"""Generate the closed renderer contract resource from the machine authority."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs/contracts/core-safety-contract-v1.json"
TARGET = ROOT / "src/agent_quota/resources/renderer_contract_v1.json"


def main() -> None:
    document = json.loads(SOURCE.read_text(encoding="utf-8"))
    contract = document["desktop_product_contract"]["renderer_command_contract"]
    if len(contract["command_ids"]) != 10 or len(contract["dto_schemas"]) != 29:
        raise RuntimeError("renderer contract closure changed")
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(
        json.dumps(contract, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
