# 第 13 轮审计处置记录

- 处置日期：2026-07-18（Asia/Shanghai）
- 处置结论：6 项工程缺口已修复；1 项产品方向继续等待用户决策
- 发行判断：仍不能进入实现冻结或通过 Gate 0A。只有新的独立审计返回零问题，并且用户完成 Codex 稳定身份决策后，才可改变该结论。
- 边界：未访问真实账户、Provider、凭据或用户数据；未联网；未 stage、commit 或 push；未修改第 1–13 轮既有审计报告或第 1–12 轮处置记录。

## 逐项处置

| 审计 ID | 状态 | 修复与证据 | 剩余风险 |
| --- | --- | --- | --- |
| `AQ-R13-001` | `BLOCKED_USER_DECISION` | 保持 Codex `official_cli_zero_binding` 的稳定身份来源未登记、正式 fetch/cache/LKG incompatible、Gate 0A fail closed；没有新增 `account/read`，没有移除 Codex，也没有放宽身份域或多账户隔离要求。 | 必须由用户选择并确认有稳定 identity evidence/domain 的方向，随后另行修改合同、迁移与隔离向量并接受新审计。 |
| `AQ-R13-002` | `FIXED` | `evaluate_retention_ast` 不再按 live/fixture 绕过 persistence 或 TTL 判定。既有非 surface 段落只能通过 retention artifact 中 schema-bound、UTF-8 排序且逐项必须被消费的 `(path, leaf_sha256, reason)` 例外；fixture 不接收例外。三份主文档分别加入新增 TTL owner 与无 directive persistence mutation，6 项均拒绝；26 个 fixture 与现有 9 个三段式 directive 继续通过。 | 任何被例外覆盖的 leaf 改动都会使 digest 失配并要求重新审查；例外仍需在后续独立审计中确认是否足够窄。 |
| `AQ-R13-003` | `FIXED` | `rate_reserve_result_contract.success_path_counts` 对 discover/doctor 的 HTTP 与 official-cli 四条路径形成总映射。schema 对 HTTP 固定 `1/1/1/1`、official-cli 固定 `0/0/1/1`；semantic validator 从实际 steps 推导 credential resolution、Credential Source call、reservation row 和 provider attempt，且显式断言 zero-binding Source call 为 0。计数漂移 mutation 被拒绝。 | 当前映射只覆盖该结果合同登记的四条路径；未来增加路径必须同时扩展总映射、schema 与 step-closure 验证。 |
| `AQ-R13-004` | `FIXED` | operation projection source 已包含完整 `/error_rows` 与 `/safe_param_schemas`，连同 path/stage/error union 生成无损 canonical JSON marker；marker 内字节与 projection SHA-256 exact verification。任一 error row 改动但保留旧 marker 的 mutation 被拒绝。正文表明确降级为非穷举阅读索引。 | marker 较大但仍受 registry 524288-byte 上限；实现仍必须读取 artifact，不能解析 Markdown。 |
| `AQ-R13-005` | `FIXED` | lease inference 现在返回 `value_type/unit/clock_domain`，逐 operand/operator/formula/conversion/policy reference 和四个顶层 formula reference 验证签名。每个 policy 显式登记 expiry/parent-deadline expected signature；expiry 强制为 DB UTC millisecond timestamp。boolean-as-expiry、DB/monotonic domain 混用、非法 conversion 三项 mutation 均拒绝，现有 boundary/renew/takeover/provider deadline 与 signed-int64 gate 继续通过。 | 新 operator 或 formula result kind 必须新增明确 propagation rule；未知规则 fail closed。 |
| `AQ-R13-006` | `FIXED` | package/lock identity、root dependency 与闭包逐项核对；helper 回报实际 Ajv version、package/entry 解析路径、全部依赖 package version 与内容树摘要。Node/npm/Pandoc 的 exact version 和 resolved executable SHA-256 被固定。`run-release-gate-v1.py` 在隔离目录执行 offline clean `npm ci`，双次重放 validator 与 projection verifier，并强制运行完整 28-case mutation suite。runtime profile 与 checkout 明确标记为 audit evidence，不能自授 release authority。 | 生产/0A 仍需要外部签名 release，或 VCS commit + tool raw SHA-256 + 先前受信根授权；不同 OS/runtime 必须产生受审查的新 profile，不能静默接受。 |
| `AQ-R13-007` | `FIXED` | `RepositoryReader` 首次 no-follow 读取时冻结 bytes 与 `(dev,inode,mode,size,mtime_ns,ctime_ns)`；后续验证和 input digest 只使用首次 snapshot，成功前逐路径重开并比较身份、stat、长度和内容。validator、canonicalizer 与 release gate 都执行 source-unchanged；验证期间修改 README 的并发 mutation 被拒绝。 | 文件系统若不能提供稳定 inode/stat 语义应 fail closed，并需在目标平台另行验证；当前证据只覆盖本机工具链。 |

## 机器合同与摘要

- registry anchor：`272f3e41da77f0bc8f92cb40e27dc3afd87b49ad04e4632f748d0cb29b34841b`
- artifact pin projection：`871c78434970fd745cc0439a796effd4187dc417d30102436e1731bb0d1e3f20`
- semantic validator：11 个
- JSON Schema instance：8 个；schema array policy object：91 个
- core fixture：25 个；retention fixture：26 个；live directive：9 个
- mutation：28 个；其中 fixture ID 仅诊断的正向项通过，其余 27 个负向项全部拒绝
- 固定运行时证据：Node `v24.15.0`、npm `11.12.1`、Pandoc `3.9.0.2`、Ajv `8.17.1`

## 已执行验证

```text
python3 -m py_compile docs/contracts/validate-contracts-v1.py docs/contracts/canonicalize-registry-v1.py docs/contracts/run-validation-mutations-v1.py docs/contracts/run-release-gate-v1.py
node --check docs/contracts/validate-json-schema-v1.mjs
jq -e . docs/contracts/*.json docs/contracts/schemas/*.json docs/contracts/fixtures/*.json
python3 docs/contracts/validate-contracts-v1.py
python3 docs/contracts/canonicalize-registry-v1.py
python3 docs/contracts/run-validation-mutations-v1.py
python3 docs/contracts/run-release-gate-v1.py
```

正常 validator 输出 `status=ok` 与 `source_bytes_unchanged=true`；projection verifier 输出 `projection_status=verified` 与 `source_bytes_unchanged=true`；mutation runner 输出 `mutations=28`、`source_bytes_unchanged=true`、`status=ok`；release gate 输出 `clean_install=verified`、两类 replay deterministic、`mutation_suite=passed`、`release_authority=audit-evidence-only-not-a-release-authority` 与最终 `status=ok`。

## 历史完整性与 Git 状态

- 第 1–12 轮 audit/resolution 与第 13 轮 audit 的 SHA-256 已在修复前后比较；历史文件未变。
- 仓库仍为 `No commits yet on main`，全部文件未跟踪；本轮没有 stage、commit、push 或破坏性 Git 操作。
- 本记录是本轮唯一新增的 resolution；仍需由新的独立 Agent 进行下一轮全量对抗性审计。
