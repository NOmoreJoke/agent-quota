# 第 3 轮独立对抗性审计

> 审计结论：`FAIL_WITH_12_ISSUES`  
> 严重度：阻断 1 / 高 8 / 中 3 / 低 0  
> 审计日期：2026-07-18  
> 审计范围：`README.md`、`docs/design-proposal.md`、`docs/provider-contract.md`、`docs/security-model.md`  
> 审计方式：全新 Agent 从零全量审查；候选清单冻结前未读取 `docs/audits/` 下任何历史 audit/resolution；本轮只新增本报告，不修改正文或旧记录。

## 总结

本轮不能给出零问题结论。12 项均有可执行修复，其中 `AQ-R3-001` 需要用户在两个产品基线中作选择；其余问题可以直接修订设计。

已知的 Codex 身份问题由本 Agent 独立复现。当前正文只允许握手和 `account/rateLimits/read`，但该响应没有稳定账户身份；官方 `account/read(refreshToken=false)` 可以返回 ChatGPT 账户类型、计划和邮箱，但邮箱明确允许为 `null`。因此，现有 allowlist 不能生成文档要求的 `verified_stable` 身份。

## 问题清单

### AQ-R3-001 — 阻断 — Codex 身份要求与 RPC allowlist 互斥

- 定位：`docs/design-proposal.md:420`、`docs/design-proposal.md:875`、`docs/design-proposal.md:959`；`docs/provider-contract.md:150-155`、`docs/provider-contract.md:170-175`、`docs/provider-contract.md:189-193`；`docs/security-model.md:166-173`。
- 反例：启动 app-server、完成握手后只调用当前允许的 `account/rateLimits/read`。响应包含额度窗口和计划信息，但不包含能区分“当前登录账户是否已切换”的稳定身份。core 无法同时满足“账户切换必须改变 cache identity”和“业务 RPC 只能调用 rateLimits/read”。
- 原因：身份协议需要一个账户标识，但安全 allowlist 禁止了能返回账户信息的 `account/read`。本机 `codex-cli 0.142.5` 的生成 schema 还证明 `account/read` 的 ChatGPT `email` 可为 `null`，所以即使放行也必须定义空值失败语义。
- 建议：由用户明确选择且写成唯一基线：
  1. 允许只读 `account/read(refreshToken=false)`；只在内存中以本地专用密钥对 `(account.type, normalized email)` 生成身份，禁止持久化/记录原文，`account=null`、非 ChatGPT 或 `email=null` 一律 fail closed；或
  2. Codex 不作为 MVP Supported Adapter，换成另一个具备稳定身份契约的第二 Adapter。
- 可验证验收：合约测试覆盖同账户重启、账户切换、登出重登、`email=null`、`account=null`、非 ChatGPT 账户；证明旧缓存/LKG 不跨身份复用，原始邮箱不进入配置、SQLite/WAL、日志、fixture、投影或审计。

### AQ-R3-002 — 高 — `fetch` 允许静默漏掉请求能力

- 定位：`docs/design-proposal.md:413-415`、`docs/design-proposal.md:425-429`；`docs/provider-contract.md:199-206`。
- 反例：core 请求两个 capability，恶意或有 bug 的 Adapter 返回空元组。空集合是请求集合的子集、数量也没有超限，因此通过当前边界规则；调用者既收不到快照，也收不到缺失原因或操作错误，旧值和失败计数保持不变。
- 原因：合同只规定“返回集合是请求集合的子集”，没有为每个未返回项定义封闭结果。
- 建议：要求每个请求 key 恰好产生一个 `CapabilitySnapshot`，或增加按 `(subject_id, capability_id)` 绑定的封闭 `FetchOutcome`；禁止无解释缺项。
- 可验证验收：对空结果、漏一项、重复项、额外项、跨 subject 项做恶意 FakeAdapter 测试；每个请求 key 必须得到唯一快照或整批稳定 OperationError，且不能悄悄保留旧成功状态。

### AQ-R3-003 — 高 — `MissingCapability` 无法表达“哪个主体缺哪项能力”

- 定位：`docs/design-proposal.md:380-403`、`docs/design-proposal.md:424-429`；`docs/provider-contract.md:184-195`。
- 反例：一次发现得到 subject A 和 subject B；A 缺 `rolling-secondary`，B 拥有它。当前 `MissingCapability.target` 只能填 capability ID 或 subject handle：填 capability ID 会丢失主体，填 subject handle会丢失 capability。
- 原因：缺失 DTO 把一个二维关系压成了单字段联合。
- 建议：改成至少包含 `subject_handle + capability_id + reason`；若确需 principal 级缺失，使用另一个有明确判别字段的联合分支。
- 可验证验收：双 subject、同 capability 不同 entitlement 的 fixture 能无歧义往返序列化；悬空 handle、未知 capability、重复二元组和越界 reason 均整批拒绝。

