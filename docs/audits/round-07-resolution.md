# 第 7 轮审计处置记录

> 处置日期：2026-07-18  
> 范围：仅修订 `README.md`、三份现行设计正文并新增本记录；历史审计与历史处置记录保持不变  
> 统计：fixed 13 / rejected 0 / blocked 1 / total 14  
> 门禁：仍不能宣告零问题或通过 0A；用户身份决策完成后仍须由新的独立 Agent 全量复审

## AQ-R7-001 — `BLOCKED_USER_DECISION`

- 成立判断：成立；现有握手与额度读取不能证明稳定 Codex subject。
- 处置：保持 Codex 在 MVP、保持当前 RPC allowlist，不加入身份读取 RPC，不代替用户选择两个互斥产品基线。
- 规范位置：`README.md:3,33,53`；`docs/design-proposal.md:1318,1322-1334`；`docs/provider-contract.md:175-198`；`docs/security-model.md:174-175`。
- 验证：正文仍明确 subject evidence source 未登记；扫描确认没有把身份读取 RPC加入 allowlist。

## AQ-R7-002 — `FIXED`

- 成立判断：成立；旧 wire schema 会拒绝官方合法 envelope，通知与 error map 也未冻结。
- 处置：冻结 `aq-codex-wire-v1`、exact argv/frames/opt-out/error map，并规定 `jsonrpc` 字段必须缺失。
- 规范位置：`docs/design-proposal.md:1288-1336`；`docs/provider-contract.md:175-179`；`docs/security-model.md:174`。
- 验证：本机 schema 只读核验和 fake-stdio golden 集覆盖 header present/absent、success/error、notification、server request及 ID 异常；未调用账户 RPC。

## AQ-R7-003 — `FIXED`

- 成立判断：成立；Source 直接返回含 core identity 的 Lease 形成所有权循环。
- 处置：Source 唯一返回 `CredentialResolution`，core 验 evidence、派生 identity 后才构造 `CredentialLease`；两个 DTO 各有 schema hash。
- 规范位置：`docs/design-proposal.md:779-797,979-985`；`docs/provider-contract.md:124-144`；`docs/security-model.md:168`。
- 验证：接口扫描不存在 Source 返回/refresh/invalidate Lease 的第二接口，恶意 identity/metadata/secret 在 Adapter 前拒绝。

## AQ-R7-004 — `FIXED`

- 成立判断：成立；旧 cohort 输入混入 principal/binding，复制配置会拆分预算。
- 处置：授权 binding、访问代际与上游 subject evidence 分离；唯一派生函数的 stable cohort 只使用 Provider identity domain/subject，无法证明时使用部署级保守 cohort。
- 规范位置：`docs/design-proposal.md:987-1017`；`docs/provider-contract.md:135-144`；`docs/security-model.md:175`。
- 验证：golden vectors要求相同稳定 subject 跨 principal/binding 同 cohort，不同 subject 不同 cohort，复制进程不扩容。

## AQ-R7-005 — `FIXED`

- 成立判断：成立；旧阶段顺序会在 endpoint/幂等判定前解析秘密，也无法构造部分 context。
- 处置：以唯一执行路径矩阵生成 authorize→config/manifest/endpoint→idempotency→credential/identity→context→probe/reserve/fetch；official-cli zero-binding 显式跳过 Source。
- 规范位置：`docs/design-proposal.md:328-355`；`docs/provider-contract.md:150-157`；`docs/security-model.md:187`。
- 验证：全 operation/mode golden trace要求非法 endpoint与幂等 replay的 Source 调用数为零，并构造 doctor/discover/refresh context。

## AQ-R7-006 — `FIXED`

- 成立判断：成立；旧 floor 查询不计 active reserved，两个进程可同时放行。
- 处置：增加 reservation 到期字段、floor partial unique、reserved floor/hour blocker、owner/fence cancel与 crash takeover规则；committed/unknown 不因 lease 释放。
- 规范位置：`docs/design-proposal.md:1396-1407`；`docs/provider-contract.md:369-377`；`docs/security-model.md:181`。
- 验证：双进程虚拟时钟覆盖同 key 并发、冲突、取消、queue timeout、owner crash、接管与边界相等。

## AQ-R7-007 — `FIXED`

- 成立判断：成立；旧正文存在两种互斥 binding key ID 算法。
- 处置：所有初始化、启动、恢复和读取只调用一个 domain-separated lowercase-hex `binding_key_id_v1`，并 constant-time 比较。
- 规范位置：`docs/design-proposal.md:1491-1505`；`docs/security-model.md:259`。
- 验证：扫描不存在无 domain 的替代 recipe；固定向量要求两实现同值且逐 bit/编码/domain 篡改拒绝。

## AQ-R7-008 — `FIXED`

