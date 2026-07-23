# 第 16 轮修复处置记录

- 修复日期：2026-07-18（Asia/Shanghai）
- 处置结论：`PARTIAL_FIXED_PENDING_USER_DECISION_AND_FRESH_AUDIT`
- 范围：仅修复本轮三项可直接修复的验证、留存引用与状态投影缺口；没有替用户选择 Codex 产品方向，没有发布、提交或暂存任何文件。

## AQ-R16-001 — BLOCKED_USER_DECISION

Codex 稳定账户身份来源仍等待用户选择方向 A 或 B。本轮没有新增 `account/read`，没有从 rate-limit payload、principal、进程或临时 session 推导稳定身份，没有移除 Codex，也没有降低 Gate 0A、多账户 cache/LKG/rate cohort 隔离要求。正式 fetch 与 0A 继续 fail closed；本记录不构成产品签字。

## AQ-R16-002 — FIXED

41-case mutation 合同现已覆盖 runner 的完整实现闭包，而不是只固定顶层 executor 函数。机器合同新增 52 个顶层函数的 source digest、118 条本地调用边和 213 个逐字节外部符号调用目标，并为 34 个 executor 计算 domain-separated closure digest；除 literal `MUTATORS` dispatcher 外，动态 callable 一律拒绝。每条 case 都固定自己的 closure digest、canonical target path、结构化 locator、exact before/after state hash 与 expected failure class，原 41 个 case ID、数量、顺序和 verdict 保持不变。

validator 使用与 runner 分离的 AST 实现独立重建并 exact compare 整个闭包。release gate 也独立验证该闭包，并在隔离 case root 中自行重算 before/after locator state、source input path snapshot、mutated output path snapshot、actual success 与 observed failure class；所有读取都经 canonical RepoPath 和 no-follow traversal。JSON Pointer、text anchor、filesystem、runtime、result-payload locator 均为封闭 discriminator，runtime/result 只能使用 schema 中明确列举的 evidence descriptor。`schema-const` 额外直接断言目标 pointer 从 `core-safety-contract-v1` 变为 `wrong-artifact-id`。

新增 5 个 gate-only helper closure 反例，分别篡改 `save`、`repin`、`subprocess_success`、`observed_failure_class` 和 `recipe_path_snapshot`，保持顶层 executor source 不变；validator 对 5 个反例全部拒绝。保留 mutated case root 的能力只在 gate 设置 `AQ_RELEASE_GATE_EVIDENCE=1` 时开放，不能成为普通 runner 的未授权写入口。

## AQ-R16-003 — FIXED

retention lint 机器合同新增唯一 `retention_entry_registry`，固定 retention table 的完整 heading path、同 section table ordinal、exact headers、ID 列和严格 `RET-*` pattern。validator 现在按 heading level 与 sibling ordinal 计算路径，拒绝重复、移动或相似标题的替代表格；RET ID、surface ID 和 owner cell 都必须是唯一单 Code span，RET ID 全局逐字节唯一。

inventory 的 3 条 owner join 已逐条机器化，分别覆盖 migration temporary claim、migration temporary file 和 observed subject metadata。inventory 与 9 条 live persistence record 的 owner 都必须逐字节命中唯一 RET ID 集；未知 owner、复制 inventory、错误 heading ordinal、重复 RET ID，以及 inventory/record 同时使用未知 owner 的 5 个结构反例全部拒绝。原 43 个 retention fixture、38 个 exact live exception 和 9 条 live record 保持并通过。

## AQ-R16-004 — FIXED

核心机器合同新增唯一 `current_design_status`，记录设计版本、修订轮次、当前 blocker、最新 audit/resolution 路径、处置状态和 gate 状态。README、设计文档、Provider 合同与安全说明都只投影同一个 `AQ-GENERATED-CURRENT-STATUS-V1` canonical one-line JSON block；validator 从核心机器源生成期望字节并对四处 marker block exact compare，旧的当前状态引用不能再与机器事实分叉。

当前状态仍明确为：第 16 轮有一个用户决策 blocker，三项工程缺口已修复，尚未达到 zero issues，也不是 Gate 0A 放行。README 已指向本轮 audit 与本 resolution。

## 验证证据

最终 clean-install gate 输出：

