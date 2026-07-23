# 第 3 轮审计处置记录

> 处置日期：2026-07-18  
> 处置范围：`README.md`、`docs/design-proposal.md`、`docs/provider-contract.md`、`docs/security-model.md`  
> 统计：`fixed=11` / `rejected=0` / `blocked=1`  
> 当前结论：可确定项已修订；仍需用户决定 Codex 身份产品基线，之后必须由全新独立 Agent 全量复审。

## AQ-R3-001 — BLOCKED_USER_DECISION

- 核验：成立。`account/rateLimits/read` 没有可验证的稳定账户身份，而现行发送端 allowlist 又只允许握手与该业务 RPC；两项要求无法在当前约束内同时实现。
- 处理结论：保持 Codex 为 1B/MVP Supported 候选，并保持 RPC allowlist 与严重度不变。没有擅自允许 `account/read`，也没有替换第二个 MVP Adapter。用户必须在“允许只读 `account/read(refreshToken=false)`，空账户/空邮箱 fail closed”与“Codex 退出 MVP Supported、改用具备稳定身份契约的第二 Adapter”之间选择。
- 最终位置：`docs/design-proposal.md:477-479,1005,1176,1189`；`docs/provider-contract.md:174-180,199-201`；`docs/security-model.md:170-173`；状态见 `README.md:3`。
- 验证：静态确认 `account/read` 未进入业务 allowlist，`account/rateLimits/read` 与 Codex MVP 候选仍存在；本项在决策前不能标记 fixed。

## AQ-R3-002 — FIXED

- 核验：成立。旧“请求集合子集”允许空结果或漏项静默通过。
- 修复：冻结 `(subject_id, capability_id)` 精确集合合同；每个 request key 恰好一条快照，空、漏、重复、额外、跨 subject 均整批 `adapter_contract_violation`，运行时缺失必须用封闭快照表达。
- 最终位置：`docs/design-proposal.md:448-453,481-488`；`docs/provider-contract.md:203-212`。
- 验证：旧“返回集合只能是请求集合的子集”模式为 0；正文列出五类恶意 FakeAdapter 反例及零部分写入语义。

## AQ-R3-003 — FIXED

- 核验：成立。单字段 target 无法表达主体与能力的二维缺失关系。
- 修复：`MissingCapability` 改为 `subject_handle + capability_id + reason`；二元组必须唯一，悬空 handle、未知 capability、重复或越界 reason 整批拒绝。
- 最终位置：`docs/design-proposal.md:443-446,487`；`docs/provider-contract.md:88,196,201`。
- 验证：旧 `MissingCapability(target, reason)` 模式为 0；双 subject/同 capability 不同 entitlement 有无歧义验收规则。

## AQ-R3-004 — FIXED

- 核验：成立。把最终 wheel digest 写回 wheel 中的 assurance 字段会形成自引用。
- 修复：冻结 `aq-assurance-v1`：对 assurance 投影为 `null` 且排除 sidecar/RECORD 的规范 wheel payload 求 digest，再与 manifest/fixture/report 摘要计算 ID；最终 carrier 另由 RECORD/发行签名保护。
- 最终位置：`docs/design-proposal.md:544-553`；`docs/provider-contract.md:184-188`。
- 验证：算法不求哈希不动点；规定双构建复现、一字节受保护内容篡改和 carrier 完整性反例。

## AQ-R3-005 — FIXED

- 核验：成立。旧 dimension 包含 policy/health，和“跨来源只发一条”冲突。
- 修复：episode 身份改为 capability/generation/window 的 `AlertAggregateKey`；policy、freshness、health、status 只作为 contributing sources。ack、cooldown、resolve 和投递序号都归属聚合 episode。
- 最终位置：`docs/design-proposal.md:975-984`；`docs/security-model.md:327,336`。
- 验证：规范明确两个 policy 加一个 health 只生成一条最高级通知，逐源清除不提前 resolve，全部清除只恢复一次。

## AQ-R3-006 — FIXED

- 核验：成立。旧 manifest 平行元组无法机器化表达合法组合、binding purpose/数量和 selector schema。
- 修复：加入严格的 `ProviderProfile`、`CredentialRequirement`、`SubjectSpec`、`SelectorSchema/SelectorFieldSpec`、`RefreshPolicy`；一个 profile 原子绑定合法组合，通用验证器禁止笛卡尔积和 Adapter 私有补合同。
- 最终位置：`docs/design-proposal.md:345-417,490-492`；`docs/provider-contract.md:89,182-188`。
- 验证：离线验收只依赖通用 manifest schema，并覆盖交叉拼接、错误 purpose/数量、selector 额外字段和非法组合。

