# FAIL_WITH_4_ISSUES

## 第 16 轮独立全量设计一致性、可实现性与验证完整性 QA 审计

- 审计日期：2026-07-18（Asia/Shanghai）
- 结论：当前设计仍不能通过 Gate 0A，也不能宣告质量审计零问题。
- 问题数：1 个 Blocker、2 个 High、1 个 Medium。其中 1 个必须由用户作产品决定，另外 3 个可直接修复。
- 审计边界：只读检查 README、三份主文档、registry、5 个 artifact、6 个 schema、2 个 fixture artifact、validator、只读 projection verifier、41-case runner、release gate、Node helper、package manifest/lock。除本报告外不修改 live 设计、合同、工具或既有审计历史。
- 数据边界：未联网，未访问真实账户、Provider、凭据、Hermes、飞书或用户业务数据；所有结论仅来自当前仓库字节、本地固定工具和机器合同。
- 证据等级：`E1` 表示当前字节上的直接机器证据或确定性合同矛盾；`E2` 表示静态交叉证明。本轮 4 项均为 `E1`。

## AQ-R16-001 — Codex 稳定账户身份产品决策仍未冻结

- 严重度：Blocker
- 确定性：Certain
- 证据等级：E1
- 分类：`BLOCKED_USER_DECISION`
- 定位：`README.md:3,48,68`；`docs/design-proposal.md:1142,1188,1211,1489,1501,2306,2341`；`docs/provider-contract.md:144-146,162,169,181,191,202-206,451`；`docs/security-model.md:176-178,380-390,417-443`；`docs/contracts/core-safety-contract-v1.json#/identity_bootstrap`。
- 可复核证据：现行 Codex 只登记 `codex-local-rate-limit-v1` budget group，没有能跨刷新、重启、账户切换与登出重登保持正确隔离的 `IdentitySourceContract` / `ProviderIdentityDomain`。业务 RPC allowlist 仍只有握手与 `account/rateLimits/read`，正文同时禁止实现自行加入 `account/read`，也禁止从 rate-limit payload、principal、进程或临时 session 推导稳定账户身份。因此 Codex 必须保持 `incompatible`，不能执行正式 fetch 或持久化 cache/LKG；但它仍是阶段 1B Supported 候选与第二个 MVP Adapter。
- 产品/实现影响：第二个 MVP Adapter 的退出条件无法满足，Gate 0A 不能关闭。若没有稳定账户身份却继续 fetch，account-scoped cache、LKG 与 rate cohort 无法证明隔离；若维持现行 fail closed，则 Codex 不能计入 MVP Supported。
- 确定性验收：
  1. 用户明确选择并确认一个产品方向；本报告不代替用户作决定。
  2. 方向 A：批准一个最小只读稳定身份来源，并冻结 exact method/argv、允许字段、null 语义、source generation、identity domain、最小披露、账户切换/登出重登、超时/错误与 fail-close 向量。
  3. 方向 B：保持现有最小 RPC allowlist，把 Codex 从 MVP Supported/第二 Adapter 退出条件中移出，以已有稳定身份合同的 Adapter 替换；Codex 保持 Experimental/incompatible 且不计入 MVP。
  4. 任一方向都要同步更新机器合同、Provider binding、cache/LKG eligibility、迁移、Gate 0A 与多账户隔离向量，并交给新的独立 Agent 复审。

## AQ-R16-002 — mutation recipe 只固定顶层 executor，未闭合其传递 helper 与实际 locator 结果

- 严重度：High
- 确定性：Certain
- 证据等级：E1
- 分类：机器合同闭包与验证覆盖
- 定位：`docs/contracts/core-safety-contract-v1.json#/validation_mutation_contract/cases/*/mutation_spec`；`docs/contracts/validate-contracts-v1.py:828-856`；`docs/contracts/run-release-gate-v1.py:174-248`；`docs/contracts/run-validation-mutations-v1.py:42-159,162-386,469-640,650-739`。
- 可复核证据：
  1. 每个 case 的 `executor_implementation_sha256` 只覆盖指定顶层函数的源码段。validator 与 gate 的 AST 检查也只重算这些顶层函数段以及两个 literal map。
  2. 多数 executor 依赖未被 case 实现摘要覆盖的共享 helper，例如 `load()`、`save()`、`repin()`、`append_live_probe()`、`subprocess_success()`、`recipe_path_snapshot()`、`synthetic_results()` 与 `observed_failure_class()`。例如 `mutate_schema_const()` 的摘要不包含它调用的 `save()` 与 `repin()` 实现。
  3. machine recipe 登记了 `operation.locator/expected_before/expected_after`，但 validator、runner 与 gate 都没有从 case 临时根独立读取 locator 并逐字节验证 before/after。gate 只重算 source path snapshot；对 `mutated_output_sha256` 仅检查 64 位十六进制形状以及 changed/unchanged 布尔关系，并接受 runner 回报的 failure class。
  4. 因此当前门禁能证明“固定顶层名字返回了预期 verdict”，却不能独立证明登记的 JSON Pointer、文本锚点或文件状态确实发生了指定变化。正常基线的 41 case 全部通过，并不能补上这条实现闭包。
