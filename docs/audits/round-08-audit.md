# Agent Quota 第 8 轮独立设计审计

- 审计日期：2026-07-18（Asia/Shanghai）
- 审计者：独立 Agent `/root/audit_round_8`
- 审计对象：当前工作区的 `README.md`、`docs/design-proposal.md`、`docs/provider-contract.md`、`docs/security-model.md`
- 审计结论：`FAIL_WITH_11_ISSUES`
- 严重度分布：Blocker 1 / High 7 / Medium 3
- 阶段 0A 结论：不通过。除仍待用户决策的 Codex 稳定身份 blocker 外，本轮另发现 10 个可由设计修订闭环的确定问题。

## 1. 范围、顺序与证据方法

本轮先在不读取历史审计结论的情况下，从头逐行阅读四个现行文档并冻结候选问题；随后才读取 `docs/audits/round-01-*` 至 `round-07-*`，用于去重、确认旧问题是否已关闭，以及识别哪些问题仍属于用户决策。没有把历史结论当成当前事实。

审计覆盖：Standalone core/CLI、Provider/凭据/身份、Codex local-stdio、DeepSeek HTTP、缓存/LKG/query generation、限流/并发/幂等、operation/error 代数、配置迁移/journal/恢复、LocalKeyRing、发行/trust、Hermes/飞书/Web 可选集成、保存期限/数据清单、阶段门禁。仓库当前没有应用代码，所以本轮能验证的是设计合同的完备性、可执行性、一致性与本机官方 schema 兼容性，而不是运行时实现。

证据等级：

- E1：当前本地文件、行号、命令输出或由本机已安装官方 CLI 生成的 schema。
- E2：官方上游文档或官方仓库材料。
- E3：跨现行文档的规范推导；所有推导均列出可复核前提。
- E4：历史审计/处置记录，仅用于状态核对，不作为新问题的唯一依据。

本轮只执行读取、哈希、帮助/schema 生成到系统临时目录等非账户业务调用。没有调用真实 Provider 额度接口，没有执行 `account/read` 或读取任何真实账户、额度、Token、Cookie、动态 key、系统凭据、Hermes/飞书数据；没有安装依赖、启动项目服务、修改模型配置、切换分支、暂存或提交。唯一仓库写入是本报告。

## 2. 当前有效问题

### AQ-R8-001 — Codex allowlist 仍不能产生正式 fetch 所需的稳定主体证据

- 严重度：Blocker
- 确定性：高
- 状态：用户决策，非实现者可自行修复
- 证据：E1/E2
- 文件与行号：`README.md:3,33,53`；`docs/design-proposal.md:1025,1322-1330,1943-1951`；`docs/provider-contract.md:142-144,194-198`；`docs/security-model.md:175,375`
- 事实：现行合同要求 zero-binding `official-cli` 在正式 fetch 前提供可验证的账户/会话代际，core 再派生 `verified_stable` AccessIdentity；Codex 发送 allowlist 仅含初始化与 `account/rateLimits/read`，并明确禁止加入 `account/read`。本机 `codex-cli 0.142.5` 生成的 `GetAccountRateLimitsResponse` schema 只要求 `rateLimits`，可选 credits/map，不含稳定账户或会话主体；生成的 v2 schema 原始 SHA-256 为 `efe472413e781e7be004c84993bb3954b7d505fa35c7522f33f389ba7744ed7d`。因此当前 allowlist 没有可登记为 stable subject evidence 的字段。
- 影响：Codex Adapter 按自身合同必须返回 `incompatible`，不能成为 Supported、不能正式 fetch、不能持久化缓存/LKG；阶段 1B 的 Codex 路径和阶段 0A 身份门禁均不能关闭。把进程、principal、binding 或速率窗口键当稳定主体会违反身份与限流安全边界。
- 修复：只能由用户在历史上已列明的互斥产品基线中选择：批准一种额外只读稳定身份来源并相应扩展协议，或保留最小 allowlist、将 Codex 降级并替换第二个 MVP Adapter。本审计不代用户选择、不加入 `account/read`、也不移除 Codex。
- 验证：所选基线形成新的、封闭的 source contract；官方 schema fixture 能给出稳定主体或明确替代路径；账户切换、重新登录、进程重启、多 principal 同账户/异账户测试同时证明 cache 隔离和 cohort 合并正确；在此之前 Codex Supported/fetch fixture 必须继续 fail closed。

