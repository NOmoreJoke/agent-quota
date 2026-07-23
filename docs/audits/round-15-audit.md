# FAIL_WITH_3_ISSUES

## 第 15 轮独立对抗性设计审计

- 审计日期：2026-07-18（Asia/Shanghai）
- 结论：当前设计仍不能通过 Gate 0A，也不能宣告质量审计零问题。
- 问题数：1 个 Blocker、2 个 High。其中 1 个必须由用户作产品决定，另外 2 个是可直接修复的验证合同缺口。
- 审计边界：只读检查当前 README、三份主文档、registry、5 个 artifact、6 个 schema、2 个 fixture、validator、canonicalizer、mutation runner、release gate、Node helper、package manifest/lock；执行正常基线与隔离临时副本上的对抗性 QA。除本报告外没有修改仓库文件。
- 证据等级：`E1` 表示当前字节上的可重复执行反例或直接机器合同矛盾；`E2` 表示当前正文/代码的静态交叉证明。本报告 3 项均有 E1 证据。

## AQ-R15-001 — Codex 稳定账户身份仍等待用户产品决策

- 严重度：Blocker
- 确定性：Certain
- 证据等级：E1
- 分类：`BLOCKED_USER_DECISION`
- 定位：`README.md:3,47`；`docs/provider-contract.md:144-146,162,166-170`；`docs/security-model.md:176-178,380-386,417,443`；`docs/contracts/core-safety-contract-v1.json#/identity_bootstrap`；`docs/contracts/core-safety-contract-v1.json#/codex_schema_bundle`
- 可重复证据：当前 Codex 仍只登记 endpoint budget group，没有登记可跨刷新、重启、账户切换与登出重登稳定工作的 `IdentitySourceContract` / `ProviderIdentityDomain`。现行允许业务 RPC 仍只有 `account/rateLimits/read`，设计明确禁止工程自行加入 `account/read` 或从 rate-limit payload、principal、进程或临时 session 推导稳定账户身份。因此 Codex 仍保持 `incompatible`，不能执行正式 fetch、持久 cache/LKG，Gate 0A 对 DeepSeek/Codex verified identity 的检查项仍不能关闭；同时 README 与 Provider 矩阵仍把 Codex 列为阶段 1B Supported 候选。
- 产品/实现影响：第二个 MVP Adapter 的 Supported/GA 退出条件无法满足。若实现侧绕过未决产品选择，会直接破坏 account-scoped cache、LKG 与 rate cohort 隔离；若继续维持 fail closed，则当前 1B 基线与 Gate 0A 无法完成。
- 确定性验收：
  1. 用户明确选择并签字确认一个方向；本报告不代替用户作决定。
  2. 方向 A：批准一个最小只读稳定身份来源（例如经单独批准的 `account/read(refreshToken=false)`），并冻结 exact argv/method、允许字段与 null 语义、source generation、identity domain、最小披露、账户切换/登出重登、超时/错误/fail-close 以及同账户重启与 A→B 隔离向量。
  3. 方向 B：保持现有最小 RPC allowlist，把 Codex 从 MVP Supported/第二 Adapter 退出条件中移除，并以已有稳定身份契约的 Adapter 替换；Codex 保持 Experimental/incompatible，不能计入 MVP。
  4. 任一方向都必须同步更新唯一机器合同、Provider binding、cache/LKG eligibility、迁移与 Gate 0A，并由新的独立 Agent 再审；证据不足继续 fail closed。

## AQ-R15-002 — retention validator 允许同一 leaf 的无关 directive 替新增存储 surface 借壳

- 严重度：High
- 确定性：Certain
- 证据等级：E1
- 分类：可直接修复；R14 local-file 词法修复后的当前残余分支
- 定位：`docs/contracts/validate-contracts-v1.py:1618-1645,1675-1704`；`docs/contracts/retention-lint-v1.json#/detector_grammar/persistence_signal_lexer`；`docs/contracts/retention-lint-v1.json#/detector_grammar/persistence_directive_ast`；`docs/contracts/retention-lint-v1.json#/live_leaf_exceptions`；`docs/security-model.md:424,432,438`
- 可重复证据：
  1. `evaluate_retention_ast()` 先收集一个 Markdown leaf 内全部合法 directive 到 `exact_in_leaf`；当该 leaf 命中 persistence signal 时，只有 `exact_in_leaf` 为空才拒绝。它没有证明 signal 指向哪个 surface，也没有把具体 prose clause 与 `surface_id + operation + owner` 逐项绑定。
  2. 在隔离副本中，仅向已有 ``persist:subject_metadata_observed:update`` 的同一 Markdown 段落追加 `The implementation MUST store API tokens in a local file.`，不增加新 directive、inventory owner 或 exception。直接调用同一 AST decision core 得到 `verdict=accept`；现有 9 条 directive 仍保持 9 条，声明的 26 个 live exception 仍全部恰好被消费。
  3. 对照组中，把同一句放到没有 directive 的新 leaf 会被 R14 新增的 local-file grammar 拒绝。这证明当前反例不是词法未命中，而是同 leaf 的无关 directive 被当成整个 leaf 的通行证。
