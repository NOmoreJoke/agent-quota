# Release acceptance matrix

Authoritative machine record: `docs/acceptance-matrix-v2.json`.
Closed structure: `docs/acceptance-matrix-v2.schema.json`.

`COMPLETE` requires every `claimed=true` and `release_denominator=true` capability
cell to be current installed-release `PASS`, plus every formal release gate. Product
existence, documentation, fixtures, HTTP 200, catalog visibility, or parser tests do
not substitute for holder-controlled live acceptance.

## Launch scope (15 product cards)

| Product card | Adapter | Current state | Release denominator |
|---|---|---|---:|
| DeepSeek API 余额 | `deepseek` | Creatable; cross-language minimizer + parser verified; live acceptance blocked | Yes |
| Kimi API 余额（中国区） | `kimi-cn` | Creatable; live acceptance blocked | Yes |
| Kimi Code Token Plan | `kimi-code` | Creatable (OAuth device flow); live acceptance blocked | Yes |
| MiniMax Token Plan（中国区） | `minimax-cn` | Creatable; 5h/weekly + boost pack Wallet View; live acceptance blocked | Yes |
| GLM Coding Plan（中国区） | `glm-cn` | Creatable; 5h/weekly/MCP + boost pack Wallet View; live acceptance blocked | Yes |
| Google Antigravity | `antigravity` | Creatable (Google OAuth + CloudCode read-only) + local `agy` `statusLine` CLI bridge coexistence; live acceptance blocked | Yes |
| WorkBuddy 个人版（中国区） | `workbuddy-cn` | Creatable (portless OAuth + billing summary + boost Wallet View); live acceptance blocked | Yes |
| 火山方舟 Agent Plan（个人版） | `volc-plan` | Adapter & dual-secret dialog implemented; `current_creatable=false` pending holder check | Yes |
| 火山引擎账户余额 | `volc-wallet` | Official `GET` + 5-string decimal parser implemented; `current_creatable=false` pending holder check | No |
| 百炼 Coding Plan | — | Disabled information card; official read API absent | No |
| 百炼 Token Plan 个人版 | — | Disabled information card; official read API absent | No |
| Xiaomi MiMo Token Plan | — | Disabled information card; official read API absent | No |
| 智谱 GLM API 账户余额 | — | Disabled information card; official pure API-key cash balance API absent | No |
| MiniMax API 账户余额 | — | Disabled information card; official pure API-key cash balance API absent | No |
| Qoder 个人版（中国区） | — | Disabled information card; personal quota behind browser Cookie/WAF (OpenAPI is org-only) | No |

Scope totals: `15` product cards, `10` brands, `9` target actionable candidates,
`7` currently creatable Keychain/OAuth products (with Antigravity also keeping `agy` local CLI bridge coexistence),
`2` holder-gated Volcengine candidates, and `6` disabled information cards.

## Firewalled scope boundaries

- 火山 Agent Plan (`volc-plan`) and 火山钱包 (`volc-wallet`) are independent products,
  capability sets and acceptance units. Agent Plan claims only the 5-hour and weekly windows.
- 火山钱包 enforces the official `GET` contract, strict five-string decimal schema,
  no-inferred-currency rendering, independent `ArrearsBalance` error state, and LKG fail-closed
  behavior; it stays `current_creatable=false` until installed-release holder checks pass.
- Google Antigravity supports both official Google OAuth 2.0 + CloudCode read-only quota queries
  (`daily-cloudcode-pa.googleapis.com` / `cloudcode-pa.googleapis.com` with `loadCodeAssist` +
  `fetchAvailableModels` + best-effort `retrieveUserQuotaSummary` and strict Swift PII stripping)
  and the documented `agy` CLI `statusLine` JSON stdin bridge (`https://antigravity.google/docs/cli/statusline`)
  with immediate PII/workspace stripping — never undocumented localhost `language_server` port probing.
- 百炼 Coding Plan、百炼 Token Plan、MiMo Token Plan、智谱 GLM API 账户余额、MiniMax API 账户余额 与 Qoder 个人版（中国区）
  are visible scope records only: no add action, credential collection, Provider request, scraping, or release score.
- The 78-row Provider catalog remains audit input; launch cards are generated deterministically
  from `docs/acceptance-matrix-v2.json` into `src/agent_quota/resources/launch_products_v1.json`.

## Holder-controlled acceptance

For every claimed capability: add -> Keychain -> refresh -> restart -> refresh; verify
subject, unit, window, remaining/limit, reset semantics, server timestamp and
`last_success_at`; then exercise 401 reauthentication, stale LKG, upgrade/rollback,
uninstall/reinstall retention and native-confirmed purge.

Machine completion additionally requires every required `formal_release_gates` row to
be `PASS`, carry the final 40-character release commit binding, and contain evidence.