## AQ-R3-007 — FIXED

- 核验：成立。旧 journal 没有双 writer 串行化，也只在启动处理外部 TOML 漂移。
- 修复：增加 SQLite 独占 writer lease、单调 fencing token、唯一 active migration、专属临时文件；所有服务入口、Scheduler claim 与长任务提交复核 file/DB/memory digest、generation 和 runtime fence，drift 时关闭 gate 并恢复。
- 最终位置：`docs/design-proposal.md:812-824`；`docs/provider-contract.md:93,401`；`docs/security-model.md:220`。
- 验证：验收覆盖双 CLI、CLI+daemon、外部编辑、writer 崩溃、lease 接管和旧 token 提交；权威禁用/删除后旧宿主不能再读缓存或访问 Provider。

## AQ-R3-008 — FIXED

- 核验：成立。多个本地 HMAC/PRF/签名 key 没有统一生成、轮换、丢失与 purge 合同。
- 修复：定义 InstallationRegistry 绑定的版本化 `LocalKeyRing`、分用途 HKDF domain、非秘密 key ID、active/verify-only/retired 状态、fenced 轮换、保护窗和缺失 fail closed；purge 包含全部 key material。
- 最终位置：`docs/design-proposal.md:665-679`；`docs/provider-contract.md:157-159`；`docs/security-model.md:38,171,206-207,224,328`。
- 验证：合同覆盖重启、正常轮换、轮换崩溃、旧 key 到期、registry/keyring/binding key 单独丢失与 purge，且禁止静默重建扩容预算。

## AQ-R3-009 — FIXED

- 核验：成立。Linux platformdirs 会读取 XDG，purge 时重算会让环境改变删除根。
- 修复：platformdirs/XDG 只在 init 计算并显式确认一次；固定 OS 账户数据库 home 锚点保存带 MAC 的 root/device/inode/owner/mode。purge 忽略当前 HOME/XDG/cwd，只接受登记根并二次验证。
- 最终位置：`docs/design-proposal.md:667-669,692-700`；`docs/security-model.md:224,315`。
- 验证：攻击 corpus 包含改变全部 XDG/HOME/cwd、同名目录、registry/MAC 篡改、symlink、mount 与确认后 inode 交换；任何变化都不能改变删除目标。

## AQ-R3-010 — FIXED

- 核验：成立。旧文档未定义兼容 bucket、多 bucket、可空窗口和 reached type 的唯一映射。
- 修复：MVP 唯一使用顶层 backward-compatible `rateLimits`；multi-bucket 只接受空或唯一且一致的 `codex` bucket，否则 probe `unverified_version`。primary/secondary null 各自返回 not-applicable 快照，并新增封闭 reached status capability。
- 最终位置：`docs/design-proposal.md:586-605`；`docs/provider-contract.md:180,282-286`；`docs/security-model.md:170`。
- 验证：fixture 清单覆盖 single/multi/未知/不一致 bucket、两个窗口分别/同时为空、非法窗口、全部/未知 reached type和动态 key 脱敏。

## AQ-R3-011 — FIXED

- 核验：成立。旧“canonical schema hash”没有指定生成模式、文件集合和 allowlist 组合方式。
- 修复：冻结 `aq-codex-schema-bundle-v1`：空目录、stable 命令、唯一 v2 聚合根、`aq-json-c14n-v1`、规范 Codex 版本与有序 RPC allowlist 共同参与 bundle hash。
- 最终位置：`docs/design-proposal.md:555-571`；`docs/provider-contract.md:186-188`。
- 验证：规定两机同版本同 hash；experimental、版本、根内容/集合或 allowlist 任一变化必改 hash，构建日志只记非敏感配方与摘要。

## AQ-R3-012 — FIXED

- 核验：成立。飞书文本的 24 小时和笼统“飞书幂等 30 天”互相冲突。
- 修复：安全模型第 10.1 节建立唯一 `RET-*` 表，逐类定义 CLI、Web、飞书文本、卡片、审计、迁移、rate ledger、key 与真实本地审计；其他正文只引用条目 ID，并明确到期重放语义。
- 最终位置：`docs/security-model.md:191-210,228,246,267,273`；`docs/design-proposal.md:616,630,647-659,920,1016`；`docs/provider-contract.md:359,404,418`。
- 验证：除唯一表外，三份现行正文中“文本 24 小时/飞书 30 天”等重复期限声明为 0；虚拟时钟边界由条目 ID 唯一决定。

## 处置结论

11 项成立且可确定的问题已修订，0 项驳回，1 项需要用户产品决策。现行正文仍不能宣称零问题收敛；决策落文后必须由新的独立 Agent 从零全量审计，不能只复查本轮清单。
