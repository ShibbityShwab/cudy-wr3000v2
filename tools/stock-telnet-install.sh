#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-only
#
# stock-telnet-install.sh - install our sysupgrade image from the vendor stock
# firmware over its root telnet shell (the transport this bench actually has).
#
# STATUS: bench tool, fail-closed.  Nothing is written without
# --apply --attended --recovery-armed.  --apply writes ONLY pair b
# (kernelb + rootfsb): our image's baked cmdline hardcodes ubi.mtd=rootfsb, so
# pair a after a RESET-hold recovery would mix our kernel with the stock rootfs.
# It also refuses when the U-Boot env bootflag disagrees with the selector cell
# (the loader reads the kernel slot named by the env bootflag), sets and reads
# back the env bootflag together with the selector, and after boot requires
# /proc/cmdline to contain ubi.mtd=rootfsb and the project marker.  The broker
# channel (CVE-2026-71961) only works on a consistent vendor kernel+rootfs pair
# (vendor /proc/sys/dev/flash_uuid for the bdinfo checkuuid); the mixed state
# disables the vendor web wizard and cmagent, so recover the stock pair first.
# Why: tools/first-install-stock.sh needs SSH, but the vendor image has no
# dropbear/opkg, so that transport cannot be provisioned on this unit (probed
# 2026-11-21).  This tool performs the same measured install path over telnet.
#
# usage: tools/stock-telnet-install.sh --inspect --image FILE
#        tools/stock-telnet-install.sh --apply --attended --recovery-armed --image FILE
set -o pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
HOST=$STOCK_HOST
[ -n "$HOST" ] || HOST=192.168.10.1
HTTP_BASE=$HTTP_BASE_URL
[ -n "$HTTP_BASE" ] || HTTP_BASE=http://192.168.10.44:8000
STAGING=$STAGING_DIR
[ -n "$STAGING" ] || STAGING=~/staging-fi
TELNET=$TELNET_HELPER
[ -n "$TELNET" ] || TELNET=$ROOT/tools/telnet-exec.py
BOOT_TIMEOUT=$BOOT_TIMEOUT_SECS
[ -n "$BOOT_TIMEOUT" ] || BOOT_TIMEOUT=240
IMAGE=""
APPLY=0
ATTENDED=0
RECOVERY_ARMED=0
say() { printf '%s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
pair_value() { if [ "$1" = a ]; then echo 0x10; else echo 0x11; fi; }
t() { "$TELNET" --host "$HOST" -- "$@" | tr -d '\r'; }
while [ $# -gt 0 ]; do
	case "$1" in
	--inspect) APPLY=0 ;;
	--apply) APPLY=1 ;;
	--attended) ATTENDED=1 ;;
	--recovery-armed) RECOVERY_ARMED=1 ;;
	--image) IMAGE=$2; shift ;;
	--staging) STAGING=$2; shift ;;
	--http-base) HTTP_BASE=$2; shift ;;
	--host) HOST=$2; shift ;;
	--boot-timeout) BOOT_TIMEOUT=$2; shift ;;
	-h|--help) sed -n '3,30p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
	*) die "unknown option: $1" ;;
	esac
	shift
done
[ -x "$TELNET" ] || die "missing telnet helper: $TELNET"
[ -n "$IMAGE" ] || die "--image is required"
[ -f "$IMAGE" ] || die "image not found: $IMAGE"
[ -d "$STAGING" ] || die "missing staging dir: $STAGING"
if [ "$APPLY" = 1 ]; then
	[ "$ATTENDED" = 1 ] || die "--apply requires --attended"
	[ "$RECOVERY_ARMED" = 1 ] || die "--apply requires --recovery-armed"
	"$ROOT/tools/bench-link.sh" | tail -3 | grep -q PASS || die "bench link check failed"
	"$ROOT/tools/recovery-card.sh" | tail -8 | grep -qE 'READY|PASS' || die "recovery card check failed (arm TFTP first)"
fi
python3 - "$IMAGE" "$STAGING" <<'PY' || die "image split failed"
import hashlib, sys, tarfile
img, out = sys.argv[1], sys.argv[2]
KS = 8650752
def sha(b): return hashlib.sha256(b).hexdigest()
with tarfile.open(img, "r:") as tf:
    k = tf.extractfile("sysupgrade-cudy_wr3000-v2/kernel").read()
    r = tf.extractfile("sysupgrade-cudy_wr3000-v2/root").read()
open(out + "/kernel.bin", "wb").write(k)
open(out + "/rootfs.ubi", "wb").write(r)
slot = k + b"\xff" * (KS - len(k))
open(out + "/install-vars.env", "w").write("\n".join([
    "KSIZE=%d" % len(k), "RSIZE=%d" % len(r),
    "KSHA=%s" % sha(k), "RSHA=%s" % sha(r), "KSLOT=%s" % sha(slot)]) + "\n")
