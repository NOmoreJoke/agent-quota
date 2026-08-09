#!/bin/sh
set -eu

MACOSX_DEPLOYMENT_TARGET_REQUIRED="13.0"
if [ "${MACOSX_DEPLOYMENT_TARGET:-$MACOSX_DEPLOYMENT_TARGET_REQUIRED}" != "$MACOSX_DEPLOYMENT_TARGET_REQUIRED" ]; then
  echo "MACOSX_DEPLOYMENT_TARGET must be exactly $MACOSX_DEPLOYMENT_TARGET_REQUIRED" >&2
  exit 1
fi
if [ "${SWIFT_MACOSX_DEPLOYMENT_TARGET:-$MACOSX_DEPLOYMENT_TARGET_REQUIRED}" != "$MACOSX_DEPLOYMENT_TARGET_REQUIRED" ]; then
  echo "SWIFT_MACOSX_DEPLOYMENT_TARGET must be exactly $MACOSX_DEPLOYMENT_TARGET_REQUIRED" >&2
  exit 1
fi
export MACOSX_DEPLOYMENT_TARGET="$MACOSX_DEPLOYMENT_TARGET_REQUIRED"
export SWIFT_MACOSX_DEPLOYMENT_TARGET="$MACOSX_DEPLOYMENT_TARGET_REQUIRED"

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
generated="$repo_root/src-tauri/generated-resources"
pyi_root="$repo_root/build/pyinstaller"
artifact_dir="$repo_root/artifacts/iteration-4"

source_commit=$(git -C "$repo_root" rev-parse HEAD)
verify_source_lock() {
  if [ "$(git -C "$repo_root" rev-parse HEAD)" != "$source_commit" ] || \
     [ -n "$(git -C "$repo_root" status --porcelain)" ]; then
    echo "package build source lock changed or became dirty" >&2
    exit 1
  fi
}
verify_source_lock

if [ "$(uname -s)" != "Darwin" ] || [ "$(uname -m)" != "arm64" ]; then
  echo "package build requires Apple Silicon macOS" >&2
  exit 1
fi

case "${AQ_RUST_BIN:-}" in
  /*) ;;
  *) echo "AQ_RUST_BIN must be an absolute toolchain bin directory" >&2; exit 1 ;;
esac

if /usr/bin/env | /usr/bin/grep -Eq '^(RUSTFLAGS|RUSTDOCFLAGS|RUSTC_BOOTSTRAP|RUSTC_WRAPPER|RUSTC_WORKSPACE_WRAPPER|CARGO_HOME|CARGO_ENCODED_RUSTFLAGS|CARGO_INCREMENTAL|CARGO_BUILD_|CARGO_PROFILE_|CARGO_TARGET_)='; then
  echo "unsafe Cargo or rustc environment override" >&2
  exit 1
fi
real_home=$(/usr/bin/python3 -I -S -c 'import os, pwd; print(pwd.getpwuid(os.geteuid()).pw_dir)')
[ "${HOME:-}" = "$real_home" ] || {
  echo "HOME must match the OS account database during package builds" >&2
  exit 1
}
for cargo_config in \
  "$real_home/.cargo/config" "$real_home/.cargo/config.toml" \
  "$repo_root/.cargo/config" "$repo_root/.cargo/config.toml"; do
  [ ! -e "$cargo_config" ] || {
    echo "Cargo config override is not allowed: $cargo_config" >&2
    exit 1
  }
done

for tool in uv pnpm node xcrun; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "missing build tool: $tool" >&2
    exit 1
  fi
done
PNPM=$(command -v pnpm)
NODE=$(command -v node)

"$repo_root/tools/verify_rust_toolchain.sh"
RUSTC="$AQ_RUST_BIN/rustc"
CARGO="$AQ_RUST_BIN/cargo"
export RUSTC CARGO

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
  "$repo_root/tools/verify_rust_toolchain.sh" >/dev/null
rust_command_shim="$pyi_root/rust-command-shim"
/bin/mkdir -m 0700 "$rust_command_shim"
/bin/ln -s "$CARGO" "$rust_command_shim/cargo"
/bin/ln -s "$RUSTC" "$rust_command_shim/rustc"
/bin/ln -s "$PNPM" "$rust_command_shim/pnpm"
node_bin_dir=$(/usr/bin/dirname -- "$NODE")
AQ_RESOURCE_MANIFEST_SHA256="$resource_manifest_sha256" \
  PATH="$rust_command_shim:$node_bin_dir:/usr/bin:/bin:/usr/sbin:/sbin" \
  "$PNPM" tauri build --runner "$CARGO" --target aarch64-apple-darwin \
    --features production --bundles app

app="$repo_root/src-tauri/target/aarch64-apple-darwin/release/bundle/macos/Agent Quota.app"
if [ ! -d "$app" ]; then
  echo "Tauri application output is incomplete" >&2
  exit 1
fi
/usr/bin/codesign --force --sign - "$app"
/usr/bin/codesign --verify --deep --strict --verbose=2 "$app"

/usr/bin/ditto "$app" "$artifact_dir/Agent Quota.app"
uv run python tools/audit_macos_bundle.py \
  --app "$artifact_dir/Agent Quota.app" \
  --output "$artifact_dir/bundle-audit.json"
uv run python tools/verify_clean_install_sidecar.py \
  --sidecar "$artifact_dir/Agent Quota.app/Contents/Resources/sidecar/agent-quota-sidecar" \
  --output "$artifact_dir/clean-install-audit.json"
uv run python "$repo_root/tools/audit_package_size.py" \
  --root "$artifact_dir/Agent Quota.app" \
  --max-mib 40
/usr/bin/hdiutil create \
  -volname "Agent Quota" \
  -srcfolder "$app" \
  -ov \
  -format UDZO \
  "$artifact_dir/Agent-Quota-0.1.0-arm64-local-unsigned.dmg"
/usr/bin/hdiutil verify "$artifact_dir/Agent-Quota-0.1.0-arm64-local-unsigned.dmg"

dmg_bytes=$(/usr/bin/stat -f%z "$artifact_dir/Agent-Quota-0.1.0-arm64-local-unsigned.dmg")
if [ "$dmg_bytes" -gt 20971520 ]; then
  echo "DMG exceeds 20MiB budget: $dmg_bytes bytes" >&2
  exit 1
fi

uv run python tools/generate_bundle_manifest.py \
  --root "$artifact_dir/Agent Quota.app" \
  --output "$artifact_dir/bundle-manifest.txt"
uv run python tools/generate_package_sbom.py \
  --output "$artifact_dir/sbom.cdx.json"
verify_source_lock
uv run python tools/generate_build_provenance.py \
  --app "$artifact_dir/Agent Quota.app" \
  --commit "$source_commit" \
  --dmg "$artifact_dir/Agent-Quota-0.1.0-arm64-local-unsigned.dmg" \
  --output "$artifact_dir/build-provenance.json"

(
  cd "$artifact_dir"
  /usr/bin/shasum -a 256 \
    "Agent-Quota-0.1.0-arm64-local-unsigned.dmg" \
    "build-provenance.json" \
    "bundle-audit.json" \
    "bundle-manifest.txt" \
    "clean-install-audit.json" \
    "sbom.cdx.json" > artifact-sha256.txt
)
verify_source_lock

echo "$artifact_dir"
