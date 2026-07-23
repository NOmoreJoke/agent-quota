# Agent Quota 第 11 轮独立对抗性设计审计

- 审计日期：2026-07-18（Asia/Shanghai）
- 审计者：独立 Agent `/root/audit_round_11`
- 唯一结论：`FAIL_WITH_12_ISSUES`
- 严重度：Blocker 2 / High 8 / Medium 2
- 分类：用户决策 1 / 不改变 Codex 身份基线即可修订 11 / 本轮驳回 0
- 阶段 0A：不通过

## 1. 结论

现行 v1.6 不能宣告零问题，也不能进入阶段 0A。Codex stable identity 仍是必须由用户选择产品基线的 blocker；本轮没有加入 `account/read`、没有移除 Codex、没有从 rate-limit payload、进程或 principal 猜测账户身份。

另有 11 项不改变该身份基线即可修订的问题，其中 `AQ-R11-001` 会按当前加载顺序直接拒绝合同集合：registry 中 3 个 canonical pin 与现行文件不符，正文登记的 registry canonical anchor 也已失效。其余问题覆盖 identity context 数据流、doctor/discover 预算拒绝的 credential 副作用、74 个 array pointer 的顺序合同、lease typed AST、Codex schema descriptor、LocalKey payload、retention 路径与 detector、core-safety fixture、operation/migration 投影一致性。

## 2. 范围、独立性与证据方法

### 2.1 读取顺序

本轮先完整读取 `audit-verify-explain-grade-5/SKILL.md`，随后从零完整审阅：

- `README.md`；
- `docs/design-proposal.md`、`docs/provider-contract.md`、`docs/security-model.md`；
- `docs/contracts/contract-registry-v1.json`；
- 5 份 artifact、6 份 Draft 2020-12 schema、2 份 fixture。

读取任何 `round-01..10` audit/resolution 前，候选清单冻结为 12 项：canonical digest、Codex identity、context/reservation 顺序、doctor/discover credential 副作用、array order、lease AST、Codex descriptor、LocalKey payload、retention path、retention detector、core fixture、权威投影。之后才读取历史做去重；没有从历史反向添加候选，也没有因既往 `FIXED` 声明删除当前仍可复现的问题。

### 2.2 证据等级

- `E1`：现行本地文件、精确行号或 JSON pointer、raw/canonical hash。
- `E2`：本轮直接执行的 JSON Schema、Pandoc、排序、密码学或摘要核对。
- `E3`：只使用现行规范构造的确定性反例或状态机推导。
- `E4`：`round-01..10` 历史，只用于去重与核对处置声明。

### 2.3 隐私与调用边界

本轮没有读取环境变量、系统凭据、Codex/Hermes 登录材料、真实账户、额度、计划、重置时间、Token、Cookie 或 Provider 响应；没有执行真实 Provider HTTP、真实账户 RPC、`account/read` 或 `account/rateLimits/read`。所有动态证据仅处理仓库公开规范、虚构 vector 与本地公开工具版本。

## 3. 问题清单

### AQ-R11-001 — 三个 canonical pin 与现行文件不符，合同集合按规定顺序不可加载

- Severity：`Blocker`
- 确定性：高
- 证据等级：`E1/E2/E4`
- 分类：`当前缺陷；身份外可直接修订`
- 定位：`docs/contracts/contract-registry-v1.json:7-10,27,35-39,61-62`；JSON pointers `/artifacts/0/schema_canonical_sha256`、`/artifacts/2/artifact_canonical_sha256`、`/artifacts/2/schema_canonical_sha256`；`docs/design-proposal.md:12`。
- 事实：按 registry 自己的域分离 recipe 与 `aq-jcs-nfc-v1` 重算时，7 个未受影响的 artifact/schema pin 与 2 个 fixture pin均可逐字复现；但以下 3 个值不匹配：

  | 对象 | registry pin | 本轮重算 |
  | --- | --- | --- |
  | core-safety schema | `249dddf0a8d50472fc0fd7367a503bea19ae218db8e8a7ec3e4805acffd71374` | `5fa8df475d8041ee7f3f591afcbb09739c0daf87fbd883cb7e5087a6886528ff` |
  | LocalKey artifact | `df0f830bdb06ac4f462c7d467585783b6a2e85f5fd076f33c4f83ae263e538c3` | `66a7a8d8342195663bd7153d8f31b901bb700894fadabecfe558455054533a9a` |
  | LocalKey schema | `e98cf47bab219b8f6ea6f279679b59b19e34b987450f801983c07b034725cb0c` | `a9e041c913c74413b20229f01a394c693330c322caab6f53fc80842e92906880` |

  现行 registry 的 domain-separated canonical digest 是 `cb7913746fa869cd365fc8ece694ed3bf372e9d8fdbde7d3bfcd5798cc50a79d`，正文仍登记 `ed6c37af941bfb6d5129dc36ef38314efdc2f99324807c1d0a391cc61fa60e8a`。raw SHA-256 均与 registry 当前 raw pin 相符，故这不是读错文件或换行问题。
