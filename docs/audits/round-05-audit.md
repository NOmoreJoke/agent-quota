# 第 5 轮独立对抗性审计

> 审计结论：`FAIL_WITH_16_ISSUES`  
> 严重度：阻断 1 / 高 8 / 中 7 / 低 0  
> 审计日期：2026-07-18  
> 审计范围：`README.md`、`docs/design-proposal.md`（v1.0）、`docs/provider-contract.md`（v0.9）、`docs/security-model.md`（v0.8）  
> 审计方式：全新的独立 Agent 从零全量审查；候选清单冻结前未读取 `docs/audits/` 历史。本轮只新增本报告，不修改正文或旧记录。

## 结论摘要

本轮不能给出零问题结论。共发现 16 项高置信、可定位、可复现、可执行的问题：1 项是必须由用户选择的 Codex 产品基线，另外 15 项可以由修复 Agent 直接核验并修订。

Codex 身份阻塞被本 Agent 独立复现。当前本机 `codex-cli 0.142.5` 的 stable schema 和只读实测都证明：现行 allowlist 内的 `account/rateLimits/read` 不提供稳定账户身份；另一个只读方法 `account/read(refreshToken=false)` 存在，但 ChatGPT `email` 在官方 schema 中允许为 `null`。实测还发现一个与身份决策无关、可直接修复的新问题：当前本机 rate-limit 响应包含 2 个合法 bucket，而现行合同只接受唯一 `codex` bucket，所以当前 Codex 版本会在 probe 阶段被拒绝。

本报告不记录真实邮箱、计划、额度、重置时间、bucket 名称或任何账户值；本机实测只记录字段存在性、类型、基数和规范相等性。

## 必须由用户决定的阻塞项

### AQ-R5-001 — 阻断 — Codex 稳定身份要求与当前只读 RPC allowlist 仍然互斥

- 严重度：阻断。
- 定位：`docs/design-proposal.md:516-520`、`docs/design-proposal.md:630-634`、`docs/design-proposal.md:730-734`、`docs/design-proposal.md:1176-1178`、`docs/provider-contract.md:149-156`、`docs/provider-contract.md:181-206`、`docs/security-model.md:166-176`。
- 反例：用户把本地 Codex 从账户 A 切换到账户 B。Adapter 只允许握手和 `account/rateLimits/read`；响应包含额度窗口、计划和 bucket，但没有稳定账户/会话身份。core 无法证明 `cache_identity` 必须变化，旧缓存/LKG 可能跨账户复用。放行 `account/read` 也不能无条件成功，因为官方 schema 明确允许 ChatGPT `email=null`。
- 原因：合同要求零 binding official-cli 在正式 fetch 前生成 `verified_stable` identity，但现行发送端 allowlist 没有提供所需身份材料。本轮未找到另一个当前已允许且可验证的稳定字段。
- 建议：由用户选择一个且只选择一个产品基线：
  1. 允许只读 `account/read(refreshToken=false)`；只在内存中使用专用 LocalKeyRing purpose 对经严格验证的身份元组生成 keyed identity，`account=null`、类型不符或必要身份字段为空时 fail closed，原文永不持久化；同时明确邮箱是否足以代表实际 rate-limit 主体；或
  2. Codex 退出 MVP Supported/第二个真实 Adapter 退出条件，改用具有稳定身份契约的 Provider。
