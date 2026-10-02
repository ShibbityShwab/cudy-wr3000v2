#!/usr/bin/env python3
import os
import re
import struct
import sys
import zipfile
from collections import defaultdict

from Crypto.Cipher import DES

PEB, UBI_HDR = 131072, 4096
HSQS = b"hsqs"


def parity(b):
    out = bytearray()
    for x in b:
        x &= 0xFE
        p = bin(x).count("1") & 1
        out.append(x | (1 - p))
    return bytes(out)


def des_string_to_key(s: bytes) -> bytes:
    if len(s) % 2:
        s = s + b"\x00"
    temp = bytearray(8)
    for i, ch in enumerate(s):
        temp[i % 8] ^= (ch << 1) & 0xFF
        if i >= 8:
            temp[7 - (i % 8)] ^= ch
    temp = parity(temp)
    cbc = DES.new(b"\x00" * 8, DES.MODE_CBC, b"\x00" * 8)
    return parity(cbc.encrypt(temp))


KEY = des_string_to_key(b"88T3j05dtFu8=")
print(f"[*] bdinfo DES key: {KEY.hex()}")


def try_des(data, off, n=1024):
    cbc = DES.new(KEY, DES.MODE_CBC, b"\x00" * 8)
    chunk = data[off:off + n]
    pad = (-len(chunk)) % 8
    return cbc.decrypt(chunk + b"\x00" * pad)[:len(chunk)]


def scan_blobs(data, label, cap=8):
    n = len(data) // 8 * 8
    dec = DES.new(KEY, DES.MODE_ECB).decrypt(data[:n])
    hits = []
    for m in re.finditer(rb"[a-z_]{2,14} = [\x21-\x7e]", dec):
        if m.start() % 8 == 0:
            hits.append(m.start())
            if len(hits) >= cap:
                break
    print(f"[*] {label}: DES blob hits at {[hex(h) for h in hits]}")
    for h in hits[:4]:
        pt = try_des(data, h)
        kv = dict(re.findall(rb"([A-Za-z_]{2,16})\s*=\s*([^\r\n\x00]{0,64})", pt))
        shown = {k.decode("latin1"): v.decode("latin1") for k, v in kv.items()}
        print(f"    @{hex(h)}: {shown if shown else pt[:96]!r}")
    return hits


def load(path):
    if path.lower().endswith(".zip"):
        z = zipfile.ZipFile(path)
        name = [n for n in z.namelist() if n.lower().endswith(".bin")][0]
        print(f"[*] zip member: {name} ({z.getinfo(name).file_size} bytes)")
        return z.read(name)
    return open(path, "rb").read()


def main():
    path = sys.argv[1]
    data = load(path)
    print(f"[*] {path}: {len(data)} bytes; magic={data[:10]!r}")

    for m in re.finditer(re.escape(b"\x27\x05\x19\x56"), data):
        hdr = data[m.start():m.start() + 64]
        size, loadaddr, _ = struct.unpack(">III", hdr[12:24])
        name = hdr[32:64].rstrip(b"\0")
        if 0 < size < len(data):
            print(f"[*] uImage @ {hex(m.start())} {name!r} size={size}")
            break

    fs = None
    for m in re.finditer(re.escape(HSQS), data):
        o = m.start()
        inodes = struct.unpack_from("<I", data, o + 4)[0]
        bytes_used = struct.unpack_from("<Q", data, o + 40)[0]
        if inodes > 100 and 0 < bytes_used < len(data):
            fs = (o, inodes, bytes_used)
            break
    if fs:
        o, inodes, used = fs
        print(f"[*] squashfs @ {hex(o)} inodes={inodes} used={used}")
        start = o - UBI_HDR
        out = bytearray()
        i = 0
        while True:
            base = start + i * PEB
            if data[base:base + 4] != b"UBI#":
                break
            out += data[base + UBI_HDR:base + PEB]
            i += 1
            if len(out) >= used:
                break
        sq = bytes(out[:used])
        outp = path + ".rootfs.sqfs"
        open(outp, "wb").write(sq)
        print(f"[+] wrote {outp} ({len(sq)} bytes, ok={sq[:4] == HSQS})")

        vols = defaultdict(list)
        i = 0
        while True:
            b = start + i * PEB
            if b + PEB > len(data):
                break
            if data[b:b + 4] == b"UBI#" and data[b + 64:b + 68] == b"UBI!":
                volid = struct.unpack(">I", data[b + 72:b + 76])[0]
                lnum = struct.unpack(">I", data[b + 76:b + 80])[0]
                vols[volid].append((lnum, b))
            i += 1
        print("[*] UBI volumes: " + ", ".join(f"vol{v}: {len(p)} PEBs" for v, p in sorted(vols.items())))
        for v, p in sorted(vols.items()):
            _, b = sorted(p)[0]
            print(f"    vol{v} first payload: {data[b + UBI_HDR:b + UBI_HDR + 48]!r}")

    for pat in (b"bdinfo", b"deviceid", b"secret"):
        offs = [hex(m.start()) for m in list(re.finditer(re.escape(pat), data))[:5]]
        print(f"[*] raw '{pat.decode()}': {offs}")

    scan_blobs(data, os.path.basename(path))

    bp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "pages", "backup.bin")
    if os.path.exists(bp):
        b = open(bp, "rb").read()
        print(f"[*] backup.bin {len(b)} bytes, head {b[:12].hex()}")
        for off in (0, 2):
            pt = try_des(b, off, 128)
            print(f"    des@{off}: {pt[:96]!r}")
        scan_blobs(b, "backup.bin")


if __name__ == "__main__":
    main()
