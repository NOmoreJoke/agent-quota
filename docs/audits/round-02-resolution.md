# 第 2 轮审计处置记录

> 处置对象：`README.md`、`docs/design-proposal.md`、`docs/provider-contract.md`、`docs/security-model.md`  
> 修复角色：第 2 轮全新独立修复 Agent  
> 处置日期：2026-07-18  
> 文档版本：设计 v0.8、Provider v0.7、安全 v0.6  
> 处置结论：13 项已修复，0 项拒绝，1 项需要用户决策；修订后仍需全新的独立 Agent 全量复审

## 逐项处置

### AQ-R2-001

- 核验结论：成立，`BLOCKED_USER_DECISION`。未修改 Codex Supported 目标、发送端 allowlist 或“至少两个真实 Supported Adapter”的 MVP 口径。
- 当前证据：本机 `codex-cli 0.142.5`；连续三次生成 v2 schema 后用排序键、紧凑 JSON 规范化，SHA-256 均为 `427a16fdf33e339d5689d738a9e45e9cc4058567ebf16e1e50b2a3a953a646e9`。`initialize` 只有 `codexHome/platformFamily/platformOs/userAgent`；`account/rateLimits/read` 响应只有额度与重置积分结构；二者都没有账户 ID、会话 ID 或登录代际。`account/read` 是独立 RPC，ChatGPT 分支可返回 nullable email 与 planType，但当前发送端明确禁止该方法。原始生成文件的键顺序跨运行不稳定，因此正文已要求 canonical JSON hash，而不把原始字节 hash 当协议身份。
- 当前规范位置：`docs/design-proposal.md:420`、`docs/design-proposal.md:875`、`docs/design-proposal.md:959-967`、`docs/design-proposal.md:1003-1004`；`docs/provider-contract.md:150-155`、`docs/provider-contract.md:171-174`、`docs/provider-contract.md:184-193`、`docs/provider-contract.md:278-280`。
- 互斥选项 A：允许只读 `account/read(refreshToken=false)`，原始 email/account 字段只在内存中进入带域分离的 keyed PRF 后立即丢弃；缺 email 时 fail closed。身份契约改为稳定账户身份：A→B 必须改变 cache/cohort，旧缓存不可见；同一账户重新登录不再承诺产生新代际，继续受 TTL 与协议 generation 隔离。影响是扩大本地 RPC 与 PII 处理 TCB，必须新增原文不进入配置/SQLite/WAL/日志/异常/投影的测试。
- 互斥选项 B：保持现有 allowlist，把 Codex 降为 Experimental，并由用户明确指定另一个有稳定身份、固定出口和真实 opt-in 证据的第二个 MVP Adapter。影响是阶段 1B/2、README、安装 extra 和“两个 Supported”验收需要同步改名；`planned/no-contract` Provider 不能未经证据直接顶替。
- 阻塞原因：当前证据没有既保持 allowlist、又能区分账户切换的第三条安全路径；两项选择都会改变产品/隐私基线，修复 Agent 无权代选。

### AQ-R2-002

- 核验结论：成立，已修复。
- 修改位置：`README.md:29`；`docs/design-proposal.md:468-479`、`docs/design-proposal.md:557-568`、`docs/design-proposal.md:906-922`、`docs/design-proposal.md:949-954`、`docs/design-proposal.md:998`；`docs/provider-contract.md:178-180`、`docs/provider-contract.md:277`、`docs/provider-contract.md:443-448`；`docs/security-model.md:280-290`、`docs/security-model.md:315-318`。
- 修复与验证：定义独立 `agent-quota-testkit` wheel/sdist；FakeAdapter 只存在于 testkit。生产 meta/extra 不依赖 testkit，干净生产环境检查依赖闭包、文件和用户 entry point，另一个干净环境显式安装 testkit 运行 Fake 组合矩阵。

### AQ-R2-003

- 核验结论：成立，已修复。
- 修改位置：`docs/design-proposal.md:373-419`、`docs/design-proposal.md:422-429`；`docs/provider-contract.md:85-87`、`docs/provider-contract.md:184-206`、`docs/provider-contract.md:414-420`；`docs/security-model.md:176-179`、`docs/security-model.md:284-292`。
- 修复与验证：接口改为调用级 `DiscoveredSubject/DiscoveredCapability` DTO，正式 ID 只能由确认事务生成；`offline/local_only/network_allowed` 冻结了凭据、子进程和联网边界。离线验证三类调用计数均为 0，正式 ID、越权 selector、控制字符 label 或未获网络许可的返回整批拒绝且配置不变。

### AQ-R2-004

