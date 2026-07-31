# Iteration 2 Quality Gate

Status: **PASS**
Scope: Tauri 2 trusted host, React renderer, Python anonymous-pipe sidecar
Baseline: `650c2b614296b3652e92abd986c2602f576d1524` + accepted Iteration 0/1 working tree
External review: https://chatgpt.com/c/6a6b6470-3838-83ea-bb0b-665fb8976d97
Security scan: **SKIPPED by user instruction**

## External delivery integrity

| Artifact | Bytes | SHA-256 | Verdict |
|---|---:|---|---|
| Pro v1 delivery | 4,496,518 | `92f311e31c5546b5fee640f00f4571f50188c2783808d70eab1fbe8ea7d41ede` | REJECT |
| Pro v2 delivery | 4,479,592 | `5f3efad42e3716fe40dde9f27d1d696259cfc22b4ac2084fdec81b61e979435e` | REJECT |
| Codex initial review source | 4,644,904 | `317605e245a43c9a940ff166388bae87415428a8126c84e61d6d66bd2365e6d4` | Reviewed |
| Codex corrected review source | 4,647,758 | `88f9d171a6853303b287e9a51825dc6b93f1450b6be0815d3fbd899fb0dd3dd0` | PASS |

Pro v1/v2 remained placeholders despite claiming Tauri/React completion:

- `src-tauri/src/lib.rs`: 375 bytes, one `status()` function.
- `renderer/src/App.tsx`: 286 bytes, static output.
- no ten-command/29-DTO host path, supervisor, lock, E2E, or runtime proof.
- v2 statement contradicted the downloaded artifact; no Pro code was merged.

## Implemented boundary

- exact ten renderer commands; exact 29 closed DTO schemas in Python, Rust, TypeScript.
- unknown/additional/nested/type/enum/bounds rejected before application dispatch.
- renderer has no network, filesystem, shell, process, credential-value, or sidecar API.
- Fixture path is dynamic, dev-only; production+fixture rejects at startup.
- production bundle scanner verifies fixture markers are absent.
- Tauri CSP uses documented internal IPC origins: `ipc:` and `http://ipc.localhost`.
- minimal Tauri capability: `core:default`; no HTTP/listener/plugin permission.
- sidecar transport: anonymous stdio + independent inherited session-secret pipe.
- frames: u32 big-endian, non-empty UTF-8 JSON object, maximum 1 MiB.
- HMAC-SHA256 session proof; request ID starts at one and increments exactly.
- remaining budget: `1..=9_000_000_000 ns`.
- post-dispatch timeout: `outcome-unknown`, no replay, TERM → KILL → reap.
- credential/destructive commands remain host-owned and return contract-safe cancellation until Iteration 3.

## Three final review rounds

| Round | Reviewer | Gate | Result | P0/P1/P2 |
|---|---|---|---|---|
| R1 | ChatGPT Pro | contract + architecture | PASS | 0/0/0 |
| R2 | ChatGPT Pro | adversarial IPC + renderer + sidecar | PASS | 0/0/0 |
| R3 | Codex | runtime + build + E2E | PASS | 0/0/0 |

Initial external review found production commands bypassing `SidecarSupervisor`, missing production Fixture exclusion, and missing real timeout/reap coverage. Fixes:

1. `HostState` owns the supervisor; eligible commands call `sidecar.call`.
2. static-success production responses removed; unavailable/timeout responses stay inside the authoritative DTO contract and are revalidated.
3. production Fixture dynamic import + build assertion + bundle marker scan.
4. real Python sidecar round-trip and hanging-child timeout/reap tests.

Rejected external objections:

- `http://ipc.localhost` is Tauri's internal IPC origin, not public HTTP access.
- adding a capability field would violate the immutable 29-DTO closure.
- malformed frame/envelope/contract termination is intentional fail-closed behavior; a contract-external generic error is prohibited.

## Independent execution

| Gate | Result |
|---|---|
| `uv run ruff check src tests` | PASS |
| `uv run mypy src` | PASS |
| Python tests | 95 PASS |
| Python branch coverage | 91.27% (required 90%) |
| `pnpm lint` | PASS |
| `pnpm typecheck` | PASS |
| renderer boundary scan | PASS |
| Vitest | 5 PASS |
| production renderer build | PASS |
| production Fixture exclusion | PASS |
| Playwright | 2 PASS |
| `cargo fmt --check` | PASS |
| `cargo clippy --all-targets -- -D warnings` | PASS |
| Rust tests | 10 PASS |
| real Python sidecar child | PASS |
| hanging child timeout/outcome_unknown/reap | PASS |
| Tauri debug `.app` bundle | PASS |
| macOS native process/window smoke | PASS |

## Evidence

- `docs/audits/evidence/iteration-2-renderer-overview-2026-07-31.png`
  - bytes: 65,020
  - SHA-256: `2695e64a18550958c05c8ccac460ddbd9eb21e15aa5c338fe86608170a48239a`
- native smoke screenshot (temporary, not persisted because it included unrelated desktop content):
  - SHA-256: `8cb003ab03f5b79bd5f80775b7e7a6b6652113721f1414ac9cedef7b392dc565`
- real host+sidecar process evidence:
  - host: `agent-quota-desktop`
  - child: `.venv/bin/agent-quota-sidecar`
  - both observed concurrently; child absent after parent termination.

## Residual scope

- release bundle still needs a packaged standalone sidecar, signing/notarization policy, and DMG: Iteration 4.
- native secure credential entry and destructive confirmation surfaces: Iteration 3.
- Fixture E2E proves renderer behavior; native process tests prove IPC lifecycle. No real provider or production user data was used.
