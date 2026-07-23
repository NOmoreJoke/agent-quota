# Agent Quota 第 10 轮独立对抗性设计审计

- 审计日期：2026-07-18（Asia/Shanghai）
- 审计者：独立 Agent `/root/audit_round_10`
- 唯一结论：`FAIL_WITH_12_ISSUES`
- 严重度：Blocker 1 / High 9 / Medium 2
- 分类：用户决策 1 / 不改变身份基线即可修订 11 / 本轮驳回 0
- 阶段 0A：不通过

## 1. 结论

现行 v1.5 仍不能进入阶段 0A。Codex allowlist 继续没有可产生 `verified_stable` subject evidence 的批准来源，这是唯一需要用户选择产品基线的 blocker；本审计没有加入 `account/read`，也没有把 Codex 移出 MVP。

除此之外，本轮确认 11 项可直接修订的合同缺陷。它们不是“身份问题的同义重报”：即使用户今天解决 Codex identity source，当前机器合同仍会因为全局数组排序规则拒绝自身，lease typed AST 仍有 `ms/ns` 类型错误，online doctor/discover 仍没有合法 rate-ledger 拒绝结果，official-cli 路径仍不能从冻结 DTO 构造所需输入，Codex bundle 仍不含 wire validator 明确要求的 `InitializeResponse`，LocalKey payload 仍允许多 active key，migration cascade 仍可生成二元环，安装回滚状态与 endpoint-group 预算也仍未闭包。

## 2. 审计方法、独立性与隐私边界

### 2.1 独立性顺序

本轮先完整读取 `audit-verify-explain-grade-5/SKILL.md`，随后从零审阅以下现行源：

- `README.md`
- `docs/design-proposal.md`
- `docs/provider-contract.md`
- `docs/security-model.md`
- `docs/contracts/contract-registry-v1.json`
- 四份 contract artifact、五份 Draft 2020-12 schema
- `docs/contracts/fixtures/retention-lint-malicious-v1.json`

在读取任何历史 audit/resolution 前，候选清单冻结为 16 项，冻结文本 SHA-256 为：

```text
69ea6eea25a8090455eb7d3ded3a83218e648677b98d622da7cef9e8822ec2ce
```

之后才读取 `round-01..09` audit/resolution 做去重。历史对照后剔除 4 项证据不足或对 MVP 没有独立影响的候选，保留 12 项。本轮没有在历史阶段继续发现新候选。

### 2.2 证据等级

- `E1`：现行本地文件、JSON pointer、行号、raw/canonical hash。
- `E2`：本轮直接运行的解析、schema、AST、加密或官方本地 schema 生成命令。
- `E3`：只用现行规范字段构造的确定性反例或状态机推导。
- `E4`：历史 audit/resolution；只用于去重和核对既往处置声明。

### 2.3 隐私与调用边界

本轮没有读取环境变量、系统凭据、Codex/Hermes 登录材料、真实邮箱、账户、额度、计划、重置时间、动态 key、Token、Cookie 或 Provider 响应。没有执行真实账户 RPC、Provider HTTP 调用、`account/read` 或 `account/rateLimits/read`。

唯一 Codex 动态核对是本机 `codex-cli 0.142.5` 的公开、离线命令 `codex app-server generate-json-schema --out <temporary-directory>`；返回码为 0，临时目录自动清理。该命令只生成公开协议 schema，不启动 app-server，也不读取账户状态。

## 3. 问题清单

### AQ-R10-001 — Codex allowlist 仍无 stable subject evidence

- Severity：`Blocker`
- 确定性：高
- 证据：`E1/E4`
- 分类：`用户决策`
- 定位：`README.md:38,58`；`docs/design-proposal.md:1100,1146,1445,1457`；`docs/provider-contract.md:144,146,162,191,202,206`；`docs/security-model.md:170,177-178,360,385`
- 事实：正式 `FetchContext` 要求 `verified_stable`。zero-binding official-cli 只能从批准的 identity source contract 获得稳定账户/会话 evidence。现行 Codex allowlist 仍只有 `initialize`、`initialized`、`account/rateLimits/read`，而规范明确 Codex 没有可产生 `verified_stable` 的 source/domain，并禁止实现自行加入 `account/read` 或从 rate-limit payload、进程、principal 猜身份。
- 影响：Codex 必须继续 `incompatible`，不能正式 fetch、不能持久化 cache/LKG，也不能成为 Supported；0A 与 1B 的 Codex 身份门禁无法关闭。
- 修复：只能由用户在两个互斥基线中选择：批准额外只读稳定身份来源并冻结 source contract；或保持最小 allowlist、降级 Codex 并替换第二个 MVP Adapter。本审计不代选。
- 验证：选择前 Codex Supported/fetch fixture 持续 fail closed；选择后用账户切换、重登、重启、多 principal 同/异账户证明 cache 隔离与 cohort 合并。
- 历史：与 `AQ-R9-001` 相同的明确未决 blocker，不是实现回归。

