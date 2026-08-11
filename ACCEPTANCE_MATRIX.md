# RC acceptance matrix

Authoritative machine record: `docs/acceptance-matrix-v1.json`.

`COMPLETE` requires `21/21 PASS` plus every release gate. Historical live
fixtures, HTTP 200, documented product limits, and an `Unsupported` UI state do
not satisfy current installed-RC live acceptance.

| Provider | Wallet | 5h | Week | Current result |
|---|---:|---:|---:|---|
| DeepSeek | BLOCKED_ACCOUNT | BLOCKED_PRODUCT_ABSENT | BLOCKED_PRODUCT_ABSENT | BLOCKED |
| Alibaba Bailian | BLOCKED_ACCOUNT | BLOCKED_OFFICIAL_API_ABSENT | BLOCKED_OFFICIAL_API_ABSENT | BLOCKED |
| Volcengine | BLOCKED_ACCOUNT | BLOCKED_ACCOUNT | BLOCKED_ACCOUNT | BLOCKED |
| MiniMax | BLOCKED_OFFICIAL_API_ABSENT | BLOCKED_ACCOUNT | BLOCKED_ACCOUNT | BLOCKED |
| Zhipu GLM | BLOCKED_OFFICIAL_API_ABSENT | BLOCKED_ACCOUNT | BLOCKED_OFFICIAL_API_ABSENT | BLOCKED |
| Kimi | BLOCKED_ACCOUNT | BLOCKED_ACCOUNT | BLOCKED_ACCOUNT | BLOCKED |
| Xiaomi MiMo | BLOCKED_OFFICIAL_API_ABSENT | BLOCKED_PRODUCT_ABSENT | BLOCKED_PRODUCT_ABSENT | BLOCKED |

## Product/account binding

| Provider | Wallet principal | Plan principal | Region |
|---|---|---|---|
| DeepSeek | Open Platform API key | No verified product | China |
| Alibaba Bailian | Alibaba Cloud RAM AccessKey | Coding/Token Plan key | China |
| Volcengine | Billing AK/SK | Ark Agent Plan AK/SK + active plan | cn-beijing |
| MiniMax | Open Platform API account | Token Plan key | China |
| Zhipu GLM | Open Platform billing account | Coding Plan token | China |
| Kimi | Open Platform API key | Kimi Code OAuth membership | China |
| Xiaomi MiMo | Open Platform API account | Monthly/annual Token Plan key | China/global platform |

## Account preflight

- Configured accounts at `2026-08-11T15:47:47+08:00`: `1` DeepSeek account,
  lifecycle `needs-reauth`; the installed app binary differs from the RC artifact, so it
  does not satisfy current installed-RC acceptance.
- No Keychain value was queried; no credential reference was emitted.
- Account holder action: use only the installed app native secure dialog.
- A blocked cell does not stop safe work on other cells.
