#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
dmg=${1:-"$repo_root/artifacts/iteration-4/Agent-Quota-0.1.0-arm64-local-unsigned.dmg"}
test_root=$(mktemp -d /private/var/tmp/agent-quota-i4-lifecycle.XXXXXX)
mount_point="$test_root/mount"
applications="$test_root/Applications"
installed="$applications/Agent Quota.app"
backup="$test_root/rollback/Agent Quota.app"
data_root="$test_root/home/Library/Application Support/com.agentquota.desktop"
main_pid=
mount_device=

cleanup() {
  if [ -n "$main_pid" ] && /bin/kill -0 "$main_pid" 2>/dev/null; then
    /bin/kill -TERM "$main_pid" 2>/dev/null || true
    wait "$main_pid" 2>/dev/null || true
  fi
  if [ -n "$mount_device" ]; then
    /usr/bin/hdiutil detach "$mount_device" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT HUP INT TERM

launch_and_check() {
  executable="$installed/Contents/MacOS/agent-quota-desktop"
  sidecar="$installed/Contents/Resources/sidecar/agent-quota-sidecar"
  if [ ! -x "$executable" ] || [ ! -x "$sidecar" ]; then
    echo "installed bundle is incomplete" >&2
    exit 1
  fi
  /usr/bin/env -i \
    HOME="$test_root/home" \
    PATH=/nonexistent \
    TMPDIR="$test_root/tmp" \
    /usr/bin/sandbox-exec \
    -p '(version 1) (allow default) (deny network*)' \
    "$executable" >"$test_root/app.log" 2>&1 &
  main_pid=$!
  attempts=0
  while [ "$attempts" -lt 50 ]; do
    if ! /bin/kill -0 "$main_pid" 2>/dev/null; then
      echo "application exited during launch" >&2
      exit 1
    fi
    sidecar_pid=$(
      /bin/ps -axo pid=,command= |
        /usr/bin/awk -v target="$sidecar" 'index($0, target) {print $1; exit}'
    )
    if [ -n "$sidecar_pid" ]; then
      break
    fi
    /bin/sleep 0.1
    attempts=$((attempts + 1))
  done
  if [ -z "${sidecar_pid:-}" ]; then
    echo "bundled sidecar did not start" >&2
    exit 1
  fi
  for pid in "$main_pid" "$sidecar_pid"; do
    if /usr/sbin/lsof -nP -a -p "$pid" -iTCP -iUDP 2>/dev/null |
      /usr/bin/grep -q .; then
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
attach=$(
  /usr/bin/hdiutil attach -readonly -nobrowse -mountpoint "$mount_point" "$dmg"
)
mount_device=$(printf '%s\n' "$attach" | /usr/bin/awk 'NR == 1 {print $1}')
if [ ! -d "$mount_point/Agent Quota.app" ]; then
  echo "DMG does not contain Agent Quota.app" >&2
  exit 1
fi

# Install and relaunch.
/usr/bin/ditto "$mount_point/Agent Quota.app" "$installed"
/usr/bin/codesign --verify --deep --strict "$installed"
launch_and_check
launch_and_check

# Upgrade replacement and rollback preserve application data.
/bin/mkdir -p "$data_root"
/usr/bin/touch "$data_root/lifecycle-sentinel"
/usr/bin/ditto "$installed" "$backup"
/bin/mv "$installed" "$test_root/replaced-app"
/usr/bin/ditto "$mount_point/Agent Quota.app" "$installed"
launch_and_check
if [ ! -f "$data_root/lifecycle-sentinel" ]; then
  echo "upgrade removed application data" >&2
  exit 1
fi
/bin/mv "$installed" "$test_root/upgraded-app"
/usr/bin/ditto "$backup" "$installed"
launch_and_check

# Normal uninstall preserves data; reinstall remains launchable.
/bin/mv "$installed" "$test_root/uninstalled-app"
if [ ! -f "$data_root/lifecycle-sentinel" ]; then
  echo "uninstall removed application data" >&2
  exit 1
fi
/usr/bin/ditto "$mount_point/Agent Quota.app" "$installed"
launch_and_check

echo "macOS package lifecycle PASS"
echo "evidence_root=$test_root"
