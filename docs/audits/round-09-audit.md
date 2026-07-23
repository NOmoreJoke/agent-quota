# Agent Quota 第 9 轮独立对抗性设计审计

- 审计日期：2026-07-18（Asia/Shanghai）
- 审计者：独立 Agent `/root/audit_round_9`
- 唯一结论：`FAIL_WITH_13_ISSUES`
- 严重度：Blocker 1 / High 9 / Medium 3
- 分类：当前缺陷 12 / 用户决策 1 / 本轮驳回 0
- 阶段 0A：不通过

## 1. 结论

当前规范仍未达到零问题放行条件。Codex allowlist 仍没有正式 fetch 所需的 stable subject evidence，继续构成必须由用户选择产品基线的 blocker；本报告没有加入 `account/read`，也没有把 Codex 移出 MVP。

除该 blocker 外，本轮确认 12 项可直接修订的实现合同缺陷。最集中的问题是：新增加的四份 JSON “机器权威源”只能证明内容可被 JSON 解析和哈希，仍不能仅凭自身生成严格 validator；operation、lease、LocalKey 与 retention 的关键语义没有闭包。另有四个可构造的状态机反例：verified 与 conservative budget 可被身份重建穿透、RefreshBatch 无法表达无 LKG 的 expired failure、migration create 依赖图不完整、journal 在 `complete` 后清 claim 的 kill point 无恢复路径。

## 2. 方法、证据与隐私边界

### 2.1 独立性顺序

先完整读取 `audit-verify-explain-grade-5/SKILL.md`，再从零逐行审阅以下现行源：

- `README.md`
- `docs/design-proposal.md`
- `docs/provider-contract.md`
- `docs/security-model.md`
- `docs/contracts/*.json`
- `docs/contracts/fixtures/*.json`

候选问题冻结为 13 项后，才读取 `round-01..08` audit/resolution 做历史去重与完整性核对。历史没有用来生成候选。

### 2.2 证据等级

- `E1`：现行本地文件、JSON pointer、行号、哈希或命令输出。
- `E2`：本轮直接运行的标准解析器/AST 工具结果。
- `E3`：由现行规范构造的确定性反例或状态机推导。
- `E4`：历史 audit/resolution；只用于判断重复、处置声明和完整性。

### 2.3 隐私

本轮没有读取环境变量、系统凭据、Codex/Hermes 登录材料、真实邮箱、账户、额度、计划、重置时间、动态 key、Token、Cookie 或 Provider 响应。没有执行真实账户 RPC、Provider HTTP 调用、`account/read` 或 `account/rateLimits/read`。所有反例均由公开规范字段和虚构状态构造。

## 3. 问题清单

### AQ-R9-001 — Codex allowlist 仍无 stable subject evidence

- Severity：`Blocker`
- 确定性：高
- 证据：`E1/E4`
- 分类：`用户决策`
- 定位：`README.md:38,58`；`docs/design-proposal.md:1070,1114,1137,1413,1425,2083,2187`；`docs/provider-contract.md:144,146,162,191,202,206`；`docs/security-model.md:170,177-178,360,385`
- 事实：正式 FetchContext 要求 `verified_stable`；zero-binding official-cli 必须由批准的 source contract 提供稳定账户/会话 evidence。现行 Codex RPC allowlist 只有 `initialize`、`initialized`、`account/rateLimits/read`，而现行规范明确 `identity_source_contracts/provider_identity_domains` 中没有可为 Codex 产生 `verified_stable` 的条目，并禁止实现自行加入 `account/read` 或从 rate-limit payload、进程、principal 猜身份。
- 影响：Codex 必须继续 `incompatible`，不能正式 fetch、不能持久化缓存/LKG、不能成为 Supported；0A 与阶段 1B 的 Codex 身份门禁无法关闭。
- 修复：只能由用户在两个互斥基线中选择：批准额外的只读稳定身份来源并冻结 source contract，或保持最小 allowlist、降级 Codex并替换第二个 MVP Adapter。本审计不代选。
- 验证：在选择完成前，Codex Supported/fetch fixture 必须持续 fail closed；选择后用账户切换、重登、重启、多 principal 同/异账户证明 cache 隔离与 cohort 合并。
- 历史：与 `AQ-R8-001` 相同的未决产品 blocker；不是实现回归。

### AQ-R9-002 — 四份 JSON 权威合同不是自描述的严格 schema