- 验收：覆盖同账户重启、A→B 切换、登出重登、`account=null`、`email=null` 和非目标账户类型；证明旧缓存/LKG 不可见，身份原文不进入 TOML、SQLite/WAL/SHM、日志、fixture、投影或审计；最终 schema bundle allowlist、发送端测试和三份正文完全一致。
- 协议证据：[OpenAI 官方 app-server Auth endpoints](https://github.com/openai/codex/blob/main/codex-rs/app-server/README.md#auth-endpoints)列出 `account/read` 与 `account/rateLimits/read`，并明确 ChatGPT email 可以为 null；本机 stable schema 与隐私安全只读调用独立复现相同事实。

## 可直接修复的问题

### AQ-R5-002 — 高 — 当前 Codex 的合法多 bucket 响应会被现行合同无条件拒绝

- 严重度：高。
- 定位：`docs/design-proposal.md:751-753`、`docs/design-proposal.md:769-771`、`docs/provider-contract.md:181-187`、`docs/provider-contract.md:299-301`、`docs/security-model.md:171`。
- 反例：本机 `codex-cli 0.142.5` 的 `account/rateLimits/read` 实测返回 `rateLimitsByLimitId` 对象，基数为 2；两个 map key 都与各自 snapshot 的 `limitId` 一致，其中恰好一个 snapshot 与 backward-compatible 顶层 `rateLimits` 规范相等。现行合同规定非空 map 只能有唯一 key `codex`，因此同一份当前官方响应会在 probe 阶段成为 `unverified_version`，Codex 无法进入 1B。
- 原因：官方 schema 把该字段定义为 `additionalProperties: RateLimitSnapshot` 的 multi-bucket map，没有唯一 key/唯一元素约束；正文把较早的单 bucket 观察冻结成了永久合法形状。
- 建议：保持 MVP 只消费顶层 backward-compatible `rateLimits`，但把 map 校验改为有界、脱敏、向前兼容的合同，例如限制总基数/深度/类型，要求恰好一个 bucket 与顶层规范相等并逐项验证 key 与 `limitId`，其余 bucket 丢弃且不得进入 ID/label/selector/日志；若产品要展示多 bucket，则另行版本化为用户确认的 subject，而不是静默扩展。
- 验收：当前本机的 2-bucket 结构能在不记录动态 key 的情况下通过 probe 并只映射顶层三项 capability；空/null、零匹配、多个匹配、key/limitId 不一致、超基数、错型和顶层不匹配均有唯一 fail-closed 结果；不得写入真实 bucket 名称。

### AQ-R5-003 — 高 — DiscoveryContext 和返回类型无法表达“发现尚未落盘的主体”

- 严重度：高。
- 定位：`docs/design-proposal.md:544-569`、`docs/design-proposal.md:576-619`、`docs/design-proposal.md:623-632`、`docs/design-proposal.md:638-643`、`docs/provider-contract.md:88-90`、`docs/provider-contract.md:162-166`。
- 反例：一个 principal 尚无任何 subject，用户执行 `subject discover`。`DiscoveryContext.selectors` 只能接收含正式 `SubjectId` 的 `AuthorizedSelector`，但待发现主体尚未生成 `aqs_` ID；传空 selectors 的含义也没有定义。即使 Adapter 发现了主体，`discover_subjects()` 只返回 `tuple[DiscoveredSubject]`，不能返回同批 `DiscoveredCapability` 或 `MissingCapability`；这些字段反而被重复塞进 `ProbeResult`。
- 原因：配置验证、协议 probe、主体 discovery 三个阶段没有各自唯一输入/输出。当前接口既要求 discovery 发生在用户确认和正式 ID 生成之前，又要求其 selector 已绑定正式 subject。
- 建议：定义独立 `DiscoveryRequest/DiscoverySeedSelector`，只引用 manifest profile/subject kind/schema 和受限候选字段，不引用正式 SubjectId；定义唯一 `DiscoveryResult(subjects, capabilities, missing)`，并从 `ProbeResult` 移除业务发现结果或明确其只做什么。
- 验收：从“principal 已配置、subject 为 0”开始，DeepSeek/Fake 能完成 offline 校验、显式 network discovery、同批 handle/capability/missing 校验、用户确认、core 生成正式 ID；未确认结果不落盘，跨批 handle、悬空 capability 和越 scope seed 全部拒绝。

### AQ-R5-004 — 高 — `CredentialLease` 在两份规范中的字段结构不一致

- 严重度：高。
- 定位：`docs/design-proposal.md:524-530`、`docs/design-proposal.md:630`、`docs/provider-contract.md:126-147`、`docs/provider-contract.md:162-166`。
- 反例：core 按设计方案构造 lease，字段为 `binding_id/principal_id/purpose/access_identity/secret/expires_at`；Provider SDK 按 Provider 契约实现时却期待 `source` 和 `transport_metadata`，并且没有 `purpose`。同一个 frozen FetchContext 在两份文档中因此产生不同 JSON Schema/Pydantic 模型；purpose 绑定无法验证，或 transport metadata 在实现间被丢失/错误序列化。
- 原因：第 4 轮把显式 context 加入设计时，没有建立真正唯一的 CredentialLease 规范源。
- 建议：只保留一个 canonical DTO，并明确 `purpose`、`source_kind`、有限 transport metadata 的字段名、类型、Secret 包装、repr/serialization 行为、到期与 principal/profile 绑定；其他文档只引用，不重复定义。
- 验收：core 与 Adapter SDK 对同一 schema 生成相同 canonical hash；缺 purpose、未知 transport key、普通字符串秘密、principal/profile 不匹配均在 Adapter 前拒绝；repr、异常、日志和通用 serializer 不含 secret/transport 值。

### AQ-R5-005 — 高 — NetworkPolicy 缺少 core endpoint builder 所需的机器契约

- 严重度：高。
- 定位：`docs/design-proposal.md:448-477`、`docs/design-proposal.md:539-542`、`docs/provider-contract.md:221-268`。
- 反例：`NetworkPolicyHandle` 携带 `endpoint_id`，但 `HttpNetworkPolicy` 只有平行的 `http_methods/path_templates/rpc_methods`，没有任何 `EndpointSpec` 定义 endpoint ID 与 method、path template、path 参数 schema、query key/type/cardinality 的原子组合。core 无法判断 `GET /user/balance` 是哪一个 endpoint，也无法执行第 266 行要求的有限 query 和逐字段 path 参数校验；若让 Adapter 私有代码补齐，又违反“只有 core 结构化 endpoint builder 构造 URL”。
- 原因：安全算法已经写到“规范化后双重比较”，但 manifest meta-schema没有提供算法的完整输入。
- 建议：增加判别式 `HttpEndpointSpec(endpoint_id, method, path_segments/template, path_param_schema, query_schema, auth_injection_policy, response_policy_id)`，由 profile 显式引用；LocalStdio 同样以 endpoint/RPC spec 原子绑定方法与 frame/deadline policy，禁止平行元组做笛卡尔积。
- 验收：通用 loader 不调用 Adapter 私有 URL 代码即可构造 DeepSeek endpoint；未知 endpoint、method/path 错配、重复/未知 query、分隔符注入和凭据解析前后目标变化均拒绝；`NetworkPolicyHandle.endpoint_id` 必须命中唯一 spec。

### AQ-R5-006 — 高 — “解包前验签”与普通 pip 安装路径没有可执行闭环

- 严重度：高。
- 定位：`docs/design-proposal.md:703-716`、`docs/design-proposal.md:846-860`、`docs/design-proposal.md:1301`。
- 反例：用户在全新虚拟环境直接安装 `agent-quota[deepseek,codex]`。正文要求“安装器在解包前”验证 detached attestation，但发行矩阵没有定义或发行任何 bootstrap installer，meta distribution 也不能在自己被 pip 安装之前拦截 pip 对 Provider wheel 的解包/安装。只在运行时 loader 验证时，未经信任的 Provider 文件已经进入环境；若它含导入副作用或构建钩子，`adapter_not_distributable` 来得太晚。
- 原因：文档混用了 pip 的安装器与尚未定义的 Agent Quota 安装器。pip 官方流程是解析依赖、构建 wheel、安装包，并没有本文 detached attestation 的自定义前置钩子。
- 建议：二选一并写成唯一流程：发行一个先被信任/固定 hash 的 bootstrap installer，先下载而不安装、验证整套 wheel/sidecar/trust bundle 后再调用 pip；或放弃“解包前”承诺，明确只提供加载前验证，并证明未验证 Provider 在加载前绝不会执行。sdist 路径也必须说明 build backend 的执行信任边界。
- 验收：篡改 Provider wheel/sidecar、缺 sidecar、依赖替换和恶意 import/build hook 测试证明未验证代码在拒绝前没有执行；三套干净环境使用文档给出的逐字命令可复现预期。参考 [pip install 官方阶段说明](https://pip.pypa.io/en/stable/cli/pip_install/#overview)。

### AQ-R5-007 — 高 — 发行签名与 trust bundle 仍缺少可互操作的密码学/格式规范

- 严重度：高。
- 定位：`docs/design-proposal.md:703-716`、`docs/provider-contract.md:189-195`、`docs/security-model.md:175`。
- 反例：发布器 A 用 Ed25519、RFC 8785 JSON、整数 Unix 秒签名；验证器 B 用 ECDSA、本文未定义的 `canonical()` 和 RFC 3339 字符串。二者都可声称遵守当前散文，却得到不同 payload/digest/signature。`normalized_content`、signature envelope、publisher key ID、根/子 key schema、阈值、撤销条目、有效期边界和 bundle 签名内容均没有唯一字节级合同。
- 原因：第 4 轮补上了“谁签名、签哪些语义”，但还没有冻结“准确签哪些字节、用什么算法和数据结构验证”。这不足以让两套独立实现离线互验，也不足以生成确定性攻击 fixture。
- 建议：定义版本化 `aq-release-attestation-v1`/trust-bundle JSON Schema 和字节级 canonicalization，冻结签名算法/参数、hash、key ID derivation、时间格式/边界、threshold 规则、撤销与 sequence 比较、sidecar 文件名/编码，以及各文件类型的 `normalized_content`。未知算法/字段/version 一律拒绝。
- 验收：两套独立实现对同一 wheel 生成相同 payload bytes/digest并互验；一位 bit、字段顺序、Unicode、时间边界、未知算法、阈值不足、撤销、bundle 回滚、跨包/版本/文件名重放均有 golden fixture。

### AQ-R5-008 — 高 — `not_authorized` 同时被定义成操作错误和 capability 快照

- 严重度：高。
- 定位：`docs/design-proposal.md:287-301`、`docs/design-proposal.md:1059`、`docs/provider-contract.md:210-219`、`docs/provider-contract.md:382-396`、`docs/security-model.md:114-124`、`docs/security-model.md:182`。
- 反例：请求包含 scope 外 capability。授权章节要求在缓存/凭据/Provider 前返回统一 `OperationError(not_authorized)`；状态矩阵却允许 `health=not_authorized/status_code=not_authorized/fresh` 快照，Provider 返回边界还说运行时缺失可用 not-authorized 快照。实现 A 会在本地保存一个可被 status 读取的快照，泄露主体存在；实现 B 返回操作错误。两者均能引用当前文档。
- 原因：本地 actor/scope 拒绝与上游“已授权请求中的某项能力未获 entitlement”被混成同一个枚举和表面。Adapter 理论上永远不应收到 scope 外 key。
- 建议：本地授权失败只允许 OperationError，零快照/零缓存/零 Provider；上游 capability 权限结果使用单独、语义明确的本地状态（例如 missing reason/not_entitled），并定义它是否可缓存及 TTL。移除或严格限制快照中的 `not_authorized`。
- 验收：P_A/P_B、S_A/S_B、伪造 view、空 scope 和跨主体完整矩阵只得到相同 OperationError，Provider/cache/ledger/计数均为 0；已授权请求中的上游 entitlement 缺失按另一个唯一状态处理且不泄露上游原文。

### AQ-R5-009 — 高 — Adapter 无法在不读取 core 缓存的前提下构造 stale/LKG 失败快照

- 严重度：高。
- 定位：`docs/design-proposal.md:287-301`、`docs/design-proposal.md:602-630`、`docs/design-proposal.md:636-643`、`docs/design-proposal.md:786`、`docs/provider-contract.md:368-396`。
- 反例：DeepSeek 请求网络超时，core 已有 LKG。合同要求本次每个 request key 恰好返回一条 `stale+network_error` 且携带类型匹配的旧值；但 `ProviderAdapter.fetch()` 只能返回 `CapabilitySnapshot`，FetchContext 没有 LKG，Adapter 又被禁止反查 registry/cache。若 Adapter返回 `expired+network_error`，core 是否允许在“Adapter 返回边界整批校验”前后注入 LKG没有定义；OperationErrorCode 也没有 transport `network_error`。
- 原因：Adapter 的上游观察结果与 core 最终持久化/展示的 CapabilitySnapshot 被当成同一个 DTO，导致 LKG 所有权和失败原子性没有唯一实现位置。
- 建议：定义 Adapter 返回的封闭 `FetchObservation/FetchFailure`，每个 request key 只含经白名单归一化的新值或本地失败类别，不含 LKG；core 在验证完整 key 集合后原子读取当前 generation LKG，唯一生成 fresh/stale/expired snapshots，再提交计数/缓存。明确整批 transport 失败与逐 capability 业务失败的边界。
- 验收：同一 timeout fixture 在有/无 LKG 时分别稳定得到 stale/expired；Adapter 对 cache/registry 的访问计数为 0；跨 generation LKG 不可见；半批错误、Adapter 越界和 core 崩溃均不产生部分提交。

### AQ-R5-010 — 中 — TTL 没有机器可读唯一值，Provider 状态可被永久标成 fresh

- 严重度：中。
- 定位：`docs/design-proposal.md:289-299`、`docs/design-proposal.md:369-390`、`docs/design-proposal.md:773-787`、`docs/design-proposal.md:813`。
- 反例：DeepSeek `wallet-availability=available` 或 Codex `rate-limit-status=available` 是一次上游观察。当前 `fresh` 规则允许“稳定非数值状态”的 `expires_at=None`，它们可永久保持 fresh；另一实现可在“2 至 3 分钟”范围任选 120、150 或 180 秒。`RefreshPolicy/CapabilitySpec` 都没有 snapshot TTL 字段，测试无法判定谁正确。
- 原因：刷新请求地板与缓存新鲜度 TTL 是不同合同；正文只给区间，没有把精确 TTL/允许覆盖范围放入 manifest，也没有区分永久结构状态和会变化的 Provider status。
- 建议：为 capability/profile 增加精确、有限范围的 `fresh_ttl_seconds`（或版本化 freshness policy），参与 query generation；只有明确登记的永久结构状态可用 `expires_at=None`，Provider 观察到的 available/reached/balance/window/counter 都必须到期。
- 验收：相同 manifest 在所有实现上产生相同 expires_at；DeepSeek availability 与 Codex reached 到期后变 stale/expired；not_applicable 等永久状态按唯一规则处理；TTL 变化生成新 query generation 并清旧 LKG。

### AQ-R5-011 — 中 — Codex schema bundle 示例的 RPC allowlist 没有按自己规定的顺序编码

- 严重度：中。
- 定位：`docs/design-proposal.md:718-734`。
- 反例：描述符示例为 `initialize, initialized, account/rateLimits/read`，下一段却要求按 UTF-8 字节排序。严格排序结果应以 `account/...` 开头。实现 A 照抄示例，实作 B 照散文排序，两者对同一 CLI 生成不同 `protocol_schema_hash`，从而产生不同 query generation。
- 原因：规范示例与 canonicalization 规则自相矛盾。
- 建议：把示例改为真实规范顺序，并明确 allowlist 是 set 后排序还是调用序列；用户决定 AQ-R5-001 后若加入 `account/read`，同样按最终规则重算。
- 验收：固定输入的 bundle bytes/hash golden case在两套实现上一致；打乱源集合顺序不改变 hash，增删任一 RPC 必须改变 hash。

### AQ-R5-012 — 中 — AccessContext 的操作授权枚举与 OperationName 不一致

- 严重度：中。
- 定位：`docs/design-proposal.md:254-282`、`docs/design-proposal.md:1040-1057`、`docs/provider-contract.md:141-147`、`docs/security-model.md:90-106`、`docs/security-model.md:121`。
- 反例：`OperationName` 包含 status/config_validate/configure/probe/discover/credential_resolve/fetch/refresh/migrate/delete/purge；`AccessContext.operation` 却是普通 `str`，注释只列 status/refresh/configure/purge。一次用户 refresh 内部执行 probe→credential_resolve→fetch 时，实现可以沿用 refresh 授权，也可以要求三个未定义的独立 actor 权限；delete/migrate/discover 同样没有唯一授权映射。
- 原因：面向 actor 的请求操作和 core 内部执行阶段没有分层，且没有复用同一个判别枚举。
- 建议：冻结 `RequestedOperation` 与内部 `ExecutionStage` 两个不同联合，给出唯一映射和禁止升级规则；AccessContext 只接收前者，CredentialSource/Adapter error 记录后者。任何未知字符串 fail closed。
- 验收：逐 operation 授权矩阵证明 status 不能触发 refresh/configure/delete/purge，refresh 只能进入允许的内部阶段，discover/migrate/delete 有明确权限；未知值在读取缓存前拒绝。

### AQ-R5-013 — 中 — 唯一保存期限表遗漏告警 episode 和 LLM consent 持久记录

- 严重度：中。
- 定位：`docs/design-proposal.md:335`、`docs/design-proposal.md:1033-1036`、`docs/design-proposal.md:1148-1157`、`docs/security-model.md:152-160`、`docs/security-model.md:194-213`。
- 反例：系统长期运行后，SQLite 中持续积累已 resolved 的 AlertEpisode/contributing_sources/notification delivery state，以及已过期或撤销的 ConsentContext generation/scope 记录。第 10.1 节自称唯一 retention 源，但没有这些记录的 `RET-*` 条目；实现可以永久保存，也可以立即删除并破坏重放/撤销证明。
- 原因：新增告警聚合与逐调用 consent 后，没有同步数据清单、起算点、到期动作和对象删除矩阵。
- 建议：在唯一表新增 alert/notification 与 consent/revocation 条目，明确 active 与 terminal 状态、起算时间、最短安全保护窗、对象 disable/delete/purge 行为和 key 依赖；其他章节只引用 ID。
- 验收：虚拟时钟覆盖 open/ack/resolved、投递崩溃、consent 到期/撤销/重建、对象删除和 key 轮换；到期后无 Confidential 残留，同时旧会话不能因记录提前删除而恢复权限或重复投递。

### AQ-R5-014 — 中 — Codex local-stdio 的单 attempt 总 deadline 同时被定义为 6 秒和 8 秒

- 严重度：中。
- 定位：`docs/design-proposal.md:462-475`、`docs/design-proposal.md:1294-1297`、`docs/provider-contract.md:270-272`、`docs/security-model.md:171`。
- 反例：Codex 握手耗时接近 3 秒，业务请求再耗时 4 秒。Provider/Security 合同的 8 秒进程总时长允许成功；性能门禁却规定 HTTP/local-stdio 单 attempt 外层总 deadline 为 6 秒，必须取消。相同运行在两个规范下分别成功和超时。
- 原因：local-stdio 的 handshake/request/process deadline 与通用性能 attempt deadline没有形成单一嵌套不变量。
- 建议：为每种 transport 冻结 `queue <= attempt <= aggregate` 的准确层级，说明握手是否每次计入、request 6 秒是独立上限还是剩余预算；所有章节引用同一 policy 字段。
- 验收：虚拟单调时钟覆盖 3+4 秒、恰好边界、排队、TERM→KILL→reap；Provider contract、性能基准和最终 OperationError 对每个 case 给出相同结果，且总墙钟不超过全局 deadline。

### AQ-R5-015 — 中 — 非公开接口强制 breakage protocol 没有进入 AdapterManifest meta-schema

- 严重度：中。
- 定位：`docs/design-proposal.md:496-514`、`docs/design-proposal.md:653-680`、`docs/provider-contract.md:303-366`。
- 反例：一个 `source_type=undocumented` Adapter 提供完整 capability/semantic/network 合同，却不提供结构路径白名单、map-key 规则、schema fingerprint contract 或 breakage policy。当前 `AdapterManifest` 模型没有字段可让通用 loader拒绝它；只能靠 Adapter 私有代码或人工约定补齐，与“每个 undocumented Adapter 必须实现统一 breakage_protocol”冲突。
- 原因：第 8.1/Provider 第 9 节的规范输入仍停留在散文，没有成为 manifest 引用闭包的一部分。
- 建议：增加版本化 `StructureContract/BreakagePolicy`，冻结静态 path ID、必需/可选类型、map-key 归一化、基数/深度限制、fingerprint recipe、失败类别和恢复 policy 引用；undocumented profile 必须恰好引用一个。
- 验收：通用 loader 在 offline、零 Adapter 私有代码条件下拒绝缺失/悬空/未使用/重复结构合同；动态邮箱/ID key、结构漂移、未知路径和相同结构语义漂移 fixture分别命中唯一结果。

### AQ-R5-016 — 中 — InstallationRegistry/LocalKeyRing 的 MAC 与封装格式不足以独立实现和验证

- 严重度：中。
- 定位：`docs/design-proposal.md:831-844`、`docs/provider-contract.md:158-160`、`docs/security-model.md:38`、`docs/security-model.md:172`、`docs/security-model.md:229`。
- 反例：实现 A 用 JSON+HMAC-SHA-256 保护 registry，并用 AES-GCM 封装 keyring；实现 B 用 msgpack+裸 MAC 和另一个 nonce/associated-data 方案。两者都满足“记录 MAC”“由 binding key 封装”，但无法互相读取，也对截断、nonce 重用、generation 回滚和 registry/keyring 交换有不同结果。
- 原因：文档冻结了生命周期和用途域，却没有冻结 registry canonical bytes、MAC 算法、AEAD/KDF、nonce/salt 长度与生成、associated data、文件 version、原子写入和 anti-rollback 字段的确切格式。
- 建议：定义版本化 registry/keyring envelope schema和字节级 canonicalization，冻结 HMAC/AEAD/HKDF 参数、nonce/salt、AAD 对 installation/purpose/generation 的绑定、sequence/fence 与原子替换流程；未知 version/算法 fail closed。
- 验收：两套独立实现可互读；单 bit 篡改、截断、nonce 重用 fixture、registry/keyring 交换、旧 generation 回滚、写入崩溃和 binding key 错误全部稳定 `local_keyring_unavailable`，且无 secret 出现在诊断。

## 当前协议与静态验证证据

1. 本机版本：`codex-cli 0.142.5`，可执行文件由当前 PATH 解析为用户安装的 Codex CLI；本轮未读取或复制 `$CODEX_HOME/auth.json`。
2. 本机执行 `codex app-server generate-json-schema --out <empty-temporary-directory>`，未启用 `--experimental`；生成目录共 267 个文件，规范 v2 聚合根 `codex_app_server_protocol.v2.schemas.json` 的 SHA-256 为 `45109764447555f7847b8c3348a6ecbcfdf16dcc78fe2c34ee7dbcd90e78fa10`。
3. 本机 stable schema证明：`GetAccountRateLimitsResponse.required=["rateLimits"]`；`rateLimitsByLimitId` 是允许任意数量 `RateLimitSnapshot` 的 map 或 null；`RateLimitWindow` 只要求 `usedPercent`；ChatGPT account 的 email 是 `string|null`。
4. 隐私安全只读调用依次执行 initialize/initialized、`account/read(refreshToken=false)`、`account/rateLimits/read`：三个请求成功；当前 account 结构含 email/planType/type，但报告不记录值；rate-limit 顶层与窗口结构合法；bucket map 基数为 2、恰好一个 bucket 与顶层 canonical snapshot 相等、两个 key 都与各自内部 limit ID 一致。未调用登录、登出、配置写入或 consume。
5. [OpenAI 官方 app-server 文档](https://github.com/openai/codex/blob/main/codex-rs/app-server/README.md)确认 stable schema按 CLI 版本生成、初始化握手、`account/read`、`account/rateLimits/read`、email nullable 和 backward-compatible rate-limit 表面。[DeepSeek 官方余额文档](https://api-docs.deepseek.com/api/get-user-balance/)仍确认 `GET /user/balance`、boolean `is_available`、CNY/USD 与三个字符串金额字段；本轮未发现当前 DeepSeek 主源字段/出口漂移。
6. 静态扫描未发现 `TODO/TBD/FIXME/XXX` 或未替换模板。正常的开发前门禁、阶段性未勾选验收项不算占位符；唯一明确必须由用户作产品选择的是 AQ-R5-001。
7. 审计开始时仓库没有 commit，现行四份正文均为未跟踪工作区文件；本轮以工作区内容为权威。候选清单冻结后才读取第 4 轮 audit/resolution，以排除把旧清单当作本轮输入；本轮未修改任何旧记录。

## 覆盖结论

- 需求范围、阶段边界、模型联合、状态/错误表面：发现 AQ-R5-008、AQ-R5-009、AQ-R5-010。
- manifest meta-schema、显式调用 context、凭据与 identity：发现 AQ-R5-001、AQ-R5-003、AQ-R5-004、AQ-R5-005、AQ-R5-011、AQ-R5-012、AQ-R5-015。
- Provider 映射与当前协议：发现 AQ-R5-001、AQ-R5-002；DeepSeek 当前官方表面未发现新增问题。
- cache、limit、idempotency、告警与 retention：发现 AQ-R5-009、AQ-R5-010、AQ-R5-013；已登记四渠道 at-most-once 和 ACTION_TTL 未发现新的高置信矛盾。
- migration、destructive diff、purge、InstallationRegistry/LocalKeyRing：发现 AQ-R5-016；第 4 轮新增 planner digest、nonce、lease/fence 与 roll-forward 主状态机未发现另一个高置信问题。
- assurance、attestation、wheel/sdist 与干净安装：发现 AQ-R5-006、AQ-R5-007。
- 渠道/Hermes/Web：发现 consent retention 的 AQ-R5-013；群聊零披露、确定性命令、Web Host/Origin/CORS/CSRF 当前未发现新的高置信问题。
- 性能与阶段验收：发现 AQ-R5-014；固定 4-request 基准的其余边界可执行。
- 示例、链接、占位符与跨文档一致性：发现 AQ-R5-004、AQ-R5-011、AQ-R5-012；未发现遗留 TODO/TBD 模板或正文引用的本地文件缺失。

## 收敛判定

`FAIL_WITH_16_ISSUES`

计数：阻断 1 / 高 8 / 中 7 / 低 0。

Codex 身份问题已独立复现：**是**。当前多 bucket 不兼容问题也已通过本机只读协议调用独立复现，且与身份产品决策分开列示。

用户决定 AQ-R5-001，并由一个全新的修复 Agent 逐项核验和处置全部 16 项后，仍必须由另一个全新的独立审计 Agent 从干净视角重新全量审查；不得只复查本清单。
