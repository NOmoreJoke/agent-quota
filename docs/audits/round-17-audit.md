# FAIL_WITH_8_ISSUES

## 第 17 轮独立全量设计一致性、可实现性与验证完整性 QA 审计

- 审计日期：2026-07-19（Asia/Shanghai）
- 结论：当前设计仍不能通过 Gate 0A，也不能宣告质量审计零问题。
- 问题数：1 个 Blocker、5 个 High、1 个 Medium、1 个 Low。其中 Blocker 必须由用户作产品决定，另外 7 项可直接修复。
- 审计边界：独立读取 README、三份主文档、registry、5 个 artifact、6 个 schema、2 个 fixture artifact、validator、只读 projection verifier、41-case runner、release gate、Node helper、package manifest/lock，以及读取候选冻结后的第 1–16 轮审计历史。除本报告外不修改 live 设计、合同、工具或既有历史。
- 数据边界：未联网，未访问真实账户、Provider、凭据、Hermes、飞书或用户业务数据；负例只在 `/tmp/aq-r17-*` 隔离副本中执行。
- 证据等级：`E1` 表示当前字节上的直接机器证据、可复现负例或确定性合同矛盾。本轮 8 项均为 `E1`。

## AQ-R17-001 — Codex 稳定账户身份产品决策仍未冻结

- 严重度：Blocker
- 确定性：Certain
- 证据等级：E1
- 分类：`BLOCKED_USER_DECISION`
- 定位：`README.md:3-5,48,68`；`docs/design-proposal.md:1142-1215,1489-1505,2341-2345`；`docs/provider-contract.md:144-210,258,451-462`；`docs/security-model.md:176-178,380-390,417-447`；`docs/contracts/core-safety-contract-v1.json#/identity_bootstrap`。
- 可复核证据：Codex 仍只登记 `codex-local-rate-limit-v1` budget group，没有可跨刷新、重启、账户切换及登出重登保持正确隔离的 `IdentitySourceContract` / `ProviderIdentityDomain`。业务 RPC allowlist 仍只有握手与 `account/rateLimits/read`；正文同时禁止实现自行加入 `account/read`，也禁止从 rate-limit payload、principal、进程或临时 session 推导稳定账户身份。因此 Codex 必须保持 `incompatible`，不能执行正式 fetch 或持久化 cache/LKG，但它仍是阶段 1B Supported 候选和第二个 MVP Adapter。
- 产品/实现影响：第二个 MVP Adapter 的退出条件无法满足，Gate 0A 不能关闭。若没有稳定身份却继续 fetch，account-scoped cache、LKG 和 rate cohort 无法证明隔离；若保持现行 fail closed，Codex 又不能计入 MVP Supported。
- 确定性验收：
  1. 用户明确选择一个产品方向；审计或修复 Agent 不代替用户决定。
  2. 方向 A：批准一个最小只读稳定身份来源，并冻结 exact method/argv、允许字段、null 语义、source generation、identity domain、最小披露、账户切换/登出重登、超时/错误及 fail-close 向量。
  3. 方向 B：保持现有最小 RPC allowlist，把 Codex 从 MVP Supported/第二 Adapter 退出条件中移出，以已有稳定身份合同的 Adapter 替换；Codex 保持 Experimental/incompatible 且不计入 MVP。
  4. 任一方向都要同步更新机器合同、Provider binding、cache/LKG eligibility、迁移、Gate 0A 与多账户隔离向量，再交给新的独立 Agent 复审。

## AQ-R17-002 — Python 验证运行时未固定，所谓实现闭包可由三个未登记解释器共同通过