- 产品/实现影响：主文档可以在一个已登记 surface 的段落中新增 token/secret/credential 本地文件、目录或其他敏感持久化 surface，而 release validator 仍输出 `status=ok`。新增 surface 没有唯一 inventory owner、保存期限、清除动作或审计责任，却被现有无关 surface 的 directive 隐藏，违反“新增 surface 缺少自己的三段式 directive 必须拒绝”的门禁承诺。
- 确定性验收：
  1. 不再以“leaf 内存在任意合法 directive”作为通过条件；每个持久化声明必须在机器可判定的 clause/record 边界绑定自己的 `surface_id + operation + owner`。优先使用结构化声明记录或表格字段，歧义必须 fail closed。
  2. 新增 fixture 与固定 mutation case：在含合法 A surface directive 的同一 leaf 加入未登记 B surface 的 local-file/token 持久化句，必须拒绝；跨句、同句多 surface、中文同义改写和一个 directive 覆盖两个 signal 也必须有唯一 verdict。
  3. 合法 9 条 live directive、38 个 retention fixture、38 个 fixture case 与确有必要的 digest-bound live exception 继续通过；不得通过增加宽泛 exception 关闭反例。
  4. validator、retention artifact/schema、fixture、mutation machine contract 与三份正文的规范性描述必须同步，之后完整 release gate 非零/零退出行为与预期一致。

## AQ-R15-003 — mutation 机器合同只固定标签，没有固定实际执行的 mutation 语义

- 严重度：High
- 确定性：Certain
- 证据等级：E1
- 分类：可直接修复；R14 exact case 集闭包后的当前残余分支
- 定位：`docs/contracts/core-safety-contract-v1.json:353-374` 及 `#/validation_mutation_contract/cases/*/mutation_spec`；`docs/contracts/validate-contracts-v1.py:801-809`；`docs/contracts/run-validation-mutations-v1.py:341-377,469-480,565-595`；`docs/contracts/run-release-gate-v1.py:157-180,242-248`；`README.md:80,92`；`docs/design-proposal.md:2339`
- 可重复证据：
  1. 41 个 `mutation_spec` 只固定类似 `{"kind":"schema-const"}` 的标签。validator 只要求 `mutation_spec.kind == case_id` 并 hash 这个浅对象；真正修改哪个文件、JSON pointer、前后值与预期失败类别全部硬编码在 runner 的函数和 `MUTATORS` 映射中。
  2. 在隔离副本中只把 runner 的映射从 `"schema-const": mutate_schema_const` 改成 `"schema-const": mutate_artifact_unknown`。机器合同、case ID、sequence、expected verdict 与 `mutation_sha256` 均不变；41-case suite 仍通过，完整 release gate 仍输出 `status=ok`。
  3. 变体的 `mutation_results_sha256` 与正常基线完全相同，均为 `983b46d21e0e1c97980c38d5cce44842aa8181f92191dbfe1e6a61c4e50b6f65`。gate 能看见 runner 源摘要变化，因此 release input digest 会变化，但当前未提交 checkout 没有外部 expected tool digest；更关键的是所谓 exact machine suite 的结果证据本身无法区分“schema const 被改坏”与“另一个 artifact 被改坏”。
