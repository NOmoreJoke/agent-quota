# 第 1 轮审计处置记录

> 处置对象：`README.md`、`docs/design-proposal.md`、`docs/provider-contract.md`、`docs/security-model.md`  
> 修复角色：第 1 轮独立修复 Agent  
> 处置日期：2026-07-18  
> 处置原则：逐项核验证据，只采纳成立问题；设计正文只保留规范，不混入审计过程

## 处置明细

### AQ-R1-001

- 核验结论：成立，采纳。
- 修改位置：`docs/design-proposal.md:140-268`；`docs/provider-contract.md:177-200`。
- 修复摘要：把 subject/capability/freshness/health/source/probe/status 改为封闭枚举；value 使用 discriminator；冻结 kind/value/unit、health/status/空值/freshness、时间、币种唯一性和有限数值矩阵，并统一 `unverified_version`、`reauth_required`、`not_entitled` 的落点。
- 验证方法/结果：静态正反例契约检查确认未知枚举、kind/value 错配、重复币种、非有限数和时间倒序均有唯一拒绝结果；Provider 文档引用同一矩阵。

### AQ-R1-002

- 核验结论：成立，采纳。
- 修改位置：`docs/design-proposal.md:630-648`；`docs/security-model.md:95-117`。
- 修复摘要：`AccountScope` 改为绑定 `(principal,subject)` 与 `(principal,subject,capability)`；构造和服务入口双重核验 registry 父子关系，空 scope/伪造 view/已移动或删除引用统一拒绝且无读取副作用。
- 验证方法/结果：P_A/P_B、S_A/S_B 交叉矩阵的验收条件已写入 `docs/design-proposal.md:889`，不存在独立 subject/capability 列表拼接路径。

### AQ-R1-003

- 核验结论：成立，采纳。
- 修改位置：`docs/design-proposal.md:349-355`；`docs/provider-contract.md:192-200`。
- 修复摘要：冻结 Adapter 返回边界的调用身份、registry、请求子集、唯一性、基数、manifest 和 generation 校验；任一违规整批 `adapter_contract_violation`，禁止部分写缓存/LKG/计数。
- 验证方法/结果：合约测试清单已加入跨 principal/subject、额外/重复 capability、错误 kind/unit/contract/version 反例，并要求所有运行表不变。

### AQ-R1-004

- 核验结论：成立，采纳。
- 修改位置：`docs/design-proposal.md:415-417`；`docs/provider-contract.md:360-365`；`docs/security-model.md:166`。
- 修复摘要：新增覆盖 endpoint、规范 selector、kind/unit/scale、semantic contract、Adapter/API version 的 `query_contract_generation`，加入缓存/LKG/singleflight namespace；generation 在事务内切换并删除旧运行数据。
- 验证方法/结果：逐项改变六类输入的测试已写入 `docs/provider-contract.md:391`；崩溃恢复只能看到切换前或切换后的完整 generation。

### AQ-R1-005

- 核验结论：成立，采纳。
- 修改位置：`docs/design-proposal.md:474-481`；`docs/security-model.md:194`。
- 修复摘要：冻结 purge 允许目标、宿主停止/DB 关闭、随机确认、no-follow 父目录句柄、device/inode 二次核验、逐项删除、未知文件停止和系统备份边界。
- 验证方法/结果：root/home/空路径/`..`/symlink/TOCTOU/owner/mode/mount/跨文件系统/未知文件攻击 corpus 已成为强制验收，全部 fail closed。

### AQ-R1-006

- 核验结论：成立，采纳。
- 修改位置：`docs/provider-contract.md:205-253`；`docs/security-model.md:164`。
- 修复摘要：HTTP 与 local-stdio policy 分型；Codex 固定 install ID、no-follow inode 校验、`shell=False`、最小环境、stdin/stdout/stderr/frame/并发/deadline 上限，以及 TERM→KILL→reap 进程组回收。
- 验证方法/结果：fake stdio 的 PATH/symlink/inode、秘密环境、洪泛、畸形 frame、挂起、fork/zombie 反例已写入契约，且要求其他 Provider 不受阻断。

### AQ-R1-007

- 核验结论：成立，采纳。
- 修改位置：`docs/design-proposal.md:423-430`；`docs/provider-contract.md:368`；`docs/security-model.md:198`。
- 修复摘要：所有渠道统一为绑定 actor/operation/scope 的持久化 at-most-once 键；定义 `prepared/running/completed/failed_safe/outcome_unknown`、结果复用和 24 小时/30 天保留期。
- 验证方法/结果：CLI、飞书文本、卡片、Web 的并发重复、完成后重试和崩溃后重试均已列入合约测试；同键不得产生第二次 Provider 调用或计数副作用。

### AQ-R1-008

- 核验结论：成立，采纳。
- 修改位置：`docs/design-proposal.md:448-459`；`docs/provider-contract.md:339`；`docs/security-model.md:181-190`。
- 修复摘要：分离 principal/subject 的 disable/delete、capability disable 和 `manifest_removed`，逐项冻结 live config、运行数据、刷新预算、审计/幂等/备份和再启用 generation。
- 验证方法/结果：三份设计文档均引用同一生命周期矩阵；快照到期不清基线，refresh ledger 不因删除而绕过，事务与 WAL 崩溃恢复要求明确。

### AQ-R1-009

