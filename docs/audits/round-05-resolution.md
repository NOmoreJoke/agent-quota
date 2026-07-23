# 第 5 轮审计处置记录

> 处置结论：`FIXED_15_BLOCKED_1_REJECTED_0`  
> 处置日期：2026-07-18  
> 修订版本：设计 v1.1 / Provider v1.0 / 安全模型 v0.9  
> 范围：只修订现行正文与 README；未修改第 1～5 轮审计报告或第 1～4 轮处置记录，未提交 Git

## 处置原则

- 逐项从现行正文核验反例；15 项成立并修复，0 项驳回。
- Codex 身份项确需用户在互斥产品基线中选择，标记为 `BLOCKED_USER_DECISION`；未代选、未降低严重度、未移出 MVP、未扩大 RPC allowlist。
- 正文只保留现行规范；本文件记录问题、结论、修改位置和静态验证。

## 逐项处置

### AQ-R5-001 — `BLOCKED_USER_DECISION`

- 核验：成立。当前握手与 `account/rateLimits/read` 仍不能提供稳定账户身份；允许 `account/read` 或替换第二个 MVP Adapter 是产品基线选择。
- 处理：未代替用户选择。Codex 仍是 1B/MVP Supported 候选，业务 allowlist 仍只有 `account/rateLimits/read`，schema descriptor 仍只有该业务 RPC 与握手；文档明确未决期间不得加入 `account/read`。
- 位置：`docs/design-proposal.md:946-962,1497-1501,1591,1604`；`docs/provider-contract.md:175-180,194-201`；`docs/security-model.md:171-176`。
- 验证：MVP/严重度/allowlist 未降级；本项不计 fixed，也不伪造零问题结论。

### AQ-R5-002 — `FIXED`

- 核验：成立。stable schema 允许多 bucket，旧唯一 key 合同会拒绝当前合法响应。
- 处理：允许 absent/null/空或 1..16 bucket；逐项限制深度/节点/key/type并要求 key 与 child limitId 一致、恰一 bucket 与顶层 canonical 相等。MVP 只消费顶层三项能力，其他 bucket 验证后丢弃且不进入任何 ID/输出/持久化。
- 位置：`docs/design-proposal.md:977-999`；`docs/provider-contract.md:175-180,263-267`；`docs/security-model.md:171`。
- 验证：规范覆盖合法 2 bucket、零/多匹配、key 不一致、17 bucket、超深/错型和动态 key 脱敏。

### AQ-R5-003 — `FIXED`

- 核验：成立。旧 discovery 输入依赖正式 SubjectId，返回又不能同批表达 capability/missing。
- 处理：引入独立 `DiscoverySeedSelector/DiscoveryRequest/DiscoveryResult`；seed 只含 profile/kind/schema/有限候选，0 subject 用空 seeds；ProbeResult 移除业务发现字段，未确认结果不落盘。
- 位置：`docs/design-proposal.md:694-747,829-847`；`docs/provider-contract.md:88,155-159,194-201`；`docs/security-model.md:167,179`。
- 验证：规则拒绝跨批 handle、越 scope seed、悬空 capability/missing、正式 ID 和 probe/discovery 混用。

### AQ-R5-004 — `FIXED`

- 核验：成立。core 与 Provider 文档曾定义不同 lease 字段。
- 处理：设计方案成为唯一 `CredentialLease` DTO，冻结 profile/purpose/source kind、Secret transport fields、到期与 identity 绑定；SDK 直接导入同一模型并比较 canonical schema hash，Provider 文档不再重复类定义。
- 位置：`docs/design-proposal.md:653-668,827-829`；`docs/provider-contract.md:127-140`。
- 验证：缺字段、未知 metadata、普通字符串秘密、过期和 principal/profile 错配均在 Adapter 前拒绝；repr/serializer 无秘密值。

### AQ-R5-005 — `FIXED`

- 核验：成立。旧 NetworkPolicy 的平行 method/path/RPC 元组不能驱动通用 endpoint builder。
- 处理：增加判别式 HTTP/local endpoint、path/query/auth/response/frame/deadline spec；handle 必须唯一命中 endpoint。DeepSeek 固定 `GET /user/balance`，Codex 三个 RPC 各自原子绑定。
- 位置：`docs/design-proposal.md:508-603,819-825`；`docs/provider-contract.md:216-252`；`docs/security-model.md:169-171`。
- 验证：规范在凭据前拒绝未知 endpoint、method/path 错配、重复/未知 query、分隔符注入和最终发送对象变化。