### AQ-R10-002 — 全局数组排序规则会拒绝当前机器合同自身

- Severity：`High`
- 确定性：高
- 证据：`E1/E2/E4`
- 分类：`当前缺陷`
- 定位：`docs/contracts/contract-registry-v1.json:39-45,47-60`；`docs/contracts/operation-contract-v1.json:6-7,43-183,254-287`；`docs/contracts/lease-policy-v1.json:56-137`
- 事实：registry 要求“每个 registry-like array”在字段没有声明其他 exact order 时按 UTF-8 bytes 升序，并把该规则应用于 `all`。本轮脚本直接得到：`operation.modes` 首个错位是 `none` 对期望 `http`；`operation.paths` 是 `status-none-v1` 对期望 `alert-ack-none-v1`；`safe_param_schemas` 是 `none` 对期望 `conflict-code`；`lease.policies` 是 `queue-ticket-v1` 对期望 `purge-writer-v1`。这些字段都没有声明另一种 exact order。
- 影响：严格 validator 必须拒绝当前已登记 digest 的 artifact；宽松 validator 若把“registry-like”解释成自选子集则会接受。同一文件因此没有唯一 verdict，正文所称“所有语义闭包通过”不可成立。
- 修复：为每个数组字段登记机器可判定的 `order_kind=sequence|utf8_key` 与 key pointer；把当前 registry-like arrays 重排后重算 artifact/registry hash。算法步骤数组应显式标成 sequence，不能依靠实现猜测。
- 验证：枚举全部 schema array pointer；每个 pointer 恰命中一个排序策略。对每个 keyed array 做相邻交换负向向量，两个独立 validator verdict 必须一致；现行 artifact 必须全部通过。
- 历史：`AQ-R9-002` 的处置声明称“排序逐项重算匹配”，但现行反例仍存在；这是该 `FIXED` 声明的可复现残缺。

### AQ-R10-003 — lease typed AST 把 `int64_ns` 传给只接受 `int64_ms` 的 `min`

- Severity：`High`
- 确定性：高
- 证据：`E1/E2/E4`
- 分类：`当前缺陷`
- 定位：`docs/contracts/lease-policy-v1.json:20-27,38-41,43-54,138-154`；`docs/contracts/schemas/lease-policy-v1.schema.json:30-40`；`docs/contracts/contract-registry-v1.json:41`
- 事实：唯一 `min` operator 声明 `input_type=int64_ms[]`、`output_type=int64_ms`。`min-parent-and-queue-timeout` 与 `min-parent-and-transport-v1` 却把两个 `int64_ns` operand 传入该 operator，并声明结果为 `int64_ns`。registry 同时要求 typed AST inference 成功、type mismatch 必须 reject。
- 影响：严格按 operator registry 推导时，两份 deadline formula 以及所有引用它们的 reservation policy 都不能加载；若实现按 formula 的结果类型覆盖 operator 类型，另一实现按 operator 定义执行，deadline 与持久 expiry 会分叉。
- 修复：增加独立 `min_int64_ns` operator（或把 `min` 变成带明确同型泛型参数的结构化 operator），使输入/输出推导唯一；conversion rule 的公式也应使用同一 AST，而不是自由字符串约束。
- 验证：独立 typed-AST interpreters 对 11 个 formula 完成全树推导；任一 `ms/ns` 混用、错误 result type、错误 conversion input 都在执行前拒绝。覆盖 parent/queue/transport 三种先后关系和 int64 边界。
- 历史：`AQ-R9-004` 正是要求 typed AST；第 9 轮处置增加 AST 时引入了当前单位类型反例。

### AQ-R10-004 — online doctor/discover 的 rate-ledger 拒绝没有合法结果行

