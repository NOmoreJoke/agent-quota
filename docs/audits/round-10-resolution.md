# Agent Quota 第 10 轮审计处置记录

> 处置版本：v1.6 / 2026-07-18
> 结论：11 项已修复，1 项等待用户决策；仍需新的独立 Agent 全量复审，当前不能宣告零问题或通过阶段 0A。

本轮保持既定安全边界：没有加入 `account/read`，没有读取真实账户，没有移除 Codex，也没有把稳定身份、发行、路径或持久化控制降级。

| 审计项 | 判定与状态 | 机器闭环 | 最终证据位置 | 验证 |
| --- | --- | --- | --- | --- |
| AQ-R10-001 | **BLOCKED_USER_DECISION**。问题有效；两个互斥产品基线不能由修订者代选。 | Codex 继续 `incompatible`，正式 fetch、cache/LKG 写入与 0A 均 fail closed。 | `README.md` 状态；`docs/design-proposal.md` 第 21 节；`docs/provider-contract.md` 第 14 节；`docs/security-model.md` 第 19 节。 | 搜索确认 allowlist 未新增该 RPC；状态仍要求新独立复审。 |
| AQ-R10-002 | **FIXED**。全局模糊排序规则确为当前缺陷。 | 五份 artifact schema 都登记逐 `type=array` pointer 的 `sequence_exact` 默认和 `utf8_key` 精确 override；registry validator 拒绝重复/悬空策略。 | `docs/contracts/schemas/*.schema.json` 的 `/x-aq-array-order`；registry `/semantic_validators/schema-array-order-coverage-v1`。 | 枚举所有 array pointer，确认每个恰有一项策略且无 dangling override；现行 artifact 结构验证通过。 |
| AQ-R10-003 | **FIXED**。ns 值调用 ms operator 的反例有效。 | 新增 `min_int64_ns`；UTC-ms/monotonic-ns 转换改为 typed AST 的 clamped subtraction、ns→ms floor division和 checked add。 | `docs/contracts/lease-policy-v1.json` 的 `/operators`、`/conversion_rule`、`/formula_definitions`。 | 两套 typed-AST 路径推导 11 份 formula 与 conversion；混用 ms/ns 在执行前拒绝。 |
| AQ-R10-004 | **FIXED**。四条 online path 的 reserve 拒绝缺结果行。 | 共享 reserve result contract 映射 budget、ledger、lease、fence、storage 与 transaction reason；四条 path 的拒绝统一为 public OperationError，Provider/Credential/cache 副作用为零。 | `docs/contracts/operation-contract-v1.json` 的 `/rate_reserve_result_contract`、`/error_rows`、`/safe_param_schemas`。 | exact path/stage/error 矩阵闭包与副作用计数检查通过。 |
| AQ-R10-005 | **FIXED**。先返回 identity 再复用 fetch/discovery 的边界不完整。 | 冻结 joint `IdentityAndFetch` / `IdentityAndDiscovery` context-response、request digest、acceptance order与一 reservation/response/read cardinality。 | `docs/contracts/core-safety-contract-v1.json` 的 `/identity_bootstrap`；operation artifact `/identity_bootstrap_contract`。 | digest mismatch、evidence错配与 payload key错配均在 config/cache/LKG 写入前拒绝。 |
| AQ-R10-006 | **FIXED**。InitializeResponse 未进入 schema hash 闭包。 | descriptor roots 精确包含 aggregate v2 schema 与 `v1/InitializeResponse.json`；wire references、missing/changed/unused verdict与 runtime root-only open policy均冻结。 | core-safety artifact `/codex_schema_bundle`。 | 本机 stable generator 验证两个必需 roots；删除/bit flip 改变 verdict/hash，未引用文件不改 hash。 |
| AQ-R10-007 | **FIXED**。LocalKey entry 的 active/state/key-id 语义缺失。 | 冻结 `(purpose,generation)` 主键/排序、每 purpose 一个 active、verify-only allowlist、代际转移、CSPRNG salt用途和 exact `aqk_` recipe；补完整 payload/envelope vector。 | LocalKey artifact `/key_entry_semantics`、`/local_keyring_wire/golden_payload_envelope`；schema `/$defs/keyEntrySemantics`。 | key ID 重算、nonce/AAD/decrypt、salt与目的 bit binding、active cardinality和转移负例检查通过。 |
| AQ-R10-008 | **FIXED**。持久化词典和 runtime allow 的组合绕过有效。 | lexer 增加规范 token classes/边界、sensitive-object signal、exact persist directive 与唯一 owner；retention reject 优先于 runtime allow；补 Unicode/中英混合恶意 fixture。 | retention artifact `/detector_grammar/persistence_signal_lexer`、`/decision_precedence`；fixture `/cases`。 | 18 例 fixture 逐规则得到期望 verdict；合法 transport timeout保持 accept。 |
| AQ-R10-009 | **FIXED**。cascade 与 delete 双向 edge 会构成环。 | cascade 只作为 membership/reason；execution dependency 禁止 cascade，删除仅 child→parent；Kahn min-heap与 prefix invariant冻结。 | core-safety artifact `/migration_graph`；`docs/design-proposal.md` migration envelope。 | parent-child、三层、多兄弟、mixed vectors 无环；反向 cascade edge拒绝。 |
| AQ-R10-010 | **FIXED**。InstallationRegistry exact payload不足以保存回滚状态。 | exact schema 增加完整 current bundle bytes/digest/sequence、按 distribution/publisher 分区 attestation floor、accepted plan sequence/digest；定义原子升级、purge/restore与cross-component rollback。 | core-safety schema `/$defs/installationRegistryPayload`；artifact `/installation_registry`。 | 同 sequence 不同 digest、单组件回滚与跨组件组合 fixture均拒绝。 |
| AQ-R10-011 | **FIXED**。group 与 profile 可携带两份不同预算。 | versioned BudgetPolicy 成为唯一数值源；EndpointBudgetGroup只引用 policy，profile只引用 group；cohort+group union 与 digest recipe冻结。 | core-safety artifact `/budget_policies`、`/endpoint_budget_groups`、`/profile_budget_bindings`、`/budget_ledger_contract`。 | 同 group 多 endpoint/profile 不扩容；冲突 policy 在 Provider/credential 前拒绝。 |
| AQ-R10-012 | **FIXED**。registry 路径 regex 接受 escape/alias。 | artifact/schema/fixture 使用分目录窄 grammar；加载器固定 repo root、逐 segment验证、canonical re-encode byte equal、`openat(O_NOFOLLOW)`与最终 beneath proof。 | registry schema `/$defs/artifactPath|schemaPath|fixturePath`；registry `/path_resolution`；core-safety artifact `/repository_path_contract`。 | absolute、dot、重复 slash、case、percent、Unicode、traversal与symlink vectors全部拒绝，canonical路径接受。 |

## 验证摘要

- JSON 严格解析与 Draft 2020-12/AJV `strict=false`：registry、5 份 artifact、5 份 artifact schema 均通过。
- 注册摘要：5 份 artifact/schema 与 2 份 fixture 的 raw/domain-separated canonical SHA-256 全部重算匹配。
- 语义验证：array-policy coverage、typed lease AST、reserve error matrix、identity digest cardinality、Codex root closure、LocalKey golden decrypt、retention fixture、migration DAG、installation/budget/path fixture均执行。
- 历史完整性：第 1 至 9 轮 audit/resolution 文件未修改；第 10 轮 audit 未修改。
- 仓库仍无应用实现，因此没有可运行的 unit/integration/e2e；本处置只关闭规范与机器合同缺陷。

最终状态是 `11_FIXED_1_BLOCKED_USER_DECISION_NEEDS_NEW_AUDIT`。只有用户作出剩余产品决策并由新的独立 Agent 全量复审后，才可重新评估阶段 0A；不得把本处置解释为零问题结论。
