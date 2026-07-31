# Iteration 4 — macOS package / install acceptance

Status: `PASS`

## Baseline

- Branch: `dev`
- Source commit: `3056549567029fe753f4f0007aa3f04c16312bbb`
- Source ZIP: `/private/var/tmp/agent-quota-iteration4-source-3056549.zip`
- Source ZIP bytes: `4,698,727`
- Source ZIP SHA-256: `b0ba63ad416ba724f3b20d66f00643958dbb18ff4a39decbe74c0edcd3acbb18`
- Security scan: skipped by explicit user request
- External review: <https://chatgpt.com/c/6a6c3ee9-f884-83ea-ae46-899d631ad61d>

## Delivered

- PyInstaller `6.21.0` one-directory arm64 sidecar with fixed CPython `3.11.15`.
- Production lookup restricted to validated bundle resources; no PATH/user-Python
  fallback.
- Nested signed `AgentQuotaNative.app` resource.
- Compile-time pinned resource manifest with owner/mode/size/hash/dev/inode/closure
  checks and no-follow opens.
- Critical executable absolute-path, ownership, mode, symlink, canonical-path and
  identity checks.
- DMG builder, lifecycle test, bundle audit, bundle manifest, CycloneDX SBOM and
  SHA-256 inventory.
- Explicit-off destructive checkbox and initially disabled confirmation action.
- Install/upgrade/rollback/uninstall/purge instructions.

## Package evidence

Artifact class: `local unsigned development package`

| File | Bytes | SHA-256 |
|---|---:|---|
| `Agent-Quota-0.1.0-arm64-local-unsigned.dmg` | 18,573,716 | `a209ee3f209d3308a3c63dc83c89b5b6a5a457adbe6993a1be2e768e0302a42f` |
| `bundle-audit.json` | 18,539 | `2326698e96f41d95ed4a35cd097e4a629c5fd70a3266bb8a42f12e3a4de82257` |
| `bundle-manifest.txt` | 14,537 | `1d47ef2038e4ad91fdddae6be685f7c23db6cbec04b36cbab98c0d6d6aae1aab` |
| `sbom.cdx.json` | 83,059 | `87ab9f47fd91a4db0584e6884d3da6bb3b7841ec9dd0f21135c4419348e4f041` |

- Bundle identifier: `com.agentquota.desktop`
- Architecture: `arm64`
- Deep strict codesign verification: pass (ad-hoc)
- Notarized: no
- Resource entries: `64`
- Resource manifest SHA-256:
  `5a7228c93daf53a758bebe6fde815d5a344d9c22bf075b8bf0ebf4440a7f9d80`
- Mach-O inventory SHA-256:
  `dc68b86ab7d828ef19c4ad9cb222f7d3e4bd14e3bde83fa2401eea32afa21a1d`
- Quarantine attribute: absent
- Audit errors: `0`

## Automated gates

| Gate | Result |
|---|---|
| Ruff lint / format | PASS |
| mypy | PASS |
| pytest + coverage | `103/103`, `90.61%` |
| Renderer lint / typecheck / Vitest | PASS, `5/5` |
| Renderer boundary / production build | PASS |
| Playwright | `2/2` |
| Rust fmt / clippy | PASS |
| Rust tests | `22/22` |
| Bundled sidecar real round-trip / persistence / purge / timeout-reap | PASS |
| DMG mount / install / relaunch / hostile PATH / offline / upgrade / rollback / uninstall-preserve / reinstall | PASS |
| No TCP listener | PASS |
| Resource tamper and re-signed tamper fail-closed | PASS |
| Full frozen contract release gate | PASS |

Final frozen-gate evidence:

- `release_input_sha256=e3dbd449e41ca8a9b2bd6d11d32e1184292f78034f85b637ec1c7d888ffdd837`
- `mutation_case_count=50`
- `mutation_results_sha256=6b267aef7791f75b5f35681ce0b68ce83037c09758a3ffc0283b3b65ba262964`
- `source_bytes_unchanged=true`
- `status=ok`

The first full frozen-gate run rejected an Iteration 4 README status edit:
`release_gate_error=mutation locator before-state mismatch:
validation-input-changed`. The README was restored byte-for-byte because it is
part of the frozen contract input. Runtime/package status is recorded in
`CLAUDE.md`, `docs/INSTALLATION.md` and this report.

## Three adversarial rounds

### R1 — contents / dependencies / locks / SBOM

- Verified Python, Node and Cargo locks plus CycloneDX inventory.
- Verified no repository path or Homebrew dylib dependency in packaged Mach-O
  closure.
- Result: PASS; open P0/P1/P2 = `0/0/0`.

### R2 — path / symlink / substitution / lifecycle

- Verified resource closure, no escaping symlink, critical ownership/mode, no-follow
  identity, compile-time manifest pin, signature failure and re-signed tamper
  fail-closed behavior.
- Verified upgrade/rollback/uninstall/reinstall lifecycle.
- Result: PASS; open P0/P1/P2 = `0/0/0`.

### R3 — installed runtime / regression / package

- Installed current artifact at `/Applications/Agent Quota.app`.
- Verified main process and bundled sidecar launch with no listener.
- Verified offline/hostile-PATH lifecycle and complete automated regression suite.
- External reviewer requested removal of the redundant naked native-helper output
  and stronger evidence closure; both were corrected.
- External reviewer final verdict: `P0 OPEN: 0`, `P1 OPEN: 0`, `P2 OPEN: 0`.
- Result: PASS.

## Scope and unresolved validation

- No Developer ID signature or Apple notarization.
- No clean macOS VM or Intel/universal-binary validation.
- No real provider, credential, production service, deployment or database
  migration.
- Native secure credential entry remains a manual installed-app acceptance step;
  automation intentionally does not inject secrets into the secure dialog.
- Ad-hoc signing means Gatekeeper distribution behavior is not production-qualified.