print("members: kernel %d B, root %d B" % (len(k), len(r)))
PY
. "$STAGING/install-vars.env"
say "image kernel $KSIZE B sha $KSHA (slot sha $KSLOT)"
say "image root   $RSIZE B sha $RSHA"
say "http $HTTP_BASE serving $STAGING"
# stock state
out=$(t 'cat /sys/devices/platform/sysenv/boot_reg; echo' 'fw_printenv bootflag 2>/dev/null')
cellraw=$(printf '%s\n' "$out" | grep -E '^[0-9a-fA-F]{1,8}$' | head -1)
case "$cellraw" in
10|0x10|0x00000010) cell=0x10 ;;
11|0x11|0x00000011) cell=0x11 ;;
*) die "cannot read the selector cell from stock (got: $cellraw)" ;;
esac
eflag=$(printf '%s\n' "$out" | sed -n 's/^bootflag=//p' | head -1)
case "$eflag" in
a|b) ;;
*) eflag="" ;;
esac
if [ -n "$eflag" ]; then
	case "$cell" in
	0x10) cellpair=a ;;
	0x11) cellpair=b ;;
	esac
	if [ "$eflag" != "$cellpair" ]; then
		die "U-Boot env bootflag=$eflag disagrees with selector cell $cell (cell says pair $cellpair) - the loader would mix kernel and rootfs pairs; recover the stock pair first"
	fi
fi
case "$cell" in
0x10) ap=a; tp=b ;;
0x11) ap=b; tp=a ;;
*) die "unexpected selector cell $cell" ;;
esac
# Our image's baked cmdline uses ubi.mtd=rootfsb, so it can only be written
# consistently to pair b (kernelb + rootfsb). Writing pair a (which the old
# installer did after a recovery) produces a mixed our-kernel/stock-rootfs
# system in which the stock userland's bdinfo checkuuid fails (no vendor
# /proc/sys/dev/flash_uuid) and neither the web wizard nor cmagent works.
if [ "$tp" != b ]; then
	die "active pair is b (stock is booting from kernelb/rootfsb); this image can only be written to pair b because its cmdline expects rootfsb - recover the stock pair first"
fi
# The target pair must be fully inactive: if the stock kernel command line already
# uses rootfsb (or the env bootflag is b), the UBI device is attached while stock runs
# and ubiformat /dev/mtd14 fails -> the flash leaves our kernel with the stock rootfs
# (mixed system: no vendor flash_uuid, wizard/broker dead, no management IP).
case "$(cat /proc/cmdline)" in
*rootfsb*) die "stock is running from rootfsb (cmdline uses ubi.mtd=rootfsb); switch stock to pair a first: fw_setenv bootflag a, write 0x10 to /sys/devices/platform/sysenv/boot_reg, reboot, then rerun" ;;
esac
if [ "$eflag" = b ]; then
	die "U-Boot env bootflag=b (stock boots pair b); switch stock to pair a first: fw_setenv bootflag a, write 0x10 to /sys/devices/platform/sysenv/boot_reg, reboot, then rerun"
fi
say "stock selector cell $cell -> active pair $ap, write pair $tp (active untouched)"
case "$tp" in
a) kdev=/dev/mtd11; rdev=/dev/mtd13 ;;
b) kdev=/dev/mtd12; rdev=/dev/mtd14 ;;
esac
case "$ap" in
a) adev=/dev/mtd11 ;;
b) adev=/dev/mtd12 ;;
esac
out=$(t "dd if=$adev bs=131072 count=66 2>/dev/null | sha256sum | cut -d' ' -f1")
act_before=$(printf '%s\n' "$out" | grep -E '^[0-9a-f]{64}$' | head -1)
say "active kernel slot sha256: $act_before"
if [ "$APPLY" != 1 ]; then
	say ""
	say "INSPECT ONLY - nothing written. Plan: write $kdev + ubiformat $rdev, selector -> $(pair_value $tp), reboot."
	exit 0
