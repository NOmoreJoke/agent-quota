# 第 8 轮审计处置记录

> 处置版本：v1.4；处置统计：`FIXED=10`、`REJECTED=0`、`BLOCKED_USER_DECISION=1`、`TOTAL=11`。本记录不改写第 8 轮审计事实，也不宣告零问题；用户完成唯一产品决策后，仍须由全新的独立 Agent 做全量复审。

## 逐项处置

### AQ-R8-001

- 状态：`BLOCKED_USER_DECISION`
- 判定：成立；严重度保持 Blocker。当前 Codex allowlist 与官方 rate-limit schema 仍不能提供合同要求的稳定主体证据，这是产品基线选择，不是实现者可自行补齐的字段。
- 变更：没有加入 `account/read`，没有移除或降级删除 Codex，也没有把进程、principal、binding 或 rate-limit payload 伪装成稳定主体。现行 manifest 明确不登记 Codex verified-stable identity source/domain，正式 fetch 继续 fail closed。
- 最终证据：`README.md:3,58`；`docs/design-proposal.md:1070,1114,1137,1413,1425`；`docs/provider-contract.md:162,191`；`docs/security-model.md:178`。
- 验证：在用户选择“扩展额外只读稳定身份来源”或“保留最小 allowlist 并替换第二个 MVP Adapter”前，阶段 0A 和 Codex Supported/fetch fixture必须保持阻断；本轮不代选。

### AQ-R8-002

- 状态：`FIXED`
- 判定：成立；原 manifest 缺少身份来源、身份域和 endpoint budget-group 的可闭包注册表。
- 变更：增加封闭 `IdentitySourceContract`、`ProviderIdentityDomain`、`EndpointBudgetGroup` 与 `EndpointBudgetBinding`；冻结 source kind、binding、evidence field、stability basis、generation、domain 与 endpoint 双向完整分区，并拒绝重复、悬空、未使用和多映射。DeepSeek 与 Codex 的现行登记边界被明确区分。
- 最终证据：`docs/design-proposal.md:736-799,1066-1070,1133-1137`；`docs/provider-contract.md:189-191`；`docs/security-model.md:178`。
- 验证：manifest 闭包规则要求每个 Provider-I/O endpoint 恰有一个 group，source/domain/profile 引用必须双向命中；Codex 未决 source 仍为空而非伪造条目。

### AQ-R8-003

- 状态：`FIXED`
- 判定：成立；原 doctor/discover/refresh 路径允许业务 I/O 先于 rate reservation。
- 变更：把 I/O class、request kind、predicate 和 exact step path 移入唯一 operation artifact；每个 `provider_io` step 必须先消费同 path、同 request kind 的已提交 reservation。身份未知时先记部署级 conservative cohort，验证后原子归并且保留原 debit；`identity_and_fetch` 只复用同一已预留 response，不发第二次等价请求。
- 最终证据：`docs/contracts/operation-contract-v1.json:5-15,52-143,270-281`；`docs/design-proposal.md:330-351,841-843,1066-1070`；`docs/provider-contract.md:160-162`；`docs/security-model.md:180-187`。
- 验证：artifact 闭包断言 `provider_io_requires_earlier_matching_unconsumed_reservation=true` 和 `one_provider_attempt_one_reservation=true`；所有 machine path 的 outbound step 均有更早的 matching reserve。

### AQ-R8-004

- 状态：`FIXED`
- 判定：成立；原 action envelope 不能规范引用新对象，也没有编号前的 cascade graph 排序规则。
- 变更：把 object ref 改成 existing/new 判别联合，新对象携带预生成 opaque ID 与域分离 canonical handle；由 semantic body 生成稳定 semantic key，完整 graph 进入 digest，使用以 key bytes 为最小堆 tie-break 的 Kahn 拓扑排序后才赋 action ID，并拒绝重复、自环、悬空、多父与 cycle。
- 最终证据：`docs/design-proposal.md:1550-1607`；`docs/security-model.md:261`。
- 验证：同一 graph 的输入遍历顺序不影响 bytes、digest 或 action order；create/update/cascade 和异常图都具有唯一结果或固定拒绝。

### AQ-R8-005