- 产品/实现影响：case set/count/order/verdict closure 只能证明“runner 对每个标签返回了期望布尔值”，不能证明命名的安全 guard 真正被激活。多个负向 case 可以退化为同一个通用失败 mutation，仍产生完全相同的逐 case 结果与结果摘要，导致回归覆盖被静默掏空。
- 边界说明：这不是绕过生产外部 tool pin 的结论。当前正文正确地把 checkout 内 gate 标为 `audit-evidence-only`，生产/0A 仍要求外部签名 release 或 VCS commit + tool raw SHA-256 + 既有受信根。问题在于 machine mutation contract 自身所宣称的“exact mutation suite”没有独立绑定 mutation 语义。
- 确定性验收：
  1. 每个 case 的机器合同登记可独立解释的可执行 mutation recipe：至少包含 canonical RepoPath、结构化操作/JSON pointer、expected before/after 或预期 mutated framed digest、预期 validator/failure class；若选择固定 executor，则必须由 runner 之外的先前信任直接固定每个 executor recipe 与实现摘要。
  2. runner 对每个 case 输出实际应用的 source/input digest、mutated output digest 与观察到的 failure class；release gate 从独立合同重新推导并 exact compare，不能只接受 runner 回显的标签和布尔 verdict。
  3. 加入 self-test：把 `schema-const` executor 重定向到 `artifact-unknown` 时，即使两者都是 expected failure，也必须使 mutation suite 或 release gate 非零退出。
  4. 保留当前 case set/count/order/result digest closure 与外部 tool identity 要求；新增字段、schema、validator、runner、gate 与正文投影必须形成同一闭包。

## 基线、机械检查与对抗性 QA

当前正常样本全部通过，但正常样本通过不抵消上述反例：

| 检查 | 当前结果 |
| --- | --- |
| Python syntax + `python3 docs/contracts/validate-contracts-v1.py` | 6 个 meta-schema、8 个 schema instance、106 个 array schema object、13 个 semantic validator、36 个 core fixture、38 个 retention fixture、9 个 live directive；`source_bytes_unchanged=true`，`status=ok` |
| `python3 docs/contracts/canonicalize-registry-v1.py` | artifact pin projection SHA `ad336a27005d6a7585fa7a11431e43dd4c4be7b89e6f5130c640ea171a233dd4`；`projection_status=verified` |
| `python3 docs/contracts/run-validation-mutations-v1.py --root .` | 41 个 exact case；39 个负向拒绝，2 个约定正向通过；`results_sha256=983b46d21e0e1c97980c38d5cce44842aa8181f92191dbfe1e6a61c4e50b6f65`；`status=ok` |
| `python3 docs/contracts/run-release-gate-v1.py --root .` | clean install、两次 validator/projection deterministic replay、41-case suite 均通过；`release_input_sha256=a0e5ef5664a15b03352202d6bbea0e1e7b677bfb1ad96e0ac28fbf76a4d8b559`；`release_authority=audit-evidence-only-not-a-release-authority` |
| JSON / Markdown | 全部 contract JSON 通过 `jq empty`；4 份当前 Markdown 的本地链接无缺失，fence parity 正常；未发现占位标记 |

运行时证据：Node v24.15.0、npm 11.12.1、Pandoc 3.9.0.2、Ajv 8.17.1。validator 摘要为 `input_sha256=e0876bf877ed861d711b95947f4dc830adfd6492e5e0529f656c15159e702e9b`，registry anchor 为 `e24781e18140944cc31a84baa408f201639c83e6e8d536671195fab1e480725e`；release gate canonical root identity SHA-256 为 `5a7ed8a03ccdcf9d04e1b2ca9bb4708aea3718c4eb051c3ddebecb70990c6ffc`。

两项新反例全部只在 `/tmp` 的隔离副本或内存 AST 上运行，使用虚构英文句子和本地工具源码映射，不使用真实账户、凭据、Provider 请求、网络、Hermes、飞书或业务数据；临时副本没有回写仓库。

## 覆盖面复核

本轮逐项复核了：需求与阶段边界；principal/identity/bootstrap；Adapter DTO 与 Provider I/O；Codex local-stdio 与 DeepSeek HTTP；cache/LKG/query generation；rate ledger、并发、超时与幂等；operation/error algebra；LocalKeyRing、配置迁移、journal/recovery；安装与 release trust；Hermes/飞书/Web 可选集成；retention inventory/directive/lint；schema/fixture/projection/release gates；完整 mutation machine contract 与 runner/gate 闭包。

当前字节上未另行立项的部分包括：strict JSON/NFC/duplicate/float/int64 边界，5 个 artifact pin 与 6 个 schema 的引用闭包，106 个数组顺序策略，ProbeResult 四分支与 11 个 probe fixture，LocalKey purpose closure 与 golden vector，lease policy 签名/clock-domain、operation path/error row projection、npm 实现树 pin、入口/root/source/concurrent no-follow 反例，以及现有合法 retention owner/directive 集合。仓库仍只有设计、合同和验证工具，没有应用实现；这些结论是设计与静态验证证据，不是 unit/integration/e2e 或真实 Provider 运行时证明。

