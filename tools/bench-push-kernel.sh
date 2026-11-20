#!/bin/bash
# Bench fast kernel iteration: push a built kernel image into the INACTIVE kernel
# slot over SSH (host->box stdin), verify the payload, select that slot, reboot,
# and wait for the box to come back on it.  The rootfs slot is left untouched, so
# an image built with ubi.mtd=rootfsb keeps mounting the working rootfs.
#
# usage: tools/bench-push-kernel.sh <path-to-kernel.bin> [--slot a|b]
set -u
BOX=root@192.168.1.1
SSH="ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o BatchMode=yes -o ConnectTimeout=8"
K="$1"; SLOT=""
shift || true
while [ $# -gt 0 ]; do case "$1" in --slot) SLOT="$2"; shift 2;; *) shift;; esac; done
[ -f "$K" ] || { echo "missing kernel file $K"; exit 2; }
KSLOT=$(python3 - "$K" <<'PY'
import sys,hashlib
k=open(sys.argv[1],'rb').read(); KS=8650752
print(hashlib.sha256(k+b'\xff'*(KS-len(k))).hexdigest())
PY
)
CUR=$($SSH $BOX 'grep -o "ubi.mtd=rootfs[a-b]" /proc/cmdline' 2>/dev/null | tail -1)
if [ -z "$SLOT" ]; then
  case "$CUR" in *rootfsa) SLOT=b;; *rootfsb) SLOT=a;; *) echo "cannot determine running slot ($CUR)"; exit 2;; esac
fi
case "$SLOT" in a) KMTD=kernela; RMTD=rootfsa; PAIR=a;; b) KMTD=kernelb; RMTD=rootfsb; PAIR=b;; *) echo "bad slot $SLOT"; exit 2;; esac
if [ "$CUR" = "ubi.mtd=rootfs$SLOT" ]; then echo "slot $SLOT is RUNNING; refusing to flash it"; exit 2; fi
echo "== pushing kernel $(sha256sum "$K" | cut -c1-16) to inactive slot $SLOT ($KMTD) =="
sudo -n true 2>/dev/null || true
$SSH $BOX "cat > /tmp/bench-kernel.bin" < "$K" || exit 1
GOT=$($SSH $BOX 'sha256sum /tmp/bench-kernel.bin' 2>/dev/null | cut -d' ' -f1)
if [ "$GOT" != "$(sha256sum "$K" | cut -d' ' -f1)" ]; then echo "push verify FAILED ($GOT)"; exit 1; fi
echo "== writing $KMTD and verifying full-slot hash =="
$SSH $BOX "mtd erase $KMTD && mtd write /tmp/bench-kernel.bin $KMTD" || exit 1
GOTSLOT=$($SSH $BOX "dd if=/dev/mtd$([ "$SLOT" = a ] && echo 11 || echo 12) bs=131072 count=66 2>/dev/null | sha256sum" 2>/dev/null | cut -d' ' -f1)
if [ "$GOTSLOT" != "$KSLOT" ]; then echo "slot verify FAILED: got $GOTSLOT want $KSLOT"; exit 1; fi
echo "slot hash OK"
echo "== selecting pair $PAIR and rebooting =="
$SSH $BOX "echo $PAIR > /sys/devices/platform/boot-selector/next_pair; sync; reboot -f" >/dev/null 2>&1 || true
sleep 20
UP=0
for i in $(seq 1 30); do
  if timeout 2 ping -c1 -W1 192.168.1.1 >/dev/null 2>&1; then
    if $SSH $BOX 'grep -q '"$( [ "$PAIR" = a ] && echo rootfsa || echo rootfsb)"' /proc/cmdline' 2>/dev/null; then UP=1; break; fi
  fi
  sleep 4
done
[ "$UP" = 1 ] || { echo "BOX DID NOT COME BACK on pair $PAIR - last-good kernel is in the other slot; use the loader/pair to fall back"; exit 1; }
sleep 3
echo "== verify =="
$SSH $BOX 'cat /proc/uptime; uname -r; grep -o "ubi.mtd=rootfs[a-b]" /proc/cmdline; echo raw=[$(cat /sys/devices/platform/boot-selector/raw)]; dmesg | grep -cE "Oops|panic|Internal error"' 2>&1 | tail -6
timeout 20 ping -c10 -W1 192.168.1.1 2>&1 | tail -2
echo "PASS: booted slot $SLOT kernel, rootfs unchanged"
