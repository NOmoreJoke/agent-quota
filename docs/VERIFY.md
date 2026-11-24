# Agent Quota 分级验证手册 (VERIFY)

按执行成本由低到高划分为 **L1 → L2 → L3** 三级确定性门禁。日常迭代先跑 L1，涉及跨进程/UI 交互跑 L2，涉及打包/发布前跑 L3。

## L1：静态边界 + 单元与契约测试（秒级，每次改动必跑）

```bash
# 1. 产品范围投影一致性校验
uv run python tools/generate_launch_products.py --check

# 2. Python 静态检查、类型与全量单测（含架构不变量与黄金向量）
uv run ruff check src tests tools
uv run ruff format --check src tests tools
uv run mypy src
uv run pytest -q

# 3. Renderer 分层 Lint、类型、边界守卫、单测与生产包无 Fixture 校验
pnpm lint
pnpm typecheck
pnpm boundary
pnpm test
pnpm build
```

### ESLint 负向反证（修改 `eslint.config.mjs` 时必跑，防假绿）

```bash
# 验证 UI 组件裸写 useEffect 被精准阻断
printf 'import { useEffect } from "react";\nexport const X = () => { useEffect(() => {}, []); return null; };\n' \
  | pnpm exec eslint --stdin --stdin-filename src/ui/ForbiddenEffect.tsx

# 验证 UI 组件使用命令式定时器被精准阻断
printf 'export const X = () => { setTimeout(() => {}, 10); return null; };\n' \
  | pnpm exec eslint --stdin --stdin-filename src/ui/ForbiddenTimer.tsx

# 验证跨层反向依赖被精准阻断
printf 'import { App } from "../ui/App";\nexport const x = App;\n' \
  | pnpm exec eslint --stdin --stdin-filename src/host/ForbiddenImport.ts
```
以上三条命令均**必须以非 0 退出码失败**并打印根因修复提示。

## L2：原生编译 + 跨进程集成 + 浏览器 E2E（分钟级）

```bash
# 1. Swift/C Native Helper 编译（strict-concurrency + Werror）及最小化/标签自测
AQ_ALLOW_ADHOC_SIGNING=1 ./tools/build_native_helper.sh

# 2. Rust Host 格式、开发/生产双模式 Clippy 与真实 Python Sidecar 集成测试
cargo +1.97.1 fmt --manifest-path src-tauri/Cargo.toml --check
cargo +1.97.1 clippy --locked --manifest-path src-tauri/Cargo.toml --all-targets --features development-overrides -- -D warnings
AQ_RESOURCE_MANIFEST_SHA256="0000000000000000000000000000000000000000000000000000000000000000" \
  cargo +1.97.1 clippy --locked --manifest-path src-tauri/Cargo.toml --release --target aarch64-apple-darwin --features production -- -D warnings
AQ_SIDECAR_TEST_EXECUTABLE="$PWD/.venv/bin/agent-quota-sidecar" \
AQ_PYTHON_TEST_EXECUTABLE="$(uv run python -c 'import sys; from pathlib import Path; print(Path(sys.executable).resolve())')" \
  cargo +1.97.1 test --locked --manifest-path src-tauri/Cargo.toml --features development-overrides

# 3. Playwright 端到端测试（总览、悬浮窗、明暗外观、响应式与异常态）
pnpm e2e
```

## L3：macOS 打包审计与冻结机器合同门禁（发布候选必跑）

```bash
# 1. 验收矩阵 Schema 与不变量门禁
./tools/validate_acceptance_matrix.sh

# 2. 固定运行时机器合同门禁（需匹配 docs/contracts/package.json 固定运行时身份）
npm run validate --prefix docs/contracts

# 3. 本机 macOS 包体、资源闭包、干净安装 Sidecar、SBOM 与许可证审计（要求 clean git worktree）
#    已安装 Apple Development / Developer ID 证书时优先使用 AQ_CODESIGN_AUTO=1 产出稳定 Team 签名包；
#    仅在无证书测试环境显式回退 AQ_ALLOW_ADHOC_SIGNING=1。
AQ_RUST_BIN="$HOME/.cache/agent-quota/rust-1.97.1/bin" \
  AQ_CODESIGN_AUTO=1 ./tools/build_macos_package.sh

# 4. Xcode + 隔离钥匙串跨构建免弹窗正反证（验证不同 CDHash 同 Team ID 静默读取 + ad-hoc 伪造包拦截）
uv run python tools/verify_xcode_apple_signing.py

# 5. Xcode CLI 二进制 minos / Assets.car 动态图标 / 禁网沙箱与常驻内存门禁
./tools/verify_macos_runtime_xcode.sh "/Applications/Agent Quota.app"
```

完整 macOS + Xcode + Apple 证书标准开发与跨项目复用规范见 [MACOS_XCODE_TESTING_SOP.md](./MACOS_XCODE_TESTING_SOP.md)。
