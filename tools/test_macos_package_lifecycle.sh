#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
dmg=${1:-"$repo_root/artifacts/iteration-4/Agent-Quota-0.1.0-arm64-local-unsigned.dmg"}
test_root=$(mktemp -d "${TMPDIR:-/tmp}/agent-quota-i5-lifecycle.XXXXXX")
mount_point="$test_root/mount"
applications="$test_root/Applications"
installed="$applications/Agent Quota.app"
backup="$test_root/rollback/Agent Quota.app"
real_home=$(/usr/bin/python3 -c 'import os, pwd; print(pwd.getpwuid(os.geteuid()).pw_dir)')
data_root="$real_home/Library/Application Support/com.agentquota.desktop"
state_file="$data_root/native-accounts-v1.json"
main_pid=
mount_device=
cleanup_started=0
cleanup_result=0

AQ_HDIUTIL_BIN=${AQ_HDIUTIL_BIN:-/usr/bin/hdiutil}
AQ_MOUNT_BIN=${AQ_MOUNT_BIN:-/sbin/mount}
AQ_PYTHON_BIN=${AQ_PYTHON_BIN:-/usr/bin/python3}
AQ_SLEEP_BIN=${AQ_SLEEP_BIN:-/bin/sleep}
AQ_IDENTITY_HELPER=${AQ_IDENTITY_HELPER:-"$repo_root/tools/dmg_mount_identity.py"}
export AQ_HDIUTIL_BIN AQ_MOUNT_BIN AQ_PYTHON_BIN AQ_SLEEP_BIN AQ_IDENTITY_HELPER
. "$repo_root/tools/dmg_lifecycle_cleanup.sh"

if /usr/bin/pgrep -f '/Agent Quota.app/Contents/MacOS/agent-quota-desktop' >/dev/null 2>&1; then
  echo "quit Agent Quota before lifecycle validation" >&2
  exit 1
fi
[ -f "$state_file" ] || {
  echo "lifecycle validation requires an existing safe account state" >&2
  exit 1
}
state_before=$(/usr/bin/shasum -a 256 "$state_file" | /usr/bin/awk '{print $1}')
credential_references=$(/usr/bin/python3 - "$state_file" <<'PY'
import json
import sys
from pathlib import Path

document = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if document.get("schema") != "aq-native-account-state-v1":
    raise SystemExit("unexpected account-state schema")
references = [account.get("credential_reference") for account in document.get("accounts", [])]
if not references or any(not isinstance(reference, str) or "\n" in reference for reference in references):
    raise SystemExit("account state has unsafe credential references")
print("\n".join(references))
PY
)

assert_persistent_state() {
  state_after=$(/usr/bin/shasum -a 256 "$state_file" | /usr/bin/awk '{print $1}')
  [ "$state_after" = "$state_before" ] || {
    echo "lifecycle launch changed account state" >&2
    exit 1
  }
  while IFS= read -r reference; do
    /usr/bin/security find-generic-password \
      -s com.agentquota.desktop.credentials.v1 -a "$reference" >/dev/null 2>&1 || {
      echo "lifecycle launch removed a retained Keychain reference" >&2
      exit 1
    }
  done <<EOF
$credential_references
EOF
}

assert_persistent_state

cleanup() {
  [ "$cleanup_started" -eq 0 ] || return "$cleanup_result"
  cleanup_started=1
  result=0
  if [ -n "$main_pid" ] && /bin/kill -0 "$main_pid" 2>/dev/null; then
    /bin/kill -TERM "$main_pid" 2>/dev/null || result=1
    wait "$main_pid" 2>/dev/null || true
  fi
  aq_cleanup_dmg "$dmg" "$mount_point" "$mount_device" || result=1
  if [ -d "$test_root" ]; then
    /usr/bin/find "$test_root" -depth -delete || result=1
  fi
  cleanup_result=$result
  return "$result"
}

finish() {
  body_result=$?
  trap - EXIT HUP INT TERM
  cleanup_result=0
  cleanup || cleanup_result=$?
  if [ "$body_result" -ne 0 ]; then exit "$body_result"; fi
  exit "$cleanup_result"
}
trap finish EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

launch_and_check() {
  executable="$installed/Contents/MacOS/agent-quota-desktop"
  sidecar="$installed/Contents/Resources/sidecar/agent-quota-sidecar"
  if [ ! -x "$executable" ] || [ ! -x "$sidecar" ]; then
    echo "installed bundle is incomplete" >&2
    exit 1
  fi
  /usr/bin/env -i HOME="$test_root/home" PATH=/nonexistent TMPDIR="$test_root/tmp" \
    /usr/bin/sandbox-exec -p '(version 1) (allow default) (deny network*)' \
    "$executable" >"$test_root/app.log" 2>&1 &
  main_pid=$!
  attempts=0
  sidecar_pid=
  while [ "$attempts" -lt 50 ]; do
    /bin/kill -0 "$main_pid" 2>/dev/null || {
      echo "application exited during launch" >&2
      exit 1
    }
    sidecar_pid=$(
      /bin/ps -axo pid=,command= |
        /usr/bin/awk -v target="$sidecar" 'index($0, target) {print $1; exit}'
    )
    [ -z "$sidecar_pid" ] || break
    /bin/sleep 0.1
    attempts=$((attempts + 1))
  done
  [ -n "$sidecar_pid" ] || { echo "bundled sidecar did not start" >&2; exit 1; }
  for pid in "$main_pid" "$sidecar_pid"; do
    if /usr/sbin/lsof -nP -a -p "$pid" -iTCP -iUDP 2>/dev/null | /usr/bin/grep -q .; then
      echo "network socket detected for PID $pid" >&2
      exit 1
    fi
  done
  /bin/kill -TERM "$main_pid"
  wait "$main_pid" 2>/dev/null || true
  main_pid=
  attempts=0
  while [ "$attempts" -lt 30 ]; do
    if ! /bin/ps -axo command= | /usr/bin/grep -F "$sidecar" |
      /usr/bin/grep -v grep >/dev/null; then
      return
    fi
    /bin/sleep 0.1
    attempts=$((attempts + 1))
  done
  echo "sidecar survived host shutdown" >&2
  exit 1
}

/bin/mkdir -p "$mount_point" "$applications" "$test_root/rollback" \
  "$test_root/home" "$test_root/tmp"
"$AQ_HDIUTIL_BIN" attach -readonly -nobrowse -mountpoint "$mount_point" "$dmg" >/dev/null
mount_device=$(aq_identity "$dmg" "$mount_point") || {
  echo "attached DMG identity is unavailable" >&2
  exit 1
}
[ -d "$mount_point/Agent Quota.app" ] || { echo "DMG application is absent" >&2; exit 1; }

/usr/bin/ditto "$mount_point/Agent Quota.app" "$installed"
/usr/bin/codesign --verify --deep --strict "$installed"
launch_and_check
assert_persistent_state
launch_and_check
assert_persistent_state

/usr/bin/ditto "$installed" "$backup"
/bin/mv "$installed" "$test_root/replaced-app"
/usr/bin/ditto "$mount_point/Agent Quota.app" "$installed"
launch_and_check
assert_persistent_state
/bin/mv "$installed" "$test_root/upgraded-app"
/usr/bin/ditto "$backup" "$installed"
launch_and_check
assert_persistent_state

/bin/mv "$installed" "$test_root/uninstalled-app"
assert_persistent_state
/usr/bin/ditto "$mount_point/Agent Quota.app" "$installed"
launch_and_check
assert_persistent_state

cleanup
trap - EXIT HUP INT TERM
echo "macOS package lifecycle PASS"
echo "evidence_retention=none"
