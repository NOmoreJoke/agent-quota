# 第 6 轮独立对抗性设计审计

> 审计结论：`FAIL_WITH_17_ISSUES`  
> 严重度：阻断 1 / 高 6 / 中 8 / 低 2  
> 审计日期：2026-07-18  
> 审计对象：当前工作区中的 `README.md`、`docs/design-proposal.md`、`docs/provider-contract.md`、`docs/security-model.md`  
> 实施状态：仓库仍无应用代码、无 commit；本轮只能验证设计合同、当前官方协议 schema、文档一致性和可执行命令，不能声称运行中的 Agent Quota 已通过测试

## 1. 唯一结论

本轮不能通过零问题门禁。共确认 17 项当前问题：1 项必须由用户决定的 Codex 产品基线，另有 16 项可以直接修复的设计缺陷。除 Codex 身份决策外，仍有 6 项高、8 项中、2 项低严重度问题。

Codex 身份问题被独立复现：当前允许的 `initialize → initialized → account/rateLimits/read` 稳定表面没有账户或会话身份。官方另有只读 `account/read`，但 ChatGPT 身份字段可为空，且“邮箱是否足以代表实际 rate-limit subject”仍是产品判断。本报告不替用户放行 RPC，也不替用户把 Codex 移出 MVP。

## 2. 证据等级与方法

按 `audit-verify-explain-grade-5` 的顺序使用证据：

- `E1`：自动执行的测试、解释器反例或校验器结果。
- `E2`：运行真实命令或工作流。
- `E3`：生成的 schema、hash、日志或构建产物。
- `E4`：现行正文与官方源码/官方文档的静态核对。
- `E5`：缺少更强证据时的明确推断。本报告没有仅凭 E5 成立的问题。

审计顺序：先完整读取四份现行正文并冻结独立候选清单；之后才读取第 1～5 轮 audit/resolution，避免被旧结论锚定。历史只用于检查当前正文是否已经真正闭环，不用于生成本轮候选。

执行过的主要只读/隐私安全验证：

