# Known issues

## Active external release gates

| ID | Severity | Issue | Exit condition |
|---|---:|---|---|
| RC-001 | P0 | No claimed capability has current installed-release holder live acceptance | Every denominator cell in `docs/acceptance-matrix-v2.json` is `PASS` |
| RC-004 | Accepted scope boundary | 百炼 Coding Plan、百炼 Token Plan、MiMo Token Plan、智谱 GLM API 余额、MiniMax API 余额、Qoder 个人版（中国区）、Claude Code、ChatGPT Codex have product evidence but no verified public non-Cookie read-only HTTP quota API | Keep disabled/no-credential/no-request/no-scraping, or add a future official contract |
| RC-005 | P0 | Full install -> refresh -> restart -> 401 -> uninstall/reinstall -> purge lifecycle is not live-proven with holder credentials | Holder-controlled installed-release lifecycle evidence for every claimed product |
| RC-006 | P0 | Local development package uses explicit ad-hoc test signing when no Apple Development / Developer ID identity is installed in Keychain | Developer ID Application certificate, hardened runtime, timestamp, notarization, stapling and Gatekeeper checks |
| RC-008 | P2 | Release handoff and machine gate summary must be regenerated for the final clean notarized release commit | Commit-bound checksums, SBOM, provenance, acceptance and notarization evidence |
| RC-009 | P2 | Frozen offline contract validator (`docs/contracts/`) pins Ajv 8.17.1 / fast-uri 3.1.3; these packages are dev-only validation inputs and are never bundled into app runtime | Repin in a future contract version bump if upstream contract freeze is reopened |

## Resolved engineering items (closed in codebase, awaiting live holder promotion)

| ID | Resolution summary | Remaining promotion condition |
|---|---|---|
| RC-002 | `volc-plan` independent product card, dual-secret AppKit `CredentialSelectorGate`, and negative parser/signature tests are implemented | Live 5h/weekly holder acceptance before flipping `current_creatable` to `true` |
| RC-003 | `volc-wallet` switched to official `GET` `QueryBalanceAcct` without body `Content-Type`, enforcing all five bounded decimal strings, no inferred currency, and independent `ArrearsBalance` error health | Live holder IAM/account acceptance before flipping `claimed` / `current_creatable` to `true` |
| RC-007 | Launch UI uses the generated 15-card / 10-brand `launch_products_v1.json` model (7 creatable Keychain/OAuth cards including `antigravity` CloudCode & `workbuddy-cn`, 2 Volcengine candidate cards, 6 disabled information cards; plus `agy statusLine` CLI bridge coexistence) | Verified by `test_launch_products.py`, `launchProducts.test.ts`, `test_acceptance_matrix.py`, and Playwright E2E |
| RC-010 | Antigravity OAuth builds default `antigravityDefaultOAuthClientID` / `antigravityDefaultOAuthClientSecret` to `""` unless `AQ_ANTIGRAVITY_OAUTH_CLIENT_ID` / `AQ_ANTIGRAVITY_OAUTH_CLIENT_SECRET` are supplied at native helper build time (keeping secrets out of Git) | User can supply OAuth Client ID/Secret in the native dialog or rebuild with build-time env injection |

Do not replace any blocker with browser scraping, Cookie reuse, private console endpoints,
undocumented localhost port probing, local estimation, synthetic values, or historical fixtures.
