# Release acceptance matrix

Authoritative machine record: `docs/acceptance-matrix-v2.json`.
Closed structure: `docs/acceptance-matrix-v2.schema.json`.

`COMPLETE` requires every `claimed=true` and `release_denominator=true` capability
cell to be current installed-release `PASS`, plus every formal release gate. Product
existence, documentation, fixtures, HTTP 200, catalog visibility, or parser tests do
not substitute for holder-controlled live acceptance.

## Launch scope

| Product card | Adapter | Current state | Release denominator |
|---|---|---|---:|
| DeepSeek API 余额 | `deepseek` | Creatable; live acceptance blocked | Yes |
| Kimi API 余额（中国区） | `kimi-cn` | Creatable; live acceptance blocked | Yes |
| Kimi Code Token Plan | `kimi-code` | Creatable; live acceptance blocked | Yes |
| MiniMax Token Plan（中国区） | `minimax-cn` | Creatable; live acceptance blocked | Yes |
| GLM Coding Plan（中国区） | `glm-cn` | Creatable; live acceptance blocked | Yes |
| 火山方舟 Agent Plan（个人版） | `volc-plan` | Implementation and live acceptance blocked | Yes |
| 火山引擎账户余额 | `volc-wallet` | Implementation blocked; not yet claimed | No |
| 百炼 Coding Plan | — | Disabled information card; official read API absent | No |
| 百炼 Token Plan 个人版 | — | Disabled information card; official read API absent | No |
| Xiaomi MiMo Token Plan | — | Disabled information card; official read API absent | No |

Scope totals: `10` product cards, `7` brands, `7` target actionable candidates,
`5` currently creatable products, `2` implementation-blocked candidates, and `3`
disabled information cards.

## Firewalled scope boundaries

- 火山 Agent Plan and 火山钱包 are independent products, capability sets and
  acceptance units. Agent Plan claims only the 5-hour and weekly windows.
- 火山钱包 stays `creatable=false`, `claimed=false` until the official GET contract,
  strict five-string amount schema, no-inferred-currency rendering, LKG fail-closed
  behavior, signing negatives, IAM boundary and installed-release live checks pass.
- 百炼 Coding Plan, 百炼 Token Plan and MiMo Token Plan are visible scope records only:
  no add action, credential collection, Provider request, scraping, or release score.
- MiMo uses monthly/annual fixed Credits and has no 5-hour/weekly product window.
- The 78-row Provider catalog remains audit input; launch cards are a separate product
  model and must not be inferred from a catalog row's combined `adapter_ids`.

## Holder-controlled acceptance

For every claimed capability: add -> Keychain -> refresh -> restart -> refresh; verify
subject, unit, window, remaining/limit, reset semantics, server timestamp and
`last_success_at`; then exercise 401 reauthentication, stale LKG, upgrade/rollback,
uninstall/reinstall retention and native-confirmed purge.

Machine completion additionally requires every required `formal_release_gates` row to
be `PASS`, carry the final 40-character release commit binding, and contain evidence.