## 历史去重

候选问题在读取第 1–14 轮历史前已经冻结；随后按根因核对全部既有 audit/resolution：

- AQ-R15-001 是持续的用户决策 blocker，当前仍未关闭；不是可由审计 Agent 自行选择的工程修复项。
- AQ-R15-002 不是 R14-003 的旧词法问题。R14 已让普通 `local file` 在无 directive 的 leaf 中被拒绝；当前反例保留新词法并利用同 leaf 的无关合法 directive 隐藏另一个 storage surface，是修复后的独立残余。
- AQ-R15-003 不是 R14-006 的旧 case-count 问题。R14 已固定 case ID、集合、数量、顺序、expected verdict 和 results digest；当前反例完整保留这些闭包，只替换标签背后的实际 executor 语义，结果摘要仍完全相同。
- R13 的 live/fixture bypass、release gate 根替换、npm 实现树闭包等既有问题均已按当前字节复核，没有重复计入本轮。

因此 3 个 ID 对应 3 个当前可独立复现的根因，没有把同一 current root 重复计数。

## Source、历史、隐私与 Git 完整性

- 审计启动时（读取历史前）记录的 source aggregate SHA-256：`d463e8e99e415f8c45e1f6baa420dd25b238cebe3fad89a4e235d99325a091da`。范围为 26 个当前 source 文件，排除 `.git/`、`docs/audits/` 与 `docs/contracts/node_modules/`。
- 第 1–14 轮 28 个 audit/resolution 文件 aggregate SHA-256：`766ccadaa144d95bafdc94980fd0c83c1c9e80a96d81b3a6832908031aada64c`。
- `node_modules` 528 个文件 aggregate SHA-256：`bc336bde42109b60ef13ad6284d61bcb99f3a0e0ba1856b82389eb6d3fc4a384`。
- 审计启动时 54 个非 `node_modules` 文件的完整 manifest aggregate SHA-256：`18eeaa38fa5a1b4648db074a6dbb637e338a2e2f182358a8e7808dda577f3e5d`。
- 关键当前文件 SHA-256：README `43997f1e3c5af4031405357379c241ce3b080d0f1d876a022b2d7740cab19170`；design `e2ad7aa0bd78ca2a495e3975ade7da0711217d41d1e483f966b18fdeaa531dbf`；provider `dc2d906f33e450b2768c4e41c455ffca1f3f217577c151619f461f848769130f`；security `5a8d803d1c9f5ecbeee3466cdfb792507a3ca9126032e2d4c2ec8c694b42a1f7`；validator `3ffbf0a2c1c7f7af31c0a76f7a26d573876e401fc255abde4b924de9fa4a7f92`；canonicalizer `33f15afbd12e5ce8e72a8129c72d5813b694c2726314f32ee3ebf578ec5efb55`；release gate `46c549c772ad666dfe53bbc0dde91c5d4f980d36fe86fe036094ed560d4815c7`；mutation runner `cbabcf87e2c858dff0d6d068c35b2e83f991ad06517da217d78d8bbd5ae63d5b`；package `b518e76361980eb0f981b08771dfba8ead265fb0787f3b7726964cbe3a9195fe`；lock `59401ff5b927eda4e6d2a3ea9328e10bd57e3429661a596368ea2be9484c751d`。
- 基线与临时 QA 后，source manifest、第 1–14 轮历史 manifest 与 node_modules manifest 均逐字节等于启动值；未产生仓库内 `__pycache__`。本轮没有访问网络、真实 Provider、凭据、账户、Hermes、飞书或任何用户业务内容。
- Git 状态仍为 `No commits yet on main`，仓库文件未跟踪；无 staged change、commit 或 push。第 1–14 轮历史文件逐字节未变。
- 本轮唯一新增文件是 `docs/audits/round-15-audit.md`。

## 最终结论

`FAIL_WITH_3_ISSUES`

在 AQ-R15-002 与 AQ-R15-003 修复、AQ-R15-001 获得用户决定，并由新的独立 Agent 再次全量审计得到 `PASS_ZERO_ISSUES` 前，不能宣告设计质量门禁通过。