- 严重度：High
- 确定性：Certain
- 证据等级：E1
- 分类：验证运行时与可复现性闭包
- 定位：`docs/contracts/package.json:7-11,16-33`；`docs/contracts/validate-contracts-v1.py:508-550`；`docs/contracts/run-release-gate-v1.py:729-740`；runner 和 gate 中全部 `sys.executable` 调用点。
- 可复核证据：
  1. `aqValidationRuntime` 精确固定 Node、npm、Pandoc、Ajv 及 npm implementation tree，但没有 Python implementation、version、ABI、binary digest、stdlib tree 或受支持 platform/architecture 字段；validator 的 runtime field closure 还明确只允许现有 11 个字段。
  2. validator、projection verifier、mutation runner 与 release gate 的主要语义均由 Python 执行；gate 直接用调用它的 `sys.executable` 重放工具。helper closure 同时把 Python stdlib 调用列为 external target，却宣称 external policy 已固定 runtime tool identity。
  3. 当前 `/usr/bin/python3` 是 Python `3.9.6`，真实二进制为 Xcode Python 3.9，SHA-256 为 `271143990bc83af0fb2404a255038f5faafb96df1584ed7f085e5018c0f33ffb`；同一 full release gate 又分别在 `/opt/homebrew/bin/python3.11`（`3.11.15`）和 `/Users/kyle/.local/bin/python3.12`（`3.12.12`）下返回成功。三个解释器都不在机器 runtime profile 中。
- 产品/实现影响：同一 checkout 的判定取决于宿主选择的 Python parser、stdlib、Unicode/JSON/AST/Path/subprocess 行为，却仍可被标记为固定运行时证据。跨机器重放不能证明执行的是同一验证程序语义，helper source digest 也不能覆盖未固定的解释器实现。
- 确定性验收：
  1. 在机器 runtime profile 中固定 Python implementation、exact version、ABI、resolved executable、binary SHA-256、stdlib/依赖 implementation closure 及受支持 OS/architecture；或改用仓库随附且哈希固定的 hermetic runtime。
  2. 在导入或执行 validator/runner 之前由 gate 独立验证该 runtime，禁止由待验证的 Python 代码自证自身。
  3. clean replay、runtime locator 和外部调用闭包均引用同一 runtime identity；未登记的 3.9/3.11/3.12 必须确定性拒绝。
  4. 增加 exact-version、binary drift、stdlib drift、ABI/platform drift 与 PATH/launcher substitution 负例。

## AQ-R17-003 — offline clean install 依赖宿主 npm cache，发布输入本身不能完成干净安装

- 严重度：High
- 确定性：Certain
- 证据等级：E1
- 分类：依赖供应与离线重放完整性
- 定位：`docs/contracts/package-lock.json`；`docs/contracts/run-release-gate-v1.py:716-728`；`docs/provider-contract.md:461`。
- 可复核证据：gate 把调用者的 `HOME` 原样带入 clean environment，然后在只复制 source snapshot、没有复制任何 npm tarball/cache 的临时仓库中执行 `npm ci --offline`。在全新空 `HOME` 下运行同一 gate 会以 npm `ENOTCACHED` 失败，明确缺少 `require-from-string-2.0.2.tgz`；正常运行成功只是因为当前宿主已有缓存。package-lock 的 registry URL 和 integrity 不能让 `--offline` 自行取得缺失 tarball，且 npm cache 不属于 release input digest 或 registry allowlist。
- 产品/实现影响：`clean_install=verified` 并非由声明的仓库输入独立产生，而是依赖未登记、可变化且不可审计的宿主状态。新机器、清空缓存或不同用户环境无法按同一输入重放 gate，离线供应链边界也无法确认。
- 确定性验收：
  1. 把所需 package tarball 或内容寻址 cache 作为明确、逐文件哈希固定的 release input；或把确定性在线 prefetch 独立定义为有网络策略、来源和完整性验证的前置阶段，不再称其为 offline clean install。
  2. gate 使用独立空 `HOME` 和独立 npm cache，禁止读取调用者 cache；安装前后验证 cache/bundle 文件集及摘要。
  3. 空 HOME、空 cache、额外 cache entry、缺失 tarball、tarball bit drift 和 registry URL drift 均有封闭负例。
  4. `clean_install=verified` 只在所有依赖都来自已登记 release input 时输出。

## AQ-R17-004 — runtime/result-payload locator 的 before/after 摘要不包含实际状态变化

