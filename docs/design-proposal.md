# Agent Quota 设计方案

<!-- AQ-GENERATED-CURRENT-STATUS-V1:BEGIN -->
```json
{"design_version":"v2.5","gate_status":"ZERO_ISSUES_AUDIT_CONFIRMED","latest_audit_path":"docs/audits/round-20-audit.md","latest_audit_verdict":"PASS_ZERO_ISSUES","latest_issue_ids":[],"revision_round":20,"status_kind":"ZERO_ISSUES"}
```
<!-- AQ-GENERATED-CURRENT-STATUS-V1:END -->
<!-- AQ-NORMATIVE-DECISION-LINK-V1:audits/gui-product-decision-resolution.md -->
> 上述 marker 是第 20 轮零问题终态；第 1–19 轮历史保持不可改写。GUI/Codex/OpenRouter 产品方向仍以 [`gui-product-decision-resolution.md`](audits/gui-product-decision-resolution.md) 和本规范第 20 节为决策源；`ZERO_ISSUES_AUDIT_CONFIRMED` 只允许进入后续 Gate 0A 工作，不表示实现或生产发布已完成。
> 最后更新：2026-07-19
> 实施状态：尚未进入开发
> 仓库名：`agent-quota`

## 1. 一句话定义

Agent Quota Desktop 是一个可独立安装、本地优先、最小披露的多模型额度桌面产品：macOS GUI 是 MVP 主入口，统一 Python core 通过受控 application service 为桌面与辅助 CLI 提供账户配置、额度发现、刷新、状态和清理能力；Hermes、飞书、SchedulerHost 与远期 Web 是可选集成。

以下版本化 JSON 是对应主题的唯一机器权威源，正文仅为投影：[`core-safety-contract-v1`](contracts/core-safety-contract-v1.json)、[`operation-contract-v1`](contracts/operation-contract-v1.json)、[`local-key-purpose-registry-v1`](contracts/local-key-purpose-registry-v1.json)、[`lease-policy-v1`](contracts/lease-policy-v1.json)与[`retention-lint-v1`](contracts/retention-lint-v1.json)。每份 artifact 的 `$schema` 精确绑定 Draft 2020-12 schema；[`contract-registry-v1`](contracts/contract-registry-v1.json)绑定五组 artifact/schema 与两份 fixture 的 raw/domain-separated canonical SHA-256、官方 meta-schema、raw/AST bounds、固定根 no-follow 路径解析、逐数组 `sequence_exact|utf8_key` 策略和引用闭包。五个 artifact ID 与 canonical 摘要只由下方 `AQ-GENERATED-ARTIFACT-PINS-V1` 投影登记，不在 prose 维护第二份列表；registry canonical 摘要为 `9cc20b26c88824a7db5dc0eba709f792be9830eedfe24c56d555756877adb55d`。删除、重排、别名路径、未知字段、hash 或投影不符、悬空顺序策略或语义 fixture 不匹配均离线拒绝。

<!-- AQ-GENERATED-ARTIFACT-PINS-V1:BEGIN -->
```json
{"artifact_pins":[{"artifact_id":"core-safety-contract-v1","canonical_sha256":"3433efb9772bdd8de8e7191724fcadd041df5278c997889b1e0a6d6274bcb3d4"},{"artifact_id":"lease-policy-v1","canonical_sha256":"e35025270a95404bf7d916d42efe48081681e532fa4a8f1e0c8c331c5ff0934b"},{"artifact_id":"local-key-purpose-registry-v1","canonical_sha256":"3f2a2b8cb11f918c9a7ba11d7e8cb527f94beec7e80ee8d90418b868aa843c0d"},{"artifact_id":"operation-contract-v1","canonical_sha256":"7b3af5ce70cc09cbff7c405c8129856526b8a32f389dcc93af892125160ecc10"},{"artifact_id":"retention-lint-v1","canonical_sha256":"bf3804de286cb2bee86e24e2a274dfb9eba98995ac074d87d98fd6995b9ad342"}],"projection_sha256":"48b6a5ec04953dee434e7dda09c4d8edb95e3aabb590b4faf5e5854c6f0db133"}
```
<!-- AQ-GENERATED-ARTIFACT-PINS-V1:END -->

“本地优先”不等于“严格本地”。Provider 查询必然访问对应供应商；任何进入 Hermes 通用工具链的结果还可能进入模型上下文、模型供应商日志和其他插件钩子。MVP 的详细额度路径因此不得依赖 LLM 转述。

## 2. 背景与问题

目前多个模型账户分别来自 Coding Plan、个人订阅、开放平台余额和第三方中转服务。各平台的额度定义、查询入口和重置周期并不统一，常见问题包括：

- 需要反复打开浏览器并登录不同控制台。
- 有的平台展示 5 小时与一周额度，有的平台只有余额、月度额度或 Premium interactions。
- 额度耗尽发生在 Agent 工作过程中，发现得太晚，影响任务连续性。
- Hermes 虽然可以配置多个主模型和回退模型，但缺少统一的额度观察入口。
- API Key、网页登录态和本地 CLI 凭据不适合被复制到另一个云端面板。
- 不同供应商对重置时间使用 UTC、本地时间或无时区字符串，容易导致“距离重置还有多久”的计算错误。

因此，本项目的核心不是简单复制 CC Switch 的界面，而是把“额度采集与归一化”做成可复用底座，再让不同界面消费它。

## 3. 产品目标

### 3.1 MVP 目标

1. 在 Agent Quota Desktop GUI 中查看所有已配置 principal/subject 的最新额度、余额、重置时间、freshness、health 和安全查询状态；GUI 是 MVP 必需表面。
2. 支持供应商各自真实存在的额度类型，不强行把所有平台套成“5 小时 + 一周”。
3. 本地操作者通过 GUI 获得确定性结果；CLI 只作为维护、诊断、无障碍和自动化辅助，并与 GUI 调用同一 application service。可选 Hermes/飞书集成达到阶段 3A 后，也只消费同一确定性投影。
4. 默认只查询额度或显式刷新缓存，不自动切换模型、不修改 Hermes 配置；额度命令不产生额外模型调用消费。
5. 抽离稳定的 Provider Adapter 与 SDK，使项目可以独立开源和扩展。
6. 同一 Provider 支持多个认证身份，每个身份支持多个订阅/工作区/钱包主体，每个主体支持不同额度能力；缺失或不适用的能力必须显式表示。
7. 默认签名桌面包在没有 Hermes、没有仓库源码或 Python 开发环境的干净 macOS 中也能安装、配置、查询、升级和卸载；Python runtime 与 core sidecar 随包固定，不依赖用户 PATH。

### 3.2 非目标

- 第一版不做完整的企业计费、发票或财务对账系统。
- 第一版不通过浏览器自动化抓取后台页面。
- 第一版不把所有密钥上传到托管云服务。
- 第一版不根据余额自动修改 Hermes 的主模型或回退顺序。
- 对非公开接口的支持不等同于供应商官方兼容承诺。
- Desktop MVP 只承诺 macOS；Linux Desktop 在独立 packaging/secret-store/sandbox 合同完成后进入后续阶段，Windows 在拥有 ACL 与 Credential Manager 契约前 fail closed。Python core/CLI 的 Linux 可移植性不等于 Linux Desktop 已发布。

## 4. 可行性范围与虚构示例

本机验证只能证明采集路径在特定时间可行。真实账户别名、余额、使用率、计划和主模型/回退组合属于机密账户数据，不得写入公开仓库、fixture、Issue 或测试断言。真实验证结果只保存在本地、不入库的审计记录中，并受 [安全模型](security-model.md) 的保存期限约束。

以下数值全部为虚构示例，只用于验证数据模型的表达能力：

| 虚构主体 | 示例数据 | 归一化方式 |
| --- | --- | --- |
| Provider A / Account 01 | 5 小时已使用 42%，一周已使用 18% | 两个滚动时间窗 |
| Provider B / Account 02 | 本月已使用 120 / 500 次 | 固定周期计数窗口 |
| Provider C / Account 03 | CNY 88.88 | 货币余额，不伪装成百分比额度 |
| Provider D / Account 04 | 当前无可用固定配额 | 稳定状态码，不保存上游原文 |

## 5. 核心设计原则

### 5.1 额度类型保持真实

统一的是数据结构和访问方式，不是额度含义。一个 Provider 可以返回任意数量的时间窗，也可以只返回余额、调用次数或文字状态。

### 5.2 本地优先

阶段 1 交付本地桌面产品：Tauri 2/Rust trusted host 启动随包固定的 Python core sidecar，React/TypeScript renderer 是主界面；不依赖 Hermes，不开放 loopback 或公网监听。凭据优先复用官方 CLI/SDK 登录态、macOS Keychain 引用或显式环境变量，不进入 renderer，也不通过消息卡片传输。SchedulerHost 和远期 Web 均为可选宿主。

额度数据只在“Provider → Agent Quota 内核 → 经授权的确定性渲染器”路径中保持本地处理。进入飞书即构成向飞书披露；进入 Hermes 通用工具结果即可能向当前模型供应商、会话日志和观察插件披露。每种披露都必须有单独规则。

### 5.3 查询优先，副作用显式

Provider Adapter 的第一版业务能力只允许读取上游额度。`quota_status` 是缓存读取；`quota_refresh` 会读取凭据、访问网络并修改缓存、失败计数和审计状态，必须按有副作用操作授权、限流和幂等，不能描述为“只读工具”。自动切换模型属于后续独立能力，需要单独授权、审计和回滚设计。

### 5.4 显式标记数据可信度

每条快照记录其来源：公开 API、本地官方 CLI、非公开接口或估算值。界面必须显示过期状态和失败原因，不能用旧数据冒充实时结果。

### 5.5 单一数据底座，多种消费入口

Desktop host、辅助 CLI、Hermes、飞书和远期 Web 不分别实现供应商查询逻辑，它们只调用一个版本化 application service/use-case surface。依赖方向固定为 `renderer → Tauri command allowlist → trusted host → application service → agent_quota.core`，以及 `其他宿主 → application service → agent_quota.core`；核心包不得导入 Tauri、React、Hermes、飞书、FastAPI 或任何渠道类型。

### 5.6 时间统一为 UTC

Provider Adapter 在边界处把可识别的时间统一转换为带时区的 UTC 时间。存储层只保存 UTC，CLI、飞书和 Web 展示层再转换为用户时区；无法确认时区的原始时间必须标记为 `timezone_unknown`，不能静默按本地时间解释。

### 5.7 额度数据默认机密

余额、额度、使用率、计划、账户别名、认证状态和精确重置时间均为机密账户数据。它们不因“不含 Token”而成为非敏感元数据。授权、存储、日志、飞书群聊和 LLM 投影都按机密数据处理。

## 6. 总体架构

独立内核是产品，不是 Hermes 插件的内部模块。默认安装与依赖方向如下：

```text
React/TypeScript renderer（不可信展示层）
                  │ 仅显式 Tauri command allowlist
                  ▼
Tauri 2 / Rust trusted desktop host（主入口、单实例、sidecar supervisor）
                  │ 匿名管道/stdio，有界关联 IPC；不监听端口
                  ▼
Python application service + agent_quota.core（唯一业务/授权/缓存权威）
                  │
                  ▼
Provider Adapter Packages → Provider API / 官方 CLI / 凭据引用

辅助入口：CLI / SchedulerHost / Hermes-飞书 / 远期 Web
                  │
                  └────────────→ 同一 application service
```

核心服务只接收渠道无关的 `AccessContext(actor, account_scope, operation)`；`account_scope` 使用 `(principal_id, subject_id)` 和 `(principal_id, subject_id, capability_id)` 绑定引用，避免任何独立列表形成越权笛卡尔积。Desktop host 和辅助 CLI 都以 OS 用户构造 `LocalActor`；renderer 不能构造或覆盖 actor/scope。Hermes/飞书包把网关事件转换为 `FeishuActor`。飞书 CallerContext 桥接只阻塞该可选集成，不阻塞 Desktop。

远期若确有远程浏览器消费需求，另立可选 Web surface；它不是 Desktop renderer，也不得复用 Desktop IPC 作为远程认证：

```text
独立 Web host ─> application service ─> core
```

Web 必须单独完成认证、Host/Origin、CORS、CSRF 和部署门禁；`127.0.0.1` 从来不是认证。Desktop MVP 不包含 FastAPI、HTTP server 或浏览器会话。

### 6.1 Desktop host、renderer 与 sidecar 冻结合同

机器权威源是 [`core-safety-contract-v1`](contracts/core-safety-contract-v1.json) 的 `desktop_product_contract`。实现必须同时满足：

1. Tauri host 是唯一可启动 sidecar 的组件。它以绝对 no-follow 路径打开随包 Python runtime/sidecar，核对 bundle code signature、Team ID/designated requirement、普通文件 owner/mode/size 与 release manifest raw SHA-256，再从已验证文件描述符启动；PATH、shell、用户可写替代文件、symlink 与下载后直接执行均拒绝。
2. host 使用专属匿名 stdin/stdout 管道与 sidecar 通信，并通过另一条仅子进程继承的匿名管道发送每次启动重新生成的 256-bit session secret；不创建 Unix socket、TCP socket、loopback 端口或可重连命名端点。stdio 只是传输，child process binding + session secret + envelope 校验共同建立本次会话。
3. wire 为 `u32be length || UTF-8 JSON`；frame 最大 1 MiB。请求恰含 `protocol_version, request_id, command, payload, remaining_budget_ns, session_proof`，响应恰含同一 `protocol_version, request_id` 与 `result|error` 判别联合。host 发送 `1..9_000_000_000` 的剩余预算而不跨进程传递绝对 monotonic timestamp；sidecar 只在完整合法 frame 收妥后读取自己的 monotonic clock，用 checked-add 重建本地 deadline，并同时受 host 原始 9 秒 hard cap 约束，因此排队与传输时间会消耗 host 预算。`now >= local_deadline`、零/负/超上限、checked-add overflow 或旧 session 预算复用都在 dispatch 前拒绝，Provider I/O 与写入均为 0。dispatch 后 host 超时不能声称零写入：状态固定为 outcome unknown、禁止自动重放，并执行 0.5 秒 TERM→KILL→reap，要求 orphan 为 0，再由既有幂等/事务恢复决定写入终态。`request_id` 是每个新 session 从 1 开始的 unsigned 64-bit counter，host 每次请求严格加一，sidecar 只接受期望的下一值，响应逐字节回显；溢出前终止会话并新建 session，不能 wrap 或随机跳号。未知/重复/乱序关联、额外字段、非规范 UTF-8、超限或 sidecar 主动 notification 均终止会话。敏感字段永不进入 IPC DTO。生产 sidecar 的 stderr 在 spawn 时直接连接 OS null sink，不创建 stderr pipe；原始 stderr 永不进入 host 日志、renderer 或 IPC，结构化错误只能通过受约束的 IPC error 联合返回。
4. renderer 只加载 bundle 内静态资产，Tauri capability/command allowlist 恰为 `bootstrap_state, accounts_read, quota_overview, refresh_scope, config_validate_apply, credential_dialog_open, destructive_confirmation_open, reauthenticate, export_redacted, scheduler_state`。机器合同为这 10 个 command 逐项绑定 request/response schema reference、host 重建字段、秘密/破坏性分类和 commit policy；同一源中的 29 个 DTO schema 全部封闭 `additional_properties=false`，nested reference 也必须解析到这张表中的有类型、有界、脱敏 schema。`config_validate_apply` 的 `config_change_set` 只能引用封闭的 non-destructive change-set/change schema，并只能直接提交 core 分类为 non-destructive 的变更；遇到 destructive diff 只能转入 host-owned trusted confirmation，不能由该 command 静默提交。`credential_dialog_open` 无 secret payload；`destructive_confirmation_open` 只能提交封闭 operation intent/opaque selection handle，不能提交或接收 plan、digest、nonce、user-presence token。host 为每个 command 重建 `LocalActor`、RequestedOperation 和 scope，renderer 参数不能直接成为 SQL、路径、URL、header、CredentialRef 或 Provider selector；未知、额外或 nested 注入字段在 application service 前拒绝。
5. renderer 无 shell、文件系统、网络、sidecar、凭据或秘密输入 capability；CSP 固定为 `default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'none'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'`。API Key 只能进入 host-owned macOS native secure dialog 或由该 dialog 选择既有 Keychain item；keystroke、paste、secret value/length、SecretBuffer 都不得进入 WebView DOM/event、React state/prop、Tauri command payload 或 IPC response。credential dialog 仅在应用 foreground 且主 key window 激活时打开，每 installation 同时只能有一个 trusted dialog，host 执行固定 cooldown 并对 renderer spam fail closed。只允许 app origin 导航，禁止任意外链、新窗口、远程脚本、WebSocket 与 custom URL fetch；需要打开官方帮助时，host 只接受本地登记的固定 HTTPS URL ID，并交给 OS 浏览器。
6. purge、disable、delete、cascade，以及会移除或替换 endpoint/auth/binding/capability/manifest 的 destructive config diff，都由 core 生成同一份脱敏 plan；Rust host-owned native confirmation surface 才能展示它并捕获 user presence。plan digest、confirmation nonce 与 user-presence token 只在 host↔core 通道，一律不返回 renderer；renderer 只请求打开 trusted surface，并只收到 `cancelled|committed|status`。surface 同样要求 foreground/key window、单 active dialog 与 host cooldown；取消、失焦、超时、plan/generation 改变或重复请求都零副作用 fail closed。
7. 单实例锁按 OS 用户 + installation ID 绑定。第二实例只向已验证主实例发送无 payload 的 activate 信号；不能携带 command/scope/URL。host 崩溃时 sidecar 因 parent-death/pipe EOF 退出；正常退出先停止接单、等待有界在途事务、TERM，0.5 秒后 KILL 并 reap。一次自动重启前重新验证二进制并生成新 session；连续两次崩溃进入安全故障页，不无限重启。
8. 升级只接受已验证签名/notarized app bundle 与 release attestation；在新 bundle staging 自检、sidecar pin、配置 migration dry-run 成功后原子切换。失败保留旧完整 bundle/数据 generation；schema migration 已提交时只按既有 migration journal roll-forward，绝不混跑新 host/旧 sidecar。卸载默认保留 core 数据；显式 purge 走同一 plan/confirm 契约和 trusted confirmation surface。
9. renderer 的“后台刷新”状态只投影 `SchedulerHost installed && heartbeat healthy`。否则固定显示“仅按需刷新”，不能使用“实时”“持续监控”或预计后台告警文案。renderer 被攻陷仍可能欺骗当前 UI，因此 host/core 必须拒绝越权；本合同不承诺抵御已控制 OS 用户、已替换受信任 host 或平台 WebView 漏洞。

## 7. 标准数据模型

Provider、登录账户和订阅不是同一概念。核心使用以下稳定层级：

```text
ProviderAdapter
  └─ AccountPrincipal      # 一个认证身份或官方 CLI 会话
       └─ QuotaSubject     # 订阅、组织、工作区、钱包、项目或计费主体
            └─ QuotaCapability  # 可查询的窗口、余额、计数或状态
                 └─ CapabilitySnapshot
```

- `AccountPrincipal` 绑定认证变体、地区、Credential Lease 与 endpoint profile，但不必等于邮箱。
- `QuotaSubject` 是授权、展示和删除的最小业务主体；同一登录身份可以拥有多个订阅、工作区或钱包。
- `QuotaCapability` 具有稳定 ID、判别类型、单位和来源。不存在、不适用、未授权、版本不兼容必须是不同状态。
- `CapabilitySnapshot` 只记录一个主体的一项能力，避免用单个 `plan` 或单个余额承载多种含义。

```python
PrincipalId = Annotated[str, StringConstraints(pattern=r"^aqp_[0-9a-f]{32}$")]
SubjectId = Annotated[str, StringConstraints(pattern=r"^aqs_[0-9a-f]{32}$")]
ManifestCapabilityId = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9-]{0,63}$")]
SemanticContractId = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9._-]{0,127}$")]

SubjectKind = Literal["subscription", "workspace", "organization", "wallet", "project"]
CapabilityKind = Literal["window", "balance", "counter", "status"]
DataFreshness = Literal["fresh", "stale", "expired"]
Health = Literal[
    "ok", "auth_error", "rate_limited", "network_error", "schema_changed",
    "semantic_suspect", "provider_error", "unsupported", "incompatible",
]
SourceType = Literal["public_api", "official_cli", "undocumented", "estimated"]
ResetTimeStatus = Literal["known", "timezone_unknown", "not_provided"]
ProbeCompatibility = Literal[
    "compatible", "incompatible", "auth_required", "unavailable", "unverified_version"
]
LocalStatusCode = Literal[
    "unlimited", "unknown", "available", "insufficient_balance",
    "rate_limit_reached", "credits_depleted", "usage_limit_reached",
    "not_applicable", "unsupported", "not_entitled",
    "reauth_required", "unverified_version", "unsupported_version",
    "temporarily_unavailable",
]

class AccountPrincipal:
    id: PrincipalId
    adapter_id: str
    provider_variant: str
    auth_variant: str
    region: str | None
    credential_binding_ids: tuple[str, ...]  # 可以为空，例如 official-cli
    endpoint_profile: str                    # 只能引用 AdapterManifest 允许值

class QuotaSubject:
    id: SubjectId
    principal_id: PrincipalId
    kind: SubjectKind
    label: Annotated[str, StringConstraints(min_length=1, max_length=80)]
    plan_code: str | None     # 必须命中 manifest 的有限枚举

class QuotaCapability:
    id: ManifestCapabilityId
    subject_id: SubjectId
    kind: CapabilityKind
    unit: str | None          # 必须命中对应 CapabilitySpec 的有限 canonical_unit
    label_key: str            # manifest 中的本地文案枚举，不接收上游自由文本

class WindowValue:
    kind: Literal["window"]
    duration_minutes: DurationMinutes | None
    used_percent: float | None       # 0..100
    used_value: float | None
    limit_value: float | None
    resets_at: datetime | None       # 仅在 reset_time_status=known 时保存带时区 UTC
    reset_time_status: ResetTimeStatus

class BalanceEntry:
    currency: str                    # core 支持且 manifest 允许的有限币种枚举
    total: Decimal
    granted: Decimal | None
    topped_up: Decimal | None

class BalanceValue:
    kind: Literal["balance"]
    entries: tuple[BalanceEntry, ...]  # 支持同一钱包返回 CNY、USD 等多币种

class CounterValue:
    kind: Literal["counter"]
    used: Decimal | None
    limit: Decimal | None
    unit: str

class StatusValue:
    kind: Literal["status"]
    code: LocalStatusCode

class NumericParam:
    kind: Literal["number"]
    value: Decimal                   # 有限数，不允许 NaN/Infinity

class CurrencyParam:
    kind: Literal["currency"]
    code: str                        # core 支持的币种枚举

class EnumParam:
    kind: Literal["enum"]
    code: str                        # 必须命中 manifest 中的有限允许集

class UtcTimeParam:
    kind: Literal["utc_time"]
    value: datetime                  # 带时区 UTC

DisplayParamValue = NumericParam | CurrencyParam | EnumParam | UtcTimeParam

class CapabilitySnapshot:
    adapter_id: str
    principal_id: PrincipalId
    subject_id: SubjectId
    capability_id: ManifestCapabilityId
    data_freshness: DataFreshness
    health: Health
    source_type: SourceType
    fetched_at: datetime      # 带时区 UTC
    evaluated_at: datetime    # core 判定 freshness 的带时区 UTC 时间
    expires_at: datetime | None
    value: WindowValue | BalanceValue | CounterValue | StatusValue | None
    status_code: LocalStatusCode | None
    display_params: tuple[tuple[str, DisplayParamValue], ...]  # key UTF-8 bytes 排序且唯一；core-owned 深拷贝后构造
    schema_fingerprint: str | None
    semantic_contract_id: SemanticContractId
    adapter_version: str

RequestedOperation = Literal[
    "status", "configure", "doctor", "discover", "refresh", "migrate", "delete", "purge",
    "alert_ack", "consent_grant", "consent_revoke",
]
# 这两个 union 只由文末 AQ-GENERATED-OPERATION-PROJECTION-V1 生成。
ExecutionStage = GeneratedOperationStage
OperationErrorCode = GeneratedOperationErrorCode

OperationContractFailureCode = Literal[
    "invalid_operation_envelope", "illegal_execution_plan", "illegal_error_envelope"
]

class OperationError:
    outcome: Literal["error"]
    requested_operation: RequestedOperation
    failed_stage: ExecutionStage
    code: OperationErrorCode
    retryable: bool
    occurred_at: datetime                 # 带时区 UTC
    safe_params: tuple[tuple[str, DisplayParamValue], ...]  # key 排序且唯一；按 code schema 校验，无自由文本

T = TypeVar("T")

class OperationSuccess(Generic[T]):
    outcome: Literal["success"]
    requested_operation: RequestedOperation
    value: T

class OperationContractFailure:
    outcome: Literal["contract_failure"]
    recognized_operation: RequestedOperation | None  # 非法/未知 operation 为 None
    failed_stage: Literal["contract_validate"]
    code: OperationContractFailureCode
    retryable: Literal[False]
    occurred_at: datetime
    raw_operation_digest: LowerHexSha256       # 对最多 256 bytes 有界原始字段做域分离摘要
    safe_params: tuple[tuple[Literal["envelope_code"], EnumParam], ...]

OperationResult: TypeAlias = OperationSuccess[T] | OperationError | OperationContractFailure
```

`value.kind` 是判别字段，且必须与 `QuotaCapability.kind` 完全相同；`unit` 必须等于 manifest 中该 capability 的 `canonical_unit`（`balance/status` 必须为 `None`，币种位于 entry 中）。所有 Decimal/float 必须有限，禁止 NaN/Infinity。`WindowValue` 使用以下完整联合不变量：`duration_minutes` 非空时必须大于 0；`used_percent` 非空时位于 `0..100`；`used_value/limit_value` 必须同时为空或同时存在，存在时均非负且 `used_value <= limit_value`；正常定量窗口至少提供 `used_percent` 或完整的绝对值对。若两种表示同时存在且 `limit_value > 0`，必须满足 `abs(used_percent - 100*used_value/limit_value) <= CapabilitySpec.percentage_consistency_tolerance_points`，该容差为 manifest 必填的有限 Decimal 且范围 `0..1`；`limit_value=0` 时只能是 `used_value=0` 且 `used_percent=None`，避免定义 `0/0`。余额 `entries` 至少一项且同一币种只能出现一次，`total/granted/topped_up` 均为有限非负 Decimal；counter 的 used/limit 非负且同时存在时 `used <= limit`。`remaining_percent` 只由 core 计算。全部时间必须是 UTC，且 `fetched_at <= evaluated_at`；`expires_at` 存在时必须 `fetched_at <= expires_at`。`reset_time_status=known` 当且仅当 `resets_at` 为非空 UTC；其他状态的 `resets_at` 必须为 `None`。

以下状态矩阵是规范性的；不在表内的组合一律返回操作级 `OperationError(code="adapter_contract_violation")` 并整批拒绝，不能静默修正或伪造一条快照：

| 情况 | `health` | `status_code` | `value` | `data_freshness` |
| --- | --- | --- | --- | --- |
| 正常数值/状态 | `ok` | `None` | 与 capability kind 匹配的非空值 | `fresh` 或带 LKG 的 `stale` |
| 无上限/未知但上游成功 | `ok` | `unlimited/unknown` | 定量 capability 为 `None`；status capability 为匹配的 `StatusValue` | `fresh` |
| 不适用/未提供能力 | `unsupported` | `not_applicable/unsupported/not_entitled` | `None` | `fresh` |
| 需重新认证 | `auth_error` | `reauth_required` | LKG 或 `None` | 有 LKG 为 `stale`，否则 `expired` |
| 协议版本未验证/不兼容 | `incompatible` | `unverified_version/unsupported_version` 或 `None` | `None` | `expired` |
| 网络、限流、上游、结构或语义失败 | 对应非 `ok` health | 本地枚举或 `None` | 仅 `stale` 时可带类型匹配的 LKG；`expired` 必须为 `None` | `stale/expired` |

`fresh` 表示 core offline manifest 求值产生、policy 明示允许且 `expires_at is None` 的 static `not_applicable|unsupported`，或 `evaluated_at < expires_at`；任何 Provider observation 都必须使用后者的有限 TTL。`stale` 必须有当前 generation 非空 LKG 且已到期；`expired` 不向投影返回旧值。`unverified_version` 只属于 probe/incompatible；`reauth_required` 只属于 auth；`not_entitled` 只属于已授权请求的上游缺失。未知枚举、空必填值、kind/value 错配或表外组合全部拒绝。

`OperationError` 与 `CapabilitySnapshot` 是互斥表面。任何本地 actor/scope 拒绝都只能返回 `OperationError(code="not_authorized", failed_stage="authorize")`，并且在缓存、幂等、凭据、Provider、ledger 和失败计数之前结束；快照枚举中不存在 `not_authorized`。已授权请求中由上游表达的 capability entitlement 缺失使用 `health=unsupported + status_code=not_entitled`，它不是本地授权结论，也不得携带上游原文。配置、发现、凭据、Adapter 边界、本地子进程、迁移和删除失败同样返回封闭操作错误，不创建伪快照；Provider 业务响应所表达的 network/rate-limit/5xx/schema/semantic 状态才由 core 按上表生成 capability 快照。错误渲染只使用本地 `code + safe_params` 模板。调用者若要看旧值，必须另行执行已授权的 `status` 缓存读取；refresh 错误结果不得把 LKG 塞入 `OperationError`。

`RequestedOperation` 是 actor 请求且是唯一授权输入；`ExecutionStage` 只是 core 内部执行位置，不能单独获得权限或替换原请求。唯一机器数据源是 [`operation-contract-v1`](contracts/operation-contract-v1.json)；实现从其中生成 validator、context builder 和文末 `AQ-GENERATED-OPERATION-PROJECTION-V1`。exact trace 不在正文手写第二份；任何 stage/error/path 增删或换序都会使 projection 反向摘要与 registry 门禁失败。

predicate 只能取 artifact 中登记的 exact ID；不得增加阶段。`endpoint_validate` 先完成 endpoint/policy/identity-source/budget-group 闭包、URL/argv 与发送对象投影；refresh 再完成 `idempotency_prepare`，命中 completed/failed_safe/outcome_unknown 的旧键立即终结，二者的 Credential Source 调用计数都必须为 0。`official_cli_zero_binding` 没有 `credential_resolve`，只能由 core 生成 `ZeroBindingProof`。任何标为 `provider_io` 的 step 必须消费同一 path 中位于其前且 request kind 相同的一张未消费 reservation；没有 reservation 不可写出首个 outbound byte。嵌套调用始终保留原 `requested_operation`；Credential Source/Adapter 不接收 actor 权限枚举。

输入 envelope、mode 或整条计划在 `contract_validate` 不命中 artifact 时，唯一公开终局是 `OperationContractFailure(recognized_operation=None|合法枚举, raw_operation_digest=...)`，且 cache/credential/process/Provider/ledger/全部写入计数均为 0。摘要只覆盖最多 256 bytes 的有界原始 operation bytes，不回显原文；超界先以固定 `envelope_code` 拒绝。已进入受信任 core 后若内部代码试图构造表外 stage 转移或表外 `OperationError`，必须抛出不序列化的固定 fatal `CoreInvariantFatal("AQ_OPERATION_MATRIX_V1")` 并终止请求；禁止递归转换。

### 7.1 操作、幂等与状态变更结果代数

Python 3.11 的可执行声明必须显式 `from typing import Generic, TypeAlias, TypeVar`，并使用上文的 `OperationResult: TypeAlias = OperationSuccess[T] | OperationError | OperationContractFailure`；不得使用 Python 3.12 的 PEP 695 语法或给下标表达式赋值的旧写法。所有模型 `extra=forbid`。refresh、alert 与 consent 成功值也是封闭联合：

```python
IdempotencyState = Literal[
    "prepared", "running", "completed", "failed_safe", "outcome_unknown"
]
RateReservationState = Literal["reserved", "committed", "outcome_unknown"]
ProviderFailureCategory = Literal[
    "auth_error", "network_error", "provider_error", "rate_limited",
    "schema_changed", "semantic_suspect"
]

class RefreshRequestKey:
    subject_id: SubjectId
    capability_id: ManifestCapabilityId

class RefreshFreshResult:
    request_digest: LowerHexSha256
    request_keys: tuple[RefreshRequestKey, ...]
    disposition: Literal["provider_fresh", "singleflight_fresh"]
    snapshots: tuple[CapabilitySnapshot, ...]
    failure_category: None
    retry_after_seconds: None

class RefreshLkgResult:
    request_digest: LowerHexSha256
    request_keys: tuple[RefreshRequestKey, ...]
    disposition: Literal["lkg_stale"]
    snapshots: tuple[CapabilitySnapshot, ...]
    failure_category: None
    retry_after_seconds: None

class RefreshProviderFailureResult:
    request_digest: LowerHexSha256
    request_keys: tuple[RefreshRequestKey, ...]
    disposition: Literal["provider_failure"]
    snapshots: tuple[CapabilitySnapshot, ...]
    failure_category: ProviderFailureCategory
    retry_after_seconds: RetryAfterSeconds | None

class RefreshPreAttemptEmptyResult:
    request_digest: LowerHexSha256
    request_keys: tuple[RefreshRequestKey, ...]
    disposition: Literal["deferred", "capacity", "timeout", "outcome_unknown"]
    snapshots: tuple[()]
    failure_code: Literal[
        "refresh_deferred", "capacity_exhausted", "local_process_timeout", "outcome_unknown"
    ]
    retry_after_seconds: RetryAfterSeconds | None

RefreshRequestResult: TypeAlias = (
    RefreshFreshResult | RefreshLkgResult | RefreshProviderFailureResult |
    RefreshPreAttemptEmptyResult
)

class RefreshBatchResult:
    kind: Literal["refresh_batch_v1"]
    results: tuple[RefreshRequestResult, ...]  # 1..32；request_digest bytes 严格升序

class AlertAcknowledged:
    kind: Literal["alert_acknowledged"]
    episode_id: SequenceInt
    notification_sequence: SequenceInt

class ConsentChanged:
    kind: Literal["consent_granted", "consent_revoked"]
    consent_generation: SequenceInt

RefreshOperationValue: TypeAlias = RefreshBatchResult
StateChangeValue: TypeAlias = AlertAcknowledged | ConsentChanged
```

完整 refresh 请求先按 `(adapter_id,principal_id,cache_identity,query_contract_generation,endpoint_id,request_kind,normalized selectors)` 计算 `request_digest=SHA256(b"agent-quota:refresh-request:v1\x00"+JCS(key))`；digest 不包含 secret 且请求间唯一。每个 digest 的 `request_keys` 按 `(subject_id,capability_id)` UTF-8 bytes 排序、非空且互不重叠，输入的每个完整 request digest 必须恰有一个 `RefreshRequestResult`，禁止漏项/重复/额外项。判别联合不变量为：fresh 与 LKG 分支的 snapshots 恰覆盖 `request_keys`；Provider failure 分支也必须恰覆盖全部 key，并由 core 对每个 key 生成同 generation LKG `stale`，没有 LKG 时生成 `expired + value=None`；只有发出首个 Provider byte 前的 deferred/capacity/timeout 和已提交 attempt 的 `outcome_unknown` 分支允许 snapshots 为空。`RefreshProviderFailureResult.retry_after_seconds` 仅在 `failure_category=rate_limited` 时可为经 `aq-bounds-v1` 截断的非空值，其他类别必须为空；empty 分支只有 `deferred` 可携带同样有界值。`lkg_stale` 和 failure snapshots 必须是 core 本次合成，不是 Adapter 返回值。

`FetchFailureCategory → result/snapshot` 是封闭映射：`auth_error→auth_error/reauth_required`、`network_error→network_error/None`、`provider_error→provider_error/None`、`rate_limited→rate_limited/rate_limit_reached`、`schema_changed→schema_changed/None`、`semantic_suspect→semantic_suspect/None`；每项均有 LKG 时 `stale + 类型匹配旧 value`，无 LKG 时 `expired + value=None`。未知类别、status/health 不匹配、缺 key 或额外 snapshot 整批合同失败。幂等记录保存这一判别联合的完整 canonical bytes；同键重放不得重新读取 LKG、重新计算 Retry-After 或改变有/无 snapshot 的分支。

在授权、配置、幂等 prepare 或整个本地存储边界尚未形成合法 request tuple 前失败，返回顶层 `OperationError`。一旦形成至少一个合法 request，所有 request 都进入 `RefreshBatchResult`；即使全部 timeout/capacity/failure 也返回 `OperationSuccess[RefreshBatchResult]`，使调用者不丢完整 key 集。仅 artifact 明示的 request 外 fatal（例如 ledger 数据库整体不可用）仍为顶层 OperationError。幂等记录原子保存完整 canonical `OperationSuccess` 或顶层 `OperationError` envelope，不只保存摘要；并发重复逐字节返回同一 envelope。结果按 request digest 排序，因此协程完成顺序、singleflight leader 或进程调度不改变序列化。`AlertAcknowledged` 只允许原 episode 为 `open`，事务后为 `acknowledged`；重复相同 actor/episode 返回既有 success，不增加 notification sequence。`consent_grant` 新建或替换 scope 并递增 generation，`consent_revoke` 即使重复也返回当前 generation 且不复活旧 context；两者只引用 retention ID。

错误合同由 [`operation-contract-v1`](contracts/operation-contract-v1.json) 的 exact `error_rows` 唯一确定；每行主键是 `(code,operation,stage)`，不含自然语言集合。下表只是便于阅读的分组索引，不宣称穷举；文末 `AQ-GENERATED-OPERATION-PROJECTION-V1` 才是包含完整 `error_rows`、`safe_param_schemas`、path/stage/error union 的无损确定性投影，并由 marker 字节 exact verification。任一 row 增删改在重新生成 marker 前必须失败。实现不得解析 Markdown。`retryable` 不能由 Adapter/渠道选择；`safe_params` 只接受 artifact 登记 schema。入口表外计划/envelope 只能返回上文的 `OperationContractFailure`；受信任 core 表外 `OperationError` 只能进入固定 fatal。“零写入”包含配置、缓存、LKG、失败计数、alert、consent 和 ledger。

