# FAIL_WITH_7_ISSUES

## Round 13 — 设计一致性与验证完整性 QA 复核

- 复核日期：2026-07-18（Asia/Shanghai）
- 复核结论：`FAIL_WITH_7_ISSUES`
- 发布判断：当前设计不能进入实现冻结。`AQ-R13-001` 是必须由用户作出的产品决定；另有 6 项可直接修复的规范或验证缺口。
- 复核边界：只读检查当前 README、三份主文档、registry、5 个 contract artifact、6 个 schema、2 个 fixture、canonicalizer、validator、mutation runner、JSON Schema helper、package manifest/lock。没有访问真实账户、真实 provider、凭据或用户数据，也没有联网。
- 定位约定：Markdown 使用行号；JSON 使用稳定 JSON Pointer；Python/JavaScript 使用函数名，并在已固定的关键处补行号。JSON Pointer 比易随格式化移动的行号更精确。

## 基线结果

当前仓库的正常输入全部通过现有工具：

| 检查 | 当前结果 |
|---|---|
| JSON Schema meta/instance | 6 个 meta-schema、8 个 instance，通过 |
| array-order dialect | 90 个 array schema object，通过 |
| semantic validators | 11 个，通过 |
| core fixtures | 25 个，通过 |
| retention fixtures | 26 个，通过 |
| live persistence directives | 9 个，通过 |
| mutation runner | 14 个 case 均得到预期结果；runner 报告 `source_bytes_unchanged=true` |
| projection verifier | `projection_status=verified` |
| validator | `status=ok` |

可复核摘要：

- `input_sha256=2683a3c6b3378adbee31e870971b9a894ffd30efe90e3ee150d565f5e5f3d229`
- `registry_anchor=b5d232b62b5dfcdb3be9791c503d186b893cc887dc9230a85190fb9109ea81d1`
- `artifact_pin_projection_sha256=314e510519f1123364bbf756288b2d159bfc0355887da36318420259d98c61fc`
- 本机工具证据：Python 3.9.6、Node v24.15.0、npm 11.12.1、Pandoc 3.9.0.2、当前实际可解析的 Ajv 8.17.1。

这些通过结果证明“当前正常样本被接受”，但不能覆盖以下 7 个互相独立的产品设计或验证完整性问题。

## AQ-R13-001 — 稳定账户身份产品决策未冻结

- 级别：Blocker
- 确定性：Certain
- 证据等级：L1，当前规范直接证据
- 受影响位置：
  - `docs/design-proposal.md`：Codex stable identity / Gate 0A 段落
  - `docs/provider-contract.md`：Codex `official_cli_zero_binding` 身份边界段落
  - `docs/contracts/core-safety-contract-v1.json#/codex_schema_bundle`
  - `docs/contracts/core-safety-contract-v1.json#/identity_bootstrap`
- 简明证据：当前规范已明确把 Codex 标为 `BLOCKED_USER_DECISION`。现有材料只足以定义预算组和 fail-closed 行为，尚未冻结可跨刷新、重启和多账户场景稳定工作的账户身份来源与域；同时规范正确地没有为此新增账户读取，也没有允许 Codex 进入 fetch/cache/LKG。
- 产品影响：Gate 0A 无法通过，Codex 不能形成可验证的 account-scoped key，也就不能安全进入后续实现冻结。此处不是工程团队可以自行补默认值的问题。
- 修复验收标准：
  1. 用户明确选择并签字确认一个产品方向；本轮不代替用户选择。
  2. 选定方向必须有受支持、可重复验证的稳定账户标识证据和明确 identity domain。
  3. 更新 identity context、Adapter binding、cache/LKG eligibility、迁移与多账户隔离向量。
  4. Gate 0A 对选定方向通过；未选定或证据不足时继续 fail closed。
  5. 在验收完成前，不新增账户读取能力，也不移除 Codex provider。

## AQ-R13-002 — live retention 扫描绕过了规范要求的持久化与 TTL 判定

- 级别：High
- 确定性：Certain
- 证据等级：L1，代码分支与隔离 QA 样本一致
- 受影响位置：
  - `docs/contracts/validate-contracts-v1.py:1231-1275`，`evaluate_retention_ast`
  - `docs/contracts/validate-contracts-v1.py:1259-1262`
  - `docs/contracts/validate-contracts-v1.py:1297-1303`，live 文档调用点
  - `docs/contracts/retention-lint-v1.json#/detector_grammar/decision_precedence`
  - `docs/contracts/retention-lint-v1.json#/detector_grammar/persistence_signal_lexer/signal_without_valid_directive`
  - `docs/contracts/retention-lint-v1.json#/verdicts/new_persistent_surface_without_persist_tag`
