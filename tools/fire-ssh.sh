#!/usr/bin/env bash
# fire-ssh.sh - generic SSH fire driver: stage, fire, poll, read.
set -uo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
RSH="$ROOT/tools/rsh.sh"
RSCP="$ROOT/tools/rscp.sh"
HOST=${ROUTER_HOST:-root@192.168.10.1}
SLICE=""
DEVICE_SCRIPT="$ROOT/tools/fire-device.sh"
LABEL="manual"

while [ $# -gt 0 ]; do
    case "$1" in
        --slice) SLICE=$2; shift 2 ;;
        --device-script) DEVICE_SCRIPT=$2; shift 2 ;;
        --label) LABEL=$2; shift 2 ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
done

[ -n "$SLICE" ] && [ -f "$SLICE" ] || {
    echo "usage: fire-ssh.sh --slice <path> [--device-script <path>] [--label <name>]" >&2
    exit 2
}
[ -f "$DEVICE_SCRIPT" ] || { echo "missing device script: $DEVICE_SCRIPT" >&2; exit 2; }

TRAILER="$ROOT/build/linux-kbuild/slice-trailer-40732.bin"
if [ -f "$TRAILER" ]; then
    if ! tail -c 40732 "$SLICE" | cmp -s - "$TRAILER"; then
        echo "error: slice trailer mismatch: $SLICE" >&2
        exit 2
    fi
fi

SIZE=$(stat -c %s "$SLICE")
MD5=$(md5sum "$SLICE" | awk '{print $1}')
echo "slice: $SLICE ($SIZE bytes, md5 $MD5)"
echo "label: $LABEL"

if ! "$RSH" 'cat /proc/uptime' >/dev/null 2>&1; then
    echo "error: preflight SSH unreachable" >&2
    exit 1
fi

REMOTE_SLICE="/tmp/slice-$LABEL.bin"
REMOTE_SCRIPT="/tmp/fire-$LABEL.sh"

"$RSCP" "$SLICE" "$HOST:$REMOTE_SLICE" || { echo "scp slice failed" >&2; exit 1; }
"$RSCP" "$DEVICE_SCRIPT" "$HOST:$REMOTE_SCRIPT" || { echo "scp device script failed" >&2; exit 1; }

REMOTE_MD5=$("$RSH" "md5sum $REMOTE_SLICE | awk '{print \$1}'")
if [ "$REMOTE_MD5" != "$MD5" ]; then
    echo "error: remote md5 mismatch: $REMOTE_MD5 != $MD5" >&2
    exit 1
fi
echo "staged and verified"

"$RSH" "SLICE=$REMOTE_SLICE sh $REMOTE_SCRIPT" 2>&1 || true

echo "waiting for the vendor slot"
BACK=0
for i in $(seq 1 150); do
    OUT=$("$RSH" 'printf "UP=%s HI=%s\n" "$(cut -d. -f1 /proc/uptime)" "$(lsmod | grep -c "^hi_")"' 2>/dev/null | tail -1)
    UP=${OUT#UP=}
    UP=${UP%% *}
    HI=${OUT#*HI=}
    case "$UP" in ''|*[!0-9]*) UP=0 ;; esac
    case "$HI" in ''|*[!0-9]*) HI=0 ;; esac
    echo "poll $i: up=$UP hi=$HI"
    if [ "$UP" -gt 0 ] && [ "$UP" -lt 400 ] && [ "$HI" -gt 5 ]; then
        BACK=1
        echo "VENDOR_BACK"
        break
    fi
    sleep 10
done

if [ "$BACK" -ne 1 ]; then
    echo "VENDOR_DID_NOT_RETURN"
    exit 2
fi

echo "=== verdict cells ==="
"$RSH" 'for c in C04 C18 C1C C70 C88 C90 C94 C98 C9C; do printf "%s=" $c; devmem 0x10100$c 32; done' 2>&1

echo "=== overlay upper ==="
"$RSH" 'ls /overlay/upper 2>/dev/null | tr "\n" " "; echo' 2>&1
"$RSH" 'wc -c /overlay/upper/boot.log /overlay/upper/mod-load.log 2>/dev/null' 2>&1

echo "=== done ==="
