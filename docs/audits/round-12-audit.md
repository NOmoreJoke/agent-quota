# Agent Quota 第 12 轮独立对抗性设计审计

- 审计日期：2026-07-18（Asia/Shanghai）
- 审计者：独立 Agent `/root/audit_round_12`
- 唯一结论：`FAIL_WITH_6_ISSUES`
- 严重度：Blocker 3 / High 3
- 分类：用户决策 1 / 不改变 Codex 身份基线即可修订 5
- 阶段 0A：不通过

## 1. 结论

现行 v1.7 不能宣告零问题，也不能进入阶段 0A。Codex stable identity 仍是必须由用户选择产品基线的 blocker；本轮没有加入 `account/read`、没有读取真实账户，也没有移除 Codex。

除此之外有 5 项当前可修订问题：canonicalizer 会在没有执行 registry schema、artifact schema、semantic closure、array-order 和 strict fixture runner 的情况下输出 `status=ok`；其读取/写入没有落实 fixed-root、no-follow 和原子边界；canonicalizer 自身没有可信 pin 或实际 VCS 身份；正文 5 个 artifact canonical pin 全部漂移；structured persistence 同时保留新旧两种不兼容 directive，且现行正文仍只使用旧格式。

因此本轮唯一合法 verdict 是：

```text
FAIL_WITH_6_ISSUES
```

## 2. 范围、独立性与证据方法

### 2.1 读取顺序与候选冻结

本轮先完整读取 `audit-verify-explain-grade-5/SKILL.md`，随后从零完整审阅：

- `README.md`；
- `docs/design-proposal.md`、`docs/provider-contract.md`、`docs/security-model.md`；
- `docs/contracts/contract-registry-v1.json` 与 `canonicalize-registry-v1.py`；
- 5 份 artifact、6 份 Draft 2020-12 schema、2 份 fixture。

在读取任何 `round-01..11` audit/resolution 前，候选清单冻结为 6 项：Codex stable identity、canonicalizer 未执行登记门禁、canonicalizer 路径/写边界、canonicalizer 自身信任身份、正文 artifact pins、structured persistence dialect。冻结后才读取历史做去重；没有从历史反向增加候选，也没有因为既往 `FIXED` 声明删除当前仍可复现的问题。

### 2.2 证据等级

- `E1`：现行本地文件、精确行号/JSON pointer、raw/canonical hash。
- `E2`：本轮直接执行的解析、摘要、排序、投影、密码学或只读 canonicalizer 检查。
- `E3`：仅使用现行规范与代码构造的确定性反例或数据流推导。
- `E4`：R01–R11 历史，仅用于去重和核对处置声明。
- `E5`：2026-07-18 读取的上游官方公开协议说明；仅用于 Codex identity 独立核对。

### 2.3 隐私、账户与写入边界

本轮没有读取环境变量、系统凭据、Codex/Hermes 登录材料、真实账户、额度、计划、重置时间、Token、Cookie 或真实 Provider 响应；没有执行真实 Provider HTTP、`account/read`、`account/rateLimits/read` 或其他账户 RPC。上游核对只读取 OpenAI 官方公开文档。

所有本地动态证据只处理仓库公开规范和虚构 golden fixture。`canonicalize-registry-v1.py` 只以默认只读模式运行，未运行 `--write`。除本审计报告外，没有修改产品文件、既往 audit/resolution、fixture、schema 或历史记录。

## 3. 问题清单

### AQ-R12-001 — Codex 仍没有获批准的 stable identity evidence source