fi
say ""
say "== upload members =="
out=$(t 'cd /tmp' "wget -q -O /tmp/fi-k.bin $HTTP_BASE/kernel.bin; echo K=\$?" "wget -q -O /tmp/fi-r.ubi $HTTP_BASE/rootfs.ubi; echo R=\$?" 'sha256sum /tmp/fi-k.bin /tmp/fi-r.ubi')
printf '%s\n' "$out" | grep -E '^K=|^R=' | sed 's/^/  /'
printf '%s\n' "$out" | grep -q 'K=0' || die "kernel upload failed"
printf '%s\n' "$out" | grep -q 'R=0' || die "rootfs upload failed"
uk=$(printf '%s\n' "$out" | awk '$2 ~ /fi-k.bin/ {print $1}')
ur=$(printf '%s\n' "$out" | awk '$2 ~ /fi-r.ubi/ {print $1}')
[ "$uk" = "$KSHA" ] || die "uploaded kernel sha $uk != $KSHA"
[ "$ur" = "$RSHA" ] || die "uploaded rootfs sha $ur != $RSHA"
say "  uploaded members verified"
say ""
say "== write kernel slot $kdev =="
out=$(t "mtd erase kernel$tp" "mtd write /tmp/fi-k.bin kernel$tp; echo WR=\$?" "dd if=$kdev bs=131072 count=66 2>/dev/null | sha256sum | cut -d' ' -f1")
printf '%s\n' "$out" | grep -q 'WR=0' || die "kernel slot write failed"
wslot=$(printf '%s\n' "$out" | grep -E '^[0-9a-f]{64}$' | head -1)
[ "$wslot" = "$KSLOT" ] || die "kernel slot read-back sha $wslot != $KSLOT"
say "  read-back matches the expected slot hash"
say ""
say "== ubiformat rootfs slot $rdev =="
out=$(t "ubiformat $rdev -y -f /tmp/fi-r.ubi >/dev/null 2>&1; echo UBI=\$?")
printf '%s\n' "$out" | grep -q 'UBI=0' || die "ubiformat failed"
say "  ubiformat OK"
say ""
say "== active pair unchanged =="
out=$(t "dd if=$adev bs=131072 count=66 2>/dev/null | sha256sum | cut -d' ' -f1")
act_after=$(printf '%s\n' "$out" | grep -E '^[0-9a-f]{64}$' | head -1)
[ "$act_before" = "$act_after" ] || die "ACTIVE kernel slot changed"
say "  active kernel slot unchanged"
say ""
say "== handover: U-Boot env bootflag -> $tp =="
out=$(t 'ln -sf /bin/fw_printenv /tmp/fw_setenv; /tmp/fw_setenv bootflag '"$tp"'; echo SET=\$?' 'fw_printenv bootflag 2>/dev/null')
printf '%s\n' "$out" | grep -q 'SET=0' || die "could not set the U-Boot env bootflag"
printf '%s\n' "$out" | grep -q "bootflag=$tp" || die "U-Boot env bootflag read-back is not $tp"
say "  env bootflag=$tp verified"
say ""
say "== handover: selector -> $(pair_value $tp) =="
target_val=$(pair_value "$tp")
out=$(t "echo -n $target_val > /sys/devices/platform/sysenv/boot_reg" 'cat /sys/devices/platform/sysenv/boot_reg; echo')
nowraw=$(printf '%s\n' "$out" | grep -E '^[0-9a-fA-F]{1,8}$' | tail -1)
case "$nowraw" in
10|0x10|0x00000010) now=0x10 ;;
11|0x11|0x00000011) now=0x11 ;;
*) die "cannot read back the selector (got: $nowraw)" ;;
esac
[ "$now" = "$target_val" ] || die "selector read-back $now != $target_val"
say "  selector verified: $now"
say ""
say "== reboot and poll for our image (up to $BOOT_TIMEOUT s) =="
t 'sync; reboot' >/dev/null 2>&1 || true
i=0
up=0
while [ "$i" -lt "$BOOT_TIMEOUT" ]; do
	if timeout 2 ping -c1 -W1 192.168.1.1 >/dev/null 2>&1; then up=1; break; fi
	sleep 3
	i=$((i + 3))
done
if [ "$up" = 1 ]; then
	say "  ping OK after $i s"
	un=""
	j=0
	while [ "$j" -lt 60 ]; do
		un=$(timeout 12 ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o BatchMode=yes -o ConnectTimeout=8 root@192.168.1.1 'uname -r' 2>/dev/null | tail -1)
		[ -n "$un" ] && break
		sleep 3
		j=$((j + 3))
	done
	if [ -z "$un" ]; then
		say "FAIL: the box pings but SSH does not answer; inspect it before trusting this install."
		exit 3
	fi
	cpus=$(timeout 12 ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o BatchMode=yes -o ConnectTimeout=8 root@192.168.1.1 'grep -c ^processor /proc/cpuinfo' 2>/dev/null | tail -1)
	case "$un" in
	6.18*)
		cmd=$(timeout 12 ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o BatchMode=yes -o ConnectTimeout=8 root@192.168.1.1 'cat /proc/cmdline' 2>/dev/null | tail -1)
		case "$cmd" in
		*ubi.mtd=rootfsb*) ;;
		*) die "booted kernel cmdline does not use rootfsb - the handover mixed the pair; verify the env bootflag and selector" ;;
		esac
		case "$cmd" in
		*luofu_switch*) ;;
		*) die "booted kernel cmdline lacks the project marker - not our image?" ;;
		esac
		say "  image: $un CPUs: $cpus (cmdline: ubi.mtd=rootfsb + project marker verified)"
		say ""
		say "PASS: wrote pair $tp, handover verified, our image booted."
		exit 0
		;;
	*)
		say "FAIL: unexpected kernel $un (stock fallback?); inspect the box and the selector."
		exit 3
		;;
	esac
fi
say "FAIL: our image did not answer within $BOOT_TIMEOUT s after the selector move."
say "  the loader should fall back to the ACTIVE pair $ap; wait 2 minutes, then power-cycle."
say "  if the box stays silent: physical RESET+TFTP recovery with tools/recovery-card.sh --arm."
exit 3
