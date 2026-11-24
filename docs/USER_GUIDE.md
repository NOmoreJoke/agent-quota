# Agent Quota 使用手册

## 安装与运行平台

目标平台：Apple Silicon（`arm64`）、macOS 13.0 及以上。按 [INSTALLATION.md](INSTALLATION.md) 构建或安装本地开发包；公开发布前需额外具备 Apple Developer ID 签名与公证（见 [MACOS_SIGNING.md](MACOS_SIGNING.md)）。

## 接入远程 API / OAuth Provider

1. 打开主窗口「账户与 Provider」（页面顶部提供低调中性隐私提示，点击「安全与隐私说明 →」可直达安全详情）。
2. `Provider Preset` 展示 11 张独立产品卡，支持按关键词搜索及「全部 / Window View / Wallet View」切换筛选。
3. 点击已开放产品的「打开原生选择器」或右上角「添加 Provider」。
4. 在 macOS 原生 AppKit 安全弹窗中选择产品并输入凭据（单 API Key、AK/SK 双密钥或 `Kimi Code` OAuth 设备授权）；凭据直写 macOS Keychain，绝不经过前端 WebView 或 Python 磁盘文件。
5. 返回「概览」或展开桌面悬浮胶囊，点击「全部刷新 / 刷新用量」按需拉取最新额度。

## 一键接入 Google Antigravity 用量（零密钥本地桥接）

Google Antigravity 不设公开远程 HTTP 额度接口，Agent Quota 对接官方公开的 `agy` CLI `statusLine` 标准输入契约（自动剥离 `email`、`cwd`、`workspace`、`transcript_path` 等隐私字段，并对 60 秒内无变化的配额快照跳过磁盘写入）：

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
- **Wallet View（钱包视图）**：展示各平台原币种余额、`Extra Usage` 或 `AI Credits`。不同单位、不同币种与不同 Provider 严格隔离，绝不混算求和。
- **桌面悬浮胶囊**：悬停 `160 ms` 展开、移出 `350 ms` 收起（仅读取本地缓存快照，2 秒内焦点重读自动节流）；点击「保持展开」固定在桌面，`Escape` 取消固定并收起；侧栏支持一键切换浅色 / 深色主题并跨双窗口实时同步。

## 轻量化资源与数据清理（Purge）

- **零后台轮询**：无常驻定时抓取线程、无本地监听端口、无空闲 CPU 轮询唤醒；Sidecar 采用单会话常驻读取线程并在异常断开后支持按需冷却自愈（绝不自动重放超时请求）。
- **应用内全量清理**：卸载前如需清空本机状态与 Keychain 引用，请在「设置 → 清理本机数据」完成原生破坏性确认（Purge）。
