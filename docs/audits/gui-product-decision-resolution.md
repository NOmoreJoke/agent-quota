# GUI 产品决策处置记录（非审计轮次）

> 决策日期：2026-07-19  
> 状态：已确认，待独立 R20 对抗性审计  
> 适用对象：当前 `README.md`、设计方案、Provider 契约、安全模型与机器合同

<!-- AQ-NORMATIVE-PRODUCT-DECISION-V1:BEGIN -->
```json
{"codex":{"account_read":"forbidden","disposition":"experimental-incompatible-parser-only","persistent_cache":"forbidden","real_cli":"forbidden","runtime_fetch":"forbidden"},"decision_status":"confirmed-current-pending-independent-r20","history_membership":"forbidden-not-audit-not-resolution","live_document_links":{"README.md":"docs/audits/gui-product-decision-resolution.md","docs/design-proposal.md":"audits/gui-product-decision-resolution.md","docs/provider-contract.md":"audits/gui-product-decision-resolution.md","docs/security-model.md":"audits/gui-product-decision-resolution.md"},"openrouter":{"lifecycle":"supported-candidate","mvp_count_rule":"only-after-real-opt-in-gate","target":"get-current-api-key"},"product":{"cli_role":"auxiliary","mvp_platform":"macos","primary_surface":"local_desktop_gui","product_name":"Agent Quota Desktop"},"record_kind":"normative-product-decision-non-history","schema":"aq-normative-product-decision-v1"}
```
<!-- AQ-NORMATIVE-PRODUCT-DECISION-V1:END -->

## 1. 记录性质

本文记录第 19 轮审计结束后由用户确认的产品方向，不是 `round-19-resolution.md` 的修订，不计作第 20 轮，也不声称关闭 Gate 0A。第 1–19 轮审计与处置文件继续作为不可改写的历史输入；顶部 current-status marker 继续准确表达 R19 当时的 `BLOCKED_USER_DECISION`。

当前文档可把 `AQ-R19-001` 解释为已经获得产品选择，但只有新的独立 R20 审计才能建立新的权威 current status。若 R20 发现问题，必须按既有历史协议报告，不能用本文覆盖审计结论。

## 2. 已确认产品决策

1. 产品名为 **Agent Quota Desktop**，GUI 是 MVP 主入口；辅助 CLI 只服务维护、诊断、无障碍与自动化，并与 Desktop 调用同一 application service。
2. macOS 是唯一 Desktop MVP 平台；Linux Desktop staged，Windows fail closed。Linux core/CLI 能运行不等于 Linux Desktop 已支持。
3. Desktop 使用 Tauri 2/Rust trusted host、bundle 内 React/TypeScript 静态 renderer 与固定 Python core sidecar；默认安装不包含 Hermes、飞书、SchedulerHost 或 Web。
4. host 启动 sidecar 时只使用匿名 pipes/stdio，另以独立继承 pipe 传递每次启动的 256-bit session secret；MVP 不监听 loopback、TCP、Unix socket、HTTP 或 WebSocket。IPC request ID 每 session 从 1 开始按 unsigned 64-bit 严格递增，response 原样回显，溢出前终止。跨进程只传 `remaining_budget_ns`，不传 host 绝对 monotonic epoch；sidecar 收妥完整合法 frame 后以本地 monotonic clock checked-add 重建 deadline，同时受 host 9 秒 hard cap 约束。dispatch 前过期/越界/overflow 才是零 Provider I/O/零写入；dispatch 后 host timeout 必须 outcome unknown、禁止自动重放并 TERM→KILL→reap 至 orphan 为 0。生产 sidecar stderr 直接连接 OS null sink，原始 stderr 不进入日志、renderer 或 IPC。
5. renderer 只拥有封闭 Tauri command allowlist；机器合同逐 command 绑定 request/response reference，同源 DTO schema 与 nested ref 全部封闭、有类型、有界、脱敏，`config_change_set` 也只能引用 non-destructive change-set/change schema。renderer 禁止直接访问凭据、identity evidence、Provider transport、本地数据文件、网络、shell、进程、sidecar 或秘密输入。API Key 只能由 WebView 外的 host-owned native secure dialog 接收，或由其选择既有 Keychain item；React 只能请求打开 dialog 并接收 opaque ref/status，不能接收 keystroke、paste、value、length 或 SecretBuffer。dialog 要求 app foreground/key window、每 installation 单 active 与 host cooldown/spam fail-closed。host 另负责 sidecar 路径、签名、Team ID、raw hash、frame、correlation、budget/deadline、崩溃回收和原子升级。
6. purge、disable/delete/cascade 与 endpoint/auth/binding/capability/manifest destructive config diff 的 core 脱敏 plan 只在 Rust host-owned native confirmation surface 展示；plan digest、nonce、user-presence token 只在 host↔core。renderer 只能请求打开 trusted surface并接收 `cancelled|committed|status`，不能自行完成确认。
7. Desktop MVP 必须覆盖首次启动、凭据引用、账户/Subject 配置、额度总览、手动刷新、freshness/health/safe error、离线、后台刷新真实状态、重认证、脱敏导出、purge 二次确认，以及 loading/empty/partial/total failure 和无障碍状态。
8. 没有已安装且健康的 SchedulerHost 时，GUI 只能显示“仅按需刷新/未启用后台刷新”，不得以 renderer timer 或窗口存活暗示实时监控。
9. Codex 固定降级为 `experimental/incompatible`、默认关闭且不计 MVP：只保留离线 schema/allowlist/parser fixture，不启动或探测真实 CLI，不发送 `account/rateLimits/read`/`account/read`，不执行 discovery/fetch，不生成 Snapshot/LKG/cache。未来恢复必须新增合同版本、stable identity source 与独立审计。
10. OpenRouter `/api/v1/key` 成为第二个 Supported 目标，初始 lifecycle 为 `supported-candidate`；只有真实 opt-in 合同测试、签名发行与 Desktop E2E 都通过后才能升为 Supported 并计入 MVP。
11. OpenRouter current-key 契约固定为 Bearer `GET https://openrouter.ai/api/v1/key`。已验证 API key binding 与 credential generation 形成 access/cache identity；required nullable `creator_user_id` 为 null 时没有 observed metadata，非 null 也禁止进入 stable ProviderIdentityDomain、cache identity 或 rate cohort，后者固定使用 endpoint/deployment conservative group。`expires_at` 是 optional nullable，absent/null/RFC3339 分别表示 unknown/not supplied、no expiration、known expiry。只有 `limit=null && limit_remaining=null` 表示 per-key cap 不限；finite pair 必须满足 `0 <= remaining <= limit`，nullability mismatch fail closed。该 cap 不是账户总余额。需要 management key 的 `/api/v1/credits` 不属于 MVP，也不能被 current-key credential 隐式调用。
12. Hermes、飞书、SchedulerHost 与远期 Web 都是可选集成；它们的缺失不阻塞 Desktop MVP。远期 Web 必须是独立 host/认证表面，不复用 Desktop renderer 或 IPC。