- 影响：`validation_order` 在 semantic closure 前先做 schema/artifact canonical hash；严格 loader 必须拒绝 core schema 与 LocalKey artifact/schema，后续所有声称“语义验证通过”的门禁都到不了。若实现忽略 canonical pin，则又违反 registry 的 `schema_hash_mismatch/artifact_hash_mismatch=reject`。
- 修复：修正本报告其他问题后，以同一个受版本控制的 canonicalizer 原子重算所有 raw/domain pin与正文 registry anchor；不要只手改这 4 个字符串。把 registry 自身 anchor 的生成加入同一脚本并输出输入清单。
- 验证：两套独立实现重算 5 artifact、6 schema、2 fixture 和 registry；每项等于登记值。任一文件单 bit 或数组相邻交换都必须改变相应 canonical pin并在 semantic validation 前拒绝。
- 历史去重：R10 处置称全部注册摘要重算匹配；现行文件证明该声明已经失效，属于 R10 修订后的当前 blocker。

### AQ-R11-002 — Codex 仍无可批准的 stable identity evidence source

- Severity：`Blocker`
- 确定性：高
- 证据等级：`E1/E4`
- 分类：`用户决策`
- 定位：`README.md:3,42,62`；`docs/design-proposal.md:1146,1192,1215,2169,2308`；`docs/provider-contract.md:144-146,191,202,206`；`docs/security-model.md:170,177-178,417`。
- 事实：正式 `FetchContext` 要求 `verified_stable` AccessIdentity。现行 Codex 只登记 endpoint budget group，未登记可产生 stable account/session evidence 的 `IdentitySourceContract` 或 `ProviderIdentityDomain`；允许的业务 RPC 只有 `account/rateLimits/read`，规范同时禁止从其额度 payload、进程、principal 推断 identity，也禁止在用户决策前加入 `account/read`。
- 影响：Codex 必须保持 `incompatible`，不能正式 fetch、不能持久化 cache/LKG、不能成为 Supported Adapter，阶段 0A 不能通过。
- 修复：由用户选择互斥产品基线后，再冻结被批准的稳定身份来源、字段、generation、domain 与账户切换语义；或维持当前 fail-closed 产品状态。本审计不代用户加入 RPC，也不代用户移除 Codex。
- 验证：决策前所有 Codex Supported/fetch fixture 持续 fail closed。决策后覆盖切换账户、登出重登、重启、同/异账户多 principal，证明 cache identity 隔离与 cohort 合并均只依赖获批 evidence。
- 历史去重：与 `AQ-R2-001` 至 `AQ-R10-001` 的明确未决 blocker 同源；R10 resolution 仍标记 `BLOCKED_USER_DECISION`，本轮独立复核后结论不变。

### AQ-R11-003 — 三条 Provider 路径在 reservation receipt 存在前构造必填 receipt 的不可变 context

- Severity：`High`
- 确定性：高
- 证据等级：`E1/E3/E4`
- 分类：`当前缺陷；身份外可直接修订`
- 定位：core-safety artifact JSON pointers `/identity_bootstrap/identity_and_fetch_context/required_fields`、`/identity_bootstrap/identity_and_discovery_context/required_fields`（`docs/contracts/core-safety-contract-v1.json:31-36,46-50`）；operation artifact `/paths[path_id=discover-official-cli-v1]/steps`（`453-463`）、`/paths[path_id=refresh-http-v1]/steps`（`874-884`）、`/paths[path_id=refresh-official-cli-v1]/steps`（`965-975`）；`docs/design-proposal.md:1012-1023,1036-1045,1052-1061,1142`。
- 事实：三种 context 的 DTO 都要求非空 `reservation_receipt`，且 official joint context 被声明为 core-owned deep-frozen。机器 path 却依次执行 `identity_and_discovery_context_build → rate_ledger_reserve`、`operation_context_build → rate_ledger_reserve`、`identity_and_fetch_context_build → rate_ledger_reserve`。build 时 receipt 尚不存在；reserve 后又没有第二个 final-context build stage。
- 影响：实现无法同时满足 stage trace、必填 DTO 与深冻结。它只能先塞占位值后突变、让 Adapter 不拿 receipt、或秘密重建第二个未登记 context；三者分别破坏不可变绑定、Provider-I/O receipt gate或唯一执行矩阵。
- 修复：把成功 reserve/commit 放在最终 context build 前；若 reserve 所需参数必须先聚合，冻结独立的 `*RequestPlan` 预上下文，再由 receipt 构造唯一 final context，二者使用不同 schema/stage。所有 Provider I/O 只消费 final context。
- 验证：生成每条 online path 的数据依赖图，要求 `receipt.produced_at < final_context.created_at < first_provider_byte_at`；对 null/占位 receipt、receipt 后突变、错误 endpoint/group/request kind/fence均拒绝。kill-point证明 reserve拒绝时没有 context 被交给 Adapter。
- 历史去重：R10-005 要求 joint DTO；R10 resolution 新增 DTO 后仍把 build 排在 reserve 前，本项是该修复的数据流残缺，不是恢复旧设计。

