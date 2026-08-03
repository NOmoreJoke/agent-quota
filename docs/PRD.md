# Agent Quota Desktop PRD

## 范围

| 字段 | 规则 | 验收 |
|---|---|---|
| Provider Catalog | 73 截图预设 + 5 主流 Agent | 78 行；唯一 `row_id` |
| Window View | Coding Plan/订阅窗口 | 仅 Supported 查询可添加 |
| Wallet View | API balance/credit/Extra Usage | 不跨币种/Provider 求和 |
| 凭据 | host-owned native + Keychain | Renderer 无秘密/网络能力 |
| 平台 | Apple Silicon, macOS >= 13 | 固定 arm64/deployment target |
| 后台 | manual/on-demand | 无账户零请求；无定时器/listener |
| 包体 | app <= 40 MiB, DMG <= 20 MiB | 构建超限 fail |

## 状态机

`Catalog-only/Unsupported -> 不可添加`

`Experimental -> 可查看边界，不发查询`

`Supported -> 原生凭据 -> probe -> 手动 refresh -> Window/Wallet projection`

## 边界条件

- 无公开稳定机器合同 => 不得 Supported。
- 自定义 URL、Cookie、浏览器状态、私有 CLI 文件 => 不得读取。
- fixture/mock => 只算合同与 UI 验证，不算 live/production。
- Provider 401/403 => reauth；429/5xx => bounded retryable error；未知 schema => fail closed。
- 低电量/thermal 后台调度未实现 => 不得宣称已优化运行时调度。
- 自动刷新未来启用条件 => Low Power/thermal 暂停、15 分钟最短周期、单并发合并、
  失败退避/熔断、退出释放、10 分钟空闲 wakeups/RSS/网络证据全部通过。