### AQ-R3-004 — 高 — `release_assurance_id` 的构建公式形成自引用哈希

- 定位：`docs/design-proposal.md:431-433`；`docs/provider-contract.md:178-182`。
- 反例：先构建 wheel 得到 artifact digest，再把由该 digest 算出的 `release_assurance_id` 写回 wheel。写入会改变 wheel digest，使 manifest 中的 assurance 不再对应最终发行物；若先写 assurance 再算 artifact digest，则公式需要先知道自身结果。
- 原因：公式排除了 manifest 的 assurance 字段，却没有排除或规范化发行物中承载该字段的字节。
- 建议：定义非循环方案，例如对“assurance 字段置零后的规范化 wheel 内容”求 digest，或把 assurance 放在不参与 artifact digest 的签名 sidecar/attestation 中；同时冻结 RECORD、zip 时间戳和文件排序规则。
- 可验证验收：同一源码两次可复现构建得到相同 assurance；对最终 wheel 任一受保护文件做一字节修改都会验证失败；验证器不需要寻找哈希不动点。

### AQ-R3-005 — 高 — 告警 episode 键与“跨策略只发一条”互相矛盾

- 定位：`docs/design-proposal.md:834-850`，特别是 `docs/design-proposal.md:846` 与 `docs/design-proposal.md:848-849`。
- 反例：同一 capability 同时命中 `window_used_percent` 和 `reset_pressure`。`AlertDimensionKey` 包含 `policy_id_or_health`，因此会建立两个 dimension/episode；下一段却要求多个 policy/health 先合并到最高级后只发一条。
- 原因：状态键按输入策略分裂，通知语义却按 capability 聚合，规范没有定义二者之间的聚合层和原子指针。
- 建议：冻结唯一模型：要么 episode 以 capability/generation/window 为聚合键，并把 contributing policy 集合作为 episode 明细；要么保留策略 dimension，但另定义原子聚合 notification episode，明确 resolve/ack/cooldown 的归属。
- 可验证验收：两个策略加一个 health 同时命中只创建/投递一个最高严重度 episode；分别清除其中一个来源不会提前 resolved；全部清除后只恢复一次；双 SchedulerHost 和重启结果一致。

### AQ-R3-006 — 高 — `AdapterManifest` 不能机器化表达正文要求的认证与 selector 约束

- 定位：`docs/design-proposal.md:343-367`、`docs/design-proposal.md:418-443`、`docs/design-proposal.md:677-683`；`docs/provider-contract.md:81-94`、`docs/provider-contract.md:176-195`。
- 反例：新增一个 Adapter，auth A 需要 0 个 binding，auth B 需要两个不同 purpose 的 binding，并且两个 subject kind 使用不同 selector schema。正文要求 config validate 离线拒绝错误组合，但列出的 manifest 只有相互独立的 `auth_variants/regions/endpoint_profiles/subject_kinds` 元组，没有 binding 数量/purpose、合法组合或 selector schema 字段；验证器只能写 Provider 特例。
- 原因：叙述引用了 `CapabilitySpec`、`SemanticContract`、`RefreshPolicy` 和 selector/binding schema，却没有给出这些类型的完整封闭合同；平行元组还会产生未声明的笛卡尔积。
- 建议：定义判别式 `ProviderProfile/AuthProfile/SubjectSpec/CapabilitySpec/RefreshPolicy`，把合法 variant-region-auth-endpoint 组合、binding 数量与 purpose、selector 字段、canonicalizer、capability 和刷新规则放在同一可验证分支。
- 可验证验收：仅靠通用 manifest schema 即可离线接受所有合法组合并拒绝交叉拼接、错误 binding purpose/数量、错误 selector 和额外字段；测试不得依赖 Adapter 私有 if/else。

### AQ-R3-007 — 高 — migration journal 缺少跨进程写者互斥和运行时配置漂移门禁

