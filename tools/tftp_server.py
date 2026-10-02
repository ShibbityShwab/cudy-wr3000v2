#!/usr/bin/env python3
import os
import socket
import struct
import sys

BLKSZ = 512


def parse_req(data):
    parts = data[2:].split(b"\x00")
    return parts[0].decode(errors="replace"), (parts[1].decode(errors="replace") if len(parts) > 1 else "octet")


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
    name, _ = parse_req(data)
    path = os.path.join(base, safe_name(name))
    if not os.path.isfile(path):
        print("RRQ miss " + name, flush=True)
        send_error(addr, 1, "File not found")
        return
    print("RRQ " + name + " -> " + path, flush=True)
    tsock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    tsock.bind(("0.0.0.0", 0))
    tsock.settimeout(3)
    try:
        blob = open(path, "rb").read()
        blk = 1
        off = 0
        while True:
            chunk = blob[off:off + BLKSZ]
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
            if len(chunk) < BLKSZ:
                print("RRQ sent " + str(len(blob)) + " bytes", flush=True)
                return
            blk = (blk + 1) & 0xFFFF
    finally:
        tsock.close()


def handle_wrq(data, addr, inbox):
    name, _ = parse_req(data)
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
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 6969
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
                handle_wrq(data, addr, inbox)
        except Exception as e:
            print("transfer error: " + repr(e), flush=True)


if __name__ == "__main__":
    main()
