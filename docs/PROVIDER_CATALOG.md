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

Desktop 的 Provider Preset 只渲染当前已完成本机接入的 5 张卡片：DeepSeek、Kimi、
Kimi For Coding、MiniMax、Zhipu GLM。其余目录行继续保留为合同/审计输入，但不进入
卡片、搜索结果或能力筛选结果。

首发范围目标另由 `docs/acceptance-matrix-v2.json` 管理：10 张独立产品卡、7 个品牌、
7 个目标可操作候选与 3 张禁用信息卡。该目标不是当前实现状态；launch product card
不得由 catalog row 的组合 `adapter_ids` 推导，避免将火山钱包/Agent Plan 或百炼钱包/
Plan 能力错误合并。

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
QoderWork/QwenWork 当前均为 Experimental，且不在 Desktop Provider Preset 中展示。
升级到 Supported 需要公开稳定机器合同、固定 identity/endpoint/auth/response schema、
脱敏 fixture 和独立 live opt-in 门禁。