- 严重度：High
- 确定性：Certain
- 证据等级：E1
- 分类：mutation 证据精确性
- 定位：`docs/contracts/core-safety-contract-v1.json#/validation_mutation_contract/cases`；`docs/contracts/run-release-gate-v1.py:328-379,640-669`；`docs/provider-contract.md:461`。
- 可复核证据：
  1. 41 个 case 的 locator 分布为 18 个 `json-pointer`、11 个 `text-anchor`、5 个 `runtime`、4 个 `result-payload`、3 个 `filesystem`。9 个 runtime/result case 的 `expected_before_state_sha256` 与 `expected_after_state_sha256` 全部相等。
  2. gate 的 `locator_state()` 对 runtime/result 只序列化 repo path 的 `kind`、静态 locator 和未变化的 `evidence_descriptor`，没有读取实际 synthetic result payload、resolved executable、source replacement 或任何 transient observation；因此隔离副本执行前后必然得到同一状态。
  3. gate 随后仅重跑 case 并比较 broad success/failure class。只有 `schema-const` 得到 exact resolved value 的专门 before→after 断言。runtime/result case 可以由另一种 malformed payload 或另一种 runtime 变化产生相同 rejection class，而仍满足当前登记摘要。
- 产品/实现影响：R16 新增的 gate-owned evidence 能证明“某个 case 被拒绝”，却不能证明机器 recipe 指定的 runtime/result 字段确实从登记前值变成登记后值。`mutation_locator_and_failure_evidence=gate-owned-exactly-recomputed` 和正文“exact before/after state”的表述超出实际证据。
- 确定性验收：
  1. 为 runtime 与 result-payload 定义 gate-owned typed state serializer；before 必须来自完整合法 payload/实际 runtime observation，after 必须来自执行后的确切字段值与结构。
  2. 每个 case 登记并验证不相等的 canonical before/after state hash，以及必要的 exact field/value assertion；不能只依赖 failure class。
  3. runtime state 至少绑定 resolved executable、binary/tree digest、被替换 source identity 与观测命令；result state 至少绑定完整 case ID 集、顺序、字段和值。
  4. 增加“错误字段变化但同样被拒绝”“不同 malformed payload 产生同一 failure class”“descriptor 不变但 runtime 实体变化”等负例，均必须拒绝 evidence match。

## AQ-R17-005 — consent 谓词没有 false 分支执行语义，合法的反向真值修改仍可通过验证

- 严重度：High
- 确定性：Certain
- 证据等级：E1
- 分类：操作代数可执行性与隐私授权
- 定位：`docs/contracts/operation-contract-v1.json:100-132,1138-1152`；`docs/contracts/schemas/operation-contract-v1.schema.json#/properties/predicate_definitions`；`docs/contracts/validate-contracts-v1.py:1412-1430`；status projection 的 `consent_validate` step。
- 可复核证据：
  1. `consent-required-for-status-projection` 的表达式当前是 `audience == llm_minimal`，输入允许 `feishu_private|llm_minimal|local_detail`，missing input 为 reject；status path 的 `consent_validate` step 引用该谓词。
  2. step schema 只有 `stage/predicate_id/io_class/request_kind`，没有定义 predicate 为 false 时是跳过 stage、拒绝 operation、选择另一条 path，还是产生何种 typed result。正文和机器合同都没有补充这一控制流语义。
  3. validator 只校验 predicate ID/input/allowed-values 的集合与排序，不计算表达式真值，也不对受保护的 audience→verdict 建立 semantic oracle。在隔离副本中把右值从 `llm_minimal` 改成 `feishu_private`、重新固定 artifact/registry/投影摘要后，validator 仍输出全部基线计数和 `status=ok`。