1. `nl -ba` / `sed`：逐行读取四份现行正文。
2. `codex --version`：本机为 `codex-cli 0.142.5`。
3. `codex app-server generate-json-schema --out <empty-temp-dir>`：未启用 `--experimental`；只分析 stable v2 schema 的字段名、required、类型、方法集合和基数合同。
4. `jq`：确认 `GetAccountRateLimitsResponse` 只有 rate-limit/credit 表面；`initialize` 返回的协议表面不提供账户身份；stable schema 同时含只读 `account/read` 与 `account/rateLimits/read`。
5. stable v2 聚合根原始 SHA-256：`08890d08b7747c8d01dc4fd305d41b187fe95f5eeecb22df0ef6366f6783791b`。该值只是本次本机生成物证据，不被当成设计中的 canonical bundle hash。
6. Python 3.11 最小反例：按正文原样执行 `OperationResult[T] = OperationSuccess[T] | OperationError`，得到 `NameError`。
7. 官方一手来源：[OpenAI Codex app-server README](https://github.com/openai/codex/blob/main/codex-rs/app-server/README.md) 与 [DeepSeek Get User Balance](https://api-docs.deepseek.com/api/get-user-balance/)。

本轮没有启动账户读取 RPC，没有读取或复制真实邮箱、账户标识、计划、额度、重置时间、动态 bucket key、Token、Cookie 或任何账户响应。报告只记录 schema、类型、基数、版本和摘要。

## 3. 必须由用户决定的问题

### AQ-R6-001 — Codex 当前 allowlist 不能产生稳定 subject/AccessIdentity

- severity：`blocker`
- 确定性：高
- 证据等级：`E2 + E3 + E4`
- 定位：`docs/design-proposal.md:645-648,685-695,754-768,837-839,946-962,977-999`；`docs/provider-contract.md:142-149,174-180,190-201`；`docs/security-model.md:166-178`；`README.md:3,31`
- 事实：现行合同要求零 binding 的 official-cli 在正式 fetch 前得到 `verified_stable` 身份，并在账户切换时改变 cache identity。当前 schema bundle allowlist 只有握手和 `account/rateLimits/read`；该响应只有额度/credit 结构，初始化响应也没有稳定账户/会话身份。[OpenAI 官方 Auth endpoints](https://github.com/openai/codex/blob/main/codex-rs/app-server/README.md#auth-endpoints)列出另一个只读 `account/read`，但 ChatGPT `email` 可以为 `null`。
- 影响：账户 A 切换到 B 后，core 无法证明缓存、LKG、限流 cohort 和 subject 绑定必须改变。Codex 不能满足 Supported 身份门禁。
- 可操作修复：用户必须二选一：A）允许只读 `account/read(refreshToken=false)`，再明确可接受的稳定身份元组、空值 fail-closed、最小披露和 subject 语义；B）Codex 退出 MVP Supported/第二真实 Adapter 门禁，换成有稳定身份合同的 Provider。不得由修复 Agent 代选。
- 验证标准：覆盖同账户重启、A→B、登出重登、`account=null`、身份字段为空、非 ChatGPT account；旧缓存/LKG 不可见，原始身份材料不进入 TOML、SQLite/WAL/SHM、日志、fixture、投影或审计；最终 RPC allowlist、schema bundle、发送端测试与三份正文一致。

## 4. 可直接修复的高严重度问题

### AQ-R6-002 — Installation binding key 没有可实现的持久化合同

- severity：`high`
- 确定性：高
- 证据等级：`E4`
- 定位：`docs/design-proposal.md:1058-1079`；`docs/security-model.md:234-236`
- 事实：正文定义了 registry envelope 和加密 keyring envelope，也说两者依赖 32-byte `installation_binding_key`；但没有定义该根秘密实际存放在哪个文件或 OS backend、文件名/编码/权限、首次创建原子性、no-follow 读取、备份/恢复和 purge 顺序。`key_id` 又依赖未在 key entry 中定义的 `public salt`。
- 影响：新安装无法从正文唯一实现“重启后先取得 binding key，再验 registry MAC、再解 keyring”的链；不同实现会产生不兼容格式，或把根秘密误放进 registry/SQLite/普通备份。registry、trust-bundle floor、cohort、幂等和 action key 都因此失去共同根。
- 可操作修复：冻结唯一 binding-material backend。若用文件，定义固定 anchor-relative 文件名、exact bytes/envelope、`0600`/owner/mode/no-follow/device/inode、`O_EXCL` 初始化、fsync/rename、备份和 purge；若用 Keychain/Secret Service，定义条目 ID、不可用/丢失/恢复状态。同步定义 `public_salt` 的生成、存储和 key-id recipe。
- 验证标准：两套独立实现能在重启后互读；覆盖 binding material 单独丢失、替换、截断、权限放宽、symlink、registry/keyring/binding 三者交换、初始化崩溃、恢复和 purge；所有异常都在读机密数据前稳定返回 `local_keyring_unavailable`，不静默重建。

### AQ-R6-003 — 多进程刷新限流只有持久化键，没有原子 check-and-reserve

- severity：`high`
- 确定性：高
- 证据等级：`E4`
- 定位：`docs/design-proposal.md:1003-1011,1016-1023,1025-1029,1230-1232`；`docs/provider-contract.md:368-382`；`docs/security-model.md:172-178,214,240`
- 事实：正文冻结了 request-floor/hourly bucket 的键并要求跨重启持久化，但没有定义两个 CLI、CLI+daemon 或两个 SchedulerHost 在 Provider 调用前如何原子预留同一个 bucket。幂等只约束同一 actor/request key，不能阻止两个不同请求同时通过相同 cohort/endpoint 的限流检查。
- 影响：两个进程可以同时读到“尚有预算”，随后都访问 Provider，绕过 30 秒/5 分钟地板或小时上限；崩溃后是否计入预算也不确定。复制进程虽不复制 principal，仍可扩容真实请求次数。
- 可操作修复：为 `RET-RATE-LEDGER` 定义 SQLite `BEGIN IMMEDIATE` 的 `available → reserved → committed|outcome_unknown` 状态机和 fencing/lease；在解析凭据前原子检查 DB UTC、预留完整 request-floor key及 endpoint-hour key。明确被 singleflight 合并、排队超时、Provider 前崩溃、Provider 后崩溃和 Retry-After 的计数规则。
- 验证标准：用两个独立进程和虚拟时钟同时刷新相同 cohort/endpoint；在 floor/hour 上限下 Provider 调用总数不超限。逐点 kill 后重启不能释放已可能发生的调用预算，也不能永久死锁；复制 principal/binding/进程不增加预算。

### AQ-R6-004 — `verified-install-plan-v1.json` 被称为“已签名”，但没有签名与信任合同

- severity：`high`
- 确定性：高
- 证据等级：`E4`
- 定位：`docs/design-proposal.md:910-944,1083-1096`；`docs/security-model.md:176`
- 事实：生产安装器依赖 release directory 中的 `verified-install-plan-v1.json` 来批准完整第三方 wheel 文件名/hash。正文只说“验证签名 install plan”，没有定义 envelope schema、canonical bytes、签名 domain、signer key 用途、distribution/extras/Python tag 绑定、有效期、撤销、bundle sequence 或 plan 自身如何被 bootstrap lock/attestation 固定。第 8.3.1 节只定义 wheel attestation 和 trust bundle 两种 envelope。
- 影响：若实现把 plan 当普通 JSON，攻击者可一起替换 plan 与第三方 wheel；Agent Quota 自有 wheel 的 attestation 仍通过，但恶意依赖会被 hashed pip 安装。若各实现自行设计签名，生产安装路径不可互操作。
- 可操作修复：定义 `aq-verified-install-plan-envelope-v1` 的 exact schema、JCS bytes、Ed25519 domain、publisher key purpose、trust-bundle binding、sequence/expiry/revocation；payload 必须绑定 installer/core/meta/Provider 版本、requested extras、Python ABI/platform tag、全部文件名/hash和禁止额外文件。也可把 canonical plan digest直接纳入每个相关受信任 attestation并定义闭包验证。
- 验证标准：替换 plan、依赖 wheel、extras、Python target、字段顺序/Unicode、signer、sequence 或增添文件均在任何目标代码执行前拒绝；两套独立 installer 对 golden plan 互验。

### AQ-R6-005 — 封闭 OperationResult/授权操作代数无法表达正文要求的结果

- severity：`high`
- 确定性：高
- 证据等级：`E4`
- 定位：`docs/design-proposal.md:253-320,1018-1023,1384-1388`；`docs/provider-contract.md:109-116,336-366`；`docs/security-model.md:152-160,183,240`
- 事实：`OperationErrorCode` 没有普通 invalid-config/storage/cache/rate-ledger 错误，也没有安全模型明确返回的 `consent_required`；`RequestedOperation` 没有 alert acknowledgement、consent grant/revoke 等正文已有的状态变更。Provider 契约还构造不存在的 `OperationError(operation="credential_resolve", ...)`，而唯一模型要求 `requested_operation + failed_stage`。`outcome_unknown`/本地刷新地板拒绝的外部结果 DTO 也未冻结。
- 影响：同一错误可能被实现为未捕获异常、错误 snapshot、任意字符串或不合法 DTO；日志/飞书/Web 可能回显堆栈或上游文本，重试者也无法区分安全失败、预算延后和未知结果。默认拒绝的授权映射并不覆盖所有已设计写操作。
- 可操作修复：建立完整判别联合：actor 请求、内部阶段、operation error、refresh/idempotency status、integration consent/action error 分层但闭包；补齐 config/storage/ledger/projection 等安全错误与 alert/consent 操作，删除 `operation=` 旧字段。每个 code 固定合法 operation/stage、retryable、safe_params 和副作用。
- 验证标准：为每个 operation/stage/code 生成正反例矩阵；非法组合在读取缓存前拒绝。invalid TOML、SQLite 不可用、rate ledger 失败、consent 过期、alert ack、`outcome_unknown` 和 system credential backend 不可用都能严格序列化，且无自由文本/LKG/部分写入。

### AQ-R6-006 — 安全关键数值缺少机器可读上下界

- severity：`high`
- 确定性：高
- 证据等级：`E3 + E4`
- 定位：`docs/design-proposal.md:388-399,539-568,579-599,621-643,798-813,964-975,983-999`；`docs/provider-contract.md:220-238,261-267`
- 事实：多个安全字段只是裸 `int/Decimal`：refresh floor/hour limit/provider concurrency、wire/decoded/frame/stdout/stderr bytes、max processes、discovery counts、`retry_after_seconds`。DeepSeek 金额 regex 没有限制总位数/小数位；Codex `resetsAt` 只要求非负，当前 stable schema 的 `int64` 也超出 Python UTC datetime 可表示范围。严格 `extra=forbid` 不会自动给这些值加上下界。
- 影响：负数/零可关闭限流或造成死锁；超大 manifest 值可取消资源上限；接近 1 MiB 的十进制字符串可造成昂贵 Decimal 解析/运算；超大时间戳可在转换时溢出并绕过“解析异常不得冒泡”的目标。
- 可操作修复：所有字段改用 `Annotated`/JSON Schema minimum/maximum，并冻结跨字段不变量和平台无关 UTC 范围。金额声明最大字符数、整数位、小数位/scale；Retry-After 声明合法来源、范围和超界策略；manifest 的 byte/process/discovery/concurrency 值设全局硬上限，签名也不能放宽。
- 验证标准：property/fuzz 测试覆盖负数、零、边界±1、巨大整数/Decimal/timestamp、NaN/Infinity、超大 signed manifest；在解析凭据/分配大对象/启动进程前得到稳定本地错误，内存和墙钟保持在固定上限内。

### AQ-R6-007 — official-cli 身份 DTO 的所有权方向错误，且 assurance 不是封闭枚举

- severity：`high`
- 确定性：高
- 证据等级：`E4`
- 定位：`docs/design-proposal.md:645-648,685-695,754-768,833-839`；`docs/provider-contract.md:124-159,190-201`
- 事实：正文说 `AccessIdentity` 必须由 core 使用 LocalKeyRing 生成；但 `ProbeResult` 让 Adapter 直接返回 `AccessIdentity`，没有可供 core 验证并派生身份的有限 `IdentityEvidence` DTO。Adapter 不拥有 core 的 HMAC key，因此无法合法构造 stable identity；若直接信任 Adapter 字符串，又破坏“core 生成”。同时 `assurance: str` 接受任意值，而下游只允许 `verified_stable|ephemeral`。
- 影响：即使用户解决 AQ-R6-001 并允许身份 RPC，接口仍没有安全的数据流把短暂身份证据交给 core。实现可能让 Adapter伪造 `verified_stable`，或把原始邮箱/账户字段塞进普通字符串并泄露。
- 可操作修复：把 Probe 输出改为封闭、source-specific、不可持久化/不可 repr 的 `IdentityEvidence`，由 core 校验 profile/协议/空值后立即用专用 LocalKeyRing purpose 生成 `AccessIdentity`；或把身份协议解析移动到受信 core helper。`assurance` 改为 Literal，并禁止 Adapter直接提交 keyed identity。
- 验证标准：恶意 Adapter 返回未知 evidence/assurance、跨 principal evidence、空身份、原始 PII 普通字符串均拒绝；A→B 必变 identity，同账户重启稳定；任何输出、异常和序列化都不含原始证据。

## 5. 可直接修复的中严重度问题

### AQ-R6-008 — `aq-assurance-v1` 仍缺完整字节级 canonical recipe

- severity：`medium`
- 确定性：高
- 证据等级：`E4`
- 定位：`docs/design-proposal.md:910-931`
- 事实：attestation/trust-bundle 已冻结 `aq-jcs-nfc-v1`，但 `adapter_payload_digest` 和 `assurance_payload` 仍使用未定义的 `canonical(...)`；没有冻结 tuple/object 编码、path normalization/排序、ZIP 重复 entry、symlink、mode bits、manifest carrier 唯一路径和 `agent-quota-assurance.json` sidecar schema。
- 影响：发布器与运行时验证器可对同一 wheel 得到不同 assurance；恶意/异常 wheel 的重复路径、symlink 或 mode 解释也不唯一，导致拒绝结果依赖实现。
- 可操作修复：给 `aq-assurance-v1` 单独定义 exact JCS schema与 domain、entry object字段、path/mode规则、重复/链接拒绝、唯一 manifest定位、sidecar envelope和排序。
- 验证标准：两套独立实现对正常 wheel、字段重排、Unicode、重复 ZIP path、symlink、mode 差异、manifest 多 carrier、单 bit 修改产生唯一且相同的接受/拒绝与 digest。

### AQ-R6-009 — Codex local-stdio 只有发送顺序，没有完整 JSON-RPC 相关性状态机

- severity：`medium`
- 确定性：高
- 证据等级：`E3 + E4`
- 定位：`docs/design-proposal.md:579-600,829-833,946-962`；`docs/provider-contract.md:236-245,417-419`
- 事实：合同定义了 `initialize → initialized → account/rateLimits/read`、frame 和 deadline，但没有定义 request ID 类型/唯一性、response ID 相关、error envelope、重复/未知 ID、初始化间插入 notification/server request、EOF/多 frame/尾随 frame的处理。OpenAI 官方协议是可双向发送通知/请求的 JSON-RPC 变体，不能安全地把“下一行”默认当成本请求响应。
- 影响：合法通知可被误判为响应；恶意/损坏本地进程可把另一帧绑定到 rate-limit 请求，造成错误身份/额度或不一致的 timeout/失败计数。
- 可操作修复：冻结连接级状态机和有限 incoming allowlist：core-generated request IDs、精确 response correlation、允许/忽略哪些通知、拒绝 server requests和多余帧、JSON-RPC error→本地分类、EOF/重复 ID行为。明确所有帧共用 execution/byte budget。
- 验证标准：fake stdio 覆盖通知前插、错 ID、重复 response、error response、unknown method、server request、EOF、分帧/多帧和尾随数据；只接受与当前 request ID、schema、阶段匹配的唯一响应，无 orphan。

### AQ-R6-010 — HTTP policy 暴露 POST/代理分支，却没有请求体或代理信任合同

- severity：`medium`
- 确定性：高
- 证据等级：`E4`
- 定位：`docs/design-proposal.md:533-578,829-835`；`docs/provider-contract.md:216-234`
- 事实：`HttpEndpointSpec.method` 允许 `POST`，但没有 body/content-type/schema/size/secret-injection policy；`HttpNetworkPolicy.allow_proxy` 可为 true，却没有 proxy host/port/auth/CA/no_proxy或凭据转发合同。正文同时要求 URL 和认证对象完全由 core 的结构化 spec 构造。
- 影响：未来 signed manifest 可进入 schema 明示允许、但 core 无法安全构造/校验的分支；实现只能让 Adapter自由构造 body/proxy，重新打开数据外发和资源上限缺口。
- 可操作修复：schema v1 直接把 HTTP method 限为 GET、`allow_proxy=False`；或新增判别式 RequestBodyPolicy/ProxyPolicy，并绑定 content type、canonical body schema、字节上限、proxy/CA/credential destination和双重发送对象比较。
- 验证标准：当前 DeepSeek 正例不变；POST/代理配置在没有完整 policy 时 offline 拒绝且凭据解析次数为 0。若实现新分支，覆盖 body 注入、超大 body、proxy userinfo/重定向/CA替换和认证泄漏。

### AQ-R6-011 — `plan_code` 有映射规则，但没有 Adapter 输出或更新路径

- severity：`medium`
- 确定性：高
- 证据等级：`E4`
- 定位：`docs/design-proposal.md:174-180,400-405,721-743,774-806,997,1008-1009,1206-1208`；`docs/provider-contract.md:83-95,180,261-267`
- 事实：Codex 已知 `planType` 被要求映射为有限 `plan_code`，但 `DiscoveryResult`、Fetch observations、ProbeResult 和 `SubjectConfig` 都没有 plan_code 字段。唯一运行模型 `QuotaSubject.plan_code` 因此没有来源；plan 变化是否修改 subject、触发确认、进入 query generation 也未定义。
- 影响：实现会丢弃已知 plan、私自改配置，或把上游 plan 当 label/自由文本；不同实现的展示与能力选择不一致。
- 可操作修复：明确二选一：MVP 完全丢弃 plan 并删除 plan_code/展示承诺；或增加受限 `SubjectMetadataObservation(plan_code)`，定义发现确认、后续更新、未知值丢弃、存储/retention、generation和告警影响。
- 验证标准：known/unknown/null/变化 plan fixture各有唯一结果；已知 plan能从协议到达 subject/projection而不经过自由文本，未知值不落盘；变化时配置/运行状态使用明确定义的事务且旧 generation行为唯一。

### AQ-R6-012 — 多币种 balance 不能同时配置多个 `balance_floor`

- severity：`medium`
- 确定性：高
- 证据等级：`E4`
- 定位：`docs/design-proposal.md:197-205,1160-1188,1210,1363-1374`；`docs/provider-contract.md:58-67,92,261-267`
- 事实：balance capability 明确可同时含 CNY/USD，`balance_floor` 又要求声明币种；但配置规则拒绝同一 capability/metric 重复，因此 CNY 与 USD 两条 floor 会互相冲突。
- 影响：多币种展示已支持，告警却只能保护其中一种币种；实现若自行把 currency加入唯一键，又违反当前严格规则。
- 可操作修复：把 policy identity/重复键冻结为 `(subject_id, capability_id, metric, dimension)`；`balance_floor.dimension=currency`，其他 metric使用各自唯一维度。episode仍可按 capability聚合 contributing sources。
- 验证标准：同一 wallet 的 CNY/USD 两条 policy可同时通过，各自独立命中/清除并聚合最高 severity；同币种真正重复仍拒绝，多币种不求和。

### AQ-R6-013 — 全量刷新并发和请求内重试语义未冻结

- severity：`medium`
- 确定性：高
- 证据等级：`E4`
- 定位：`docs/design-proposal.md:555-568,831-835,1005-1007,1025-1029,1528-1535`；`docs/provider-contract.md:226-238,313-334,368-382`
- 事实：正文要求全局/Provider并发限制，但只有 Provider manifest字段，生产全局值/公平排队/取消策略没有规范；`attempt_timeout < aggregate_timeout` 暗示可能多 attempt，却没有声明 MVP 是否自动重试、最大 attempt、可重试类别、backoff/jitter或每次 attempt如何占用 rate ledger。性能 fixture 的“全局4/Provider2”只描述基准，不等于生产合同。
- 影响：实现可在同一 logical refresh内调用 Provider一次或多次，导致不同耗时、限流、幂等和失败计数；大配置也可能先创建无界任务再靠 semaphore排队。
- 可操作修复：最简单的 v1合同是 `max_attempts=1`，并冻结全局 semaphore、Provider semaphore、bounded task queue、公平性、取消和部分结果；若允许重试，则把 attempt policy放进 manifest/query generation并与 AQ-R6-003的原子预算预留绑定。
- 验证标准：相同 fixture在所有实现上产生相同调用数；大配置的待处理 task数有界；queue/attempt/aggregate恰好边界、取消、崩溃和429/5xx序列得到唯一结果且不超10秒基准。

### AQ-R6-014 — Codex 版本 comparator 和 normalize 函数只有名字，没有算法

- severity：`medium`
- 确定性：高
- 证据等级：`E2 + E4`
- 定位：`docs/design-proposal.md:604-619,856,946-962`；`docs/provider-contract.md:184-201`
- 事实：合同登记 `codex-cli-v1/aq-codex-cli-v1` 与 `normalize_codex_version(...)`，却没有定义可接受 stdout regex、前缀/空白、pre-release/build metadata、比较顺序、无效/多行输出和规范字符串。本机实际 stdout 形状为 `codex-cli 0.142.5`。
- 影响：构建器、probe 和另一实现可能对同一 CLI 得到不同 schema bundle hash或 supported-range结论，导致错误加载/拒绝和 generation分叉。
- 可操作修复：冻结 exact ASCII grammar、抽取和 canonical output；定义 prerelease/build比较或明确全部拒绝；版本读取必须限制stdout bytes/lines并校验exit code。为 comparator发布golden向量。
- 验证标准：空白、前缀、CRLF、多行、pre-release、build、前导零、超长、非UTF-8、边界倒置和正常版本在两套实现上得到相同 normalize/compare/hash。

### AQ-R6-015 — `frozen=True` 不能让嵌套 dict 真正不可变

- severity：`medium`
- 确定性：高
- 证据等级：`E3 + E4`
- 定位：`docs/design-proposal.md:235-249,721-726,833-848`
- 事实：`CapabilitySnapshot.display_params` 与 `DiscoveredSubject.selector_candidate` 是可变 `dict`，同时正文宣称 DTO 使用 `frozen=True`。Pydantic 官方把 frozen称为 [faux-immutable](https://docs.pydantic.dev/latest/api/config/#pydantic.config.ConfigDict.frozen)：它阻止属性重新赋值，不会把嵌套 dict 变成不可变对象。
- 影响：Adapter可在边界校验后通过保留引用修改 discovery selector；集成消费者也可改 snapshot参数。验证时看到的值可能不是提交/渲染时的值，破坏原子批次和安全投影假设。
- 可操作修复：把这些字段改为 canonical tuple/不可变 mapping DTO，或在不可信边界深拷贝并重新构造只含不可变成员的 core-owned对象；不要把 `frozen=True` 当深冻结。
- 验证标准：恶意 FakeAdapter在 return后修改原 dict、并发 background mutation、consumer修改 display参数均不能改变core已验证对象；hash/序列化/提交值稳定。

## 6. 可直接修复的低严重度问题

### AQ-R6-016 — Python 3.11 的泛型别名示例无法执行

- severity：`low`
- 确定性：高
- 证据等级：`E1 + E4`
- 定位：`docs/design-proposal.md:280-287,1031-1035`
- 事实：项目基线是 Python 3.11+，正文写 `OperationResult[T] = OperationSuccess[T] | OperationError`。在 Python 3.11按原样执行得到 `NameError: name 'OperationResult' is not defined`。
- 影响：实现者照抄规范模型即失败，生成的 schema/type checker也没有统一入口。
- 可操作修复：Python 3.11使用 `OperationResult: TypeAlias = OperationSuccess[T] | OperationError`；若改用 PEP 695，则最低版本必须提高到 Python 3.12并写 `type OperationResult[T] = ...`。
- 验证标准：在声明的最低Python版本完成import、mypy/pyright和Pydantic schema生成；`OperationResult[int]`可解析 success/error正反例。

### AQ-R6-017 — “唯一保存期限源”仍在其他正文重复具体数值

- severity：`low`
- 确定性：高
- 证据等级：`E4`
- 定位：`docs/security-model.md:195-216,238-242`；`docs/design-proposal.md:351-355,1016-1023,1269-1272,1393-1395,1576`
- 事实：安全模型规定其他章节只能引用 RET ID，不得重写数值；设计正文仍重复 consent 24小时、action 15分钟与卡片幂等30天，并用这些副本作验收断言。action章节也自称唯一时间合同。
- 影响：当前数字恰好一致，但下一次只改一处就会得到不同清理/重放边界，违反文档自己要求的单一规范源。
- 可操作修复：设计正文只引用 `RET-CONSENT-*`、`ACTION_TTL`、`RET-IDEM-FEISHU-CARD`及安全模型中的静态不变量；测试从同一常量/schema生成，不复制值。
- 验证标准：静态检查除安全模型唯一表/唯一 action合同外不再出现这些保留期数值；修改规范源后所有golden测试从同一常量变化。

## 7. 已闭环、未列为问题与不适用项

以下检查没有形成新问题：

- Codex 多 bucket：现行正文已允许 absent/null/空或 1..16项，要求恰一项与顶层规范相等并丢弃其他动态 key；第5轮该项在当前正文中已闭环。
- DeepSeek 当前官方合同仍是 `GET /user/balance`、boolean `is_available`、CNY/USD和三个字符串金额字段；本轮新问题是本地数值长度/范围边界，不是官方字段漂移。
- LKG所有权、每 request key恰一 observation、当前 generation隔离、动态 map-key脱敏、OperationError与snapshot分离的主方向已闭环。
- Hermes/飞书/Web明确是可选阶段；3A/4未实现本身不算Standalone MVP缺陷。仍对其现行设计做了授权、同意、群聊、重放、Host/Origin/CORS/CSRF静态核对。
- SQLite明文额度数据库是当前明确的OS-uid/文件权限风险取向；文档没有承诺同uid插件隔离或全盘静态加密，因此本轮不把“未加密SQLite”重复列为缺陷。LocalKeyRing根秘密落盘缺失则是可实现性问题，已单列AQ-R6-002。
- 固定Provider host、TLS、禁环境代理、双重URL比较和无用户base URL已覆盖当前DeepSeek SSRF主路径；DNS/TLS对端被明确视为外部边界。本轮未发现需要单独成立的DNS rebinding问题。
- README关于“无代码、无依赖、无commit、Codex身份未决、仍需全新审计”的启动时状态真实。完成本报告后，后续修复轮应更新README以反映本轮17项结论；本审计按约束不修改README。

## 8. 覆盖矩阵

| 范围 | 结论 |
| --- | --- |
| 需求、边界、用户旅程 | Standalone/可选宿主边界清楚；Codex身份阻断见AQ-R6-001，plan路径见AQ-R6-011 |
| 身份/subject发现 | AQ-R6-001、AQ-R6-007；discovery handle/seed主合同已闭环 |
| Adapter接口/错误模型 | AQ-R6-005、AQ-R6-007、AQ-R6-015 |
| Codex/DeepSeek协议 | AQ-R6-001、AQ-R6-006、AQ-R6-009、AQ-R6-014；DeepSeek官方字段未漂移 |
| rate-limit多bucket/缓存/LKG | 多bucket已闭环；跨进程预算见AQ-R6-003 |
| 调度/超时/并发 | AQ-R6-003、AQ-R6-013 |
| 网络/SSRF/DNS | 当前GET固定出口可接受；未完成POST/代理分支见AQ-R6-010 |
| 认证/凭据租约 | lease字段主合同已闭环；根key与identity所有权见AQ-R6-002、AQ-R6-007 |
| 安装/供应链/签名/回滚 | AQ-R6-004、AQ-R6-008 |
| 存储/加密/回滚 | AQ-R6-002；SQLite同uid边界为明确风险取向 |
| 隐私/留存/日志 | 主分类与禁记字段完整；唯一期限重复见AQ-R6-017 |
| 可观测性/告警 | 多币种policy冲突见AQ-R6-012；episode主状态机已闭环 |
| 发布门禁/测试可执行性 | AQ-R6-004、AQ-R6-006、AQ-R6-008、AQ-R6-013、AQ-R6-016 |
| 跨文档/类型/枚举/状态机 | AQ-R6-005、AQ-R6-007、AQ-R6-011、AQ-R6-012、AQ-R6-014、AQ-R6-015、AQ-R6-016、AQ-R6-017 |
| README状态真实性 | 审计开始时真实；修复轮需加入本轮结论 |

## 9. 文件完整性与历史证据

本轮开始和报告写入前，四份现行源码 SHA-256 相同：

| 文件 | SHA-256 |
| --- | --- |
| `README.md` | `973a169371aac88df735888b03b04c3b190748295d2134303b281453310dabb9` |
| `docs/design-proposal.md` | `c582d51aa7ef2716414fed45411dfdffd3cfff0d93f67fac8f708393679f0c91` |
| `docs/provider-contract.md` | `0570a0d8177273299bb58113b50cc17710b65323b8f750b301968755aac76d02` |
| `docs/security-model.md` | `9a83d63becd19be165b90303d5780204f31804a0b1b80fc8d2d47812ea5703cb` |

第1～5轮历史 audit/resolution 均未修改。报告写入前的 SHA-256：

```text
a00a14c901881d84ba7648987a2cb7ceff92b41bd9f077a13605e38bad76abdd  round-01-audit.md
c4630344e20561d3677e6d393cf206f4bf6d438871444d28e9d7872dedd53935  round-01-resolution.md
c997a3853d0d47b9e44e1fbb0f8476ddbdf9006438855a3cf1cd246857b54c9a  round-02-audit.md
8b13adaec95df01fa7da78bbed6c305076597535f4e415f396840be4774c65df  round-02-resolution.md
4c0283dfe7827922b0be8001e8b0d381e247ac6f6fab3d8c95d9c95aba2cca32  round-03-audit.md
7ad08ed95a607d1a353c9c54d4bbd359798dd6145c2f6a3918204e3efae12581  round-03-resolution.md
ea0e5002fa17b6d3a8396c5ce8d11fa321e45ae2b1470ba33149a845b1a82897  round-04-audit.md
2b57e50bbfe68928a74a7d2d090614407909a5da1481c80db6710219cd2cf171  round-04-resolution.md
7339b048a03f98b91119d01fec86d6364af645043da42cbfc42617de48542c86  round-05-audit.md
0c3858ded76f622b3dc50ec87c9de0f931f97b6cdd93b0f0ed9de2f98c3d27a4  round-05-resolution.md
```

本轮唯一新增文件是 `docs/audits/round-06-audit.md`；没有修改README、三份现行正文、`.gitignore`或任何历史证据，没有执行git commit。

## 10. 最终计数与下一门禁

- 结论：`FAIL_WITH_17_ISSUES`
- 阻断：1
- 高：6
- 中：8
- 低：2
- 除 Codex 身份产品决策外的可修复问题：有，共16项

下一步必须先由用户处理AQ-R6-001的互斥产品选择；其余16项可由修复Agent直接修订。修订后仍需另一名全新的独立审计Agent从零全量复审，不能只复查本清单。
