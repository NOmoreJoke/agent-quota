# Third-party notices

Agent Quota is distributed under the MIT License. Third-party dependencies and
their licenses remain governed by their respective copyright holders and
license terms.

The release SBOM is generated from the exact `pnpm-lock.yaml`, `uv.lock`,
`src-tauri/Cargo.lock`, and offline `docs/contracts/package-lock.json` inputs.
Contract validator dependencies are marked `source-validation-only`; they are
not bundled in the app runtime. A release is blocked if a dependency has a
missing, unknown, or incompatible license. Exact component attribution,
license/notice text, and text SHA-256 bindings are shipped in
`THIRD_PARTY_LICENSE_CORPUS.json`; target-excluded lockfile entries are retained
in the SBOM but excluded from the binary notice corpus. Crates whose published
archives omit repository-level notices are bound to exact VCS commits, source
paths, metadata hashes, upstream notices, and pinned SPDX texts in
`THIRD_PARTY_UPSTREAM_LICENSE_SOURCES.json`; placeholder attribution and
unrelated-package templates are rejected. No external fonts or photographs are
bundled. The original MIT-licensed application icon is documented in
`ASSET_PROVENANCE.md`.

Sanitized Provider fixtures contain only response field topology and synthetic
replacement values. They do not contain Provider code, documentation text,
credentials, account identifiers, or complete upstream responses.