- 产品/实现影响：若 false 表示 reject，`local_detail`/`feishu_private` 的 status 查询会被不必要阻断；若 false 表示 skip，所谓 exact trace 实际包含未登记的条件分支。当前验证器还会接受完全反转 LLM consent 适用对象的结构合法合同，直接影响隐私授权边界。
- 确定性验收：
  1. 为每个 predicate step 冻结 true/false/missing/error 的 exact control-flow 与 typed result；条件跳过必须在 path AST 中显式表示，不能依赖实现约定。
  2. 定义并机器验证三种 audience 的真值表：只有 `llm_minimal` 需要 consent；`local_detail` 与 `feishu_private` 不进入 LLM consent，但仍遵守各自授权边界；missing/unknown 输入 fail closed。
  3. validator 必须解释受限 expression AST，验证所有引用 input 已声明并执行 semantic vectors；projection 从同一真值表生成。
  4. 增加右值反转、运算符替换、false branch 改写、missing/unknown input 和三种 audience 全组合负例。

## AQ-R17-006 — current_design_status 仍有三份机器真值且审计历史未进入验证输入

- 严重度：High
- 确定性：Certain
- 证据等级：E1
- 分类：当前状态单一来源与审计链完整性
- 定位：四份入口文档第 5 行；`docs/contracts/core-safety-contract-v1.json:5422-5430`；`docs/contracts/schemas/core-safety-contract-v1.schema.json:1245-1258`；`docs/contracts/validate-contracts-v1.py:90-116,1563-1577`；`docs/design-proposal.md:1146,1192,1215,1493,1505,2345`；`docs/provider-contract.md:166,195,447,462`；`docs/security-model.md:430,447`。
- 可复核证据：
  1. artifact 保存 R16 current status；schema 又把同一组 `v2.2 / 16 / AQ-R16-001 / round-16-*` 值写成 `const`；validator 第三次把完整字典硬编码后做相等检查。所谓 artifact 单一机器来源实际需要同时修改三份 executable truth。
  2. validator 的 compile-time `ALLOWED_READ_PATHS` 不包含 `docs/audits/*`。release gate 的 clean snapshot 也不复制审计历史；删除、替换或改写 latest audit/resolution 字节不会影响现有 validator/gate，当前状态只验证路径字符串，不验证文件存在、摘要、首行 verdict、resolution status 或 round/ID 一致性。
  3. 四个顶层 marker 当前确实与 artifact 的 R16 值一致，但规范性正文仍把 `AQ-R10-001`、`AQ-R11-002`、`AQ-R14-001` 分别写为“当前/仍未决/唯一用户决策”。同一 blocker 因而有四个 current-style ID，机器状态无法关闭历史引用。
  4. 隔离 retention QA 副本完全不含 `docs/audits` 仍能输出 `status=ok`，证明历史文件不是 gate evidence 的输入。
- 产品/实现影响：一次修订必须人工同步三份机器逻辑和四个文档 marker，容易再次产生“当前轮次一致但验证器自身仍指向旧轮次”的循环。更严重的是，latest audit/resolution 可以缺失或内容不匹配而 gate 继续成功，无法证明本轮修复对应哪份审计结论。
- 确定性验收：
  1. artifact 作为唯一 current-status value source；schema 只验证 shape、enum/pattern 和关系约束，validator 动态读取 artifact，不再硬编码当前轮值。
  2. 建立受保护 history manifest，固定 latest audit/resolution 的 repo path、raw SHA-256、round、issue set、首行 verdict 与 resolution status；gate clean snapshot 必须包含并 no-follow 读取这些输入。
  3. 动态验证 `revision_round`、issue ID、文件名、audit verdict、resolution status、四个 marker 和 gate status 的关系；缺失、替换、旧轮回退或内容不一致均拒绝。
  4. 正文旧 ID 必须明确标为 historical/non-normative，当前未决只引用 status source 的唯一 ID。
  5. 增加“只更新 artifact 即可生成/验证全部投影”的升级测试，以及删除/替换 audit、替换 resolution、伪造首行和旧 ID 回退负例。

## AQ-R17-007 — retention heading path 只绑定层级序号，没有绑定标题文本

