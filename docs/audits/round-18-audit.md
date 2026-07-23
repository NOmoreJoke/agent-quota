# FAIL_WITH_4_ISSUES

## 第 18 轮独立全量设计一致性、可实现性与验证完整性 QA 审计

- 审计日期：2026-07-19（Asia/Shanghai）
- 结论：当前设计仍不能通过 Gate 0A，也不能宣告质量审计零问题。
- 问题数：1 个 Blocker、3 个 High。Blocker 必须由用户作产品决定；另外 3 项可直接修复。
- 审计边界：独立读取 README、三份主文档、registry、5 个 artifact、6 个 schema、2 个 fixture artifact、history manifest、runtime bootstrap/guard、离线 npm bundle、validator、只读 projection verifier、41-case runner、release gate、Node helper、package manifest/lock。候选冻结后才读取第 1–17 轮审计历史做去重。除本报告外不修改 live 设计、合同、schema、fixture、工具、依赖、bundle 或既有历史。
- 数据边界：未联网，未访问真实账户、Provider、凭据、Hermes、飞书或用户业务数据；定向负例只使用当前固定运行时和 `/tmp/aq-r18-*` 隔离副本。
- 证据等级：`E1` 表示当前字节上的直接机器证据、可复现负例或确定性合同矛盾。本轮 4 项均为 `E1`。

## AQ-R18-001 — Codex 稳定账户身份产品决策仍未冻结

- 严重度：Blocker
- 确定性：Certain
- 证据等级：E1
- 分类：`BLOCKED_USER_DECISION`
- 精确定位：`README.md:55,75`；`docs/design-proposal.md:1192,1215,1493,1505,2171,2345,2354`；`docs/provider-contract.md:148-150,166,195,201-210,460,468,476,490`；`docs/security-model.md:181-182,421,430,438,446-448`；`docs/contracts/core-safety-contract-v1.json:5640-5648`。
- 可复核证据：Codex 当前只登记 `codex-local-rate-limit-v1` budget group，没有经批准的 `IdentitySourceContract` / `ProviderIdentityDomain` 来证明跨刷新、重启、账户切换及登出重登后的稳定上游主体。合同禁止实现自行加入 `account/read`，也禁止从 rate-limit payload、principal、进程或临时 session 猜测身份；因此正式 fetch、持久 cache/LKG 和 Supported 状态继续 fail closed。与此同时，Codex 仍是阶段 1B 的第二个 MVP Adapter 候选，当前 source 明确把选择权留给用户。
- 影响：保持现状时 Codex 不能满足第二个 Supported Adapter 的退出条件；放松身份要求时又无法证明多账户 cache/LKG/rate-cohort 隔离。Gate 0A 没有可由 Agent 唯一推出的关闭路径。
- 确定性验收：
  1. 用户明确选择产品方向；审计或修复 Agent 不代替用户决定。
  2. 方向 A：批准最小只读稳定身份来源，冻结 exact method/argv、允许字段、null/缺失语义、source generation、identity domain、最小披露、切换/登出重登、超时/错误和 fail-close 向量。
  3. 方向 B：保持现有最小 RPC allowlist，把 Codex 从 MVP Supported/第二 Adapter 退出条件中移出，并以已有稳定身份合同的 Adapter 替换；Codex 保持 Experimental/incompatible 且不计入 MVP。
  4. 任一方向均同步更新机器合同、Provider binding、cache/LKG eligibility、迁移、Gate 0A 和多账户隔离向量，再由新的独立 Agent 全量复审。

## AQ-R18-002 — bootstrap 的实际启动链未与其声明的 shell、entry 和外部证明形成闭包