- Severity：`High`
- 确定性：高
- 证据：`E1/E3`
- 分类：`当前缺陷`
- 定位：`docs/design-proposal.md:12`；`docs/contracts/operation-contract-v1.json#/`；`docs/contracts/local-key-purpose-registry-v1.json#/`；`docs/contracts/lease-policy-v1.json#/`；`docs/contracts/retention-lint-v1.json#/`
- 事实：设计要求 raw bounds 后拒绝 unknown field、错型、float、重复 key，并称 JSON 是唯一机器权威源。但四份 artifact 都只有自定义字符串字段 `schema`，均没有 `$schema`、`$id`、`type`、`properties`、`required`、`additionalProperties` 或 `$defs`，也没有引用一个被同一摘要绑定的 meta-schema。`jq -e` 只能证明它们是合法 JSON，不能证明字段/类型/额外字段合法。向任一对象加入 `"future_trust_root":{}` 仍是合法 JSON，而 artifact 自身无法给出 accept/reject。
- 影响：实现只能在代码或另一份未登记 schema 中自选允许字段，形成第二权威源。新增字段、版本、引用、数值或信任根无法由现行 artifact 单独 fail closed；“正文投影从机器源生成”的前提不成立。
- 修复：为每个 artifact 增加被 contract digest 封闭的 exact JSON Schema/meta-schema（或把 schema 本身作为 envelope 的哈希绑定成员），冻结 raw byte/AST bounds、字段集、类型、枚举、格式、数组排序、唯一性和 `additionalProperties=false`。自定义 `schema` discriminator 不能替代 meta-schema。
- 验证：对每个对象/嵌套对象逐字段做 delete/add/rename/wrong-type/bool-as-int/float/duplicate/unknown-version vectors；两套独立 validator 必须给出相同 verdict 和 canonical bytes。
- 历史：第 8 轮新增四份 artifact 后首次进行其自身 schema 闭包检查；不是旧 manifest meta-schema 问题的简单重报。

### AQ-R9-003 — operation artifact 的 predicate、safe enum 与 step 语义未闭包

- Severity：`High`
- 确定性：高
- 证据：`E1/E3`
- 分类：`当前缺陷`
- 定位：`docs/contracts/operation-contract-v1.json#/predicate_ids`、`#/paths/0/steps/3`、`#/paths/10/steps/7`、`#/safe_param_schemas`、`#/closure_rules`；`docs/design-proposal.md:330-353,405-430`
- 事实：静态脚本确认 path ID、`(operation,mode)`、error 主键、引用、未使用项和“每个 provider_io 恰有一个更早 matching reserve”均闭合。但 artifact 只登记 predicate 名 `consent-required-for-status-projection`，没有 predicate 的输入、表达式或真假分支；八个非空 safe-param schema 只给 `name/kind=enum`，没有任何允许值集合。正文生成投影还给 official-cli reserve 加上 `conservative`，给 `operation_context_build` 加上 `reuse_observation`，而 JSON step 没有这两个字段。artifact 中搜索 `conservative|reuse_observation|allowed_values|enum_values|predicate_definition` 为零命中。
- 影响：生成器不能仅从机器源决定何时需要 consent、哪个 enum 值可安全输出、identity bootstrap 使用什么 cohort、是否必须复用同一次 response。恶意上游字符串可被不同实现当作合法 `EnumParam`；另一些实现会发起第二次 I/O。
- 修复：增加结构化 predicate definitions（输入字段、布尔表达式、缺值行为）、每个 safe enum 的 exact values，并把 `cohort_source`、`reuse_observation` 等影响 I/O/预算的 step 属性写入 artifact。closure 必须拒绝未定义/未使用值。
- 验证：从 artifact 生成 validator、Markdown trace 和全笛卡尔 vectors；反向解析投影必须逐格相等。任意 predicate/safe enum/step attribute 缺失或新增均使加载失败并改变摘要。
- 历史：`AQ-R8-007` 的 JSON 化处置只完成了主键和引用闭包，未完成语义闭包；本项是对 `FIXED` 声明的现行反例。

### AQ-R9-004 — lease policy 的 formula ID 没有机器定义

