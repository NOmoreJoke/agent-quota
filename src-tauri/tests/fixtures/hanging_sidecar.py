#!/usr/bin/env python3
"""Test-only child that authenticates launch, receives one frame, then hangs."""

import os
import struct
import sys
import time

with os.fdopen(int(os.environ["AQ_SESSION_SECRET_FD"]), "rb") as secret_stream:
    if len(secret_stream.read()) != 32:
        raise SystemExit(64)

header = sys.stdin.buffer.read(4)
if len(header) != 4:
    raise SystemExit(64)
length = struct.unpack(">I", header)[0]
if len(sys.stdin.buffer.read(length)) != length:
    raise SystemExit(64)
time.sleep(60)
