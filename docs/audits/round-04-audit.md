# 第 4 轮独立对抗性审计

> 审计结论：`FAIL_WITH_10_ISSUES`  
> 严重度：阻断 1 / 高 4 / 中 5 / 低 0  
> 审计日期：2026-07-18  
> 审计范围：`README.md`、`docs/design-proposal.md`、`docs/provider-contract.md`、`docs/security-model.md`  
> 审计方式：全新 Agent 从零全量审查；候选清单冻结前未读取 `docs/audits/` 下历史 audit/resolution。本轮只新增本报告，不修改正文或旧记录。

## 总结

本轮不能给出零问题结论。独立全量审计得到 10 项可执行问题：1 项必须由用户选择产品基线，另 9 项不需要产品取舍，可以由修复 Agent 逐项核验并修订。

Codex 身份阻塞被本 Agent 独立复现：当前本机 `codex-cli 0.142.5` 的 stable schema 中，`account/rateLimits/read` 响应没有稳定账户身份；`account/read(refreshToken=false)` 存在，但 ChatGPT `email` 可以为 `null`。因此，当前“只允许握手和 rate-limits RPC”与“必须生成 verified-stable 身份”无法同时成立。

## 必须由用户决定的阻塞项

### AQ-R4-001 — 阻断 — Codex 身份要求与只读 RPC allowlist 仍然互斥

- 严重度：阻断。
- 定位：`docs/design-proposal.md:479`、`docs/design-proposal.md:567-571`、`docs/design-proposal.md:618`、`docs/design-proposal.md:1005`、`docs/design-proposal.md:1089`、`docs/design-proposal.md:1134`、`docs/design-proposal.md:1176`、`docs/design-proposal.md:1189`；`docs/provider-contract.md:150-155`、`docs/provider-contract.md:174-180`、`docs/provider-contract.md:195-201`；`docs/security-model.md:166-173`。
- 反例：Codex 用户从账户 A 切换到账户 B。Adapter 只调用当前允许的 `account/rateLimits/read`，两个响应都只带额度/计划表面，没有稳定账户标识；core 无法知道应改变 `cache_identity`，旧缓存/LKG 可能跨账户复用。放行 `account/read` 也不能无条件解决，因为本机 schema 和官方文档都允许 ChatGPT `email=null`。
- 原因：身份安全要求需要一个能区分账户/会话代际的受信任输入，但现有发送端 allowlist 不提供该输入。本轮没有发现另一个已允许字段能证明账户稳定身份。
- 建议：由用户选择一个且只选择一个产品基线：
  1. 允许只读 `account/read(refreshToken=false)`，仅在内存中使用专用 LocalKeyRing purpose 对 `(account.type, normalized email)` 生成 keyed identity；`account=null`、非 ChatGPT 或 `email=null` fail closed，原文永不持久化；或
  2. Codex 退出 MVP Supported/第二 Adapter 退出条件，替换为具有稳定身份契约的 Provider。
