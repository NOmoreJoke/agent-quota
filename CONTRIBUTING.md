# Contributing

## Setup

Use the pinned runtimes and exact dependency locks documented in `CLAUDE.md` and
`docs/INSTALLATION.md`.

## Required checks

```bash
uv run ruff check src tests tools
uv run ruff format --check src tests tools
uv run mypy src
uv run pytest --cov=agent_quota --cov-branch
pnpm lint && pnpm typecheck && pnpm test && pnpm boundary && pnpm build && pnpm e2e
cargo fmt --manifest-path src-tauri/Cargo.toml --check
cargo clippy --manifest-path src-tauri/Cargo.toml --all-targets --features development-overrides -- -D warnings
cargo test --manifest-path src-tauri/Cargo.toml --features development-overrides
```

Contract or normative document changes also require the full clean-install contract gate in
`CLAUDE.md`.

## Data rules

- Never commit or attach `.env`, credentials, tokens, cookies, private keys, Keychain exports,
  local databases, browser state, or real account/Provider payloads.
- Use synthetic or explicitly sanitized fixtures only.
- Production packages must pass bundle runtime-state scanning and packaged-sidecar clean-install
  verification.
- Do not weaken renderer, host, sidecar, Provider allowlist, or destructive-confirmation boundaries.
