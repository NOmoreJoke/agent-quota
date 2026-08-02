#!/usr/bin/env python3
"""Resolve one exact hdiutil image/device/mount identity from a bounded plist."""

from __future__ import annotations

import argparse
import os
import plistlib
import sys
from typing import cast

MAX_PLIST_BYTES = 2 * 1024 * 1024


def identities(document: object) -> list[tuple[str, str, str]]:
    if not isinstance(document, dict):
        raise ValueError("plist root mismatch")
    rows: list[tuple[str, str, str]] = []
    images = document.get("images")
    if not isinstance(images, list):
        raise ValueError("hdiutil images mismatch")
    for image in images:
        if not isinstance(image, dict) or not isinstance(image.get("image-path"), str):
            raise ValueError("hdiutil image mismatch")
        image_path = os.path.realpath(cast(str, image["image-path"]))
        entities = image.get("system-entities")
        if not isinstance(entities, list):
            raise ValueError("hdiutil entities mismatch")
        for entity in entities:
            if not isinstance(entity, dict):
                raise ValueError("hdiutil entity mismatch")
            device = entity.get("dev-entry")
            mount = entity.get("mount-point")
            if isinstance(device, str) and isinstance(mount, str):
                rows.append((image_path, device, os.path.realpath(mount)))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True)
    parser.add_argument("--mount", required=True)
    parser.add_argument("--device")
    args = parser.parse_args()
    raw = sys.stdin.buffer.read(MAX_PLIST_BYTES + 1)
    if not raw or len(raw) > MAX_PLIST_BYTES:
        return 2
    try:
        document = plistlib.loads(raw)
        matches = [
            row
            for row in identities(document)
            if row[0] == os.path.realpath(args.image)
            and row[2] == os.path.realpath(args.mount)
            and (args.device is None or row[1] == args.device)
        ]
    except (OSError, ValueError, plistlib.InvalidFileException):
        return 2
    if not matches:
        return 1
    if len(matches) != 1:
        return 2
    print(matches[0][1])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
