"""Frozen sidecar executable entrypoint."""

from agent_quota.sidecar import main  # type: ignore[import-untyped]

if __name__ == "__main__":
    raise SystemExit(main())
