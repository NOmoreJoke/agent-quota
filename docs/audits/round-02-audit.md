# 第 2 轮独立对抗性审计

> 审计日期：2026-07-18  
> 审计对象：`README.md`、`docs/design-proposal.md`、`docs/provider-contract.md`、`docs/security-model.md`  
> 审计方式：全新 Agent 从零全量审计，只读核验正文与当前官方/本机协议；未读取 `docs/audits/` 下任何上一轮审计或处置记录  
> 最终结论：`FAIL_WITH_14_ISSUES`

## 1. 结论与计数

本轮发现 14 项可执行问题：

| 严重度 | 数量 |
| --- | ---: |
| 阻断 | 1 |
| 高 | 5 |
| 中 | 8 |
| 低 | 0 |
| 合计 | 14 |

存在阻断项。当前文档不能通过阶段 0A 的“零问题”门禁，也不能宣称 Codex 已具备进入 Supported 候选所需的稳定访问身份契约。

## 2. 审计范围与验证方法

本轮从零检查了以下方面：

- 需求完整性、阶段范围和 MVP 退出条件。
- principal/subject/capability/snapshot 数据模型与封闭状态矩阵。
- 配置迁移、对象删除、缓存代际、singleflight、限流 cohort 和刷新幂等。
- Adapter 边界、发现流程、HTTP/local-stdio 出口、当前 Codex app-server 协议和 DeepSeek 官方余额协议。
- 授权、凭据、日志、投影、飞书/LLM/Web 披露边界。
- 告警状态机、失败恢复、性能门禁、打包与干净环境验收。
- 跨文档冲突、不可实现的原子性要求、遗留占位符和不可验证验收标准。

本仓库尚无应用代码，因此本轮能验证的是“设计是否自洽并可实现”，不能把尚未运行的实现或测试写成已通过。

## 3. 当前协议证据

### 3.1 Codex 本机官方协议

在当前机器执行：

```bash
codex --version
codex app-server generate-json-schema --experimental --out <temp-dir>
```

得到：

- CLI：`codex-cli 0.142.5`。
- 生成的 `codex_app_server_protocol.v2.schemas.json` SHA-256：`b760fd4e54deca9aabdf3e21c8f89b6f8595ccf3295b6df73df636a042003d5b`。
- `account/rateLimits/read` 的请求参数为 `null`；响应含 `rateLimits`、可选 `rateLimitsByLimitId` 和重置积分摘要，但没有账户 ID、会话 ID或登录代际。
- `initialize` 响应只有 `codexHome`、`platformFamily`、`platformOs`、`userAgent`，也没有账户/会话代际。
- `account/read` 是另一个只读 RPC，ChatGPT 账户分支可返回 `email` 与 `planType`；但是当前设计的业务 RPC allowlist 明确只允许 `account/rateLimits/read` 加握手，禁止其他方法。
- 当前 npm 安装入口是指向 `codex.js` 的符号链接；包内另有可直接执行的受版本约束原生 Mach-O 二进制，因此“登记原生二进制”本身可行，问题不在是否能启动进程，而在允许方法无法提供文档要求的稳定身份材料。

### 3.2 DeepSeek 官方协议