- Severity：`Medium`
- 确定性：高
- 证据：`E1/E3`
- 分类：`当前缺陷`
- 定位：`docs/contracts/lease-policy-v1.json#/renew_rule`、`#/takeover_rule`、`#/deadline_rule`、`#/policies/*/expiry_formula_id`、`#/policies/*/parent_deadline_formula_id`、`#/closure_rules`；`docs/design-proposal.md:1491,1784`
- 事实：policy 数值唯一、`duration<=max_lifetime` 和 `renew_before<duration` 均可验证；登记摘要也匹配。但三个 `expiry_formula_id` 和四个 `parent_deadline_formula_id` 只是未注册字符串，artifact 没有 formula registry、操作数、单位、运算顺序或 overflow 规则。特别是 `min-parent-and-transport-plus-2000ms-crash-grace` 不能从 ID 判断是 `min(parent,transport)+grace` 还是 `min(parent,transport+grace)`，也没有定义如何由 monotonic 剩余量约束 DB-UTC persisted expiry。`renew_rule/takeover_rule/deadline_rule` 仍是英文自然语言。
- 影响：两个实现可在不同 DB 时刻续租、接管或删除 reservation/temp claim；较早接管会破坏活 owner，较晚接管会造成死锁。现行 virtual-clock gate没有唯一 oracle。
- 修复：把公式变成封闭 AST/typed operands，例如 clock domain、`min/max/checked_add`、duration source、grace placement、边界和 overflow verdict；formula ID 必须引用唯一对象，未使用/悬空/未知 formula 拒绝。
- 验证：两实现对 renew 前后、`now==expiry`、parent/transport先后到期、DB clock backward、monotonic rollback、overflow、owner kill 生成完全相同的时间和状态转移。
- 历史：`AQ-R8-009` 处置补了数值与 formula 名，但没有补 formula 的机器含义。

### AQ-R9-005 — LocalKey consumer 与 verify-only 查找规则未闭包

- Severity：`High`
- 确定性：高
- 证据：`E1/E3`
- 分类：`当前缺陷`
- 定位：`docs/contracts/local-key-purpose-registry-v1.json#/purposes`、`#/purposes/*/consumer`、`#/purposes/*/rotation`、`#/closure_rules/consumer_may_use_only_named_purpose`；`docs/design-proposal.md:1076-1112,1481,1493,1614,1641-1645`
- 事实：八个 purpose 及 HKDF salt/info 已登记，hash匹配。可是 `consumer` 是不可引用的自然语言说明，没有 `consumer_id -> purpose` 机器表；正文公式使用 `access_identity_key/cache_identity_key/cohort_key/local_generation_key` 等变量，但除 `cache-identity-v1` 与 `rate-ledger-v1` 的散文提示外，没有把每个变量精确绑定到 purpose ID。`verify_only` 也没有规定新请求如何枚举 active/verify-only generations。rate cohort 与 ledger digest各自轮换时，查旧 blocker需要对两类 key generation 做有界、确定的组合查找，现行 artifact只给一个单词 `verify_only`。
- 影响：实现可误用同一 derived key、轮换后只查 active generation而看不到旧 ledger/idempotency/action，造成刷新预算扩容或旧动作失去重放保护；另一个实现可能无界枚举旧 generation。
- 修复：登记封闭 `consumer_id/purpose_id/new-value-policy/verification-lookup-policy`；为每个 persistent surface定义 active+verify generation 的有界搜索、组合顺序、去重和退休条件。正文公式必须引用 consumer ID，不使用自由变量名建立隐式映射。
- 验证：跨两种 purpose 同时/交错轮换的 golden vectors证明旧 ledger仍阻塞、旧 action/幂等仍可验证但不能签发新值、搜索有上限且结果与生成顺序无关。
- 历史：`AQ-R8-006` 的 purpose 缺项已修；本项是新增 registry 的 consumer/rotation 闭包仍不足。

### AQ-R9-006 — LocalKeyRing exact JSON wire 丢失 AEAD 与 bytes 编码

