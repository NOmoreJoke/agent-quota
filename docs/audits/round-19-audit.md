# FAIL_WITH_4_ISSUES

## 第 19 轮独立本地设计一致性、验收规则与验证覆盖审计

- 审计日期：2026-07-19（Asia/Shanghai）
- 结论：现行设计仍不能进入 `PASS_ZERO_ISSUES`，也不能通过 Gate 0A。
- 问题数：4 个，分别为 1 个 Blocker、2 个 High、1 个 Medium。
- 审计边界：只读本地 README、三份现行主文档、全部一方合同/Schema/fixture/工具链、package/lock、离线 bundle 登记、R1–R18 audit/resolution 与 history manifest。除本报告外未修改任何仓库文件。
- 数据边界：未联网，未访问账户、Provider、凭据、Hermes、飞书或其他外部系统。最小复现只使用当前源码、内存构造数据和自动清理的本地临时目录。
- Gate 边界：没有启动新的 full gate。只用 `ps` 观察既有 PID 95015 及其子进程，没有发送信号、写入其输入、读取其文件描述符或改变其执行。
- 证据口径：`E1` 是当前字节上的直接矛盾或实际本地函数复现；本轮四项均为 `E1`。

## AQ-R19-001 — Codex 稳定账户身份仍需用户作 A/B 产品决定

- 严重度：Blocker
- 确定性：Certain
- 证据等级：E1
- 分类：`BLOCKED_USER_DECISION`

### 代码与文档证据

1. `README.md:56,76` 仍把 Codex 是否增加只读身份来源或退出第二个 MVP Adapter 位置留给用户决定。
2. `docs/design-proposal.md:1192,1215,1493,1505,2171,2216-2217,2262,2310,2354,2361` 同时规定：
   - `official_cli` 要成为 Supported 并执行正式 fetch，必须得到 `verified_stable` 身份；
   - Codex 当前不能自行增加 `account/read`，也不能用 rate-limit payload、principal、进程或临时 session 猜身份；
   - Codex 仍是阶段 1B 的第二个真实 Adapter 候选。
3. `docs/provider-contract.md:148-150,181-189,195-210,490,496` 与 `docs/security-model.md:180-182,364,389,421,430,438,446,448` 保持同一 fail-closed 语义：Codex 只有握手和 `account/rateLimits/read`，没有获批准的 stable subject source/domain。
4. `docs/contracts/core-safety-contract-v1.json:286-320` 只给 Codex 登记 `codex-local-rate-limit-v1` endpoint budget group；`docs/contracts/core-safety-contract-v1.json:5750-5779` 的 current status 仍是 `ISSUES_OPEN`，blocker 为 `AQ-R18-001/BLOCKED_USER_DECISION`。R19 只是本轮重新确认同一个未决产品选择，没有把它虚构为已关闭。

### 最小本地复核

只读检索四份正文与 core artifact，得到以下闭合事实：

```text
Codex business RPC allowlist = initialize + initialized + account/rateLimits/read
Codex verified-stable IdentitySourceContract = absent
Codex ProviderIdentityDomain = absent
Codex stage-1B second Supported adapter expectation = present
current_blocker_status = BLOCKED_USER_DECISION
```

该组合没有可由审计 Agent 唯一推出的实现结果。

### 影响

- 保持当前 allowlist 时，Codex 不能满足 Supported、正式 fetch、持久 cache/LKG 和多账户隔离的退出条件。
- 放宽身份条件却不冻结稳定 subject source 时，无法证明账户切换、重启和登出重登后的 cache/LKG/rate-cohort 归属正确。
- 因此 Gate 0A 不能由文档修复 Agent自行关闭。

### 确定性修复与验收

本项不是工程 Agent 可代选的修复。用户必须明确选择下面一个互斥方向：

- 方向 A：批准一个最小只读、稳定的 Codex 身份来源，并冻结 exact argv/method、允许字段、null/缺失语义、source generation、identity domain、最小披露、账户切换/登出重登、deadline/error/fail-close 与多账户向量。
- 方向 B：保持当前最小 RPC allowlist，把 Codex 从 MVP Supported/第二 Adapter 退出条件中移出，选择另一个已有稳定身份合同的 Adapter；Codex 保持 Experimental/incompatible 且不计入 MVP。

