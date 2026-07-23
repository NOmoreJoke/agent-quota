# Provider 与凭据契约

<!-- AQ-GENERATED-CURRENT-STATUS-V1:BEGIN -->
```json
{"design_version":"v2.5","gate_status":"ZERO_ISSUES_AUDIT_CONFIRMED","latest_audit_path":"docs/audits/round-20-audit.md","latest_audit_verdict":"PASS_ZERO_ISSUES","latest_issue_ids":[],"revision_round":20,"status_kind":"ZERO_ISSUES"}
```
<!-- AQ-GENERATED-CURRENT-STATUS-V1:END -->
<!-- AQ-NORMATIVE-DECISION-LINK-V1:audits/gui-product-decision-resolution.md -->
> 上述 marker 是第 20 轮零问题终态；第 1–19 轮历史保持不可改写。GUI/Codex/OpenRouter 决策见 [`gui-product-decision-resolution.md`](audits/gui-product-decision-resolution.md) 与设计方案第 20 节；下一步是 Gate 0A 工作，不是生产发布。
> 最后更新：2026-07-19
> 安全边界：本文描述身份/主体配置、凭据、能力协商、网络出口和多组合隔离，不记录真实凭据或账户数据

## 1. 目的

本契约解决 Adapter 开发中最容易卡住的八个问题：

1. 用户显式注册了哪些认证身份、订阅/工作区/钱包主体与额度能力。
2. 每个身份需要零个、一个还是多个凭据绑定，以及如何安全读取。
3. 如何判断凭据失效，以及由谁负责刷新或重新登录。
4. 非公开额度接口发生结构变化时如何优雅降级。
5. 凭据只能发送到哪些协议、主机、端口、HTTP 路径或本地 RPC。
6. 多 principal/subject/capability 并发时如何避免跨凭据合并缓存、限流或结果。
7. 如何在正式刷新前协商 Adapter、官方 CLI 和上游协议能力。
8. 如何让 Desktop 与辅助 CLI 通过同一 application service 使用 Provider，而不依赖 Hermes 路径或类型。

Provider Adapter 负责额度协议；Credential Source 负责凭据解析；core 负责 principal/subject/capability、授权和缓存。三者必须解耦，Adapter 不得自行遍历用户目录寻找 Token。

