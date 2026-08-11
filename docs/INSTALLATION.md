# Agent Quota macOS 本机安装

## 产物等级

`Agent-Quota-0.1.0-arm64-local-unsigned.dmg` 是
`local unsigned development package`：

- Apple Silicon `arm64`，最低 macOS 13.0；不按芯片代际或 Pro/Max/Ultra 型号特判。
- 内含固定 CPython 3.11.15 sidecar 与 macOS native helper。
- ad-hoc 签名；未使用 Developer ID，未公证。
- 不代表 Intel/universal、干净 VM、真实 Provider 或生产环境验证。
- 全芯片目标兼容不等于全部机型实机验证。

## 构建

前置：Apple Silicon macOS、Xcode Command Line Tools、Python 3.11、uv、
Node/pnpm、`rust-toolchain.toml` 固定的 Rust 1.97.1 + clippy/rustfmt。

```bash
uv sync --all-groups --locked
pnpm install --frozen-lockfile
AQ_RUST_BIN=/absolute/persistent/path/rust-1.97.1/bin ./tools/verify_rust_toolchain.sh
AQ_RUST_BIN=/absolute/persistent/path/rust-1.97.1/bin ./tools/build_macos_package.sh
```

固定工具链必须安装到非临时、当前用户不可被其他用户写入的持久目录并显式传入；
构建不读取 `PATH` 中的 Rust，`/private/var/tmp` 会被门禁拒绝：

```bash
AQ_RUST_BIN=/absolute/persistent/path/rust-1.97.1/bin ./tools/build_macos_package.sh
```

门禁逐项核对 Rust 官方 standalone archive SHA-256、完整安装树 SHA-256、rustc
release/commit/host、cargo release、clippy/rustfmt；工具及其
目录链必须由 root/当前 euid 持有且不可 group/world 写，拒绝 symlink、非普通/非可
执行文件、硬链接、临时工具链和验证后 inode 漂移。构建使用已验证的绝对
`RUSTC`/`CARGO` 路径；Tauri 显式使用该 Cargo runner、固定 target 与 `production`
feature，并在 build 前重新验证。包构建拒绝 Rust/Cargo wrapper、profile、flags、
target 与用户/repository Cargo config 覆写；`production` 与
`development-overrides` feature 互斥，production + debug assertions 编译失败。
解析器固定为 root 持有、不可 group/world 写的 `/usr/bin/python3`、`awk`、`grep`、
`dirname`；Python 使用 isolated/no-site 模式，拒绝 `AQ_RUST_BIN`、`PATH`、
`PYTHONPATH` 或用户 site 中的替身。

输出：

- `artifacts/iteration-4/Agent Quota.app`
- `artifacts/iteration-4/Agent-Quota-0.1.0-arm64-local-unsigned.dmg`
- `bundle-manifest.txt`
- `bundle-audit.json`
- `clean-install-audit.json`
- `sbom.cdx.json`
- `third-party-license-corpus.json`
- `upstream-license-sources.json`
- `artifact-sha256.txt`

`bundle-audit.json` 拒绝打包账户状态、SQLite、浏览器存储与 Keychain 目录；
`clean-install-audit.json` 使用包内 sidecar 和全新 `0700` 数据目录启动，要求账户数为 0。
静态 Provider Preset 目录是产品能力清单，不是已保存账户。

## 安装

1. 退出正在运行的 Agent Quota。
2. 打开 DMG。
3. 将 `Agent Quota.app` 拖入 `/Applications`。
4. 启动应用。

生产数据目录由 `getpwuid_r(geteuid())` 得到的 macOS 账户 home 固定派生，不信任
`HOME`；同一 macOS 用户只允许一个 host 实例。第二实例会在 sidecar、Keychain
显式 pending cleanup 和 Provider helper 启动前因独占 lease 失败而退出；不要并行直接执行
第二份 app binary。

启动流程绝不按 Keychain service 补集清理凭据。状态文件缺失、部分恢复或普通重装
均不得触发批量 Keychain 删除；仅显式 destructive journal 中记录的引用可被删除。

若 macOS 提示来源未识别，不得关闭 Gatekeeper 或清除全局安全属性；仅在确认
本机生成产物的 SHA-256 后，通过 macOS 提供的单应用人工确认流程处理。

## 升级

1. 退出应用。
2. 保留当前 `.app` 作为可回滚副本。
3. 用新 `.app` 替换 `/Applications/Agent Quota.app`。
4. 启动并核对账户、设置和刷新状态。

应用数据位于用户 Application Support；替换 `.app` 不删除数据或 Keychain 项。

因此，同一 macOS 用户重装后看到其原有账户属于本机数据保留，不代表 DMG 携带账户。
需要空白状态时，先在应用内完成 purge；安装或升级流程不得静默删除用户数据。

## 公开发布门禁

第三方直接下载版本必须同时具备 Developer ID 签名、Apple notarization/stapling、
GitHub Release 校验和、SBOM、源码标签和可复现门禁证据。当前
`local unsigned development package` 未满足签名/公证要求，不得标记为公开正式版。

## 回滚

1. 退出应用。
2. 恢复上一版本 `.app`。
3. 启动并核对数据 schema 兼容性。

若新版报告不可逆 schema 迁移，禁止直接回滚；本迭代未执行数据库迁移。

## 卸载

1. 退出应用。
2. 将 `/Applications/Agent Quota.app` 移到废纸篓。

普通卸载保留 Application Support 数据与 Keychain 引用，便于重装恢复。

| 本机数据面 | 普通卸载 | 重装 | 应用内确认 Purge |
|---|---|---|---|
| `/Applications/Agent Quota.app` | 移除 | 重新复制 | 不处理 App 本体 |
| Application Support 配置、账户绑定、LKG | 保留 | 恢复读取 | 删除已登记的本应用状态 |
| `com.agentquota.desktop.credentials.v1` 精确 Keychain 引用 | 保留 | 继续使用 | 仅删除 destructive journal 登记的引用 |
| 系统备份中的历史副本 | 不处理 | 不处理 | 无法保证删除，需由用户管理备份策略 |

## Purge

必须在应用内发起 purge，并完成原生破坏性确认；成功后再卸载 `.app`。此流程由
host/core 删除本机状态并清理 Keychain 引用。若 `.app` 已被移除，先重装同版本，
再执行 purge；不要手工猜测或批量删除 Keychain 项。

## 故障排查

| 现象 | 判定/处理 |
|---|---|
| macOS 提示来源未识别 | 先核对发布方给出的 SHA-256；仅使用 Finder/系统设置提供的单应用人工确认，不关闭 Gatekeeper、不执行全局放行 |
| 启动后账户数为 0 | 干净安装的预期状态；通过原生安全窗口添加账户，不把凭据写入配置或终端 |
| 显示 `needs-reauth` | 重新认证；旧 LKG 只能显示 `stale`，认证成功刷新前不得视为最新数据 |
| 显示 `provider-unavailable` | 保留 stale LKG；检查网络及官方服务状态，避免重复提交或切换到非官方接口 |
| 显示 `contract-error` | 上游 schema 与固定合同不符；停止信任该次响应并升级应用/提交脱敏诊断 |
| 重装后账户仍存在 | 普通卸载按设计保留本机状态；需要空白状态时先执行应用内原生确认 Purge |
| Purge 被拒绝或中断 | 不手工删除部分文件/Keychain 项；重启同版本应用并重试，使 journal 完成精确清理 |

校验 DMG：

```bash
/usr/bin/shasum -a 256 Agent-Quota-0.1.0-arm64-local-unsigned.dmg
```