任一方向的验收都必须同时更新机器合同、Provider profile/binding、cache/LKG eligibility、rate cohort、迁移、Gate 0A 与 current status；用同账户重启、A→B 切换、登出重登、空/缺失身份和跨 principal 组合矩阵验证；最后由新的独立 Agent 全量复核。用户没有选择前，本项保持 Blocker。

## AQ-R19-002 — Pandoc/Node 的非系统 loaded-image 收集只识别两个路径前缀

- 严重度：High
- 确定性：Certain
- 证据等级：E1
- 分类：验证运行时动态依赖集合不完整

### 代码与文档证据

1. `docs/contracts/package.json:68-72` 把系统 image 定义为 exact Darwin build 覆盖的 `/System` 或 `/usr/lib`，其余实际 loaded image 都应逐项固定。
2. `docs/design-proposal.md:2359`、`docs/provider-contract.md:494` 与 `docs/security-model.md:445` 声明 Python/Pandoc/Node 的全部非系统 loaded image 都会进入精确集合。
3. Python 自检的 `docs/contracts/python_runtime_guard_v1.py:138-152` 确实枚举所有 dyld image，只排除 `/System/` 和 `/usr/lib/`。
4. 但 Pandoc/Node 使用的 `docs/contracts/validate-contracts-v1.py:607-624` 从 `vmmap` 文本提取路径时，正则被写成：

   ```python
   re.findall(r"(/(?:opt/homebrew|usr/local)/[^\s)]+)", completed.stdout)
   ```

   因此只有 `/opt/homebrew/...` 与 `/usr/local/...` 会成为观察集合。`/Library/...`、`/Applications/...`、`/Users/...` 和系统临时目录中的合法绝对本地路径不会被收集。
5. `docs/contracts/validate-contracts-v1.py:785-786` 只把这个不完整观察集合与登记 closure 比较。若登记 closure 同样漏掉该 image，集合仍可能相等，不能证明“全部非系统 image”已经精确收集。

### 最小本地复现

本轮加载现行 `validate-contracts-v1.py`，只替换其 `Popen/run/sleep` 为本地假进程与固定 `vmmap` 文本，然后直接调用现行 `_probe_process_non_system_images()`。fixture 在 `tempfile.TemporaryDirectory(prefix="aq-r19-image-")` 中创建一个普通本地文件，并提供四条映射：

```text
/opt/homebrew/lib/libinside-homebrew.dylib
/usr/local/lib/libinside-local.dylib
/var/folders/.../T/aq-r19-image-.../liboutside-prefix.dylib
/Library/AgentQuota/liboutside-library.dylib
```

实际输出：

```text
collector_observed=['/opt/homebrew/lib/libinside-homebrew.dylib', '/usr/local/lib/libinside-local.dylib']
outside_temp_image_observed=false
outside_library_image_observed=false
```

fixture 自动清理，仓库字节没有变化。该复现测试的是现行函数本身，不依赖外部账户、网络或真实 Provider。

### 影响

Pandoc/Node 可以在已登记 executable 不变的情况下装载位于其他合法本地前缀的非系统 image，而当前观察集合看不见它。这样，`actual set == registered closure` 可能在实际集合并不完整时仍成立。现行“全部非系统动态依赖已精确固定”的验证结论因此超出收集器证据。

### 确定性修复与验收

1. 把 loaded-image 的分类规则统一为：canonical resolved path 位于 `/System/` 或 `/usr/lib/` 才属于 exact OS build 边界；其他实际文件 image 一律属于非系统集合，不得用安装前缀决定是否收集。
2. `vmmap` 解析器先从固定格式中提取全部实际 file-backed image 的绝对路径，再做 canonical/no-follow/file-kind 校验与系统/非系统分类。发现过程不能先用已登记 closure 当筛选器，否则未知 image 仍会不可见。
3. 所有非系统观察项都必须与 `non_system_images` 的 path、kind、uid/gid、mode、size、raw SHA-256 和递归依赖边形成精确双向集合；额外项、缺失项、bit drift 或路径解析失败均在成功摘要前拒绝。
4. 修复 validator 后同步更新工具 raw pin、传递 helper closure、mutation/runtime 证据、package/registry/artifact/schema 投影与相应摘要；不得只改散文声明。

验收矩阵至少包含：

