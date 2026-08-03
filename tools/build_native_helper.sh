#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
output_dir="$repo_root/src-tauri/bin"
app_dir="$output_dir/AgentQuotaNative.app"
app_binary="$app_dir/Contents/MacOS/AgentQuotaNative"
app_plist="$app_dir/Contents/Info.plist"
mkdir -p "$output_dir"
/bin/rm -rf "$app_dir"
mkdir -p "$app_dir/Contents/MacOS"

xcrun swiftc \
  -target arm64-apple-macosx13.0 \
  -parse-as-library \
  -strict-concurrency=complete \
  -warnings-as-errors \
  -O \
  -framework AppKit \
  -framework Security \
  "$repo_root/native/AgentQuotaNative.swift" \
  -o "$app_binary"

/usr/bin/plutil -create xml1 "$app_plist"
/usr/bin/plutil -insert CFBundleExecutable -string AgentQuotaNative "$app_plist"
/usr/bin/plutil -insert CFBundleIdentifier -string com.agentquota.desktop.native-helper "$app_plist"
/usr/bin/plutil -insert CFBundleName -string "Agent Quota Native" "$app_plist"
/usr/bin/plutil -insert CFBundlePackageType -string APPL "$app_plist"
/usr/bin/plutil -insert LSUIElement -bool true "$app_plist"
/usr/bin/codesign --force --deep --sign - "$app_dir"
bundle_inventory=$(CDPATH= cd -- "$app_dir" && /usr/bin/find . -mindepth 1 -print | LC_ALL=C /usr/bin/sort)
expected_inventory='./Contents
./Contents/Info.plist
./Contents/MacOS
./Contents/MacOS/AgentQuotaNative
./Contents/_CodeSignature
./Contents/_CodeSignature/CodeResources'
[ "$bundle_inventory" = "$expected_inventory" ] || {
  echo "native helper bundle closure mismatch" >&2
  exit 1
}
"$app_binary" --self-test-provider-minimization