### AQ-R5-006 — `FIXED`

- 核验：成立。普通 pip 无法执行文档承诺的 Provider 解包前自定义验证。
- 处理：生产路径固定为 hash-pinned `agent-quota-installer`：stage/download、不导入 → 验证 wheel/sidecar/bundle/依赖 plan → hashed binary-only pip → 安装后重验。sdist 明确只属隔离源码审阅并会执行受信 build backend。
- 位置：`docs/design-proposal.md:933-944,1082-1095`；`docs/security-model.md:176`；`README.md:30-49`。
- 验证：给出两条可执行 bootstrap 命令；生产 staging 禁止 sdist，缺 sidecar、依赖替换和未知文件在目标代码执行前拒绝。

### AQ-R5-007 — `FIXED`

- 核验：成立。旧文本未冻结签名字节、算法、key ID、envelope 和 bundle threshold。
- 处理：冻结 `aq-jcs-nfc-v1`、Ed25519、SHA-256/key ID、RFC3339 UTC 边界、base64url、sidecar/bundle 文件名与 schema、domain-separated signed bytes、normalized wheel content、前一 bundle threshold 和 sequence/revocation。
- 位置：`docs/design-proposal.md:925-931`；`docs/security-model.md:176`。
- 验证：规范要求独立实现 golden bytes 互验，并区分字段重排等价与语义 bit/Unicode/时间/重放变更失败。

### AQ-R5-008 — `FIXED`

- 核验：成立。本地 scope 拒绝曾同时存在于 OperationError 和 capability snapshot。
- 处理：从 Health/LocalStatusCode/状态矩阵移除本地授权快照；本地拒绝唯一为 authorize-stage OperationError，零缓存/Provider/ledger。已授权请求的上游 entitlement 缺失独立为 `unsupported+not_entitled`。
- 位置：`docs/design-proposal.md:162-175,286-305`；`docs/provider-contract.md:328,350-364`；`docs/security-model.md:119-123,174,183`。
- 验证：P/S/view/空 scope 只产生相同错误；上游缺 entitlement 不使用本地授权枚举。

### AQ-R5-009 — `FIXED`

- 核验：成立。Adapter 在禁止读 cache 时无法自行构造带 LKG 的 failure snapshot。
- 处理：Adapter 返回封闭 success/unavailable/failure observation 或 batch failure；core 验证完整 key 集后原子读取当前 generation LKG并唯一合成 fresh/stale/expired snapshot，一次事务提交。
- 位置：`docs/design-proposal.md:774-817,835-850,1013`；`docs/provider-contract.md:205-212,267,309-310`；`docs/security-model.md:174`。
- 验证：规范覆盖有/无 LKG、batch transport/逐 capability failure、半批越界、跨 generation 和提交崩溃零部分写入。

### AQ-R5-010 — `FIXED`

- 核验：成立。旧 TTL 区间与永久 Provider status 不可确定。
- 处理：新增精确 FreshnessPolicy；Codex 三项为 180 秒、DeepSeek 两项为 600 秒，全部 Provider observation 必须到期。只有 core offline manifest-static 且 policy 允许的结构状态可永久；policy digest 参与 generation。
- 位置：`docs/design-proposal.md:394-399,1001-1013`；`docs/provider-contract.md:370-372`；`docs/security-model.md:174`。
- 验证：同 manifest 产生唯一 expires_at，available/reached/not_entitled 到期，TTL 改动清旧 generation/LKG。

### AQ-R5-011 — `FIXED`

- 核验：成立。旧 allowlist 示例未按自己的 UTF-8 排序规则编码。
- 处理：descriptor 固定为 `account/rateLimits/read, initialize, initialized`；allowlist 定义为去重 set 后排序，不是调用顺序。
- 位置：`docs/design-proposal.md:946-962`。
- 验证：源集合打乱不改变 hash，增删 RPC 必须改变 hash；未加入身份未决的 RPC。

### AQ-R5-012 — `FIXED`