| fixture | 期望 |
| --- | --- |
| `/opt/homebrew/...`、`/usr/local/...` 已登记 | 收集并匹配 |
| `/Library/...`、`/Applications/...`、`/Users/...`、真实临时目录已登记 | 同样收集并匹配 |
| 任一上述路径已加载但未登记 | `unregistered non-system loaded image` |
| 已登记路径 bytes 改变 | digest mismatch |
| `/System/...`、`/usr/lib/...` 且 OS build 完全匹配 | 归入系统边界 |
| 路径含 symlink、非普通文件或不能 canonicalize | fail closed |

还要用一个只加载临时目录 dylib 的本地 fixture 进程做端到端负例，证明收集结果与安装前缀无关。

## AQ-R19-003 — 实际 R20 `ZERO_ISSUES` 会让 release gate 的两项历史 QA 自相矛盾

- 严重度：High
- 确定性：Certain
- 证据等级：E1
- 分类：终态历史状态机与 release-gate 覆盖不一致

### 代码与文档证据

1. `docs/design-proposal.md:2360`、`docs/provider-contract.md:495`、`docs/security-model.md:446` 与 README 的验证说明都承诺：R19 可以继续 FAIL 并有 resolution，随后 R20 可以是 `PASS_ZERO_ISSUES`、空 issue、无本轮 resolution，且不修改 validator/release-gate 字节。
2. `docs/contracts/validate-contracts-v1.py:1884-2005` 与 `docs/contracts/schemas/core-safety-contract-v1.schema.json:1268-1331` 已能表达 `ISSUES_OPEN` / `ZERO_ISSUES` 判别联合；问题不在这里。
3. `docs/contracts/run-release-gate-v1.py:946-953` 的 `verify_external_negative_self_tests()` 无条件要求 latest 含 resolution：

   ```python
   resolution_rel = baseline_latest.get("resolution", {}).get("path")
   require(isinstance(resolution_rel, str),
           "external history QA requires the current open round resolution")
   ```

   这与 `ZERO_ISSUES` 明确禁止本轮 resolution 相冲突。
4. `docs/contracts/run-release-gate-v1.py:1154-1165` 的 `verify_dynamic_history_state_machine()` 无条件计算 `next_round=current_round+1` 并要求它不超过 20。实际 latest 已是 R20 时，它仍尝试构造 R21。
5. `docs/contracts/run-release-gate-v1.py:1366-1369` 在每次正常 gate 中无条件调用以上两项 QA，所以这不是不可达 helper。

### 最小本地复现

本轮没有运行 full gate。测试加载现行 validator 与 release-gate 函数，读取当前 complete snapshot，在内存中把 latest 替换为合法外形的 R20 `ZERO_ISSUES/PASS_ZERO_ISSUES/no resolution`，并加入临时 `round-20-audit.md` bytes。随后分别直接调用两个现行函数。

实际输出：

```text
external_negative_self_tests=RuntimeError:external history QA requires the current open round resolution
dynamic_history_state_machine=RuntimeError:dynamic history pass QA has no remaining round
```

第二个函数自行使用 `TemporaryDirectory` 复制 snapshot；临时副本已自动清理。两条错误均发生在函数自己的状态前置条件，早于完整终态语义验证。

### 影响

如果后续按正文把 R19 处置完并让 R20 成为零问题，validator 可以接受该数据形状，但 full release gate 会因自己的 QA harness 报错。也就是说，验证目标允许的终态与执行该验证的 gate 不一致，最终 `status=ok` 不可到达。

### 确定性修复与验收

1. 把 external history QA 改为按 `latest.state` 分支：
   - `ISSUES_OPEN`：必须有 resolution，并执行 delete/replace/status 负例；
   - `ZERO_ISSUES`：必须没有 resolution，用“注入一个本轮 resolution 必须被拒绝”替代“删除 resolution”测试；audit 删除、替换、伪首行、回退和 marker 漂移仍执行。
2. 把 dynamic history QA 改为显式状态机，而不是永远“下一轮 PASS”：
   - `round < MAX_AUDIT_ROUNDS` 时测试合法下一轮转换；
   - `round == 20 && state == ZERO_ISSUES` 时测试终态固定点、重复验证和非法 R21 拒绝，不再尝试推进；
   - `round == 20 && state == ISSUES_OPEN` 时给出确定的 round-budget-exhausted 失败，不能伪造 PASS。
