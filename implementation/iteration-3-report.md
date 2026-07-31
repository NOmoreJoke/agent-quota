# Iteration 3 — macOS trusted native surfaces

状态：`PASS`（R1/R2/R3；未解决 P0/P1/P2 = 0）
基线：`50b209f9a4284e2182b6f3f75fd86259e4a91b47` (`dev`)
外部审查对话：<https://chatgpt.com/c/6a6c103b-c278-83ea-8154-06948ddd7429>

## 外部代理交付审计

- ChatGPT Pro 被要求提供实际实现、unified patch、报告、manifest 与测试证据。
- Pro 明确报告尚未完成代码修改和 patch；该回复未被视为交付，也未直接落地。
- Codex 基于冻结 contracts 独立实现、审查、运行门禁并生成本仓库 artifact。

## 实现边界

- Renderer 仍为冻结的 10 commands / 29 DTO；未新增 secret、credential reference、plan、digest、nonce 或 user-presence 字段。
- 凭据正文只存在于独立 AppKit `NSSecureTextField`、短生命周期原生缓冲和 Security.framework。
- Keychain service 固定为 `com.agentquota.desktop.credentials.v1`；account 使用 `credential-<uuid>` exact lookup。
- Rust host 校验 foreground/visible/key-window，执行单 active dialog、750 ms cooldown、bounded stdin/stdout、timeout 与 kill/reap。
- host-core 私有命令使用既有匿名管道、session HMAC 和严格单调 request ID；`host_internal.*` 不可由 Renderer 调用。
- Python core 持久化的只有脱敏账户元数据、opaque Keychain reference、generation 与待清理 reference；文件为 0700 root 下 0600 atomic JSON。
- destructive 流程：core prepare plan/digest/generation/nonce -> AppKit 展示并捕获 user presence -> core 重验并 commit -> Keychain cleanup/ack；取消、失焦、超时、漂移、重复均不提交。
- replace/purge/delete 的旧 Keychain reference 进入持久化 cleanup queue；删除成功后 ack，启动时自动重试。
- 不执行 Provider I/O，不使用真实凭据，不迁移既有 SQLite schema。

## 状态机

### Credential

`idle -> foreground gate -> native secure dialog -> cancelled | Keychain add -> core commit -> visible account`

- core commit 失败：立即删除新 Keychain item。
- replace：expected account generation 必须一致；commit 后旧 reference 进入 cleanup queue。
- restart：`accounts_read` 从私有元数据恢复脱敏账户，不读取 secret。

### Destructive

`idle -> core prepare -> native confirm -> cancelled | presence token -> core revalidate -> committed -> Keychain cleanup/ack`

- plan 60 秒过期；同时最多 8 个 core plan；host 同时最多 1 个原生 dialog。
- digest/generation/nonce/plan ID/token 任一不一致：拒绝。
- commit 后 plan 消费；重复提交与 token replay：拒绝。
- sidecar crash/timeout：host 丢弃 session并返回安全错误，不自动重放。

## 对抗性审查

### R1 — ownership / contract

- PASS：Renderer command/DTO 数量未变；权威 contracts 未修改。
- PASS：native helper、Rust host、Python core 的职责及失败回滚闭合。
- PASS：重启持久化由真实跨进程 Rust/Python 测试覆盖。

### R2 — spoof / spam / TOCTOU / exfiltration

