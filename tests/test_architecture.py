from __future__ import annotations

import ast
from pathlib import Path


def test_production_package_does_not_import_testkit() -> None:
    root = Path(__file__).resolve().parents[1] / "src/agent_quota"
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert all(not alias.name.startswith("agent_quota_testkit") for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith("agent_quota_testkit")


def test_production_package_has_no_network_or_http_server_imports() -> None:
    forbidden = {"socket", "http.server", "urllib.request", "requests", "httpx"}
    root = Path(__file__).resolve().parents[1] / "src/agent_quota"
    imports: set[str] = set()
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)
    assert not imports.intersection(forbidden)
