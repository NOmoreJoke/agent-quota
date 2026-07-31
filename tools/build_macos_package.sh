#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
generated="$repo_root/src-tauri/generated-resources"
pyi_root="$repo_root/build/pyinstaller"
artifact_dir="$repo_root/artifacts/iteration-4"

if [ "$(uname -s)" != "Darwin" ] || [ "$(uname -m)" != "arm64" ]; then
  echo "package build requires Apple Silicon macOS" >&2
  exit 1
fi

if [ -n "${AQ_RUST_BIN:-}" ]; then
  PATH="$AQ_RUST_BIN:$PATH"
  export PATH
fi

for tool in uv pnpm xcrun cargo; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "missing build tool: $tool" >&2
    exit 1
  fi
done

/bin/rm -rf "$generated" "$pyi_root" "$artifact_dir"
/bin/mkdir -p "$generated" "$pyi_root/work" "$pyi_root/spec" "$artifact_dir"

cd "$repo_root"
uv run --group package pyinstaller \
  --clean \
  --noconfirm \
  --onedir \
  --name agent-quota-sidecar \
  --paths src \
  --collect-data agent_quota \
  --distpath "$generated" \
  --workpath "$pyi_root/work" \
  --specpath "$pyi_root/spec" \
  tools/sidecar_entry.py

# Tauri fails closed on resource symlinks; materialize the Python framework tree.
/bin/mv "$generated/agent-quota-sidecar" "$pyi_root/agent-quota-sidecar-with-symlinks"
/bin/cp -RL "$pyi_root/agent-quota-sidecar-with-symlinks" \
  "$generated/agent-quota-sidecar"

"$repo_root/tools/build_native_helper.sh"
/usr/bin/ditto "$repo_root/src-tauri/bin/AgentQuotaNative.app" \
  "$generated/AgentQuotaNative.app"
/bin/chmod 0755 \
  "$generated/agent-quota-sidecar/agent-quota-sidecar"
/usr/bin/codesign --force --deep --sign - "$generated/agent-quota-sidecar/agent-quota-sidecar"

uv run python tools/generate_resource_manifest.py \
  --generated "$generated" \
  --output "$generated/resource-manifest.json"
resource_manifest_sha256=$(
  /usr/bin/shasum -a 256 "$generated/resource-manifest.json" | /usr/bin/awk '{print $1}'
)
AQ_RESOURCE_MANIFEST_SHA256="$resource_manifest_sha256" \
  pnpm tauri build --bundles app

app="$repo_root/src-tauri/target/release/bundle/macos/Agent Quota.app"
if [ ! -d "$app" ]; then
  echo "Tauri application output is incomplete" >&2
  exit 1
fi
/usr/bin/codesign --force --sign - "$app"
/usr/bin/codesign --verify --deep --strict --verbose=2 "$app"

/usr/bin/ditto "$app" "$artifact_dir/Agent Quota.app"
/usr/bin/hdiutil create \
  -volname "Agent Quota" \
  -srcfolder "$app" \
  -ov \
  -format UDZO \
  "$artifact_dir/Agent-Quota-0.1.0-arm64-local-unsigned.dmg"
/usr/bin/hdiutil verify "$artifact_dir/Agent-Quota-0.1.0-arm64-local-unsigned.dmg"

uv run python tools/audit_macos_bundle.py \
  --app "$artifact_dir/Agent Quota.app" \
  --output "$artifact_dir/bundle-audit.json"
uv run python tools/generate_bundle_manifest.py \
  --root "$artifact_dir/Agent Quota.app" \
  --output "$artifact_dir/bundle-manifest.txt"
uv run python tools/generate_package_sbom.py \
  --output "$artifact_dir/sbom.cdx.json"

(
  cd "$artifact_dir"
  /usr/bin/shasum -a 256 \
    "Agent-Quota-0.1.0-arm64-local-unsigned.dmg" \
    "bundle-audit.json" \
    "bundle-manifest.txt" \
    "sbom.cdx.json" > artifact-sha256.txt
)

echo "$artifact_dir"
