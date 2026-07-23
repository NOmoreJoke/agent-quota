# 第 15 轮修复处置记录

- 修复日期：2026-07-18（Asia/Shanghai）
- 处置结论：`PARTIAL_FIXED_PENDING_USER_DECISION_AND_FRESH_AUDIT`
- 范围：仅修复第 15 轮两项可直接修复的验证合同缺口；没有替用户选择 Codex 产品方向，没有发布、提交或暂存任何文件。

## AQ-R15-001 — BLOCKED_USER_DECISION

Codex 稳定账户身份来源仍等待用户选择方向 A 或 B。本轮没有新增 `account/read`，没有从 rate-limit payload、principal、进程或临时 session 推导稳定身份，没有移除 Codex，也没有降低 Gate 0A、多账户 cache/LKG/rate cohort 隔离要求。正式 fetch 与 0A 继续 fail closed；本记录不构成产品签字。

## AQ-R15-002 — FIXED

持久化声明升级为自含 `surface_id + operation + owner_id` 的独立 Code-span record v1：`persist:v1:<surface_id>:<operation>:<owner_id>`。validator 只把该 Code span 本身视为规范记录，逐个移除 exact record 后重新扫描同一 Pandoc leaf；任何剩余 ordinary persistence signal 仍独立拒绝，不能再因 leaf 中存在任意合法 record 而放行。owner 必须逐字节命中 inventory 的唯一生命周期源，未知 surface、旧格式、未知 operation、owner mismatch、重复 record 均 fail closed。现有 9 条 live 声明已原子迁移，原 38 条 retention fixture 全部保留，并增加 5 条 record-boundary fixture，总数 43；没有增加宽泛 exception，既有 38 个 exception 仍是逐 path/leaf digest 精确绑定。

对抗性复核实际得到：legal A record 加未登记 B local-file/token 同 leaf、跨句、同句多 surface、中文同义、一个 record 覆盖两个 signal 的 5 个 case 全部输出 `reject`。`live-security-local-file-persistence` 的固定 41-case recipe 也改为把 B 声明注入已有 A record 的同一 leaf，完整 mutation suite 证明该分支非零拒绝。

## AQ-R15-003 — FIXED

`core-safety-contract-v1#/validation_mutation_contract` 的 41 条 case 保持原 ID、数量、顺序和 expected verdict，同时每条 recipe 新增并纳入 domain-separated `mutation_sha256`：canonical `repo_paths`、结构化 operation/locator、expected before/after、expected failure class、expected repository effect、executor ID 与 executor source-segment implementation SHA-256。普通 JSON/text/filesystem case 具有 JSON Pointer 或文本/文件锚点；gate/runtime/result case 由同一外部机器合同固定 executor recipe ID 与实现摘要。

runner 逐 case 输出实际 `source_input_sha256`、`applied_recipe_sha256`、`executor_id`、`executor_implementation_sha256`、`mutated_output_sha256`、`observed_failure_class` 与 verdict。validator 和 release gate 都独立解析 runner AST，要求 literal `MUTATORS` 与 `EXECUTOR_BY_CASE` 映射逐 case 等于机器合同，并从函数 source segment 重新计算 implementation digest；gate 还从 clean-install case root 重新计算 input digest，exact compare recipe/executor/failure evidence，并校验 expected changed/unchanged effect。

新增 test-only redirect preflight：只有显式 `AQ_MUTATION_RECIPE_SELF_TEST=1` 才能请求，`schema-const=artifact-unknown` 实际退出 1，错误为 `mutation_runner_error=executor mapping mismatch:schema-const`。完整 release gate 在正式 41-case suite 前固定执行并要求该反例失败，因此两个预期均为 rejection 的 executor 互换也不能静默通过。

## 验证证据

最终 clean-install gate 输出：

