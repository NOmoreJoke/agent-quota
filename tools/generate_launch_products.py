"""Project the approved launch scope into renderer data and the native create list."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from agent_quota.providers import MANIFESTS

ROOT = Path(__file__).resolve().parents[1]
BEGIN = "// BEGIN GENERATED LAUNCH CREATE IDS"
END = "// END GENERATED LAUNCH CREATE IDS"
CAPABILITIES = {
    "wallet_balance": ("wallet", "账户余额"),
    "extra_usage_wallet_when_present": ("wallet", "额外用量 (存在时)"),
    "wallet_five_independent_amounts": ("wallet", "五项独立金额"),
    "window_5h": ("window", "5 小时窗口"),
    "token_window_5h": ("window", "5 小时 Token 窗口"),
    "window_week": ("window", "周窗口"),
    "window_5h_week": ("window", "5 小时 / 周窗口"),
    "mcp_monthly_usage": ("window", "MCP 月度用量"),
    "calls_5h_week_month": ("window", "5 小时 / 周 / 月调用量"),
    "credits_5h_7day": ("window", "5 小时 / 7 天积分"),
    "monthly_annual_fixed_credits": ("credits", "月度 / 年度固定积分"),
}


def project(document: dict[str, Any]) -> list[dict[str, Any]]:
    products = document["products"]
    if len(products) != 10 or len({p["product_id"] for p in products}) != 10:
        raise ValueError("launch product identities mismatch")
    if len({p["brand"] for p in products}) != 7:
        raise ValueError("launch brands mismatch")
    cards = []
    for product in products:
        candidate = product["target_actionable_candidate"]
        creatable = product["current_creatable"]
        adapter = product["adapter_id"]
        if type(candidate) is not bool or type(creatable) is not bool:
            raise ValueError("launch policy flags must be booleans")
        if candidate:
            if adapter not in MANIFESTS:
                raise ValueError("candidate has no fixed Python adapter")
        elif adapter is not None or creatable or any(c["claimed"] for c in product["capabilities"]):
            raise ValueError("information card must have no execution mapping")
        capability_rows = [
            CAPABILITIES[c["capability_id"]]
            for c in product["capabilities"]
            if c["status"] != "NOT_APPLICABLE_OUT_OF_RELEASE_SCOPE"
        ]
        cards.append(
            {
                "product_id": product["product_id"],
                "brand": product["brand"],
                "display_name": product["display_name"],
                "adapter_id": adapter,
                "candidate": candidate,
                "creatable": creatable,
                "window": any(kind == "window" for kind, _ in capability_rows),
                "wallet": any(kind == "wallet" for kind, _ in capability_rows),
                "capabilities": [label for _, label in capability_rows],
                "state": "creatable"
                if creatable
                else "implementation-blocked"
                if candidate
                else "information-only",
            }
        )
    if (sum(c["candidate"] for c in cards), sum(c["creatable"] for c in cards)) != (7, 5):
        raise ValueError("launch candidate/create count mismatch")
    candidate_ids = [c["adapter_id"] for c in cards if c["candidate"]]
    if len(set(candidate_ids)) != len(candidate_ids):
        raise ValueError("duplicate launch adapter mapping")
    return cards


def outputs(root: Path) -> dict[Path, str]:
    source = (root / "docs/acceptance-matrix-v2.json").read_bytes()
    cards = project(json.loads(source))
    data = {
        "schema": "aq-launch-products-v1",
        "source_sha256": hashlib.sha256(source).hexdigest(),
        "products": cards,
    }
    ids = sorted(card["adapter_id"] for card in cards if card["creatable"])
    block = BEGIN + "\nprivate let creatableProviderIDs = [\n"
    block += "".join(f'    "{value}",\n' for value in ids) + "]\n" + END
    swift_path = root / "native/AgentQuotaNative.swift"
    swift = swift_path.read_text()
    pattern = re.escape(BEGIN) + r".*?" + re.escape(END)
    if len(re.findall(pattern, swift, flags=re.S)) != 1:
        raise ValueError("native generated block missing or duplicated")
    return {
        root / "src/agent_quota/resources/launch_products_v1.json": json.dumps(
            data, ensure_ascii=False, indent=2
        )
        + "\n",
        swift_path: re.sub(pattern, lambda _match: block, swift, flags=re.S),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    for path, expected in outputs(ROOT).items():
        if arguments.check:
            if not path.exists() or path.read_text() != expected:
                raise SystemExit(f"launch projection drift: {path.relative_to(ROOT)}")
        else:
            path.write_text(expected)
    print("launch products projection PASS")


if __name__ == "__main__":
    main()
