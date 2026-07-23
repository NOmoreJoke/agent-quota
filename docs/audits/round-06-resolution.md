# 第 6 轮审计处置记录

> 处置结论：`RESOLVED_WITH_1_USER_DECISION`  
> 日期：2026-07-18  
> 范围：`README.md`、`docs/design-proposal.md`、`docs/provider-contract.md`、`docs/security-model.md`  
> 实施边界：仓库仍无应用代码；以下 PASS 只证明文档合同与机械检查，不声称运行时实现已经测试

## AQ-R6-001 — BLOCKED_USER_DECISION

- 成立判断：成立。现有只读 allowlist 不能提供稳定 Codex subject/身份，是否增加只读身份 RPC 或更换第二个 MVP Adapter 是互斥产品选择。
- 具体修改：未代替用户选择；没有加入 `account/read`，没有把 Codex 移出 MVP。正文把 Codex identity evidence source 保持未登记，正式 fetch 继续 fail closed，并明确只能由用户解除。
- 最终位置：`README.md:3,32,52`；`docs/design-proposal.md:944,1142,1146`；`docs/provider-contract.md:151,205`；`docs/security-model.md:175`。
- 验证标准/结果：PASS（静态）。allowlist 仍只有握手与 rate-limit read；两条产品路径都未被暗中选定；状态明确仍需全新 Agent 复审。

## AQ-R6-002 — FIXED

- 成立判断：成立。旧正文没有 binding root secret 的唯一可实现持久化 backend，也没有 public salt/key-id、恢复和 purge 精确顺序。
- 具体修改：冻结 anchor-relative `installation-binding-v1.key` raw 32 bytes、owner/mode/no-follow/O_EXCL/fsync/exact-read、partial init、完整集合恢复、最后删除和逐目录 fsync；冻结 public_salt 与 domain-separated key ID recipe。
- 最终位置：`docs/design-proposal.md:1275-1308`；`docs/provider-contract.md:157`；`docs/security-model.md:243`。
- 验证标准/结果：PASS（合同静态）。两实现可按相同 bytes/path/状态机互读；缺失、替换、截断、宽权限、symlink、partial restore 均在 Confidential store 前 fail closed。

## AQ-R6-003 — FIXED

- 成立判断：成立。旧正文只有持久化限流键，没有多进程原子 check-and-reserve 与 crash 计数语义。
- 具体修改：冻结同一 SQLite `BEGIN IMMEDIATE` 的 floor/hour 双检查、`reserved→committed|outcome_unknown`、writer lease/fence、singleflight leader、Provider 前后 crash、429/Retry-After 与对象重建语义。
- 最终位置：`docs/design-proposal.md:1208-1221`；`docs/provider-contract.md:398`；`docs/security-model.md:181`。
- 验证标准/结果：PASS（合同静态）。双进程/虚拟时钟/逐点 kill 的调用上限、unknown 保守计数与 expired reservation 回收规则均唯一。

## AQ-R6-004 — FIXED

- 成立判断：成立。旧 install plan 没有 envelope、签名 domain、trust purpose、sequence/expiry/revocation与完整目标闭包。
- 具体修改：定义 `aq-verified-install-plan-envelope-v1` exact fields/JCS/Ed25519 domain、install_plan key purpose、bundle/sequence/time/revocation、meta/extras/Python ABI/platform、全 wheel/sidecar/依赖闭包和执行前验证顺序。
- 最终位置：`docs/design-proposal.md:1110-1118`；`docs/provider-contract.md:194`；`docs/security-model.md:179`。
- 验证标准/结果：PASS（合同静态）。替换 plan/file/extras/target/signer/sequence或增加文件必须在 import、解包、metadata hook 与 pip 前拒绝。

## AQ-R6-005 — FIXED

- 成立判断：成立。旧 operation/error 联合缺 config/storage/ledger/projection/consent、alert ack、consent change、refresh/idempotency outcome，且 Provider 仍使用旧字段。
- 具体修改：补 actor operation、internal stage、error code、retryable/safe_params/副作用矩阵；增加 alert ack、consent grant/revoke、refresh/idempotency/action success DTO，删除旧 `operation` 构造字段。
- 最终位置：`docs/design-proposal.md:253-390`；`docs/provider-contract.md:116,350-381`；`docs/security-model.md:121,130-139`。
- 验证标准/结果：PASS（合同静态）。全笛卡尔正反例矩阵有唯一合法组合；表外 code/stage/params 在 cache/credential/Provider/ledger 前拒绝。

