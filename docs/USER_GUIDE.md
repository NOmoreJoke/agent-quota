# Agent Quota 使用手册

## 安装

目标平台：Apple Silicon、macOS 13.0 及以上。按 `INSTALLATION.md` 构建或安装本地
unsigned DMG；当前不提供 Intel/universal、Developer ID 或公证声明。

## 添加 Provider

1. 打开「账户与 Provider」。
2. Provider Preset 仅展示 DeepSeek、Kimi、Kimi For Coding、MiniMax、Zhipu GLM；可搜索名称，并按「全部 / Window View / Wallet View」筛选。
3. 选择显示「添加」的预设继续；其他目录供应商不会生成卡片。
4. 在 macOS 原生安全窗口输入凭据。Renderer 不接收秘密正文。
5. 返回概览，手动刷新并查看对应 Window View 或 Wallet View。

## 视图

- Window View：Coding Plan、订阅或滚动窗口的剩余额度。
- Wallet View：API 钱包、credit 或 Extra Usage。
- 不同单位、币种和 Provider 不求和；错误或过期数据保留明确 health/freshness。

## 无真实订阅时的验证

项目使用官方 schema fixture、脱敏录制、HTTP/字段错误注入和 deterministic contract
tests；这些验证不会发出真实 Provider 请求，也不代表账户或生产环境通过。

## 资源策略

默认仅按需刷新；没有账户时不触发 Provider 网络。当前无常驻 SchedulerHost、Renderer
定时器或 loopback listener。完整边界和包大小门禁见 `PERFORMANCE.md`。
