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

All gates are unproven until replayed against the final exact commit and final
artifact. Outputs must include exit status, artifact path, size, SHA-256, SBOM,
and build provenance.

## Publishing boundary

Local release-ready assets may be generated. Push, PR, or GitHub Release is not
performed without explicit existing authorization for that external write.