- Severity：`High`
- 确定性：高
- 证据：`E1/E3/E4`
- 分类：`当前缺陷`
- 定位：`docs/design-proposal.md:1616-1624`；`docs/security-model.md:269`
- 事实：`local-keyring-v1.json` 被声明为 JCS JSON，含 `kdf/aead/nonce/ciphertext`；明文 JCS 又含“32 bytes”的 key material。现行源没有给 `kdf`/`aead` 字段的 exact wire literal，没有写 AES-256-GCM，且没有规定 nonce、ciphertext+tag、key material 在 JSON 中使用 base64url、hex还是整数数组。JSON 不能直接承载 raw bytes。正文只明确 registry MAC tag和 `public_salt` 使用无 padding base64url，不能据此推断其他字段。
- 影响：两套自称合规的实现无法互读；同一 envelope没有唯一 canonical bytes、AAD/ciphertext表示或长度检查，篡改/截断测试也没有唯一输入。错误选择甚至会重复编码或遗漏 GCM tag。
- 修复：冻结 exact algorithm literals（含 KDF hash、AES key size、AEAD/tag长度）、每个 byte field 的唯一无 padding编码及 decode-before-length-check顺序，并给出完整 envelope/payload JSON Schema与 golden bytes。
- 验证：固定 binding key/generation/sequence/payload 由两实现产生相同 nonce、AAD、ciphertext、tag、JCS bytes；逐字符、padding、大小写、短/长/非法 alphabet vectors均唯一拒绝。
- 历史：`AQ-R5-016` 的处置记录曾声称已冻结 AES-256-GCM 与 exact bytes；现行 v1.4 已无 `AES` 字样或 byte encoding，属于该闭环的回归/丢失。

### AQ-R9-007 — retention locator 指定的 CommonMark parser不能产生 Table AST

- Severity：`Medium`
- 确定性：高
- 证据：`E1/E2`
- 分类：`当前缺陷`
- 定位：`docs/contracts/retention-lint-v1.json#/parser`、`#/locations/retention_table_ttl_cells/table_ordinal`、`#/inventory/table_ordinal`；`docs/security-model.md:205-245`
- 事实：artifact 固定 `parser="CommonMark-0.30"`，同时用 Table/column ordinal定位保存期限表和 inventory。实测 `pandoc -f commonmark -t json docs/security-model.md` 的 Table 节点数为 0；`pandoc -f commonmark_x` 才得到 6 个 Table。CommonMark core不定义 pipe-table扩展，所以声明 parser 下两个 locator不可达。heading ordinal本身在扩展 reader下能定位到 H2第10项/H3第1项/H4第1项，但这不能修复 parser冲突。
- 影响：严格按 artifact 的 lint 无法找到任何 owner table，当前四正文不能得到 accept；若实现私自开启 GFM/Pandoc扩展，又违反唯一机器配置并造成 AST差异。
- 修复：冻结一个包含 table扩展的具体 reader、版本与 extension set，并冻结其 AST node model；或把 owner registry移出 Markdown table，使用 CommonMark core可定位的结构。
- 验证：在干净环境解析当前四正文，两个 locator均恰好命中一个目标；关闭/更换任一 extension必须 fail closed而不是静默改 AST。
- 历史：`AQ-R8-010` 移除了 slug 与内联恶意 fixture，但新 Table locator没有与 parser能力一起验证。

### AQ-R9-008 — retention artifact 没有 duration/persistence detector grammar

- Severity：`Medium`
- 确定性：高
- 证据：`E1/E3`
- 分类：`当前缺陷`
- 定位：`docs/contracts/retention-lint-v1.json#/scan`、`#/verdicts`、`#/locations`；`docs/contracts/fixtures/retention-lint-malicious-v1.json#/cases`；`docs/security-model.md:241-245`
- 事实：artifact只给 Unicode normalization、case fold、扫描 node种类和 fixture ID；没有 duration token grammar、中文/英文单位词典、scientific/word-number识别规则、上下文条件，也没有“新 persistent surface”的语法/检测器。当前正文在合法 transport/lease/冷却等上下文存在大量时间数值，所以不能简单拒绝 owner外所有 duration。两个实现可让所有 fixture都按其 `expected` 硬编码，却对新的等价写法给出相反结果。
- 影响：`duration_outside_exact_location` 与 `new_persistent_surface_without_persist_tag` 不是可执行规则；lint既可能漏掉复制的 retention TTL，也可能误报合法 deadline。fixture hash和 ID闭包通过，不能证明行为闭包。
- 修复：在 artifact中登记确定 lexer/parser或规范 AST matcher，包含 duration形态、单位、上下文、相邻节点拼接、持久介质/动词识别和 fail-closed边界；fixture只作为这些规则的 vectors。
- 验证：当前四正文先 accept；所有现有 fixture和等价变体 reject；对合法 transport deadline、注释、链接、code/table/HTML、Unicode拆分与新持久声明给出固定 verdict。
- 历史：仍是 `AQ-R8-010` 处置的未完成行为闭包，不是 fixture文件本身缺失。

