# Iteration 0 质量报告（2026-07-30）

## Verdict

`PASS`：R1/R2/R3 全部通过；仅允许进入 Iteration 1，不代表应用、安装包或生产发布通过。

## R1 — Contract / Architecture

- 10 renderer commands / 29 DTO schema closure：validator 通过。
- registry anchor：`e94259e960cac8a0f19da81338f1493fe8ed73c11b0941aeeb812cfb811f069e`
- validation input：`4d7fed2d6e08847d5ff8d0135d043e1008471c2cd95509fbb591aefb8f28b06b`
- CSP：仅 `ipc:` / `http://ipc.localhost`；真实 loopback、外部 origin、WebSocket、wildcard 均拒绝。
- 原型：Pencil layout problems=0；关键状态 PDF 已固定 hash。

## R2 — Adversarial / Failure

- ChatGPT Pro：CSP targeted review `PASS`；inherited pipe FD targeted review `PASS`。
- Codex：修复 reauth 自动 replay、credential generation/cohort 混淆、purge failed/outcome_unknown、canonical TMPDIR/dyld fixture、并发 barrier 高 FD 假设。
- 高 FD 回归：预占 24 个 FD，writer FD=28；validator 与 release gate 均收到 ready，输入替换后均退出 1 且报告 source changed。
- 按用户要求：未运行安全扫描；本轮结论来自机器合同、对抗用例和运行门禁。

## R3 — Runtime / Regression

隔离工作树：

- root identity SHA-256：`9b7d278b8df7b6aa1b9d17354537a97195674906bdd78bffeab13bca4fa8cb6b`
- release input SHA-256：`cf0f243669a5139adef01cc144a695398084873ab43938f4a08154d0449edefb`
- mutation results SHA-256：`5ae9e18815279c3b07dc3d22a88c24e758eeb80adf7cb06394a0e8257937c68f`
- mutation cases：50/50
- external negative：27/27 rejected
- bootstrap negative：7/7 rejected
- loaded-image QA：16/16
- dynamic history QA：11/11
- clean install / deterministic validation / deterministic projection：通过
- source bytes unchanged：true
- final status：ok
- `npm run validate --prefix docs/contracts`：独立完整重放通过
- npm replay root identity SHA-256：`5a7ed8a03ccdcf9d04e1b2ca9bb4708aea3718c4eb051c3ddebecb70990c6ffc`
- npm replay release/mutation SHA-256：与隔离工作树一致

## Exit gate

- Iteration 1：允许开始。
- 应用本地运行：未验证。
- macOS 安装包：未构建、未验证。
- Git：未提交、未推送、未部署。
