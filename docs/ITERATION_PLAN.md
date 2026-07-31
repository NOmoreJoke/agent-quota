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