- 简明证据：持久化信号和 duration/retention 判定都被 `if not live` 包住；三份真正参与发布的 Markdown 恰好以 `live=True` 调用。隔离样本中，同一段“新增 retention 期限”的 AST 在 `live=True` 时为 `accept`、在 fixture 路径为 `reject`；同一已被 lexer 识别的持久化描述也呈现相同差异。当前 26 个 fixture 因走 `live=False`，无法发现这个分支差异。
- 产品影响：主文档可新增 TTL owner 或持久化表述而没有三段式 `persist:<surface_id>:<operation>` 指令，validator 仍可能输出 `status=ok`。这与 artifact 的 decision precedence 和 verdict 直接矛盾，使 retention inventory 的发布门禁失真。
- 修复验收标准：
  1. live 文档和 fixture 使用同一 persistence/retention 判定核心；若确需例外，必须是显式、可枚举、受 schema 约束的例外。
  2. 在三份 live 文档分别加入“新 TTL owner”和“新持久化 surface 但无指令”的 QA case，均必须被拒绝。
  3. 合法的三段式指令、唯一 inventory owner 和现有 9 个 live directive 继续通过。
  4. mutation runner 新增 live 路径覆盖，不能只验证 fixture 字符串。

## AQ-R13-003 — rate reserve 成功计数与 official CLI 路径定义互相矛盾

- 级别：High
- 确定性：Certain
- 证据等级：L1，当前 machine-readable contract 直接矛盾
- 受影响位置：
  - `docs/contracts/operation-contract-v1.json:432-508`，`discover-official-cli-v1`
  - `docs/contracts/operation-contract-v1.json:651-727`，`doctor-official-cli-v1`
  - `docs/contracts/operation-contract-v1.json:2189-2255`，`rate_reserve_result_contract`
  - `docs/contracts/schemas/operation-contract-v1.schema.json#/$defs/rateReserveResultContract/properties/success_credential_resolution_count`
  - `docs/contracts/validate-contracts-v1.py`，`validate_operation_semantics`
- 简明证据：`rate_reserve_result_contract.provider_path_ids` 明确包含两个 HTTP 路径和两个 `official_cli_zero_binding` 路径，并对所有这些路径把 `success_credential_resolution_count` 固定为 1。但两个 official CLI 路径的 step list 都没有 `credential_resolve`；规范正文也要求这些路径的 Source call 为 0。现有 semantic validator 只校验部分拒绝计数和引用闭包，没有校验这个成功计数与每条路径的 step 闭包。
- 产品影响：两个 conforming implementation 会被迫在“遵守路径步骤”和“遵守成功计数”之间二选一，测试与遥测口径也会分叉。
- 修复验收标准：
  1. 将成功计数改为 path-aware 的总映射，或把 HTTP 与 zero-binding 结果 contract 分开。
  2. schema 对每个 path/mode 的成功计数施加条件约束。
  3. semantic validator 从实际 step list 推导并核对 credential resolution、reservation row 和 provider attempt 数。
  4. 为四个 provider path 各增加一个成功向量；official CLI 仍保持 Source call 为 0。

## AQ-R13-004 — 正文错误矩阵声称由 artifact 生成，但 projection 没有绑定 `error_rows`

- 级别：Medium
- 确定性：Certain
- 证据等级：L1，当前正文与 artifact 对照
- 受影响位置：
  - `docs/design-proposal.md:388-425`，OperationError 错误矩阵及“generated”说明
  - `docs/contracts/operation-contract-v1.json:1295-2030`，完整 `error_rows`
  - `docs/contracts/operation-contract-v1.json:1801-1840`，`rate_ledger_unavailable` rows
  - `docs/contracts/operation-contract-v1.json:1863-1994`，`storage_unavailable` rows
  - `docs/contracts/operation-contract-v1.json:2147-2157`，`projection_contract`
- 简明证据：正文矩阵把自己描述为 machine artifact 的生成结果，但 projection 的 source pointers 只有 `/error_codes`、`/paths`、`/stages`，没有 `/error_rows`。当前正文已经少列 artifact 中的多个 operation/stage 组合：例如 artifact 对 discover、doctor、refresh 同时覆盖 reserve/commit 的 ledger/storage rows，而正文把若干项压缩或遗漏。projection verifier 仍显示 verified，因为它从未绑定该表。
- 产品影响：实现者从正文读取的错误集合与 machine contract 不同；同时“verified projection”会给发布评审造成该表已经被逐字校验的错误印象。
- 修复验收标准：
  1. 将 `/error_rows` 与所需 safe schema 字段纳入 projection source pointers。
  2. 由 artifact 确定性生成整张矩阵，并对 marker 内字节做 exact verification。
  3. 明确展示或确定性聚合每个 code/operation/stage，不得静默丢失组合。
  4. 对任意一个 error row 的增删改必须使 projection 验证失败，重新生成后才恢复通过。