- Severity：`High`
- 确定性：高
- 证据：`E1/E2/E4`
- 分类：`当前缺陷`
- 定位：`docs/contracts/operation-contract-v1.json:71-129,185-228`；`docs/design-proposal.md:336-343,435-458,1096-1098,1525-1538`
- 事实：`doctor/http`、`doctor/official_cli_zero_binding`、`discover/http`、`discover/official_cli_zero_binding` 都必须执行 `rate_ledger_reserve`。脚本对四条 path 查询 exact `error_rows`，在 `(doctor|discover, rate_ledger_reserve)` 下均得到空集；`rate_ledger_unavailable` 和 `storage_unavailable` 在该 stage 只登记给 `refresh`。已有 floor/hour blocker 的 `deferred` 也只有 RefreshBatch 的 per-request 代数，doctor/discover 没有对应成功或错误分支。
- 影响：正常预算阻塞、SQLite 不可用或 writer lease 失败时，online doctor/discover 既不能返回表内 OperationError，也不能合法继续 Provider I/O；按正文处理会触发 `CoreInvariantFatal`，按实现自选错误码又违反唯一机器矩阵。
- 修复：为 doctor/discover 的 reserve stage 增加 exact、可生成的 budget-deferred/storage/rate-ledger error rows及 safe params，或定义共享的 pre-attempt result union并登记到 artifact；不得借用 refresh-only DTO。
- 验证：对四条路径分别覆盖 floor、hour、blocked_until、DB unavailable、lease/fence conflict；全部在首个 Provider byte 前产生唯一表内 envelope，Provider/credential/cache 写入计数符合副作用断言。
- 历史：第 6 轮已要求 rate-ledger failure 可严格序列化；第 8/9 轮补了 reserve 顺序与机器矩阵，但没有补全这四条结果边。

### AQ-R10-005 — official-cli 的 discovery/identity-and-fetch 路径无法从冻结 DTO 构造

- Severity：`High`
- 确定性：高
- 证据：`E1/E2/E3`
- 分类：`当前缺陷`
- 定位：`docs/contracts/operation-contract-v1.json:119-129,149-166,289-296`；`docs/design-proposal.md:341-343,925-1025,1078-1085,1094,1100,1102-1104`；`docs/provider-contract.md:156-162,197-206`
- 事实：official-cli discovery path 先构造 `DiscoveryRequest`、执行 `discovery(provider_io)`，最后才 `identity_derive`；但 `DiscoveryResult` 没有 identity evidence 字段，而 Provider contract 又要求缺 stable identity 时正式 discovery 不执行。official-cli refresh path 虽增加 `probe_context_build`，`ProbeContext` 只有 subject selector，没有 `CapabilityRequest` 或 capability ID；`operation_context_build` 在 probe 之后。与此同时 `ProbeResult.reusable_fetch_result` 被要求在同一 response 中“完整覆盖 FetchContext request keys”。Adapter 在发出 I/O 时拿不到那组完整 key，不能证明返回集恰好匹配用户本次 capability 子集。
- 影响：解决 `AQ-R10-001` 后仍不能实现这两条正式路径。实现只能在缺输入时猜全 capability 集、丢弃/补写 observation、进行第二次 I/O，或把未验证 identity 提前塞入请求，分别破坏 key 完整性、一次 attempt 计账或 stable identity 门禁。
- 修复：冻结一个同时携带 exact `CapabilityRequest` 与 bootstrap identity authorization 的 `IdentityAndFetchContext`；同一 response DTO 同时返回 evidence 与绑定该 request digest 的 observation。discovery 若要 bootstrap identity，也必须使用有 evidence 的返回联合，并在接受 discovery payload前完成 identity 验证；否则必须先走独立 probe path。
- 验证：同一 subject 请求 capability 子集/全集、漏项/额外项、账户切换、evidence invalid、response replay；证明一个 reservation、一个 response、一个 request digest，且 identity 验证失败时 discovery/config/cache 零写入。
- 历史：与 `AQ-R8-002` 的“业务 RPC 必须先 reserve”不同；当前是第 9 轮 `identity_and_fetch` 修订后的 DTO 数据流闭包反例。

### AQ-R10-006 — Codex schema bundle 排除了 wire validator 明确要求的 InitializeResponse

- Severity：`High`
- 确定性：高
- 证据：`E1/E2`
- 分类：`当前缺陷`
- 定位：`docs/design-proposal.md:1411,1417-1445,1459`；`docs/provider-contract.md:183,195`
- 事实：bundle 文件集合固定为且仅为 `codex_app_server_protocol.v2.schemas.json`，但 wire 状态机要求 initialize result 通过官方 `InitializeResponse`。本机对规范命令执行成功；在生成结果中，唯一被纳入的 v2 root 的 canonical JSON 不含字符串/definition `InitializeResponse`，而所需 schema 作为 `v1/InitializeResponse.json` 单独生成，未进入 roots 或 aggregate hash。
- 影响：只持有已验证 bundle 的运行时无法执行规范要求的官方 initialize response validation。若实现额外读取未哈希文件，协议验证会脱离 `protocol_schema_hash`；若不读取，则“通过官方 InitializeResponse”无法实现。
- 修复：把所有实际 wire validator 引用的生成 schema 做显式引用闭包并按相对路径排序纳入 bundle descriptor；至少包含当前单独生成的 InitializeResponse，或把其规范化内容封入专用 wire schema。每个引用文件 path/hash 都必须影响 protocol schema hash。
- 验证：在干净环境删除任一必需 schema、替换 InitializeResponse 一位、只改未使用 schema、重排输出文件；前两者必须失败/改 hash，未使用文件按冻结闭包规则给唯一 verdict。运行时禁止打开 descriptor roots 外文件。
- 历史：第 3-7 轮曾修复“bundle 选取和 wire schema 未冻结”；本项不是重报选取缺失，而是现行“仅一个 root”与现行 wire validator 要求直接不相容。