3. 正常 gate 根据当前状态执行恰当 QA，并把输出改为不假定“fail-to-next-pass”的中性字段，例如 `dynamic_history_state_qa=<count>-verified`。
4. 修改 gate 后同步更新 bootstrap/package entry raw pin、函数与传递 helper closure、registry/artifact pin、schema/projection 和 mutation 期望；保证工具链引用闭合。

修复后的验收必须在隔离副本覆盖：

- R18 `ISSUES_OPEN` 的当前基线仍能完成状态 QA；
- R19 `ISSUES_OPEN` + resolution → R20 `ZERO_ISSUES` + no resolution，full gate 成功；
- 同一 R20 终态连续运行两次，输出一致且不构造 R21；
- R20 零问题态加入 resolution、非空 issue、blocker 或 FAIL 首行均拒绝；
- R20 失败态明确拒绝收敛，R21、删除/替换 audit、首行伪造、回退、自引用、单点 marker 漂移仍拒绝；
- 测试前后 validator/gate 之外的临时状态不泄漏，source-byte 复核保持一致。

## AQ-R19-004 — 多个 blocker 的 retry-after 取最小值会给出仍不可重试的时间

- 严重度：Medium
- 确定性：Certain
- 证据等级：E1
- 分类：rate-ledger 聚合语义错误

### 代码与文档证据

1. `docs/design-proposal.md:1578` 定义 floor、active reservation、hour/`blocked_until` 为独立 blocker，任一未到期就拒绝。
2. 紧接着的 `docs/design-proposal.md:1579` 却规定 retry-after 是“全部未到期 boundary 与 now 非负差的最小值”。
3. `docs/design-proposal.md:1558,1581,1584-1586`、`docs/provider-contract.md:370,383` 和 `docs/security-model.md:420` 要求 endpoint group 与 verified cohort 的限制取 union，并允许上游 `Retry-After` 只收紧 gate。多个限制因此会同时有效，不是任选一个通过即可。
4. 当前机器 artifact 冻结了 budget policy、group 与 reason/error vocabulary，但没有一个机器字段覆盖多个 active blocker 的 retry-after 聚合规则，现有测试清单也没有 10 秒 + 60 秒交叉向量。

### 最小本地复现

用同一 `now=100` 构造两个已在事务中确认 active 的 boundary：floor=`110`、hour=`160`，执行现行文字规则：

```text
current_min_retry_after=10
active_at_reported_retry=['hour']
earliest_all_clear_retry_after=60
```

调用方按返回值在 10 秒后重试，仍满足 `retry_time < hour_boundary`，所以会再次得到同类拒绝。

### 影响

`retry_after_seconds` 不能表示“这次完整请求最早可能通过的时间”。调用方遵守它仍会产生一次确定无效的本地重试；这会增加排队、幂等和限流噪声，也让不同实现可能分别选择最早 boundary、最晚 boundary 或某个 reason 的 boundary。

### 确定性修复与验收

在同一个 `BEGIN IMMEDIATE` 和同一个 DB UTC sample 内：

1. 先计算 group umbrella 与 verified cohort union 中全部 active blocker；`now >= boundary` 的项已到期，不进入集合。
2. 只要集合非空就拒绝；`retry_after_seconds = clamp(max(active_boundaries) - now)`。也就是所有必要条件都解除的最早时刻，而不是任一条件先解除的时刻。
3. 没有 active blocker 时 `retry_after_seconds=None` 并允许 reserve。聚合必须与输入顺序、primary reason 和进程调度无关。
4. 把规则放入机器合同并由 schema/validator/fixture 引用；正文只引用该唯一字段。上游/策略产生的 `blocked_until=max(existing, upstream, policy)` 继续保持只收紧语义。

验收矩阵：

| active boundary（相对 now） | 期望 retry-after / 结果 |
| --- | --- |
| 无 | `None`，允许 reserve |
| floor=10 | 10 |
| hour=60 | 60 |
| floor=10, hour=60 | 60 |
| reservation=20, blocked_until=40 | 40 |
| group=10, verified cohort=60 | 60 |
| expired=0, hour=60 | 60 |
| floor=0, hour=0 | `None`，允许 reserve |
| 相同集合的任意排列 | 完全相同结果 |
| 最大 boundary 超过 `aq-bounds-v1` hard max | 按唯一上界夹取，仍保持 deferred |

