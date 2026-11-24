# macOS + Xcode + Apple 证书标准开发与测试流程 (SOP)

> **适用范围**：本规范提炼自 `Agent Quota`（Tauri + Rust + Swift/C + Python）的工程实践，同样适用于 `Classic Mines (minesweeper)` 等原生 Swift/AppKit、Tauri 2 及 Electron macOS 桌面应用仓库，可直接纳入新项目冷启动与流水线加固标准（`agentic-repo-bootstrap`）。

---

## 一、核心原则：把“手动经验”下沉为 Xcode / Security 确定性门禁

在引入 `Apple Development`（本机开发与实机回归）或 `Developer ID Application`（公开发布）证书后，macOS 桌面工程必须淘汰 `codesign --deep -s -`（ad-hoc）手工打包习惯，将以下 **5 个高发踩坑点** 固化为自动化脚本门禁：

1. **陷阱 1：证书 `CN` 括号内的 ID 不等于 `Team ID`（`subject.OU`）**
   - 个人/免费或单人开发者账号的证书通用名形如 `Apple Development: xxx@gmail.com (392AK27NA8)`，其中括号内为 **Member ID**，而 macOS Keychain `PartitionID`（`teamid:<OU>`）与 `codesign -R` 实际校验的是 X.509 证书中的 **`subject.OU`**（如 `34Y68VQZ4R`）。
   - **标准做法**：禁止肉眼抄写括号字符串，统一通过 `openssl x509 -noout -subject -nameopt RFC2253` 自动解析 `OU=([A-Z0-9]{10})`（见 `tools/macos_signing.py discover` / `AQ_CODESIGN_AUTO=1`）。
2. **陷阱 2：`codesign --deep` 破坏内嵌资源清单与分层权限**
   - 包含内嵌 Helper `.app`、PyInstaller Sidecar 或动态库的应用包，**严禁使用 `codesign --deep` 签名**。
   - **标准做法**：遵循 **由内向外（Inside-Out）** 顺序：① 先逐个签名内嵌 Mach-O `.so`/`.dylib` 与子 `.app`/Sidecar → ② 计算并锁定资源 SHA-256 清单 → ③ 编译主宿主并注入 `Assets.car` → ④ 最后仅对外层 `.app` 执行非 `--deep` 签名，再用 `codesign --verify --deep --strict` 做只读核验。
3. **陷阱 3：跨版本升级重复弹出钥匙串密码框（未做跨 `CDHash` 正反证）**
   - 静态检查 `codesign -dv` 通过，不代表升级版本后不会重弹钥匙串授权。
   - **标准做法**：在隔离临时钥匙串（`SecKeychainCreate` + 测试后销毁，绝不触碰用户 `login.keychain-db`）中自动编译两个**字节与 `CDHash` 不同、但同属一个 Apple `Team ID`** 的探针包（`Build A` 写入、`Build B` 在 `SecKeychainSetUserInteractionAllowed(false)` 下静默读取成功），同时用同 Bundle ID 的 `ad-hoc` 包 `Build C` 做**负向拦截反证**（必须拒绝读取），见 `tools/verify_xcode_apple_signing.py`。
4. **陷阱 4：Xcode 26 在全局 `MACOSX_DEPLOYMENT_TARGET=13.0` 下的宿主 `proc-macro` `LINKEDIT` 未对齐 Bug**
   - 在 macOS Tahoe / Xcode 26 工具链下，若全局导出 `MACOSX_DEPLOYMENT_TARGET=13.0` 从零编译 Rust 宿主过程宏（`lib*_proc_macro.dylib`），链接器会生成未对齐的 `LINKEDIT string pool` 导致 `dlopen` 报 `E0463: can't find crate`。
   - **标准做法**：先在临时取消 `MACOSX_DEPLOYMENT_TARGET` 与 `CARGO_ENCODED_RUSTFLAGS` 的原生宿主 SDK 环境下预热 `cargo check --release --features ...,tauri/custom-protocol`（使宿主宏指纹与 `tauri build --target` 1:1 对齐），再开启 `MACOSX_DEPLOYMENT_TARGET=13.0` 编译 `--target aarch64-apple-darwin` 目标产物，最后用 `xcrun vtool -show-build` 逐个校验产物 `minos <= 13.0`。
5. **陷阱 5：图标缺失动态深浅色与比例跳变**
   - 统一对齐 Apple HIG `1024×1024` 画布下的 `824×824` 连续超椭圆网格（无黑角透明 PNG + 原生底投影），使用 `xcrun actool` 编译包含 `Any`（浅色）与 `luminosity=dark`（深色）的 `Assets.car` + `AppIcon.icns`。

---

## 二、借助 Xcode 工具链新增的标准分级测试矩阵（L2.5 / L3）

