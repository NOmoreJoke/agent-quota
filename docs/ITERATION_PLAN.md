# Agent Quota 迭代开发计划

## 通用进入/退出规则

- 每次迭代只在上次全部测试和三轮质量审查通过后开始。
- 每轮证据记录：commit/worktree、命令、退出码、日志路径、产物 SHA-256、未验证项。
- R1 = contract/architecture；R2 = adversarial security/failure；R3 = runtime/regression/package。
- 任一 P0/P1、必跑测试失败、伪造生产验证、缺失产物/hash => 当前迭代 `BLOCKED`。
- 每迭代可提交到 `dev` 的条件：交付物完整 + 自动化门禁全绿 + R1/R2/R3 全通过。

## Iteration 0 — Gate 0A / 设计冻结

状态：`PASS`（2026-07-30）

交付物：

- 可复现 runtime bootstrap/profile。
- 10 command / 29 DTO schema closure。
- 修正后的 `.pen`、最终审计、状态/交互矩阵。

自动化：

- `/bin/sh docs/contracts/runtime-bootstrap-v1.sh docs/contracts/run-release-gate-v1.py --root .`
- `npm run validate --prefix docs/contracts`
- Pencil：全树 layout problems=0；Purge/re-auth/offline 状态文本断言。
- Tauri CSP 静态断言：`connect-src` 精确允许 `ipc:`/`http://ipc.localhost`，拒绝真实 localhost/127.0.0.1、外部 origin、WebSocket 与 wildcard；Iteration 2 必须补真实 invoke reachability。

三轮：

- R1：合同闭包、版本、hash、文档一致性。
- R2：renderer 注入、secret/destructive token、cohort/replay、TOCTOU/outcome_unknown。
- R3：全量 release gate、干净 worktree 重放、原型导出/hash。

## Iteration 1 — Python core + application service + FakeAdapter

状态：`PASS`（2026-07-30）

交付物：

- `agent-quota-core`、CLI/testkit、FakeAdapter。
- principal/subject/capability、freshness/health、refresh state machine。
- config journal/lease/fence、redacted export、purge planner。
- wheel/sdist。

自动化：

- Ruff/format、mypy/pyright、pytest unit/property/contract。
- SQLite crash-point/lease takeover/migration roll-forward。
- FakeAdapter normal/null/missing/wrong-type/401/403/429/5xx/timeout/oversize。
- wheel/sdist build + isolated install; secret-negative fixtures。

三轮：

- R1：domain invariants、dependency direction、schema parity。
- R2：auth scope/IDOR、concurrency/fence、retention/export/purge、parser adversarial cases。
- R3：coverage、mutation/property tests、clean install/CLI smoke。

## Iteration 2 — Tauri host + React renderer + sidecar IPC

状态：`PASS`（2026-07-31）

交付物：

- Tauri 2/Rust trusted host、React/TypeScript renderer。
- 10-command allowlist、29 DTO validators、anonymous-pipe sidecar supervisor。
- Prototype routes/states：overview/accounts/refresh/settings/status/diagnostics/offline/reauth/export/purge。
- CSP/capability/navigation policy。

自动化：

- Rust fmt/clippy/test；TypeScript lint/typecheck/unit。
- DTO unknown/additional/nested-field rejection。
- u64 request ID/deadline/TERM→KILL→reap/outcome_unknown。
- Renderer bundle static scan：无 secret input、network/file/shell/process API。
- Playwright/E2E：原型全部主流程和错误状态；keyboard/accessibility/light-dark。

三轮：

- R1：command mapping、state transitions、prototype parity。
- R2：compromised renderer、IPC framing、timeout/replay、CSP/navigation。
- R3：local app launch、E2E screenshots/AX tree、production build smoke。

## Iteration 3 — macOS trusted native surfaces

状态：`PASS`（2026-07-31；R1/R2/R3；未解决 P0/P1/P2 = 0；基线 `50b209f9a4284e2182b6f3f75fd86259e4a91b47`）

交付物：

- Keychain opaque-reference flow。
- Native credential dialog。
- Native destructive confirmation：disable/delete/cascade/config/purge。
- foreground/key-window/single-dialog/cooldown/user-presence。

自动化：

- Keychain locked/cancelled/duplicate/write-failed/import-success。
- plan/digest/generation drift、失焦、超时、重复/并发全部零副作用。
- Renderer/IPC bundle absence tests：secret value/length/buffer、plan/digest/nonce/token。
- Native UI accessibility/E2E。

三轮：

- R1：host/core ownership、native state matrix。
- R2：dialog spoof/spam/TOCTOU、buffer zeroization、renderer exfiltration。
- R3：real macOS Keychain/native UI smoke + regression suite。

## Iteration 4 — macOS package / install acceptance

交付物：

- `.app`、DMG/PKG、bundled pinned Python runtime/sidecar、SBOM/manifest。
- install/upgrade/rollback/uninstall/purge instructions。
- SHA-256、signature/notarization evidence。

自动化：

- production build、bundle manifest/hash closure。
- clean macOS user install/launch/quit/relaunch/uninstall。
- offline first launch、no user Python/PATH dependency、no listener。
- full lint/type/unit/contract/E2E/package regression。