### AQ-R8-002 — 身份派生引用了 manifest 中不存在的 source contract 与 budget-group 注册表

- 严重度：High
- 确定性：高
- 状态：当前缺陷
- 证据：E1/E3
- 文件与行号：`docs/design-proposal.md:717-739,748-772,985-1023`；`docs/provider-contract.md:138-148`；`docs/security-model.md:175,178`
- 事实：`EvidenceAuthorizationBinding` 携带 `source_contract_id/source_generation`，`UpstreamSubjectEvidence` 携带声称来自 manifest 有限枚举的 `provider_identity_domain`，保守 cohort PRF 又使用 `endpoint_budget_group`。但 `AdapterManifest` 的封闭字段没有 identity source contract、identity domain 或 endpoint budget-group 注册表；文档也没有给出这些对象的 schema、唯一性、引用闭包、允许 evidence 来源、稳定性证明或 generation 规则。`endpoint_budget_group` 只出现在 PRF 输入中。
- 影响：core 无法按声明离线验证 source contract、稳定主体域与保守预算组，也无法保证不同实现对同一 manifest 派生同一 AccessIdentity/cohort。恶意或错误 Adapter/Source 可提交未登记域，或者不同实现退化成自行命名的 budget group，造成缓存错复用或预算拆分。
- 修复：在 manifest/registry 中加入封闭、版本化的 `IdentitySourceContract` 与 `EndpointBudgetGroup` 模型，明确 source kind、授权 binding、允许的 evidence 字段、provider identity domain、stable/ephemeral 证明、generation 和 endpoint 到 budget group 的唯一映射；加入完整闭包与未使用/悬空/重复拒绝规则。
- 验证：canonical schema/golden manifest 覆盖合法 DeepSeek、Codex undecided、未知 source、跨 profile、重复 domain、悬空 budget group 和同 endpoint 多映射；两套独立实现对同一输入生成相同派生值，所有未登记输入在派生前失败。

### AQ-R8-003 — 会产生 Provider I/O 的 probe/discovery 位于 rate reservation 之前或完全不计账

- 严重度：High
- 确定性：高
- 状态：当前缺陷
- 证据：E1/E3
- 文件与行号：`docs/design-proposal.md:328-349,985,1322-1338,1394-1407`；`docs/provider-contract.md:191-198,369-371`；`docs/security-model.md:180-183,187`
- 事实：唯一执行矩阵让 `doctor/discover` 的在线 probe/discovery 在没有 `rate_ledger_reserve` 的路径上运行；`refresh` 也先 probe，后 reserve。Codex 的 probe 状态机实际发送业务 RPC `account/rateLimits/read`，而 rate ledger 规定任何 Provider byte/子进程业务 RPC 发生前必须把 reservation 提交。`ProbeResult` 又被限制为 compatibility/version/identity evidence，不能承载业务额度结果，意味着后续 fetch 仍需再次读取。
- 影响：doctor/discover 可绕过 floor/hour budget；refresh 在获得 reservation 前已经读取一次额度，并可能为一次用户动作读取两次。对 zero-binding Codex，identity 由这个未计账读取产生，而 ledger 又要求 identity/cohort 才能 reserve，形成 bootstrap 循环。多进程和复制 principal 可利用未计账 probe 放大上游调用。
- 修复：把纯本地协议/版本验证与会产生业务 I/O 的动作分开。所有会发送 Provider byte 或业务 RPC 的 probe/discovery/fetch 都必须有明确 `request_kind` 并先进入同一 ledger；身份未知阶段使用唯一部署级保守 cohort 预留，完成稳定身份验证后只能按机器规则归并/提交，不能再发第二次等价业务请求。若一次 Codex RPC同时提供身份与额度，应把该单次已预留结果作为本次 fetch observation 使用。
- 验证：为 doctor/discover/refresh 和 HTTP/local-stdio 生成逐字节 I/O trace；断言每个 outbound attempt 恰有一个先提交的 reservation、同一次 Codex refresh 只有一个 rate-limit read、crash/cancel 边界不超 floor/hour；无身份 bootstrap 的并发测试不能扩容。