- 严重度：Medium
- 确定性：Certain
- 证据等级：E1
- 分类：retention locator 精确性
- 定位：`docs/contracts/retention-lint-v1.json:252-313`；`docs/contracts/schemas/retention-lint-v1.schema.json:351-469`；`docs/contracts/validate-contracts-v1.py:1749-1790,1995-2021`；`docs/security-model.md:205-241`。
- 可复核证据：artifact 的每段 `heading_path` 只保存 `{level,sibling_ordinal}`；Pandoc parser 也只生成和比较该结构 tuple，不读取 heading inline text。隔离副本把 `### 10.1 唯一保存期限表` 改为 `### 10.1 唯一保存期限清单` 后，validator 仍输出 43 个 retention fixture、5 个 structural QA、9 个 live persistence directive 和 `status=ok`。现有 `wrong-heading-ordinal` QA 修改的是 artifact ordinal，不是 source heading text，所以没有覆盖 R16 resolution 声称的“相似标题拒绝”。
- 产品/实现影响：表仍在相同结构位置时可以被重命名为另一语义，机器 gate 却继续把它当成唯一权威保存期限表。未来插入/改名章节时，owner/TTL join 可能绑定到结构同位但语义不同的表。
- 确定性验收：
  1. 每个 heading path segment 同时登记并验证 exact normalized inline text（及需要时 identifier），不只登记 level/ordinal。
  2. exact table ordinal、表头/列 ordinal、retention ID set 与三表 join 继续保持现有约束。
  3. 新增标题改名、同义/相似标题、同位复制、前方插入、跨 heading 移动与重复 exact 标题负例；任一 locator 不唯一或文本不等都拒绝。
  4. 保留当前 43 个 retention fixture、5 类结构 QA、9 个合法 persistence record 及 38 个 live exception 的正向结果。

## AQ-R17-008 — 主文档章节编号重复且 Provider 章节倒序

- 严重度：Low
- 确定性：Certain
- 证据等级：E1
- 分类：文档结构与可引用性
- 定位：`docs/design-proposal.md:2278,2300`；`docs/provider-contract.md:434,442,450,457,464`。
- 可复核证据：设计文档连续出现两个一级 `## 21`（“评审清单”和“第 10 轮规范性闭包”）；Provider 文档依次出现 `## 14`、`## 15`、`## 15.1`、`## 15.2` 后又回到 `## 13`。Pandoc 本地链接检查没有断链，但人工章节号不唯一、也不单调，不能作为稳定评审引用。
- 产品/实现影响：评审、修复说明和实现注释引用“第 21 节”时产生歧义；Provider 第 13 节的倒序会误导规范覆盖顺序，也增加后续生成目录和锚点漂移风险。
- 确定性验收：
  1. 四份入口/主文档的手工章节号在同级内唯一且单调；子节号必须属于正确父节。
  2. 更新受影响的本地锚点和交叉引用，不改变规范语义。
  3. 增加 heading number lint，覆盖同级重复、倒序、缺失父节及文内链接；Pandoc local file/anchor 检查保持零问题。

## 基线与自动验证证据

正常基线全部通过，但正常样本通过不抵消上述产品未决、运行时、离线依赖、语义或 evidence locator 问题：

| 检查 | 当前结果 |
| --- | --- |
| `python3 docs/contracts/validate-contracts-v1.py` | 6 个 meta-schema、8 个 schema instance、117 个 array schema object、13 个 semantic validator、36 个 core fixture、43 个 retention fixture、5 个 retention structural QA、9 个 live persistence directive；Node `v24.15.0`、npm `11.12.1`、Pandoc `3.9.0.2`、Ajv `8.17.1`；input SHA-256 `a330666d1fede655c98bf1bb691d0eb34a3e886abec6ae068d4a1b9ce80adeb6`；`source_bytes_unchanged=true`，`status=ok` |
| `python3 docs/contracts/canonicalize-registry-v1.py` | artifact pin projection SHA-256 `33b72c17feba74eb1dd2c3a9696fde2ebcb1a23ba5b5584f1e5111851288ae74`；registry anchor `e133e5cea49549e4af16ecdeb4f55281083da4f66c117345fea42a69e8b51829`；`projection_status=verified` |
| `python3 docs/contracts/run-validation-mutations-v1.py --root .` | 41 个 exact case；results SHA-256 `1b755074f8c4b05dd11d7d0ec165cb663dc0b48197b000cfcfc18aeed5d30cdb`；`source_bytes_unchanged=true`，`status=ok` |
| `python3 docs/contracts/run-release-gate-v1.py --root .` | clean install、双次 validator/projection replay、41-case exact match、executor redirect、5 个 helper closure self-test 均报告通过；release input SHA-256 `ddd793fe093e236c8f5d2dbceb708b063667746dc502f919bc98140c5f50b768`；`release_authority=audit-evidence-only-not-a-release-authority`；最终 `status=ok` |
| Markdown file/anchor 检查 | 20 个本地 anchor link，0 个缺失文件或缺失 anchor |