- 定位：`docs/design-proposal.md:685-695`、`docs/design-proposal.md:523-527`；`docs/security-model.md:191-206`。
- 反例一：两个 CLI 同时读取相同 old digest，使用固定临时文件名并分别写 `prepared` journal。正文没有“最多一个未完成 migration”、writer lease 或 fencing token；恢复面对两个 roll-forward 计划时没有唯一结果。
- 反例二：daemon 已运行时，用户直接把 TOML 改成禁用某 principal。当前“无 journal 的直接编辑”只描述启动恢复；长期进程可以继续用旧 registry 刷新被禁用账户。
- 原因：单次迁移的崩溃阶段写得很细，但没有定义多进程串行化、查询侧 fencing 或运行中权威 TOML digest 的复核点。
- 建议：增加数据库独占 migration lease/fencing token、唯一 active migration 约束、每次迁移唯一临时文件；所有查询/调度事务验证 active config/generation fence。运行中发现文件 digest 漂移时先关闭服务入口并恢复，不能继续使用旧内存 registry。
- 可验证验收：双 CLI 竞争、CLI 与 daemon 并发、外部编辑、writer 崩溃和 lease 接管测试均只产生一个计划；旧 fencing token 不能提交；禁用/删除一经权威配置生效，旧宿主不再读缓存或访问 Provider。

### AQ-R3-008 — 高 — 多个本地安全密钥没有生命周期合同

- 定位：`docs/design-proposal.md:506-509`、`docs/design-proposal.md:516-521`、`docs/design-proposal.md:550-553`；`docs/provider-contract.md:148-155`；`docs/security-model.md:34-43`、`docs/security-model.md:210-228`、`docs/security-model.md:257-263`。
- 反例：本地 HMAC/PRF 密钥丢失后被静默重建。相同上游账户会得到新 `rate_limit_cohort`，从而绕过原 30 天刷新预算；旧卡片签名、幂等 actor 绑定、query generation 和假名化关联也会同时失配。正文没有规定启动应拒绝、迁移还是轮换。
- 原因：文档使用 generation key、cohort key、pseudonym key 和 action signing key，却没有定义分用途密钥、key ID、生成/存储权限、备份、轮换、丢失恢复、删除和 purge 清单。
- 建议：加入版本化 `LocalKeyRing` 契约；每种用途域分离并记录非秘密 key ID；轮换使用 journal/fence 迁移，限流与幂等在最长保护期内保留旧 key 验证能力；意外丢失 fail closed，不能当作空白安装。
- 可验证验收：重启、正常轮换、轮换中崩溃、旧 key 到期、密钥文件丢失和 purge 测试证明：刷新预算不扩容、旧重放不重新执行、缓存不会错复用、Secret 不进入日志/备份、purge 清单包含所有 key material。

### AQ-R3-009 — 高 — purge 的“环境变量不能决定根”与 `platformdirs` 重算互斥