三轮：

- R1：bundle contents/dependency/lock/SBOM。
- R2：signature/path/symlink/substitution/upgrade rollback。
- R3：本机安装运行 + 干净用户/VM acceptance。

最终 gate：

- 本地可启动并覆盖原型全部功能。
- macOS 安装包可在目标 Mac 安装运行。
- 未完成真实签名/notarization/干净 VM 时，只能标注 `local unsigned development package`。

## Iteration 5 — Provider catalog / Apple Silicon 资源门禁

状态：`PASS`（2026-08-03；全量门禁通过；本地未签名/未公证）

交付物：

- 78 项 Provider Preset 目录与 Window/Wallet 能力状态。
- 现有 8 个固定官方 adapter 映射；其余 fail closed。
- README、PRD、使用手册、Provider catalog 与性能边界。
- macOS 13.0 deployment target、app 40 MiB、DMG 20 MiB 构建门禁。

自动化：

- catalog 78 行/唯一 ID/adapter closure；搜索、筛选、禁用状态。
- fixture/contract parser；不得把 mock 计作 live。
- Python、renderer、Rust、合同、package 全门禁。

## Iteration 6 — 全栈轻量化重构、跨层契约修复与确定性工程护栏

状态：`PASS`（2026-11-24；基线 `800a539`）

交付物：

- 修复 DeepSeek Swift 裁剪器与 Python 解析器字段断路；新增 Swift `--self-test-minimize-stdin` → Python 解析器真实跨语言联调门禁。
- 完成 `volc-wallet` 官方 `GET` 签名、严格 5 字符串十进制与欠费态解析，以及原生弹窗 `CredentialSelectorGate` 双密钥/OAuth 动态切换。
- Tauri 全部 10 个命令异步非阻塞化（消除最长 150s UI 主线程冻结）、Sidecar 单读取线程 + `Condvar` 零轮询门控 + `SidecarSlot` 按需受控自愈（严守 `outcome-unknown` 不重放）。
- Swift（6 模块）、Rust（5 模块）与 React 受控 `src/hooks/` 物理拆分；升级 `eslint.config.mjs` 静态依赖与副作用门禁，修复 Node 26 Vitest 兼容，落地私有仓省额 CI 与 `FEATURE-MAP.md` / `VERIFY.md`。

自动化：

- Python `ruff` + `mypy` + `pytest`（323 passed）；Rust `fmt` + `clippy` + `cargo test`（38 passed）；Swift `-strict-concurrency=complete` 自检。
- Renderer `lint` + `typecheck` + `boundary` + `vitest`（60 passed）+ 4 组 ESLint `--stdin` 负向违规拦截反证 + Playwright E2E（10 passed）。

## Iteration 7 — Google Antigravity 零门槛接入与文档一致性收口

状态：`PASS`（2026-11-24）

交付物：

- 基于官方 `agy` CLI `statusLine` JSON 标准输入契约实现无密钥配额接入（入口剥离 `email`/`cwd`/`workspace`/`transcript_path`/`vcs`，60 秒无变化免 `fsync` 写盘去重）。
- 新增 `setup-antigravity`（自动识别开发态 CLI 与 `.app` 包内 `agent-quota-sidecar cli`、防符号链接、冲突保护、`--check`/`--uninstall`）与 `--render-statusline` 终端状态栏精炼单行渲染。
- 补齐无密钥桥接账户 Delete/Purge/Reauthenticate 边界与悬浮窗双视图 E2E 验收；同步刷新 `KNOWN_ISSUES.md`、`ACCEPTANCE_MATRIX.md`、`RELEASE_HANDOFF.md`、`PROVIDER_CATALOG.md`、`USER_GUIDE.md`。

## Iteration 8 — Apple Silicon 生产级 `.app` / `.dmg` 构建与干净安装全链路验收

状态：`PASS`（2026-11-24；`adhoc-test-only` 本地开发包门禁闭环，待外部 Apple Developer ID 签名公证）

交付物：

- 基于独立锁死 Rust `1.97.1` 工具链、PyInstaller 独立 Sidecar、多模块 Swift `AgentQuotaNative.app` 与 Tauri `production` 特性构建完整 `Agent Quota.app` 与 `Agent-Quota-0.1.0-arm64-local-development.dmg`。
- 通过 `audit_macos_bundle.py`、`verify_clean_install_sidecar.py`、`audit_package_size.py`（`.app <= 40 MiB`、`.dmg <= 20 MiB`）、CycloneDX `sbom.cdx.json`、第三方许可证闭包与包内 `agent-quota-sidecar cli` 实机管道冒烟验收。
- 完成主窗口与悬浮窗视觉降噪：移除「概览 / 刷新队列」顶部黄色静态横条，在「账户与 Provider」保留中性灰底隐私说明并支持点击跳转「设置 → 安全」，统一正常额度行清爽中性底色，并同步更新 `docs/design/agent-quota-desktop.pen` 复用组件与主题变量。

## Iteration 9 — 悬浮窗标题栏点击折叠、凭据过期自动提示与测试覆盖率闭环