### AQ-R11-004 — doctor/discover HTTP 在 reserve 拒绝前已经读取 credential

- Severity：`High`
- 确定性：高
- 证据等级：`E1/E3/E4`
- 分类：`当前缺陷；身份外可直接修订`
- 定位：operation artifact `/paths[path_id=discover-http-v1]/steps`（`docs/contracts/operation-contract-v1.json:380-395`）、`/paths[path_id=doctor-http-v1]/steps`（`575-590`）、`/rate_reserve_result_contract/provider_path_ids` 与 `/credential_read_count_before_reserve`（`1995-2001,2052-2056`）；core-safety artifact `/budget_ledger_contract/mismatched_group_policy_reference`（`docs/contracts/core-safety-contract-v1.json:76-83`）；`docs/design-proposal.md:1582,2304`；`docs/security-model.md:416`。
- 事实：共享 reserve result contract 对四条 doctor/discover provider path承诺 `credential_read_count_before_reserve=0`。但两条 HTTP path均先执行 `credential_resolve`、`identity_derive`，之后才 `rate_ledger_reserve`。这不是抽象可能性，而是 exact stage array 的确定顺序。
- 影响：floor/hour/blocked-until、ledger、lease、fence或storage拒绝时已经触碰系统凭据后端，直接违反“Provider/Credential/cache副作用为零”的公开安全合同；不可用 Keychain/Secret Service还可能抢先返回另一个错误，使同一预算状态得到不同结果。
- 修复：按现行 umbrella 语义先用 deployment conservative group完成第一阶段 reserve，再解析 credential/evidence；verified cohort 只能在同一 reservation row 上附加/check，不得删除旧 row、建立第二次 capacity 或第二次 Provider attempt。
- 验证：为 discover-http/doctor-http 注入每个 reserve rejection，credential source read counter必须为 0；成功路径仍只有一 row、一次 credential resolution与一次 Provider attempt。unknown→verified rebind不能增加 floor/hour容量。
- 历史去重：R10-004 修复了结果 union，R10-011 修复了 umbrella policy；当前 exact path仍违反两项处置共同承诺。

### AQ-R11-005 — 74 个 array pointer 没有统一现行 dialect，且 core fixture 本身违反 utf8 顺序

- Severity：`High`
- 确定性：高
- 证据等级：`E1/E2/E4`
- 分类：`当前缺陷；身份外可直接修订`
- 定位：registry `/semantic_validators/schema-array-order-coverage-v1` 与 `/closure_rules/array_order`（`docs/contracts/contract-registry-v1.json:52,65`）；`docs/design-proposal.md:2302`；lease schema `/x-aq-array-order`（`docs/contracts/schemas/lease-policy-v1.schema.json:557-594`）；operation schema `/x-aq-array-order`（`docs/contracts/schemas/operation-contract-v1.schema.json:863-974`）；core schema override `/$defs/fixtureArtifact/properties/cases`（`docs/contracts/schemas/core-safety-contract-v1.schema.json:5-18`）；`docs/contracts/fixtures/core-safety-v1.json:19-22`。
- 事实：枚举 6 份 schema 得到 `4+18+6+6+19+21=74` 个 `type=array` schema object，全部 override pointer存在且不重复。4 份 schema使用现行 `{default:"sequence_exact",overrides:[{policy:"utf8_key",key_json_pointers:...}]}`；lease与operation的 25 个 array仍使用未登记 dialect `{default:{kind:"sequence"},utf8_key_overrides:[{key_pointers:...}]}`。即使兼容解释旧 dialect，core fixture `/cases` 还有确定逆序：`path-case-variant` 位于 UTF-8 bytes 更小的 `path-canonical-artifact` 前。
- 影响：只实现 registry 声称的 `sequence_exact|utf8_key` validator会拒绝两份 schema；兼容旧 dialect的validator又引入未版本化解释。进一步地，任何正确执行 core fixture override的实现都必须拒绝当前被 pin 的 fixture，因此“74 pointer覆盖/现行顺序通过”不成立。
- 修复：将 lease/operation 规范化为唯一登记格式；按 `fixture_id` 修正 core fixture顺序；重算受影响 schema/fixture/registry摘要。为 `x-aq-array-order` 本身提供 meta-schema/version，而不是让实现按字段名猜 dialect。
- 验证：枚举恰为 74，每个 array恰得一项策略；6 份 schema、5 artifact、2 fixture当前实例全部满足策略。对每个 keyed array做相邻交换，两个独立validator都拒绝；对 sequence array换序必须造成 canonical mismatch。
- 历史去重：R10-002 的处置声称所有 schema已采用同一 exact policy且现行文件通过；本轮计数与逆序反例直接否定该处置验证。