| 阶段 | Xcode / macOS 工具 | 自动化入口 | 验证目标与通过标准 |
| :--- | :--- | :--- | :--- |
| **L2.5 签名连续性正反证** | `xcrun swiftc` + `Security.framework` + `codesign` | `uv run python tools/verify_xcode_apple_signing.py` | 隔离钥匙串内：**正向**不同 `CDHash` 同 Team ID 静默读取 `0` 弹窗通过；**负向**同 Bundle ID 的 `ad-hoc` 伪造包读取被拒 |
| **L3 二进制与系统版本审计** | `xcrun vtool -show-build` + `otool -l` + `lipo` | `uv run python tools/audit_macos_bundle.py` | 全量 Mach-O 仅含 `arm64`、`minos <= 13.0`、无 `/Users/` 本地路径泄漏、无越界 `@rpath` |
| **L3 动态图标目录编译** | `xcrun actool` + `iconutil` + `plutil` | `tools/generate_macos_icons.swift` + `build_macos_package.sh` | 生成 `Assets.car`（浅/深 20 张 mipmap）与 `AppIcon.icns`，`CFBundleIconName=AppIcon` |
| **L3 沙箱冷启动与资源基线** | `sandbox-exec` + `lsof` + `ps` / `xctrace` | `./tools/verify_macos_runtime_xcode.sh` | 禁网沙箱冷启动成功、TCP/UDP 监听端口数 `= 0`、记录主进程与 Sidecar 真实常驻内存（RSS）基线 |
| **L3 升级/回滚/钥匙串无损验收** | `hdiutil` + `ditto` + `security` | `./tools/test_macos_package_lifecycle.sh <dmg>` | 模拟挂载安装 → 升级 → 回滚 → 卸载重装，本机账户快照 SHA-256 与钥匙串引用 100% 零丢失 |

> **进阶性能剖析（按需手动执行）**：当怀疑存在内存泄漏或后台唤醒异常时，使用 Xcode Instruments CLI 非侵入采样：
> ```bash
> xcrun xctrace record --template 'Time Profiler' --time-limit 30s --attach <PID> --output build/profile.trace
> /usr/bin/leaks <PID>
> ```

---

## 三、本机其他项目横向排查与可复用改造清单

对 `/Users/kyle/Code/Project` 下全部项目扫描后，识别出以下可直接复用本 SOP 的项目：

### 1. `/Users/kyle/Code/Project/minesweeper`（Classic Mines · Swift 6 原生 macOS 应用）— **高优推荐接入**
当前 `scripts/package.sh` 与 `scripts/verify_release.sh` 存在 4 处可直接按本 SOP 升级的点：
1. **升级稳定 Apple Team 签名**：`scripts/package.sh:32` 当前硬编码了 `codesign --force --deep --sign -`；可接入 `AQ_CODESIGN_AUTO=1` 同款自动 `subject.OU` 发现逻辑（移除 `--deep`，使用 `34Y68VQZ4R` 签名），消除每次重打包被 Gatekeeper 当作新未知应用的问题。
2. **接入 `xcrun actool` 浅/深动态图标**：`scripts/package.sh:24-29` 当前仅用 `sips` + `iconutil` 生成静态 `.icns`，可升级为 `Assets.car` 支持 macOS 浅色/深色自动切换图标。
3. **固定最低系统版本并加 `vtool` 门禁**：`swift build -c release` 默认绑定当前主机 SDK（macOS 26/27），建议显式指定 `arm64-apple-macosx13.0` 并增加 `xcrun vtool -show-build` 断言。
4. **解耦 Hardened Runtime 与 `DYLD_INSERT_LIBRARIES` 探针**：`scripts/verify_release.sh:63` 通过 `DYLD_INSERT_LIBRARIES` 注入禁网探针，后续开启 `--options runtime`（公证必需）后会被 macOS AMFI 拦截；应拆分为“开发态动态库探针 + 生产签名包 `nm -u` 符号白名单 + `sandbox-exec` + `lsof` 双重门禁”。

### 2. Web / 小程序 / 后端全栈项目（`FXplanner-V1.2.0`、`decide-to-eat`、`Roast tactical board`、`deer-flow` 等）
- 当前形态为 Web / Docker / 微信小程序，不涉及 macOS `.app` 签名与 Keychain ACL；若后续封装桌面端（Tauri / Electron）或 iOS/macOS 客户端（Capacitor），初始化时直接启用本 SOP 即可避免重走 `ad-hoc` 返工弯路。

---

## 四、可沉淀至全局 `agentic-repo-bootstrap` Skill 的标准条款片段

若需将本规范永久写入全局初始化技能，可在 `agentic-repo-bootstrap` 中追加以下规则块：

```markdown
### macOS / Xcode 原生桌面打包与测试铁律
1. **证书解析禁读 CN 括号**：自动从钥匙串提取证书 PEM 并经 `openssl x509 -noout -subject -nameopt RFC2253` 读取 `OU` 作为 `TeamIdentifier`；无证书测试须显式传 `ALLOW_ADHOC=1`，严禁静默降级。
2. **由内向外分层签名**：禁 `codesign --deep` 写签名；先签嵌套 `.dylib`/`.so`/Helper，锁定资源哈希后再签外层 `.app`。
3. **钥匙串跨版本正反证**：凡读写 macOS Keychain 的应用，必须在隔离临时钥匙串中通过“同 Team 异 CDHash 静默免弹窗读取（正证）+ 同 Bundle ID 的 ad-hoc 包读取被拒（反证）”双重自动化测试。
4. **Xcode CLI 静态与沙箱门禁**：L3 打包必跑 `xcrun vtool -show-build`（核对 `minos`）、`xcrun actool`（编译浅/深 `Assets.car`）及禁网 `sandbox-exec` + `lsof` 零端口冷启动检查；Rust 跨版本目标构建前先在原生宿主 SDK 下预热 `proc-macro` 规避 Xcode 26 `LINKEDIT` 未对齐缺陷。
```
