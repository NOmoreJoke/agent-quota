# 第 1 轮独立对抗性审计报告

> 审计对象：`README.md`、`docs/design-proposal.md`、`docs/provider-contract.md`、`docs/security-model.md`  
> 审计方式：从当前工作树逐行静态审计；未参考其他 Agent 的结论；未修改任何设计正文  
> 证据等级：当前仓库只有设计文档、尚无实现或测试，因此本轮结论均由可定位的跨文档契约检查、反例推演和验收可执行性检查得出；没有把“未来会实现”当作已经验证

## 1. 结论先行

当前设计不能通过零问题门禁。本轮确认 **16 个可执行问题**：**阻断 0、高 6、中 9、低 1**。

文档已经较完整地覆盖了本地优先、Provider 出口、凭据隔离、保留期、Hermes/飞书披露和分阶段发布，但 0A 要冻结的核心契约仍存在可导致越权、缓存串用、误删、子进程失控或多实现分歧的缺口。文档中的未来阶段清单和明确关闭的 Experimental Adapter 本身不作为问题；本报告只记录会使当前规范无法唯一、安全实现或无法按验收标准证明的事项。

## 2. 严重度口径

- **阻断**：必须由用户作产品/风险决策，且现有上下文不能确定。
- **高**：可能造成越权、跨身份数据污染、凭据/机密暴露、破坏性删除，或使 0A 核心契约无法安全实现。
- **中**：会造成行为不一致、错误恢复、重复副作用、隐私边界漂移或关键验收不可重复。
- **低**：局部枚举/文档契约不一致，风险有限但会直接阻碍严格校验或测试。

## 3. 问题清单

### AQ-R1-001 — 核心数据模型仍是自由字符串，无法实现文档承诺的严格判别联合

- **严重度**：高
- **证据**：
  - `docs/design-proposal.md:153-165`：`QuotaSubject.kind`、`QuotaCapability.kind/unit` 都是普通 `str`。
  - `docs/design-proposal.md:210-227`：`data_freshness`、`health`、`source_type`、`status_code`、`semantic_contract_id` 等仍是普通字符串，`value` 只是未用 kind 判别的联合。
  - `docs/design-proposal.md:230-234`：正文要求多项跨字段不变量和未知内容拒绝，但没有给出完整状态/组合矩阵。
  - `docs/provider-contract.md:182`：出现 `unverified_version`，但 `docs/design-proposal.md:283-289` 的 `ProbeResult.compatibility` 允许值没有它；`docs/provider-contract.md:144,157` 的 `reauth_required` 也没有明确归属到 probe、health 或 status_code。
  - `docs/design-proposal.md:779-782`：验收又要求严格校验和无损表示全部状态。
- **风险场景**：Adapter 返回 `kind="balance" + WindowValue`、`health="ok" + value=None`、重复 CNY `BalanceEntry`、`expired + fetched_at/expires_at` 矛盾，或返回拼写错误的 `unverified_version`。不同实现可能分别接受、静默修正或崩溃，导致缓存和告警结果不一致。
- **为什么当前设计不足**：注释列举允许值不等于机器可执行契约；当前结构也不能证明 capability kind、value variant、unit、health、freshness、status_code/display_params 之间的合法组合。缺失/不适用/未授权/不兼容究竟属于 health、status_code 还是 StatusValue 仍不唯一。
- **建议修复**：给出规范性的 `Literal/Enum` 与带 discriminator 的模型；定义每个 kind 的 value、unit、状态、空值和时间字段组合；统一 `unverified_version`、`reauth_required`、`not_entitled`、`not_applicable` 等状态的唯一落点；补充余额币种唯一性、时间顺序、Decimal 有限性等不变量。
- **可验证验收条件**：从文档可直接生成 schema；对每个合法状态有正例，对未知枚举、kind/value 错配、重复币种、矛盾 freshness/health/value 和不合法时间有反例，所有实现必须得到相同的接受/拒绝结果。

### AQ-R1-002 — `AccountScope` 没有真正绑定 principal 与 subject，仍可形成越权笛卡尔积

- **严重度**：高
- **证据**：
  - `docs/design-proposal.md:112` 声称 scope 会绑定 principal、subject 与 capability。
  - `docs/design-proposal.md:546-558` 和 `docs/security-model.md:95-111` 实际把 `allowed_principal_ids`、`allowed_subject_ids`、`allowed_capability_refs` 分成三组集合；只明确禁止 subject 与 capability 的独立拼接，没有规定 principal/subject 必须作为一对命中。
