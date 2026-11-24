# Agent Quota Feature Map

面向开发者与 AI 协作者的用户视角功能地图、确定性验证入口与红线索引。

## 核心表面与入口

| 用户场景 | 前端/CLI 入口 | 宿主与原生/核心模块 | 确定性验证命令 |
|---|---|---|---|
| **主窗口：额度总览（Window / Wallet View）** | `src/ui/App.tsx` + `src/ui/quotaPresentation.ts` | `src-tauri/src/commands.rs` → `src/agent_quota/native_control.py` | `pnpm test`、`pnpm e2e` |
| **桌面右上角悬浮窗（展开/固定/拖拽）** | `src/ui/FloatingQuota.tsx` + `src/hooks/useFloatingShell.ts` | `src-tauri/src/window.rs` + `src/host/floatingWindow.ts` | `pnpm test`、`pnpm exec playwright test tests/e2e/floating.spec.ts` |
| **明暗外观切换与跨窗口同步** | `src/ui/AppearanceSwitch.tsx` + `src/hooks/useAppearance.ts` | `src/ui/appearancePreference.ts`（哈希固定） | `pnpm boundary`、`pnpm exec playwright test tests/e2e/appearance.spec.ts` |
| **添加账户 / 重新认证（Keychain 托管）** | `useQuotaController.nativeCredential` / `reauthenticate` | `src-tauri/src/commands.rs` → `native/Sources/{Dialogs,KeychainStore}.swift` | `./tools/build_native_helper.sh`、`uv run pytest tests/test_native_control.py` |
| **按需手动刷新与字段最小化解析** | `useQuotaController.refresh` | `src-tauri/src/refresh.rs` → `native/Sources/{ProviderTransport,ResponseMinimizer}.swift` → `src/agent_quota/providers.py` | `uv run pytest tests/test_providers.py` |
| **Google Antigravity 用量查询（官方 `statusLine` 桥接）** | `agent-quota ingest-antigravity-statusline --quiet` | `src/agent_quota/cli.py` → `providers.py`（强制剥离 PII + 60s 相同快照零落盘去重） | `uv run pytest tests/test_cli.py tests/test_providers.py` |
| **两阶段破坏性确认（删除账户 / Purge）** | `useQuotaController.destructive` | `src-tauri/src/commands.rs` → `native/Sources/Dialogs.swift` → `native_control.py` | `uv run pytest tests/test_native_control.py tests/test_export_purge.py` |

## Google Antigravity CLI (`agy`) 接入示例

在 `~/.gemini/antigravity-cli/settings.json` 中配置官方 `statusLine` 钩子（`--quiet` 模式零终端污染，且 60 秒内相同额度零磁盘写入）：

```json
{
  "statusLine": {
    "type": "command",
    "stack_with_default": true,
    "command": "agent-quota ingest-antigravity-statusline --quiet"
  }
}
```

## 绝对架构红线（由确定性门禁强制守护）

1. **冻结合同不可弱化**：`docs/contracts/**`、`docs/{design-proposal,provider-contract,security-model}.md`、`README.md` 与 `renderer_contract_v1.json` 受摘要及 `retention-lint` 保护，禁止顺手改写。
2. **Renderer 物理沙箱**：`src/ui/**` 严禁直接引用 `@tauri-apps/*`、严禁裸写 `useEffect` 或命令式定时器（统一收敛至 `src/hooks/`），严禁发起网络请求或读写任意 `localStorage`（由 `pnpm lint` + `pnpm boundary` 拦截）。
3. **非阻塞宿主与按需自愈**：Tauri 命令一律通过 `async fn` + `spawn_blocking` 执行；Sidecar 超时后立即 `TERM → KILL → reap` 并返回 `outcome-unknown`（绝不自动重放失败请求，仅在后续新请求到来时按需重拉起新会话）。