- 产品/实现影响：某个共享 helper 的实现变化可以改变多条 case 的实际输入修改、执行命令、结果分类或摘要计算，而 case 的顶层 executor 摘要仍保持不变。发布证据可能继续显示 exact-contract-match，但命名 guard 的指定 before→after 行为并未被独立证明，回归覆盖会与机器 recipe 分离。
- 确定性验收：
  1. 为每个 executor 固定完整传递实现闭包；可选方案是登记并验证 call-graph 中全部 helper source digest，或由 gate 自己解释独立 recipe，不能只 pin 顶层 wrapper。
  2. gate 必须从隔离 case root 自己读取 locator，验证 canonical RepoPath、exact before、exact after 与预期 filesystem kind；对 JSON Pointer、文本锚点、symlink、runtime/result case 分别使用封闭判别 schema。
  3. `mutated_output_sha256` 与 failure class 要由 gate 从 gate-owned 临时证据重算，不能只检查 runner 回报的形状和相等关系。
  4. 新增 helper-closure 回归：只改变 `save/repin/subprocess_success/observed_failure_class/recipe_path_snapshot` 任一传递 helper、保持顶层 executor 段不变时，validator 或 release gate 必须拒绝；`schema-const` 必须证明 exact pointer 从登记 before 变成登记 after。
  5. 保留现有 executor redirect self-test、41-case ID/顺序/数量与外部 tool identity 要求。

## AQ-R16-003 — persistence owner 没有与唯一保存期限表的 `RET-*` 条目形成机器闭包

- 严重度：High
- 确定性：Certain
- 证据等级：E1
- 分类：设计一致性与 retention 机器合同闭包
- 定位：`docs/security-model.md:205-241`；`docs/contracts/retention-lint-v1.json#/inventory`、`#/locations/retention_table_ttl_cells`、`#/verdicts/unknown_ret_id`；`docs/contracts/validate-contracts-v1.py:1494-1587,1651-1720,1721-1790`。
- 可复核证据：
  1. artifact 明确登记 `unknown_ret_id = reject`，正文也声明 data inventory 的 owner 必须来自同文档唯一保存期限表中的现有 `RET-*` 条目。
  2. `extract_inventory()` 实际只在整份 Pandoc AST 中寻找表头前三列恰为 `surface_id / owner/介质 / 唯一生命周期源` 的表，然后直接把第三列字符串作为 owner。它没有按 artifact 的 heading/table ordinal locator 取表，也没有提取唯一保存期限表的条目 ID 集。
  3. `evaluate_retention_ast()` 只验证 record 的 owner 等于该 inventory 字符串；`validate_retention()` 只验证每个 surface 恰有一个 owner、9 个 live record 覆盖 surface 集。两者均未验证 owner 存在于唯一保存期限表，也未执行 artifact 已声明的 `unknown_ret_id` 判定。
  4. 因而，一个格式合法但在保存期限表中不存在的 `RET-*` owner，只要 inventory 与 record 同时引用它，就满足当前 owner join；该 surface 仍没有可实现的期限起点和到期动作。
