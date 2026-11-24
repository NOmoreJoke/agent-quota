# Iteration 9–13 Final Verification & Release Audit Report

- **Date**: 2026-11-24 / 2026-11-25
- **Source Branch**: `fix/widget-header-collapse` (`0279eba`)
- **Worktree**: `/Users/kyle/Code/Project/agent-quota-iter10-13` (branch `feat/iter10-13-providers`)
- **Artifact Class**: `local development package` (`adhoc-test-only`, built cleanly at commit `3260f4861920e5cbffa4b38b9ea6b0bd7e14ae19`, `source_dirty=false`)
- **Status**: L1 / L2 / L3 **PASS** (L4 holder live-account acceptance & Apple Developer ID notarization remain honestly `BLOCKED_ACCOUNT` / `BLOCKED_IMPLEMENTATION`)

---

## 1. Iteration Commits

1. `0279eba` (`fix/widget-header-collapse`) — `chore(iter9): close widget/reauth WIP, sync catalog count, restore py coverage`
2. `6345b11` (`feat/iter10-13-providers`) — `chore(iter10): add protocol spike audit, sanitized fixtures, and host-allowlist guard`
3. `c60d910` (`feat/iter10-13-providers`) — `feat(iter11): add Antigravity Google OAuth + CloudCode quota with CLI bridge fallback`
4. `3e7d619` (`feat/iter10-13-providers`) — `feat(iter12): add GLM/MiniMax boost-pack wallet projection and API wallet catalog cards`
5. `15fdc54` (`feat/iter10-13-providers`) — `feat(iter13): add WorkBuddy CN personal OAuth/billing and Qoder CN personal catalog card`
6. `7347a6f` (`feat/iter10-13-providers`) — `docs(iter9-13): sync iteration plan, provider catalog, guides, and acceptance docs`
7. `3260f48` (`feat/iter10-13-providers`) — `chore(package): port Xcode 26 host proc-macro warmup fix from main`

---

## 2. Final Matrix & Provider Protocol Summary

- **Launch Matrix Counts (`docs/acceptance-matrix-v2.json` -> `src/agent_quota/resources/launch_products_v1.json`)**:
  - Brands: **10**
  - Product cards: **15**
  - Target actionable candidates: **9**
  - Currently creatable (`current_creatable: true`): **7** (`antigravity`, `deepseek`, `glm-cn`, `kimi-cn`, `kimi-code`, `minimax-cn`, `workbuddy-cn`)
  - Implementation-blocked candidates: **2** (`volc-plan`, `volc-wallet` — pending live holder acceptance)
  - Disabled information-only cards (`BLOCKED_OFFICIAL_API_ABSENT`, zero Cookie/scraping): **6** (`bailian-coding-plan`, `bailian-token-plan-personal`, `xiaomi-mimo-token-plan`, `glm-api-balance-cn`, `minimax-api-balance-cn`, `qoder-personal-cn`)

| Provider / Card | Adapter | Auth / Transport Boundary | Window View | Wallet View |
|---|---|---|---|---|
| **Google Antigravity** | `antigravity` | Google OAuth 2.0 + PKCE `S256` + `state` + `NWListener` IPv4 loopback (`127.0.0.1:0/oauth-callback`) + build-time `GeneratedOAuthConfig.swift` + CloudCode 3-step read-only (`loadCodeAssist`, `fetchAvailableModels`, best-effort `retrieveUserQuotaSummary`); coexists with `agy statusLine` CLI bridge (`agy-statusline-stdin`) | 5h + Weekly per family | `AI Credits` (`GOOGLE_ONE_AI`) |
| **GLM Coding Plan（中国区）** | `glm-cn` | Fixed HTTPS `open.bigmodel.cn/api/monitor/usage/quota/limit` (`raw-authorization`) | 5h (`unit=3`) + Weekly (`unit=6`) + MCP (`TIME_LIMIT`) | 加油包 (`extraPackage` / `CREDIT_LIMIT`) |
| **MiniMax Token Plan（中国区）** | `minimax-cn` | Fixed HTTPS `www.minimaxi.com/v1/token_plan/remains` (`Bearer`) | 5h + Weekly per model | 加油包 (`extra_remains` / `boost_remains`) |
| **WorkBuddy 个人版（中国区）** | `workbuddy-cn` | Portless OAuth (`POST /v2/plugin/auth/state?platform=workbuddy` -> browser -> `GET /v2/plugin/auth/token`, refresh `POST /v2/plugin/auth/token/refresh`) + `POST /billing/meter/get-user-resource-summary` | Cycle credits | 加油包 (`extra` / `boost` / `addon` package codes) |
| **智谱 GLM API 账户余额** | `—` | Disabled `information-only` (`BLOCKED_OFFICIAL_API_ABSENT`, no public pure-API-Key cash balance endpoint) | — | Information only |
| **MiniMax API 账户余额** | `—` | Disabled `information-only` (`BLOCKED_OFFICIAL_API_ABSENT`, no public pure-API-Key cash balance endpoint) | — | Information only |
| **Qoder 个人版（中国区）** | `—` | Disabled `information-only` (`BLOCKED_OFFICIAL_API_ABSENT`, personal quota gated by browser Cookie/WAF; official OpenAPI is org-only) | — | Information only |

