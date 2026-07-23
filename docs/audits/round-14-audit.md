# FAIL_WITH_6_ISSUES

## 第 14 轮独立对抗性设计审计

- 审计日期：2026-07-18（Asia/Shanghai）
- 结论：当前设计仍不能进入实现冻结，也不能通过 Gate 0A。
- 问题数：2 个 Blocker、4 个 High。其中 1 个必须由用户作产品决定，另外 5 个是可直接修复的设计/验证缺口。
- 审计边界：只读检查当前 README、三份主文档、registry、5 个 artifact、6 个 schema、2 个 fixture、validator、canonicalizer、mutation runner、release gate、Node helper、package manifest/lock。除本报告外没有修改仓库文件。
- 证据等级：`E1` 表示当前字节上的可重复执行反例或直接机器合同矛盾；`E2` 表示当前正文/代码的静态交叉证明。本报告 6 项均有 E1 证据。

## AQ-R14-001 — Codex 稳定账户身份仍等待用户产品决策

- 严重度：Blocker
- 确定性：Certain
- 证据等级：E1
- 分类：`BLOCKED_USER_DECISION`
- 定位：`README.md:3,46`；`docs/provider-contract.md:191,206`；`docs/security-model.md:417,442`；`docs/contracts/core-safety-contract-v1.json#/codex_schema_bundle`；`docs/contracts/core-safety-contract-v1.json#/identity_bootstrap`
- 可重复证据：当前 Codex 只登记 endpoint budget group，未登记可跨刷新、重启和账户切换稳定工作的 `IdentitySourceContract` / Provider identity domain。现行允许协议也不提供已批准的稳定账户/会话 evidence。因此合同正确地保持 `incompatible`、禁止正式 fetch/cache/LKG，并让 Gate 0A fail closed。
- 影响：Codex 不能形成可验证的 account-scoped cache identity 与 rate cohort；若工程侧自行用 principal、进程、rate-limit payload 或临时 session 代替，会造成跨账户缓存复用或预算拆分。
- 确定性验收：
  1. 用户明确选择并签字确认一个产品方向；本报告不代选。
  2. 选定方向登记封闭、版本化、可重复验证的稳定 identity evidence/source/domain，并覆盖同账户重启、A→B、登出重登、多 principal 同/异账户隔离向量。
  3. 更新 Adapter binding、cache/LKG eligibility、迁移和 Gate 0A；证据不足继续 fail closed。
  4. 在用户决定前不得新增 `account/read`，不得移除 Codex，也不得降低 Gate 0A 或多账户隔离要求。

## AQ-R14-002 — `ProbeResult` 没有字段承载 official-cli probe 产生的 IdentityEvidence

- 严重度：High
- 确定性：Certain
- 证据等级：E1
- 分类：可直接修复；R6 identity DTO 根因的当前回归分支
- 定位：`docs/design-proposal.md:995-998,1094-1101,1120`；`docs/provider-contract.md:197-206`；`docs/contracts/operation-contract-v1.json#/paths/9/steps`
- 可重复证据：
  1. `ProviderAdapter.probe()` 的唯一返回类型是 `ProbeResult`，而该 DTO 只有 `compatibility` 和 `detected_protocol_version` 两个字段。
  2. Provider 合同却要求 Adapter 返回短命 IdentityEvidence，并明确说 `ProbeResult` 包含 identity evidence；设计正文也说 official-cli Adapter 最多返回 `OfficialProtocolIdentityEvidence`。
  3. `doctor-official-cli-v1` 的机器路径在 `probe` Provider I/O 后执行 `identity_derive`，但中间没有其他返回对象或 evidence carrier。