- 产品/实现影响：机器 gate 可能接受一个没有生命周期定义的持久化 surface。实现无法确定何时删除、如何清理或由哪个 retention 条目负责，直接破坏 purge、migration temp、subject metadata 与隐私期限的一致实现。
- 确定性验收：
  1. 按 artifact 的 exact heading path、table ordinal 与列 ordinal 解析唯一保存期限表和 data inventory；locator 不唯一、移动、复制或表头相似但位置错误均拒绝。
  2. 生成唯一、格式严格的 retention entry ID 集，并要求每个 inventory owner 逐字节属于该集合；重复、未知、缺失 ID 一律拒绝。
  3. 固定三个现有 surface 的 owner join，并继续要求 9 个 live record 的 `surface + operation + owner` 完整覆盖。
  4. 新增 fixture 与 mutation：不存在的 `RET-*` owner、复制的 inventory 表、错误 heading ordinal、重复 retention ID、inventory/record 同时改成未知 owner，均必须拒绝。
  5. artifact/schema/validator/fixture/正文投影同步更新，43 个现行 retention fixture、38 个 exact live exception 与 9 个合法 record 继续通过。

## AQ-R16-004 — 四份入口文档的当前版本与修订轮次不一致

- 严重度：Medium
- 确定性：Certain
- 证据等级：E1
- 分类：文档状态与审计可追溯性
- 定位：`README.md:3`；`docs/design-proposal.md:3`；`docs/provider-contract.md:3`；`docs/security-model.md:3`；另见 `README.md:68`。
- 可复核证据：README 声明“第 15 轮修订至 v2.1”，并引用 `AQ-R15-001..003`；三份主文档仍声明“v2.0 / 第 14 轮修订”，只引用 `AQ-R14-001..006`。README 第 68 行又把当前 Codex 决策指向更早的 `AQ-R11-002`。同一 checkout 因此同时给出三套“当前”审计身份。
- 产品/实现影响：评审者、实现 Agent 与发布 gate 的人工签字无法从入口状态判断哪一轮是当前设计基线，也容易把已经修复的旧 ID、当前 blocker 与历史记录混为一项。机器合同虽仍可通过，但发布可追溯性不完整。
- 确定性验收：
  1. 四份入口文档统一到同一个设计版本、当前修订轮次、当前 blocker ID 与最近处置状态；历史章节可保留旧 ID，但顶层“当前状态”不能分叉。
  2. 把当前状态改成单一可生成投影或加入 validator 的 exact equality 检查，避免 README 与三主文档再次独立维护。
  3. 新的独立审计确认四份入口状态一致，且本轮新增问题的修复状态可从顶层直接追溯到 audit/resolution。

## 基线与自动验证证据

正常基线全部通过，但正常样本通过不抵消上述机器闭包与产品未决项：

| 检查 | 当前结果 |
| --- | --- |
| `python3 docs/contracts/validate-contracts-v1.py` | 6 个 meta-schema、8 个 schema instance、108 个 array schema object、13 个 semantic validator、36 个 core fixture、43 个 retention fixture、9 个 live persistence record；固定 Node `v24.15.0`、npm `11.12.1`、Pandoc `3.9.0.2`、Ajv `8.17.1`；`source_bytes_unchanged=true`，`status=ok` |
| `python3 docs/contracts/canonicalize-registry-v1.py` | artifact pin projection SHA-256 `da6294910e92027c984b9674def141ef703e1337ca70fbd1f8952e159362ebce`；registry anchor `17a839e52871f3165aacd6c8a1426e1f445dc257d88ba8da46bf4faaca82cf0f`；`projection_status=verified` |
| `python3 docs/contracts/run-validation-mutations-v1.py --root .` | 41 个 exact case；结果 SHA-256 `34e831b5455d21c9836c84a7ebd511c4cece4118a5be5f53cf5a4d8caa6fcf45`；`source_bytes_unchanged=true`，`status=ok` |
| `python3 docs/contracts/run-release-gate-v1.py --root .` | clean install、两次 validator/projection deterministic replay、41-case exact-contract-match 与 executor redirect rejection 均报告通过；release input SHA-256 `514021e50a915c6a87f3c2504f933872600e5bb92cfd532c0c25b875a6245b3f`；`release_authority=audit-evidence-only-not-a-release-authority`；最终 `status=ok` |

validator 当前输入 SHA-256 为 `a15152fb2e96391309b67246648e9c475a89129cb40d725e2dc2f051ee073641`；canonical root identity SHA-256 为 `5a7ed8a03ccdcf9d04e1b2ca9bb4708aea3718c4eb051c3ddebecb70990c6ffc`。这些是当前设计与文档工具的审计证据，不是 core/CLI/Provider 实现、真实 Provider 运行时或生产发布授权。

## 覆盖面复核

