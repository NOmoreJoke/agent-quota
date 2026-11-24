# Release acceptance matrix

Authoritative machine record: `docs/acceptance-matrix-v2.json`.
Closed structure: `docs/acceptance-matrix-v2.schema.json`.

`COMPLETE` requires every `claimed=true` and `release_denominator=true` capability
cell to be current installed-release `PASS`, plus every formal release gate. Product
existence, documentation, fixtures, HTTP 200, catalog visibility, or parser tests do
not substitute for holder-controlled live acceptance.

## Launch scope (11 product cards)

| Product card | Adapter | Current state | Release denominator |
|---|---|---|---:|
| DeepSeek API 余额 | `deepseek` | Creatable; cross-language minimizer + parser verified; live acceptance blocked | Yes |
| Kimi API 余额（中国区） | `kimi-cn` | Creatable; live acceptance blocked | Yes |
| Kimi Code Token Plan | `kimi-code` | Creatable (OAuth device flow); live acceptance blocked | Yes |
| MiniMax Token Plan（中国区） | `minimax-cn` | Creatable; live acceptance blocked | Yes |
| GLM Coding Plan（中国区） | `glm-cn` | Creatable; live acceptance blocked | Yes |
| Google Antigravity | `antigravity` | Official `agy` `statusLine` local push bridge (`setup-antigravity`); live session check pending | No |
| 火山方舟 Agent Plan（个人版） | `volc-plan` | Adapter & dual-secret dialog implemented; `current_creatable=false` pending holder check | Yes |
| 火山引擎账户余额 | `volc-wallet` | Official `GET` + 5-string decimal parser implemented; `current_creatable=false` pending holder check | No |
| 百炼 Coding Plan | — | Disabled information card; official read API absent | No |
| 百炼 Token Plan 个人版 | — | Disabled information card; official read API absent | No |
| Xiaomi MiMo Token Plan | — | Disabled information card; official read API absent | No |

Scope totals: `11` product cards, `8` brands, `8` target actionable candidates,
`5` currently creatable Keychain/OAuth products, `1` local CLI statusLine bridge
(`Google Antigravity`), `2` holder-gated Volcengine candidates, and `3` disabled
information cards.

## Firewalled scope boundaries

- 火山 Agent Plan (`volc-plan`) and 火山钱包 (`volc-wallet`) are independent products,
  capability sets and acceptance units. Agent Plan claims only the 5-hour and weekly windows.
- 火山钱包 enforces the official `GET` contract, strict five-string decimal schema,
  no-inferred-currency rendering, independent `ArrearsBalance` error state, and LKG fail-closed
  behavior; it stays `current_creatable=false` until installed-release holder checks pass.
- Google Antigravity uses only the documented `agy` CLI `statusLine` JSON stdin bridge
  (`https://antigravity.google/docs/cli/statusline`) with immediate PII/workspace stripping and
  60-second identical-projection write deduplication — never undocumented localhost ports or
  private IDE OAuth tokens.
- 百炼 Coding Plan, 百炼 Token Plan and MiMo Token Plan are visible scope records only:
  no add action, credential collection, Provider request, scraping, or release score.
- The 78-row Provider catalog remains audit input; launch cards are generated deterministically
  from `docs/acceptance-matrix-v2.json` into `src/agent_quota/resources/launch_products_v1.json`.

## Holder-controlled acceptance

For every claimed capability: add -> Keychain -> refresh -> restart -> refresh; verify
subject, unit, window, remaining/limit, reset semantics, server timestamp and
`last_success_at`; then exercise 401 reauthentication, stale LKG, upgrade/rollback,
uninstall/reinstall retention and native-confirmed purge.

Machine completion additionally requires every required `formal_release_gates` row to
be `PASS`, carry the final 40-character release commit binding, and contain evidence.
