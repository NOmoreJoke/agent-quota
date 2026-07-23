# Agent Quota 第 9 轮审计处置记录

- 处置日期：2026-07-18（Asia/Shanghai）
- 处置者：修订 Agent `/root/fix_round_9`
- 结论：`RESOLVED_WITH_1_USER_DECISION`
- 判定：13 项审计结论全部成立；12 项当前缺陷已修订，1 项保持用户决策，0 项驳回
- 阶段状态：仍不通过 0A；用户决策完成且全新独立 Agent 全量复审前，不宣告零问题

## 1. 逐项处置

### AQ-R9-001 — `BLOCKED_USER_DECISION`

审计判定成立，且本轮有意不代替用户选择。Codex 当前仍没有可生成 `verified_stable` subject evidence 的批准 source contract，因而继续 `incompatible`、不能正式 fetch、不能持久化 cache/LKG，也不能成为 Supported。现行 allowlist 未加入 `account/read`，Codex 未移出 MVP，安全要求未降级。证据见 `README.md:3,60`、`docs/design-proposal.md:1146,1169,1445,1457`、`docs/provider-contract.md:162,191`、`docs/security-model.md:170,177-178`。用户仍须在“批准额外只读稳定身份来源并冻结 source contract”与“保持最小 allowlist、降级 Codex 并替换第二个 MVP Adapter”之间选择；选择前相关 fixture 必须持续 fail closed。

### AQ-R9-002 — `FIXED`

审计判定成立。四份机器 artifact 现均有 `$schema/$id`，并新增五份 exact Draft 2020-12 schema；嵌套对象均封闭字段，registry 绑定 artifact/schema 的 raw 与 domain-separated canonical digest、官方 meta-schema、bounds、验证顺序和语义 validator。证据见 `docs/contracts/contract-registry-v1.json#/artifact_schema_bindings`、`#/validation_order`、`docs/contracts/schemas/*.schema.json` 与 `docs/design-proposal.md:12`。四 artifact 的 delete/add/rename/wrong-type/bool-as-int/float/duplicate-key/unknown-version 共 32 个负向向量全部拒绝，五份现行文档全部通过结构 validator。

### AQ-R9-003 — `FIXED`

审计判定成立。operation artifact 新增结构化 predicate 定义及缺值行为、八个 safe enum 的 exact allowed values、六个 Provider I/O step 的 ordinal/request/cohort/reuse 属性，并把定义、引用、恰一映射与未使用项纳入闭包。证据见 `docs/contracts/operation-contract-v1.json#/predicate_definitions`、`#/safe_param_schemas`、`#/io_step_definitions`、`#/closure_rules`。闭包验证覆盖 16 条 path、93 个 error 与 6 个 Provider I/O step，全部通过。

### AQ-R9-004 — `FIXED`

审计判定成立。lease artifact 现以 typed AST 冻结 clock domain、typed operand/operator、11 个 formula、grace 位置、边界比较和 checked overflow verdict；policy 与 renew/takeover/deadline rule 只引用 formula ID。证据见 `docs/contracts/lease-policy-v1.json#/clock_domains`、`#/operators`、`#/operands`、`#/formula_definitions`、`#/closure_rules`。闭包验证确认 11 个 formula、12 个 operand、7 个 operator 均无悬空或未使用项。

### AQ-R9-005 — `FIXED`

审计判定成立。LocalKey artifact 新增封闭的 `consumer_id -> purpose_id` 表、新值策略、两个有界 lookup policy，以及四个 persistent surface 的 generation 组合顺序、去重、上限与退休条件；正文公式仅通过 consumer ID 取 key。证据见 `docs/contracts/local-key-purpose-registry-v1.json#/consumer_bindings`、`#/verification_lookup_policies`、`#/persistent_surfaces`、`docs/design-proposal.md:1144,1525`。闭包验证确认 8 个 purpose、8 个 consumer、4 个 surface 全部可达且无自由 key 映射。

### AQ-R9-006 — `FIXED`

