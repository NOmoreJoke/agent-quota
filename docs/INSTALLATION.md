# Agent Quota macOS 本机安装

## 产物等级

`Agent-Quota-0.1.0-arm64-local-unsigned.dmg` 是
`local unsigned development package`：

- Apple Silicon `arm64`。
- 内含固定 CPython 3.11.15 sidecar 与 macOS native helper。
- ad-hoc 签名；未使用 Developer ID，未公证。
- 不代表 Intel/universal、干净 VM、真实 Provider 或生产环境验证。

## 构建

前置：Apple Silicon macOS、Xcode Command Line Tools、Python 3.11、uv、
Node/pnpm、Rust/cargo。

```bash
uv sync --all-groups --locked
pnpm install --frozen-lockfile
./tools/build_macos_package.sh
```

若 `cargo` 不在 `PATH`：

```bash
AQ_RUST_BIN=/absolute/path/to/rust/bin ./tools/build_macos_package.sh
```

输出：

- `artifacts/iteration-4/Agent Quota.app`
- `artifacts/iteration-4/Agent-Quota-0.1.0-arm64-local-unsigned.dmg`
- `bundle-manifest.txt`
- `bundle-audit.json`
- `sbom.cdx.json`
- `artifact-sha256.txt`

## 安装

1. 退出正在运行的 Agent Quota。
2. 打开 DMG。
3. 将 `Agent Quota.app` 拖入 `/Applications`。
4. 启动应用。

若 macOS 提示来源未识别，不得关闭 Gatekeeper 或清除全局安全属性；仅在确认
本机生成产物的 SHA-256 后，通过 macOS 提供的单应用人工确认流程处理。

## 升级

1. 退出应用。
2. 保留当前 `.app` 作为可回滚副本。
3. 用新 `.app` 替换 `/Applications/Agent Quota.app`。
4. 启动并核对账户、设置和刷新状态。

应用数据位于用户 Application Support；替换 `.app` 不删除数据或 Keychain 项。

## 回滚

1. 退出应用。
2. 恢复上一版本 `.app`。
3. 启动并核对数据 schema 兼容性。

若新版报告不可逆 schema 迁移，禁止直接回滚；本迭代未执行数据库迁移。

## 卸载

1. 退出应用。
2. 将 `/Applications/Agent Quota.app` 移到废纸篓。

普通卸载保留 Application Support 数据与 Keychain 引用，便于重装恢复。

## Purge

必须在应用内发起 purge，并完成原生破坏性确认；成功后再卸载 `.app`。此流程由
host/core 删除本机状态并清理 Keychain 引用。若 `.app` 已被移除，先重装同版本，
再执行 purge；不要手工猜测或批量删除 Keychain 项。
