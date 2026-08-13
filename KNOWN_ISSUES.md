# Known issues

| ID | Severity | Issue | Exit condition |
|---|---:|---|---|
| RC-001 | P0 | No claimed capability has current installed-release holder live acceptance | Every denominator cell in `docs/acceptance-matrix-v2.json` is `PASS` |
| RC-002 | P0 | 火山方舟 Agent Plan has a fixed adapter but is not in the current UI/native create allowlist | Independent product card, native create path, negative tests and live 5h/week acceptance |
| RC-003 | P0 | 火山钱包 implementation uses POST instead of the official GET and does not yet enforce the strict five-string/no-inferred-currency contract | Complete every `promotion_gate` item before setting `claimed` or `creatable` true |
| RC-004 | Accepted scope boundary | 百炼 Coding Plan、百炼 Token Plan、MiMo Token Plan have product evidence but no verified public read-only quota API | Keep disabled/no-credential/no-request/no-scraping, or add a future official contract |
| RC-005 | P0 | Full install -> refresh -> restart -> 401 -> uninstall/reinstall -> purge lifecycle is not live-proven | Holder-controlled installed-release lifecycle evidence for every claimed product |
| RC-006 | P0 | Current package is ad-hoc, unsigned by Developer ID and not notarized/stapled | Developer ID, hardened runtime, timestamp, notarization, stapling and Gatekeeper checks |
| RC-007 | P1 | Launch UI still derives five visible cards from the 78-row catalog; it has no independent 10-card product model | Add exact 10-card model with 7 candidate and 3 disabled-card invariants |
| RC-008 | P2 | Release handoff and machine gate summary must be regenerated for the final clean release commit | Commit-bound checksums, SBOM, provenance, acceptance and notarization evidence |
| RC-009 | P2 | Offline contract validator pins Ajv 8.17.1 / fast-uri 3.1.3 with published advisories; these packages are not shipped in app runtime | Repin Ajv >= 8.19.0 and fast-uri >= 3.1.4, then regenerate closed hashes |

Do not replace any blocker with browser scraping, Cookie reuse, private console endpoints,
local estimation, synthetic values, or historical fixtures.
