# Agent Quota 使用手册

## 安装与运行平台

目标平台：Apple Silicon（`arm64`）、macOS 13.0 及以上。按 [INSTALLATION.md](INSTALLATION.md) 构建或安装本地开发包；公开发布前需额外具备 Apple Developer ID 签名与公证（见 [MACOS_SIGNING.md](MACOS_SIGNING.md)）。

## 接入远程 API / OAuth Provider

1. 打开主窗口「账户与 Provider」（页面顶部提供低调中性隐私提示，点击「安全与隐私说明 →」可直达安全详情）。
2. `Provider Preset` 展示 15 张独立产品卡（涵盖 10 个品牌），支持按关键词搜索及「全部 / Window View / Wallet View」切换筛选。
3. 点击已开放产品的「打开原生选择器」或右上角「添加 Provider」。
4. 在 macOS 原生 AppKit 安全弹窗中选择产品并输入凭据（单 API Key、AK/SK 双密钥、`Kimi Code` 设备授权 OAuth、`Google Antigravity` Google OAuth 或 `WorkBuddy 个人版 (中国区)` 官方无端口 OAuth）；凭据直写 macOS Keychain，绝不经过前端 WebView 或 Python 磁盘文件。
   - **Antigravity OAuth Client 配置说明**：源码仓库不含任何硬编码 OAuth `client_secret`；构建时可通过环境变量 `AQ_ANTIGRAVITY_OAUTH_CLIENT_ID` / `AQ_ANTIGRAVITY_OAUTH_CLIENT_SECRET` 注入默认值，或在原生授权弹窗的 Client ID / Client Secret 输入框中临时指定（同样仅写入本机 Keychain）。
5. 返回「概览」或展开桌面悬浮胶囊，点击「全部刷新 / 刷新用量」按需拉取最新额度。
6. **凭据过期与重新授权**：当 API Key 失效或 `Kimi Code` / `Antigravity` / `WorkBuddy` OAuth 凭据过期（含 OAuth `400 invalid_grant`、401/403）时，主窗口会自动跳出「凭据已过期，请重新授权」浮层提示，悬浮胶囊也会亮起警示并显示 `N 项需授权`。直接点击「重新授权」即可拉起 macOS 原生授权窗口完成重新登录；若先点击「稍后处理」，主窗口顶部仍保留快捷重新授权提示条，再次点击刷新会重新弹出提示。

## Google Antigravity 备选：`agy statusLine` 本地零密钥桥接

除上述原生 Google OAuth + CloudCode 远端查询外，Agent Quota 仍保留官方 `agy` CLI `statusLine` 标准输入契约作为本地零密钥备选（与 OAuth 账户共存，互不覆盖；自动剥离 `email`、`cwd`、`workspace`、`transcript_path` 等隐私字段，并对 60 秒内无变化的配额快照跳过磁盘写入）：

- **方式 A（开发环境已安装 `agent-quota` CLI）**：
  ```bash
  agent-quota setup-antigravity
  ```
- **方式 B（仅安装 `/Applications/Agent Quota.app`，无需本机安装 Python）**：
  ```bash
  "/Applications/Agent Quota.app/Contents/Resources/sidecar/agent-quota-sidecar" cli setup-antigravity
  ```

常用维护参数：
- 检查当前绑定状态：`agent-quota setup-antigravity --check`
- 静默模式（不在 `agy` 终端底部渲染单行额度摘要）：`agent-quota setup-antigravity --quiet-hook --force`
- 移除状态栏钩子（无损保留 `~/.gemini/antigravity-cli/settings.json` 其余配置）：`agent-quota setup-antigravity --uninstall`
- 终端只读查看桌面端脱敏额度快照：`agent-quota desktop-status`

## 双视图与悬浮胶囊交互

- **Window View（窗口视图）**：展示 5 小时 / 周度 / 月度订阅配额剩余百分比；正常额度行统一使用清爽中性底色，仅耗尽、异常或因周额度耗尽联动的短周期行高亮提示。
- **Wallet View（钱包视图）**：展示各平台原币种余额、`Extra Usage`、`AI Credits` 及 `GLM` / `MiniMax` / `WorkBuddy` 加油包余额。不同单位、不同币种与不同 Provider 严格隔离，绝不混算求和。对于仅提供网页后台会话查余额且无公开纯 API Key 余额接口的产品（`智谱 GLM API 账户余额`、`MiniMax API 账户余额`、`Qoder 个人版（中国区）`），卡片保留只读信息展示并严禁 Cookie 抓取。
- **桌面悬浮胶囊**：悬停 `160 ms` 展开、移出 `350 ms` 收起（仅读取本地缓存快照，2 秒内焦点重读自动节流）；点击顶部标题栏（`Agent Quota`）可随时切换展开或折叠（已固定状态下点击同样取消固定并立即折叠）；点击「保持展开」固定在桌面，`Escape` 取消固定并收起；侧栏支持一键切换浅色 / 深色主题并跨双窗口实时同步。

## 轻量化资源与数据清理（Purge）

- **零后台轮询**：无常驻定时抓取线程、无本地监听端口、无空闲 CPU 轮询唤醒；Sidecar 采用单会话常驻读取线程并在异常断开后支持按需冷却自愈（绝不自动重放超时请求）。
- **应用内全量清理**：卸载前如需清空本机状态与 Keychain 引用，请在「设置 → 清理本机数据」完成原生破坏性确认（Purge）。