- 影响：即使未来用户解决 AQ-R14-001，official-cli doctor 路径仍无法按唯一 DTO 把 probe 得到的 evidence 交给 core。实现只能丢弃 evidence、越权扩展 DTO，或发明第二个未登记接口。
- 确定性验收：
  1. 为 `ProbeResult` 定义封闭的判别联合：只有允许的 official-cli 成功分支可携带短命 `OfficialProtocolIdentityEvidence`；HTTP/offline/失败分支的字段基数明确。
  2. schema、Adapter protocol、operation path 和三份正文只保留一个规范源，未知/跨 profile/过期 evidence 在 `identity_derive` 前拒绝。
  3. 加入 machine fixture：official-cli success 能把 evidence 唯一传给 core；HTTP/offline/不兼容/恶意额外字段均得到唯一 verdict。
  4. 不得让 Adapter 返回 `AccessIdentity`、cache identity、cohort 或 assurance。

## AQ-R14-003 — retention live detector 接受未标记的普通本地文件凭据持久化

- 严重度：High
- 确定性：Certain
- 证据等级：E1
- 分类：可直接修复；R13-002 修复后的未覆盖词法分支
- 定位：`docs/contracts/retention-lint-v1.json#/detector_grammar/persistence_signal_lexer/media_terms`（文件行 513-529）；`docs/contracts/validate-contracts-v1.py:1412-1441,1480-1483,1528-1534`；`docs/audits/round-13-resolution.md:13`
- 可重复证据：在隔离副本中，分别向 `docs/design-proposal.md`、`docs/provider-contract.md` 和 `docs/security-model.md` 加入一句 `The implementation MUST store API tokens in a local file.`，不加入任何 `persist:<surface_id>:<operation>` 指令；三次 `python3 docs/contracts/validate-contracts-v1.py --quiet` 都返回 0。作为控制组，现有 6 个 `database` 形式的 live mutation 均按预期拒绝。
- 根因：`persistence_signal()` 要求 media term 与写动作/敏感对象同时命中；media allowlist 有 `database/sqlite/registry/journal/wal/temp file`，却没有普通 `file/local file/data file/cache`。所以“store + token + local file”完全不进入 directive/owner 判定。
- 影响：主文档可新增本地文件保存 token/secret/credential 的设计而 release validator 仍输出 `status=ok`，与“任何新持久化 surface 都必须有唯一 inventory owner 与 directive”的门禁承诺矛盾。
- 确定性验收：
  1. 把 detector 改为有版本、可解释、封闭测试的持久化语法；至少覆盖普通文件、local/data/config/cache 文件、目录、keychain/keystore 与等价中文表达，且不依赖单一关键词猜测。
  2. 三份 live 文档各加入上述 `local file` 负向 case，并加入同义改写 corpus；全部必须拒绝。
  3. 合法 9 个 directive、唯一 owner join、26 个 fixture 和确有必要的 digest-bound exception 继续通过。
  4. 任何 detector 词表/规则变化必须同时更新 schema、fixture 与 mutation inventory。

## AQ-R14-004 — release gate 本身可被符号链接换根，成功验证另一个仓库

- 严重度：Blocker
- 确定性：Certain
- 证据等级：E1
- 分类：可直接修复；R13-007 的 release-gate 残余分支
- 定位：`docs/contracts/run-release-gate-v1.py:23-25,28-42,73-83,92-122`；`docs/security-model.md:440-441`；`docs/design-proposal.md:2312-2313`；`docs/audits/round-13-resolution.md:18`
- 可重复证据：
  1. 在隔离目录准备一个原样干净仓库和一个含未标记凭据数据库持久化句子的恶意仓库；恶意仓库正常运行 gate 会以 `retention live scan rejected: README.md` 失败。
  2. 将恶意仓库的 `docs/contracts/run-release-gate-v1.py` 换成指向干净仓库同名脚本的 symlink，再从恶意仓库调用该路径；返回码为 0，输出最终 `status=ok`。
  3. 代码先对 `Path(__file__).resolve()` 求值，再从解析后的脚本位置计算 `ROOT`，且没有对 gate 自身做 `lstat/no-follow`。`source_snapshot()` 也使用会跟随链接的 `rglob/is_file/stat/read_bytes`，没有继承 `RepositoryReader` 的固定根、逐段 no-follow immutable snapshot。
