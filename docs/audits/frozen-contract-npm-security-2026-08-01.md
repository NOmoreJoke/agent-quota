# Frozen contract npm 安全记录

`docs/contracts/package-lock.json` 的隔离安装审计结果：

| 组件 | 版本 | 等级 | 状态 |
|---|---:|---:|---|
| ajv | 8.17.1 | moderate | npm audit 当前无可用修复 |
| fast-uri | 3.1.3 | high | npm audit 当前无可用修复 |

影响域：仅冻结的本地合同 validator 工具链；不打入桌面应用 runtime。直接升级会改变 v1 lock、offline bundle、SBOM 与 gate hash，违反冻结合同边界。

处置：v1 字节保持不变并记录残余风险；后续以 versioned contract v2 同步升级 lock/offline bundle/SBOM/gate pins。不得将当前记录表述为漏洞已修复。