- 状态：`FIXED`
- 判定：成立；原 pre-journal claim 在创建文件后、属性回写前崩溃会留下无法安全收敛的状态。
- 变更：冻结 `name_claimed → file_opened → file_sealed → attached` 与 takeover-only `cleanup_claimed` 状态和字段不变量；首个 write 必须晚于 no-follow inode 的 `file_opened` 事务。恢复按 state、parent fd、inode、owner、mode、nlink、length/hash 逐层验证，旧 fence、symlink、替换 inode 与 hardlink 均不能推进或删除。
- 最终证据：`docs/design-proposal.md:1784-1803`；`docs/security-model.md:263`；`docs/contracts/lease-policy-v1.json:81-90`。
- 验证：create/fstat/claim update/write/fchmod/fsync/parent fsync/seal 前后均落在可判别 state；orphan 只删除已证明属于本 migration 的 inode，gate 可安全收敛。

### AQ-R8-006

- 状态：`FIXED`
- 判定：成立；原 LocalKey purpose 集缺少 cache identity 与 rate ledger，root 到 purpose/generation 的 HKDF 也未冻结。
- 变更：新增唯一机器 purpose registry，登记八个 consumer purpose（含 `cache-identity-v1` 与 `rate-ledger-v1`）、32-byte root/derived length、exact SHA-256 HKDF salt/info/编码、generation 与 replace/verify 生命周期；未知、重复、跨 purpose 复用和 root 直接使用均拒绝。
- 最终证据：`docs/contracts/local-key-purpose-registry-v1.json:1-74`；`docs/design-proposal.md:1614-1641`；`docs/provider-contract.md:150`；`docs/security-model.md:269`。
- 验证：JSON 唯一性/引用闭包通过；登记摘要 `a48a6a5afc1ed280d3730f3653da03bb4c3d5fec3598b0e0c9d37c1b238c11a6` 与正文一致。

### AQ-R8-007

- 状态：`FIXED`
- 判定：成立；原 Markdown 矩阵和自然语言错误集合不能生成唯一闭包，未知 operation 也无法构造封闭 RequestedOperation。
- 变更：新增唯一 `operation-contract-v1` JSON，逐行冻结 operation、mode、stage、predicate、I/O class、request kind、path、error 主键、retryable 与 safe-param schema；Markdown 只作生成投影。入口失败允许 `recognized_operation=null`，只保存最多 256 bytes 输入的域分离 digest且不回显原文。
- 最终证据：`docs/contracts/operation-contract-v1.json:1-282`；`docs/design-proposal.md:260-353,405-428`；`docs/provider-contract.md:359`；`docs/security-model.md:193`。
- 验证：path/error/safe-param 主键与引用闭包通过；未知 enum/字段、悬空或未使用 predicate拒绝；登记摘要 `f6473f26f12b1452fa5430c4667ca43a00d43f620885bc423637bec64122cb23` 与正文一致。

### AQ-R8-008

- 状态：`FIXED`
- 判定：成立；原单一 refresh disposition 无法表达多请求部分成功、失败、合并、LKG 和重放。
- 变更：定义 1..32 个 canonical `RefreshRequestResult` 组成的 `RefreshBatchResult`，每个完整 request digest/key 集恰有一项；封闭 disposition 联合覆盖 provider fresh、singleflight、LKG/stale、deferred、timeout、capacity、failure 和 unknown。tuple形成后即使全部失败仍返回完整 batch success；幂等层原子保存完整 canonical envelope。
- 最终证据：`docs/design-proposal.md:355-403,1514`；`docs/provider-contract.md:369`；`docs/security-model.md:181`。
- 验证：结果按 request digest bytes 排序，输入 key 无漏项、重复或额外项；并发完成顺序不影响序列化，重放逐字节返回同一 envelope。

### AQ-R8-009

- 状态：`FIXED`
- 判定：成立；原 writer/reservation/queue/slot/migration/temp-claim 时长、续租和接管公式没有唯一数值源。
- 变更：新增唯一 `lease-policy-v1` JSON，分别冻结 DB UTC 与进程 monotonic 用途、边界语义、duration、renew-before、max lifetime、reservation expiry、takeover 与 parent/transport deadline 公式；正文和 Adapter 只能引用 policy ID。
- 最终证据：`docs/contracts/lease-policy-v1.json:1-102`；`docs/design-proposal.md:1491,1784`；`docs/provider-contract.md:380`；`docs/security-model.md:187`。
- 验证：policy ID/class 唯一，`renew_before < duration`，各持久/执行 lease 有明确时钟和 `now == expiry` 规则；登记摘要 `3664e6edd314e9f82cbdd0c1b8f313fd61bcd51e5c78e8aa7d2c9f6e23a49cef` 与正文一致。

