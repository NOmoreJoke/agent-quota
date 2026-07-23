# 第 7 轮独立对抗性设计审计

> 审计日期：2026-07-18  
> 审计对象：`README.md`、`docs/design-proposal.md`、`docs/provider-contract.md`、`docs/security-model.md`  
> 实施状态：仓库仍无应用代码、无 commit；本轮验证的是现行设计合同、官方协议 schema、跨文档一致性与测试可执行性，不声称运行中的 Agent Quota 已通过测试

## 1. 唯一结论

`FAIL_WITH_14_ISSUES`

严重度计数：blocker 1 / high 10 / medium 3 / low 0。

本轮不能通过零问题门禁。`AQ-R7-001` 仍只能由用户在两个互斥产品基线中二选一；本报告没有擅自加入 `account/read`，也没有把 Codex 移出 MVP。除该身份决策外，另有 13 项可以直接修订的实现合同缺陷。

## 2. 方法、范围与证据等级

我先完整读取审计技能和四份现行正文，冻结独立候选清单后，才读取第 1～6 轮 audit/resolution。历史只用于排除真正已闭环或不适用的旧项，没有作为本轮问题来源。

证据等级：

- `E1`：可执行的本地反例或机械检查。
- `E2`：运行真实但不读取账户数据的本机命令。
- `E3`：本机官方工具生成的 schema/hash。
- `E4`：现行正文与官方一手源码/文档的静态核对。

本轮覆盖了需求与阶段边界、主体身份/发现、Adapter DTO、错误代数、Codex/DeepSeek 协议、缓存/LKG、跨进程 rate ledger、并发/超时/幂等、HTTP/local-stdio、凭据、根密钥/存储/恢复、发行与安装信任、隐私/留存、告警/多币种、迁移、投影、可观测性、发布门禁、数值边界、跨文档一致性和 README 状态真实性。

主要只读验证：