## AQ-R13-005 — lease 类型检查没有完成 clock-domain 与 policy result-type 闭包

- 级别：Medium
- 确定性：High
- 证据等级：L1，semantic validator 代码检查
- 受影响位置：
  - `docs/contracts/validate-contracts-v1.py`，`infer_lease_expression`
  - `docs/contracts/validate-contracts-v1.py`，`validate_lease_semantics`
  - `docs/contracts/lease-policy-v1.json#/clock_domains`
  - `docs/contracts/lease-policy-v1.json#/formula_definitions`
  - `docs/contracts/lease-policy-v1.json#/policies`
  - `docs/contracts/lease-policy-v1.json#/closure_rules`
  - `docs/contracts/schemas/lease-policy-v1.schema.json#/$defs/formulaExpression`
- 简明证据：expression inference 返回的是标量类型，没有把 operand 的 `clock_id` 带入组合判断；policy 校验只确认 formula ID 存在，没有证明 `expiry_formula_id`、`parent_deadline_formula_id` 等引用的结果类型符合字段语义。因此，schema 合法但 clock domain 不一致的表达式，或 policy 把 deadline 字段指向 boolean formula 的情况，不在当前 11 个 semantic gate 的拒绝闭包中。现有 mutation 只覆盖 int64 overflow。
- 产品影响：lease/renew/takeover 的 machine contract 可以在保持 JSON Schema 合法的同时形成不可执行或单位/时钟含义错误的 policy；当前 validator 会把“引用存在”误当成“引用类型正确”。
- 修复验收标准：
  1. expression inference 返回 `{value_type, unit, clock_domain}`，并按 operator contract 同时核对三者。
  2. 每个 policy formula 字段声明并验证 expected result type、unit 与 clock domain。
  3. 增加 boolean-as-expiry、wall-clock/monotonic 混用、非法 conversion 三类 QA case，全部拒绝。
  4. 当前 boundary/renew/takeover/provider deadline 公式继续通过，并保持 signed-int64 边界检查。

## AQ-R13-006 — 发布验证只核对 lock 声明，没有证明实际执行的是被锁定的工具实现

- 级别：Medium
- 确定性：High
- 证据等级：L1，依赖加载路径与基线环境对照
- 受影响位置：
  - `docs/contracts/package.json#/dependencies/ajv`
  - `docs/contracts/package-lock.json#/packages/node_modules~1ajv`
  - `docs/contracts/validate-contracts-v1.py`，`run_ajv`
  - `docs/contracts/validate-json-schema-v1.mjs`，Ajv import
  - `docs/contracts/validate-contracts-v1.py:1286-1289`，Pandoc PATH lookup
- 简明证据：当前 manifest/lock 都指向 Ajv 8.17.1，本机基线也确实解析到 8.17.1；但 validator 的证明链只读取 lock 中的版本字段，然后让 Node 从当前 `node_modules` 解析模块。它没有核对 `package.json` 与 lock 的完整闭包，也没有核对实际加载模块的版本、路径或内容摘要。Node 和 Pandoc 同样通过 PATH/本地解析取得。也就是说，正常环境当前正确，但 `status=ok` 本身不足以证明执行实现与固定依赖声明相同。
- 产品影响：不同机器、陈旧安装目录或工具解析差异可能产生同样的成功摘要，却不是同一套验证实现；这削弱 clean-room 重放和发布证据的可复现性。
- 修复验收标准：
  1. 在发布 gate 中核对 manifest-lock exact parity，并记录实际加载 Ajv 的版本、解析路径和受信摘要。
  2. 固定并证明 Node/Pandoc 的来源与版本；或使用内容寻址的隔离验证环境。
  3. clean-room 安装后两次输出相同 contract 摘要；实际模块或工具版本改变时必须 fail closed。
  4. 把依赖安装/完整性检查和 14 个 mutation case 纳入同一个必须通过的发布 gate，而不是仅作为可选脚本。

## AQ-R13-007 — `status=ok` 与最终 input digest 不是同一个原子输入快照

- 级别：Medium
- 确定性：High
- 证据等级：L1，读取生命周期代码检查
- 受影响位置：
  - `docs/contracts/validate-contracts-v1.py:269-299`，`load_contract_set`
  - `docs/contracts/validate-contracts-v1.py:1332-1342`，`input_digest`
  - `docs/contracts/validate-contracts-v1.py:1345-1405`，`run_all`
  - `docs/contracts/run-validation-mutations-v1.py`，独立 `source_snapshot`/`source_bytes_unchanged`
