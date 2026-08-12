# Release handoff

## Baseline

- Source branch: `codex/open-source-rc-20260811`
- Base commit: `eaa7db5f82a0b669de74002ceb292df9968588b3`
- Dirty `dev` owner changes are excluded from this worktree and package.
- Target: macOS Apple Silicon local unsigned DMG.

## Required holder-controlled acceptance

1. Install the final DMG without disabling macOS security controls.
2. Enter credentials only in native secure dialogs.
3. For each non-blocked product, run add -> refresh -> restart -> refresh.
4. Verify subject, currency/unit, window, remaining/limit, reset time/timezone,
   server timestamp, and `last_success_at`.
5. Exercise 401 reauthentication and confirm stale LKG is never fresh.
6. Verify uninstall retention, reinstall recovery, and native-confirmed purge.

## Release gate status

| Gate | Result | Evidence |
|---|---|---|
| TypeScript | PASS | lint, typecheck, 6 unit tests, 4 E2E tests, production build |
| Python | PASS | lint, format, mypy; 213 tests; 90.06% coverage |
| Rust | PASS | fmt; clippy `-D warnings`; 33 tests in each production/development feature set |
| Contract | PASS | 50-case exact mutation match; deterministic validator/projection replay; result SHA-256 `8579704000211908d497a8e035d86d83cd0454b345755e8fef3ed8cb6b9d6a6f` |
| Error/fail-closed | PASS | 401/403, 429, 5xx, schema drift, stale LKG, pre-helper journal, credential/destructive transaction fence, outcome-unknown and mutation negative tests |
| Package/bundle | PASS | Final `bundle-audit.json`, DMG verification and size gate |
| Clean install/lifecycle | BLOCKED_ACCOUNT | Empty-sidecar clean install and no-network install/upgrade/rollback/uninstall/reinstall retention PASS; real refresh, 401 recovery and native purge remain holder-controlled |
| License/SBOM | PASS | 442 inventoried components; 245 distributed components bound to 454 hashed license/notice texts; 16 unpackaged repo-level notices bound to exact VCS commits; contract-only dependencies marked `source-validation-only` |
| SHA-256/provenance | PASS | Final `artifact-sha256.txt` and clean-source `build-provenance.json` |

Machine-readable exact results are delivered as
`artifacts/iteration-4/release-gates-v1.json`. Overall Goal remains blocked:
the acceptance matrix is `0/21 PASS` and the holder-controlled lifecycle is
incomplete.

## Publishing boundary

Local release-ready assets may be generated. Push, PR, or GitHub Release is not
performed without explicit existing authorization for that external write.
