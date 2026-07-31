#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
output_dir="$repo_root/src-tauri/bin"
mkdir -p "$output_dir"

xcrun swiftc \
  -parse-as-library \
  -warnings-as-errors \
  -O \
  -framework AppKit \
  -framework Security \
  "$repo_root/native/AgentQuotaNative.swift" \
  -o "$output_dir/agent-quota-native"

codesign --force --sign - "$output_dir/agent-quota-native"