- **风险场景**：scope 同时含 `P_A`、属于 `P_B` 的 `S_B` 和 `(S_B,C_B)`。请求用 `P_A + S_B + C_B` 时三个独立成员检查都通过，随后可能拿 P_A 的凭据查询 S_B 的 selector，或把错误结果写到 S_B 的缓存。
- **为什么当前设计不足**：`QuotaSubject.principal_id` 虽存在，但授权算法没有规定在读取、刷新、view 过滤和 Adapter 调用前必须验证该父子关系；数据结构本身也允许构造矛盾 scope。
- **建议修复**：把 scope 改为规范化的 `allowed_subject_refs={(principal_id,subject_id)}` 与 `allowed_capability_refs={(principal_id,subject_id,capability_id)}`，或明确 scope 构造器必须从注册表解析并拒绝任何父子不一致，服务入口再次校验。
- **可验证验收条件**：加入 P_A/P_B、S_A/S_B 的完整交叉矩阵；任何父 principal 不匹配、已移动/删除 subject、伪造 view 或空 scope 都统一 `not_authorized`，且不会调用 Adapter、读取缓存、更新失败计数或泄露主体存在性。

### AQ-R1-003 — 未规定 core 如何校验 Adapter 返回值与本次请求/manifest 的绑定，存在缓存投毒面

- **严重度**：高
- **证据**：
  - `docs/design-proposal.md:291-300` 的 `probe/discover/fetch` 可直接返回带 ID 的 subject、capability 和 snapshot 集合。
  - `docs/design-proposal.md:364-365`、`docs/provider-contract.md:310-314` 规定按返回能力拆缓存，但只说明键和“不复用”，没有规定返回边界校验。
  - `docs/provider-contract.md:332-336` 要测试多 principal 不串用，却没有测试 Adapter 返回错误 principal/subject/capability、重复项、超出请求项或与 manifest kind/unit 不一致时 core 必须拒绝。
- **风险场景**：有缺陷的 Adapter 在 P_A 请求中返回 `principal_id=P_B` 或返回未请求的 `(S_B,C_B)`；若 core 以 snapshot 自带 ID 写缓存，P_A 的网络结果会污染 P_B/S_B，后续授权读取可看到错误数据。
- **为什么当前设计不足**：内置 Adapter 属于 TCB 不代表它不会有解析或并发 bug；core 既然承担授权与缓存，就必须在信任边界处验证所有返回标识和基数，而不能只验证 display 参数。
- **建议修复**：冻结返回校验算法：adapter_id 必须等于已加载 manifest；principal_id 必须等于调用 principal；subject/capability 必须是请求集合子集并满足注册表父子关系；禁止重复；kind/unit/value/semantic_contract_id 必须命中 manifest；任何违规整批拒绝且不得写缓存/LKG。
- **可验证验收条件**：用恶意 FakeAdapter 覆盖跨 principal、跨 subject、额外 capability、重复 snapshot、错误 kind/unit/contract ID；断言 core 返回稳定 `adapter_contract_violation`，缓存、LKG、失败计数和其他主体均不变化，日志不包含机密返回值。

### AQ-R1-004 — Capability 缓存命名空间未覆盖端点、selector/config 代际和语义契约升级

- **严重度**：高
- **证据**：
  - `docs/design-proposal.md:364` 与 `docs/provider-contract.md:310` 的缓存键只有 `(adapter_id, principal_id, subject_id, capability_id, cache_identity)`。
  - `docs/design-proposal.md:365` 的 singleflight 额外包含 endpoint 和 selector，说明这些因素会改变请求，但已落盘缓存键没有它们。
  - `docs/design-proposal.md:386` 仅说 Adapter/语义升级经 probe/迁移切换基线，没有定义缓存/LKG 的代际切换或原子失效规则。
  - `docs/design-proposal.md:491-497` 只保证记录 ID 不变；endpoint profile、selector、enabled capability 和 manifest/adapter 版本可在同一 ID 下变化。
