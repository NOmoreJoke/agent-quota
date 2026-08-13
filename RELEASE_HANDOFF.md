# Release handoff

## Baseline

- Scope decision branch: `main`.
- Scope decision base: `4590bd1a7ca96d225a90922f479e86214a2d2bee`.
- Exact formal release commit: not selected.
- Dirty `dev` owner changes remain outside this clean worktree.
- Last built artifact class: macOS Apple Silicon local unsigned development package.

## Scope status

- Machine authority: `docs/acceptance-matrix-v2.json`.
- Target: 10 product cards / 7 brands.
- Target actionable candidates: 7; currently creatable: 5.
- Implementation-blocked candidates: 火山 Agent Plan and 火山账户余额.
- Disabled information cards: 百炼 Coding Plan、百炼 Token Plan、MiMo Token Plan.
- Current scope commit records decisions only; it does not implement the 10-card UI,
  expand native create allowlists, or prove any live Provider capability.

## Required holder-controlled acceptance

1. Install the final signed/notarized DMG without disabling macOS security controls.
2. Enter credentials only in native secure dialogs.
3. For every claimed product, run add -> refresh -> restart -> refresh.
4. Verify subject, unit, window, remaining/limit, reset semantics, server timestamp and
   `last_success_at`.
5. Exercise 401 reauthentication and confirm stale LKG is never fresh.
6. Verify upgrade/rollback, uninstall retention, reinstall recovery and native-confirmed purge.

## Formal release gates

| Gate | Current result |
|---|---|
| Scope machine contract | Recorded; implementation pending |
| Claimed Provider live acceptance | BLOCKED_ACCOUNT |
| 火山 Agent Plan enablement | BLOCKED_IMPLEMENTATION |
| 火山 wallet contract hardening | BLOCKED_IMPLEMENTATION |
| Ten-card launch UI invariants | BLOCKED_IMPLEMENTATION |
| Developer ID signing/notarization | BLOCKED_IDENTITY |
| Package/checksum/SBOM/provenance | Must be regenerated from final clean release commit |
| Release gate machine summary | Not generated |

## Publishing boundary

Do not create a tag or GitHub Release until every formal release gate passes. Public
assets must include the notarized/stapled DMG, checksums, provenance/audits, SBOM,
license evidence and source archive. GitHub Packages is not the DMG distribution path.