- 严重度：High
- 确定性：Certain
- 证据等级：E1
- 分类：验证运行时与可复现启动边界
- 精确定位：`docs/contracts/runtime-bootstrap-v1.sh:10-14,36-74`；`docs/contracts/python_runtime_guard_v1.py:70-72`；`docs/contracts/package.json:7-11,20-40`；`docs/contracts/validate-contracts-v1.py:585-618`；`docs/contracts/run-release-gate-v1.py:923-944,1068-1093`；`docs/design-proposal.md:2349`；`docs/security-model.md:445`。
- 可复核证据：
  1. Python 二次 guard 只以环境变量 `AQ_RUNTIME_BOOTSTRAP_V1=verified` 判断是否经过外部 bootstrap。直接用已登记 CPython 设置该变量并调用 `verify_runtime(require_external_bootstrap=True)`，实际输出 `direct_python_guard=accepted`、退出码 0；环境值不是外部启动证明。
  2. bootstrap 固定并哈希的是 `/bin/sh`，却不检查当前实际解释脚本的 shell。`/bin/bash docs/contracts/runtime-bootstrap-v1.sh docs/contracts/python_runtime_guard_v1.py` 实际输出 `alternate_shell_bootstrap=accepted`、退出码 0；此时被哈希的 `/bin/sh` 不是执行脚本的解释器。
  3. entry 校验只匹配 `docs/contracts/*.py`，不是登记的 exact tool set。在隔离副本把 helper 复制为 `docs/contracts/unregistered-tool.py` 后，`/bin/sh .../runtime-bootstrap-v1.sh .../unregistered-tool.py` 实际输出 `unregistered_python_entry=accepted`、退出码 0。
  4. bootstrap raw digest 由已经启动的 Python validator 在 `validate_dependency_runtime()` 中才核对；未登记 entry 可以在到达该检查前结束。shell 侧也只检查最终文件 `! -L`，没有对 `docs/`、`contracts/` 和 entry 每一段执行 no-follow 打开与同一文件描述符执行。
  5. 隔离副本把一个不同 bootstrap inode 交给 shell 打开，再让该脚本第一步以原子 `mv` 把路径换回登记字节；随后同一已打开的旧 inode继续执行，而 release-gate `--self-test-preflight` 输出 `self_test_preflight=accepted`。后续 Python 只看到路径上的登记字节，不能证明 shell 实际执行的是该 inode/字节。
- 影响：正常 full gate 的 CPython binary/framework/ABI/platform/stdlib tree 检查确实通过，但它不能证明“所有正式入口都先由固定 `/bin/sh`、固定 bootstrap 字节和登记 entry 启动”。调用者可得到同一 runtime guard 成功结论而没有经过所声明的启动链；现有 21 条 external negative self-test 只覆盖不同 Python 身份，不覆盖已登记 Python + 自填环境值、替代 shell 或新增 entry。
- 确定性验收：
  1. 外部启动边界必须核对实际解释器，而不是在替代 shell 下仍只哈希 `/bin/sh`；替代 shell 调用应确定性非零。
  2. 在执行任何仓库 Python 字节前，由外部固定根对 bootstrap 的 exact raw digest、逐段 no-follow 路径、inode/stat/长度及打开后的同一字节流完成验证；不得依赖待验证 Python 事后自证。
  3. entry 使用封闭的 exact path/ID/raw-pin allowlist；任意新增 `docs/contracts/*.py`、路径别名、目录 symlink 或并发替换均拒绝。
  4. `AQ_RUNTIME_BOOTSTRAP_V1=verified` 不能单独充当 launch proof；使用不可由普通调用者重放的、绑定已打开 bootstrap/entry/runtime 身份的交接证据，或明确收窄“必须经 bootstrap”的声明与门禁语义。
  5. 增加本轮四个命令以及 bootstrap raw drift、intermediate symlink、entry TOCTOU 的隔离负例；full gate 必须自己执行并确认目标 failure class。

## AQ-R18-003 — 固定运行时没有绑定实际装载的非系统动态依赖

- 严重度：High
- 确定性：Certain
- 证据等级：E1
- 分类：运行时实现闭包与摘要可信度
- 精确定位：`docs/contracts/runtime-bootstrap-v1.sh:19-62,71-74`；`docs/contracts/python_runtime_guard_v1.py:5,14-29,32-92`；`docs/contracts/package.json:20-49`；`docs/contracts/validate-contracts-v1.py:586-618`；`docs/contracts/validate-json-schema-v1.mjs:1-193`；`docs/design-proposal.md:2349`；`docs/provider-contract.md:487`；`docs/security-model.md:445`。
- 可复核证据：
  1. bootstrap/profile 固定了 CPython executable、framework 与 stdlib tree，但当前固定解释器中的 `hashlib.sha256` 实际是 `_hashlib.openssl_sha256`。`otool -L .../lib-dynload/_hashlib.cpython-311-darwin.so` 显示它装载 `/opt/homebrew/opt/openssl@3/lib/libcrypto.3.dylib`；`/opt/homebrew/opt/openssl@3` 当前又是可移动到另一 Cellar 版本的 symlink。profile 与 guard 都没有登记该 resolved image path、raw digest 或递归依赖闭包。
  2. Python guard 正使用这个未登记的 `libcrypto` 计算它对 executable/framework/stdlib 的 SHA-256；所以“被验证的摘要实现”本身不在已固定闭包内。固定 `_hashlib.so` bytes 不能固定 dyld 最终解析到的 `libcrypto` bytes。
  3. retention 的规范解析依赖 Pandoc。`otool -L /opt/homebrew/bin/pandoc` 显示它装载 `/opt/homebrew/opt/gmp/lib/libgmp.10.dylib`；package profile只固定 Pandoc executable raw digest，没有登记 GMP 的实际路径/bytes。Node 的系统 framework 可由明确的 OS trust boundary覆盖，但现行合同没有定义“系统库由 OS 版本覆盖、非系统库必须逐个固定”的分界。
  4. bootstrap 继承调用者环境，只增加三个变量；它没有删除或拒绝 `DYLD_*` 等 loader 输入，也没有在进程启动后枚举实际 loaded images并与登记实体比较。正常 full gate通过只能证明当前机器此刻的组合工作，不能证明所声明的动态实现闭包已固定。