### AQ-R11-006 — lease 的 crash grace 仍不是 typed constant，schema 还接受越过 int64 的毫秒值

- Severity：`High`
- 确定性：高
- 证据等级：`E1/E2/E4`
- 分类：`当前缺陷；身份外可直接修订`
- 定位：lease artifact `/operand_definitions[operand_id=crash_grace_ms]`（`docs/contracts/lease-policy-v1.json:161-165`）、引用它的 formulas（`294-305,371-385`）；lease schema `/$defs/intMs`（`docs/contracts/schemas/lease-policy-v1.schema.json:102-106`）、`/$defs/operand`（`242-280`）、`/$defs/ast/oneOf/1`（`296-309`）；registry raw int bound（`docs/contracts/contract-registry-v1.json:20-21`）；`docs/design-proposal.md:1569,2303`。
- 事实：`crash_grace_ms` 的唯一数值只藏在自由字符串 `source="literal-2000"`；operand schema没有 typed value字段，AST literal又只有无单位 integer/null。实现若不解析自然语言式 source就无法得到 2000 ms。另有边界冲突：lease `intMs.maximum=9223372036854776000`，比 signed int64 max `9223372036854775807` 大；本轮 JSON Schema mutation确认 `9223372036854775808` 与 `9223372036854776000` 均通过 lease schema。
- 影响：两个 AST evaluator可分别把 source当 opaque ID或解析尾数，得到不可执行/不同 crash boundary；只走 lease schema的生成器还可产生 registry raw-bound必拒绝的“结构合法”policy。typed inference、conversion与checked arithmetic因此没有单一输入域。
- 修复：把常量建模为带 `type=int64_ms,value=2000` 的 typed operand或带unit的AST literal；所有 int64 schema上限统一为 `9223372036854775807`，并让 raw bound与schema共享一个机器常量。
- 验证：两套 evaluator不解析 `source` 文本即可推导全部 formula；1999/2000/2001 ms golden vector一致。对 `2^63-1` 接受、`2^63` 拒绝，boolean/float拒绝，任何 ms/ns混参在执行前失败。
- 历史去重：R10-003 修复了 `min_int64_ns`，但未把 crash grace常量和 int64边界纳入 typed closure。

### AQ-R11-007 — Codex descriptor 的“固定”构造示例仍漏掉 InitializeResponse root

- Severity：`High`
- 确定性：高
- 证据等级：`E1/E3/E4`
- 分类：`当前缺陷；身份外可直接修订`
- 定位：core-safety artifact `/codex_schema_bundle/descriptor_roots` 与 `/wire_schema_references`（`docs/contracts/core-safety-contract-v1.json:6-18`）；core schema `/properties/codex_schema_bundle/properties/descriptor_roots`（`docs/contracts/schemas/core-safety-contract-v1.schema.json:27-37`）；`docs/design-proposal.md:1455-1457,1463-1471,1491`；core fixture `codex-initialize-bit-flip`（`docs/contracts/fixtures/core-safety-v1.json:10`）。
- 事实：机器合同正确要求两个 roots：aggregate v2 与 `v1/InitializeResponse.json`。但正文紧接着称“bundle 描述符固定为”，其 executable projection 的 `roots` 数组只写 aggregate v2一项。`protocol_schema_hash` 又直接哈希该 projection。按该代码执行，InitializeResponse bit flip不会进入 descriptor；按 machine artifact执行则会改变 hash。
- 影响：两份都被写成规范性的实现说明给出相反 hash closure。复制正文构造器的实现可在 InitializeResponse schema改变时继续接受旧 `protocol_schema_hash`，违反 wire validator与 core fixture。
- 修复：从 machine artifact的 exact `descriptor_roots` 与 `wire_schema_references`生成 descriptor；正文示例必须列出两项 path/hash，CI反向比较投影摘要。最好为 descriptor本身增加 strict schema，禁止手写 roots。
- 验证：两个 roots恰好一次且按 path bytes排序；删除/bit-flip任一 referenced root必须失败或改 hash，改变未引用文件保持 hash不变，runtime只能打开 descriptor roots。
- 历史去重：R10-006 的 machine artifact修复有效，但同轮未同步“固定”descriptor projection；本项是修复后仍存在的双规范。

### AQ-R11-008 — LocalKey 的“每 purpose 一个 active”与合法 schema/golden payload互相冲突

