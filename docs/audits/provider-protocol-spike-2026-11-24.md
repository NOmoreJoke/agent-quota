# Provider Protocol Discovery Spike (Iterations 10–13)

- **Date**: 2026-11-24
- **Branch**: `feat/iter10-13-providers` (worktree `agent-quota-iter10-13`)
- **Boundary Compliance**: Zero user tokens/cookies read, zero `~/.workbuddy`/`~/.qoder`/`~/.antigravity` user data inspection, zero `language_server` local port probing, zero browser Cookie scraping, zero committed OAuth secrets.

---

## 1. Google Antigravity (`antigravity`) — Promoted to `current_creatable: true`

- **Auth Flow**: Google OAuth 2.0 (`https://accounts.google.com/o/oauth2/auth` -> `POST https://oauth2.googleapis.com/token`) with PKCE `S256`, cryptographic `state`, IPv4 loopback `NWListener` (`127.0.0.1:0`, `/oauth-callback`), plus manual redirect-URL fallback.
- **Client Secret Handling (Zero Secret Commit)**: Build-time `tools/build_native_helper.sh` generates untracked `build/native/GeneratedOAuthConfig.swift` from optional `AQ_ANTIGRAVITY_OAUTH_CLIENT_ID` / `AQ_ANTIGRAVITY_OAUTH_CLIENT_SECRET` env vars (empty string by default; `native/Sources/*.swift` never calls `ProcessInfo.processInfo.environment` or `UserDefaults`). `Dialogs.swift` also allows user-supplied Client ID / Client Secret fields stored inside Keychain `AntigravityTokenBundle`.
- **CloudCode Read-Only API** (fixed HTTPS host allowlist: `daily-cloudcode-pa.googleapis.com`, fallback `cloudcode-pa.googleapis.com`):
  1. `POST /v1internal:loadCodeAssist` (`mode: FULL_ELIGIBILITY_CHECK`) -> `cloudaicompanionProject`, `paidTier.id` / `currentTier.id`, and sum `paidTier.availableCredits[].creditAmount` (`creditType == "GOOGLE_ONE_AI"`) -> AI Credits Wallet (`cap-antigravity-ai-credits`).
  2. `POST /v1internal:fetchAvailableModels` (`{"project": projectID}`) -> model quota buckets (`remainingFraction`, `resetTime`, `quotaBucketType`, `quotaGroup`).
  3. Best-effort `POST /v1internal:retrieveUserQuotaSummary` (`{"project": projectID}`) -> `groups[].buckets[]` (`gemini-5h`, `gemini-weekly`, `3p-5h`, `3p-weekly`), falling back to `fetchAvailableModels` buckets on non-auth failure.
- **PII Stripping (`ResponseMinimizer.swift`)**: Retains ONLY `tier` (`<= 48` chars), optional numeric `aiCredits`, and `buckets[]` (max 16 rows with `id`, `window`, `remainingFraction`, `resetTime`). All email, account, user, displayName, project, and token fields are dropped inside Swift.
- **Fallback Coexistence**: Retains `agy statusLine` CLI bridge (`credential_type: "agy-statusline-stdin"`, `display_label: "Google Antigravity (CLI Bridge)"`). `host_internal.credential_context` exposes `credential_type` only to the Rust host so `refresh_principal` skips remote HTTP solely for `agy-statusline-stdin` while refreshing OAuth Antigravity accounts normally.

---

## 2. 智谱 GLM (`glm-cn` / `glm-global`) & MiniMax (`minimax-cn` / `minimax-global`) + Independent API Wallet Cards

- **GLM Coding Plan (`glm-cn` / `glm-global`)**:
  - Endpoint: `GET https://open.bigmodel.cn/api/monitor/usage/quota/limit` (`api.z.ai` global), raw `Authorization: <token>`.
  - Topology expanded in `ResponseMinimizer.swift` & `providers.py`:
    - `TOKENS_LIMIT` with `unit == 3` -> `5小时已用 <pct>%` (supports legacy payloads without `unit`).
    - `TOKENS_LIMIT` with `unit == 6` -> `周已用 <pct>%` (weekly window).
    - `TIME_LIMIT` -> `MCP月度已用 <pct>%`.
    - Boost/extra pack (`CREDIT_LIMIT`/`EXTRA_LIMIT`/`BOOST_LIMIT` or `data.extra` / `extraPackage` / `boostPack` / `fuelPack`) -> `cap-{provider_id}-boost-wallet` (`display_kind: "wallet"`).
- **MiniMax Token Plan (`minimax-cn` / `minimax-global`)**:
  - Endpoint: `GET https://www.minimaxi.com/v1/token_plan/remains` (`www.minimax.io` global), `Authorization: Bearer <token>`.
  - Topology expanded to preserve optional boost/extra pack objects (`extra_remains` / `boost_remains` / `package_remains` / `wallet_remains`) -> `cap-{provider_id}-boost-wallet` (`display_kind: "wallet"`), keeping full backward compatibility with `model_remains` 5h/weekly rows.