- validator：6 个 meta-schema、8 个 schema instance、108 个 array schema object、13 个 semantic validator、36 个 core fixture、43 个 retention fixture、9 个 live record；`status=ok`
- registry anchor：`17a839e52871f3165aacd6c8a1426e1f445dc257d88ba8da46bf4faaca82cf0f`
- validator input SHA-256：`a15152fb2e96391309b67246648e9c475a89129cb40d725e2dc2f051ee073641`
- artifact pin projection SHA-256：`da6294910e92027c984b9674def141ef703e1337ca70fbd1f8952e159362ebce`
- release input SHA-256：`514021e50a915c6a87f3c2504f933872600e5bb92cfd532c0c25b875a6245b3f`
- 41-case mutation results SHA-256：`34e831b5455d21c9836c84a7ebd511c4cece4118a5be5f53cf5a4d8caa6fcf45`
- `clean_install=verified`，validator/projection 双次 replay 均 deterministic，`mutation_suite=exact-contract-match`，`mutation_executor_redirect_self_test=verified-rejected`，`source_bytes_unchanged=true`，最终 `status=ok`

执行过的主要命令：

```text
python3 -m py_compile docs/contracts/validate-contracts-v1.py docs/contracts/canonicalize-registry-v1.py docs/contracts/run-validation-mutations-v1.py docs/contracts/run-release-gate-v1.py
node --check docs/contracts/validate-json-schema-v1.mjs
python3 docs/contracts/validate-contracts-v1.py
python3 docs/contracts/canonicalize-registry-v1.py
python3 docs/contracts/run-validation-mutations-v1.py --root .
python3 docs/contracts/run-release-gate-v1.py --root .
AQ_MUTATION_RECIPE_SELF_TEST=1 python3 docs/contracts/run-validation-mutations-v1.py --root . --self-test-redirect-executor schema-const=artifact-unknown
```

生产与 Gate 0A 的 tool identity 规则未改变：当前未跟踪 checkout 与本 gate 结果仍仅是 audit evidence，不能自授 release authority；生产仍要求外部签名 release，或 VCS commit + raw tool SHA-256 + 先前受信根授权。

## Source、历史、隐私与 Git

- 修复后 26 个 source 文件（排除 `.git/`、`docs/audits/`、`node_modules/`、`__pycache__`）framed aggregate SHA-256：`4b2b9962e20f747158c5f77c8d1894c163ee66e04edec764922af24dd875c953`。
- 写本记录前，第 1–15 轮 audit 与第 1–14 轮 resolution 共 29 个受保护历史文件 framed aggregate SHA-256：`505fe94c3300aac35abccb1d6bbeb4a05f18ddecaf2ca59bd46877d06ecadd72`；逐文件摘要与修复启动值一致。
- 关键文件 SHA-256：README `835ad4fbd773ed994b7d2a8336bacf89a7b517f82cba0d123b7b5b36dc31d849`；design `9e0026ad2f01d0778c4099cebb870c8f8f331271697c3292c44342a679258459`；provider `c026e582f29f5671e2d62e5b29fc44eaa8a3523bdc6e29dfb7a5b8f54d150b83`；security `b5ed33e417eaa74d277e7b779ea71c335d93b39e9d8255018933a84f18f62b9d`；validator `2a37c1915553215ea57aa7ee305a3751be7920783dfe55734ce9caf8d4a9b4e7`；mutation runner `24919ce2abd01359528e3080cb1a1b229ce80a36faa89eb02c5bf4caa76699fa`；release gate `bd81be42f7fefa68c83603ffd0c290125917832c972677d395b06263e4337148`。
- 本轮未联网，未访问真实账户、Provider、凭据、Hermes、飞书或用户业务数据。临时 mutation 仅使用虚构字符串和隔离副本。
- Git 仍为 `No commits yet on main`，文件未跟踪；没有 staged change、commit 或 push。

## 剩余风险与交接

两项工程修复已经通过当前 validator、projection、完整 mutation suite 与 clean-install gate，但不能自行关闭用户决策 blocker，也不能代替下一轮全新的独立 Agent 对当前字节做放行审计。下一步应保持本轮历史只读，由新 Agent 全量复审；只有用户完成 Codex 方向选择并且之后独立审计返回 `PASS_ZERO_ISSUES`，目标才能完成。
