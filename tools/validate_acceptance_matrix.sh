#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
runtime_root=$(/usr/bin/mktemp -d -t aq-acceptance-runtime.XXXXXX)
cleanup() {
  /bin/rm -rf "$runtime_root"
}
trap cleanup EXIT HUP INT TERM

for tool in node npm; do
  command -v "$tool" >/dev/null 2>&1 || {
    echo "missing validation tool: $tool" >&2
    exit 1
  }
done

npm install \
  --prefix "$runtime_root" \
  --cache "$runtime_root/npm-cache" \
  --offline \
  --ignore-scripts \
  --no-audit \
  --no-fund \
  "$repo_root/docs/contracts/offline-npm-bundle-v1/ajv-8.17.1.tgz" \
  "$repo_root/docs/contracts/offline-npm-bundle-v1/fast-deep-equal-3.1.3.tgz" \
  "$repo_root/docs/contracts/offline-npm-bundle-v1/fast-uri-3.1.3.tgz" \
  "$repo_root/docs/contracts/offline-npm-bundle-v1/json-schema-traverse-1.0.0.tgz" \
  "$repo_root/docs/contracts/offline-npm-bundle-v1/require-from-string-2.0.2.tgz" \
  >/dev/null

AQ_ACCEPTANCE_RUNTIME_ROOT="$runtime_root" \
  node "$repo_root/tools/validate_acceptance_matrix.mjs" "$@"