1. `nl -ba`、`sed`：逐行读取四份现行正文，共 2774 行。
2. `codex --version`：本机为 `codex-cli 0.142.5`。
3. `codex app-server generate-json-schema --out <empty-temp-dir>`：未使用 `--experimental`；只分析类型、required 字段、RPC 方法和 wire envelope，没有启动账户 RPC。
4. 生成的 `codex_app_server_protocol.v2.schemas.json` 原始 SHA-256 为 `29f8f2a6568cc0d986fd220636532583c08a1d7cd053446cf8926a2516499291`；独立 `JSONRPCResponse.json` 为 `94ecf5e81bdbc2af858afad0044b95c7fb4decf77d7fd7d6321324dad79eef57`。这些只是本机证据，不冒充设计中的 canonical bundle hash。
5. Python 纯虚构字节反例：两种 `binding_key_id` recipe 结果不等；相同虚构 evidence 配置到不同 principal/binding 后，现行 cohort 公式结果不等；两种 planner digest 对 `new_config_digest` 的绑定结果不同。
6. rate ledger 最小状态反例：第一行仍为 `reserved` 时，正文的 floor 查询只看 `committed|outcome_unknown`，第二个相同 floor key 仍被允许。
7. 官方一手来源：[OpenAI Codex app-server README](https://github.com/openai/codex/blob/main/codex-rs/app-server/README.md)、[DeepSeek Get User Balance](https://api-docs.deepseek.com/api/get-user-balance/)。

隐私保护：本轮没有调用 `account/read`、`account/rateLimits/read` 或任何真实 Provider；没有读取、记录或输出真实邮箱、账户标识、计划、额度、重置时间、动态 bucket key、Token、Cookie 或账户响应。schema 只用于字段与类型验证；所有计算反例使用固定虚构字节。

## 3. 问题清单

### AQ-R7-001 — Codex allowlist 仍不能产生 stable subject/AccessIdentity

- severity：`blocker`
- 确定性：高
- 证据等级：`E2 + E3 + E4`
- 分类：`用户决策`
- 精确定位：`README.md:3,32,52`；`docs/design-proposal.md:942-944,1142,1146,1730-1739`；`docs/provider-contract.md:149-151,196-205`；`docs/security-model.md:174-175,359`
- 事实：正式 Codex fetch 要求 `verified_stable` identity；当前唯一发送序列和 schema allowlist 只有握手与 `account/rateLimits/read`。该响应提供额度结构，不提供稳定账户/会话主体。官方另有只读 `account/read`，但当前合同明确禁止擅自加入，而且其身份字段存在空值分支。
- 影响：账户切换、登出重登或 subject 变化时，core 无法证明旧缓存、LKG、cohort 和 subject 绑定应失效；Codex 不能达到 Supported 门禁，阶段 2 的“至少两个真实 Supported Adapter”也不能按当前基线完成。
- 可操作修复：用户必须二选一：A）批准只读身份 RPC，并冻结稳定 evidence 元组、空值 fail closed、最小披露和 subject 语义；B）Codex 退出 MVP Supported/第二 Adapter 门禁，改用具备稳定身份合同的 Provider。修复 Agent 不得代选。
- 验证标准：同账户重启稳定；A→B、登出重登和 identity 空值不会复用旧缓存/LKG；原始身份材料不进入配置、SQLite/WAL/SHM、日志、fixture、投影或审计；最终 RPC allowlist、schema hash和三份正文一致。

### AQ-R7-002 — Codex wire envelope 与官方协议相反，合法响应会被全部拒绝

- severity：`high`
- 确定性：高
- 证据等级：`E3 + E4`
- 分类：`缺陷`
- 精确定位：`docs/design-proposal.md:663-671,1144-1154`；`docs/provider-contract.md:182-186,244-246`；`docs/security-model.md:174`
- 事实：现行状态机要求每个 response 恰含 `jsonrpc="2.0"`。OpenAI 官方协议明确说明 app-server 在线路上省略该字段；本机 stable `JSONRPCResponse.json` 也只要求 `id/result`，`JSONRPCError.json` 只要求 `id/error`。因此官方合法 response 不满足现行合同。另一个未闭合点是第 8.4.1 节声称使用“有限 error code map”，却没有登记任何 code→category 表；空 incoming notification allowlist 也没有绑定 exact initialize `optOutNotificationMethods`，而官方协议允许连接通知。
- 影响：按正文实现的 Codex Adapter 会把所有成功响应判成 `local_protocol_violation`；另一实现若按官方 wire 忽略 `jsonrpc`，又违反现行合同。两实现不能互操作，R6 的 JSON-RPC correlation 修订无法成立。
- 可操作修复：冻结 app-server 专用 wire schema：明确 `jsonrpc` 必须缺失，冻结 exact process argv、initialize params/clientInfo/notification opt-out、request frames、合法 error code map和通知处理；全部内容进入 schema bundle hash。
- 验证标准：用官方生成 schema和 fake stdio互验 omitted/present `jsonrpc`、success/error、通知、server request、错/重复/orphan ID、EOF/tail；两套实现只接受同一集合，官方合法 success 可完成握手和读取。

### AQ-R7-003 — CredentialSource 接口与 IdentityEvidence 所有权形成循环

- severity：`high`
- 确定性：高
- 证据等级：`E4`
- 分类：`缺陷`
- 精确定位：`docs/provider-contract.md:124-151`；`docs/design-proposal.md:722-756,936-944`
- 事实：`CredentialSource.resolve()` 的唯一签名返回 `CredentialLease`；唯一 `CredentialLease` 又强制包含 `access_identity: AccessIdentity`。但同两节同时禁止 Credential Source 返回 AccessIdentity，并要求它只能返回 `CredentialIdentityEvidence`，再由 core 派生身份。现行接口没有返回 secret/transport metadata + evidence、再由 core 构造 lease 的可执行路径。
- 影响：实现只能让 Credential Source越权伪造 core-keyed identity、构造缺字段 lease，或发明正文之外的第二个接口。独立 SDK/Source 实现不能共享同一 schema。
- 可操作修复：把 Source 返回值改为封闭的 `CredentialResolution(secret, transport_metadata, identity_evidence, expiry, binding fields)`，不得含 AccessIdentity；core 校验 evidence、派生 identity后才构造唯一 `CredentialLease`。也可以定义等价的显式两阶段接口，但必须只有一个规范源。
- 验证标准：生成 schema可表达完整成功/失败路径；Source 无 LocalKeyRing也能实现；恶意 Source提交 AccessIdentity、跨 binding evidence、普通字符串 secret或未知 metadata均在 Adapter 前拒绝。

### AQ-R7-004 — rate_limit_cohort 公式把 principal/binding 混入上游身份，复制 principal 可扩容

- severity：`high`
- 确定性：高
- 证据等级：`E1 + E4`
- 分类：`缺陷`
- 精确定位：`docs/design-proposal.md:722-740,942,1202-1203`；`docs/provider-contract.md:144-147,389-392`；`docs/security-model.md:175-180`
- 事实：`identity_digest` 对 IdentityEvidence 除 evidence/expiry 外的全部 source-specific 字段做 HMAC；这些字段包含 `principal_id`、`credential_binding_id` 或 RPC endpoint以及本地 generation。随后 cohort 又基于该 digest派生。相同上游 evidence只要配置到不同 principal/binding，就必然得到不同 cohort；本轮虚构字节反例结果为 false。这与“同一访问材料经不同 binding/principal必须共享 cohort”直接相反。
- 影响：复制 principal/binding 可以绕过 request floor/hour budget；多 Token同账户又会被拆成多个预算，破坏跨进程风险边界。
- 可操作修复：身份 envelope的授权绑定与 cohort PRF输入分离。先验证 principal/binding/profile/generation只用于证明 evidence来自当前请求；cohort输入只能是规范 Provider身份域 + 稳定上游 subject evidence。无法证明多材料同账户时使用部署级保守 cohort；cache identity另行绑定 principal和访问代际。
- 验证标准：相同上游证据跨不同 principal/binding得到同 cohort；不同账户得到不同 cohort；凭据轮换但账户不可证明时进入保守 cohort；复制配置、进程或 binding不增加调用预算。

### AQ-R7-005 — RequestedOperation 阶段顺序违反“先校验 endpoint/幂等，再读凭据”

- severity：`high`
- 确定性：高
- 证据等级：`E4`
- 分类：`缺陷`
- 精确定位：`docs/design-proposal.md:313-329,938,1233-1240`；`docs/provider-contract.md:159-163,226-240,397`；`docs/security-model.md:169-185,247`
- 事实：唯一阶段矩阵把 refresh写成 `probe? → credential_resolve → endpoint_build → idempotency_prepare`，但网络安全合同要求在解析凭据前完成 endpoint校验，幂等合同也要求重复请求在再次读取凭据前返回。doctor表根本不包含正文说可进入的 `credential_resolve`；discover把 `probe` 放在 `credential_resolve?` 前，而 HTTP ProbeContext又必须先有 lease/identity。
- 影响：严格遵循矩阵会在目标未验证、幂等未命中前读取 secret，或无法构造 HTTP ProbeContext；按网络章节重排又会生成矩阵禁止的 stage序列和错误 envelope。
- 可操作修复：重画唯一执行图并生成矩阵：authorize/config/manifest/endpoint validate → idempotency prepare（有副作用请求）→ credential resolution/evidence derive → probe → rate reserve → fetch。official-cli零 binding分支显式跳过 Credential Source。为 context build/identity derive补必要 stage或明确归属。
- 验证标准：全 `RequestedOperation × stage` golden序列一致；非法 endpoint和幂等重复的 credential resolve计数为0；DeepSeek doctor/discover/refresh能合法构造 lease后probe；Codex local-only不调用 Credential Source。

### AQ-R7-006 — floor reservation 不计 active `reserved`，并发相同请求可同时放行

- severity：`high`
- 确定性：高
- 证据等级：`E1 + E4`
- 分类：`缺陷`
- 精确定位：`docs/design-proposal.md:1208-1221`；`docs/provider-contract.md:386-399`；`docs/security-model.md:180-181`
- 事实：hour窗口显式计 `reserved|committed|outcome_unknown`，但 floor只查询最近 `committed|outcome_unknown` effective time。第一个事务插入 `reserved` 后、取得 slot/commit前，第二进程对同一 floor key仍看不到任何占位，因而也可 reserve并最终发送。虚构状态机反例连续两次均返回 allowed。
- 影响：public/undocumented refresh floor可被并发突破；若 hourly limit为空或较大，Provider调用数超过合同。singleflight没有冻结跨进程 leader backend，不能修补此竞态。
- 可操作修复：为每个 floor key增加唯一 active reservation，或让 floor检查同时考虑未过期 `reserved` 的 provisional block time；取消/超时/旧 fence按唯一事务释放，commit后转实际 effective time。
- 验证标准：2+进程同时请求同一 key时最多一个进入 commit/send；不同 key按策略并行；取消、queue timeout、owner crash、lease接管和 `now==boundary`都不死锁也不超发。

### AQ-R7-007 — binding_key_id 有两种互斥字节算法

- severity：`high`
- 确定性：高
- 证据等级：`E1 + E4`
- 分类：`缺陷`
- 精确定位：`docs/design-proposal.md:1281-1285,1289-1297`；`docs/security-model.md:243`
- 事实：唯一 envelope格式先定义 `binding_key_id="aqbk_"+SHA256(binding_key)`，启动算法又定义 `SHA256("agent-quota:binding-key-id:v1\0"+binding_key)`。固定虚构32字节输入的两个 digest不等；第一处还没有明确 hex编码，第二处要求 `.hex()`。
- 影响：按一处初始化的 registry/keyring，按另一处启动必定 `local_keyring_unavailable`；两套实现不能互读，正常安装首次重启即失败。
- 可操作修复：只保留一个带 domain separation的 exact bytes recipe，并统一 lowercase hex、前缀和 constant-time比较；registry、keyring、init、startup、restore和golden envelope均引用同一函数。
- 验证标准：两套独立实现对固定 vectors得到相同 ID并互读；任一 bit、前缀、编码或 domain变化稳定拒绝。

### AQ-R7-008 — installer 没有预安装 trust root，install plan仍可自举信任

- severity：`high`
- 确定性：高
- 证据等级：`E4`
- 分类：`缺陷`
- 精确定位：`docs/design-proposal.md:1071-1075,1089-1097,1099-1118,1310-1319`
- 事实：目标 core/CLI被要求携带 trust bundle，但它们尚未安装时，唯一 bootstrap组件是 `agent-quota-installer`。正文没有要求 installer内嵌 genesis root/bundle digest，也没有让独立核验的 `bootstrap.lock`绑定 trust bundle。release directory同时提供 bundle和由其 key签名的 plan；新安装的 verifier没有规范化的先验 root来判断这个 bundle为何可信。bundle更新又要求前一 bundle签名，但release格式不携带可验证链。
- 影响：一种实现会接受同目录自签 bundle，供应链信任退化为自洽签名；另一实现会因没有 genesis anchor拒绝所有新安装。signed plan不能建立非循环信任。
- 可操作修复：由独立核验的 installer wheel嵌入固定 genesis root set/最低 bundle digest+sequence，或让独立渠道同时固定 bundle digest；定义从该 anchor到当前 bundle的完整可离线验证链和最大链长度。目标 core/CLI不能作为自己的预安装信任根。
- 验证标准：恶意release directory同时替换bundle、plan、wheel和全部签名仍在解包/import前失败；全新安装与已有floor升级均能从先验anchor验证；缺中间bundle、回滚、root替换和自签初始bundle拒绝。

### AQ-R7-009 — release directory闭包规则互相排斥，合法安装目录无法构造

- severity：`high`
- 确定性：高
- 证据等级：`E4`
- 分类：`缺陷`
- 精确定位：`docs/design-proposal.md:1101-1108,1110-1118`
- 事实：release directory被要求包含“第三方依赖 hash lock”，但 signed plan的 `files.role`只允许 Agent Quota wheel、第三方 wheel和attestation sidecar，没有lock角色；control file列表又只排除 bootstrap.lock、installer wheel、trust bundle和plan。第1118行还要求release directory与`files`完全相等，和第1116行“control files不进入闭包”字面冲突。
- 影响：严格实现会因必需control/hash-lock是额外文件而拒绝；宽松实现会自选忽略文件，破坏“未知文件全部拒绝”和两installer互操作。
- 可操作修复：选择一个唯一模型。推荐只让 signed plan列出全部目标wheel/sidecar，installer由plan生成`verified-pip.lock`，删除输入的第三方hash lock；另以封闭control-file集合从目录等式中显式扣除。若保留输入lock，增加签名角色、digest和唯一文件名。
- 验证标准：发布器能构造一份被两installer共同接受的目录；增删/替换任一control或closure文件都得到相同verdict；不存在实现自选ignore集合。

### AQ-R7-010 — release attestation声称 exact，却没有 exact payload schema

- severity：`high`
- 确定性：高
- 证据等级：`E4`
- 分类：`缺陷`
- 精确定位：`docs/design-proposal.md:1062-1075,1089-1097`；`docs/provider-contract.md:190-194`；`docs/security-model.md:179`
- 事实：第8.3.1节只说payload“恰含第8.3节列出的字段”，但第8.3节没有给出 `attestation_payload` 的精确字段名、嵌套对象、类型、排序/唯一性、attestation ID位置或 assurance/build-proof字段结构。与之相比，install plan和assurance sidecar都有逐字段schema。
- 影响：publisher和verifier无法从正文生成同一JCS签名字节；实现可能漏签build proof/assurance，或因字段命名差异拒绝合法包。受信任wheel门禁不可互操作。
- 可操作修复：给 `aq-release-attestation-envelope-v1` 定义完整JSON Schema/Pydantic模型和exact signed payload字段，包括ID、distribution/version/filename、raw wheel digest、payload/assurance/report/build-proof digests、issued/expires、sequence；定义数组排序、签名阈值和未知字段拒绝。
- 验证标准：两套独立publisher/verifier对golden payload产生相同JCS bytes/signature/verdict；逐字段删除、重命名、重排、跨包/版本/filename重放和digest替换全部有唯一结果。

### AQ-R7-011 — destructive planner与journal计算不同的 plan_digest

- severity：`high`
- 确定性：高
- 证据等级：`E1 + E4`
- 分类：`缺陷`
- 精确定位：`docs/design-proposal.md:1269-1271,1445-1459`；`docs/provider-contract.md:93-95`
- 事实：通用破坏性planner定义 `SHA256(canonical(actions, old_config_digest, target_manifest_digest))`；migration journal定义 `SHA256(canonical(actions, old_config_digest, new_config_digest, target_manifest_digest))`，同时要求两者复用“相同plan digest”。前者不绑定new config且`canonical(...)`没有字节recipe。虚构反例中改变new config不会改变第一种digest，却会改变第二种。
- 影响：dry-run摘要无法被正式journal按同一算法验证；若采用较弱公式，同actions可被重放到另一份new config；若采用较强公式，用户提交的摘要不匹配。
- 可操作修复：建立一个版本化domain-separated `aq-migration-plan-v1` envelope，精确绑定old/new config digest、target manifest digest、稳定排序actions及其typed fields；所有delete/cascade/drift/plan metadata路径只调用该函数。
- 验证标准：两套planner对同一plan得到相同bytes/digest；任一old/new config、manifest、action字段或顺序语义变化都改变digest；dry-run→confirm→crash recovery始终复用同一digest。

### AQ-R7-012 — OperationResult矩阵没有合法的表外失败落点，且两文档枚举不同

- severity：`medium`
- 确定性：高
- 证据等级：`E4`
- 分类：`缺陷`
- 精确定位：`docs/design-proposal.md:331-390`；`docs/provider-contract.md:358-379`
- 事实：设计方案要求任何表外 operation/stage/code转成 `adapter_contract_violation`，但该code本身只允许 `doctor|discover|refresh` 的 `probe|discovery|provider_fetch`。例如 `status + provider_fetch`或`delete + projection`转码后仍是表外组合，合同没有可序列化结果。Provider表又把 `migration_conflict`分组为可用于`delete/deletion_plan`，而设计方案唯一矩阵只允许`configure|migrate`。
- 影响：全笛卡尔反例不能达到“每个输入都有唯一合法输出”；实现会抛未建模异常、发明internal错误或返回不同envelope，渠道也无法统一安全渲染。
- 可操作修复：定义一个对所有RequestedOperation都合法、stage处理明确的core contract failure，或规定表外对象只在构造边界抛固定不可序列化fatal并终止请求；然后从一个机器表生成Provider摘要，禁止手写分组扩大组合。
- 验证标准：全笛卡尔输入对每个表外组合都有唯一终局和零副作用；design/provider生成表逐格相等；不存在递归产生另一个非法OperationError。

### AQ-R7-013 — aq-bounds没有覆盖签名前的plan/bundle解析资源

- severity：`medium`
- 确定性：高
- 证据等级：`E4`
- 分类：`缺陷`
- 精确定位：`docs/design-proposal.md:985-1026,1089-1097,1110-1118`；`docs/provider-contract.md:238`；`docs/security-model.md:172,179`
- 事实：正文宣称全部安全关键bytes/count在分配前使用`aq-bounds-v1`，install verifier也要求“有界读取”；但bounds没有plan/bundle JSON bytes、files/signatures/keys/revocations/distribution bindings的数量上限。plan只限制单文件size和1 GiB闭包，理论上仍可声明极大条目数；trust bundle数组没有hard maximum。
- 影响：未签名或签名无效的本地release输入可在验签前造成巨大解析/分配和超长验证；两个installer也可选择不同隐含上限，得到不同接受/拒绝结果。
- 可操作修复：把plan/bundle/envelope bytes、files、signatures、root/release/install keys、revocations、bindings和字符串长度加入`aq-bounds-v1`，并规定流式/深度/节点限制及先bound后JCS/crypto的顺序。
- 验证标准：每个新边界覆盖min-1/min/max/max+1、巨大数组/深度/字符串和checked arithmetic；失败在解包、hash大量文件、签名验证和pip前完成，内存/墙钟上限可测且两实现一致。

### AQ-R7-014 — 新增metadata/temp持久化没有生命周期，retention lint也不能确定性兜底

- severity：`medium`
- 确定性：高
- 证据等级：`E4`
- 分类：`缺陷`
- 精确定位：`docs/design-proposal.md:955-957,1447-1455`；`docs/provider-contract.md:385`；`docs/security-model.md:177,199-225`
- 事实：相同plan观察会持久化`last_observed_at`，但唯一保存期限表只覆盖pending plan change，正文没有该行在disable/delete/generation replacement/purge时的生命周期。migration在写journal前创建含新TOML的`0600`临时文件；此点崩溃时“没有journal”，后文只删除已知migration的临时文件，没有孤儿识别/清理规则。`retention-source-lint-v1`只用未定义的“语境/section allowlist”查duration literal，既检测不到这两种无duration记录，也没有冻结AST节点/heading allowlist；Provider和安全摘要还在“到期”语境重复Codex 180秒/DeepSeek 600秒。
- 影响：Confidential metadata和配置临时副本可能在对象删除或崩溃后无限残留；lint实现要么拒绝当前正文，要么靠自选例外放行，不能作为发布门禁证据。
- 可操作修复：把same-plan observation和orphan migration temp加入机器化data inventory，给出对象生命周期/RET ID、terminalization和安全no-follow清理；冻结lint的文件、heading、AST node、code/table处理和exact allowlist，从唯一常量引用freshness数值。
- 验证标准：虚拟时钟/逐点kill覆盖same-plan、pending、disable/delete/generation/purge和journal前崩溃；启动只清理可证明属于本安装且无active journal的orphan；lint对当前正文通过，并对每类复制duration、漏登记持久化surface和伪装单位fixture失败。

## 4. 历史核对、已闭环与不适用

历史核对没有把第 6 轮17项处置当作默认正确。当前源码直接推翻了其中若干“已完成”断言：binding key、rate reservation、signed install plan、OperationResult、aq-bounds、IdentityEvidence、JSON-RPC、plan metadata和retention lint分别由本轮现行证据重新成立；本报告使用新的R7 ID，而不是复述旧清单。

以下检查在当前正文中没有形成问题：

- DeepSeek官方表面仍是固定`GET /user/balance`、boolean `is_available`、CNY/USD与三个字符串金额；现行两capability原子映射与官方一手文档一致。
- Codex顶层兼容rateLimits、多bucket有界验证、primary/secondary/reached三态映射和动态key不持久化的主方向已闭环；本轮Codex问题是身份和wire envelope。
- Adapter每request key恰一observation、core拥有LKG/snapshot合成、query generation隔离、HTTP固定出口/禁代理/流式上限、alert episode聚合、多币种不求和与群聊零披露没有出现新的高置信缺陷。
- Hermes/飞书/Web是后续可选阶段，尚未实现本身不算Standalone MVP问题；SQLite对同uid插件不加密是正文明确接受的profile风险，不重复列为缺陷。
- README关于“无代码、无依赖、无commit、Codex决策未定、仍需全新审计”的仓库状态属实；但本轮证明“第6轮16项可确定问题已闭环”不能作为当前0A通过证据，后续修订应更新状态摘要。

## 5. 文件完整性与历史证据

审计开始时四份现行源文件SHA-256：

```text
137935eab41f73c4e9a73d59888e3cb0ac9a3d56ae06c010c49987e8bef2d91c  README.md
9a3ef3313b1152b9c99776ec831c07079e86a23cd6387d337c64b3f646a5e358  docs/design-proposal.md
3f0bf03262706989142dae961f24787d45d430a1dcaa15e7eb6595a5564e0b82  docs/provider-contract.md
ef585d829f52a4966ad177082a8fa1a4fae51104b3df343e5d2f9550a84b261a  docs/security-model.md
```

第1～6轮历史证据在本轮读取时SHA-256：

```text
a00a14c901881d84ba7648987a2cb7ceff92b41bd9f077a13605e38bad76abdd  docs/audits/round-01-audit.md
c4630344e20561d3677e6d393cf206f4bf6d438871444d28e9d7872dedd53935  docs/audits/round-01-resolution.md
c997a3853d0d47b9e44e1fbb0f8476ddbdf9006438855a3cf1cd246857b54c9a  docs/audits/round-02-audit.md
8b13adaec95df01fa7da78bbed6c305076597535f4e415f396840be4774c65df  docs/audits/round-02-resolution.md
4c0283dfe7827922b0be8001e8b0d381e247ac6f6fab3d8c95d9c95aba2cca32  docs/audits/round-03-audit.md
7ad08ed95a607d1a353c9c54d4bbd359798dd6145c2f6a3918204e3efae12581  docs/audits/round-03-resolution.md
ea0e5002fa17b6d3a8396c5ce8d11fa321e45ae2b1470ba33149a845b1a82897  docs/audits/round-04-audit.md
2b57e50bbfe68928a74a7d2d090614407909a5da1481c80db6710219cd2cf171  docs/audits/round-04-resolution.md
7339b048a03f98b91119d01fec86d6364af645043da42cbfc42617de48542c86  docs/audits/round-05-audit.md
0c3858ded76f622b3dc50ec87c9de0f931f97b6cdd93b0f0ed9de2f98c3d27a4  docs/audits/round-05-resolution.md
0924b992e71170ef4944980e37c7fe85fdf1a56a09a489ab77b9d987de62cd32  docs/audits/round-06-audit.md
97048a24cab36d824726227278d68f71e74d60650abf3e1488438da8ed448609  docs/audits/round-06-resolution.md
```

仓库为`main`且没有commit；本轮唯一写入文件是`docs/audits/round-07-audit.md`，没有修改README、三份现行正文、`.gitignore`或任何历史audit/resolution，也没有执行git commit。

## 6. 最终门禁

- 结论：不能进入零问题状态。
- 身份用户决策：存在，见`AQ-R7-001`。
- 身份决策外的可修复问题：存在，共13项。
- 下一步：先修订13项可确定缺陷；Codex产品基线仍由用户二选一。完成后必须由新的独立Agent再次从零全量审计，不能只复查本报告。