审计判定成立。LocalKeyRing wire 已冻结为 `HKDF-SHA-256` 与 `AES-256-GCM`，所有 byte field 只允许无 padding base64url，先解码再验证 nonce/tag/salt/key 长度；envelope/payload exact schema、AAD/nonce recipe 与无秘密 golden primitive vector 同源。证据见 `docs/contracts/local-key-purpose-registry-v1.json#/local_keyring_wire`、`docs/contracts/schemas/local-key-purpose-registry-v1.schema.json#/$defs/localKeyRingEnvelope`、`#/$defs/localKeyRingPayload`、`docs/design-proposal.md:1655`。本轮以 AES-256-GCM 重算 golden vector，得到 2-byte ciphertext 与 16-byte tag，逐字节匹配 artifact。

### AQ-R9-007 — `FIXED`

审计判定成立。retention parser 已改为 exact Pandoc `3.9.0.2`、reader `commonmark+pipe_tables`、唯一 extension set 与 API version，并冻结 Table/leaf AST model；任一版本、extension 或 API mismatch 都 fail closed。证据见 `docs/contracts/retention-lint-v1.json#/parser` 与 `#/locations`。干净解析当前安全模型得到 6 个 Table；retention table、inventory table 与 action paragraph 三个 locator 分别唯一命中预期 AST block ordinal `53/56/72`。

### AQ-R9-008 — `FIXED`

审计判定成立。retention artifact 现登记 ASCII/scientific/英文词数/中文数值、单位、NFKC、duration AST、retention context、owner/action 例外、runtime 非 retention 排除、持久介质/动词、`persist:` tag、token distance 与 ambiguity fail-closed 规则；fixture selection 明确禁止按 fixture ID 特判。证据见 `docs/contracts/retention-lint-v1.json#/detector_grammar`、`#/fixture_evaluation`、`docs/contracts/fixtures/retention-lint-malicious-v1.json#/cases`。规则驱动扫描接受四份现行正文，并让全部恶意 fixture 与其 expected verdict 一致。

### AQ-R9-009 — `FIXED`

审计判定成立。endpoint budget group 现为真正 umbrella：所有 verified attempt 也占同一 group blocker，unknown bootstrap 在首个 outbound byte 前检查 group 全部 activity；response 只给同一 reservation row 附加 verified index，因此一行只计一次 attempt、不双计。证据见 `docs/design-proposal.md:1098,1525`、`docs/provider-contract.md:160,379`、`docs/security-model.md:185`。复制 principal/binding/process 或丢失 identity cache 均不能绕过既有 verified floor/hour blocker。

### AQ-R9-010 — `FIXED`

审计判定成立。RefreshRequestResult 已改为判别联合：fresh、LKG、Provider failure、pre-attempt empty 与 outcome-unknown 分支分别拥有可构造的不变量；Provider failure 恰覆盖 request keys，有同 generation LKG 时生成 stale，无 LKG 时生成 `expired + value=None`，429 才可携带有界 retry-after。证据见 `docs/design-proposal.md:373-429`、`docs/provider-contract.md:215-217`、`docs/security-model.md:180-181`。failure category 到 disposition/health/snapshot 的映射及 byte-identical idempotent replay 均已冻结。

### AQ-R9-011 — `FIXED`

审计判定成立。`NewObjectRef` 现在把 `creation_parent_ref` 作为 envelope 内必填判别字段，并将它纳入 semantic body、new handle 与 plan digest；validator 只凭 envelope 即可重算。证据见 `docs/design-proposal.md:1600-1636` 与 `docs/security-model.md:261`。parent 在 existing/new/null 间任一变化都会改变 handle 与 plan digest，禁止依赖 planner 隐状态。

### AQ-R9-012 — `FIXED`

审计判定成立。migration graph 现以封闭 `dependency_kind` 覆盖 creation-parent、create-before-use、remove-reference-before-mutation、child-before-parent-delete、generation replacement 与 cascade；所有执行顺序只来自 graph，隐藏依赖和不可执行拓扑前缀都拒绝。证据见 `docs/design-proposal.md:1615,1634-1640` 与 `docs/security-model.md:261`。唯一 Kahn 算法对全部 typed edge 计算 indegree，并以 semantic key bytes 确定 tie-break。

### AQ-R9-013 — `FIXED`

