# Agent Quota

<!-- AQ-GENERATED-CURRENT-STATUS-V1:BEGIN -->
```json
{"design_version":"v2.5","gate_status":"ZERO_ISSUES_AUDIT_CONFIRMED","latest_audit_path":"docs/audits/round-20-audit.md","latest_audit_verdict":"PASS_ZERO_ISSUES","latest_issue_ids":[],"revision_round":20,"status_kind":"ZERO_ISSUES"}
```
<!-- AQ-GENERATED-CURRENT-STATUS-V1:END -->
<!-- AQ-NORMATIVE-DECISION-LINK-V1:docs/audits/gui-product-decision-resolution.md -->

> 上述 marker 是第 20 轮零问题终态，必须与 history manifest 保持一致；第 1–19 轮历史保持不可改写，审计后的用户产品决策仍见 [`gui-product-decision-resolution.md`](docs/audits/gui-product-decision-resolution.md)。`ZERO_ISSUES_AUDIT_CONFIRMED` 表示可进入后续 Gate 0A 工作，不等于实现完成或生产发布授权。

Agent Quota Desktop 是一个本地优先的独立桌面额度聚合产品。macOS 桌面 GUI 是 MVP 主入口；用户可配置自己拥有的认证身份、订阅、工作区、组织或钱包，并查看各主体真实存在的窗口、余额、计数、freshness、health 与安全错误。CLI 只承担维护、诊断、无障碍和自动化辅助；Hermes、飞书与 SchedulerHost 是可选集成，远期 Web 不是 Desktop GUI 的同义词，也不是 MVP 依赖。

## 当前内容

- [完整设计方案](docs/design-proposal.md)
- [Provider 与凭据契约](docs/provider-contract.md)
- [安全模型与分层门禁](docs/security-model.md)
- [Desktop GUI 与 Codex/OpenRouter 当前决策记录](docs/audits/gui-product-decision-resolution.md)
- [core safety 权威合同](docs/contracts/core-safety-contract-v1.json)
- [operation 权威合同](docs/contracts/operation-contract-v1.json)
- [LocalKey purpose 权威合同](docs/contracts/local-key-purpose-registry-v1.json)
- [lease 权威合同](docs/contracts/lease-policy-v1.json)
- [retention lint 权威合同](docs/contracts/retention-lint-v1.json)
- [合同与 JSON Schema 摘要注册表](docs/contracts/contract-registry-v1.json)
- [第 1–20 轮审计历史清单](docs/contracts/history-manifest-v1.json)与[固定离线 npm 包](docs/contracts/offline-npm-bundle-v1/)
- [完整只读合同 validator](docs/contracts/validate-contracts-v1.py)、[只读投影/pin verifier](docs/contracts/canonicalize-registry-v1.py)与[clean-install 发布门禁](docs/contracts/run-release-gate-v1.py)
- [第 1 轮审计](docs/audits/round-01-audit.md)与[处置记录](docs/audits/round-01-resolution.md)
- [第 2 轮审计](docs/audits/round-02-audit.md)与[处置记录](docs/audits/round-02-resolution.md)
- [第 3 轮审计](docs/audits/round-03-audit.md)与[处置记录](docs/audits/round-03-resolution.md)
- [第 4 轮审计](docs/audits/round-04-audit.md)与[处置记录](docs/audits/round-04-resolution.md)
- [第 5 轮审计](docs/audits/round-05-audit.md)与[处置记录](docs/audits/round-05-resolution.md)
- [第 6 轮审计](docs/audits/round-06-audit.md)与[处置记录](docs/audits/round-06-resolution.md)
- [第 7 轮审计](docs/audits/round-07-audit.md)与[处置记录](docs/audits/round-07-resolution.md)
- [第 8 轮审计](docs/audits/round-08-audit.md)与[处置记录](docs/audits/round-08-resolution.md)
- [第 9 轮审计](docs/audits/round-09-audit.md)与[处置记录](docs/audits/round-09-resolution.md)
- [第 10 轮审计](docs/audits/round-10-audit.md)与[处置记录](docs/audits/round-10-resolution.md)
- [第 11 轮审计](docs/audits/round-11-audit.md)与[处置记录](docs/audits/round-11-resolution.md)
- [第 12 轮审计](docs/audits/round-12-audit.md)与[处置记录](docs/audits/round-12-resolution.md)
- [第 13 轮审计](docs/audits/round-13-audit.md)与[处置记录](docs/audits/round-13-resolution.md)
- [第 14 轮审计](docs/audits/round-14-audit.md)与[处置记录](docs/audits/round-14-resolution.md)
- [第 15 轮审计](docs/audits/round-15-audit.md)与[处置记录](docs/audits/round-15-resolution.md)
- [第 16 轮审计](docs/audits/round-16-audit.md)与[处置记录](docs/audits/round-16-resolution.md)
- [第 17 轮审计](docs/audits/round-17-audit.md)与[处置记录](docs/audits/round-17-resolution.md)
- [第 18 轮审计](docs/audits/round-18-audit.md)与[处置记录](docs/audits/round-18-resolution.md)
- [第 19 轮审计](docs/audits/round-19-audit.md)与[处置记录](docs/audits/round-19-resolution.md)
- [第 20 轮零问题审计](docs/audits/round-20-audit.md)（终态无处置记录）
- 本地 Git 仓库，默认分支为 `main`
- 最小化的敏感信息忽略规则