还要在双进程虚拟时钟测试中验证：10 秒时仍拒绝但不会被先前结果误导为“应当成功”；60 秒边界满足 `now >= boundary` 时才允许新 reservation。

## 全量覆盖复核

除上述四项外，本轮没有足够证据新增问题。以下“未新增”只表示当前静态设计与本轮定向复现没有形成另一个确定矛盾，不表示应用已经实现或真实集成已经验证。

| 覆盖面 | 本轮复核结果 |
| --- | --- |
| 启动边界 | exact `/bin/sh`、四入口 allowlist、opened-fd entry 与“本地 checker 不等于外部 release authority”的边界在正文和工具中一致；新增问题只限 AQ-R19-002 的 Pandoc/Node loaded-image 收集缺口。 |
| 动态依赖 | Python dyld 全路径枚举与 package image pin 存在；Pandoc/Node 的前缀过滤形成 AQ-R19-002。未把该问题扩大成其他未复现的 runtime 结论。 |
| 历史状态 | R1–R18 共 36 个文件与 detached manifest raw digest 全部一致，四份 current-status marker 与 core artifact 一致；实际 R20 gate 矛盾单列 AQ-R19-003。 |
| 身份与多账户 | principal/subject/capability、cache identity、query generation、cohort 与 conservative group 的分离规则仍在；Codex stable identity 的唯一产品缺口单列 AQ-R19-001。 |
| lease / retention | `lease-policy-v1` 的 8 个 policy、11 个 typed formula、clock-domain/overflow closure，以及 retention inventory/owner/directive lint 仍有机器合同与 schema；本轮未发现新的确定矛盾。 |
| 迁移 / 回滚 / purge | 单一 plan envelope/digest、Kahn 顺序、writer lease/fence、journal roll-forward、temp claim 与 no-follow purge 边界仍闭合；没有新增证据问题。 |
| 可观测性与数据边界 | safe error params、假名化关联、日志禁入字段、alert/consent/idempotency retention 引用仍一致；没有把未实现的运行时行为写成已验证。 |
| 供应链 | registry、artifact/schema raw+canonical pin、离线 npm bundle、package/lock 与 runtime tool profile仍存在；本轮只做本地静态/字节复核，未把运行中的 gate 说成已经完成。 |
| Provider / cache / 并发 | DeepSeek HTTP、Codex stdio、observation→core snapshot、LKG/query generation、singleflight、semaphore、at-most-once 与 9/10 秒边界未出现新的高置信矛盾；多 blocker retry 聚合单列 AQ-R19-004。 |
| Hermes / 飞书 / Web | 三者仍是可选集成；群聊零披露、私聊授权、card action TTL/幂等、Web loopback/Host/Origin/CORS/CSRF 边界没有新的本地证据问题。 |
| 证据一致性 | 文档仍明确“设计/合同验证不是 core/CLI/Provider 实现，也不是生产 release authority”。本轮没有把静态解析、运行中 gate 或历史处置误写成真实 Provider 通过。 |

## 读取范围

本轮读取和核对：

- `.gitignore`、`README.md`；
- `docs/design-proposal.md`、`docs/provider-contract.md`、`docs/security-model.md`；
- `docs/contracts/` 下 5 个 artifact、6 个 artifact/registry schema、2 个 fixture、registry、history manifest、package/lock、5 个 Python 工具、1 个 shell bootstrap、1 个 Node helper；
- `docs/contracts/offline-npm-bundle-v1/` 的 5 个固定 tarball清单与摘要；
- `docs/contracts/node_modules/` 的 vendored implementation tree 文件集合与 aggregate digest；
- `docs/audits/round-01-*` 至 `round-18-*` 全部 36 个 audit/resolution，并核对每轮 issue 标题、处置状态、历史 raw pin 与持续 blocker。

一方 source（排除 `docs/audits/` 与 vendored `node_modules/`）为 33 个文件；R1–R18 历史为 36 个文件；总计 69 个现行一方/历史文件。vendored `node_modules` 为 528 个文件，离线 bundle 为 5 个 tarball；它们按字节树与 pin 复核，不把上游包源码当作本项目设计正文。

## 执行命令与结果