- Severity：`Blocker`
- 确定性：高
- 证据等级：`E1/E3/E4/E5`
- 分类：`用户产品决策；本审计不得代选`
- 定位：`README.md:3,43,63`；`docs/design-proposal.md:1110,1156,1179,1457,2274,2286`；`docs/provider-contract.md:144,162,191,202,206,435,443`；`docs/security-model.md:177-178,417,426`；core artifact `/endpoint_budget_groups[group_id=codex-local-rate-limit-v1]` 与 `/profile_budget_bindings[profile_id=codex-official-cli-v1]`。
- 事实：正式 fetch 和持久化 cache/LKG 要求 core 从获批准的稳定账户/会话代际 evidence 派生 `verified_stable` AccessIdentity。现行 Codex 只登记 endpoint budget group，没有对应 `IdentitySourceContract` 或 `ProviderIdentityDomain`，并明确禁止从 rate-limit payload、进程或 principal 推断身份。当前允许的业务 RPC 仍只有 `account/rateLimits/read`。
- 独立上游核对：OpenAI 当前 [app-server 官方文档](https://github.com/openai/codex/blob/main/codex-rs/app-server/README.md)把 `account/rateLimits/read` 描述为额度、月度信用限制、spend-control 和 reset-credit 快照；其示例响应没有稳定账户身份。账户信息是另一个独立的 `account/read` 方法。由此只能得出：现行 allowlist 本身仍不能证明账户切换或登录代际；不能把额度字段猜成 identity。该结论是基于官方字段的推断，不是对真实账户的调用。
- 影响：Codex 必须继续为 `incompatible`，不得正式 fetch、不得持久化 cache/LKG、不得成为 Supported Adapter，阶段 0A 不能通过。
- 修复：由用户在两个互斥产品基线中选择其一，再冻结 source contract：A）明确批准额外只读稳定身份来源及其字段、空值、generation、domain、最小披露和切换语义；B）保持现行最小 allowlist，把 Codex 降级并选择另一个具备稳定身份合同的第二个 MVP Adapter。本报告不擅自加入 `account/read`，也不移除 Codex。
- 验证：决策前 Codex Supported/fetch fixture 必须持续 fail closed。决策后覆盖同账户重启、A→B 切换、登出重登、空账户/空身份字段、非 ChatGPT account、同/异账户多 principal；证明 cache identity 与 budget cohort 都只依赖获批准 evidence，身份原文不进入 TOML、SQLite/WAL/SHM、日志、fixture、投影或审计。
- 历史去重：与 `AQ-R11-002` 及更早轮次的未决 blocker 同源；R11 resolution 仍为 `BLOCKED_USER_DECISION`，本轮独立复核后结论不变。

### AQ-R12-002 — canonicalizer 没有执行登记的验证与 fixture runner，却返回 `status=ok`

- Severity：`Blocker`
- 确定性：高
- 证据等级：`E1/E2/E3/E4`
- 分类：`当前缺陷；身份外可直接修订`
- 定位：registry `docs/contracts/contract-registry-v1.json:61-73,149-215,217-233`；canonicalizer `docs/contracts/canonicalize-registry-v1.py:31-68,95-138,141-189,207-228`；`README.md:70-73`；`docs/design-proposal.md:12,2285-2286`；R11 resolution `docs/audits/round-11-resolution.md:10,25-29`。
- 事实：registry 的 `validation_order` 明确要求 registry schema validate、schema meta-validate、artifact schema validate 和 semantic closure；11 个 semantic validator还要求 90 个 array pointer、core strict fixture、LocalKey、lease、operation、RepoPath 与 retention runner。现行 canonicalizer 实际只做 JSON duplicate-key parse/NFC canonicalization、两个 Markdown projection、两个 fixture hash reference、registry pin 与 design registry anchor 刷新。它没有调用 JSON Schema validator或meta-validator，没有遍历/执行 `semantic_validators`，没有运行两份 fixture，也没有执行 array-order、RepoPath、retention 或 LocalKey closure。
- 机器证据：仓库中唯一 `.py/.js/.ts/.sh` 可执行文件就是 `canonicalize-registry-v1.py`；`core-safety-fixture-runner-v1`、`schema_meta_validate`、`artifact_schema_validate` 等字符串只存在于 registry 数据中，没有实现引用。本轮默认只读运行得到：

  ```text
  registry_anchor=8a4a374bdd04cc08acc8a89cc46bdfbc939cf9f6468ad7e9bc8c94a20fd8a0e1
  status=ok
  ```

  但 `AQ-R12-005/006` 的当前 pin 与 directive 反例仍存在，直接证明这个 `ok` 不代表 registry 所登记的完整门禁通过。
- 影响：结构或语义无效的 schema/artifact/fixture 可以被 `--write` 重新计算并“合法化”；strict loader、CI 与修订者会把 hash 自洽误当成合同正确。R11 resolution 声称 structured persistence、strict fixture runner 与 semantic closure“均执行”，但当前仓库无法复现该门禁。
- 修复：实现一个受信任、可调用的完整 validator（可以与 renderer 分离），严格按 registry `validation_order` 在任何写入前执行 bounds、NFC、schema hash、官方 Draft 2020-12 meta-validation、artifact/fixture schema、全部 semantic validator和fixture runner。`status=ok` 只能在所有门禁实际运行并通过后输出；输出逐 validator 的稳定结果与输入摘要。renderer 不得用重新 pin 掩盖 validation failure。
- 验证：对每个门禁至少一项 mutation：schema const/required、artifact unknown field、90 个 array pointer 的 duplicate/dangling/逆序、core fixture `fixture_id` 改名与 input mutation、RepoPath alias/symlink、LocalKey 缺 purpose、lease `2^63`、operation dangling dependency、旧 persistence directive。每项都必须在写入前非零退出且所有源文件字节不变；正常输入连续两次只读运行结果一致。
- 历史去重：这是 R11 新 canonicalizer 和“machine gate”处置后的实现缺口；R01–R10 不存在该脚本，R11 resolution 的 `FIXED` 不能替代当前可执行证据。

### AQ-R12-003 — canonicalizer 的读取/写入没有落实 fixed-root、no-follow 或原子边界

- Severity：`High`
- 确定性：高
- 证据等级：`E1/E3/E4`
- 分类：`当前缺陷；身份外可直接修订`
- 定位：canonicalizer `docs/contracts/canonicalize-registry-v1.py:2,14-16,31-32,67-68,95-117,121-135,141-187,192-201`；registry `docs/contracts/contract-registry-v1.json:53-59,193-196,231-233`；R11 resolution `docs/audits/round-11-resolution.md:10,18`。
- 事实：脚本以 `Path(__file__).resolve()` 推导 root，以 `ROOT / registry-supplied-path` 打开输入，并用 `read_text/read_bytes/write_text` 直接访问目标。它没有逐 segment 验证 canonical RepoPath，没有从一次打开的 root directory fd 使用 `openat(O_NOFOLLOW)`，没有最终 fd/relative bytes proof，也没有拒绝 symlink。Python 的这些路径 API 会跟随 symlink；绝对 registry path 还会覆盖 `/` 运算左侧的 `ROOT`。写入直接 truncate/replace 文件内容，没有同目录 exclusive temp、fsync、rename、事务清单或崩溃恢复；与模块 docstring 的 “Atomically” 不符。
- 影响：攻击者或异常 checkout 可让脚本读取注册根外 JSON，或让固定写目标/registry/design 通过 symlink 指向仓库外文件；`--write` 可能覆盖非目标数据。进程在多文件写入中崩溃还会留下 projection、artifact、registry 与 design anchor 部分更新的混合 generation，第二次运行未必能区分合法修订与中断恢复。
- 修复：先打开并固定 repository root fd；所有 registry path 先按统一 RepoPath grammar验证，再逐 segment `openat/openat2` no-follow并确认最终 regular fd 与登记 bytes完全相同。输出先全部在内存计算并验证，写到同目录 `O_CREAT|O_EXCL|O_NOFOLLOW` temp，fsync file+directory，再按有版本的事务清单/恢复协议 rename；每次 rename 前后复核目标 identity，拒绝 symlink、hardlink/owner/mode异常和跨 root目标。
- 验证：在隔离临时副本中覆盖 absolute、dot/dot-dot、repeated slash、case/Unicode/percent alias、每一层 symlink、最终目标 symlink、确认后 inode exchange、只读/满盘和每个写点 kill。所有越界/混合状态 fail closed，仓库外 sentinel 字节不变；正常 `--write` 后第二次只读运行零差异。
- 历史去重：R10/R11 为“合同加载器”登记了 RepoPath/no-follow，但 R11 新增 canonicalizer 没有复用它；这是修复工具自身的新边界缺口，不是重报旧 artifact path regex。

### AQ-R12-004 — canonicalizer 自身不在信任锚内，且当前并未实际受版本控制

- Severity：`High`
- 确定性：高
- 证据等级：`E1/E2/E3/E4`
- 分类：`当前缺陷；身份外可直接修订`
- 定位：registry `docs/contracts/contract-registry-v1.json:14-32`；canonicalizer `docs/contracts/canonicalize-registry-v1.py:141-201`；R11 resolution `docs/audits/round-11-resolution.md:10,28`；`README.md:29,37`。
- 事实：registry 的 `/canonicalizer` 只有 `implementation_path`、自由版本字符串、13 个数据输入路径和 registry anchor recipe；没有 canonicalizer raw/canonical digest、签名或受信任 VCS revision，且 `input_paths` 不包含脚本本身。当前脚本 raw SHA-256 是 `08a26814dcc630cde2d2d1f0ec973563eb7a3cdd3cc4947def2cd72889d1f0cd`，但该值没有出现在任何 trust input。更关键的是当前 Git 状态为 `No commits yet on main`，`git rev-parse --verify HEAD` 失败，全部仓库内容均 untracked；R11 resolution 所称“受版本控制”在当前 checkout 没有事实基础。
- 影响：只修改 canonicalizer 代码、不修改登记的 path/version，就能改变 canonical bytes、pin、projection 与 design anchor 的生成结果，而 registry 仍看不到工具身份变化。被替换的工具可以同时改数据与新 anchor，留下自洽但非受信的输出；这破坏 supply-chain bootstrap 和审计可追溯性。
- 修复：建立独立于脚本输出的 bootstrap：至少把 canonicalizer raw digest/版本绑定到受签名或外部固定的 release/VCS identity，并由一个更小的 trusted launcher 在执行前验证。脚本不能自行更新自己的信任 pin；升级必须是显式、可审计、需要旧信任根授权的 generation 变更。仓库首次 commit 后记录/验证具体 commit，不得只写“受版本控制”。
- 验证：修改脚本任意一 bit、替换同 path同 version脚本、symlink脚本或从不同 commit运行都必须在执行其代码前拒绝；只有获授权的新 tool generation 可生成新 pins。两台干净 checkout 对同一受信 commit得到相同 tool identity与输出。
- 历史去重：R11-001 首次新增该脚本并把它称为受版本控制；既往历史没有检查脚本自身 bootstrap。本项不是 `AQ-R12-003` 的文件路径问题，而是“谁有权生成信任摘要”的独立供应链问题。

### AQ-R12-005 — design 登记的五个 artifact canonical pin 全部与当前 registry 不符

- Severity：`Blocker`
- 确定性：高
- 证据等级：`E1/E2/E4`
- 分类：`当前缺陷；身份外可直接修订`
- 定位：`docs/design-proposal.md:12`；registry `docs/contracts/contract-registry-v1.json:81-131`；canonicalizer `docs/contracts/canonicalize-registry-v1.py:192-203`；`README.md:70`；R11 resolution `docs/audits/round-11-resolution.md:10`。
- 事实：design 第 12 行依次登记 core/operation/purpose/lease/retention 五个 canonical digest，但与当前 registry 值逐项比较全部不等：

  | artifact | design pin | registry 当前 canonical pin |
  | --- | --- | --- |
  | core | `9cecb9b3d2627cef30a6c27359732d6f5bfecf9bb67d1258d83d74dc772fec2a` | `67c74fc4ee5f90d90895e5961691ad91c16e71b827b9e427cd80099ed6b58aee` |
  | operation | `8d82c37a8bda7eff235125841091ee183fa4d51cf03a08ea3c5212b1db69c398` | `cd267291dcc55331c87f51336e99242a5a5616cc106d0004f2a63ea83074d096` |
  | purpose | `df0f830bdb06ac4f462c7d467585783b6a2e85f5fd076f33c4f83ae263e538c3` | `3f2a2b8cb11f918c9a7ba11d7e8cb527f94beec7e80ee8d90418b868aa843c0d` |
  | lease | `7c25c2c6072f47b37d922de1cb147eaaa511ebd31fa155935468b5e59f644bc0` | `50d4b8269733315d2d3df8c4b6d79c5b75acf4ac7f69564396c63de7287ad817` |
  | retention | `00718bc7940825e74350c657bc096873d4cf019199e4fa1392fcd6941350859d` | `236c66bf87568010482d047a025637e74d6a94b2e8f785257f0148e8f460b02f` |

  当前 registry anchor `8a4a374b...fd8a0e1` 与 design 相同，说明不是整段文档没有刷新。canonicalizer 的 `update_design_anchor()` 只匹配 registry anchor，完全不检查或生成这五个 artifact pin；所以它仍输出 `status=ok`。
- 影响：README 与 design 声称加载时 artifact 摘要必须等于正文登记值。严格实现按正文必须拒绝全部五份当前 artifact；忽略正文又违反“正文登记摘要相等”的公开加载契约。R11 所称“所有登记摘要逐项匹配”不成立。
- 修复：完成其他修订后，从 registry 的 artifact rows 唯一生成 design pin projection，不再手写五个值；canonicalizer/validator 必须反向解析该 projection并逐项比较，数量、顺序、ID、digest任一漂移都失败。不要只手改当前五个字符串。
- 验证：两套独立实现按登记 recipe重算 5 artifact、6 schema、2 fixture 与 registry，全部等于 registry；design 五项按 artifact ID 精确投影，删除/重排/改变任一 pin 都使只读门禁非零退出。`--write` 后第二次只读运行零差异。
- 历史去重：与 R11-001 同属 pin 完整性类别，但不是旧值重报：R11 修复后当前 registry 自身 pins已自洽，新增缺陷是 canonicalizer 漏掉 design 的五项投影，导致 R11 修改后的五项全部漂移。

### AQ-R12-006 — structured persistence 合同仍同时接受新旧两种 directive，现行正文只使用旧格式

- Severity：`High`
- 确定性：高
- 证据等级：`E1/E2/E3/E4`
- 分类：`当前缺陷；身份外可直接修订`
- 定位：retention artifact `docs/contracts/retention-lint-v1.json:389-406,437-444`，JSON pointers `/detector_grammar/persistence_signal_lexer/directive_rule`、`/detector_grammar/persistence_directive_ast/exact_pattern`、`/detector_grammar/persistent_surface_ast/requires_exact_tag_pattern`；retention schema `docs/contracts/schemas/retention-lint-v1.schema.json:698-720,722-799`；`README.md:73`；`docs/design-proposal.md:1169,1840,1850,1865,2285`；`docs/security-model.md:226,228,263,424`；R11 resolution `docs/audits/round-11-resolution.md:19,27`。
- 事实：同一 machine artifact 给出互斥规则：`persistence_directive_ast.exact_pattern` 要求 `persist:<surface_id>:<operation>`，但 `persistence_signal_lexer.directive_rule` 与 `persistent_surface_ast.requires_exact_tag_pattern` 仍要求/接受只有 surface 的 `persist:<surface_id>`。schema 又把旧 lexer rule固定为 const，同时让旧 `requires_exact_tag_pattern` 只是任意字符串，并把新 exact AST固定为 const。现行 design 有 5 个、security 有 4 个实际 directive，全部是旧 `persist:<surface_id>`；没有任何实际 `persist:<surface_id>:(create|delete|update|write)` directive。README/security 的“新格式已统一”只是声明，不是合规实例。
- 影响：实现 A 按新 AST 拒绝全部 9 个现行 directive；实现 B 按 lexer/persistent-surface AST 接受它们但丢失 create/update/delete/write 意图。两个实现都能声称遵循 machine artifact，live-input retention lint 没有唯一 verdict，新持久化动作也无法与 inventory owner/operation做机器绑定。
- 修复：删除所有旧规则并只保留一个 strict discriminated directive AST；schema 对每个相关字段都引用同一 canonical pattern/operation enum。把 9 个现行 code span迁移为明确 operation，逐项与唯一 inventory owner核对。普通 prose继续不产生 storage 语义，未知 directive/surface/operation一律 fail closed。
- 验证：对四份 live input 执行真实 Pandoc AST runner，所有现行声明按新格式命中且 owner/operation唯一；旧两段式、未知 operation、跨 leaf、重复 owner、无 owner和 prose伪装均拒绝。fixture ID改名不改变 verdict；R11 resolution 所称 structured persistence 必须能由仓库命令复现。
- 历史去重：这是 R11-010 “只保留三段式 strict AST”修订后的内部残留与 live-doc迁移遗漏，不是重报 R10 的自然语言词形问题。

## 4. 本轮直接验证与未另报范围

以下检查在当前文件上得到预期结果，因此没有扩展为额外问题：

- 6 份 schema 共枚举 `7+28+6+6+21+22=90` 个 `type=array` schema object；所有 override pointer 无重复、无 dangling，现行受 `utf8_key` 约束的可执行实例未发现逆序。问题在于 canonicalizer 没有执行门禁，不是 array metadata 当前仍错。
- operation artifact 的 16 条 path、6 条 Provider-I/O path、105 条 error row引用闭合；6 条 Provider path 都满足 machine data-dependency 的 `RequestPlan → reserve → commit → final context → Provider I/O`。doctor/discover 四条登记路径的 reserve-before-credential约束与 exact stage一致；本轮不重报 R11-003/004。
- lease `crash_grace_ms` 当前是 `{type:int64_ms,unit:milliseconds,value:2000}`；schema 上限为 signed int64 max。本轮不重报 R11-006。
- Codex descriptor 当前恰有 aggregate v2 与 `v1/InitializeResponse.json` 两个 roots，wire references与 generated core projection一致。本轮不重报 R11-007。
- LocalKey registry/golden payload当前包含 8 个 purpose且每项恰一 active；本轮使用 fixture虚构材料独立重算 8 个 key ID、nonce与 AES-256-GCM ciphertext/tag均一致。本轮不重报 R11-008。
- registry/core/retention 的当前 RepoPath schema和 artifact登记已统一；本轮发现的是 canonicalizer实现没有使用该边界，而不是 machine RepoPath合同再次变宽。
- generated operation/core marker各唯一，source pointer和 projection digest在现行 artifact/Markdown之间匹配；本轮不重报 R11-012。
- 所有 14 份 JSON 可被 `jq` 严格解析；全部本地 `$ref` 可解析且没有外部悬空引用。本机未安装 `jsonschema`/AJV，因此本轮没有把自写 subset validator冒充完整 Draft 2020-12 meta-validation；这也正是 `AQ-R12-002` 要求仓库提供可复现正式 runner 的原因。
- Pandoc 实际版本为 `3.9.0.2`，与 retention artifact pin一致。
- Adapter identity、cache/LKG generation、concurrency、idempotency、stdio/HTTP数据流、privacy、alerts 与 release gates按现行 machine合同做了静态闭包检查；除本报告 identity/canonicalizer/trust/persistence问题外，没有冻结新的 MVP候选。仓库仍没有应用实现，因此不能把这些静态通过表述为 unit/integration/e2e 运行时通过。

## 5. 可复现证据摘要

### 5.1 关键命令与结果

```text
python3 docs/contracts/canonicalize-registry-v1.py
  registry_anchor=8a4a374bdd04cc08acc8a89cc46bdfbc939cf9f6468ad7e9bc8c94a20fd8a0e1
  status=ok

schema type=array count / override count / dangling / duplicate:
  registry   7 /  6 / 0 / 0
  core      28 / 13 / 0 / 0
  lease      6 /  5 / 0 / 0
  local-key  6 /  6 / 0 / 0
  operation 21 / 19 / 0 / 0
  retention 22 / 14 / 0 / 0
  total     90

live structured directives:
  docs/design-proposal.md  old=5 new=0
  docs/security-model.md   old=4 new=0

git status --short --branch:
  ## No commits yet on main
  ?? .gitignore
  ?? README.md
  ?? docs/

git rev-parse --verify HEAD:
  fatal: Needed a single revision
```

另执行：`jq -e` 解析全部 JSON；本地 `$ref` 解析；artifact/schema/fixture raw 与 domain pin重算；operation path/data-dependency/error引用检查；LocalKey golden decrypt；projection marker/digest检查；`pandoc --version`；`shasum -a 256`。没有运行 `--write`、真实 Provider或账户 RPC。

### 5.2 当前审计输入 raw SHA-256

| 文件 | SHA-256 |
| --- | --- |
| `README.md` | `d9eebe53a67837f5c2a9ccb1af135c5014407c3ec07bbd802feb8d0973f4665c` |
| `docs/design-proposal.md` | `2482c0ad5d331e058c54ea3f92811ca8201ee13c7d4ae9de573487b103d70704` |
| `docs/provider-contract.md` | `9cbcc3954473c8aff3c24c9d05df173963a9ff1c48a6f7290cc0834165317247` |
| `docs/security-model.md` | `26efe74300dedbeed38ea843d818d1d693779addadce9145d64a8f621566042b` |
| `docs/contracts/contract-registry-v1.json` | `9e072e49203940c1bc239696ff99346a1fd46fb9038d4ec4144f80e80b05095d` |
| `docs/contracts/canonicalize-registry-v1.py` | `08a26814dcc630cde2d2d1f0ec973563eb7a3cdd3cc4947def2cd72889d1f0cd` |
| `docs/contracts/core-safety-contract-v1.json` | `82def2b7b13bd7faf3e82dc51351f20113abdad82e044a765fa393c891b7e450` |
| `docs/contracts/lease-policy-v1.json` | `53d9ccac515b5b2454bd9c4eb69bba42c3c324c9833528fe5456ffb0a329b236` |
| `docs/contracts/local-key-purpose-registry-v1.json` | `1a46c58ba2550a9a32af37a5b97b180b3e8e9e171d511e8da42cec4211ce2f6d` |
| `docs/contracts/operation-contract-v1.json` | `1496453c35909727082f433a6971e793799aa9dcf19a7045264963128821f4f3` |
| `docs/contracts/retention-lint-v1.json` | `56b43ee95a2e1231854ecf30017da3d44e97413a6508687c28fdcace791c654c` |
| `docs/contracts/fixtures/core-safety-v1.json` | `cc16f9324c8108d74c7135105b711e78a6edb07de15ea15abfca5c13ce4403f5` |
| `docs/contracts/fixtures/retention-lint-malicious-v1.json` | `db6ed7ba6d4ec84c9ae188fabb7da58a130379a4d25b507408b5ebaf249619ba` |
| `docs/contracts/schemas/contract-registry-v1.schema.json` | `978ec6bce73797ae236d7c179ecf764a35887fe1730e04094dbeafde560c5fb8` |
| `docs/contracts/schemas/core-safety-contract-v1.schema.json` | `445ef7578ce6d74968dd86064eab43f069395887ad647fd3edc57adc390f24c5` |
| `docs/contracts/schemas/lease-policy-v1.schema.json` | `345bf8f67f52f64dd93b0b2a78c45856b2e8e4c74f4e6232589e0094f09db29d` |
| `docs/contracts/schemas/local-key-purpose-registry-v1.schema.json` | `9d9f71c8532c376c0fd7c49c66390e97dd487e4bc05392e99c1ce3666a3e0e0a` |
| `docs/contracts/schemas/operation-contract-v1.schema.json` | `b713c8cc4c784297224a6c2eccd2f65307f99834921ae2c28486f373223f899b` |
| `docs/contracts/schemas/retention-lint-v1.schema.json` | `f623db72e6cbc08e801654b4c68d847626c5b6eda1ef070105d98d75a69c2e0b` |

当前 registry domain-separated canonical anchor 为：

```text
8a4a374bdd04cc08acc8a89cc46bdfbc939cf9f6468ad7e9bc8c94a20fd8a0e1
```

## 6. 历史去重与完整性

- 候选冻结后读取 R01–R11 audit/resolution。`AQ-R12-001` 是明确延续的用户决策 blocker；`AQ-R12-002/003/004` 来自 R11 新 canonicalizer 的验证、文件边界与 bootstrap；`AQ-R12-005` 是 R11 pin修复后遗漏的 design五项投影；`AQ-R12-006` 是 R11 structured directive修复后的内部残留和live-doc迁移遗漏。
- R11 resolution `:10,19,25-28` 分别声称 canonicalizer收敛、structured persistence已统一、semantic fixture已执行和历史完整。当前文件直接否定前三项的可复现性，因此不能按历史状态词把问题去掉。
- 本轮没有修改 R01–R11 audit/resolution。可是当前 repository 没有任何 commit/HEAD，`.gitignore`、README 与整个 `docs/` 都是 untracked；因此无法用 Git object identity证明“既往文件自修订后从未变化”，也无法验证 R11 resolution `:28` 的历史 hash断言。能确认的只有本轮读取时的当前字节和本轮未编辑历史文件，不能把它夸大为 VCS级历史完整性。

## 7. 最终门禁

- Verdict：`FAIL_WITH_6_ISSUES`
- Blocker：3
- High：3
- Codex identity 之外可修订项：5
- 用户决策前 Codex 必须继续 `incompatible`、正式 fetch/cache/LKG/0A fail closed。
- 只有 6 项全部关闭、完整 validator/fixture runner可由仓库命令复现、canonicalizer有安全写边界与可信 tool identity、所有 pins/directives收敛，并由新的独立 Agent 从零复审后，才可重新评估 `PASS_ZERO_ISSUES`。
