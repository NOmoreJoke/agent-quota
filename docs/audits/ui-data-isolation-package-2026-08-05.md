# UI 与安装包数据隔离验收 — 2026-08-05

## 结论

- UI 筛选器重叠：FIXED。
- 发布包携带账户/Provider 运行状态：FIXED + VERIFIED NOT PRESENT。
- 全新私有数据目录首次启动：VERIFIED，`accounts_count=0`。
- 正常升级：继续保留当前 macOS 用户自己的 Application Support/Keychain 数据；安装流程不静默删除用户数据。
- 产物等级：`local unsigned development package`；未达到第三方公开正式发布所需的 Developer ID 签名和 Apple notarization。

## 基线

- worktree：`/private/var/tmp/agent-quota-provider-expansion`
- branch：`codex/provider-expansion`
- base commit：`de388f8f4c2de3a820b3b60ebe99fbde00aa14ad`
- 交付状态：未提交、未推送、未部署、未迁移数据库、未操作真实用户数据。

## 修复

1. `src/ui/styles.css`
   - Provider 能力筛选器使用 3 个等宽列；按钮禁止折行。
2. `tests/e2e/prototype.spec.ts`
   - 断言 3 个按钮同一行，且底边不超出筛选容器。
   - 修复前复现：`Expected 1 / Received 2`；修复后通过。
3. `tools/audit_macos_bundle.py`
   - 拒绝包内 `native-accounts-v1.json`、Agent Quota SQLite、浏览器存储、Keychain/Application Support 运行状态路径。
4. `tools/verify_clean_install_sidecar.py`
   - 使用包内 sidecar、真实 FD 3 会话协议和全新 canonical `0700` 数据目录。
   - `bootstrap_state=ok`、`accounts_read=[]`、未创建账户状态文件。
5. `tools/build_macos_package.sh`
   - DMG 创建前强制执行包内干净安装检查，并将报告加入 SHA-256 清单。
6. 开源准备
   - 新增 MIT `LICENSE`、`SECURITY.md`、`CONTRIBUTING.md`。
   - 补齐 npm/Python/Rust 仓库与许可证元数据、安装数据隔离说明、公开发布门禁。

## 验证

| Gate | Result |
|---|---|
| Ruff check/format | PASS |
| mypy | PASS，19 source files |
| pytest | PASS，183/183，branch coverage 90.59% |
| pnpm lint/typecheck | PASS |
| Vitest | PASS，5/5 |
| renderer boundary | PASS，9 files |
| production build/fixture exclusion | PASS |
| Playwright E2E | PASS，4/4 |
| Rust fmt/clippy | PASS |
| Rust test/doctest | PASS，28/28 |
| Frozen contract gate | PASS，50 mutations，clean install，deterministic replay，27 external negatives，7 bootstrap negatives，`status=ok` |
| High-confidence secret scan | PASS，206 source files |
| Bundle audit | PASS，`runtime_state_files=[]`，codesign strict exit 0 |
| Packaged sidecar clean install | PASS，`accounts_count=0`，`state_file_present=false` |
| Read-only mounted DMG audit | PASS，same bundle/resource digests，zero runtime state |
| `hdiutil verify` | PASS |

合同证据：

- `release_input_sha256=821bcdb82ad9cf75db475e47d6fd84a2a13cd36b96c497eaeb25788b7984a519`
- `mutation_results_sha256=3c612cd46efad7997cb2647c5507ce8143d1ce057c129d2d668159ce6421e9ed`

## 产物

- DMG：`Agent-Quota-0.1.0-arm64-local-unsigned.dmg`
- bytes：`13,265,480`
- SHA-256：`3077ca0d290af48587c9da644b92457cc246eea304b12f5e77c81ddd22230556`
- source ZIP：`agent-quota-source-de388f8-ui-data-isolation.zip`
- source ZIP bytes：`5,227,168`
- source ZIP SHA-256：`f4c22bdf2aac207ac8ac49491f2c62292b225306acecdc9ffa0c7658e25eb316`
- UI screenshot SHA-256：`55eee56debb78f0dab49739f8ea15528f9e010fc67cc8c215969af8331088973`
- persistent delivery directory：`/Users/kyle/Code/Project/agent-quota-deliverables/2026-08-05/package-ui-data-isolation-uncommitted`

## 外部复核与剩余风险

- ChatGPT Pro 对话：`https://chatgpt.com/c/6a71a677-4b74-83ea-b645-4c8d3969c6c6`。
- 本轮 source ZIP 上传被内置浏览器文件选择事件阻塞；原生 GUI 回退被 Codex 安全策略禁止。因此本轮未获得 ChatGPT Pro 独立复核，不把历史 v4/v5 回复作为当前修复验收。
- 未验证：Developer ID 签名、Apple notarization/stapling、Intel/universal、干净 macOS VM、真实 Provider、真实账户、生产部署。
- 没有以已安装生产 app 的完整 GUI 读取临时数据根；production host 固定使用真实 OS 用户目录。数据隔离由挂载包扫描 + 包内真实 sidecar 临时根证明，renderer 由 fixture E2E 证明；二者未冒充同一项端到端生产验证。
