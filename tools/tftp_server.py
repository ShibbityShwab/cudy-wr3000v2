#!/usr/bin/env python3
import os
import socket
import struct
import sys

# RFC2348 blksize option: U-Boot's TFTP client asks for 1428-byte blocks on this board,
# so honouring it cuts a 20 MB recovery from ~41000 round trips to ~1500. Without the
# option we fall back to 512 as the RFC requires.
BLKSZ = 512
MAX_BLKSZ = 1468


def parse_req(data):
    parts = data[2:].split(b"\x00")
    name = parts[0].decode(errors="replace")
    mode = parts[1].decode(errors="replace") if len(parts) > 1 else "octet"
    opts = {}
    rest = parts[2:]
    for i in range(0, len(rest) - 1, 2):
        k = rest[i].decode(errors="replace").lower()
        v = rest[i + 1].decode(errors="replace")
        if k:
            opts[k] = v
    return name, mode, opts


def safe_name(name):
    s = os.path.normpath("/" + name.replace("\\", "/")).lstrip("/\\")
    if not s or s.startswith(".."):
        raise ValueError("bad name")
    return s


def send_error(addr, code, msg):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.sendto(struct.pack(">HH", 5, code) + msg.encode() + b"\x00", addr)
    finally:
        s.close()


def handle_rrq(data, addr, base):
    name, _mode, opts = parse_req(data)
    path = os.path.join(base, safe_name(name))
    if not os.path.isfile(path):
        print("RRQ miss " + name, flush=True)
        send_error(addr, 1, "File not found")
        return
    print("RRQ " + name + " -> " + path, flush=True)
    tsock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    tsock.bind(("0.0.0.0", 0))
    tsock.settimeout(6)
    blksz = BLKSZ
    try:
        want = opts.get("blksize")
        if want and want.isdigit():
            blksz = max(8, min(int(want), MAX_BLKSZ))
        blob = open(path, "rb").read()
        if blksz != BLKSZ:
            oack = struct.pack(">H", 6) + b"blksize\x00" + str(blksz).encode() + b"\x00"
            acked = False
            for _ in range(8):
                tsock.sendto(oack, addr)
                try:
                    ack, _a = tsock.recvfrom(1024)
                except socket.timeout:
                    continue
                if len(ack) >= 4 and struct.unpack(">HH", ack[:4]) == (4, 0):
                    acked = True
                    break
            if not acked:
                print("RRQ give up on OACK", flush=True)
                return
            print("RRQ blksize " + str(blksz), flush=True)
        blk = 1
        off = 0
        while True:
            chunk = blob[off:off + blksz]
            pkt = struct.pack(">HH", 3, blk) + chunk
            acked = False
            for _ in range(4):
                tsock.sendto(pkt, addr)
                try:
                    ack, _ = tsock.recvfrom(1024)
                except socket.timeout:
                    continue
                if len(ack) >= 4 and struct.unpack(">HH", ack[:4]) == (4, blk):
                    acked = True
                    break
            if not acked:
                print("RRQ give up at block " + str(blk), flush=True)
                return
            off += len(chunk)
            if len(chunk) < blksz:
                print("RRQ sent " + str(len(blob)) + " bytes", flush=True)
                return
            blk = (blk + 1) & 0xFFFF
    finally:
        tsock.close()


def handle_wrq(data, addr, inbox):
    name, _mode, _opts = parse_req(data)
    path = os.path.join(inbox, safe_name(name).replace("/", "_"))
    print("WRQ " + name + " -> " + path, flush=True)
    tsock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    tsock.bind(("0.0.0.0", 0))
    tsock.settimeout(6)
    try:
        f = open(path, "wb")
        try:
            tsock.sendto(struct.pack(">HH", 4, 0), addr)
            exp = 1
            total = 0
            while True:
                try:
                    pkt, _ = tsock.recvfrom(2048)
                except socket.timeout:
                    print("WRQ timeout", flush=True)
                    break
                if len(pkt) < 4:
                    continue
                op, blk = struct.unpack(">HH", pkt[:4])
                if op == 3 and blk == exp:
                    chunk = pkt[4:]
                    f.write(chunk)
                    total += len(chunk)
                    tsock.sendto(struct.pack(">HH", 4, blk), addr)
                    exp = (exp + 1) & 0xFFFF
                    if len(chunk) < BLKSZ:
                        print("WRQ received " + str(total) + " bytes", flush=True)
                        break
                elif op == 3:
                    tsock.sendto(struct.pack(">HH", 4, blk), addr)
        finally:
            f.close()
    finally:
        tsock.close()


def main():
    base = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tftp"))
    inbox = os.path.join(base, "inbox")
    os.makedirs(inbox, exist_ok=True)
    # Recovery only needs RRQ. Writes are root-owned file drops over an unauthenticated
    # UDP service, so WRQ is off unless the operator explicitly asks for it.
    allow_wrq = "--allow-wrq" in sys.argv[1:]
    port = next((int(a) for a in sys.argv[1:] if a.isdigit()), 6969)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("0.0.0.0", port))
    print("tftp server on 0.0.0.0:" + str(port) + " serving " + base, flush=True)
    while True:
        try:
            data, addr = s.recvfrom(2048)
        except Exception:
            continue
        if len(data) < 2:
            continue
        op = struct.unpack(">H", data[:2])[0]
        try:
            if op == 1:
                handle_rrq(data, addr, base)
            elif op == 2:
                if allow_wrq:
                    handle_wrq(data, addr, inbox)
                else:
                    print("WRQ denied (start with --allow-wrq to permit uploads)", flush=True)
                    send_error(addr, 2, "WRQ disabled")
        except Exception as e:
            print("transfer error: " + repr(e), flush=True)


if __name__ == "__main__":
    main()