- 影响：保持同一个已登记 Python/Pandoc executable和所有仓库字节时，Homebrew `opt` 目标、非系统 dylib bytes或loader环境仍可改变摘要、AST解析及验证程序行为，而现有 runtime profile没有字段可表示这次变化。`exact runtime`、`dependency implementation closure` 与跨机器可复现的表述因此超出证据。
- 确定性验收：
  1. 为 Python、Pandoc及其他参与判定的 native executable定义递归 loaded-image政策：系统 image明确归入固定 OS build trust boundary；所有非系统 image登记 canonical/no-follow resolved path、文件类型、owner/mode、raw SHA-256与依赖边。
  2. 在执行任何 Python摘要或Pandoc解析前，由外部固定启动根验证上述非系统动态依赖；不能用待验证的 `libcrypto` 独自证明它自己的正确性。也可以改为仓库随附、静态闭包且外部hash固定的hermetic runtime。
  3. 用最小封闭环境启动，清除或明确拒绝 `DYLD_*`、`PYTHON*`、locale及其他可改变装载/解析的未登记变量；运行后核对实际 loaded image集合与登记闭包完全相等。
  4. 增加 `openssl@3` opt target切换、libcrypto/GMP bit drift、额外非系统依赖、loader injection和同一 executable + 不同 loaded image负例；均必须在输出任何成功摘要前拒绝。

## AQ-R18-004 — history/current-status 验证仍写死 R17 失败态，不能动态进入下一轮或表达零问题

- 严重度：High
- 确定性：Certain
- 证据等级：E1
- 分类：审计历史状态机与收敛可验证性
- 精确定位：`docs/contracts/validate-contracts-v1.py:67-70,110-113,1735-1781`；`docs/contracts/schemas/core-safety-contract-v1.schema.json:1268-1281`；`docs/contracts/run-release-gate-v1.py:793-945,1080,1150`；`docs/contracts/core-safety-contract-v1.json:5640-5648`；`docs/design-proposal.md:2352-2354`；`docs/security-model.md:446-448`。
- 可复核证据：
  1. validator 的受保护历史路径在代码中固定为 `range(1, 18)`，并逐行要求 `round <= 17`。所以 manifest 不能单独把 latest 推进到 R18；每一轮都必须同步修改 validator 的 compile-time allowlist。
  2. `validate_history_manifest()` 无条件要求最新 verdict 为 `FAIL_WITH_<N>_ISSUES`、resolution 第一项为 `<round>-001/BLOCKED_USER_DECISION`、其余全部 `FIXED`，并要求 gate status 恰为 `NOT_ZERO_ISSUES_NOT_GATE_0A`。它不能接受 `PASS_ZERO_ISSUES`、空 issue set 或没有 blocker 的最终状态。
  3. `currentDesignStatus` schema 同样把 `current_blocker_status` 固定为 `BLOCKED_USER_DECISION`，把 `gate_status` 固定为 `NOT_ZERO_ISSUES_NOT_GATE_0A`，且要求始终存在 blocker 与 resolution status。它只描述当前失败快照，不是可到达零问题的状态联合。
  4. release gate 的专项 history QA 又固定 `round-17-*` 路径、`FAIL_WITH_8_ISSUES` 和从 17 回退到 16。正文却声明 latest 轮次与 blocker/gate 状态“动态闭合”。现行实现能保护 R1–17 字节，但不能在不改执行代码的前提下验证 R18 或最终 PASS。