- 核验：成立。actor 请求权限和内部执行阶段被同一个开放字符串混用。
- 处理：冻结 `RequestedOperation` 与 `ExecutionStage` 两个联合、逐请求唯一阶段映射和禁止升级规则；AccessContext 只接收前者，错误保留 requested operation 与 failed stage。
- 位置：`docs/design-proposal.md:253-318,1284-1295`；`docs/provider-contract.md:350-364`；`docs/security-model.md:101-123`。
- 验证：status/refresh/discover/migrate/delete/purge 各有唯一阶段集合，未知字符串在 cache 前拒绝。

### AQ-R5-013 — `FIXED`

- 核验：成立。唯一 retention 表遗漏 alert episode/delivery 与 LLM consent/tombstone。
- 处理：新增 active/terminal alert 与 active/tombstone consent 四个唯一条目，冻结起算点、terminalization、30 天保护、对象 inactive/purge 和 verify-only key 依赖。
- 位置：`docs/security-model.md:198-220`；`docs/design-proposal.md:1395`。
- 验证：虚拟时钟验收覆盖 open/ack/resolved、投递崩溃、consent 到期/撤销/重建、对象删除、key 轮换和边界清理。

### AQ-R5-014 — `FIXED`

- 核验：成立。local-stdio attempt 同时写成 6 秒和 8 秒。
- 处理：唯一 TransportDeadlinePolicy：HTTP queue/attempt/aggregate=1/6/9；local=1/8/9，内部 handshake/request/execution/grace=3/6/7.5/0.5。每次 fresh process，阶段用剩余预算，回收计入 attempt。
- 位置：`docs/design-proposal.md:555-567,819-825,1531-1535`；`docs/provider-contract.md:218-238`；`docs/security-model.md:171`。
- 验证：冻结 3+4 成功、3+6 截断、恰好边界、排队和 TERM→KILL→reap/orphan=0。

### AQ-R5-015 — `FIXED`

- 核验：成立。undocumented breakage protocol 未进入 manifest 引用闭包。
- 处理：增加 StructurePath/MapRule/StructureContract/BreakagePolicy；undocumented profile 必须恰一引用，其他 profile 为 null；静态 path ID/type、map 归一化、基数/深度、fingerprint、失败类别和恢复 policy 均机器可读。
- 位置：`docs/design-proposal.md:471-506,854-883`；`docs/provider-contract.md:184,271-287`；`docs/security-model.md:175`。
- 验证：offline 通用 loader 可拒绝缺失/悬空/重复/未使用合同；动态 key、结构漂移与语义漂移各有唯一表面。

### AQ-R5-016 — `FIXED`

- 核验：成立。registry/keyring 的 MAC、AEAD、canonical bytes、nonce/AAD、sequence 和原子替换不足以互操作。
- 处理：冻结 JCS registry HMAC envelope、HKDF 分用途 key、AES-256-GCM keyring envelope、salt/nonce/AAD、payload 字段、sequence/generation/nonce/DB floors 与 journal/fence 两文件 roll-forward；明确纯软件整套旧备份回滚边界。
- 位置：`docs/design-proposal.md:1058-1080`；`docs/security-model.md:236`。
- 验证：规范要求独立实现互读，并覆盖 bit/截断/nonce 复用/交换/旧 generation/错误 binding key/双 rename 崩溃且诊断无 secret。

## 统计与后续门禁

- Fixed：15
- Rejected：0
- Blocked：1
- 唯一阻塞：Codex 稳定身份产品基线，必须由用户选择；当前文档不能宣告零问题收敛。
- 下一步：用户决策后由全新的修复 Agent 落实身份合同，再由另一个全新的独立审计 Agent 从零全量复审；不得只复查本轮清单。

## 静态验证摘要

- 现行正文的约定占位标记扫描结果为 0。
- README/正文/本处置记录的本地 Markdown 链接目标均存在，代码围栏平衡。
- 第 1～4 轮 audit/resolution SHA-256 与修复前一致；第 5 轮 audit 未修改。
- 旧规则扫描未发现 DiscoveryContext、重复 CredentialLease、单 bucket 强拒绝、授权快照、TTL 区间、local 6/8 秒双定义或平行 NetworkPolicy 元组残留。
- 文档未写入真实邮箱、计划、额度、重置时间、bucket 名称、Token、Cookie 或账户响应；仅保留审计报告已有的非敏感版本/schema digest 证据。