- 定位：`docs/design-proposal.md:568-575`；`docs/security-model.md:181-206`。
- 反例：Linux 的 `platformdirs` 明确支持 `XDG_CONFIG_HOME/XDG_DATA_HOME/XDG_CACHE_HOME/XDG_STATE_HOME` 覆盖。若 purge 在执行时“重新计算”路径，启动环境可把 app 子目录指向另一组 `agent-quota` 目录；这与“禁止环境变量直接提供删除根”冲突。owner/mode 检查不能证明该目录就是本次安装创建的目录。
- 原因：规范没有区分初始化时可信绑定的路径与 purge 时进程环境派生的路径。
- 建议：初始化时生成不可伪造的 installation ID，并在受保护的固定锚点登记每个 app root 的 device/inode/owner 与路径策略；purge 只接受登记根。若支持 XDG 覆盖，必须在 init 时显式确认并固定，purge 时环境变化只导致 fail closed。
- 可验证验收：改变任一 XDG 变量、cwd、symlink、mount 或同名 app 目录都不能改变删除目标；只有与安装登记和二次 inode 校验一致的目录可删。协议依据：[platformdirs Unix 实现](https://github.com/tox-dev/platformdirs/blob/main/src/platformdirs/unix.py)明确说明 XDG 环境变量覆盖。

### AQ-R3-010 — 中 — Codex 多 bucket/可空窗口没有确定映射

- 定位：`docs/design-proposal.md:474-479`、`docs/design-proposal.md:585-603`、`docs/design-proposal.md:956-960`；`docs/provider-contract.md:275-280`。
- 反例：本机 `codex-cli 0.142.5` schema 的 `GetAccountRateLimitsResponse` 同时有向后兼容的 `rateLimits` 和按动态 `limitId` 索引的 `rateLimitsByLimitId`；每个 snapshot 的 primary/secondary 都可为 null。正文只声明固定 `rolling-primary/rolling-secondary`，没有说明选择哪个 bucket、多个 bucket 如何变成 subject/capability、窗口为空返回何种状态。
- 原因：Codex 只登记了能力名称，没有像 DeepSeek 一样冻结字段到规范模型的完整语义映射。
- 建议：明确使用哪个稳定 bucket ID，或把每个受支持 limit ID 映射为独立、用户确认的 subject；冻结 primary/secondary null、未知 limit ID、动态 map key、reset 秒数和 reached type 的唯一状态。
- 可验证验收：single bucket、multi bucket、未知/重复 limit ID、primary/secondary 各自为空、两者都空、窗口值非法的 fixture 都产生唯一预期，且动态 key 不进入日志/指纹。

### AQ-R3-011 — 中 — Codex `protocol_schema_hash` 没有可复现输入配方

- 定位：`docs/design-proposal.md:357-363`、`docs/design-proposal.md:431-433`；`docs/provider-contract.md:176-193`。
- 反例：本机同一 `codex-cli 0.142.5` 执行 `generate-json-schema` 与 `generate-json-schema --experimental`，分别生成 267 与 335 个文件，聚合 schema 的 SHA-256 也不同；正文只说“canonical app-server schema hash”，没有指定 stable/experimental 模式、根文件、文件集合或组合顺序。
- 原因：只定义了单个 JSON 对象的 canonicalization，没有定义 schema bundle 的选取。
- 建议：冻结精确命令、是否启用 experimental、生成器版本、唯一根 schema 或按相对路径排序的 bundle Merkle/aggregate 算法；只哈希 Adapter 实际允许的方法也必须定义引用闭包。
- 可验证验收：两台干净机器对同一 Codex 版本得到同一 hash；切换生成模式、删改任一纳入文件或改变允许方法集合必然改变 hash；构建日志记录非敏感配方与 digest。

### AQ-R3-012 — 中 — 飞书文本幂等保留期在文档内外冲突

- 定位：`docs/design-proposal.md:518-521`、`docs/design-proposal.md:541-550`；`docs/provider-contract.md:393`；`docs/security-model.md:191-200`、`docs/security-model.md:210`、`docs/security-model.md:257-263`。
- 反例：一条飞书文本 `/刷新` 在第 25 天重放。设计方案、Provider 契约和安全模型第 11 节规定文本记录只保留 24 小时；安全模型第 10 节却写“飞书幂等……保留 30 天”，第 14 节又把“安全幂等/审计表”统一写成 30 天。实现者无法判断应拒绝重放还是允许新请求。
- 原因：卡片 30 天、文本 24 小时和审计 30 天在安全摘要中被合并成了一个“飞书幂等”口径。
- 建议：建立唯一 retention 表，逐类列出 CLI、Web、飞书文本、飞书卡片、审计、rate-limit ledger；其他章节只引用该表。
- 可验证验收：虚拟时钟在 24 小时和 30 天边界逐类验证读取、删除和重放结果；所有文档、配置默认值和清理任务使用同一常量/规范源。

## 协议与静态验证证据

1. 本机协议版本：`codex-cli 0.142.5`。
2. 本机生成命令：

   ```text
   codex app-server generate-json-schema --out <tmp>
   codex app-server generate-json-schema --experimental --out <tmp>
   ```

   stable/experimental 分别生成 267/335 个文件；二者都包含 `account/read` 与 `account/rateLimits/read`，但 schema bundle 不同。
3. 本机类型事实：`GetAccountResponse.account` 可为 null；ChatGPT `email` 可为 string 或 null；`GetAccountRateLimitsResponse` 没有稳定账户 ID，并包含兼容单 bucket 与可选多 bucket 表面。
4. 官方主源：[Codex app-server README](https://github.com/openai/codex/blob/main/codex-rs/app-server/README.md)说明初始化握手、`account/read(refreshToken=false)`、email 可为 null、`account/rateLimits/read` 的窗口字段与 Unix 秒时间戳；[DeepSeek 官方余额契约](https://api-docs.deepseek.com/api/get-user-balance/)与正文登记的字段、币种和金额字符串表面一致。
5. 本地文档静态检查：未发现 `TODO/TBD/FIXME/XXX`；本轮明确发现的未决产品项只有 Codex 身份基线。未将后续实施阶段的正常未勾选测试门禁误报为占位符。
6. 仓库状态：当前没有提交历史，权威内容为工作区现行文件；本轮未依赖 commit 差异得出结论。

## 收敛判定

`FAIL_WITH_12_ISSUES`

在 `AQ-R3-001` 获得用户决策、其余 11 项修订完成后，必须由新的独立 Agent 从零进行全量审计；不能只复查本清单。