- 核验结论：成立，已修复。
- 修改位置：`README.md:39`；`docs/design-proposal.md:506-507`、`docs/design-proposal.md:550-552`、`docs/design-proposal.md:685-702`、`docs/design-proposal.md:999`；`docs/provider-contract.md:93-94`、`docs/provider-contract.md:390`、`docs/provider-contract.md:417`；`docs/security-model.md:195-202`、`docs/security-model.md:295-297`。
- 修复与验证：TOML 明确为权威配置；SQLite journal 记录 old/new digest、新配置恢复字节、plan/generation digest 和封闭阶段。`prepared` 后固定 roll-forward，rename/fsync 与 DB 事务由启动恢复协调。逐点 kill 覆盖文件、journal、rename、目录 fsync、DB、checkpoint；第三个 digest fail closed，连续重启幂等收敛。

### AQ-R2-005

- 核验结论：成立，已修复。
- 修改位置：`docs/design-proposal.md:846-855`、`docs/design-proposal.md:1000`；`docs/provider-contract.md:430`；`docs/security-model.md:309`。
- 修复与验证：维度键与 episode 分离，episode ID 单调；resolved 为终态，再次恶化原子创建下一 episode。恢复由最终 severity=`none` 驱动，`fresh+unsupported` 可关闭旧 health 告警；disable/delete/generation 切换终止旧 episode 且不伪报额度恢复。虚拟时钟覆盖两次完整恶化/恢复和双宿主接管。

### AQ-R2-006

- 核验结论：成立，已修复。
- 修改位置：`docs/design-proposal.md:157-163`、`docs/design-proposal.md:485-495`、`docs/design-proposal.md:623`、`docs/design-proposal.md:673`、`docs/design-proposal.md:836-838`、`docs/design-proposal.md:1002`；`docs/provider-contract.md:278-284`、`docs/provider-contract.md:422-423`、`docs/provider-contract.md:444`。
- 修复与验证：DeepSeek 同时登记 balance 与 availability capability；false 唯一映射为 `StatusValue(insufficient_balance)` 和 high severity。金额使用严格普通十进制 Decimal，CNY/USD 唯一，`total=granted+topped_up` 精确成立；结构错误映射 schema_changed，组成错误映射 semantic_suspect，两项原子提交。fixture 矩阵覆盖 true/false、单双币种、空/重复/未知币种、错列和组成不等。

### AQ-R2-007

- 核验结论：成立，已修复。
- 修改位置：`docs/design-proposal.md:344-366`、`docs/design-proposal.md:431-433`、`docs/design-proposal.md:506-507`；`docs/provider-contract.md:178-182`、`docs/provider-contract.md:193`、`docs/provider-contract.md:385-390`、`docs/provider-contract.md:412-417`；`docs/security-model.md:171-174`。
- 修复与验证：严格 manifest 补齐 adapter version、测试协议上下界、canonical schema hash、release assurance 和发现上限；缺适用字段拒绝加载。assurance 生成输入和信任来源固定，所有字段参与 query generation；逐项变化必须隔离旧 LKG，普通 probe 不能解除 schema/semantic/local-protocol pause。

### AQ-R2-008

- 核验结论：成立，已修复。
- 修改位置：`docs/design-proposal.md:375-394`、`docs/design-proposal.md:425-429`；`docs/provider-contract.md:190-206`、`docs/provider-contract.md:418-420`；`docs/security-model.md:176-179`。
- 修复与验证：自由字典替换为 `MissingCapability(target, MissingReasonCode)`；只有四个 code，target 只能是 manifest capability 或同批 handle，三类条目有上限。未知/重复/悬空/邮箱外部 ID/超量输入整批拒绝，本地 code 模板是唯一文案来源。

### AQ-R2-009

- 核验结论：成立，已修复。
- 修改位置：`docs/design-proposal.md:255-281`、`docs/design-proposal.md:285-299`；`docs/provider-contract.md:115`、`docs/provider-contract.md:259`、`docs/provider-contract.md:330-376`；`docs/security-model.md:170`、`docs/security-model.md:179`、`docs/security-model.md:302`。
- 修复与验证：新增封闭 `OperationResult/OperationError`；凭据 backend、Adapter/发现越界、local-stdio 协议/超时、迁移/引用冲突不再伪造快照。错误无自由文本或 LKG，side effect 由唯一表决定。严格序列化 fixture 断言唯一 code、计数、零写入边界和进程组回收。

### AQ-R2-010

- 核验结论：成立，已修复。
- 修改位置：`docs/design-proposal.md:309-335`、`docs/design-proposal.md:577-584`、`docs/design-proposal.md:1007`；`docs/provider-contract.md:29-31`、`docs/provider-contract.md:431`；`docs/security-model.md:102-122`、`docs/security-model.md:304`。
- 修复与验证：增加渠道无关 PresentationContext 与 schema v1 本地 timezone；可信 actor profile > 本地配置 > UTC，已提供但非法的 zone 直接 UTC fallback 并标注。时区不参与授权或缓存身份；UTC/上海/洛杉矶、DST、缺失和非法 zone 使用同一函数 golden 测试。

