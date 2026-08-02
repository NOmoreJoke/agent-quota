# Iteration 5 Provider 实机验证记录

## 边界

- 源码基线：`03ecdd0b26fad212737aaca1fb537b872c0c371e`（detached 隔离工作树）。
- 凭据只经原生安全输入框进入 macOS Keychain；报告、fixture、源码 ZIP 均不保存 API Key、OAuth token、Keychain reference、principal reference、Cookie 或原始账户响应。
- 数值不落审计文档；真实账户响应仅保留脱敏字段拓扑。
- 本记录是 Iteration 4 历史报告的后续事实源，不改写历史证据。

## 实机矩阵

| Provider | add→Keychain→probe→refresh→projection | relaunch | reauth/旧引用清理 | delete/purge |
|---|---:|---:|---:|---:|
| GLM 中国区 | PASS（2 项） | PASS | PASS | NOT VERIFIED |
| DeepSeek | PASS（1 项） | PASS | NOT VERIFIED | PASS；删除后状态与 Keychain 旧引用均不存在，重启后未复活 |
| MiniMax 中国区 | PASS（4 项） | PASS | PASS | NOT VERIFIED |
| Kimi Code Token Plan | PASS（2 项，官方 OAuth） | PASS | PASS | NOT VERIFIED |
| Kimi API 中国区 | PASS（3 项） | PASS | PASS | NOT VERIFIED |

DeepSeek purge 后的重新添加仍须在原生安全窗口由测试账户持有人完成，完成前当前持久化状态为 4 个 active Provider、11 项投影；不得将历史 DeepSeek PASS 误报为当前 5/5 状态。最终 native helper 在 Round 9 源码提交审查后重建并重新 ad-hoc 签名；此前完成的重认证不构成最终包的 Keychain 授权证据，最终 live refresh 必须再次由账户持有人完成重认证后复验。

脱敏录制位于 `tests/fixtures/providers/`。GLM、DeepSeek、MiniMax 保留实机响应字段拓扑；Kimi fixture 的 live/synthetic 标识以 fixture 元数据为准，禁止把 synthetic fixture 表述为实网验证。

## 网络与数据边界复核

- Native helper 固定 HTTPS scheme、官方 host/path、GET method；拒绝 port、userinfo、query、fragment 与运行时 endpoint 注入。
- URLSession 使用 ephemeral 配置，禁用缓存、Cookie、credential storage、自动重定向和 proxy dictionary；系统 TLS 信任链仍是剩余边界，未实现证书 pinning。
- 请求密钥仅由 Keychain reference 在 native helper 内读取；Renderer 不接收 credential、原始 HTTP body、status 或响应头。
- Provider body 以 256 KiB 增量上限接收；Content-Length 或累计数据超限立即取消。
- 原始响应先最小化，再经固定 parser 生成 quota projection；持久化文件 mode `0600`，只含脱敏标签、生命周期、错误码和额度投影。
- Kimi OAuth refresh 在 trusted Rust host 的整个 helper fetch 上使用 single-flight，避免多个 helper 进程并发轮换同一 refresh token；并发回归证明 fetch 不重叠。
- host 在任何 sidecar、显式 pending Keychain cleanup 或 Provider helper 前取得 OS 进程级独占 lease；锁文件位于可替换 app state 目录之外。app state rename/recreate 后第二进程仍被拒绝；第二实例安静退出，锁在正常或强制退出后由内核释放。
- 启动不再枚举 Keychain service 或执行 retained-reference 补集删除。状态缺失、部分恢复和普通重装不能触发批量凭据删除；仅 destructive journal 明确记录的逐引用 cleanup 可执行。
- Production 与 development override 使用互斥 Cargo feature；production + debug assertions 编译失败，且最终 binary 实测忽略 `AQ_DATA_ROOT`、sidecar/native helper 环境覆写。

## ChatGPT Pro 审查

- Provider 对话：<https://chatgpt.com/c/6a6d5ff5-f458-83ea-8485-d688de967d5a>
- Packaging 对话：<https://chatgpt.com/c/6a6d606f-a270-83ea-a26a-61f2064dc604>

