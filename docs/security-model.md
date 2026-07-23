# Agent Quota 安全模型

<!-- AQ-GENERATED-CURRENT-STATUS-V1:BEGIN -->
```json
{"design_version":"v2.5","gate_status":"ZERO_ISSUES_AUDIT_CONFIRMED","latest_audit_path":"docs/audits/round-20-audit.md","latest_audit_verdict":"PASS_ZERO_ISSUES","latest_issue_ids":[],"revision_round":20,"status_kind":"ZERO_ISSUES"}
```
<!-- AQ-GENERATED-CURRENT-STATUS-V1:END -->
<!-- AQ-NORMATIVE-DECISION-LINK-V1:audits/gui-product-decision-resolution.md -->
> 上述 marker 是第 20 轮零问题终态；第 1–19 轮历史保持不可改写。GUI/Codex/OpenRouter 产品决策见 [`gui-product-decision-resolution.md`](audits/gui-product-decision-resolution.md) 与设计方案第 20 节；`ZERO_ISSUES_AUDIT_CONFIRMED` 之后进入 Gate 0A 工作，仍不构成生产发布授权。
> 最后更新：2026-07-19
> 适用范围：Agent Quota Desktop host/renderer/core sidecar、Provider Adapter、辅助 CLI、Hermes/飞书集成、SchedulerHost 和远期可选 Web

## 1. 安全目标与非承诺

