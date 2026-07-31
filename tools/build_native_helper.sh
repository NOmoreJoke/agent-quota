#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
output_dir="$repo_root/src-tauri/bin"
app_dir="$output_dir/AgentQuotaNative.app"
app_binary="$app_dir/Contents/MacOS/AgentQuotaNative"
app_plist="$app_dir/Contents/Info.plist"
mkdir -p "$output_dir"
mkdir -p "$app_dir/Contents/MacOS"

xcrun swiftc \
  -parse-as-library \
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