- Severity：`High`
- 确定性：高
- 证据等级：`E1/E2/E4`
- 分类：`当前缺陷；身份外可直接修订`
- 定位：LocalKey artifact `/purposes`（`docs/contracts/local-key-purpose-registry-v1.json:17-57`）、`/key_entry_semantics/load_validation` 与 `/active_cardinality_per_purpose`（`78-90`）、`/local_keyring_wire/golden_payload_envelope/payload/key_entries`（`125-140`）；LocalKey schema `/$defs/localKeyRingPayload/properties/key_entries`（`docs/contracts/schemas/local-key-purpose-registry-v1.schema.json:39-41`）；registry semantic validator（`docs/contracts/contract-registry-v1.json:47`）；`docs/design-proposal.md:1700,1710`。
- 事实：registry有8个 purpose，正文与semantic validator要求每个 purpose恰有一个 active。schema只要求 `key_entries.minItems=1`，load validation只拒绝“multiple active”，没有拒绝“registered purpose missing active”。被称为完整的 golden payload只含 `access-identity-v1` 一条 active，缺其余7个 purpose；它仍通过schema。本轮独立重算确认现有单条 `aqk_` key ID、nonce与AES-256-GCM envelope全部匹配，所以问题不是vector密码学，而是payload覆盖语义。
- 影响：实现A按正文拒绝golden，实施B按schema接受并在另外7个consumer首次使用时返回missing；也可由实现自行选择lazy generation。cache/cohort/action/idempotency/query/ledger key可用性因此没有唯一启动与恢复结果。
- 修复：明确选择且只保留一种合同：若所有purpose eager存在，则 schema/semantic validator要求 purpose集合等于registry且每项恰一active，并补全golden；若允许lazy，必须改写 cardinality、缺失结果、原子创建/恢复/rollback状态机与golden含义。不能同时保留当前两套语义。
- 验证：缺任一required purpose、零/双active、禁止purpose的verify-only、duplicate generation、key ID/salt/purpose bit flip均有结构化负向fixture；两套实现互读完整payload并选出相同active/verify set。
- 历史去重：R10-007 增加了key-entry语义与golden，但处置只验证现有一条entry的密码学，没有验证8个purpose的active覆盖。

### AQ-R11-009 — retention 自己的 repoPath 重新接受 dot segment 与 repeated slash，且没有 no-follow loader

- Severity：`Medium`
- 确定性：高
- 证据等级：`E1/E2/E4`
- 分类：`当前缺陷；身份外可直接修订`
- 定位：retention schema `/$defs/repoPath` 及其使用点（`docs/contracts/schemas/retention-lint-v1.schema.json:14-16,25,28-34`）；retention artifact `/inputs`、`/excluded_fixture_files`、`/fixture_artifacts`、`/locations/*/file`、`/inventory/file`（`docs/contracts/retention-lint-v1.json:19-32,34-67`）；registry fixed-root policy（`docs/contracts/contract-registry-v1.json:26`）；core repository path policy（`docs/contracts/core-safety-contract-v1.json:108-115`）。
- 事实：R10收紧的是 registry绑定路径和 core contract路径；retention schema另定义宽 regex `^(?:README\.md|docs/[a-z0-9_./-]+)$`。本轮 schema mutation确认它接受 `docs/x/../design-proposal.md`、`docs/./provider-contract.md` 与 `docs//security-model.md`。retention artifact也没有为这些嵌入路径引用 fixed-root/openat/O_NOFOLLOW算法。
- 影响：一个结构合法且可被签名/pin的lint合同可用别名扫描不同路径，或在检查与读取间跟随symlink；不同实现规范化与否会得到不同输入集合，导致遗漏真实owner、扫描错误文件或越过预期docs子树。
- 修复：复用一个全局 canonical RepoPath type，逐segment拒绝 `.`、`..`、empty/repeated slash、case/Unicode/percent alias；从一次打开的repo root逐segment `openat(O_NOFOLLOW)`，最终fd与canonical bytes一致。所有 artifact内部file/path字段都需注册到同一semantic validator。
- 验证：上述3个mutation及absolute、backslash、symlink、case/Unicode/percent变体全部拒绝；4个现行输入与2个fixture引用接受且解析到唯一regular fd。
- 历史去重：与R10-012相邻但不是重报：其修复范围只覆盖 registry/core path，现行 retention schema保留了第二个宽 `repoPath`。

### AQ-R11-010 — retention persistence detector 对词形/未知 pair 没有可执行的 fail-closed 规则

