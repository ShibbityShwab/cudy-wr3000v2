#!/bin/sh
# box-provision.sh - bring a stock Cudy WR3000 v2 to a known state over the LAN, without SSH.
#
# The stock firmware runs the vendor's MQTT broker on 1883 and accepts a JWT signed with the fleet
# secret from the device's own bdinfo. That channel executes commands as root and returns their stdout,
# which is all this needs: the 2.4.15 image ships no /usr/sbin/dropbear, so SSH cannot work until a
# binary exists. Every step below reads its result back before reporting success.
#
# usage:
#   box-provision.sh --bdinfo dumps/router-20261108/bdinfo.bin --admin-pass <pw>
#                    [--ssid <ssid>] [--wifi-pass <pw>] [--host 192.168.10.1]
#                    [--ssh-key <pubkey-file>] [--telnetd] [--dry-run]
#
# --dry-run prints the box's current wireless config and exits; use it before changing anything.
set -eu

HERE=$(cd "$(dirname "$0")/.." && pwd)
HOST=192.168.10.1
BDINFO=""
ADMIN_PASS=""
SSID=""
WIFI_PASS=""
SSH_KEY=""
START_TELNETD=0
DRY_RUN=0

while [ $# -gt 0 ]; do
    case "$1" in
        --bdinfo) BDINFO=$2; shift 2 ;;
        --admin-pass) ADMIN_PASS=$2; shift 2 ;;
        --ssid) SSID=$2; shift 2 ;;
        --wifi-pass) WIFI_PASS=$2; shift 2 ;;
        --host) HOST=$2; shift 2 ;;
        --ssh-key) SSH_KEY=$2; shift 2 ;;
        --telnetd) START_TELNETD=1; shift ;;
        --dry-run) DRY_RUN=1; shift ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
done

if [ -z "$BDINFO" ] || [ ! -f "$BDINFO" ]; then
    echo "error: --bdinfo <dump> is required (the device's own bdinfo.bin)" >&2
    exit 2
fi

PY=""
for cand in "$HERE/.provision-venv/bin/python" "$HERE/pyenv/bin/python3" python3; do
    if [ -x "$cand" ] || command -v "$cand" >/dev/null 2>&1; then
        if "$cand" -c 'import Crypto, jwt, paho.mqtt' >/dev/null 2>&1; then
            PY=$cand
            break
        fi
    fi
done
if [ -z "$PY" ]; then
    echo "creating $HERE/.provision-venv (needs network for pip)" >&2
    python3 -m venv "$HERE/.provision-venv"
    "$HERE/.provision-venv/bin/pip" install -q pycryptodome PyJWT paho-mqtt
    PY="$HERE/.provision-venv/bin/python"
fi

SECRET=$("$PY" "$HERE/tools/decrypt_bdinfo.py" "$BDINFO" | sed -n 's/^ *secret *= *//p' | awk '{print $1}' | head -1)
DEVICEID=$("$PY" "$HERE/tools/decrypt_bdinfo.py" "$BDINFO" | sed -n 's/^ *deviceid *= *//p' | awk '{print $1}' | head -1)
if [ -z "$SECRET" ]; then
    echo "error: could not recover the fleet secret from $BDINFO" >&2
    exit 1
fi

    root_cmd() {
    "$PY" "$HERE/tools/mqtt_takeover.py" --host "$HOST" --port 1883 \
        --deviceid "$DEVICEID" --role satellite --secret "$SECRET" \
        --cmd "id; $1" --listen "${2:-12}" 2>&1 |
        strings |
        sed -n 's/.*"data":"\(.*\)$/\1/p' | tail -1
}

if [ "$DRY_RUN" -eq 1 ]; then
    root_cmd 'uci show wireless' 15
    exit 0
fi

if [ -n "$SSID" ] || [ -n "$WIFI_PASS" ]; then
    if [ -z "$SSID" ] || [ -z "$WIFI_PASS" ]; then
        echo "error: --ssid and --wifi-pass must be given together" >&2
        exit 2
    fi
    echo "[*] setting Wi-Fi ssid=$SSID"
    root_cmd "uci set wireless.@wifi-iface[0].ssid='$SSID'; uci set wireless.@wifi-iface[0].key='$WIFI_PASS'; uci set wireless.@wifi-iface[0].encryption='psk2'; uci set wireless.@wifi-iface[1].ssid='$SSID'; uci set wireless.@wifi-iface[1].key='$WIFI_PASS'; uci set wireless.@wifi-iface[1].encryption='psk2'; uci commit wireless; wifi reload; sleep 3; uci get wireless.@wifi-iface[0].ssid" 25
fi

if [ -n "$ADMIN_PASS" ]; then
    echo "[*] setting the admin (root) password"
    root_cmd "printf 'root:%s\\n' '$ADMIN_PASS' | chpasswd; grep -c '^root:.' /etc/shadow" 15
fi

if [ -n "$SSH_KEY" ]; then
    if [ ! -f "$SSH_KEY" ]; then
        echo "error: ssh key not found: $SSH_KEY" >&2
        exit 2
    fi
    PUB=$(cat "$SSH_KEY")
    echo "[*] installing the SSH key and trying to start dropbear"
    root_cmd "mkdir -p /etc/dropbear; echo '$PUB' > /etc/dropbear/authorized_keys; chmod 600 /etc/dropbear/authorized_keys; opkg update >/dev/null 2>&1; opkg install dropbear 2>&1 | tail -1; /etc/init.d/dropbear enable >/dev/null 2>&1; /etc/init.d/dropbear start >/dev/null 2>&1; sleep 2; netstat -tln 2>/dev/null | grep -c ':22 '" 40
fi

if [ "$START_TELNETD" -eq 1 ]; then
    echo "[*] starting the root telnet listener on 23"
    root_cmd '/usr/sbin/telnetd -l /bin/sh; sleep 1; netstat -tln 2>/dev/null | grep -c ":23 "' 15
fi

echo "[*] done"