审计判定成立。journal 新增 `cleanup_pending`，在该阶段保留 temp/claim 重验字段与新配置字节；按 fence 幂等 unlink、父目录 fsync、删除同 claim 并写三个 cleanup proof 后，最后一个 DB 事务才标记 `complete`。证据见 `docs/design-proposal.md:1822-1841` 与 `docs/security-model.md:263`。`complete` 禁止残留 attached claim；kill matrix 覆盖进入 cleanup、unlink、fsync、claim/proof commit 与最终 complete 前后。

## 2. 最终机器合同摘要

摘要按 registry 中冻结的 recipe 重算；fixture 使用独立 fixture domain。

| 文档 | raw SHA-256 | canonical SHA-256 |
| --- | --- | --- |
| `operation-contract-v1.json` | `d02e27cd60cee7f33d13223d824f0c3d90af70bb5d872a288cc7318e5ee1cd88` | `d59a0bde52c6dec7fb4a3da9dfe07449373d4c5fa7dc30e1a095034adceb2444` |
| `local-key-purpose-registry-v1.json` | `d2bc244c379d7504e8108b23db12bf7e07d48b6ff27398fe538b9c3358fb179e` | `28bffb5f00e48faf5d571a5f41055a1130752785c28febf000310614a319db15` |
| `lease-policy-v1.json` | `89a5a16ab706fad92393db77f544c8ac684e4298e21cca6e3c7e144176a5a742` | `8e00518663df33a32cce601b447ec375f5bd2f34b136b819a91f58cdc32adaff` |
| `retention-lint-v1.json` | `831cf4880caf8e2008411e8cb5e94e69e81c8d7d4ba40d25b3e686c1e9b81fbc` | `ed4f77b8a57e719a73ab1616c250a80b7bfd93b0dc170e0d1b45b7ddea0c9108` |
| `contract-registry-v1.json` | `67d2b26e9e542fb28157d5d2e906dec00ed87d3ce6c7bf2005a95e824c447b8d` | `834d9592d96d51ab4f3d73d7d6b6367159e6454e4a2ae0202cd6c494c7e22451` |
| `retention-lint-malicious-v1.json` | `4f7bf217e5455b39176b085652b396d4504599a7ff023350111084a52cee9a71` | `de1c33c972f8582b90989cb66653d8f7aec086101af6758c75dae3462be67b59` |

五份 schema 的 raw/canonical 对分别为：registry `41db10c6…ab5b1 / 5f79a09f…23185`、lease `ba7c7a0d…d1e22 / abe90c4a…dfa48`、LocalKey `f56703c7…7ff7 / 9bbb04b3…e516`、operation `46ea0f4d…63229 / 6e3c520f…b8852`、retention `db48722e…327ae / a87c0cbb…132d`；完整 64-hex 值由 `contract-registry-v1.json` 唯一登记。

## 3. 验证与完整性

- `jq -e` 解析所有 artifact、schema 与 fixture；结果全部通过。
- 本地没有预装第三方 `jsonschema` 模块，因此使用两条独立路径：官方 Draft 2020-12 schema 的结构/闭包检查，以及确定性 strict validator 的正反例执行；未把“可解析 JSON”冒充 schema 验证。
- schema 正向验证 5/5；负向验证 32/32 均按预期拒绝；duplicate-key 在 schema validation 前拒绝。
- registry 的 artifact/schema raw 与 canonical digest、schema URI、排序和引用逐项重算匹配；所有语义闭包与 AES golden vector 通过。
- Pandoc exact version/API/extension、三个 locator、rule-driven fixture 和四份 live-input retention scan 全部通过。
- Markdown 相对链接全部存在，代码围栏配对；未发现未完成工作标记或未解析 digest 值。
- `round-01..08` audit/resolution 与本轮 audit 的 raw SHA-256 均与修订前记录一致；没有改写历史审计或处置文件。
- 未读取或调用真实账户、环境凭据、Provider API、动态 key、Token、Cookie 或额度响应；未增加 RPC 权限。
- 仓库仍只有设计/合同材料，没有应用代码、数据库或可执行 runtime，因此以上是规范与离线合同验收，不等价于 unit/integration/e2e 或真实 Provider 测试通过。
- 未执行 git stage、commit 或 push。

## 4. 下一门禁

当前唯一不能由修订 Agent关闭的是 Codex 稳定身份产品基线。用户完成选择后，应由全新的独立 Agent 从零读取现行源，重新执行全量对抗性审计；在此之前本记录不构成 0A 放行声明。
