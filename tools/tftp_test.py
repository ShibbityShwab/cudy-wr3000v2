#!/usr/bin/env python3
import hashlib
import os
import socket
import struct
import sys
import time

HOST = "127.0.0.1"
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 6969
BASE = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tftp"))


def get(remote, local):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(4)
    req = struct.pack(">H", 1) + remote.encode() + b"\x00octet\x00"
    s.sendto(req, (HOST, PORT))
    out = open(local, "wb")
    exp = 1
    while True:
        pkt, addr = s.recvfrom(2048)
        op, blk = struct.unpack(">HH", pkt[:4])
        if op == 5:
            raise RuntimeError("server error: " + pkt[4:].decode())
        if op == 3 and blk == exp:
            out.write(pkt[4:])
            s.sendto(struct.pack(">HH", 4, blk), addr)
            if len(pkt[4:]) < 512:
                break
            exp = (exp + 1) & 0xFFFF
    out.close()
    s.close()


def put(local, remote):
    blob = open(local, "rb").read()
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(4)
    req = struct.pack(">H", 2) + remote.encode() + b"\x00octet\x00"
    s.sendto(req, (HOST, PORT))
    ack, addr = s.recvfrom(1024)
    assert struct.unpack(">HH", ack[:4]) == (4, 0)
    blk = 1
    off = 0
    while True:
        chunk = blob[off:off + 512]
        pkt = struct.pack(">HH", 3, blk) + chunk
        for _ in range(4):
            s.sendto(pkt, addr)
            try:
                ack, _ = s.recvfrom(1024)
            except socket.timeout:
                continue
            if struct.unpack(">HH", ack[:4]) == (4, blk):
                break
        off += len(chunk)
        if len(chunk) < 512:
            break
        blk = (blk + 1) & 0xFFFF
    s.close()


def main():
    src = os.path.join(BASE, "serve_test.bin")
    payload = os.urandom(1500)
    open(src, "wb").write(payload)
    time.sleep(0.3)
    get("serve_test.bin", os.path.join(BASE, "got_test.bin"))
    got = open(os.path.join(BASE, "got_test.bin"), "rb").read()
    print("GET ok:", got == payload, len(got))
    up = os.path.join(BASE, "put_src.bin")
    open(up, "wb").write(payload[:1300])
    put(up, "put_result.bin")
    time.sleep(0.6)
    dst = os.path.join(BASE, "inbox", "put_result.bin")
    rx = open(dst, "rb").read() if os.path.exists(dst) else b""
    print("PUT ok:", rx == payload[:1300], len(rx))
    print("sha src:", hashlib.sha256(payload).hexdigest()[:16], "sha rx:", hashlib.sha256(rx).hexdigest()[:16])


if __name__ == "__main__":
    main()
