# 开发前最终审计（2026-07-30）

## 结论

`ITERATION 0 PASS / DEVELOPMENT RELEASE BLOCKED`：设计/机器合同可作为实现输入且完整 release gate 已通过；仓库仍无应用源码，不能声称原型功能已本地运行、macOS 安装包已验证或生产安全已验证。

基线：

- branch: `dev`
- commit: `650c2b614296b3652e92abd986c2602f576d1524`
- source package: `agent-quota-audit-650c2b6.zip`
- package SHA-256: `9cda4929df2c1c4ad71bda95477133ce10f5da071c2d3f0ff99501a5d50132cc`

## 阻断项与处置

| ID | 证据 | 处置 | 状态 |
|---|---|---|---|
| G0A-01 | runtime package 固定到不存在的 Python/OpenSSL/Pandoc/Node profile | 恢复本机已证明 profile；同步 raw digest | fixed; full release gate passed |
| G0A-02 | bootstrap 清空环境后未固定 canonical `TMPDIR`，`/tmp` alias 被 validator 拒绝 | 固定 `TMPDIR=/private/tmp`，不放宽 canonical-path validator | fixed; full release gate passed |
| G0A-03 | gate-owned 并发探针 90 秒上限在完整负载下产生时序失败；dyld 将 `/private/tmp` fixture 显示为非 canonical `/tmp` | 探针等待改为 180 秒但拒绝语义不变；dylib fixture 固定到 canonical `/private/var/tmp` | fixed; full release gate passed |
| G0A-04 | 完整 gate 持有多个只读 FD 时，合法 inherited pipe descriptor 可大于 4；validator/gate test hook 将其误判为非法，导致 ready barrier 永远不可达 | 保留 test-only 环境门禁；改为要求 FD `>=3` 且 `fstat` 类型必须为 FIFO/pipe，不再依赖进程当前 FD 编号 | fixed; writer FD 28 regression and full release gate passed |
| UX-01 | 画布 27 个 partially/fully clipped 节点 | 调整画板/组件尺寸、文本换行和失效 `fit_content(0)` | fixed; Pencil layout problems=0 |
| SEC-01 | 8.1 写“重认证后自动 retry”，与“Provider I/O 仅由本次显式手动刷新授权”冲突 | 禁止 reauth/退出离线自动 I/O；必须用户显式刷新 | fixed |
| SEC-02 | 8.6 将 credential generation 轮换与 `rate_limit_cohort` 重映射绑定 | cohort 保持；仅 verified principal identity 真正变化时隔离新 identity/cache namespace | fixed |
| SEC-03 | Purge 缺 `failed`、`outcome_unknown` 可视状态 | 新增 9.9/9.10；未知结果禁止重提 destructive commit，等待 fence recovery | fixed |
| SEC-04 | `connect-src 'none'` 会阻断 Tauri 2 custom-protocol invoke，与 10-command GUI 边界矛盾 | 仅允许 `ipc:`/`http://ipc.localhost`；显式禁止真实 loopback listener、外部 connect source 和降级回退 | fixed; runtime assertion pending |
| UX-02 | Pencil 文档无可执行交互，`href=0` | 不能用静态画布证明运行功能；转为 Iteration 2 的 renderer E2E gate | open by design |
| APP-01 | 无 Tauri/Rust、React/TypeScript、Python core/application service 源码 | 按迭代计划实现 | blocking release |
| APP-02 | 29 DTO 中 `classification` 允许值长 36 bytes，但 `max_utf8_bytes=32`，合法枚举不可构造 | 将该字段上限最小修正为 36；生成资源与 property/closure tests 绑定机器合同 | fixed in Iteration 1; contract gate pending |

原型证据：

- `docs/audits/evidence/prototype-key-flows-2026-07-30.pdf`
- 3,720,753 bytes
- SHA-256 `ef56a89c5d7d276fc7bf2529739d572d61a5f4a3c0788d96d85590688c7e7616`

## 不可破坏边界

- Renderer 仅 10 个 machine-registered command；未知/额外/nested 字段在 application service 前拒绝。
- Renderer 无 secret input/value/length/buffer、文件、网络、shell、sidecar capability。
- Credential 与 destructive confirmation 仅 host-owned native surface。
- Plan digest、nonce、user-presence token 仅 host↔core；renderer 只收 opaque status。
- Reauth、退出离线、超时和 `outcome_unknown` 均禁止自动 Provider replay。
- `config_validate_apply` 仅直接提交 core 分类为 non-destructive 的变更。
- macOS MVP 不启动 HTTP/loopback listener；renderer CSP `connect-src` 仅允许 Tauri 2 内建 custom-protocol IPC 的 `ipc:`/`http://ipc.localhost`，禁止真实 localhost/127.0.0.1、外部网络与 wildcard source。

## 实现前门禁

1. 固定 release gate 返回 0。**已满足（Iteration 0）**
2. Pencil 全文无自动 Provider replay/cohort-generation 混淆；layout problems=0。
3. `docs/contracts` 的 10 command / 29 DTO schema closure 验证返回 0。
4. 应用实现不得把 FakeAdapter、mock/native-overlay 视觉稿声称为真实 Provider 或生产 native surface。

## 外部版本依据

- Tauri 2 CSP：<https://v2.tauri.app/security/csp/>
- Tauri 2 HTTP headers/CSP 示例：<https://v2.tauri.app/security/http-headers/>
- Tauri CLI v2 custom-protocol IPC release note：<https://v2.tauri.app/release/tauri-cli/v2.0.0-alpha.11/>