- 影响：release evidence 可以描述另一个 checkout，而不是调用者以为正在审核的 checkout；`source_bytes_unchanged=true` 也只证明了被换根后的仓库。这使发布门禁的根身份与证据绑定失效。
- 确定性验收：
  1. gate 的入口脚本、repository root 和全部编译期输入都由外部可信调用边界显式固定；入口任一 symlink、alias、跨 root 或非 regular file 必须在运行验证逻辑前拒绝。
  2. gate 使用与 validator 同一 `RepositoryReader` 语义读取和复核所有源，包括 gate 自身、runner、package/lock；不得用 `Path.resolve()/rglob()/is_file()/read_bytes()` 代替 no-follow fd 证明。
  3. 输出绑定 canonical root identity 与完整输入摘要；调用 cwd/root 与证据 root 不一致时 fail closed。
  4. 加入 gate-script symlink、root substitution、源文件 symlink、并发替换四类 mutation；所有 case 必须由真正待审仓库的 gate 拒绝。

## AQ-R14-005 — npm pin 只固定两行 launcher，没有固定实际执行的 npm 实现树

- 严重度：High
- 确定性：Certain
- 证据等级：E1
- 分类：可直接修复；R13-006 的运行时证明残余分支
- 定位：`docs/contracts/package.json:16-30`；`docs/contracts/validate-contracts-v1.py:392-412,415-457`；`docs/contracts/run-release-gate-v1.py:85-101`；`docs/audits/round-13-resolution.md:17`
- 可重复证据：本机被固定的 npm launcher 内容只是 shebang 加 `require('../lib/cli.js')(process)`。隔离 QA 复制相同 launcher 字节，因此其 SHA-256 与 `npm_cli_sha256` 完全相同；随后替换相邻 `lib/cli.js`，让伪实现回报精确版本 `11.12.1` 并把 `ci` 委托给真实 npm。把该目录置于 PATH 后，完整 release gate 返回 0 和 `status=ok`。
- 根因：`executable_evidence()` 只 hash `shutil.which("npm")` 实际解析的单个 launcher 文件并探测版本；`package_tree_sha256` 固定的是项目的 Ajv 依赖树，不是 npm 自身的实现闭包。被 launcher `require()` 的 npm `lib/` 没有进入证据。
- 影响：不同或恶意 npm 实现可以生成同样的“exact version + resolved executable SHA”发布证据，并控制 clean install 的实际语义。当前门禁不能证明运行的是声明的 npm 实现。
- 确定性验收：
  1. 选择可证明闭包的运行时策略：内容寻址容器/包、外部签名工具链，或固定 npm package root 的完整 regular-file tree、入口解析和依赖闭包。
  2. 证据必须覆盖 launcher 递归加载的实现文件，而不是只覆盖 shim；任何 `lib/cli.js` 或依赖字节变化必须 fail closed。
  3. 加入“相同 launcher/版本、不同实现树”的 mutation；release gate 必须在执行 `npm ci` 前拒绝。
  4. 继续保持 checkout/runtime 仅为 audit evidence，不能自授生产或 0A release authority。

## AQ-R14-006 — release gate 不校验 mutation case 的完整清单或数量