## 当前边界

- 未安装任何应用依赖；仓库只为文档合同验证登记 exact-pinned AJV 依赖与 lock，本地 `node_modules/` 不入库
- 未创建 Desktop host、renderer、sidecar、服务端或 Web 前端代码；当前全部内容仍是静态设计/机器合同
- 未接入任何真实 API Key、登录凭据或飞书应用
- 未执行 Git commit，也未创建远程 GitHub 仓库

## 已确定的实施基线

1. 核心模型采用 `AccountPrincipal → QuotaSubject → QuotaCapability → CapabilitySnapshot`
2. 阶段 1A 同时实现 Tauri 2/Rust trusted host、React/TypeScript renderer、Python core sidecar、共享 application service、辅助 CLI、版本化配置和 FakeAdapter；不安装 Hermes、不开放网络监听
3. 阶段 1B 的两个 Supported 目标是 DeepSeek 与 OpenRouter：OpenRouter 先为 supported candidate，只有真实 opt-in 合同门禁通过并升为 Supported 后才计数。Codex 已确定降为 `experimental/incompatible`、默认关闭，不新增 `account/read`，不计 MVP；Kimi/MiniMax/GLM 在 schema v1 为 `planned/no-contract`
4. 所有发行单元均构建 wheel/sdist；Supported/GA Provider 只由独立 hash-pinned installer 从内嵌 genesis anchor 验证 trust chain、signed plan、wheel/sidecar 后在 staging 生成依赖 lock，sdist 只进入隔离 source-review 路径
5. 只有 Supported/GA Adapter 计入 MVP，Experimental 默认关闭且不计数
6. core 使用渠道无关 AccessContext 与 `(principal, subject, capability)` 绑定式 AccountScope，并在 Adapter 返回边界整批校验
7. Desktop GUI 是 MVP 必需表面；默认只按需刷新。未安装且健康的 SchedulerHost 时必须显示“仅按需刷新”，不得暗示实时监控；Hermes、飞书、远期 Web 和 `quota_recommend` 都不是 MVP 必需项
8. 异构额度按 capability kind/unit 分区，跨类型只比较 severity，多币种不求和
9. 所有 `/刷新` 都使用绑定 actor/scope 的持久化 at-most-once 幂等；各渠道期限只引用安全模型的唯一保存期限表
10. 命名 view 可组合已启用的 subject/capability；DeepSeek-only、OpenRouter-only 或混合配置复用同一构建产物；Codex 实验配置必须显著显示不兼容且不能正式 fetch
11. 目标许可证为 MIT，内部独立 MVP 稳定后再公开 GitHub 仓库
12. 缓存/LKG 绑定 query contract generation；endpoint、selector、unit/scale、语义或 Adapter 版本变化不得复用旧值
13. purge、HTTP URL、Codex local-stdio、对象生命周期、失败恢复、聚合告警 episode 与性能基准均使用可执行状态机/反例门禁
14. TOML 为权威配置；SQLite migration journal 使用独占 writer lease、单调 `fencing_token` 与运行时 drift 门禁，以崩溃可恢复的 roll-forward 协调文件替换和 generation 切换
15. Adapter manifest 使用判别式 profile/selector/binding schema；每个 fetch request key 恰好产生一个快照，发现缺失按 subject+capability 绑定
16. 发行 assurance、受信任 wheel attestation、Codex schema bundle、LocalKeyRing、初始化根登记和保存期限均有非循环、可复现、可撤销且可离线验证的唯一规范源
17. 官方 discovery/fetch 只接收不可变的 `IdentityAndDiscoveryContext` / `IdentityAndFetchContext`；身份 evidence、request digest、endpoint、deadline 和 reservation 由 core 一次绑定，Adapter 返回同一 evidence 与 digest 后才可接受 payload
18. 外部 TOML drift 先做类型化 diff；任何破坏性变化都必须复用 planner 的 plan digest 与一次确认 nonce，未确认时配置/运行数据库零变化且 Provider 不被调用；Desktop 的脱敏 plan 只显示在 Rust host-owned native confirmation surface，nonce/user-presence token 不返回 renderer
19. Adapter 只返回 observation/failure；core 在完整 key 校验后读取同 generation LKG并原子生成 snapshot。每个 capability 使用精确 freshness policy，本地授权失败只返回 OperationError
20. manifest 原子绑定 endpoint/auth/response/frame/deadline 与 undocumented StructureContract；Supported/GA 只通过 hash-pinned bootstrap 的 stage→verify→hashed-pip 安装
21. release/trust 与 registry/keyring 使用版本化字节级 envelope；告警和 LLM consent 使用唯一 retention 条目
22. installation binding material、active reservation rate ledger、签名 install plan/release attestation、Codex stdio/version 与全局并发使用冻结机器合同；全部持久 lease/claim 时序只引用 `lease-policy-v1`
23. Credential Source 只能返回 `CredentialResolution`；授权、访问代际和可选稳定上游主体 evidence 分离，AccessIdentity 与 CredentialLease 只由 core 构造。OpenRouter 的 access/cache identity 只来自已验证 API key binding 与 credential generation；required nullable `creator_user_id` 为 null 时没有 metadata，非 null 也不得进入 stable domain/cohort/cache identity。`expires_at` optional nullable；只有 `limit=null && limit_remaining=null` 表示 per-key unlimited，finite pair 必须满足 `0 <= remaining <= limit`，nullability mismatch fail closed。Codex 没有批准的稳定 identity source，保持实验性 fail closed
24. operation/stage/error 由唯一执行矩阵生成 design/provider 合同；表外入口返回零副作用 contract failure，内部表外转移进入固定 fatal
25. Codex app-server 专用 wire 明确省略 JSON-RPC header，并冻结 exact argv、握手、notification opt-out、请求与 error map 到 schema bundle
26. destructive dry-run/confirm/journal 只使用同一个 migration plan envelope/digest；journal 前临时文件也有 fenced claim、no-follow orphan 恢复与保留期
27. same-plan metadata、migration temp、freshness 常量与 retention lint 进入机器 data inventory；release/trust/migration 输入统一先 bound，再 parse/JCS/crypto/hash/pip
28. identity source/domain/endpoint budget group 在 manifest 中形成闭包；任何 outbound HTTP 或业务 RPC 先以 request kind 进入同一 rate ledger，身份未知时只用唯一部署级保守 cohort
29. migration action graph、temp claim、per-request refresh result、LocalKey purpose 与 keyring nonce 都有确定性、可恢复且有界的机器合同
30. `docs/contracts/*.json` 是相应主题的唯一机器权威源；正文表格仅为投影。合同摘要统一为 `SHA256("agent-quota:contract-artifact:v1\\0" || aq-jcs-nfc-v1(document))`，加载时必须与正文登记摘要相等
31. 五份权威 artifact 分别绑定 Draft 2020-12 exact JSON Schema，schema/artifact raw 与 canonical digest、bounds、严格路径解析、逐数组顺序策略和跨 artifact semantic closure 统一由 `contract-registry-v1` 登记
32. 所有 Provider I/O 只消费 reserve/commit 后构造的 final context；预计算只进入不含 receipt/credential/access identity 的 immutable `*RequestPlan`
33. 统一 `aq-array-order-v1`、全局 canonical `RepoPath`、自含 owner 的结构化 `persist:v1:<surface_id>:<operation>:<owner_id>` record、可执行 core/retention fixture 与正文投影均由完整只读 validator 和只读 projection/pin verifier 门禁；record 绝不授权同 leaf 的普通持久化 prose
34. 文档验证工具不写文件，也不是发行信任根；当前未提交 checkout 只提供审计证据，生产/0A 必须从外部固定的签名 release 或 VCS commit、tool raw SHA-256 与旧根授权建立 tool identity，工具不能自更新自己的授权 pin
35. live/fixture retention 共用判定核心；provider 成功计数由 path steps 推导；lease 表达式闭包携带 type/unit/clock domain；所有成功摘要与投影均绑定同一 immutable byte/stat snapshot
36. 发布门禁固定 Node/npm/Pandoc/Ajv 版本、可执行摘要、完整 npm package 实现树摘要、依赖实现树摘要与 manifest/lock closure；入口要求显式根目录、cwd/入口/根身份闭包和逐段 no-follow，在隔离 clean install 中双次重放 validator/projection。50 条 mutation recipe 固定 RepoPath、封闭 locator、exact before/after state、failure class、executor ID、顶层实现摘要及完整传递 helper call graph；runner 只提供执行结果，gate 保留每个隔离 case root，自己 no-follow 读取 locator、重算 source/mutated digest 与 failure class。仅修改任一共享 helper、executor 重定向、locator 漂移或结果伪造都必须拒绝；当前未跟踪 checkout 仍只产生审计证据
37. Desktop renderer 只能调用机器登记的 10 个 Tauri command；每个 request/response reference 都解析到同源、封闭、有类型、有界、脱敏的 29 个 DTO schema，nested ref 与 non-destructive config change-set 也不能成为任意字段入口。Rust host 以匿名管道/stdio 启动 hash-pinned、同签名 sidecar，并使用每 session 从 1 开始的 unsigned 64-bit 严格单调 request ID，响应原样回显，溢出即终止会话。跨进程只传 `1..9_000_000_000` 的 `remaining_budget_ns`；sidecar 收完合法 frame 后按本地 monotonic clock checked-add 重建 deadline，同时受 host 9 秒 hard cap 约束。dispatch 前过期/越界/overflow 才能声称 Provider I/O/写入为 0；dispatch 后 host 超时必须 outcome unknown、禁止自动重放并 TERM→KILL→reap 至 orphan 为 0。生产 sidecar stderr 直接连接 OS null sink，原始 stderr 不进入日志、renderer 或 IPC，结构化错误只走 IPC。秘密只能由 host-owned native secure dialog 接收或选择既有 Keychain item；dialog 只在前台 key window 打开、全安装同时最多一个且由 host 执行 cooldown。purge、disable/delete/cascade 及 destructive endpoint/auth/binding/capability/manifest diff 的 core 脱敏 plan 只在 host-owned native confirmation surface 展示，nonce/user-presence token 只在 host↔core，renderer 仅收到 cancelled/committed/status；MVP 不启动 loopback HTTP