### AQ-R8-010

- 状态：`FIXED`
- 判定：成立；原 lint 在 allowlist 外复制自己的恶意 duration，且使用 CommonMark 未定义 slug。
- 变更：新增唯一 `retention-lint-v1` JSON，固定四个 live input，以 exact file + CommonMark AST heading level/sibling ordinal path + table/paragraph/column ordinal 定位 owner；恶意字符串仅存于被明确排除的 JSON fixture，规范正文只引用 fixture ID。配置同时冻结 inventory owner 与缺 surface fixture。
- 最终证据：`docs/contracts/retention-lint-v1.json:1-85`；`docs/contracts/fixtures/retention-lint-malicious-v1.json:1-17`；`docs/security-model.md:241-243`。
- 验证：live inputs 与 excluded fixture 不相交；allowlist owner唯一；恶意 fixture与缺失 surface fixture均要求 reject。配置摘要 `2adf6e1280845b8eff80e20f1ca8ee923f78bb7989ac895a0a0ac6bdc8d3e6ef`、fixture摘要 `abcd5c5ab6b93b33dbf561accb1d0cadbefaa6b3693aa31a3232395bd74fd82a` 已核对。

### AQ-R8-011

- 状态：`FIXED`
- 判定：成立；永久 nonce digest set 会无界增长并最终触发 envelope bounds。
- 变更：删除历史 nonce set，按 AEAD generation 派生独立 aead/nonce key，以严格单调 envelope sequence 的域分离 HMAC 前 12 bytes构造 nonce；journal 原子预留 generation/sequence 并持久化 floor，允许跳号、不允许回退或复用，达到 sequence 边界前先轮换 generation。
- 最终证据：`docs/design-proposal.md:1618-1639`；`docs/security-model.md:269`。
- 验证：同一 generation 下 sequence 唯一决定 nonce，跨 generation key 独立；registry大小不随写次数增长，rollback/交换/mismatch 固定关闭 gate。

## 机器契约摘要

统一算法为 `SHA256(b"agent-quota:contract-artifact:v1\x00" + aq-jcs-nfc-v1(document))`：

| artifact | SHA-256 |
| --- | --- |
| `operation-contract-v1.json` | `f6473f26f12b1452fa5430c4667ca43a00d43f620885bc423637bec64122cb23` |
| `local-key-purpose-registry-v1.json` | `a48a6a5afc1ed280d3730f3653da03bb4c3d5fec3598b0e0c9d37c1b238c11a6` |
| `lease-policy-v1.json` | `3664e6edd314e9f82cbdd0c1b8f313fd61bcd51e5c78e8aa7d2c9f6e23a49cef` |
| `retention-lint-v1.json` | `2adf6e1280845b8eff80e20f1ca8ee923f78bb7989ac895a0a0ac6bdc8d3e6ef` |

## 验证结果

- 11 个问题号在本记录各出现一次；状态统计与总数一致。
- 所有新增 JSON 可由 `jq -e` 严格解析，唯一主键、引用闭包、时序约束和摘要核对通过。
- 四份 live 文档的本地 Markdown 链接均存在，代码围栏成对闭合。
- live spec 与新增 contracts 中没有未决标记；旧 operation 自然语言集合、旧 claim 单态和永久 nonce set 均未继续作为有效合同。
- round 01..08 audit 与 round 01..07 resolution 的 SHA-256 均与修订前记录一致。
- 未发现疑似真实 Token、Cookie、Authorization header、邮箱或账户响应；没有执行真实 Provider 调用。
- 工作区没有暂存、提交、切换分支或修改模型配置。

最终结论：10 项确定缺陷已修订，0 项驳回，1 项保持产品决策阻断。当前仍不能宣告零问题或通过阶段 0A；产品决策完成后必须重新做全新独立全量审计。
