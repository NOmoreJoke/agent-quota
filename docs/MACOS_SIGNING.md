# macOS 签名与钥匙串凭据名称

刷新通过 `AgentQuotaNative.app` 读取钥匙串。macOS 将允许访问的代码身份保存在
每条凭据的 ACL 中，还单独校验 PartitionID。普通 ad-hoc 或自签名 helper 在更改
后二进制哈希会变化；仅固定 bundle ID 或使用持久自签证书不能解决跨构建授权。

## 配置稳定签名

在本机钥匙串安装含私钥的 Apple Development（macOS）或 Developer ID Application
证书。保持同一 Apple Team、证书类型及 bundle ID。证书私钥不应放入仓库、构建
目录或聊天。列出本机可用身份并自动提取真实的 `subject.OU` Team ID（切勿误用证书 CN 括号内的个人 Member ID）：

```sh
python3 tools/macos_signing.py discover
```

若本机钥匙串仅有一组 Apple Team 身份，可直接启用 `AQ_CODESIGN_AUTO=1` 自动完成稳定签名（若同时存在 `Developer ID Application` 与 `Apple Development`，优先选用 `Developer ID Application`）：

```sh
AQ_CODESIGN_AUTO=1 AQ_RUST_BIN='/absolute/persistent/path/rust-1.97.1/bin' \
  ./tools/build_macos_package.sh
```

也可显式将选中的证书 40 位 SHA-1 和 10 位 `OU` Apple Team ID 作为构建环境变量传入：

```sh
export AQ_CODESIGN_IDENTITY='<40-character certificate SHA-1>'
export AQ_CODESIGN_TEAM_ID='<10-character Apple Team ID (subject.OU)>'
export AQ_RUST_BIN='/absolute/persistent/path/rust-1.97.1/bin'
./tools/build_macos_package.sh
```

构建签名使用系统生成的 designated requirement，不固定叶证书哈希，不弱化为仅
bundle ID。helper 和 sidecar 先签名，再生成资源清单；Tauri 使用 `--no-sign`，
最后仅签外层 app，避免再次签署已经锁定哈希的资源。嵌套 Python Mach-O 逐个由内
向外签名，不使用 `codesign --deep` 进行签名。

`signing-audit.json` 验证三个入口的 bundle/signing ID、同一预期 Team、Apple
签名链及非 CDHash 的 designated requirement。构建溯源包含该报告的哈希和签名
模式。身份不可用、团队错误或自签名均使稳定模式失败，不会静默降级。

首次从旧 ad-hoc 包迁移时，已有凭据仍可能各需一次系统授权。之后使用同团队、
同签名类型及 bundle ID 的更新才具有身份连续性；钥匙串锁定、用户撤销权限或
切换开发团队仍可要求确认。Apple Development 适合本机开发；公开分发另需
Developer ID、Hardened Runtime、notarization/stapling 等发布验收。

## 无证书时的测试模式

```sh
AQ_ALLOW_ADHOC_SIGNING=1 ./tools/build_native_helper.sh
AQ_ALLOW_ADHOC_SIGNING=1 AQ_RUST_BIN='/absolute/persistent/path/rust-1.97.1/bin' \
  ./tools/build_macos_package.sh
```

该模式与 Apple 签名变量互斥。报告必须为 `mode=adhoc-test-only`、
`keychain_identity_stable=false`。它仅验证代码和包结构，不能被称为跨版本授权
问题已解决。无有效证书时应明确保留这项交付限制，不创建一个无效的自签替代方案。

## 凭据名称与旧项迁移

名称由公开 Provider 名称和本机凭据 reference 的短标识组成，不取 API Key、Token、
邮箱或任何秘密的片段。服务及账户定位键保持不变。名称用于区分同一 Provider
的不同凭据，不代表服务商账户名。

钥匙串列表的 label 与访问弹窗的 ACL description 是不同字段，需要同步处理。
迁移只处理已知旧通用名称，保留自定义名称、秘密值、允许访问的应用、权限与
提示标记。不能通过删除重建凭据或放宽为所有应用来消除授权提示。

普通刷新不修改凭据名称或 ACL，避免把旧项迁移的系统授权混入刷新过程。
要显式迁移已有条目，先构建新版 app，再运行：

```sh
uv run python tools/migrate_keychain_labels.py --app '/absolute/path/Agent Quota.app'
# 预览正确后退出 Agent Quota，执行以下命令并在 macOS 系统窗口中确认。
uv run python tools/migrate_keychain_labels.py --app '/absolute/path/Agent Quota.app' --apply
```

工具取得与应用相同的单实例锁，仅按已有账户映射逐条更新名称；全程不读取秘密
内容、不改账户文件、不调用 Provider。先授权更新 ACL 描述，再更新列表名称；
macOS 不保证这两项原子提交，后一项失败时可重试补齐。拒绝或失败时停止后续
提示，已完成条目无需重复处理。macOS 可能逐条要求登录钥匙串密码；不要将密码
传给命令行或聊天。
自定义名称保持原样，首次授权前尚未迁移的条目仍可能显示旧通用名称。

## 验收边界

- 自动化：缺少签名配置、显式测试模式、错误团队、CDHash 身份、自签名链均有
  失败路径；资源清单覆盖最终签名后的字节。
- 本机：在隔离测试钥匙串中验证假凭据的新名称、旧名称转换计划与公开 ACL 字段，
  不用真实 Provider 密钥做构建测试。可信应用的完整代码签名约束不在公开快照中；
  真实旧项 ACL 提交和用户拒绝仍需系统交互验收。
- 有证书后的实际验收：两个不同 helper 构建使用同一团队签名；第一个获得假凭据
  访问授权，第二个读取同一假凭据不应再次询问。静态签名检查或模拟测试不能替代
  这一验收。

依据：[Apple Code Signing In Depth](https://developer.apple.com/library/archive/technotes/tn2206/_index.html)、
[Apple Security 的 PartitionID 实现](https://github.com/apple-oss-distributions/Security/blob/db15acbe6a7f257a859ad9a3bb86097bfe0679d9/securityd/src/clientid.cpp#L187-L287)。