## 文档合同验证

固定命令调用仓库内 bootstrap，但这个 bootstrap 只提供本机审计证据，永远输出 `external_launch_attestation=absent`，不能证明生产固定启动。生产或 Gate 0A 的固定启动必须由仓库外既有信任根绑定实际解释器、同一已打开 bootstrap/entry 字节、运行时身份与工具摘要后出具 attestation。仓库内 checker 仍拒绝替代 shell和四项 exact allowlist 之外的 entry，逐段拒绝 symlink，并从两个已核对 inode/stat/长度的 fd 摘要和执行同一 entry 字节。它在 Python 前固定 macOS build、关键非系统动态 image 与依赖边，并用封闭环境启动；随后 guard/validator 从实际 file-backed image 全量发现后分类，只有 exact build 下 canonical `/System` 或 `/usr/lib` 归系统，其他 Python/Pandoc/Node image 不按安装前缀过滤，必须逐项 no-follow/regular/raw-pin 匹配。离线 npm 安装只读取仓库 tarball/lock，不读取主机 cache，也不调用动态 `npx latest`：

```bash
/bin/sh docs/contracts/runtime-bootstrap-v1.sh docs/contracts/run-release-gate-v1.py --root .
/bin/sh docs/contracts/runtime-bootstrap-v1.sh docs/contracts/run-validation-mutations-v1.py --root .
npm run validate --prefix docs/contracts
```

`validate` 是必须通过的 clean-install 发布门禁：它拒绝隐式根目录或替换入口，冻结 root identity 与完整输入摘要，核验固定 Node/npm/Pandoc/Ajv、完整 npm package tree 与 dependency-tree 摘要，在隔离目录执行两次 validator、两次 projection verifier，并只接受机器合同登记的 exact mutation case 集、顺序、数量、预期 verdict 和结果摘要。历史输入由 manifest 在固定 1..20 路径宇宙中动态派生；`ISSUES_OPEN` 要求 FAIL audit 与 resolution，`ZERO_ISSUES` 只允许 `PASS_ZERO_ISSUES`、空 issue set 且无本轮 resolution。R20 零问题态是可重复验证的终态固定点；R20 仍有问题则明确 `round-budget-exhausted`，R21 一律拒绝。推进到下一轮只更新 audit/resolution、manifest、current-status marker 与摘要 pin，不修改 validator/release-gate 字节。内部 validator 严格按 registry `validation_order` 执行全部门禁，并在成功前复核所有输入的 inode/stat/长度与字节。只有整条链通过才输出最终 `status=ok`。当前未提交 checkout 的结果仍只是审计证据，不是 core/CLI/Provider 实现、运行时安全证明或生产发布授权。
