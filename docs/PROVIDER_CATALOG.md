# Provider Catalog

## 口径

| 状态 | Window View | Wallet View | 可添加 |
|---|---|---|---|
| Supported | 固定官方合同 | 固定官方合同 | 是 |
| Experimental | 合同或解析器未冻结 | 合同或解析器未冻结 | 否 |
| Catalog-only | 仅实体/预设目录 | 仅实体/预设目录 | 否 |
| Unsupported | 安全边界明确拒绝 | 安全边界明确拒绝 | 否 |

机器权威清单：`src/agent_quota/resources/provider_catalog_v1.json`。清单固定 78 行、
`row_id` 唯一；同一官方实体的区域/产品预设允许共享 `canonical_id`。

## 已实现查询

| Preset | Adapter | Window | Wallet | 验证方式 |
|---|---|---:|---:|---|
| DeepSeek | `deepseek` | — | API balance | 官方 schema + 脱敏录制 |
| Kimi | `kimi-cn`, `kimi-global` | — | API balance | 官方 schema；区域隔离 |
| Kimi For Coding | `kimi-code` | Token Plan | Extra Usage | 官方 OAuth/usage schema |
| MiniMax / MiniMax en | `minimax-cn`, `minimax-global` | Token Plan | — | 官方 schema + fixture |
| Zhipu GLM / Zhipu GLM en | `glm-cn`, `glm-global` | Coding Plan | — | 官方 schema + fixture |

没有真实订阅的 Provider 使用 schema fixture、错误注入和合同测试，只能证明解析器与
fail-closed 行为；不得表述为真实账户、生产或所有地区验证。

## 主流 Agent

Codex、Claude Code、GitHub Copilot、Cursor、Trae、WorkBuddy、
QoderWork/QwenWork 当前均为 Experimental：UI 可搜索和查看能力边界，但不会调用
网络、读取 CLI 私有状态或接受 Cookie。升级到 Supported 需要公开稳定机器合同、固定
identity/endpoint/auth/response schema、脱敏 fixture 和独立 live opt-in 门禁。