| code | 合法 actor operation / stage | retryable | 唯一 safe params | 副作用 |
| --- | --- | --- | --- | --- |
| `not_authorized` | `status/authorize; configure/authorize; doctor/authorize; discover/authorize; refresh/authorize; migrate/authorize; delete/authorize; purge/authorize; alert_ack/authorize; consent_grant/authorize; consent_revoke/authorize` | false | `()` | 全部零读取/零写入 |
| `invalid_config` | `configure|doctor|discover|refresh|migrate|delete` / `config_validate` | false | `field_code:EnumParam` | 零运行写入 |
| `config_unavailable` | `status/config_gate; configure/config_gate; doctor/config_gate; discover/config_gate; refresh/config_gate; migrate/config_gate; delete/config_gate; purge/config_gate; alert_ack/config_gate; consent_grant/config_gate; consent_revoke/config_gate` | true | `()` | 关闭服务 gate |
| `storage_unavailable` | `status/cache_read; configure/migration_commit; doctor/config_gate; discover/config_gate; refresh/idempotency_prepare; refresh/rate_ledger_reserve; refresh/cache_commit; refresh/idempotency_finalize; migrate/migration_commit; delete/migration_commit; purge/purge_commit; alert_ack/alert_ack_commit; consent_grant/consent_commit; consent_revoke/consent_commit` | true | `store_code:EnumParam` | 当前事务回滚 |
| `rate_ledger_unavailable` | `refresh` / `rate_ledger_reserve` | true | `()` | Provider 调用为 0 |
| `projection_failed` | `status|refresh|alert_ack` / `projection` | false | `projection_code:EnumParam` | 不回滚已提交 refresh；返回安全错误 |
| `consent_required` | `status` / `consent_validate` | false | `()` | 缓存读取为 0 |
| `consent_expired` | `status|consent_revoke` / `consent_validate` | false | `()` | 只允许 terminalize/tombstone |
| `credential_backend_unavailable` | `doctor|discover|refresh` / `credential_resolve` | true | `()` | Provider/失败计数为 0 |
| `adapter_contract_violation` | `doctor/probe; discover/discovery; refresh/provider_fetch; refresh/probe` | false | `violation_code:EnumParam` | 整批零写入 |
| `invalid_discovery_result` | `discover` / `discovery` | false | `violation_code:EnumParam` | 配置/运行表零写入 |
| `local_protocol_violation` | `doctor/probe; discover/discovery; refresh/provider_fetch; refresh/probe` | false | `protocol_code:EnumParam` | 只更新对应本地失败类别 |
| `local_process_timeout` | `doctor/probe; discover/discovery; refresh/provider_fetch; refresh/probe` | true | `()` | 只更新对应本地失败类别 |
| `local_keyring_unavailable` | `status/config_gate; configure/config_gate; doctor/config_gate; discover/config_gate; refresh/config_gate; migrate/config_gate; delete/config_gate; purge/config_gate; alert_ack/config_gate; consent_grant/config_gate; consent_revoke/config_gate` | false | `envelope_code:EnumParam` | 关闭服务 gate，不重建 key |
| `unsupported_platform` | `configure/config_validate; doctor/config_validate; doctor/probe; discover/config_validate; refresh/config_validate` | false | `()` | 零运行写入 |
| `adapter_not_distributable` | `configure/config_validate; doctor/config_validate; doctor/probe; discover/config_validate; refresh/config_validate` | false | `()` | Provider 调用为 0 |
| `migration_conflict` | `configure/migration_plan; migrate/migration_plan; configure/migration_commit; migrate/migration_commit` | false | `conflict_code:EnumParam` | 未确认时零写入；提交事务回滚 |
| `referenced_object_conflict` | `configure/migration_plan; migrate/migration_plan; delete/deletion_plan` | false | `object_kind:EnumParam` | 零写入 |

`alert_ack`、`consent_grant`、`consent_revoke` 在授权后若存储失败只使用 artifact 展开的 `storage_unavailable` exact 行；不存在运行时文字集合解释。正反例生成器必须对 `RequestedOperation × ExecutionStage × OperationErrorCode × retryable × safe_params` 做全笛卡尔验证，并断言表外组合在任何 cache/credential/Provider/ledger 访问前失败。

实现时只保留经过白名单投影的 Provider 元数据，默认不持久化完整原始响应。上游 `message`、错误正文、响应头和未知字符串不得进入 `CapabilitySnapshot`。`display_params` 不接受普通 `str`；core 根据本地 `status_code` 对参数名、判别类型和有限枚举再次校验，未知参数、未知枚举和任意短文本一律拒绝。展示层只使用内置模板和本地枚举文案，避免把 Adapter 自律当成唯一的提示注入/敏感回显防线。

`schema_fingerprint` 不得简单遍历所有对象键。JSON 对象键也可能是邮箱、用户 ID 或其他动态值；每个 Provider 必须声明静态路径白名单，并把映射型对象的动态键归一化为 `<map-key>` 后再对“规范化路径 + 基础类型”计算哈希。未知路径默认丢弃，不进入日志或指纹差异。

结构指纹不能证明字段含义和单位没有变化。每个 capability 还必须在 AdapterManifest 中冻结 `semantic_contract_id`、规范单位、上游到规范值的缩放规则、硬值域和 Provider 专属 canary/跨快照跳变规则。示例包括“百分比按百分数点而非 0..1 比例解释”、滚动窗口在足够观测后长期落在异常小区间，以及余额在没有充值/扣费事件依据时出现数量级跳变。命中语义规则时不得写成 `fresh + ok` 或覆盖 last-known-good，而应返回 `semantic_suspect`；有旧值时为 `stale`，无旧值时为 `expired`。启发式只能发现可疑变化，不能证明数据正确，因此规则、最少样本数、容差与误报恢复流程都必须按 Provider 版本化并用 fixture 验证。

面向不同渠道生成独立投影，禁止把完整 `CapabilitySnapshot` 集合直接交给集成层：

```python
class QuotaProjection:
    audience: Literal["local_detail", "feishu_private"]
    aggregate_health: str
    subject_rows: tuple[SafeQuotaSubjectRow, ...]
    generated_at: datetime
    presentation_timezone_id: str
    timezone_fallback: bool

class LlmMinimalProjection:
    schema_version: Literal[1]
    aggregate_health: Literal["normal", "degraded", "unavailable", "unknown"]
    capacity_band: Literal["comfortable", "watch", "scarce", "unknown"]
    freshness_band: Literal["recent", "aged", "unknown"]

class PresentationContext:
    timezone_id: str                  # 经 IANA tzdb 验证后的 canonical zone，fallback 时固定 UTC
    source: Literal["actor_profile", "local_config", "utc_fallback"]
    fallback_reason: Literal["missing", "invalid"] | None
```

- `local_detail`：本机授权操作者可查看 scope 内 principal/subject/capability 的详细数据。
- `feishu_private`：授权操作者私聊可查看 scope 内主体与能力的详细数据。
- `feishu_group`：不是 `QuotaProjection` audience。MVP 群聊路由器不读取额度存储，只返回固定文案“请私聊机器人查看额度状态”。不得包含主体数、正常/异常数、总体健康、Provider 分组、告警、新鲜度或前后变化；因此群聊重复调用也不能形成额度时间序列。
- `llm_minimal`：不是 `QuotaProjection.audience`，只能序列化为上面的封闭 `LlmMinimalProjection`。`capacity_band` 取 scope 内已配置策略所得最高数值 severity：`none→comfortable`、`warning→watch`、`high|critical→scarce`；没有可比数值策略时为 `unknown`。`freshness_band` 仅为 `recent/aged/unknown`，不得携带时间。该 schema **不允许正常/异常数量、主体数、ID、别名、Provider 对应关系、能力列表、精确值、余额、计划、认证状态或时间戳**，附加字段必须被序列化器拒绝。它默认禁用；同意生命周期只引用 `RET-CONSENT-ACTIVE/RET-CONSENT-TOMBSTONE`，每次调用必须在读取缓存前重验 consent generation/范围/到期/撤销。撤销立即使既有会话失效。冷却与双层频率限制只引用安全模型的 `LLM_PROJECTION_COOLDOWN/LLM_PROJECTION_HOURLY_LIMIT`，同意有效时才能返回同一缓存桶。

`PresentationContext` 是授权后渲染输入，不属于 `AccessContext`，也不进入快照、缓存键、query generation、scope 或幂等身份。来源优先级固定为：可信渠道映射的 actor profile IANA zone，其次 schema v1 `[presentation].timezone`，最后 UTC。缺失时使用 `UTC` 并显示 `UTC (fallback: missing)`；任一已提供值无法由当前 IANA tzdb 加载时不猜固定偏移、不再尝试更低优先级，使用 `UTC (fallback: invalid)`。CLI、飞书和 Web 共用同一 `zoneinfo` 转换函数，按 UTC instant 转换并由 tzdb 处理 DST 跳变；上游 `timezone_unknown` 仍不得生成 `resets_at`。UTC、Asia/Shanghai、America/Los_Angeles、DST 间隙/重复时刻、缺失和非法 zone 必须有 golden 序列化测试。

展示层先按 `display_group` 和能力类型分区。只有相同 `capability kind + unit` 的值可以数值排序；跨百分比、货币、次数和状态的首页排序使用统一序列 `none < warning < high < critical`，再以显式 `display_order` 和稳定 ID 作为 tie-breaker，绝不比较“¥10、20%、300 interactions”谁更少。每个命中的 `alert_policy` 先产生一个 severity，同一 capability 的多个策略与独立固定的 health severity 一律取最高值。没有匹配策略且 `health=ok` 时为 `none`，不得偷偷套用百分比默认值。

## 8. Provider Adapter SDK

每个供应商以适配器形式接入，建议最小接口如下：

```python
SelectorScalarType = Literal["string", "integer", "boolean"]

class SelectorFieldSpec:
    name: str                              # 本地 manifest 枚举；不是上游动态 key
    scalar_type: SelectorScalarType
    required: bool
    enum_values: tuple[str | int | bool, ...] | None
    string_pattern: str | None
    integer_min: SignedInt64 | None
    integer_max: SignedInt64 | None

class SelectorSchema:
    schema_id: str
    fields: tuple[SelectorFieldSpec, ...]
    extra: Literal["forbid"]
    canonicalizer: Literal["aq-selector-c14n-v1"]  # 字段名排序、UTF-8/NFC、类型保持

class CredentialRequirement:
    purpose: str                           # manifest 有限枚举，如 quota-read
    allowed_source_kinds: tuple[str, ...]
    min_count: NonNegativeCount
    max_count: UInt16Count

class BudgetPolicy:
    policy_id: str
    version: Literal[1]
    request_floor_seconds: RefreshFloorSeconds
    hourly_group_limit: HourlyEndpointLimit
    blocked_until_scope: Literal["endpoint_budget_group_and_verified_cohort_union"]
    policy_digest_recipe: Literal["aq-budget-policy-digest-v1"]

class FreshnessPolicy:
    policy_id: str
    provider_success_ttl_seconds: Annotated[int, Field(strict=True, ge=1, le=86_400)]
    provider_unavailable_ttl_seconds: Annotated[int, Field(strict=True, ge=1, le=86_400)]
    static_permanent_codes: tuple[Literal["not_applicable", "unsupported"], ...]

# aq-freshness-constants-v1：唯一数值定义；其他文档只引用名称。
CODEX_FRESHNESS_SECONDS = Literal[180]
DEEPSEEK_FRESHNESS_SECONDS = Literal[600]
OPENROUTER_FRESHNESS_SECONDS = Literal[600]

class SubjectSpec:
    kind: SubjectKind
    selector_schema_id: str
    capability_ids: tuple[ManifestCapabilityId, ...]
    allowed_plan_codes: tuple[str, ...]       # 空元组表示该 subject 不接收 plan_code

class ProviderProfile:
    profile_id: str
    provider_variant: str
    region: str
    auth_variant: str
    endpoint_profile: str
    credential_requirements: tuple[CredentialRequirement, ...]
    subject_specs: tuple[SubjectSpec, ...]
    endpoint_budget_group_id: str          # 只引用 group；不得复制预算数值
    network_policy_id: str
    structure_contract_id: str | None       # source_type=undocumented 时恰好引用一个
    identity_source_contract_ids: tuple[str, ...]

class CapabilitySpec:
    capability_id: ManifestCapabilityId
    kind: CapabilityKind
    label_key: str                            # 本地文案 key；该 capability 唯一固定值
    canonical_unit: str | None
    scale: Decimal
    percentage_consistency_tolerance_points: Decimal
    semantic_contract_id: SemanticContractId
    freshness_policy_id: str
    display_param_schema_ids: tuple[str, ...]
    allowed_currency_codes: tuple[str, ...]   # 仅 balance 非空；其他 kind 必须为空
    allowed_status_codes: tuple[LocalStatusCode, ...]  # 仅 status 非空；其他 kind 必须为空

DisplayParamKind = Literal["number", "currency", "enum", "utc_time"]

class DisplayParamFieldSpec:
    name: str
    kind: DisplayParamKind
    required: bool
    enum_values: tuple[str, ...]              # 仅 enum 非空
    currency_codes: tuple[str, ...]           # 仅 currency 非空
    minimum: Decimal | None                   # 仅 number 可用
    maximum: Decimal | None

class DisplayParamSchema:
    schema_id: str
    status_code: LocalStatusCode
    fields: tuple[DisplayParamFieldSpec, ...]
    extra: Literal["forbid"]

SemanticCanaryKind = Literal[
    "sample_range", "max_step_ratio", "balance_composition", "window_consistency"
]
SemanticRecoveryKind = Literal["new_assurance", "frozen_consecutive_samples"]

class SemanticCanaryRule:
    rule_id: str
    kind: SemanticCanaryKind
    min_samples: UInt16Count
    observation_window_seconds: Annotated[int, Field(strict=True, ge=1, le=2_592_000)]
    lower_bound: Decimal | None
    upper_bound: Decimal | None
    max_step_ratio: Decimal | None
    required_field_ids: tuple[str, ...]        # manifest 本地 path ID；不是上游动态 key

class SemanticContract:
    contract_id: SemanticContractId
    capability_id: ManifestCapabilityId
    upstream_numeric_type: Literal["none", "integer", "decimal_string", "number"]
    canonical_unit: str | None
    scale: Decimal
    hard_minimum: Decimal | None
    hard_maximum: Decimal | None
    canary_rule_ids: tuple[str, ...]
    recovery_kind: SemanticRecoveryKind
    recovery_consecutive_samples: UInt16Count | None

StructureValueType = Literal[
    "null", "boolean", "integer", "number", "string", "object", "array"
]

class StructurePathSpec:
    path_id: str                            # 本地稳定 ID，不是上游 path/key 原文
    canonical_path: str                    # 静态路径；map 位置只能写 `<map-key>`
    required: bool
    allowed_types: tuple[StructureValueType, ...]

class StructureMapRule:
    path_id: str
    key_normalization: Literal["<map-key>"]
    max_entries: Annotated[int, Field(strict=True, ge=1, le=64)]
    key_string_max_bytes: Annotated[int, Field(strict=True, ge=1, le=256)]
    require_key_equals_child_path_id: str | None

class BreakagePolicy:
    policy_id: str
    fingerprint_recipe: Literal["aq-structure-fingerprint-v1"]
    max_depth: Annotated[int, Field(strict=True, ge=1, le=32)]
    max_total_nodes: NodeCount
    schema_failure_health: Literal["schema_changed"]
    semantic_failure_health: Literal["semantic_suspect"]
    recovery_policy_id: str                # 引用版本化恢复策略

class StructureContract:
    contract_id: str
    static_paths: tuple[StructurePathSpec, ...]
    map_rules: tuple[StructureMapRule, ...]
    breakage_policy_id: str

ScalarWireType = Literal["string", "integer", "boolean"]

class PathParamSpec:
    name: str
    scalar_type: ScalarWireType
    string_pattern: str | None
    integer_min: SignedInt64 | None
    integer_max: SignedInt64 | None

class QueryFieldSpec:
    name: str
    scalar_type: ScalarWireType
    required: bool
    enum_values: tuple[str | int | bool, ...] | None
    max_occurrences: Literal[1]

class StaticPathSegment:
    kind: Literal["static"]
    value: str                             # 单个已规范 UTF-8 segment，无 `/`、`%`、`.`、`..`

class ParamPathSegment:
    kind: Literal["param"]
    name: str                              # 恰好引用一个 PathParamSpec

PathSegmentSpec = StaticPathSegment | ParamPathSegment

class AuthInjectionPolicy:
    policy_id: str
    kind: Literal["none", "authorization_bearer"]
    credential_purpose: str | None
    allowed_transport_metadata_keys: tuple[str, ...]

class HttpResponsePolicy:
    policy_id: str
    allowed_content_encodings: tuple[str, ...]
    max_wire_bytes: HttpWireBytes
    max_decoded_bytes: HttpDecodedBytes

class HttpEndpointSpec:
    endpoint_id: str
    method: Literal["GET"]
    path_segments: tuple[PathSegmentSpec, ...]
    path_params: tuple[PathParamSpec, ...]
    query_fields: tuple[QueryFieldSpec, ...]
    auth_injection_policy_id: str
    response_policy_id: str
    deadline_policy_id: str
    endpoint_budget_group_id: str

class TransportDeadlinePolicy:
    policy_id: str
    transport: Literal["http", "local-stdio"]
    queue_timeout_seconds: BoundedTransportSeconds
    attempt_timeout_seconds: BoundedTransportSeconds
    aggregate_timeout_seconds: BoundedTransportSeconds
    connect_timeout_seconds: BoundedTransportSeconds | None
    read_timeout_seconds: BoundedTransportSeconds | None
    write_timeout_seconds: BoundedTransportSeconds | None
    handshake_timeout_seconds: BoundedTransportSeconds | None
    request_timeout_seconds: BoundedTransportSeconds | None
    process_execution_timeout_seconds: BoundedTransportSeconds | None
    termination_grace_seconds: BoundedTransportSeconds | None

class HttpNetworkPolicy:
    policy_id: str
    scheme: Literal["https"]
    hosts: tuple[str, ...]
    ports: tuple[int, ...]
    allow_proxy: Literal[False]
    endpoints: tuple[HttpEndpointSpec, ...]
    auth_injection_policies: tuple[AuthInjectionPolicy, ...]
    response_policies: tuple[HttpResponsePolicy, ...]

class LocalFramePolicy:
    policy_id: str
    max_stdin_bytes: LocalStdinBytes
    max_stdout_frame_bytes: LocalFrameBytes
    max_stdout_total_bytes: LocalStdoutBytes
    max_stderr_total_bytes: LocalStderrBytes

class LocalRpcEndpointSpec:
    endpoint_id: str
    rpc_method: str
    role: Literal["request", "notification"]
    frame_policy_id: str
    deadline_policy_id: str
    endpoint_budget_group_id: str

class LocalStdioPolicy:
    policy_id: str
    scheme: Literal["local-stdio"]
    executable_install_ids: tuple[str, ...]
    env_allowlist: tuple[str, ...]
    max_processes: LocalProcessCount
    endpoints: tuple[LocalRpcEndpointSpec, ...]
    frame_policies: tuple[LocalFramePolicy, ...]

NetworkPolicy = HttpNetworkPolicy | LocalStdioPolicy

class OrderedProtocolContract:
    kind: Literal["ordered"]
    version_scheme: Literal["semver", "pep440", "codex-cli-v1"]
    comparator_id: Literal["aq-semver-v1", "aq-pep440-v1", "aq-codex-cli-v1"]
    supported_range: str
    tested_min: str
    tested_max: str
    schema_hash_required: bool

class VersionlessProtocolContract:
    kind: Literal["versionless"]
    version_scheme: Literal["none"]
    evidence_id: str                         # 固定官方合同/fixture 证据摘要
    schema_hash_required: Literal[False]

ProtocolContract = OrderedProtocolContract | VersionlessProtocolContract

IdentitySourceKind = Literal["credential_source", "official_protocol"]
IdentityBindingKind = Literal["credential_binding", "rpc_endpoint", "zero_binding"]
IdentityStability = Literal["verified_stable", "ephemeral"]
IdentityEvidenceField = Literal["access_generation_material", "upstream_subject"]
IdentityStabilityBasis = Literal[
    "credential_generation", "provider_account_subject", "provider_wallet_subject",
    "official_session_generation", "process_ephemeral"
]

class ProviderIdentityDomain:
    domain_id: str
    material_kind: Literal["provider_account", "provider_wallet", "provider_session"]
    canonicalizer_id: Literal["opaque-bytes-v1", "utf8-nfc-v1"]
    min_material_bytes: Annotated[int, Field(strict=True, ge=1, le=512)]
    max_material_bytes: Annotated[int, Field(strict=True, ge=1, le=512)]

class EndpointBudgetGroup:
    group_id: str
    transport: Literal["http", "local-stdio"]
    budget_policy_id: str                 # 唯一 versioned BudgetPolicy
    endpoint_ids: tuple[str, ...]       # UTF-8 bytes 排序、非空、同 manifest endpoint 全分区

class IdentitySourceContract:
    contract_id: str
    contract_version: Literal[1]
    contract_generation: SequenceInt
    source_kind: IdentitySourceKind
    profile_ids: tuple[str, ...]
    binding_kind: IdentityBindingKind
    credential_purpose: str | None
    rpc_endpoint_ids: tuple[str, ...]
    allowed_evidence_fields: tuple[IdentityEvidenceField, ...]
    stability: IdentityStability
    stability_basis: IdentityStabilityBasis
    provider_identity_domain_id: str | None

class EndpointBudgetBinding:
    endpoint_id: str
    endpoint_budget_group_id: str

class AdapterManifest:
    adapter_id: str
    adapter_api_version: str
    adapter_version: str                  # 规范 SemVer，等于发行物版本
    lifecycle: Literal["test_only", "experimental", "supported", "ga"]
    profiles: tuple[ProviderProfile, ...] # 唯一合法组合；禁止平行元组做笛卡尔积
    selector_schemas: tuple[SelectorSchema, ...]
    capability_specs: tuple[CapabilitySpec, ...]
    semantic_contracts: tuple[SemanticContract, ...]
    semantic_canary_rules: tuple[SemanticCanaryRule, ...]
    freshness_policies: tuple[FreshnessPolicy, ...]
    budget_policies: tuple[BudgetPolicy, ...]
    structure_contracts: tuple[StructureContract, ...]
    breakage_policies: tuple[BreakagePolicy, ...]
    display_param_schemas: tuple[DisplayParamSchema, ...]
    network_policies: tuple[NetworkPolicy, ...]
    deadline_policies: tuple[TransportDeadlinePolicy, ...]
    identity_source_contracts: tuple[IdentitySourceContract, ...]
    provider_identity_domains: tuple[ProviderIdentityDomain, ...]
    endpoint_budget_groups: tuple[EndpointBudgetGroup, ...]
    endpoint_budget_bindings: tuple[EndpointBudgetBinding, ...]
    protocol_contract: ProtocolContract
    protocol_schema_hash: str | None       # 第 8.4 节 bundle recipe；有可生成 schema 的协议时必填
    release_assurance_id: str | None       # 第 8.3 节非循环 assurance
    release_attestation_id: str | None     # supported/ga 必填的受信任发行签名
    max_discovered_subjects: DiscoverySubjects
    max_discovered_capabilities: DiscoveryCapabilities
    max_missing_reasons: DiscoveryMissing

AccessIdentityAssurance = Literal["verified_stable", "ephemeral"]

class AccessIdentity:
    cache_identity: str              # principal + 访问代际绑定
    rate_limit_cohort: str           # 只绑定 Provider 稳定上游 subject，或部署级保守 cohort
    assurance: AccessIdentityAssurance

class EvidenceAuthorizationBinding:
    principal_id: PrincipalId
    profile_id: str
    source_contract_id: str
    source_generation: SequenceInt
    credential_binding_id: str | None
    rpc_endpoint_id: str | None

class UpstreamSubjectEvidence:
    provider_identity_domain: str    # manifest 有限枚举，不含 principal/binding/process
    subject_material: SecretBytes    # Field(repr=False, exclude=True)；Provider 稳定上游 subject 规范字节

class CredentialIdentityEvidence:
    source: Literal["credential_source"]
    authorization_binding: EvidenceAuthorizationBinding
    access_generation_material: SecretBytes  # Field(repr=False, exclude=True)；只用于 cache identity
    upstream_subject: UpstreamSubjectEvidence | None
    expires_monotonic_ns: MonotonicNs

class OfficialProtocolIdentityEvidence:
    source: Literal["official_protocol"]
    authorization_binding: EvidenceAuthorizationBinding
    access_generation_material: SecretBytes
    upstream_subject: UpstreamSubjectEvidence | None
    expires_monotonic_ns: MonotonicNs

IdentityEvidence: TypeAlias = CredentialIdentityEvidence | OfficialProtocolIdentityEvidence

ScalarSelectorValue = str | int | bool
ProbeNetworkMode = Literal["offline", "local_only", "network_allowed"]
ProviderRequestKind = Literal["probe", "discovery", "fetch", "identity_and_fetch"]
ProviderIoClass = Literal["pure_local", "provider_io"]

class RateReservationReceipt:
    reservation_id: str
    request_kind: ProviderRequestKind
    endpoint_id: str
    endpoint_budget_group_id: str
    cohort_source: Literal["verified", "deployment_conservative"]
    writer_fencing_token: SequenceInt
    state: Literal["committed"]       # Provider byte 前已提交；Adapter 只读

class CredentialResolution:
    binding_id: str
    principal_id: PrincipalId
    profile_id: str
    purpose: str
    source_kind: str
    secret: SecretStr | None         # Field(repr=False, exclude=True)；进程内使用，禁止序列化
    transport_metadata: tuple["CredentialTransportField", ...]
    identity_evidence: CredentialIdentityEvidence
    expires_at: datetime | None

class CredentialLease:
    binding_id: str
    principal_id: PrincipalId
    profile_id: str
    purpose: str
    source_kind: str
    access_identity: AccessIdentity
    secret: SecretStr | None
    transport_metadata: tuple["CredentialTransportField", ...]
    expires_at: datetime | None

class CredentialTransportField:
    key: str                         # 必须命中 AuthInjectionPolicy 的有限 key
    value: SecretStr                 # Field(repr=False, exclude=True)

class ZeroBindingProof:
    principal_id: PrincipalId
    profile_id: str
    issued_monotonic_ns: MonotonicNs
    expires_monotonic_ns: MonotonicNs
    core_mac: SecretBytes             # Field(repr=False, exclude=True)；只由 core 核验

class NetworkPolicyHandle:
    policy_id: str
    policy_digest: str
    endpoint_id: str

class AuthorizedSelector:
    subject_id: SubjectId
    selector_schema_id: str
    canonical_selector: tuple[tuple[str, ScalarSelectorValue], ...]

class ProbeContext:
    principal: AccountPrincipal
    profile_id: str
    selectors: tuple[AuthorizedSelector, ...]
    credential_leases: tuple[CredentialLease, ...]
    zero_binding_proof: ZeroBindingProof | None
    access_identity: AccessIdentity          # official-cli 首次 probe 可为 ephemeral，禁止持久化
    network_policy: NetworkPolicyHandle
    network_mode: ProbeNetworkMode
    io_class: ProviderIoClass
    request_kind: ProviderRequestKind | None
    reservation_receipt: RateReservationReceipt | None
    deadline_monotonic_ns: MonotonicNs

DiscoveryHandle = Annotated[str, StringConstraints(pattern=r"^disc_[A-Za-z0-9_-]{16,64}$")]
DiscoverySeedId = Annotated[str, StringConstraints(pattern=r"^seed_[A-Za-z0-9_-]{16,64}$")]
MissingReasonCode = Literal[
    "not_entitled", "unsupported_version", "temporarily_unavailable"
]

class DiscoverySeedSelector:
    seed_id: DiscoverySeedId                # core 生成；只在本请求有效
    subject_kind: SubjectKind
    selector_schema_id: str
    canonical_candidate: tuple[tuple[str, ScalarSelectorValue], ...]

class DiscoveryRequest:
    principal: AccountPrincipal
    profile_id: str
    seeds: tuple[DiscoverySeedSelector, ...] # 可为空；为空=发现该 profile/scope 允许的全部 subject kind
    allowed_subject_kinds: tuple[SubjectKind, ...]
    allowed_capability_ids: tuple[ManifestCapabilityId, ...]
    credential_leases: tuple[CredentialLease, ...]
    zero_binding_proof: ZeroBindingProof | None
    access_identity: AccessIdentity
    network_policy: NetworkPolicyHandle
    network_mode: ProbeNetworkMode
    io_class: ProviderIoClass
    request_kind: ProviderRequestKind | None
    reservation_receipt: RateReservationReceipt | None
    deadline_monotonic_ns: MonotonicNs

class DiscoveredSubject:
    handle: DiscoveryHandle          # 只在本次调用有效，不得持久化
    kind: SubjectKind
    selector_candidate: tuple[tuple[str, ScalarSelectorValue], ...]  # key 排序且唯一；无共享可变引用
    suggested_label: str             # NFC/长度/控制字符校验后再按目标转义；不是正式 label

class DiscoveredCapability:
    subject_handle: DiscoveryHandle
    capability_id: ManifestCapabilityId
    kind: CapabilityKind
    canonical_unit: str | None

class MissingCapability:
    subject_handle: DiscoveryHandle
    capability_id: ManifestCapabilityId
    reason: MissingReasonCode

class DiscoveryResult:
    adapter_id: str
    principal_id: PrincipalId
    subjects: tuple[DiscoveredSubject, ...]
    capabilities: tuple[DiscoveredCapability, ...]
    missing: tuple[MissingCapability, ...]
    metadata_observations: tuple["SubjectMetadataObservation", ...]

class SubjectMetadataObservation:
    subject_ref_kind: Literal["discovery_handle", "subject_id"]
    subject_ref: str                    # 按 kind 严格解析为本批 handle 或请求内 SubjectId
    field: Literal["plan_code"]
    plan_code: str                      # 必须命中当前 SubjectSpec.allowed_plan_codes
    observed_at: datetime               # UTC；有限时间范围

class CapabilityRequestItem:
    subject_id: SubjectId
    capability_id: ManifestCapabilityId
    selector_schema_id: str
    canonical_selector: tuple[tuple[str, ScalarSelectorValue], ...]

class CapabilityRequest:
    items: tuple[CapabilityRequestItem, ...]  # `(subject_id, capability_id)` 在请求内唯一

class FetchContext:
    principal: AccountPrincipal
    profile_id: str
    request: CapabilityRequest
    credential_leases: tuple[CredentialLease, ...]
    zero_binding_proof: ZeroBindingProof | None
    access_identity: AccessIdentity          # 必须为 verified_stable
    network_policy: NetworkPolicyHandle
    io_class: Literal["provider_io"]
    request_kind: Literal["fetch", "identity_and_fetch"]
    reservation_receipt: RateReservationReceipt
    deadline_monotonic_ns: MonotonicNs

class ProbeFailureResult:
    kind: Literal["failure"]
    mode: Literal["http", "official_cli_zero_binding", "offline"]
    compatibility: Literal["auth_required", "incompatible", "unavailable", "unverified_version"]
    detected_protocol_version: str | None

class ProbeHttpSuccessResult:
    kind: Literal["http_success"]
    mode: Literal["http"]
    compatibility: Literal["compatible"]
    detected_protocol_version: str | None

class ProbeOfficialCliSuccessResult:
    kind: Literal["official_cli_success"]
    mode: Literal["official_cli_zero_binding"]
    compatibility: Literal["compatible"]
    detected_protocol_version: str | None
    identity_evidence: OfficialProtocolIdentityEvidence

class ProbeOfflineResult:
    kind: Literal["offline_result"]
    mode: Literal["offline"]
    compatibility: Literal["compatible"]
    detected_protocol_version: str | None

ProbeResult: TypeAlias = (
    ProbeFailureResult | ProbeHttpSuccessResult |
    ProbeOfficialCliSuccessResult | ProbeOfflineResult
)

class BootstrapIdentityAuthorization:
    principal_id: PrincipalId
    profile_id: str
    source_contract_id: str
    source_generation: SequenceInt
    rpc_endpoint_id: str

class IdentityAndFetchContext:
    principal: AccountPrincipal
    profile_id: str
    capability_request: CapabilityRequest
    capability_request_digest: LowerHexSha256
    bootstrap_identity_authorization: BootstrapIdentityAuthorization
    zero_binding_proof: ZeroBindingProof
    network_policy: NetworkPolicyHandle
    reservation_receipt: RateReservationReceipt
    deadline_monotonic_ns: MonotonicNs

class IdentityAndFetchResponse:
    identity_evidence: OfficialProtocolIdentityEvidence
    capability_request_digest: LowerHexSha256
    fetch_observation: "FetchBatchResult | FetchBatchFailure"

class IdentityAndDiscoveryContext:
    principal: AccountPrincipal
    profile_id: str
    discovery_request: DiscoveryRequest
    discovery_request_digest: LowerHexSha256
    bootstrap_identity_authorization: BootstrapIdentityAuthorization
    zero_binding_proof: ZeroBindingProof
    network_policy: NetworkPolicyHandle
    reservation_receipt: RateReservationReceipt
    deadline_monotonic_ns: MonotonicNs

class IdentityAndDiscoveryResponse:
    identity_evidence: OfficialProtocolIdentityEvidence
    discovery_request_digest: LowerHexSha256
    discovery_payload: DiscoveryResult

# official-cli 首次身份建立必须使用以上 joint response；不得先返回可复用业务结果。
# core 对一次 context 只允许一次 reservation、一次 response、一次 Provider read，
# 依次验证 authorization → identity evidence → verified identity → request digest → key set，
# 全部成功后才原子接受 payload；digest mismatch 时 config/cache/LKG 零写入。

FetchFailureCategory = Literal[
    "auth_error", "rate_limited", "network_error", "schema_changed",
    "semantic_suspect", "provider_error",
]

class FetchSuccessObservation:
    outcome: Literal["success"]
    subject_id: SubjectId
    capability_id: ManifestCapabilityId
    observed_at: datetime
    value: WindowValue | BalanceValue | CounterValue | StatusValue | None
    status_code: Literal["unlimited", "unknown"] | None
    schema_fingerprint: str | None
    semantic_contract_id: SemanticContractId

class FetchUnavailableObservation:
    outcome: Literal["unavailable"]
    subject_id: SubjectId
    capability_id: ManifestCapabilityId
    observed_at: datetime
    reason: Literal["not_applicable", "unsupported", "not_entitled"]
    provenance: Literal["provider_observation"]

class StaticCapabilityState:
    subject_id: SubjectId
    capability_id: ManifestCapabilityId
    code: Literal["not_applicable", "unsupported"]
    provenance: Literal["manifest_static"]    # 只由 core offline 求值器创建，不是 Adapter DTO

class FetchFailure:
    outcome: Literal["failure"]
    subject_id: SubjectId
    capability_id: ManifestCapabilityId
    observed_at: datetime
    category: FetchFailureCategory
    retry_after_seconds: RetryAfterSeconds | None

FetchItemObservation = FetchSuccessObservation | FetchUnavailableObservation | FetchFailure

class FetchBatchFailure:
    outcome: Literal["batch_failure"]
    request_keys: tuple[tuple[SubjectId, ManifestCapabilityId], ...]
    observed_at: datetime
    category: FetchFailureCategory
    retry_after_seconds: RetryAfterSeconds | None

class FetchBatchResult:
    outcome: Literal["items"]
    items: tuple[FetchItemObservation, ...]
    metadata_observations: tuple[SubjectMetadataObservation, ...]

class ProviderAdapter(Protocol):
    manifest: AdapterManifest

    async def probe(self, context: ProbeContext) -> ProbeResult: ...
    async def discover_subjects(
        self, request: DiscoveryRequest
    ) -> DiscoveryResult: ...
    async def fetch(self, context: FetchContext) -> FetchBatchResult | FetchBatchFailure: ...
```

NetworkPolicy 不再用 method/path/RPC 平行元组。每个 `NetworkPolicyHandle.endpoint_id` 必须命中唯一 endpoint spec；core 只接受该原子 spec 中的 method、逐段 path 参数、单值 query、auth injection、response 和 deadline 引用。DeepSeek schema v1 只有 `endpoint_id=deepseek-user-balance-v1`、`GET`、静态 segments `user/balance`、空 path/query、`authorization_bearer` purpose `quota-read`；通用 builder 不调用 Adapter 私有 URL 代码即可构造请求。Codex 分别登记 `initialize` request、`initialized` notification、`account/rateLimits/read` request endpoint，并各自绑定 frame/deadline；不存在 method/path 或 RPC/frame 的笛卡尔积。未知 endpoint、method/path 错配、重复/未知 query、分隔符注入或凭据解析前后发送对象变化都在解析/附加秘密前拒绝。

deadline 只来自 `TransportDeadlinePolicy`，且必须满足 `0 < queue_timeout <= attempt_timeout <= aggregate_timeout`。schema v1 的唯一值是：HTTP `queue=1.0s, attempt=6.0s, aggregate=9.0s, connect=2.0s, read=3.0s, write=3.0s`，local-stdio `queue=1.0s, attempt=8.0s, aggregate=9.0s, handshake=3.0s, request=6.0s, process_execution=7.5s, termination_grace=0.5s`；不适用字段必须为 null。每次 local attempt 启动一个新进程，handshake 和 request 都计入 7.5 秒 execution，request 上限为 `min(6s, execution_deadline-now)`，7.5 秒到达时 TERM，0.5 秒后 KILL/reap，整个 attempt 不超过 8 秒。排队计入 9 秒 aggregate；各边界在 `now >= deadline` 时到期。因而 3 秒握手+4 秒请求成功，3+6 会被 execution deadline 截断。所有章节和 OperationError 只引用该 policy，不另写 transport 总时长。

以上 manifest/调用 DTO 均以 `extra=forbid, frozen=True` 构造，但 `frozen=True` **不被视为深冻结**。任何跨 Adapter、Provider、Credential Source、Web、Hermes 或存储解码边界的 mapping/list/set，core 必须先做有界深拷贝、验证全部叶子类型，再重建成只含 immutable scalar、frozen DTO 与 canonical tuple 的 core-owned 模型；mapping 统一为按 key UTF-8 bytes 排序且 key 唯一的 `tuple[tuple[K,V], ...]`。输入对象、其子对象和 Adapter 保留的引用之后发生修改都不得改变已验证模型、hash、序列化或提交值。`CredentialResolution` 与 `CredentialLease` 只在本节各定义一次；Source 只能构造前者，core 验证 evidence 并派生 `AccessIdentity` 后才能构造后者。core 与 Provider SDK 直接导入同一模型及 canonical JSON Schema，并分别记录 `credential_resolution_schema_hash` 与 `credential_lease_schema_hash=SHA256(aq-json-c14n-v1(schema))`；任一 hash 不同即拒绝加载。`secret`、每个 `CredentialTransportField.value`、两类 evidence 的 secret bytes、`UpstreamSubjectEvidence.subject_material` 与 `ZeroBindingProof.core_mac` 都必须 `repr=False, exclude=True`，通用 serializer 遇到它们直接拒绝；普通字符串秘密、重复/未知 metadata key、缺 purpose/source_kind/profile、过期 resolution/lease 或 principal/profile/access identity 不匹配都在 Adapter 前拒绝。

core 先规范化 selector、绑定 AccessIdentity、选择 manifest 中已闭包校验的 endpoint spec、计算单调 deadline，并仅在模式允许时解析 Credential Source，再创建一次性 context；Adapter 不得反查全局 registry、Credential Source、环境或“当前账户”状态。`offline` Probe/DiscoveryRequest 必须同时使用空 leases 与空 zero-binding proof、ephemeral identity，且 Adapter I/O 计数为 0；`local_only` official-cli 必须只有 zero-binding proof；`network_allowed` HTTP 必须只有已解析 leases；任何 FetchContext 则必须恰有 leases/zero proof 一类并使用 verified-stable identity。lease 的 principal/purpose/profile/source kind、selector/seed schema、endpoint/policy digest、AccessIdentity 与当前 AccessContext/account scope 全部匹配。调用结束或 deadline 到期后 core 清除 lease 引用，日志/异常/快照/fixture 不得包含 secret、transport metadata、proof 或其 repr。

I/O 判别是封闭规则，不由 Adapter 声明：manifest/schema/URL/argv/文件属性校验、`--version`、不发送业务 method 的 initialize/initialized 握手和纯 fixture parser 是 `pure_local`；任何 outbound HTTP attempt 一律是 `provider_io`，local-stdio 中任何 role=request 且 endpoint purpose 为 probe/discovery/quota observation 的业务 RPC 也是 `provider_io`。`pure_local` context 的 `request_kind/reservation_receipt` 必须同时为空；`provider_io` context 二者必须同时非空，receipt 的 endpoint/group/request kind/fence 必须命中当前 context，且 ledger `committed_at <= first_outbound_byte_at`。doctor、discover、refresh 使用同一规则和同一 rate ledger，不存在“诊断流量”豁免。

