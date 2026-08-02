#!/bin/sh
set -eu

expected_release=1.97.1
expected_commit=8bab26f4f68e0e26f0bb7960be334d5b520ea452
expected_commit_short=8bab26f4f6
expected_host=aarch64-apple-darwin
expected_archive_sha256=c9748cc86107734a2a024069908a895de7caa2d37062fb641eef9f756938ace2
expected_tree_sha256=71936ef4f2fee02f3f493f206b12209705d61c2d850128b6f507b7f4ec39e9be
repo_root=$(CDPATH= cd -- "$(/usr/bin/dirname -- "$0")/.." && pwd)
path_guard="$repo_root/tools/verify_tool_path.py"

for helper in /usr/bin/python3 /usr/bin/awk /usr/bin/grep /usr/bin/dirname; do
  [ ! -L "$helper" ] && [ -f "$helper" ] && [ -x "$helper" ] || {
    echo "unsafe fixed helper: $helper" >&2
    exit 1
  }
  helper_uid=$(/usr/bin/stat -f '%u' "$helper")
  helper_mode=$(/usr/bin/stat -f '%OLp' "$helper")
  [ "$helper_uid" = 0 ] && [ $((0$helper_mode & 022)) -eq 0 ] || {
    echo "unsafe fixed helper: $helper" >&2
    exit 1
  }
done

case "${AQ_RUST_BIN:-}" in
  /*) ;;
  *) echo "AQ_RUST_BIN must be an absolute toolchain bin directory" >&2; exit 1 ;;
esac

for tool in rustc cargo cargo-clippy cargo-fmt; do
  path="$AQ_RUST_BIN/$tool"
  [ -x "$path" ] || { echo "missing Rust tool: $path" >&2; exit 1; }
  record=$(/usr/bin/python3 -I -S "$path_guard" "$path") || {
    echo "unsafe Rust tool: $path" >&2
    exit 1
  }
  canonical=${record%%|*}
  identity=${record#*|}
  case "$tool" in
    rustc) rustc_path=$canonical; rustc_identity=$identity ;;
    cargo) cargo_path=$canonical; cargo_identity=$identity ;;
    cargo-clippy) cargo_clippy_path=$canonical; cargo_clippy_identity=$identity ;;
    cargo-fmt) cargo_fmt_path=$canonical; cargo_fmt_identity=$identity ;;
  esac
done

toolchain_root=$(/usr/bin/dirname -- "$(/usr/bin/dirname -- "$rustc_path")")
tree_sha256=$(/usr/bin/python3 -I -S "$path_guard" --tree "$toolchain_root") || {
  echo "unsafe Rust toolchain tree" >&2
  exit 1
}
[ "$tree_sha256" = "$expected_tree_sha256" ] || {
  echo "Rust toolchain tree digest mismatch" >&2
  exit 1
}

release=$("$rustc_path" -Vv | /usr/bin/awk '/^release:/ {print $2}')
commit=$("$rustc_path" -Vv | /usr/bin/awk '/^commit-hash:/ {print $2}')
host=$("$rustc_path" -Vv | /usr/bin/awk '/^host:/ {print $2}')
cargo_release=$("$cargo_path" -Vv | /usr/bin/awk '/^release:/ {print $2}')
[ "$release" = "$expected_release" ] || { echo "rustc release mismatch: $release" >&2; exit 1; }
[ "$commit" = "$expected_commit" ] || { echo "rustc commit mismatch: $commit" >&2; exit 1; }
[ "$host" = "$expected_host" ] || { echo "rustc host mismatch: $host" >&2; exit 1; }
[ "$cargo_release" = "$expected_release" ] || {
  echo "cargo release mismatch: $cargo_release" >&2
  exit 1
}
rustfmt_version=$("$cargo_fmt_path" --version)
clippy_version=$("$cargo_clippy_path" --version)
printf '%s' "$rustfmt_version" | /usr/bin/grep -F "$expected_commit_short" >/dev/null || {
  echo "rustfmt commit mismatch: $rustfmt_version" >&2
  exit 1
}
printf '%s' "$clippy_version" | /usr/bin/grep -F "clippy 0.1.97" >/dev/null || {
  echo "clippy release mismatch: $clippy_version" >&2
  exit 1
}

if [ "${AQ_REQUIRE_INTEL_TARGET:-0}" = "1" ]; then
  sysroot=$("$rustc_path" --print sysroot)
  [ -d "$sysroot/lib/rustlib/x86_64-apple-darwin" ] || {
    echo "Intel target is not installed" >&2
    exit 1
  }
fi

for tool in rustc cargo cargo-clippy cargo-fmt; do
  case "$tool" in
    rustc) path=$rustc_path; identity=$rustc_identity ;;
    cargo) path=$cargo_path; identity=$cargo_identity ;;
    cargo-clippy) path=$cargo_clippy_path; identity=$cargo_clippy_identity ;;
    cargo-fmt) path=$cargo_fmt_path; identity=$cargo_fmt_identity ;;
  esac
  /usr/bin/python3 -I -S "$path_guard" --expect "$identity" "$path" >/dev/null || {
    echo "Rust tool changed after validation: $path" >&2
    exit 1
  }
done

final_tree_sha256=$(/usr/bin/python3 -I -S "$path_guard" --tree "$toolchain_root") || {
  echo "Rust toolchain tree changed after validation" >&2
  exit 1
}
[ "$final_tree_sha256" = "$tree_sha256" ] || {
  echo "Rust toolchain tree changed after validation" >&2
  exit 1
}

echo "rust-toolchain=verified release=$release commit=$commit host=$host archive_sha256=$expected_archive_sha256 tree_sha256=$tree_sha256"
