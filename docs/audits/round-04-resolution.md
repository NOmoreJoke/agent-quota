# 第 4 轮审计处置记录

> 处置结论：`PARTIAL_CONVERGENCE_WITH_1_USER_DECISION`
> 处置日期：2026-07-18
> 修订版本：设计方案 v1.0 / Provider 契约 v0.9 / 安全模型 v0.8
> 处置者：第 4 轮全新独立修复 Agent；逐项核验后只采纳成立问题

## 逐项处置

| 问题 ID | 核验结论 | 处理状态 | 最终修改位置 | 处理与验证 |
| --- | --- | --- | --- | --- |
| AQ-R4-001 | 成立；当前 stable rate-limits 表面没有稳定账户身份，放行 nullable email 的只读身份 RPC或替换 MVP Adapter 是互斥产品选择，无法由现行代码/上下文唯一推出 | `BLOCKED_USER_DECISION` | `docs/design-proposal.md:634,730,1178`；`docs/provider-contract.md:185,206`；`docs/security-model.md:171` | 保持 Codex 为 1B Supported 候选、保持业务 allowlist 与阻断严重度，不代替用户放行 RPC或移出 MVP；下一轮前必须由用户二选一 |
| AQ-R4-002 | 成立 | `FIXED` | `docs/design-proposal.md:516-629`；`docs/provider-contract.md:162-166`；`docs/security-model.md:167` | 新增 frozen Probe/Discovery/FetchContext，显式绑定 selector、lease/零 binding proof、AccessIdentity、NetworkPolicy 与 deadline；secret/proof 禁止 repr/序列化，Adapter 禁止反查全局状态，并增加双身份 fake transport 验收 |
| AQ-R4-003 | 成立 | `FIXED` | `docs/design-proposal.md:375-514,645-651`；`docs/provider-contract.md:191-195`；`docs/security-model.md:174` | 补齐 semantic/display/network/protocol meta-schema、plan/label/currency/status 有限集合与引用闭包；ordered comparator 与 versionless evidence 分支可由通用 loader 离线正反例验证 |
| AQ-R4-004 | 成立 | `FIXED` | `docs/design-proposal.md:703-716`；`docs/provider-contract.md:195,355-364,436`；`docs/security-model.md:175` | 将可复现 assurance 与发行真实性分层；detached publisher attestation 签住包名、版本、raw wheel、payload、报告与构建证明，trust bundle 提供有效期、撤销、防回滚和离线验证；RECORD 仅作内部完整性 |
| AQ-R4-005 | 成立 | `FIXED` | `docs/design-proposal.md:966-992,1303`；`docs/provider-contract.md:94`；`docs/security-model.md:223-225` | 外部 TOML 先做 old DB→new file 类型化 diff；仅冻结展示集合可自动采用，destructive diff 必须相同 planner digest + 一次 nonce，确认前 active digest/运行表/Provider 均零变化 |
| AQ-R4-006 | 成立 | `FIXED` | `docs/design-proposal.md:751-771,1323`；`docs/provider-contract.md:187,301,449` | 冻结 primary/secondary/reached、window 成员、map/limit/plan/unused 字段的 absent/null/value；空对象/单窗口/reached absent 整批 schema_changed，不能默认为可用 |
| AQ-R4-007 | 成立 | `FIXED` | `docs/design-proposal.md:858-860,1256,1301`；`docs/provider-contract.md:436`；`docs/security-model.md:175` | Supported/GA 只接受受信任发布者签名的最终 wheel；sdist 供审阅/重新发行，普通本地派生 wheel 无对应 attestation 时确定性拒绝且不能解除 pause；新增独立 `--no-binary :all:` 验收 |
| AQ-R4-008 | 成立 | `FIXED` | `docs/design-proposal.md:1091,1338`；`docs/security-model.md:205,210,235-254` | 安全模型冻结唯一 `ACTION_TTL=15 minutes`；有效消费时间与 15 分钟/30 天窗口证明 action 先于幂等记录到期，verify-only key 至少保留到最大 action 到期，过期签名在 Provider 前拒绝并覆盖第 31/60 天重放 |
| AQ-R4-009 | 成立 | `FIXED` | `docs/design-proposal.md:751,893,1323`；`docs/provider-contract.md:449` | Codex 完整 TOML 改为 `compat-default`，Codex SelectorSchema 只允许该枚举；DeepSeek 保留独立 `default`，offline 负例拒绝其他值 |
| AQ-R4-010 | 成立 | `FIXED` | `docs/provider-contract.md:347-370` | 第 9.4 节继续是唯一失败状态机；第 10 节删除自动重试/暂停复述，只登记 health/freshness 并显式引用唯一表，schema/semantic 第三次后的 fetch 均为禁止 |

## 统计

- `FIXED=9`
- `REJECTED=0`
- `BLOCKED_USER_DECISION=1`
- `TOTAL=10`

## 历史记录完整性基线

修订前冻结的 SHA-256：

```text
a00a14c901881d84ba7648987a2cb7ceff92b41bd9f077a13605e38bad76abdd  docs/audits/round-01-audit.md
c4630344e20561d3677e6d393cf206f4bf6d438871444d28e9d7872dedd53935  docs/audits/round-01-resolution.md
c997a3853d0d47b9e44e1fbb0f8476ddbdf9006438855a3cf1cd246857b54c9a  docs/audits/round-02-audit.md
8b13adaec95df01fa7da78bbed6c305076597535f4e415f396840be4774c65df  docs/audits/round-02-resolution.md
4c0283dfe7827922b0be8001e8b0d381e247ac6f6fab3d8c95d9c95aba2cca32  docs/audits/round-03-audit.md
7ad08ed95a607d1a353c9c54d4bbd359798dd6145c2f6a3918204e3efae12581  docs/audits/round-03-resolution.md
ea0e5002fa17b6d3a8396c5ce8d11fa321e45ae2b1470ba33149a845b1a82897  docs/audits/round-04-audit.md
```

## 验证结论

- 正文只保留现行规范；审计/处置事实只在本文件记录。
- 版本与 README 已标为第 4 轮修订，并明确仍待 Codex 产品决策和全新的独立全量复审。
- 静态验证覆盖占位词、本地 Markdown 链接、围栏配对、历史哈希、10 个问题 ID 唯一性、Codex selector、旧错误摘要、外部 TOML 自动 roll-forward 与关键版本字段矛盾模式。
- 当前不是零问题收敛：唯一未关闭事项是 Codex 身份产品基线；用户选择并由全新修复 Agent落地后，必须再由全新审计 Agent 从零全量复审。