### AQ-R8-004 — migration plan envelope 无法规范表示 create 和 cascade 依赖

- 严重度：High
- 确定性：高
- 状态：当前缺陷
- 证据：E1/E3
- 文件与行号：`docs/design-proposal.md:1457-1481,1657-1667`；`docs/security-model.md:247,253-255`
- 事实：action `kind` 允许 `create`，但 `object_ref` 被要求必须是“当前 registry 中”的 opaque ID，因此新对象没有合法引用。排序时先移除 `action_id/cascade_parent_action_id` 后按 action bytes 排序并编号，随后要求 parent 是更早 action；合同没有给出编号前的 canonical parent key、拓扑排序或父子同序 tie-break，所以 cascade 关系既不参与初始排序，也无法在编号前确定。
- 影响：初始化/配置新增对象无法构造合法 envelope；同一 cascade graph 可因实现遍历顺序不同产生不同 action ID/digest，甚至合法父动作被排在子动作之后。dry-run、确认 nonce、journal 重放和跨实现恢复因此不能保证同一计划。
- 修复：把 existing object reference 与 new-object canonical handle 设计成判别联合；为未编号 action 定义稳定 semantic key。cascade parent 先引用该 semantic key，执行确定性拓扑排序并定义同层 tie-break，最后才赋 action ID；把完整有向图纳入 digest，并明确 cycle/duplicate 拒绝。
- 验证：golden vector 覆盖 create、create 后 update、单层/多层 cascade、同层不同输入顺序、cycle、重复 semantic key 和 999999 边界；两套实现及重启恢复必须产生相同 bytes/digest/action order。

### AQ-R8-005 — journal 前临时文件在属性回写前崩溃会永久关闭 gate

- 严重度：High
- 确定性：高
- 状态：当前缺陷
- 证据：E1/E3
- 文件与行号：`docs/design-proposal.md:1657-1675`；`docs/security-model.md:222,253`
- 事实：状态机先插入只含 basename/plan 的 `claimed` 行，再 `O_EXCL` 创建并写临时文件，最后才把 device/inode/owner/mode/nlink/digest 回写 claim。若在文件创建后、属性回写前崩溃，无 active journal 的恢复规则要求文件存在时逐项匹配 claim 中的全部属性和 digest；这些字段尚不存在，因此既不能证明匹配并删除，也不能按“文件不存在”分支清 claim。无 claim/不匹配又明确要求 fail closed 并保持 gate 关闭。
- 影响：一个设计内承诺覆盖的 kill point可把安装永久卡死；正常的更大 fence 接管也无法恢复，除非人工越过安全状态机处理机密临时文件。
- 修复：给 claim 定义至少 `name_claimed → file_opened → file_sealed → attached/cleanup_claimed` 的封闭状态与字段不变量。对 pre-attribute 文件使用可验证的安全恢复：例如创建后立即在同一受控目录句柄下记录 inode，再写内容并 seal digest；每个阶段明确可删除/可重建条件，旧 fence 无权推进。
- 验证：在 create、fchmod、write、file fsync、directory fsync、属性回写的每个系统调用前后 kill；接管者只能安全删除本 migration 文件或继续，不误删 symlink/替换 inode，且 gate 最终收敛。