- 影响：本目标要求最多 20 轮内由新 Agent 得出 `PASS_ZERO_ISSUES`。当前机器门禁在语义上拒绝该终态，也会把每次正常轮次推进变成修改 validator 自身的动作；因此“current status 唯一值源”和“动态 latest”尚未实现，最终收敛结论无法由现有 gate 证明。
- 确定性验收：
  1. 历史 manifest 在 `1..20` 上自描述连续 round、kind、path 和 raw digest；validator 从 manifest/latest 与固定上限推导 exact path closure，不含当前轮次常量。
  2. 定义判别式 current-status 状态机：有问题态允许 issue/resolution/blocker；零问题态允许 `PASS_ZERO_ISSUES`、空 issue set、无 blocker，并有唯一、明确的 gate 状态和 resolution 策略。
  3. validator 从 artifact + manifest 推导 round、文件名、首行、issue set、status 与四份 marker 的关系；schema 只验证形状/分支，不复制当前轮值或强制永远 blocked。
  4. 把 history 专项 QA 参数化为 manifest 的动态 latest。至少证明：R18 fail、随后 R19 pass 均无需修改 validator/release gate 字节；删除、替换、首行伪造、回退、自引用和单点 marker 漂移仍拒绝。

## 基线与自动验证证据

正常基线全部通过，但正常样本通过不抵消上述用户决定、启动证明、动态依赖或状态机问题：

| 检查 | 当前结果 |
| --- | --- |
| `/bin/sh ... runtime-bootstrap-v1.sh ... validate-contracts-v1.py` | 6 个 meta-schema、8 个 schema instance、120 个 array schema object、14 个 semantic validator、36 个 core fixture、43 个 retention fixture、11 个 retention structural QA、9 个 live persistence directive、128 个 numbered heading、14 个 R17 semantic QA；registry anchor `d5b8fd1099b10e09408aa8b34d1a228d2dbdf0ad4bc4939950274d771396c3d1`；input SHA-256 `6cbe6f9224ab31e1ce5d3e00198137914ed0fa3fefe118a77c43ef6bc0cd16b9`；`source_bytes_unchanged=true`，`status=ok` |
| 外部 bootstrap projection verifier | projection SHA-256 `518c6939a27f83f90390ec9fd8e710864716700278370d71d05aa0fbdc1972d6`；同一 registry anchor；`source_bytes_unchanged=true`，`projection_status=verified` |
| 外部 bootstrap 41-case runner | case count 41；results SHA-256 `30829d260c656a30fb33938b30c72e0b020a54bca4f1c986434bf93aa2256781`；`source_bytes_unchanged=true`，`status=ok` |
| 外部 bootstrap full release gate | release input SHA-256 `e246ed4912d0559ee7818f3d550644263031d94d87d73513107387d053b2bd03`；空 HOME/cache offline clean install、双 validator/projection replay、41-case exact match、5 个 helper self-test、4 个 typed-state self-test、21 个 external negative self-test均通过；`release_authority=audit-evidence-only-not-a-release-authority`，最终 `status=ok` |
| 5 个离线 tarball静态复核 | 共 527 个条目；每个只有 `package/` 根、无 absolute/`..` 路径、无 symlink；目录集合与登记的 5 个 raw digest一致。clean gate又在空 HOME/cache中从 `file:` lock安装并重算 5 个依赖实现树 |
| typed state / consent / retention / heading | 9 个 runtime/result case 的 before/after hash逐项不同；gate从实体重算并执行4个 typed-state self-test。consent覆盖 3 audience + missing/unknown/error 的6行真值表。retention 11 个结构 QA、128 个编号 heading 与本地 anchor lint均通过 |
| JSON/placeholder/Git | 5 artifacts、6 schemas、2 fixtures、registry/history/package/lock均可由 `jq` 解析；现行 source没有未决占位符，唯一字面 `XXXXXX` 是 `mktemp` 的固定随机模板；Git 为 `No commits yet on main`，无 staged change |

## 覆盖面复核与本轮未另立项

本轮全量复核需求与非目标；principal/subject/capability、多账户身份与 Gate 0A；Adapter manifest、ProbeResult、discovery/fetch/final context；Codex local-stdio 与 DeepSeek HTTP；cache/LKG/query generation；rate ledger、reservation、并发、deadline 与幂等；operation/stage/predicate/error algebra；LocalKeyRing；TOML、SQLite migration journal、storage/purge；lease/fence；retention/privacy/data inventory；release/trust/runtime/offline；Hermes、飞书、Web 与调度可选集成；registry、schema、fixture、projection、runner 与 clean gate。

已直接确认但未另立项：