[DeepSeek 官方 Get User Balance](https://api-docs.deepseek.com/api/get-user-balance/) 当前说明：

- 方法为 `GET /user/balance`。
- 响应顶层含 `is_available`，表示余额是否足以调用 API。
- `balance_infos[]` 每项含 `currency`、`total_balance`、`granted_balance`、`topped_up_balance`；币种枚举为 CNY/USD。
- 官方语义说明 `total_balance` 包含赠送余额和充值余额。

## 4. 问题清单

### AQ-R2-001 — 阻断 — Codex 的稳定身份要求无法由允许的 RPC 满足

**定位**

- `docs/design-proposal.md:347`：零 binding official-cli 必须从受信任协议取得可验证、非秘密的账户/会话代际，否则不得正式 `fetch`。
- `docs/design-proposal.md:764`：Codex 业务 RPC 只允许 `account/rateLimits/read` 加初始化握手。
- `docs/design-proposal.md:847`、`docs/design-proposal.md:892`：Codex Supported 门禁要求 verified stable session identity。
- `docs/provider-contract.md:150`、`docs/provider-contract.md:173-184`、`docs/provider-contract.md:188`：重复要求稳定账户/会话代际，同时禁止 `account/read` 等其他 RPC。

**反例**

在 Codex 0.142.5 中，允许的 `initialize` 和 `account/rateLimits/read` 都不返回账户 ID、会话 ID 或登录代际。两个不同 ChatGPT 账户若恰好拥有相同套餐和相同额度窗口，Adapter 看到的允许字段可以完全相同，无法生成既稳定又能区分账户切换的 `cache_identity`。协议虽有 `account/read`，但设计的发送端 allowlist 会在发送前拒绝它。

**原因与影响**

这是一个闭环矛盾：门禁要求一个输入，但安全策略禁止唯一可能提供账户信息的额外只读方法，而当前允许响应本身没有该输入。按文档 fail closed 后 Codex 永远不能成为 Supported；阶段 2 又要求至少两个真实 Supported Adapter，当前首选组合因而被阻断。

**修复建议**

二选一并冻结为规范：

1. 在明确的数据最小化契约下允许 `account/read`，把账户字段仅在内存中做带域分离的 keyed identity，立即丢弃原文，并重新定义“账户切换/同账户重登”时缓存失效规则；或
2. 保持现有 allowlist，把 Codex 降为 Experimental，并选择另一个能提供稳定身份的第二个 MVP Supported Adapter。

不得继续声称现有允许方法可返回当前 schema 中不存在的“非秘密会话代际”。

**可验证验收条件**

- 对实际支持的最低/最高 Codex 版本生成 schema fixture，证明身份材料来自允许方法且字段存在。
- A 账户 → B 账户切换必须改变 `cache_identity`，旧缓存/LKG 不可读；同一账户的规则必须按冻结契约可预测。
- 原始邮箱/账户字段不进入配置、SQLite、WAL、日志、异常或投影。
- 如果选择降级，MVP 文档另行指定并验证第二个 Supported Adapter，且所有退出条件同步更新。

### AQ-R2-002 — 高 — FakeAdapter 被禁止进入发行物，却又是干净安装验收的必需组件

**定位**

- `docs/design-proposal.md:390`：`test_only` Adapter 禁止进入默认 wheel/sdist/meta distribution。
- `docs/design-proposal.md:474`：从本地构建产物安装 `agent-quota[deepseek,codex]` 后要求用 Fake fixture 查询组合。
- `docs/design-proposal.md:835-842`：阶段 1A 依赖 FakeAdapter 并要求构建 core/CLI wheel 与 sdist 后查询。
- `docs/provider-contract.md:177`、`docs/provider-contract.md:273`：再次禁止 FakeAdapter 进入默认发行物和用户 entry point。

**反例**

在无源码 checkout 的全新虚拟环境只安装文档列出的 `agent-quota[deepseek,codex]`。按照生命周期规则，环境中不能包含 FakeAdapter；按照安装验收，又必须加载 Fake fixture。两项不能同时成立。

**原因与影响**

发行矩阵没有定义 testkit 包、测试 extra 或仅 CI 可安装的 FakeAdapter artifact。阶段 1A 的主要端到端证据因此不可复现。

**修复建议**

定义独立的 `agent-quota-testkit`/`test` extra，或把 FakeAdapter 作为 core 内部测试实现但禁止注册到用户 Adapter entry point。明确哪一个构建产物进入干净环境、生产 meta 包为何不会依赖它。

**可验证验收条件**

- 从明确列出的 artifacts 在无源码环境完成 Fake 多组合查询。
- 安装普通生产 `agent-quota` 后，用户 Adapter 列表和 entry point 中不存在 FakeAdapter。
- CI 分别证明 testkit 可用与生产依赖闭包不含 testkit。

### AQ-R2-003 — 高 — `probe/discover` 返回运行时对象，绕过了发现确认和联网授权边界

**定位**

- `docs/design-proposal.md:325-342`：`ProbeResult.subjects` 为 `QuotaSubject`，`discover_subjects()` 也返回 `QuotaSubject`；`probe()` 没有 `allow_network` 参数。
- `docs/design-proposal.md:345-347`：只有用户允许联网后才能发现，发现结果必须待确认。
- `docs/design-proposal.md:581`：`DiscoveredSubject` 与 `QuotaSubject` 必须分离，ID/label 只能在用户确认后由 core 生成。
- `docs/provider-contract.md:24`、`docs/provider-contract.md:85-86`、`docs/provider-contract.md:179-186`：重复规定显式联网、待确认和 probe 返回发现对象。

**反例**

恶意或有缺陷的 Adapter 在 `probe()` 中联网枚举工作区，直接返回带自己生成 `aqs_...` ID 和上游 label 的 `QuotaSubject`。接口类型允许这样做，而且 `probe()` 没有联网许可参数。core 无法只靠类型区分“未确认候选”与“已注册运行对象”。

**原因与影响**

规范同时定义了两套相反边界：文字要求 Adapter 只能返回临时候选，接口却要求正式对象。这会破坏 core 生成 ID、用户拥有 label、发现最小披露和离线 `config validate` 的可测试性。

**修复建议**

把接口改为封闭的 `DiscoveredSubject/DiscoveredCapability` DTO，只允许本次命令 opaque handle、manifest kind、受 schema 约束 selector 候选和经转义建议 label。为 `probe` 明确 `offline|local_only|network_allowed` 策略；离线配置验证不得解析凭据或访问 Provider。确认事务才由 core 生成正式 ID/label/registry 记录。

**可验证验收条件**

- 离线 `config validate` 的网络和 Credential Source 调用计数均为 0。
- Adapter 返回正式 ID、控制字符 label、未声明 selector 或未获网络许可时整批拒绝且配置不变。
- 用户确认前重启不会留下正式 subject；确认后 ID 只能由 core 生成。

### AQ-R2-004 — 高 — TOML 配置与 SQLite 运行状态被要求进行不可实现的“单数据库事务”

**定位**

- `docs/design-proposal.md:416`：配置迁移要求在单一事务安装 active generation 并删除旧运行数据。
- `docs/design-proposal.md:459`：要求“active generation/config 更新”与全部运行数据删除在一个数据库事务中，崩溃后只能看到完整前态或后态。
- `docs/design-proposal.md:474`、`docs/design-proposal.md:585`：权威配置仍是 platformdirs 下的版本化文件，正式迁移采用原子文件写入和限时备份。
- `docs/provider-contract.md:24`、`docs/provider-contract.md:89`、`docs/provider-contract.md:365`：Registry 读取显式配置文件，同时要求 generation 在单事务切换。

**反例**

先原子替换 `config.toml`，再提交 SQLite：两步之间断电会得到新配置 + 旧运行状态。先提交 SQLite，再替换文件：断电会得到旧配置 + 新 generation。SQLite 事务不能把文件系统 rename 纳入同一个 ACID 提交。

**原因与影响**

文档没有指定唯一权威存储、迁移 journal、恢复标记或两阶段协调算法，却要求跨两种介质达到单数据库事务语义。实现无法证明崩溃恢复门禁。

**修复建议**

选择并规范一种可实现模型：SQLite 成为 active config 的唯一权威、TOML 只做导入导出；或设计持久化 migration journal（旧/新配置 digest、阶段、fsync/rename 顺序、幂等恢复）并明确每个崩溃点的恢复方向。

**可验证验收条件**

- 对文件写入前后、DB commit 前后、rename 前后和 checkpoint 前后逐点 kill。
- 每次重启都自动收敛到一个有明确定义的前态或后态，不出现启用引用指向旧/半删 generation。
- 恢复算法幂等，连续重启不会扩大删除或丢失可恢复配置。

### AQ-R2-005 — 高 — 告警状态机无法处理“恢复后再次告警”

**定位**

- `docs/design-proposal.md:736`：状态机被限定为 `closed→open→acknowledged→resolved`。
- `docs/design-proposal.md:738-740`：定义首次告警和恢复，但没有 `resolved→open` 或新 episode 规则。
- `docs/design-proposal.md:743`：虚拟时钟测试要求覆盖恢复，却未覆盖同 key 再次恶化。

**反例**

余额 capability 使用稳定的 `window_identity=non_resetting`：余额跌破阈值，事件变为 open；充值后 resolved；再次消费后又跌破阈值。`AlertEventKey` 完全相同，但状态机没有从 resolved 回到 open 的合法路径。相同问题也会出现在同 generation 下反复发生的 network/auth health 告警。

另一个反例：网络错误产生 warning 后，Provider 成功返回 `fresh+unsupported`。最终 severity 已是 none，但当前规则只允许 `fresh+ok` 进入 resolved，旧告警会永久悬挂。

**原因与影响**

事件 key 表示告警维度，不表示一次独立 episode。单向状态机把第一次 resolved 变成终态，且恢复条件把“无告警”错误收窄为 `health=ok`。

**修复建议**

允许 `resolved→open` 并增加单调 `episode_id`，或每次重新进入告警时生成明确的新 episode key。恢复应由冻结后的最终 severity/终止状态驱动，并定义 disable/delete/manifest generation 切换如何关闭旧事件。

**可验证验收条件**

- 虚拟时钟覆盖 open→resolved→open→resolved，第二次恶化只通知一次。
- 覆盖 balance/non-resetting、已知重置窗口、health 错误、unsupported、generation 切换和对象删除。
- 双 SchedulerHost 与崩溃接管不会把一个 episode 重复生成。

### AQ-R2-006 — 高 — DeepSeek Supported 契约丢失官方可用性信号

**定位**

- `docs/design-proposal.md:203-206`：余额模型只保存币种和三类金额。
- `docs/design-proposal.md:396-401`、`docs/design-proposal.md:844-848`：DeepSeek 被定义为首批 Supported 候选，仅登记多币种余额。
- `docs/provider-contract.md:271-278`：只登记 `wallet-balances`。
- `docs/design-proposal.md:890-891`：MVP 验收要求无损表达额度状态和真实 Adapter。

**反例**

DeepSeek 官方响应为 `is_available=false`，同时 `balance_infos` 仍有非负金额。现有契约没有 `wallet-availability` capability，也没有规定映射到哪个 `health/status_code`。一种实现会只显示余额，看起来正常；另一种会自创错误状态。两者都可能通过当前余额 fixture。

官方还说明 `total_balance` 包含 `granted_balance + topped_up_balance`，但通用模型只检查三者非负，不要求 DeepSeek 的组成关系；解析错列也可能被接受。

**原因与影响**

设计只建模“有多少钱”，没有建模 Provider 明确提供的“能否调用”。这会让用户在最需要额度工具时得到误导性正常结果。

**修复建议**

为 DeepSeek 冻结一个状态 capability，或明确 `is_available` 到现有封闭状态的唯一映射；同时在 DeepSeek `SemanticContract` 中冻结金额字符串解析、币种、组成关系和容差（若官方存在舍入例外，也要明确）。

**可验证验收条件**

- fixture 覆盖 true/false、CNY/USD、空/重复币种、金额错列和 `total != granted + topped_up`。
- 每种输入得到唯一、文档化的 snapshot/health/status 组合。
- `is_available=false` 不会渲染成“可正常调用”。

### AQ-R2-007 — 中 — AdapterManifest 缺少后续强制校验所需的机器字段

**定位**

- `docs/design-proposal.md:303-318`：规范性 `AdapterManifest` 只有 `adapter_api_version`，没有 `adapter_version`、测试版本边界、schema hash 或 `release_assurance_id`。
- `docs/design-proposal.md:354`、`docs/design-proposal.md:415`：返回校验和 query generation 又必须使用 `adapter_version`。
- `docs/provider-contract.md:177-188`：要求机器可读测试版本范围和 Codex schema hash。
- `docs/provider-contract.md:332-337`：schema/semantic pause 只能由新的 `release_assurance_id` generation 恢复。

**反例**

两个包具有相同 `adapter_api_version`，但解析逻辑和 fixture 证据不同。由于 manifest schema 没有规范的包版本/assurance 字段，core 无法按文档判断 snapshot 的 `adapter_version` 是否匹配，也无法证明恢复使用了“带新 assurance 的 generation”。

**原因与影响**

文字要求的数据没有进入封闭机器契约，导致实现只能从包元数据猜测或增加私有字段。不同 Adapter 会生成不兼容的 generation 和恢复行为。

**修复建议**

补全严格 manifest schema：至少加入规范 `adapter_version`、`tested_protocol_min/max`、可选 schema hash、`release_assurance_id`、其生成算法/信任来源和对 query generation 的参与规则。说明缺失字段在各 lifecycle 下是拒绝还是降级。

**可验证验收条件**

- 严格 schema 拒绝 Supported Adapter 缺少任一必需字段。
- 逐项改变 adapter version/schema hash/assurance，generation 必须变化且旧 LKG 不可见。
- 普通 probe 成功不能解除 schema/semantic pause；新 assurance 的正确构建才可解除。

### AQ-R2-008 — 中 — `missing_reasons` 使用自由字符串，绕过了封闭枚举和不可信 Adapter 校验

**定位**

- `docs/design-proposal.md:325-331`：`ProbeResult.missing_reasons: dict[str, str]`。
- `docs/design-proposal.md:349-355`：声称所有 Adapter 返回会整批校验，但列出的校验没有约束 missing reason 的 key/value。
- `docs/design-proposal.md:268-270`：其他上游未知字符串必须拒绝。
- `docs/provider-contract.md:185`、`docs/provider-contract.md:190`：文字只允许四种稳定 missing reason。
- `docs/provider-contract.md:194-200`：Adapter 返回边界仍未列 missing reason 校验。

**反例**

Adapter 返回 `{"unknown-account@example.com": "token expired; run <script>"}`。类型完全合法；若 doctor/CLI 为解释缺失能力而显示或记录该字典，就会泄露账户标识并把不可信文本送入输出渠道。

**原因与影响**

封闭枚举只写在说明文字里，接口却暴露两个自由字符串，且整批校验遗漏它们。这直接破坏提示注入/PII 防线。

**修复建议**

定义 `MissingReasonCode` Literal/Enum；key 只能是 manifest capability ID 或本次发现 opaque handle，并设置条目数/长度上限。把它加入 Adapter 整批原子校验和本地模板映射。

**可验证验收条件**

- 未知 code、邮箱/外部 ID key、重复/悬空 capability 和超量字典整批拒绝。
- 恶意字符串不会进入快照、日志、doctor、CLI、飞书或 LLM。
- 四种允许原因都有唯一的本地文案和落点。

### AQ-R2-009 — 中 — 多个强制错误没有合法、唯一的数据契约落点

**定位**

- `docs/design-proposal.md:148-163`：`Health` 与 `LocalStatusCode` 的封闭枚举。
- `docs/design-proposal.md:256-268`：snapshot 状态矩阵没有定义 `adapter_contract_violation`、`local_protocol_violation`、`local_process_timeout` 的 health/freshness/value 组合。
- `docs/design-proposal.md:349-355`：要求整批返回 `adapter_contract_violation`，但没有定义它是异常、操作结果还是 snapshot。
- `docs/provider-contract.md:110`：要求返回 `credential_backend_unavailable`，该值不在上述封闭枚举。
- `docs/provider-contract.md:251-253`：local-stdio 超限映射到两个本地状态，但错误矩阵 `docs/provider-contract.md:341-351` 没有它们。

**反例**

Codex stdout frame 超限。实现 A 返回 `health=provider_error + local_protocol_violation`；实现 B 返回 `health=schema_changed`；实现 C 抛出操作级异常。当前矩阵无法判断哪一个合规。系统凭据后端不可用时更没有合法 snapshot/status 值。

**原因与影响**

文档混用了 capability snapshot、probe 结果和操作级错误，却没有一个封闭的 `OperationResult/OperationError` 契约。所谓“未知组合一律拒绝”会连规范要求的错误也一起拒绝。

**修复建议**

明确哪些错误属于 snapshot，哪些属于 probe/config/credential/refresh 操作结果；为每个表面定义封闭 union、稳定错误码、是否允许 LKG、是否更新失败计数和安全渲染模板。不要把所有错误硬塞进 `CapabilitySnapshot`。

**可验证验收条件**

- 为每个已声明错误码给出唯一合法对象示例和反例。
- frame 超限、进程超时、Adapter 越界、凭据后端缺失均通过严格序列化测试。
- 任一错误的缓存/LKG/失败计数副作用可由表驱动测试断言。

### AQ-R2-010 — 中 — “按用户时区展示”没有任何时区输入来源

**定位**

- `docs/design-proposal.md:85-87`：要求展示层转换为用户时区。
- `docs/design-proposal.md:276-295`：投影模型没有 presentation timezone。
- `docs/design-proposal.md:483-577`：schema v1 配置没有全局/actor 时区字段。
- `docs/design-proposal.md:627-646`：`AccessContext` 没有 locale/timezone。
- `docs/design-proposal.md:895`：MVP 验收要求按用户时区转换。

**反例**

服务运行在 Asia/Shanghai，但飞书操作者位于 America/Los_Angeles；或 CLI 在容器中系统时区为 UTC。相同 UTC reset time 应显示成哪个时区没有规范输入。实现只能猜系统时区，无法证明“用户时区”验收。

**原因与影响**

存储 UTC 已定义，但显示转换缺少 IANA timezone 的来源、优先级、校验和 DST 规则。这会造成错误重置时间和跨渠道不一致。

**修复建议**

增加渠道无关 `PresentationContext(timezone_id)` 或明确本地配置/actor profile 的 IANA timezone；定义缺失/非法时 fail closed 到 UTC 并明确标注，不得猜固定偏移。时区只影响渲染，不进入授权或快照身份。

**可验证验收条件**

- 同一 UTC 快照在 UTC、Asia/Shanghai、America/Los_Angeles 得到确定结果。
- DST 跳变、非法 timezone、缺失 profile 有 golden test。
- CLI/飞书/Web 使用相同转换函数，未知上游时区仍不生成 `resets_at`。

### AQ-R2-011 — 中 — 删除和迁移规则把互斥行为留给实现自由选择

**定位**

- `docs/design-proposal.md:455-457`：subject delete、capability disable 允许“自动修正引用或拒绝事务”两种行为。
- `docs/design-proposal.md:585`：旧敏感/非 opaque ID 可“拒绝或迁移”。
- `docs/provider-contract.md:89`、`docs/security-model.md:185-187`：重复相同不确定选择。

**反例**

一个 subject 被 view 与 alert policy 引用。实现 A 静默级联删除引用并成功；实现 B 返回冲突；两者都能引用当前文字声称合规。用户无法在 dry-run 前知道破坏范围，验收也不能给出唯一预期。

**原因与影响**

这些是数据破坏和敏感 ID 迁移规则，不是无害的实现细节。保留“或”会产生不同产品行为和恢复边界。

**修复建议**

冻结默认行为，例如默认拒绝并列出类型化句柄，只有显式 `--cascade`/迁移子命令才原子修正；旧自由 ID 明确区分“安全可自动迁移”与“必须用户确认/拒绝”的判定规则。

**可验证验收条件**

- 对每种引用关系，普通命令与显式 cascade 都有唯一状态转移表。
- dry-run 与正式运行使用相同计划 digest；未确认时零写入。
- 崩溃恢复和备份测试证明引用与运行数据不会半删。

### AQ-R2-012 — 中 — WindowValue 允许负数、空测量和互相矛盾的数值

**定位**

- `docs/design-proposal.md:188-196`：`duration_minutes`、`used_percent`、`used_value`、`limit_value` 都可为空。
- `docs/design-proposal.md:254`：只有 used 与 limit 同时存在时才要求 `0 <= used <= limit`；未限制 duration，未要求至少一种测量，也未定义百分比与绝对值一致性。

**反例**

以下对象按现有文字可通过：

- `duration_minutes=-5, used_percent=None, used_value=None, limit_value=None`；
- `used_value=-1, limit_value=None`；
- `used_percent=10, used_value=90, limit_value=100`。

它们分别表示负窗口、负使用量和互相冲突的 10%/90%。

**原因与影响**

模型写了局部范围，却没有完整联合不变量。恶意/错误 Adapter 可以生成无法可靠告警和排序的 fresh+ok 快照。

**修复建议**

冻结 WindowValue 判别规则：duration 若存在必须为正；used/limit 单独存在也必须非负；正常定量值至少提供百分比或一组可解释的绝对值；同时提供两种表示时按 manifest 的精度/舍入容差一致。无法满足时返回语义/合约错误，不得 fresh+ok。

**可验证验收条件**

- property-based 测试覆盖 null 组合、负数、零 duration、超限和矛盾比例。
- 所有非法输入在写缓存前整批拒绝。
- 合法的仅百分比、仅绝对值和带容差双表示各有 golden fixture。

### AQ-R2-013 — 中 — 连续失败后的暂停语义跨文档互相冲突

**定位**

- `docs/design-proposal.md:381`：非公开接口连续三次失败后持久化“主体/能力暂停”，按需刷新仍可执行。
- `docs/design-proposal.md:421`：泛化为认证错误/连续三次失败后 paused，直到按需探测成功、凭据更新或 Adapter 修复。
- `docs/design-proposal.md:897`：MVP 验收只写统一的“三次失败后暂停”。
- `docs/provider-contract.md:324-339`：精细表规定 auth 暂停 refresh、network/provider 只暂停 Scheduler、schema/semantic 暂停全部 fetch 只允许 probe、rate limit 不使用三次计数。

**反例**

同一 capability 连续三次 network timeout。按设计方案概述可进入 paused；按 Provider 表只暂停 Scheduler，用户按需仍可 probe+fetch。测试作者无法知道第三次后手动 refresh 应调用 fetch 还是只 probe。

**原因与影响**

详细表和摘要/验收标准不是同一状态机。实现可能错误地永久停掉可恢复网络请求，或在 schema 漂移时继续 fetch 并覆盖风险边界。

**修复建议**

把 Provider 第 9.4 节表提升为唯一规范源；设计方案和 MVP 验收逐类引用准确动作。明确 `probe` 与 `fetch`、Scheduler 与 on-demand、generation 切换和计数恢复的每个状态。

**可验证验收条件**

- auth/network/rate-limit/provider/schema/semantic 逐类三次序列都有表驱动测试。
- 第三次后的 Scheduler、手动 probe、手动 fetch 调用计数与规范完全一致。
- 交错失败只改变对应类别，不误清其他计数。

### AQ-R2-014 — 中 — 当前契约仍保留未核验能力和“待冻结”占位符

**定位**

- `docs/provider-contract.md:158-161`：Kimi/GLM 的 variant、region、binding 仍为“待冻结”。
- `docs/provider-contract.md:261-263`：三个候选 Provider 的出口仍为“待冻结”。
- `docs/provider-contract.md:274-276`：在“待核验”的同时写入具体窗口能力结论。
- `docs/provider-contract.md:427`：把这些决定推迟到未来升级。
- `docs/design-proposal.md:401`、`docs/design-proposal.md:849`：它们被标为 Experimental/关闭，不阻塞 1A。

**反例**

实现者看到“Kimi 滚动 5 小时 + 周窗口”，据此建立 capability manifest；但同一行又说接口待核验，且没有合法出口。该具体能力可能是错的。另一个实现者因“待冻结”完全不注册它。两种行为都能从当前文档得到支持。

**原因与影响**

默认关闭降低运行风险，但不能把未核验事实变成合格的设计契约。本目标要求无遗留占位符或未决事项；这些词仍是明确未决状态。

**修复建议**

从 schema v1 规范中移除未核验的能力断言，把这些 Provider 统一登记为 `planned/no-contract`：无 auth variant、无 capability、无 NetworkPolicy、不可启用。另建带明确证据清单的升级门禁；取得官方/真实 opt-in 证据后再用版本化变更加入完整 manifest。

**可验证验收条件**

- 当前规范正文不再包含 `待冻结/待核验/TBD/TODO` 一类占位词。
- schema v1 对这些 Provider 的配置一律稳定拒绝，而不是以空字段运行。
- 每个未来升级门禁列出协议证据、出口、认证、时区、fixture 和 lifecycle 变更要求。

## 5. 覆盖结论

本轮问题覆盖了目标要求的主要风险面：

- 需求/门禁：AQ-R2-001、AQ-R2-002、AQ-R2-014。
- 数据与接口契约：AQ-R2-003、AQ-R2-006、AQ-R2-007、AQ-R2-008、AQ-R2-009、AQ-R2-012。
- 配置迁移/删除：AQ-R2-004、AQ-R2-011。
- 缓存/身份/当前协议可实现性：AQ-R2-001、AQ-R2-004、AQ-R2-007。
- 安全与隐私：AQ-R2-001、AQ-R2-003、AQ-R2-008、AQ-R2-009。
- 状态机、异常和恢复：AQ-R2-005、AQ-R2-013。
- 可测试性与验收：每项均给出可复验条件，AQ-R2-002/004/005/013 直接指出当前门禁无法形成唯一证据。
- 跨文档冲突和占位符：AQ-R2-004、AQ-R2-011、AQ-R2-013、AQ-R2-014。

## 6. 收敛判定

本轮不能给出 `PASS_ZERO_ISSUES`。只有在 14 项逐条处置、正文同步修订，并由一个全新的独立 Agent 重新进行全量审计后，才可以重新判断是否收敛。阻断项 AQ-R2-001 不能通过降低严重度或仅补一句“未来验证”关闭；它必须用当前可复现协议证据闭环，或明确改变 Codex/MVP 支持基线。