- Severity：`Medium`
- 确定性：中高
- 证据等级：`E1/E3/E4`
- 分类：`当前缺陷；身份外可直接修订`
- 定位：retention artifact `/detector_grammar/persistence_signal_lexer`、`/persistent_media_terms`、`/persistent_write_verbs`、`/unrecognized_persistent_medium_or_verb_pair`（`docs/contracts/retention-lint-v1.json:103-120`）；retention schema `/$defs/persistenceSignalLexer` 与 `/$defs/detector`（`docs/contracts/schemas/retention-lint-v1.schema.json:42-43`）；fixture `cases`（`docs/contracts/fixtures/retention-lint-malicious-v1.json:7-24`）。
- 事实：唯一 signal rule是 exact media term 与 exact write verb/sensitive object在六token内；没有stemming、plural/inflection表或“unknown pair”识别算法。`databases store quota snapshots` 因 `databases` 不命中 `database`，`SQLite records quota snapshots` 因 `records` 不命中write verbs，均不能按已定义signal rule形成声明。字段 `unrecognized_persistent_medium_or_verb_pair="reject_as_ambiguous"` 只给结果，不定义怎样从无限普通词汇识别“unrecognized persistent”；若把media附近任意未知词都当verb，又会让普通说明大面积误拒绝。18个fixture没有plural/inflection或未知pair反例。
- 影响：两个合理实现会一方漏掉新的持久化surface，另一方因过宽ambiguous规则拒绝无关文本；CI retention gate没有唯一 verdict，新增保存面可能绕过 `persist:<surface_id>` 与唯一owner。
- 修复：优先改为结构化 machine directive/AST，不用自然语言猜持久化；若保留lexer，冻结形态归一化、未知pair候选集合、词边界与否定/引用语义，并给出可执行伪代码或表驱动自动机。
- 验证：把上述两个反例、plural media、第三人称/过去式verb、中英混合与无关“database supports...”加入fixture；两套独立实现逐项得到相同 verdict，现行4正文仍通过且合法runtime timeout不误拒绝。
- 历史去重：R10-008 补了exact词典与precedence；本项只针对该修订未定义的词形/unknown-pair执行语义。

### AQ-R11-011 — core-safety fixture 只有 opaque label，没有可由合同执行的输入

- Severity：`High`
- 确定性：高
- 证据等级：`E1/E3/E4`
- 分类：`当前缺陷；身份外可直接修订`
- 定位：core fixture `/cases`（`docs/contracts/fixtures/core-safety-v1.json:7-31`）；core schema `/$defs/fixtureCase` 与 `/$defs/fixtureArtifact`（`docs/contracts/schemas/core-safety-contract-v1.schema.json:79-80`）；core artifact `/closure_rules/fixture_verdicts_must_match`（`docs/contracts/core-safety-contract-v1.json:120-130`）；registry semantic validator（`docs/contracts/contract-registry-v1.json:46`）。
- 事实：每个case只有 `domain`、任意1..512字符的 `vector` 字符串和 `expected`。例如 `change_v1_initialize_response_one_bit`、`new_keyring_old_registry_or_old_db_floor` 没有prestate、mutation target/bytes、graph/action或actual output；schema也没有discriminated input union。现行5个domain共25个label没有artifact内的解释表或fixture interpreter合同。
- 影响：validator不能仅凭合同构造被测状态。它只能硬编码label、把label当自然语言自行解释，或直接相信 `expected`；三者都不能证明 Codex closure、migration DAG、InstallationRegistry rollback、BudgetPolicy umbrella与repo path的实际行为。R10处置声称“fixture均执行”不可由仓库重现。
- 修复：为每个domain定义strict判别fixture schema，明确base input、mutation、actual computation与oracle；需要真实bytes/graph/payload时直接嵌入小型虚构对象或引用带pin的fixture文件。`fixture_id`只能诊断，不能决定结果。
- 验证：随机改fixture_id不改变verdict；随机改mutation必改变实际结果；两套独立runner不含case-name switch仍可执行全部case。对migration/registry的kill/rollback vector检查具体中间状态而非字符串。
- 历史去重：这是R10新增 core-safety fixture的可执行性缺口；历史没有提供当前25个label的机器解释器。

### AQ-R11-012 — 声称由 machine artifact 生成的 operation/migration 投影仍与权威源不一致