## AQ-R6-006 — FIXED

- 成立判断：成立。旧安全字段含裸 int/Decimal/timestamp/bytes/process/discovery/concurrency/Retry-After，可能负值、溢出或资源放大。
- 具体修改：新增 `aq-bounds-v1` Annotated/JSON Schema bounds、Decimal 38/18 grammar、UTC/monotonic范围、Retry-After来源/截断、跨字段不变量、checked arithmetic 与 fuzz gate；DTO改用约束类型。
- 最终位置：`docs/design-proposal.md:985-1026`；`docs/provider-contract.md:238`；`docs/security-model.md:172`。
- 验证标准/结果：PASS（合同静态）。边界±1、bool、巨大整数/Decimal/timestamp/signed manifest和overflow均要求在凭据、大分配和进程启动前拒绝。

## AQ-R6-007 — FIXED

- 成立判断：成立。旧 ProbeResult 让 Adapter 返回 core-keyed AccessIdentity，assurance 还是开放字符串。
- 具体修改：Adapter/Credential Source 只可返回封闭、短命、不可 repr/持久化的 IdentityEvidence；core 校验并用 LocalKeyRing 分用途 PRF派生 AccessIdentity；assurance 改为 Literal，Codex source继续未决。
- 最终位置：`docs/design-proposal.md:709-750,936-944`；`docs/provider-contract.md:125-151`；`docs/security-model.md:175`。
- 验证标准/结果：PASS（合同静态）。未知/跨 principal/空/过期 evidence与 Adapter keyed identity 均拒绝；原始 evidence 不进入任何持久化或输出。

## AQ-R6-008 — FIXED

- 成立判断：成立。旧 assurance 使用未定义 canonical，缺 wheel path/mode/duplicate/symlink/carrier/sidecar唯一规则。
- 具体修改：冻结 `aq-assurance-v1` exact entry object、JCS/domain、NFC POSIX path、regular mode、duplicate/symlink拒绝、唯一 manifest/sidecar/RECORD carrier、完整 entry闭包与无自引用 payload投影。
- 最终位置：`docs/design-proposal.md:1077-1087`；`docs/provider-contract.md:194`；`docs/security-model.md:179`。
- 验证标准/结果：PASS（合同静态）。字段重排、Unicode、duplicate path、symlink、mode bit、多 carrier与sidecar bit变化都有唯一 digest/verdict。

## AQ-R6-009 — FIXED

- 成立判断：成立。旧 Codex local-stdio 只有发送顺序，缺连接级 ID correlation 与 incoming frame 状态机。
- 具体修改：冻结 connection-local monotonic ID、唯一 outstanding response、空 incoming notification allowlist、server request/error/EOF/duplicate/orphan/tail处理，以及共享 byte/deadline/process budget。
- 最终位置：`docs/design-proposal.md:1144-1154`；`docs/provider-contract.md:184`；`docs/security-model.md:173`。
- 验证标准/结果：PASS（合同静态）。fake stdio 必须覆盖通知前插、错/重复 ID、error/server request、EOF、partial/multiple/tail frame且 orphan=0。

## AQ-R6-010 — FIXED

- 成立判断：成立。旧 schema 暴露未设计的 HTTP POST 和 proxy true 分支。
- 具体修改：schema v1 `HttpEndpointSpec.method` 只允许 GET，`allow_proxy` 恒 false；body/proxy/custom CA在 Credential Source 前离线拒绝。
- 最终位置：`docs/design-proposal.md:615-645`；`docs/provider-contract.md:228-238`；`docs/security-model.md:172-173`。
- 验证标准/结果：PASS（合同静态）。DeepSeek GET正例保留；POST/代理配置的凭据解析与Provider调用计数必须为0。

## AQ-R6-011 — FIXED

- 成立判断：成立。旧 plan_code 有展示/映射承诺，却没有 Adapter observation、确认、更新、retention或generation路径。
- 具体修改：新增有限 SubjectMetadataObservation；定义known初次确认、known变化pending+维护告警、unknown/null丢弃、无自由文本、唯一retention ID、planner确认与subject/query generation切换。
- 最终位置：`docs/design-proposal.md:838-850,955-957,1189`；`docs/provider-contract.md:90`；`docs/security-model.md:220,275`。
- 验证标准/结果：PASS（合同静态）。known/unknown/null/change各有唯一落点；未知不落盘，变化未确认不改config/cache/LKG。

