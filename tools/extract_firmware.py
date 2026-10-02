#!/usr/bin/env python3
"""
extract_firmware.py — unpack a Cudy WR3000 2.0 sysupgrade image.

The .bin inside Cudy's sysupgrade.zip is an `hboot1tag` flash container:
custom header, bootloader blob, a uImage kernel, and a UBI region whose
root filesystem volume is a static squashfs. Each UBI PEB is 131072 bytes
with a 4096-byte header, so the squashfs must be reassembled PEB-by-EB
before unsquashfs can read it.

Verified against WR3000V2 firmware 2.4.14 / 2.4.15 / 2.5.24 images.
Research context: CVE-2026-71960 (hard-coded JWT secret, CWE-798).

Usage:
    python3 extract_firmware.py <image.bin> [--out DIR] [--keep-sqfs]

Requires: unsquashfs (squashfs-tools) on PATH when --out is given.
Authorised research only — run against images you legitimately obtained.
"""
import argparse
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile

PEB = 131072          # UBI physical erase block size on this device
UBI_HDR = 4096        # EC/VID header area at the start of every PEB
HSQS = b"hsqs"        # squashfs 4.0 little-endarian magic
UIMAGE = b"\x27\x05\x19\x56"


def uimage_info(data, off):
    hdr = data[off:off + 64]
    size, load, ep = struct.unpack(">III", hdr[12:24])
    name = hdr[32:64].rstrip(b"\0").decode(errors="replace")
    return name, size, load, ep


def find_squashfs(data):
    for m in re.finditer(re.escape(HSQS), data):
        off = m.start()
        inodes = struct.unpack_from("<I", data, off + 4)[0]
        bytes_used = struct.unpack_from("<Q", data, off + 40)[0]
        if inodes > 100 and 0 < bytes_used < len(data):
            return off, inodes, bytes_used
    return None, None, None


def reassemble(data, fs_off, bytes_used):
    """Concatenate the payload half of every UBI PEB from fs_off's PEB on."""
    peb_start = fs_off - UBI_HDR
    out = bytearray()
    i = 0
    while True:
        base = peb_start + i * PEB
        if data[base:base + 4] != b"UBI#":
            break
        out += data[base + UBI_HDR:base + PEB]
        i += 1
        if len(out) >= bytes_used:
            break
    return bytes(out[:bytes_used])


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("image")
    ap.add_argument("--out", help="directory to extract the filesystem into")
    ap.add_argument("--keep-sqfs", action="store_true",
                    help="keep the reassembled rootfs.sqfs next to the image")
    args = ap.parse_args()

    data = open(args.image, "rb").read()
    print(f"[*] {args.image}: {len(data)} bytes")
    if not data.startswith(b"hboot1tag"):
        print("[!] warning: no hboot1tag magic — continuing anyway")

    for m in re.finditer(re.escape(UIMAGE), data):
        name, size, load, _ = uimage_info(data, m.start())
        if 0 < size < len(data) and name.isprintable() and "Linux" in name:
            print(f"[*] uImage kernel @ {m.start()} (#x%x): '{name}' "
                  f"({size} bytes, load #x%x)" % (m.start(), load))
            break

    fs_off, inodes, bytes_used = find_squashfs(data)
    if fs_off is None:
        sys.exit("[!] no squashfs superblock found — not a Cudy sysupgrade image?")
    print(f"[*] squashfs @ {fs_off} (PEB {fs_off - UBI_HDR}): "
          f"inodes={inodes}, bytes_used={bytes_used}")

    sqfs = reassemble(data, fs_off, bytes_used)
    print(f"[*] reassembled {len(sqfs)} bytes from UBI PEBs")
    if sqfs[:4] != HSQS:
        sys.exit("[!] reassembly failed (bad magic)")

    sqfs_path = args.image + ".sqfs" if args.keep_sqfs else \
        os.path.join(tempfile.mkdtemp(), "rootfs.sqfs")
    open(sqfs_path, "wb").write(sqfs)
    print(f"[+] {sqfs_path} written")

    if args.out:
        if not shutil.which("unsquashfs"):
            sys.exit("[!] unsquashfs not found (install squashfs-tools)")
        subprocess.run(["unsquashfs", "-d", args.out, sqfs_path], check=True)
        print(f"[+] filesystem extracted to {args.out}/")
        for rel in ("usr/lib/auth_plugin_jwt.so", "usr/lib/libbdinfo.so",
                    "etc/mosquitto/mosquitto.conf"):
            p = os.path.join(args.out, rel)
            print(f"    {'[+] ' if os.path.exists(p) else '[!] missing '}{rel}")


if __name__ == "__main__":
    main()
