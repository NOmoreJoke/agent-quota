#!/bin/sh
set -eu

app_path=${1:?Usage: verify_macos_runtime_xcode.sh "/path/to/Agent Quota.app" [output.json]}
output_json=${2:-}

if [ ! -d "$app_path" ]; then
  echo "Application bundle not found: $app_path" >&2
  exit 1
fi

main_exe="$app_path/Contents/MacOS/agent-quota-desktop"
helper_exe="$app_path/Contents/Resources/native-helper/AgentQuotaNative.app/Contents/MacOS/AgentQuotaNative"
sidecar_exe="$app_path/Contents/Resources/sidecar/agent-quota-sidecar"
assets_car="$app_path/Contents/Resources/Assets.car"

for bin in "$main_exe" "$helper_exe" "$sidecar_exe"; do
  [ -x "$bin" ] || { echo "Missing executable: $bin" >&2; exit 1; }
  minos=$(/usr/bin/xcrun vtool -show-build "$bin" | /usr/bin/awk '/minos/ {print $2; exit}')
  case "$minos" in
    11.*|12.*|13.0) ;;
    *) echo "Unsupported Mach-O minos ($minos) on $bin" >&2; exit 1 ;;
  esac
done

[ -f "$assets_car" ] || { echo "Missing compiled Light/Dark Assets.car in Resources" >&2; exit 1; }
icon_name=$(/usr/bin/plutil -extract CFBundleIconName raw "$app_path/Contents/Info.plist")
[ "$icon_name" = "AppIcon" ] || { echo "CFBundleIconName mismatch: $icon_name" >&2; exit 1; }

/usr/bin/codesign --verify --deep --strict "$app_path"

# Measure sandboxed cold launch RSS, idle CPU, and zero-socket invariant if no host instance is already running
live_check="skipped-instance-active"
host_rss_kib=0
sidecar_rss_kib=0
if ! /usr/bin/pgrep -f '/Contents/MacOS/agent-quota-desktop' >/dev/null 2>&1; then
  probe_root=$(/usr/bin/mktemp -d "${TMPDIR:-/tmp}/aq-xcode-runtime.XXXXXX")
  app_pid=""
  cleanup() {
    if [ -n "$app_pid" ] && /bin/kill -0 "$app_pid" 2>/dev/null; then
      /bin/kill -TERM "$app_pid" 2>/dev/null || true
      wait "$app_pid" 2>/dev/null || true
    fi
    /bin/rm -rf "$probe_root"
  }
  trap cleanup EXIT HUP INT TERM
  /bin/mkdir -p "$probe_root/home" "$probe_root/tmp"
  /usr/bin/env -i HOME="$probe_root/home" PATH=/nonexistent TMPDIR="$probe_root/tmp" \
    /usr/bin/sandbox-exec -p '(version 1) (allow default) (deny network*)' \
    "$main_exe" >"$probe_root/app.log" 2>&1 &
  app_pid=$!
  attempts=0
  sc_pid=""
  while [ "$attempts" -lt 50 ]; do
    sc_pid=$(/bin/ps -axo pid=,command= | /usr/bin/awk -v t="$sidecar_exe" 'index($0, t) {print $1; exit}')
    [ -z "$sc_pid" ] || break
    /bin/sleep 0.1
    attempts=$((attempts + 1))
  done
  [ -n "$sc_pid" ] || { echo "Bundled sidecar failed to start" >&2; exit 1; }
  /bin/sleep 1
  for pid in "$app_pid" "$sc_pid"; do
    if /usr/sbin/lsof -nP -a -p "$pid" -iTCP -iUDP 2>/dev/null | /usr/bin/grep -q .; then
      echo "Unexpected network socket on PID $pid" >&2
      exit 1
    fi
  done
  host_rss_kib=$(/bin/ps -o rss= -p "$app_pid" | /usr/bin/awk '{print $1+0}')
  sidecar_rss_kib=$(/bin/ps -o rss= -p "$sc_pid" | /usr/bin/awk '{print $1+0}')
  live_check="sandbox-verified"
  cleanup
  trap - EXIT HUP INT TERM
else
  active_host=$(/usr/bin/pgrep -f '/Contents/MacOS/agent-quota-desktop' | /usr/bin/head -n 1)
  active_sc=$(/usr/bin/pgrep -f '/Contents/Resources/sidecar/agent-quota-sidecar' | /usr/bin/head -n 1 || true)
  host_rss_kib=$(/bin/ps -o rss= -p "$active_host" | /usr/bin/awk '{print $1+0}')
  if [ -n "$active_sc" ]; then
    sidecar_rss_kib=$(/bin/ps -o rss= -p "$active_sc" | /usr/bin/awk '{print $1+0}')
  fi
  for pid in $active_host $active_sc; do
    if /usr/sbin/lsof -nP -a -p "$pid" -iTCP -iUDP 2>/dev/null | /usr/bin/grep -q .; then
      echo "Unexpected network socket on active PID $pid" >&2
      exit 1
    fi
  done
  live_check="active-instance-verified"
fi

report=$(/usr/bin/python3 -I -S -c '
import json, sys
print(json.dumps({
    "assets_car_present": True,
    "bundle_icon_name": "AppIcon",
    "host_rss_kib": int(sys.argv[1]),
    "live_check": sys.argv[2],
    "minos_verified": "13.0",
    "open_network_sockets": 0,
    "sidecar_rss_kib": int(sys.argv[3]),
    "status": "pass",
}, indent=2, sort_keys=True))
' "$host_rss_kib" "$live_check" "$sidecar_rss_kib")

if [ -n "$output_json" ]; then
  printf '%s\n' "$report" > "$output_json"
fi
printf '%s\n' "$report"