本轮执行的检查均为本地只读，临时 fixture 自动清理：

1. 文件/历史/版本状态：`rg --files`、`find`、`wc -l`、`sed`、`nl`、`rg`、`jq`、`shasum`、`git status --short --branch --untracked-files=all`。
2. 结构解析：17 个一方 JSON 全部通过 `jq -e .`；5 个 Python 工具全部通过 `ast.parse`；`runtime-bootstrap-v1.sh` 通过 `/bin/sh -n`；Node helper 通过 `node --check`。
3. 历史 raw pin：`history_entries=36`、`history_raw_digests_match=true`、`latest_round=18`、`latest_state=ISSUES_OPEN`。
4. current status：四份 Markdown marker 与 core artifact 完全相等；`status_kind=ISSUES_OPEN`、`current_blocker_status=BLOCKED_USER_DECISION`。
5. loaded-image 临时 fixture：现行 `_probe_process_non_system_images()` 只返回 `/opt/homebrew` 与 `/usr/local` 两项，临时目录和 `/Library` 两项均为 `false`。
6. R20 内存/临时副本：现行两个 release-gate 函数分别稳定返回：

   ```text
   RuntimeError:external history QA requires the current open round resolution
   RuntimeError:dynamic history pass QA has no remaining round
   ```

7. retry 聚合：10/60 两个 blocker按现行 min 返回 10；在该时刻 `hour` blocker仍 active；全部解除的最早时间为 60。

本轮没有执行 `run-release-gate-v1.py --root .`、完整 mutation suite、npm install、Provider 请求或任何外部命令。

## 既有 gate 观察状态

- 首次观察：PID 95015 存活，命令是固定 CPython 执行 `docs/contracts/run-release-gate-v1.py --root .`。
- 中途观察：PID 95015 已运行约 18 分 51 秒，状态 `S`；子进程 PID 12113 正运行 `run-validation-mutations-v1.py --root . --evidence-root /tmp/aq-contract-release-.../mutation-evidence`，可判断处于 mutation suite 阶段。
- 本轮只做进程表观察，没有干预。报告完成时的最终观察见下一节完整性记录。

## Source、历史、Git 与最终完整性记录

审计写报告前的基线：

```text
.gitignore SHA-256 = da8325885a2eddde74f0b0f7696e8b960b3d7ae20c437a45491601880b035e1a
33 source files hash-manifest SHA-256 = d8f9d71f6198508adae115feb9e9b7007f328420172d9beca998d25176861fe2
36 R1-R18 history files hash-manifest SHA-256 = 7d72e62f7d2f4ab8ee57d21ff876371ac5b34798eeb3da2440fcdc24b8de2712
528 node_modules files hash-manifest SHA-256 = 0bc2fceca57bbe08093062f7f494f8cf164d7c9e57f8fdbd4718a311b64b6794
5 offline bundle files hash-manifest SHA-256 = 32f76749eee4b35dd992d38ababbfaf91e2ac5dfc0b6182b4045debb4568ce66
Git = No commits yet on main; no staged change
```

最终复核结果：

- 上述 `.gitignore`、33 个 source、36 个 R1–R18 历史、528 个 vendored 文件和 5 个 bundle 的 aggregate digest 均保持不变。
- 启动清单之外唯一新增仓库文件是 `docs/audits/round-19-audit.md`；没有修改 README、三份主文档、合同、schema、fixture、工具、package/lock、bundle 或 R1–R18 历史。
- 没有 stage、commit、push，也没有创建分支或远程状态。
- 最终 gate 只读观察：报告落盘后 PID 95015 仍存活，elapsed 约 22 分 37 秒、状态 `S`；其子进程 PID 12113 仍是 `run-validation-mutations-v1.py`，elapsed 约 15 分 18 秒、状态 `S`。本轮没有取得 gate 最终 stdout，因此没有把它写成成功或失败。

## 最终结论

当前结论是 `FAIL_WITH_4_ISSUES`。AQ-R19-001 必须等待用户明确选择 Codex A/B 产品方向；AQ-R19-002、AQ-R19-003、AQ-R19-004 可以由后续修复 Agent 按各自机器合同和验收矩阵处理。四项关闭并经新的独立全量审计得到 `PASS_ZERO_ISSUES` 前，不能宣告 Gate 0A 或设计质量终态通过。
