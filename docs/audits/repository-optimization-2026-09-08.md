# 优化更新 · 2026-09-08

| 项目 | 实现 | 验收边界 |
|---|---|---|
| 基线 | 延续 `codex/repo-refactor-20260908` 上轮重构工作区 | 原 `dev` 工作区四项改动保留；未合并、推送 |
| 产品模型 | 验收矩阵 → `launch_products_v1.json` + Swift 生成名单 | 10 产品、7 候选、5 可创建、2 实现阻塞、3 信息卡；未提高任何 capability claim |
| UI | 10 产品卡、搜索/能力筛选、原生选择器入口 | 禁用卡不可触发凭据入口；可用卡打开现有选择器，不预选产品 |
| 配置一致性 | 生成器 `--check` + Python/Swift endpoint 对照 | CI、打包预检拒绝投影漂移；原请求与鉴权方式未变 |
| 连接状态 | checking / ready / offline / unavailable | 未连接不显示健康；只读重连不调用 Provider 刷新 |
| 生命周期 | 挂载代次校验 Host 请求结果 | 卸载后忽略迟到结果、不发起后续读取；不声称撤销已经提交的 Host 动作 |
| CI | Rust job 安装固定 Python，显式设置 sidecar/Python 可执行文件 | 三个环境条件集成测试真实执行；不再因变量缺失提前返回 |
| Rust 反例 | 超限 helper 自然退出 10s、测试预算和时长上限 5s | 替代易受构建负载影响的 1s 断言；旧无界等待仍失败；生产期限未变 |

## 数据来源与更新

权威输入：`docs/acceptance-matrix-v2.json`。生成器只投影现有范围；不写回验收状态。

```sh
uv run python tools/generate_launch_products.py
uv run python tools/generate_launch_products.py --check
```

- React 读取生成 JSON，不再从历史 78 行 catalog 推导上线范围。
- Swift 保留独立的静态、安全网络配置；可创建名单由同一输入生成。
- Python manifest 与 Swift hostname/path 通过离线测试比对；该测试不证明签名或真实 API 成功。
- 原始 78 行 catalog 保留，用于历史审计和 adapter 覆盖；不删除数据。

## 验证

| 门禁 | 当前结果 | 证据 |
|---|---|---|
| Python | PASS | 297 tests；总覆盖率（含分支）90.31% |
| Renderer | PASS | 42 tests；lint / typecheck / boundary / production build |
| Playwright E2E | PASS | 4 tests；10 卡片、5 enabled/5 disabled、筛选、响应式、离线禁用 |
| 页面检查 | PASS | 桌面1280、窄屏390截图已检查；fixture账户非真实账户；开发favicon缺失404与本轮改动无关 |
| Swift | PASS | arm64 编译、warnings-as-errors、provider minimization 自检 |
| Rust | PASS | clippy；37 tests；显式启用真实 sidecar 的三个条件测试 |
| 完整DMG与安装生命周期 | 未执行 | 仅更新/检查打包预检入口；不计作发布验收 |
| 冻结合同 | BLOCKED | `runtime_bootstrap_error=operating system release mismatch` |
| 独立门禁第 1 轮 | PASS | 产品投影/执行名单、连接与卸载边界、CI条件测试配置核验 |
| 独立门禁第 2 轮 | PASS | 重复adapter、信息卡提升权限、未知capability反例；生成确定性和打包预检核验 |
| 独立门禁第 3 轮 | PASS | 最终代码、生成数据、日志、桌面/窄屏截图核验；未发现本轮代码阻断 |

Rust 本轮首次运行只有超限反例的 `<1s` 性能断言失败；实际返回仍为 Protocol。调整的是测试调度余量，随后完整重跑通过。

## 剩余队列

| 项目 | 状态 | 原因 / 下一步 |
|---|---|---|
| RC-007 产品模型 | 代码已实现；安装态验收未完成 | 本报告更新原 `KNOWN_ISSUES.md` 中“无10卡模型”的历史状态 |
| 文档与冻结合同 | BLOCKED | README/规范仍保留原发布基线；固定运行环境恢复后统一更新并验证 |
| 火山两项、百炼/MiMo禁用项 | 保持禁用 | 原实现/API 证据与权限验收缺口不由本轮产品投影解决 |
| Apple 身份、真实账户生命周期 | 待外部条件 | 未调用真实凭据/Provider；未签名发布、安装或清理用户数据 |
| Rust/Swift/Python大模块拆分 | 待后续 | 本轮先收敛产品来源与异步边界；不迁移现有 JSON/SQLite 数据 |
| 功耗/内存测量 | 未执行 | 需目标安装产物与独立空闲测量；无未测性能结论 |
| 依赖重锁/合同摘要更新 | BLOCKED | 固定合同门禁不可用；不绕过 OS/二进制身份校验 |
