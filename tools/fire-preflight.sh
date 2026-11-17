#!/usr/bin/env bash
# fire-preflight.sh - fail-closed gate that must pass before any slice is written to flash.
#
# This gate exists because the expensive failures on this project were simple overlooks:
# a fire written to the wrong slot, a fire with no recovery armed, a fire with no console
# capture, and a fire whose captured kernel was stock while everyone read it as ours.
# It checks those conditions; it CANNOT prove the delivery lane or the kernel - only fail
# on known hazards.
#
# usage:
#   tools/fire-preflight.sh --slice <path> --slot a|b --attended [--label NAME] [--no-console]
#
# --attended is not decoration: recovery needs a human to power-cycle the router and hold
# RESET through the counter. If no human is at the bench, do not fire.
set -uo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT" || exit 1
export LC_ALL=C

SLICE=""
SLOT=""
LABEL=preflight
ATTENDED=0
CONSOLE_REQUIRED=1
FAIL=0
WARN=0
OK=0

pass() { OK=$((OK + 1)); printf '  PASS  %s\n' "$*"; }
fail() { FAIL=$((FAIL + 1)); printf '  FAIL  %s\n' "$*"; }
note() { WARN=$((WARN + 1)); printf '  WARN  %s\n' "$*"; }

ancestor_pids() {
	local p=$$
	while [ -n "$p" ] && [ "$p" -gt 1 ]; do
		printf '%s\n' "$p"
		p=$(ps -o ppid= -p "$p" 2>/dev/null | tr -d ' ')
	done
}
ANCESTORS=$(ancestor_pids | tr '\n' ' ')
matching_pids() {
	local pat=$1 pid
	for pid in $(pgrep -f "$pat" 2>/dev/null || true); do
		case " $ANCESTORS " in *" $pid "*) continue ;; esac
		printf '%s\n' "$pid"
	done
}
# A capture's argv is 'timeout N cat' (the redirection is not in argv), so match that plus
# the pidfiles uart-capture.sh writes. Never match the literal pattern text in our own argv.
capture_pids() {
	local pf pid out=""
	for pf in "$ROOT"/build/uart-logs/*.pid; do
		[ -f "$pf" ] || continue
		pid=$(cat "$pf" 2>/dev/null) || continue
		case "$pid" in ''|*[!0-9]*) continue ;; esac
		if kill -0 "$pid" 2>/dev/null || sudo -n kill -0 "$pid" 2>/dev/null; then
			out="$out $pid"
		else
			sudo -n rm -f "$pf" 2>/dev/null || rm -f "$pf" 2>/dev/null || true
		fi
	done
	for pid in $(matching_pids 'timeout [0-9]+ cat'); do out="$out $pid"; done
	out=${out# }
	[ -n "$out" ] && printf '%s\n' "$out"
}

usage() { sed -n '3,18p' "$0" | sed 's/^# \{0,1\}//'; }

while [ $# -gt 0 ]; do
	case "$1" in
		--slice) SLICE=$2; shift ;;
		--slot) SLOT=$2; shift ;;
		--label) LABEL=$2; shift ;;
		--attended) ATTENDED=1 ;;
		--no-console) CONSOLE_REQUIRED=0 ;;
		-h|--help) usage; exit 0 ;;
		*) echo "unknown argument: $1" >&2; usage; exit 2 ;;
	esac
	shift
done

echo "== fire preflight: slice=${SLICE:-<none>} slot=${SLOT:-<none>} label=$LABEL =="

case "$SLOT" in
	a) TARGET_MTD=kernela; TARGET_DEV=/dev/mtd11; TARGET_FLAG=a; TARGET_REG='<not established for a manual slot-A fire>' ;;
	b) TARGET_MTD=kernelb; TARGET_DEV=/dev/mtd12; TARGET_FLAG=b; TARGET_REG=0x21 ;;
	*) fail "--slot must be 'a' or 'b' (the flash slot, not an address)"; TARGET_MTD=''; TARGET_DEV=''; TARGET_FLAG=''; TARGET_REG='' ;;
esac

# ---- slice artifact ----
if [ -z "$SLICE" ]; then
	fail "no --slice given"
else
	if [ -f "$SLICE" ]; then
		SLICE_SIZE=$(stat -c %s "$SLICE")
		SLICE_MD5=$(md5sum "$SLICE" | awk '{print $1}')
		pass "slice exists: $SLICE ($SLICE_SIZE B, md5 $SLICE_MD5)"
		if [ "$SLICE_SIZE" -le 8650752 ]; then pass "slice fits the slot (<= 8,650,752 B)"; else fail "slice is larger than a kernel slot"; fi
		if [ "$(od -An -tx1 -N4 "$SLICE" | tr -d ' \n')" = "27051956" ]; then pass "slice starts with a uImage header"; else fail "slice does not start with a uImage magic (0x27051956)"; fi
		TRAILER="$ROOT/build/linux-kbuild/slice-trailer-40732.bin"
		if [ -f "$TRAILER" ]; then
			if tail -c 40732 "$SLICE" | cmp -s - "$TRAILER"; then pass "fixed 40,732-byte trailer matches slice-trailer-40732.bin"; else fail "slice trailer does not match slice-trailer-40732.bin"; fi
		else
			fail "missing $TRAILER (cannot validate the FIP trailer)"
		fi
		if tail -c 40732 "$SLICE" | strings -n 8 | grep -q 'hsan-luofu'; then pass "slice trailer carries the vendor luofu DTB container"; else note "vendor DTB container marker not found in the slice tail"; fi
	else
		fail "slice does not exist: $SLICE"
	fi
fi

# ---- local guards ----
if "$ROOT/tools/check-init-shadow.sh" >/dev/null 2>&1; then pass "shadow guard PASS"; else fail "shadow guard FAILED (tools/check-init-shadow.sh)"; fi
if "$ROOT/tools/check-lab-src.sh" --manifest-only >/dev/null 2>&1; then pass "tracked kernel snapshot PASS (manifest)"; else fail "tracked kernel snapshot FAILED (tools/check-lab-src.sh)"; fi

# ---- no double fire, no stale writers ----
ACTIVE_FIRE=$(matching_pids 'bash .*fire-ssh[.]sh|bash .*fire-device[.]sh|bash .*run-phase[0-9a-z]+[.]sh')
STALE_WRITERS=$(matching_pids 'tee -a .*/fire-')
if [ -n "$ACTIVE_FIRE" ]; then
	fail "another fire driver is already running (pid(s): $(echo $ACTIVE_FIRE)); never run two fires at once"
else
	pass "no other fire driver is running"
fi
if [ -n "$STALE_WRITERS" ]; then
	note "stale fire-log writer(s) from an old lane still running (pid(s): $(echo $STALE_WRITERS)); stop them with tools/bench-teardown.sh --apply"
fi

# ---- host bench link ----
if "$ROOT/tools/bench-link.sh" >/tmp/fire-preflight-link.out 2>&1; then pass "host bench link PASS (tools/bench-link.sh)"; else fail "host bench link not ready; run tools/bench-link.sh --apply"; fi

# ---- recovery door ----
if "$ROOT/tools/recovery-card.sh" >/tmp/fire-preflight-recovery.out 2>&1; then
	pass "recovery door READY (TFTP armed, recovery.bin md5 matches, host 192.168.1.88 up)"
else
	fail "recovery door NOT ready; fix before any fire (tools/recovery-card.sh)"
fi

# ---- console capture (read-only) ----
CAPTURE_PID=$(capture_pids | awk '{print $1; exit}')
if [ "$CONSOLE_REQUIRED" -eq 1 ]; then
	if [ -n "$CAPTURE_PID" ]; then
		pass "read-only UART capture is running (pid $CAPTURE_PID)"
	else
		fail "no UART capture running; arm it first: tools/uart-capture.sh start --label $LABEL"
	fi
else
	note "--no-console: a fire without a console capture cannot prove which kernel ran"
fi

# ---- calibration snapshot ----
SNAP=$(ls -d build/linux-kbuild/cal-snapshots/*/ 2>/dev/null | tail -1)
if [ -n "$SNAP" ] && [ -f "$SNAP/MANIFEST.sha256" ]; then pass "calibration snapshot present: $SNAP"; else note "no calibration snapshot with MANIFEST.sha256; snapshot before an experiment"; fi

# ---- device state ----
PROBE=$(timeout 20 "$ROOT/tools/rsh.sh" 'echo "UP=$(cut -d. -f1 /proc/uptime)"; echo "KERNEL=$(uname -r)"; echo "BOOTFLAG=$(fw_printenv bootflag 2>/dev/null | cut -d= -f2)"; echo "BOOTREG=$(cat /sys/devices/platform/sysenv/boot_reg 2>/dev/null)"; echo "WIPHY=$(ls /sys/class/ieee80211 2>/dev/null | wc -l)"; echo "CAL2=$(dmesg | grep -c "hwifi_rf_cali_file_load_2g succ")"; echo "CAL5=$(dmesg | grep -c "hwifi_rf_cali_file_load_5g succ")"; echo "HI=$(lsmod | grep -c "^hi_")"; echo "OMO=$(ls /lib/modules/5.10.201/*.omo-off 2>/dev/null | wc -l)"; echo "OVERLAYKO=$(ls /overlay/upper/lib/hisilicon/ko/*.ko 2>/dev/null | wc -l)"; grep -E "mtd(11|12):" /proc/mtd' 2>/dev/null)
if [ -z "$PROBE" ]; then
	fail "router unreachable over SSH; recovery would need hands on the box"
else
	declare -A P=()
	while IFS='=' read -r k v; do [ -n "$k" ] && P["$k"]=$v; done <<< "$(printf '%s\n' "$PROBE" | grep '=')"
	UP=${P[UP]:-0}; HRS=$((UP / 3600)); MINS=$(( (UP % 3600) / 60 ))
	pass "router up ${HRS}h${MINS}m, kernel ${P[KERNEL]:-?}, bootflag=${P[BOOTFLAG]:-?} boot_reg=0x${P[BOOTREG]:-?}"
	[ "${P[WIPHY]:-0}" -ge 2 ] 2>/dev/null && pass "2 wiphys present" || fail "fewer than 2 wiphys"
	[ "${P[CAL2]:-0}" -ge 1 ] 2>/dev/null && [ "${P[CAL5]:-0}" -ge 1 ] 2>/dev/null && pass "calibration [SUCC] on both bands" || fail "calibration not [SUCC] on both bands"
	[ "${P[OMO]:-1}" = "0" ] 2>/dev/null && pass "no .omo-off leftovers" || fail ".omo-off leftovers present"
	[ "${P[OVERLAYKO]:-0}" -gt 0 ] 2>/dev/null && pass "patched vendor module set staged in /overlay/upper (${P[OVERLAYKO]} .ko)" || note "no staged patched modules: a vendor-stack test will fail until tools/box-provision.sh --stage lab"
	if [ -n "$TARGET_MTD" ]; then
		if printf '%s\n' "$PROBE" | grep -q "\"$TARGET_MTD\""; then pass "target slot exists: $TARGET_MTD ($TARGET_DEV)"; else fail "target slot $TARGET_MTD not found in /proc/mtd"; fi
		pass "planned handover: bootflag=$TARGET_FLAG boot_reg=$TARGET_REG (current: bootflag=${P[BOOTFLAG]:-?} boot_reg=0x${P[BOOTREG]:-?})"
		[ "$SLOT" = "a" ] && note "slot-A manual handover is not established in the repo (the last slot-A read was invalid); fire-device.sh requires BOOT_REG for slot A"
	fi
fi

# ---- delivery-lane honesty ----
note "delivery lane unproven: our slice is read by U-Boot but recent fires do not show our kernel starting. The slice is built and was never deliberately fired (3dk's write was a non-result). A fire can cost a physical TFTP recovery."
note "validity rule: our uImage prints Data Size (e.g. 2965176) and 'Image Name: Linux-5.10.201'; ONLY the stock image prints 'Uncompressing Linux'. Do not use 'Uncompressing' as proof our kernel ran."

# ---- attended ----
if [ "$ATTENDED" -eq 1 ]; then
	pass "operator marked the bench attended"
else
	fail "not --attended: recovery needs a human to power-cycle the router and hold RESET; do not fire unattended"
fi

echo
if [ "$FAIL" -gt 0 ]; then
	echo "PREFLIGHT: FAIL ($FAIL failures, $WARN warnings, $OK passes) - DO NOT FIRE"
	[ -s /tmp/fire-preflight-recovery.out ] && { echo "recovery detail:"; sed 's/^/  /' /tmp/fire-preflight-recovery.out | tail -20; }
	exit 1
fi
echo "PREFLIGHT: PASS ($OK passes, $WARN warnings) - the known hazards are covered"
echo "REMINDER: a valid fire reading shows U-Boot printing OUR uImage (Data Size + Image Name),"
echo "then kernel output. Stock is 4,294,096 B and prints 'Uncompressing Linux'; ours does not."
exit 0
