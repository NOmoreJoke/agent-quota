# Release handoff

## Baseline

- Active branch: `main`.
- Exact formal public release commit: not yet selected (pending Apple Developer ID signing, notarization, and live holder acceptance).
- Built artifact class without Apple Developer certificate: `local development package` (`adhoc-test-only` signing mode).

## Scope & engineering status

- Machine authority: `docs/acceptance-matrix-v2.json` -> `src/agent_quota/resources/launch_products_v1.json`.
- Launch product matrix: **15 product cards / 10 brands**:
  - **7 creatable Keychain/OAuth cards**: DeepSeek API 余额、Kimi API 余额（中国区）、Kimi Code Token Plan、MiniMax Token Plan（中国区）（含加油包 Wallet）、GLM Coding Plan（中国区）（含周窗口与加油包 Wallet）、Google Antigravity（Google OAuth + CloudCode 只读查询，同时兼容 `agy statusLine` 本地零密钥桥接共存）、WorkBuddy 个人版（中国区）（官方无端口 OAuth + Billing 周期积分与加油包 Wallet）.
  - **2 holder-gated candidate cards**: 火山方舟 Agent Plan（个人版）and 火山引擎账户余额 (adapters, official `GET` signature, strict 5-string decimal parser, and dynamic dual-secret AppKit dialog implemented; kept `current_creatable=false` until live holder verification).
  - **6 disabled information cards**: 百炼 Coding Plan、百炼 Token Plan 个人版、Xiaomi MiMo Token Plan、智谱 GLM API 账户余额、MiniMax API 账户余额、Qoder 个人版（中国区）.

## Required holder-controlled acceptance

1. Install an Apple-signed (`Developer ID Application`) and notarized DMG without disabling macOS Gatekeeper.
2. Enter API/OAuth credentials only in native AppKit secure dialogs (or bind `agy` `statusLine` via `setup-antigravity`).
3. For every claimed product, run add -> refresh -> restart -> refresh.
4. Verify subject, unit, window, remaining/limit, reset semantics, and `last_refresh_epoch_ms`.
5. Exercise 401 reauthentication and confirm stale LKG is never reported as fresh.
6. Verify upgrade/rollback, uninstall retention, reinstall recovery and native-confirmed purge.

## Formal release gates

| Gate | Current result |
|---|---|
| Scope machine contract (`validate_acceptance_matrix.sh`) |Implemented & validated (`status=blocked` until live cells pass) |
| Fifteen-card launch UI & cross-language minimizer/parser invariants | PASS |
| Volcengine `volc-plan` / `volc-wallet` code & dual-secret selector | Implemented; awaiting live holder promotion |
| Antigravity OAuth/CloudCode + `agy` `statusLine` zero-PII bridge coexistence | PASS |
| WorkBuddy CN Personal OAuth/Billing & GLM/MiniMax boost-pack minimizer/parser | PASS |
| Claimed Provider live holder acceptance | `BLOCKED_ACCOUNT` |
| Developer ID signing / notarization / stapling | `BLOCKED_IDENTITY` |
| Local `.app` (`<= 40 MiB`), `.dmg` (`<= 20 MiB`), SBOM & license closure | Verified in `adhoc-test-only` mode; must be re-run with `Developer ID` on final tag |

## Publishing boundary

Do not create a public binary GitHub Release until every formal release gate passes. Public
assets must include the notarized/stapled DMG, checksums, provenance/audits, SBOM,
license evidence and source archive.