- Severity：`High`
- 确定性：高
- 证据等级：`E1/E3/E4`
- 分类：`当前缺陷；身份外可直接修订`
- 定位：operation artifact `/stages`、`/error_codes`（`docs/contracts/operation-contract-v1.json:25-56,68-87`）与 official paths（`453-475,965-986`）；`docs/design-proposal.md:259-278,330-343,435-456`；operation closure `/markdown_is_generated_projection`（`docs/contracts/operation-contract-v1.json:1988`）；core migration `/migration_graph/cascade_membership_fields`（`docs/contracts/core-safety-contract-v1.json:85-93`）对比 `docs/design-proposal.md:1664-1668`；`README.md:63,69-70`。
- 事实：正文 `ExecutionStage` 缺 `identity_and_discovery_context_build`、`identity_and_fetch_context_build`、`identity_verify_and_accept`，`OperationErrorCode` 缺 artifact已有的 `budget_deferred`；official discovery/refresh Markdown trace仍展示旧的 `operation_context_build/identity_derive` 顺序，而artifact使用joint stages。另一个同类投影漂移是 machine cascade field名 `cascade_root_semantic_key`，正文migration envelope写 `root_semantic_key`。这与“operation/stage/error唯一矩阵生成正文”及 `markdown_is_generated_projection=true`直接冲突。
- 影响：从正文类型/trace实现的core会拒绝artifact合法error/stage或构造不同migration bytes；从artifact实现的core又不能通过正文所承诺的反向projection digest。API类型、运行stage、plan digest与fixture会跨实现分叉。
- 修复：只从machine artifact生成类型union、trace、error table和migration字段投影；CI保存反向摘要并拒绝手工漂移。若正文示例不是规范，应删除可复制的完整类型/对象并明确只链接生成物。
- 验证：解析生成的Markdown/code block，比较operation/mode/stage/error全集合和exact trace；migration envelope字段集合逐字节等于core contract。对新增/删除一个stage/error/field的mutation要求CI失败。
- 历史去重：R10处置新增joint stages与cascade machine contract但没有同步全部projection；本项只报告当前可定位差异，不把历史旧表重复计数。

## 4. 本轮直接验证与未另报范围

### 4.1 通过的结构与工具检查

- 6 份 schema均通过 Draft 2020-12 meta-validation；registry、5 artifact与2 fixture均通过各自结构schema。结构通过不覆盖本报告的semantic closure反例。
- Pandoc精确为 `3.9.0.2`，4个输入均产生 API `[1,23,1,1]`。retention table、action TTL与inventory三个heading locator各唯一命中；请求的table/paragraph ordinal存在。本轮不重报R9 parser/locator问题。
- LocalKey现有golden单entry的 `aqk_` key ID、HMAC nonce与AES-256-GCM ciphertext/tag全部独立重算匹配。本轮不重报key-id recipe或AEAD primitive。
- 把两种 `x-aq-array-order` dialect按意图兼容解释时，5 artifact与retention fixture的现行 keyed arrays排序正确；确定逆序仅在core fixture的相邻case。本报告问题是dialect未统一加当前fixture逆序，不声称74个数组全部乱序。
- core-safety当前 BudgetPolicy→EndpointBudgetGroup→profile binding引用集合闭合；migration execution kind方向与cascade membership分离；InstallationRegistry schema承载bundle/attestation/plan字段。本轮不另报R10-009..011的旧字段缺失，剩余可执行验证问题已归入 `AQ-R11-004/011/012`。

### 4.2 可复现实验关键结果

```text
schema type=array count:
  registry=4 core=18 lease=6 local-key=6 operation=19 retention=21 total=74
array metadata dialect:
  current=registry/core/local-key/retention
  legacy=lease/operation
core fixture inversion:
  path-case-variant > path-canonical-artifact

retention RepoPath schema mutations:
  docs/x/../design-proposal.md  ACCEPT
  docs/./provider-contract.md   ACCEPT
  docs//security-model.md       ACCEPT

lease intMs schema mutations:
  9223372036854775807 ACCEPT
  9223372036854775808 ACCEPT
  9223372036854776000 ACCEPT

LocalKey golden:
  key_id_match=True nonce_match=True aead_match=True
  payload_purposes=1 registry_purposes=8 missing=7

canonical mismatches:
  core_schema=5fa8df475d8041ee7f3f591afcbb09739c0daf87fbd883cb7e5087a6886528ff
  local_artifact=66a7a8d8342195663bd7153d8f31b901bb700894fadabecfe558455054533a9a
  local_schema=a9e041c913c74413b20229f01a394c693330c322caab6f53fc80842e92906880
  registry=cb7913746fa869cd365fc8ece694ed3bf372e9d8fdbde7d3bfcd5798cc50a79d
```

### 4.3 不能运行的证据

仓库没有应用实现、数据库、installer或runtime，因此不能运行unit/integration/e2e、真实migration/rollback、Provider contract test或双实现互操作测试。缺少这些实现不单独计为问题；本报告只列规范自身可确定的矛盾、反例和不可执行合同。

## 5. 当前源、合同与历史完整性

### 5.1 当前正文 raw SHA-256

```text
b83367a66fb302d3f7a80bcdb702c58cdccd1c66c97b9964989e5bcc8f90f3fc  README.md
917954d05aab995baf86bef7f04f1d318c03d69379ae747683f3be95c831b502  docs/design-proposal.md
5ca139e5cb806648936624ef8e071450a378ca2959ae9cafd3f4f844a591280e  docs/provider-contract.md
03408c78740f53bec6cde213b22cd5b0ade07a13d4af19a302041a11340bceaf  docs/security-model.md
```

### 5.2 contract/fixture raw SHA-256