每个 Provider I/O attempt（包括已有 verified identity）都必须在一个 `BEGIN IMMEDIATE` 中先检查并占用 endpoint budget group 的 umbrella floor/hour digest；verified 请求同时建立其 cohort-specific digest，身份未知请求只建立 group umbrella digest。发送前 blocker 是 group umbrella 与可用 verified cohort activity 的并集，任一命中均 deferred，因此此前 verified A 的 attempt 会在复制 principal、identity cache 丢失或新进程 bootstrap A 时阻止第二次 outbound byte。若本次已计账 response 产生 stable evidence，core 只在原 reservation 行附加 verified digest；group umbrella索引保留到 `RET-RATE-LEDGER`，不能删除、拆成第二 reservation或再次发送。一个 reservation row 永远只代表并只计一次 Provider attempt；umbrella 与 verified 是同一行的两个索引，不得把小时计数或请求次数相加两次。并发 bootstrap、不同 principal/binding/process 与本地 identity cache 丢失都不能扩容。

`request_kind=identity_and_fetch` 只允许 identity source contract 与 endpoint response contract 同时声明 identity evidence 和完整 quota key 集时使用。core 必须构造 `IdentityAndFetchContext` 并接收唯一 `IdentityAndFetchResponse`；先验证 evidence 并派生 verified identity，再逐字节比较 capability request digest 与完整 key set，最后原子接受 observation。该次 context 恰有一张 reservation、一次 Provider read 与一次 response，不存在 `ProbeResult.reusable_fetch_result` 或第二次读取。Codex 当前没有该 source contract，所以仍不能正式进入这一分支。历史 `AQ-R10-001` 只是非规范性旧编号；当前 blocker ID 只读取顶层 current status source。

MVP 不扫描本机自动发现认证身份。`AccountPrincipal` 必须由用户显式配置或通过 `agent-quota init/account add` 创建。`network_mode=offline` 只校验配置与 manifest，网络、Credential Source 和子进程调用计数必须均为 0；`local_only` 只允许受登记的 local-stdio 协议且不解析 Credential Source（官方 CLI 自身可能产生的协议流量属于其已声明 TCB 风险）；`network_allowed` 只能由本次显式用户动作授予，才可解析该 principal 的凭据并访问 manifest 固定 Provider 出口。HTTP Adapter 在前两种模式下不得联网。`DiscoveryRequest` 不含正式 SubjectId：已有候选只能变成绑定 profile/subject kind/schema 的有限 seed；principal 尚有 0 个 subject 时使用空 seeds，语义是发现本次授权 profile 中 `allowed_subject_kinds/allowed_capability_ids` 的交集，绝不表示全安装。`DiscoveryResult` 是发现的唯一输出，必须同批返回 subjects/capabilities/missing；结果在用户确认前不落盘，确认事务才由 core 生成正式 ID 与本地 label。跨批 handle、越 scope seed、悬空 capability/missing 或 Adapter 把 probe 当 discovery 都整批拒绝。

`probe()` 是配置验证和 `doctor` 的机器可读能力协商。上述类型只是 `core-safety-contract-v1#/probe_result_contract` 的可读投影；机器合同以 `kind` 为判别字段并对每个分支 `additional_properties=forbid`。failure、HTTP success 与 offline 分支禁止 identity evidence；只有 `official_cli_success + official_cli_zero_binding` 分支必须恰有一份 `OfficialProtocolIdentityEvidence`。core 在任何身份派生或写入前依次完成 bounds/discriminator、分支字段基数、额外字段、context mode、authorization binding、evidence lifetime 与派生字段禁令校验；未知分支、跨 profile/RPC/generation evidence、过期 evidence 或 Adapter 返回 AccessIdentity/cache identity/rate cohort/assurance 均原子返回 `adapter_contract_violation`。Credential Source 只能把 `CredentialIdentityEvidence` 放入 `CredentialResolution`，两类 evidence 不可互换。`access_generation_material` 与可选 `subject_material` 分别为 `1..512` bytes，寿命满足 `now_monotonic < expires_monotonic_ns <= now_monotonic+60s`，且本进程单次使用。

唯一派生函数是 `derive_access_identity_v1`。其中 `u64be(n)` 是无符号 64-bit big-endian，JSON 均为 `aq-jcs-nfc-v1`，HMAC 原始 32 bytes 只在最外层编码为 lowercase hex：

```python
access_digest = HMAC_SHA256(
    active_key_for_consumer("access-generation-digest-v1"),
    b"agent-quota:access-generation:v1\x00"
    + JCS({"adapter_id": adapter_id, "profile_id": profile_id,
           "source_contract_id": binding.source_contract_id,
           "source_generation": binding.source_generation})
    + u64be(len(access_generation_material)) + access_generation_material,
)
cache_identity = "aqci_" + HMAC_SHA256(
    active_key_for_consumer("cache-identity-prf-v1"),
    b"agent-quota:cache-identity:v1\x00"
    + JCS({"adapter_id": adapter_id, "profile_id": profile_id,
           "principal_id": binding.principal_id}) + access_digest,
).hex()

if upstream_subject is not None:  # 只在 source contract 证明为 Provider 稳定 subject 后允许
    rate_limit_cohort = "aqrc_" + HMAC_SHA256(
        active_key_for_consumer("rate-limit-cohort-prf-v1"),
        b"agent-quota:upstream-subject-cohort:v1\x00"
        + JCS({"adapter_id": adapter_id,
               "provider_identity_domain": upstream_subject.provider_identity_domain})
        + u64be(len(upstream_subject.subject_material))
        + upstream_subject.subject_material,
    ).hex()
else:
    rate_limit_cohort = "aqrc_" + HMAC_SHA256(
        active_key_for_consumer("rate-limit-cohort-prf-v1"),
        b"agent-quota:deployment-conservative-cohort:v1\x00"
        + JCS({"installation_id": installation_id, "adapter_id": adapter_id,
               "endpoint_budget_group": endpoint_budget_group}),
    ).hex()
```

`principal_id/credential_binding_id/rpc_endpoint_id/source_generation/process_id` 都不得进入稳定上游 subject 的 cohort 分支。多份访问材料只有在同一 manifest source contract 能验证出相同 `provider_identity_domain + subject_material` 时才合并；否则必须进入部署级保守 cohort。因此复制 principal、binding 或进程不增加预算，而 cache identity 仍按 principal+访问代际隔离。派生后立即覆写/释放全部 secret evidence；它们不得进入 TOML、SQLite/WAL/SHM、缓存、日志、异常、fixture、投影、审计或 repr。

`active_key_for_consumer()` 只接受 LocalKey artifact 的 `consumer_id`，新值永远只用 active generation。读取/验签既有持久对象必须按该 artifact 的 `persistent_surfaces` 选择 consumer 组合：每个 consumer 先 active、再 verify-only generation 降序；多个 consumer 按 consumer ID UTF-8 bytes 升序做有界笛卡尔积，以最终 record digest 去重，超过 surface 上限立即拒绝。rate ledger 因 cohort 与 record digest 交错轮换最多检查 artifact 登记的 16 组，任何一组命中 blocker 都拒绝新 attempt；保护窗到期且引用计数为零后才可退休旧 generation。正文公式不得再以自由 key 变量或 purpose 字符串隐式建立映射。

零 binding 的 `official_cli` 必须通过受信任本地协议返回可验证的账户/会话代际 evidence，由 core 生成 `verified_stable` AccessIdentity；拿不到时不得正式 `fetch` 或复用持久化缓存，Supported 候选直接为 `incompatible`。当前决策明确不批准 Codex 任何可用于正式 `fetch` 的 `source_contract_id` 或协议字段；因此 Codex manifest 不得登记任何 `verified_stable` identity evidence contract，也不得加入 `account/read`。未来只有新的显式用户决策、合同版本更新与独立审计共同完成后才能改变该限制。历史 `AQ-R10-001` 是非规范性索引；当前 ID 只由 current status source 给出。

core 把 Adapter 返回值视为不可信边界。`probe/discover/fetch` 每次调用返回后、写配置/缓存/LKG/失败计数前必须整批执行以下原子校验：

1. `ProbeResult` 只允许判别联合对应分支的封闭字段，不含业务发现字段；official-cli success 的 evidence 必须先经 `probe_result_validate`，其余分支出现 evidence 一律拒绝。`DiscoveryResult.adapter_id/principal_id` 必须等于实际加载 manifest/调用 principal。fetch item 本身不重复 adapter/principal，二者只由不可变 context 决定。
2. discovery 只能返回 `DiscoveredSubject/DiscoveredCapability/MissingCapability`，不得返回 `aqp_/aqs_` 正式 ID；每个 handle 在本批唯一，capability/missing 必须引用同批 handle，selector 只能含 request seed/schema 和允许 scope 已声明字段。`fetch` 的正式 subject/capability 必须属于当前 registry；请求和 observation 都以 `(subject_id, capability_id)` 为 key。
3. discovery subject/capability/missing 条目分别不得超过 manifest 上限。`FetchBatchResult.items` 的 key 集必须与请求集合完全相等且每 key 恰好一项；`FetchBatchFailure.request_keys` 同样必须规范排序且完全相等。空、漏、重复、额外或跨 subject 结果整批返回 `adapter_contract_violation`。本地 scope 不允许根本不会进入 Adapter；已授权请求的上游“不适用/未提供 entitlement”使用 `FetchUnavailableObservation`，不能省略 key。suggested label 拒绝控制/双向字符和越界长度，不能进入日志。
4. success observation 的 kind/unit/value discriminator/`semantic_contract_id` 与 manifest 完全一致；unavailable/failure 的 reason/category 位于封闭枚举。Adapter 不得读取 core cache，也不得返回 `CapabilitySnapshot`、LKG、`data_freshness`、`expires_at` 或自造 health。
5. `MissingCapability.reason` 只能取 `not_entitled|unsupported_version|temporarily_unavailable`；本地 `not_authorized` 永远是 OperationError，不是 discovery reason。每条 missing 必须绑定同批 handle 与 manifest capability 且二元组唯一；悬空 handle、未知 capability、重复二元组、外部 ID/邮箱形态和超量条目均拒绝。渲染器只把 code 映射为本地文案。
6. 任一失败则整批返回稳定操作错误 `adapter_contract_violation` 或 `invalid_discovery_result`：不得部分接受，不得写配置/缓存/LKG、刷新成功时间或失败计数，也不得在日志保存违规返回值；其他 principal/subject 状态不变。

`SubjectMetadataObservation` 是 plan 的唯一 Provider 输出路径。discovery 只能使用同批 handle，fetch 只能使用本请求 subject ID；每个 subject/field 最多一项。已知 `plan_code` 必须命中该 profile/subject kind 的有限 `allowed_plan_codes`，不得含 label/上游原文；上游 absent/null/`unknown`/未登记值在 Adapter parser 中立即丢弃并不形成 DTO，恶意 Adapter 直接返回未知值则整批合同拒绝。初次 discovery 的已知 plan 随用户确认由 migration journal 写入 `SubjectConfig.plan_code`；未确认前不落盘。

已配置 subject 后观察到相同 plan 只更新假名化 `last_observed_at`（规范记录 `persist:v1:subject_metadata_observed:update:RET-SUBJECT-METADATA-OBSERVED`）；观察到不同已知 plan 写入隔离的 `plan_change_pending` 行，使用 `RET-SUBJECT-METADATA-PENDING`，不自动改 TOML、capability、selector 或旧 generation，并按 `(subject_id,old_plan_code,new_plan_code,current_generation)` 只发一次本地维护告警，通知不含 plan 原值。用户执行 `configure` 的同一 planner/digest/nonce 确认后，journal 原子更新 config plan、递增 `subject_metadata_generation` 与 `query_contract_generation`、删除旧缓存/LKG/metadata pending并关闭维护告警；拒绝/到期只清 pending。subject disable/delete/generation replacement 或 purge 在同一事务清理 observed/pending metadata。confirmed plan 只随 config/object 生命周期保留，不另设 TTL。

只有 core 能把 observation 合成为 `CapabilitySnapshot`。整批 key/类型验证通过后，core 在一个当前 runtime fence/当前 query generation 的读事务中原子读取全部 LKG：success 使用 capability 的精确 freshness policy 生成 `fresh+ok`；provider unavailable 生成有限 TTL 的 `fresh+unsupported`；failure 有同 generation 且类型匹配的 LKG 时生成 `stale + 对应 health`，否则生成 `expired + 对应 health + value=None`。`manifest_static` 只能由 core 的 offline manifest 求值器产生，Adapter 返回该 provenance 视为越界；它是唯一可以按 policy 使用 `expires_at=None` 的来源。批量 transport 失败用 `FetchBatchFailure` 同时作用于完整 request key 集；逐 capability 业务失败用 item failure。core 完成全部 snapshot、ledger 和失败动作后一次事务提交；半批错误、越 fence、LKG 类型错配或提交崩溃都零部分写入。Adapter 对 cache/registry 的访问计数必须为 0。

manifest 及其全部嵌套类型使用 `extra=forbid, frozen=True` 的严格 schema。`ProviderProfile` 是合法的 variant/region/auth/endpoint/binding/subject/refresh/network 组合分支；通用加载器只能按一个完整 profile 匹配，禁止把多个平行列表交叉拼接，也禁止 Adapter 私有 `if/else` 补足合同。每个 `CredentialRequirement` 的 purpose、source kind 与数量范围，以及每个 `SubjectSpec` 的 selector schema/capability/plan code 集合，都必须仅靠 manifest 完成离线校验。selector 使用字段判别类型、有限枚举/值域和固定 `aq-selector-c14n-v1`；未知字段或组合整批拒绝。

通用 loader 必须先完成全图闭包，再允许匹配 profile：所有 ID 在各自命名空间唯一；`ProviderProfile.network_policy_id/structure_contract_id/identity_source_contract_ids`、`SubjectSpec.selector_schema_id/capability_ids`、`CapabilitySpec.semantic_contract_id/freshness_policy_id/display_param_schema_ids`、`SemanticContract.canary_rule_ids`、endpoint 的 auth/response/deadline/frame/budget-group 引用与 `StructureContract.breakage_policy_id` 必须恰好引用一个同 manifest 对象，悬空、重复和未使用的安全合同都拒绝。`source_type=undocumented` 的 profile 必须恰好引用一个 StructureContract，其他 profile 必须为 `None`；通用 loader 因此可在 offline、零 Adapter 私有代码条件下拒绝缺失合同。

identity/budget 子图另执行以下完整闭包，任一失败都在 evidence/凭据派生前拒绝：每个 profile 引用的 source contract 必须反向包含该 profile；`credential_source` 只能用 `credential_binding`、非空 credential purpose、空 RPC 集，`official_protocol` 只能用 `rpc_endpoint|zero_binding`、空 credential purpose、非空且同 profile local-stdio endpoint 集。`verified_stable` 必须允许 `access_generation_material`；只有同时允许 `upstream_subject` 时才可引用一个 `ProviderIdentityDomain`，反之 domain 必须为空。`ephemeral` 只能使用 `process_ephemeral` 且不能提供 upstream subject。domain ID 全局唯一且必须恰被至少一个 stable source 使用；source、domain、group、binding 的重复/悬空/未使用全部拒绝。每个会产生 Provider I/O 的 endpoint 必须在 endpoint spec 和 `EndpointBudgetBinding` 中恰好映射同一个 group；group 的 endpoint 集与反向 binding 集必须完全相等、互不重叠并覆盖全部 Provider-I/O endpoint。notification/纯握手 endpoint 仍映射其所属组但不会自行形成 ledger attempt。`contract_generation` 只允许随 source schema/stability/domain/endpoint 集变化而严格递增，旧 generation evidence 不能用于新 manifest。

DeepSeek schema v1 登记 `deepseek-credential-generation-v1`：`source_kind=credential_source`、`binding_kind=credential_binding`、purpose=`quota-read`、evidence 仅 `access_generation_material`、`stability=verified_stable`、basis=`credential_generation`、domain=null；`deepseek-user-balance-v1` 映射 `deepseek-balance-global-v1` 保守 budget group，因此凭据轮换隔离 cache，但没有 Provider 主体证据时所有该部署请求共享该组的唯一 conservative cohort。OpenRouter 只登记 `openrouter-credential-generation-v1` 作为 access/cache identity source：已验证 API key binding 与 `CredentialResolution.generation` 共同形成访问代际；`creator_user_id` 只是同次已认证 response 的有界 observed metadata，官方文档没有承诺长期稳定或不可回收，禁止进入 stable ProviderIdentityDomain、cache/access identity 或 cohort。`openrouter-current-key-v1` 映射 `openrouter-current-key-global-v1` 的 endpoint/deployment conservative cohort。Codex 只登记 `codex-local-rate-limit-v1` budget group，没有可产生 `verified_stable` 的 identity source/domain，不能由实现补写。历史 `AQ-R10-001` 仅为非规范性索引。

`QuotaSubject.plan_code` 只能取匹配 `SubjectSpec.allowed_plan_codes`；`QuotaCapability.label_key` 必须等于其 `CapabilitySpec.label_key`；balance entry、status value 和 display 参数分别只能取有限集合。kind、freshness、structure 和 endpoint 判别类型决定字段唯一合法组合。结构指纹只对规范 path ID/type 排序后哈希，map 原 key验证后替换为 `<map-key>` 并立即丢弃；同结构语义漂移仍交给 SemanticContract。通用 JSON Schema/模型必须独立拒绝未知、重复、悬空、未使用或越界合同，不得调用 Adapter 私有代码补齐。

`ProtocolContract` 是判别联合而不是三元 nullable 字段。`ordered` 必须使用登记的 comparator 对 `supported_range/tested_min/tested_max` 解析并证明 `tested_min <= tested_max` 且两端位于支持范围；字符串不可比较、未知 scheme/comparator 或边界倒置拒绝。Codex 固定 `codex-cli-v1/aq-codex-cli-v1` 且 `schema_hash_required=true`。没有上游版本号的 DeepSeek 官方 HTTP 合同与 FakeAdapter 使用 `versionless`，以固定 `evidence_id` 锁定官方合同/fixture，禁止伪造 `0`、`latest` 等版本；此分支不得出现测试边界且 `protocol_schema_hash=None`。若 ordered 分支要求 schema hash，则 hash 必填，否则必须为 `None`。

`planned` 只是路线图记录，不允许发行 entry point，schema v1 配置引用它稳定返回 `adapter_not_distributable`。可执行的 `test_only/experimental/supported/ga` 都必须给出规范 SemVer `adapter_version`、完整 `ProtocolContract` 与 `release_assurance_id`；`supported/ga` 还必须有第 8.3 节受信任且未撤销的 `release_attestation_id`。缺任一适用字段时整个 Adapter entry point 拒绝加载，不能靠生命周期降级继续 fetch。assurance、发行 attestation 与 schema bundle 分别只按第 8.3、8.4 节计算；用户配置、sdist 本地构建和普通 probe 不能自造。`adapter_version/protocol_contract/protocol_schema_hash/release_assurance_id/release_attestation_id` 全部参与 query generation。普通 probe 成功不构成新 assurance 或发行授权。

适配器元数据需要声明：

- Adapter API 版本、生命周期状态和已验证的上游协议版本范围。
- 支持的认证变体、地区、主体类型和 Credential Binding 数量范围（可为零或多个）。
- 是否使用公开 API。
- 按 `source_type` 冻结的刷新地板、滑动窗口次数上限与并发策略。
- 稳定的 capability ID、判别类型、规范单位、缩放规则、语义 canary/跳变规则、不变量与缺失原因。
- 每个本地 `status_code` 可接受的 display 参数名、判别类型和有限枚举；core 在 Adapter 返回边界再次强制。
- 是否允许在开源版本中默认启用。
- 凭据失效、限流、网络失败的错误映射。
- 固定的协议、域名、端口、HTTP 方法/路径或本地 RPC 方法允许列表。
- 代理、重定向、TLS、超时和最大响应体策略。
- `breakage_protocol`、当前结构指纹和连续失败处理策略。

详细认证与失效处理见 [Provider 与凭据契约](provider-contract.md)。

### 8.0 安全关键标量与资源上限

下列 `aq-bounds-v1` 是 JSON Schema、Pydantic `Annotated` 和 manifest loader 共用的唯一机器边界。签名 manifest 只能选择范围内更保守的值，不能放宽 hard maximum；整数以拒绝 bool 的数学整数解析，Decimal 只接受 ASCII，时间在构造 `datetime` 或分配缓冲区前检查。

```python
UInt16Count = Annotated[int, Field(strict=True, ge=1, le=65_535)]
NodeCount = Annotated[int, Field(strict=True, ge=1, le=65_536)]
NonNegativeCount = Annotated[int, Field(strict=True, ge=0, le=65_535)]
SignedInt64 = Annotated[int, Field(strict=True, ge=-(2**63), le=2**63-1)]
SequenceInt = Annotated[int, Field(strict=True, ge=1, le=2**63-1)]
MonotonicNs = Annotated[int, Field(strict=True, ge=0, le=2**63-1)]
RefreshFloorSeconds = Annotated[int, Field(strict=True, ge=0, le=86_400)]
HourlyEndpointLimit = Annotated[int, Field(strict=True, ge=1, le=1_000)]
ProviderConcurrency = Annotated[int, Field(strict=True, ge=1, le=4)]
GlobalConcurrency = Literal[4]
PendingTaskLimit = Literal[32]
MaxAttempts = Literal[1]
RetryAfterSeconds = Annotated[int, Field(strict=True, ge=0, le=86_400)]
UnixUtcSeconds = Annotated[int, Field(strict=True, ge=0, le=253_402_300_799)]
DurationMinutes = Annotated[int, Field(strict=True, ge=1, le=5_256_000)]
DiscoverySubjects = Annotated[int, Field(strict=True, ge=1, le=1_024)]
DiscoveryCapabilities = Annotated[int, Field(strict=True, ge=1, le=4_096)]
DiscoveryMissing = Annotated[int, Field(strict=True, ge=0, le=4_096)]
HttpWireBytes = Annotated[int, Field(strict=True, ge=1, le=1_048_576)]
HttpDecodedBytes = Annotated[int, Field(strict=True, ge=1, le=1_048_576)]
LocalStdinBytes = Annotated[int, Field(strict=True, ge=1, le=65_536)]
LocalFrameBytes = Annotated[int, Field(strict=True, ge=1, le=262_144)]
LocalStdoutBytes = Annotated[int, Field(strict=True, ge=1, le=1_048_576)]
LocalStderrBytes = Annotated[int, Field(strict=True, ge=1, le=262_144)]
LocalProcessCount = Annotated[int, Field(strict=True, ge=1, le=4)]
EnvelopeBytes = Annotated[int, Field(strict=True, ge=1, le=1_048_576)]
InstallPlanBytes = Annotated[int, Field(strict=True, ge=1, le=1_048_576)]
TrustBundleBytes = Annotated[int, Field(strict=True, ge=1, le=1_048_576)]
TrustChainBytes = Annotated[int, Field(strict=True, ge=1, le=8_388_608)]
MigrationPlanBytes = Annotated[int, Field(strict=True, ge=1, le=1_048_576)]
ReleaseFileCount = Annotated[int, Field(strict=True, ge=1, le=4_096)]
ReleaseControlFileCount = Literal[5]
SignatureCount = Annotated[int, Field(strict=True, ge=1, le=64)]
RootKeyCount = Annotated[int, Field(strict=True, ge=1, le=64)]
ReleaseKeyCount = Annotated[int, Field(strict=True, ge=1, le=256)]
InstallKeyCount = Annotated[int, Field(strict=True, ge=1, le=64)]
RevocationCount = Annotated[int, Field(strict=True, ge=0, le=4_096)]
DistributionBindingCount = Annotated[int, Field(strict=True, ge=1, le=4_096)]
TrustChainLength = Annotated[int, Field(strict=True, ge=1, le=32)]
JsonDepth = Annotated[int, Field(strict=True, ge=1, le=32)]
JsonNodeCount = Annotated[int, Field(strict=True, ge=1, le=100_000)]
JsonStringBytes = Annotated[int, Field(strict=True, ge=0, le=4_096)]
MigrationActionCount = Annotated[int, Field(strict=True, ge=0, le=999_999)]
BoundedTransportSeconds = Annotated[
    Decimal, Field(gt=Decimal("0"), le=Decimal("9"), max_digits=3, decimal_places=1)
]
```

所有 `Decimal` wire string 使用 `aq-decimal-38-18-v1`：UTF-8/ASCII 长度 `1..58` bytes，regex `^(0|[1-9][0-9]{0,37})(\.[0-9]{1,18})?$`，整数位最多 38、小数位最多 18，总 significant digits 最多 38；禁止符号、指数、前后空白、前导零、NaN/Infinity，先验长度/regex 后才构造 Decimal。内部 Decimal 也必须 finite，绝对值 `< 10^38`，scale 不超过 18。百分数点固定 `0..100`；ratio/canary `0..10^6`；序列、fencing token、generation 与 episode ID 是 `1..2^63-1`，任何加一将溢出时 fail closed 为 `storage_unavailable`，不得回绕。

时间字符串只接受第 8.3.1 节 UTC 秒格式；Unix 秒先验证 `UnixUtcSeconds` 再转换，超界为 `schema_changed`。monotonic deadline 使用同进程 `0..2^63-1` ns，计算采用 checked subtraction/addition；UTC 与 monotonic 绝不直接相减。`retry_after_seconds` 只来自：合法 `Retry-After` delta-seconds（ASCII `^[0-9]{1,5}$`）、合法 HTTP-date 与 DB UTC 的非负差、或 manifest policy。header 总长度最多 64 bytes；过去日期归一为 0，超过 hard max 归一为 86_400 并仍返回 `rate_limited`，错型/重复/非法日期忽略 header 而使用 manifest policy，绝不把 header 原文写入输出。

跨字段不变量：`0 <= request_floor_seconds <= 86_400`；hourly limit 非空时 `request_floor_seconds * hourly_endpoint_limit <= 3_600 * hourly_endpoint_limit` 不作为放宽依据，两个限制都独立执行；`provider_concurrency <= GlobalConcurrency`；`max_processes <= GlobalConcurrency`；`max_stdout_frame_bytes <= max_stdout_total_bytes`；`max_wire_bytes <= max_decoded_bytes`（schema v1 二者都固定 1 MiB）；`0 < queue <= attempt <= aggregate <= 9`，transport 子 timeout 均 `<= attempt`；discovery 三类实际长度分别 `<=` manifest limit 且 manifest limit `<=` hard maximum；`max_attempts` 恰为 1。

所有签名 envelope、install plan、trust bundle/chain、migration plan 与 release 目录都执行同一顺序：先由 no-follow `fstat`/流式读取执行 raw byte/file-count hard bound；再用 streaming UTF-8 tokenizer 执行 `JsonDepth/JsonNodeCount/JsonStringBytes`；随后才允许严格 JSON parse、JCS/NFC、key/count/threshold 校验与密码学验证；目录内容则在签名通过后才枚举目标文件并流式 hash，最后才允许 ZIP 解包、import、build backend 或 pip。任何前序失败都不得进入后一阶段。

加载签名 manifest、解析 response 或启动子进程前执行 bounds validator。property/fuzz gate 必须覆盖每个边界 `min-1/min/max/max+1`、负数、零、bool、`2^63±1`、百万位十进制、巨大 timestamp、NaN/Infinity、超大 signed manifest 与 checked arithmetic overflow；拒绝必须发生在凭据解析、大对象分配、进程启动和 Provider 调用前，单 fixture 输入读取只引用 `EnvelopeBytes`，墙钟只引用对应 aggregate deadline。

### 8.1 非公开接口断裂协议

每个 `source_type=undocumented` profile 必须在 manifest 中恰好引用一个版本化 `StructureContract`，该合同再恰好引用一个 `BreakagePolicy`；缺失、悬空、重复、未使用或 public/official profile 私带合同都由通用 loader 在 offline 阶段拒绝。合同以本地 path ID 冻结 required/optional 基础类型、`<map-key>` 归一化、key/child 约束、基数/深度/总节点、`aq-structure-fingerprint-v1` recipe、schema/semantic 唯一失败类别和恢复 policy，不允许 Adapter 私有代码补字段。统一 breakage protocol 为：