- **Independent API Wallet Product Cards (`information-only`, `BLOCKED_OFFICIAL_API_ABSENT`)**:
  - `glm-api-balance-cn` (`智谱 GLM API 账户余额`): Official `docs.bigmodel.cn` developer API docs do not publish a pure-API-Key cash balance REST endpoint; `/api/biz/account/query-customer-account-report` is an internal console endpoint. Kept honest as `information-only` (`target_actionable_candidate: false`, `adapter_id: null`, `status: "BLOCKED_OFFICIAL_API_ABSENT"`) with zero browser cookie scraping.
  - `minimax-api-balance-cn` (`MiniMax API 账户余额`): MiniMax Open Platform provides cash balance only in the web console, with no official pure-API-Key cash balance REST endpoint. Kept honest as `information-only` (`BLOCKED_OFFICIAL_API_ABSENT`).

---

## 3. WorkBuddy 个人版（中国区）(`workbuddy-cn`) — Promoted to `current_creatable: true`

- **Evidence Source**: Official WorkBuddy Desktop client configuration (`/Applications/WorkBuddy.app/Contents/Resources/app.asar.unpacked/cli/product.json` + `main/common2.js` + `main/account.js`, read-only schema inspection only).
- **Portless OAuth Flow** (`authMode: .workbuddyCNOAuth`, zero loopback HTTP server, zero Cookies):
  1. `POST https://www.workbuddy.cn/v2/plugin/auth/state?platform=workbuddy` with `{}` and headers `X-No-Authorization: true`, `X-No-User-Id: true`, `X-No-Enterprise-Id: true`, `X-No-Department-Info: true` -> extracts `data.state` & `data.authUrl` (validated `https` + host in `{"www.workbuddy.cn", "copilot.tencent.com"}`).
  2. Opens `authUrl` in default browser (`NSWorkspace.shared.open`) while displaying a cancellable native waiting dialog.
  3. Polls `GET https://www.workbuddy.cn/v2/plugin/auth/token?state=<state>` every 2s (up to 180s; keeps polling on `code == 11217`) -> stores `WorkBuddyTokenBundle { accessToken, refreshToken, expiresAt, tokenType }` in macOS Keychain.
- **Refresh**: `POST https://www.workbuddy.cn/v2/plugin/auth/token/refresh` with headers `X-Refresh-Token: <refreshToken>` and `X-Auth-Refresh-Source: plugin`; maps 401/403 or invalid refresh responses to `reauth-required`.
- **Billing Summary API**: `POST https://www.workbuddy.cn/billing/meter/get-user-resource-summary` (`Authorization: Bearer <accessToken>`, `{}`).
- **PII Stripping & Projection**:
  - `ResponseMinimizer.swift` keeps ONLY `code`, `data.IsPaidUser`, `data.SubscriptionPackageCode`, and `data.Packages[]` (max 32 entries, keys restricted to `PackageCode`, `CycleTotalCapacity`, `CycleRemainCapacity`, `CycleUsedCapacity`).
  - `providers.py` sums base subscription packages into `cap-workbuddy-cn-credits` (`display_kind: "window"`) and extra/boost packages (`extra`/`boost`/`addon` in `PackageCode`) into `cap-workbuddy-cn-boost-wallet` (`display_kind: "wallet"`).

---

## 4. Qoder 个人版（中国区）(`qoder-personal-cn`) — Honest `information-only` Card (`BLOCKED_OFFICIAL_API_ABSENT`)

- **Findings**:
  - `qoder.com.cn/api/v2/me/usages/big_model_credits` is a web console endpoint protected by WAF requiring browser session `Cookie` + `Origin`/`Referer`.
  - Official Bearer OpenAPI endpoints (`api.qoder.com.cn` / `openapi.qoder.com.cn`: `/v1/organizations/{organization_id}/members/{member_id}/quota` & `/usage-events`) are scoped to **Organization / Enterprise** API Keys, NOT Personal accounts (`qoder-personal-cn`).
- **Disposition**: Under the strict no-Cookie-scraping & Batch-1 Personal-CN-only policy, register `qoder-personal-cn` (`Qoder 个人版（中国区）`) under brand `Qoder` as `information-only` (`target_actionable_candidate: false`, `current_creatable: false`, `adapter_id: null`, `status: "BLOCKED_OFFICIAL_API_ABSENT"`).

---

## 5. Planned Matrix Transition Summary (Iterations 11–13)

| Scope Metric | Iter 9 Baseline | After Iter 13 | Delta |
|---|---:|---:|---:|
| `brand_count` | 8 | 10 | +WorkBuddy, +Qoder |
| `product_card_count` | 11 | 15 | +glm-api-balance-cn, +minimax-api-balance-cn, +workbuddy-personal-cn, +qoder-personal-cn |
| `target_actionable_candidate_count` | 8 | 9 | +workbuddy-personal-cn |
| `current_creatable_count` | 5 | 7 | +antigravity, +workbuddy-cn |
| `implementation_blocked_candidate_count` | 3 | 2 | -antigravity |
| `disabled_information_card_count` | 3 | 6 | +glm-api-balance-cn, +minimax-api-balance-cn, +qoder-personal-cn |