- validator：6 个 meta-schema、8 个 schema instance、117 个 array schema object、13 个 semantic validator、36 个 core fixture、43 个 retention fixture、5 个 retention structural QA、9 个 live persistence record；`status=ok`
- registry anchor：`e133e5cea49549e4af16ecdeb4f55281083da4f66c117345fea42a69e8b51829`
- validator input SHA-256：`a330666d1fede655c98bf1bb691d0eb34a3e886abec6ae068d4a1b9ce80adeb6`
- artifact pin projection SHA-256：`33b72c17feba74eb1dd2c3a9696fde2ebcb1a23ba5b5584f1e5111851288ae74`
- canonical root identity SHA-256：`5a7ed8a03ccdcf9d04e1b2ca9bb4708aea3718c4eb051c3ddebecb70990c6ffc`
- release input SHA-256：`ddd793fe093e236c8f5d2dbceb708b063667746dc502f919bc98140c5f50b768`
- 41-case mutation results SHA-256：`1b755074f8c4b05dd11d7d0ec165cb663dc0b48197b000cfcfc18aeed5d30cdb`；2 个 `none`、8 个 `release-gate-rejection`、31 个 `validator-rejection`
- `clean_install=verified`，validator/projection replay 均 deterministic，`mutation_suite=exact-contract-match`，executor redirect 反例拒绝，5 个 helper closure 反例拒绝，locator/failure evidence 由 gate exact 重算，`source_bytes_unchanged=true`，最终 `status=ok`

执行过的主要命令：

```text
python3 -m py_compile docs/contracts/validate-contracts-v1.py docs/contracts/canonicalize-registry-v1.py docs/contracts/run-validation-mutations-v1.py docs/contracts/run-release-gate-v1.py
node --check docs/contracts/validate-json-schema-v1.mjs
python3 docs/contracts/validate-contracts-v1.py
python3 docs/contracts/canonicalize-registry-v1.py
python3 docs/contracts/run-validation-mutations-v1.py --root .
python3 docs/contracts/run-release-gate-v1.py --root .
```

生产与 Gate 0A 的 tool identity 规则未改变：当前未跟踪 checkout 与本 gate 结果仍仅是 audit evidence，不能自授 release authority；生产仍要求外部签名 release，或 VCS commit + raw tool SHA-256 + 先前受信根授权。

## Source、历史、隐私与 Git

- 修复后 26 个 source 文件（排除 `.git/`、`docs/audits/`、`node_modules/`、`__pycache__`）framed aggregate SHA-256：`26b9366f8215a816e11dff19b5e86f2f1c19c473637ad4e4fd8d4c2e29dc75ac`。
- 写本记录前，第 1–16 轮 audit 与第 1–15 轮 resolution 共 31 个受保护历史文件 framed aggregate SHA-256：`602bcc156427527e6718c887a21c0447fcf59ec58b7d0b5445c57fca3ad97dbc`；逐文件摘要与修复启动值一致。
- 关键文件 SHA-256：README `d36fa499ebff4a86a12ab3998eb8fe129a55eaf9ed53ae5c08d992a35e6bb6dc`；design `0527f93467c51a0a7b8e5f0b46b79fd8dbffb885ee379be91045b9ee7e494343`；provider `b7b19bb793cff028d3be525120d55b766f67f71a31e2d24c49c1871cc1cb25ca`；security `35ba98ad9e9ed8fc11db0a9a1992869dd5c4ac6d8155f84e70c85a7026b627bf`；validator `2955ba2b42737005215b9f105a975e5392e8207ec76f948b319d569a94b97d72`；mutation runner `61ef8bad977a67ed5f639e5bb847add563c594e706e96578422a1f0b0f913089`；release gate `fd2c7c0a7f22d41889167d06bf9f26c42801377608e040e43207012136b17917`；core artifact `eb43181d4fb4ed25280748df3acb179c0e8e50a733c96166134a4bcfc0dd67a6`；retention artifact `bba82a00fdd9f468ea9bfd6b1ee60dd2bba4ec852f20ca98fd7a0beee3e82d70`；contract registry `593cfd34a351d14103ed31a701faa5839265e1c35057498ae13a0b2c6871240c`。
- 本轮未联网，未访问真实账户、Provider、凭据、Hermes、飞书或用户业务数据。mutation 只使用虚构字符串和隔离副本。
- Git 仍为 `No commits yet on main`，文件未跟踪；没有 staged change、commit 或 push。

## 剩余风险与交接

三项工程修复已经通过当前 validator、projection、完整 mutation suite 与 clean-install gate，但不能自行关闭用户决策 blocker，也不能代替下一轮全新的独立 Agent 对当前字节做放行审计。下一步应保持第 1–16 轮 audit 与第 1–15 轮 resolution 只读，由新 Agent 全量复审；只有用户完成 Codex 方向选择并且之后独立审计返回 `PASS_ZERO_ISSUES`，目标才能完成。