- 严重度：High
- 确定性：Certain
- 证据等级：E1
- 分类：可直接修复；R13-006 的 suite-closure 残余分支
- 定位：`docs/contracts/run-validation-mutations-v1.py:319-347,350-406`；`docs/contracts/run-release-gate-v1.py:112-119`；`docs/security-model.md:440`；`docs/design-proposal.md:2312`；`docs/audits/round-13-resolution.md:17,27`
- 可重复证据：在隔离副本中把 runner 的 `CASES` 改为空 tuple，保留末尾并发输入变化 case。runner 输出 `mutations=1`、`source_bytes_unchanged=true`、`status=ok`；完整 release gate 仍返回 0 和 `mutation_suite=passed`。
- 根因：release gate 只检查 runner stdout 是否以 `status=ok` 结尾，没有固定 runner 摘要、预期 28 个 case ID/顺序/期望或数量。runner 因而可以自行缩减测试再自行宣告成功。
- 影响：任何 mutation case 被误删、改名、跳过或 runner 逻辑退化时，发布门禁仍可声称“完整 28-case suite”通过；负向闭包不是发布证据的一部分。
- 确定性验收：
  1. 在独立于 runner 的 machine contract 中固定 case ID、顺序、期望 verdict、输入 mutation digest 和总数；release gate 读取并 exact compare。
  2. runner 返回结构化、可 canonical hash 的逐 case 结果，gate 要求集合完全相等，缺失、额外、重复、跳过或 verdict 漂移都失败。
  3. 加入 self-test：删除一个 case、空 `CASES`、伪造尾部 `status=ok`、重复 ID 均必须使 gate 非零退出。
  4. 新增 AQ-R14-003 至 005 的负向样本后同步增加受固定清单约束的 case 数，正文不得再手写过时数量。

## 基线、机械检查与对抗性 QA

当前正常样本全部通过，但正常样本通过不抵消上述反例：

| 检查 | 当前结果 |
| --- | --- |
| `python3 docs/contracts/validate-contracts-v1.py` | 6 个 meta-schema、8 个 schema instance、91 个 array schema object、11 个 semantic validator、25 个 core fixture、26 个 retention fixture、9 个 live directive；`source_bytes_unchanged=true`，`status=ok` |
| `python3 docs/contracts/canonicalize-registry-v1.py` | artifact projection SHA `871c78434970fd745cc0439a796effd4187dc417d30102436e1731bb0d1e3f20`；`projection_status=verified` |
| `python3 docs/contracts/run-validation-mutations-v1.py` | 28 个 case；27 个负向拒绝，fixture-ID diagnostic 正向通过；并发输入变化拒绝；`status=ok` |
| `npm run validate --prefix docs/contracts` | clean install、两次 validator/projection deterministic replay、mutation suite 均报告通过；`release_authority=audit-evidence-only-not-a-release-authority` |
| JSON / Markdown | 全部 contract、schema、fixture 通过 `jq empty`；4 份当前 Markdown 的本地链接与 fence parity 无问题 |

运行时证据：Python 3.9.6、Node v24.15.0、npm 11.12.1、Pandoc 3.9.0.2、Ajv 8.17.1。validator 摘要为 `input_sha256=eab00ae487808b84484fa48ed9361e44c747bda3b9331603f6b4bddc81e8c0a8`，registry anchor 为 `272f3e41da77f0bc8f92cb40e27dc3afd87b49ad04e4632f748d0cb29b34841b`。

对抗性 QA 全部只在临时副本中运行，使用虚构句子、伪 npm 文件树和本地 symlink；没有真实账户、凭据、Provider 请求或业务数据。临时副本没有回写仓库。

## 覆盖面复核

本轮逐项复核了：需求与阶段边界；principal/identity/bootstrap；Adapter DTO 与 Provider I/O；Codex local-stdio 与 DeepSeek HTTP；cache/LKG/query generation；rate ledger、并发、超时与幂等；operation/error algebra；LocalKeyRing、配置迁移、journal/recovery；安装与 release trust；Hermes/飞书/Web 可选集成；retention inventory/directive/lint；schema/fixture/projection/release gates。

当前字节上未另行立项的部分包括：strict JSON/NFC/duplicate/float/int64 边界，5 个 artifact pin 与 6 个 schema 的引用闭包，91 个数组顺序策略，LocalKey purpose closure 与 golden vector，lease policy 签名/clock-domain 当前 mutation，operation path/error row projection，以及现有合法 retention owner/directive join。仓库仍只有设计/合同和验证工具，没有应用实现，因此这些结论是设计与静态验证证据，不是 unit/integration/e2e 或真实 Provider 运行时证明。

## 历史去重