- **风险场景**：保持 principal/subject ID 与凭据不变，把 endpoint profile、subject selector 或 Adapter 的 scale/semantic_contract_id 改掉。`cache_identity` 不变，`quota_status` 仍可能读出旧端点/旧主体/旧单位的 fresh 缓存，且新语义 canary 可能拿旧 LKG 比较。
- **为什么当前设计不足**：`cache_identity` 只表示访问材料/登录代际，不表示查询含义或配置代际；“迁移切换”没有说明是删除、隔离还是重验证旧值。
- **建议修复**：定义 core 生成的 `query_contract_generation`（覆盖 endpoint profile、规范化 selector、capability spec、adapter version、semantic_contract_id），加入缓存/LKG namespace；配置/manifest 更新时以事务切换 generation，并明确旧代值是删除还是仅保留为不可展示的迁移证据。
- **可验证验收条件**：分别修改 endpoint、selector、scale、unit、semantic contract 和 adapter version，保持 credential 不变；旧缓存不得作为新 generation 的 fresh/stale/LKG 返回，切换过程崩溃恢复后也只能看到一个完整 generation。

### AQ-R1-005 — `purge` 只有“路径校验和确认”口号，没有可实现的破坏性删除契约

- **严重度**：高
- **证据**：
  - `docs/design-proposal.md:402` 只写显式 `agent-quota purge` 与再次确认目标路径。
  - `docs/design-proposal.md:802` 把“有路径校验和确认”作为 MVP 验收，但没有定义如何解析和允许目标。
  - `docs/security-model.md:292` 将 purge 目标校验列为 0A 待关闭门禁；`docs/security-model.md:178-189` 的删除章节也未给出 symlink、根目录、home、挂载点或 platformdirs 越界规则。
- **风险场景**：数据目录被替换为指向 home 的 symlink、环境变量/XDG 配置解析到空串或宽目录、路径在确认后被交换（TOCTOU），递归删除可能清除非 Agent Quota 数据。
- **为什么当前设计不足**：仅打印路径和二次确认不能证明目标属于本应用，也不能防 symlink/目录替换；实现者会自行选择 `resolve()`、字符串前缀或递归删除，安全结果不同。
- **建议修复**：冻结 purge 状态机和目标集合：目标只能来自已验证 platformdirs 下的固定 app 子目录；拒绝 `/`、home、workspace、父目录、挂载点、symlink/reparse point 和非预期 owner/mode；使用目录句柄/no-follow 逐项删除并重新校验 inode；先停宿主、checkpoint/关闭 DB；列出配置、数据、日志、迁移备份和明确不可能删除的系统备份。
- **可验证验收条件**：测试 `/`、home、空路径、`..`、symlink 链、确认后目录替换、非本用户 owner、嵌套非应用文件和跨文件系统；全部 fail closed。正常 purge 只删除清单内文件，保留边界和不可清除的 Time Machine 提示可验证。

### AQ-R1-006 — Codex `local-stdio` 缺少子进程、环境和输出资源边界

- **严重度**：高
- **证据**：
  - `docs/provider-contract.md:188-201` 的 `NetworkPolicy` 同时容纳 `local-stdio`，但后续 `docs/provider-contract.md:203-213` 的强制大小、超时和环境规则只针对 HTTP。
  - `docs/provider-contract.md:215-220` 与 `docs/security-model.md:161` 只限定 Codex 的可执行文件/允许 RPC，没有规定可执行文件解析、无 shell 启动、继承环境、stdout/stderr/frame 上限、超时后的进程组终止。
  - `docs/design-proposal.md:381` 承认可执行文件发现规则尚是平台门槛的一部分。
- **风险场景**：PATH 中的同名程序被启动；合法或失陷的 Codex 进程无限输出 stdout/stderr、发送超大 JSON frame 或永不退出；子进程继承与额度无关的 API Key 环境变量。结果可造成内存/进程耗尽或扩大秘密暴露面。
- **为什么当前设计不足**：RPC allowlist 只控制 Agent Quota 发送什么方法，不控制启动了谁、对方能读到什么环境、能返回多少数据以及如何可靠回收进程。
- **建议修复**：定义 absolute/canonical executable 发现和校验、`shell=False`、最小环境 allowlist、stdin/stdout/stderr 独立字节/帧上限、握手/请求/总截止时间、并发上限、超时后 terminate→kill 进程组及 zombie 回收；任何超限映射到稳定本地错误且不保存原文。
- **可验证验收条件**：fake stdio 程序覆盖 PATH 劫持、symlink 替换、超大/无换行/畸形 frame、stderr 洪泛、挂起、fork 子进程和敏感环境探测；全部在固定资源内终止，秘密不被传入，其他 Provider 查询不受阻断。

