# 第 17 轮修复处置记录

- 修复日期：2026-07-19（Asia/Shanghai）
- 处置结论：7 项可直接修复的问题已关闭；1 项产品方向继续等待用户决策。
- 边界：没有联网、没有访问真实账户、Provider 或凭据；没有加入 `account/read`，没有移除 Codex，没有降低 Gate 0A；没有 stage、commit 或 push。
- 历史策略：本文件先完成并冻结字节，再由独立的 history manifest 记录 raw SHA-256。本文件不记录 manifest 路径、manifest 摘要或自己的摘要，因此不存在自引用摘要循环。

## AQ-R17-001 — BLOCKED_USER_DECISION

- 核验结论：审计意见成立，但无法从当前合同或上下文唯一推出产品方向。
- 处理：保持 Codex `incompatible`、零正式 fetch、零持久化 cache/LKG；等待用户选择最小只读稳定身份来源，或把 Codex 移出 MVP Supported 并替换第二个 Adapter。
- 验证：机器 current status、history manifest 与四份文档 marker 均保持本项为唯一当前 blocker；修复 Agent 未替用户选择。

## AQ-R17-002 — FIXED

- 核验结论：成立。
- 处理：新增固定 `/bin/sh` 外部启动信任根、只读 bootstrap 与 Python 二次 guard；固定 CPython implementation、exact version、ABI、platform、resolved regular executable、二进制与 framework 摘要、stdlib 实现树、OS 与 architecture。正式命令必须先过 bootstrap，随后只 exec 固定解释器。
- 验证：未登记解释器、版本、binary、framework、stdlib、ABI/platform、PATH/launcher substitution 均由封闭负例拒绝；release authority 仍为 audit evidence only。

## AQ-R17-003 — FIXED

- 核验结论：成立。
- 处理：将 Ajv 与四个传递依赖打包为五个仓库内 `file:` tarball；package、lock、bundle 文件集和逐文件 raw SHA-256 形成同一个 release input。clean install 使用空 HOME 和独立空 npm cache，禁止读取宿主 cache。
- 验证：空初始 cache 成功；额外条目、缺失 tarball、bit drift、registry URL drift、manifest/lock/bundle 不一致均 fail closed。

## AQ-R17-004 — FIXED

- 核验结论：成立。
- 处理：runtime 与 result-payload locator 改为 gate-owned typed state serializer。runtime 状态绑定 observation command、resolved executable、binary/tree/source identity；result 状态绑定完整 case set、顺序、字段和值。before 与 after 使用不同 canonical state hash。
- 验证：gate 不信任 runner，自行重放并重算状态；错误字段但同 failure、不同 malformed payload、descriptor 不变但实体变化均拒绝 evidence match。

## AQ-R17-005 — FIXED

- 核验结论：成立。
- 处理：predicate 定义新增 true/false/missing/error exact control flow 与 typed result；status path 以显式 conditional node 表示 skip。validator 解释封闭 AST，并执行同源 semantic vectors；projection 直接包含 predicate 定义。
- 验证：只有 `llm_minimal` 执行 LLM consent；`local_detail` 与 `feishu_private` 跳过该阶段但保留各自授权边界；missing/unknown/error fail closed。literal、operator、false branch 与三 audience 组合负例全部拒绝。

## AQ-R17-006 — FIXED

- 核验结论：成立。
- 处理：artifact 成为 current status 唯一值源；schema 仅验证 shape/pattern/range，validator 动态验证关系。受保护 history manifest 逐文件固定历史 raw SHA，并固定 latest audit/resolution 的 round、issue set、首行/verdict 和处置状态；clean snapshot no-follow 包含全部历史。
- 验证：删除、替换、伪首行、旧轮回退、只改 artifact 不更新投影均拒绝。resolution 先冻结、本 manifest 后生成，resolution 不包含 manifest 或自身摘要，故无摘要循环。

## AQ-R17-007 — FIXED

- 核验结论：成立。
- 处理：retention heading path 每段同时固定 level、sibling ordinal、normalized exact text 与 identifier；表、列、ID set 和三表 join 约束保持不变。
- 验证：标题改名、同义标题、同位复制、前方插入、跨 heading 移动和重复 exact 标题均拒绝；43 个 fixture、原 5 类结构 QA、9 个合法 record 与 38 个 live exception 保持正向成立，并新增 6 类 heading QA。

## AQ-R17-008 — FIXED

- 核验结论：成立。
- 处理：四份入口/主文档编号已改为同级唯一、严格单调，所有编号子节都有父节；Provider 第 13 节恢复到第 14 节之前，15.1/15.2 改为三级标题；设计方案重复的第 21 节及后续编号已顺延。
- 验证：heading number/anchor lint 覆盖重复、倒序、缺父节和文内 anchor；本地文件与 anchor 检查保持零缺失。

## 最终验证边界

本记录只证明第 17 轮修复内容。完整 validator、projection、mutation suite、空 HOME/空 cache clean gate、双 replay、R17 负例、history manifest、自引用检查、JSON/链接/anchor/fence/heading 与 Git/staged 检查必须全部通过后，才可交给全新的第 18 轮审计 Agent。唯一产品 blocker 未解除，因此本轮不能宣告零问题或 Gate 0A 通过。