候选问题在读取第 1–13 轮历史前已经冻结；随后按根因核对全部既有 audit/resolution：

- AQ-R14-001 是持续的用户决策 blocker，当前仍未关闭；不是工程修复项。
- AQ-R14-002 与 R6-007 的 identity DTO 所有权根因同族，但当前不是旧文字复述：R6 后禁止 Adapter 返回 AccessIdentity，却留下了“正文要求 evidence、`ProbeResult` 无 evidence 字段”的可执行路径断裂，因此按当前回归证据重新开放。
- AQ-R14-003 是 R13-002 修复后的新残余分支：现有 database 负向 case 已关闭，普通 local-file 介质词法仍漏检。
- AQ-R14-004 是 R13-007 修复后的 gate 入口/根身份残余：validator/canonicalizer 的 `RepositoryReader` 已闭合，但 gate 自身仍先 `resolve()` 并用跟随链接的 Path traversal。
- AQ-R14-005 和 AQ-R14-006 分别是 R13-006 后的工具实现闭包与测试清单闭包；“gate 强制调用脚本”并不等于“固定 npm 实现树”或“固定 28-case 集合”。

因此 6 个 ID 对应 6 个当前可独立复现的根因，没有把同一 current root 重复计数。

## Source、历史与 Git 完整性

- 审计启动时（读取历史前）记录的 source aggregate SHA-256：`6e9f7d74e4ee2dfea96e106fc71f313da7ebb7b534ac47d6bb5e179aafa51586`。范围排除 `.git/`、`docs/audits/` 与 `docs/contracts/node_modules/`。
- 第 1–13 轮 audit/resolution aggregate SHA-256：`8e22d3e9fd55635723a3c33d60cfe2d65a230a76ee54ef6bc93d6389ddbdecae`。
- `node_modules` aggregate SHA-256：`bc336bde42109b60ef13ad6284d61bcb99f3a0e0ba1856b82389eb6d3fc4a384`。
- 关键当前文件 SHA-256：README `5c4d475d22109cf3ac1b9f000a4159b0481ad013ca5e1ee2b833579ebc0246b5`；design `8419e9e92c183f569abdc66b95ad964019a5e6e9c676d250a34eafc828051e0f`；provider `b9422e75faac55021446df061063ab1a048d3dc2307d73cf08afc58bb6ca2ff5`；security `60545d290fa329fa9a6fd37fccec79ff35c725cfb9a8e7729e12165c9bf925e0`；validator `e6483a96abeff156497f59f9d80c796cac5bf0452edd4263e0c378ff0ed51e51`；canonicalizer `33f15afbd12e5ce8e72a8129c72d5813b694c2726314f32ee3ebf578ec5efb55`；release gate `27eb7294a8f1717739582e05c6b73584770594bc53753fe4237efd18870abc20`；mutation runner `9552a2a57cfdce854ef1dc031396ed3797d12c0f331d61eff92ae0b1752dc060`；Node helper `1b591d5db59edb510054c74180f1c01ac53c610f3cfdc362d1e422ec1e55508a`；package `c254076ca80f23614a7161a53a8f34ad73e3e3017116a2d37b5dfc4aa3d26e43`；lock `59401ff5b927eda4e6d2a3ea9328e10bd57e3429661a596368ea2be9484c751d`。
- 正常基线和临时 QA 后，source manifest、历史 aggregate 与 node_modules aggregate 均与审计启动值一致；未产生 `__pycache__`。
- Git 状态仍为 `No commits yet on main`，全部仓库文件未跟踪；无 staged change、commit 或 push。第 1–13 轮历史文件逐字节未变。
- 本轮唯一新增文件是 `docs/audits/round-14-audit.md`。

## 最终结论

`FAIL_WITH_6_ISSUES`

在 AQ-R14-002 至 AQ-R14-006 修复、AQ-R14-001 获得用户决定，并由新的独立 Agent 再次全量审计得到 `PASS_ZERO_ISSUES` 前，不能宣告设计质量门禁通过。
