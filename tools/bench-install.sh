#!/bin/bash
# bench-install.sh - install a built sysupgrade image into the box's B pair from
# the host, with no physical recovery: reboot the box to the vendor slot (pair a),
# wait for stock, provision telnet, write kernelb+rootfsb, select pair b, boot,
# then verify ping + SSH + runtime.
#
# usage: tools/bench-install.sh <sysupgrade.bin> [--skip-stock-switch]
set -u
BOX_OURS=192.168.1.1
BOX_STOCK=192.168.10.1
SSH="ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o BatchMode=yes -o ConnectTimeout=8"
IMG=${1:?usage: $0 <sysupgrade.bin> [--skip-stock-switch]}
REPO=$(cd "$(dirname "$0")/.." && pwd)
STAGE=/home/shibbityshwab/staging-fi
SWITCH=1
[ "${2:-}" = "--skip-stock-switch" ] && SWITCH=0

if [ "$SWITCH" = 1 ]; then
  echo "== reboot box to vendor slot (pair a) =="
  $SSH root@$BOX_OURS 'echo a > /sys/devices/platform/boot-selector/next_pair; sync; reboot -f' >/dev/null 2>&1 || true
  sleep 25
  for i in $(seq 1 30); do timeout 2 ping -c1 -W1 $BOX_STOCK >/dev/null 2>&1 && break; sleep 5; done
  timeout 2 ping -c1 -W1 $BOX_STOCK >/dev/null 2>&1 || { echo "stock did not come up"; exit 1; }
fi
echo "== provision stock telnet =="
timeout 90 "$REPO"/tools/box-provision.sh --bdinfo "$REPO"/dumps/router-20261108/bdinfo.bin --stage base --host $BOX_STOCK --telnetd >/tmp/bench-install-prov.log 2>&1 || true
sleep 2

echo "== extract image members =="
python3 - "$IMG" "$STAGE" <<'PY'
import tarfile,sys,hashlib,os
img,out=sys.argv[1],sys.argv[2]; KS=8650752; RP=24379392
def sha(b): return hashlib.sha256(b).hexdigest()
def slot_sha(d,s): return sha(d+b'\xff'*(s-len(d)))
with tarfile.open(img,'r:') as t:
    k=t.extractfile('sysupgrade-cudy_wr3000-v2/kernel').read(); r=t.extractfile('sysupgrade-cudy_wr3000-v2/root').read()
open(os.path.join(out,'kernel.bin'),'wb').write(k); open(os.path.join(out,'rootfs.ubi'),'wb').write(r)
vals={'KSHA':sha(k),'RSHA':sha(r),'KSLOT':slot_sha(k,KS),'RPART':slot_sha(r,RP)}
open(os.path.join(out,'vars.env'),'w').write('\n'.join('%s=%s'%(a,b) for a,b in vals.items())+'\n')
print(vals)
PY
cd "$STAGE" || exit 1
. ./vars.env
echo "== push image to stock =="
timeout 90 python3 telnet-run.py 'cd /tmp' \
  'wget -q -O fi-k.bin http://192.168.10.44:8000/kernel.bin; echo KW=$?' \
  'wget -q -O fi-r.ubi http://192.168.10.44:8000/rootfs.ubi; echo RW=$?' >/tmp/bench-install-wget.log 2>&1 || true
grep -q 'KW=0' /tmp/bench-install-wget.log || { echo "kernel wget failed"; tail -3 /tmp/bench-install-wget.log; exit 1; }
grep -q 'RW=0' /tmp/bench-install-wget.log || { echo "rootfs wget failed"; tail -3 /tmp/bench-install-wget.log; exit 1; }
echo "== write kernelb =="
timeout 90 python3 telnet-run.py 'mtd erase kernelb' 'mtd write /tmp/fi-k.bin kernelb; echo WR=$?' 2>&1 | grep -q 'WR=0' || { echo "kernel write failed"; exit 1; }
GOT=$(timeout 60 python3 telnet-run.py 'dd if=/dev/mtd12 bs=131072 count=66 2>/dev/null | sha256sum' 2>&1 | grep -oE '^[0-9a-f]{64}' | head -1)
[ "$GOT" = "$KSLOT" ] || { echo "kernel slot verify failed"; exit 1; }
echo "== write rootfsb =="
timeout 150 python3 telnet-run.py 'ubiformat /dev/mtd14 -y -f /tmp/fi-r.ubi; echo UBI=$?' 2>&1 | grep -q 'UBI=0' || { echo "rootfs write failed"; exit 1; }
echo "== select pair b and boot =="
timeout 30 python3 telnet-run.py 'echo -n "0x11" > /sys/devices/platform/sysenv/boot_reg; echo SEL' >/dev/null 2>&1 || true
timeout 15 python3 telnet-run.py 'reboot' >/dev/null 2>&1 || true
echo "== wait for our image =="
UP=0
for i in $(seq 1 40); do
  if timeout 2 ping -c1 -W1 $BOX_OURS >/dev/null 2>&1; then
    if $SSH root@$BOX_OURS 'grep -q ubi.mtd=rootfsb /proc/cmdline' 2>/dev/null; then UP=1; break; fi
  fi
  sleep 4
done
[ "$UP" = 1 ] || { echo "box did not come back on our image (stock/recovery lane)"; exit 1; }
sleep 3
echo "== verify =="
$SSH root@$BOX_OURS 'cat /proc/uptime; uname -r; grep -o "ubi.mtd=rootfs[a-b]" /proc/cmdline; ping -c5 -W1 192.168.1.88 >/dev/null && echo ping_ok' 2>&1 | tail -5
echo "PASS: installed $IMG"
