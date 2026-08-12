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


def test_native_provider_transport_is_fixed_keychain_owned_and_nonproxying() -> None:
    root = Path(__file__).resolve().parents[1]
    swift = (root / "native/AgentQuotaNative.swift").read_text()
    for host in (
        "api.deepseek.com",
        "api.moonshot.cn",
        "api.moonshot.ai",
        "api.kimi.com",
        "www.minimaxi.com",
        "www.minimax.io",
        "open.bigmodel.cn",
        "api.z.ai",
    ):
        assert swift.count(f'host: "{host}"') == 1
    for constraint in (
        'components.scheme = "https"',
        "url.host == host",
        "url.path == path",
        "url.port == nil",
        "url.user == nil",
        "url.password == nil",
        "url.query == nil",
        "url.fragment == nil",
        "request.httpMethod = method",
    ):
        assert constraint in swift
    assert "connectionProxyDictionary = [:]" in swift
    assert "urlCredentialStorage = nil" in swift
    assert 'request.setValue("identity", forHTTPHeaderField: "Accept-Encoding")' in swift
    assert "completionHandler(nil)" in swift
    assert "URLSessionDataDelegate" in swift
    assert "didReceive data: Data" in swift
    assert "dataTask.cancel()" in swift
    assert "expected > Int64(limit)" in swift
    assert "data.count > limit - body.count" in swift
    assert "private let lock = NSLock()" in swift
    assert "func snapshot()" in swift
    assert "let snapshot = delegate.snapshot()" in swift
    assert "dataTask(with: request) {" not in swift
    assert "keychainRead(account: reference)" in swift
    assert 'var requestMethod = "GET"' in swift
    assert 'host: "auth.kimi.com"' not in swift
    assert 'private let kimiCodeOAuthHost = "auth.kimi.com"' in swift
    assert 'path: "/coding/v1/usages"' in swift
    assert 'path: "/api/oauth/device_authorization"' in swift
    assert 'path: "/api/oauth/token"' in swift
    assert "expiresIn <= 86_400" not in swift
    assert 'positiveInt64(document["expires_in"]) ?? 300' in swift
    assert "TimeInterval(authorizationLifetime)" in swift
    assert "private func minimizedProviderDocument" in swift
    for provider in ("deepseek", "kimi-cn", "kimi-code", "minimax-cn", "glm-cn"):
        assert f'provider == "{provider}"' in swift
    assert 'selected(balance, ["type", "amount", "amountLeft"])' in swift
    assert "private func isSafeCredential" in swift
    assert '!isSafeCredential("injected\\r\\nHeader: value")' in swift
    assert 'case "keychain-prune"' not in swift
    assert "pruneReferences" not in swift
    assert "if status == errSecItemNotFound" in swift
    assert "provider: id, httpStatus: 401" in swift
    assert 'document["user"]' not in swift
    assert 'document["authentication"]' not in swift
    assert "ProcessInfo.processInfo.environment" not in swift
    assert "UserDefaults" not in swift
    assert "didResignActiveNotification" not in swift
    assert "alert.runModal() == .alertFirstButtonReturn" in swift
    assert "#selector(NSText.paste(_:))" in swift
    assert 'keyEquivalent: "v"' in swift
    assert "pasteItem.keyEquivalentModifierMask = [.command]" in swift
    assert swift.index("application.finishLaunching()") < swift.index("let pasteItem")
    assert 'NSMenuItem(title: "Edit"' in swift
    assert "final class PasteSecureTextField" in swift
    assert 'event.charactersIgnoringModifiers?.lowercased() == "v"' in swift
    assert "editor.paste(nil)" in swift
    assert "secure.menu = secureMenu" in swift
    assert "private let creatableProviderIDs = [" in swift
    assert "creatableProviders.map(\\.id) == creatableProviderIDs" in swift
    assert "Set(creatableProviderIDs).count == 5" in swift
    assert "for item in creatableProviders" in swift
    assert "creatableProviders[selector.indexOfSelectedItem].id" in swift
    create_ids = swift.split("private let creatableProviderIDs = [", 1)[1].split("]", 1)[0]
    assert {value.strip().strip('"') for value in create_ids.split(",") if value.strip()} == {
        "deepseek",
        "glm-cn",
        "kimi-cn",
        "kimi-code",
        "minimax-cn",
    }
    assert all(
        provider not in create_ids
        for provider in (
            "bailian-wallet",
            "glm-global",
            "kimi-global",
            "minimax-global",
            "volc-wallet",
            "volc-plan",
        )
    )
    assert "NSText.copy" not in swift
    assert 'let reference = "credential-\\(UUID()' not in swift
    assert '["action", "dialogPurpose", "opaqueReference"]' in swift
    assert "isCredentialReference(reference)" in swift
    rust_host = (root / "src-tauri" / "src" / "lib.rs").read_text()
    lease = rust_host.index("InstanceLease::acquire(&data_root)")
    builder = rust_host.index("tauri::Builder::default()")
    assert "app.path().app_data_dir()" not in rust_host
    assert "fixed_app_data_root()" in rust_host
    assert "Err(InstanceLeaseError::AlreadyRunning) => return" in rust_host
    assert lease < builder
    assert lease < rust_host.index("runtime_resources(app)")
    assert lease < rust_host.index("SidecarSupervisor::spawn")
    assert lease < rust_host.index("NativeHost::new")
    assert "prune_references" not in rust_host
    assert "host_internal.credential_references" not in rust_host
    credential_flow = rust_host[
        rust_host.index("fn credential_dialog_open") : rust_host.index(
            "fn destructive_confirmation_open"
        )
    ]
    assert credential_flow.index("create_credential_candidate(&state)") < credential_flow.index(
        "state.native.credential"
    )
    assert credential_flow.index(
        "credential_destructive_transaction.lock()"
    ) < credential_flow.index("create_credential_candidate(&state)")
    assert '"opaqueReference": reference' in credential_flow
    destructive_flow = rust_host[
        rust_host.index("fn destructive_confirmation_open") : rust_host.index("fn reauthenticate")
    ]
    assert destructive_flow.index(
        "credential_destructive_transaction.lock()"
    ) < destructive_flow.index("host_internal.destructive_prepare")
    helper = (root / "tools/build_native_helper.sh").read_text()
    assert "-strict-concurrency=complete" in helper
    assert "-target arm64-apple-macosx13.0" in helper
    assert '"$app_binary" --self-test-provider-minimization' in helper
    renderer_contract = (root / "src/agent_quota/resources/renderer_contract_v1.json").read_text()
    assert "body_base64" not in renderer_contract
    assert "http_status" not in renderer_contract