- 成立判断：成立；旧 installer 没有预安装 trust root，目录内 bundle 可形成循环自信任。
- 处置：独立 installer wheel 内嵌 genesis anchor，bootstrap 独立 pin installer，完整连续 bundle chain 从 anchor或已安装 floor验证，新 root不能自授权。
- 规范位置：`docs/design-proposal.md:1231-1249`；`docs/provider-contract.md:187`；`docs/security-model.md:179`。
- 验证：新装/升级/修复 vectors覆盖同目录全替换、缺中间 bundle、回滚、自签 genesis、root 替换和最大链长。

## AQ-R7-009 — `FIXED`

- 成立判断：成立；旧 control/lock/files 规则不能构造唯一合法目录。
- 处置：生产目录固定 5 个 control files，目标集合恰为 signed plan files；不接收第三方 lock，验证后只在 staging 生成 lock，source-review 使用隔离目录。
- 规范位置：`docs/design-proposal.md:1251-1282`；`docs/provider-contract.md:187`；`docs/security-model.md:179`。
- 验证：两 installer 对 control/target增删替换得到同一 verdict，生产目录出现 sdist/source-review lock 必拒绝。

## AQ-R7-010 — `FIXED`

- 成立判断：成立；旧 release attestation 没有可互操作的 exact payload。
- 处置：冻结 `aq-release-attestation-envelope-v1` 全字段、类型、签名字节、排序、阈值、key purpose/distribution binding与 replay规则。
- 规范位置：`docs/design-proposal.md:1194-1228`；`docs/provider-contract.md:187`；`docs/security-model.md:179`。
- 验证：双实现 golden payload及逐字段删除/改名/重排/跨包版本文件名重放均有唯一结果。

## AQ-R7-011 — `FIXED`

- 成立判断：成立；旧 destructive planner 与 journal 对 new config 的绑定不同。
- 处置：所有 dry-run/confirm/delete/purge/drift/metadata/journal只调用同一个 domain-separated `aq-migration-plan-envelope-v1` 与 digest。
- 规范位置：`docs/design-proposal.md:1457-1487,1657-1667`；`docs/provider-contract.md:93-95`。
- 验证：任一 old/new config、manifest、action字段或 cascade关系变化都改变 digest，恢复只重放原 envelope。

## AQ-R7-012 — `FIXED`

- 成立判断：成立；旧表外错误可能递归生成另一非法错误，design/provider 组合也不一致。
- 处置：入口表外对象使用零副作用 `OperationContractFailure`，内部表外转移使用固定不可序列化 fatal；Provider 摘要从唯一错误行表生成。
- 规范位置：`docs/design-proposal.md:267-308,351-412`；`docs/provider-contract.md:351`；`docs/security-model.md:187`。
- 验证：全笛卡尔 fixture 为每个表内/表外输入给出唯一终局，生成的 design/provider 单元行逐格相等。

## AQ-R7-013 — `FIXED`

- 成立判断：成立；旧 bounds 未覆盖未签名 plan/bundle/envelope 与数组资源。
- 处置：为 envelope/plan/bundle/chain/migration bytes、files/signatures/keys/revocations/bindings、JSON深度/节点/字符串和 action数量增加 hard bounds，并冻结先 bound 后 parse/JCS/crypto/hash/pip顺序。
- 规范位置：`docs/design-proposal.md:1096-1127`；`docs/provider-contract.md:187,231`；`docs/security-model.md:172,179`。
- 验证：min-1/min/max/max+1、巨大数组/深度/字符串与 checked overflow均在解包、批量 hash、crypto 和 pip前拒绝。

## AQ-R7-014 — `FIXED`

- 成立判断：成立；same-plan metadata和journal前临时文件缺生命周期，旧 lint不能确定性发现漏登记或伪装 literal。
- 处置：observed metadata与temp claim/file进入 data inventory/RET；temp先 claim后创建，orphan只在lease到期、更大fence和no-follow属性/digest全匹配时清理；lint冻结文件、AST、heading、allowlist、单位归一和变更声明语法。
- 规范位置：`docs/design-proposal.md:1038,1657-1667`；`docs/security-model.md:220-241`；`docs/provider-contract.md:357`。
- 验证：虚拟时钟/逐点 kill覆盖same-plan、对象生命周期、journal前崩溃与claim异常；lint正例通过，复制duration、漏surface、伪装单位 fixtures失败。

## 最终核验口径

- 四份现行文档与本记录必须通过 Markdown fence/local-link、禁用占位词、敏感信息与旧矛盾合同扫描。
- 历史审计和前六轮处置文件的 SHA-256 必须与修订前完全一致。
- 工作树不得有 staged change、commit或分支切换；本轮仍只有设计文档，没有应用代码或真实账户数据。