canonical root identity SHA-256 为 `5a7ed8a03ccdcf9d04e1b2ca9bb4708aea3718c4eb051c3ddebecb70990c6ffc`。这些只是当前设计、合同和本地工具的审计证据，不是 core/CLI/Provider 应用实现、真实 Provider 运行时或生产发布授权。

## 独立负例证据

| 隔离变体 | 实际结果 | 证明边界 |
| --- | --- | --- |
| 空 `HOME` 执行 release gate | npm `ENOTCACHED`，缺 `require-from-string-2.0.2.tgz` | 正常 offline clean install 依赖宿主 cache |
| 同一 source 分别由 Python 3.9.6、3.11.15、3.12.12 执行 full gate | 三者均成功 | Python runtime identity 未固定 |
| 9 个 runtime/result case 的 locator state 静态复算 | 9 个 before hash 均等于 after hash | 没有证明 transient state 的指定变化 |
| 把 consent equality literal 从 `llm_minimal` 改为 `feishu_private` 并 repin | validator `status=ok` | 未验证隐私谓词真值表或 false branch |
| 把“唯一保存期限表”改成“唯一保存期限清单” | validator `status=ok` | heading locator 未绑定标题文本 |
| 不复制 `docs/audits` 的完整 validator 副本 | validator `status=ok` | audit/resolution 字节不属于验证输入 |

所有变体都只作用于临时副本；没有变更 live source、合同、工具、依赖或既有审计历史。

## 覆盖面复核与排除项

本轮复核 principal/subject/capability 与多账户身份；Adapter manifest、ProbeResult、discovery/fetch context；Codex local-stdio 与 DeepSeek HTTP；cache/LKG/query generation；rate ledger、reservation、并发、deadline 与幂等；operation/stage/predicate/error algebra；LocalKeyRing；配置、migration journal 与 purge；lease/fence；retention、privacy 与 data inventory；release/tool trust；offline、Hermes、飞书与 Web 可选集成；registry、schema、fixture、projection、runner 与 clean-install gate。

已直接确认但未另立项的部分：

- R16 新增的 helper closure 不是空壳：当前 52 个函数、118 条 local call edge、213 个 external target 和 34 个 executor closure 均可重算；只改变 `save/repin/subprocess_success/observed_failure_class/recipe_path_snapshot` 的 5 个 self-test 会被拒绝。
- JSON Pointer、text anchor 和 filesystem locator 会读取 gate-owned 隔离状态；本轮 locator 问题只限于 runtime/result-payload 的静态 descriptor。
- retention 的 owner→`RET-*` membership、inventory/record/TTL 三面 join、9 个 directive 和现有 5 个 structural QA 当前成立；本轮只报告 heading text 未绑定。
- 四份顶层 current-status marker 当前逐字节一致；本轮状态问题是 machine truth 重复、历史字节不入 gate 以及正文旧 ID 仍以 current 语气存在。
- strict JSON/NFC/duplicate/float/int64、5 个 artifact pin、6 个 schema 引用、117 个数组对象、ProbeResult 分支、36 个 core fixture、LocalKey purpose/golden vector、lease type/unit/clock-domain、read-only canonicalizer 和 no-follow root 检查均通过现有基线。
- 仓库仍只有设计、合同与验证工具，没有应用实现；上述通过项不能视为 unit/integration/e2e 或真实 Provider 证明。