### AQ-R1-007 — 全渠道 `quota_refresh` 的幂等语义没有闭合

- **严重度**：中
- **证据**：
  - `docs/design-proposal.md:75` 明确要求所有 `quota_refresh` 按有副作用操作执行授权、限流和幂等。
  - `README.md:32` 只对飞书按钮额外要求持久化幂等。
  - `docs/design-proposal.md:551-555` 有 `request_id`，但未规定唯一性、重试窗口、持久化或结果复用。
  - `docs/security-model.md:191-212` 只完整定义卡片按钮幂等；CLI、飞书文本 `/刷新` 和未来 Web POST 没有等价契约。
- **风险场景**：CLI/Web/飞书命令在超时后以相同 request 重试。对 `official_cli` 地板可为 0 的 Adapter，会再次读取 Provider，并重复修改失败计数、审计状态或触发上游预算；调用者无法区分首次结果丢失和新刷新。
- **为什么当前设计不足**：singleflight 只合并并发中的相同请求，RefreshPolicy 只限制频率，两者都不是完成后重试的幂等结果契约。
- **建议修复**：选择并写明一种全局语义：要么 core 对所有刷新用可信来源生成的幂等键持久化状态/安全结果与 TTL；要么明确 CLI/Web 是 at-least-once，并从“必须幂等”中移除，同时规定重复失败计数和审计合并。飞书文本命令也需绑定可信 event/message ID。
- **可验证验收条件**：对 CLI、飞书文本、卡片和 Web 分别测试并发重复、完成后重试、进程崩溃前/后重试和不同 actor 复用 request_id；同一逻辑请求的 Provider 调用次数、失败计数和审计记录符合唯一的书面语义。

### AQ-R1-008 — principal/subject/capability 的禁用与删除清理规则互相矛盾