### AQ-R9-009 — unknown conservative bootstrap 可绕过既有 verified budget

- Severity：`High`
- 确定性：高
- 证据：`E1/E3`
- 分类：`当前缺陷`
- 定位：`docs/design-proposal.md:1068,1103-1112,1483-1484,1495-1506`；`docs/provider-contract.md:140-144,160,366,372-373,379`；`docs/security-model.md:177,184-186`
- 事实：已知 stable identity 的请求“直接使用 verified cohort”，不在 deployment-conservative bucket留下 debit。新 zero-binding principal/进程在 identity未知时只检查 conservative bucket，发送后才把同一行附加 verified index。构造反例：账户 A 刚完成 verified fetch并占 verified floor；复制/重建一个尚无 identity的 zero-binding principal，conservative bucket中没有 A 的那次 debit，因此第二次业务 RPC立即被允许；response解析出A后才发现 verified bucket已有 blocker，但 Provider attempt已经发生。
- 影响：复制 principal、丢失本地 identity缓存或 bootstrap可在每次重建时多获得一次调用，违反“复制 principal/binding/process不扩容”和 request floor/hour上限。post-response rebind只能避免第三次，无法撤回第二次。
- 修复：unknown bootstrap必须受 endpoint budget group 的真正 umbrella budget约束：例如所有 verified attempt同时占同 group conservative blocker，或 unknown reserve在发送前原子检查该 group内 conservative+全部 verified activity的并集。归并仍须一行一次attempt，不能双计业务调用。
- 验证：先由 verified A调用，再立即用新 principal/binding/process对同一A bootstrap；第二次必须在首个 outbound byte前 deferred。再覆盖不同账户、并发bootstrap、floor/hour边界、rebind crash和 group中多endpoint。
- 历史：是 `AQ-R8-003` reservation顺序与 `AQ-R7-004` cohort隔离组合后的新反例；基础的一attempt一reservation结构本轮已验证通过。

### AQ-R9-010 — RefreshBatch 无法表达无 LKG 的 expired provider failure

- Severity：`High`
- 确定性：高
- 证据：`E1/E3`
- 分类：`当前缺陷`
- 定位：`docs/design-proposal.md:363-403,1026-1046,1129,1486,1514`；`docs/provider-contract.md:215-217,369`；`docs/security-model.md:180-181`
- 事实：core规则要求 Provider failure 在没有同 generation LKG时合成 `expired + 对应 health + value=None` 的 CapabilitySnapshot。RefreshRequestResult不变量却只允许 `provider_fresh|singleflight_fresh|lkg_stale` 携带 snapshots；`failure|timeout|capacity|outcome_unknown` 必须 snapshots为空。无 LKG 的 network/429/5xx/schema failure既不是 fresh，也不是 LKG stale；若 disposition=`failure` 又不能携带规范要求的 expired snapshot，所以没有合法结果。Provider 429的 `retry_after_seconds` 也被“只有 deferred可带”排除在 provider failure结果之外。
- 影响：首次刷新失败时，实现必须丢掉规范 snapshot、伪装为 fresh/LKG、违反 result algebra，或退回顶层 OperationError并丢完整 request key集。幂等 replay不能稳定还原同一结果。
- 修复：把 per-request value改成判别联合：Provider业务失败分支可携带恰覆盖 request keys 的 stale/expired snapshots和受限 retry-after；pre-attempt deferred/capacity/timeout分支可保持空 snapshots。明确每种 FetchFailureCategory到 disposition/failure code/snapshot的全映射。
- 验证：每个 Provider failure category分别覆盖有/无 LKG和 429 retry-after；每个输入 key恰一 snapshot或恰一合法空结果，所有组合可被 schema构造并逐字节重放。
- 历史：`AQ-R8-008` 的 per-request改造解决了多请求外形，但没有覆盖无 LKG failure 的内部代数。

### AQ-R9-011 — migration new-object handle 无法由 envelope重算