## 3. 规范落点

- [`core-safety-contract-v1.json`](../contracts/core-safety-contract-v1.json) 的 `desktop_product_contract` 与 `openrouter_adapter_contract` 是上述产品/Provider 决策的机器源。
- [`design-proposal.md`](../design-proposal.md) 第 6.1、13、17、18、20 节定义 Desktop host/renderer/sidecar、GUI 状态、交付阶段与接受标准。
- [`provider-contract.md`](../provider-contract.md) 定义 OpenRouter identity/response/错误/发布门禁，以及 Codex parser-only 边界。
- [`security-model.md`](../security-model.md) 定义 renderer、host、sidecar、session/framing、升级与远期 Web 的信任边界。

## 4. 官方证据边界

以下 OpenRouter 官方页面于 2026-07-19 核验：

- [Get current API key](https://openrouter.ai/docs/api/api-reference/api-keys/get-current-key)
- [Get credits](https://openrouter.ai/docs/api/api-reference/credits/get-credits)
- [Authentication](https://openrouter.ai/docs/api/reference/authentication)
- [API rate limits](https://openrouter.ai/docs/api/reference/limits)
- [OpenAPI](https://openrouter.ai/openapi.json)

上述页面与 OpenAPI 支持 current-key endpoint、Bearer 认证、key cap/remaining、usage、expiry、`creator_user_id` 字段和 credits 的 management-key 边界；OpenAPI 明确 `creator_user_id` required 且 `string|null`，`expires_at` 为 `string|null` 但不在 required 列表。它没有保证 `creator_user_id` 长期稳定、全局唯一或不可回收。因此当前合同不得把该字段提升为 stable subject evidence。文档也没有证明 Agent Quota 已完成真实 Provider 测试、账户覆盖、签名发行或 Desktop runtime 验证，所以 OpenRouter 保持 candidate。

## 5. 本次变更范围

本次只修改当前规范与当前机器合同：

- `README.md`
- `docs/design-proposal.md`
- `docs/provider-contract.md`
- `docs/security-model.md`
- `docs/contracts/core-safety-contract-v1.json`
- `docs/contracts/schemas/core-safety-contract-v1.schema.json`
- `docs/contracts/fixtures/core-safety-v1.json`（同步中性公共 API 预算 fixture）
- `docs/contracts/retention-lint-v1.json`（移除当前正文不再需要的 dangling leaf exception）
- `docs/contracts/contract-registry-v1.json`（同步机器摘要）
- `docs/contracts/validate-json-schema-v1.mjs`（仅修复 stdin 的 UTF-8 分片解码，不放宽 schema）
- 本决策记录

未修改 `docs/audits/round-01-*` 至 `docs/audits/round-19-*`。没有创建应用代码、依赖、真实凭据、提交、分支、远端仓库或发行物。

## 6. 验证证据

最终交付必须在当前 checkout 依次执行下列三项门禁，并且只能在三项都退出 0、输出成功状态后声称静态规范通过机器验证：

- `/bin/sh docs/contracts/runtime-bootstrap-v1.sh docs/contracts/run-release-gate-v1.py --root .`
- `/bin/sh docs/contracts/runtime-bootstrap-v1.sh docs/contracts/run-validation-mutations-v1.py --root .`
- `npm run validate --prefix docs/contracts`

命令的实际状态与摘要只记录在最终交付回报，不回写本文，避免验证输入为了记录自己的结果而改变并形成递归摘要。本文中的命令集合和成功判定本身由最后一次门禁覆盖。

即使三项静态门禁成功，也只证明登记的文档/合同一致性与负向 mutation 行为，不证明 Tauri app、sidecar、Provider、签名/notarization、升级或无障碍 E2E 已实现。

### 6.1 UTF-8 helper 正确性修复

最终门禁前的确定性诊断发现，Node helper 原先把异步 stdin 的每个 `Buffer` chunk 单独隐式转成字符串。pipe 边界若切开中文等 UTF-8 多字节字符，就会在 schema 与 instance 的不同位置产生 U+FFFD，偶发伪报 `expected_headers must be equal to constant`。修复只在读取前调用 `process.stdin.setEncoding("utf8")`，由流解码器跨 chunk 保存不完整 code point；Ajv 版本、strict 选项、schema、instance 顺序和错误路径均未改变。

修复当时，同一含中文的 exact helper payload 连续执行 20 次均接受；在内存中人为改变 `retention_entry_registry.expected_headers` 后仍以原 const 错误拒绝。下表是 PRE20 修复前保存的证据快照；后续修复已经改变部分工具字节，因此它不表示当前 checkout，也不是仓库自授的生产信任根。当前摘要只在最终交付回报中从实际文件重算，避免本文自引用：

| 路径 | raw SHA-256 |
|---|---|
| `docs/contracts/canonicalize-registry-v1.py` | `c7d5d85b5df933fd2fa57872e1ecfe0cdc550be5690bbe33aa656e1aecfd31aa` |
| `docs/contracts/validate-contracts-v1.py` | `4ef7f08a378762f2fdaa5901c4360d5cb92c9b116a3c9fc9ef6431131c4aa924` |
| `docs/contracts/run-release-gate-v1.py` | `96fe68c3210317259de5eab68bb5a11df1ab79eaae1a3f14913989301e5f68af` |
| `docs/contracts/run-validation-mutations-v1.py` | `9d401bbcde57229d6ff38e5da2e4b8509a0088be12bb1552676b6027f98c1549` |
| `docs/contracts/validate-json-schema-v1.mjs` | `e481c27d81047910535c932d98909ca21469e3f0a72513ee581fa65f04cdfbad` |
| `docs/contracts/package.json` | `dcc7d9740aa1c6c9e12e05041fcd9f375b124095757c643b7265a2b9cf9774bc` |
| `docs/contracts/package-lock.json` | `4a0813d273120e93af343db6494d67528763c2d32540874f5ee0e9dec4ea031e` |
| `docs/contracts/runtime-bootstrap-v1.sh` | `b31579b70739f382da1dd48090ca1930be91ffff8bc645e199e4b98f3f8432cf` |
| `docs/contracts/python_runtime_guard_v1.py` | `06a01bff92a033562a1184ae6acd40a81ec2fff92ad8aebbfecdac9b7090ee00` |

### 6.2 PRE20 fail-closed 补强

- 本决策记录作为独立、非历史的规范输入进入 registry、immutable snapshot、input digest 与 release copy snapshot；它不进入 `history_entries`，也不得伪装为 audit/resolution。删除、bit drift、status/record-kind/history-membership 漂移和四份 live 文档任一反向链接漂移均有独立负向 mutation。
- renderer command 合同以 10 个 command row 和 29 个闭合 DTO schema 建立可执行 allowlist；request/response reference、nested reference、字段类型/界限/脱敏、host 重建字段与 commit policy 同源验证。未知、缺失、重复、重排、ref swap、nested secret 注入和 renderer 直提 destructive commit 均拒绝。
- sidecar budget 只使用 `remaining_budget_ns` 和 sidecar 本地 monotonic deadline；fixture 覆盖不同 epoch/offset、边界、跨 session 复用、上限、overflow、timeout reap/orphan 与 dispatched timeout 零写入误报。只有 pre-dispatch rejection 能承诺零副作用；dispatch 后是 outcome unknown 并由既有幂等/事务恢复裁定。

## 7. 尚未验证与下一门槛

- 尚无 Desktop host、renderer、sidecar 或 GUI 运行证据。
- 尚无真实 OpenRouter opt-in 账户、权限、null/错型/限流矩阵或多账户隔离证据。
- 尚无签名/notarized macOS bundle、受 foreground/single-active/cooldown 约束的 host-owned native credential/confirmation surfaces、`renderer-secret-input-path-absent`、`renderer-destructive-confirmation-token-absent`、u64 request ID、stderr null sink、sidecar 替换防护、IPC framing/session、崩溃恢复或原子升级证据。
- 尚无 DeepSeek/OpenRouter 都达到 Supported 的发行证据。
- 尚无 R20 独立对抗性审计结论；在 R20 通过前 Gate 0A 仍关闭。