## 历史去重

候选根因在读取第 1–16 轮历史前已经冻结，随后逐项核对 audit/resolution：

- Codex 项是持续的用户决定 blocker；没有因轮次推进而虚构关闭。
- Python runtime 未固定不是此前已修复的 Node/npm/Pandoc/Ajv/tool tree 固定；当前新反例是三个未登记 Python 解释器都能形成同样的成功证据。
- npm cache 项不是 package-lock parity 或 npm implementation tree drift；当前新反例是 declared release input 在空 cache 下无法完成其自称的 offline clean install。
- runtime/result locator 项承认 R16 已完成 helper closure、gate-owned case root 和 locator hash；当前新反例只针对这两类 locator 的 before/after state 仍是同一个静态 descriptor。
- predicate 项不是 R9 已修复的 input/expression 缺失。现有表达式和 missing verdict 已存在；当前问题是 false 分支控制流与受保护的 audience 真值表仍未定义、未执行。
- current status 项合并了单一来源、历史字节与旧 current-style ID 三个同根证据，未把同一可追溯性根因重复计数。
- retention 项不重复 R16 已修复的 owner join；现有 join 成立，当前反例只证明 heading path 不含标题文本。
- 章节编号是独立文档结构问题，没有与任何机器合同根因合并或重复计数。

因此 8 个问题对应 8 个当前独立根因。

## Source、历史、node_modules、隐私与 Git 完整性

- 审计开始时，`docs/` 下排除 `docs/audits/` 与 `docs/contracts/node_modules/` 的 24 个 source 文件 manifest SHA-256 为 `febc886b9a3c8c06a428eb7fa1520851ef73a731b830bb835edd1e63d944acca`。
- 读取历史前，第 1–16 轮 32 个 audit/resolution 文件 manifest SHA-256 为 `50c24a0dda123ae2696e2ceb3fced6b9a4af25be447b3b5a0285736fde802aab`。
- `docs/contracts/node_modules/` 共 528 个 regular file，manifest SHA-256 为 `bc336bde42109b60ef13ad6284d61bcb99f3a0e0ba1856b82389eb6d3fc4a384`。
- 本轮未联网，未读取真实账户、Provider、凭据或用户数据，未启动 Hermes/飞书集成。所有 baseline 输出均声明 `source_bytes_unchanged=true`。
- Git 初始状态为 `No commits yet on main`；仓库文件未跟踪，无 staged change、commit 或 push。
- 本轮允许的唯一仓库新增文件是 `docs/audits/round-17-audit.md`；最终逐文件复核见文末记录。

## 最终完整性记录

- Source manifest：最终仍为 `febc886b9a3c8c06a428eb7fa1520851ef73a731b830bb835edd1e63d944acca`，24 个 live source 文件逐文件与启动值相同。
- 第 1–16 轮受保护历史：排除本报告后最终仍为 `50c24a0dda123ae2696e2ceb3fced6b9a4af25be447b3b5a0285736fde802aab`，32 个既有 audit/resolution 文件逐文件与启动值相同。
- `node_modules` manifest：最终仍为 `bc336bde42109b60ef13ad6284d61bcb99f3a0e0ba1856b82389eb6d3fc4a384`，528 个文件逐文件与启动值相同。
- 唯一文件边界：启动清单之外只新增 `docs/audits/round-17-audit.md`；README、三主文档、contracts、schemas、fixtures、工具、package/lock 与 R1–16 历史均未修改。
- 最终 Git 状态仍为 `No commits yet on main`，没有 staged change、commit 或 push。

## 最终结论

在 7 个可直接修复问题关闭、Codex 稳定身份获得用户产品决定，并由新的独立 Agent 再次全量审计得到 `PASS_ZERO_ISSUES` 前，不能宣告设计质量门禁通过。