## AQ-R6-012 — FIXED

- 成立判断：成立。旧重复键没有currency dimension，导致同wallet不同币种的balance_floor互相冲突。
- 具体修改：policy identity冻结为 `(subject,capability,metric,dimension)`；balance dimension=currency，counter=unit，window固定；同dimension重复拒绝，不同币种独立且不求和，severity仍聚合到同capability episode。
- 最终位置：`docs/design-proposal.md:1389-1441,1615`；`docs/provider-contract.md:56-92`。
- 验证标准/结果：PASS（合同静态）。CNY/USD可并存并独立命中/清除，同币种重复拒绝，多币种永不相加。

## AQ-R6-013 — FIXED

- 成立判断：成立。旧并发只有概念性限制，attempt数量、公平队列、取消和部分结果不唯一。
- 具体修改：v1固定MaxAttempts=1、跨进程global=4、Provider=1..4、pending=32、SQLite lease slots、Provider内FIFO/global oldest-eligible、公平跳过、取消/crash回收、9秒parent与10秒投影边界。
- 最终位置：`docs/design-proposal.md:1223-1229`；`docs/provider-contract.md:399`；`docs/security-model.md:181`。
- 验证标准/结果：PASS（合同静态）。大配置不建无界task；429/5xx不自动重试；慢请求只生成确定partial result且无orphan。

## AQ-R6-014 — FIXED

- 成立判断：成立。旧 Codex comparator/normalize只有名称，没有stdout grammar、pre-release/build和golden vectors。
- 具体修改：冻结64-byte single-line ASCII grammar、LF/CRLF、三段无前导零整数、拒绝pre-release/build、多行/非ASCII、tuple比较、canonical range与golden vectors。
- 最终位置：`docs/design-proposal.md:1124-1128`；`docs/provider-contract.md:184`。
- 验证标准/结果：PASS（合同静态）。构建器、probe、range validator和bundle hash必须共用同一normalize/comparator。

## AQ-R6-015 — FIXED

- 成立判断：成立。旧 frozen DTO 内仍有可变dict/list，不能阻止Adapter或consumer通过保留引用修改。
- 具体修改：display params、safe params、selector candidate、projection rows和alert source改canonical tuple；所有跨不可信边界nested collection先有界深拷贝再重建core-owned immutable模型，明确frozen不等于深冻结。
- 最终位置：`docs/design-proposal.md:248,284,404,818,936`；`docs/provider-contract.md:161`；`docs/security-model.md:169`。
- 验证标准/结果：PASS（合同静态）。return后的原dict mutation、后台并发mutation和consumer mutation不得改变hash/序列化/提交值。

## AQ-R6-016 — FIXED

- 成立判断：成立。旧泛型别名在最低Python版本会NameError。
- 具体修改：使用Python 3.11可执行 `TypeAlias` 声明并显式列出Generic/TypeAlias/TypeVar import；禁止下标赋值旧写法与Python 3.12-only语法。
- 最终位置：`docs/design-proposal.md:293,331-359`。
- 验证标准/结果：PASS（合同静态）。最低Python版本可import并对success/error联合生成schema；实现阶段仍需mypy/pyright/Pydantic实测。

## AQ-R6-017 — FIXED

- 成立判断：成立。旧设计/集成章节重复consent、action和card idempotency的具体期限。
- 具体修改：retention数值只保留在安全模型唯一表，action数值只保留在唯一ACTION_TTL定义；其他正文只引用RET ID/常量，并定义Markdown AST `retention-source-lint-v1`防止复制。
- 最终位置：`docs/security-model.md:199-223,249`；`docs/design-proposal.md:424,1503,1558,1807`。
- 验证标准/结果：PASS（静态扫描）。live docs 中目标期限字面量只命中唯一表、唯一action定义和非retention频率常量。

## 最终统计

- fixed: 16
- rejected: 0
- blocked_user_decision: 1
- total: 17
- 下一门禁：用户作出唯一剩余产品选择后，仍需一名全新的独立 Agent 从零全量复审；当前处置记录不宣告零问题或0A通过。