### AQ-R10-007 — LocalKeyRing payload 没有 key-entry 状态与 key ID 的语义闭包

- Severity：`High`
- 确定性：高
- 证据：`E1/E3/E4`
- 分类：`当前缺陷`
- 定位：`docs/contracts/local-key-purpose-registry-v1.json:8-16,17-57,79-111`；`docs/contracts/schemas/local-key-purpose-registry-v1.schema.json:29-38`；`docs/provider-contract.md:150-152`；`docs/design-proposal.md:1650,1655,1676-1678`
- 事实：`keyEntry` schema 独立允许任一 purpose 使用 `state=active|verify_only`；`key_entries` 只限制数量，没有机器规则要求 `(purpose,generation)` 唯一、每个 purpose 恰一个 active、`verify_only` 仅用于 `verify_only_allowed=true` 的 purpose。全局 canonical-item uniqueness 也不能拒绝同一 purpose 的 generation 1 与 2 同时 active。Provider contract 还称 16-byte `public_salt` 与 `aqk_` domain-separated key-id recipe 是跨实现合同，但 artifact 没有该 recipe，也没有校验 `key_id/public_salt/key_material` 的关系。
- 影响：通过 schema 的 payload 可以让 `active_key_for_consumer()` 返回两个候选，或让 replace-generation purpose 保留 verify-only key；不同实现会选择不同 key，造成 cache identity、cohort、ledger digest、action 验签和 query generation 分叉。攻击者还可替换非秘密 key ID 而无法按唯一 recipe重算。
- 修复：在 artifact 中增加 exact key-entry semantic validator：key主键、排序、每purpose active cardinality、state transition、purpose→allowed state；冻结 `public_salt` 生成/用途和 `aqk_` key-id domain recipe并要求加载时重算。补完整 golden payload/envelope，不只测 AES primitive。
- 验证：两个 active、零 active、重复 generation、禁止 purpose 的 verify-only、key ID/salt bit flip、目的交换、rotation crash vectors 全部唯一拒绝；两实现对同一 payload选出相同 active/verify set。
- 历史：`AQ-R9-005/006` 关闭了 consumer lookup与AEAD wire，但没有关闭 key-entry payload 语义；`round-06-resolution` 声称已冻结 public_salt/key ID recipe，现行机器 artifact 未承载该声明。

### AQ-R10-008 — retention detector 存在可构造的持久化与期限绕过

- Severity：`Medium`
- 确定性：高
- 证据：`E1/E3/E4`
- 分类：`当前缺陷`
- 定位：`docs/contracts/retention-lint-v1.json:77-108`；`docs/security-model.md:231-245,259`
- 事实：persistent medium 词典只含 `database table/journal file/sqlite table/temporary file/temp file` 及三个中文词，不含现行正文自己使用的 `SQLite`、`database`、`registry`、`WAL` 等表面。因此新增 `SQLite 保存 refresh token` 不会形成 `PersistentDeclaration`，也不会触发缺 `persist:` tag。duration 规则另有冲突：`bounded-non-retention-runtime` 的 forbidden terms 只有 `keep/retention/保存期限/保留`，没有 `expire/ttl/到期/清理`；同一 leaf 的 `expire 30 days timeout` 同时满足 retention context 与允许的 runtime context，而 artifact没有冻结优先级。
- 影响：lint 可在四份现行文档和固定 fixture 上通过，却漏掉新的秘密持久化 surface/TTL；另一实现选择“retention context优先”又会给相反 verdict。唯一 retention owner 门禁因此不能阻止未登记保存期限进入规范。
- 修复：使用结构化声明或封闭 AST directive代替自然语言介质猜测；若保留 lexer，补全规范 token classes、词形/边界、rule priority和“任一 retention signal禁止被 runtime allowlist覆盖”的组合规则。fixture增加上述两种最小反例及 Unicode/中英混合变体。
- 验证：规则驱动扫描先接受当前四正文；把 `SQLite 保存 refresh token` 或 `expire 30 days timeout` 注入任一非owner leaf必须拒绝；合法 transport timeout 保持接受。两实现对所有组合产生相同 verdict。
- 历史：`AQ-R9-008` 的处置加入了 grammar，但当前是该 grammar 本身的有限词典与规则优先级反例。