- 修复：Python `json.dumps` 默认 ASCII escape 与 Rust UTF-8 JSON 导致中文账户名 response HMAC 不一致；proof 改为 canonical UTF-8。
- 修复：replace/purge 后旧 Keychain item 可能孤儿化；新增持久化 cleanup/ack/retry。
- 修复：credential reference / presence token 正则允许错误连字符位置；改为精确 UUID 分组。
- 修复：native state 的 `Path` 检查后读取存在替换窗口；改为目录 FD、逐级 `O_NOFOLLOW`、owner/mode/nlink 校验。
- 修复：损坏 native state 的 `ValueError` 未被 sidecar 顶层收敛；统一无 traceback、退出码 64。
- 修复：native helper stdin/stdout 异常路径可能遗留 child；统一 TERM -> 200 ms grace -> KILL -> wait。
- 修复：credential commit `outcome-unknown` 时误删新 Keychain item，可能形成已提交 metadata -> 缺失 secret；结果未知不再删除，启动时由 core active-reference 集合驱动同 helper/signing identity 下的 orphan prune。
- PASS：foreground/key-window、single-active/cooldown、bounded protocol、unknown fields、generation drift、plan expiry、cancel、duplicate、replay。
- PASS：Renderer bundle/boundary 门禁；敏感字段只作为冻结 denylist 名称存在，不存在相应数据通路或输入控件。

### R3 — macOS runtime / regression

- PASS：Swift warnings-as-errors、ad-hoc app/helper codesign、真实临时 Keychain add/read/update/delete/cleanup。
- PASS：真实 Tauri `.app` 启动、Python sidecar 连接、AppKit credential dialog 调起。
- 修复：`NSWindow.didResignKey` 在正常关闭 `NSAlert` 时也触发，导致保存/确认必然被误判为取消；改为应用级 `didResignActive`。
- PASS：使用非真实测试串完成新增；页面显示 1 个账户；状态文件 0600；exact Keychain item 存在。
- PASS：退出并重启 `.app` 后账户仍恢复；Renderer 未收到凭据正文或 opaque reference。
- PASS：原生 purge 显示准确范围、generation、digest；未勾选不能提交；确认后状态、cleanup queue、Keychain 全部归零；再次重启仍为空。
- PASS：两轮隔离 runtime 均移入废纸篓；固定 Keychain service 无残留。
- PASS：同一已签名 helper 独立创建未提交 Keychain item；下一次 `.app` 启动按空 active-reference 集合自动 prune，exact lookup 返回 not-found。

## 已执行门禁

| 命令/证据 | 结果 |
|---|---|
| Ruff format/check | PASS |
| mypy strict | PASS |
| pytest + branch coverage | PASS — 103 tests；90.61% |
| Swift `-warnings-as-errors` | PASS |
| Keychain self-test add/read/update/delete/retained-orphan prune | PASS |
| helper `.app` + raw helper ad-hoc codesign verify | PASS |
| cargo fmt/clippy `-D warnings` | PASS |
| Rust tests（显式启用真实 Python sidecar restart） | PASS — 17 |
| pnpm lint/typecheck/boundary/test/build | PASS — Vitest 5 |
| Playwright | PASS — 2 |
| debug `.app` bundle build + ad-hoc deep sign verify | PASS |
| 固定 release/50-case gate | PASS — 50；deterministic；source unchanged；results `6b267aef7791f75b5f35681ce0b68ce83037c09758a3ffc0283b3b65ba262964` |
| 安全扫描 | SKIPPED — 用户明确要求 |
| 原生成功/重启/purge UI E2E | PASS — 真实 AppKit/Keychain；仅非真实测试串 |

## 当前限制

- 当前 helper 与 sidecar 通过 debug-only absolute environment override 接线；正式 bundle pin/signature/resource closure 属 Iteration 4。
- 未连接真实 Provider；账户仅验证 Keychain reference 与脱敏元数据生命周期。
- debug `.app` 仅 ad-hoc 签名；未完成 notarization、Developer ID 签名、DMG/PKG 或干净用户安装验收。
- ad-hoc helper 重编译会改变签名主体；跨构建 Keychain ACL 连续性不计入本轮通过项，必须由 Iteration 4 的稳定 Developer ID 签名与升级验收闭合。
- release gate 的 `release_authority` 明确为 `audit-evidence-only-not-a-release-authority`；不构成生产发布、签名或安装证明。
