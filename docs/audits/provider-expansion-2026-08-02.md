# Provider expansion audit — 2026-08-02

## Baseline / external review

| Item | Evidence |
|---|---|
| Source commit | `3e2e1874be2f2fd84e2024051fbe74350b26f532` |
| Sanitized source ZIP | `4,795,007` bytes; SHA-256 `e96eaf9ebeb8b6c836e425974be42bedf2e031332527dc607f171b446ba95686` |
| Implementation chat | <https://chatgpt.com/c/6a6f60ab-0468-83ea-bd87-614f6993c460> |
| Provider research chat | <https://chatgpt.com/c/6a6f618d-719c-83ea-9fd0-6ddee85dbf1b> |
| macOS/performance chat | <https://chatgpt.com/c/6a6f61c0-d7e4-83ea-8ae9-f3171a0acede> |

The upload excluded `.git`, dependencies, caches, build/package outputs, databases,
runtime/browser state and credential-shaped paths. Filename/content secret scans found no
credential candidate. ChatGPT artifacts were treated as untrusted inputs.

The final-source scan repeated credential-shaped filename and high-confidence key/token/PEM
checks. A broad assignment scan produced one lexical false positive: Swift `access_token` field
mapping names, not a credential literal.

## External defects corrected or rejected

- Provider v1 mislabeled DeepSeek/Kimi/MiniMax/GLM capabilities, collapsed 8 adapters into
  5 brands, omitted evidence, did not update Pen and ran no gates.
- Provider v2 claimed 78 rows but contained 83, removed `coverage_count`, retained stale
  incorrect rows, added duplicate `adapter-*` rows, left 76 evidence values blank and supplied
  a non-standalone patch. It was rejected; ChatGPT subsequently confirmed the defects and did
  not claim or fabricate a v3 artifact.
- macOS v4 did not enforce the architecture scan root and FIFO rejection correctly. Local
  implementation added package path/type/size tests.
- Independent package inspection found the Swift helper at `minos=26.0`. The helper now passes
  explicit `-target arm64-apple-macosx13.0`; the bundle audit rejects non-arm64-only binaries,
  missing deployment metadata and any deployment target newer than macOS 13.
- Rust production doctests were incorrectly rejected by the debug guard. `doc` compilation is
  excluded while ordinary non-test production debug builds remain rejected.

## Delivered scope

- Machine catalog: exactly 78 rows, unique IDs, screenshot presets plus Claude Code, WorkBuddy,
  QoderWork/QwenWork, Trae and Cursor.
- UI: searchable Provider Preset catalog, Window/Wallet filters, explicit capability tiers and
  fail-closed add buttons. Only the existing 8 fixed official adapters enter host-owned
  credential flow.
- Docs: README, PRD, provider matrix, user/install guide and background resource strategy.
- Pencil: 78 provider labels, Window/Wallet legend, supported/experimental/catalog boundaries,
  and DeepSeek Wallet-only correction. Exported evidence:
  `docs/audits/evidence/provider-preset-catalog-2026-08-02.png`, SHA-256
  `35d5590e543184ba4713f7b05c3305a34d6dad4fe2bb8b9cdba9b6be7260b46c`.
- Package gates: App <= 40 MiB; DMG <= 20 MiB; no forbidden paths, symlinks or special files;
  arm64-only and macOS 13-compatible Mach-O closure checked before DMG creation.

## Independent gates

| Gate | Result |
|---|---|
| Web lint / typecheck / Vitest / renderer boundary / production build | PASS; 5 tests |
| Playwright E2E | PASS; 3 tests; 78/search/filter/disabled/390/1024 covered |
| Python Ruff / format / mypy / pytest | PASS; 181 tests |
| Rust fmt / release clippy `-D warnings` / release test | PASS; 28 tests + doctest |
| macOS package / code-sign verify / `hdiutil verify` / SBOM | PASS |
| Frozen contract release gate | PASS; 50/50; deterministic replay; source bytes unchanged |

Fixture/schema/error-injection tests do not constitute real subscription, production or
all-region validation.

## Package evidence

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| `Agent-Quota-0.1.0-arm64-local-unsigned.dmg` | 13,266,510 | `082b10a6e53fedbab0d98786f84ab8f4255a7cc225a0db6883a0deb0869c7d81` |
| `bundle-audit.json` | 5,297 | `503d374ba31e3f6a2a8a14b20b1f58a156245fd733d2d7501bfd818f289fe2bc` |
| `bundle-manifest.txt` | 3,051 | `78c4e5f31fbc45512f608d2cbee9ea907974b5cfbfd65dddd7fb1a683c7dc645` |
| `sbom.cdx.json` | 83,059 | `87ab9f47fd91a4db0584e6884d3da6bb3b7841ec9dd0f21135c4419348e4f041` |

App size: 35,018,320 bytes. `codesign --verify --deep --strict` and `hdiutil verify`
passed. Mach-O audit: four binaries, all exactly arm64; deployment targets 11.0/13.0.

## Contract maintenance evidence

The first release-gate replay identified README byte drift in typed mutation locators 28, 36 and
47. Repository commit `50b209f9a4284e2182b6f3f75fd86259e4a91b47` establishes the reviewed maintenance precedent:
recompute exact before/after/recipe hashes, then update the core canonical hash, registry anchor
and design projection without rewriting immutable R1-R20 history. ChatGPT Pro initially requested
a new contract version, then withdrew that requirement after the precedent and complete locator
inventory were provided.

Only `core-safety-contract-v1.json`, `contract-registry-v1.json` and the generated contract block
in `design-proposal.md` were repinned. Final validation evidence:

- registry anchor: `005e0d89c2b18fc1fad27b20da7eb8ff3ff3165ae20eadc074661b94559769de`
- input SHA-256: `ae9ee3bde7f67e6a46afd69034ba9baf2e95119360092545dadcaf105971c1db`
- mutation results SHA-256: `eb61440097c969208be1d08b2d53883cccaf70f520e0db76589fc07b1f0614ba`
- release input SHA-256: `5920ed62c18fb3a760ba4031891c52476cc318e5d76edf9635cba06fa9c4e5e2`
- result: 50 cases, deterministic validation/projection replay, exact contract match,
  `source_bytes_unchanged=true`, `status=ok`

## Unresolved acceptance boundary

The 78-entry catalog is complete, but 71 presets do not have a verified stable machine-readable
quota contract in this review. They remain Experimental/Catalog-only/Unsupported and cannot make
network queries. Treating static price/RPM pages, dashboard scraping, arbitrary URLs, Cookies or
invented fixtures as live support would be false and unsafe. Therefore “all 78 providers have
working Window and Wallet queries” is not claimed.