def test_macos_package_script_has_ordered_resource_gates() -> None:
    root = Path(__file__).parents[1]
    script = (root / "tools/build_macos_package.sh").read_text()
    assert 'MACOSX_DEPLOYMENT_TARGET_REQUIRED="13.0"' in script
    assert "SWIFT_MACOSX_DEPLOYMENT_TARGET must be exactly" in script
    assert '"$repo_root/tools/audit_package_size.py"' in script
    assert "verify_clean_install_sidecar.py" in script
    assert script.index("audit_macos_bundle.py") < script.index("hdiutil create")
    assert script.index("verify_clean_install_sidecar.py") < script.index("hdiutil create")
    assert script.index("audit_package_size.py") < script.index("hdiutil create")
    assert script.index("generate_third_party_licenses.py") < script.index("hdiutil create")
    assert script.index("audit_sbom_licenses.py") < script.index("hdiutil create")
    assert '"$dmg_root/THIRD_PARTY_LICENSE_CORPUS.json"' in script
    assert '"$dmg_root/THIRD_PARTY_UPSTREAM_LICENSE_SOURCES.json"' in script
    assert '"third-party-license-corpus.json"' in script
    assert '"upstream-license-sources.json"' in script
    assert "20971520" in script
    assert script.count("verify_source_lock") == 4
    assert "rev-parse HEAD" in script
    assert "status --porcelain" in script
    assert "generate_build_provenance.py" in script
    assert '"build-provenance.json"' in script


def test_clean_install_verifier_matches_host_fd_and_canonical_path_boundary() -> None:
    root = Path(__file__).parents[1]
    verifier = (root / "tools/verify_clean_install_sidecar.py").read_text()
    assert "SESSION_SECRET_FD = 3" in verifier
    assert "pass_fds=tuple(sorted({child_secret_fd, SESSION_SECRET_FD}))" in verifier
    assert 'Path(temporary).resolve(strict=True) / "data"' in verifier


def test_production_renderer_has_no_timer_or_loopback_patterns() -> None:
    root = Path(__file__).parents[1] / "src"
    forbidden = ("setInterval(", "setTimeout(", "http://127.0.0.1", "http://localhost")
    production = [
        path
        for path in root.rglob("*")
        if path.is_file()
        and path.suffix in {".ts", ".tsx", ".js"}
        and not path.name.endswith(".test.ts")
        and not path.name.endswith(".test.tsx")
        and path.name != "fixtures.ts"
    ]
    for path in production:
        text = path.read_text(encoding="utf-8", errors="strict")
        assert not any(pattern in text for pattern in forbidden), path
