#!/usr/bin/env python3
import sys

from Crypto.Cipher import DES


def parity(b):
    out = bytearray()
    for x in b:
        x &= 0xFE
        p = bin(x).count("1") & 1
        out.append(x | (1 - p))
    return bytes(out)


def des_string_to_key(s):
    if len(s) % 2:
        s += b"\x00"
    temp = bytearray(8)
    for i, ch in enumerate(s):
        temp[i % 8] ^= (ch << 1) & 0xFF
        if i >= 8:
            temp[7 - (i % 8)] ^= ch
    cbc = DES.new(b"\x00" * 8, DES.MODE_CBC, b"\x00" * 8)
    return parity(cbc.encrypt(parity(temp)))


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "fake_bdinfo.bin"
    key = des_string_to_key(b"88T3j05dtFu8=")
    lines = [
        # documentation example MAC; the lab unit's per-unit MAC was redacted 2026-11-18
        "mac = 02:00:00:00:00:01",
        "sn = 2543XXXXXX",
        "deviceid = 000000000000",
        "secret = FAKE-SECRET-FOR-ROUNDTRIP",
        "fuuid = 0",
    ]
    pt = ("\n".join(lines) + "\n").encode()
    pad = (-len(pt)) % 8
    cbc = DES.new(key, DES.MODE_CBC, b"\x00" * 8)
    with open(out, "wb") as fh:
        fh.write(cbc.encrypt(pt + b"\x00" * pad))
    print("fake bdinfo written", len(pt) + pad, "bytes", "to", out)


if __name__ == "__main__":
    main()