- Severity：`High`
- 确定性：高
- 证据：`E1/E3`
- 分类：`当前缺陷`
- 定位：`docs/design-proposal.md:1556-1604`，特别是 `1568-1579`、`1588-1600`
- 事实：`NewObjectRef` 在 envelope中只有 `object_id/new_object_handle/proposed_object_id`；handle recipe却额外输入 `creation_parent_ref`。正文随后明确 `creation_parent_ref` 是 existing ID、另一个 new handle或 null，并且不是 action graph edge，但这个字段既不在 object_ref，也不在 payload其他位置。只拿规范 envelope的 validator无法重算 `new_object_handle`，也不能验证攻击者替换 parent后handle是否应变化。
- 影响：dry-run、确认、journal恢复和两套实现不能独立验证同一 canonical plan；实现只能依赖 envelope外的隐式 planner状态或从被hash隐藏的配置值猜 parent，破坏自包含digest。
- 修复：把 `creation_parent_ref` 作为 NewObjectRef的必填判别字段写入 envelope并进入 semantic body/digest；或者从recipe中删除它并用已包含、可唯一重算的字段替代。禁止依赖 envelope外状态。
- 验证：固定 create principal→subject→capability vectors，两实现只凭 envelope即可重算每个handle；改 parent/null/new-handle任一 bit都改变handle和plan digest。
- 历史：`AQ-R8-004` 引入 canonical new handle时遗漏了其一个 recipe输入；这是其 `FIXED` 声明的直接反例。

### AQ-R9-012 — migration graph只编码 cascade，未编码 create/general semantic dependency

- Severity：`High`
- 确定性：高
- 证据：`E1/E3`
- 分类：`当前缺陷`
- 定位：`docs/design-proposal.md:1600-1606`；`docs/security-model.md:261`
- 事实：正文说 `creation_parent_ref` “不是 action graph edge”；graph只由每个 `cascade parent` 建 `parent→child` edge。Kahn排序因此看不到“先创建principal再创建subject”“create后才能update/引用”“先remove_reference再delete”等执行依赖。semantic key的字节顺序可能把child create排在parent之前；多实现即使算出同一顺序，也会得到语义上不可执行的计划。
- 影响：合法create/cascade计划可能在中途违反外键/registry不变量，或者实现私自增加隐藏排序规则，导致dry-run bytes、action ID、plan digest和恢复次序分叉。
- 修复：定义完整 semantic dependency graph，至少包含 creation-parent、create-before-use、remove-reference-before-disable/delete、child-before-parent-delete和generation replacement依赖。所有执行先后只能来自该 graph；隐藏依赖拒绝。
- 验证：对嵌套create、create+update、cascade delete、引用移除、同层重排和cycle生成golden DAG；任意输入遍历顺序得到相同且每步可执行的action order。
- 历史：`AQ-R8-004` 只冻结cascade拓扑，没有冻结所有action依赖。

### AQ-R9-013 — journal标记 complete 后的 attached claim没有恢复路径

- Severity：`High`
- 确定性：高
- 证据：`E1/E3`
- 分类：`当前缺陷`
- 定位：`docs/design-proposal.md:1791-1805`；`docs/security-model.md:228,263`
- 事实：完成步骤先把journal标为 `complete`并清空 `new_config_bytes`，之后才删除临时文件/claim并fsync。DB commit与文件/claim清理不可能原子；若在“complete commit之后、claim delete之前”kill，journal已不再active，claim仍为 `attached`。orphan规则明确只处理 `name_claimed|file_opened|file_sealed→cleanup_claimed`，并明确 `attached` 只能由同migration active journal roll-forward，不能由orphan接管。恢复算法也只列 `prepared/file_committed/db_committed`，没有 `complete+attached`。
- 影响：一个明示要求覆盖的kill point会永久留下不可清理claim并关闭gate；人工删除又绕过no-follow/fence安全状态机。
- 修复：增加 `cleanup_pending` journal阶段，先按fence清理/确认temp basename与claim并fsync，再在最后一个DB事务标 `complete`；或明确允许completed journal以只清理相同attached claim的幂等恢复分支。必须保留完成清理所需字段直到清理证明完成。
- 验证：在 complete事务提交前后、claim delete前后、父目录fsync前后逐点kill；重启必须幂等收敛，且永不unlink当前config或非本migration inode。
- 历史：`AQ-R8-005` 修复了pre-journal create/write窗口；本项是新增状态机的terminal cleanup窗口。

## 4. 已闭环、不适用与用户决策区分

### 4.1 已闭环，本轮不报为问题

