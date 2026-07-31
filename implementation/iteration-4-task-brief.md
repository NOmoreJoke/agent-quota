# Iteration 4 — macOS package / install acceptance

## Baseline

- Repository snapshot: `3056549567029fe753f4f0007aa3f04c16312bbb`
- Source archive: `agent-quota-iteration4-source-3056549.zip`
- Archive bytes: `4,698,727`
- Archive SHA-256: `b0ba63ad416ba724f3b20d66f00643958dbb18ff4a39decbe74c0edcd3acbb18`
- Target: Apple Silicon macOS; local development package.

## Background and goal

Iterations 0–3 passed their documented gates. The current Tauri application can run
from the repository, but its production bundle does not contain the Python 3.11
sidecar/runtime or native helper. Complete the final packaging iteration so a user
can install and run the prototype locally without a user Python installation or
PATH dependency.

## Architecture and immutable boundaries

- React renderer -> strict Tauri command allowlist -> Rust trusted host -> framed
  anonymous-pipe Python sidecar -> local SQLite/filesystem state.
- Native macOS helper owns Keychain credential entry and destructive confirmation.
- No HTTP/WebSocket listener; no renderer network/file/shell/process capability.
- Preserve the 10-command/29-DTO contract, unknown-field rejection, CSP/navigation
  policy, sidecar deadline/reap/outcome-unknown semantics, native TOCTOU protection,
  and Keychain opaque-reference boundary.
- Do not weaken or silently regenerate frozen `docs/contracts/*.json`.
- Exact dependency locks remain authoritative.
- Existing user changes must not be overwritten.

## Required research and modification scope

1. Design a relocatable, pinned Apple Silicon Python 3.11 runtime and deterministic
   sidecar payload embedded inside the `.app`.
2. Ensure Rust production lookup uses bundle resources only and never falls back to
   user Python/PATH. Keep explicit development-only lookup testable.
3. Bundle the macOS native helper as an executable resource.
4. Produce `.app` and DMG, deterministic bundle inventory, SHA-256 closure, dependency
   inventory/SBOM, and install/upgrade/rollback/uninstall/purge instructions.
5. Detect absolute Homebrew paths, unexpected non-system dylibs, symlinks escaping
   the bundle, missing executables, writable/substitutable critical resources, and
   forbidden listeners.
6. Repair documentation drift that still describes this repository as design-only.
7. Add focused automation for package construction and installed/offline launch.

## Deliverables

- Source patch with all build/runtime/test/documentation changes.
- `.app` and DMG local unsigned development artifacts.
- Bundle manifest: relative path, type, mode, size, SHA-256 or symlink target.
- Dependency/SBOM record with pinned versions and architecture.
- Installer operations guide.
- Iteration report with R1/R2/R3 evidence and unresolved risks.
- Artifact manifest containing sizes and SHA-256 values.

## Mandatory validation

- Python: lint, format, typecheck, unit/property/contract tests, coverage.
- Renderer: lint, typecheck, unit, boundary scan, production build, Playwright E2E.
- Rust: `cargo fmt --check`, `cargo clippy -- -D warnings`, `cargo test`.
- Package: clean production build; bundle closure; Mach-O architecture/load-command
  audit; no external Homebrew/working-copy reference; no listener.
- Runtime: launch with hostile empty PATH and no user Python; offline first launch;
  add account, quit, relaunch, persistence, refresh/export/disable/delete/purge;
  uninstall without purge, reinstall, then explicit purge.
- Full frozen contract release gate on the final source state.
- Three independent adversarial rounds:
  - R1: contents/dependencies/locks/SBOM.
  - R2: signature/path/symlink/substitution/upgrade/rollback.
  - R3: installed runtime/regression/package acceptance.

## Forbidden operations and claims

- No deployment, database migration, production configuration, real provider,
  real API credential, or real user data.
- No Git push, PR, release, or direct main mutation during engineering.
- No security scan; the user explicitly skipped it.
- Do not claim Developer ID signing, notarization, clean VM, Intel/universal support,
  production validation, or successful installation without direct evidence.
- Do not expose or request passwords, cookies, tokens, recovery codes, or Keychain
  material.
- Do not treat mocks as live-provider verification.

## Acceptance

- A fresh local install launches from the packaged `.app` with networking disabled,
  hostile PATH, and no dependency on repository files or user Python.
- All prototype functions are locally exercisable through trusted boundaries and
  persisted across relaunch.
- The DMG can install and run on the target Apple Silicon Mac.
- Bundle/resource hashes close; critical binaries are arm64 and have no unresolved
  non-system dependencies.
- Full automated gates plus R1/R2/R3 pass with no unresolved P0/P1.
- Because no Developer ID/notarization evidence is available, every artifact/report
  must say `local unsigned development package`.