| Round | Verdict | 处置 |
|---|---|---|
| 1 | `P0=0/P1=0/P2=1`（纠正后） | 256 KiB streaming body bound |
| 2 | `P0=0/P1=0/P2=2` | delegate 锁；固定 endpoint runtime policy |
| 3 | `P0=0/P1=0/P2=0` | Round 2 两项关闭 |
| 4 | `P0=0/P1=0/P2=1` | 发现 Kimi OAuth 跨 helper 并发 refresh 风险 |
| 5 | `P0=0/P1=1/P2=1` | 发现跨 app process 单实例缺失；Rust verifier 的 `0775`/owner/目录链误放行 |
| 6 | `P0=0/P1=1/P2=1` | 发现 `HOME` 可改变 production root；固定 helper 可被 PATH shadow |
| 7 | `P0=0/P1=2/P2=3` | 旧两项关闭；发现启动 Keychain 补集删除、debug profile 退化、目录 inode 置换、Rust provenance/runner、源码/helper 污染 |
| 8 | `P0=0/P1=0/P2=0` | Round 7 五类问题及 stale target package 路径修正均关闭 |
| 9 | 无最终 verdict | 长时间停滞且页面网络错误；保留已完成的完整性、认证注入、Renderer 边界检查，不冒充完成 |
| 10 | `P0=0/P1=0/P2=0` | 901–1100px 两列断点、1024px 无溢出 E2E、Round 7 五类回归均关闭 |

Pro 只审查上传的脱敏源码包，未接触本机凭据或真实账户；其结论不替代 Codex 本机测试。

## 原型一致性

- 权威原型：`docs/design/agent-quota-desktop.pen`；只通过 Pencil 读取，未改写原型文件。
- 1280px 桌面基线：240px sidebar；Overview/Refresh/Status 在左，Accounts/Settings 在右；主区 32px 起始边距。
- 安全边界提示条固定最大 760px；Accounts 成功态为三列、每列约 315px；Settings 主内容最大 800px。
- 浏览器截图与计算布局复核：1280px 下 Accounts sidebar=`right`、3 cards、card widths=`315/315/315`、提示条=`760×40`；901–1100px 自动收敛为两列，≤900px 为一列。2 条 Playwright E2E PASS，含 1024px 与 390px 无横向溢出、侧栏方向、主导航、host-owned action、失败/空/离线状态。

## Iteration 4 结论修订

Iteration 4 的 `PASS/P2=0` 只覆盖当时 local unsigned arm64 包，不代表真实 Provider、后续 DMG cleanup、固定 Rust toolchain、Developer ID、公证、Intel 或干净 VM 已验证。

## 2026-08-02 本地门禁

- 冻结合同发布门禁：`status=ok`；50/50 mutation；clean install、validation replay、projection replay PASS；release input SHA-256 `e3dbd449e41ca8a9b2bd6d11d32e1184292f78034f85b637ec1c7d888ffdd837`；mutation results SHA-256 `6b267aef7791f75b5f35681ce0b68ce83037c09758a3ffc0283b3b65ba262964`。
- Python：Ruff check/format、mypy PASS；165 tests PASS；branch coverage 90.59%。
- Web：ESLint、TypeScript、5 Vitest、renderer boundary、production build、2 Playwright E2E PASS。
- Rust：固定 `rustc 1.97.1` / commit `8bab26f4f68e0e26f0bb7960be334d5b520ea452`；官方 standalone archive SHA-256 `c9748cc86107734a2a024069908a895de7caa2d37062fb641eef9f756938ace2`；完整安装树 SHA-256 `71936ef4f2fee02f3f493f206b12209705d61c2d850128b6f507b7f4ec39e9be`；fmt、clippy `-D warnings`、28 tests PASS。
- Package：精确 Cargo runner/target/production feature；codesign strict、DMG verify、安装→双启动→升级→回滚→卸载保留数据→重装→cleanup PASS；未遗留测试挂载。alternate `HOME` 第二实例安静退出，主 host/sidecar 保持唯一且状态 SHA 不变。
- 最新 local unsigned arm64 DMG：13,257,933 bytes；SHA-256 `15cf772da8f23f849a4f0c3472e0ccf7655a4b1374e3437c9e47bc337fbb86a8`。
- 最新 bundle audit SHA-256 `70bf0c292ebadb298d82e43675cd7c47ad6366bd584473fff66db7ec80f64f94`；bundle manifest SHA-256 `569186566b1491d44f87069271bbee4cfa5e8a2697cffbf3541ae2d670736211`；resource manifest SHA-256 `80c036dc372414ac71e7a30ef1d226e6cb7185b6d7fb98a778d7f9920b9c90cf`；DMG lifecycle PASS，无遗留挂载。

## 发布边界

- 当前仅隔离工作树本地修改；未 commit、push、PR、merge、部署或迁移数据库。
- Developer ID、notarization、Intel、干净 VM：未验证；只能标记 `local unsigned arm64 package`。