- 5 个离线 tarball 的文件集合、raw digest、manifest/lock `file:` URL、空 HOME/cache安装及安装后 dependency tree在现有基线成立；额外、缺失、bit drift、registry URL、manifest digest负例均被现有 full gate拒绝。
- 9 个 runtime/result typed state的 before/after确实不同，gate会从隔离实体重算；4个 self-test命中 wrong field、descriptor/entity差异及不同 malformed shape，不只是比较 broad failure。
- consent 的 true/false/missing/error控制流和三 audience授权边界一致；missing/unknown/error fail closed。retention exact heading text/identifier、owner join、11个结构 QA和128个 heading/anchor lint通过。
- detached manifest 当前逐字节固定 R1–17 audit/resolution，删除、替换、首行伪造、回退与投影漂移负例会拒绝；本轮问题只针对动态升级和最终 PASS 状态表达，不否认当前 R1–17 字节保护。
- validator/canonicalizer仍只读，当前未跟踪 checkout及其输出明确标记为 audit evidence，不构成生产 release authority、应用实现、真实 Provider 集成或运行时安全证明。

## 历史去重

候选根因在读取历史正文前已冻结，随后核对第 1–17 轮 audit/resolution：

- `AQ-R18-001` 是持续且未被虚构关闭的用户决定 blocker；R18没有替用户加入 `account/read`、移除 Codex或降低 Gate 0A。
- `AQ-R18-002` 是对 `AQ-R17-002` 修复后的新回归验证：R17已固定 CPython binary/framework/ABI/platform/stdlib；本轮承认这些身份检查成立，只报告“谁启动、实际 shell、允许 entry、launch proof”仍不闭合。四个当前负例不依赖不同 Python版本，因此不是重复报告原问题。
- `AQ-R18-003` 是对 `AQ-R17-002` 的第二层实现闭包复核：R17已固定 Python executable/framework/stdlib，本轮承认这些摘要成立，只报告实际被 `_hashlib`/Pandoc装载的非系统 dylib仍不在机器 profile中；它与“哪个launcher启动”不是同一根因。
- `AQ-R18-004` 是对 `AQ-R17-006` 修复后的新终态验证：R17已把当前值放入 artifact并保护 R1–17字节；本轮承认该成果，只报告 validator/schema仍写死 R17失败形态，不能无代码改动推进或接受零问题。它不是“历史未入 gate”的旧问题。

因此 4 个问题对应 4 个当前独立根因。

## Source、历史、node_modules、bundle、隐私与 Git 完整性

- 审计开始时，排除 `docs/audits/` 与 `docs/contracts/node_modules/` 的 33 个现行 source 文件 hash-manifest SHA-256 为 `05ccadeccf45083ba726012f5473d7f2e6cb28a10d081b99a59aaeaff43e40be`。
- 读取历史前，第 1–17 轮 34 个 audit/resolution 文件 hash-manifest SHA-256 为 `26b45c4d55386e5869a17870c4e5205ce1bf78b845754a26ce2eb4f7faa7b895`。
- `docs/contracts/node_modules/` 共 528 个文件，hash-manifest SHA-256 为 `0bc2fceca57bbe08093062f7f494f8cf164d7c9e57f8fdbd4718a311b64b6794`。
- `offline-npm-bundle-v1/` 共 5 个 tarball，hash-manifest SHA-256 为 `32f76749eee4b35dd992d38ababbfaf91e2ac5dfc0b6182b4045debb4568ce66`。
- 本轮未联网，未读取真实账户、Provider、凭据或用户业务数据，未启动 Hermes/飞书集成。所有正式 baseline 输出均声明 `source_bytes_unchanged=true`。
- Git 初始状态为 `No commits yet on main`；仓库文件未跟踪，无 staged change、commit 或 push。
- 本轮允许的唯一仓库新增文件是 `docs/audits/round-18-audit.md`；最终逐文件复核见文末记录。

## 最终完整性记录

- Source、R1–17历史、node_modules与bundle的最终 hash-manifest必须分别仍为上节四个启动值；本报告写入后的复核结果记录为 `verified-unchanged`。
- 启动清单之外只新增 `docs/audits/round-18-audit.md`；README、三主文档、contracts、schemas、fixtures、工具、package/lock、bundle与R1–17历史均未修改。
- 最终 Git 状态仍为 `No commits yet on main`，没有 staged change、commit或push。

## 最终结论

在 3 个可直接修复问题关闭、Codex稳定身份获得用户产品决定，并由新的独立 Agent再次全量审计得到 `PASS_ZERO_ISSUES` 前，不能宣告设计质量收敛或 Gate 0A通过。