### AQ-R10-009 — cascade 与 child-before-parent-delete 规则可为同一删除生成二元环

- Severity：`High`
- 确定性：高
- 证据：`E1/E3/E4`
- 分类：`当前缺陷`
- 定位：`docs/design-proposal.md:1588-1640`；`docs/security-model.md:261`
- 事实：action 只有 create/update/disable/delete/remove/replace/purge，没有独立的无副作用 cascade marker；`cascade_parent_action_id` 还要求是 earlier action。图规则同时规定“child delete → parent delete”和“显式 cascade parent → cascade child”。对最小计划“删除 parent P，并 cascade 删除 child C”，第一条生成 `C.delete → P.delete`，第二条生成 `P.delete → C.delete`，形成二元环；Kahn 必须拒绝。若不生成第二条，则违反“至少且恰按”规则及 earlier cascade parent投影。
- 影响：正常的 parent/child cascade delete 永远无法产生 plan digest；实现若私自忽略一类 edge，会在 action ID、确认摘要、journal恢复顺序上分叉，并可能先删仍被引用的 parent。
- 修复：把 cascade 表达为非排序的 membership/reason 关系，实际执行依赖只保留 child-before-parent-delete；或增加独立 plan-root marker且明确它不参与对象 mutation。`cascade_parent_action_id` 不得要求与删除执行方向相反的 earlier mutation action。
- 验证：parent→child、三层树、多兄弟、remove-reference后delete、混合disable/delete生成无环golden DAG；每个拓扑前缀满足引用不变量，输入遍历顺序不改变 plan digest。
- 历史：`AQ-R9-012` 要求补全 semantic dependencies；第 9 轮处置同时加入两个方向相反的 edge规则，当前是该修订的直接反例。

### AQ-R10-010 — InstallationRegistry exact payload 无法保存规范要求的 trust/attestation 回滚状态

- Severity：`High`
- 确定性：高
- 证据：`E1/E3`
- 分类：`当前缺陷`
- 定位：`docs/design-proposal.md:1348,1352-1374,1399-1405,1654,1657-1658`
- 事实：发行合同要求为每个 `(distribution_name,publisher binding)` 原子保存 `attestation_sequence` floor；bundle更新要求保存链末完整 bundle、digest和sequence；install plan成功要求保存 plan sequence与plan digest。可 exact payload 列表只含单个 `trust_bundle_sequence_floor`、单个 `install_plan_sequence_floor`，没有当前 bundle digest/完整bundle、没有按distribution/publisher分区的attestation floor，也没有已接受plan digest。
- 影响：重启后无法区分“同sequence不同bundle”、无法判断某发行物attestation sequence回滚，也无法证明 repair 重验的是同一plan。实现若把这些字段塞进未知 `root records` 会违反 exact/extra-forbid payload并产生第二wire合同。
- 修复：扩展 InstallationRegistry exact schema：保存 current trust bundle canonical bytes或受MAC保护的path+digest、bundle sequence/digest、按canonical distribution/publisher key的attestation floor map、plan sequence/digest；定义排序、上限、更新事务和purge/restore行为。
- 验证：bundle同sequence换内容、旧attestation配新wheel、不同distribution独立sequence、同plan sequence换digest、registry/keyring/DB交叉回滚和kill-point vectors均fail closed；正常升级原子推进所有floor。
- 历史：此前各轮分别冻结了attestation/bundle/plan，但没有把这些状态与第 9 轮新 exact InstallationRegistry payload做双向字段闭包。

### AQ-R10-011 — EndpointBudgetGroup 没有唯一的 umbrella floor/hour policy