本轮复核范围包括：principal/subject/capability 与多账户身份；Adapter manifest、ProbeResult、discovery/fetch context；Codex local-stdio 与 DeepSeek HTTP；cache/LKG/query generation；rate ledger、reservation、并发、deadline 与幂等；operation/stage/error algebra；LocalKeyRing；配置、migration journal 与 purge；lease/fence；retention、privacy 与 data inventory；release/tool trust；offline、Hermes、飞书与 Web 可选集成；registry、schema、fixture、projection、runner 与 clean-install gate。

当前字节上未另行立项的已检查部分包括：strict JSON/NFC/duplicate/float/int64 边界；5 个 artifact pin 与 6 个 schema 的引用闭包；108 个数组顺序对象；ProbeResult 四分支；36 个 core fixture；LocalKey purpose 与 golden vector；lease type/unit/clock-domain；operation path/error row projection；fixed-root/no-follow/immutable input；Node/npm/Pandoc/Ajv 运行时与依赖树摘要。仓库仍只有设计、合同和验证工具，没有应用实现，因此这些结论不等于 unit/integration/e2e 运行证明。

## 历史去重

候选在读取第 1–15 轮历史前已经冻结，随后按根因核对既有 audit/resolution：

- `AQ-R16-001` 是持续的用户决策 blocker，当前仍未关闭，不能由审计 Agent 自行选择。
- `AQ-R16-002` 不是 R15-003 已修复的 executor 重定向问题。当前 literal map、顶层 executor 摘要与 redirect self-test均存在；本轮问题是顶层 executor 之外的传递 helper 和登记 locator/before/after 没有独立闭合。
- `AQ-R16-003` 不是 R15-002 已修复的同 leaf record 边界问题。record 移除后 residual signal 已独立扫描；本轮问题是 record/inventory owner 没有与唯一保存期限表中的实际 `RET-*` ID 集做机器 join。
- `AQ-R16-004` 是第 15 轮修复后入口状态产生的当前版本分叉，不重复既有产品或工具根因。

因此 4 个 ID 对应 4 个当前独立根因，没有把同一项重复计数。

## Source、历史、node_modules、隐私与 Git 完整性

- 审计开始时，26 个 source 文件 manifest 的 SHA-256 为 `3e1746ae243858e7e88035fe02f732ddaf8f936d3e4a53933e9db7a33ffa3823`；范围排除 `.git/`、`docs/audits/` 与 `docs/contracts/node_modules/`。
- 读取历史前，第 1–15 轮 30 个 audit/resolution 文件 manifest 的 SHA-256 为 `a8359833d8a4f34f9b583a44831e4383078758ffe5f743178d6f136088e1588b`。
- `docs/contracts/node_modules/` 共 528 个 regular file，其 manifest SHA-256 为 `bc336bde42109b60ef13ad6284d61bcb99f3a0e0ba1856b82389eb6d3fc4a384`。
- 基线命令前后输出均声明 `source_bytes_unchanged=true`。本轮未联网，未读取真实账户、Provider、凭据或用户数据，未启动 Hermes/飞书集成。
- Git 初始状态为 `No commits yet on main`；仓库文件未跟踪，无 staged change、commit 或 push。
- 完成本报告后的逐文件复核结果见文末最终完整性记录；本轮允许的唯一仓库新增文件是 `docs/audits/round-16-audit.md`。

## 最终完整性记录

- Source manifest：最终仍为 `3e1746ae243858e7e88035fe02f732ddaf8f936d3e4a53933e9db7a33ffa3823`，逐文件与启动值相同。
- 第 1–15 轮受保护历史：最终仍为 `a8359833d8a4f34f9b583a44831e4383078758ffe5f743178d6f136088e1588b`，30 个既有 audit/resolution 逐文件与启动值相同。
- `node_modules` manifest：最终仍为 `bc336bde42109b60ef13ad6284d61bcb99f3a0e0ba1856b82389eb6d3fc4a384`，528 个文件逐文件与启动值相同。
- 唯一文件边界：启动清单之外只新增 `docs/audits/round-16-audit.md`；README、三主文档、contracts、schemas、fixtures、工具、package/lock 与 R1-15 历史均未修改。
- 最终 Git 状态仍为 `No commits yet on main`，没有 staged change、commit 或 push。

## 最终结论

`FAIL_WITH_4_ISSUES`

在 `AQ-R16-002..004` 修复、`AQ-R16-001` 获得用户产品决定，并由新的独立 Agent 再次全量审计得到 `PASS_ZERO_ISSUES` 前，不能宣告设计质量门禁通过。