- 核验结论：成立，采纳。
- 修改位置：`docs/design-proposal.md:278-295`；`docs/security-model.md:146-154`。
- 修复摘要：新增封闭 `LlmMinimalProjection`，只含 schema version、aggregate health、capacity band、freshness band；明确禁止正常/异常数量、主体数和附加字段。
- 验证方法/结果：两份文档都引用同一字段集合；1/2/多主体和 0/1/多异常 golden 序列化必须得到相同无计数 schema。

### AQ-R1-010

- 核验结论：成立，采纳。
- 修改位置：`docs/design-proposal.md:488-505`；`docs/provider-contract.md:152-163`。
- 修复摘要：Codex canonical region 统一为 `local`；DeepSeek 继续为 `global`，二者不混用。
- 验证方法/结果：Codex 示例与认证矩阵均为 `local`；全文上下文检索中 `global` 只对应 DeepSeek/全球 endpoint。

### AQ-R1-011

- 核验结论：成立，采纳。
- 修改位置：`docs/design-proposal.md:498-505`、`docs/design-proposal.md:519-526`、`docs/design-proposal.md:579-585`；`docs/provider-contract.md:80-87`。
- 修复摘要：配置增加必填本地 label 和 enabled；分离 `SubjectConfig/DiscoveredSubject/QuotaSubject`，冻结 NFC、长度、控制/双向字符、确认、所有权和有限 plan_code 规则。
- 验证方法/结果：离线配置与发现确认都有唯一映射；上游 label/plan 未确认或未知时不会自动进入配置、日志或投影。

### AQ-R1-012

- 核验结论：成立，采纳。
- 修改位置：`docs/provider-contract.md:235-249`；`docs/security-model.md:162-163`。
- 修复摘要：冻结结构化 endpoint builder 和 URL 唯一规范化：IDNA A-label、大小写/尾点、端口、禁止 IP/userinfo/fragment、path 编解码/dot segment/分隔符、query allowlist，并在凭据前和发送前双校验。
- 验证方法/结果：恶意 URL corpus 覆盖 IDNA/IP/单双重编码/dot segment/重复斜线/query 注入；只有登记 endpoint 能进入凭据解析。

### AQ-R1-013

- 核验结论：成立，采纳。
- 修改位置：`docs/provider-contract.md:322-339`。
- 修复摘要：按 auth/network/rate-limit/provider/schema/semantic/incompatible/not-authorized 分离计数、暂停、next_allowed 和唯一恢复事件；发布时合约证据改为 manifest `release_assurance_id`，不再要求用户运行时“通过合约测试”。
- 验证方法/结果：交错错误、credential rotate、Adapter generation、普通 probe 和 frozen semantic recovery 的状态结果已由表格唯一决定。

### AQ-R1-014

- 核验结论：成立，采纳。
- 修改位置：`docs/design-proposal.md:736-743`。
- 修复摘要：新增带 generation/window identity 的 `AlertEventKey`、`closed/open/acknowledged/resolved` 状态机、通知/升级/冷却/恢复/reset 条件，以及 SchedulerHost fencing lease。
- 验证方法/结果：虚拟时钟 golden 测试覆盖多策略、重放、重启、窗口轮换、未知时区、LKG、双宿主；未知时间和余额不能生成 reset。

### AQ-R1-015

- 核验结论：成立，采纳。
- 修改位置：`docs/design-proposal.md:875-882`；`docs/provider-contract.md:241`。
- 修复摘要：冻结 2 vCPU/4 GiB、4 principals/8 subjects/16 capabilities/4 批请求的 cold-cache 基准，单 attempt 6 秒、全局 9 秒、30 次 p95 小于 9.5 秒且硬上限 10 秒，并定义部分结果与取消回收。
- 验证方法/结果：测量起止、排队、慢 Provider、缓存清理和超规模公式均明确；单请求 deadline 与产品 SLA 留出聚合余量。

### AQ-R1-016

- 核验结论：成立，采纳。
- 修改位置：`docs/design-proposal.md:303-307`、`docs/design-proposal.md:386-405`；`docs/provider-contract.md:177`、`docs/provider-contract.md:267-273`。
- 修复摘要：生命周期加入规范值 `test_only`；FakeAdapter 使用同一 manifest schema，但禁止用户 entry point、默认发行包和支持计数；未知值仍拒绝。
- 验证方法/结果：设计方案与 Provider 登记统一为 `test_only`，不存在旧的连字符自由拼写。

## 验证证据

- ID 完整性：本文件 16 个问题标题各出现一次，无缺失、重复或额外 ID。
- 交叉契约：枚举、Codex region、Adapter lifecycle、query generation、对象生命周期、`llm_minimal`、purge 与刷新幂等在三份设计文档中使用同一口径。
- 链接：四份现行文档和本记录中的所有相对 Markdown 链接均指向存在的本地文件；外部 HTTPS 参考未作联网可用性声明。
- 占位符：`README.md`、三份现行设计文档和本记录无常见未决标记；路线图中的“待冻结”和未勾选阶段门禁是明确关闭的未来范围，不是本轮遗留占位符。
- 改动范围：仓库无 Git 基线（`No commits yet on main`），因此以 `git status --short --branch`、允许文件清单和 SHA-256 摘要复核；未修改 `docs/audits/round-01-audit.md`。
- 证据边界：当前仓库仍只有设计文档，没有实现、schema 或测试；本轮证明的是规范内部已闭合和验收可执行，不声称运行时测试已经通过。

## 计数

| 处置 | 数量 |
| --- | ---: |
| 已修复 | 16 |
| 拒绝 | 0 |
| 阻塞 | 0 |
| **合计** | **16** |

**结论：ROUND_01_RESOLVED_PENDING_INDEPENDENT_REAUDIT**