- 四份 contract 的登记摘要均按 `SHA256("agent-quota:contract-artifact:v1\0" || aq-jcs-nfc-v1(document))` 重算匹配；fixture登记摘要也匹配。
- operation artifact 的 operation/mode/path/error/safe-schema主键唯一；stage、predicate ID、error code、safe schema引用无悬空/未使用；每个 `provider_io` step均恰有一个更早、同request kind、未消费reserve，且没有多余reserve。缺陷是这些对象的语义定义，不是当前静态引用关系。
- Credential Source唯一返回 `CredentialResolution`，core派生AccessIdentity后构造`CredentialLease`；现行DTO字段只有一份规范定义，本轮没有重现第5/7轮的Resolution/Lease所有权循环。
- IdentitySourceContract/ProviderIdentityDomain/EndpointBudgetGroup/Binding的抽象双向闭包已写入manifest模型；本轮问题是unknown bootstrap与既有verified activity没有共同umbrella blocker。
- temp claim在`name_claimed/file_opened/file_sealed`阶段的pre-journal kill points已有可判别恢复；本轮只报告`complete+attached` terminal组合。
- nonce由每generation独立key和单调sequence确定，永久nonce set已移除；本轮问题是JSON byte wire未定义，不重报nonce set无界。
- retention fixture文件与live inputs不相交，fixture canonical digest匹配；本轮问题是parser能力和detector grammar。

### 4.2 不适用

- 仓库没有应用代码、测试、数据库或构建产物，不能运行unit/integration/e2e、migration runtime、真实installer或Provider合约测试。这不等于测试通过。
- 新contract文件没有直接引入publisher/root public key或远程trust root；供应链trust仍由正文的installer genesis/trust bundle合同约束。本轮没有发现需要另列的新增trust-root值。
- Hermes/飞书/Web仍是后续可选阶段；本轮已审阅其边界，但未把“尚未实现”当0A缺陷。

### 4.3 用户决策

- 只有`AQ-R9-001`需要用户选择产品基线。
- `AQ-R9-002..013`都可在不扩大Provider权限、不读取真实账户、不改变Codex产品选择的前提下直接修订。

## 5. 当前源与机器合同哈希

### 5.1 当前正文 raw SHA-256

```text
417bb0d222ac8145b82786003485999190bd38ad070257458e27861f778a5b73  README.md
25e45df29db84f6901212787f0987d262d8839a300a68d963f17d4796c15507e  docs/design-proposal.md
2024384f2c383c87a468640ec38c75d7e2b459c1de09ee1f71c96db3bb10c64f  docs/provider-contract.md
fe1087293227e53ccd230b9c09275ac87fc0b45a35b6d4fa0b772b912c79ec92  docs/security-model.md
```

### 5.2 contract raw / canonical登记摘要

| artifact | raw SHA-256 | contract/fixture canonical SHA-256 | 结果 |
| --- | --- | --- | --- |
| `operation-contract-v1.json` | `a433a19df0b13d557780f8df780c09d9f568178fb4507f89c7f62832ded07e57` | `f6473f26f12b1452fa5430c4667ca43a00d43f620885bc423637bec64122cb23` | 匹配 |
| `local-key-purpose-registry-v1.json` | `bbfad297afd49d001e87f929005cf55ec7c3f69df2a4e716ae6d25ee7048d6a4` | `a48a6a5afc1ed280d3730f3653da03bb4c3d5fec3598b0e0c9d37c1b238c11a6` | 匹配 |
| `lease-policy-v1.json` | `9c4c3314cf4583a5106e996eb5f48232bf697ab1f5b01be5e1eaa52330db4148` | `3664e6edd314e9f82cbdd0c1b8f313fd61bcd51e5c78e8aa7d2c9f6e23a49cef` | 匹配 |
| `retention-lint-v1.json` | `a1b0367641b258248ca28b27108cf7b2d0c2b5473715e67e12d7aa546ee9df7f` | `2adf6e1280845b8eff80e20f1ca8ee923f78bb7989ac895a0a0ac6bdc8d3e6ef` | 匹配 |
| `retention-lint-malicious-v1.json` | `df56debb25e6d35dbee009dc9e94ba837d7f091ddec12a89843ba36f7b6f1865` | `abcd5c5ab6b93b33dbf561accb1d0cadbefaa6b3693aa31a3232395bd74fd82a` | 匹配 |

## 6. 历史完整性与去重

第8轮审计在其`4.2`节登记的round-01..07 audit/resolution SHA-256与本轮重算逐项相等，说明这14份历史文件在该基线后没有变化：

