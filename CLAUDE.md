# CLAUDE.md — Agent Quota

> 这是给 AI 协作者的**精简主上下文**：只收录无法从仓库推断的导航与工作规则。
> 所有具体规范——含禁令清单、反例、反模式目录——一律留在其权威文档原位，**不在此复述、不搬进主上下文**。

## 这是什么

- **设计合同 + 可运行桌面实现**：Python core/sidecar、Tauri/Rust host、React renderer、macOS native helper。
- 设计终态仍为第 20 轮 `ZERO_ISSUES`；冻结机器合同不得因实现便利而弱化。
- 实现改动必须运行对应 Python/renderer/Rust/package 门禁；合同或规范输入变化还必须运行完整合同门禁。

## 权威顺序（冲突时谁赢）

1. `docs/contracts/*.json` —— 机器权威源（schema / artifact / fixture，带 digest）。
2. `docs/{design-proposal,provider-contract,security-model}.md` —— 规范正文（契约的投影）。
3. `README.md` 的 37 条基线 —— 摘要。

正文与 `.json` 冲突，以 `.json` 为准。

## 验证命令

```bash
# 必须在固定运行时上跑（Python 3.11.15_4 / Node v24.11.1 / Pandoc 3.10.1）：
/bin/sh docs/contracts/runtime-bootstrap-v1.sh docs/contracts/run-release-gate-v1.py --root .
npm run validate --prefix docs/contracts          # 等价入口

uv run ruff check src tests tools
uv run ruff format --check src tests tools
uv run mypy src
uv run pytest --cov=agent_quota --cov-branch
pnpm lint && pnpm typecheck && pnpm test && pnpm boundary && pnpm build && pnpm e2e
cargo fmt --manifest-path src-tauri/Cargo.toml --check
cargo clippy --manifest-path src-tauri/Cargo.toml --all-targets -- -D warnings
cargo test --manifest-path src-tauri/Cargo.toml
```

门禁绑定**具体二进制哈希**（见 `docs/contracts/package.json` 的 `aqValidationRuntime`），他机不可替代；当前 checkout 的任何本地通过只算审计证据，不等于生产发布授权。

## 改动前必知：两个地雷

1. **retention-lint**：四份正文逐 leaf 扫「持久化信号」（文件/缓存/数据库/WAL/journal/密钥库 + 写动作）。除 9 条 `persist:v1:<surface_id>:<operation>:<owner_id>` record 外，**任何残留 signal 都 fail closed**。→ 改动存储/凭据/删除相关句子极易触雷。
2. **标题即锚点**：跨文档链接绑定 heading 文字（如 `provider-contract.md#94-连续失败与恢复`），retention locator 也绑定 normalized heading + ordinal。改标题 = 断链 + 断 locator。`AQ-GENERATED-*` 块字节冻结，勿动。

## 工作方法：先给每条要求分类

- **硬不变量 / 禁令**（安全、授权、凭据、进程/网络边界、留存）→ 不可改写、不可弱化。原文在 `security-model.md` 与 `provider-contract.md`；去那里读，**不要把条文拷进上下文或代码注释**。
- **判断框架 / 偏好**（命名、风格、可由结构推断的约定）→ 当作默认值，可被更优方案覆盖，无需逐字照搬。

判不准时先做 **blind-spot pass**：先列出 unknowns，再动手。开始一个改动前，默认先 `Explore`/读相关章节确认影响面，而非直接编辑正文。

## 改文档的正确姿势

- 只在固定运行时上改；每改一处立即 `npm run validate`。
- 优先「指针」而非「抄录」：新增说明应指向契约路径，不复述条文。
- 不往正文塞自由散文段，除非同步更新 retention / 投影 / heading 校验。
- 禁令、反例、反模式目录一律留在其规范文档原位，不搬进 README 或本文件。
- 详见 [`STREAMLINE-PLAN.md`](STREAMLINE-PLAN.md) 的分层风险判定（T1 安全 / T3 不建议改写）。

## 去哪里找

| 主题 | 位置 |
|---|---|
| 整体设计 / 数据模型 / 分阶段 | `docs/design-proposal.md` |
| Provider / 凭据 / discovery | `docs/provider-contract.md` |
| 安全模型 / 分层门禁 / 日志留存 | `docs/security-model.md` |
| 机器权威源（schema + artifact + fixture） | `docs/contracts/*.json` |
| 校验工具 | `docs/contracts/*.py` / `*.mjs` / `*.sh` |
| 审计历史 / 产品决策记录 | `docs/audits/` |
| 文档精简计划 | `STREAMLINE-PLAN.md` |

## 不要做

- 不要在未验证门禁时改正文或契约。
- 不要把契约条文复制进代码注释或新文档——指过去即可。
- 不要为实现便利顺手改契约措辞；实现必须服从冻结合同。
