# Agent Quota 第 12 轮问题处置记录

> 状态：v1.8 文档与机器合同修复完成；5 项 `FIXED`，1 项 `BLOCKED_USER_DECISION`。本记录不是新的独立审计，不能解除 0A 门禁。

| Finding | 结论 | 处置与证据 |
|---|---|---|
| AQ-R12-001 | `BLOCKED_USER_DECISION` | Codex stable identity 仍无可由代码或公开协议唯一推出的安全基线。保持 Codex、保持 incompatible 与 0A fail closed；不增加 `account/read`、不读取真实账户、不降低要求，等待用户作产品决策。 |
| AQ-R12-002 | `FIXED` | 新增固定根、逐 segment no-follow、编译期 allowlist 的只读 validator；覆盖 JSON 边界、Draft 2020-12 meta/instance、全部 pin、90 个数组策略、RepoPath、operation、lease、LocalKey、retention 与 core fixture。Ajv `8.17.1` 由 manifest/lock 固定，全部门禁通过后才输出 `status=ok`。 |
| AQ-R12-003 | `FIXED` | `canonicalize-registry-v1.py` 收窄为纯只读 verifier/renderer：无写入参数、写入 API 或自选根目录；validator 从固定根按编译期 allowlist 逐 segment no-follow 读取。既然没有写入路径，失败时不存在半写或原子替换边界。 |
| AQ-R12-004 | `FIXED` | 将 checkout 内未跟踪工具明确降级为审计证据。生产/0A 工具身份只能由外部签名 release，或 VCS commit 加工具 raw SHA-256 与先前受信根授权固定；工具禁止自 pin。 |
| AQ-R12-005 | `FIXED` | 五个 artifact pin 改为 registry 行的唯一生成投影，以 `AQ-GENERATED-ARTIFACT-PINS-V1` marker 与 projection hash 绑定；缺项、手写分叉、重排或 hash 不一致均由 verifier 拒绝。 |
| AQ-R12-006 | `FIXED` | persistence 语法收敛为严格 `persist:<surface_id>:<operation>`；九处规范性声明迁移到具体 operation，fixture 覆盖旧二段式、未知操作、跨 leaf、重复 directive、无 owner 与合法三段式。 |

本轮未修改第 1 至 12 轮 audit，也未修改第 1 至 11 轮 resolution；未执行 stage 或 commit。修复通过本地只读验证与 mutation suite 后，仍须新的独立审计，并且 Codex stable identity 决策完成，才可重新评估 0A。