### AQ-R8-006 — LocalKeyRing purpose 与身份/ledger 实际依赖不闭合

- 严重度：High
- 确定性：高
- 状态：当前缺陷
- 证据：E1/E3
- 文件与行号：`docs/design-proposal.md:987-1020,1394-1403,1485-1495`；`docs/provider-contract.md:146-150`
- 事实：身份函数实际使用 `access_identity_key`、`cache_identity_key`、`cohort_key`，rate ledger digest要求 `rate-ledger` purpose；但 LocalKeyRing 初始化列出的固定 purpose 只有 `query-generation-v1`、`access-identity-v1`、`rate-limit-cohort-v1`、`pseudonym-v1`、`idempotency-binding-v1`、`action-signing-v1`，没有 `cache-identity-v1` 或 `rate-ledger-v1`。同时只为 binding key 到 registry/keyring envelope key给出 HKDF Extract/Expand，未给根 key 到各 purpose key 的 exact salt/info/输入编码。
- 影响：合规实现无法构造两个必需 key，或只能自行复用/发明 HKDF recipe；这直接破坏文档要求的 cache/cohort/query/ledger domain separation 和跨实现互操作。
- 修复：建立唯一 machine-readable purpose registry，至少补齐 `cache-identity-v1` 与 `rate-ledger-v1`，并为 root key 到每个 `(purpose,generation)` key 冻结 exact HKDF Extract salt、Expand info、长度和 JCS/字节编码；明确轮换/verify-only 生命周期和哪些 purpose 不允许兼任。
- 验证：两套实现互读固定 root/generation golden vectors；任意 purpose 交换产生不同 key，缺 purpose/未知 purpose/复用 key 失败；cache identity、cohort 与 ledger digest 端到端 fixture 可构造。

### AQ-R8-007 — 声称唯一的 operation/error 数据源仍不可机器执行

- 严重度：High
- 确定性：高
- 状态：当前缺陷
- 证据：E1/E3
- 文件与行号：`docs/design-proposal.md:299-308,328-351,386-412`；`docs/security-model.md:187`
- 事实：执行矩阵把 `C/M/E`、`offline/http/official_cli_zero_binding` 和未定义的 `consent_validate?` predicate 混在 Markdown 中；错误表虽声称工具只展开 `a|b`，却使用“任一”“任一需要 SQLite 的 operation”“实际 SQLite stage”“任一需要 key”“实际失败阶段”等自然语言集合。入口 `invalid_operation_envelope` 的 contract failure 仍要求 `requested_operation: RequestedOperation`，但未知/非法 operation 恰好不能构造该封闭字段。
- 影响：无法从当前表唯一生成 enum validator、全笛卡尔 fixture和公开失败 envelope；不同实现会自行解释集合和可选阶段。非法入口要么在解析前无法序列化错误，要么被迫伪造一个合法 operation。
- 修复：把权威源移为版本化 JSON/YAML/typed literal，每行只使用 exact enum 和显式 predicate ID；展开后生成文档投影。`OperationContractFailure` 应保存受限 raw-operation digest/枚举 `unknown` 或使 requested operation 可空，且不能回显原始不可信文本。
- 验证：生成器对全部 operations/modes/stages/errors 输出无歧义闭包；文档表由 artifact 反向校验；unknown、拼写错误、额外字段、缺字段都能在零副作用下构造 deterministic contract failure。

### AQ-R8-008 — refresh 成功值不能表达规范要求的多请求部分结果

