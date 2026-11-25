#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
exec uv run python "$repo_root/tools/notarize_macos_package.py" "$@"