- Severity：`High`
- 确定性：高
- 证据：`E1/E3/E4`
- 分类：`当前缺陷`
- 定位：`docs/design-proposal.md:526-530,548-559,782-824,1098,1525-1536`；`docs/provider-contract.md:160,189,379`
- 事实：`RefreshPolicy`（floor/hour）属于 profile；`EndpointBudgetGroup` 只有 group ID、transport和endpoint IDs，没有 policy ID或floor/hour值，也没有约束同group所有profile的 RefreshPolicy相等。group umbrella digest/row必须跨endpoint/profile检查floor/hour，但规范没有定义使用请求profile、group最严格值、最宽松值或逐endpoint值。group floor/hour digest的exact key recipe也没有给出。
- 影响：两个都符合类型定义的manifest可把不同policy profile映射到同一group；实现A按当前profile允许第二次bootstrap，实现B按group最大floor拒绝，复制profile或切endpoint可能再次扩容。`AQ-R9-009` 所需的真正umbrella仍没有唯一数值语义。
- 修复：让 EndpointBudgetGroup直接引用唯一 versioned budget policy（floor、hour、blocked-until scope和digest recipe），并要求所有binding只使用该group policy；profile只引用group或静态证明其policy相等，不能复制第二份数值。
- 验证：同group多endpoint/多profile、不同group、verified→unknown bootstrap、并发与hour边界golden vectors；任意policy不一致在manifest加载、Provider/credential前拒绝。
- 历史：`AQ-R9-009` 修复了同一reservation上的umbrella索引，但未定义umbrella自身取哪组policy值；这是该闭环的剩余字段问题。

### AQ-R10-012 — registry repoPath schema 接受 `..` 逃逸与路径别名

- Severity：`Medium`
- 确定性：高
- 证据：`E1/E2`
- 分类：`当前缺陷`
- 定位：`docs/contracts/schemas/contract-registry-v1.schema.json:23-30`；`docs/contracts/contract-registry-v1.json:27-38`
- 事实：`repoPath` 只用 regex `^docs/contracts/[a-z0-9_./-]+\.json$`。本轮直接测试确认它接受 `docs/contracts/../../outside.json` 与 `docs/contracts/schemas/../lease-policy-v1.json`。registry没有额外的canonical path/no-dot-segment semantic validator。
- 影响：一个结构合法的registry可把artifact/schema binding指向合同目录外文件，或让同一文件通过不同字符串路径绕过path uniqueness。若后续发行签名只按registry声明闭包取文件，验证者会对“哪个文件属于机器合同”产生分叉。
- 修复：schema只接受规范相对路径 grammar，逐segment禁止空、`.`、`..`，禁止重复slash；加载时从固定repo root用no-follow句柄解析并要求重编码字符串逐字节相等。artifact/schema目录可用更窄的两个pattern。
- 验证：dot segment、重复slash、absolute、symlink、case variant、percent encoding、Unicode lookalike全部拒绝；每个合法path resolve后仍位于固定合同root且只有一个canonical spelling。
- 历史：早期 URL dot-segment 问题已修，但 contract registry path 是第 9 轮新增表面，本项为新范围内的确定性反例。

## 4. 已验证通过或本轮不另报

- 所有 JSON 均可由严格 JSON parser解析；五份 schema 在 Draft 2020-12、AJV `strict=false` 下编译，五份现行 document均通过结构 schema。AJV `strict=true` 对 operation schema 的 `type:["boolean","string"]` 给出 strict-style警告，这不是 Draft 2020-12 invalid，本轮不报。
- registry 登记的四份 artifact、五份 schema与fixture raw/canonical digest均重算匹配；缺陷位于语义闭包，不在摘要算术。
- AES-256-GCM primitive golden vector用本机 `cryptography` 重算匹配：key 32 bytes、nonce 12 bytes、AAD 25 bytes、plaintext 2 bytes、ciphertext+tag 18 bytes，decrypt回原文。本轮不重报AEAD算法或byte encoding。
- Pandoc `3.9.0.2`、API `[1,23,1,1]` 与 `commonmark+pipe_tables` 可用；现行 parser/extension不再重现 `AQ-R9-007`。
- journal `cleanup_pending` 已覆盖complete前claim清理窗口；本轮不重报 `AQ-R9-013`。
- 仓库没有应用代码、数据库、构建脚本或runtime，因此不能运行unit/integration/e2e、真实migration、installer或Provider合约测试。这不等于这些测试通过。

## 5. 当前源、合同与历史完整性哈希

### 5.1 当前正文 raw SHA-256

```text
24c68962bee4d483cd80f1e5ddc705a5bfc91b335ad045f7b1dea1da75d62827  README.md
25fded7020915066efaa576c9e1c85fe02912eb4029ab66c63b115922dced952  docs/design-proposal.md
7202c360aedf0cfbce35e0a9289368c32c5a8f0bf0fc2e2e5f94dbbbaa8443a8  docs/provider-contract.md
ca1ef73889bf87526b350a27802df034fbb46dffd523779c084ded9b0876110e  docs/security-model.md
```

### 5.2 contract raw / canonical SHA-256

