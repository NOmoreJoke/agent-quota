# Provider Catalog

## 口径

| 状态 | Window View | Wallet View | 可操作方式 |
|---|---|---|---|
| Creatable (`Supported`) | 固定官方合同 | 固定官方合同 | 原生安全弹窗录入 Keychain / OAuth |
| Local CLI Bridge | 官方 `statusLine` JSON 推送 | `AI Credits` 计数 | `setup-antigravity` 一键配置本地桥接（无密钥） |
| Candidate (Hold) | 固定官方合同已实现 | 固定官方合同已实现 | 代码就绪，待持有人实机验收后开放添加 |
| Information-only / Unsupported | 无公开只读接口 | 无公开只读接口 | 仅展示范围边界，禁止抓取或复用私有会话 |

## 双层目录架构

1. **全量审计目录（`src/agent_quota/resources/provider_catalog_v1.json`）**：固定 78 行、`row_id` 唯一，作为合同与安全边界审计输入保留。
2. **桌面端首发产品矩阵（`docs/acceptance-matrix-v2.json` → `src/agent_quota/resources/launch_products_v1.json`）**：独立定义 **11 张产品卡（8 个品牌）**，支持搜索与「全部 / Window View / Wallet View」能力筛选，绝不将火山方舟 Agent Plan 与火山现金钱包混并在同一张卡片中。

## 首发 11 张产品卡状态

| 产品卡 | Adapter | Window View | Wallet View | 当前桌面端状态 |
|---|---|---:|---:|---|
| DeepSeek API 余额 | `deepseek` | — | API balance | 可添加（原生单密钥） |
| Kimi API 余额（中国区） | `kimi-cn` | — | API balance | 可添加（原生单密钥，区域隔离） |
| Kimi Code Token Plan | `kimi-code` | 5h + 周窗口 | Extra Usage | 可添加（原生 OAuth 设备授权流） |
| MiniMax Token Plan（中国区） | `minimax-cn` | 分模型 5h + 周窗口 | — | 可添加（原生单密钥） |
| GLM Coding Plan（中国区） | `glm-cn` | 5h + 月度 MCP | — | 可添加（原生单密钥） |
| Google Antigravity | `antigravity` | 分模型 5h + 周窗口 | AI Credits | 本地 `agy statusLine` 桥接（零密钥） |
| 火山方舟 Agent Plan（个人版） | `volc-plan` | 5h + 周窗口 | — | 代码与双密钥弹窗已就绪，待实机解锁 |
| 火山引擎账户余额 | `volc-wallet` | — | 5 字段精确余额/欠费 | 官方 `GET` 与解析器已就绪，待实机解锁 |
| 百炼 Coding Plan | — | — | — | 仅信息展示（无公开只读额度 API） |
| 百炼 Token Plan 个人版 | — | — | — | 仅信息展示（无公开只读额度 API） |
| Xiaomi MiMo Token Plan | — | — | — | 仅信息展示（无公开只读额度 API） |

> 注：底层解析器同时保留 `kimi-global`、`minimax-global`、`glm-global` 国际区官方合同实现；没有真实持有人订阅验收的卡片严格使用官方 schema fixture、跨语言裁剪联调与错误注入验证 fail-closed 行为，不冒充实机生产通过。