### AQ-R2-011

- 核验结论：成立，已修复。
- 修改位置：`docs/design-proposal.md:543-552`、`docs/design-proposal.md:681-702`；`docs/provider-contract.md:93-94`、`docs/provider-contract.md:432`；`docs/security-model.md:195-202`、`docs/security-model.md:296`。
- 修复与验证：有引用的普通删除/禁用/manifest activation 固定拒绝；只有显式 cascade、同一 plan digest 与确认 nonce 才修改。当前 opaque ID 保持，唯一非 secret legacy 图需显式迁移；secret-like/重复/歧义/悬空固定冲突且零写入。journal 只重放确认动作集。

### AQ-R2-012

- 核验结论：成立，已修复。
- 修改位置：`docs/design-proposal.md:188-196`、`docs/design-proposal.md:283`、`docs/design-proposal.md:1000`；`docs/provider-contract.md:421`。
- 修复与验证：duration 必须正；绝对 used/limit 同空同现且非负；正常窗口至少有百分比或完整绝对值；双表示按 manifest 0..1 百分点容差一致；0/0 只允许无百分比。property/golden 测试覆盖全空、负数、零 duration、单缺、超限、矛盾和三种合法表示。

### AQ-R2-013

- 核验结论：成立，已修复。
- 修改位置：`docs/design-proposal.md:512`、`docs/design-proposal.md:1009`；`docs/provider-contract.md:328-347`、`docs/provider-contract.md:409-410`、`docs/provider-contract.md:429`；`docs/security-model.md:175`。
- 修复与验证：Provider 第 9.4 节提升为唯一规范源，逐类冻结第三次动作、Scheduler、on-demand probe/fetch、next_allowed 与唯一恢复事件；新增本地协议/超时操作错误类别。其他文档只引用，不再重述一个泛化暂停状态；交错失败不得误清其他类别。

### AQ-R2-014

- 核验结论：成立，已修复。
- 修改位置：`README.md:28`；`docs/design-proposal.md:468-479`、`docs/design-proposal.md:944`、`docs/design-proposal.md:961`、`docs/design-proposal.md:1046`、`docs/design-proposal.md:1059`；`docs/provider-contract.md:166-168`、`docs/provider-contract.md:267`、`docs/provider-contract.md:280`、`docs/provider-contract.md:448`、`docs/provider-contract.md:457`；`docs/security-model.md:318`。
- 修复与验证：Kimi/MiniMax/GLM 在 schema v1 统一为 `planned/no-contract`，没有 auth/region/binding/capability/NetworkPolicy/可执行 manifest，配置稳定拒绝。未来升级必须同一版本化变更提交协议证据、出口、认证、时区、fixture 与完整 manifest；正文移除未核验能力断言和未决占位词。

## 计数与剩余决策

| 处置 | 数量 |
| --- | ---: |
| 已修复 | 13 |
| 拒绝 | 0 |
| 用户决策阻塞 | 1 |
| **合计** | **14** |

唯一剩余决策是 Codex 身份产品基线的两个互斥选项。作出选择并同步正文后，必须由全新的独立 Agent 从零进行全量审计；本记录不宣称已达到零问题收敛。

## 验证边界

- 当前仓库仍只有设计文档，没有实现、schema fixture、构建产物或测试代码；本轮证明的是规范可实现性与静态一致性，不声称运行时测试已通过。
- 本机协议复验使用 `codex --version`、`codex app-server generate-json-schema --experimental`、`jq -S -c` 与 SHA-256；DeepSeek 语义按官方 `GET /user/balance` 文档核对。
- 本轮只修改 README、三份现行设计正文，并新增本记录；历史审计/处置记录保持只读。
- 机械验证：本记录 14 个问题 ID 各出现一次；五份现行/处置文档本地链接均存在、代码围栏成对、记录中的文件行号均在目标文件范围内；四份现行正文的 `TODO/TBD/FIXME/待冻结/待核验` 计数为 0，旧发现 DTO、自由 missing 字典和互斥 lifecycle 文案模式计数为 0。
- 历史文件 SHA-256 保持为：round-01 audit `a00a14c901881d84ba7648987a2cb7ceff92b41bd9f077a13605e38bad76abdd`；round-01 resolution `c4630344e20561d3677e6d393cf206f4bf6d438871444d28e9d7872dedd53935`；round-02 audit `c997a3853d0d47b9e44e1fbb0f8476ddbdf9006438855a3cf1cd246857b54c9a`。
- Git 仍为 `No commits yet on main`；本轮未提交、未切换分支。
