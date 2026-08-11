# Known issues

| ID | Severity | Issue | Exit condition |
|---|---:|---|---|
| RC-001 | P0 | 21/21 live semantic acceptance is not met | Every matrix cell is current installed-RC `PASS` |
| RC-002 | P0 | DeepSeek has no verified 5h/week plan product in the checked official surface | Official product and stable read-only API |
| RC-003 | P0 | MiMo Token Plan is monthly/annual fixed Credits, not 5h/week | Official 5h/week product and stable read-only API |
| RC-004 | P0 | Bailian Coding/Token Plan documents UI usage but no supported read-only usage API was verified | Official public usage API |
| RC-005 | P0 | GLM official query source exposes 5h tokens and monthly MCP, not weekly usage | Official weekly field/API |
| RC-006 | P0 | No current installed-RC Provider accounts are configured | Holder-controlled native credential entry and live matrix replay |
| RC-007 | P0 | Full install -> refresh -> restart -> 401 -> uninstall/reinstall -> purge lifecycle is not live-proven | Configure a safe real account, run `tools/test_macos_package_lifecycle.sh`, then complete native 401 and purge checks |
| RC-008 | Accepted | Package remains local unsigned arm64 | Explicit RC target; document Gatekeeper launch |
| RC-009 | P2 | Offline contract validator pins Ajv 8.17.1 / fast-uri 3.1.3 with published advisories; `$data`, network loading, and untrusted schema input are disabled/absent, and these packages are not shipped in the app runtime | Repin Ajv >= 8.19.0 and [fast-uri >= 3.1.4](https://github.com/advisories/GHSA-v2hh-gcrm-f6hx), then regenerate the closed contract/runtime hashes |

Do not replace any issue with browser scraping, Cookie reuse, private console
endpoints, local estimation, synthetic values, or historical fixtures.