```text
72e8eaaf498aaf450bf1fd79105261a12dc7842e169dbc6ba8a82b5d79852fac  docs/contracts/contract-registry-v1.json
bc2510b7cdcce89b10db886357e2abf4d5ee0936a108d51eb246dced256a66e0  docs/contracts/core-safety-contract-v1.json
e7e111635aabfab7b58c9d8de9208c459f3dbf7b71e2964df7c12e22df5de055  docs/contracts/lease-policy-v1.json
bb4ff65f7725eeb76b0f7a6c78b7ec33b8cf7ef2524eb5896ea73e80975956f5  docs/contracts/local-key-purpose-registry-v1.json
10ca815a7d63c59b69223c0a8547b26f347f5611269a65248702d2be4fbc142b  docs/contracts/operation-contract-v1.json
9ef071eeb231f026697fd3adf6fd8c08f2926035cec5149e04a1c6a1be7f32ca  docs/contracts/retention-lint-v1.json
e39ccc2caff4d3d5c593fdcd6298b97a26c0cdaa20cd0d162fae6746657b0754  docs/contracts/schemas/contract-registry-v1.schema.json
6433f5347939c8cd3d7d23a0169e6b0647f47e84aba97b4c72916b551d7e2bd9  docs/contracts/schemas/core-safety-contract-v1.schema.json
04bca8a238604404c7a7a67a916ea5e91e9714df0d7dcfee5314537f1bff8147  docs/contracts/schemas/lease-policy-v1.schema.json
15a6cc06a386c164ed565fdb9b56f76b41c7e20f1c5c205f372fa560f218c390  docs/contracts/schemas/local-key-purpose-registry-v1.schema.json
df6e349c52f8ec45197a3428493f532ba686572f86515c931523163a3df6e716  docs/contracts/schemas/operation-contract-v1.schema.json
bde00880141e3e6ae1f803a8036f14d6c917a463ad948b98cd346f7636523b36  docs/contracts/schemas/retention-lint-v1.schema.json
26fb4a1f5dbab425ea95a473929cf175fe33d2e1e9037db079e9ce99c85ab069  docs/contracts/fixtures/core-safety-v1.json
4e8518af99539d4fb2bfd055f0acefaf18bf47105567e660fec0bb084b95970c  docs/contracts/fixtures/retention-lint-malicious-v1.json
```

### 5.3 历史完整性

本轮读取历史前已经冻结候选。`round-01..09` 的20个audit/resolution当前hash与round-10 audit记录的锚逐项一致；本轮另记录round-10两份当前hash：

```text
b0152d186058b1410f8dafaaeaa901ce154dfbf9aa6bdaea464f21f1e551d441  docs/audits/round-10-audit.md
095709aef7e7994884efa8e6ef05508be8ac4a2af6a7a7b3b67f3007dde72786  docs/audits/round-10-resolution.md
```

仓库仍为 `No commits yet on main`，`git rev-parse --verify HEAD`没有可用commit锚。写报告前 `git status --short --branch`仅显示原有未跟踪 `.gitignore`、`README.md`、`docs/`；本轮没有修改README、三正文、contracts、历史audit/resolution或`.gitignore`，没有stage、commit或push。

## 6. 可复核命令

```text
nl -ba README.md
nl -ba docs/design-proposal.md
nl -ba docs/provider-contract.md
nl -ba docs/security-model.md
nl -ba docs/contracts/*.json
nl -ba docs/contracts/schemas/*.json
nl -ba docs/contracts/fixtures/*.json
jq -e . docs/contracts/*.json docs/contracts/schemas/*.json docs/contracts/fixtures/*.json
pandoc -f commonmark+pipe_tables -t json <input>
shasum -a 256 README.md docs/*.md docs/contracts/*.json docs/contracts/schemas/*.json docs/contracts/fixtures/*.json
shasum -a 256 docs/audits/round-{01..10}-{audit,resolution}.md
git status --short --branch
```

本轮只读Python用于：Draft 2020-12 meta/instance validation、74个array schema object枚举与override解析、keyed-array顺序、canonical digest、repoPath/int64 mutation、Pandoc locator、`aqk_`/HMAC/AES-GCM golden重算。脚本没有读取账户、环境变量或secret，也没有调用Provider。

## 7. 决策、可修项与最终门禁

- 唯一用户决策：`AQ-R11-002`。
- 身份外可直接修订：`AQ-R11-001`、`AQ-R11-003..012`，共 11 项。
- 其中当前加载 blocker：`AQ-R11-001`；其余身份外项不需要改变Codex allowlist或产品基线。
- 本轮没有建议用加入 `account/read`、读取真实账户、移除Codex或降低stable identity要求来关闭任何问题。

最终结论：

`FAIL_WITH_12_ISSUES`

在用户处理 `AQ-R11-002`、修订其余11项、原子重算全部受影响摘要，并由新的独立Agent再次全量复审前：不得宣告零问题，不得通过阶段0A，不得把Codex作为Supported MVP Adapter执行正式fetch。