- **严重度**：中
- **证据**：
  - `docs/design-proposal.md:387` 与 `docs/security-model.md:182`：禁用/删除 principal 会清理；subject 只有“删除”会清理。
  - `docs/design-proposal.md:676`：principal **或 subject** 禁用/删除都会清理缓存、失败计数和结构状态。
  - `docs/provider-contract.md:289`：只有显式 Adapter/合约迁移或 principal/subject/**capability 删除**才清理；`docs/provider-contract.md:330` 又把“删除 capability”作为测试条件。
  - 配置实际只有 `enabled_capabilities`（`docs/design-proposal.md:423,441`），没有定义 manifest capability 记录如何“删除”。
- **风险场景**：用户临时禁用 subject 后重新启用。有的实现保留 LKG/语义基线，有的实现立即清空；禁用单个 capability 时可能既无法删除，也可能误清整个 subject。隐私保留和误报恢复结果均不一致。
- **为什么当前设计不足**：禁用、从 enabled 列表移除、删除配置记录、Adapter 移除 capability、principal 级联删除是不同事件，目前被混写。
- **建议修复**：给每类对象定义生命周期状态与转换表，逐项列出 live config、快照、LKG、语义基线、失败计数、限流、审计、备份的保留/清理行为及事务边界；说明重新启用是否产生新 generation。
- **可验证验收条件**：对 principal、subject、capability 分别覆盖 disable→enable、remove/delete、Adapter 升级移除和级联删除；每个存储表的预期状态唯一，崩溃恢复与 WAL 清理可验证，三份文档用词一致。

### AQ-R1-009 — `llm_minimal` 是否披露异常数量在跨文档中冲突

- **严重度**：中
- **证据**：
  - `docs/design-proposal.md:253` 限定只提供汇总健康、粗粒度余量区间和新鲜度。
  - `docs/security-model.md:149` 明确再加入“异常数量”；`docs/security-model.md:40` 也把正常/异常数量列为允许进入 LLM 的 Internal 数据。
  - `docs/design-proposal.md:243-248` 只有通用 `QuotaProjection` 草图，没有 `llm_minimal` 的字段级 schema。
- **风险场景**：一个实现向模型返回异常数量，另一个按设计方案将其删除；安全测试和同意文案无法确定哪个是合规结果，小主体集合下计数还可能帮助推断具体主体状态。
- **为什么当前设计不足**：“只提供”形成封闭列表，两个封闭列表不一致；没有字段级类型、桶边界或小基数规则可作为唯一真源。
- **建议修复**：定义独立 `LlmMinimalProjection` schema，明确是否允许计数；若允许，规定桶化/上限/小基数抑制和 consent 文案；其他文档引用该 schema，不重复手写字段列表。
- **可验证验收条件**：golden schema 与序列化快照证明所有允许字段且仅允许字段能输出；1/2/多主体、0/1/多异常和跨时间调用测试不能出现被禁止 ID、Provider 对应关系、精确值或未声明计数。

### AQ-R1-010 — Codex 的 region 示例与 Provider 契约直接冲突

- **严重度**：中
- **证据**：
  - `docs/design-proposal.md:409-416` 的 OpenAI Codex principal 使用 `region = "global"`。
  - `docs/provider-contract.md:148-151` 的认证变体矩阵把 OpenAI Codex region 冻结为 `local`。
  - `docs/design-proposal.md:305` 与 `docs/provider-contract.md:173-180` 要求 probe 对不符合 manifest 的 region fail closed。
- **风险场景**：照设计方案复制官方示例后运行 `config validate/doctor`，如果 manifest 遵循 Provider 契约就会拒绝该 principal，导致 Codex-only 验收样例自相矛盾。
- **为什么当前设计不足**：这不是未来实现状态，而是同一首批 Supported 候选的规范值冲突。
- **建议修复**：选择唯一 canonical region（若 `local` 描述传输而非供应商地区，则改为 endpoint profile 属性），同步所有示例、manifest 说明和测试 fixture。
- **可验证验收条件**：从文档示例生成的 Codex-only 配置通过严格 schema 与 Fake manifest/probe；把 region 改成其他值时得到确定的拒绝错误。

### AQ-R1-011 — 显式 subject 配置无法唯一构造必填的 `QuotaSubject.label`

- **严重度**：中
- **证据**：
  - `docs/design-proposal.md:153-158` 将 `QuotaSubject.label` 定义为必填字符串。
  - `docs/provider-contract.md:24` 允许 subject 显式配置，不要求一定先联网发现。
  - `docs/design-proposal.md:418-443` 和 `docs/provider-contract.md:38-45` 的 subject 配置均没有 label；`docs/provider-contract.md:75` 又说人类可读名称只能放在对应 label 字段。
  - `docs/design-proposal.md:493` 声称配置必须表达 `QuotaSubject`，但没有给出配置 DTO 到运行模型的映射规则。
- **风险场景**：离线创建 DeepSeek wallet subject。严格配置可通过示例，却无法实例化必填 label；实现者可能拿 selector、上游自由文本、subject ID 或空串补齐，分别造成机密回显、提示注入或 UI 不一致。
- **为什么当前设计不足**：运行时发现字段和用户配置字段混在同一模型里，必填值的来源、校验、保密和更新所有权没有定义。
- **建议修复**：分离 `SubjectConfig`、`DiscoveredSubject` 和规范化 `QuotaSubject`；明确 label 是用户必填、core 生成的本地默认、还是经白名单/长度/字符规则处理的 Provider 候选并需确认；定义 plan_code 同样的来源与更新规则。
- **可验证验收条件**：显式离线、联网发现后确认、label 更新、恶意上游 label 和无 label 五种 fixture 都能产生唯一结果；未确认的上游字符串不会进入配置、日志或投影。

### AQ-R1-012 — HTTP allowlist 的规范化与匹配算法未定义

- **严重度**：中
- **证据**：
  - `docs/provider-contract.md:188-200` 只给出 `hosts` 和 `path_templates` 集合。
  - `docs/provider-contract.md:205,212` 要求“规范化域名”和发送前 path 校验，但没有定义 IDNA/大小写/尾点、IPv6、默认端口、百分号编码、重复斜线、dot segment、query 与 path template 参数的处理顺序。
  - `docs/security-model.md:159,166` 把固定出口和目标校验作为凭据附加前的安全边界。
- **风险场景**：Adapter 构造 `/allowed/%2e%2e/other`、双重编码路径、带尾点/Unicode 的 host 或 template 参数包含 `/`；校验器与 HTTP 客户端/服务器采用不同规范化方式，凭据可能发到未审查操作。
- **为什么当前设计不足**：安全 allowlist 只有字段，没有可互操作的比较算法；“先校验再发送”无法证明校验对象与线上实际请求相同。
- **建议修复**：冻结 URL 构造器与 canonicalization：解析一次、拒绝歧义编码/userinfo/fragment、host IDNA A-label+小写+去尾点、显式端口、解码/重编码规则、禁止 dot segment 和模板参数路径分隔符、query key/value allowlist；对最终发送对象再比较，不接受 Adapter 自由 URL。
- **可验证验收条件**：建立恶意 URL corpus 覆盖大小写/尾点/IDNA/IPv4/IPv6/双重编码/dot segment/重复斜线/query 注入；只有精确登记 endpoint 能在解析凭据后发送，其余在解析凭据前拒绝。

### AQ-R1-013 — 连续失败后的恢复条件把运行时 probe 与发布时合约测试混在一起

- **严重度**：中
- **证据**：
  - `docs/design-proposal.md:369`：按需探测成功、凭据更新或 Adapter 修复都可解除 paused。
  - `docs/provider-contract.md:284-289`：要求“探测成功且合约测试通过”才清零，并仅明确认证失败与结构漂移分别计数。
  - `docs/provider-contract.md:296-301` 还允许网络、限流、5xx、schema、semantic 等多种失败和不同重试策略。
- **风险场景**：三次网络错误后运行时 probe 成功，但用户机器无法证明“合约测试通过”；实现 A 清零并恢复，B 永久 paused。三次 schema_changed 后普通 probe 成功又可能错误接受未经新 Adapter/fixture 验证的结构基线。
- **为什么当前设计不足**：发布时证据、运行时事件和不同失败原因没有组成明确状态机；“连续”是否跨错误类别、何时重置也不清楚。
- **建议修复**：为 auth/network/rate-limit/provider/schema/semantic 分别定义计数、暂停、next_allowed、恢复事件和是否需要新 adapter/contract generation；把“发行物已通过合约测试”建模为 manifest/release assurance，而不是运行时条件。
- **可验证验收条件**：对每类失败运行 2 fail→success、3 fail→probe、credential rotate、adapter upgrade、semantic recovery 和交错错误序列；paused、计数、LKG、基线和调度恢复结果完全由表格决定且重启后不变。

### AQ-R1-014 — 告警去重、冷却和“额度已重置”恢复事件没有确定性契约

- **严重度**：中
- **证据**：
  - `docs/design-proposal.md:634` 只写“对同一窗口做去重和冷却”，没有 key、时间、持久化或状态转换。
  - `docs/design-proposal.md:638-644` 列出耗尽、凭据、连续失败和“额度已经重置”事件，并说明只有 SchedulerHost 才通知，但没有定义恢复判断、一次性通知或重启行为。
  - `docs/design-proposal.md:789` 只验收 paused/无后台告警，没有验收通知合并。
- **风险场景**：进程每次启动都重发同一 warning；窗口 reset_at 滚动、未知时区恢复或 LKG 过期时，被误判为“已重置”；多策略同时命中虽然 severity 合并了，通知仍可能重复多条。
- **为什么当前设计不足**：severity 合并规则完整，但通知事件是另一套有状态行为。没有事件 identity、open/ack/resolved 状态、cooldown 起点、持久化和宿主接管协议，无法证明“不刷屏”或恢复通知正确。
- **建议修复**：定义 AlertEvent 状态机和键（capability + policy/health category + contract generation + window identity），规定首次触发、升级、降级、resolved、reset、冷却、确认、重启和多宿主租约；未知时间不得生成 reset 事件。
- **可验证验收条件**：虚拟时钟测试多 tier/多 policy、health+numeric、同一 snapshot 重放、重启、窗口轮换、unknown timezone、LKG stale/expired 和两个 SchedulerHost；通知次数和最终状态均有 golden 断言。

### AQ-R1-015 — “全量查询小于 10 秒”没有可复现的负载定义，并与 10 秒单请求截止时间贴边

- **严重度**：中
- **证据**：
  - `docs/design-proposal.md:788` 要求单次全量查询在正常网络下小于 10 秒。
  - `docs/provider-contract.md:209` 给单个 HTTP 请求外层 10 秒总截止时间。
  - `docs/design-proposal.md:303,356-363` 允许每个 principal 多 subject/capability，只说设置全局/Provider 并发限制，没有给最大配置规模、基准 fixture、排队预算或全局 deadline/cancellation 语义。
- **风险场景**：单个 Provider 用满 10 秒截止时间，聚合和渲染开销必然超过 10 秒；或用户配置很多 principal，Provider 并发上限导致排队，即使每个请求“正常”也无法满足未限定的全量 SLA。
- **为什么当前设计不足**：验收没有样本数量、延迟分布、冷/热缓存、失败比例、硬件、是否包含 probe 和渲染等条件，测试通过/失败可被任意解释。
- **建议修复**：定义参考工作负载与测量边界；设置小于产品 SLA 的 per-attempt deadline 和全局 deadline，规定超时取消、部分结果与排队策略；若规模不受限，把目标改成按 N 个请求的公式/百分位。
- **可验证验收条件**：固定 macOS/Linux CI fixture（principal/subject/capability 数、模拟延迟、冷缓存、一个慢 Provider），以单调时钟测 p95；全局 deadline 内返回部分结果并取消慢任务，无后台 orphan，且阈值与单请求 budget 留有明确聚合余量。

### AQ-R1-016 — FakeAdapter 使用了 manifest 未允许的 `test-only` 生命周期值

- **严重度**：低
- **证据**：
  - `docs/design-proposal.md:262-266` 的 `AdapterManifest.lifecycle` 允许 `planned, experimental, supported, ga`。
  - `docs/design-proposal.md:345-350` 与 `docs/provider-contract.md:231-238` 把 FakeAdapter 标为 `test-only`。
  - `docs/design-proposal.md:738-742,783` 又要求 FakeAdapter 通过同一 core/manifest 组合测试。
- **风险场景**：严格 manifest schema 会拒绝 FakeAdapter；若实现为测试特例，又无法证明生产生命周期解析对未知值 fail closed。
- **为什么当前设计不足**：生命周期枚举与首个必需 Adapter 的登记值直接不相交。
- **建议修复**：加入规范值 `test_only` 并明确永不进入 entry point/用户支持计数，或规定 FakeAdapter 使用 `experimental` 加独立 `distribution_scope=test`；禁止只在测试代码中偷偷绕过验证。
- **可验证验收条件**：FakeAdapter manifest 通过与生产 Adapter 相同的 schema；打包测试证明它不进入默认发行/支持计数；未知生命周期仍被拒绝。

## 4. 覆盖检查

| 审计域 | 结果 |
| --- | --- |
| 需求完整性与范围 | MVP/非目标/阶段边界清楚；发现 purge、stdio、告警状态机和性能基准缺口 |
| 逻辑一致性 | 发现 region、生命周期、删除/禁用、LLM 投影冲突 |
| 边界与异常 | 发现失败恢复、重复刷新、恶意 Adapter 返回、URL 歧义和子进程失控缺口 |
| 技术可行性 | 主架构可行；当前 schema 与 10 秒验收尚不能唯一实现/复现 |
| 接口/数据契约 | 发现判别联合、返回绑定、配置到运行模型映射不闭合 |
| 安全与隐私 | 固定出口、日志、保留期和披露原则较强；发现 scope、cache、purge、stdio、LLM 字段风险 |
| 配置/迁移/删除 | strict/migrate 基线较清楚；purge 与对象生命周期未冻结 |
| 缓存/并发/限流 | cohort/singleflight 设计较完整；缓存 generation 和 refresh 重试语义缺失 |
| 可测试性/验收 | 大量攻击与合约测试已列出；性能、告警、返回边界和破坏性删除缺少可执行用例 |
| 发布门禁 | 分层门禁清楚；上述高/中问题关闭前不能把 0A 视为通过 |
| 占位符/未决事项 | Kimi/MiniMax/GLM 的“待冻结”明确绑定 Experimental/关闭且不阻塞 1A，未单独报问题；当前 16 项是会影响已承诺 core/首批 Adapter 的实际缺口 |

## 5. 本轮验证证据与限制

- 已逐行读取四份指定文档及 `.gitignore`；仓库没有额外 `AGENTS.md`，也没有实现代码、schema、测试、构建产物或运行时可供动态验证。
- 本轮没有把文档中的 `[ ]` 自动视为缺陷；只有当正文已经要求某契约、但规范仍缺失或互相冲突时才报告。
- 本轮未修改 README 或三份设计文档，仅新增本报告。

## 6. 最终计数

| 严重度 | 数量 |
| --- | ---: |
| 阻断 | 0 |
| 高 | 6 |
| 中 | 9 |
| 低 | 1 |
| **合计** | **16** |

**结论：FAIL_WITH_16_ISSUES**