状态：`PASS`（2026-11-24；基线 commit `0279eba`）

交付物：

- 悬浮窗顶部标题栏（`Agent Quota`）支持点击即时切换展开/折叠（包含固定状态下取消固定并收起），外观偏好与动效偏好跨主窗口/悬浮窗持久化同步。
- 主窗口与悬浮窗落地 `needs-reauth`（含 OAuth `invalid_grant`）自动弹出重新授权提示及顶部快捷横幅。
- 动态同步 `App.tsx` 目录摘要统计，补充 `test_cli.py` 与 `test_providers.py` 边界单测恢复 Python 分支覆盖率 `>= 90%`，并在独立 worktree 开启 Iter 10–13。

## Iteration 10 — 协议勘察与隔离契约/护栏升级

状态：`PASS`（2026-11-24；commit `6345b11`）

交付物：

- 完成 Antigravity CloudCode、智谱 GLM / MiniMax 加油包与 API Wallet、WorkBuddy CN 个人版、Qoder CN 个人版协议勘察，沉淀 `docs/audits/provider-protocol-spike-2026-11-24.md` 与 `tests/fixtures/protocol_spike/*.json`。
- 将 `tests/test_architecture.py` 从粗粒度主机字符串计数升级为精确 `(provider_id, host, path)` allowlist 对齐校验。

## Iteration 11 — Google Antigravity 官方 OAuth + CloudCode 远端查询与 CLI Bridge 双模兼容

状态：`PASS`（2026-11-24；commit `c60d910`）

交付物：

- 新增 `antigravity` 原生 Google OAuth 2.0 + PKCE `S256` + `state` + `NWListener` 临时回环（`127.0.0.1:0/oauth-callback` + 手动回调兜底）与自动刷新，构建时从环境变量注入 `GeneratedOAuthConfig.swift`（仓内零字面量密钥）并支持弹窗手动覆盖 Client ID/Secret。
- 实现固定域名 `daily-cloudcode-pa.googleapis.com`（降级 `cloudcode-pa.googleapis.com`）3 步只读配额查询（`loadCodeAssist` AI Credits 余额 + `fetchAvailableModels` + `retrieveUserQuotaSummary` 组桶），Swift 层剥离全部邮件/项目/账户 PII。
- 保留 `agy statusLine`（`credential_type="agy-statusline-stdin"`、`Google Antigravity (CLI Bridge ...)`）共存，宿主机 `credential_context` 区分内部 `credential_type`，解锁 Antigravity OAuth 刷新、Keychain 删除清理与目录 `creatable=true`。

## Iteration 12 — 智谱 GLM / MiniMax 加油包 Wallet 投影与 API 口径余额目录卡

状态：`PASS`（2026-11-24；commit `3e7d619`）

交付物：

- 扩展 Swift `ResponseMinimizer.swift` 与 Python `providers.py`，支持 GLM 5h（`unit=3`）、周窗口（`unit=6`）、MCP 月度及 `extraPackage`/`CREDIT_LIMIT` 加油包 Wallet View 投影，以及 MiniMax `extra_remains`/`boost_remains` 加油包 Wallet View 投影，同时保持旧版双字段响应 100% 兼容。
- 坚守无 Cookie / 无私有控制台抓取红线，新增 `glm-api-balance-cn` 与 `minimax-api-balance-cn` 独立 `information-only` Wallet View 卡片（`BLOCKED_OFFICIAL_API_ABSENT`）。

## Iteration 13 — WorkBuddy 个人版（中国区）接入与 Qoder 个人版（中国区）目录卡

状态：`PASS`（2026-11-24；commit `15fdc54`）

交付物：

- 新增 `workbuddy-cn`（首批仅个人版/中国区）无端口 OAuth（`/v2/plugin/auth/state` → 浏览器 → 轮询 `/v2/plugin/auth/token`、`code=11217` 继续）与 `/v2/plugin/auth/token/refresh` 自动刷新，对接 `POST https://www.workbuddy.cn/billing/meter/get-user-resource-summary` 并投影周期积分窗口与 `extra` 加油包 Wallet View。
- 新增 `qoder-personal-cn`（首批仅个人版/中国区）独立目录卡，因个人版网页额度接口需浏览器 Cookie / WAF 且官方仅开放组织级 OpenAPI，诚实标为 `information-only`（`BLOCKED_OFFICIAL_API_ABSENT`）。
- 矩阵收口至 **15 张产品卡 / 10 个品牌 / 9 个候选 / 7 个当前可添加 / 6 个仅信息展示**。

## 后续排期（Next Phase：Iterations 14–16）

- **Iteration 14**：通用 Webhook / OpenTelemetry 只读上报与多工作区配额分组视图；开放火山方舟 Agent Plan / 火山钱包实机验收解锁（待持有人验收）。
- **Iteration 15**：WorkBuddy / Qoder 国际区或企业版只读适配（仅在官方非 Cookie API 发布后解锁）；多账户批量刷新并发调度优化。
- **Iteration 16**：Apple Developer ID 签名/公证/Stapling 闭环与全量持有人实机 L4 验收后发布正式公开 DMG/Release。
