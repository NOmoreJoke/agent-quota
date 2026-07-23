# 第 19 轮修复处置记录

- 处置日期：2026-07-19（Asia/Shanghai）
- 处置边界：仅处理第 19 轮审计项；不替用户作产品选择，不访问真实账户、Provider 或凭据，不联网，不 stage、commit 或 push。
- 设计版本：`v2.5`

## AQ-R19-001 — BLOCKED_USER_DECISION

- 核验结论：成立，且只能由用户决定。
- 处理：保持阻塞。没有增加 `account/read`，没有从现有响应猜测稳定身份，没有移除 Codex 或放宽 Gate 0A。
- 验收：方向 A/B 仍须由用户明确选择；此前 Codex 保持 incompatible，Gate 0A 保持关闭。

## AQ-R19-002 — FIXED

- 核验结论：成立。Pandoc/Node 的旧 `vmmap` 收集器只观察两个安装前缀，无法证明全部非系统 loaded image 已进入闭包。
- 处理：Python、Pandoc、Node 统一为“先发现、后分类”。`vmmap` 从固定 file-backed Mach-O 映射形状收集全部绝对路径，发现阶段不读取登记 closure 或安装前缀；只有 canonical resolved path 位于 `/System` 或 `/usr/lib` 且 exact Darwin build 匹配时归系统，其余路径必须 no-follow、regular、Mach-O 并进入非系统集合。额外项、缺失项、bytes/metadata/dependency drift、symlink、非普通文件或 canonicalize 失败全部 fail closed。
- 验收：本地专项矩阵覆盖 `/opt/homebrew`、`/usr/local`、`/Library`、`/Applications`、`/Users`、真实临时目录、未登记/缺失集合、bytes drift、symlink、非普通文件和缺失路径；端到端进程实际加载临时目录 dylib 后，收集器必须观察到该路径。loader/Python 环境仍在 bootstrap 与子进程中清空到封闭集合。

## AQ-R19-003 — FIXED

- 核验结论：成立。旧 external QA 无条件要求 resolution，旧 dynamic QA 无条件构造下一轮，导致合法 R20 `ZERO_ISSUES` 不可达。
- 处理：external history QA 按 `ISSUES_OPEN` / `ZERO_ISSUES` 分支；前者要求 resolution，后者禁止 resolution并以注入负例验证。动态 QA 显式区分可推进轮、零问题终态固定点与 R20 `round-budget-exhausted`；输出改为中性 `dynamic_history_state_qa`。
- 验收：现行 R19 FAIL+resolution可验证；隔离 R20 `PASS_ZERO_ISSUES`/空 issue/no resolution 连续验证两次并保持工具字节不变。注入 resolution、非空 issue、blocker、FAIL 首行、R21、回退、自引用尝试和单点 marker 漂移均拒绝；R20 open 明确得到 round-budget-exhausted。

## AQ-R19-004 — FIXED

- 核验结论：成立。多个同时 active blocker 取最小差值不能表示完整请求最早可通过时刻。
- 处理：唯一机器规则冻结在 `core-safety-contract-v1.json#/budget_ledger_contract/retry_after_aggregation`。同一 `BEGIN IMMEDIATE`、同一 DB UTC sample 对 endpoint group 与 verified cohort union 收集全部 active boundary；`retry_after_seconds=clamp(max(active_boundaries)-now,0,86400)`，无 active 时为 `None` 并允许 reserve。expired boundary不计，结果与输入顺序、primary reason和进程调度无关；`blocked_until=max(existing,upstream,policy)` 只收紧。
- 验收：artifact、schema、validator 与 fixture 覆盖空集合、单 floor/hour、10+60、reservation+blocked_until、group+cohort、expired boundary、任意排列和 hard-max clamp。双进程虚拟时钟在 10 秒边界仍 deferred，只在 60 秒 all-clear boundary 允许新 reservation。

## 验证记录

- 机器验证：Python 与 65 份 JSON 语法、正式 bootstrap validator、read-only projection verifier、exact mutation suite、empty-HOME/cache offline clean-install release gate与双重确定性 replay均纳入本轮最终复核。
- R19 专项：loaded-image prefix-independent discovery、R20 terminal state、branch-specific history negatives 与 retry-after双进程虚拟时钟均由固定 gate 执行。
- 历史完整性：R1–R19 audit 与 R1–R18 resolution 保持原始字节；本文件采用 detached 两阶段流程，不包含自身摘要或 history manifest 摘要。
- 当前边界：所有成功结果仍是 `audit-evidence-only-not-a-release-authority`；本轮唯一用户决策项仍未解决，Gate 0A 仍关闭。