- 简明证据：contract set 在开始时读入并按内存中的 raw/document 验证；`input_digest` 在所有 gate 结束后重新按路径读取文件。两次读取之间没有 initial/final byte、inode/stat 或 digest equality gate。因此 validator 的结论可能针对第一组字节，而打印的 `input_sha256` 针对稍后的另一组字节。mutation runner 自己有 source snapshot，但默认 `validate` 和 canonicalizer 并不继承该检查。
- 产品影响：并发格式化、编辑器保存或构建步骤写入时，成功状态和证据摘要可能描述不同版本；这使发布记录无法唯一重放。
- 修复验收标准：
  1. validation 与 digest 都基于同一份首次读取的 immutable bytes；或在结束时对所有输入进行强制等值复核。
  2. 文件身份、长度、mtime 与内容任一变化都 fail closed，并明确报告变化路径。
  3. 默认 validator、projection verifier 和发布 gate 都执行 source-unchanged 检查。
  4. 增加“验证期间输入变化”的并发 QA case，必须拒绝；静态输入的摘要保持确定性。

## 覆盖面复核结论

以下部分在当前样本上具备直接且一致的通过证据，未单独立项：

- RepoPath allowlist、逐段 no-follow、regular-file/type/raw-bound 基线，以及现有 path alias/symlink mutation。
- strict JSON 的 duplicate key、float/non-finite、NFC、signed-int64 边界和 90 个 array-order metadata gate。
- 5 个 artifact pin 的 raw/canonical hash、registry anchor、core/operation projection 的当前 marker 验证。
- LocalKey purpose/consumer/surface closure、golden crypto vector、core fixture、migration graph、budget policy、installation registry 的当前合法样本。
- operation path/stage/predicate/error reference 的现有闭包、provider I/O reservation 顺序及 0-byte rejection 基线。
- canonicalizer 当前源码没有直接写文件调用；运行前后 source manifest 无差异。其 trust status 已正确限制为 audit evidence，而不是 release authority。
- 当前三段式 persistence directives 的语法、operation enum、唯一 owner join 和 9 个 live reference 均通过；问题是新信号在 live 分支不被检查，见 `AQ-R13-002`。

现有 14 个 mutation case 都通过预期结果，但没有覆盖 `AQ-R13-002`、`AQ-R13-003` 的成功计数、`AQ-R13-005`、`AQ-R13-006`、`AQ-R13-007`，因此不能作为这些根因已关闭的证据。

## 隐私与数据边界

- 未登录或查询任何真实账户。
- 未请求真实 provider 数据，未触发外部业务调用。
- 未读取、打印或生成凭据、token、账户标识或用户内容。
- 隔离 QA 只使用虚构 Markdown 句子和当前公开 contract 结构。
- 未联网。

## Source unchanged 与历史完整性摘要

- 在运行基线 validator、projection verifier 和 mutation runner 前后，对 `docs/audits/`、`.git/`、`node_modules/` 之外的仓库文件生成了两份 SHA-256 manifest；逐字节 diff 为空。
- 已确认未变的当前源文件集合：`README.md`、三份主文档、registry、5 个 artifact、6 个 schema、2 个 fixture、canonicalizer、validator、mutation runner、JSON Schema helper、`package.json`、`package-lock.json` 和 `.gitignore`。
- mutation runner 独立报告 `source_bytes_unchanged=true`；未产生 `__pycache__`。
- 仓库当前没有 Git commit（`main` 为 no-commit 状态，文件均未跟踪），因此不能用 Git object 充当历史基线。
- 候选问题冻结前没有读取 round-01 至 round-12 的 audit/resolution，避免让旧结论影响当前事实判断。随后收到停止新增检查、立即整理报告的约束，因此本轮没有完成跨轮文本去重，也没有生成历史文件的独立 before/after hash manifest。可以确认本轮没有写入任何历史 audit/resolution，但不能把“未写入”表述成已完成独立 hash 证明。
- 本轮唯一允许并实际新增的仓库文件是 `docs/audits/round-13-audit.md`；没有 stage、commit 或其他文件改动。

## 最终结论

`FAIL_WITH_7_ISSUES`

- 1 个用户产品决策项：`AQ-R13-001`。
- 6 个非身份、可直接修复项：`AQ-R13-002` 至 `AQ-R13-007`。
- 在 7 项全部按验收标准关闭之前，不应把当前 validator 的 `status=ok` 解释为实现冻结或发布就绪。