---

## 3. L1 / L2 / L3 Verification Evidence

- **Launch Products & Matrix Contracts**:
  - `uv run python tools/generate_launch_products.py --check` -> `launch products projection PASS`
  - `./tools/validate_acceptance_matrix.sh` -> `acceptance-matrix-v2 status=blocked`
  - Frozen `retention-lint-v1.json` docs (`README.md`, `docs/design-proposal.md`, `docs/provider-contract.md`, `docs/security-model.md`) & `provider_catalog_v1.json` (78 rows) preserved untouched.
- **Python Core & Cross-Language Suite**:
  - `uv run ruff format --check src tests tools` -> `63 files already formatted`
  - `uv run ruff check src tests tools` -> `All checks passed!`
  - `uv run mypy src` -> `Success: no issues found in 19 source files`
  - `uv run pytest --cov=agent_quota --cov-branch -q` -> **334 passed**, **91.69% branch coverage** (`>= 90%` threshold passed)
- **Renderer / Frontend & Guardrails**:
  - `pnpm lint` (`eslint . --max-warnings 0`) -> PASS
  - `pnpm typecheck` (`tsc -b --pretty false`) -> PASS
  - `pnpm boundary` -> `renderer boundary PASS (26 files)` (+ 2 boundary unit tests passed)
  - `pnpm test` (`vitest run --coverage.enabled`) -> **9 test files passed (65 tests passed)**
  - `pnpm build` -> `production fixture exclusion PASS (1 chunks)`
  - Negative ESLint `--stdin` proofs:
    - `useEffect` in `src/ui/ForbiddenEffect.tsx` -> exit 1 (`NEG1_PASS`)
    - `setTimeout` in `src/ui/ForbiddenTimer.tsx` -> exit 1 (`NEG2_PASS`)
    - `../ui/App` import in `src/host/ForbiddenImport.ts` -> exit 1 (`NEG3_PASS`)
- **Swift Native Helper (`arm64-apple-macosx13.0`, `-strict-concurrency=complete -warnings-as-errors`)**:
  - `AQ_ALLOW_ADHOC_SIGNING=1 ./tools/build_native_helper.sh` -> PASS (including `--self-test-provider-minimization` and `--self-test-credential-labels`)
- **Rust Tauri Host (`1.97.1`)**:
  - `cargo +1.97.1 fmt --check`, dev `clippy --all-targets -D warnings`, prod `--release --target aarch64-apple-darwin --features production` `clippy -D warnings` -> PASS
  - `cargo +1.97.1 test --locked --features development-overrides` -> **39 passed, 0 failed**
- **Playwright E2E**:
  - `pnpm e2e` -> **14 passed (10.1s)**
- **L3 Local macOS Packaging (`3260f4861920e5cbffa4b38b9ea6b0bd7e14ae19`)**:
  - Output directory: `artifacts/iteration-4-3260f4861920e5cbffa4b38b9ea6b0bd7e14ae19-adhoc-test-only/`
  - `Agent Quota.app`: **35,816,173 bytes** (~34.16 MiB <= 40 MiB limit `41943040`)
  - `Agent-Quota-0.1.0-arm64-local-development.dmg`: **14,004,675 bytes** (~13.36 MiB <= 20 MiB limit `20971520`), `sha256=d2a4565419a2ffa42cdf1c79bdb1472213cc00d82b4f4b4f089b4b9d25cb21bc`, `hdiutil verify` VALID
  - `bundle-audit.json`: `status="pass"`, `architecture="arm64"`, `deployment_target="13.0"`, `runtime_state_files=[]`, `codesign_verify_exit=0`
  - `clean-install-audit.json`: `status="pass"`, `accounts_count=0`, `state_file_present=false`
  - `third-party-license-corpus.json` & `sbom.cdx.json`: `license_corpus_entries=245`, `license_corpus_status="ok"`

---

## 4. Remaining External Steps (L4 — Requires Holder Live Credentials / Apple Signing Identity)

1. Rebuild helper with optional Google Antigravity OAuth Client ID/Secret injected at build time (`AQ_ANTIGRAVITY_OAUTH_CLIENT_ID` / `AQ_ANTIGRAVITY_OAUTH_CLIENT_SECRET`) or enter them directly in the macOS Keychain Add dialog.
2. Execute live holder lifecycle acceptance (`add -> Keychain -> refresh -> restart -> refresh -> 401/invalid_grant reauth -> delete/purge`) across all 7 creatable products + `volc-plan`/`volc-wallet` before promoting remaining gates in `docs/acceptance-matrix-v2.json`.
3. Sign with `Developer ID Application`, notarize, and staple before public distribution (`RELEASE_HANDOFF.md`).