- 验收：测试同账户重启、A→B 切换、登出重登、`account=null`、`email=null`、非 ChatGPT 类型；证明旧缓存/LKG 不可见，邮箱原文不进入 TOML、SQLite/WAL/SHM、日志、fixture、投影或审计；schema bundle allowlist 与正文、发送端测试完全一致。
- 当前协议证据：[OpenAI 官方 app-server 文档](https://github.com/openai/codex/blob/main/codex-rs/app-server/README.md#auth-endpoints)列出 `account/read` 与 `account/rateLimits/read`，并明确 email 可为 null；本机 stable v2 schema复现相同事实。

## 可直接修复的问题

### AQ-R4-002 — 高 — ProviderAdapter 请求接口没有显式传递凭据租约或 subject selector

- 严重度：高。
- 定位：`docs/design-proposal.md:448-474`、`docs/design-proposal.md:477`、`docs/design-proposal.md:617-619`；`docs/provider-contract.md:20`、`docs/provider-contract.md:131-155`、`docs/provider-contract.md:396-403`。
- 反例：DeepSeek 的 `fetch(principal, request)` 收到的只有 principal 和 `(subject_id, capability_id)`；`AccountPrincipal` 只有 binding ID，request 也没有已校验的 wallet selector、`CredentialLease`、`AccessIdentity` 或 endpoint context。Adapter 若自行解析 Credential Source 或读取 registry 才能发请求，就违反“Credential Source 负责解析”和“认证上下文随请求显式传递”；若把当前 Token/selector 保存在 Adapter 实例，又违反并发隔离规则。
- 原因：安全叙述要求 core 完成凭据解析、selector 规范化和身份绑定，但规范性 Protocol 没有把这些结果传入 `probe/discover/fetch`。文档中的 singleflight/限流键依赖 normalized selector，Adapter 调用面却拿不到它。
- 建议：定义封闭、不可变的 `ProbeContext/DiscoveryContext/FetchContext`；至少携带本次已授权并经 manifest 校验的 principal、按 request item 绑定的规范 selector、短期 CredentialLease 或零-binding 证明、AccessIdentity、endpoint/network policy handle 和 deadline。Secret 字段不得落入 DTO repr/序列化；Adapter 不得反查全局 registry/Credential Source。
- 验收：DeepSeek 真实形状的 fake transport 能只靠显式 context 完成请求；两个 principal/selector 并发时不会串 Token、Cookie、selector 或结果；恶意 Adapter 不能通过 context 请求 scope 外 subject；调用完成后 lease 可清除且不进入日志/异常。

### AQ-R4-003 — 高 — 严格 manifest 仍缺少正文声称可机器校验的 schema

- 严重度：高。
- 定位：`docs/design-proposal.md:179-187`、`docs/design-proposal.md:391-417`、`docs/design-proposal.md:490-501`；`docs/provider-contract.md:182-188`。
- 反例一：`AdapterManifest.semantic_contracts` 和 `display_param_schemas` 引用 `SemanticContract`、`DisplayParamSchema`，但四份现行文档没有定义这两个类型的字段、不变量或 canonicalization。core 无法按宣称的 `extra=forbid` schema 验证 canary 或 safe display 参数。
- 反例二：`QuotaSubject.plan_code` 必须命中 manifest 有限枚举，`QuotaCapability.label_key`、balance currency、status 参数也必须命中 manifest；现有 `ProviderProfile/SubjectSpec/CapabilitySpec` 没有对应有限集合。严格 loader 无处取得允许值。
- 反例三：所有可执行 lifecycle 被要求提供“有序且可比较”的 `tested_protocol_min/max`，但没有定义 comparator/version scheme，也没有说明无版本 HTTP API 和 FakeAdapter 用什么合法值；字段类型同时仍允许 `None`。
- 原因：第 3 轮增加了 profile 外壳，但多个嵌套合同仍停留在名称或散文，无法由通用 loader 独立完成离线验证。
- 建议：补齐完整 manifest meta-schema：定义 SemanticContract、DisplayParamSchema、NetworkPolicy 引用闭包、plan/label/currency/status 枚举与每种协议的 version scheme/comparator；明确 versionless 协议的判别分支，而不是伪造字符串版本。
- 验收：只使用通用 manifest loader 即可接受 DeepSeek/Codex/Fake 正例，并拒绝未知 plan、label、币种、display param、canary 字段、悬空 policy/schema 引用和不可比较测试边界；JSON Schema/模型本身可生成并通过正反例测试，不调用 Adapter 私有 `if/else` 补合同。

### AQ-R4-004 — 高 — `release_assurance_id` 只有可重算摘要，没有发行信任锚

- 严重度：高。
- 定位：`docs/design-proposal.md:544-553`；`docs/provider-contract.md:186-188`、`docs/provider-contract.md:348-357`。
- 反例：攻击者修改 Adapter 解析代码和 fixture/report 摘要，按公开配方重算 `release_assurance_id`，再修改 manifest、sidecar 和 `RECORD`。运行时从同一个被修改的 wheel 读取所有输入，两个校验层都可自洽通过；攻击者随后可用新的 assurance generation 解除 schema/local-protocol pause。
- 原因：哈希配方解决了自引用，却没有回答“谁批准这个摘要”。`RECORD` 的 hash 由同一 wheel 携带，且 `RECORD` 自身不哈希自身；正文写“RECORD/发行签名”，但没有规定签名是强制的、信任根在哪里、签什么、如何绑定包名/版本/assurance、如何轮换/撤销或离线验证。
- 建议：把 authenticity 与 reproducibility 分开：由受信任发布根对包名、版本、wheel digest、assurance payload 与构建证明签名，或采用有固定信任策略的 Sigstore/TUF/索引 attestation；RECORD 只用于 wheel 内部完整性。没有受信任 attestation 的 Adapter 不得成为 supported/ga，也不得用新 assurance 解除安全暂停。
- 验收：修改 code/manifest/fixture/report/sidecar/RECORD 后，即使全部摘要重新计算也因缺少可信签名而失败；错误签名者、过期/撤销 key、版本降级、跨包重放均拒绝；离线安装使用固定 trust bundle 可验证。PyPA 的 [wheel 规范](https://packaging.python.org/en/latest/specifications/binary-distribution-format/)说明 RECORD 是 wheel 内部文件 hash 表，且旧 `RECORD.jws/RECORD.p7s` 已弃用，不能把 RECORD 本身当发行者身份。

### AQ-R4-005 — 高 — 外部有效 TOML 可绕过破坏性 planner、plan digest 与确认 nonce

- 严重度：高。
- 定位：`docs/design-proposal.md:650-661`、`docs/design-proposal.md:802-820`；`docs/security-model.md:212-220`。
- 反例：操作者或编辑器直接从 `config.toml` 同时删除 subject、view 和 policy，使新 TOML 严格校验仍然有效。运行时 drift 逻辑会自动建立 `file_committed` journal并执行第 4 步，删除该 subject 的运行数据；整个过程没有 `--cascade --dry-run`、确认过的 `plan_digest` 或一次性 nonce。
- 原因：生命周期章节承诺所有破坏性操作共用确定性 planner，外部编辑恢复分支却把任意有效新 TOML 自动视作已提交计划。`config.toml` 是权威源不等于所有 destructive diff 已确认。
- 建议：drift 恢复先对 old DB registry 与新 TOML 计算类型化 diff；只有明确列入安全自动采用集合的非破坏性变更可自动 journal。disable/delete/manifest removal、引用移除或 generation 数据清理必须关闭 gate，输出脱敏 dry-run，并要求相同 plan digest + nonce 后才 roll-forward。
- 验收：外部新增 label/view 等安全变更按定义处理；外部删除 principal/subject/capability 或同时移除引用时，在确认前配置 DB digest和全部运行表零变化且 Provider 不被调用；确认后 crash/restart 只重放同一动作集，任一再次编辑使 digest 失效。

### AQ-R4-006 — 中 — Codex 合法的缺字段 RateLimitSnapshot 没有唯一映射

- 严重度：中。
- 定位：`docs/design-proposal.md:586-605`；`docs/provider-contract.md:292-294`。
- 反例：本机 `codex-cli 0.142.5` stable v2 schema 的 `RateLimitSnapshot` 没有 `required` 数组，因此 `{ "rateLimits": {} }`、只含 primary 或缺少 `rateLimitReachedType` 都是协议 schema 合法对象。正文只定义字段为对象、字段为 `null`、已知 reached type 和未知 reached type；没有定义“字段缺失”。实现者可能把缺失窗口当 not_applicable、把缺失 reached type 当 available，或整批 schema_changed，结果不唯一。
- 原因：合同把 nullable 与 optional 混为一类；但空值、缺字段和明确未达限并不必然同义。
- 建议：逐字段冻结 absent/null/value 三态。保守方案是：缺少 primary/secondary/reached 字段整批 `schema_changed`；若官方语义证明 absent 等同 null，则在版本化 SemanticContract 中明确等价，并用 schema 证据固定。
- 验收：空对象、只含一个窗口、两个窗口分别 absent/null、reached absent/null/known/unknown 全部有唯一 fixture 结果；每次请求仍恰好返回三项快照或一个整批 OperationError，不得默认为“可用”。

### AQ-R4-007 — 中 — wheel 专属 assurance 与 sdist 安装验收没有闭环

- 严重度：中。
- 定位：`docs/design-proposal.md:546-553`、`docs/design-proposal.md:680-692`、`docs/design-proposal.md:1128`。
- 反例：用户强制从 sdist 安装。pip 必须先在用户环境构建一个新 wheel；这个 wheel 的内容/构建证明可能不同于发布者预先计算 assurance 的 wheel。现有配方没有说明 sdist 内携带哪个 ID、谁在本地重写 manifest、fixture/report 是否进入 sdist、生成的新 ID由谁签名，运行时也无法判断本地 wheel 是否获发布者批准。
- 原因：发行矩阵要求 wheel 与 sdist，assurance recipe 和 verifier 却只定义受控构建的最终 wheel；干净环境验收也没有明确用 `--no-binary` 单独覆盖 sdist 路径。
- 建议：明确二选一：supported Adapter 只允许安装已签名 wheel，sdist 仅供源码审阅/下游重新发行且默认不获得 supported assurance；或定义 sdist source attestation、受控可复现本地构建和派生 wheel attestation 的完整链。
- 验收：wheel 与 `--no-binary :all:` 两条干净安装测试都有唯一预期；本地 wheel 字节不同、build backend/lock 改变、缺 fixture/report 或没有有效派生签名时不能获得 supported/ga，也不能解除 pause。PyPA [package formats](https://packaging.python.org/en/latest/discussions/package-formats/)明确 sdist 安装会先调用 build backend 构建 wheel。

### AQ-R4-008 — 中 — 卡片 action 的有效期没有受幂等记录/验签 key 保存期约束

- 严重度：中。
- 定位：`docs/design-proposal.md:915-920`；`docs/security-model.md:195-207`、`docs/security-model.md:230-246`。
- 反例：服务端签发一个 `expires_at` 为 60 天后的 action；`RET-IDEM-FEISHU-CARD` 在 prepared 后 30 天删除消费记录。第 31 天重放原 action 时，若签名 key 仍 active，签名仍有效而消费唯一记录已消失，动作会被当成新请求再次刷新 Provider。
- 原因：正文要求 action 带过期时间，但没有规定最大 action TTL、签发时必须小于哪一个 retention 窗口，也没有定义 action 验证截止时间与幂等记录删除/verify-only key 的不变量。
- 建议：冻结短且唯一的 `ACTION_TTL`，并强制 `expires_at <= issued_at + ACTION_TTL <= idempotency_delete_at`；消费记录和所有可验签 key 必须至少保留到 action 最晚有效时刻之后。拒绝超界签名，即使密码学签名正确。
- 验收：虚拟时钟覆盖签发边界、消费前后、30 天清理、active/verify-only key 轮换和第 31/60 天重放；任何仍可能验签的 action 都有消费记录，任何已删除记录对应 action 都必然先过期。

### AQ-R4-009 — 中 — Codex 示例 selector 与唯一规范值自相矛盾

- 严重度：中。
- 定位：`docs/design-proposal.md:588`、`docs/design-proposal.md:719-726`、`docs/design-proposal.md:808`。
- 反例：用户复制设计文档的 Codex TOML 示例，得到 `selector={source="default"}`；Codex 映射规范却固定要求 `{source="compat-default"}`。严格 selector schema 必须拒绝示例，或放宽后产生两个指向同一 bucket 的 cache/query generation。
- 原因：v0.9 新增唯一 bucket selector 时没有同步配置示例。
- 建议：把 Codex 示例改为 `compat-default`，并在 Codex SelectorSchema 中只允许这个枚举；DeepSeek 的 `default` 保持 Provider 自己的独立 schema。
- 验收：逐字提取文档完整 TOML 示例可通过 schema v1 config validate；把 Codex source 改回 default/其他值会在 offline、零凭据/网络/子进程条件下稳定拒绝。

### AQ-R4-010 — 中 — 唯一失败表与同文档错误摘要仍给出相反暂停动作

- 严重度：中。
- 定位：`docs/design-proposal.md:621`；`docs/provider-contract.md:338-357`、`docs/provider-contract.md:363-371`。
- 反例：同一 generation 连续三次 `schema_changed`。唯一表第 348 行要求“暂停全部 fetch”，按需 fetch 也禁止；错误摘要第 369 行只写“三次后暂停定时刷新”，实现者可能继续允许 on-demand fetch。对 `semantic_suspect`，唯一表第三次也暂停全部 fetch，摘要只写“不自动接受新基线”，同样没有表达禁止 fetch。
- 原因：第 9.4 节被声明为唯一规范源，但第 10 节重新声明了不完整且冲突的动作，而不是只引用唯一表。
- 建议：删除第 10 节“自动重试”列中的暂停状态机，或逐项精确引用第 9.4 节；任何摘要不得改变 Scheduler/on-demand probe/fetch 的允许动作。
- 验收：从文档生成表驱动 golden case；schema/semantic 第三次后 Scheduler=禁止、on-demand probe=允许、fetch=禁止，直到各自唯一恢复事件；全文搜索不存在另一个不同口径的“三次后暂停定时刷新”。

## 当前协议与静态验证证据

1. 本机版本：`codex-cli 0.142.5`。
2. 本机执行 `codex app-server generate-json-schema --out <empty-tmp-dir>`，未启用 `--experimental`；生成 37 个文件，v2 聚合根 SHA-256 为 `bb9dea586068ef5550427c6d1bbe918070a8616db02877eee60adc0141c8baf3`。
3. 本机 stable v2 schema：
   - `GetAccountRateLimitsResponse.required=["rateLimits"]`，但 `RateLimitSnapshot` 的 primary、secondary、rateLimitReachedType 等属性均非 required；
   - `GetAccountRateLimitsResponse` 没有账户 ID/email/session generation；
   - `account/read` 存在，ChatGPT account 的 email 类型为 `string|null`；
   - reached type 枚举与正文登记的五个当前值一致。
4. [OpenAI 官方 app-server 文档](https://github.com/openai/codex/blob/main/codex-rs/app-server/README.md)确认 stable schema 按 Codex 版本生成、初始化握手、`account/read`/`account/rateLimits/read`、email nullable、窗口与 Unix 秒时间。
5. [DeepSeek 官方余额文档](https://api-docs.deepseek.com/api/get-user-balance/)确认固定 `GET /user/balance`、boolean `is_available`、CNY/USD 和三个字符串金额字段；本轮未发现正文的当前 DeepSeek 字段名/出口漂移。
6. 静态扫描未发现 `TODO/TBD/FIXME/XXX` 或未替换模板。正常的实施状态、阶段性未勾选验收项不算占位符；唯一明确产品未决项是 `AQ-R4-001`。
7. 现行 TOML 中另有一个可复现的严格配置矛盾，即 `AQ-R4-009`；未发现真实 Token、邮箱、Open ID、Tenant/App ID 或账户余额写入审计范围文件。
8. 仓库当前没有 commit；本轮以工作区现行文件为权威。候选清单冻结后才读取历史审计，用于确认本轮结论不是把旧清单当输入；`AQ-R4-001` 独立复现，其他问题均从 v0.9 当前文本与当前协议重新得出。

## 覆盖结论

- 需求/范围、阶段边界：已审查；除 Codex MVP 基线外无新增产品决策阻塞。
- 数据模型、判别联合、发现/fetch、身份/缓存/限流/幂等：发现 `AQ-R4-002`、`AQ-R4-006`。
- manifest profile、schema/assurance、打包/testkit：发现 `AQ-R4-003`、`AQ-R4-004`、`AQ-R4-007`。
- migration fence、LocalKeyRing、InstallationRegistry、purge：发现 `AQ-R4-005`；其余当前状态机未发现新的高置信可执行问题。
- DeepSeek/Codex 映射与当前协议：发现 `AQ-R4-001`、`AQ-R4-006`、`AQ-R4-009`；DeepSeek 主源表面一致。
- 告警聚合、retention、渠道披露：发现 `AQ-R4-008`、`AQ-R4-010`；群聊零披露和 episode 聚合未发现新的高置信问题。
- 性能、平台、阶段验收、跨文档一致性、占位符：固定性能基准与平台边界可验证；另发现上述 selector、sdist 与失败摘要问题。

## 收敛判定

`FAIL_WITH_10_ISSUES`

在用户决定 `AQ-R4-001`，并由新的修复 Agent 核验、处置其余 9 项后，必须再由一个全新独立 Agent 从零进行全量审计；不能只复查本清单。