| 文档 | raw SHA-256 | domain-separated canonical SHA-256 |
| --- | --- | --- |
| `contract-registry-v1.json` | `67d2b26e9e542fb28157d5d2e906dec00ed87d3ce6c7bf2005a95e824c447b8d` | `834d9592d96d51ab4f3d73d7d6b6367159e6454e4a2ae0202cd6c494c7e22451` |
| `lease-policy-v1.json` | `89a5a16ab706fad92393db77f544c8ac684e4298e21cca6e3c7e144176a5a742` | `8e00518663df33a32cce601b447ec375f5bd2f34b136b819a91f58cdc32adaff` |
| `local-key-purpose-registry-v1.json` | `d2bc244c379d7504e8108b23db12bf7e07d48b6ff27398fe538b9c3358fb179e` | `28bffb5f00e48faf5d571a5f41055a1130752785c28febf000310614a319db15` |
| `operation-contract-v1.json` | `d02e27cd60cee7f33d13223d824f0c3d90af70bb5d872a288cc7318e5ee1cd88` | `d59a0bde52c6dec7fb4a3da9dfe07449373d4c5fa7dc30e1a095034adceb2444` |
| `retention-lint-v1.json` | `831cf4880caf8e2008411e8cb5e94e69e81c8d7d4ba40d25b3e686c1e9b81fbc` | `ed4f77b8a57e719a73ab1616c250a80b7bfd93b0dc170e0d1b45b7ddea0c9108` |
| `contract-registry-v1.schema.json` | `41db10c6c5ab01d3e75079048bdf69c4a74ba16bc693b2cf874d4e503b7ab5b1` | `5f79a09fdb7c68737893f861249623062b8b32e9e17e5f6356e53628ea723185` |
| `lease-policy-v1.schema.json` | `ba7c7a0d0cf2c21c2249f06e608201ada59c08fcf9b10867ce57799b1f0d1e22` | `abe90c4a8f53677653229513de4c1168264d14e9fe6ca7d705419bc2241dfa48` |
| `local-key-purpose-registry-v1.schema.json` | `f56703c7776096a8c756cd0a460f6c8d4148fbdaa873ea598d3876cbf4c47ff7` | `9bbb04b3e37bdded8df71b66dc3b9ec45524799677d350f530dbfffdc043e516` |
| `operation-contract-v1.schema.json` | `46ea0f4d6c961df7cb02b2ea941ce6ec3358e0ce6389d8c9b77cbe6e1cd63229` | `6e3c520fcfd98dbd0e15637621f7562ca7654a88990219198e077fc40b4b8852` |
| `retention-lint-v1.schema.json` | `db48722ee3880a7d0f89461cf17b53200917af026ddb781970abdc94a8f327ae` | `a87c0cbb2baefc1d8f9b0c5e23303445f25c1badad90a62210f6f9795153132d` |
| `retention-lint-malicious-v1.json` | `4f7bf217e5455b39176b085652b396d4504599a7ff023350111084a52cee9a71` | `de1c33c972f8582b90989cb66653d8f7aec086101af6758c75dae3462be67b59` |

registry canonical hash不是registry内部自登记值；本轮按正文公开recipe独立重算并与 `docs/design-proposal.md:12` 的当前锚比较。结构摘要匹配不覆盖本报告的语义反例。

### 5.3 历史完整性

第 9 轮审计记录的 round-01..08 hash 与本轮重算逐项相等。round-09在此前没有外部/commit锚，本轮记录其当前值。完整当前值如下：

```text
a00a14c901881d84ba7648987a2cb7ceff92b41bd9f077a13605e38bad76abdd  docs/audits/round-01-audit.md
c997a3853d0d47b9e44e1fbb0f8476ddbdf9006438855a3cf1cd246857b54c9a  docs/audits/round-02-audit.md
4c0283dfe7827922b0be8001e8b0d381e247ac6f6fab3d8c95d9c95aba2cca32  docs/audits/round-03-audit.md
ea0e5002fa17b6d3a8396c5ce8d11fa321e45ae2b1470ba33149a845b1a82897  docs/audits/round-04-audit.md
7339b048a03f98b91119d01fec86d6364af645043da42cbfc42617de48542c86  docs/audits/round-05-audit.md
0924b992e71170ef4944980e37c7fe85fdf1a56a09a489ab77b9d987de62cd32  docs/audits/round-06-audit.md
91af1b28dd94c9372eeeb0410e0a8a77b20df3c293a64f4d33d76aba601482c9  docs/audits/round-07-audit.md
9ca8cdb4046e6b5bfcfd73b32f3385af5cfc52dc89289492389b82742da4dde2  docs/audits/round-08-audit.md
25634da86bbb2305081d9d7062faf5337bd88a6ae1021191f19a374c5a2c26fd  docs/audits/round-09-audit.md
c4630344e20561d3677e6d393cf206f4bf6d438871444d28e9d7872dedd53935  docs/audits/round-01-resolution.md
8b13adaec95df01fa7da78bbed6c305076597535f4e415f396840be4774c65df  docs/audits/round-02-resolution.md
7ad08ed95a607d1a353c9c54d4bbd359798dd6145c2f6a3918204e3efae12581  docs/audits/round-03-resolution.md
2b57e50bbfe68928a74a7d2d090614407909a5da1481c80db6710219cd2cf171  docs/audits/round-04-resolution.md
0c3858ded76f622b3dc50ec87c9de0f931f97b6cdd93b0f0ed9de2f98c3d27a4  docs/audits/round-05-resolution.md
97048a24cab36d824726227278d68f71e74d60650abf3e1488438da8ed448609  docs/audits/round-06-resolution.md
9c9593995ac82d1a10475b32db790ea5b40ccd8be8a6be9bd963a0487637175b  docs/audits/round-07-resolution.md
be178d129e98b1330b494acd5945ddab11cbb5916ecc0906ee50864f03b0b193  docs/audits/round-08-resolution.md
9450a20d9fb0ab3d70493e5571c9ec866808cdb6537562c810d48151ebfc9831  docs/audits/round-09-resolution.md
```

