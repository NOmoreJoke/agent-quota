# Frontend prototype sync quality report — 2026-08-04

## Scope and authority

- Integration baseline: `ee4c8fb446b6bd383ac3aef412fce29f7aedb7ae` (`codex/provider-expansion`), a direct descendant of `origin/main@83aaa9e`.
- ChatGPT Pro frontend review: <https://chatgpt.com/c/6a71a677-4b74-83ea-b645-4c8d3969c6c6>.
- ChatGPT Pro contract-gate review: <https://chatgpt.com/c/6a71b0e5-a7c4-83ea-b3e4-4ca78d6c5a42>.
- Final acceptance authority: local source review, isolated tests, and browser checks in this report. ChatGPT Pro claims were not treated as evidence.

## Source transfer evidence

| Package | Baseline | Bytes | SHA-256 | Secret/path scan |
|---|---|---:|---|---|
| `agent-quota-main-source-ee4c8fb.zip` | `ee4c8fb` | 4,933,728 | `81e40712c6da3f958db239365fd3f3f2a3abe3ca4409362fab445d3dbec3911f` | PASS; no unsafe paths or high-confidence credential matches |
| `agent-quota-source-07a9a47.zip` | superseded `dev@07a9a47` | 4,746,343 | `7c59f12679aa06d47659f61924895fe3fd39685aba351c96ec072e8b86329ea6` | PASS; not used for main integration |

Both packages excluded Git metadata, dependencies, build/cache output, databases, runtime/browser state, environment files, cookies, tokens, keys, and other credential material.

## Findings and resolution

| Finding | Evidence | Resolution |
|---|---|---|
| Accounts/settings sidebar drifted right | React/CSS/E2E contradicted the repaired 240px left-sidebar prototype | Removed all right-sidebar branches and CSS; all five views use the left sidebar |
| Queue fabricated per-account/provider work rows | Existing DTO exposed only global refresh state | Replaced rows with an explicit `idle/running/completed` global refresh projection and independent result state |
| Queue result depended on unrelated global notice | Offline/load warnings could be mislabeled as refresh outcome | Refresh result is now owned by `refreshState`, not `notice.tone` |
| Scheduler health was inferred from installation alone | `installed=true, health=unhealthy` could render as running without warning | Healthy requires both installed and `health=healthy`; unhealthy/absent fail closed to manual-only messaging |
| Prototype acceptance coverage was incomplete | Existing E2E asserted side only and did not verify geometry/navigation invariants | Added 1280×800 geometry, five-item navigation, unique current item, accounts/settings repetition, queue/status semantics, and 390×844 overflow/operability checks |
| Loaded-image self-test used a non-canonical Darwin alias | `/private/var/tmp` was reported by `vmmap` as `/var/tmp`, causing a fail-closed false negative | Moved only the test fixture to canonical `/Users/Shared`; canonical/no-follow/regular-file policy remains unchanged |
| Runner change invalidated reviewed mutation evidence | The runner is bound by sequence 33 filesystem state, sequence 34 typed runtime source identity, and its `package.json` pin is bound by sequence 37 | Recomputed real macOS before/after states, mutation digests, core artifact pins, registry anchor, and design projection; all 50 before states and full replay now match |

## ChatGPT Pro correction history

| Delivery | Result | Correction required |
|---|---|---|
| v1 (`3c57c8d...`) | REJECT | Old `dev` renderer, failing unit contract, incomplete E2E |
| v2 (`ae135669...`) | REJECT | Missing report/test file; stale unit assertion; insufficient geometry coverage |
| v3 (`ffc50173...`) | REJECT | Deleted three existing E2E suites and regressed status semantics |
| v4 (`265980ec...`) | PARTIAL | Restored E2E coverage; queue/scheduler state semantics still incorrect |
| v5 | REJECT | Pro acknowledged the claimed ZIP did not exist; earlier bytes/hash were not real artifact evidence |

The accepted implementation was reconstructed and reviewed by Codex from the valid main baseline, using only the defensible parts of the external review.

The independent contract review also required three corrections: Pro first claimed a two-file closure, then omitted sequence 34, then omitted the second-order `package.json` source-identity binding in sequence 37. Each claim was rejected with full-gate evidence. Pro acknowledged all three errors; the accepted closure was derived and validated locally.

## Independent verification

| Gate | Result |
|---|---|
| `pnpm lint` | PASS |
| `pnpm typecheck` | PASS |
| `pnpm test` | PASS — 5 tests |
| `pnpm boundary` | PASS — 9 renderer files |
| `pnpm build` | PASS — production fixture exclusion |
| `pnpm e2e` | PASS — 4 Playwright tests |
| Python ruff/format/mypy | PASS |
| Python pytest | PASS — 181 tests, 90.59% branch coverage total |
| Rust fmt/clippy/test (`development-overrides`) | PASS — 28 tests plus subprocess/doc-test targets |
| Contract read-only validator | PASS — 50-case before-state scan: 0 mismatches; `status=ok` |
| Contract release gate | PASS — 50 mutations; deterministic validation/projection replay; 27 external, 7 bootstrap, and 16 loaded-image negative/QA checks |
| `npm run validate --prefix docs/contracts` | PASS — repository npm entry executed the same full gate; exit 0 |
| In-app browser fixture verification | PASS — five navigation items; accounts/settings/queue/status reachable; idle refresh and fixture scheduler provenance visible |

The Rust test worktree required the ignored generated Tauri resource tree already produced by the repository packaging flow. The contract worktree required `npm ci --prefix docs/contracts`; neither prerequisite is tracked or included in the change.

## Residual limits

- Fixture and mock-backed tests do not prove real Provider behavior, production credentials, or real user data paths.
- No signed/notarized package, clean-VM, Intel/universal, production deployment, or database migration was executed.
- Contract tooling reports one high and one moderate advisory in its pinned offline AJV/`fast-uri` validator bundle. These are not renderer/runtime dependencies; changing them requires a separate frozen validation-runtime repin and contract regeneration.
- Local contract validation is audit evidence only; external launch attestation remains absent by design.