core safety、operation/error、LocalKey purpose、lease 与 retention lint 的唯一机器源分别是 [`core-safety-contract-v1`](contracts/core-safety-contract-v1.json)、[`operation-contract-v1`](contracts/operation-contract-v1.json)、[`local-key-purpose-registry-v1`](contracts/local-key-purpose-registry-v1.json)、[`lease-policy-v1`](contracts/lease-policy-v1.json) 与 [`retention-lint-v1`](contracts/retention-lint-v1.json)。统一读取/hash 规则只引用[设计方案第 1 节](design-proposal.md#1-一句话定义)；本文不复制另一套预算、身份、HKDF、lease 数值或 lint allowlist。

## 2. Principal、Subject 与配置注册表

MVP 不扫描本机自动发现登录身份。`PrincipalRegistry` 只读取 `schema_version=1` 的显式配置；Subject 可以显式配置，或在用户允许联网后由已配置 principal 发现并确认：

```toml
schema_version = 1

[presentation]
timezone = "Asia/Shanghai"

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
subject_refs = [
  { principal_id = "aqp_8b3e6d1a4f9c2e7b5d8a1c6f3e9b4d20", subject_id = "aqs_6c1a8e3d7b2f9d4e5a8c1b6f3d7e2a90" },
]
capability_refs = [
  { principal_id = "aqp_8b3e6d1a4f9c2e7b5d8a1c6f3e9b4d20", subject_id = "aqs_6c1a8e3d7b2f9d4e5a8c1b6f3d7e2a90", capability_id = "wallet-balances" },
]
```

示例文件不包含密钥。路径由 `platformdirs` 决定；macOS/Linux 配置目录必须为 `0700`、文件为 `0600`。principal/subject label、selector 和外部 ID 属于机密数据。

配置规则：

- principal、subject、credential binding、view 与 alert policy 的本地 ID 由 core 生成且不可编辑，格式为类型前缀 `aqp_/aqs_/aqb_/aqv_/aqa_` 加 32 位小写十六进制随机值；不得接受邮箱、账号、组织名、外部 ID、用户自定义 slug 或其他自由字符串作为记录 ID。人类可读名称只能放在对应 label 字段。
- principal 必须声明 `enabled`、Adapter、provider/auth variant、region、批准的 endpoint profile 和 binding 引用列表；subject 必须声明 `enabled`、所属 principal、主体类型、本地用户确认的 label、符合 Adapter schema 的 selector、启用 capability 与展示顺序。
- capability ID 是 AdapterManifest 随代码冻结的公共枚举，不是用户记录 ID，也不得由上游账户标识动态生成。
- `credential_bindings` 数量由 AdapterManifest/auth variant 约束；`official-cli` 可以为零，双凭据协议可以多于一个。
- 未知字段、重复 ID、悬空引用、未声明 capability、binding 数量错误、未知 endpoint profile 或未来 schema version 一律拒绝。
- probe 只返回兼容性/协议版本及短命 `IdentityEvidence`，不返回 `AccessIdentity`，也不承载业务发现。discovery 使用设计方案唯一的 `DiscoveryRequest/DiscoverySeedSelector → DiscoveryResult(subjects, capabilities, missing)`；seed 不含正式 SubjectId，principal 为 0 subject 时空 seeds 表示本次已授权 profile/kind/capability 交集。Adapter 不得生成 `aqp_/aqs_` ID；missing reason 只允许 `not_entitled|unsupported_version|temporarily_unavailable`，本地 `not_authorized` 只属于 OperationError。用户确认前不落盘，跨批 handle、越 scope seed和悬空引用整批拒绝。
- `network_mode=offline` 的 config validate 不得解析 Credential Source、启动子进程或联网；通用验证器只匹配 manifest 中一个完整 `ProviderProfile`，据其 `CredentialRequirement/SubjectSpec/SelectorSchema/EndpointBudgetGroup→BudgetPolicy` 引用验证合法组合、binding purpose/数量和 selector，禁止 profile 复制预算数值或 Adapter 私有分支补合同。`local_only` 只允许登记的 local-stdio 且不解析 Credential Source；`network_allowed` 必须来自本次显式用户动作。
- `SubjectConfig`、`DiscoveredSubject` 与运行时 `QuotaSubject` 是不同 DTO。离线配置 label 必填，NFC 后 1..80 字符并拒绝控制/双向覆盖字符和首尾空白；不得以 selector、ID 或上游原文补齐。发现结果只用本次命令的 opaque handle 展示经目标转义的建议 label，用户确认后才生成本地 label/opaque ID；Provider 后续不得覆盖。`DiscoveredCapability` 只能引用同批 subject handle 与 manifest capability，selector 候选只能含 schema 字段。plan 只通过有限 `SubjectMetadataObservation(plan_code)` 输出：known 值初次随用户确认写 config，后续变化先进入 pending+维护告警，只有 planner/digest/nonce 确认才切 generation；unknown/null 丢弃且不落盘，不允许自由文本。
- view 只能引用已启用的 `(principal_id, subject_id)` 与 `(principal_id, subject_id, capability_id)`；它是展示过滤器，不是授权来源，不能扩大 `AccountScope`。
- `alert_policies` 是按 metric 判别的严格联合，只能引用已启用 capability；唯一 policy identity 为 `(subject,capability,metric,dimension)`。balance 的 dimension 是 currency，counter 是 canonical unit，窗口是 `window`；同币种/同 unit 重复拒绝，不同币种独立评估且不相加。严重度固定为 `none < warning < high < critical`；同一 capability 所有 dimension/policy 与固定 health severity取最高值进入同一 episode。
- 迁移必须显式、幂等、可 dry-run，并使用[设计方案的 TOML + SQLite migration journal](design-proposal.md#1021-toml--sqlite-migration-journal)协调文件替换与 generation/运行数据事务。SQLite 独占 writer lease、单调 fencing token、唯一 active migration 与每 migration 专属临时文件阻止双 CLI 分叉；所有运行入口和提交点复核文件/DB/内存 digest、generation 与 runtime fence，发现 drift 立即关闭 gate 并恢复。dry-run 不输出原始记录 ID，只按确定顺序显示本次运行内稳定的类型化句柄、字段路径、动作和 plan digest；label、selector、外部 ID、完整 CredentialRef 及其值在 stdout/stderr、日志与 CI artifact 中统一显示为类型化占位符。
- 外部有效 TOML drift 不能绕过 planner：core 必须对 old DB registry/manifest 与新文件计算类型化 diff。只有 presentation、现有 subject 的纯展示字段，以及只引用已启用绑定对象且不改变授权/运行数据的 view 过滤修改可自动采用；disable/delete/manifest removal、所有权/policy/后代引用移除、selector/endpoint/auth/binding/capability/manifest 变化或 generation 数据清理都保持 gate 关闭，必须由 `config adopt --dry-run` 产生相同 plan digest，再以一次 nonce 确认。确认前 active config digest/运行表不变且 Credential Source/子进程/Provider 调用为 0；文件或 manifest 再变使 digest/nonce 失效。
- legacy ID 已符合 opaque 语法时保持；不符合但引用图唯一、无悬空/重复且不含 secret-like Token 时，只能经显式 `migrate legacy-ids --cascade`、相同 plan digest 与确认生成新 ID并重写引用；secret-like、重复、歧义或悬空输入稳定返回 `migration_conflict` 且零写入。subject delete、capability disable 和 manifest removal 有引用时默认返回 `referenced_object_conflict`；只有显式 cascade 的同一计划摘要可修改引用。

## 3. CredentialRef

建议第一版支持以下引用：

| 引用形式 | 含义 | 使用边界 |
| --- | --- | --- |
| `env:VAR_NAME` | 从当前进程环境读取显式变量 | 适合独立 CLI、CI 或非 Hermes 用户 |
| `official-cli:NAME` | 通过供应商官方 CLI 或本地协议查询，适配器不接触 Token | OpenAI Codex 等已有安全本地接口的 Provider |
| `system-credential:SERVICE/ACCOUNT` | 从 macOS Keychain 或 Linux Secret Service 读取明确条目 | 通过受审查 backend；不得模糊搜索整个凭据存储 |
| `hermes-env:VAR_NAME` | 可选 `agent-quota-hermes` 调用 Hermes 配置加载器 | 只在 Hermes profile 注册；core/CLI 默认不识别 |
| `hermes-auth:PROVIDER` | 可选 Hermes OAuth resolver | 只在 Hermes profile 注册且版本受约束 |

核心规则：

- 禁止“扫描 `~/.config` 后选择第一个看起来像 Token 的文件”。
- 禁止在配置文件中接受明文 `api_key = "..."`。
- 凭据只在单次请求内存在于内存，不进入 SQLite、结构指纹或异常对象。
- 任何 `CredentialRef` 都必须匹配 Provider 的允许列表，避免把 A 平台密钥发送到 B 平台。
- 日志只允许输出 binding ID 和 source kind，不输出完整 CredentialRef 或解析结果。
- `system-credential` backend 必须显式探测。Keychain/Secret Service、D-Bus 会话或受审查 backend 不可用时返回操作级 `OperationError(requested_operation=<原 actor 请求>, failed_stage="credential_resolve", code="credential_backend_unavailable")` 并 fail closed；不创建 capability 快照、不更新 Provider 失败计数、不得自动改读 `env:`、文件或其他引用。改用环境变量必须由用户显式修改 CredentialRef。
- Desktop renderer 只能使用机器登记的 10 个 command；每个 request/response reference 都必须解析到同一 `renderer_command_contract` 中封闭、有类型、有界、脱敏的 29 个 DTO schema，nested ref 与 non-destructive config change-set 也不例外。renderer 只能请求 host 打开 native credential dialog，不能提交 secret 参数。API Key keystroke/paste/SecretBuffer 只存在于 WebView 之外的 host-owned secure field 和受审查 Keychain import 调用；renderer 只接收 opaque CredentialRef/status。host 仅在 app foreground + key window 打开 dialog，每 installation 同时最多一个 trusted dialog，并执行 cooldown/spam fail-closed。`renderer-secret-input-path-absent` 必须对 React DOM/event/state/prop、Tauri command schema 与 host→renderer DTO 做负向断言。
- Desktop 的 purge、disable/delete/cascade 与 endpoint/auth/binding/capability/manifest destructive config diff 必须由 core 生成脱敏 plan，只在 Rust host-owned native confirmation surface 展示；plan digest、nonce、user-presence token 只走 host↔core，renderer 只能请求打开并接收 `cancelled|committed|status`。`renderer-destructive-confirmation-token-absent` 必须覆盖 Tauri command schema、renderer bundle 和 host→renderer DTO。

### 3.1 `CredentialRef` 不是隔离边界

`CredentialRef` 是正常代码的路由与最小授权契约，不是进程内安全边界。Desktop profile 的 TCB 是已签名 host/core sidecar、系统凭据服务、启用的内置 Adapter 与 OS 用户；renderer 只能通过脱敏 command DTO，辅助 CLI 使用同一 application service。Hermes profile 额外包含 Hermes 及全部进程内插件。两种 profile 的风险不能混写。

MVP 只允许仓库内置、已审查的 Adapter 解析凭据。第三方 Adapter 不得接触原始凭据。若未来开放 P2，最低边界为独立低权限进程、过滤环境、每实例单 principal/lease、固定 RPC 与出口、响应大小/时间限制和可撤销授权。

## 4. Credential Source 接口

```python
class CredentialSource(Protocol):
    async def resolve(
        self, binding: CredentialBinding, principal: AccountPrincipal
    ) -> CredentialResolution: ...
```

`CredentialResolution` 与 `CredentialLease` 都不在本文重复定义，唯一 DTO 位于[设计方案第 8 节](design-proposal.md#8-provider-adapter-sdk)。Source 只能构造 Resolution：授权 binding、访问代际材料、可选上游主体 evidence、secret 与有限 metadata；它不能构造 `AccessIdentity` 或 Lease。core 先验证 evidence authorization/expiry/profile/purpose，调用唯一 `derive_access_identity_v1` 生成隔离缓存身份与稳定或保守 cohort，再构造唯一 canonical Lease。core 与 SDK 直接导入两个模型并比较各自 schema hash；缺字段、未知 metadata、普通字符串秘密、过期或 principal/profile 不匹配都在 Adapter 前拒绝，repr/异常/日志/通用序列化均无 secret/metadata value。

`AccessIdentity` 是 core 内部运行身份，不进入用户配置、普通日志或渠道投影；其所有公式只引用设计方案的 `derive_access_identity_v1`：

- `cache_identity` 隔离结果，必须包含 principal 与访问代际；同一凭据或 official-cli 账户发生轮换、切换、登出重登时必须变化，不能使用 `None`、binding ID 或 principal 常量代替。
- `rate_limit_cohort` 聚合上游风险预算，不包含 principal、binding、CredentialRef、访问代际或进程；稳定分支只使用经验证的 Provider identity domain 与稳定上游 subject material。没有稳定 subject evidence 时只使用 deployment/adapter/endpoint budget group 的保守 cohort，不能由访问材料假装稳定账户身份。
- 多份访问材料只有在 evidence 证明属于同一稳定上游主体时才能合并 cohort；否则使用保守 cohort。授权 binding evidence 单独验证，绝不混入 cohort 输入。
- `env:`/`system-credential:` 的 keyed identity 在秘密值原地轮换后必须变化；专用本地密钥与生成结果均按 Confidential 管理。它们是缓存/限流标识，不是凭据替代品，也不构成同 uid 隔离。

`official-cli` principal 的 binding 列表可以为空，此时 Adapter 不调用 Credential Source，但仍必须通过受信任本地协议取得非秘密、可验证的账户/会话代际，再由 core 生成 `verified_stable` AccessIdentity。若只能生成进程级 `ephemeral` identity，禁止持久化缓存/last-known-good；要成为 Supported 或执行正式 `fetch`，必须 fail closed 为 `incompatible`，直至稳定身份契约可用。来源轮换或重新认证由显式操作后再次 `resolve()` 表达，不存在 Source 可直接刷新或失效 Lease 的第二接口。

身份输入只使用设计方案封闭的 `EvidenceAuthorizationBinding`、访问代际材料与可选 `UpstreamSubjectEvidence`；三者分别授权、隔离缓存和聚合预算，禁止复用同一 opaque bytes 同时承担三种语义。evidence 为 `SecretBytes(repr=False, exclude=True)`，受 `aq-bounds-v1`、短期到期与单次使用约束；错误分支、未知 source contract、跨 principal/profile/binding/endpoint、空或过期 evidence 全部在派生前拒绝。core 只调用 `derive_access_identity_v1`，验证后立即清除 evidence。Adapter/Source 提交 AccessIdentity、任意 assurance 字符串或 keyed identity 视为合同违规。OpenRouter 只用已验证 API key binding 与 `CredentialResolution.generation` 形成 access/cache identity；同次已认证 `/api/v1/key` 的 `creator_user_id` 只形成 bounded observed metadata，禁止升级为 UpstreamSubjectEvidence、ProviderIdentityDomain 或 rate cohort。Codex 的 official-protocol subject source contract未登记，不能由实现自行选择字段或 RPC。

### 4.1 AccessIdentity 的 LocalKeyRing 依赖

生成 cache identity、cohort、query generation 与 ledger digest 的 key 只能通过 [`local-key-purpose-registry-v1`](contracts/local-key-purpose-registry-v1.json) 的 exact `consumer_id`取得；purpose、consumer→purpose、新值只用active、active+verify-only有界查找、持久surface组合/去重/退休与LocalKeyRing wire均只读该artifact。SQLite只记录非秘密key ID/generation。轮换由migration writer lease/fence驱动；已有registry/DB时keyring缺失或回滚返回`local_keyring_unavailable`，不能静默生成新cohort绕过预算。

installation binding material 只允许设计方案第 10.0.1 节 anchor-relative `installation-binding-v1.key` raw-32-byte backend；owner/mode/no-follow/O_EXCL/fsync/read-exact/recovery/purge 顺序不得由 Provider实现。key entry 的 16-byte public_salt 与 `aqk_` domain-separated key-id recipe 同样是跨实现合同，Adapter看不到两者。

### 4.2 不可变 Adapter 调用上下文

Adapter 的唯一调用面是[设计方案第 8 节](design-proposal.md#8-provider-adapter-sdk)冻结的 `ProbeContext/DiscoveryRequest/FetchContext`，不得再接受裸 `principal + request`。discovery seed 只绑定 profile/subject kind/schema/有限候选字段，不引用正式 SubjectId；唯一返回是同批 `DiscoveryResult`。三个输入都以 `extra=forbid, frozen=True` 构造，但 nested collection 先由 core 有界深拷贝并重建为 canonical tuple；`frozen=True` 不作为深冻结证明。输入显式携带 principal/profile、seed/selector、canonical CredentialLease/零 binding proof、AccessIdentity、唯一 endpoint spec handle 与单调 deadline。offline lease/proof 为空且 I/O 为 0；local_only official-cli 只有 proof；network_allowed HTTP 只有 lease；FetchContext 必须恰有一类并只接受 `verified_stable`。

core 只执行 `operation-contract-v1` 生成的 exact path。非法 endpoint 与幂等 replay 的 Source 调用计数为 0；official-cli zero-binding 分支显式跳过 Source。lease/proof 二者恰有一个合法，且 principal/purpose/profile/source kind/selector/endpoint/policy digest/access identity 必须相同；Adapter 不能反查全局状态。`secret/core_mac/transport_metadata` 禁止 repr 与序列化，结束后清除引用。

I/O class 不由 Adapter 自报：本地 schema/file/version/不含业务 method 的握手为 `pure_local`；全部 outbound HTTP 与 local-stdio 业务 request 为 `provider_io`。后者 context 必须携带 exact request kind 与已经 committed 的 matching `RateReservationReceipt`，且首个 outbound byte 必须晚于 ledger commit；doctor/discover 同样计账。endpoint budget group 是真正umbrella：所有verified attempt也原子占同group blocker并附加verified索引；身份未知时发送前检查group umbrella所覆盖的全部activity。response验证出stable identity后只给同一reservation行附加verified索引，一行仍只计一次attempt。复制principal/binding/process或丢失identity cache均不扩容。

只有 manifest source/response contract 同时声明 identity 与 quota observation 时才允许 `identity_and_fetch`。core 为同一次 reservation 构造 `IdentityAndFetchContext`，Adapter 返回带同一 request digest 的唯一 joint response；core 先验 identity、再验 digest/key set、最后原子接受 observation，不得丢弃后再 fetch。OpenRouter `/api/v1/key` 使用这一原子路径；Codex 没有所需 identity source contract，保持 fail closed。历史 `AQ-R10-001` 与顶层 marker 只记录当时审计态。

## 5. Adapter 认证变体矩阵

| Adapter | provider/auth variant | region | Desktop/core binding | Hermes 可选扩展 | 目标状态 |
| --- | --- | --- | --- | --- | --- |
| DeepSeek | `open-platform/api-key` | `global` | `env` 或 `system-credential`，1 个 `quota-read` binding | `hermes-env:DEEPSEEK_API_KEY` | 1B Supported 候选 |
| OpenRouter | `current-key/api-key` | `global` | macOS Keychain `system-credential` 或显式 `env`，1 个 `quota-read` binding | 可选独立 `hermes-env` | 1B Supported 候选；真实门禁前不计数 |
| OpenAI Codex | `chatgpt-codex/official-cli` | `local` | 0 个 binding；`official-cli:codex` profile | 不读取 Hermes Token | `experimental/incompatible`、默认关闭、不计 MVP |

API Key 的 401 不自动刷新，返回 `reauth_required`；403 按 endpoint contract 映射 `not_entitled`。OAuth/Keychain 更新由受信任 backend 的显式重新认证动作完成，core 随后重新调用 `resolve()`；official-cli 由其客户端管理登录。Hermes 引用只在可选包存在时合法，Desktop 配置不能隐式退回 `~/.hermes`。

### 5.1 `planned/no-contract` Provider 升级门槛

Kimi Coding Plan、MiniMax 中国区与 GLM/Z.AI 在 schema v1 只有路线图名称：没有 auth/provider variant、region、binding、capability、NetworkPolicy 或可执行 manifest；配置引用稳定返回 `adapter_not_distributable`。未来版本必须先取得官方文档或真实 opt-in 协议证据，并在同一个版本化变更中提交精确出口、认证/地区、时区、完整 capability/语义契约、脱敏 fixture、错误映射和 lifecycle 变更，才能进入 Experimental。不得依据路线图名称推断窗口或认证方式。

### 5.2 OpenAI Codex 的隔离原则

Agent Quota 独立包使用 Codex app-server 的官方本地接口，不读取或复制 `$CODEX_HOME/auth.json` 中的 Token。可选 Hermes 包也不得改用 `~/.hermes/auth.json` 或触发跨客户端 Token 同步。

Codex Adapter 不得获得整个 app-server 协议的通用调用能力。业务方法允许列表只有 `account/rateLimits/read`，另允许启动协议所必需的 `initialize`/`initialized` 握手；任何其他方法均在本地发送前拒绝。尤其必须拒绝会消耗重置额度的 `account/rateLimitResetCredit/consume`、登录/登出、配置写入和发送邮件等方法。

连接必须逐字实现[设计方案第 8.4.1 节](design-proposal.md#841-codex-json-rpc-连接状态机)：官方 app-server wire envelope 省略 JSON-RPC header，任何 frame 出现 `jsonrpc` 字段都拒绝；success 恰为 `{id,result}`，error 恰为 `{id,error}`。固定 argv、initialize/initialized、完整排序 opt-out notification 集、`account/rateLimits/read`、monotonic ID correlation 和有限 error-code map 都纳入 schema bundle；收到已 opt-out notification 或任何 server request 均终止连接且不回应。Codex version 只接受 `aq-codex-cli-v1` 的 64-byte single-line ASCII grammar，拒绝 pre-release/build/leading-zero/multiline，按 integer tuple 比较；构建器与 probe 共用 golden vectors。

额度响应只按[设计方案第 8.6 节](design-proposal.md#86-codex-rate-limit-唯一映射)解析：MVP 只消费顶层 backward-compatible `rateLimits` 并声明三项 capability。bucket map absent/null/空均合法；非空允许有界 1..16 项，逐项验证 key/limitId、深度/节点/schema，且必须恰一项与顶层 canonical 相等。其余合法 bucket 验证后丢弃，不生成主体/能力或输出；零/多匹配、错型、超界在 probe 阶段 `unverified_version`。primary/secondary/reached 仍按 absent/null/value 封闭映射，动态 key 统一为 `<map-key>` 且不持久化。

## 6. AdapterManifest 与能力协商

每个可执行 Adapter 必须提供 `extra=forbid, frozen=True` 的机器可读 `AdapterManifest`，完整 meta-schema 只以[设计方案第 8 节](design-proposal.md#8-provider-adapter-sdk)为准。一个 profile 原子绑定 variant/region/auth/endpoint、CredentialRequirement、SubjectSpec、唯一 endpoint budget group、NetworkPolicy、IdentitySourceContract 与适用 StructureContract；预算数值只存在于 group 引用的 versioned BudgetPolicy。通用 loader 独立闭包全部引用；未知、重复、悬空、未使用或重复数值均拒绝。

IdentitySourceContract 的 source kind、binding kind、profile、credential purpose/RPC endpoint、allowed evidence fields、stable/ephemeral basis、domain 与 contract generation 是封闭字段。只有 stable source 且明确允许 upstream subject 时才能引用唯一 ProviderIdentityDomain；否则 cohort 必须落到 endpoint budget group 的部署级 conservative 分支。DeepSeek 只登记 credential generation evidence、无 upstream domain，并固定映射余额 endpoint 到保守组。OpenRouter 也只登记 `openrouter-credential-generation-v1`，由已验证 binding+credential generation 隔离 access/cache；官方页面仅证明 `creator_user_id` 字段存在，没有证明长期稳定或不可回收，因此不登记 upstream domain，rate cohort 固定落到 `openrouter-current-key-global-v1` 的 endpoint/deployment conservative 分支。Codex 只登记 endpoint budget group，未登记 verified-stable identity source/domain；当前决定禁止增加 `account/read` 或从 rate-limit payload/进程/principal 猜身份。历史 `AQ-R10-001` 仅为非规范性索引。

协议采用 `ProtocolContract` 判别联合：ordered 分支声明登记的 version scheme/comparator、支持范围和有序 tested min/max；Codex 固定 `codex-cli-v1` 且要求 schema hash。DeepSeek/OpenRouter 官方 HTTP 与 FakeAdapter 没有协议版本号，必须使用 `versionless + evidence_id`，不得伪造 `0/latest` 或出现 nullable 测试边界。`test_only` 只进入独立 testkit；`planned/no-contract` 不可执行。全部可执行 lifecycle 要求 adapter SemVer、完整协议合同与可复现 assurance；Supported/GA 另要求受信任且未撤销的 `release_attestation_id`。

schema 与发行证据不得含糊：Codex `protocol_schema_hash` 只按第 8.4 节 stable bundle；`release_assurance_id` 只按第 8.3.0 节 exact recipe。detached publisher attestation 必须使用 `aq-release-attestation-envelope-v1` 绑定包名、版本、文件名、最终 raw wheel digest、adapter payload、assurance envelope/report/build proof digest、sequence 与期限，并按 distribution-specific release key set/threshold 验证。生产安装从 installer 内嵌 genesis anchor 或已安装 current trust bundle 起步，逐个验证连续 trust chain；新 root 不能自签跳过旧 root threshold。release directory 恰有固定 control set 与 signed plan target set，不接收第三方 lock 或 source-review 工件；目标代码执行前先按 `aq-bounds-v1` 限 raw bytes/AST/count，再验 chain/plan/attestation/hash，最后在 staging 生成 lock 并调用 pip。`RECORD` 仅是 wheel 内部完整性，不是信任锚。普通 probe、用户配置或 sdist 本地构建不能生成这些发行证据。

`probe(ProbeContext)` 在正式刷新前验证：

1. core 支持该 Adapter API 版本。
2. principal 的 variant/region/auth/binding/endpoint profile 符合 manifest。
3. 官方 CLI 或上游协议版本落在已验证范围，必需的只读方法存在。
4. Adapter 返回可验证的短命 IdentityEvidence；core 派生 `verified_stable` AccessIdentity。零 binding official-cli 缺少可信账户/会话代际 evidence 时为 `incompatible`，正式 `fetch` 不执行。
5. `ProbeResult` 必须命中 `core-safety-contract-v1#/probe_result_contract` 的封闭判别联合：failure/HTTP/offline 分支禁止 evidence，只有 official-cli success 恰有一份官方 evidence；它不返回 AccessIdentity、cache identity、rate cohort、assurance 或 discovery DTO，业务发现必须另调 `discover(DiscoveryRequest)`。
6. 未知协议、缺少方法、身份不稳定或返回与 manifest 冲突时 fail closed，正式 discovery/fetch 不执行。

Codex 只保留构建时生成/核验的 canonical app-server schema hash、最低/最高已测试 CLI 版本元数据与离线 fixture/parser 测试。当前 lifecycle 固定为 `experimental/incompatible`、默认关闭；运行态不得启动 Codex CLI、读取 `codex --version`、发送 `account/rateLimits/read`/`account/read` 或接受 IdentityEvidence，因此不会升级为 Supported，也不会执行正式 discovery/fetch。当前不存在已批准的 Codex subject evidence source；未来改变必须新增合同版本并重新审计。

`ProbeCompatibility` 的封闭值为 `compatible|incompatible|auth_required|unavailable|unverified_version`。`unverified_version` 只表示 probe 版本/bucket 超出已验证范围；`reauth_required` 只属于 auth snapshot；三个 discovery missing reason 为 `not_entitled|unsupported_version|temporarily_unavailable`。本地 `not_authorized` 只返回 OperationError。missing/subject/capability 受 manifest 上限；未知、重复、悬空、越 scope seed或外部 ID 使整批 `invalid_discovery_result`。

### 6.1 Adapter 返回边界

core 不信任内置 Adapter 的标识或基数。`probe/discover/fetch` 返回后、任何缓存/LKG/计数写入前，必须验证：

- ProbeResult 先按 `kind + mode` 完成 branch closure、context binding、evidence lifetime 与禁止派生字段校验，再允许 official-cli 路径执行 identity derive；unknown/cross-profile/expired evidence 在任何写入前返回 `adapter_contract_violation`。ProbeResult 不含 discovery；DiscoveryResult 的 adapter/principal、同批 handle/seed scope/selector/label/missing 和上限命中请求/manifest，不能返回正式运行对象。
- FetchBatchResult item keys 或 FetchBatchFailure request keys 与请求集合完全相等且每 key 恰一项；空、漏、重复、额外、跨 subject 整批拒绝。本地 scope 拒绝不进入 Adapter，上游 entitlement 缺失使用 unavailable `not_entitled`。
- observation kind/unit/value/semantic contract 或 failure category 命中 manifest。Adapter 不得返回 Snapshot/LKG/freshness/expires_at，也不得读取 cache/registry。
- 完整边界通过后，core 原子读取当前 generation LKG并合成 snapshots：success/Provider unavailable 用精确 TTL；failure 有 LKG 为 stale、无 LKG 为 expired；一次事务提交完整批次和计数。

任一违规整批返回操作级 `adapter_contract_violation` 或 `invalid_discovery_result`，不得创建伪快照、部分写入或更新 LKG/成功时间/失败计数，日志只记 endpoint/adapter 与违规类别，不保存返回值。恶意 FakeAdapter 必须覆盖跨 principal/subject、正式 ID、额外/重复 capability、错误 kind/unit/contract/version、恶意 missing/label/selector；断言配置、所有运行表和其他主体不变。

## 7. 凭据与网络出口绑定

Provider 与 CredentialRef 匹配还不够。每个 Adapter 必须随代码提交不可由普通用户覆盖的 `NetworkPolicy`：

唯一 meta-schema 是设计方案第 8 节的 `HttpEndpointSpec/LocalRpcEndpointSpec/TransportDeadlinePolicy`。endpoint 原子绑定 ID、method/RPC、逐段 path 参数、单值 query、auth injection、response/frame 与 deadline；禁止 method/path/RPC 平行元组。DeepSeek 只有 `deepseek-user-balance-v1 = GET /user/balance`；OpenRouter 只有 `openrouter-current-key-v1 = GET /api/v1/key`；两者都无 path param/query/body。Codex 三个允许 RPC 各有 endpoint spec。`NetworkPolicyHandle.endpoint_id` 必须唯一命中，通用 loader 不调用 Adapter 私有代码即可构造/拒绝。

HTTP Adapter 的统一强制项：

- 只允许 `https` 和显式列出的规范化域名，默认只允许端口 `443`；配置文件不得接受任意 `base_url`、IP 地址、URL userinfo 或通配域名。
- `httpx.AsyncClient(trust_env=False, follow_redirects=False)`；不读取 `HTTP_PROXY`、`HTTPS_PROXY`、`ALL_PROXY`、`NO_PROXY`、`SSL_CERT_FILE` 或 `SSL_CERT_DIR` 等环境配置。
- schema v1 代理恒关闭；不存在 Provider/用户级启用开关。未来能力只能通过新 schema/单独评审加入。
- TLS 证书校验强制开启，最低 TLS 1.2；代码和配置均不能提供 `verify=False`。重定向响应直接失败，不把 Authorization/Cookie 转发到新位置。
- timeout 只引用 manifest policy：HTTP queue/attempt/aggregate=1/6/9 秒，connect/read/write=2/3/3 秒；不得在本文另设值。
- MVP 请求发送 `Accept-Encoding: identity`，只接受空值/`identity`；使用 `AsyncClient.stream()`，先拒绝超过上限的 `Content-Length`，再通过 `aiter_raw()` 在读取过程中累计字节，超过默认 1 MiB 立即关闭响应，不能先 `await client.get()` 完整载入后再检查。
- 若未来某 Adapter 必须支持 gzip/br，NetworkPolicy 必须显式列出，并分别限制 wire bytes 与解压后 bytes；实现使用受限流式解码，合约测试覆盖超大 chunked、伪造 Content-Length 和压缩炸弹。
- 在解析凭据、设置认证头和发送请求前完成 scheme/host/port/method/path 校验；日志只记录稳定的 endpoint ID，不记录完整查询参数或响应正文。
- Adapter 不得在跨 principal 共享的客户端上设置默认 `Authorization`、Cookie 或其他身份头。连接池可以共享，但认证材料必须在已校验目标的单次请求上注入；任何需要 Cookie jar 或可变会话状态的 Adapter 必须按 `(principal_id, cache_identity, endpoint_profile)` 隔离实例并禁止跨身份复用。

schema v1 的 HTTP surface 只允许 `method=GET` 且 `allow_proxy=false`；`POST`、request body、proxy、proxy auth、custom CA 和环境代理在 meta-schema 阶段拒绝，且 Credential Source 解析次数为 0。未来若需要这些能力，必须升级 schema 判别类型并另行冻结 body/proxy 信任合同，不能用 manifest 扩展字段开启。所有 int/Decimal/timestamp/bytes/process/discovery/concurrency/Retry-After 的上下界、checked arithmetic 和 fuzz gate 唯一引用[设计方案第 8.0 节](design-proposal.md#80-安全关键标量与资源上限)的 `aq-bounds-v1`；Provider/manifest 不得放宽。

HTTP 请求只能由 core 的结构化 endpoint builder 构造，Adapter 不得提供自由 URL。最终发送对象按以下唯一算法匹配 allowlist：只解析一次并拒绝 userinfo/fragment、控制字符、无效 UTF-8、反斜线、重复斜线、空 path segment、已编码或解码后的 `.`/`..`、双重/非规范百分号编码；host 先执行 IDNA2008 A-label，再 ASCII 小写并去一个尾点，禁止 IP literal（含混合/IPv4/IPv6 形式）和通配，端口省略时规范为 443。path template 参数先按字段 schema 校验，禁止 `/`、`\`、`%2f`/`%5c` 及 dot segment，再逐段 UTF-8 percent-encode；query 使用 endpoint 明示的有限 key、单值类型和确定排序，未知/重复 key 拒绝。校验在凭据解析前对 builder 的规范对象执行，设置认证后立即对 HTTP 客户端将发送的 method、canonical host/port/path/query 再比较一次；两次对象不同则拒绝。

恶意 URL corpus 必须覆盖大小写/尾点/Unicode/IDNA、IPv4/IPv6 变体、userinfo、fragment、默认/显式端口、单/双重编码、dot segment、重复斜线、模板分隔符和 query 注入；只有登记 endpoint 能进入凭据解析。

`local-stdio` 不复用 HTTP 字段。Codex 可执行文件只从安装器登记的绝对路径或用户显式选择后保存的 install ID 解析；每次启动前以 no-follow 打开并校验 canonical path、regular file、当前 owner/受信任系统 owner、不可被 group/world 写、device/inode 与登记一致，symlink/PATH 搜索/相对路径/确认后替换全部拒绝。启动固定为 `shell=False`、新进程组、关闭无关 fd，环境从空字典构造，只允许 locale、最小 `PATH`（若协议必需）和 manifest 显式变量，任何 `*_TOKEN/*_KEY` 等未列变量不得继承。

Codex frame 上限为 stdin 64 KiB、单 frame 256 KiB、stdout 1 MiB、stderr 256 KiB；deadline 只引用 `local-stdio-v1`：queue/attempt/aggregate=1/8/9 秒，handshake=3、request=6、process execution=7.5、TERM→KILL/reap grace=0.5 秒。handshake/request 都计入 execution，request 取剩余预算；每 principal 1 个、部署 4 个进程。超限/超时映射 `local_protocol_violation/local_process_timeout`，不保存原文；fake stdio 覆盖 3+4 成功、边界、排队、TERM→KILL→reap 与 orphan=0。

首批与候选 Adapter 出口登记：

| Provider | 允许出口 | 允许操作 | 状态 |
| --- | --- | --- | --- |
| DeepSeek | `https://api.deepseek.com:443/user/balance` | `GET` | 已由官方余额文档确认；不允许用户覆盖 base URL |
| OpenRouter | `https://openrouter.ai:443/api/v1/key` | `GET` + `Authorization: Bearer` | 官方 current-key endpoint，64 KiB，禁止 redirect/proxy；Supported candidate |
| OpenAI Codex | 固定的本机 Codex 可执行文件，`local-stdio` | 握手 + `account/rateLimits/read` | Experimental/incompatible；发送前拒绝 `account/read` 与其他 RPC，不正式 fetch |
| Kimi Coding Plan、MiniMax 中国区、GLM/Z.AI | 无 NetworkPolicy | 无 | `planned/no-contract`；schema v1 配置拒绝，不可启用 |

任何 Provider 的域名或路径发生变化，都必须通过 Adapter 代码与合约测试更新，不能让最终用户临时输入新地址绕过评审。

## 8. Adapter 接口与生命周期登记

每个 Adapter 在进入发行包前必须填写完整机器契约；未知接口性质或缺字段一律拒绝进入发行包，不能靠 Experimental 继续执行。

| Provider | 额度能力 | 接口性质 | 当前结论 | 编码门槛 |
| --- | --- | --- | --- | --- |
| FakeAdapter | 窗口、计数、多币种余额、状态 | 本地 fixture | `test_only`，只进入独立 testkit | 覆盖多 principal/subject/capability 组合；生产依赖闭包与用户 entry point 中不存在 |
| DeepSeek | `wallet-balances` + `wallet-availability`，CNY/USD entries | [官方 `GET /user/balance` 文档](https://api-docs.deepseek.com/api/get-user-balance/) | 公开 API；Supported 候选 | 固定出口、流式上限、多币种、`is_available` 与金额组成测试 |
| OpenRouter | current-key limit/remaining、daily/weekly/monthly usage、expiry status | [官方 `GET /api/v1/key`](https://openrouter.ai/docs/api/api-reference/api-keys/get-current-key) | 公开 API；Supported 候选，真实门禁前不计数 | Bearer、64 KiB、null/type/bounds、binding+credential generation identity、`creator_user_id` metadata-only、conservative cohort、401/403/429/5xx、Desktop E2E |
| OpenAI Codex | 协议 parser 的 primary/secondary/reached 安全 fixture | [官方 app-server 协议](https://github.com/openai/codex/blob/main/codex-rs/app-server/README.md) | `experimental/incompatible`、默认关闭 | 保留 schema bundle/allowlist；无 stable identity，不新增 `account/read`，零正式 fetch/cache/LKG |
| Kimi Coding Plan、MiniMax 中国区、GLM/Z.AI | 无 | 无可执行协议契约 | `planned/no-contract` | 取得协议证据后通过版本化升级一次性增加完整 manifest，不得推断能力 |

### 8.1 DeepSeek `SemanticContract`

响应必须有 boolean `is_available` 和 1..2 个唯一 CNY/USD `balance_infos`。`total_balance/granted_balance/topped_up_balance` 只接受设计方案 `aq-decimal-38-18-v1` 的 ASCII 非负普通十进制字符串，先执行 bytes/整数位/小数位/总 significant digits hard bound，禁止符号、指数、空白和 locale 分隔符，再用 Decimal 精确解析；每项必须满足 `total = granted + topped_up`。合法 true/false 分别生成 `StatusValue(available)` 与 `StatusValue(insufficient_balance)`，后者固定 severity 为 high，不能显示为“可正常调用”。缺字段/错类型/未知币种/非法金额整批映射 `schema_changed`；空/重复币种、负数、金额错列或组成关系不等整批映射 `semantic_suspect`。两项 capability 原子提交，失败时保留 LKG 则 stale、否则 expired，且不覆盖成功基线。

### 8.2 OpenRouter `SemanticContract`

机器权威源是 `core-safety-contract-v1.openrouter_adapter_contract`，官方资料核验日期为 2026-07-19：[`GET /api/v1/key`](https://openrouter.ai/docs/api/api-reference/api-keys/get-current-key)、[`GET /api/v1/credits`](https://openrouter.ai/docs/api/api-reference/credits/get-credits)、[Authentication](https://openrouter.ai/docs/api/reference/authentication)、[Limits](https://openrouter.ai/docs/api/reference/limits)。MVP 只调用 `/api/v1/key`，不为账户 credits 索取 management key；`/credits` 保持 planned/显式 opt-in。

response 顶层必须恰有 required `data` object；未知字段只在全局 bounds 后忽略，不能参与 identity/cache key、结构指纹 value 或展示。官方 OpenAPI 把 `creator_user_id` 列为 required `string|null`：null 表示没有 observed metadata，非 null 必须是 `1..256` UTF-8 bytes 非空字符串且只形成 authenticated observed metadata，禁止展示/日志，也禁止进入 UpstreamSubjectEvidence、ProviderIdentityDomain、access/cache identity、query generation 或 rate cohort；缺失、空字符串或其他错型整批拒绝，null/非 null/值变化都不改变身份或 cohort。已验证 API key binding 与 `CredentialResolution.generation` 共同形成 access/cache identity，凭据代际变化必须改变该身份；rate cohort 始终使用 endpoint/deployment conservative group，不能因复制 principal/binding 扩容。

`limit`、`limit_remaining` 都是 required，接受 JSON integer/number 或 null；number 必须 finite、非负、无 exponent，并精确转换为 `aq-decimal-38-18-v1`，bool/string 拒绝。只有两者同时 null 才表示当前 API key 没有 per-key cap，不表示账户余额无限；nullability 不匹配直接 fail closed。finite pair 必须满足 `0 <= limit_remaining <= limit`，违反为 `schema_changed`，不能单独把 `limit_remaining=null` 展示为 unlimited。`usage|usage_daily|usage_weekly|usage_monthly` 为 required finite 非负 number；`limit_reset` 为 null 或 `1..64` bytes 安全文本，未知值只能显示“上游 reset policy”，不能猜日期；`is_management_key` 为 required bool。官方 OpenAPI 的 `expires_at` 不在 required 列表：absent 投影 `unknown/not supplied`，null 投影 `no expiration`，string 必须为 RFC 3339 UTC并投影 known expiry；其他类型拒绝。弃用 `rate_limit` 只忽略，不产生 capability/rate budget。

DeepSeek 与 OpenRouter 的 endpoint group、cohort、reservation 和 ledger row 始终分离；两者只因当前冻结的 documented public API floor/hour 参数完全相同而共同引用 provider-neutral `documented-public-api-budget-v1`。任一 Provider 未来要求不同 floor/hour/blocked-until 语义时必须新建版本化 policy 并改变 query generation，不得修改共享 policy 后静默影响另一方。

能力固定为 `openrouter-key-limit|openrouter-key-remaining|openrouter-key-usage-daily|openrouter-key-usage-weekly|openrouter-key-usage-monthly|openrouter-key-expiry-status`，全部引用 `OPENROUTER_FRESHNESS_SECONDS`。它们描述 current key cap/usage，不是 total account credits、法币余额或模型请求 rate limit。401=`reauth_required`、403=`not_entitled`、429=`rate_limited`、5xx=`provider_error`；错误正文不进入投影。promotion gate 必须覆盖 missing/null/number/string/bool/exponent/negative/over-precision、identity rotate、management/non-management key、expiry、wire/decoded 上限与 Desktop 并发/重认证。

### 8.3 Codex `SemanticContract`

`GetAccountRateLimitsResponse.rateLimits` 只作为 Experimental parser/protocol 安全表面，top-level 字段必填且为对象。bucket map 使用第 5.2 节有界 1..16/恰一 canonical 匹配合同，额外合法 bucket 只验证后丢弃。primary/secondary/reached 逐一按 absent/null/value 冻结；因为没有 stable identity，产品不得把这些 observation 接受为正式快照、cache 或 LKG。动态 limit key 不进入任何持久化或输出。

## 9. Breakage Protocol

### 9.1 结构指纹

`source_type=undocumented` profile 必须恰好引用设计方案的 `StructureContract/BreakagePolicy`；合同机器化冻结 path ID、required/optional types、map-key 规则、基数/深度/总节点、fingerprint recipe、失败类别和恢复 policy。public/official profile 不得引用，缺失/悬空/重复/未使用在 offline loader 拒绝，Adapter 私有解析器不能补合同。

每个 Provider 先按静态 schema 白名单提取路径，再生成路径与基础类型集合，例如：

```text
$.data.windows[]:array
$.data.windows[].used_percent:number
$.data.windows[].reset_at:string
```

排序后计算 SHA-256。数组只记录元素结构，不记录长度和内容。对象键不能默认视为字段名：响应中以邮箱、用户 ID、组织 ID 或账户号作为键的映射对象必须先识别为 map，并统一记录为 `<map-key>`；未知对象键默认丢弃，不能出现在指纹、差异日志或告警中。

以下字段和值即使出现也必须在指纹输入前删除或归一化：

- Authorization、Cookie、Token、Key、Secret。
- 邮箱、手机号、用户 ID、组织 ID。
- 余额具体值、额度具体值和时间戳值。
- 动态邮箱、手机号、用户/组织/账户 ID 形式的对象键。

仅靠字段名黑名单不构成充分脱敏。实现必须同时使用 Provider 静态路径白名单、动态 map-key 归一化、值类型检查和脱敏测试。

### 9.2 语义与单位漂移处置

结构指纹相同只代表白名单路径与基础类型相同，不代表含义、单位或缩放比例相同。core 必须在正式写入前执行 AdapterManifest 中版本化的 `SemanticContract`：

- `canonical_unit` 与 `scale` 冻结上游数值如何转换为百分数点、货币主单位或计数单位；Adapter 不得在运行时猜测 `42` 与 `0.42` 的含义。
- 硬值域之外直接拒绝；值域之内仍执行 Provider 专属 canary，例如在足够样本后长期异常小的百分比，或无合理业务事件时余额发生数量级跳变。
- canary 必须声明最少样本数、观察窗口、容差、缺样行为与人工/版本升级恢复流程。不得把“所有小于 1 的使用率”写成跨 Provider 通用规则。
- 命中时不覆盖最近成功语义基线或 last-known-good，返回 `health=semantic_suspect`；有旧值为 `stale`，无旧值为 `expired`。只有更新后的合约/fixture 通过 probe，或满足已冻结的恢复规则后，才能接受新基线。
- `schema_fingerprint`、`semantic_contract_id` 和检测结论一起进入诊断，但不记录原始余额、额度或时间值。启发式是可疑信号，不是正确性证明。

### 9.3 结构漂移处置

1. 新指纹与最近成功指纹一致：进入正常解析。
2. 指纹不同但已知必要字段仍存在：在隔离解析器中尝试解析，结果标记 `health=schema_changed`，不立即覆盖成功基线。
3. 必要字段缺失或类型不兼容：停止解析，绝不抛出到聚合器顶层。
4. Adapter 返回完整 key 集的 `schema_changed` failure；core 有当前 generation LKG 时合成 `stale+schema_changed`。
5. core 无当前 generation LKG 时合成 `expired+schema_changed`，UI 显示“暂不可用”；Adapter 不读取 cache/LKG。
6. 记录新增/缺失路径、状态码、适配器版本和时间；不保存原始值。

### 9.4 连续失败与恢复

本节下表是所有文档和实现的**唯一规范失败源**。每个 `(principal, subject, capability, query_contract_generation)` 为每个类别保存独立计数/paused reason；一种失败既不增加也不清零另一种。`consecutive` 表示该类别两次事件间没有一次通过其唯一恢复事件，重启不清零。操作级本地错误不创建快照，但仍按表更新自己的计数；Provider 业务错误按设计方案状态矩阵生成快照。

| 类别/表面 | 第 3 次或首次动作 | Scheduler | on-demand probe | on-demand fetch/refresh | `next_allowed` | 唯一恢复事件 |
| --- | --- | --- | --- | --- | --- | --- |
| `auth_error` snapshot | 第 3 次暂停该 generation 的全部 refresh | 不调用 | 仅在检测到凭据/官方会话代际变化后允许 | 代际改变且 probe 成功后只允许一次恢复 fetch | 不早于 endpoint group 的 BudgetPolicy | 新代际的 verified identity + probe + 恢复 fetch 均成功 |
| `network_error` snapshot | 第 3 次暂停 Scheduler | 不调用 | 到时允许 | 到时执行 probe，成功后 fetch | 指数退避 + policy | 同 generation probe 连通且 fetch 成功 |
| `rate_limited` snapshot | 不使用三次计数，首次记录限流 | 到时前不调用 | 可本地探测但不得绕过 fetch 时间 | 到时前拒绝 fetch | `max(Retry-After, policy)` | 到时后一次成功 fetch |
| `provider_error` snapshot | 第 3 次暂停 Scheduler | 不调用 | 到时允许 | 到时允许 fetch | 有上限退避 + policy | 同 generation 成功 fetch |
| `schema_changed` snapshot | 第 3 次暂停全部 fetch | 不调用 | 允许 | 禁止 | policy | 带新 assurance 且 Supported/GA 有有效 publisher attestation 的 generation 激活并 probe 成功 |
| `semantic_suspect` snapshot | 第 3 次暂停全部 fetch | 不调用 | 允许 | 禁止 | policy | 已冻结自动恢复规则满足，或带有效 attestation 的新 assurance generation 激活并 probe 成功 |
| `local_protocol_violation` OperationError | 第 3 次暂停全部 fetch | 不调用 | `local_only` 允许 | 禁止 | policy | 带修复 fixture/测试证据、且 Supported/GA 有有效 attestation 的新 assurance generation 激活并 probe 成功 |
| `local_process_timeout` OperationError | 第 3 次暂停 Scheduler | 不调用 | `local_only` 到时允许 | probe 成功后允许一次 fetch | 有上限退避 + policy | 同 generation local probe 与 fetch 均在 deadline 内成功 |
| `incompatible` probe | 首次即阻止 fetch，不使用三次计数 | 不调用 | 安装/协议变化后允许 | 禁止 | 直到安装/协议变化 | 新 generation/CLI 版本 probe 为 compatible |
| `not_authorized` OperationError | 首次即拒绝，不更新 Provider 失败计数 | 不调用 | 新 scope 前拒绝 | 新 scope 前拒绝 | 直到 scope/config 变化 | 新授权上下文完整重新验证 |
| `credential_backend_unavailable` OperationError | 首次 fail closed，不更新 Provider 失败计数 | 不调用 | 配置/后端变化后允许 | 不调用 | 直到显式配置或 backend 变化 | 同一 CredentialRef backend 可用并成功 resolve；不得 fallback |
| `adapter_contract_violation/invalid_discovery_result` OperationError | 首次整批拒绝，不更新 Provider 失败计数 | 当前调用失败 | 新 Adapter generation 前只可诊断 | 当前调用不写任何状态 | 直到 Adapter generation 变化 | 带新 assurance 的 Adapter generation 通过严格边界测试并 probe 成功 |

`release_assurance_id` 是 manifest、Adapter artifact、脱敏 fixture 与 schema/contract 报告的可复现摘要，不证明发布者身份；Supported/GA 还必须验证第 8.3 节 publisher attestation、trust bundle 撤销与包/version/wheel 绑定。运行时绝不声称在用户机器“运行了合约测试”。普通 probe、无签名 sdist 派生 wheel或仅重算公开摘要不能解除 schema/semantic/local-protocol pause。恢复事务只清对应类别计数/paused，并按 journal 安装唯一 active generation；不相关类别按表保留。

暂停期间按需 probe 仍受 source-type 限流；`undocumented` 的同一 cohort/完整请求至少间隔 5 分钟且同一 `rate_limit_cohort/endpoint` 每小时最多 6 次。只有 SchedulerHost 存在时才停定时任务并按[设计方案告警状态机](design-proposal.md#14-告警设计)发送一次维护事件。快照值与 ledger 分别使用 `RET-SNAPSHOT`/`RET-RATE-LEDGER`；启用期间的基线、计数、`last_success_at` 和暂停独立保留。对象 disable/delete/`manifest_removed` 严格按设计方案第 10 节生命周期表处理，不能用快照到期或复制 principal 清零。

## 10. 错误映射与安全消息

本节只登记 capability snapshot 的映射，不定义重试、计数、暂停、Scheduler/on-demand 允许动作或恢复。那些动作逐项且唯一引用[第 9.4 节失败表](#94-连续失败与恢复)，任何实现/摘要/golden case 都必须从该表生成；不得在本节复述成较弱规则。

| 上游情况 | `health` | `data_freshness` |
| --- | --- | --- |
| 成功且缓存未过期 | `ok` | `fresh` |
| 网络超时/断网 | `network_error` | 按 last-known-good 判定 `stale/expired` |
| 401/403 或明确认证错误 | `auth_error` | `stale/expired` |
| 429 | `rate_limited` | `stale/expired` |
| 结构指纹变化且解析失败 | `schema_changed` | `stale/expired` |
| 结构相同但单位/canary 可疑 | `semantic_suspect` | `stale/expired` |
| 供应商 5xx | `provider_error` | `stale/expired` |

这些是 capability snapshot 表面。强制操作错误的唯一机器源是 [`operation-contract-v1`](contracts/operation-contract-v1.json) 的 exact rows；Provider SDK 只导入生成产物，本文不维护 Markdown parser或第二张手写表。入口未知 operation 使用 `recognized_operation=null + bounded raw_operation_digest` 的零副作用 `OperationContractFailure`，不回显原文；受信任 core 内部表外转移只触发不序列化 fatal。严格序列化、retryable、safe params、LKG 与副作用由同一 artifact 全笛卡尔验证。

上游响应中的 `message`、错误正文、响应头和未知字符串均视为不可信输入，既可能包含敏感信息，也可能包含提示注入内容。Adapter 只返回本地稳定 `status_code` 与带判别标签的数字、币种、有限枚举或 UTC 时间参数；普通字符串不属于合法 display 参数。core 必须按 `status_code` 的参数名/类型/枚举 schema 再次校验，未知内容拒绝；日志、飞书和 LLM 投影只使用内置模板和本地枚举文案，不原样拼接上游文本。

## 11. 缓存、并发与手动刷新契约

- freshness 与 refresh floor 分离。每个可执行 capability 必须引用精确 `FreshnessPolicy`：DeepSeek 两项只引用 `DEEPSEEK_FRESHNESS_SECONDS`，OpenRouter 六项只引用 `OPENROUTER_FRESHNESS_SECONDS`；全部已接受 Provider observation 都必须到期，仅 core offline manifest-static not_applicable/unsupported 可永久。Codex parser 的历史映射 fixture 仍可引用 `CODEX_FRESHNESS_SECONDS` 做确定性测试，但 parser-only 不提交 observation、Snapshot、LKG 或 cache。policy digest 变化生成新 query generation。
- 手动刷新绕过普通 TTL，但不绕过 endpoint group 引用的 `BudgetPolicy`：数值、hour scope 与 digest recipe 只读 core-safety artifact；上游 `Retry-After` 只可用 `max(existing,upstream,policy)` 收紧。多 blocker 返回值唯一引用 `budget_ledger_contract.retry_after_aggregation`：同一 DB UTC sample 对 group+verified cohort union 取全部 active boundary 的最大值减 now 并夹到 `0..86_400`；无 active 时为 `None`。输入顺序或 primary reason 不得改变结果。计数与 blocked-until 必须持久化，不能靠复制 profile/principal/binding、切换同 group endpoint 或重启绕过。
- 纯本地 `official_cli`/`local-stdio` 不继承 HTTP 30 秒默认值，允许 manifest 明示独立地板（包括 0）；仍执行 TTL、singleflight、并发上限、官方协议限流与只读 RPC allowlist。本地 fixture/`estimated` 不计入网络请求次数。
- 返回结果必须说明是新请求、被最小间隔合并，还是使用 last-known-good。
- refresh 返回设计方案 `RefreshBatchResult` 的判别联合：1..32 个request result按request digest bytes排序，每个完整request key集恰一项。Provider业务失败分支对每个key携带同generation LKG stale或无LKG expired snapshot；rate-limit分支可携带有界Retry-After。只有pre-attempt deferred/capacity/timeout与outcome_unknown分支可为空snapshot。`FetchFailureCategory→health/status/snapshot`只按设计方案封闭映射；形成tuple后即使全部失败也返回完整batch success envelope。幂等保存完整canonical envelope并逐字节重放，不重新读取LKG或重算Retry-After。
- `query_contract_generation` 按设计方案第 9 节覆盖 endpoint/network policy、规范 selector、confirmed plan/subject metadata generation、capability kind/label/unit/currency/status/scale、semantic/display contract、Adapter/API version、ProtocolContract、canonical schema hash、release assurance 和发行 attestation。Capability 缓存/LKG 键包含 `(adapter_id, principal_id, subject_id, capability_id, cache_identity, query_contract_generation)`。
- 网络 singleflight 键至少包含 `(adapter_id, principal_id, cache_identity, query_contract_generation, endpoint_id, request_kind, normalized_subject_selector, normalized_capability_selector)`；只有完整请求、principal、访问代际与查询语义代际相同才可合并。
- 请求地板的限流键至少包含 `(adapter_id, rate_limit_cohort, endpoint_id, request_kind, normalized_subject_selector, normalized_capability_selector)`；小时总量键为 `(adapter_id, rate_limit_cohort, endpoint_id)`。缓存隔离身份与上游限流身份不得混用。
- `cache_identity` 与 `rate_limit_cohort` 只能来自 core 生成的 `verified_stable` AccessIdentity。凭据轮换、official-cli 切换账户或登录代际变化后不得复用旧缓存；共享上游身份的多个 principal 必须共享限流 cohort。
- 一个上游请求可返回多个 capability，但写缓存时必须按 subject/capability 拆分；不同 principal、选择器或 lease 不能复用结果。
- endpoint/selector/kind/unit/scale/semantic contract/Adapter/API version/测试边界/schema hash/assurance 变化时，使用设计方案第 10.2.1 节 migration journal 协调权威 TOML 与 SQLite；服务在恢复完成前关闭。journal 以 writer lease/fence 固定单一 roll-forward 计划并幂等切换唯一 active generation/删除旧运行数据；每次查询/调度和旧长任务提交前都复核 active runtime fence，TOML 外部编辑或 fence 变化立即关闭 gate。旧值不得作为新 generation 的 fresh/stale/expired/LKG/canary 返回。
- Adapter 不得保存“当前账户/当前 Token”一类可变全局状态；并发调用的认证上下文必须随请求显式传递。
- 手动刷新不得自动弹出网页登录；需要重新认证时只返回安全的恢复指引。
- 所有渠道 refresh 在调用 Provider 前使用绑定 `actor + operation + canonical scope` 的持久化幂等键。Desktop/辅助 CLI 共用本地 application service 与 `RET-IDEM-CLI`；远期 Web、飞书文本/卡片分别使用 `RET-IDEM-WEB`、`RET-IDEM-FEISHU-TEXT`、`RET-IDEM-FEISHU-CARD`。`running` 时崩溃恢复为 `outcome_unknown`，同键不得再次调用 Provider；singleflight/限流不代替幂等。
- rate limit check-and-reserve 只使用设计方案第 9.0 节同一 SQLite 的 `BEGIN IMMEDIATE` 状态机：每次attempt原子占group umbrella floor/hour并在身份已知时附加verified索引，二者指向同一reservation且不双计；unknown发送前检查group union。commit前可证明未调用的崩溃可回收，commit后任何crash/cancel/429/timeout都计预算，Retry-After只延长gate。singleflight只有leader reserve；复制进程/principal/identity cache丢失不扩容。
- rate writer、reservation、queue、slot、migration writer 与 temp claim 的所有时钟/时长/renew-at/max lifetime/expiry/takeover/deadline 只读取 [`lease-policy-v1`](contracts/lease-policy-v1.json) 的对应 policy ID；Provider 或 Adapter manifest 不能覆盖。
- v1 请求内 `max_attempts=1`。跨进程 global semaphore 固定 4，Provider limit 为 manifest `1..4`，pending queue 固定 32；按 Provider 内 FIFO、全局 oldest eligible 公平取得 SQLite lease slot，取消和 owner crash 按 fence 回收。parent aggregate 9 秒、投影 10 秒 hard boundary；慢请求变 partial result，绝无无界 task/backoff retry/orphan。

## 12. Provider 合约测试

每个要达到 Supported 的 Adapter 至少覆盖：

- 正常响应与所有支持的额度窗口。
- 重置时间转 UTC，包括无时区字符串设为 `timezone_unknown` 且不生成 `resets_at`、时间 severity 或告警。
- 401/403、429、超时、5xx。
- 可选字段缺失。
- 必要字段重命名和类型变化。
- 路径/类型不变但百分比缩放或余额数量级变化时触发 `semantic_suspect`，不覆盖 last-known-good；覆盖最少样本、误报和合约升级恢复。
- last-known-good 的 stale/expired 降级。
- auth/network/rate-limit/provider/schema/semantic/local-protocol/local-timeout 分别按第 9.4 节唯一表持久化计数/暂停；第三次后的 Scheduler、按需 probe/fetch 与恢复事件逐项匹配，无 SchedulerHost 时不会假装后台运行。
- `RET-SNAPSHOT` 到期不会清空结构/语义基线、失败计数、`last_success_at` 或刷新限制；principal/subject/capability 的 disable/delete/`manifest_removed` 逐项按设计方案生命周期矩阵清理，`RET-RATE-LEDGER` 不被误删。
- 日志、异常、快照与 fixture 中无凭据或个人信息。
- 同 Provider 的不同 principal/subject/capability/凭据不会串用认证头、缓存或结果。
- `env:`/system credential 原地轮换、official-cli 切换账户/登出重登会改变 `cache_identity`；零 binding official-cli 缺少 verified stable identity 时 fail closed，不能读取旧缓存。
- 并发请求不会因共享 HTTP 连接池、Cookie jar 或 Adapter 可变状态而串用 principal 身份。
- DeepSeek fake transport 只依赖不可变 FetchContext 即可得到规范 selector、当前 lease/AccessIdentity、NetworkPolicy 与 deadline；双 principal/selector 并发不串 Token/Cookie/selector，越 scope request 在 Adapter 前拒绝，完成/异常后 context secret 不可序列化或记录。
- endpoint、request kind 或规范化 subject/capability selector 不同的请求不会共享 singleflight/限流。
- AdapterManifest/probe 覆盖支持/不支持的 auth variant、region、binding 数量、endpoint profile、ordered/versionless ProtocolContract、adapter version、canonical schema hash、release assurance、受信任/撤销 attestation、AccessIdentity assurance 和封闭 capability 缺失原因；逐项变化 generation 必变。
- 通用 manifest loader 不调用 Adapter 私有代码即可接受 DeepSeek/OpenRouter/Fake 正例与 Codex Experimental-incompatible manifest，并拒绝未知 plan/label/currency/status/display 参数、重复/悬空 policy/schema/canary 引用、错误 kind 分支、不可比较 ordered 边界和 versionless 伪版本。
- Supported/GA wheel 在离线 trust bundle 下验证包名/版本/raw wheel digest/payload/assurance/签名者/有效期/撤销/sequence；篡改 code/manifest/fixture/report/sidecar/RECORD 后即使重算公开摘要也不能通过。`--no-binary :all:` 的 Provider sdist 派生 wheel 没有该最终 wheel attestation 时只得到 `adapter_not_distributable`、零 Provider 调用且不能解除 pause。
- 严格模型正反例覆盖未知枚举、kind/value 错配、重复币种/ID、非有限 Decimal、非法时间顺序，以及 `unverified_version/reauth_required/not_entitled` 的唯一落点。
- `network_mode=offline` 的网络/Credential Source/子进程计数均为 0；local_only/network_allowed 越权调用拒绝。恶意 Adapter 返回正式 ID、跨 principal/subject、额外/重复 capability、错误 selector/kind/unit/semantic contract/version、未知/超量/悬空 missing reason 时整批操作错误，配置/缓存/LKG/失败计数均不变。
- endpoint/network policy、selector、kind/label/unit/currency/status/scale、semantic/display contract、Adapter/API version、ProtocolContract、schema hash、assurance、attestation 各自改变会生成新 `query_contract_generation`；旧缓存/LKG 不可见。对文件写入/fsync、journal commit、rename/目录 fsync、DB commit、checkpoint 逐点 kill，恢复必须幂等收敛到 journal 的新态。
- `public_api`、`undocumented` 与 `official_cli` 使用各自刷新地板/小时上限；相同访问材料/账户经不同 binding/principal 配置仍共享 cohort，进程重启不能绕过持久化限制，本地 official-cli 不被误套 HTTP 默认值。无法验证身份时使用部署级保守 cohort。
- `system-credential` backend 不可用时返回稳定错误且不回退 `env:`；自由格式/含邮箱或 Token 的记录 ID 被拒绝或迁移，dry-run 只输出运行内类型化句柄，不输出原始 ID、label、selector、外部 ID 或完整 CredentialRef。
- schema v1 告警测试覆盖 `reset_pressure` 缺失/非法 severity 的拒绝，以及多 tier/多策略/health 同时命中时固定取最高严重度。
- `WindowValue` property-based 测试覆盖全空测量、负数/零 duration、used/limit 单缺、负绝对值、超限、零 limit 和百分比/绝对值超出 manifest 容差；仅百分比、仅完整绝对值与容差内双表示各有 golden fixture，非法批次写缓存前拒绝。
- DeepSeek fixture 覆盖 `is_available` true/false、CNY/USD 单/双币种、空/重复/未知币种、非法金额字符串、金额错列与 `total != granted + topped_up`，严格得到第 8.1 节唯一状态并原子提交/拒绝。
- OpenRouter fixture 覆盖 `/api/v1/key` 的 required/optional/null/number/string/bool/exponent/negative/over-precision；`creator_user_id` 覆盖 null/string/empty/absent/change，`expires_at` 覆盖 absent/null/RFC3339/错型，limit pair 覆盖双 null、finite pair、nullability mismatch 与 remaining 大于 limit；另覆盖 management/non-management、401/403/429/5xx、64 KiB wire/decoded 上限。测试必须证明 API key binding+credential generation 改变 access/cache identity，`creator_user_id` null/变化不改变 identity/cohort，复制 principal/binding 不扩展 endpoint group budget，只有双 null 表示 per-key unlimited，且从不调用 management-key-only `/credits`。
- HTTP 客户端固定 `trust_env=False`、禁止重定向、强制 TLS/超时/响应上限，并拒绝未允许域名、端口、方法和路径。
- URL canonicalization corpus 覆盖 IDNA/尾点/IP literal、userinfo、单双重编码、dot segment、重复斜线、模板分隔符和 query 注入，并证明拒绝发生在凭据解析前。
- HTTP 响应使用 `stream()`；超大 Content-Length、chunked、非允许 Content-Encoding 和压缩炸弹在完整载入前终止。
- Codex Adapter 的 parser allowlist 允许 `account/rateLimits/read`，拒绝 `account/read`、`account/rateLimitResetCredit/consume`、登录/登出和配置写入等其他 RPC；产品层无 stable identity 时仍禁止正式 fetch。
- Codex fixture 对 primary/secondary/reached、window 内三个成员、limit/plan/map 字段逐项覆盖 absent/null/value，只验证 parser/协议拒绝语义；任何成功解析都不能产生正式快照/cache/LKG。配置始终为 Experimental/incompatible、默认关闭。
- fake local-stdio 覆盖可执行文件 PATH/symlink/inode 劫持、敏感环境、stdout frame/总量、stderr、挂起/fork/zombie；超限在固定 deadline/字节内回收进程组。
- 上游错误消息中的提示注入、Token、邮箱和控制字符不会进入快照、日志、飞书或 LLM 投影；core 拒绝普通字符串、未知 display 参数名/类型/枚举。
- 以邮箱/用户 ID 为动态对象键的 fixture 不会把原键写入结构指纹或差异日志。
- auth/network/rate-limit/provider/schema/semantic 的交错序列、credential rotate、Adapter generation 升级与 frozen semantic recovery 完全按第 9.4 节表恢复，普通 probe 不解除 schema/semantic pause。
- 告警虚拟时钟覆盖同 dimension 的 `open→resolved→open→resolved`、单调 episode、`fresh+unsupported` 恢复、对象 disable/delete/generation 切换和双 SchedulerHost，第二次恶化只生成/通知一个新 episode。
- Desktop/CLI/飞书/远期 Web 对同一 UTC instant 在 UTC、Asia/Shanghai、America/Los_Angeles 与 DST 跳变使用同一渲染函数；缺失/非法 IANA zone 明示 UTC fallback，timezone 不参与授权或缓存身份。
- subject delete/capability disable/manifest removal 的普通命令有引用时零写入，显式 cascade 的 dry-run/正式运行 plan digest 相同；legacy opaque/可安全重写/secret-like 或歧义 ID 各有唯一迁移结果。
- Desktop/CLI、飞书文本、卡片和远期 Web 的并发重复、完成后重试与 `running` 崩溃恢复符合绑定 actor/scope 的 at-most-once 契约。

fixture 必须人工脱敏并使用虚构数值。FakeAdapter 还必须覆盖一个 Provider 多 principal、一个 principal 多 subject、一个 subject 多 capability、多币种余额以及不兼容/未授权状态。
同一构建产物还必须加载 DeepSeek-only、OpenRouter-only 和混合三种虚构配置，证明命名 view 只返回其引用且不会改变授权结果；Codex 配置只能得到显式 Experimental/incompatible 状态与零 Provider 调用。

## 13. 编码与生命周期核验清单

- [ ] `schema_version=1`、principal/subject/capability 与严格迁移规则已冻结
- [ ] schema v1 判别式告警策略、脱敏 dry-run 与未知时区告警抑制已冻结
- [ ] AdapterManifest/probe、verified AccessIdentity 和 Adapter API 兼容范围已冻结
- [ ] 独立 testkit 的 FakeAdapter 多组合/多币种 fixture 已定义，生产依赖闭包无 Fake
- [x] DeepSeek 官方 `GET /user/balance`、`is_available`、CNY/USD 与金额组成语义已登记
- [x] OpenRouter 官方 `GET /api/v1/key`、Bearer、current-key 语义、identity separation 与 management-key `/credits` 非 MVP 边界已登记
- [ ] OpenAI Codex 最低/最高测试版本、schema hash 与 app-server probe 已确认
- [ ] Desktop/core 与 Hermes 扩展的 CredentialRef 命名空间已分离
- [x] Desktop macOS Keychain reference + `platformdirs` POSIX `0700/0600` 拒绝式权限基线已定义；Linux Desktop staged
- [ ] DeepSeek/OpenRouter NetworkPolicy 真实测试已通过；Codex 保持 Experimental-incompatible；Kimi/MiniMax/GLM 保持 `planned/no-contract`
- [ ] HTTP 客户端 `trust_env=False`、无重定向、TLS/超时与流式 wire/decoded 上限测试已通过
- [x] Codex 产品决策冻结：只保留握手与 `account/rateLimits/read` parser allowlist，不增加 `account/read`，无正式 fetch/cache/LKG
- [ ] 所有 Experimental Adapter 默认关闭
- [ ] Capability 缓存与网络 singleflight 使用完整 principal/subject/capability/selector 键
- [ ] 分 source type 的持久化刷新策略、跨 principal rate-limit cohort 与 official-cli 稳定身份/本地豁免已冻结
- [ ] 结构指纹不包含任何字段值或动态敏感对象键
- [ ] 语义/单位 canary、受限 display 参数与结构状态独立保留已冻结
- [ ] 真实凭据不会写入 SQLite、日志、fixture 或 Git
- [ ] Kimi/MiniMax/GLM 只有在同一版本化变更提交协议证据、出口、认证、地区、时区、fixture 与完整 manifest 后才可进入 Experimental；不阻塞 1A

## 14. v1.6 Provider 执行闭包

- manifest 的 profile 只保存 `endpoint_budget_group_id`；group 保存唯一 `budget_policy_id`，数值和 digest recipe 只在 `core-safety-contract-v1` 的 versioned policy 中出现。任何重复数值、悬空引用或同 group policy 不一致在凭据解析和 Provider I/O 前拒绝。
- official discovery/fetch 分别接收 `IdentityAndDiscoveryContext` / `IdentityAndFetchContext`，并只返回带同一 request digest 的 joint identity response。Adapter 不能把 probe payload 标记为可复用；core 必须先核验 identity evidence，后核验 digest/key set，最后一次性接受结果。
- online doctor/discover 的 reservation 拒绝使用 operation artifact 的共享结果表。预算阻塞是公开 `OperationError(code=budget_deferred)`；ledger/storage 失败只用登记的 safe code/params。所有拒绝发生在 Credential Source、HTTP、stdio 和缓存写入前。
- Codex wire validator 只能打开 bundle descriptor 的两个 roots：aggregate v2 schema 与 `v1/InitializeResponse.json`。引用文件缺失或 bit flip 拒绝/改 hash，未引用生成文件不改 hash。当前决策固定只保留握手与 `account/rateLimits/read` parser allowlist，不得增加 `account/read`，且不正式 fetch。
- LocalKeyRing 加载器按 artifact 重算 `aqk_`，验证 `(purpose,generation)` 唯一、每 purpose 一个 active、verify-only allowlist 与代际转移；完整 payload/envelope golden vector是互操作门禁。

## 15. v1.7 Provider 数据依赖闭包

- Adapter 调用前的输入分为两期：pre-reservation `*RequestPlan` 不含 receipt、credential lease 或 AccessIdentity；reserve 与 commit 成功后，core 才构造带 committed receipt 的唯一 final context。任何 Provider I/O 接受 plan、placeholder receipt 或可突变 context 都是合同失败。
- HTTP doctor/discover 使用 endpoint group 的 conservative cohort 先 reserve，因此所有 reserve rejection 的 credential read、Provider byte 与 cache write 计数均为 0。成功后 verified cohort 只能附加到同一 row，不能建立第二次 capacity、reservation 或 Provider attempt。
- operation artifact 的 `provider_io_data_dependencies` 是 exact path 证明：每条 provider path 都满足 request plan → reserve → commit → final context → Provider I/O。stage union、error code 和 exact trace 只从机器投影生成，本文不维护第二份表。
- Codex descriptor roots 精确包含 aggregate v2 与 `v1/InitializeResponse.json`；LocalKey golden payload eager 覆盖八个 purpose。历史 `AQ-R11-002` 与 marker 记录当时未决态；当前已决定不增加 `account/read`，Codex 保持 Experimental/incompatible 与零正式 fetch。
- 本文的 Provider 行为描述不能创建新的存储 surface；规范性声明只能使用安全模型登记的独立 record v1 `persist:v1:<surface_id>:<operation>:<owner_id>`。validator 移除 record 后仍独立扫描同 leaf 的普通 prose，因此同句、跨句、中文同义或一个 record 覆盖多个 signal 都 fail closed。

### 15.1 v1.8 Provider 验证边界

- registry 的 artifact/schema/fixture pin、schema 实际枚举的全部数组顺序策略、RepoPath、ProbeResult、operation exact path 与 lease typed formula 由固定 allowlist 的只读 validator 全量执行；任一失败都不得输出成功状态。
- `canonicalize-registry-v1.py` 只读验证 Provider 投影，不生成或覆写正文；五个 artifact pin 只从 registry 行投影到带 hash 的唯一 marker。
- 当前 checkout 中未跟踪的工具只能提供审计证据。生产或 0A 的 validator 身份必须由外部签名 release，或 VCS commit 加 raw SHA-256 与先前受信根授权固定，不能由工具自证或自 pin。
- Codex 产品方向已选择降级：不增加 `account/read`、不移除协议安全合同、不降低要求，正式 fetch 继续 fail closed；OpenRouter 取代第二 Supported 目标。全部静态变更仍等待 R20 独立审计。

### 15.2 v2.0 Provider 路径与发布证据

- discover/doctor 的 HTTP 与 `official_cli_zero_binding` 四条成功路径使用机器 `success_path_counts`；validator 从 step closure 反推 credential resolution、Source call、reservation 与 provider attempt。official-cli 的 Source call 固定为 0，HTTP 固定为 1，所有四条路径各有一张 reservation 与一次 provider attempt。
- operation 的完整 error rows 与 safe parameter schema 进入 design exact marker；任何 row 变化在 marker 重生成前失败。lease 的 deadline/expiry reference 同时验证 type、unit 与 clock domain，不能用“引用存在”代替可执行性证明。
- clean-install gate 要求显式 root 并验证 cwd/入口/root identity 与逐段 no-follow，固定并验证实际 Node/npm/Pandoc/Ajv、完整 npm package regular-file tree 与依赖实现树；它双次重放 validator/projection，并仅执行机器合同登记的 exact 50-case mutation sequence/count/recipe/verdict/digest。每条 recipe 固定 RepoPath、封闭判别 locator、exact before/after state、failure class、executor ID、顶层实现摘要和传递 helper call graph；gate 保留并逐段 no-follow 打开每个隔离 case root，独立读取 locator、重算 source/mutated digest、重新执行判定命令并分类 failure。所有摘要来自同一 immutable input snapshot；任一 helper-only 漂移、入口 symlink、根替换、源文件 symlink、并发替换、`schema-const` 重定向或 mutation 结果缺失/重复/伪造均 fail closed。
- 这些结果只构成当前 checkout 的审计证据。生产或 0A 仍需外部签名 release，或 VCS commit + tool raw SHA-256 + 先前受信根授权。Codex 已按当前决策降级；历史 `AQ-R14-001` 与顶层 marker 只记录当轮审计态。

### 15.3 v2.3 离线运行时与条件路径证据

- Provider/operation 合同验证只接受 bootstrap 固定的 CPython implementation、exact patch、ABI/platform、解析后 executable、framework 与标准库实现树；Node/npm/Pandoc/Ajv 的既有固定继续生效。npm clean install 只从仓库内 exact tarball closure 运行，空 HOME、空 cache、offline 模式下必须可复现。
- `status-none-v1` 的 LLM consent 是显式 conditional node：true 执行 consent stage，false 只跳过该专属 stage，missing/error 终止操作。三类 audience 与异常输入都由机器 truth table 覆盖，不能把“条件字段存在”当作执行语义证明。
- mutation runtime/result locator 绑定 gate 实际观察的 typed state 与完整 payload；descriptor 不变但实体改变、错误字段、不同 malformed shape 都产生不同证据或直接拒绝。Provider 正文的编号/父级/同级顺序与本地 anchor 也进入 fail-closed lint。
- R19 时 `AQ-R19-001` 等待用户选择；审计后已选择 Codex Experimental/incompatible + OpenRouter 第二 Supported 目标，不增加 `account/read`、不执行正式 fetch。Gate 0A 是否关闭仍由 R20 独立审计决定。

### 15.4 v2.4 固定启动链与动态审计终态

- Provider 合同的四个 Python入口只允许本地 checker 的 exact path/raw-pin allowlist；替代 shell、新 entry、symlink和entry drift拒绝，fd-bound entry字节避免path swap影响实际执行。但仓库 checker永远只返回本地审计证据，不能由环境变量或当前 checkout证明生产固定启动；正式 launch必须来自仓库外既有信任根 attestation。exact Darwin build覆盖系统 image，Python/Pandoc/Node所有非系统 loaded image逐项绑定canonical path、owner/mode/size/raw SHA与递归依赖边；`_hashlib/libcrypto`、`_lzma/liblzma`、Pandoc/GMP、opt切换和loader注入均在成功前门禁。
- 审计历史不再硬编码当前轮。manifest 派生 1..20 内实际输入集合，并以 open/zero判别状态表达下一轮 FAIL+resolution及最终 `PASS_ZERO_ISSUES`/无 resolution；Provider 当前 marker 只投影 artifact同源状态。
- 该轮 `AQ-R18-001` 已由第 19 轮重新确认并编号；当前 Codex 降级决策继续保持 incompatible、不增加 `account/read`、不执行正式 fetch，Gate 0A 结果等待 R20。

### 15.5 v2.5 全路径 image、R20 终态与 retry-after

- Pandoc/Node 从 `vmmap` 的全部 file-backed Mach-O 映射发现路径，不能先按 Homebrew/local 或登记 closure 筛选；Python使用同一 system/non-system 分类与 no-follow/regular规则。额外、缺失、digest、kind、symlink或 canonicalize 失败均在成功摘要前拒绝。
- open/zero history QA 分支闭合；R20 `PASS_ZERO_ISSUES`/无 resolution连续验证两次，非法resolution/issue/blocker/FAIL/R21/回退/marker漂移拒绝，R20 open明确耗尽轮次。
- retry-after 唯一读取 core machine contract的 `max(active_boundaries)-now`，group/cohort union、expired boundary、hard max和双进程虚拟时钟矩阵都进入 fixture/validator/gate。
- R19 历史 resolution 中 `AQ-R19-001` 保持 `BLOCKED_USER_DECISION`，不得改写；当前独立决策记录已选择 Codex 降级与 OpenRouter。Codex 保持 incompatible、不增加 `account/read`、不执行正式 fetch，R20 前不宣称 Gate 0A 通过。