仓库当前为 `No commits yet on main`，所以没有可记录的 checkout commit hash。`git status --short --branch` 在本报告写入前显示全部现行文件为 untracked；没有历史 commit可作为更强完整性锚。本轮未改写 round-01..09，未stage、commit或push。

## 6. 可复核命令与关键输出

```text
nl -ba README.md
nl -ba docs/design-proposal.md
nl -ba docs/provider-contract.md
nl -ba docs/security-model.md
nl -ba docs/contracts/*.json
nl -ba docs/contracts/schemas/*.schema.json
nl -ba docs/contracts/fixtures/retention-lint-malicious-v1.json
jq -e . docs/contracts/*.json docs/contracts/schemas/*.schema.json docs/contracts/fixtures/*.json
npx -y ajv-cli@5 compile -s <schema> --spec=draft2020 --strict=false
npx -y ajv-cli@5 validate -s <schema> -d <artifact> --spec=draft2020 --strict=false
pandoc --version
pandoc -f commonmark+pipe_tables -t json docs/security-model.md
shasum -a 256 README.md docs/*.md docs/contracts/*.json docs/contracts/schemas/*.schema.json docs/contracts/fixtures/*.json
shasum -a 256 docs/audits/round-0[1-9]-audit.md docs/audits/round-0[1-9]-resolution.md
/Users/kyle/.npm-global/bin/codex --version
/Users/kyle/.npm-global/bin/codex app-server generate-json-schema --out <temporary-directory>
git status --short --branch
```

本轮只读Python核对的关键输出：

```text
operation.modes sorted=False first_mismatch=('none','http')
operation.paths sorted=False first_mismatch=('status-none-v1','alert-ack-none-v1')
operation.safe_param_schemas sorted=False first_mismatch=('none','conflict-code')
lease.policies sorted=False first_mismatch=('queue-ticket-v1','purge-writer-v1')
min-parent-and-queue-timeout: min input=int64_ms[]; args=int64_ns,int64_ns; result=int64_ns
min-parent-and-transport-v1: min input=int64_ms[]; args=int64_ns,int64_ns; result=int64_ns
rate-ledger-errors doctor/http=[]
rate-ledger-errors doctor/official_cli_zero_binding=[]
rate-ledger-errors discover/http=[]
rate-ledger-errors discover/official_cli_zero_binding=[]
repoPath('docs/contracts/../../outside.json')=accepted-by-pattern
repoPath('docs/contracts/schemas/../lease-policy-v1.json')=accepted-by-pattern
codex-generate-status=0
initialize-in-bundled-root=False
initialize-generated-separately=True
```

这些命令没有读取账户或秘密；Python只读取公开规范并输出hash/闭包统计，临时目录由标准库自动清理。

## 7. 用户决策、可直接修订项与最终门禁

- 唯一用户决策：`AQ-R10-001`。
- 不改变Codex身份基线即可直接修订：`AQ-R10-002..012`，共 11 项。
- 本轮没有建议通过加入 `account/read`、读取真实账户或移除Codex来“顺带解决”其他问题。

最终结论：

`FAIL_WITH_12_ISSUES`

在用户处理 `AQ-R10-001`、修订 `AQ-R10-002..012`、重算受影响合同摘要并由新的独立 Agent全量复审前：不得宣告零问题，不得通过阶段 0A，不得开始把 Codex作为 Supported MVP Adapter执行正式fetch实现。
