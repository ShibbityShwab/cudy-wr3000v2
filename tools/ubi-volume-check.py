#!/usr/bin/env python3
"""ubi-volume-check.py - semantic UBI volume compare for the first-install read-back.

Raw-partition hashes cannot match a ubinize image after ubiformat: the tool rewrites
the EC header image_seq (and its CRC) per PEB, and may refresh erase counters. This
compares the actual static volume payload: for each PEB with a matching volume id it
records (lnum, data_size) and lays the data bytes out in LNM order, then hashes that.

usage: ubi-volume-check.py --expected IMAGE --readback MTD_READBACK [--volume-id N]
"""
import argparse, hashlib, struct, sys

PEB_MAGIC = b"UBI#"
VID_MAGIC = b"UBI!"
EC_HDR = 64
VID_HDR = 64


def parse(buf, peb_size, volume_id=None):
    if len(buf) % peb_size:
        raise SystemExit("readback size %d is not a multiple of PEB %d" % (len(buf), peb_size))
    pieces = {}
    used_ebs = None
    data_pad = None
    for i in range(0, len(buf), peb_size):
        eb = buf[i:i + peb_size]
        if eb[:4] != PEB_MAGIC:
            if eb[:4] == b"\xff" * 4 or not eb[:4]:
                continue  # erased or padding PEB
            raise SystemExit("PEB %d has no UBI# EC magic" % (i // peb_size))
        vid_off = struct.unpack(">I", eb[16:20])[0]
        data_off = struct.unpack(">I", eb[20:24])[0]
        vid = eb[vid_off:vid_off + VID_HDR]
        if vid[:4] != VID_MAGIC:
            # ubiformat writes an EC header on every PEB of the formatted partition but
            # only the used volumes carry VID headers; the rest are erased formatting PEBs.
            if eb[vid_off:] == b"\xff" * (peb_size - vid_off):
                continue
            raise SystemExit("PEB %d has a UBI# EC header but no UBI! VID magic" % (i // peb_size))
        vtype, copy_flag, compat = vid[5], vid[6], vid[7]
        vol_id = struct.unpack(">I", vid[8:12])[0]
        lnum = struct.unpack(">I", vid[12:16])[0]
        dsize = struct.unpack(">I", vid[20:24])[0]
        uebs = struct.unpack(">I", vid[24:28])[0]
        dpad = struct.unpack(">I", vid[28:32])[0]
        if vol_id == 0x7FFFEFFF:  # UBI internal layout volume (volume table)
            continue
        if volume_id is not None and vol_id != volume_id:
            continue
        if vol_id not in pieces:
            pieces[vol_id] = {}
            used_ebs = used_ebs or uebs
            data_pad = data_pad if data_pad is not None else dpad
        pieces[vol_id][lnum] = eb[data_off:data_off + dsize]
    out = {}
    for vol, lm in pieces.items():
        expected_lnums = set(range(used_ebs if used_ebs else len(lm)))
        have = set(lm)
        if expected_lnums - have:
            raise SystemExit("volume %d missing LEBs %s" % (vol, sorted(expected_lnums - have)[:8]))
        payload = b"".join(lm[n] for n in range(used_ebs if used_ebs else len(lm)))
        if data_pad is not None and data_pad:
            payload = payload  # data_pad bytes at the end of the volume are not payload
        out[vol] = (used_ebs, data_pad, hashlib.sha256(payload).hexdigest(), len(payload))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--expected", required=True)
    ap.add_argument("--readback", required=True)
    ap.add_argument("--peb-size", type=lambda x: int(x, 0), default=131072)
    ap.add_argument("--volume-id", type=int, default=None)
    a = ap.parse_args()
    exp = parse(open(a.expected, "rb").read(), a.peb_size, a.volume_id)
    got = parse(open(a.readback, "rb").read(), a.peb_size, a.volume_id)
    ok = True
    for vol in sorted(set(exp) | set(got)):
        e = exp.get(vol)
        g = got.get(vol)
        if e is None or g is None:
            print("FAIL volume %s: present only in %s" % (vol, "image" if e else "readback"))
            ok = False
            continue
        same = e[0] == g[0] and e[1] == g[1] and e[2] == g[2]
        print("%s volume %d: used_ebs %s/%s data_pad %s/%s payload %s/%s sha %s" % (
            "PASS" if same else "FAIL", vol, e[0], g[0], e[1], g[1],
            e[3], g[3], e[2][:16] + ("=" + g[2][:16] if same else " != " + g[2][:16])))
        ok = ok and same
    if not exp:
        print("FAIL: no volume found in the expected image")
        ok = False
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
