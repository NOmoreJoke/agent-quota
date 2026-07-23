# Agent Quota 第 11 轮审计处置记录

> 处置版本：v1.7 / 2026-07-18
> 结论：11 项已修复，1 项等待用户决策；仍需新的独立 Agent 全量复审，当前不能宣告零问题或通过阶段 0A。

本轮保持既定安全边界：没有加入 `account/read`，没有读取真实账户，没有移除 Codex，也没有降低身份、路径、持久化、凭据副作用或发行安全要求。

| 审计项 | 判定与状态 | 机器闭环 | 验证 |
| --- | --- | --- | --- |
| AQ-R11-001 | **FIXED** | 新增受版本控制的 `canonicalize-registry-v1.py`，一次生成正文投影、fixture 引用、5 artifact/6 schema/2 fixture 的 raw/domain pin 与 registry anchor；输入清单登记在 registry。 | `--write` 后再次只读运行收敛为 `status=ok`；所有登记摘要逐项匹配。 |
| AQ-R11-002 | **BLOCKED_USER_DECISION** | Codex 继续 `incompatible`，正式 fetch、cache/LKG 写入与 0A 保持 fail closed。 | allowlist 未增加 `account/read`，没有从 rate-limit payload、进程或 principal 推断身份，也没有移除 Codex。 |
| AQ-R11-003 | **FIXED** | online path 统一为 immutable `*RequestPlan → reserve → commit → final context → Provider I/O`；plan 禁止 receipt/credential/access identity，final context 必须带 committed receipt。 | 6 条 provider path 的 data-dependency row 与 exact stage array 一一对应，均满足 receipt/context/first-byte 时序。 |
| AQ-R11-004 | **FIXED** | HTTP doctor/discover 先以 conservative endpoint group reserve，成功后才 credential/evidence；verified cohort 只在同一 row attach。 | reserve 前 credential read 为 0；成功路径 row/credential/attempt 均恰为 1，第二次 reserve 被禁止。 |
| AQ-R11-005 | **FIXED** | 6 schema 统一 `aq-array-order-v1`；registry schema 提供 strict `arrayOrderMetadata` fragment；core fixture 按 `fixture_id` 修正顺序。 | 每个 `type=array` pointer 恰取默认或一个 override；legacy 字段、duplicate/dangling override 与 keyed 相邻逆序拒绝。 |
| AQ-R11-006 | **FIXED** | `crash_grace_ms` 改为 `{type:int64_ms,unit:milliseconds,value:2000}`；AST literal 带 type/unit；int64 最大值统一为 `9223372036854775807`。 | `2^63-1` 接受、`2^63` 拒绝，source 文本不参与求值，混合 unit 在执行前失败。 |
| AQ-R11-007 | **FIXED** | Codex descriptor 投影直接生成自 core artifact 的 exact roots/wire refs，包含 aggregate v2 与 `v1/InitializeResponse.json`。 | generated core projection 显示两个 roots 恰一次；projection hash 由 canonicalizer 反向验证。 |
| AQ-R11-008 | **FIXED** | 选择 eager 语义：payload purpose 集合必须等于 8 项 registry，且每项恰一 active；golden payload/envelope补全全部 entry。 | 独立重算 8 个 key ID、nonce、AAD 与 AES-256-GCM ciphertext/tag一致；缺 purpose/未知 purpose/零或双 active 拒绝。 |
| AQ-R11-009 | **FIXED** | registry/core/retention 复用 canonical `RepoPath` grammar；retention 登记 fixed-root、逐 segment `openat(O_NOFOLLOW)` 与 final fd proof。 | absolute、dot、dot-dot、repeated slash、backslash、case、percent、Unicode 与 symlink mutation拒绝，现行路径接受。 |
| AQ-R11-010 | **FIXED** | 规范性 persistence 只来自 `persist:<surface_id>:<operation>` strict AST 与唯一 inventory owner；普通 prose 明确无 storage 语义。 | plural/inflection prose得到确定的 non-normative verdict；未知 directive/surface fail closed，fixture ID 不参与结果。 |
| AQ-R11-011 | **FIXED** | core fixture 的 opaque `vector` 替换为按 5 个 domain 判别的 strict input union；budget/Codex/registry/migration/path 都给出可计算输入。 | runner 只读 `domain+input`；改 fixture ID 不改变 verdict，schema 拒绝 domain/input错配和额外字段。 |
| AQ-R11-012 | **FIXED** | operation stage/error/path 与 core descriptor/cascade 字段从 artifact 生成 Markdown marker 区块并保存反向摘要；删除旧 hand-written trace union。 | projection source pointer、marker、digest 与正文逐字节匹配；cascade 字段统一为 `cascade_root_semantic_key`。 |

## 验证摘要

- JSON 严格解析：registry、5 artifact、6 schema、2 fixture 全部通过；6 schema 通过 Draft 2020-12 meta-validation，registry 与5 artifact 通过绑定 schema。
- 密码学：LocalKey 八个 `aqk_`、nonce、AAD、payload ciphertext/tag全部独立重算匹配。
- 语义：provider dependency、reserve side effects、array dialect/order、typed lease AST、RepoPath corpus、structured persistence、strict fixture union与 generated projection均执行。
- 历史完整性：第 1 至 11 轮 audit 与第 1 至 10 轮 resolution 的修订前 SHA-256 全部保持不变；只新增本文件。
- 仓库仍无应用实现，因此没有可运行的 unit/integration/e2e；本处置只关闭规范、schema、fixture 与机器门禁缺陷。

最终状态是 `11_FIXED_1_BLOCKED_USER_DECISION_NEEDS_NEW_AUDIT`。只有用户作出唯一产品决策并由新的独立 Agent 全量复审后，才可重新评估阶段 0A；不得把本处置解释为零问题结论。
