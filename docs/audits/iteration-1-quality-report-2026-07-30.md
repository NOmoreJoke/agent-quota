# Iteration 1 质量报告（2026-07-30）

## Verdict

`PASS`：Python core/application service/FakeAdapter 的 R1/R2/R3 全部通过。该结论不包含 Tauri/React、真实 Provider、Keychain/native dialog、DMG、签名、公证或部署。

## R1 — Domain / Contract / Architecture

- Python：3.11.15；runtime 三方依赖：0；dev lock：`uv.lock`。
- renderer 边界：10 commands / 29 DTO；生成资源与 machine contract 完全相等。
- `classification=destructive-trusted-surface-required`：36 UTF-8 bytes 可构造。
- core import graph：无 Tauri/React/Hermes/FastAPI/HTTP；FakeAdapter 仅在 `agent_quota_testkit`。
- scope 身份：`(principal_id, subject_id, capability_id)` 复合键；跨 principal 同名 subject/capability 回归通过。
- snapshot INSERT + refresh `succeeded`：同一 fenced SQLite transaction。
- dispatch 后 lease 过期：不发布 snapshot；持久化 `outcome_unknown`；同 key 禁止 replay。

## R2 — Adversarial / Failure

- ChatGPT Pro R1：`REJECT`；P1 config rename、purge TOCTOU、lease cleanup。
- 修复：
  - config：no-follow-every-component、private root fd、O_EXCL temp、fstat/owner/nlink/0600、dir-fd rename、file/root fsync、planned/renamed/file_committed recovery、每阶段 fence。
  - purge：内部 name/dev/inode/mode/size/nlink binding 纳入 digest；renderer 不输出；commit 前重算，openat/O_NOFOLLOW/fstat/identity/owner-mode/hardlink/empty-cache 门禁。
  - lease cleanup：best effort，不覆盖既定 success/failure/outcome_unknown。
- ChatGPT Pro R2：`PASS`；P0/P1 none；逐项确认上述修复、复合身份、原子 success transition、DTO/secret/FakeAdapter packaging。
- secret-negative export、unknown/additional/nested DTO、401/403/429/5xx/timeout/oversize/scope/identity/digest mismatch：全部自动化覆盖。
- 按用户要求：未运行通用安全扫描或依赖漏洞扫描。

## R3 — Test / Build / Install

| Gate | Result |
|---|---|
| `uv lock --check` | PASS |
| Ruff format/check | PASS |
| mypy `--strict` | PASS |
| pytest | 82 passed |
| branch coverage | 90.22% |
| wheel build | PASS |
| sdist build | PASS |
| fresh venv offline/no-deps install | PASS |
| CLI init/accounts/export/purge-plan + invalid-status | PASS |
| data root/db mode | 0700 / 0600 |
| wheel testkit absence | PASS |
| redacted export secret-negative | PASS |

Artifacts:

- `dist/agent_quota_core-0.1.0-py3-none-any.whl`
  - 30,215 bytes
  - SHA-256 `e8228597007e824e7b2f20943df29a833719eb1138eda27562fa42b7e6d16403`
- `dist/agent_quota_core-0.1.0.tar.gz`
  - 42,784 bytes
  - SHA-256 `2d0c3eaadf203e73485c41d0bf16edc0d497f48ddb89b0cb8a98132cfa3c2be1`
- isolated smoke root: `/private/var/tmp/aq-wheel-smoke-final.tMM1kd`

## Exit gate

- 完整 machine-contract release gate：`PASS`。
- `mutation_case_count=50`
- `mutation_results_sha256=6b267aef7791f75b5f35681ce0b68ce83037c09758a3ffc0283b3b65ba262964`
- `release_input_sha256=e3dbd449e41ca8a9b2bd6d11d32e1184292f78034f85b637ec1c7d888ffdd837`
- `registry_anchor=73ef4913f08cc3234ae3b4922c184a61ce86f21c3425ab72c1eab1ca93cb717b`
- 持久日志：`/private/var/tmp/agent-quota-release-gate-final.log`
- 外层 mutation suite watchdog 从 1800s 修正为 3600s；单用例 timeout、执行器、failure class 与 fail-closed 判定不变；相关 raw pin、3 个 locator state 与 recipe digest 已闭合。
- Iteration 2：已开放。
- Git：未提交、未推送、未部署。