- 严重度：High
- 确定性：高
- 状态：当前缺陷
- 证据：E1/E3
- 文件与行号：`docs/design-proposal.md:353-384,398-400,1411-1417`；`docs/provider-contract.md:355-371`
- 事实：`RefreshCommitted` 只有一个全局 `disposition` 和 snapshots。与此同时，`refresh(all)` 明确允许多个 request 同时出现 provider-called、singleflight、排队取消、timeout/capacity/failure，并要求已完成 request 正常提交、失败 request 覆盖其完整 request keys，最终 success 可含部分 snapshots。当前成功代数没有 per-request key、disposition、failure 或 LKG 结果项；失败的完整 key 集也无处返回。
- 影响：调用者无法区分未请求、失败、合并、使用 LKG 与真正空结果；幂等 replay 也无法还原同一次部分结果。实现要么丢信息，要么发明未登记字段/顶层 OperationError，违反唯一合同。
- 修复：把 refresh value 改为有界、canonical 排序的 per-request result tuple；每项绑定完整 request key/digest，并以封闭联合表达 fresh provider result、singleflight join、LKG/stale、deferred、timeout/capacity/failure及 snapshots。明确何时整体是 success、何时是 OperationError，以及幂等 ledger保存的完整结果 envelope。
- 验证：golden cases 覆盖 2+ requests 的成功+timeout、成功+capacity、join+provider、LKG+失败、全部失败和重放；每个输入 key 恰有一个结果，顺序与并发完成次序无关。

### AQ-R8-009 — 所有 lease/reservation 的时长与续租公式未冻结

- 严重度：Medium
- 确定性：高
- 状态：当前缺陷
- 证据：E1/E3
- 文件与行号：`README.md:52`；`docs/design-proposal.md:1096-1117,1394-1417,1655-1667`；`docs/security-model.md:181,222,253`
- 事实：合同依赖 rate-ledger writer lease、reservation expiry、queue/slot lease、migration writer lease 和 temp-claim lease，并用其决定接管、删除与 liveness；但 `aq-bounds-v1` 和其他唯一常量源没有给出这些 lease 的 exact duration、renewal threshold、最大延期、clock source及与 attempt/parent deadline的公式。README 却宣称“全部安全数值”已冻结。
- 影响：两个均自称合规的实现可在不同时间接管或回收。过短会让仍在运行的 owner 被抢占/文件被删，过长或不续租会造成死锁和长期 gate 关闭；虚拟时钟验收没有唯一预期。
- 修复：增加 machine-readable `LeasePolicyV1`，逐类规定 DB UTC/monotonic 用途、duration、renew-at、max lifetime、reservation expiry、fence takeover条件，以及与 transport/parent deadline的精确 min/max 公式；文档只引用符号。
- 验证：固定虚拟时钟表覆盖续租前后、`now == expiry`、owner pause/kill、DB clock跳变约束、最长 attempt与迁移恢复；两套实现得到相同接管时刻和状态转移。

### AQ-R8-010 — retention lint 会拒绝自己的规范，且依赖 CommonMark 未定义的 slug

- 严重度：Medium
- 确定性：高
- 状态：当前缺陷
- 证据：E1/E2/E3
- 文件与行号：`docs/security-model.md:225-239`
- 事实：lint 声称扫描 code span、fence、table、HTML，duration literal 的 exact allowlist 只有保存期限表第 3 列和 ACTION_TTL paragraph。但 lint 规则正文自身在 allowlist 外同时出现 marker `retention` 以及反例 literal `thirty days`、`2.592e6 seconds`，按自己的规则必须失败。定位又要求“按 CommonMark slug”，而 CommonMark 0.30 规范定义 AST/heading syntax，并没有定义 renderer 的 heading slug/ID 算法。
- 影响：按文字实现的 CI 无法让当前规范通过；若实现为了通过而特判本段，则 exact allowlist 声明不真实。不同 renderer 的 slug 差异还会让允许位置不可移植。
- 修复：以 exact file + CommonMark AST heading path/ordinal/table column定位，不使用 slug。把恶意 duration fixture 移到不属于 lint 输入的版本化 fixture 文件，或在 machine config 中显式登记 fixture AST node；规则文档只引用 fixture ID，不复制 literal。
- 验证：先对当前四文档运行 lint应通过；每个外部反例都失败；更改 heading 文本/renderer不改变定位；在 code/table/HTML复制真实 TTL 仍失败。

