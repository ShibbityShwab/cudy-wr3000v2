#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Run shell command lines over the stock firmware root telnet shell."""
import argparse
import socket
import sys
import time

p = argparse.ArgumentParser()
p.add_argument("--host", default="192.168.10.1")
p.add_argument("--port", type=int, default=23)
p.add_argument("--timeout", type=float, default=180.0)
p.add_argument("cmds", nargs=argparse.REMAINDER)
a = p.parse_args()
cmds = a.cmds
if cmds and cmds[0] == "--":
    cmds = cmds[1:]
if not cmds:
    print("usage: telnet-exec.py --host H -- <command>...", file=sys.stderr)
    sys.exit(2)
script = "\n".join(cmds) + "\necho __ALL_DONE__\nexit\n"
s = socket.create_connection((a.host, a.port), 8)
s.settimeout(2.0)
time.sleep(0.3)
try:
    s.recv(65536)
except OSError:
    pass
s.settimeout(a.timeout)
s.sendall(script.encode())
buf = b""
deadline = time.time() + a.timeout
while time.time() < deadline:
    try:
        d = s.recv(65536)
    except socket.timeout:
        continue
    if not d:
        break
    buf += d
    if b"__ALL_DONE__" in buf:
        break
s.close()
sys.stdout.write(buf.decode("utf-8", "replace"))
