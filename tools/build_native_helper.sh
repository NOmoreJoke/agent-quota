#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
/usr/bin/python3 -I -S "$repo_root/tools/macos_signing.py" preflight
output_dir="$repo_root/src-tauri/bin"
app_dir="$output_dir/AgentQuotaNative.app"
app_binary="$app_dir/Contents/MacOS/AgentQuotaNative"
app_plist="$app_dir/Contents/Info.plist"
mkdir -p "$output_dir"
/bin/rm -rf "$app_dir"
mkdir -p "$app_dir/Contents/MacOS"
mkdir -p "$repo_root/build/native"
xcrun clang -target arm64-apple-macosx13.0 -Wall -Wextra -Werror \
  -c "$repo_root/native/KeychainMetadata.c" \
  -o "$repo_root/build/native/KeychainMetadata.o"

xcrun swiftc \
  -target arm64-apple-macosx13.0 \
  -parse-as-library \
  -strict-concurrency=complete \
  -warnings-as-errors \
  -O \
  -framework AppKit \
  -framework Security \
  -framework UniformTypeIdentifiers \
  -import-objc-header "$repo_root/native/KeychainMetadata.h" \
  "$repo_root/build/native/KeychainMetadata.o" \
  "$repo_root"/native/Sources/*.swift \
  -o "$app_binary"
load_commands=$(/usr/bin/otool -l "$app_binary")
if printf '%s\n' "$load_commands" | /usr/bin/awk '
  $1 == "cmd" { is_rpath = ($2 == "LC_RPATH") }
  is_rpath && $1 == "path" && $2 == "/usr/lib/swift" { found = 1 }
  END { exit !found }
'; then
  /usr/bin/install_name_tool -delete_rpath /usr/lib/swift "$app_binary"
fi

/usr/bin/plutil -create xml1 "$app_plist"
/usr/bin/plutil -insert CFBundleExecutable -string AgentQuotaNative "$app_plist"
/usr/bin/plutil -insert CFBundleIdentifier -string com.agentquota.desktop.native-helper "$app_plist"
/usr/bin/plutil -insert CFBundleName -string "Agent Quota Native" "$app_plist"
/usr/bin/plutil -insert CFBundlePackageType -string APPL "$app_plist"
/usr/bin/plutil -insert LSUIElement -bool true "$app_plist"
/usr/bin/python3 -I -S "$repo_root/tools/macos_signing.py" sign \
  --path "$app_dir" --identifier com.agentquota.desktop.native-helper
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
"$app_binary" --self-test-credential-labels