### AQ-R8-011 — nonce replay 集无界增长，最终会使 LocalKeyRing 自行失效

- 严重度：Medium
- 确定性：高
- 状态：当前缺陷
- 证据：E1/E3
- 文件与行号：`docs/design-proposal.md:1096-1112,1493-1497`
- 事实：registry payload永久保存“已使用 keyring nonce SHA-256 集合”，每次 keyring 写入都先新增一个 digest；没有退休、压缩、分 key generation 上限或重置规则。与此同时 envelope 限 1 MiB、JSON node 限 100000，purpose rotation和普通更新都可持续写 keyring。
- 影响：长期运行后合法更新必然触及 bytes/node 上限，新的 keyring/registry envelope无法构造，启动按合同返回 `local_keyring_unavailable` 并关闭 gate。删除旧 nonce 又没有安全规则，会与“从未出现”证明冲突。
- 修复：采用可证明唯一且有界的 nonce方案，例如把严格单调 envelope sequence 与每代独立 AEAD key纳入确定性 nonce构造；或定义每代有界 nonce registry、达到上限前强制 key rotation，并给出旧集合可退休的精确证明和 journal 流程。
- 验证：模型检查/长跑跨越最大预期写次数与多次 rotation；nonce在同一 AEAD key下从不复用，envelope始终低于 bounds；接近上限、崩溃、rollback、旧备份和 rotation交叉点均有 golden fixture。

## 3. 历史核对与分类

### 3.1 仍属于用户决策

- 第 7 轮 `AQ-R7-001` 对应本轮 `AQ-R8-001`：当前 schema/allowlist 再验证后仍是 blocker；本轮没有替用户选路线。

### 3.2 已关闭，未作为当前问题重复报告

- 第 1 至第 7 轮处置记录所修订的主体模型、credential binding、渠道无关授权、cache/LKG generation、HTTP GET/URL、发行 trust/attestation、bounded parse、Codex wire 省略 `jsonrpc`、exact argv/notification opt-out、migration 主 journal、retention inventory 等主问题，在当前文本中均能找到对应闭环结构。
- 本机生成的 Codex v2 schema确认 app-server request/response envelope省略 `jsonrpc`；现行专用 wire在这一点与本机官方 schema一致，因此未把它重新报为问题。
- DeepSeek 当前使用固定 `GET /user/balance`、bearer 注入和公开 endpoint contract；本轮未发现足以形成另一项确定缺陷的现行冲突。

### 3.3 不适用或未升级为问题

- 仓库无实现代码，无法执行 unit/integration/e2e、依赖扫描、数据库迁移或真实 UI/服务测试；这不是“测试通过”，而是当前设计阶段不适用。
- Hermes、飞书、Web 是可选后续集成且门禁位于 3A；本轮仍审阅其授权、LLM consent、幂等和数据边界，但没有把纯实现期缺失升级为阶段 0A blocker。
- 未读取真实账户来验证 quota 值，也未以真实账户探测弥补 Codex schema 缺失；隐私边界优先。

### 3.4 本轮新问题与历史关系

- `AQ-R8-002` 至 `AQ-R8-011` 均不是简单重报已标记关闭的旧 ID，而是第 7 轮新增/收紧的 machine contract 在组合验证后暴露的缺口：source registry缺失、执行矩阵与 rate ledger顺序冲突、plan canonicalization、pre-journal crash window、purpose闭包、结果代数、lease数值、lint自举和 nonce有界性。

## 4. 可复核证据与完整性

### 4.1 当前源文件 SHA-256