core safety、operation/error、LocalKey purpose、lease 与 retention lint 的唯一机器源分别是 [`core-safety-contract-v1`](contracts/core-safety-contract-v1.json)、[`operation-contract-v1`](contracts/operation-contract-v1.json)、[`local-key-purpose-registry-v1`](contracts/local-key-purpose-registry-v1.json)、[`lease-policy-v1`](contracts/lease-policy-v1.json) 与 [`retention-lint-v1`](contracts/retention-lint-v1.json)。统一严格读取、JCS 与域分离摘要规则只引用[设计方案第 1 节](design-proposal.md#1-一句话定义)；本文只使用 symbol/ID 和生成投影。

Agent Quota 的安全目标是：只让经过认证和授权的 actor 查看允许 subject/capability 的最小必要额度；凭据只能到达预先审查的 Provider 出口；上游不可信内容不能进入日志或输出渠道；可选 LLM/消息集成另有披露与重放控制。

本项目是“本地优先”，不是“严格本地”：

- 查询公开 API 时，凭据和必要请求会发送给对应 Provider。
- 返回飞书时，投影后的额度数据会进入飞书基础设施。
- 只有显式启用自然语言最小投影时，额度摘要才允许进入 Hermes 模型上下文和当前模型供应商。
- Desktop profile 默认不安装 Hermes；启用 Hermes profile 后，进程内/同 uid 的 Hermes 插件与 Adapter 没有相互隔离，并可直接读取 Agent Quota 的机密配置、SQLite、WAL/SHM 和本地关联密钥。这是 Hermes profile 的明确已接受风险，不是 core 授权可以阻止的行为。

不在本安全模型内的能力包括自动切换模型、消耗/重置额度、修改 Provider/Hermes 配置、任意第三方 Adapter 和公网 Web 服务。这些能力不得借用“查询额度”的授权上线。

## 2. 可选 Hermes/飞书宿主事实

以下事实只约束阶段 3 的 `agent-quota-hermes`，不构成阶段 1/2 独立内核前置条件：

1. Hermes 将普通工具结果作为 `role=tool` 追加到模型上下文。
2. 普通工具结果会传给进程内 `post_tool_call` 和结果转换钩子。
3. 当前普通工具派发只提供 `task_id`、`user_task` 等任务信息，没有可靠的飞书租户、应用和操作者身份。
4. Hermes 通过 Python `importlib` 在主进程加载插件；插件与 Agent 共享进程权限。
5. Hermes 是单租户个人 Agent，已授权网关调用者通常位于同一信任层；这不自动解决 Agent Quota 的账户范围、群聊披露或回调重放问题。
6. 飞书 `card.action.trigger` 回调提供 `header.event_id`、`header.tenant_key`、`header.app_id`、`operator.open_id`、`context.open_chat_id` 和 `context.open_message_id`，足以构造调用者上下文和幂等绑定。
7. 本机 Hermes 的通用卡片动作去重是短命进程内缓存；重启或超时后不能继续提供重放防护。

因此，Hermes profile 的详细命令必须绕过普通工具结果链，身份来自网关事件，按钮刷新使用 Agent Quota 持久化幂等；Desktop profile 不包含这些组件。

## 3. 资产分级

| 级别 | 数据 | 默认允许目的地 |
| --- | --- | --- |
| Secret | API Key、OAuth Token、Cookie、飞书签名密钥、远期 Web Token、Desktop IPC session secret、InstallationRegistry binding key、LocalKeyRing active/verify-only key | 仅对应受信任 host/core/系统服务；永不进入 renderer、快照、LLM、飞书、普通备份、日志或 Git |
| Confidential | 余额、额度、使用率、计划、principal/subject 别名与 selector、认证状态、精确重置时间、完整主体清单 | 授权本地操作者；授权操作者飞书私聊的确定性投影 |
| Internal | 聚合健康、正常/异常数量、粗粒度阈值、数据新鲜度 | Desktop/远期 Web 授权聚合；LLM 只允许第 8 节封闭 schema 的无计数子集，MVP 群聊不接收这些数据 |
| Public | 虚构配置、虚构 fixture、公开 Provider 契约 | 开源仓库 |

“不含 Token”不等于非敏感。SQLite 快照、WAL、结构状态和失败计数至少按 Confidential 管理。

## 4. 信任边界与数据流

```text
React/TypeScript renderer（不可信展示层；无文件/网络/sidecar capability）
        │ 显式 Tauri command allowlist
        ▼
Tauri/Rust trusted host ──匿名管道/stdio──> Python core sidecar
                                                │ AccessContext/授权/缓存权威
                                                ▼
                                   Built-in Adapter → Provider/Codex CLI
                                                │
                     ┌──────────────────────────┴────────────────────┐
                     ▼                                               ▼
Desktop/辅助 CLI 确定性投影                              可选 Hermes 最小投影
```

详细数据路径的强制顺序是：认证上下文 → 授权范围 → 读取/刷新 → 渠道投影 → 确定性模板 → 发送。任何层都不能用 LLM 参数补全前一层缺失的信息。

## 5. 可信计算基与插件边界

TCB 按部署 profile 分开：

| Profile | TCB |
| --- | --- |
| Desktop（默认） | OS 用户、签名 Tauri host、固定 Python runtime/core sidecar、macOS Keychain/本地数据服务、启用的内置 Adapter；renderer 是受限攻击面，不是业务授权权威 |
| Scheduler | Desktop/core + `agent-quota daemon` 或明确的 OS scheduler 宿主 |
| Hermes | Desktop/core 数据面 + Hermes 核心、飞书网关、上下文桥接、全部已启用 Hermes 插件/钩子 |
| Web（远期） | 独立 Web host + application service + 认证浏览器会话；不是 Desktop renderer/IPC |

`CredentialRef` 只约束受信任代码的正常行为，不阻止同 uid 代码读取环境或文件。Desktop 不读取 `~/.hermes`；只有安装 Hermes profile 后，用户才承担 Hermes 全部插件进入 TCB 的风险。

Hermes profile 采用明确的 (a) 产品取向：接受全部已启用同 uid 插件可以 `open()` 机密数据库并绕过 actor/AccountScope 读取控制。`0700/0600` 只隔离其他 OS 用户，不隔离同 uid；如果解密密钥也对同 uid 可读，静态加密同样不能建立插件隔离。安装/启用界面必须直说这一点。高敏感用户应只使用 Desktop，或将 Hermes 放在独立 OS 用户/实例中并仅安装受信任插件。若未来要承诺插件间保密，必须另立独立进程/密钥代理边界，不能在当前 3A 文档中暗示已经做到。

MVP 禁止第三方 Adapter 接触原始凭据。未来 P2 Adapter 必须满足全部条件：

- 在独立低权限进程运行，不由 Hermes 主解释器导入。
- 环境默认清空，只注入单个、短期、可撤销 Credential Lease。
- RPC 仅暴露固定请求种类，不提供任意命令、文件或网络代理能力。
- OS/容器层固定网络域名、端口和协议；响应大小和运行时间有硬上限。
- 每个 Adapter 实例只服务一个 principal/Credential Lease，不能跨 principal 共享带认证客户端。

无法满足时，P2 保持禁止，而不是以风险提示代替隔离。

## 6. 渠道无关 AccessContext 与授权

core 的公共服务入口接收渠道无关上下文：

```python
class ActorPrincipal:
    kind: str                    # local, feishu, web, other-integration
    stable_actor_id: str

class AccountScope:
    allowed_principal_ids: frozenset[str]
    allowed_subject_refs: frozenset[tuple[str, str]]
    # (principal_id, subject_id)
    allowed_capability_refs: frozenset[tuple[str, str, str]]
    # (principal_id, subject_id, capability_id)

class AccessContext:
    actor: ActorPrincipal
    account_scope: AccountScope
    requested_operation: RequestedOperation
    request_id: str

class PresentationContext:
    timezone_id: str              # canonical IANA zone；fallback 固定 UTC
    source: str                   # actor_profile, local_config, utc_fallback
    fallback_reason: str | None   # missing, invalid
```

安全规则：

- Desktop host 与辅助 CLI 都由受信任本地入口使用 OS uid 构造 `LocalActor`，只需要本地 `AccountScope`，不需要 tenant/app/chat/message；renderer 不能自行构造 actor 或 scope。
- 集成包从可信平台事件构造平台 CallerContext，验证后映射为 AccessContext；模型、工具参数、卡片 `value` 或用户文本不能提供身份/scope。
- scope 构造时从当前 registry 解析每个 `(principal,subject)` 与 `(principal,subject,capability)`，父子不一致、悬空、禁用、删除或已移动引用立即拒绝；不得从三个独立列表拼接。
- 每个服务入口在读取缓存、调用 Adapter、创建幂等记录或更新失败计数前重新验证请求 principal、subject ref、capability ref 三层均命中且 registry 父子关系仍一致。空请求表示“授权范围”，空 scope/空授权结果、伪造 view 或父 principal 不匹配统一 `not_authorized`，不能回退全量，也不得泄露主体是否存在。
- 命名 view 只是对授权结果的进一步过滤；view 中的 subject/capability 引用不能成为授权依据，也不能把 `AccountScope` 外的数据带回结果。
- `requested_operation` 使用设计方案唯一 `RequestedOperation` 联合并参与授权；内部 `ExecutionStage` 不单独授权且只能命中冻结映射。status 不能触发 refresh/configure/delete/purge，refresh 不能进入迁移/删除，未知值在缓存前拒绝；错误保留原请求并记录 failed stage。
- `PresentationContext` 只在授权后的渲染阶段使用，不属于身份/scope，不进入快照、缓存、query generation 或幂等键。可信 actor profile 优先于本地 `[presentation].timezone`；缺失或非法 IANA zone 固定使用并标注 UTC fallback，不猜固定偏移。Desktop/CLI/飞书/远期 Web 使用同一 tzdb 转换函数。
- 拒绝响应使用统一 `not_authorized`，不透露主体是否存在、Provider 类型或认证状态。
- 授权策略默认拒绝。配置变更需要本地文件权限和审计；消息集成不能自助扩大范围。

Hermes 当前工具上下文不足以承载平台字段。不可伪造的 FeishuCallerContext 桥接属于阶段 3A 门禁；桥接完成前只关闭 Hermes/飞书包，不影响 LocalActor 使用 Desktop/core/辅助 CLI。

## 7. 渠道授权矩阵

| 渠道 | 默认能力 | 可见数据 |
| --- | --- | --- |
| Desktop GUI（主入口） | 状态、刷新、配置校验应用、重新认证、脱敏导出；purge 使用独立计划与二次确认 | host 授权后返回的 renderer-safe LocalActor 明细；renderer 永不接触 Secret |
| 本地 CLI（辅助入口） | 状态、刷新、配置、alert ack、consent grant/revoke；purge 另确认 | 与 Desktop 共用 application service 的 LocalActor 明细 |
| 飞书授权私聊 | 状态、刷新、scope 内 alert ack | AccessContext 允许主体/能力的确定性明细 |
| 飞书授权群聊 | 只允许固定私聊引导；状态与刷新均关闭 | 不接收任何额度衍生数据、计数、健康、告警或新鲜度 |
| Hermes 自然语言 | 默认关闭；只允许状态摘要，不允许刷新 | 显式、限时同意后受频率限制的 `llm_minimal` |
| 日志/观察系统 | 稳定状态与假名化关联 ID | 不含 Confidential/Secret；关联 ID 不承诺抵抗同 uid |
| 未知或缺失上下文 | 无 | 统一拒绝 |

consent grant/revoke 只允许受信任 LocalActor，不允许飞书/远期 Web/模型自助授予；alert ack 必须同时绑定 actor scope、`AlertEpisodeKey` 与当前 generation，过期/已 resolved episode 不可复活。三种状态变更都使用设计方案 `RequestedOperation`/stage/result 联合并在 SQLite 事务执行，未知 operation 或表外 stage/code 在任何缓存/ledger访问前拒绝。

群聊不能因发起者有明细权限就向全群展示明细。聚合和最小基数仍会被小桶、外部知识或跨时间差分去匿名，因此 MVP 的 `feishu_group` 是固定路由响应：只发送“请私聊机器人查看额度状态”，不读取 quota projection，也不包含主体数、正常/异常数、总体健康、Provider 分组、告警、新鲜度或前后变化。群聊刷新完全关闭。余额、principal/subject 别名、计划、认证状态和精确重置时间只允许本地或授权私聊。

## 8. LLM 与 Hermes 工具边界

`/额度`、`/quota` 和 `/刷新` 由 Agent 运行前的命令路由器处理：

1. 从可信网关事件构造 FeishuCallerContext，并映射为 AccessContext。
2. 完成 subject/capability/operation 授权。
3. 调用 SDK，并生成对应渠道的投影。
4. 使用内置模板直接回复或更新卡片。

这条路径不得注册为 Hermes 普通工具，不生成 `role=tool` 消息，不触发通用 `post_tool_call`/`transform_tool_result`，也不让 LLM 组织自然语言。

可选自然语言工具名为 `quota_status_summary`，并满足：

- 默认不注册；由本地操作者显式开启并确认摘要会形成可被当前模型供应商、会话日志和进程内插件跨时间采样的持续披露通道。
- 同意记录包含不可伪造的 actor/platform、core 生成的 `projection_scope_id`、`consent_generation`、`expires_at` 与撤销状态；生命周期只引用 `RET-CONSENT-ACTIVE/RET-CONSENT-TOMBSTONE`。宿主必须把这些字段通过模型不可修改的 `ConsentContext` 注入；若当前 Hermes 版本不能提供该上下文，自然语言工具保持未注册。
- 工具是否已在会话注册不构成授权。每次调用在读取缓存或生成投影之前，都必须 fail closed 地重新读取同意记录并校验 actor/platform、scope、generation、到期与撤销状态。撤销会原子递增 generation，使所有既有会话立即返回 `consent_required`；过期或撤销后连旧缓存桶也不得返回。
- 本节是频率常量的唯一规范源：`LLM_PROJECTION_COOLDOWN=15 minutes`、`LLM_PROJECTION_HOURLY_LIMIT=4`；同一 actor/platform/scope 与 `(deployment_id,projection_scope_id)` 分别执行该冷却/滑动窗口总预算。冷却期只在同意仍有效时返回同一缓存桶，不产生更细时间序列。
- 只返回设计方案第 7 节封闭 `LlmMinimalProjection(schema_version, aggregate_health, capacity_band, freshness_band)`。附加字段拒绝；**不返回正常/异常数量或主体数**。
- 不返回 principal/subject ID/别名、Provider 对应关系、余额、精确百分比、计划、认证状态、重置时间或上游消息。
- 不提供 `quota_refresh`、任意主体枚举或完整 JSON 的自然语言工具。

## 9. 凭据与网络出口

凭据处理与网络出口必须同时满足 [Provider 与凭据契约](provider-contract.md)：

- Credential Source 只返回 `CredentialResolution`；授权 binding、访问代际材料与可选稳定上游主体 evidence 分离验证，core 独占 `derive_access_identity_v1` 和 `CredentialLease` 构造。official-cli principal 可以没有 binding，但不能没有 core 验证的稳定 AccessIdentity。
- Adapter 只接收设计方案冻结的不可变 `ProbeContext/DiscoveryRequest/FetchContext`：seed 不含正式 SubjectId，结果只用同批 DiscoveryResult；core 在 Adapter 前完成 requested operation/stage、scope、registry、manifest、seed/selector、canonical lease/零 binding proof、AccessIdentity、唯一 endpoint spec 与 deadline 绑定。所有跨不可信边界的 nested mapping/list 先有界深拷贝，再重建成 immutable DTO/canonical tuple；`frozen=True` 不作为深冻结证明。Adapter 不得反查全局状态或 cache；secret/transport metadata/proof 禁止 repr/序列化并在调用后清除。
- `system-credential` 在 Keychain/Secret Service、D-Bus 会话或受审查 backend 不可用时 fail closed，返回操作级 `credential_backend_unavailable`；不创建快照、不更新 Provider 失败计数，且不得静默降级为环境变量、文件或其他 CredentialRef。
- HTTP 只允许 manifest 的原子 `HttpEndpointSpec`；endpoint ID 唯一绑定 method、逐段 path 参数、单值 query、auth injection、response 与 deadline，禁止平行元组。按 Provider 契约规范化后，对凭据解析前对象和发送前对象各比较一次；DeepSeek/OpenRouter 通用 builder 只凭 spec 构造固定出口。
- schema v1 HTTP 仅允许 `GET`、`allow_proxy=false`，不存在 body/proxy/custom CA 分支；POST/代理配置在 Credential Source 前离线拒绝。全部安全关键 int/Decimal/timestamp/bytes/process/discovery/concurrency/Retry-After 只能使用设计方案 `aq-bounds-v1`，signed manifest 不能放宽，并在凭据解析/分配/启动前通过边界与 overflow/fuzz gate。
- HTTPX 强制 `trust_env=False`、禁止自动重定向、TLS 校验和超时；使用 `AsyncClient.stream()` 在读取过程中执行 wire/decoded 上限，默认拒绝非 identity 编码。schema v1 Provider 代理恒关闭。
- Codex Adapter 被降级为 `experimental/incompatible` parser-only：只允许离线 fixture/parser 验证，不启动真实 CLI、不发送 `account/rateLimits/read` 或 `account/read`、不读取真实账户，也不形成 Snapshot/LKG/cache。未来恢复真实调用必须另立身份与上游稳定 subject 契约并重新审计。
- AccessIdentity 的 cache 与 cohort 使用不同 domain/key/input。cache 绑定 principal 与访问代际；stable cohort 只绑定经验证的 Provider identity domain/上游 subject，不包含 principal/binding/访问代际/进程；缺 stable subject evidence 时使用 deployment/adapter/endpoint budget group 的保守 cohort。Adapter/Source 禁止提交 keyed identity 或 assurance；已有安装缺失/回滚 keyring 时 fail closed。OpenRouter 的 access/cache identity 只绑定已验证 API key binding 与 credential generation；`creator_user_id` 是 required nullable，null 表示没有 observed metadata，非 null 也只是 authenticated observed metadata。官方文档没有长期稳定/不可回收保证，null/非 null/值变化均禁止进入 stable domain/cohort/cache identity。Codex subject evidence source保持未登记。
- IdentitySourceContract、ProviderIdentityDomain、EndpointBudgetGroup/Binding 是 manifest 封闭子图：source kind/binding kind、stability basis/generation 与 endpoint 映射必须双向完整；重复、悬空、未使用或一个 endpoint 多 group均在凭据/evidence 前拒绝。DeepSeek/OpenRouter 都只登记 credential-generation source与各自保守 group；OpenRouter 不登记 `creator_user_id` domain，恒用 `openrouter-current-key-global-v1` 的 endpoint/deployment conservative cohort；Codex 只保留实验预算 group，没有 verified-stable source/domain，且不得加入 `account/read`。
- Capability 缓存/LKG 键包含 adapter/principal/subject/capability/cache identity/`query_contract_generation`；该 generation 绑定 endpoint/network policy、selector、kind/label/unit/currency/status/scale、semantic/display contract、Adapter/API version、ordered/versionless ProtocolContract、canonical schema hash、release assurance 与发行 attestation。网络 singleflight 同样包含 generation、endpoint、request kind 与规范化 selector。限流键改用 rate-limit cohort，不使用 principal 作为风险预算边界。
- Adapter 只返回完整 key 集的 success/unavailable/failure observation，不返回或读取 LKG/Snapshot。core 验证全批后在当前 generation 原子读取 LKG并合成 fresh/stale/expired；本地授权拒绝始终为零快照 OperationError，上游 entitlement 缺失才是 `unsupported+not_entitled`。每个已启用 capability 使用精确 FreshnessPolicy：DeepSeek/OpenRouter 分别只引用设计方案唯一 `DEEPSEEK_FRESHNESS_SECONDS`/`OPENROUTER_FRESHNESS_SECONDS`；Codex parser-only 不产生可接受 observation。Provider 状态全部到期，只有 core offline manifest-static 状态可永久。
- refresh 的公开成功值是按request digest canonical排序的判别result tuple；每个完整request key集恰一结果。Provider业务失败分支携带恰覆盖key集的LKG stale或无LKG expired snapshots，rate-limit可携带有界Retry-After；只有pre-attempt deferred/capacity/timeout和outcome_unknown可空。`FetchFailureCategory→health/status/snapshot`封闭映射与幂等逐字节重放只按设计方案第7.1节；形成tuple后即使全部失败也保存/返回完整success envelope。
- manifest loader 必须离线闭包 profile→network/structure/identity source、source→binding/evidence/domain/endpoint、endpoint→auth/response/deadline/frame/budget group、subject→selector/capability/plan、capability→semantic/freshness/display、semantic→canary、structure→breakage；undocumented profile 恰一 StructureContract，其他为 null。未知/悬空/重复/未使用拒绝。
- Supported/GA 发布使用 exact `aq-release-attestation-envelope-v1`、distribution-specific release key threshold 与 raw wheel/assurance/report/build proof 绑定。安装器从内嵌 genesis anchor 或已安装 current trust bundle 开始逐条验证连续 trust chain，新 root 不能自签跳过旧 threshold；生产目录恰等于固定 control set 与 signed target set，不接收第三方 lock、sdist 或 source-review 工件。所有 envelope 先按 `aq-bounds-v1` 限 raw bytes/JSON AST/count，再做 parse/JCS/crypto/hash，最后才生成 staging lock 并运行 pip。
- 刷新限制按 source type 分层并持久化：公开 API 默认同一 cohort/完整请求 30 秒，非公开接口至少 5 分钟且同一 cohort/endpoint 每小时最多 6 次；纯本地 official-cli 不继承 HTTP 默认值，由 manifest 明示地板并继续受 singleflight/并发/协议限制。无法验证稳定上游身份时使用 Adapter/endpoint 部署级保守 cohort，不得复制 principal 扩容。
- I/O class 由core固定判别：本地schema/file/version/无业务method握手为pure-local，全部outbound HTTP与local-stdio业务request为Provider I/O。doctor/discover/refresh的每次Provider I/O都必须先消费matching receipt；所有verified attempt也原子占endpoint budget group umbrella，身份未知时发送前检查该group全部activity的union。验证身份后只给同一row附加verified索引，umbrella+verified不双计。复制principal/binding/process或丢失identity cache不扩容；identity+quota同一response只复用为一次observation。
- 跨进程限流唯一使用同一 SQLite `BEGIN IMMEDIATE` 的 `reserved→committed|outcome_unknown` 状态机与 writer lease/fence；active unexpired reserved 与 committed/unknown 都阻塞 floor，hour bucket 也统计三者，partial unique 保证同 floor key 仅一个 active reservation。只有零 Provider bytes 且 owner/fence 匹配的 cancel，或旧 lease 到期后更大 fence 接管，才可回收 reserved；committed/unknown 永不因 lease 释放。
- rate writer/reservation/queue/slot/migration/temp claim 的policy ID与全部时序只执行[`lease-policy-v1`](contracts/lease-policy-v1.json)的typed formula AST。DB UTC/monotonic域、唯一remaining-time转换、crash grace位置、checked arithmetic与overflow verdict均由artifact决定；host/Adapter不得覆盖或以散文公式替代。
- 所有失败计数、Scheduler/on-demand probe/fetch 允许动作与恢复事件只以 [Provider 契约第 9.4 节](provider-contract.md#94-连续失败与恢复) 为规范源；其他章节不定义泛化“三次失败”规则。
- config validate 使用 `network_mode=offline`，I/O 均为 0；probe 不含 discovery，DiscoveryResult 只有三个封闭 missing reason。正式 ID、越 scope seed、外部 ID key、控制字符 label 或超量条目整批拒绝；本地 not_authorized 只为 OperationError。

Provider 响应、DNS、代理和 TLS 对端都位于 TCB 之外。凭据只在请求发送前的最后阶段解析；目标校验失败时不得解析或附加凭据。

操作错误与 capability 快照严格分离。operation/stage/error 的唯一机器源是 [`operation-contract-v1`](contracts/operation-contract-v1.json)；endpoint validation 和 idempotent replay 都先于 credential resolve，official-cli zero-binding 路径从不调用 Source。入口未知 operation 只返回 `recognized_operation=null`、有界域分离 raw digest且不回显原文的零副作用 `OperationContractFailure`；受信任 core 表外转移只触发不序列化 fatal。错误不携带 LKG；旧值只能另行授权 status 读取。

## 10. 本地存储、删除与备份

macOS/Linux 路径由 `platformdirs` 解析，权限基线：

- 解析后的配置目录：`0700`，`config.toml` 与迁移备份：`0600`。
- 解析后的数据目录：`0700`。
- SQLite 主文件、`-wal`、`-shm`：`0600`。

进程以拒绝式策略校验权限；不能安全创建或修正时停止加载机密数据。文件创建使用 `umask 077`/等价原子权限。Windows 在 ACL/Credential Manager 契约实现前返回 `unsupported_platform`，不得套用 POSIX 数字权限后继续运行。

### 10.1 唯一保存期限表

本表是所有文档、默认配置和清理任务的**唯一规范保存期限源**；其他章节只能引用条目 ID，不得重新声明数值。边界使用数据库 UTC：记录在 `created_at + ttl <= now` 时到期，清理与业务事务使用同一时钟。幂等记录到期后，相同外部 ID 不再享有旧结果保护，只能在重新授权并通过当前 endpoint-group BudgetPolicy 后作为新请求执行；产品必须明确这不是永久重放防护。

| 条目 ID | 数据 | 保存期限与起点 | 到期动作 |
| --- | --- | --- | --- |
| `RET-SNAPSHOT` | 当前与 LKG 的额度/余额/计数值 | 最后成功写入起最多 7 天 | 删除数值；不清结构/语义/失败/刷新状态 |
| `RET-LOG` | 默认应用日志 | 写入起 7 天 | 删除/轮转 |
| `RET-IDEM-CLI` | CLI refresh 幂等 | `prepared` 起 24 小时 | 删除记录；重放按新请求处理 |
| `RET-IDEM-WEB` | Web refresh 幂等 | `prepared` 起 24 小时 | 同上 |
| `RET-IDEM-FEISHU-TEXT` | 飞书文本 refresh 幂等 | `prepared` 起 24 小时 | 同上 |
| `RET-IDEM-FEISHU-CARD` | 飞书卡片复合键、action 消费与安全投递摘要 | `prepared` 起 30 天 | 删除记录；action 已先按第 11 节 `ACTION_TTL` 过期 |
| `RET-ALERT-ACTIVE` | open/acknowledged AlertEpisode、contributing sources、dispatcher/delivery state | 对象/generation 启用且 episode 未 resolved 期间保留 | resolve 或对象 inactive/generation replaced 时原子 terminalize，不直接删除 |
| `RET-ALERT-TERMINAL` | resolved episode、terminal reason、notification sequence/安全投递摘要 | `resolved_at` 起 30 天 | 删除 episode/source/delivery；不复活或重投 |
| `RET-CONSENT-ACTIVE` | LLM consent 的假名 actor/platform、scope digest、generation、expires/revoked 状态 | 签发至 `min(issued_at+24h, revoked_at)` | 到期/撤销/对象 inactive 时原子转 tombstone并递增 generation |
| `RET-CONSENT-TOMBSTONE` | 已终止 consent 的 scope digest、generation、terminal reason | `terminal_at` 起 30 天 | 删除；旧 ConsentContext 已先因到期/generation 不匹配而永久无效 |
| `RET-AUDIT` | 最小安全审计与假名化关联 | 写入起 30 天 | 删除 |
| `RET-MIGRATION-AUDIT` | 不含配置值的 migration digest/结果 | complete 起 30 天 | 删除 |
| `RET-MIGRATION-BACKUP` | `0600`/加密迁移备份 | 迁移确认后立即删除，任何情况下创建起不超过 7 天 | 安全删除；不含解析后 secret |
| `RET-RATE-LEDGER` | refresh floor/hour cohort ledger | capability 启用时按策略窗口持续保留；对象 inactive 后 30 天 | 到期删除；对象重建前仍沿用预算 |
| `RET-KEY-VERIFY` | cohort/idempotency/action/pseudonym 的 verify-only key | key 退役起 30 天、所有引用到期、该 key 所签 action 的最大 `expires_at` 到期三者取最晚 | journal 清除 key material，只留 retired key ID |
| `RET-SUBJECT-METADATA-OBSERVED` | `persist:v1:subject_metadata_observed:update:RET-SUBJECT-METADATA-OBSERVED` 的 subject/generation 与假名化 `last_observed_at` | subject 启用且 generation 当前期间保留 | disable/delete/generation replacement 或 purge 时同事务删除 |
| `RET-SUBJECT-METADATA-PENDING` | 已知 plan_code 变化的旧/新有限 code digest、subject/generation 和维护告警去重 | 观察起 7 天或用户确认/拒绝/对象 inactive 取最早 | 删除 pending并关闭维护告警；confirmed plan 随 config 生命周期 |
| `RET-MIGRATION-TEMP-CLAIM` | `persist:v1:migration_temp_claim:update:RET-MIGRATION-TEMP-CLAIM` 与 `persist:v1:migration_temp_file:delete:RET-MIGRATION-TEMP-CLAIM` 的假名 claim、inode属性、digest和机密临时配置 | attach 到 active journal 或迁移完成前保留；无 journal 时只保留到 claim lease 到期并由更大 fence 接管 | active journal 按阶段清理；orphan 只按设计方案 no-follow claim 状态机清理，属性不符 fail closed |
| `RET-LOCAL-REAL-AUDIT` | 仓库外真实验证记录 | 写入起最多 7 天；无需调查时立即删除 | 删除 |

#### 10.1.1 机器数据清单与 retention lint

`data-inventory-v1` 以本表的 `RET-*` 行作为 TTL surface registry，并补充以下对象生命周期 surface；surface ID 全局唯一，规范正文中的持久化声明必须是单个 exact inline-code record `persist:v1:<surface_id>:<operation>:<owner_id>`。record 自含 surface、operation 与 owner，`owner_id` 必须逐字节等于 inventory 的唯一生命周期源；相邻 prose 不是授权边界。`subject_metadata_observed` 与两个 migration temp surface 分别只能引用上表对应条目；缺行、重复行、未知引用、owner 不匹配、同一 surface 多个 RET owner 或 inventory 行没有正文引用均失败。

| surface_id | owner/介质 | 唯一生命周期源 |
| --- | --- | --- |
| `subject_metadata_observed` | SQLite subject metadata | `RET-SUBJECT-METADATA-OBSERVED` |
| `migration_temp_claim` | SQLite claim | `RET-MIGRATION-TEMP-CLAIM` |
| `migration_temp_file` | config 父目录 regular file | `RET-MIGRATION-TEMP-CLAIM` |

`retention-source-lint-v1` 的唯一机器配置是 [`retention-lint-v1`](contracts/retention-lint-v1.json)。它固定本机核对过的Pandoc exact version、`commonmark+pipe_tables` reader、唯一extension set、Pandoc API version与Table/leaf AST模型，并以 exact file + 每段 heading level/sibling ordinal/normalized text/identifier path + table ordinal + column ordinal分别定位唯一保存期限表和 data inventory；不再声称CommonMark core能产生Table。validator 从唯一保存期限表第一列构造严格、无重复的 `RET-*` byte set，inventory 的每个 owner 必须逐字节属于该集合，三个 surface join 再与 9 个 live record 完整闭合。复制/移动表、标题改名或同义改写、相同位置替换、前插标题、跨层移动、重复 exact heading、相似表头、错误 ordinal、重复/缺失/未知 ID 均 fail closed；version/extension/API不匹配同样拒绝。任何 locator 标题文字或 identifier 变化都必须升级 artifact 并改变摘要。

扫描节点、NFKC/casefold/相邻node拼接、数字/scientific/英文数字词/中文数字、单位词典、retention上下文、合法非retention runtime/constant排除与 `persist:v1:<surface_id>:<operation>:<owner_id>` record matcher只由artifact解释；歧义fail closed。persistence signal grammar v3 以最长匹配 token classes 识别 ordinary `file/local file/data file/configuration file/cache file/directory/keychain/keystore/database/WAL/journal` 及登记的中文同义词，并要求 write-action 或 sensitive-object+write-action 的有限词距组合。validator 从 leaf 文本逐个移除唯一 exact record 后重新扫描；任何剩余 signal 都独立拒绝，不能由同 leaf、同句或跨句的无关 record 借壳，只有既有 digest-bound exact leaf exception 可放行。fixture逐条按`source`走相同detector，`fixture_id`仅用于诊断且禁止行为override；fixture文件仍排除于live Markdown inputs并单独做schema/digest验证。

CI 必须先用exact reader解析当前四正文并证明两个locator各唯一命中且live scan accept，再把fixture的每个source注入同一AST pipeline并与其expected verdict比较。变更前后以`(file,heading ordinal path,AST node ordinal,leaf digest)`比较；新增/修改持久化声明必须使用独立 Code span record `persist:v1:<surface_id>:<operation>:<owner_id>`，其 owner 与 inventory 唯一匹配。record 被移除后同 leaf 的普通持久化 signal 仍须独立拒绝；漏行、重复record、owner不匹配、未知surface、inventory无live引用或code/table/HTML复制owner literal都失败。

最近成功结构指纹、`semantic_contract_id`、失败计数、`last_success_at`、暂停和刷新限制不是历史快照，在对应 capability 启用期间保留；其生命周期由对象状态机而不是 TTL 驱动。快照值到期不得重置漂移检测或失败历史。完整飞书事件体、Provider 响应/响应头/错误正文和凭据从不持久化，不属于“到期后再删”的数据。

alert/consent 记录只保存假名化关联和本地枚举，不保存额度值、label 或完整平台身份。principal/subject/capability disable/delete、generation replacement 或 purge 必须在同一事务 terminalize 相应 active alert/consent；purge 再按已确认清单删除。`RET-KEY-VERIFY` 的“所有引用到期”明确包括 active/terminal alert delivery pseudonym 和 consent tombstone；key 不得在这些记录之前删除。虚拟时钟覆盖 open/ack/resolved、投递后崩溃、consent 到期/撤销/重建、对象 inactive、key 轮换和每个相关 RET 条目的到期边界。

保留与删除的其他规则：

- principal/subject 的 disable/delete、capability 从 enabled 列表移除和 Adapter `manifest_removed` 是四种不同事件，严格采用设计方案第 10 节生命周期矩阵。存在 policy/view/后代引用时，普通 delete/disable/Adapter 激活返回 `referenced_object_conflict` 且零写入；只有显式 `--cascade`、相同 dry-run plan digest 和一次确认 nonce 才按固定计划修改引用。所有再启用都生成新 query generation；refresh ledger 使用 `RET-RATE-LEDGER`，不能随对象清理而让重建绕过预算。
- `migrate --dry-run` 与正式迁移日志共用脱敏器，不输出原始记录 ID，只使用本次运行内稳定的类型化句柄、字段路径、操作和 plan digest；principal/subject label、selector、外部 ID、完整 CredentialRef 及值一律使用类型化占位符。当前 opaque ID 保持；引用图唯一且非 secret-like 的 legacy ID 只经显式 `migrate legacy-ids --cascade` 确认后生成新 ID并重写引用；secret-like、重复、歧义或悬空输入返回 `migration_conflict` 且零写入。
- 备份默认排除 Agent Quota 数据库。显式备份必须加密、限制访问，并应用相同保留和第 10 节对象生命周期策略。
- 应用无法替用户清除 Time Machine 或其他系统级备份中的历史副本。macOS 初始化/doctor 应建议并检查数据目录的 OS 级备份排除；未排除时明确提示系统备份可能绕过 `RET-SNAPSHOT`，`purge` 也不保证删除既有备份。
- 不持久化完整 Provider 响应、响应头、上游错误正文、完整飞书身份或任何凭据。

权威配置是 `config.toml`，SQLite 只保存 active digest/generation/运行状态。两种介质不得宣称同一 ACID 事务；所有配置和运行状态切换使用[设计方案第 10.2.1 节 migration journal](design-proposal.md#1021-toml--sqlite-migration-journal)：`BEGIN IMMEDIATE` 获取唯一 writer lease 与单调 fencing token，部分唯一约束只允许一个 active migration，每个 migration 使用独立 `0600` 临时文件。journal 一旦 prepared 固定 roll-forward；每个文件/DB 动作都验证当前 fence，旧 token 不能提交。启动和运行中每个服务入口/调度 claim/长任务提交都验证文件、DB、内存的 config/generation/runtime fence；外部 TOML drift、active migration 或更大 fence 立即关闭 gate 并恢复。逐点 kill、双 CLI、CLI+daemon、外部编辑、lease 接管和连续重启测试必须证明只收敛到一个新态，不出现半删、旧宿主继续查询或扩大 cascade。

Migration action 的object ref是`existing`/`new`判别联合；NewObjectRef必含envelope内`creation_parent_ref`并进入semantic body/handle/digest，只凭envelope即可重算。graph覆盖creation-parent、create-before-use、remove-ref-before-disable/delete、child-before-parent-delete、generation replacement与cascade全部依赖；隐藏依赖拒绝。唯一Kahn拓扑对全部typed edge计算indegree并用semantic key bytes tie-break，之后才赋action ID；每个拓扑前缀都必须可执行。

journal前的规范记录 `persist:v1:migration_temp_claim:update:RET-MIGRATION-TEMP-CLAIM` 只允许`name_claimed→file_opened→file_sealed→attached`或更大fence接管到`cleanup_claimed`。journal提交完成使用`db_committed→cleanup_pending→complete`：cleanup_pending保留parent/inode/digest/claim/fence字段，先幂等unlink同migration temp、fsync父目录、删除同fence attached claim并写cleanup proof，最后DB事务才complete/清机密字段。complete禁止残留attached claim；任一kill point由cleanup_pending恢复，不依赖orphan猜测。

外部 TOML 的有效语法不等于已确认变更。drift 恢复必须用 old DB registry/manifest 与新文件运行同一类型化 planner；安全自动采用集合严格限于 presentation、现有 subject 的纯展示字段，以及只引用已启用绑定对象且不改变授权/运行数据的 view 过滤修改。disable/delete/manifest removal、所有权/policy/后代引用移除、selector/endpoint/auth/binding/capability/manifest 变化与 generation 数据清理必须关闭 gate，输出脱敏 dry-run，并要求完全相同的 plan digest 与一次 nonce 后才建立 `file_committed` journal。确认前 active config/generation digest及全部运行表零变化，且不解析凭据、不启动 Codex、不访问 Provider；再次编辑或 manifest 漂移使 digest/nonce 失效。

SQLite `secure_delete` 与 WAL 清理可作为纵深措施，但不能替代“不存原始响应”和保留期控制。

`agent-quota init`按[设计方案第10.0节](design-proposal.md#100-installationregistry-与-localkeyring)建立唯一envelopes。业务purpose/consumer/HKDF/rotation/lookup及LocalKeyRing envelope/payload schema只读取[`local-key-purpose-registry-v1`](contracts/local-key-purpose-registry-v1.json)：wire exact literals为HKDF-SHA-256/AES-256-GCM，nonce/ciphertext+tag/public_salt/key material仅无padding base64url，decode全部字段后才检查12/至少16/16/32-byte边界，AAD/nonce recipe与golden bytes同源。journal原子预留generation/sequence，回滚/交换/mismatch均`local_keyring_unavailable`；普通备份只接受完整installation集合，purge最后删除binding并逐父目录fsync。

## 11. 飞书卡片重放与动作绑定

所有 `quota_refresh` 使用 core 的持久化 at-most-once 契约。唯一键绑定假名化 actor、operation、canonical scope digest 和至少 128-bit 请求 ID：CLI 保存 opaque retry handle，飞书文本从可信 event/message ID 派生，Web 的随机 `Idempotency-Key` 再绑定认证 session，卡片使用下述复合键。Provider 调用前提交 `prepared→running`；重复只返回已保存安全状态。进程在 Provider 调用与结果提交之间崩溃时恢复为 `outcome_unknown`，相同键不得再次调用 Provider。期限分别只引用 `RET-IDEM-CLI`、`RET-IDEM-WEB`、`RET-IDEM-FEISHU-TEXT`、`RET-IDEM-FEISHU-CARD`；限流使用 `RET-RATE-LEDGER`。Hermes 的内存去重不能作为安全边界。

本节是卡片 action 时间合同的唯一规范源：`ACTION_TTL = 15 minutes`，签发与验证都使用数据库 UTC，且 `expires_at` 必须恰好等于 `issued_at + ACTION_TTL`。静态不变量是 `ACTION_TTL < RET-IDEM-FEISHU-CARD`；有效消费还必须满足 `issued_at <= prepared_at < expires_at`，因此可证明 action 在 idempotency delete 前到期。签名纳入 `key_id/issued_at/expires_at`；任一超界、倒序、未来 issued time 或自定义 TTL 即使密码学签名正确也拒绝。验证顺序固定为字段/授权 → key 状态 → `issued_at <= now < expires_at` → 签名 → 单次消费；到期后不查 Provider。active key 轮换为 verify-only 后，至少保留到该 key 所签 action 的最大 `expires_at` 与 `RET-KEY-VERIFY` 共同要求的更晚时刻；消费记录至少保留 `RET-IDEM-FEISHU-CARD`。因此任何仍可验签的 action 都仍处于消费记录保护窗，任何消费记录被删除前所有对应 action 都已过期。

每个动作的必需绑定为：

```text
(event_id, operator_id, tenant_id, app_id,
 chat_id, message_id, action, subject_id, capability_id)
```

规则：

- 任一字段缺失即拒绝，不尝试降级拼接键。
- 卡片 `value` 只包含服务端生成并签名的 opaque `action_id` 与 subject/capability 引用；签名绑定 tenant/app/chat/message/action/subject/capability 和过期时间。
- 执行前事务性插入唯一幂等键并消费 `action_id`。相同事件返回已保存的安全结果，不重复读取凭据或访问网络。
- “刷新授权范围内全部主体”必须展开为 subject/capability 集合，并分别建立绑定与幂等记录；不能用通配记录绕过主体/能力绑定。
- 为防止替换 `event_id` 重放旧按钮，`action_id` 单次使用；更新后的卡片签发新 ID。
- 若 Provider 刷新成功但卡片更新失败，幂等记录保存安全结果摘要与 `delivery_state=update_failed`；相同事件返回该状态，不再次读取凭据或访问 Provider。已消费 ID 不得复活，用户通过同等授权的 `/刷新`/`/额度` 或系统重发的新卡恢复操作。
- 授权与签名校验先于幂等记录、缓存修改、失败计数和 Provider 请求。
- 幂等记录只保存动作状态、时间和带本地密钥的假名化关联标识，期限为 `RET-IDEM-FEISHU-CARD`。该标识只降低“记录离开设备但密钥未一起泄露”时的直接关联性，不是匿名化或本地隔离边界；同 uid 同时取得记录和密钥即可重新关联。
- 虚拟时钟测试必须覆盖签发前/恰好 `ACTION_TTL` 边界、消费前后、active→verify-only key 轮换、`RET-IDEM-FEISHU-CARD/RET-KEY-VERIFY` 清理边界及其后重放、并发双击、跨用户/租户/群/消息、替换 subject/capability、超界 TTL/过期但签名正确的 action，以及“Provider 成功、卡片更新失败、重复回调不再刷新、命令/新卡可恢复”。

## 12. 上游内容与提示注入

Provider 返回的 `message`、错误正文、响应头、计划名、对象键和未知字符串都视为不可信数据。安全映射规则：

- Adapter 将上游状态映射成本地枚举 `status_code`，不把原文写入 `CapabilitySnapshot`。
- 上游 plan 只能生成 manifest 有限 `SubjectMetadataObservation(plan_code)`；unknown/null/自由文本丢弃。首次值随用户确认写 config，变化值使用 `RET-SUBJECT-METADATA-PENDING` 和无 plan 原值的维护告警，只有 planner/digest/nonce 确认才切 subject/query generation。
- 可展示参数采用带判别标签的受限联合，只允许有限数字、core 支持的币种、manifest 中的有限枚举和带时区 UTC 时间；普通字符串/短标签不属于合法值。
- core 按本地 `status_code` 强制参数名、类型和枚举 schema，未知参数或值一律拒绝；Adapter 白名单不是唯一防线。渲染器只把本地枚举映射为文案，并对 Desktop/终端/飞书/远期 Web 目标转义。
- LLM 最小投影不包含任何上游自由文本。
- 结构指纹只处理 Provider 静态路径白名单；映射型对象的动态键统一为 `<map-key>`，未知键丢弃。
- 差异日志只记录本地 path ID 的新增/缺失，不记录原始动态键或值。

测试 fixture 必须包含伪造的提示注入、HTML/Markdown、终端转义、Token、邮箱和以用户 ID 为对象键的响应，证明它们不会到达任何输出渠道。

## 13. Desktop GUI 安全

Desktop 边界的唯一机器源是 [`core-safety-contract-v1.desktop_product_contract`](contracts/core-safety-contract-v1.json)。macOS MVP 使用签名 Tauri 2/Rust host、bundle 内 React/TypeScript 静态 renderer 与 Python core sidecar；不启动 HTTP 或 loopback listener。

- renderer 是不可信展示层。生产 CSP 默认 `default-src 'self'; connect-src 'none'`，禁止任意外部导航、新窗口、远程脚本、文件系统、网络、shell、进程、sidecar 与 secret-input 能力；只暴露设计方案第 6.1 节的封闭 Tauri command allowlist。机器合同逐 command 绑定 request/response schema reference；29 个同源 DTO schema 均封闭 `additional_properties=false`，nested reference 只能指向同表内有类型、有界、脱敏 schema。`config_validate_apply` 的 change-set/change 也属于该闭包，只能直接提交 core 分类为 non-destructive 的变更，destructive diff 必须转 trusted surface；`credential_dialog_open` 只能无 secret payload 地请求 host 打开原生安全面；`destructive_confirmation_open` 只能请求 trusted surface，不能收发 plan/digest/nonce/user-presence token；未知 command、额外/nested 字段或枚举在到达 application service 前拒绝。
- Rust host 在每次启动前以 no-follow 方式解析 bundle 内固定 sidecar，验证路径、代码签名、Team ID 与登记 raw hash；验证失败不回退 PATH、用户目录、下载文件或 shell。
- host 只通过继承的匿名 pipes/stdio 启动 sidecar，并通过独立继承 pipe 传递每次启动新生成的 256-bit session secret。协议为 `u32be_length || utf8_json`，单 frame 最大 1 MiB；`request_id` 是每 session 从 1 开始的 unsigned 64-bit counter，host 严格加一，sidecar 只接受下一值，响应原样回显，溢出前终止会话。请求只跨边界传 `remaining_budget_ns`，范围 `1..9_000_000_000`，不传 host 绝对 monotonic epoch；sidecar 收完合法 frame 后以本地 clock checked-add 重建 deadline，同时受 host 原始 9 秒 hard cap 约束。传输/排队会消耗 host 预算，`now >= deadline`、越界、overflow 或跨 session 复用在 dispatch 前拒绝且 Provider I/O/写入为 0。dispatch 后 host 超时固定为 `outcome_unknown`、禁止自动重放，并在 0.5 秒 TERM 后 KILL、reap，要求 orphan 为 0；不能声称写入为 0，最终由既有幂等/事务恢复判定。未知/重复/错序/超时/超界 frame 终止 sidecar。生产 sidecar stderr 在 spawn 时直接连接 OS null sink，不创建可能阻塞的未读 pipe；原始 stderr 不进入日志、renderer 或 IPC，结构化错误只走 IPC error 联合。
- renderer 不直接接触 API Key、Cookie、CredentialRef、session secret、上游原文、SQLite/WAL/SHM、安装注册表或本地关联密钥。API Key keystroke/paste 只进入 WebView 之外的 host-owned native secure dialog，或由该 dialog 选择既有 Keychain item；完成系统凭据导入后 host 清空原生缓冲区，只返回 opaque reference/status。dialog 仅在 app foreground + key window 打开，每 installation 同时最多一个 trusted dialog，host 执行 cooldown 并拒绝 renderer spam。`renderer-secret-input-path-absent` 必须证明 DOM/event/state/prop、Tauri command 与 IPC DTO 都没有 secret value/length/buffer 字段。
- purge、disable/delete/cascade，以及移除/替换 endpoint/auth/binding/capability/manifest 的 destructive config diff，都必须先由 core 生成脱敏 plan，再只在 Rust host-owned native confirmation surface 展示并捕获 user presence。nonce/token 只在 host↔core，renderer 只收到 `cancelled|committed|status`；失焦、取消、plan/generation 变化、重复/并发请求均零副作用 fail closed。`renderer-destructive-confirmation-token-absent` 必须覆盖 renderer bundle、command schema 与全部 host→renderer DTO。
- 应用固定单实例。第二实例只发送无业务 payload 的 activate 信号；第一个实例继续持有 writer lease。sidecar 崩溃时 host 最多自动重启一次，只恢复只读 bootstrap/status；refresh/configure/reauth/purge 返回 `outcome_unknown` 或安全错误，未经幂等确认不得自动重放。
- 升级使用签名、原子替换；host/renderer/sidecar/contract bundle 必须来自同一发行 attestation。版本或摘要不一致在读取凭据、打开写事务或启动 Provider I/O 前 fail closed，失败升级保留完整上一版。
- Desktop 只能展示 scheduler 的真实状态。没有已安装且可验证的 OS scheduler/daemon 时显示“未启用”，不得以 renderer timer 或窗口存活模拟后台运行。
- 该边界不承诺抵抗已控制同一 OS 用户、已控制 Tauri host/WebView 或已替换系统信任根的攻击者；这些条件进入受支持恢复/重装流程，而不是继续运行。

### 13.1 远期 Web

远期 Web 是独立 host 和认证浏览器会话，不复用 Desktop IPC。即使只监听 `127.0.0.1`，也必须同时交付随机会话凭据、严格 Host/Origin、默认拒绝 CORS、CSRF、防 DNS rebinding、请求/响应/并发/速率/超时上限以及 AccessContext 授权；“只监听 loopback”不构成认证。Web 未实现前 Desktop 绝不开放 loopback 端口。

## 14. 日志与审计

允许记录：本地 request ID、稳定 Adapter/endpoint ID、状态码、耗时区间、是否命中缓存、带本地密钥的假名化 actor/subject 关联 ID、授权/幂等结果。

禁止记录：凭据或 Credential Lease 内容、AccessIdentity 的 `cache_identity/rate_limit_cohort`、完整 CredentialRef、原始记录 ID、principal/subject 别名与 selector、余额、精确额度、认证状态、完整飞书标识、原始请求/响应、上游错误正文和卡片 payload。

日志使用 `RET-LOG`，安全审计使用 `RET-AUDIT`，各渠道幂等分别使用第 10.1 节对应条目；不得以“安全幂等”统一成一个期限。假名化只针对不含本地密钥的离机副本降低直接关联性，不防同 uid 读取密钥与记录。调试模式不能放宽 Secret/Confidential 数据禁令。任何观察插件都不能通过正常 hook 收到确定性额度命令结果；Hermes 同 uid 恶意/失陷插件仍可直接读数据库，这是第 5 节已接受风险。

## 15. 开源与真实数据边界

- 仓库、测试、文档、Issue 和 CI artifact 只使用明确标注的虚构账户和数值。
- 真实验证结果保存在仓库外、本地受限目录，使用 `RET-LOCAL-REAL-AUDIT`。
- 发布前运行 secret 扫描与账户数据扫描，至少覆盖常见 Token、邮箱、余额货币格式、Open ID、Tenant/App ID 和已知本机账户别名。
- 不提交完整原始响应，即使声称已经删掉 Token；只提交人工构造的最小 fixture。

## 16. 威胁与验收证据

| 威胁 | 强制控制 | 最低验收证据 |
| --- | --- | --- |
| 订阅/工作区被错误合并到账户 | principal/subject/capability 分层 | 同身份多主体、多能力与删除隔离测试 |
| 展示 view 被误用为授权 | 先授权、后 view 过滤 | scope 外引用、悬空引用与混合组合测试 |
| 可选 Hermes 反向进入默认 TCB | profile 分离 + 包依赖单向 | 无 Hermes 干净环境安装与 import graph 测试 |
| FakeAdapter 进入生产安装 | 独立 testkit 发行 + 生产依赖闭包禁止 | 两个无源码虚拟环境分别证明 testkit 可用与生产 entry point 无 Fake |
| Hermes 同 uid 插件直接读取机密库 | 明示已接受风险 + Desktop/独立 OS 用户建议 | 安装确认、TCB 清单与文件可读性威胁测试 |
| 详细额度进入 LLM/插件钩子 | 网关前置命令 + 确定性渲染 | 端到端测试证明无 `role=tool`、无通用 hook 观测 |
| LLM 跨时间重建使用趋势 | 每次重验同意 + generation 撤销 + actor/scope 与 deployment/scope 双层预算 | 既有会话撤销、过期、跨 actor 采样与缓存桶测试 |
| 群聊聚合/差分去匿名 | 群聊零额度披露 + 固定私聊引导 | 任意规模与重复调用的响应不随额度状态变化 |
| 未授权 actor 查询全部主体 | AccessContext + 绑定式 AccountScope + 默认拒绝 | 本地与集成跨主体/能力及笛卡尔积越权测试 |
| Adapter 返回跨身份标识污染配置/缓存 | discovered DTO + network mode + core 整批校验调用/registry/manifest/query generation | 恶意 FakeAdapter 正式 ID、跨 principal/subject、selector/missing/额外/重复返回测试 |
| 卡片重启后重放 | 持久化复合键 + 单次签名 action | 重启、超时、并发双击测试 |
| 刷新成功但卡片更新失败 | 保存投递状态 + 命令/新卡恢复 | 更新失败后不重复 Provider 请求测试 |
| 凭据经环境代理外发 | `trust_env=False` + 固定出口 | 恶意代理环境变量测试与目标断言 |
| Codex RPC 越权写操作 | 发送端 RPC allowlist | `account/rateLimitResetCredit/consume` 拒绝测试 |
| Codex 子进程劫持或资源耗尽 | no-follow install ID + 最小环境 + frame/时间/进程组上限 | PATH/symlink、环境探测、洪泛、挂起、fork/zombie 测试 |
| 同 Provider 多组合串用 | 完整 principal/subject/capability/selector 键 | 并发不同身份/主体/能力不合并测试 |
| 配置/语义变化复用旧值、双 writer 分叉或运行时 drift | query generation + writer lease/fence + TOML/SQLite roll-forward journal + 服务 gate | Desktop+CLI/daemon、外部编辑、旧 token、各阶段 kill/restart |
| 复制 principal 绕过 Provider 限流 | core 生成 rate-limit cohort + 无身份时部署级保守 cohort | 相同凭据/账户跨 binding/principal 共用预算测试 |
| official-cli 切换账户复用旧缓存 | verified stable session identity + cache identity 代际 | 切换、登出重登、无稳定身份 fail-closed 测试 |
| 超大/压缩响应耗尽内存 | 流式 wire/decoded 上限 | Content-Length、chunked、压缩炸弹 fixture |
| SQLite/备份泄露额度 | 0700/0600、保留与删除 | 权限、WAL、主体删除和到期清理测试 |
| purge 越界删除用户文件 | init 固定 InstallationRegistry roots + no-follow 句柄/二次 inode 校验 | XDG/HOME/cwd 变化、registry 篡改、同名目录、root/home/symlink/TOCTOU/mount corpus |
| 系统备份绕过应用保留期 | OS 级排除建议/检查 + 残留告知 | macOS doctor 提示与 purge 边界测试 |
| 假名化被误当本地隔离 | 明示仅防不含密钥的离机副本 | 同 uid 取得密钥与记录的威胁测试 |
| dry-run 经自由格式 ID 泄密 | core 生成 opaque ID + 输出运行内类型化句柄 | 邮箱/Token/外部账号 ID 导入与迁移 fixture |
| 上游提示注入进入输出 | 状态码映射 + 无自由文本 | 多渠道恶意 fixture 测试 |
| 操作错误被伪装为额度状态 | 封闭 OperationResult 与快照表面分离 | 凭据 backend、Adapter 越界、stdio frame/timeout 的序列化与副作用测试 |
| 结构相同但单位/语义漂移 | 版本化语义 canary + 不覆盖 LKG | 比例/百分数点与余额跳变 fixture |
| 未知时区触发错误告警/展示 | `timezone_unknown` 抑制时间策略 + IANA PresentationContext/UTC fallback | severity/通知不使用未知上游时间；三时区/DST/非法 profile golden 测试 |
| 动态对象键泄露身份 | 路径白名单 + `<map-key>` | 邮箱/用户 ID 对象键测试 |
| 不支持平台使用宽权限 | macOS MVP；Linux staged；Windows fail closed | 平台探测、安装阻断和拒绝测试 |
| renderer 直接越权或被外部内容劫持 | 封闭 command allowlist + CSP + bundle-only navigation + 无网络/文件/进程 capability | 未知 command、外部导航、CSP、文件/网络/shell/sidecar 负向测试 |
| 被攻陷 renderer 自行确认破坏性动作 | core 脱敏 plan 只在 host-owned native surface + nonce/user-presence token 不出 host↔core | `renderer-destructive-confirmation-token-absent`、伪造 confirm/重复/失焦/plan 变化均零副作用 |
| WebView 获取秘密输入或刷屏原生对话框 | host-owned native secure dialog + foreground/key-window/single-active/cooldown + 无 secret command/DTO schema | `renderer-secret-input-path-absent` 覆盖 DOM/event/state/prop/command/IPC，键入与粘贴只到原生 responder，并发/spam fail closed |
| Desktop sidecar 被替换、串话、stderr 阻塞或 frame 耗尽 | 签名/Team ID/raw hash + no-follow + 独立 session pipe + u64 session counter + stderr null sink + 有界 frame/correlation/deadline | 替换、symlink、错 session、ID 从 1 严格递增/回显/溢出、超界/挂起/大量 stderr 与 `sidecar-stderr-raw-output-absent` 测试 |
| 重复刷新产生重复副作用 | actor/scope 绑定持久化 at-most-once 键 | 四渠道并发/完成后/崩溃后重试测试 |
| 告警多策略拆成多个 episode、恢复后不能再次触发或多宿主刷屏 | capability/window 聚合 AlertEpisode + source 明细 + resolved 终态 + dispatcher fence | policy+health 合并、逐源清除、open-resolved-open-resolved、重启/双宿主测试 |
| 本地 key 丢失/轮换扩容预算或复活动作 | InstallationRegistry + 分用途 LocalKeyRing + verify-only 窗口 + fail closed | 重启、轮换崩溃、旧 key 到期、单文件丢失与 purge 测试 |

## 17. 分层安全门禁

### 17.1 阶段 0A：阻塞 Desktop/core/辅助 CLI

- [ ] core 生成 opaque 记录 ID、principal/subject/capability 与渠道无关 AccessContext 通过评审。
- [ ] Desktop host/renderer/sidecar TCB、受 foreground/single-active/cooldown 约束的 host-owned credential/confirmation surfaces、`renderer-secret-input-path-absent`、`renderer-destructive-confirmation-token-absent`、封闭 command surface、CSP/navigation、签名 sidecar、u64 session request ID、stderr null sink、stdio framing/session/deadline 和 core/CLI/Provider 单向依赖通过评审；testkit 独立发行且生产依赖闭包无 FakeAdapter。
- [ ] 含判别式 manifest/模型与 capability 聚合告警 episode 的 `schema_version=1`、脱敏 dry-run/cascade plan、writer lease/fence TOML+SQLite journal、运行时 drift、生命周期矩阵、InstallationRegistry/LocalKeyRing 和 purge 目标/TOCTOU 校验已定义。
- [ ] DeepSeek/OpenRouter 的 Credential Binding、verified AccessIdentity、rate-limit cohort、NetworkPolicy、probe 与缓存/请求键已冻结；Codex 固定 `experimental/incompatible` parser-only；Kimi/MiniMax/GLM 为 `planned/no-contract` 且 schema v1 拒绝。
- [ ] HTTP 唯一 URL 规范化/流式 wire/decoded 上限、Codex parser-only 负向边界和恶意响应测试已定义。
- [ ] platformdirs、macOS MVP 0700/0600、Linux staged、Windows fail closed 与 subject 删除/WAL 清理已定义。
- [ ] 上游安全消息、core 受限 display 参数、动态 map-key/语义 canary、未知时区抑制、Fake 多组合 fixture 与仓库敏感信息扫描已定义。
- [ ] 分 source type 的持久化刷新策略、全渠道幂等、失败恢复/告警状态机、system-credential fail closed、query generation、结构状态独立保留和系统备份残留提示已定义。

### 17.2 阶段 3A：只阻塞 `agent-quota-hermes`

- [ ] FeishuCallerContext → AccessContext、默认拒绝授权矩阵通过评审。
- [ ] 网关前置命令与不可伪造上下文桥接完成；详细结果不进入 LLM/通用 hook。
- [ ] Hermes profile 的全部插件 TCB 清单已建立，安装确认接受同 uid 插件可读机密库，Hermes Credential Source 命名空间独立。
- [ ] 飞书复合幂等键、单次签名 action、投递失败恢复、群聊零额度披露/私聊投影和重放测试完成。
- [ ] `llm_minimal` 的 ConsentContext、逐调用重验、generation 撤销、双层预算与持续披露提示通过测试。

3A 未完成时不得安装/启用 Hermes 集成，但不影响 Desktop profile 进入阶段 1/2。

## 18. 规范性参考

- [Hermes Agent Security Policy](https://github.com/NousResearch/hermes-agent/blob/main/SECURITY.md)
- [飞书卡片回传交互回调](https://open.feishu.cn/document/feishu-cards/card-callback-communication?lang=zh-CN)
- [HTTPX Environment Variables](https://www.python-httpx.org/environment_variables/)
- [HTTPX Developer Interface](https://www.python-httpx.org/api/)
- [OpenAI Codex app-server protocol](https://github.com/openai/codex/blob/main/codex-rs/app-server/README.md)
- [DeepSeek Get User Balance](https://api-docs.deepseek.com/api/get-user-balance/)
- [OpenRouter Get current API key](https://openrouter.ai/docs/api/api-reference/api-keys/get-current-key)
- [OpenRouter Get credits](https://openrouter.ai/docs/api/api-reference/credits/get-credits)
- [OpenRouter Authentication](https://openrouter.ai/docs/api/reference/authentication)
- [OpenRouter API rate limits](https://openrouter.ai/docs/api/reference/limits)
- [OpenRouter OpenAPI](https://openrouter.ai/openapi.json)

## 19. v1.6 安全闭包与剩余门禁

- 合同加载从固定 repository root 使用窄路径 grammar 与 no-follow descriptor；路径重解码、dot/repeated slash、case/Unicode/percent alias、symlink 或越界 fd 一律拒绝。所有登记数组有唯一机器顺序策略，不能由实现自行判断“registry-like”。
- retention lint 在 NFKC + casefold 后执行最长匹配 token classes；exact `persist:v1:<surface_id>:<operation>:<owner_id>` record 自含唯一 owner，移除 record 后 ordinary file/local/config/cache/directory/keychain/keystore、database/registry/sqlite/WAL/journal 及登记中文同义词与 write/sensitive-object 信号仍独立拒绝。任一 retention signal 的拒绝优先级高于 runtime timeout allow，故 `expire 30 days timeout` 不能绕过唯一 TTL owner。
- migration cascade 只是成员/理由关系，不产生执行依赖；删除只允许 child→parent。InstallationRegistry 的 MAC payload 原子保存完整 current bundle bytes/digest/sequence、按 distribution/publisher 分区的 attestation floor、accepted plan sequence/digest及 keyring/root状态；同 sequence 不同 digest、部分 restore 和跨组件回滚全部 fail closed。
- LocalKey payload 必须唯一选出 active/verify set，key ID、salt bit flip、禁止 purpose 的 verify-only、重复或跳跃 generation 都拒绝；salt不是 secret也不是KDF input。keyring、registry、DB 与 trust state 是同一 fenced update/restore set。
- 预算 floor/hour/reservation/blocked-until 按 endpoint group 与 verified cohort union 持久化。唯一机器聚合在同一 `BEGIN IMMEDIATE` 和同一 DB UTC sample 中取全部 active boundary 的最大值减 now并夹取；无 active 才返回 `None` 并允许 reserve，expired boundary 不计，顺序与 primary reason 不影响结果。doctor/discover 的预算或本地 ledger 拒绝不能触发 Provider/Credential/cache，也不能因未登记结果升级为内部 fatal。
- 本节保留 v1.6 当时的 Codex stable identity 未决背景；2026-07-19 当前决策已将 Codex 降级为 `experimental/incompatible` parser-only，不加入 `account/read`、不读取真实账户，也不降低安全要求。GUI/OpenRouter 新基线仍须新的独立 R20 审计后才能取得当前 release authority。

## 20. v1.7 安全闭包与剩余门禁

- reservation receipt 必须在 final context 创建前已经 committed；Adapter 永远看不到 pre-reservation plan。HTTP doctor/discover 在 credential backend 前先完成 conservative reserve，预算/ledger/storage 拒绝保持 credential 与 Provider 零副作用。
- 全部 schema 只使用带 meta-schema/version 的 `aq-array-order-v1`。lease crash grace 是 `int64_ms=2000` typed constant，`2^63` 及更大值结构上即拒绝。
- registry、retention 与 core 的 repo path 都使用同一 canonical segment grammar，并从一次打开的 root 逐 segment `openat(O_NOFOLLOW)`；dot、dot-dot、empty/repeated slash、absolute、backslash、case、percent、Unicode 与 symlink alias 全部拒绝。
- 规范性持久化 surface 只能由 `persist:v1:<surface_id>:<operation>:<owner_id>` 结构化 record 创建；record 自含并校验唯一 inventory owner，普通 prose 没有 storage 授权语义。core fixture runner 只读取 strict `domain+input`，fixture ID 仅诊断。
- LocalKeyRing 启动时要求八个 registered purpose 的集合完全相等且每个恰一 active；缺失、未知、零/双 active 与 payload-envelope 密码学不一致均 fail closed。
- 本节的“Codex stable identity 未决”是 v1.7 历史结论；历史 `AQ-R11-002` 仅为非规范性索引。2026-07-19 当前决策选择 parser-only 降级，不加入 `account/read`、不读取真实账户；当前变更须由新的 R20 审计建立新的 current status。

## 21. v1.8 只读验证与工具信任

- 合同 validator 对固定 allowlist 逐 segment `openat(O_NOFOLLOW)`，在任何成功状态前完成 JSON 边界、Draft 2020-12、digest、schema 实际枚举的全部数组策略、RepoPath、ProbeResult、operation、lease、LocalKey、retention 与 fixture 全门禁。Ajv 版本由 manifest 与 lockfile 双重固定。
- canonicalizer 已收窄为只读 verifier/renderer，不接受写入参数或自选根目录，不调用写入 API；artifact pin marker 由 registry 行投影并绑定 projection hash，任何分叉均 fail closed。
- retention 仅承认严格 record v1 `persist:v1:<surface_id>:<operation>:<owner_id>`；operation 必须是登记值，owner 必须逐字节命中 inventory。record 不授权 leaf 的其他 prose；旧格式、未知操作、跨 leaf、重复、owner 不匹配和多 signal 借壳都是拒绝路径。
- 未跟踪 checkout 内的工具仅是本轮审计证据，不构成发布信任。生产或 0A 必须由外部签名 release，或 VCS commit 加工具 raw SHA-256 与先前受信根授权固定；validator/canonicalizer 禁止自 pin。
- 第 12 轮五项实现问题的历史处置不变。Codex 产品决策已于 2026-07-19 选择 `experimental/incompatible` parser-only，仍不增加 `account/read`、不读取真实账户、不降低安全要求；GUI/OpenRouter 文档变更仍需新的独立 R20 审计。

## 22. v2.0 原子输入与可复现门禁

- live/fixture retention 共用一套 AST decision core；v3 grammar 覆盖 ordinary local/config/cache/data file、directory、keychain/keystore 与中文同义词。既有普通段落只能使用 artifact 内精确 path/leaf digest/reason 例外；新增 TTL owner、缺少 record v1 的 surface，或同 leaf 无关 record 试图授权普通 signal 都必须拒绝。三份主文档保留隔离负向 mutation，当前 9 条合法 record 保持通过。
- operation 成功计数按 path 推导，official-cli zero-binding 的 Credential Source 调用固定为 0；完整 error row/safe schema 被 exact marker 覆盖。lease operator、formula、policy reference 与 conversion 同时闭合 type/unit/clock domain。
- ProbeResult 的四分支 closure、official evidence 绑定/寿命与 identity derive 前置顺序由 core artifact、strict fixture 和 operation path 同时门禁；非 official evidence、未知分支、cross-profile 或 expired evidence 均在派生与写入前拒绝。
- 仓库 bootstrap 明确收窄为本地 runtime checker：它可拒绝替代 shell、新 entry、symlink/raw drift并从已打开fd执行exact entry，但任何本地成功都固定为“外部attestation缺失”，不能证明生产固定launch。生产或0A必须由仓库外既有信任根绑定实际解释器、已打开bootstrap/entry字节与runtime身份。系统动态image只由exact Darwin release/build覆盖；所有非系统 Python/Pandoc/Node image逐项登记canonical no-follow path、kind、uid/gid、mode、size、raw SHA与递归依赖边。bootstrap在Python摘要/Pandoc解析前核对关键image/opt/edge并清空未登记loader/Python/locale环境，guard与validator再核对实际loaded-image集合。clean install、双 replay、50-case suite及全部专项反例继续生效。
- 第 1–19 轮 audit/resolution 由 detached history manifest 逐文件 no-follow验证。manifest 在 1..20 中自描述连续输入，实际 snapshot 只读取 entries 派生的集合；latest 以 `ISSUES_OPEN` / `ZERO_ISSUES` 判别联合绑定四份 current-status marker。R20 zero是固定点且禁止resolution，R20 open明确round-budget-exhausted，R21拒绝；删除、替换、伪造首行、回滚、单点 marker 漂移或摘要自引用尝试均拒绝。`AQ-R19-001` 是不可改写的历史阻塞记录；2026-07-19 产品决策已另行处置，但 Gate 0A 在新的 R20 审计产生权威结果前仍保持关闭。
- validator、projection verifier 和发布门禁都以首次 no-follow 读取的 immutable bytes 计算 digest，并在成功前严格复核 inode/stat/长度/内容；发布入口要求显式 root、cwd/root/entry identity 闭包，入口 symlink、根替换、source symlink、并发替换与 mutation 结果缺失/重复/伪造必须 fail closed。
- 当前 profile 和未跟踪 checkout 仍只是审计证据，不能自授 release authority。Codex 已由 2026-07-19 决策降级为 parser-only；历史 `AQ-R14-001` 仅为非规范性索引，顶部 marker 仍是 R19 历史快照。当前不增加 `account/read`、不读取真实账户，也不在 R20 通过前放宽 Gate 0A。