```text
a00a14c901881d84ba7648987a2cb7ceff92b41bd9f077a13605e38bad76abdd  round-01-audit.md
c997a3853d0d47b9e44e1fbb0f8476ddbdf9006438855a3cf1cd246857b54c9a  round-02-audit.md
4c0283dfe7827922b0be8001e8b0d381e247ac6f6fab3d8c95d9c95aba2cca32  round-03-audit.md
ea0e5002fa17b6d3a8396c5ce8d11fa321e45ae2b1470ba33149a845b1a82897  round-04-audit.md
7339b048a03f98b91119d01fec86d6364af645043da42cbfc42617de48542c86  round-05-audit.md
0924b992e71170ef4944980e37c7fe85fdf1a56a09a489ab77b9d987de62cd32  round-06-audit.md
91af1b28dd94c9372eeeb0410e0a8a77b20df3c293a64f4d33d76aba601482c9  round-07-audit.md
c4630344e20561d3677e6d393cf206f4bf6d438871444d28e9d7872dedd53935  round-01-resolution.md
8b13adaec95df01fa7da78bbed6c305076597535f4e415f396840be4774c65df  round-02-resolution.md
7ad08ed95a607d1a353c9c54d4bbd359798dd6145c2f6a3918204e3efae12581  round-03-resolution.md
2b57e50bbfe68928a74a7d2d090614407909a5da1481c80db6710219cd2cf171  round-04-resolution.md
0c3858ded76f622b3dc50ec87c9de0f931f97b6cdd93b0f0ed9de2f98c3d27a4  round-05-resolution.md
97048a24cab36d824726227278d68f71e74d60650abf3e1488438da8ed448609  round-06-resolution.md
9c9593995ac82d1a10475b32db790ea5b40ccd8be8a6be9bd963a0487637175b  round-07-resolution.md
```

round-08没有更早的commit或外部hash anchor；本轮只记录当前值：

```text
9ca8cdb4046e6b5bfcfd73b32f3385af5cfc52dc89289492389b82742da4dde2  round-08-audit.md
be178d129e98b1330b494acd5945ddab11cbb5916ecc0906ee50864f03b0b193  round-08-resolution.md
```

去重结果：`AQ-R9-001`是明确保留的旧用户决策；其余项目均以现行v1.4的具体反例成立。它们多数揭示第8轮`FIXED`处置只关闭了原问题的一层，不是复制旧问题文字；每项历史关系已在问题内说明。

## 7. 可复核命令摘要

```text
sed -n '1,260p' /Users/kyle/.codex/skills/audit-verify-explain-grade-5/SKILL.md
nl -ba README.md
nl -ba docs/design-proposal.md
nl -ba docs/provider-contract.md
nl -ba docs/security-model.md
nl -ba docs/contracts/*.json
nl -ba docs/contracts/fixtures/*.json
jq -e . docs/contracts/*.json docs/contracts/fixtures/*.json
shasum -a 256 README.md docs/*.md docs/contracts/*.json docs/contracts/fixtures/*.json
python3 <strict-json script>                # duplicate key/non-finite number check
python3 <canonical-hash script>             # NFC/float check + JCS-like canonical bytes + domain hash
python3 <operation-closure script>          # path/error/ref/predicate-use/reservation bijection
pandoc -f commonmark -t json docs/security-model.md | jq <Table count>     # 0
pandoc -f commonmark_x -t json docs/security-model.md | jq <Table count>   # 6
rg -n 'conservative|reuse_observation|enum_values|allowed_values' docs/contracts/operation-contract-v1.json
rg -n 'AES|GCM|base64url|ciphertext|key material' README.md docs/*.md docs/contracts/*.json
shasum -a 256 docs/audits/round-0[1-8]-audit.md docs/audits/round-0[1-8]-resolution.md
git status --short --branch
```

命令中的Python只读取公开规范并输出hash/闭包统计，没有写文件、读取环境或访问网络。没有安装依赖；`jsonschema`模块当前未安装，因此没有把“缺少该本地包”误报为规范问题。

## 8. 最终门禁

`FAIL_WITH_13_ISSUES`

在用户处理`AQ-R9-001`，并修订`AQ-R9-002..013`、重新生成/登记contract摘要、由全新独立Agent再次全量验证前：

- 不得宣告零问题；
- 不得通过阶段0A；
- 不得把Codex作为Supported MVP Adapter开始正式fetch实现；
- 不得把`jq可解析+摘要匹配`当作machine contract可执行闭包的证明。