1. 对最后一次成功响应的“白名单静态字段路径 + 基础类型”生成稳定哈希；映射型对象的动态键统一替换为 `<map-key>`，哈希不得包含字段值、Token、Cookie、邮箱或账户 ID。结构相同仍必须继续执行 manifest 的语义/单位 canary。
2. 新响应进入正式解析前先生成结构指纹，并与最近成功指纹比较。
3. 结构变化时记录脱敏后的新增/缺失字段路径、HTTP 状态码、适配器版本和发生时间，不记录完整原始响应。
4. 解析异常不得向上冒泡。Adapter 返回覆盖完整 request keys 的 `schema_changed` failure；core 有当前 generation LKG 时合成 `stale`，否则合成 `expired`，展示层降级为“暂不可用”。
5. 每类失败分别按 [Provider 契约唯一失败表](provider-contract.md#94-连续失败与恢复) 计数和暂停；schema/semantic、network/provider、auth、rate-limit 与本地协议错误不能共享一个泛化状态。按需 probe/refresh 仍受非公开接口“同一 cohort 的相同请求至少 5 分钟、同一 `rate_limit_cohort/endpoint` 每小时最多 6 次”的硬限制。复制 principal 不会获得新预算。只有安装 SchedulerHost 时才存在定时刷新和维护告警。
6. 恢复也只按该表的唯一事件执行：schema/semantic 需要新 assurance generation 或已冻结自动规则，普通 probe 不足以恢复；其他类别不得借无关成功清零。恢复事务按表更新结构指纹、对应计数与调度状态。

非公开适配器一律标为 Experimental、默认关闭。开启时需要用户显式确认稳定性和供应商条款风险。

### 8.2 Adapter 生命周期与支持顺序

可执行 Adapter 生命周期是机器可读字段；`planned/no-contract` 只属于路线图登记，不是 manifest lifecycle 值：

- `test_only`：只供独立 `agent-quota-testkit` 发行物使用；禁止注册到用户 Adapter entry point、禁止成为生产 meta distribution 依赖，永不计入支持数量。testkit wheel/sdist 只由 CI/合约测试显式安装。
- `planned`：只有 `no-contract` 路线图记录；无可执行 manifest、auth variant、capability 或 NetworkPolicy，不进入发行包和支持数量，schema v1 配置稳定拒绝。
- `experimental`：默认关闭，可用于本地试验，不计入 MVP 支持数量。
- `supported`：NetworkPolicy、协议范围、真实合约测试和错误降级均通过，可计入 MVP。
- `ga`：在多个版本和平台持续通过兼容性测试，并有迁移承诺。

| 阶段 | Adapter | 目标状态 | 理由 |
| --- | --- | --- | --- |
| 1A | FakeAdapter | `test_only` | 在无网络、无凭据条件下验证多 principal/subject/capability 组合 |
| 1B | DeepSeek | supported 候选 | 官方多币种余额与 `is_available` 状态验证 balance/status capability |
| 1B | OpenRouter | supported 候选 | 官方 `GET /api/v1/key` 验证当前 key 的 limit/remaining/usage/expiry；API key binding+credential generation 提供 access/cache identity，`creator_user_id` 仅作 observed metadata；真实 opt-in 门禁通过前不计数 |
| 实验通道 | OpenAI Codex | `experimental/incompatible`、默认关闭 | 保留只读 app-server allowlist；没有批准的 stable identity source，不新增 `account/read`，不得正式 fetch、持久化 cache/LKG 或计入 MVP |
| 后续版本化升级 | Kimi Coding Plan、MiniMax 中国区、GLM | `planned/no-contract` → experimental | 取得协议证据并一次性加入 auth、capability、NetworkPolicy 与 fixture 后接入，不阻塞 1A |
| 后续 | GitHub Copilot、OpenAI Platform Usage/Costs | planned | 验证工作区、组织与复杂计费主体 |
| P2 | 第三方自定义 Adapter | planned | MVP 禁止接触原始凭据；独立进程隔离通过安全评审后再开放 |

一个 Adapter 只有达到 `supported/ga` 才能被文档称为“支持”。默认关闭或未经真实合约验证的 Experimental Adapter 不计入独立 MVP 退出条件。

OpenRouter 的机器权威源是 `core-safety-contract-v1.openrouter_adapter_contract`。核验于 2026-07-19 的官方资料为：[`GET /api/v1/key`](https://openrouter.ai/docs/api/api-reference/api-keys/get-current-key)、[`GET /api/v1/credits`](https://openrouter.ai/docs/api/api-reference/credits/get-credits)、[Authentication](https://openrouter.ai/docs/api/reference/authentication)、[Limits](https://openrouter.ai/docs/api/reference/limits) 和 [OpenAPI](https://openrouter.ai/openapi.json)。MVP 只使用 `https://openrouter.ai:443/api/v1/key`：`GET`、无 query/body、`Authorization: Bearer` 由 core 从 `quota-read` CredentialLease 注入，`trust_env=False`、禁止 redirect、验证 TLS hostname/system roots、只接受 identity 编码的 JSON，wire/decoded 各 64 KiB，queue/attempt/aggregate 为 1/6/9 秒。

响应必须在全局深度/节点/string bounds 后得到 required `data` object。`creator_user_id` 是 required，但允许 null 或 `1..256` UTF-8 bytes 非空字符串；null 表示没有 observed metadata，非 null 也只作为 authenticated observed metadata，不展示/记录，不参与 stable ProviderIdentityDomain、access/cache identity、query generation 或 rate cohort，null/非 null/值变化都不得改变这些身份。cache/access identity 只来自已验证 API key binding 与 `CredentialResolution.generation`，轮换必须改变访问代际。`limit|limit_remaining` 都是 required JSON number 或 null；只有两者同时 null 才表示“当前 key cap unlimited”，绝不表示账户余额无限。两者必须同为 null 或同为 finite 非负 number，finite 时还必须满足 `0 <= limit_remaining <= limit`；nullability 不匹配、越界或 remaining 大于 limit 均 fail closed。`usage|usage_daily|usage_weekly|usage_monthly` 为有限非负 number；`limit_reset` 为 null 或 `1..64` bytes 字符串；`is_management_key` 为 bool。`expires_at` 是 optional：缺失投影 `unknown/not_supplied`，null 投影 `no_expiration`，非 null 必须是 RFC 3339 UTC 并投影 known expiry。bool、数字字符串、指数、NaN/Infinity、超界 Decimal 或错型整批 `schema_changed`；弃用 `rate_limit` 忽略，不能生成 capability 或刷新预算。

`GET /api/v1/credits` 返回账户 total credits/usage，但官方要求 management key。MVP 不为了余额索取超权凭据；该 endpoint 保持 planned、显式 opt-in 且不计当前合同。`/api/v1/key` 的 per-key credit cap/usage 不得标成总账户余额或法币。OpenRouter 只有真实凭据下的正常/null/缺失/错型/401/403/429/5xx/超限/identity rotate 合同测试、官方条款复核、签名发行 attestation 与 macOS Desktop E2E 全部通过后才能从 supported candidate 升为 `supported`。

### 8.3 可复现 assurance 与受信任发行 attestation

可复现性与发行者真实性是两层不同证据。`release_assurance_id` 使用 `aq-assurance-v1`，证明“这组代码、manifest、fixture 和报告可重算”；`release_attestation_id` 引用受信任发布者的 `aq-release-attestation-v1`，证明“被批准的是这个包和版本”。wheel 的 `RECORD` 只用于安装内容的内部完整性，绝不充当发布者身份或信任根。

受控构建与运行时验证器按以下唯一流程执行：

1. 发布者用 CSPRNG 生成 128 bits并编码为 `release_attestation_id="aqra_" + base64url_no_padding(random_bytes)`，写入 manifest；该 ID 不由 wheel digest 推导，因此没有签名自引用。wheel 使用规范路径、固定时间戳/压缩/mode，源树、lock、backend 与构建器版本进入证明。
2. 计算 `adapter_payload_digest` 时，严格执行第 8.3.0 节 `aq-assurance-v1` 的 wheel entry、manifest carrier、mode、symlink、duplicate 和 JCS recipe；不存在未定义的 `canonical(...)`。
3. 生成第 8.3.0 节 exact `assurance_payload`；`release_assurance_id=SHA256(domain || JCS(assurance_payload))`。写回该 ID、生成唯一 sidecar 并重建规范 `RECORD` 后得到最终 wheel；对最终 wheel 原始字节再计算 `wheel_sha256`。
4. 受信任发布 key 对第 8.3.1 节 exact `attestation_payload` 签名。签名和 payload 作为 detached attestation 随 wheel 分发，不写回 wheel。一个 attestation ID 只能绑定一个包名、版本、文件名和 wheel digest；跨包、跨版本、改名或降级重放一律拒绝。
5. core/CLI 随代码携带只读的版本化 publisher trust bundle：根 key、允许的 distribution name/publisher 绑定、子 key 有效期、撤销条目和单调 `bundle_sequence`。bundle 更新必须由现有根的阈值签名授权；InstallationRegistry 保存见过的最大 sequence，旧 bundle 不得回滚覆盖。离线安装不访问网络，只使用随安装器提供且 sequence 不低于本机锚点的 bundle；过期或已撤销 key、错误发布者、未知根、签名/有效期失败均拒绝。
6. 安装器在解包前验证 detached 签名与最终 `wheel_sha256`，安装后以 `RECORD` 检查文件，再从安装内容重算 `adapter_payload_digest/release_assurance_id`。InstallationRegistry 只保存已验证 attestation payload、签名、bundle sequence 和非秘密 digest。每次加载 Supported/GA Adapter 都重验签名、撤销状态、安装文件 payload 和 manifest 绑定；任一失败拒绝 entry point，且新 assurance 不得解除 schema/semantic/local-protocol pause。

`test_only/experimental` 仍必须通过可复现 assurance，但可以没有 publisher attestation且绝不因此获得 Supported/GA 身份。`supported/ga` 缺 attestation、使用已撤销/过期 key，或仅有自洽 `RECORD` 时一律 `adapter_not_distributable`。攻击测试必须修改 code、manifest、fixture、report、sidecar 与 `RECORD` 并重算所有公开摘要：只要无法产生受信任签名就不能加载；另覆盖错误 signer、key 轮换/撤销、bundle 回滚、版本降级和跨包重放。同一源码/lock/backend 连续构建两次必须得到相同 payload/assurance；构建日志只保存工具版本和 digest，不保存 fixture 机密内容。

#### 8.3.0 `aq-assurance-v1` 唯一字节 recipe

wheel ZIP central directory 是唯一 entry 枚举源。entry path 必须是 NFC UTF-8 POSIX relative path，长度 `1..240` bytes，禁止 leading `/`、trailing `/`、空 segment、`.`、`..`、反斜线、NUL/控制字符；原始名或 NFC 后名字重复均拒绝。ZIP encrypted/data-descriptor ambiguity、multi-disk、ZIP64 size 超出 `aq-bounds-v1`、device/FIFO/socket/directory/symlink/hardlink-like entry 全部拒绝。Unix mode 从 `external_attr >> 16` 读取，只允许 regular file `0100644` 或 `0100755`；没有可信 Unix mode 也拒绝。排序一律按 NFC path 的 UTF-8 bytes。

Provider wheel 的 manifest carrier 恰为一个根路径 `agent_quota_adapter/adapter-manifest-v1.json`；其他路径不得承载 `schema="aq-adapter-manifest-v1"`。assurance sidecar 恰为一个根路径 `agent-quota-assurance.json`；`*.dist-info/RECORD` 恰为一个且与 distribution canonical name/version 匹配。多 carrier、缺 carrier、重名、symlink carrier 或 sidecar 均拒绝。除 sidecar 和 RECORD 外，所有 regular entry 都进入闭包，不允许 verifier 自选忽略文件。

每个 entry object 恰含 `{"path":"<NFC relative path>","mode":"0644|0755","size":0,"sha256":"<64 lowercase hex>"}`。`size` 是 uncompressed bytes，范围 `0..1048576`；content 是原始 uncompressed bytes，唯一例外是 manifest：解析时拒绝 duplicate/unknown/float/non-NFC，把 `release_assurance_id` 投影为 JSON null，再以 `aq-jcs-nfc-v1` 编码。entry array 按 path UTF-8 bytes 排序。`adapter_payload_digest=SHA256(b"agent-quota:adapter-payload:v1\x00" + JCS(entry_array))`。

sidecar schema 为 `aq-assurance-envelope-v1`，顶层恰含 `schema/payload`；payload 恰含 `recipe,distribution_name,distribution_version,manifest_path,manifest_digest,entries,adapter_payload_digest,fixture_digests,schema_contract_test_report_digest,build_proof_digest,release_assurance_id,assurance_payload_digest`。`recipe="aq-assurance-v1"`；distribution name 使用 PEP 503 lowercase/hyphen canonical form，version 使用 canonical PEP 440；manifest digest 是投影后 JCS bytes SHA-256；fixture digests 是 `{fixture_id,sha256}` 唯一数组并按 fixture ID UTF-8 bytes 排序；所有 digest 是 lowercase 64 hex。`entries` 是上述完整闭包但不含 sidecar/RECORD。未知字段拒绝。

计算时先把 payload 的 `release_assurance_id` 与 `assurance_payload_digest` 都投影为 JSON null 得到 `assurance_core`；`assurance_payload_bytes=b"agent-quota:assurance:v1\x00" + aq-jcs-nfc-v1(assurance_core)`。最终两个字段都填 `SHA256(assurance_payload_bytes)` lowercase hex；validator 必须重新投影后验证，禁止对最终 payload 自引用 hash。manifest projection 始终把其中的 `release_assurance_id` 置 null。任何 path/mode/size/content/manifest/fixture/report/build proof bit 改变都失败。两套独立实现必须对 normal、字段重排、Unicode、duplicate path、symlink、mode bit、multi-carrier、sidecar 改动产生相同 bytes/digest/accept-reject。

#### 8.3.1 字节级 attestation 与 trust bundle

两种文件只使用 `aq-jcs-nfc-v1`：输入必须是无 BOM 的 UTF-8 JSON，拒绝重复/未知字段、float、NaN/Infinity 和非 NFC 字符串，再按 RFC 8785 JCS 产生唯一 bytes；digest 为小写 64 位 SHA-256 hex。时间只允许 UTC 秒精度 `YYYY-MM-DDTHH:MM:SSZ`，有效边界为 `issued_at <= verification_time < expires_at`。算法只允许 Ed25519；公钥为原始 32 bytes，`publisher_key_id="aqpk_" + SHA256(public_key_bytes)`，签名为原始 64 bytes 的无 padding base64url。

detached 文件名固定为 `wheel_filename + ".aqra.json"`，schema 为 `aq-release-attestation-envelope-v1`。顶层与所有嵌套对象均 `extra=forbid`，唯一可生成结构为：

```json
{
  "schema": "aq-release-attestation-envelope-v1",
  "payload": {
    "recipe": "aq-release-attestation-v1",
    "attestation_id": "aqra_<base64url-no-padding-128-bit>",
    "attestation_sequence": 1,
    "distribution_name": "<pep503-canonical>",
    "distribution_version": "<pep440-canonical>",
    "wheel_filename": "<basename-only>",
    "wheel_sha256": "<64-lowercase-hex>",
    "adapter_payload_digest": "<64-lowercase-hex>",
    "release_assurance_id": "<64-lowercase-hex>",
    "assurance_envelope_sha256": "<64-lowercase-hex>",
    "schema_contract_test_report_sha256": "<64-lowercase-hex>",
    "build_proof_sha256": "<64-lowercase-hex>",
    "issued_at": "YYYY-MM-DDTHH:MM:SSZ",
    "expires_at": "YYYY-MM-DDTHH:MM:SSZ"
  },
  "signatures": [
    {"key_id": "aqpk_<64-lowercase-hex>", "algorithm": "Ed25519", "signature": "<base64url-no-padding-64-raw-bytes>"}
  ]
}
```

`attestation_id` 必须与 wheel manifest 的 `release_attestation_id` 相等。`attestation_sequence` 是该 `(distribution_name, publisher binding)` 下 `1..2^63-1` 的严格递增数，InstallationRegistry 原子保存 floor。`wheel_filename` 必须与实际 basename 及其内部 distribution/version/tag 一致；`wheel_sha256` 是最终 raw wheel bytes，`adapter_payload_digest/release_assurance_id` 必须与重算的 assurance payload 一致，`assurance_envelope_sha256` 是严格解析后 `aq-jcs-nfc-v1` sidecar bytes，report/build proof digest 必须同时等于 assurance 封闭的对应 digest。时间满足 `issued_at < expires_at` 与本节已定义的验证边界。

`signatures` 非空，按 `key_id` UTF-8 bytes 排序且唯一；每个 key 都必须在当前 bundle 中为未撤销、在有效期内、purpose=`release_attestation` 且精确绑定该 distribution 的已知 key。未知/重复/错 purpose/错 distribution key 不得作为“额外签名”忽略，整个 envelope 拒绝。有效不同 key 数必须达到 distribution binding 的 `release_threshold`。签名字节唯一为 `b"agent-quota:release-attestation:v1\x00" + aq-jcs-nfc-v1(payload)`。数组重排在严格 parser 阶段因非 canonical order 被拒绝；JSON 对象字段顺序经 JCS 可不同。删除/重命名字段、改包/版本/文件名/digest/time/sequence、降级重放与附加未知字段都有唯一 reject verdict。

trust bundle 文件名固定为 `agent-quota-trust-bundle-v1.json`，schema 为 `aq-trust-bundle-envelope-v1`，顶层恰含 `schema/signed/signatures`。`signed` 恰含 `recipe="aq-trust-bundle-v1"`、正整数 `bundle_sequence`、前一 bundle canonical SHA-256（初始为 null）、根 threshold、根/发布 key（raw public key、用途、有效期）、精确 distribution→publisher 绑定和撤销条目；所有数组按 ID UTF-8 bytes 排序且 ID 唯一。bundle 签名字节为 `b"agent-quota:trust-bundle:v1\x00" + aq-jcs-nfc-v1(signed)`；更新必须由**前一已信任 bundle** 中至少 threshold 个不同、当时有效且未撤销的 root key 签名，新 bundle 自带的新 root 不能授权自身。`bundle_sequence` 必须严格增加，previous digest 必须相等，InstallationRegistry 的最大 sequence 是回滚地板。未知 version/algorithm/field、阈值不足、时间边界、撤销或旧 sequence 全部 fail closed。两套独立实现必须用 golden bytes/digest/signature 互验。

key purpose 是封闭枚举 `root|release_attestation|install_plan`。release attestation 只能由 `release_attestation` key 签，安装计划只能由 `install_plan` key 签；distribution binding 恰含 `distribution_name,release_key_ids,release_threshold,install_key_ids,install_threshold,allowed_meta_distribution,allowed_extras`，只登记允许的 package 与 meta distribution/extras target，目的不可互换。撤销项恰含 `key_id,not_before,reason_code`，验证时间达到 `not_before` 即拒绝相应用途。

##### 8.3.1.1 installer genesis anchor 与离线信任链

`agent-quota-installer` 必须在**其独立构建的 wheel 内**编译不可由 release directory 覆盖的 `InstallerGenesisAnchorV1`：

```python
class InstallerGenesisAnchorV1:
    schema: Literal["aq-installer-genesis-anchor-v1"]
    genesis_bundle_sequence: Literal[1]
    genesis_bundle_sha256: LowerHexSha256
    root_threshold: UInt16Count
    root_keys: tuple[TrustRootPublicKey, ...]  # key_id UTF-8 bytes 排序、唯一
    max_chain_length: Literal[32]
```

安装器 wheel 的 raw SHA-256 由用户先按独立发布渠道取得的 `bootstrap.lock` 核对；因此该内嵌 root set 与 genesis bundle digest 在目标 core/CLI 存在之前已被独立核验。目标 core、CLI、Provider、release directory 中自带的 bundle 或 plan 都不得作为自己的 genesis anchor。

release directory 的 `agent-quota-trust-bundle-chain-v1.json` 顶层恰含 `schema="aq-trust-bundle-chain-envelope-v1"` 与 `bundles`；`bundles` 是 `1..32` 个完整 `aq-trust-bundle-envelope-v1` 的数组，严格按 sequence 升序。全新安装的第一个 bundle 必须为 sequence 1，其 canonical SHA-256 恰等于内嵌 `genesis_bundle_sha256`，且 root set/threshold 恰等于 anchor；已安装升级的第一个 bundle 必须与 InstallationRegistry 保存的当前完整 trusted bundle digest/sequence 恰好相等。之后每个 bundle 都必须 sequence 恰好 `previous+1`、`previous_bundle_sha256` 恰好匹配，并由**前一 bundle** 的当时有效未撤销 root 达到旧 threshold 签名。新 root 只能在这一步被前一 root set 授权，不能签自己或补足旧 threshold。

链末 bundle 必须与目录的 `agent-quota-trust-bundle-v1.json` 逐字节 canonical digest 相等，并且与 install plan 的 `trust_bundle_sequence` 相等。全新安装允许 target sequence `>=1`；升级只允许 target sequence 严格大于 registry floor，仅修复安装可在 sequence/digest 都恰好相同时重验；低 sequence、同 sequence 不同 digest、缺中间 bundle、链超 32、自签 genesis、无旧 threshold 授权的 root 替换全部拒绝。跨越超过 32 个 sequence 的旧安装必须先安装受信任中间版，不得放宽链上限。成功后 registry 原子保存链末完整 bundle、digest 和 sequence floor。

#### 8.3.2 可执行的生产安装信任流程

Supported/GA 的唯一生产安装入口是独立发行的 `agent-quota-installer`，普通 `pip install agent-quota[...]` 不承诺解包前信任。`aq-production-release-directory-v1` 只允许根目录 regular files，不允许子目录、symlink 或重复/NFC 冲突 basename。其封闭 control set 恰为：

```text
bootstrap.lock
<bootstrap.lock 恰好引用的唯一 agent-quota-installer wheel basename>
verified-install-plan-v1.json
agent-quota-trust-bundle-v1.json
agent-quota-trust-bundle-chain-v1.json
```

除这 5 个 control file 外，目录中恰好是 signed plan `files` 列出的全部目标 wheel 与 Agent Quota attestation sidecar。**不接受输入的第三方 lock；**第三方 wheel 与 hash 已被 plan 签名，安装器验证闭包后只在 staging 目录生成 `verified-pip.lock`，它绝不是 release directory 输入。因此目录等式唯一为 `regular_basenames(D) = CONTROL_FILES ∪ set(plan.signed.files[*].filename)` 且两集不相交；增、删、替换任一 control/target 都有唯一 reject verdict。干净环境逐字执行：

```bash
python -m pip install --no-index --no-deps --require-hashes -r ./release/bootstrap.lock --find-links ./release
agent-quota-install --release-dir ./release --extras deepseek,codex --python "$(command -v python)"
```

第一条由 pip 的 `--require-hashes` 在安装 bootstrap 前验证其 wheel raw bytes；用户必须先从独立发布渠道核对 `bootstrap.lock` 自身 SHA-256。第二条只执行“从内嵌 genesis/registry floor 验证离线 bundle chain → 验证 bundle sequence/threshold/revocation → 验证第 8.3.2.1 节 install plan → 验证目录等式 → 流式 hash 所有 target → 验证 Agent Quota wheel attestation/raw digest/payload → 生成 `verified-pip.lock` → 调用 `pip --no-index --only-binary=:all: --require-hashes` 安装 staging directory → 安装后重验 RECORD/payload”的状态机。staging 只接受 plan 闭包中的 wheel；sidecar 只由 installer verifier 读取不交给 pip。任一 sdist、缺 sidecar、依赖替换、未知文件或 hash 不符都在 pip 安装任何目标代码前拒绝并删除 staging。installer 自身无 Provider/import hook，且在验证完成前不导入、解包、执行 metadata hook 或运行 staged distribution。

##### 8.3.2.1 `aq-verified-install-plan-envelope-v1`

文件名仍固定 `verified-install-plan-v1.json`，内容是 Ed25519 envelope，顶层恰含 `schema,signed,signatures`；`schema="aq-verified-install-plan-envelope-v1"`。`signed` 恰含 `recipe="aq-verified-install-plan-v1"`、`plan_sequence`、`issued_at`、`expires_at`、`trust_bundle_sequence`、`publisher_key_id`、`meta_distribution`、`requested_extras`、`target`、`files`、`closure_sha256`。sequence 都是 `1..2^63-1`；`meta_distribution={name,version}`；`target={python_implementation,python_version,python_abi,platform_tag}`；每个 file 恰含 `filename,role,distribution_name,distribution_version,size,sha256`。

字符串均 NFC ASCII 子集：distribution 用 PEP 503 canonical name，version 用 canonical PEP 440，extra regex `^[a-z0-9]+(?:-[a-z0-9]+)*$`，ABI/platform tag regex `^[A-Za-z0-9_]+(?:[.-][A-Za-z0-9_]+)*$`。requested extras 唯一并按 UTF-8 bytes 排序，必须与 CLI 请求集合完全相等。`files` 按 filename UTF-8 bytes 排序且文件名唯一，basename-only、长度 `1..200`、禁止分隔符，单文件 size `1..268435456` bytes、闭包总 size `<=1073741824` bytes；role 只允许 `agent_quota_wheel|third_party_wheel|release_attestation_sidecar`。每个 wheel 必须有 name/version/size/SHA-256，每个 Agent Quota wheel 恰有对应 sidecar；所有第三方传递依赖、core/cli/meta/provider 和 extras 条件依赖都必须恰好出现，禁止额外文件。`closure_sha256=SHA256(b"agent-quota:install-closure:v1\x00"+JCS({meta_distribution,requested_extras,target,files}))`。

签名字节为 `b"agent-quota:verified-install-plan:v1\x00" + aq-jcs-nfc-v1(signed)`。签名项恰含 `key_id,algorithm="Ed25519",signature`，按 key ID 排序且唯一，只能使用当前 trust bundle 中 purpose=`install_plan`、绑定该 meta distribution、在 `issued_at <= verification_time < expires_at` 有效且未撤销的已知 key；未知/错 purpose/错 binding key 使整个 envelope 拒绝，不能忽略，有效不同 key 数必须达到 `install_threshold`。`trust_bundle_sequence` 必须等于离线链末 bundle sequence且不低于 registry floor。`plan_sequence` 必须严格大于该 installation 已接受的 sequence，成功安装后与 plan digest 原子写入 registry；过期、回滚、错误 signer/target/extras/package/version/文件/sidecar/大小/hash/闭包均拒绝。control set 只使用第 8.3.2 节的 5 个 basename；严格等式是 `regular_basenames(D) - CONTROL_FILES = set(files[*].filename)` 且 `regular_basenames(D) ∩ CONTROL_FILES = CONTROL_FILES`，symlink/duplicate/子目录均拒绝。

验证顺序固定为：按 `aq-bounds-v1` 先限制 control/plan/bundle/chain raw bytes 与 JSON 深度/节点/字符串 → 严格解析 → 从 genesis/registry floor 验 bundle chain → 验 plan signature/sequence/time/revocation/target/extras → 以 no-follow 句柄枚举并验证 `regular_basenames(D) - CONTROL_FILES = set(files[*].filename)` → 流式 hash/size → 验 Agent Quota release attestation 与 assurance → 在 staging 生成 hash lock → 才允许 pip 读取 wheel。替换 plan、bundle/chain、wheel、extras、Python ABI/platform、字段顺序/Unicode、signer/sequence，或增删任一 control/target 的 golden fixture 必须在任何目标代码执行前拒绝；两套独立 installer 对同一 golden envelope 产生相同 JCS/signature/closure verdict。

源码审阅路径必须使用**另一个不传给生产 installer 的 source-review directory**，其可含签名 hash 的 `sdist-source-review.lock` 并执行 `python -m pip install --no-binary=:all: --require-hashes -r ./source-review/sdist-source-review.lock`。该命令明确会信任并执行 build backend，只能在隔离审阅环境使用，产物没有原发布者 wheel attestation，Provider 稳定 `adapter_not_distributable`。生产 release directory 一旦出现 sdist 或 source-review lock，即因目录等式失败，不能作为可忽略附件。恶意 import/build hook 验收分别证明：生产 installer 因禁止 sdist/未验证 import 而在执行前拒绝；源码审阅路径不被宣传为生产信任边界。

### 8.4 Codex protocol schema bundle recipe

Codex 的 `protocol_schema_hash` 唯一使用 `aq-codex-schema-bundle-v1`。从已按 install ID/no-follow 验证的 Codex 可执行文件读取规范 `codex --version`，执行 `AQ_SCHEMA_DIR="$(mktemp -d)"` 后执行**不带** `--experimental` 的固定命令 `codex app-server generate-json-schema --out "$AQ_SCHEMA_DIR"`；非零退出、额外模式或输出目录原先非空均失败。descriptor roots 精确为 `codex_app_server_protocol.v2.schemas.json` 与 `v1/InitializeResponse.json`，按相对路径 bytes 排序；wire reference 分别固定到前者的 `/definitions/GetAccountRateLimitsResponse` 与后者整份文档。任一引用文件缺失即拒绝，任一引用 byte 改变必须改变 hash；未被 wire reference 使用的生成文件忽略且不影响 hash。运行时只能从已哈希 roots 以固定目录 `openat` + per-segment no-follow 打开文件。

`aq-codex-cli-v1` 的版本 stdout hard limit 为 64 bytes，退出码必须为 0，stderr 必须为空；只接受恰好一行 ASCII `codex-cli SP MAJOR.MINOR.PATCH`，行尾可无换行、LF 或 CRLF。`MAJOR|MINOR|PATCH = 0 | [1-9][0-9]{0,5}`；禁止前导/尾随空白、多行、空行、非 UTF-8/ASCII、前导零、缺 segment、第四 segment、pre-release 和 build metadata。normalize 的唯一输出是去前缀后的 `MAJOR.MINOR.PATCH`；比较先解析成三个 `0..999999` integer，再按 `(major,minor,patch)` lexicographic compare，绝不比较字符串或接受宽松 SemVer。supported range 只允许 canonical `>=A.B.C,<=X.Y.Z`，先证明 min<=max。

golden vectors：`codex-cli 0.142.5\n → 0.142.5`，CRLF 同结果；`0.142.5 < 0.143.0 < 1.0.0`；`00.142.5`、`0.142`、`0.142.5-beta.1`、`0.142.5+build`、两行输出、65 bytes、非 ASCII 和非零退出全部 `unverified_version`。构建器、probe、range validator 和 bundle hash 必须调用同一个函数。

bundle 描述符固定为：

```python
bundle_descriptor = {
  "recipe": "aq-codex-schema-bundle-v1",
  "generator_mode": "stable",
  "codex_version": normalize_codex_version(codex_version_stdout),
  "roots": generated_descriptor_roots_with_sha256(
      ["codex_app_server_protocol.v2.schemas.json", "v1/InitializeResponse.json"]
  ),
  "rpc_allowlist": ["account/rateLimits/read", "initialize", "initialized"],
  "argv_template": ["<verified-executable-install-id>", "app-server", "--stdio"],
  "wire_contract_recipe": "aq-codex-wire-v1",
  "wire_contract_sha256": sha256_hex(aq_jcs_nfc_v1(wire_contract_schema)),
  "notification_opt_out_methods": sorted_unique_utf8(
      extract_method_enums(root.definitions.ServerNotification)
  ),
  "error_code_map": [
    {"code": -32700, "category": "local_protocol_violation"},
    {"code": -32603, "category": "provider_error"},
    {"code": -32602, "category": "local_protocol_violation"},
    {"code": -32601, "category": "local_protocol_violation"},
    {"code": -32600, "category": "local_protocol_violation"},
    {"code": -32001, "category": "rate_limited"}
  ]
}
```

`wire_contract_schema` 是第 8.4.1 节的封闭 JSON Schema，不是实现自选的数据结构。`notification_opt_out_methods` 的提取算法只遍历 `ServerNotification.oneOf[*].properties.method.enum[*]`，每项必须为 NFC UTF-8 字符串，拒绝重复后按 UTF-8 bytes 排序；该**已解析的完整数组**进入 descriptor，因而官方 schema 新增/删除 notification 必定改变 bundle hash。`error_code_map` 按 signed integer 升序，code 唯一；未列 code 不得自选 category，只能 fail closed 为 `local_protocol_violation`。

`protocol_schema_hash = SHA256(aq-json-c14n-v1(bundle_descriptor))`。`rpc_allowlist` 的输入语义是集合：先拒绝重复，再按 UTF-8 bytes 排序后写入 descriptor；它不是调用序列。打乱源集合不改变 hash，增删任何 RPC、argv、wire schema、opt-out 列表或 error map 必须改变 hash。当前已决定不加入 `account/read`，Codex 保持 Experimental/incompatible。两台干净机器对相同 Codex 版本和 Adapter 版本必须得到同一 hash；改变 Codex 版本、根文件、根内容或任一上述合同都必须改变 hash。构建日志只记录命令模式、版本、根相对路径和 digest，不记录账户响应。该核验只生成 schema/比较字节，不启动任何账户 RPC。历史 `AQ-R10-001` 与 R19 marker 仅描述当时审计态；当前产品决策读取第 20 节。

#### 8.4.1 Codex JSON-RPC 连接状态机

每个 attempt 新建一个进程/连接。唯一 argv 是 `[registry.resolve_verified_executable(executable_install_id), "app-server", "--stdio"]`，`shell=False`，不得省略 `--stdio`、增加 `--experimental` 或使用 PATH。request ID 是 JSON integer，固定从 1 单调递增、范围 `1..2^31-1`、连接内不复用。`aq-codex-wire-v1` 的三个 client frame 按字段集恰好是：

```json
{"id":1,"method":"initialize","params":{"clientInfo":{"name":"agent_quota","title":"Agent Quota","version":"<canonical-adapter-semver>"},"capabilities":{"experimentalApi":false,"mcpServerOpenaiFormElicitation":false,"optOutNotificationMethods":["<resolved-sorted-complete-server-notification-method-set>"],"requestAttestation":false}}}
{"method":"initialized"}
{"id":2,"method":"account/rateLimits/read"}
```

角括号值在构建 manifest 时必须解析为单一字符串或完整字符串数组，不是发送到 wire 的占位符。`clientInfo.version` 恰等于已验证 Codex Adapter distribution 的 canonical SemVer。capabilities 不得缺字段或多字段；opt-out 必须等于 bundle descriptor 中的完整排序数组。唯一发送序列是 frame 1 → 收到 id=1 success → frame 2 → frame 3 → 收到 id=2 success/error。当前 blocker 解决前该序列不产生 verified identity，因此不能进入正式 fetch。历史 `AQ-R10-001` 仅为非规范性索引。

stdout 是 UTF-8、每行一个 JSON object 的 framed stream；CRLF/LF 都剥除为同一 frame，空行、BOM、非 object、duplicate JSON key、NaN/Infinity、超过 frame/total bytes 均为 `local_protocol_violation`。**官方 app-server 在 wire 上省略 JSON-RPC header，因此所有 client/server frame 的 `jsonrpc` 字段必须缺失；出现即拒绝。** success envelope 恰含 `{id,result}`，error envelope 恰含 `{id,error}`，二者不得带 `method`或额外顶层字段。initialize result 必须通过官方 `InitializeResponse`，rate-limit result 必须通过 `GetAccountRateLimitsResponse`；本专用 schema 在其外再收紧字段集、ID 和顺序。

同一时刻恰有一个 outstanding ID。response/error ID 必须为当前预期的 integer 1 或 2；string/null/bool/float ID、错误/重复/已完成/未来/orphan ID 全部拒绝，不能绑定到“下一行”。任何带 `method` 且无 id 的 server notification 都是违约：已知方法本应被 exact opt-out 抑制，未知方法未进入 bundle。任何带 `method` 和 id 的 server request 也立即终止连接，客户端不执行且不发送自选 response。

error 恰含 `code/message/data?`，额外字段拒绝；`code` 为 signed 32-bit integer，`message` 只做 `1..256` UTF-8 bytes/控制字符校验后立即丢弃，`data` 按 `aq-bounds-v1` 先限界再丢弃。id=1 的任何 error 均为 `local_protocol_violation`。id=2 只使用 bundle 内有限表：`-32001→rate_limited`、`-32603→provider_error`、`-32700|-32600|-32601|-32602→local_protocol_violation`；其他 code 统一 `local_protocol_violation`。没有官方稳定 code 证据时不得自造 `auth_error` 映射。

EOF 在 outstanding request 存在时是 `local_protocol_violation`。收到 id=2 的唯一 response 后关闭 stdin，检查已缓冲 stdout；任何非空 tail frame、第二 response 或 orphan 都使整批失败。随后在 transport policy 的剩余 execution/grace 内 TERM→KILL→reap；终止期间新 stdout 仍计入 total 并且任何完整 tail frame均拒绝。partial frame at EOF、超限 partial frame、stderr 任意 bytes、重复/错序/unknown frame 一律不产生 snapshot。

queue/handshake/request/execution/attempt/aggregate 使用同一个 monotonic budget object，stdin、单 frame、stdout total、stderr total 和 process count 使用同一个原子 counter state；不能每阶段重置。fake stdio golden cases覆盖 notification 前插、错/重复/unknown ID、error response、server request、EOF、partial/multiple/tail frame、CRLF 与 byte/deadline 恰好边界，且只接受阶段/schema/id 全匹配的唯一 response、orphan=0。

### 8.5 DeepSeek 响应语义

DeepSeek manifest 同时声明 `wallet-balances(kind=balance)` 与 `wallet-availability(kind=status)`。官方 `GET /user/balance` 的 `is_available` 必须为 boolean；`balance_infos` 必须有 1..2 项、currency 只允许 CNY/USD 且唯一。三个金额字段只接受第 8.0 节 `aq-decimal-38-18-v1`（ASCII `^(0|[1-9][0-9]{0,37})(\.[0-9]{1,18})?$`、总长/位数 hard bound），先长度与 regex 再用 Decimal 精确解析；每项必须满足 `total_balance == granted_balance + topped_up_balance`，不使用浮点容差。

| Provider 输入 | `wallet-balances` | `wallet-availability` | 整批结果 |
| --- | --- | --- | --- |
| 合法金额且 `is_available=true` | `fresh+ok+BalanceValue` | `fresh+ok+StatusValue(available)` | 提交；availability severity=`none` |
| 合法金额且 `is_available=false` | `fresh+ok+BalanceValue` | `fresh+ok+StatusValue(insufficient_balance)` | 提交；availability severity=`high`，不得渲染为“可正常调用” |
| 缺字段/错类型/未知币种/非法金额字符串 | 保留 LKG 时 `stale+schema_changed`，否则 `expired+schema_changed` | 同左 | 不覆盖任一 LKG/成功基线 |
| 空数组/重复币种/负数/金额列错位/组成关系不等 | 保留 LKG 时 `stale+semantic_suspect`，否则 `expired+semantic_suspect` | 同左 | 不覆盖任一 LKG/成功基线 |

同一 HTTP 响应的两个 capability 原子校验和提交，不允许只接受 `is_available` 或只接受金额。fixture 必须覆盖 true/false、CNY/USD 单币种与双币种、空/重复/未知币种、每个金额字段错列、非法数字和 `total != granted + topped_up`。

### 8.6 Codex rate-limit 唯一映射

MVP 只把 `GetAccountRateLimitsResponse.rateLimits` 这一官方声明为 backward-compatible 的顶层兼容表面映射为一个已由用户确认的 subscription subject，selector 固定为 `{source="compat-default"}`；Codex `SelectorSchema` 的 `source` 是 required string 且 enum 恰好为 `("compat-default",)`，`default` 或其他值必须在 offline config validate 阶段、零凭据/网络/子进程条件下拒绝。DeepSeek 的 `{source="default"}` 属于另一个 manifest schema，二者不得复用或互相 canonicalize。不从动态 `limitId/limitName` 生成 ID 或 label。该 Codex subject 恰好声明三个 capability：`rolling-primary(kind=window, unit=percent)`、`rolling-secondary(kind=window, unit=percent)` 与 `codex-rate-limit-status(kind=status, unit=None)`。

`rateLimitsByLimitId` 的 absent/null/value 处理也是封闭合同：字段缺失、`null` 或空对象都接受兼容表面；非空对象允许 1..16 个 bucket，但 MVP 仍只消费顶层 `rateLimits`。对象总深度不超过 8、总节点不超过 4096；每个 key 必须是 NFC、1..128 UTF-8 bytes、无控制/双向字符，每个 value 必须通过当前 stable schema 的完整 `RateLimitSnapshot` 类型/基数检查，其非空 `limitId` 必须与 map key 字节相等。全部 bucket 中必须**恰好一个**经 `aq-json-c14n-v1` 后与顶层 `rateLimits` 相等；零匹配或多个匹配都为 `unverified_version`。其余合法 bucket 验证后立即丢弃，绝不生成 subject/capability，也不得进入 ID、label、selector、配置、日志、差异、审计、指纹或投影。动态 key 只在有界内存比较，结构路径统一为 `<map-key>`；错型、超基数/深度、key/limitId 不一致或顶层不匹配均在 probe 阶段 fail closed。

窗口按以下唯一规则分别生成结果，因此也满足第 8 节“每个请求 key 恰好一条快照”：

| Codex 字段状态 | 对应 capability | 唯一映射 |
| --- | --- | --- |
| `primary`/`secondary` absent | 全部三项 | 结构失败，整批 `schema_changed`；不得把缺失解释为不适用或沿用另一窗口 |
| `primary`/`secondary` 为 `null` | 对应 `rolling-*` | `fresh + health=unsupported + status_code=not_applicable + value=None`，不能漏项、复制另一窗口或保留旧成功冒充本次结果 |
| `primary`/`secondary` 为对象 | 对应 `rolling-*` | `usedPercent/windowDurationMins/resetsAt` 三个成员都必须存在；`usedPercent` 是整数 `0..100` 且不得为 null，duration 为 `null` 或正整数，reset 为 `null` 或非负 Unix 秒。转换为 `WindowValue`；reset 为值时 UTC `known`，为 null 时 `not_provided` |
| `rateLimitReachedType` absent | 全部三项 | 结构失败，整批 `schema_changed`；不得默认为 available |
| `rateLimitReachedType=null` | `codex-rate-limit-status` | `fresh+ok+StatusValue(available)`，severity=`none` |
| `rate_limit_reached` | `codex-rate-limit-status` | `fresh+ok+StatusValue(rate_limit_reached)`，severity=`high` |
| owner/member credits depleted | `codex-rate-limit-status` | `fresh+ok+StatusValue(credits_depleted)`，severity=`critical` |
| owner/member usage limit reached | `codex-rate-limit-status` | `fresh+ok+StatusValue(usage_limit_reached)`，severity=`critical` |
| reached value 为未知枚举 | 全部三项 | 结构失败，整批 `schema_changed`，不得映射为 unknown/available |

顶层 `rateLimits` 必须存在且为对象；缺失/null/错型都是结构失败。其 `limitId` absent/null 均接受，value 只允许 `codex`；`limitName` absent/null/value 都不参与身份、selector 或展示，value 仅做 UTF-8/长度/控制字符上限校验后丢弃。`planType` absent/null/`unknown`/未登记 value 都丢弃，只有 manifest `allowed_plan_codes` 中的已知 value 才生成 `SubjectMetadataObservation(field="plan_code")` 并进入第 8 节确认/更新状态机。未声明为 capability 的 `credits`、`individualLimit`、`rateLimitResetCredits` 允许 absent/null/value 三态，但 value 只做当前 schema 的类型/深度/基数上限校验后丢弃；这不扩大 RPC allowlist，也绝不调用 consume。

任一结构失败都由 Adapter 返回覆盖完整三 key 的 batch/item failure；core 再按当前 generation 是否有 LKG 原子合成 `stale/expired+schema_changed`，不得部分提交或默认为可用。fixture 必须覆盖空对象、单窗口、两个窗口/member/reached 的 absent/null/value、bucket map absent/null/空、合法 1/2/16 bucket 且恰一匹配、零/多匹配、key/limitId 不一致、17 bucket、超深/错型与动态 key 脱敏；合法多 bucket 只生成顶层三项 capability，其他 bucket 的访问/持久化/输出计数为 0。

## 9. 缓存与刷新

- 缓存新鲜度没有实现自选区间或隐式默认值。每个可执行 capability 必须引用一个 `FreshnessPolicy`；`provider_success_ttl_seconds/provider_unavailable_ttl_seconds` 是 `1..86400` 的精确整数并参与 query generation。DeepSeek `wallet-balances/wallet-availability` 只引用 `DEEPSEEK_FRESHNESS_SECONDS`，OpenRouter 六项只引用 `OPENROUTER_FRESHNESS_SECONDS`；Codex 历史 parser fixture 可引用 `CODEX_FRESHNESS_SECONDS`，但 parser-only 不产生 observation/Snapshot/LKG/cache。Fake/后续 capability 也必须在 manifest 给出单值。
- Adapter 的 success、available/reached/balance/window/counter 以及 Provider 观察到的 `not_applicable/unsupported/not_entitled` 全部使用有限 TTL。只有 core 在 offline manifest 求值中产生的 `manifest_static` `not_applicable|unsupported`，且 code 命中 policy 的 `static_permanent_codes`，才允许 `expires_at=None`；Adapter 声称 `manifest_static` 整批拒绝。`evaluated_at >= expires_at` 即不再 fresh。
- 手动刷新绕过普通缓存，但不绕过 endpoint group 引用的 `BudgetPolicy`。具体 floor/hour 数值只读 core-safety artifact；上游 `Retry-After` 只可收紧。group/cohort union 的限制状态必须跨进程重启持久化。
- 纯本地 `official_cli`/`local-stdio` 不继承 HTTP 的 30 秒默认值；其地板由受审查 manifest 明示（可为 0），但仍受 TTL、singleflight、并发上限和官方协议返回的限流约束。`estimated`/本地 fixture 不得误计为 Provider 网络请求。
- 全量刷新并发执行，且只能使用第 9.0.1 节固定的跨进程全局/Provider semaphore、bounded queue、公平/取消/部分结果合同；v1 `max_attempts=1`。
- core 为每个已启用 capability 计算 `query_contract_generation = HMAC(active_key_for_consumer("query-contract-generation-v1"), canonical(adapter_id, adapter_api_version, adapter_version, protocol_contract, protocol_schema_hash, release_assurance_id, release_attestation_id, endpoint_profile, network_policy_digest, endpoint_spec_digest, deadline_policy_digest, identity_source_contract_digest, provider_identity_domain_digest, endpoint_budget_group_digest, normalized_subject_selector, confirmed_plan_code, subject_metadata_generation, capability_id, capability kind, label_key, canonical unit, allowed currencies/status codes, scale, semantic_contract_id, freshness_policy_digest, structure_contract_digest, display schema digests))`。规范序列化使用固定字段顺序、UTF-8/NFC 和 manifest 定义的 selector canonicalizer；不得包含凭据原文。Capability 缓存/LKG 键为 `(adapter_id, principal_id, subject_id, capability_id, cache_identity, query_contract_generation)`。
- endpoint/network policy、selector、capability kind/label/unit/currency/status/scale、semantic/display contract、Adapter/API version、ProtocolContract、schema hash、release assurance 或发行 attestation 任一变化时，必须使用第 10.2 节 migration journal 切换唯一 active generation并删除旧 generation 的快照、LKG、指纹、语义基线和失败状态。应用在 recovery 完成前不提供查询；完成后旧 generation 永远不可作为 fresh/stale/expired 或 canary 基线返回。迁移审计使用 `RET-MIGRATION-AUDIT`。
- 网络 singleflight 键至少为 `(adapter_id, principal_id, cache_identity, query_contract_generation, endpoint_id, request_kind, normalized_subject_selector, normalized_capability_selector)`，保证不同 principal/登录态/查询语义不共享结果。限流键与缓存隔离键分开：请求地板使用 `(adapter_id, rate_limit_cohort, endpoint_id, request_kind, normalized selectors)`，小时上限使用 `(adapter_id, rate_limit_cohort, endpoint_id)`。只有完整请求相同才可合并；一个请求返回多项能力时，再分别写入 capability 缓存。
- `rate_limit_cohort` 不可由配置或用户输入指定。core 根据 Credential Source 的受保护身份材料或官方协议验证的账户身份生成；多个 principal 共享同一上游身份时必须命中同一 cohort。无法验证稳定上游身份时，使用该 Adapter/endpoint 的部署级保守 cohort，不得退回 principal 级预算。
- 连接池不得携带跨 principal 的默认认证头、Cookie 或“当前账户”可变状态；认证材料按请求注入，需要会话状态时按 `(principal_id, cache_identity, endpoint_profile)` 隔离实例。
- 查询失败时 Adapter 只返回 `FetchFailure/FetchBatchFailure`；core 在完整 key 校验后原子读取当前 generation LKG，有值合成 `stale`、无值合成 `expired`，并展示上次成功时间。Adapter 不得读取缓存或自行拼 LKG。
- 失败计数、暂停表面、Scheduler/on-demand 的允许动作和唯一恢复事件只以 [Provider 契约第 9.4 节](provider-contract.md#94-连续失败与恢复) 为规范源；摘要不得改写为统一的“三次失败后全部暂停”。

### 9.0 跨进程 rate ledger 与执行并发

所有 writer/reservation/queue/slot/migration/temp-claim lease 的时钟、duration、renew-at、max lifetime、expiry/takeover 与 parent/transport deadline 只执行 [`lease-policy-v1`](contracts/lease-policy-v1.json) 中唯一 formula ID 的 typed AST；本节只引用 policy ID，不复述自然语言公式。持久到期只在 SQLite `BEGIN IMMEDIATE` 的 DB UTC sample比较，Provider执行授权只比较同进程 monotonic。唯一允许的域转换是 artifact 的 `monotonic-remaining-to-db-utc-v1` sample pair，用于把不超过 monotonic parent/transport的剩余量封顶到持久reservation expiry；crash grace只在转换后的持久清理边界外加，绝不延长 Provider I/O deadline。类型/clock域不匹配、DB/monotonic回退或 checked arithmetic overflow按 artifact固定 verdict拒绝；host不得自选公式。

`RET-RATE-LEDGER` 唯一 backend 是同一 data root 的主 SQLite，不允许进程内 counter、单独 JSON 或每 principal 数据库。SQLite 使用 WAL、`PRAGMA synchronous=FULL`；所有 check-and-reserve/状态转换都使用数据库 UTC 与 `BEGIN IMMEDIATE`。`rate_reservation` 至少含：`reservation_id`、group umbrella floor/hour digest、可空 verified floor/hour digest、idempotency binding digest、`request_kind`、`endpoint_budget_group_id`、`cohort_resolution=unknown|verified`、`state=reserved|committed|outcome_unknown`、`reserved_at`、`reservation_expires_at`、`effective_at`、`blocked_until`、owner、lease policy ID、lease expiry、fencing token、created/updated；record digest 只使用 consumer ID `rate-ledger-record-digest-v1`，cohort digest 只使用 `rate-limit-cohort-prf-v1`，不保存 selector/cohort 原文。唯一约束把同一幂等 binding 与逻辑 request 绑定一个 reservation；partial unique indices分别约束 active group umbrella floor与 active verified floor，但都指向同一 reservation ID。

请求地板 key 为既有完整 `(adapter_id,rate_limit_cohort,endpoint_id,request_kind,normalized selectors)`，小时 key 为 `(adapter_id,rate_limit_cohort,endpoint_id)`。事务固定执行：

1. 获取/续租 singleton `rate_ledger_writer`，接管必须在 `now >= old_lease_expires_at` 后令 `fencing_token+1`。只有新 fence 持有者可在同一事务删除同时满足 `state=reserved AND now >= reservation_expires_at AND old_owner_lease_expired` 的旧 fence 行；`committed|outcome_unknown` 永不因 owner lease 到期释放。
2. 以 DB UTC 计算三个独立 blocker：(a) floor 的最近 `committed|outcome_unknown` effective time 加 floor；(b) 同 floor key 任何未过期 `reserved` 的 `reservation_expires_at`；(c) 小时窗口 `(now-3600, now]` 内 `reserved|committed|outcome_unknown` 数量和任何 `blocked_until`。`reserved` 同时占 floor 和小时预算。所有边界统一为 `now >= boundary` 时该 blocker 到期，`now < boundary` 才拒绝。
3. retry-after 聚合只执行 [`core-safety-contract-v1.json`](contracts/core-safety-contract-v1.json) 的 `budget_ledger_contract.retry_after_aggregation`。同一 `BEGIN IMMEDIATE`、同一个 DB UTC sample 先取 group umbrella 与 verified cohort union 的全部 boundary；`now < boundary` 才 active，已到期项不计。集合非空时不插入并生成 `disposition=deferred/failure_code=refresh_deferred`，`retry_after_seconds=clamp(max(active_boundaries)-now,0,86_400)`；集合为空时为 `None` 并允许 reserve。结果与输入顺序、primary reason、进程调度无关；partial unique 冲突与显式 blocker 得到同一 per-request verdict，两个 bucket 必须一起成功或一起回滚。
4. 获得执行 slot 后、任何 Provider byte/子进程业务 RPC 可能发生前，在第二个 `BEGIN IMMEDIATE` 中验证同一 fence/lease并把 `reserved→committed`，以 DB UTC 固定 `effective_at`。commit 成功后才发送；因此 crash 在该 commit 之前可证明未调用并在 lease 到期后释放 reservation，commit 之后即使尚未真正 send 也保守计数。
5. 收到确定结果后 reservation 保持 `committed` 直到 floor/hour窗口和 `RET-RATE-LEDGER` 都允许清理；429/Provider Retry-After 同一事务把 key 的 `blocked_until=max(existing,normalized_retry_after_deadline,policy_deadline)`。v1 无请求内重试，任何 HTTP/stdio attempt 恰计一次。
6. 进程在 `committed` 后、幂等结果原子提交前崩溃，恢复者把行改为 `outcome_unknown`，相同幂等键永不再调用 Provider；该行继续同时占 floor/hour预算。旧 fence 不得释放/改写。Provider 已返回但 cache commit 崩溃也同样 unknown，不因没有 snapshot 返还预算。

以上事务同样服务 doctor/discover/refresh。`request_kind` 只取 operation artifact 的封闭值并进入 floor key；对 identity bootstrap，reserve/commit 先使用 endpoint budget group 的 deployment conservative digest。response 验证 stable evidence 后，同一事务在原行填入 verified floor/hour digest并建立二者到同一 reservation ID的索引；floor/hour查询按所用 cohort读取相应索引，行只计一次 attempt。conservative索引在 `RET-RATE-LEDGER` 前不删除，因此并发未知身份仍被阻塞；不得把 rebind实现为删除旧行、插入新 attempt或发送第二次业务 RPC。

singleflight 只有 leader 建 reservation/调用 Provider，joiner 不计数。排队超时或取消只在 `state=reserved`、owner/fence 仍匹配且 Provider byte 计数为 0 时由同一事务删除该行并释放 unique floor slot；删除失败则保守等待 lease takeover，不能自选重发。owner crash 在 commit 前只按第 1 步旧 lease+新 fence 清理；commit 后的取消、timeout、network/5xx/429、进程 kill均计数并在不能原子完成幂等结果时转 `outcome_unknown`。对象 inactive 后 reservation 仍按 `RET-RATE-LEDGER` 保留；复制 principal/binding/进程因 cohort/key 相同不增加预算。双进程虚拟时钟测试还固定 `now=100`、active boundary=`110/160`：`now=110` 仍为 deferred，`now=160` 满足 `now >= boundary` 后才允许新 reservation；并覆盖同 floor 并发、partial unique 冲突、排队取消/timeout、owner crash/lease 接管、每个 commit/send/cache 点 kill，证明总调用不超 floor/hour、unknown 不释放、expired reserved 不永久死锁。

#### 9.0.1 跨进程 semaphore、队列与单次 attempt

v1 固定 `GlobalConcurrency=4`、`PendingTaskLimit=32`、`MaxAttempts=1`；Provider concurrency 是 manifest `1..4` 且不得大于 global。SQLite `refresh_queue` 分配单调 ticket，`execution_slot` 以 lease/fence 表示 4 个全局 slot及每 Provider计数，因此 CLI/daemon/SchedulerHost 跨进程共享同一上限。pending 总数达到 32 时，对已形成的完整 request生成 `disposition=capacity/failure_code=capacity_exhausted`，不得先创建无界 coroutine/task。

公平规则是：同 Provider 严格 ticket FIFO；全局最老且其 Provider 尚有 slot 的 eligible ticket 先运行，Provider 已满时允许其他 Provider 的最老 ticket work-conserving 前进，但不得让后来的同 Provider ticket插队。queue lease、slot lease 和取消均在 `BEGIN IMMEDIATE` 更新；owner crash 后只在 lease 到期且 fence 增大时回收。调用者取消：pending ticket 原子删除；running 但未 rate commit 时释放 slot/reservation；rate commit 后取消仍计预算并以安全部分结果结束。

`refresh(all)` 在授权入口建立一个 parent monotonic deadline：所有 queue/attempt 使用各 policy 与剩余 parent budget 的最小值，单 request aggregate 不超过 9 秒；projection serialization 必须在入口后 10 秒前完成。慢/排队/失败 request 返回覆盖其完整 request keys 的封闭 result，其他已完成 request正常提交，未开始 ticket 在 parent deadline取消；一旦 request tuple形成，最终始终是含完整 `RefreshBatchResult` 的 OperationSuccess，包括零 snapshots/全部失败。没有后台 orphan。429/5xx/network/local timeout 都不自动重试、不 backoff 后再 call；backoff 只设置下一个逻辑请求的 ledger gate。

验收用 2+ 独立进程、4/32 边界、Provider limit 1/2/4、FIFO与跳过已满 Provider、取消/owner kill/lease接管、`now==deadline`、429/5xx序列和大量配置；任何实现的 Provider 调用数、部分结果 key、计数和 10 秒 hard boundary 必须相同。

### 9.1 全渠道刷新幂等

`quota_refresh` 采用 core 统一的 **at-most-once per idempotency key** 契约，singleflight 和限流不能替代它：

1. 幂等键至少 128 bit 随机且与 `actor pseudonym + operation + canonical scope digest` 组成唯一键。CLI 默认每次命令生成新键，并可用本地保存的 opaque retry handle 重试；飞书文本使用可信 event/message ID 派生键；卡片使用第 12 节复合键；Web 客户端提交的随机 `Idempotency-Key` 必须再绑定已认证 session/actor/scope。不同 actor 复用同一原始 key 不会共享结果。
2. 解析凭据或访问 Provider 前，core 在事务中写入 `prepared→running`。完成后原子写 `completed/failed_safe` 与不含机密的完整 canonical OperationResult envelope（refresh 为全部 per-request results，不是摘要）；并发和完成后重复逐字节返回该 envelope，不再次调用 Provider、不重复失败计数或审计副作用。
3. 进程在 `running` 与结果提交之间崩溃时，该键恢复为 `outcome_unknown`，后续相同键不再次调用 Provider。操作者需在 endpoint group 的 BudgetPolicy 允许后发起一个新逻辑请求；结果明确说明上次结果未知。
4. CLI/Web/飞书文本/卡片分别使用 `RET-IDEM-CLI`、`RET-IDEM-WEB`、`RET-IDEM-FEISHU-TEXT`、`RET-IDEM-FEISHU-CARD`；过期清理由事务完成，但 `RET-RATE-LEDGER` 不随幂等记录删除。授权失败不建立可泄露主体存在性的结果记录。

### 9.2 调度生命周期

阶段 1/2 核心只有 on-demand refresh，不承诺后台定时器。核心持久化刷新状态，但不会在短命 CLI 退出后继续运行。

后台刷新和告警由可选 `SchedulerHost` 驱动：独立安装可以使用 `agent-quota daemon` 或明确支持的 OS scheduler；Hermes 只是另一个可选宿主。SchedulerHost 必须调用同一 SDK，遵守持久化 `next_allowed_refresh_at`、暂停状态、随机抖动和授权范围。未安装 SchedulerHost 时，UI 必须显示“仅按需刷新”，不得暗示存在实时监控或后台告警。

## 10. 技术栈、进程模型与 CLI

Desktop MVP 采用 Tauri 2/Rust trusted host、bundle 内 React/TypeScript renderer，以及随包固定 Python 3.11+ runtime 的 core sidecar；core 使用 Pydantic、`httpx` 和 `platformdirs`。核心与辅助 CLI 不导入 Tauri/React/Hermes/FastAPI；Adapter 通过受控 entry point 注册并在使用时惰性加载。Desktop host 生命周期内 sidecar 常驻，但不成为系统级 daemon、不监听端口；退出后必须回收。

Desktop MVP 只正式支持 macOS。Linux Desktop 属于阶段 2B staged，但 Python core/辅助 CLI 仍按 `platformdirs` 遵循 XDG 并使用 POSIX 权限基线；macOS 使用系统应用目录与 Keychain。Windows 在 ACL、Credential Manager 与进程边界完成前，安装检查明确返回 `unsupported_platform`，不静默使用宽权限文件。

本地存储基线：

- POSIX 配置目录与数据目录创建为 `0700`，配置文件、数据库及其 `-wal`/`-shm` 文件创建为 `0600`；进程启动时校验，权限更宽则拒绝加载机密数据。
- 快照数值只保留当前值和 last-known-good，期限使用 `RET-SNAPSHOT`；到期删除数值不等于重置运行状态。最近成功 `schema_fingerprint`、`semantic_contract_id`、失败计数、`last_success_at`、暂停与 `next_allowed_refresh_at` 在 principal/subject/capability 仍启用期间独立保留，不得因快照过期而归零。Adapter/语义契约升级只能通过显式 probe/迁移切换基线。
- principal/subject 具有 `enabled/disabled/deleted` 生命周期；capability 的 `enabled` 表示存在于 `enabled_capabilities`，移出该列表是 `disable`，Adapter 新版本移除 spec 是 `manifest_removed`。运行数据清理遵守下表，禁止用“删除 capability”指代多种事件：

| 事件 | live config | 快照/缓存/LKG/结构语义基线/失败与调度 | 刷新预算 | 审计、幂等、迁移备份 | 再启用 |
| --- | --- | --- | --- | --- | --- |
| principal disable | 保留并标 `disabled`；所有后代不可查询 | 同一事务级联删除 | `RET-RATE-LEDGER` | 按唯一保存期限表 | 生成新 query generation，冷缓存启动 |
| principal delete | 无后代/引用时删除；否则普通命令返回 `referenced_object_conflict`，只有确认同一计划摘要的显式 `--cascade` 才删除 principal、后代与引用 | journal 协调的 DB 事务按已确认计划级联删除 | `RET-RATE-LEDGER`，防止重建绕过 | 按唯一保存期限表 | 只能创建新 opaque ID |
| subject disable | 保留并标 `disabled` | 只删除该 subject 全部 capability 运行数据 | `RET-RATE-LEDGER` | 按唯一保存期限表 | 生成新 generation |
| subject delete | 无 policy/view 引用时删除；有引用时普通命令返回 `referenced_object_conflict`，显式 `--cascade` 按确认计划移除引用后删除 | 只删除该 subject 运行数据 | `RET-RATE-LEDGER` | 按唯一保存期限表 | 只能创建新 opaque ID |
| capability disable | 无 policy/view 引用时从 enabled 列表移除；有引用时普通命令返回 `referenced_object_conflict`，显式 `--cascade` 按确认计划移除引用后禁用 | 只删除该 capability 运行数据 | `RET-RATE-LEDGER` | 按唯一保存期限表 | 重新加入时生成新 generation |
| manifest_removed | 新 Adapter 激活默认拒绝并列出类型化引用；只有显式 `migrate adapter --cascade` 的确认计划可原子移除 enabled/policy/view 引用并激活 | 按确认计划只删除该 capability 运行数据 | `RET-RATE-LEDGER` | `RET-MIGRATION-AUDIT` | 只有新 manifest 再声明后以新 generation 启用 |

本表的期限只引用[安全模型第 10.1 节唯一保存期限表](security-model.md#101-唯一保存期限表)；相关记录只留假名化关联与安全状态，不留额度值。TOML 文件与 SQLite 不能共享 ACID 事务，因此所有配置/generation/运行数据变更必须使用下述 migration journal，不能声称由一个数据库事务同时提交两种介质。备份默认不包含数据库，若用户显式开启则必须加密且遵守同一保存期限表。

破坏性操作、外部 drift 采用、plan metadata 确认与 migration journal 只能调用 `build_migration_plan_v1`。其唯一内部 envelope 是 `aq-migration-plan-envelope-v1`，顶层恰含 `schema/payload`；payload 恰含：

```json
{
  "recipe": "aq-migration-plan-v1",
  "old_config_sha256": "<64-lowercase-hex>",
  "new_config_sha256": "<64-lowercase-hex>",
  "target_manifest_sha256": "<64-lowercase-hex>",
  "actions": [{
    "action_id": "a000001",
    "semantic_key": "aqma_<64-lowercase-hex>",
    "kind": "create|update|disable|delete|remove_reference|replace_generation|purge",
    "object_kind": "principal|subject|capability|credential_binding|view|policy|metadata|generation|installation",
    "object_ref": {
      "ref_kind": "existing|new",
      "object_id": "<existing opaque ID or null>",
      "new_object_handle": "<aqn_ + 64 lowercase hex or null>",
      "proposed_object_id": "<new core-generated opaque ID or null>",
      "creation_parent_ref": "<existing object ID, new object handle, or null>"
    },
    "field_path": "<canonical-json-pointer-or-empty>",
    "before_sha256": "<64-lowercase-hex-or-null>",
    "after_sha256": "<64-lowercase-hex-or-null>",
    "reason_code": "<finite-local-enum>"
  }],
  "action_graph": [{
    "dependency_kind": "creation_parent|create_before_use|remove_ref_before_mutation|child_before_parent_delete|generation_replacement",
    "parent_semantic_key": "aqma_<64-lowercase-hex>",
    "child_semantic_key": "aqma_<64-lowercase-hex>"
  }],
  "cascade_memberships": [{
    "cascade_root_semantic_key": "aqma_<64-lowercase-hex>",
    "member_semantic_key": "aqma_<64-lowercase-hex>",
    "reason_code": "explicit-cascade"
  }]
}
```

所有字段均 strict/extra-forbid。`ExistingObjectRef` 要求 `ref_kind=existing`、`object_id` 恰命中 old registry、两个 new 字段与 `creation_parent_ref` 为 null；`NewObjectRef` 要求 `ref_kind=new`、`object_id=null`、`proposed_object_id` 是 core 在 plan 前生成但尚未注册的合法 opaque ID，且 `creation_parent_ref` 为 old registry ID、同 envelope 内另一个 new handle 或该 object kind 明示允许的 null。其 handle 唯一为：

```python
new_object_handle = "aqn_" + SHA256(
    b"agent-quota:new-object-handle:v1\x00" + JCS({
        "object_kind": object_kind, "proposed_object_id": proposed_object_id,
        "creation_parent_ref": creation_parent_ref,
        "after_sha256": after_sha256, "reason_code": reason_code,
    })
).hex()
```

`creation_parent_ref` 是 `NewObjectRef` 的 envelope 内必填判别字段并进入 semantic body、new handle 与 plan digest；validator 只凭 envelope 即可重算，禁止读取 planner 隐状态。非根 create 的 parent 必须产生 `creation_parent` graph edge。create 只能引用 new ref，其他 action 可引用 existing 或已由同 plan create 的 new ref；new handle/proposed ID 全局唯一，悬空、重复或同 proposed ID 多 handle 均拒绝。dry-run/日志仍只渲染本次运行的类型化句柄。

未编号 action 的 `semantic_body` 恰含 `kind/object_kind/object_ref/field_path/before_sha256/after_sha256/reason_code`，因此 new ref 内的 `creation_parent_ref` 被覆盖；它不含 ID、semantic key 或 action graph。`semantic_key="aqma_"+SHA256(b"agent-quota:migration-action:v1\x00"+JCS(semantic_body)).hex()`。planner 必须由全部 action semantic precondition 构造完整 dependency graph，`action_graph` edge 含封闭 `dependency_kind`，按 `(parent semantic key bytes,child semantic key bytes,dependency_kind bytes)` 排序并进入 payload。

dependency graph 至少且恰按下列规则生成：非根 create 的 parent create `→` child create；任一 action 引用 new handle 时，对应 create `→` use；remove_reference `→` 目标 disable/delete；child delete `→` parent delete；generation replacement 为 create/install new generation `→` switch all references/runtime fence `→` retire/delete old generation。cascade 只进入 `cascade_memberships` 表达成员与理由，不生成执行边；删除执行方向永远只由 child-before-parent-delete 决定。前置条件没有对应 edge、额外隐藏排序、duplicate edge、self edge、悬空端点或 cycle 一律在产生 plan digest 前拒绝。

唯一排序算法是 Kahn：计算全部 execution dependency kind 的 indegree，把所有 indegree=0 action 放入以 semantic key UTF-8 bytes 为键的最小堆；每次取最小项，输出后按 `(child semantic key bytes,dependency_kind bytes)` 升序减 indegree并入堆。同层 tie-break 因而唯一；输出不足 action 总数即 cycle。完成拓扑排序后才赋 `a000001..a999999`。最终 action 保留 semantic key，`action_graph`、`cascade_memberships` 与 actions 一起进入 digest，任一输入遍历顺序都不影响 bytes。每个拓扑前缀都必须满足 registry/引用/generation 不变量，否则拒绝整个计划。

`plan_bytes = b"agent-quota:migration-plan:v1\x00" + aq-jcs-nfc-v1(payload)`，`plan_digest=SHA256(plan_bytes).hex()`。任一 old/new config、target manifest、action 字段、对象、值或 cascade 关系改变都必须改变 digest。普通命令若发现引用则零写入并返回 `referenced_object_conflict`；`--cascade --dry-run`、`config adopt --dry-run`、plan change 确认、delete/purge 和 journal 全部保存/比较该同一 digest，正式命令另需一次 nonce。任何配置/manifest 漂移都会使 digest/nonce 失效并重新 dry-run；恢复只重放 envelope 内同一 action 集。辅助 CLI 可在终端显示脱敏 plan/digest 并显式接收 nonce；Desktop GUI 的 renderer 不能接收三者。Desktop 中 core 把同一脱敏 plan 只交给 Rust host-owned native confirmation surface，host 捕获 user presence 后在 host↔core 私有通道提交 nonce/token，renderer 只收到最终状态。
- 日志不记录账户别名、余额、精确额度、认证状态、上游正文或完整飞书标识；审计关联使用带本地密钥的假名化标识。该标识只降低日志/数据库在不含本地密钥的离机副本中的直接可关联性，不抵抗同一 OS uid 同时读取密钥与记录。
- 应用自带备份默认排除数据库，但不能控制 Time Machine 等系统备份。macOS 初始化/doctor 应建议并检查数据目录的 OS 级备份排除；用户不排除时必须提示历史备份可能超过应用保留期，`purge` 也不能保证清除已有系统备份。

### 10.0 InstallationRegistry 与 LocalKeyRing

初始化必须先建立不受 `HOME`/XDG/cwd 影响的安装锚点：从 OS 账户数据库 `getpwuid(getuid()).pw_dir` 取得真实 home，经 no-follow 父目录句柄验证后使用固定子目录 `.agent-quota/install-registry-v1`（`0700`）；禁止使用进程 `HOME`、命令参数或 cwd 替代。锚点内为每次安装生成 128-bit 随机 `installation_id`，并只按第 10.0.1 节唯一 file backend 保存 256-bit `installation_binding_key`；registry 为 `0600`。`platformdirs(appname="agent-quota")` **只在交互式 init 时计算一次** config/data/cache/log app root；若 Linux XDG 变量改变默认值，init 必须逐项显示并要求显式确认。registry 记录每个规范绝对 root 的路径策略、device/inode/owner/mode、XDG 是否显式确认和 MAC；它不保存额度或凭据。

`LocalKeyRing` 绑定 `installation_id`，存于登记的 data root 内独立 `0600` 文件并由 `installation_binding_key` 封装。root→每个 `(purpose,generation)` 的唯一 purpose 集、consumer映射、HKDF、轮换/verify-only、持久 surface 查找和 wire schema只以 [`local-key-purpose-registry-v1`](contracts/local-key-purpose-registry-v1.json) 为准；正文不得复制第二份 purpose/consumer 列表。payload 按 `(purpose,generation)` 排序并唯一，每个 purpose 恰有一个 active；只有 registry 明示允许的 purpose 可保留 verify-only。每条 key entry 的 16-byte `public_salt` 由 CSPRNG 独立生成，只用于 key-id domain separation，不是 secret、不得作为 KDF input；`aqk_` ID 按 artifact 的 exact recipe 绑定 installation、purpose、generation、salt 与 key material，加载时重算并 constant-time 比较。key ID 不暴露 key material且非秘密，可进入 journal；原始/派生 key 永不进入配置、SQLite/WAL、日志、fixture、投影、审计或应用普通备份。

registry/keyring 的唯一互操作格式如下。两者所有 JSON 都用第 8.3.1 节 `aq-jcs-nfc-v1`；未知字段/version/algorithm 拒绝。binding key 是 32-byte CSPRNG secret，其唯一 ID 函数是 `binding_key_id_v1(key) = "aqbk_" + SHA256(b"agent-quota:binding-key-id:v1\x00" + key).hex()`；`.hex()` 必须为 64 位 lowercase ASCII。init、startup、registry 解码、keyring 解封、restore、purge dry-run 和 golden vector 均只调该函数，比较只用 constant-time bytes compare，禁止任何无 domain 的 `SHA256(key)` 变体。HKDF-Extract salt 为 `SHA256(b"agent-quota:installation-binding:v1")`，分别 Expand info `registry-mac-v1` 与 `keyring-aead-v1` 得到互不相同的 32-byte key。

- `install-registry-v1.json` 是 `aq-installation-registry-envelope-v1`，恰含 `schema/payload/mac`。payload 的 exact schema 只读 core-safety contract：除 installation/binding key ID、`registry_sequence`、keyring generation/envelope sequence/digest/floor 与排序 root records 外，还必须保存 `current_trust_bundle={bundle_sequence,bundle_sha256,canonical_bundle_bytes_base64url}`、按 `(distribution_name,publisher_binding_id)` 排序的 `attestation_floors[]`，以及 `accepted_install_plan={plan_sequence,plan_digest}`；未知字段拒绝。正常升级在同一 fenced transaction 原子推进 bundle、attestation 与 plan 三类 floor；同 sequence 不同 digest、任一组件单独回滚或跨组件组合都拒绝。`mac.algorithm=hmac-sha-256`，tag 为 `HMAC(mac_key, b"agent-quota:registry:v1\x00" + JCS(payload))` 的无 padding base64url。
- `local-keyring-v1.json` 必须命中 LocalKey artifact schema 的 `localKeyRingEnvelope`：恰含 `schema/installation_id/binding_key_id/aead_generation/envelope_sequence/kdf/aead/nonce/ciphertext_and_tag`，其中 exact literals 为 `kdf="HKDF-SHA-256"`、`aead="AES-256-GCM"`。generation/sequence 都是 `1..2^63-1`；AAD只使用 artifact 的 `aad_recipe`。`nonce`、`ciphertext_and_tag`、payload内`public_salt/key_material`均且只能使用 RFC 4648 URL-safe 无 padding base64url；先校验alphabet/no `=`并解码全部字段，再检查 nonce=12 bytes、tag=16 bytes、public_salt=16 bytes、key material=32 bytes，禁止先按编码字符串长度猜字节。`ciphertext_and_tag` 是 ciphertext 后紧接 GCM tag，不存在独立 tag/ciphertext字段。明文恰命中同一 schema的`localKeyRingPayload`且 key entries按 `(purpose UTF-8 bytes,generation)` 排序。完整验证顺序与无秘密 AES-256-GCM golden bytes只读 artifact，任一大小写、padding、短/长/非法alphabet或 AAD bit变化均拒绝。
- 每个 AEAD generation 使用独立 key。`gen_salt=SHA256(b"agent-quota:keyring-generation:v1\x00"+JCS({installation_id,binding_key_id,aead_generation}))`，`prk=HKDF-Extract(gen_salt,installation_binding_key)`；`aead_key=HKDF-Expand(prk,b"agent-quota:keyring-aead:v1\x00"+u64be(aead_generation),32)`，`nonce_key=HKDF-Expand(prk,b"agent-quota:keyring-nonce:v1\x00"+u64be(aead_generation),32)`。唯一 nonce 是 `HMAC-SHA256(nonce_key,b"agent-quota:keyring-envelope:v1\x00"+u64be(envelope_sequence))[0:12]`，wire 中的 12 bytes 必须逐字节相等；同 generation sequence 严格递增且永不回退/复用，因而不保存无界 set。
- migration writer/fence 在 journal 中原子预留唯一 `(aead_generation,envelope_sequence)` 与 keyring/registry payload digest，生成 `keyring.tmp` 与 `registry.tmp`，分别 fsync并自验，再 no-follow rename keyring、registry并 fsync父目录；任何 kill 只 roll-forward 该预留 pair，允许跳号但禁止重用。无 active journal 时，registry、keyring 与 SQLite 保存的 generation/sequence/digest floor 必须完全一致，否则 `local_keyring_unavailable`。sequence 到最大值前必须由同一 journal 建立 `aead_generation+1,sequence=1`；generation 溢出 fail closed。旧 generation key在新 envelope提交并重验后即可删除，因为其 nonce只保护已被替换的 keyring envelope，不承担业务 verify-only 用途。
- 完整备份恢复只接受 binding/registry/keyring/SQLite/WAL/SHM/config 的同一原子集合；任一组件 floor 回退、旧 keyring 配新 registry、journal pair不匹配都拒绝。若外部系统把整个集合一起回滚，纯软件仍无法证明外部时间单调，这是既有备份边界；不得以此恢复单个旧 envelope或重置 floor。

两套独立实现必须互读 golden envelopes。攻击 fixture 覆盖单 bit、截断、错误 binding key、重复 nonce、registry/keyring 跨安装交换、旧 generation/sequence 回滚以及 keyring/registry 两次 rename 间崩溃；诊断只含 envelope 类别和非秘密 sequence/key ID，不含 key、salt 派生物或明文。若 registry、keyring 与 DB 三者作为同一旧系统备份一起回滚，纯软件无法证明外部时间单调性；这属于已声明的系统备份边界，恢复后仍必须通过当前 trust bundle/Provider generation 重新验证，不得宣称硬件级 anti-rollback。

#### 10.0.1 installation binding material 唯一 backend

macOS/Linux v1 唯一 backend 是安装锚点内固定文件 `installation-binding-v1.key`；禁止 Keychain/Secret Service、环境变量、registry JSON、SQLite、data root 或自选路径作为替代。文件内容恰为 32 个 CSPRNG raw bytes，无 BOM/换行/base64/envelope；anchor 必须为 current uid、mode `0700`、regular directory，key 必须为 current uid、regular file、mode 恰 `0600`、`st_nlink=1`、与 anchor 同 device。

首次创建在已 no-follow 打开的 anchor fd 上执行等价 `openat("installation-binding-v1.key", O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC, 0600)`，进程 `umask 077`；checked loop 写满 32 bytes，`fchmod(0600)`、`fsync(key_fd)`、post-write `fstat`，关闭后 `fsync(anchor_fd)`。不得先写 cwd/temp 后跨目录 rename，也不得覆盖已存在文件。registry/keyring temp 各自 `O_EXCL|O_NOFOLLOW`、fsync/self-verify 后同目录 rename并 fsync父目录；init crash 时只有“anchor + valid binding file、且 registry/data root/DB/keyring 均不存在”的状态可继续同一次初始化，任何其他 partial/existing combination 返回 `local_keyring_unavailable`，不删除、不重建 key。

每次启动先 no-follow 遍历真实 home→anchor，再 `openat(O_RDONLY|O_NOFOLLOW|O_CLOEXEC)` key；open 前后的 anchor/key `fstat` 必须一致，拒绝 symlink、非 regular、owner/mode/link/device变化。checked read 恰取 32 bytes并再读 1 byte确认 EOF；短/长/替换均失败。只调用上文 `binding_key_id_v1`，并以 constant-time compare 比较 registry 中的 ASCII ID，之后才允许验证 registry MAC、解 keyring、打开 Confidential SQLite。任何异常统一 `local_keyring_unavailable`，只输出本地 envelope/path component code，不输出 bytes/hash前缀。

应用普通备份和导出必须排除 binding file。v1 不提供单文件或部分安装恢复；唯一受支持恢复是同一 OS uid、同一 canonical roots 的文件系统快照原子恢复完整集合 `binding file + registry + keyring + SQLite/WAL/SHM + config`。启动时仍验证全部 envelope/sequence/digest/floor；集合缺一、来自不同 installation、路径/inode policy不符或只恢复旧子集都 fail closed。外部系统备份可能保留副本属于已声明边界；不得因“恢复”静默重置 installation/cohort/ledger。

purge 必须先持有 purge lease并验证 binding→registry→keyring，删除所有登记 app root 内容并 fsync各父目录；随后 no-follow unlink keyring并 fsync data root，再 unlink registry及init temp并 fsync anchor，**最后** unlink `installation-binding-v1.key` 并 fsync anchor，最后才尝试删除空 anchor目录。任何前序未知/未删项都保留 binding+registry供安全重试；binding 一旦删除不得继续读取或删除其他目标。dry-run 对四类条目分别列类型，不输出路径外秘密。golden/kill测试覆盖 O_EXCL竞态、每个 fsync/rename/unlink点、权限放宽、hardlink/symlink/inode交换、单文件丢失/截断/交换、完整恢复和 purge重试。

生命周期是拒绝式状态机：

1. 新安装只有在 registry、所有登记 root 与 DB 均不存在时才可生成 generation 1。registry/DB/root 任一表明已有安装而 keyring、binding key 或 active purpose 缺失/损坏时，返回 `local_keyring_unavailable` 并关闭 status/refresh/migrate/purge 之外的只读诊断；绝不静默重建为新安装。
2. 正常轮换必须取得第 10.2.1 节 migration writer lease/fence。新 generation 先写 `pending` 并 fsync，再由 journal 原子切换 active key ID。哪些 purpose 执行 `replace_generation`、哪些转 `verify_only` 只读取 `local-key-purpose-registry-v1`；前者原子生成新 query generation并删除旧缓存/LKG，后者在安全模型对应保护窗内只验证/查找既有 ledger/记录且不签发新值。正文不维护另一份 purpose 分类。
3. 轮换崩溃只按 migration fence roll-forward；旧 fence 不能激活 key。保护窗到期且没有任何引用后，journal 清除旧 key material 并把非秘密 key ID 标为 retired。备份恢复必须显式恢复同一 registry/keyring；无法恢复时保持 fail closed，不能以删除 ledger 后重建 key 绕过刷新或重放保护。
4. `purge --dry-run` 必须列出 active/verify-only key 数量、keyring、registry entry 和 binding key 的类型化条目；正式 purge 的 keyring→registry→binding 最终顺序、fsync 与可重试边界只按第 10.0.1 节执行。系统凭据存储或系统备份中的副本只报告为不可保证删除。

测试覆盖重启、同 key 稳定派生、正常轮换、每个崩溃点、旧 key 保护窗/到期、keyring/registry/binding key 单独丢失、回滚旧 keyring、双 writer 与 purge；证明刷新预算不扩容、旧重放不重新执行、缓存不跨 identity 复用且 Secret 不出现在任何输出或普通备份。

### 10.1 独立发行与依赖矩阵

| 发行单元 | 内容 | 允许依赖 |
| --- | --- | --- |
| `agent-quota-installer` | 最小 bootstrap、trust bundle/attestation/install-plan 验证和 verified pip 调用 | 密码学/JCS 与 pip 调用；不得导入 Provider |
| `agent-quota-desktop` | Tauri 2/Rust host、bundle 静态 renderer、签名 sidecar/runtime 与 macOS 安装/升级元数据 | 仅通过冻结 IPC 调用 application service；不得包含凭据或 Provider 逻辑 |
| `agent-quota-core` | 数据模型、配置、授权、缓存、投影、Application Service、Adapter API | Pydantic、存储与通用安全依赖；不得依赖 Tauri/React/Hermes/FastAPI |
| `agent-quota-cli` | `agent-quota` 辅助 console entry point | 只依赖与 Desktop 相同的 application service；不得复制业务规则 |
| `agent-quota-provider-deepseek` | DeepSeek Adapter | core + HTTPX |
| `agent-quota-provider-openrouter` | OpenRouter current-key Adapter | core + HTTPX；真实门禁前只是 supported candidate |
| `agent-quota-provider-codex` | 默认关闭的 Codex Experimental parser | core；只运行离线 fixture/parser，不启动或探测真实 Codex CLI，不正式 fetch |
| `agent-quota` | Python 辅助 meta distribution | core + CLI；extras `deepseek`、`openrouter`、`codex-experimental`、`daemon`、`web`，不替代 Desktop 主发行包 |
| `agent-quota-testkit` | FakeAdapter、fake HTTP/local-stdio、虚构 fixture 与合约 runner | 只依赖 core；独立 wheel/sdist，仅 CI/开发显式安装 |
| `agent-quota-hermes` | Hermes/飞书命令与 Credential Source 扩展 | core + 明确版本范围的 Hermes；不被默认包依赖 |

构建必须为 core、CLI、生产 Provider、meta distribution 和 testkit 分别生成 wheel 与 sdist，但二者的 assurance 预期不同。Supported/GA Provider **只允许**从第 8.3 节受信任发布者签名的最终 wheel 获得资格；发布 sdist 只用于源码审阅、复现和受信任下游重新发行，原发布者的 wheel attestation 不随 sdist 继承。普通 `pip --no-binary :all:` 在本机从 sdist 生成的新 wheel 即使源码相同，只要 wheel bytes/build backend/lock 不同或没有该最终 wheel 的有效 detached attestation，就不得作为 Supported/GA、不得解除安全 pause，loader 稳定返回 `adapter_not_distributable` 且 Provider 调用计数为 0。下游若要重新发行，必须以自己的受信任 publisher key、固定 backend/lock、完整 manifest/fixture/report/build proof 重新生成 assurance 与 attestation；把新 key 加入 trust bundle 是独立、显式、签名且可撤销的信任变更。

干净环境验收使用没有 Hermes、没有源码 checkout 或用户 Python 的全新 macOS VM：(a) 签名/notarized Desktop DMG/App 验证 host、renderer、runtime/sidecar、DeepSeek/OpenRouter wheel raw digest、publisher attestation、依赖 lock 与 bundle code signature；(b) wheel 生产环境由 bootstrap staging/验证后安装 `agent-quota[deepseek,openrouter]`；(c) sdist 源码审阅环境证明 core/CLI 可运行，同时 Provider 因缺最终 wheel attestation 被确定性拒绝；(d) 测试环境显式安装 core/CLI/testkit 完成 Fake 查询。所有环境断言生产依赖闭包、安装文件与用户 Adapter 列表没有 testkit/FakeAdapter；Codex extra 默认未安装，显式安装后仍为 incompatible。sdist 缺源码/manifest/fixture/report 任一项必须构建失败。卸载默认保留用户配置/数据；只有 GUI 的 purge confirm 或等价辅助 `agent-quota purge` 才执行下列破坏性状态机：

1. 只从第 10.0 节固定安装锚点读取并验证 MAC 后的 `installation_id` 与 init 时登记的 config/data/cache/log root；purge 不调用 platformdirs，不读取 `HOME`/`XDG_*`，也不接受命令参数、cwd 或环境变量改变根。当前路径、device/inode/owner/mode、路径策略或 XDG 确认状态必须与 registry 完全一致。registry 缺失/损坏、同名未登记 app 目录、空路径、`/`、真实 home、workspace、platformdirs 父目录、挂载点、跨文件系统目标、symlink/reparse point、非当前 uid owner、比 `0700` 更宽权限或含 `..` 的目标全部 fail closed。
2. 先获取独占 purge lease，停止/拒绝 Scheduler/Web/Hermes 新请求，checkpoint/truncate 并关闭数据库；列出将删除的 config、SQLite/WAL/SHM、cache、应用日志、幂等/审计表和迁移备份。系统备份与仓库外用户导出明确列为“无法删除”。
3. 辅助 CLI 用户必须输入本次随机 confirmation nonce；Desktop 则由 host-owned native confirmation surface 展示 core 脱敏计划并捕获 user presence，nonce/token 不显示、不发送给 renderer，只在 host↔core 通道原子消费。确认前后用父目录句柄和 no-follow `lstat/openat/unlinkat` 等价操作重新比较 device/inode/owner/mode，任何替换立即中止。不得用字符串前缀、递归跟随链接或先 `resolve()` 后无句柄删除。
4. 仅逐项删除受控 app 目录内由 manifest 列出的非根密钥文件/子目录；遇到未知文件、硬链接计数异常、跨 device 条目或目录交换时停止并报告剩余项，不扩大删除范围。所有 app root 普通内容完成后，严格按第 10.0.1 节依次处理 keyring、registry、binding material并逐父目录 fsync，返回已删/未删/不可保证删除清单。

攻击测试必须覆盖 root/home/空路径/`..`、init 后改变任一 XDG/HOME/cwd、同名 app 目录、registry/MAC 篡改、symlink 链、确认后 inode 交换、非当前 owner、宽权限、未知嵌套文件、挂载点/跨文件系统和仍运行宿主；全部在删除任何文件前或安全边界内 fail closed。Time Machine 等系统备份只提示用户单独处理。

### 10.2 版本化配置

```toml
schema_version = 1

[presentation]
timezone = "Asia/Shanghai"  # IANA timezone；缺失或非法时渲染为带 fallback 标识的 UTC

[[principals]]
id = "aqp_4f7a9c2e1b6d8a30f5c7e9b2d4a6813c"
enabled = true
adapter = "openai-codex"
provider_variant = "chatgpt-codex"
region = "local"
auth_variant = "official-cli"
endpoint_profile = "local-stdio"
credential_bindings = []

[[subjects]]
id = "aqs_3d8e1f6a9b2c5d7e4f8a1b6c9d2e5f70"
principal_id = "aqp_4f7a9c2e1b6d8a30f5c7e9b2d4a6813c"
enabled = true
kind = "subscription"
label = "Codex 订阅"
selector = { source = "compat-default" }
enabled_capabilities = ["rolling-primary", "rolling-secondary", "codex-rate-limit-status"]
display_group = "coding-plans"
display_order = 10

[[principals]]
id = "aqp_8b3e6d1a4f9c2e7b5d8a1c6f3e9b4d20"
enabled = true
adapter = "deepseek"
provider_variant = "open-platform"
region = "global"
auth_variant = "api-key"
endpoint_profile = "official-global"
credential_bindings = ["aqb_9e4b7c2a6d1f8e3b5c9a2d7f4e6b1c80"]

[[subjects]]
id = "aqs_6c1a8e3d7b2f9d4e5a8c1b6f3d7e2a90"
principal_id = "aqp_8b3e6d1a4f9c2e7b5d8a1c6f3e9b4d20"
enabled = true
kind = "wallet"
label = "DeepSeek 钱包"
selector = { source = "default" }
enabled_capabilities = ["wallet-balances", "wallet-availability"]
display_group = "api-wallets"
display_order = 20

[[credential_bindings]]
id = "aqb_9e4b7c2a6d1f8e3b5c9a2d7f4e6b1c80"
purpose = "quota-read"
credential_ref = "env:DEEPSEEK_API_KEY"

[[alert_policies]]
id = "aqa_1a2b3c4d5e6f708192a3b4c5d6e7f809"
subject_id = "aqs_3d8e1f6a9b2c5d7e4f8a1b6c9d2e5f70"
capability_id = "rolling-primary"
metric = "window_used_percent"
dimension = "window"
direction = "at_or_above"
warning = 70
high = 85
critical = 95

[[alert_policies]]
id = "aqa_2b3c4d5e6f708192a3b4c5d6e7f8091a"
subject_id = "aqs_3d8e1f6a9b2c5d7e4f8a1b6c9d2e5f70"
capability_id = "rolling-primary"
metric = "reset_pressure"
dimension = "window"
within_minutes = 30
min_used_percent = 80
severity = "high"

[[alert_policies]]
id = "aqa_3c4d5e6f708192a3b4c5d6e7f8091a2b"
subject_id = "aqs_6c1a8e3d7b2f9d4e5a8c1b6f3d7e2a90"
capability_id = "wallet-balances"
metric = "balance_floor"
dimension = "CNY"
direction = "at_or_below"
warning = 100
high = 50
critical = 10

[[views]]
id = "aqv_4d5e6f708192a3b4c5d6e7f8091a2b3c"
label = "我的当前订阅"
subject_refs = [
  { principal_id = "aqp_4f7a9c2e1b6d8a30f5c7e9b2d4a6813c", subject_id = "aqs_3d8e1f6a9b2c5d7e4f8a1b6c9d2e5f70" },
  { principal_id = "aqp_8b3e6d1a4f9c2e7b5d8a1c6f3e9b4d20", subject_id = "aqs_6c1a8e3d7b2f9d4e5a8c1b6f3d7e2a90" },
]
capability_refs = [
  { principal_id = "aqp_4f7a9c2e1b6d8a30f5c7e9b2d4a6813c", subject_id = "aqs_3d8e1f6a9b2c5d7e4f8a1b6c9d2e5f70", capability_id = "rolling-primary" },
  { principal_id = "aqp_4f7a9c2e1b6d8a30f5c7e9b2d4a6813c", subject_id = "aqs_3d8e1f6a9b2c5d7e4f8a1b6c9d2e5f70", capability_id = "rolling-secondary" },
  { principal_id = "aqp_4f7a9c2e1b6d8a30f5c7e9b2d4a6813c", subject_id = "aqs_3d8e1f6a9b2c5d7e4f8a1b6c9d2e5f70", capability_id = "codex-rate-limit-status" },
  { principal_id = "aqp_8b3e6d1a4f9c2e7b5d8a1c6f3e9b4d20", subject_id = "aqs_6c1a8e3d7b2f9d4e5a8c1b6f3d7e2a90", capability_id = "wallet-balances" },
  { principal_id = "aqp_8b3e6d1a4f9c2e7b5d8a1c6f3e9b4d20", subject_id = "aqs_6c1a8e3d7b2f9d4e5a8c1b6f3d7e2a90", capability_id = "wallet-availability" },
]
```

principal、subject、credential binding、view 与 alert policy 的记录 ID 必须由 core 生成且不可编辑，格式为类型前缀 `aqp_/aqs_/aqb_/aqv_/aqa_` 加 32 位小写十六进制随机值。邮箱、账号、组织名、外部 ID、用户 slug 等自由文本只能进入受保护的 label/selector，不能充当记录 ID。capability ID 例外：它是 AdapterManifest 随代码冻结的公共枚举，不得从上游账户标识动态生成。

配置 DTO 与运行模型分离：`SubjectConfig` 必须包含本地用户确认的 `id/principal_id/enabled/kind/label/selector/plan_code/enabled_capabilities/display_*`，其中 plan 可为 null 或 manifest 有限枚举；`DiscoveredSubject` 只包含本次命令内 opaque handle、manifest kind、selector 候选和经转义的 suggested label，不得直接落盘；只有用户确认并提供/接受本地 label 后，core 才生成 `QuotaSubject`。显式离线配置的 label 必填，按 NFC 规范化，长度 1..80，拒绝控制字符、双向覆盖字符和首尾空白；不得用 selector、ID 或上游原文自动补齐。Provider 的 plan 值只通过 `SubjectMetadataObservation` 映射为 manifest 有限 `plan_code`，未知值丢弃；label 由用户拥有，Provider 后续发现不得覆盖。配置必须表达 `provider_variant`、`region`、`auth_variant`、代码内批准的 `endpoint_profile`、零或多个 `credential_bindings`、启用的 capability 以及展示分组/顺序。可选 `views` 是命名展示过滤器，用来组合当前安装中实际拥有的 subject/capability；它只能引用已启用的绑定式 `(principal_id, subject_id, capability_id)`，不能定义新主体、改变凭据绑定或扩大 `AccountScope`。因此同一个发行包可以用 DeepSeek-only、OpenRouter-only 或混合配置显示不同订阅组合；Codex 配置只能处于显式 Experimental/incompatible 视图，无需修改代码。

`alert_policies` 属于 schema v1 的判别联合，并绑定一个已启用的 `(subject_id, capability_id)`。policy identity/重复键固定为 `(subject_id, capability_id, metric, dimension)`：`window_used_percent` 与 `reset_pressure` 的 dimension 固定 `window`；`balance_floor.dimension` 恰为 capability 中存在的 currency；`counter_remaining.dimension` 恰为 capability canonical unit。窗口百分比使用 `0..100` 且递增的 warning/high/critical；重置压力使用 `within_minutes + min_used_percent + severity`；余额/计数使用递减绝对阈值。metric/kind、dimension、阈值顺序、字段组合错配均拒绝；同 currency/unit 的重复键拒绝，不同 currency 是独立策略、独立命中/清除且绝不求和。每个命中的策略按统一序列产生 severity，同一 capability 的所有 dimension/policy 与固定 health severity取最高值并聚合进同一 capability episode；未命中且 health 正常为 `none`。

`selector` 按 AdapterManifest 提供的 schema 校验，属于机密配置，不能承载任意 URL。加载规则默认严格：未知字段、重复/非 opaque ID、悬空 principal/credential/subject/view/policy 引用、未声明 capability、错误 binding 数量、未知 endpoint profile 和未来 `schema_version` 均拒绝。升级使用显式、幂等迁移；`migrate --dry-run` 不输出原始记录 ID，只按确定顺序展示本次运行内稳定的类型化句柄（如 `<principal:01>`、`<subject:02>`）、字段路径和操作类型。principal/subject label、selector、外部 ID、完整 CredentialRef 及其值必须显示为类型化占位符，且 stdout/stderr/日志/CI artifact 使用同一脱敏器。旧 ID 的规则唯一确定：已经符合当前 opaque 语法则保持；不符合但引用图唯一、无悬空/重复且不含 secret-like Token 的 legacy ID 只能经 `migrate legacy-ids --cascade`、相同 plan digest 和显式确认生成新 opaque ID 并原子重写引用；含 secret-like Token、重复、歧义或悬空关系时返回 `migration_conflict` 且零写入，要求用户先在受保护编辑器中清理。正式迁移生成 `0600` 的限时备份，不迁移任何解析后的秘密值。

#### 10.2.1 TOML + SQLite migration journal

本节的 migration writer 与 temp claim 分别固定引用 `lease-policy-v1` 的 `migration-writer-v1`、`temp-claim-v1`；正文中的 `lease_expires_at` 不是可配置数值，任何实现不得另设时长、renew-at、最大寿命或接管公式。

`config.toml` 是用户配置的唯一权威文本；SQLite 保存 active config digest、query generation 与运行状态。应用在任何查询/调度入口开放前执行恢复。协调器使用 `PRAGMA synchronous=FULL`，并有唯一的 `migration_writer` 行：`owner_id` 为本次进程随机值，`lease_expires_at` 使用数据库 UTC，`fencing_token` 由 SQLite 单调递增。获取/接管必须在 `BEGIN IMMEDIATE` 中完成；SQLite 部分唯一约束保证全库最多一个阶段非 `complete` 的 migration。每个 journal 行至少含 `migration_id`、`writer_fencing_token`、`old_config_digest`、`new_config_digest`、`new_config_bytes`（按 Confidential 存在 `0600` SQLite 中且完成后清空）、`aq-migration-plan-v1` envelope bytes 及重算的 `plan_digest`、`confirmation_nonce_digest`、`target_generation_digest`、cleanup proof字段和封闭阶段 `prepared|file_committed|db_committed|cleanup_pending|complete`。`cleanup_pending` 前必须保留重验temp/claim所需的 parent device/inode、basename、file device/inode/length/hash、claim fence与journal ID；`complete` 行禁止仍有 attached claim。journal 不再定义第二个 digest 公式；它必须调用 `build_migration_plan_v1`重算并逐字节比较 envelope/digest。需要确认的计划中 nonce 至少 128 bit、一次使用、最长 10 分钟，journal 只保存其 keyed digest：

1. 先取得 `migration-writer-v1` lease/fence，再在内存完成严格校验与 dry-run 等价计划；破坏性计划仍必须复用同一 plan digest 与未消费 nonce。临时 basename 只由不可预测 `migration_id` 派生。规范记录 `persist:v1:migration_temp_claim:create:RET-MIGRATION-TEMP-CLAIM` 使用封闭阶段 `name_claimed→file_opened→file_sealed→attached`，orphan 接管只能转 `name_claimed|file_opened|file_sealed→cleanup_claimed`。所有阶段必含 migration/owner/fence/`temp-claim-v1` lease/basename/parent-directory device+inode/plan digest；`name_claimed` 的 file 属性与 digest 全为 null，`file_opened` 必须有 file device/inode/owner/mode=`0600`/nlink=1 且 digest/length为 null，`file_sealed` 再要求 checked length、SHA-256、post-fsync fstat 与 parent-fsync marker，`attached` 再要求唯一 journal ID；字段早出现、缺失或状态外组合拒绝。

   唯一 syscall/事务顺序是：`BEGIN IMMEDIATE` 写 `name_claimed` → 已登记父目录 fd 上 `openat(O_EXCL|O_NOFOLLOW|O_CLOEXEC,0600)` → 尚未写任何 byte 时立即 `fstat` → `BEGIN IMMEDIATE` 验证 current fence并写 `file_opened` inode字段 → checked write/fchmod/fsync → 同 fd 重算 length/hash并 post-fstat → fsync父目录 → `BEGIN IMMEDIATE` 验证 inode/fence后写 `file_sealed`。只有 `file_opened` 事务提交后才允许首个 write。每个 syscall 前后 kill 都落在一个可判别阶段；此时没有 journal，旧配置仍有效。
2. 持有者在 SQLite 事务中同时验证 `migration-writer-v1` lease 未过期、token 等于当前 fence、claim 恰为 `file_sealed`、全部 inode/digest/plan 字段一致且不存在其他 active migration，再写入 `prepared` journal 并把 claim 转为 `attached`；从这一点起恢复方向固定为 **roll forward 到新配置**。
3. 每次文件动作前重新验证 writer fence、旧文件 digest 与临时文件 digest，使用同目录 no-follow rename 替换 `config.toml`，再 fsync 父目录；随后只有相同 token 能把阶段推进为 `file_committed`。在 rename 与阶段更新之间崩溃，由 digest 判定文件实际状态；旧 token 即使稍后恢复也不能写阶段或 DB。
4. SQLite 事务再次验证当前 writer fence，并要求磁盘文件等于 `new_config_digest`；随后安装唯一 active generation、执行计划内运行数据删除、更新 active config digest 与 `active_runtime_fence=fencing_token`，并标为 `db_committed`。事务内所有动作以 `(migration_id, action_id)` 唯一键幂等。
5. checkpoint 后由相同 fence 在事务中把阶段改为 `cleanup_pending`，但保留 `new_config_bytes` 与全部temp/claim重验字段。持有者按已登记 parent fd、inode/digest与fence no-follow幂等 unlink临时文件，fsync父目录，再在事务中删除同 migration/fence 的 attached claim并写 `temp_absent=true,parent_fsync_complete=true,claim_absent=true` cleanup proof。最后一个 `BEGIN IMMEDIATE` 重验文件/active digest/runtime fence、三个proof与不存在 attached claim后，才把journal标为`complete`、清空`new_config_bytes`并释放lease。迁移审计期限只引用[安全模型唯一保存期限表](security-model.md#101-唯一保存期限表)。

恢复者只能在旧 lease 到期后通过同一事务取得更大的 fencing token，并接管唯一 active migration。恢复算法只接受有限组合：`prepared/file_committed` 且文件为 old digest 时，从 journal 的新配置字节重建**该 migration 专属**临时文件并继续第 3 步，同时按新文件的 no-follow 属性更新 `attached` claim；文件为 new digest 时直接继续第 4 步；其他 digest 一律 fail closed 且不删运行数据。`db_committed` 要求文件与 active digest 都为 new；DB仍为old时幂等重放第4步，匹配时推进`cleanup_pending`。`cleanup_pending` 只允许按保留字段重复执行“验证同 inode或已不存在→unlink→父目录fsync→删同fence claim→写proof→complete”；在任一kill point重启都可继续，绝不依赖orphan分支。`complete` 必须已有三个cleanup proof且claim不存在，否则视为合同损坏并关闭gate；任何第三个 DB digest都拒绝。journal 中已消费 nonce 只授权其中固定的action集，恢复可幂等重放但不得生成新动作或扩大cascade。

没有 active journal 的 orphan 使用独立声明 `persist:v1:migration_temp_claim:update:RET-MIGRATION-TEMP-CLAIM` 与 `persist:v1:migration_temp_file:delete:RET-MIGRATION-TEMP-CLAIM` 恢复状态机。只有 claim lease 到期且接管者在 `BEGIN IMMEDIATE` 获得更大 fence，才能把 orphan 阶段改为 `cleanup_claimed`；旧 fence 在每个事务、I/O、fsync 和 unlink 前复核失败，不能推进或删除。

- `name_claimed` 且文件不存在：删除 claim。文件存在时只允许由已登记父目录 fd no-follow 打开；仅当目标是 current uid、`0600`、nlink=1、同 device regular file且 size=0 时，先记录实际 inode并转 `cleanup_claimed`，再按 inode unlink。任何已写 byte、symlink或属性异常 fail closed。
- `file_opened`：无论内容为空、部分或完整，都只按 claim 已记录的 parent/basename/device/inode/owner/mode/nlink 匹配；匹配后先转 `cleanup_claimed` 再 unlink，不要求尚不存在的 digest。替换 inode、hardlink、跨 device 或缺属性均拒绝。
- `file_sealed`：除 inode字段外必须流式重算 length/hash并匹配 sealed 值，之后才转 `cleanup_claimed` 并 unlink。`attached` 只能由同 migration active journal roll-forward，orphan 分支不能接管。
- `cleanup_claimed`：重复恢复只允许按同一 inode完成 unlink、fsync父目录、再删 claim；文件已不存在时仍须验证 parent identity后幂等删 claim。任何无 claim 的临时文件保持 gate 关闭，不得凭 basename pattern、字符串路径、`resolve()` 或跟随链接清理。

golden kill矩阵在 claim insert、open、fstat、file-opened commit、每次 write、fchmod、file fsync、post-fstat/hash、directory fsync、sealed commit、attach commit、`db_committed→cleanup_pending` commit、unlink、cleanup父目录fsync、claim delete/proof commit与最终complete commit前后逐点终止；恢复必须收敛或安全 fail closed，且永不删除非本 migration inode。

无 journal 但外部有效 TOML 与 DB active digest 不同时，**禁止**直接建立 `file_committed` 并自动 roll-forward。宿主先原子关闭全部服务 gate，使用 old DB registry/active manifest 与新 TOML 计算同一个类型化 diff/planner，且在确认前不解析凭据、不启动子进程、不访问 Provider、不改变 active config/generation digest或任何快照/LKG/失败/ledger 表。唯一可以自动采用的安全集合是：(a) presentation timezone；(b) 已存在且仍启用 subject 的本地 `label/display_group/display_order`；(c) 只引用已存在、已启用且父子绑定正确对象的 view 新增、删除、过滤引用或排序修改，因为 view 不是授权来源且不清理运行数据。除这类 view 过滤引用外，自动集合不得改变 actor scope、alert policy、principal/subject/capability/credential/selector/endpoint/manifest、启用状态、所有权/policy/后代引用或任何运行数据。

任何不完全属于上述集合的 drift 都保持 gate 关闭并要求重新生成脱敏 plan：辅助 CLI 使用 `agent-quota config adopt --dry-run` 输出 actions/`plan_digest`，confirmation 表只保存一次 nonce keyed digest并执行前述 nonce 上限；active config/运行表仍为旧值。CLI 正式命令固定为 `agent-quota config adopt --plan-digest "$AQ_PLAN_DIGEST" --confirm "$AQ_CONFIRMATION_NONCE"`。Desktop 对 purge、disable/delete/cascade 及 endpoint/auth/binding/capability/manifest destructive diff 只允许 Rust host-owned native surface 展示 core plan；plan/digest/nonce/user-presence token 永不返回 renderer。host 必须重新读取同一文件、manifest 和 DB old digest并原子消费 nonce/token后才执行已确认 journal。任何 destructive diff、再次编辑、manifest 变化、nonce/token 状态失效/复用或 digest 不同都使确认失效且 DB/Provider 零变化。

运行时不能只在启动检查 drift。每个 CLI/Web/Hermes 服务入口在读取缓存、解析凭据或访问 Provider 前，都必须用 no-follow 句柄读取当前 TOML digest，并在同一 SQLite 读事务中验证 `(file_digest, active_config_digest, active_generation_digest, active_runtime_fence)` 等于进程内 registry/fence；SchedulerHost 在 claim 每个 job 前执行同一门禁。文件 digest 漂移、DB fence 变大、generation 不同或出现 active migration 时，宿主原子关闭查询/调度 gate，取消尚未进入 Provider 的任务，等待/执行上述恢复，再从新 registry 重开；旧 fence 的长任务在提交快照、LKG、计数或告警前再次检查，失败则丢弃结果且零写入。

逐点 kill 测试覆盖规范记录 `persist:v1:migration_temp_file:write:RET-MIGRATION-TEMP-CLAIM` 对应的临时对象 I/O、fsync、journal commit、rename、父级 fsync、DB commit、checkpoint 与完成清理；竞争测试覆盖双 CLI、CLI+daemon、外部有效/无效编辑、writer 崩溃与 lease 接管。连续重启只收敛到一个新态，旧 token 不能提交，禁用/删除在权威配置生效后旧宿主不得再读缓存或访问 Provider。

### 10.3 CLI 草案

```bash
agent-quota init
agent-quota config validate
agent-quota account add                 # 向导：创建 principal + 一个或多个 subject
agent-quota subject discover --account aqp_4f7a9c2e1b6d8a30f5c7e9b2d4a6813c
agent-quota doctor
agent-quota list --view aqv_4d5e6f708192a3b4c5d6e7f8091a2b3c
agent-quota refresh --subject aqs_3d8e1f6a9b2c5d7e4f8a1b6c9d2e5f70
agent-quota migrate --dry-run
agent-quota daemon                      # 可选 SchedulerHost；Desktop MVP 后提供
agent-quota serve                       # 可选远期 Web；不属于 Desktop GUI
```

CLI 不是主产品表面，只用于维护、诊断、无障碍和自动化。它与 Desktop command 调用同一个 application service 和 operation contract，不允许自行读 SQLite、解析 Provider 响应或复制授权/刷新逻辑。CLI 可以使用面向用户的“account”词汇，但权威模型必须明确生成 principal、subject 和 capability，不能重新把三者压成一个账户对象。

### 10.4 远期 Web API 草案

这一节只描述远期可选 Web，不描述 Desktop renderer。若立项，FastAPI 只封装同一个 application service，远程前端只消费授权 JSON API。

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/v1/adapters` | 返回 AdapterManifest 与兼容状态，不返回凭据 |
| GET | `/v1/subjects` | 返回授权范围内的主体和 capability 状态 |
| GET | `/v1/quotas` | 返回授权后的 capability 投影 |
| POST | `/v1/quotas/refresh` | 手动刷新指定主体/能力 |
| GET | `/v1/health` | 本地服务健康检查 |

监听 `127.0.0.1` 不是认证。阶段 4 必须同时实现：随机 256-bit 本地令牌或短期会话、严格 `Host` 允许列表、精确 `Origin` 允许列表、默认拒绝 CORS、`SameSite=Strict`/`HttpOnly` 会话 Cookie、独立 CSRF Token、状态变更请求的 `Origin`/`Content-Type` 校验，以及对 JSON 体和响应体的大小上限。不得使用 `*` CORS，不得因请求来自 loopback 就跳过认证。

## 11. Hermes 集成方案

Hermes/飞书属于阶段 3 的可选 `agent-quota-hermes` 发行包，不属于独立 MVP。该包依赖 core，core 不得反向导入 Hermes、读取 `~/.hermes` 或包含飞书事件类型。

Hermes 的“单租户个人 Agent”假设不能代替集成授权。当前普通工具派发只提供 `task_id` 和 `user_task`，不能可靠证明飞书身份；工具结果还会进入模型上下文并被其他插件钩子观察。因此可选集成采用两个明确分离的表面：

1. **确定性命令表面（集成默认表面）**：阶段 3A 集成门禁关闭后，`/额度`、`/quota` 和 `/刷新` 在 Agent 运行前由网关命令路由器处理。它把可信 `FeishuCallerContext` 映射为 core 的 `AccessContext`，完成授权、SDK 调用和确定性渲染后直接发送结果，不调用 LLM，不注册为普通工具，不经过通用工具钩子。
2. **自然语言工具表面（默认关闭）**：若用户在配置中作出由 `RET-CONSENT-ACTIVE/RET-CONSENT-TOMBSTONE` 管理的显式、可撤销同意，且宿主能注入模型不可修改的 `ConsentContext(actor, platform, projection_scope_id, consent_generation)`，才可注册 `quota_status_summary`。每次调用都在读取缓存前重新校验 generation、范围、到期与撤销；撤销原子递增 generation，使既有会话立即失效。它只返回受安全模型 `LLM_PROJECTION_COOLDOWN/LLM_PROJECTION_HOURLY_LIMIT` 双层预算保护的 `llm_minimal` 投影。自然语言表面不提供刷新，也不返回完整 JSON、账户别名、余额、精确百分比、计划、认证状态或重置时间。

core 的公共服务入口使用渠道无关模型：

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
```

Desktop trusted host 与辅助 CLI 都由受信任本地入口构造 `LocalActor(os_uid)` 与本地配置允许的 `AccountScope`，不需要伪造 tenant、app、chat 或 message 字段。飞书包在自己的边界保留完整平台字段，并依据 `(tenant, app, operator, conversation_type)` 解析 scope。scope 构造器必须从当前 registry 解析每个绑定引用，拒绝父子不一致、已移动/禁用/删除的 subject 和悬空 capability；公共服务入口在读取缓存、更新计数或调用 Adapter 前再次验证请求 principal、`(principal, subject)`、`(principal, subject, capability)` 三层均命中且 registry 父子关系仍一致。请求主体为空表示“授权范围”，绝不表示全部配置；空 scope、伪造 view 或任一父 principal 不匹配统一返回 `not_authorized`，且不得读取缓存、调用 Adapter、更新失败计数或泄露主体存在性。

Hermes 集成必须把 `MessageEvent.raw_message/source` 中的可信字段通过不可由模型修改的上下文传给命令路由器。不得从 `user_task`、`task_id`、会话标题或提示词恢复身份。桥接未完成时只禁用 `agent-quota-hermes`，独立包仍可使用。

`quota_recommend` 推迟到阶段 5，必须先有可解释的推荐策略、真实消耗速度数据和独立验收标准。第一版既不实现也不注册空占位工具。

可信计算基按部署 profile 分开：Desktop profile 包含操作系统用户、已签名 Tauri host、随包 Python runtime/core sidecar、系统 secret store/本地数据服务与启用的内置 Adapter；renderer 受 capability/CSP/command allowlist 限制但仍是本地攻击面。Hermes profile 在 core 数据面基础上增加 Hermes 核心及全部已启用插件。`CredentialRef` 和 `0600` 不是同 uid/同进程插件之间的隔离边界：启用 Hermes profile 即接受所有已启用插件可直接读取 Agent Quota 配置、SQLite、WAL/SHM 与本地假名化密钥，从而绕过 core 的 actor/AccountScope 读取控制。这是当前 profile 的明确已接受风险，不得把 Confidential 投影规则宣传成对共驻插件的保密保证。高敏感用户应只使用 Desktop，或把 Hermes 放到独立 OS 用户/实例且只启用受信任插件；在密钥仍可被同 uid 读取时，仅给 SQLite 加密不能关闭此风险。MVP 不允许第三方 Adapter 接触原始凭据；未来 P2 必须使用独立进程、过滤环境、单凭据授权和固定出口。

## 12. 飞书方案

阶段 3 的首个集成版本复用现有 Hermes 飞书机器人，不新建独立飞书应用：

1. 用户在飞书向 Hermes 发送 `/额度`、`/quota` 或自然语言问题。
2. 集成包构造 `FeishuCallerContext`，验证后映射为渠道无关 `AccessContext`，完成主体与能力范围授权；缺失上下文时拒绝。
3. 私聊中的授权操作者可收到允许主体/能力的确定性明细；群聊不读取任何额度投影，只返回固定的私聊引导，状态与刷新均关闭。
4. 用户发送 `/刷新` 触发有副作用的刷新命令，执行持久化幂等、限流和审计后直接返回结果。
5. 自然语言问题默认不触发额度工具；只有显式开启后才允许 LLM 获取最小汇总投影。

### 12.1 Hermes 网关能力核验

2026-07-17 对本机 Hermes Agent v0.13.0 的源码核验表明：

- 飞书适配器已注册 `card.action.trigger`。
- 普通卡片点击会被转换为 `/card ...` 合成命令并进入 Hermes 消息处理链。
- 飞书适配器具备更新既有消息的底层方法。

因此，网关并非完全缺少卡片回调能力；但“额度卡片按钮 → 刷新 Provider → 更新原卡片”仍不是现成的安全闭环。当前通用去重只是短命进程内缓存，不能抵抗进程重启或超时重放。阶段 3A 必须完成持久化幂等设计后才允许按钮刷新；Spike 未通过时保留经过同等授权的 `/刷新` 指令路径。

### 12.2 调用者授权与卡片幂等

- 飞书事件的 `operator.open_id`、`header.tenant_key`、`header.app_id`、`header.event_id`、`context.open_chat_id` 和 `context.open_message_id` 必须从 SDK 解码后的受信任事件对象读取，并与本地允许列表匹配。
- 卡片 `value` 只携带服务端生成的 opaque `action_id` 和 subject/capability 引用；二者必须使用本地密钥签名，并绑定原租户、应用、会话、消息、动作、主体和能力。客户端提供的引用不能扩大 `AccessContext` scope。
- action 的唯一有效期、数据库 UTC 边界、幂等记录删除不变量和 active/verify-only key 保存窗口只引用[安全模型第 11 节](security-model.md#11-飞书卡片重放与动作绑定)的 `ACTION_TTL`；集成包不得自定义更长 TTL。超界或已过期 action 即使签名正确也在幂等/Provider 前拒绝。
- 每次按钮动作必须在执行网络请求前，事务性写入唯一键 `(event_id, operator_id, tenant_id, app_id, chat_id, message_id, action, subject_id, capability_id)`。缺少任一字段、签名过期/不匹配或唯一键已存在时拒绝再次执行，并返回已保存的安全结果状态。
- 为防止攻击者替换 `event_id` 后重放同一按钮，`action_id` 也必须单次消费；卡片成功更新后签发新的 `action_id`。若 Provider 已刷新但卡片更新失败，幂等记录保存安全结果摘要与 `delivery_state=update_failed`，相同事件只返回该状态、不再次访问 Provider；旧按钮保持失效，用户通过受同等授权的 `/刷新`/`/额度` 获取新卡或由系统重发新卡。不得为了可用性重新激活已消费 ID。幂等记录使用 `RET-IDEM-FEISHU-CARD`，只保存假名化关联，不保存完整回调体。
- 授权和幂等必须在刷新、缓存修改和失败计数更新之前完成。授权失败不触发 Provider、不得泄露主体是否存在。

建议卡片内容：

- 顶部：正常、部分失败、全部不可用的汇总。
- 私聊明细中的每个主体：Provider、订阅/工作区别名及其窗口、余额或计数能力。
- 辅助信息：上次成功时间、下次重置时间、数据来源类型。
- 异常区域：凭据失效、请求限流、数据过期，但不展示密钥或完整响应。
- 群聊不发送额度卡片；只返回固定的“请私聊机器人查看额度状态”，不查询或展示任何额度衍生字段。

如果未来需要在手机或外部网络直接打开完整 H5 面板，再单独设计带认证的 HTTPS Relay。第一版不把本地服务直接暴露到公网。

## 13. Desktop GUI 产品方案

Desktop GUI 是统一观察与本地配置台，也是 MVP 主入口。React/TypeScript renderer 只消费 Tauri command 返回的脱敏 DTO，不消费 FastAPI、不读取文件、不接触 CredentialRef 实值。所有写操作先由 host 映射为冻结的 RequestedOperation，再进入同一 application service。

### 13.1 必备用户流程

1. **首次启动**：验证 app/sidecar 签名与 installation registry，显示本地数据/Provider 网络披露说明；用户选择“开始配置”或“离线浏览示例”。权限失败进入可恢复诊断页，不静默放宽目录或凭据权限。
2. **凭据引用**：macOS MVP 的 `system-credential` backend 固定为 Keychain。renderer 只能请求 `credential_dialog_open`；Rust host 在 WebView 之外打开 host-owned native secure dialog，由原生 secure field 接收 keystroke/paste 或选择既有 Keychain item，完成导入和缓冲区清零后只把 opaque reference/status 返回 renderer。React/DOM/Tauri command payload 永远没有 secret input/value/length/SecretBuffer 路径；也可选择不含秘密输入的已批准 official-cli profile。
3. **账户与 Subject 配置**：向导按 Adapter profile 创建 principal，调用 discovery 后由用户明确确认 subject/capability；未确认前不落入 active registry。OpenRouter 展示 current-key 范围；Codex 卡片固定 `Experimental / Incompatible / Disabled`，解释缺 stable identity，不提供“立即启用”或正式刷新按钮。
4. **额度总览**：显示 principal/subject、能力分区、值、unit、source、`fetched_at`、fresh/stale/expired、health 与 safe error。窗口/计数/余额/状态按 kind 分区；多币种不求和，跨类型只按 severity 排序。
5. **手动刷新**：可按授权 scope 刷新全部、subject 或 capability；进入 running 后禁用同幂等键重复动作，显示排队/进行/部分完成/失败。取消只请求取消，不能伪造 Provider 未调用；结束后从 core 重新读取投影。
6. **离线模式**：显式切换后 application service 使用 `network_mode=offline`，Credential Source/Provider/network/subprocess 计数为 0；展示缓存/LKG 的真实 freshness，不能把 stale 改写为 current。
7. **后台刷新状态**：只有 SchedulerHost 已安装且 heartbeat/lease 健康才显示最近/下次后台运行；否则固定显示“仅按需刷新”，关闭后台告警承诺。失联立即降级，不沿用旧绿色状态。
8. **重新认证**：auth error 提供 source-specific 指引；Keychain replacement/official CLI 重登后必须生成新 credential generation、重新 probe，并隔离旧 cache/LKG。renderer 不接收上游 Token、Cookie、stdout 或 identity evidence。
9. **导出与清除**：导出默认只含脱敏配置/诊断，不含 credential、identity evidence、LocalKey、SQLite/WAL/SHM 或精确机密值；需要额度数据的导出必须再次确认范围。清除时，Rust host-owned native surface 显示 core 生成的 purge plan 和不可保证删除项并捕获 user presence；plan digest/nonce/token 只在 host↔core，renderer 只收到 cancelled/committed/status且不能提交任意路径。

### 13.2 状态、错误与可访问性验收

- **loading**：使用骨架与明确文本，禁止把旧卡片当新结果；超过本地 1 秒显示当前 stage，不显示上游原文。
- **empty**：区分“未配置账户”“已配置但未发现 subject”“scope 无授权结果”；每种只提供对应安全动作，空集合不回退全量。
- **partial failure**：成功 Provider 与失败 Provider 同屏分区，每项保留自己的 freshness/health；总览不得用单一绿色掩盖失败。
- **total failure**：保留当前 generation LKG 的 stale/expired 标签；无 LKG 显示安全错误、doctor/reauth 路径，不崩溃、不伪造零额度。
- **Codex**：任意页面均显示 Experimental、默认关闭、不计 MVP，identity 未获批准前 `Refresh` disabled；不能只在设置页藏说明。
- **键盘与读屏**：全部流程只用键盘可达；焦点顺序确定，刷新后焦点不丢失；状态变化使用受控 `aria-live`，图表有等价文本/表格，颜色不是唯一信号，目标 WCAG 2.2 AA。
- **显示与隐私**：支持 200% zoom、reduce motion、高对比度和本地 IANA timezone；默认遮蔽邮箱/外部 ID，复制按钮只复制当前授权投影，不复制隐藏字段。
- **E2E**：在全新 macOS 用户、无网络、Keychain locked、sidecar crash、upgrade rollback、slow/partial Provider 和 Scheduler absent/unhealthy 场景逐项截图+accessibility tree+core trace 验收；trace 只能含安全枚举/假名化 ID。

## 14. 告警设计

schema v1 的 `alert_policies` 支持按 capability/metric 配置：

- `window_used_percent`：百分比 warning/high/critical，示例默认 70%、85%、95%。
- `reset_pressure`：距离已知重置时间不足 `within_minutes` 且已使用超过 `min_used_percent` 时，产生策略必填的 `severity`；示例为 30 分钟、80%、`high`。`reset_time_status != known` 时必须抑制，不得参与 severity、通知或“即将重置”文案。
- `balance_floor`：按指定币种的绝对余额下限告警，不跨币种换算。
- `counter_remaining`：按 capability unit 的剩余计数下限告警。

满足任一已配置策略即可告警，并对同一窗口做去重和冷却。统一严重度顺序为 `none < warning < high < critical`；同一 capability 同时命中多个 tier/策略，或数值策略与 health 错误同时存在时，一律取最高值用于排序、渠道投影与通知。没有匹配策略且 health 正常时为 `none`。另支持以下与数值阈值分离的事件：

固定状态映射也属于 schema v1 契约：`fresh=none`、`stale=warning`、`expired=high`；`health=ok|unsupported` 为 `none`，`rate_limited|network_error|provider_error` 为 `warning`，`incompatible` 为 `high`，`auth_error|schema_changed|semantic_suspect` 为 `critical`；本地 `not_authorized` 没有快照/severity。status capability 的 `StatusValue(available)=none`、`StatusValue(insufficient_balance|rate_limit_reached)=high`、`StatusValue(credits_depleted|usage_limit_reached)=critical`。最终 capability severity 是所有命中 alert policy、freshness、health 和已登记 status 映射的最大值；实现和渠道不得自行覆盖。

- 短周期额度即将耗尽。
- 周额度即将耗尽。
- 凭据失效或需要重新登录。
- 连续多次无法获取数据。
- 额度已经重置，可恢复使用。

告警只通知，不触发自动切换。只有安装 SchedulerHost 时才会后台产生告警；独立 daemon、系统通知、Hermes/飞书或 Webhook 都是可选宿主/渠道。

通知状态与 severity 计算分离，并以 SQLite 事务持久化。唯一 episode 聚合键为 `AlertAggregateKey=(principal_id, subject_id, capability_id, query_contract_generation, window_identity)`；已知重置窗口的 `window_identity=(duration_minutes,resets_at)`，无已知重置时间时使用 generation 内稳定的 `non_resetting`，不得生成 reset 事件。policy source ID 必须编码 metric+dimension；freshness、health 和 status 也只是按 source ID UTF-8 bytes 排序的 immutable `contributing_sources: tuple[tuple[SourceId,Severity], ...]`，**不得进入 episode 身份**。一次独立恶化使用 `AlertEpisodeKey=(AlertAggregateKey, episode_id)`，其中 `episode_id` 是该 aggregate 在 SQLite 事务中分配的单调整数。单个 episode 的状态只允许 `open→acknowledged→resolved`；`resolved` 是终态，之后再次恶化必须原子创建 `episode_id+1`，不能复活旧 episode。

- 每次评估在一个 SQLite 事务内重算全部 `contributing_sources`，聚合 severity 取最大值，并原子更新 aggregate 当前活跃 episode 指针。最终 severity 从 `none` 首次升为 warning/high/critical 时只建立一个 `open` episode并通知一次；同 episode 只有聚合 severity 升级可立即再通知。两个 policy 加一个 health 同时命中仍只有一个 episode/一条最高级通知。
- 单个来源清除只更新明细；只要任一来源仍为 warning/high/critical，episode 不得提前 resolved。全部来源都变为 `none` 时，活跃 episode 才转 `resolved` 并最多发一次恢复通知；不要求 `health=ok`，因此 `fresh+unsupported` 可关闭旧 health 告警。
- acknowledgement、cooldown、最后投递时间和 `notification_sequence` 全部属于聚合 episode，而不是某个 policy。cooldown 从该 episode 最后一次实际投递开始，默认 60 分钟且 manifest/policy 只能设得更保守；相同 snapshot 重放、聚合降级或冷却期内不重复通知。唯一约束 `(AlertAggregateKey, episode_id)` 与 aggregate 当前活跃 episode 指针保证双宿主不能创建两个相同 episode。
- 只有旧窗口 `resets_at <= fetched_at`、新窗口 identity 更晚、fresh+ok 且用量回落到阈值下，才能把全部来源清除后的恢复分类为“额度已重置”；`timezone_unknown/not_provided`、stale/expired、单纯 LKG 消失或余额 capability 永远不能生成 reset。
- principal/subject/capability disable/delete、`manifest_removed` 或 query generation 切换时，同一事务把受影响活跃聚合 episode 以 `terminal_reason=object_inactive|generation_replaced` 标为 resolved，不发送“额度已恢复/重置”；新 generation 的同类告警从 episode 1 的新 aggregate 开始。
- SchedulerHost 使用数据库唯一 lease `(deployment_id, alert_dispatcher)` 和 fencing token；同一时刻只有持有者可投递。两个宿主、lease 过期接管和投递后提交前崩溃使用稳定的 `AlertEpisodeKey + notification_sequence` 作为 channel delivery id 去重；不能提供幂等投递的渠道采用 at-least-once 并在 UI 明示，core 聚合 episode 仍只生成一次。

虚拟时钟 golden 测试覆盖 `open→resolved→open→resolved`（第二次恶化只产生一个新 episode）、balance/non-resetting、已知窗口、多 tier/多 policy、health+numeric、`fresh+unsupported`、重复 snapshot、重启、窗口轮换、未知时区、LKG stale/expired、disable/delete/generation 切换、两个 SchedulerHost 和 lease 接管。

alert aggregate/episode/contributing sources/notification delivery 的保存、terminalization、对象删除和 key 依赖只引用安全模型的 `RET-ALERT-ACTIVE/RET-ALERT-TERMINAL`；本节不得给另一组期限。LLM consent 的 active、到期/撤销 tombstone、generation 重建和对象删除同样只引用 `RET-CONSENT-ACTIVE/RET-CONSENT-TOMBSTONE`。

## 15. 安全与隐私

进入阶段 1 前只要求 [安全模型](security-model.md) 的 0A 核心门禁关闭；Hermes/飞书的 3A 集成门禁只阻塞对应可选包。该文档定义资产分级、部署 profile、授权、网络出口、存储保留和集成安全；本节只列摘要。

### 15.1 凭据处理

- 凭据读取与 Provider 查询分离，通过 `CredentialSource` 引用现有凭据，不由适配器直接扫描整台机器。
- Desktop profile 首选官方 CLI、macOS Keychain opaque reference 或 core 支持的显式环境变量。`hermes-env`/`hermes-auth` 只由 `agent-quota-hermes` 注册，默认包不读取 `~/.hermes`。
- 环境变量仅作为兼容方案，`.env` 已加入忽略规则。
- `system-credential` 在 Keychain/Secret Service、D-Bus 会话或受审查 backend 不可用时返回 `credential_backend_unavailable` 并 fail closed；不得静默改读环境变量、文件或其他 CredentialRef。用户若接受环境变量风险，必须显式修改配置为 `env:`。
- API Key 不写入 SQLite、日志、前端状态、飞书消息或异常追踪。
- renderer 不接收 API Key、OAuth/Cookie、CredentialRef 实值、identity evidence、LocalKey 或 Provider transport；macOS secret entry 完全属于 host-owned native dialog，React 只能请求打开 dialog 并接收 opaque reference/status。dialog 仅在 foreground/key window 打开，每 installation 同时最多一个且受 host cooldown 约束。负向门禁 `renderer-secret-input-path-absent` 必须证明 DOM/event/state/prop/command/IPC schema 不存在 secret keystroke、paste、value、length 或 buffer 字段。
- purge、disable/delete/cascade 与 endpoint/auth/binding/capability/manifest destructive diff 的脱敏 plan 只显示在 host-owned native confirmation surface；renderer 不接收 plan/digest/nonce/user-presence token，只接收 cancelled/committed/status。负向门禁 `renderer-destructive-confirmation-token-absent` 覆盖 command schema、bundle 和 host→renderer DTO。
- 日志禁止记录原始响应、Authorization 或 Cookie；白名单诊断字段仍必须移除账户 ID 等机密值。
- Desktop TCB 只包含 OS 用户、已签名 host/core sidecar、系统 secret store/本地数据服务与启用的内置 Adapter；renderer 不在业务授权 TCB 内。Hermes profile 额外包含 Hermes 及全部已启用插件。Hermes 同 uid 插件可直接读机密数据库与本地假名化密钥，`CredentialRef`、文件权限和同 uid 可读的数据库加密都不是插件隔离边界。
- 每个要达到 `supported` 的 Adapter，其凭据、协议和刷新流程必须在 [Provider 与凭据契约](provider-contract.md) 中通过评审；未完成者不阻塞 core，但保持 Experimental/关闭。

### 15.2 网络边界

- 每个 Provider 固定 `https` 域名、端口、方法/路径或本地 RPC 允许列表，不接受用户任意 `base_url`。
- `httpx` 客户端强制 `trust_env=False`、`follow_redirects=False`、TLS 校验、超时与响应大小上限；schema v1 Provider HTTP 仅 GET 且代理恒关闭，没有启用分支。
- Codex 只保留离线 app-server schema/allowlist/parser fixture；当前运行态不启动真实 Codex CLI，不发送初始化握手、`account/rateLimits/read`、`account/read` 或任何读写 RPC。
- Desktop MVP 禁止 FastAPI/HTTP/WebSocket/Unix socket 和 loopback listener；renderer 的 `connect-src` 为 `none`，只能调用显式 Tauri command。
- 远期 Web 是独立 surface；即使只监听 `127.0.0.1` 也必须启用令牌/会话认证、Host/Origin 校验、严格 CORS 和 CSRF 防护。监听地址不是普通配置项。
- 若未来增加远程访问，必须先实现身份认证、TLS、最小权限 Token、撤销机制和访问审计。

### 15.3 数据与输出边界

- 余额、额度、使用率、计划、账户别名、认证状态和重置时间均为机密账户数据；SQLite、WAL、备份、日志和飞书展示都执行对应控制。
- Hermes profile 的 `/额度`、`/quota`、`/刷新` 使用确定性模板直接返回，不进入 LLM 或 Hermes 通用工具钩子。
- 自然语言工具默认关闭；显式、限时同意后只返回受 actor/scope 与 deployment/scope 双层频率限制的 `llm_minimal` 投影。每次调用重新校验 consent generation/范围/到期/撤销，既有会话在撤销后立即失效；文档和 UI 必须说明跨时间采样仍会泄露使用趋势。
- 上游消息、错误正文和未知字符串不得原样进入 LLM、日志或飞书；只允许本地状态码与白名单参数进入经过转义的模板。
- principal/subject/capability 的 disable/delete/manifest removal 严格按第 10 节生命周期矩阵事务处理；快照、审计、各渠道幂等与刷新 ledger 全部只引用安全模型第 10.1 节对应 `RET-*` 条目。启用期间的结构/语义基线与调度元数据不随快照到期重置。

### 15.4 开源边界

- 仓库只提供适配器代码和虚构示例，不提交真实响应样本。
- 真实余额、使用率、账户别名、模型路由组合和本机审计结果只保存在本地、不入库的记录中。
- 每个适配器说明其接口性质、所需权限和潜在稳定性风险。
- 对逆向或非公开接口进行隔离，默认关闭，并明确遵循供应商条款是使用者责任。

## 16. 建议仓库结构

```text
agent-quota/
├── README.md
├── pyproject.toml                 # workspace / meta distribution
├── justfile
├── LICENSE
├── config/
│   └── agent-quota.example.toml
├── docs/
│   ├── design-proposal.md
│   ├── provider-contract.md
│   ├── security-model.md
│   ├── contracts/                # versioned machine authority + isolated fixtures
│   └── audits/                   # immutable audit history + current resolution
├── packages/
│   ├── core/src/agent_quota_core/
│   ├── cli/src/agent_quota_cli/
│   ├── provider-deepseek/
│   ├── provider-openrouter/
│   ├── provider-codex/
│   ├── testkit/                    # 独立测试发行物，不进入生产依赖闭包
│   └── hermes/                    # 独立发行，不被 core/cli 依赖
├── desktop/
│   ├── src-tauri/                 # Rust trusted host、capability 与 sidecar supervisor
│   └── renderer/                  # bundle-only React/TypeScript，不含网络/文件权限
├── integrations/
│   └── scheduler/
├── web/                           # 远期可选 surface，不属于 Desktop GUI
└── tests/
    ├── contracts/
    └── fixtures/
```

配置/数据路径由 `platformdirs` 决定，仓库只提供 `schema_version=1` 的虚构示例。真实密钥留在官方 CLI、系统凭据存储、显式环境变量或可选 Hermes Credential Source 中。

当前仓库内容仅有 `README.md`、三份设计/安全文档、版本化文档合同、审计/处置记录和安全忽略规则；Desktop 应用、发行包与测试树均尚不存在。上述结构是待阶段 0A 门禁关闭后的设计，不是实现事实。

## 17. 开源建议

- 目标许可证采用 MIT。
- 在 README 中说明设计受 CC Switch 的 Provider 用量查询思路启发，但不复制其代码或品牌资产。
- core、CLI、内置 Adapter、Provider Contract 与构建配置保持开源。
- 供应商适配器使用合约测试，脱敏 fixture 只保留字段结构。
- 每个 Pull Request 至少验证：macOS Desktop build/E2E、Python core/CLI 的 macOS/Linux 类型检查与测试、wheel/sdist 构建、干净环境安装、配置迁移、凭据泄露扫描和 Adapter 错误处理；Linux core CI 不代表 Linux Desktop 已支持。
- GitHub 远程仓库在内部 MVP 验证稳定后再创建并公开，避免 PoC 期过早承担兼容承诺。

## 18. 分阶段实施建议

### 阶段 0A：Desktop 与核心设计门禁（当前）

- 冻结 `AccountPrincipal → QuotaSubject → QuotaCapability → CapabilitySnapshot`、判别联合不变量和渠道无关 `AccessContext`。
- 冻结 `schema_version=1`、严格校验、迁移规则、AdapterManifest/probe、生命周期状态和发行依赖方向。
- 评审 Desktop host/renderer/sidecar TCB、匿名管道 IPC、u64 session request ID、stderr null sink、Tauri capability/CSP、host-owned credential/destructive confirmation surfaces、签名升级、POSIX 存储权限、保存/删除、Provider 出口和 HTTP 流式响应上限。
- 冻结 DeepSeek、OpenRouter 与 FakeAdapter 的阶段 1A/1B 契约；Codex 以 `experimental/incompatible` 默认关闭，Kimi/MiniMax/GLM 只有 `planned/no-contract` 路线图记录。
- 运行 secret/PII 扫描，确认仓库只有虚构示例。

### 阶段 1A：Desktop 主壳与独立内核 PoC

- 同时实现 Tauri trusted host、bundle renderer、Python application service/core sidecar、辅助 CLI、opaque 配置 ID、版本化配置、AccessContext/AccessIdentity、确定 severity 合并、Capability 缓存和 FakeAdapter。
- 用 FakeAdapter 覆盖：同 Provider 多 principal、同 principal 多 subject、同 subject 多 capability、多币种余额、上游 unsupported/not_entitled observation，以及本地 not_authorized OperationError。
- 用三份纯虚构配置验证 DeepSeek-only、OpenRouter-only 和混合订阅视图；另验证 Codex 实验卡片固定 incompatible/disabled 且 Provider 调用为 0。
- 实现按需刷新、分离的 cache identity/rate-limit cohort、完整缓存/singleflight/限流键、last-known-good、失败状态和安全消息映射。
- 构建签名 Desktop app、core/CLI/testkit wheel 与 sdist；验证 renderer command allowlist、foreground/single-active/cooldown host-owned credential/confirmation surfaces、`renderer-secret-input-path-absent`、`renderer-destructive-confirmation-token-absent`、u64 session request ID、stderr null sink、sidecar pin/framing/crash recovery、首次启动/配置/总览/刷新/offline/reauth/export/purge 和所有空/加载/部分/全部失败状态。
- 不实现 SchedulerHost、Hermes、飞书、FastAPI 或远期 Web；无 Scheduler 时固定显示“仅按需刷新”。

### 阶段 1B：首批受支持 Adapter

- DeepSeek：验证官方多币种余额、固定出口和流式响应上限。
- OpenRouter：验证官方 `/api/v1/key`、Bearer、current-key limit/remaining/usage/expiry 与 `creator_user_id` observed metadata 矩阵；`creator_user_id` required nullable，缺失/错型拒绝且 null 表示无 metadata；`expires_at` optional nullable，覆盖 absent/null/RFC3339/错型；limit 两字段覆盖双 null、finite pair、nullability mismatch、负值和 remaining 大于 limit。API key binding+credential generation 决定 access/cache identity，`creator_user_id` null/变化不改变 identity/cohort，endpoint/deployment conservative group 不因复制 principal/binding 扩容；不默认请求 management key 或 `/credits`。
- DeepSeek/OpenRouter 只有通过真实 opt-in 合约测试、签名发行与 Desktop E2E 后才能升为 Supported；两者都达到 Supported 才满足 MVP 数量。
- Codex 继续保留只读 app-server allowlist，但不新增 `account/read`、不执行正式 fetch、不持久化 cache/LKG。未来改变必须是新的显式用户决策与合同版本，不是 1B 退出条件。
- Kimi、MiniMax、GLM 只有在版本化升级同时提交协议证据、auth/region、capability、NetworkPolicy、时区语义与脱敏 fixture 后才从 `planned/no-contract` 进入 Experimental，不是 1B 的退出前提。

### 阶段 2：macOS Desktop MVP 发布

- 发布签名/notarized Agent Quota Desktop、随包 runtime/sidecar、辅助 meta distribution、CLI 与首批 Provider 包；默认安装不包含 Hermes、Scheduler、Codex 或 Web。
- 在 macOS 干净 VM 完成 DMG/App 安装、首次启动、Keychain、配置、doctor、组合查询、迁移 dry-run、原子升级/回滚、卸载与 purge 验收。
- 至少两个 Adapter 达到 Supported，并证明一个 Provider 多身份/主体组合与多 capability 展示；Experimental 不计数。
- 默认只按需刷新；可选 daemon/SchedulerHost 若交付，必须独立验收其暂停、抖动和告警语义。

### 阶段 2B：Linux Desktop staged

- 仅在冻结发行格式、签名/更新根、WebView/runtime 依赖、Secret Service 锁定/无 session bus 行为、XDG root、sandbox 与桌面集成后交付 Linux Desktop。
- 逐项重跑 macOS Desktop 的 IPC/renderer/Provider/升级/无障碍矩阵；Python core/CLI 已能在 Linux 运行不能替代本门禁。

### 阶段 3：可选 Hermes 与飞书集成

- 先关闭 3A 集成门禁：FeishuCallerContext → AccessContext、ConsentContext 逐调用校验、插件 TCB、群聊零额度披露、确定性命令路径、最小 LLM 投影和持久化重放。
- 发布独立 `agent-quota-hermes`，不改变 core/CLI 的依赖闭包。
- 文字命令/静态卡片先交付；按钮刷新必须通过签名 action、重启/超时重放和越权测试。

### 阶段 4：可选远期 Web 与开源发布

- 根据 Desktop MVP 与集成使用证据决定是否增加独立 FastAPI/Web surface；不得复用 Desktop renderer/IPC 认证。
- Web 与认证、Host/Origin、严格 CORS、CSRF 同时交付。
- 补充 SDK/Provider 开发指南、CI、Issue 模板和贡献指南；内部 MVP 稳定后公开 MIT 仓库。

### 阶段 5：扩展能力

- 根据真实消耗数据评估 `quota_recommend`。
- 第三方 Adapter 隔离、远程访问和自动切换分别立项，不复用查询授权。

### 18.1 可复现性能门禁

“全量查询小于 10 秒”只指以下固定 cold-cache 基准，不外推到无限配置：

- macOS CI runner 至少 2 vCPU/4 GiB；已完成 config validate/probe，计时范围从 Desktop `refresh(all)` command 进入 host 授权开始，到 renderer 收到确定性投影 DTO 结束，包含 IPC、credential resolve、排队、Provider I/O、校验、事务提交和投影；辅助 CLI 另跑同一 use case parity。
- fixture 为 4 principals、8 subjects、16 capabilities、最多 4 个上游批请求；全局并发 4、每 Provider 并发 2。三个 fake endpoint 延迟 150 ms，一个延迟超过 per-attempt deadline；每次运行清空 capability cache 但保留配置。
- deadline 只引用第 8 节 `TransportDeadlinePolicy`：HTTP queue/attempt/aggregate 为 1/6/9 秒；local-stdio 为 1/8/9 秒，内部 3 秒握手、6 秒 request、7.5 秒 execution 与 0.5 秒 TERM→KILL/reap。排队计入 9 秒 aggregate。到期后 Adapter 返回覆盖其完整 request keys 的 batch failure，由 core 合成 stale/expired 部分结果；不阻断其他请求，不留下后台 task/orphan。
- 独立进程运行 30 次，以单调时钟统计，p95 必须小于 9.5 秒且每次硬上限小于 10 秒。超过 4 个上游批请求的配置不承诺固定 SLA，估算按各 endpoint 的 manifest attempt policy 计算并仍执行 9 秒单次 aggregate deadline/部分结果语义，不再硬编码通用 6 秒。

## 19. MVP 验收标准

- 在无 Hermes、无源码 checkout/用户 Python 的全新 macOS VM 验收签名/notarized Desktop app：renderer/host/sidecar pin、匿名管道 IPC、单实例、Keychain、首次启动、升级/回滚/退出回收全部通过。另验收 wheel、`--no-binary :all:` sdist 和 testkit；签名 wheel 全部匹配才可加载 Supported/GA，sdist 派生 Provider 稳定 `adapter_not_distributable`。生产闭包无 FakeAdapter/testkit，core import graph 不含 Tauri/React/Hermes/FastAPI。
- `schema_version=1` 能严格验证、dry-run 与 journal 协调升级；记录 ID 必须为 core 生成的 opaque ID，未知字段、未来版本、secret-like/歧义 ID、重复/悬空引用与未声明 capability 会拒绝。普通删除/禁用有引用时零写入，cascade 必须复用已确认 plan digest。TOML/SQLite 各崩溃点重启只 roll-forward 到同一完整新态。
- 外部 TOML drift 只有冻结的纯展示集合可自动采用；任何 destructive diff 在相同 plan digest + 一次 nonce 确认前保持服务 gate 关闭、active config/generation/运行表零变化且 Provider 调用为 0。确认后 crash/restart 只重放同一 action 集，再次编辑使 digest 失效。
- schema v1 的判别式 `alert_policies` 与完整 WindowValue 联合不变量通过 property/golden 测试；多策略/tier/health/status 固定取最高级，未知时区不产生时间类 severity/告警。同 dimension 的告警能 `open→resolved→open→resolved`，第二次恶化只创建一个单调 episode。
- 能配置并展示同 Provider 多 principal、同 principal 多 subject、同 subject 多 capability，以及零/多个 Credential Binding；DeepSeek-only、OpenRouter-only 与混合命名视图只显示各自引用，Codex 实验视图固定 incompatible/disabled。P_A/P_B 与 S_A/S_B 完整交叉矩阵证明父 principal 不匹配、禁用/删除引用、伪造 view 与空 scope 均为 `not_authorized`，且不读缓存、不调用 Adapter、不更新计数。
- 能无损表示滚动窗口、计数、CNY/USD 多币种余额、DeepSeek `available/insufficient_balance`，以及 `unlimited/unknown/not_applicable/unsupported/incompatible`。
- FakeAdapter 完成组合矩阵测试，DeepSeek 与 OpenRouter 都达到 `supported`；OpenRouter 在真实门禁前只是 candidate，Codex 与其他 Experimental/默认关闭 Adapter 永不计数。
- OpenRouter `/api/v1/key` 的 origin/method/path/Bearer/trust_env/redirect/TLS/64 KiB/deadline 与所有 required/optional/null/错型/bounds/error fixture 通过；API key binding+credential generation 决定 cache/access identity，`creator_user_id` required nullable且 null/变化均不改变 identity/cohort，rate cohort 恒为 endpoint/deployment conservative group。`expires_at` absent/null/string 分别显示 unknown/not supplied、no expiration、known expiry；只有 `limit=null && limit_remaining=null` 显示 per-key unlimited，finite pair 满足 `0 <= remaining <= limit`，nullability mismatch fail closed，且从不冒充账户余额；MVP 不要求 management key 或 `/credits`。
- AdapterManifest/probe 能在刷新前解释 adapter、ordered/versionless ProtocolContract、canonical schema hash、release assurance、publisher attestation、认证变体、地区、协议不兼容、封闭缺失 capability、只读方法集和 AccessIdentity assurance；通用 loader 独立校验 plan/label/currency/status/display/semantic/network 引用闭包，offline 验证零凭据/网络/子进程，discovery 只返回调用级 DTO。零 binding official-cli 无 verified stable 身份时 fail closed。
- 单个 Provider 失败不会阻断其他结果。
- 所有结果包含获取时间、状态和数据来源。
- 所有时间以 UTC 存储，展示使用 IANA PresentationContext；UTC/上海/洛杉矶/DST 结果确定，缺失或非法 zone 明示 UTC fallback；未知上游时区不会被静默猜测。
- 固定 cold-cache 基准按第 18.1 节运行 30 次，p95 小于 9.5 秒且每次小于 10 秒；慢 Provider 在 9 秒全局 deadline 内被取消并返回部分结果，无后台 orphan。
- auth/network/rate-limit/provider/schema/semantic/local-protocol/local-timeout 的计数、第三次动作、Scheduler/on-demand probe/fetch 和恢复事件逐类严格符合 Provider 契约第 9.4 节唯一表；交错类别互不误清。无 SchedulerHost 时明确显示“仅按需刷新”，不承诺后台告警。
- Capability 缓存不会跨 `(adapter_id, principal_id, subject_id, capability_id, cache_identity, query_contract_generation)` 复用；网络 singleflight 不会跨 principal、访问代际、查询合约代际、endpoint、请求类型或规范化 subject/capability selector 合并。刷新预算按 core 生成的 `rate_limit_cohort` 聚合，复制 principal/binding 不会增加次数。
- 并发不同 principal 时，共享连接池、Cookie jar 或 Adapter 状态不会串用认证材料或结果。
- ProbeContext/DiscoveryRequest/FetchContext 不可变并显式绑定 seed/selector、canonical CredentialLease/零 binding proof、AccessIdentity、endpoint spec 与 deadline；DeepSeek fake transport 只靠 context 完成请求，越 scope selector 在 Adapter 前拒绝，lease metadata/proof 不进入 repr/序列化/日志。
- 非公开接口发生结构漂移时，返回旧数据的 `stale + schema_changed` 或无旧数据的 `expired + schema_changed`，不会使聚合进程崩溃。
- 路径和类型未变但单位、缩放或数量级触发 Provider 语义 canary 时，返回 `stale/expired + semantic_suspect` 且不覆盖 last-known-good；低值与跳变 fixture 覆盖误报恢复。
- 只有相同 capability kind/unit 可数值排序；跨类型按 severity/display order 排序，多币种不求和。
- 凭据不会出现在 renderer/IPC/CLI/API 返回、缓存、配置迁移日志或默认日志中；renderer 无文件/网络/shell/sidecar/secret-input capability，`renderer-secret-input-path-absent`、CSP/导航/外链攻击矩阵通过。credential dialog 的 foreground/key-window/single-active/cooldown/spam 测试通过。
- renderer 无法读写 destructive plan/digest/nonce/user-presence token；purge、disable/delete/cascade 与 endpoint/auth/binding/capability/manifest destructive diff 只有 host-owned native confirmation surface 的真实 user presence 才能提交，`renderer-destructive-confirmation-token-absent` 及伪造/重复/并发/失焦/plan 变化矩阵均零副作用。
- Desktop IPC 的 `request_id` 每 session 从 1 开始按 unsigned 64-bit 严格递增、response 原样回显且溢出前终止；生产 sidecar stderr 直连 OS null sink，大量原始 stderr 不阻塞、不进入日志/renderer/IPC，`sidecar-stderr-raw-output-absent` 通过。
- `system-credential` backend、Adapter 越界、local-stdio frame/timeout 分别返回封闭 OperationError，不伪造快照；错误副作用与 Provider 第 9.4 节一致。迁移 dry-run 的 stdout/stderr/日志只显示运行内类型化句柄、脱敏字段路径、操作与 plan digest，不显示原始 ID、label、selector、外部 ID 或完整 CredentialRef。
- 每个 Provider 的网络请求符合固定出口策略；Codex Adapter 无法调用 `account/read`、`account/rateLimitResetCredit/consume` 等未允许 RPC，并且没有 stable identity source 时正式 fetch/cache/LKG 写入计数都为 0。
- Codex protocol fixture 只证明 allowlist/parser 安全，不证明产品支持；任意配置都显示 `Experimental/Incompatible`，默认关闭。未来若批准 stable identity 必须新版本化决策与真实合同测试，不能沿用本轮候选资格。
- HTTP Adapter 使用 `AsyncClient.stream()` 并在读取过程中执行响应上限；超大、chunked 或压缩响应测试不会先完整载入内存。
- macOS app root 权限为 `0700`，core 状态工件及其 `-wal/-shm` companion 权限为 `0600`，CredentialRef 通过 Keychain 解析；principal/subject/capability 的 lifecycle 与 disable/delete/manifest removal 矩阵通过逐表及崩溃恢复测试。Linux Desktop staged，Windows fail closed。
- 快照值过期后，仍启用 capability 的结构/语义基线、失败计数、上次成功时间和刷新限制不会重置；macOS doctor 对系统备份排除状态给出明确提示。
- 上游消息与错误文本不能原样进入 CLI、日志或任何投影；动态对象键不会泄露到结构指纹。
- MVP 依赖随 Desktop 生命周期运行且无监听端口的本地 sidecar，但不依赖系统 daemon、Hermes、飞书、SchedulerHost 或 Web；卸载默认保留数据，GUI/CLI 显式 purge 共用路径校验、plan digest 和确认。
- 首次启动、凭据引用、账户/Subject 配置、额度总览、手动刷新、freshness/health/error、Codex Experimental、离线模式、后台刷新状态、重认证、导出/清除以及 loading/empty/partial/total failure 均通过键盘、读屏、200% zoom、reduce-motion 和 WCAG 2.2 AA E2E。
- 有 Provider 合约测试和至少一组完全脱敏的 fixture。

### 19.1 阶段 3 集成验收（不属于独立 MVP 门禁）

- FeishuCallerContext 缺失可信字段时拒绝；映射后的 AccessContext 只能查看允许 subject/capability。
- `/额度`、`/quota` 和 `/刷新` 的详细结果不进入模型上下文或通用插件钩子；自然语言工具默认关闭，缺少不可伪造 ConsentContext 时不注册，启用后也最多返回最小投影。
- Hermes profile 安装确认明确说明：所有同 uid 已启用插件可绕过 core 授权直接读取机密 SQLite/WAL 与本地关联密钥。
- 群聊不读取 quota projection，只返回固定私聊引导；机密明细只允许授权操作者私聊。`llm_minimal` 每次调用重验同意，撤销立即影响既有会话，并受 actor/scope 与 deployment/scope 双层预算限制。
- `/刷新` 具备授权、按 source type 分层限流、审计和持久化幂等；卡片绑定缺少任一事件/操作者/租户/应用/会话/消息/动作/主体/能力字段时拒绝。Provider 成功但卡片更新失败时不复活旧 action，重复事件不再次刷新并能通过命令/新卡恢复。
- 卡片 action 恰好使用安全模型唯一 `ACTION_TTL`；`issued_at <= prepared_at < expires_at` 与 `ACTION_TTL < RET-IDEM-FEISHU-CARD` 共同证明 action 到期早于幂等删除，active/verify-only key 至少保存到所签 action 最大到期时刻。虚拟时钟在 `ACTION_TTL` 与各 RET 条目的边界证明过期重放在 Provider 前拒绝。

## 20. 已采纳的决策基线

| 决策 | 当前基线 |
| --- | --- |
| 项目名 | 发行产品 `Agent Quota Desktop`；代码/包命名保留 `agent-quota` |
| 技术栈 | Tauri 2/Rust trusted host + bundle React/TypeScript renderer + Python 3.11+ core sidecar；辅助 CLI 共用 application service |
| 产品主体 | `AccountPrincipal → QuotaSubject → QuotaCapability → CapabilitySnapshot` |
| 部署边界 | 默认签名/notarized macOS Desktop、按需查询、无网络监听；Hermes/飞书/远期 Web/SchedulerHost 均为可选 |
| 集成依赖 | integration → core 单向；`agent-quota-hermes` 阶段 3 独立发行 |
| 非公开接口 | 允许，但 Experimental、默认关闭并强制断裂协议 |
| 展示比较 | 按 capability kind/unit 分区；跨类型使用固定 severity 序列，策略/health/freshness 取最高值 |
| 访问与限流身份 | cache identity 隔离结果；core 生成 rate-limit cohort 聚合上游预算；无稳定身份 fail closed/保守限流 |
| 群聊披露 | MVP 零额度披露，只返回固定私聊引导 |
| 首批验证 | Fake + DeepSeek + OpenRouter；OpenRouter 真实门禁前为 supported candidate。Codex 已降为 `experimental/incompatible`、默认关闭且不新增 `account/read`；Kimi/MiniMax/GLM 为 `planned/no-contract` |
| 支持口径 | 仅 Supported/GA 计入 MVP；Experimental 不计数 |
| 平台 | Desktop MVP 只支持 macOS；Linux Desktop staged；Windows fail closed |
| 推荐功能 | 第一版不做，阶段 5 再评估 |
| 许可证 | MIT |
| 公开时机 | 内部 MVP 稳定后再创建并公开 GitHub 仓库 |

### 20.1 进入阶段 1 前的剩余门槛

1. 关闭安全模型的 0A Desktop/core 门禁；Hermes/飞书 3A 门禁不阻塞阶段 1。
2. 冻结 opaque record ID、principal/subject/capability、判别联合与语义 canary、受限 display 参数、AccessContext/AccessIdentity 与完整缓存/请求/限流 cohort 键。
3. 冻结含确定 severity 合并的判别式 `alert_policies`、opaque ID 与类型化 dry-run 句柄的 `schema_version=1`、严格迁移、AdapterManifest/probe 和分层刷新生命周期状态。
4. 冻结 Tauri host/renderer/sidecar、共享 application service、core/CLI/Provider wheel 的依赖方向与无 Hermes/用户 Python 的干净 macOS 安装验收。
5. 完成 FakeAdapter、DeepSeek、OpenRouter 阶段 1 契约；Codex 降级决策已取得并固定 fail closed，Kimi/MiniMax/GLM 保持 `planned/no-contract`。
6. 定义 macOS Keychain/POSIX root、签名升级、IPC/CSP/command allowlist、机密 SQLite 与系统备份残留、上游安全消息、动态键/语义漂移和 HTTP 流式上限测试。

## 21. 评审清单

- [x] 问题定义覆盖当前真实使用场景
- [x] 本地优先、查询优先/副作用显式和非目标边界通过方向评审
- [x] 数据模型拆分 principal/subject/capability/snapshot，并统一 UTC
- [x] DeepSeek 多币种余额改为列表，异构 capability 排序规则已定义
- [x] AdapterManifest/probe、生命周期和版本化配置形成基线
- [x] 阶段 1 改为 Desktop 主壳 + 独立 core/application service/辅助 CLI，Fake + DeepSeek + OpenRouter 优先
- [x] Hermes/飞书移出独立 MVP，改为阶段 3 可选包与独立门禁
- [x] 签名 macOS Desktop、独立 wheel/sdist、无用户 Python 干净环境安装已定义；Linux Desktop staged
- [x] Desktop GUI 提升为 MVP 主入口；远期 Web 与 Desktop 完全分离
- [x] Tauri command allowlist、匿名管道 IPC、CSP/导航、single-instance、sidecar pin/crash/upgrade 合同已冻结
- [x] Codex 降为 Experimental/incompatible；OpenRouter `/api/v1/key` 作为第二个 Supported 目标并冻结官方合同
- [x] 按需刷新与可选 SchedulerHost 生命周期已拆分
- [x] 语义/单位漂移、确定 severity 合并、未知时区抑制与受限 display 参数已形成 0A 契约
- [x] verified AccessIdentity、跨 principal 限流 cohort、opaque 配置 ID 与脱敏迁移句柄已形成 0A 契约
- [x] Hermes 同 uid 数据面风险、假名化边界、群聊零额度披露和逐调用 LLM 同意校验已明确
- [x] MIT 与内部 MVP 稳定后公开形成基线
- [ ] 0A Desktop/core 安全模型通过评审
- [ ] schema v1、迁移与发行依赖契约通过评审
- [ ] DeepSeek/OpenRouter 固定出口、协议/identity 与多主体隔离通过真实合约测试
- [ ] 非公开接口断裂协议通过合约测试
- [ ] 阶段 3A 飞书按钮授权、签名 action 与持久化幂等端到端 Spike 通过

## 22. 第 10 轮规范性闭包

本节是 v1.6 对前文投影的收口；字段、顺序、摘要与 fixture 仍以五份机器 artifact 为准。

- 每个 schema 的所有 `type=array` pointer 必须恰命中一个 `sequence_exact` 或 `utf8_key` 策略。key tuple 按 UTF-8 bytes 比较；悬空、重复策略或相邻交换均拒绝。registry 只接受 artifact 根目录和 `schemas/` 的窄路径 grammar，并从固定 checkout root 逐 segment `openat(O_NOFOLLOW)`；dot、空 segment、重复 slash、大小写/百分号/Unicode 别名和 symlink 均拒绝。
- lease 的 ns deadline 只使用 `min_int64_ns`；数据库 UTC 与 monotonic deadline 的转换是结构化 typed AST，先做 clamped-zero ns subtraction，再 floor-divide 为 ms 并 checked-add。任何 ms/ns 混参在执行前拒绝。
- online doctor/discover 的 reserve 结果是共享封闭 union：`blocked_until|floor_not_elapsed|hourly_limit` 返回 `budget_deferred`，ledger/lease/fence/storage/transaction 失败只返回登记的 `rate_ledger_unavailable|storage_unavailable` 和 safe params；四条路径在拒绝时 Provider bytes、credential reads、cache writes 均为 0，不能落入 fatal。
- official-cli 首次 discovery/fetch 只能使用 joint identity context/response。一个 context 对应一个 reservation、一个 Provider read、一个 response；core 先验证 authorization/evidence并派生 verified identity，再比较 request digest 和 payload keys，最后原子接受。旧 `ProbeContext/DiscoveryRequest/FetchContext` 不能跨该门禁复用业务 payload。
- Codex schema bundle roots、LocalKey key-entry 状态、retention lexer precedence、cascade membership、InstallationRegistry rollback state 与 endpoint budget policy 全部采用第 1 节登记的机器合同及 fixture；实现不得另写隐式默认。
- budget 数值只存在于 versioned `BudgetPolicy`。`EndpointBudgetGroup` 唯一引用 policy，profile 只引用 group；同 group 的多 endpoint/profile、复制 principal 或 unknown→verified 切换都不能增加 floor/hour 容量。`blocked_until` 作用于 group 与 verified cohort 的 union。
- 第 10 轮时 Codex stable identity 尚是用户决策；当前决策已选择不增加 `account/read`，并将 Codex 固定为 Experimental/incompatible、默认关闭、零正式 fetch/cache/LKG。历史审计 marker 仍按当时事实保留。

## 23. 第 11 轮规范性闭包

本节是 v1.7 的人工索引；字段、顺序、投影和摘要只以 registry 绑定的机器 artifact 为准。

- 所有 online Provider 路径先冻结不含 receipt、credential lease 或 AccessIdentity 的 `*RequestPlan`，随后执行唯一 reservation 与 commit，再构造带 committed receipt 的 final context。Provider I/O 只消费 final context，并满足 `receipt.produced_at < final_context.created_at < first_provider_byte_at`。
- HTTP doctor/discover 先用 deployment conservative endpoint group reserve；成功后才解析 credential/evidence，并只能在同一 reservation row 上 check/attach verified cohort，不得增加容量、第二次 reserve 或第二次 Provider attempt。
- 六份 schema 只接受 `aq-array-order-v1`；dialect 本身由 registry schema 的 `arrayOrderMetadata` 严格定义。lease 常量使用带 type/unit 的 AST 值，所有 int64 上限与 registry 共用 `2^63-1`。
- Codex descriptor roots、operation/stage/error exact trace 与 migration cascade 字段均由 artifact 投影；`canonicalize-registry-v1.py` 只读反向验证下方投影与摘要，正文不再提供可分叉的第二份手写构造器。
- LocalKeyRing payload eager 包含全部八个 registered purpose 且每项恰一个 active；缺失、未知、零/双 active、重复代际与 key-id/salt/purpose bit mismatch 均 fail closed。retention 和 registry 内嵌路径统一为 canonical `RepoPath` 并逐 segment no-follow 打开。
- 持久化的规范声明只能来自单个 code-span record `persist:v1:<surface_id>:<operation>:<owner_id>`；record 自含唯一 inventory owner。移除 record 后的普通 prose 独立扫描，不能借同 leaf、同句或跨句 record 创建或隐藏 storage surface。
- core fixture 使用按 domain 判别的结构化 input；runner 只读取 `domain+input`，`fixture_id` 仅用于诊断。第 11 轮时未决的 Codex 产品方向现已关闭：不增加 `account/read`，保留协议安全 fixture，但产品保持 Experimental/incompatible 且不计 MVP。

### 23.1 基础只读验证闭包

本节是 v2.0 的人工索引；它不替代 registry、schema、fixture、机器 mutation 合同或独立新审计。

- `validate-contracts-v1.py` 从固定仓库根逐 segment no-follow 读取编译期 allowlist，依次执行 JSON 边界/NFC/重复键/非有限数、Draft 2020-12 meta-schema 与 instance、所有 digest pin、schema 实际枚举的全部数组策略、RepoPath、ProbeResult 判别联合、operation、lease、LocalKey、retention 与 core fixture 语义门禁；全部通过后才输出 `status=ok`。Draft 2020-12 引擎固定为 lockfile 中的 Ajv `8.17.1`。
- 历史命名的 `canonicalize-registry-v1.py` 已收窄为纯只读 verifier/renderer：没有写入参数、写入 API 或自选根目录，只反向验证 registry、artifact 投影、正文 marker 与 registry anchor。
- 五个 artifact pin 只从 registry 行生成到 `AQ-GENERATED-ARTIFACT-PINS-V1` marker；marker 还绑定 projection hash，手写值、缺项、重排或 registry 分叉均拒绝。
- 持久化声明仅接受严格 record v1 `persist:v1:<surface_id>:<operation>:<owner_id>`，其中 operation 必须是登记枚举且 owner 必须与 inventory 逐字节一致；当前九处规范性声明均为独立 record。旧格式、未知操作、跨 leaf、重复 record、owner 不匹配，以及一个 record 试图覆盖相邻多个 signal 均由 fixture 拒绝。
- 当前 checkout 中未跟踪的 validator/canonicalizer 仅可作为本轮审计证据，不能给自己建立发布信任。生产或 0A 只能使用外部固定的签名 release，或 VCS commit 加工具 raw SHA-256，并要求先前受信根授权；工具不得自 pin。
- 第 12 轮的 Codex 用户决策现已明确为降级：不增加 `account/read`、不移除安全 parser/allowlist、产品保持 Experimental/incompatible。静态规范仍需新的独立审计，不能据此宣称进入 0A 或实现完成。

### 23.2 第 14 轮原子验证闭包

本节是 v2.0 的人工索引；机器结果仍只以 artifact、schema、registry、fixture、生成 marker 与验证工具输出为准。

- live 文档与 fixture 进入同一个 retention AST 判定核心；既有非 surface 段落只允许命中 artifact 中 schema-bound 的 `(path, leaf_sha256, reason)` 精确例外，例外不允许 fixture 使用且必须逐项被当前 leaf 消耗。三份主文档分别有新增 TTL owner 与无 directive surface 反例，现有 9 个合法 directive 继续通过。
- online doctor/discover 的四条 provider path 分别登记成功向量；validator 从真实 step closure 推导 credential resolution、Credential Source call、reservation row 与 provider attempt。HTTP 为 `1/1/1/1`，`official_cli_zero_binding` 为 `0/0/1/1`，后者不得调用 Source。
- operation marker 无损绑定完整 `error_rows` 与必要 safe schema；lease expression inference 返回 type/unit/clock domain，逐 formula、逐 policy field、conversion 与四个顶层 reference 做签名闭包。boolean expiry、wall/monotonic 混用、非法 conversion 均为必拒绝 mutation。
- `run-release-gate-v1.py` 要求显式 `--root`，并在读取任意合同前验证 cwd、入口 regular-file 身份与逐段 no-follow 根句柄；它冻结 root identity、完整输入集合及其摘要，核对 manifest/lock closure、实际 Ajv 解析路径/版本/依赖树摘要，以及 Node/npm/Pandoc 的版本、可执行摘要和完整 npm package regular-file tree 摘要，随后只从冻结快照进入 clean install。
- mutation suite 的 50 个 case ID、sequence、expected verdict、case count、结果字段闭包与 results digest 均来自 `core-safety-contract-v1#/validation_mutation_contract`。每条 machine recipe 固定 canonical RepoPath、封闭判别的 JSON Pointer/text/filesystem/runtime/result locator、exact before/after state、failure class、executor ID、executor source-segment digest 与完整传递 helper call graph；外部调用以 exact symbolic callsite 进入闭包，未知动态 callable 除 literal `MUTATORS` dispatch 外一律拒绝。runner 只输出执行记录并把每个隔离 root 留给 gate；gate 自己逐段 no-follow 读取 locator，重算 source/mutated digest，重新执行 validator/release/result 判定并生成 failure class。`schema-const` 还必须逐值证明 `/properties/artifact_id/const` 从登记 before 变为 after。只改变 `save/repin/subprocess_success/observed_failure_class/recipe_path_snapshot` 任一 helper 或把 `schema-const` executor 重定向为 `artifact-unknown`，即使顶层 executor 未变且两者都拒绝，也必须使 self-test 非零；缺失、额外、重复、空结果、伪造 status、映射、locator 或实现漂移均 fail closed。
- reader 首次 no-follow 读取时冻结 bytes 与 inode/stat/长度；validator digest 只使用该 immutable snapshot，并在任何成功输出前逐文件重开复核。projection verifier 与发布门禁继承同一检查；验证期间的入口 symlink、根替换、源文件 symlink 或并发替换必须拒绝。运行时 profile 与当前 checkout 都只标记为 audit evidence，不能自授生产或 0A 权威。
- 历史 `AQ-R14-001` 与顶层 marker 只记录当轮未决态；当前已选择 Codex 降级，不增加 `account/read`、不移除安全合同，也不降低安全要求。新的 R20 审计决定设计门禁结果。

### 23.3 第 17 轮可复现证据闭包

- 所有正式验证入口先经仓库内 `runtime-bootstrap-v1.sh`：bootstrap 本身以固定相对路径、regular/no-follow 与 raw digest 进入发布输入，并显式固定外部 `/bin/sh` 信任根；CPython implementation、exact patch、ABI、platform、解析后路径、解释器与 framework 摘要以及排除 cache/site-packages 后的标准库树都必须一致。直接运行系统 Python、复制解释器、版本/ABI/platform/tree 漂移与 launcher 替换均拒绝。
- `package.json` 与 lock 只允许 `offline-npm-bundle-v1` 内五个 exact tarball；文件集合、包名/版本/路径/raw digest 与 lock `file:` resolution 完整闭合。clean replay 使用空 HOME 与空 npm cache 并强制 offline，缺项、额外项、bit drift、远程 registry URL 或 manifest/digest 分叉均拒绝。
- consent predicate 使用封闭 AST 与显式 true/false/missing/error 控制流。`llm_minimal` 执行同意检查，`feishu_private/local_detail` 仅跳过 LLM 专属 stage 而继续各自授权，缺失、未知或求值错误拒绝；literal/operator/false branch/audience truth-table 反例由 validator 执行。
- current status 只从 core artifact 生成到四份正文；第 1–17 轮 audit/resolution 的 path、raw digest、首行、issue/status 集合由 detached history manifest 重算，最新轮次与 blocker/gate 状态动态闭合。resolution 与 manifest 不自含自身摘要；删除、替换、首行伪造、回滚或单点投影漂移均拒绝。
- runtime/result mutation locator 使用 gate-owned typed serializer；字段闭包、observation command、解析后的 executable/dependency/tree、实际实体及完整结果 payload 分别进入 before/after digest，禁止用相同 failure class 代替实体证据。Markdown 编号同时校验层级、父节点、同级严格递增与本地 anchor；retention locator 额外绑定 exact normalized heading text 与 identifier，并执行 11 个结构反例。
- 上述结果仍仅是当前 checkout 的审计证据。`AQ-R18-001` 当时记录的 Codex 未决态已由当前降级决策关闭；不增加 `account/read`，保留 Codex 安全合同但默认关闭。R20 前不得宣称 Gate 0A 已通过。

### 23.4 第 18 轮启动与历史终态闭包

- 仓库内 bootstrap 是本地 `audit-evidence` checker，不是固定 launch 证明。四个 exact entry 使用固定相对路径/raw pin，替代 shell、新 entry、intermediate symlink 与 raw drift均拒绝；entry 从两个已核对 inode/stat/长度的已打开 fd 摘要并执行相同字节。但任何本地成功都固定声明外部 attestation 缺失，不能由环境变量、公开 handoff 或当前 checkout升级为生产权限。生产固定启动必须由仓库外既有信任根绑定实际解释器、已打开 bootstrap/entry 字节和运行时身份后出具不可由本地 checker自签的 attestation。
- 系统 image只由 exact Darwin release/build `25.5.0/25F84` 覆盖；其余 Python/Pandoc/Node loaded image逐项登记 canonical no-follow path、regular kind、uid/gid、mode、size、raw SHA-256与递归非系统依赖边。bootstrap 在任何 Python摘要/Pandoc解析前用 OS trust-root 工具固定 `_hashlib→libcrypto`、`_lzma→liblzma`、`Pandoc→GMP`及 Homebrew opt目标，清除调用者 loader/Python/locale环境；Python guard枚举实际 dyld image，validator用 `vmmap`核对 Pandoc/Node集合，额外或漂移 image一律拒绝。
- history manifest 自描述 `1..20` 内连续 round/kind/path/raw digest，实际读取与 snapshot 集严格由 entries 派生。latest 是 `ISSUES_OPEN` / `ZERO_ISSUES` 判别联合：前者绑定非空 issue set、FAIL verdict、resolution statuses 与可选唯一 blocker；后者只接受 `PASS_ZERO_ISSUES`、空 issue set、无 blocker、无本轮 resolution 和唯一 zero gate status。R19 即使仍 FAIL 并有 resolution、随后 R20 仅 PASS audit，也不要求修改 validator 或 release-gate 字节。
- 该轮 `AQ-R18-001` 后续由第 19 轮重新编号；当前用户已选择 Codex 降级，不加入 `account/read`，保留协议安全合同。是否关闭 Gate 0A 仍只由 R20 独立审计决定。

### 23.5 第 19 轮动态依赖、终态与预算聚合闭包

- Python dyld 与 Pandoc/Node `vmmap` 使用同一“先全量发现、后分类”语义。发现阶段不使用登记 closure 或安装前缀；只有 exact Darwin build 下 canonical `/System`、`/usr/lib` file-backed image 归系统，其他实际 Mach-O image 必须 no-follow、regular并逐项进入 path/metadata/raw digest/依赖闭包。`/Library`、`/Applications`、`/Users` 和真实临时目录与 Homebrew/local 路径同等处理。
- history external QA 按 `ISSUES_OPEN` / `ZERO_ISSUES` 分支；R20 零问题态是重复验证确定的终态固定点，不构造 R21。R20 open 明确为 `round-budget-exhausted`；resolution、非空 issue、blocker、FAIL 首行、R21、回退、自引用尝试与 marker 漂移均拒绝。
- 多 blocker retry-after 只执行 core artifact 的唯一聚合对象：在同一 `BEGIN IMMEDIATE` 与 DB UTC sample 内取 group/cohort union 全部 active boundary 的最大值减 now并按 `aq-bounds-v1` 夹取；无 active 才返回 `None`。fixture 与双进程虚拟时钟固定 10 秒仍拒绝、60 秒才 all-clear。
- `AQ-R19-001` 在不可改写的 R19 resolution 中仍显示 `BLOCKED_USER_DECISION`；审计后的当前决策源已选择 Codex Experimental/incompatible + OpenRouter 第二 Supported 目标，不加入 `account/read`。该决策记录不是 R19 历史修订，R20 仍须独立验证全量设计。

## 24. 参考资料

- [CC Switch 仓库](https://github.com/farion1231/cc-switch)
- [CC Switch：供应商用量查询设计](https://github.com/farion1231/cc-switch/blob/main/docs/user-manual/zh/2-providers/2.5-usage-query.md)
- [Hermes Agent 插件实现](https://github.com/NousResearch/hermes-agent/blob/main/hermes_cli/plugins.py)
- [Hermes Agent 安全模型](https://github.com/NousResearch/hermes-agent/blob/main/SECURITY.md)
- [OpenRouter：Get current API key](https://openrouter.ai/docs/api/api-reference/api-keys/get-current-key)（核验于 2026-07-19）
- [OpenRouter：Get remaining credits](https://openrouter.ai/docs/api/api-reference/credits/get-credits)（核验于 2026-07-19；management key required，非 MVP）
- [OpenRouter：Authentication](https://openrouter.ai/docs/api/reference/authentication)（核验于 2026-07-19）
- [OpenRouter：Limits](https://openrouter.ai/docs/api/reference/limits)（核验于 2026-07-19）
- [Hermes Agent Provider 文档](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/integrations/providers.md)
- [飞书：一键部署 Hermes](https://open.feishu.cn/document/mcp_open_tools/integrating-agents-with-feishu/overview)
- [飞书卡片概述](https://open.feishu.cn/document/feishu-cards/feishu-card-overview)
- [飞书卡片回传交互回调](https://open.feishu.cn/document/feishu-cards/card-callback-communication?lang=zh-CN)
- [HTTPX 环境变量](https://www.python-httpx.org/environment_variables/)
- [Codex app-server Rate Limits 接口](https://github.com/openai/codex/blob/main/codex-rs/app-server/README.md#7-rate-limits-chatgpt)
- [DeepSeek 官方余额接口](https://api-docs.deepseek.com/api/get-user-balance/)
- [OpenAI Usage API 示例](https://developers.openai.com/cookbook/examples/completions_usage_api)

<!-- AQ-GENERATED-CORE-PROJECTION-V1:BEGIN -->
```json
{"/codex_schema_bundle/descriptor_roots":[{"content":"canonical-json-bytes","path":"codex_app_server_protocol.v2.schemas.json","sha256_recipe":"SHA256(canonical-json-bytes)"},{"content":"canonical-json-bytes","path":"v1/InitializeResponse.json","sha256_recipe":"SHA256(canonical-json-bytes)"}],"/codex_schema_bundle/wire_schema_references":[{"json_pointer":"","root_path":"v1/InitializeResponse.json","use_id":"initialize-result"},{"json_pointer":"/definitions/GetAccountRateLimitsResponse","root_path":"codex_app_server_protocol.v2.schemas.json","use_id":"rate-limits-result"}],"/migration_graph/cascade_membership_fields":["cascade_root_semantic_key","member_semantic_key","reason_code"],"/probe_result_contract":{"acceptance_order":["bounds_and_discriminator","branch_field_cardinality","additional_properties","context_mode_match","authorization_binding_match","evidence_lifetime","forbidden_derived_identity_fields","identity_derive"],"adapter_forbidden_fields":["access_identity","assurance","cache_identity","rate_limit_cohort"],"branches":[{"additional_properties":"forbid","compatibility":["auth_required","incompatible","unavailable","unverified_version"],"identity_evidence_cardinality":"forbidden","kind":"failure","mode":["http","official_cli_zero_binding","offline"]},{"additional_properties":"forbid","compatibility":["compatible"],"identity_evidence_cardinality":"forbidden","kind":"http_success","mode":["http"]},{"additional_properties":"forbid","compatibility":["compatible"],"identity_evidence_cardinality":"exactly_one","kind":"official_cli_success","mode":["official_cli_zero_binding"]},{"additional_properties":"forbid","compatibility":["compatible"],"identity_evidence_cardinality":"forbidden","kind":"offline_result","mode":["offline"]}],"common_required_fields":["compatibility","detected_protocol_version","kind","mode"],"discriminator":"kind","invalid_verdict":"adapter_contract_violation_before_identity_derive_and_any_write","official_protocol_identity_evidence":{"access_generation_material_bytes":{"maximum":512,"minimum":1},"additional_properties":"forbid","authorization_binding_match":"exact-current-probe-context-and-manifest-generation","authorization_binding_required_fields":["principal_id","profile_id","rpc_endpoint_id","source_contract_id","source_generation"],"lifetime_rule":"now_monotonic_ns<expires_monotonic_ns<=now_monotonic_ns+60000000000","required_fields":["access_generation_material","authorization_binding","expires_monotonic_ns","source","upstream_subject"],"single_use":true,"source_literal":"official_protocol"},"schema":"aq-probe-result-contract-v1"},"/validation_mutation_contract/case_count":50,"/validation_mutation_contract/result_required_fields":["case_count","cases","contract_id","results_sha256","source_bytes_unchanged","status"]}
```
<!-- AQ-GENERATED-CORE-PROJECTION-V1:END -->

<!-- AQ-GENERATED-OPERATION-PROJECTION-V1:BEGIN -->
```json
{"/error_codes":["adapter_contract_violation","adapter_not_distributable","budget_deferred","config_unavailable","consent_expired","consent_required","credential_backend_unavailable","invalid_config","invalid_discovery_result","local_keyring_unavailable","local_process_timeout","local_protocol_violation","migration_conflict","not_authorized","projection_failed","rate_ledger_unavailable","referenced_object_conflict","storage_unavailable","unsupported_platform"],"/error_rows":[{"code":"adapter_contract_violation","operation":"discover","retryable":false,"safe_param_schema_id":"violation-code","stage":"discovery"},{"code":"adapter_contract_violation","operation":"doctor","retryable":false,"safe_param_schema_id":"violation-code","stage":"probe"},{"code":"adapter_contract_violation","operation":"doctor","retryable":false,"safe_param_schema_id":"violation-code","stage":"probe_result_validate"},{"code":"adapter_contract_violation","operation":"refresh","retryable":false,"safe_param_schema_id":"violation-code","stage":"probe"},{"code":"adapter_contract_violation","operation":"refresh","retryable":false,"safe_param_schema_id":"violation-code","stage":"provider_fetch"},{"code":"adapter_not_distributable","operation":"configure","retryable":false,"safe_param_schema_id":"none","stage":"config_validate"},{"code":"adapter_not_distributable","operation":"discover","retryable":false,"safe_param_schema_id":"none","stage":"config_validate"},{"code":"adapter_not_distributable","operation":"doctor","retryable":false,"safe_param_schema_id":"none","stage":"config_validate"},{"code":"adapter_not_distributable","operation":"doctor","retryable":false,"safe_param_schema_id":"none","stage":"probe"},{"code":"adapter_not_distributable","operation":"refresh","retryable":false,"safe_param_schema_id":"none","stage":"config_validate"},{"code":"budget_deferred","operation":"discover","retryable":true,"safe_param_schema_id":"budget-code","stage":"rate_ledger_reserve"},{"code":"budget_deferred","operation":"doctor","retryable":true,"safe_param_schema_id":"budget-code","stage":"rate_ledger_reserve"},{"code":"config_unavailable","operation":"alert_ack","retryable":true,"safe_param_schema_id":"none","stage":"config_gate"},{"code":"config_unavailable","operation":"configure","retryable":true,"safe_param_schema_id":"none","stage":"config_gate"},{"code":"config_unavailable","operation":"consent_grant","retryable":true,"safe_param_schema_id":"none","stage":"config_gate"},{"code":"config_unavailable","operation":"consent_revoke","retryable":true,"safe_param_schema_id":"none","stage":"config_gate"},{"code":"config_unavailable","operation":"delete","retryable":true,"safe_param_schema_id":"none","stage":"config_gate"},{"code":"config_unavailable","operation":"discover","retryable":true,"safe_param_schema_id":"none","stage":"config_gate"},{"code":"config_unavailable","operation":"doctor","retryable":true,"safe_param_schema_id":"none","stage":"config_gate"},{"code":"config_unavailable","operation":"migrate","retryable":true,"safe_param_schema_id":"none","stage":"config_gate"},{"code":"config_unavailable","operation":"purge","retryable":true,"safe_param_schema_id":"none","stage":"config_gate"},{"code":"config_unavailable","operation":"refresh","retryable":true,"safe_param_schema_id":"none","stage":"config_gate"},{"code":"config_unavailable","operation":"status","retryable":true,"safe_param_schema_id":"none","stage":"config_gate"},{"code":"consent_expired","operation":"consent_revoke","retryable":false,"safe_param_schema_id":"none","stage":"consent_validate"},{"code":"consent_expired","operation":"status","retryable":false,"safe_param_schema_id":"none","stage":"consent_validate"},{"code":"consent_required","operation":"status","retryable":false,"safe_param_schema_id":"none","stage":"consent_validate"},{"code":"credential_backend_unavailable","operation":"discover","retryable":true,"safe_param_schema_id":"none","stage":"credential_resolve"},{"code":"credential_backend_unavailable","operation":"doctor","retryable":true,"safe_param_schema_id":"none","stage":"credential_resolve"},{"code":"credential_backend_unavailable","operation":"refresh","retryable":true,"safe_param_schema_id":"none","stage":"credential_resolve"},{"code":"invalid_config","operation":"configure","retryable":false,"safe_param_schema_id":"field-code","stage":"config_validate"},{"code":"invalid_config","operation":"delete","retryable":false,"safe_param_schema_id":"field-code","stage":"config_validate"},{"code":"invalid_config","operation":"discover","retryable":false,"safe_param_schema_id":"field-code","stage":"config_validate"},{"code":"invalid_config","operation":"doctor","retryable":false,"safe_param_schema_id":"field-code","stage":"config_validate"},{"code":"invalid_config","operation":"migrate","retryable":false,"safe_param_schema_id":"field-code","stage":"config_validate"},{"code":"invalid_config","operation":"refresh","retryable":false,"safe_param_schema_id":"field-code","stage":"config_validate"},{"code":"invalid_discovery_result","operation":"discover","retryable":false,"safe_param_schema_id":"violation-code","stage":"discovery"},{"code":"local_keyring_unavailable","operation":"alert_ack","retryable":false,"safe_param_schema_id":"envelope-code","stage":"config_gate"},{"code":"local_keyring_unavailable","operation":"configure","retryable":false,"safe_param_schema_id":"envelope-code","stage":"config_gate"},{"code":"local_keyring_unavailable","operation":"consent_grant","retryable":false,"safe_param_schema_id":"envelope-code","stage":"config_gate"},{"code":"local_keyring_unavailable","operation":"consent_revoke","retryable":false,"safe_param_schema_id":"envelope-code","stage":"config_gate"},{"code":"local_keyring_unavailable","operation":"delete","retryable":false,"safe_param_schema_id":"envelope-code","stage":"config_gate"},{"code":"local_keyring_unavailable","operation":"discover","retryable":false,"safe_param_schema_id":"envelope-code","stage":"config_gate"},{"code":"local_keyring_unavailable","operation":"doctor","retryable":false,"safe_param_schema_id":"envelope-code","stage":"config_gate"},{"code":"local_keyring_unavailable","operation":"migrate","retryable":false,"safe_param_schema_id":"envelope-code","stage":"config_gate"},{"code":"local_keyring_unavailable","operation":"purge","retryable":false,"safe_param_schema_id":"envelope-code","stage":"config_gate"},{"code":"local_keyring_unavailable","operation":"refresh","retryable":false,"safe_param_schema_id":"envelope-code","stage":"config_gate"},{"code":"local_keyring_unavailable","operation":"status","retryable":false,"safe_param_schema_id":"envelope-code","stage":"config_gate"},{"code":"local_process_timeout","operation":"discover","retryable":true,"safe_param_schema_id":"none","stage":"discovery"},{"code":"local_process_timeout","operation":"doctor","retryable":true,"safe_param_schema_id":"none","stage":"probe"},{"code":"local_process_timeout","operation":"refresh","retryable":true,"safe_param_schema_id":"none","stage":"probe"},{"code":"local_process_timeout","operation":"refresh","retryable":true,"safe_param_schema_id":"none","stage":"provider_fetch"},{"code":"local_protocol_violation","operation":"discover","retryable":false,"safe_param_schema_id":"protocol-code","stage":"discovery"},{"code":"local_protocol_violation","operation":"doctor","retryable":false,"safe_param_schema_id":"protocol-code","stage":"probe"},{"code":"local_protocol_violation","operation":"refresh","retryable":false,"safe_param_schema_id":"protocol-code","stage":"probe"},{"code":"local_protocol_violation","operation":"refresh","retryable":false,"safe_param_schema_id":"protocol-code","stage":"provider_fetch"},{"code":"migration_conflict","operation":"configure","retryable":false,"safe_param_schema_id":"conflict-code","stage":"migration_commit"},{"code":"migration_conflict","operation":"configure","retryable":false,"safe_param_schema_id":"conflict-code","stage":"migration_plan"},{"code":"migration_conflict","operation":"migrate","retryable":false,"safe_param_schema_id":"conflict-code","stage":"migration_commit"},{"code":"migration_conflict","operation":"migrate","retryable":false,"safe_param_schema_id":"conflict-code","stage":"migration_plan"},{"code":"not_authorized","operation":"alert_ack","retryable":false,"safe_param_schema_id":"none","stage":"authorize"},{"code":"not_authorized","operation":"configure","retryable":false,"safe_param_schema_id":"none","stage":"authorize"},{"code":"not_authorized","operation":"consent_grant","retryable":false,"safe_param_schema_id":"none","stage":"authorize"},{"code":"not_authorized","operation":"consent_revoke","retryable":false,"safe_param_schema_id":"none","stage":"authorize"},{"code":"not_authorized","operation":"delete","retryable":false,"safe_param_schema_id":"none","stage":"authorize"},{"code":"not_authorized","operation":"discover","retryable":false,"safe_param_schema_id":"none","stage":"authorize"},{"code":"not_authorized","operation":"doctor","retryable":false,"safe_param_schema_id":"none","stage":"authorize"},{"code":"not_authorized","operation":"migrate","retryable":false,"safe_param_schema_id":"none","stage":"authorize"},{"code":"not_authorized","operation":"purge","retryable":false,"safe_param_schema_id":"none","stage":"authorize"},{"code":"not_authorized","operation":"refresh","retryable":false,"safe_param_schema_id":"none","stage":"authorize"},{"code":"not_authorized","operation":"status","retryable":false,"safe_param_schema_id":"none","stage":"authorize"},{"code":"projection_failed","operation":"alert_ack","retryable":false,"safe_param_schema_id":"projection-code","stage":"projection"},{"code":"projection_failed","operation":"refresh","retryable":false,"safe_param_schema_id":"projection-code","stage":"projection"},{"code":"projection_failed","operation":"status","retryable":false,"safe_param_schema_id":"projection-code","stage":"projection"},{"code":"rate_ledger_unavailable","operation":"discover","retryable":true,"safe_param_schema_id":"rate-ledger-code","stage":"rate_ledger_commit"},{"code":"rate_ledger_unavailable","operation":"discover","retryable":true,"safe_param_schema_id":"rate-ledger-code","stage":"rate_ledger_reserve"},{"code":"rate_ledger_unavailable","operation":"doctor","retryable":true,"safe_param_schema_id":"rate-ledger-code","stage":"rate_ledger_commit"},{"code":"rate_ledger_unavailable","operation":"doctor","retryable":true,"safe_param_schema_id":"rate-ledger-code","stage":"rate_ledger_reserve"},{"code":"rate_ledger_unavailable","operation":"refresh","retryable":true,"safe_param_schema_id":"rate-ledger-code","stage":"rate_ledger_commit"},{"code":"rate_ledger_unavailable","operation":"refresh","retryable":true,"safe_param_schema_id":"none","stage":"rate_ledger_reserve"},{"code":"referenced_object_conflict","operation":"configure","retryable":false,"safe_param_schema_id":"object-kind","stage":"migration_plan"},{"code":"referenced_object_conflict","operation":"delete","retryable":false,"safe_param_schema_id":"object-kind","stage":"deletion_plan"},{"code":"referenced_object_conflict","operation":"migrate","retryable":false,"safe_param_schema_id":"object-kind","stage":"migration_plan"},{"code":"storage_unavailable","operation":"alert_ack","retryable":true,"safe_param_schema_id":"store-code","stage":"alert_ack_commit"},{"code":"storage_unavailable","operation":"configure","retryable":true,"safe_param_schema_id":"store-code","stage":"migration_commit"},{"code":"storage_unavailable","operation":"consent_grant","retryable":true,"safe_param_schema_id":"store-code","stage":"consent_commit"},{"code":"storage_unavailable","operation":"consent_revoke","retryable":true,"safe_param_schema_id":"store-code","stage":"consent_commit"},{"code":"storage_unavailable","operation":"delete","retryable":true,"safe_param_schema_id":"store-code","stage":"migration_commit"},{"code":"storage_unavailable","operation":"discover","retryable":true,"safe_param_schema_id":"store-code","stage":"config_gate"},{"code":"storage_unavailable","operation":"discover","retryable":true,"safe_param_schema_id":"store-code","stage":"rate_ledger_commit"},{"code":"storage_unavailable","operation":"discover","retryable":true,"safe_param_schema_id":"store-code","stage":"rate_ledger_reserve"},{"code":"storage_unavailable","operation":"doctor","retryable":true,"safe_param_schema_id":"store-code","stage":"config_gate"},{"code":"storage_unavailable","operation":"doctor","retryable":true,"safe_param_schema_id":"store-code","stage":"rate_ledger_commit"},{"code":"storage_unavailable","operation":"doctor","retryable":true,"safe_param_schema_id":"store-code","stage":"rate_ledger_reserve"},{"code":"storage_unavailable","operation":"migrate","retryable":true,"safe_param_schema_id":"store-code","stage":"migration_commit"},{"code":"storage_unavailable","operation":"purge","retryable":true,"safe_param_schema_id":"store-code","stage":"purge_commit"},{"code":"storage_unavailable","operation":"refresh","retryable":true,"safe_param_schema_id":"store-code","stage":"cache_commit"},{"code":"storage_unavailable","operation":"refresh","retryable":true,"safe_param_schema_id":"store-code","stage":"idempotency_finalize"},{"code":"storage_unavailable","operation":"refresh","retryable":true,"safe_param_schema_id":"store-code","stage":"idempotency_prepare"},{"code":"storage_unavailable","operation":"refresh","retryable":true,"safe_param_schema_id":"store-code","stage":"rate_ledger_commit"},{"code":"storage_unavailable","operation":"refresh","retryable":true,"safe_param_schema_id":"store-code","stage":"rate_ledger_reserve"},{"code":"storage_unavailable","operation":"status","retryable":true,"safe_param_schema_id":"store-code","stage":"cache_read"},{"code":"unsupported_platform","operation":"configure","retryable":false,"safe_param_schema_id":"none","stage":"config_validate"},{"code":"unsupported_platform","operation":"discover","retryable":false,"safe_param_schema_id":"none","stage":"config_validate"},{"code":"unsupported_platform","operation":"doctor","retryable":false,"safe_param_schema_id":"none","stage":"config_validate"},{"code":"unsupported_platform","operation":"doctor","retryable":false,"safe_param_schema_id":"none","stage":"probe"},{"code":"unsupported_platform","operation":"refresh","retryable":false,"safe_param_schema_id":"none","stage":"config_validate"}],"/paths":[{"mode":"none","operation":"alert_ack","path_id":"alert-ack-none-v1","steps":[{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"contract_validate"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"authorize"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"config_gate"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"alert_ack_commit"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"projection"}]},{"mode":"none","operation":"configure","path_id":"configure-none-v1","steps":[{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"contract_validate"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"authorize"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"config_gate"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"config_validate"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"manifest_validate"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"migration_plan"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"migration_commit"}]},{"mode":"none","operation":"consent_grant","path_id":"consent-grant-none-v1","steps":[{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"contract_validate"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"authorize"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"config_gate"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"consent_validate"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"consent_commit"}]},{"mode":"none","operation":"consent_revoke","path_id":"consent-revoke-none-v1","steps":[{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"contract_validate"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"authorize"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"config_gate"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"consent_validate"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"consent_commit"}]},{"mode":"none","operation":"delete","path_id":"delete-none-v1","steps":[{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"contract_validate"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"authorize"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"config_gate"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"config_validate"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"manifest_validate"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"deletion_plan"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"migration_commit"}]},{"mode":"http","operation":"discover","path_id":"discover-http-v1","steps":[{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"contract_validate"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"authorize"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"config_gate"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"config_validate"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"manifest_validate"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"endpoint_validate"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"discovery_request_plan_build"},{"io_class":"pure_local","predicate_id":"always","request_kind":"discovery","stage":"rate_ledger_reserve"},{"io_class":"pure_local","predicate_id":"always","request_kind":"discovery","stage":"rate_ledger_commit"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"credential_resolve"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"identity_derive"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"discovery_context_build"},{"io_class":"provider_io","predicate_id":"always","request_kind":"discovery","stage":"discovery"}]},{"mode":"official_cli_zero_binding","operation":"discover","path_id":"discover-official-cli-v1","steps":[{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"contract_validate"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"authorize"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"config_gate"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"config_validate"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"manifest_validate"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"endpoint_validate"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"identity_and_discovery_request_plan_build"},{"io_class":"pure_local","predicate_id":"always","request_kind":"discovery","stage":"rate_ledger_reserve"},{"io_class":"pure_local","predicate_id":"always","request_kind":"discovery","stage":"rate_ledger_commit"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"identity_and_discovery_context_build"},{"io_class":"provider_io","predicate_id":"always","request_kind":"discovery","stage":"discovery"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"identity_verify_and_accept"}]},{"mode":"offline","operation":"discover","path_id":"discover-offline-v1","steps":[{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"contract_validate"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"authorize"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"config_gate"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"config_validate"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"manifest_validate"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"endpoint_validate"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"operation_context_build"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"discovery"}]},{"mode":"http","operation":"doctor","path_id":"doctor-http-v1","steps":[{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"contract_validate"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"authorize"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"config_gate"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"config_validate"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"manifest_validate"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"endpoint_validate"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"probe_request_plan_build"},{"io_class":"pure_local","predicate_id":"always","request_kind":"probe","stage":"rate_ledger_reserve"},{"io_class":"pure_local","predicate_id":"always","request_kind":"probe","stage":"rate_ledger_commit"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"credential_resolve"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"identity_derive"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"probe_context_build"},{"io_class":"provider_io","predicate_id":"always","request_kind":"probe","stage":"probe"},{"io_class":"pure_local","predicate_id":"probe-result-contract-v1","request_kind":null,"stage":"probe_result_validate"}]},{"mode":"official_cli_zero_binding","operation":"doctor","path_id":"doctor-official-cli-v1","steps":[{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"contract_validate"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"authorize"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"config_gate"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"config_validate"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"manifest_validate"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"endpoint_validate"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"probe_request_plan_build"},{"io_class":"pure_local","predicate_id":"always","request_kind":"probe","stage":"rate_ledger_reserve"},{"io_class":"pure_local","predicate_id":"always","request_kind":"probe","stage":"rate_ledger_commit"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"probe_context_build"},{"io_class":"provider_io","predicate_id":"always","request_kind":"probe","stage":"probe"},{"io_class":"pure_local","predicate_id":"probe-result-contract-v1","request_kind":null,"stage":"probe_result_validate"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"identity_derive"}]},{"mode":"offline","operation":"doctor","path_id":"doctor-offline-v1","steps":[{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"contract_validate"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"authorize"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"config_gate"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"config_validate"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"manifest_validate"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"endpoint_validate"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"probe_context_build"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"probe"},{"io_class":"pure_local","predicate_id":"probe-result-contract-v1","request_kind":null,"stage":"probe_result_validate"}]},{"mode":"none","operation":"migrate","path_id":"migrate-none-v1","steps":[{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"contract_validate"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"authorize"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"config_gate"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"config_validate"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"manifest_validate"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"migration_plan"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"migration_commit"}]},{"mode":"none","operation":"purge","path_id":"purge-none-v1","steps":[{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"contract_validate"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"authorize"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"config_gate"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"purge_plan"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"purge_commit"}]},{"mode":"http","operation":"refresh","path_id":"refresh-http-v1","steps":[{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"contract_validate"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"authorize"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"config_gate"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"config_validate"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"manifest_validate"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"endpoint_validate"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"idempotency_prepare"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"credential_resolve"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"identity_derive"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"fetch_request_plan_build"},{"io_class":"pure_local","predicate_id":"always","request_kind":"fetch","stage":"rate_ledger_reserve"},{"io_class":"pure_local","predicate_id":"always","request_kind":"fetch","stage":"rate_ledger_commit"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"fetch_context_build"},{"io_class":"provider_io","predicate_id":"always","request_kind":"fetch","stage":"provider_fetch"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"cache_commit"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"idempotency_finalize"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"alert_evaluate"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"projection"}]},{"mode":"official_cli_zero_binding","operation":"refresh","path_id":"refresh-official-cli-v1","steps":[{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"contract_validate"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"authorize"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"config_gate"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"config_validate"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"manifest_validate"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"endpoint_validate"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"idempotency_prepare"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"identity_and_fetch_request_plan_build"},{"io_class":"pure_local","predicate_id":"always","request_kind":"identity_and_fetch","stage":"rate_ledger_reserve"},{"io_class":"pure_local","predicate_id":"always","request_kind":"identity_and_fetch","stage":"rate_ledger_commit"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"identity_and_fetch_context_build"},{"io_class":"provider_io","predicate_id":"always","request_kind":"identity_and_fetch","stage":"probe"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"identity_verify_and_accept"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"cache_commit"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"idempotency_finalize"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"alert_evaluate"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"projection"}]},{"mode":"none","operation":"status","path_id":"status-none-v1","steps":[{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"contract_validate"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"authorize"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"config_gate"},{"io_class":"pure_local","predicate_branch":{"node_type":"conditional_stage","on_error":"reject_operation","on_false":"skip_stage","on_missing":"reject_operation","on_true":"execute_stage","typed_result_source":"predicate_control_flow"},"predicate_id":"consent-required-for-status-projection","request_kind":null,"stage":"consent_validate"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"cache_read"},{"io_class":"pure_local","predicate_id":"always","request_kind":null,"stage":"projection"}]}],"/predicate_definitions":[{"control_flow":{"error":{"action":"reject_operation","typed_result":"predicate_evaluation_error"},"false":{"action":"reject_operation","typed_result":"predicate_false"},"missing":{"action":"reject_operation","typed_result":"predicate_input_missing"},"true":{"action":"execute_stage","typed_result":"predicate_true"}},"expression":{"op":"literal","value":true},"inputs":[],"missing_input_verdict":"reject","predicate_id":"always","semantic_vectors":[{"action":"execute_stage","authorization_boundary":"path_authorization_unchanged","input_status":"complete","inputs":{},"predicate_result":true,"typed_result":"predicate_true","vector_id":"always-true"}]},{"control_flow":{"error":{"action":"reject_operation","typed_result":"predicate_evaluation_error"},"false":{"action":"skip_stage","typed_result":"llm_consent_not_applicable"},"missing":{"action":"reject_operation","typed_result":"predicate_input_missing"},"true":{"action":"execute_stage","typed_result":"llm_consent_required"}},"expression":{"left":{"input":"audience"},"op":"equal","right":{"literal":"llm_minimal"}},"inputs":[{"allowed_values":["feishu_private","llm_minimal","local_detail"],"name":"audience","type":"enum"}],"missing_input_verdict":"reject","predicate_id":"consent-required-for-status-projection","semantic_vectors":[{"action":"skip_stage","authorization_boundary":"feishu_private_authorization_required","input_status":"complete","inputs":{"audience":"feishu_private"},"predicate_result":false,"typed_result":"llm_consent_not_applicable","vector_id":"consent-feishu-private"},{"action":"execute_stage","authorization_boundary":"llm_consent_required","input_status":"complete","inputs":{"audience":"llm_minimal"},"predicate_result":true,"typed_result":"llm_consent_required","vector_id":"consent-llm-minimal"},{"action":"skip_stage","authorization_boundary":"local_access_context_authorization_required","input_status":"complete","inputs":{"audience":"local_detail"},"predicate_result":false,"typed_result":"llm_consent_not_applicable","vector_id":"consent-local-detail"},{"action":"reject_operation","authorization_boundary":"fail_closed","input_status":"missing","inputs":{},"predicate_result":null,"typed_result":"predicate_input_missing","vector_id":"consent-missing"},{"action":"reject_operation","authorization_boundary":"fail_closed","input_status":"invalid","inputs":{"audience":"unknown"},"predicate_result":null,"typed_result":"predicate_input_missing","vector_id":"consent-unknown"},{"action":"reject_operation","authorization_boundary":"fail_closed","input_status":"evaluation_error","inputs":{"audience":"llm_minimal"},"predicate_result":null,"typed_result":"predicate_evaluation_error","vector_id":"consent-evaluation-error"}]},{"control_flow":{"error":{"action":"reject_operation","typed_result":"predicate_evaluation_error"},"false":{"action":"reject_operation","typed_result":"predicate_false"},"missing":{"action":"reject_operation","typed_result":"predicate_input_missing"},"true":{"action":"execute_stage","typed_result":"predicate_true"}},"expression":{"op":"literal","value":true},"inputs":[],"missing_input_verdict":"reject","predicate_id":"probe-result-contract-v1","semantic_vectors":[{"action":"execute_stage","authorization_boundary":"path_authorization_unchanged","input_status":"complete","inputs":{},"predicate_result":true,"typed_result":"predicate_true","vector_id":"probe-result-valid"}]}],"/safe_param_schemas":[{"fields":[{"allowed_values":["blocked_until","floor","hour"],"kind":"enum","name":"budget_code"}],"schema_id":"budget-code"},{"fields":[{"allowed_values":["config_digest_changed","confirmation_invalid","dependency_cycle","generation_changed"],"kind":"enum","name":"conflict_code"}],"schema_id":"conflict-code"},{"fields":[{"allowed_values":["illegal_error_envelope","illegal_execution_plan","invalid_operation_envelope","malformed_local_envelope","unknown_schema_version"],"kind":"enum","name":"envelope_code"}],"schema_id":"envelope-code"},{"fields":[{"allowed_values":["duplicate_key","invalid_value","missing_required_field","unknown_field","wrong_type"],"kind":"enum","name":"field_code"}],"schema_id":"field-code"},{"fields":[],"schema_id":"none"},{"fields":[{"allowed_values":["alert_policy","capability","credential_binding","principal","subject","view"],"kind":"enum","name":"object_kind"}],"schema_id":"object-kind"},{"fields":[{"allowed_values":["invalid_projection_state","serialization_failed"],"kind":"enum","name":"projection_code"}],"schema_id":"projection-code"},{"fields":[{"allowed_values":["id_mismatch","invalid_frame","method_not_allowed","response_too_large","unexpected_message"],"kind":"enum","name":"protocol_code"}],"schema_id":"protocol-code"},{"fields":[{"allowed_values":["fence_conflict","lease_conflict","ledger_unavailable"],"kind":"enum","name":"rate_ledger_code"}],"schema_id":"rate-ledger-code"},{"fields":[{"allowed_values":["durability_failed","sqlite_unavailable","transaction_failed"],"kind":"enum","name":"store_code"}],"schema_id":"store-code"},{"fields":[{"allowed_values":["extra_output","identity_evidence_expired","identity_evidence_mismatch","invalid_observation","invalid_probe_result","invalid_request_key_set","invalid_snapshot","manifest_mismatch"],"kind":"enum","name":"violation_code"}],"schema_id":"violation-code"}],"/stages":["alert_ack_commit","alert_evaluate","authorize","cache_commit","cache_read","config_gate","config_validate","consent_commit","consent_validate","contract_validate","credential_resolve","deletion_plan","discovery","discovery_context_build","discovery_request_plan_build","endpoint_validate","fetch_context_build","fetch_request_plan_build","idempotency_finalize","idempotency_prepare","identity_and_discovery_context_build","identity_and_discovery_request_plan_build","identity_and_fetch_context_build","identity_and_fetch_request_plan_build","identity_derive","identity_verify_and_accept","manifest_validate","migration_commit","migration_plan","operation_context_build","probe","probe_context_build","probe_request_plan_build","probe_result_validate","projection","provider_fetch","purge_commit","purge_plan","rate_ledger_commit","rate_ledger_reserve"]}
```
<!-- AQ-GENERATED-OPERATION-PROJECTION-V1:END -->