```text
889d4bd0463028cae404889bc9b7c5d18c21986e036ebcec65d12b7cdcae8c06  README.md
a01fb4ad3240a5cbebfb8b4727750f43b607fce0cb8811fa602aca1a03ead992  docs/design-proposal.md
7feb1a5777e05b1022c62b758b3b99a7e1882f0e0874d4cfd810063f89c598bf  docs/provider-contract.md
de41d35b8578892f124f64662f94fd8254bc84170617e2407ccb6230b4bdf471  docs/security-model.md
```

### 4.2 历史文件 SHA-256

```text
a00a14c901881d84ba7648987a2cb7ceff92b41bd9f077a13605e38bad76abdd  docs/audits/round-01-audit.md
c997a3853d0d47b9e44e1fbb0f8476ddbdf9006438855a3cf1cd246857b54c9a  docs/audits/round-02-audit.md
4c0283dfe7827922b0be8001e8b0d381e247ac6f6fab3d8c95d9c95aba2cca32  docs/audits/round-03-audit.md
ea0e5002fa17b6d3a8396c5ce8d11fa321e45ae2b1470ba33149a845b1a82897  docs/audits/round-04-audit.md
7339b048a03f98b91119d01fec86d6364af645043da42cbfc42617de48542c86  docs/audits/round-05-audit.md
0924b992e71170ef4944980e37c7fe85fdf1a56a09a489ab77b9d987de62cd32  docs/audits/round-06-audit.md
91af1b28dd94c9372eeeb0410e0a8a77b20df3c293a64f4d33d76aba601482c9  docs/audits/round-07-audit.md
c4630344e20561d3677e6d393cf206f4bf6d438871444d28e9d7872dedd53935  docs/audits/round-01-resolution.md
8b13adaec95df01fa7da78bbed6c305076597535f4e415f396840be4774c65df  docs/audits/round-02-resolution.md
7ad08ed95a607d1a353c9c54d4bbd359798dd6145c2f6a3918204e3efae12581  docs/audits/round-03-resolution.md
2b57e50bbfe68928a74a7d2d090614407909a5da1481c80db6710219cd2cf171  docs/audits/round-04-resolution.md
0c3858ded76f622b3dc50ec87c9de0f931f97b6cdd93b0f0ed9de2f98c3d27a4  docs/audits/round-05-resolution.md
97048a24cab36d824726227278d68f71e74d60650abf3e1488438da8ed448609  docs/audits/round-06-resolution.md
9c9593995ac82d1a10475b32db790ea5b40ccd8be8a6be9bd963a0487637175b  docs/audits/round-07-resolution.md
```

### 4.3 本机/官方协议核验

```text
codex executable: /Users/kyle/.npm-global/bin/codex
codex version: codex-cli 0.142.5
app-server transport: `codex app-server --help` 接受 `--stdio`，stdio 为默认 transport
generated v2 schema hash: efe472413e781e7be004c84993bb3954b7d505fa35c7522f33f389ba7744ed7d
```

核验的官方材料包括 OpenAI Codex app-server README/schema、DeepSeek user balance API 文档和 CommonMark 0.30 规范。外部材料只用于确认本机/上游合同；每个当前问题仍有现行本地文档证据。

### 4.4 工作区状态与写边界

- Git 状态为 `No commits yet on main`；当前文件均为未跟踪状态。
- 本轮未改动 `README.md`、三个现行设计文档、`.gitignore` 或历史审计/处置记录。
- 未执行 `git add`、`git commit`、分支切换、远端写入或任何账户业务调用。

## 5. 最终门禁

`FAIL_WITH_11_ISSUES`

在 `AQ-R8-001` 获得用户产品决策，且 `AQ-R8-002` 至 `AQ-R8-011` 按各自验证门禁闭环前，不应宣告“零问题”、不应通过阶段 0A，也不应开始把 Codex 当作 Supported MVP Adapter 实现。其余 10 项不需要扩大产品范围，可以直接通过收紧现有 machine contract 修复。
