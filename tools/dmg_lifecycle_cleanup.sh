#!/bin/sh

aq_mount_line_present() {
  "$AQ_MOUNT_BIN" 2>/dev/null | /usr/bin/grep -F -- "$1 on $2 " >/dev/null 2>&1
}

aq_identity() {
  if [ -n "${3:-}" ]; then
    "$AQ_HDIUTIL_BIN" info -plist 2>/dev/null |
      "$AQ_PYTHON_BIN" "$AQ_IDENTITY_HELPER" --image "$1" --mount "$2" --device "$3"
  else
    "$AQ_HDIUTIL_BIN" info -plist 2>/dev/null |
      "$AQ_PYTHON_BIN" "$AQ_IDENTITY_HELPER" --image "$1" --mount "$2"
  fi
}

aq_cleanup_dmg() {
  image=$1
  mount_point=$2
  expected_device=${3:-}
  cleanup_device=

  set +e
  cleanup_device=$(aq_identity "$image" "$mount_point")
  identity_status=$?
  set -e
  if [ "$identity_status" -eq 2 ]; then
    echo "cannot prove DMG identity" >&2
    return 1
  fi
  if [ "$identity_status" -eq 1 ]; then
    if [ -n "$expected_device" ] && aq_mount_line_present "$expected_device" "$mount_point"; then
      echo "mount table and hdiutil identity disagree" >&2
      return 1
    fi
  else
    [ -z "$expected_device" ] || [ "$cleanup_device" = "$expected_device" ] || {
      echo "DMG device identity drift" >&2
      return 1
    }
    attempts=0
    while [ "$attempts" -lt 5 ]; do
      if "$AQ_HDIUTIL_BIN" detach "$cleanup_device" >/dev/null 2>&1; then
        break
      fi
      attempts=$((attempts + 1))
      "$AQ_SLEEP_BIN" 1
    done
    set +e
    remaining=$(aq_identity "$image" "$mount_point" "$cleanup_device")
    remaining_status=$?
    set -e
    if [ "$remaining_status" -eq 0 ]; then
      [ "$remaining" = "$cleanup_device" ] &&
        aq_mount_line_present "$cleanup_device" "$mount_point" || {
          echo "force detach identity unavailable" >&2
          return 1
        }
      "$AQ_HDIUTIL_BIN" detach -force "$cleanup_device" >/dev/null 2>&1 || return 1
    elif [ "$remaining_status" -eq 2 ]; then
      echo "cannot prove post-detach state" >&2
      return 1
    fi
  fi

  set +e
  aq_identity "$image" "$mount_point" >/dev/null
  final_identity_status=$?
  set -e
  [ "$final_identity_status" -eq 1 ] || {
    echo "DMG identity remains or is unreadable" >&2
    return 1
  }
  if [ -n "$expected_device" ] && aq_mount_line_present "$expected_device" "$mount_point"; then
    echo "DMG mount remains in mount table" >&2
    return 1
  fi
  /bin/rmdir "$mount_point" 2>/dev/null || {
    echo "DMG mount directory remains accessible or nonempty" >&2
    return 1
  }
}
