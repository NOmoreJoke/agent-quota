# 第 18 轮修复处置记录

- 处置日期：2026-07-19（Asia/Shanghai）
- 处置边界：仅处理本轮审计确认成立的问题；不替用户作产品选择，不访问真实账户、Provider 或凭据，不联网，不 stage、commit 或 push。
- 设计版本：`v2.4`

## AQ-R18-001 — BLOCKED_USER_DECISION

- 核验结论：成立，且只能由用户决定。
- 处理：保持阻塞。没有新增 `account/read`，没有猜测 Codex 身份，也没有自行把 Codex 移出 MVP 或指定替代 Adapter。
- 验收：方向 A/B 仍须由用户明确选择；Gate 0A 保持关闭。

## AQ-R18-002 — FIXED

- 核验结论：成立。原环境标志、shell 路径摘要和通配 entry 不能证明实际启动链。
- 处理：把仓库 bootstrap 明确定义为本地审计证据 checker，任何本地成功都固定输出“外部 attestation 缺失、无固定启动权限”；生产固定启动必须由仓库外既有信任根绑定实际解释器、已打开 bootstrap/entry 字节和运行时身份后出具 attestation。checker 同时拒绝替代 shell，使用四项 exact entry/raw-pin allowlist，逐段拒绝 symlink，并从已核对 inode/stat/长度的文件描述符摘要和执行同一 entry 字节。
- 验收：自填环境值不能升级权限；Bash、未登记 entry、bootstrap raw drift、intermediate symlink 均拒绝；opened-inode/path swap 永远只能得到本地审计结论；entry 并发替换由已打开描述符和读前/读后 stat 拒绝或隔离。

## AQ-R18-003 — FIXED

- 核验结论：成立。原 profile 未覆盖 `_hashlib` 的 Homebrew libcrypto、Pandoc 的 GMP、Python 的 liblzma 和实际 loaded-image 集合。
- 处理：新增 exact macOS build `25F84` 系统 image 信任边界。Python、Pandoc、Node 的每个非系统 image 都登记 canonical no-follow path、regular kind、uid/gid、mode、size、raw SHA-256 和递归非系统依赖边；Homebrew `opt` 目标单独绑定。bootstrap 在启动 Python 或 Pandoc 前用 OS 信任根工具核对关键 image/edge，并清除调用者环境；Python guard 枚举当前 dyld image，validator 用 `vmmap` 核对 Pandoc/Node 实际集合。
- 验收：opt target 切换、libcrypto/GMP/liblzma bit drift、额外非系统 image、loader/Python 注入、同 executable 不同 image 集均 fail closed；任何成功摘要前先完成外部预检。

## AQ-R18-004 — FIXED

- 核验结论：成立。旧 validator/schema/release QA 把 R17 失败快照写死，无法在不改代码时进入最终 PASS。
- 处理：history manifest 现在自描述 `1..20` 连续 round/kind/path/raw digest；snapshot 与 validator 从 manifest 动态推导当前 exact closure。current status 是 `ISSUES_OPEN` 与 `ZERO_ISSUES` 判别联合：FAIL 轮必须有 resolution，PASS 轮必须为 `PASS_ZERO_ISSUES`、空 issue、无 blocker 且禁止 resolution。schema 只约束形状和分支，artifact + manifest 决定当前值，四份 Markdown marker 必须一致。
- 验收：动态 latest QA 覆盖删除、替换、伪首行、回退、自引用和 marker 漂移；R18 fail→R19 pass 隔离模拟只改 history/manifest/artifact/docs/registry 数据，validator 与 gate 原始字节摘要保持不变。

## 验证记录

- 机器验证：正式 bootstrap 下 validator、projection verifier、41-case mutation runner、full clean-install release gate 均须通过；validator/projection 双重 replay 必须逐字节一致。
- R18 专项：启动边界、动态 image 和动态 history/PASS 状态反例由 full gate 自行执行并核对目标 failure class。
- 完整性：R1–R18 audit 与 R1–R17 resolution 的启动哈希保持不变；本文件采用 detached 两阶段流程，不含自身摘要或 manifest 摘要。
- 当前边界：全部成功结果仍是 `audit-evidence-only-not-a-release-authority`，不等于生产发布授权，也不关闭尚待用户选择的产品阻塞项。
