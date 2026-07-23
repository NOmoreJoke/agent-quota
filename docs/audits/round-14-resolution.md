# 第 14 轮审计处置记录

- 处置日期：2026-07-18（Asia/Shanghai）
- 处置结论：5 项可直接修复的设计/验证缺口已关闭；1 项产品方向继续等待用户决策
- 发行判断：仍不能进入实现冻结或通过 Gate 0A。只有用户完成 Codex 稳定身份决策，且新的独立 Agent 全量审计返回零问题，才可改变该结论。
- 边界：没有访问真实账户、Provider、凭据或用户数据；没有新增 `account/read`，没有移除 Codex，没有降低身份、路径、持久化或发行安全边界；没有 stage、commit 或 push；没有修改第 1–14 轮 audit 或第 1–13 轮 resolution。

## 逐项处置

| 审计 ID | 状态 | 修复与当前字节证据 | 剩余风险 |
| --- | --- | --- | --- |
| `AQ-R14-001` | `BLOCKED_USER_DECISION` | 保持 Codex stable identity source/domain 未登记、正式 fetch/cache/LKG incompatible、Gate 0A fail closed；未读取真实账户，也未替用户选择产品方向。 | 用户必须选择并确认可验证的稳定 identity evidence/source/domain；随后另行更新绑定、迁移、多账户隔离向量并接受新审计。 |
| `AQ-R14-002` | `FIXED` | core artifact 新增以 `kind` 判别的四分支 ProbeResult 合同；仅 official-cli success 恰有一份短命官方 evidence，其余分支禁止 evidence，全部分支禁止额外字段和 Adapter 派生身份字段。operation 在 `probe` 后立即执行 `probe_result_validate`，且 official 路径在 `identity_derive` 前完成 context/binding/lifetime 校验。schema 与 11 个 strict fixture 覆盖正常、unknown、cross-profile、expired、extra-field 和错误 evidence 分支。 | 这是设计合同证据；未来实现必须从 artifact 生成同一 DTO/schema，不能复制一套手写联合。 |
| `AQ-R14-003` | `FIXED` | retention lexer 升级到版本化 phrase grammar v2，覆盖 ordinary/local/data/config/cache file、directory、keychain/keystore、数据库/WAL/journal 及登记中文同义词，并以有限 token distance 组合 write/sensitive-object 信号。三份 live 文档的 local-file mutation 均拒绝；同义 corpus 正向基线、38 个 malicious fixture、9 个合法 directive/owner join 和 38 个逐 leaf digest-bound 精确例外全部通过。 | 精确例外仍需后续独立审计确认足够窄；任一 leaf 字节变化都会使摘要失配并要求重新审查。 |
| `AQ-R14-004` | `FIXED` | release gate 强制显式 `--root`，要求 cwd/root/入口严格一致并在业务逻辑前拒绝入口非 regular file；root 与全部编译期输入使用逐 segment `O_NOFOLLOW` reader，冻结 root identity、完整输入集合与摘要。入口 symlink、root substitution、source symlink、并发替换四项机器 mutation 全部拒绝。 | 当前根身份依赖本机 POSIX inode/stat 语义；其他平台必须建立并审计等价的 fail-closed profile。 |
| `AQ-R14-005` | `FIXED` | runtime profile 除 npm launcher/version 外固定实际 npm package entry 与完整 regular-file tree 摘要；validator 在 `npm ci` 前复核 package root、每个路径/mode/bytes 与前后快照。同 launcher/version、修改 `lib/cli.js` 的实现树漂移 mutation 被拒绝。 | 当前只是 checkout 的 audit evidence；生产/0A 仍需外部签名工具链或 VCS/tool hash 与既有受信根授权。 |
| `AQ-R14-006` | `FIXED` | core artifact 独立登记 mutation case ID、sequence、expected verdict、mutation spec/digest、总数、结果字段闭包与 results digest recipe。runner 输出 canonical 逐 case JSON；gate exact compare 全集合、顺序、数量、digest、verdict 与结果摘要。缺 case、空 cases、伪 `status=ok`、重复 ID 四项 self-test 全部拒绝。 | 新增或修改 case 必须同步 artifact/schema/projection/hash；runner 不能自行扩缩发布证据。 |

## 机器合同与摘要

- registry anchor：`e24781e18140944cc31a84baa408f201639c83e6e8d536671195fab1e480725e`
- artifact pin projection：`ad336a27005d6a7585fa7a11431e43dd4c4be7b89e6f5130c640ea171a233dd4`
- schema：6 个 meta-schema、8 个 instance、106 个 array schema object
- semantic validator：13 个
- fixture：36 个 core、38 个 retention；live directive：9 个
- mutation：41 个；2 个正向基线通过，39 个负向项全部拒绝；结果摘要 `983b46d21e0e1c97980c38d5cce44842aa8181f92191dbfe1e6a61c4e50b6f65`
- 固定运行时证据：Node `v24.15.0`、npm `11.12.1`、Pandoc `3.9.0.2`、Ajv `8.17.1`

## 已执行验证

```text
python3 -m py_compile docs/contracts/validate-contracts-v1.py docs/contracts/canonicalize-registry-v1.py docs/contracts/run-release-gate-v1.py docs/contracts/run-validation-mutations-v1.py
node --check docs/contracts/validate-json-schema-v1.mjs
find docs/contracts -name '*.json' -type f -print0 | xargs -0 -n1 jq empty
python3 docs/contracts/validate-contracts-v1.py
python3 docs/contracts/canonicalize-registry-v1.py
python3 docs/contracts/run-validation-mutations-v1.py --root .
python3 docs/contracts/run-release-gate-v1.py --root .
```

validator 与 projection verifier 各做了两次确定性重放且输出完全一致。完整 gate 输出 `clean_install=verified`、`validation_replay_deterministic=true`、`projection_replay_deterministic=true`、`mutation_suite=exact-contract-match`、`release_authority=audit-evidence-only-not-a-release-authority`、`source_bytes_unchanged=true` 与最终 `status=ok`。gate 绑定 canonical root identity 摘要 `5a7ed8a03ccdcf9d04e1b2ca9bb4708aea3718c4eb051c3ddebecb70990c6ffc` 和 release input 摘要 `a0e5ef5664a15b03352202d6bbea0e1e7b677bfb1ad96e0ac28fbf76a4d8b559`。

## 历史完整性与后续门禁

- 第 1–14 轮 audit 与第 1–13 轮 resolution 的 SHA-256 已在修复前后逐文件比较；历史字节未变。
- 仓库仍为 `No commits yet on main`，全部文件未跟踪；本轮没有 staged change、commit、push 或破坏性 Git 操作。
- 本记录是本轮唯一新增 resolution。当前结果只证明第 14 轮五项工程缺口在本机当前 checkout 上闭合，不等于设计已零问题，也不构成实现、Provider 运行时或生产发布授权；必须交给新的独立 Agent 继续全量对抗性审计。
