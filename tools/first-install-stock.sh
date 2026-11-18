#!/usr/bin/env bash
# first-install-stock.sh - attended first-install path: stock firmware -> our generated image.
#
# STATUS: HOST-SIDE TOOL, FAIL-CLOSED, NEVER EXECUTED ON HARDWARE BY ITS AUTHORS.
# It writes flash only with explicit attended flags; the default mode is a read-only
# inspection. No UART, TFTP, env-block or vendor-data write is ever performed.
#
# WHAT IT DOES
#   From a ROOT SHELL ON THE STOCK VENDOR FIRMWARE (reachable over the project's
#   tools/rsh.sh SSH transport, key from .omo-secrets/), stage and write our generated
#   sysupgrade container's two members into the INACTIVE flash slot pair, read both
#   regions back, and - only for the higher modes - move the measured boot selector to
#   the written pair and reboot. The active pair, rootfs_data (mtd15), upgrade (mtd16),
#   the env blocks (mtd3/mtd4) and all vendor data partitions are never written.
#
#   The installation path is the one TARGET-DESIGN.md section 5.5 option 2 records as
#   measured (FLASH-PLAN.md builds 0.1-0.3): the stock vendor userspace can write the
#   inactive kernel slot (mtd by label) and ubiformat the inactive rootfs slot. The
#   closed TFTP recovery image's write path is not characterized and is not used.
#
#   Handover uses ONLY the measured selector semantics (opensource/docs/SELECTOR-0x21.md):
#   the env bootflag selects the pair and the SYSCTRL cell is the loader's
#   opposite-pair/failed-boot record. Writing the WRITTEN pair's recorded low byte into
#   the cell (0x10 = A pair, 0x11 = B pair) makes the next boot see a mismatch and take
#   the loader's env re-stamp/failover path to the written pair. The env blocks are
#   NEVER written by this tool. 0x21 is the project's bench value and is never used.
#
# MODES (one per invocation; higher modes include the lower ones)
#   (no mode) / --inspect   read-only: host checks, image validation, device probe,
#                           readiness report and the exact write/handover plan.
#   --write                 write kernel slice + rootfs UBI to the inactive pair and
#                           verify both read-backs. Selector NOT moved, no reboot.
#   --handover              --write, then move the selector to the written pair and
#                           verify it (no reboot; the box keeps running stock until a
#                           reboot; a true power cycle clears the cell and boots the
#                           active pair).
#   --reboot                --handover, then sync and reboot; poll for a return and
#                           classify the outcome (stock fallback / target via SSH /
#                           unverified). Verification of OUR image is console-side:
#                           this target image is not expected to accept this key.
#
# WRITE GATES
#   --write/--handover/--reboot REFUSE unless ALL of these hold:
#     --attended        a human is at the bench, able to power-cycle the box and hold
#                       RESET through the counter for the physical TFTP recovery;
#     --recovery-armed  the operator asserts that door is armed; additionally
#                       tools/recovery-card.sh must PASS (recovery.bin md5, TFTP on
#                       UDP 69, host 192.168.1.88) and tools/bench-link.sh must PASS;
#     --image PATH      validated sysupgrade container (luofu-image.py check + the
#                       independent byte checks in this script);
#     --reboot also requires a read-only UART capture to be armed.
#
# EXIT CODES
#   0  success / inspection ready
#   1  failed safely (nothing or only the inactive pair written; recovery plan printed)
#   2  usage error
#   3  completed but the outcome needs a human/console (reboot issued; unverified or
#      stock fallback observed)
#
# EVIDENCE / NO SECRETS
#   The tool prints file paths, sizes and sha256 values only. It never prints the SSH
#   key, any credential, or the contents of the image members. Remote /tmp paths carry
#   a timestamp tag; staged files are removed on a successful run.
#
# SAFETY RULES ENCODED HERE (see BENCH-FACTS.md, LESSONS.md, RUNBOOK.md)
#   - default read-only; no write without --attended AND --recovery-armed;
#   - mtd partitions are resolved BY LABEL from /proc/mtd, never by bare number, and
#     the measured slot sizes are re-checked (LESSONS.md 21);
#   - only the inactive pair is written; the active pair is fingerprinted before and
#     after and must not change;
#   - no env write, ever (the loader owns mtd3/mtd4); no fw_setenv call exists;
#   - a partial write never moves the selector; the selector move is the last step and
#     is re-verified with a whole-cell read-back;
#   - every failure path prints the recovery plan and the current safe state.
#
# TEST SEAMS (host-side mocked harness only; unset in production)
#   FIRST_INSTALL_RSH, FIRST_INSTALL_RSCP, FIRST_INSTALL_REMOTE_HOST,
#   FIRST_INSTALL_PYTHON, FIRST_INSTALL_IMAGE_TOOL,
#   FIRST_INSTALL_BENCH_LINK_CMD, FIRST_INSTALL_RECOVERY_CARD_CMD,
#   FIRST_INSTALL_UART_CHECK_CMD, FIRST_INSTALL_POLL_ATTEMPTS,
#   FIRST_INSTALL_POLL_INTERVAL, FIRST_INSTALL_REBOOT_DELAY.
#
# usage:
#   tools/first-install-stock.sh                       # read-only inspection
#   tools/first-install-stock.sh --inspect --image <container>
#   tools/first-install-stock.sh --write --attended --recovery-armed --image <container>
#   tools/first-install-stock.sh --handover --attended --recovery-armed --image <container>
#   tools/first-install-stock.sh --reboot --attended --recovery-armed --image <container>
#   options: --tag NAME  --expect-active a|b  --dry-run  --keep  -h|--help
set -uo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
export LC_ALL=C

# ---- measured constants (BENCH-FACTS.md 5, TARGET-DESIGN.md 3.3, 5.1) -------
KERNEL_SLOT_SIZE=8650752          # 0x840000, kernela/kernelb
ROOTFS_PART_SIZE=24379392         # 0x1740000, rootfsa/rootfsb (proc_mtd)
ROOTFS_IMAGE_BUDGET=24313856      # the image recipe budget inside the partition
UBI_PEB_SIZE=131072
UBI_VID_HDR_OFFSET=2048
GATE_MAGIC=d7b7ab1e
BOARD_NAME=cudy_wr3000-v2
TARGET_NAME=hisilicon/luofu
MEASURED_LABELS="kernela kernelb rootfsa rootfsb rootfs_data upgrade enva envb"

# ---- defaults / seams -------------------------------------------------------
RSH=${FIRST_INSTALL_RSH:-$ROOT/tools/rsh.sh}
RSCP=${FIRST_INSTALL_RSCP:-$ROOT/tools/rscp.sh}
REMOTE_HOST=${FIRST_INSTALL_REMOTE_HOST:-root@192.168.10.1}
IMAGE_TOOL=${FIRST_INSTALL_IMAGE_TOOL:-$ROOT/opensource/target-skeleton/tools/luofu-image.py}
BENCH_LINK_CMD=${FIRST_INSTALL_BENCH_LINK_CMD:-$ROOT/tools/bench-link.sh}
RECOVERY_CARD_CMD=${FIRST_INSTALL_RECOVERY_CARD_CMD:-$ROOT/tools/recovery-card.sh}
UART_CHECK_CMD=${FIRST_INSTALL_UART_CHECK_CMD:-}
POLL_ATTEMPTS=${FIRST_INSTALL_POLL_ATTEMPTS:-30}
POLL_INTERVAL=${FIRST_INSTALL_POLL_INTERVAL:-5}
REBOOT_DELAY=${FIRST_INSTALL_REBOOT_DELAY:-2}

MODE=inspect
IMAGE=""
TAG=""
EXPECT_ACTIVE=""
DRY_RUN=0
KEEP=0
ATTENDED=0
RECOVERY_ARMED=0

STATE=none            # none | kernel_written | rootfs_written | verified
SELECTOR_MOVED=0
FINALIZED=0
PLAN_PRINTED=0
BLOCKERS=0
STOCK_READY=0
WORK=""
DEVICE_SCRIPT=""
PY=""
REMOTE_KERNEL=""
REMOTE_ROOT=""
BOOT_ID=""
ACTIVE_PAIR=""
TARGET_PAIR=""
BOOTFLAG=""
KERNEL_FILE=""
ROOT_FILE=""
KERNEL_SIZE=0
ROOT_SIZE=0
KERNEL_SHA=""
ROOT_SHA=""
KERNEL_SLOT_SHA=""
ROOT_PART_SHA=""
ROOT_PEB0_SHA=""
BOARD_DIR=""
ACTIVE_KERNEL_SHA0=""
ACTIVE_ROOTFS0_SHA0=""
declare -A P=()      # parsed FI_* probe values

say()  { printf '%s\n' "$*"; }
warn() { printf 'WARNING: %s\n' "$*" >&2; }
err()  { printf 'ERROR: %s\n' "$*" >&2; }

usage() {
	sed -n '3,100p' "$0" | sed 's/^# \{0,1\}//'
}

die_usage() {
	err "$*"
	usage >&2
	FINALIZED=1
	exit 2
}

# ---- recovery plan / abort --------------------------------------------------
print_recovery_plan() {
	local detail=${1:-}
	[ "$PLAN_PRINTED" -eq 1 ] && return 0
	PLAN_PRINTED=1
	say ""
	say "=================================================================="
	say " RECOVERY PLAN - read before touching the box"
	say "=================================================================="
	[ -n "$detail" ] && say " reason: $detail"
	say " safe state: writes=$STATE selector_moved=$SELECTOR_MOVED active_pair=${ACTIVE_PAIR:-unknown} target_pair=${TARGET_PAIR:-unknown}"
	case "$SELECTOR_MOVED" in
	1)
		say " The selector now names the WRITTEN pair. If the box is still up over SSH, cancel with"
		say " the ACTIVE pair's record value (A = 0x10, B = 0x11) written on the device:"
		say "     printf '0x10\\n' > /sys/devices/platform/sysenv/boot_reg   # when the ACTIVE pair is A"
		say "     printf '0x11\\n' > /sys/devices/platform/sysenv/boot_reg   # when the ACTIVE pair is B"
		say " then: cat /sys/devices/platform/sysenv/boot_reg   (must show the active pair record)."
		say " A true power-on clears the SYSCTRL cell, so a physical power cycle before the next"
		say " boot returns to the active (stock) pair. A warm reboot takes the loader's failover"
		say " path to the written pair - do NOT warm-reboot."
		;;
	*)
		say " The selector was NOT moved, so the box still boots the ACTIVE pair."
		if [ "$STATE" = kernel_written ] || [ "$STATE" = rootfs_written ]; then
			say " The INACTIVE pair may be partially written. Do not hand it over; re-run the"
			say " install when the failure is understood, or leave it (the active pair boots)."
		else
			say " No flash write happened: the box is unaffected."
		fi
		;;
	esac
	say ""
	say " If the box is unreachable: recovery is physical. On the host:"
	say "   tools/bench-link.sh --apply"
	say "   tools/recovery-card.sh --arm"
	say "   tools/uart-capture.sh start --label firstinstall-recover   # READ-ONLY console"
	say " Then the human: power OFF, hold RESET, power ON still holding; the console must show"
	say " 'RESET button is pressed for: 2 second(s)' / 'Resetting...' / 'recovery button press',"
	say " then the loader TFTPs recovery.bin from 192.168.1.88. Recovery restores the stock"
	say " firmware; the overlay comes back empty."
	say "=================================================================="
}

abort() {
	local reason=$*
	err "$reason"
	say ""
	say "RESULT: FAILED SAFELY - aborting before the next step"
	print_recovery_plan "$reason"
	FINALIZED=1
	exit 1
}

cleanup() {
	[ "$KEEP" -eq 1 ] && { [ -n "$WORK" ] && warn "kept work dir: $WORK"; return; }
	[ -n "$WORK" ] && rm -rf "$WORK"
}

on_exit() {
	local rc=$?
	if [ "$FINALIZED" -ne 1 ] && [ "$PLAN_PRINTED" -ne 1 ] && [ "$rc" -ne 0 ]; then
		print_recovery_plan "unexpected exit (rc=$rc)"
	fi
	cleanup
}
trap on_exit EXIT

# ---- small helpers ---------------------------------------------------------
be32_hex() { od -An -tx1 -N4 -j "$2" "$1" 2>/dev/null | tr -d ' \n'; }
be32_dec() {
	local h
	h=$(be32_hex "$1" "$2") || return 1
	[ "${#h}" -eq 8 ] || return 1
	echo "$((0x$h))"
}
hexval() {
	[ -n "$1" ] || return 1
	echo "$((0x$(printf '%s' "$1" | sed 's/^0[xX]//')))"
}
file_sha() { sha256sum "$1" | cut -d' ' -f1; }
file_size() { wc -c < "$1" | tr -d ' '; }
pair_value() { [ "$1" = a ] && echo 10 || echo 11; }
other_pair() { [ "$1" = a ] && echo b || echo a; }

# sha256 of <file> followed by 0xff padding up to <total-size>
slot_sha() { # <file> <total-size> <label>
	"$PY" - "$1" "$2" "$3" <<'PYEOF'
import hashlib, sys
path, total, label = sys.argv[1], int(sys.argv[2]), sys.argv[3]
h = hashlib.sha256()
n = 0
with open(path, "rb") as f:
    while True:
        b = f.read(1 << 20)
        if not b:
            break
        n += len(b)
        h.update(b)
if n > total:
    sys.stderr.write("%s: %s is %d B, over the %d B region\n" % (label, path, n, total))
    sys.exit(1)
pad = total - n
while pad:
    chunk = min(pad, 1 << 20)
    h.update(b"\xff" * chunk)
    pad -= chunk
print(h.hexdigest())
PYEOF
}

manifest_get() { sed -n "s/^$1:[[:space:]]*//p" "$2" 2>/dev/null | head -n 1; }

# ---- argument parsing ------------------------------------------------------
parse_args() {
	while [ $# -gt 0 ]; do
		case "$1" in
		--inspect) MODE=inspect ;;
		--write) MODE=write ;;
		--handover) MODE=handover ;;
		--reboot) MODE=reboot ;;
		--image) IMAGE=${2:-}; [ -n "$IMAGE" ] || die_usage "--image needs a path"; shift ;;
		--tag) TAG=${2:-}; [ -n "$TAG" ] || die_usage "--tag needs a name"; shift ;;
		--expect-active) EXPECT_ACTIVE=${2:-}; shift ;;
		--attended) ATTENDED=1 ;;
		--recovery-armed) RECOVERY_ARMED=1 ;;
		--dry-run) DRY_RUN=1 ;;
		--keep) KEEP=1 ;;
		-h|--help) usage; FINALIZED=1; exit 0 ;;
		*) die_usage "unknown argument: $1" ;;
		esac
		shift
	done
	case "$EXPECT_ACTIVE" in
	""|a|b) ;;
	*) die_usage "--expect-active must be a or b" ;;
	esac
	case "$TAG" in
	"") TAG=$(date -u +%Y%m%dT%H%M%SZ) ;;
	*[!A-Za-z0-9_-]*) die_usage "--tag may only use [A-Za-z0-9_-]" ;;
	esac
	case "$POLL_ATTEMPTS$POLL_INTERVAL$REBOOT_DELAY" in
	*[!0-9]*) die_usage "poll seams must be integers" ;;
	esac
	if [ "$MODE" != inspect ]; then
		[ "$ATTENDED" -eq 1 ] || die_usage "$MODE requires --attended (a human at the bench can power-cycle the box and hold RESET)"
		[ "$RECOVERY_ARMED" -eq 1 ] || die_usage "$MODE requires --recovery-armed (the physical RESET+TFTP recovery door is armed)"
		[ -n "$IMAGE" ] || die_usage "$MODE requires --image <built sysupgrade container>; nothing is written without a validated image"
	fi
	if [ -n "$IMAGE" ] && [ ! -f "$IMAGE" ]; then
		err "image not found: $IMAGE"
		FINALIZED=1
		exit 1
	fi
}

# ---- host preflight --------------------------------------------------------
uart_capture_armed() {
	local pf pid
	for pf in "$ROOT"/build/uart-logs/*.pid; do
		[ -f "$pf" ] || continue
		pid=$(cat "$pf" 2>/dev/null) || continue
		case "$pid" in ''|*[!0-9]*) continue ;; esac
		kill -0 "$pid" 2>/dev/null && return 0
	done
	pgrep -f 'timeout [0-9]+ cat' >/dev/null 2>&1 && return 0
	return 1
}

host_preflight() {
	say ""
	say "== host preflight =="
	[ -x "$RSH" ] || abort "missing/not executable rsh helper: $RSH"
	[ -x "$RSCP" ] || abort "missing/not executable rscp helper: $RSCP"
	for cand in "${FIRST_INSTALL_PYTHON:-}" "$ROOT/.provision-venv/bin/python" python3; do
		[ -n "$cand" ] || continue
		if command -v "$cand" >/dev/null 2>&1 && "$cand" -c 'import hashlib' >/dev/null 2>&1; then
			PY=$cand
			break
		fi
	done
	[ -n "$PY" ] || abort "no usable python3 for the image validation"
	export PYTHONDONTWRITEBYTECODE=1
	say "  python:      $PY"
	if [ -n "$IMAGE" ]; then
		[ -f "$IMAGE_TOOL" ] || abort "image validation tool not found: $IMAGE_TOOL"
		say "  image:       $IMAGE"
		say "  image tool:  $IMAGE_TOOL"
	fi
	if [ "$MODE" != inspect ]; then
		say "  mode:        $MODE (attended=yes recovery-armed=yes)"
		if ! "$BENCH_LINK_CMD" >"$WORK/bench-link.log" 2>&1; then
			cat "$WORK/bench-link.log" >&2 || true
			abort "host bench link is not ready (tools/bench-link.sh); fix with: tools/bench-link.sh --apply"
		fi
		say "  bench link:  PASS"
		if ! "$RECOVERY_CARD_CMD" >"$WORK/recovery-card.log" 2>&1; then
			cat "$WORK/recovery-card.log" >&2 || true
			abort "recovery door is NOT READY (tools/recovery-card.sh); arm it before any write"
		fi
		say "  recovery:    READY (recovery.bin md5, TFTP on UDP 69, host 192.168.1.88)"
		if [ "$MODE" = reboot ]; then
			if [ -n "$UART_CHECK_CMD" ]; then
				"$UART_CHECK_CMD" >"$WORK/uart-check.log" 2>&1 || {
					cat "$WORK/uart-check.log" >&2 || true
					abort "read-only UART capture is not armed; a reboot without it cannot prove which image ran"
				}
			else
				uart_capture_armed || abort "no read-only UART capture is running; arm it first: tools/uart-capture.sh start --label firstinstall"
			fi
			say "  uart capture: armed (read-only)"
		fi
	else
		say "  mode:        inspect (read-only; no flash write)"
		if "$BENCH_LINK_CMD" >"$WORK/bench-link.log" 2>&1; then
			say "  bench link:  PASS"
		else
			warn "host bench link is not ready (tools/bench-link.sh) - inspection continues"
		fi
		if "$RECOVERY_CARD_CMD" >"$WORK/recovery-card.log" 2>&1; then
			say "  recovery:    READY"
		else
			warn "recovery door is NOT ready (tools/recovery-card.sh) - arm it before any write"
		fi
	fi
}

# ---- image validation (host-only bytes) ------------------------------------
validate_image() {
	say ""
	say "== image validation (host-only, from the bytes) =="
	[ -n "$IMAGE" ] || abort "no --image given; refusing (a first install needs a validated container)"
	local img_size
	img_size=$(file_size "$IMAGE")
	say "  file:        $IMAGE ($img_size B, sha256 $(file_sha "$IMAGE"))"

	if ! "$PY" "$IMAGE_TOOL" check-container "$IMAGE" >"$WORK/check-container.log" 2>&1; then
		cat "$WORK/check-container.log" >&2 || true
		abort "luofu-image.py check-container REFUSED the container"
	fi
	say "  check:       luofu-image.py check-container PASS"
	grep -E '^  (control|kernel slice|rootfs UBI|install status):' "$WORK/check-container.log" | sed 's/^/  /' || true

	local members bd count control
	members=$("$PY" - "$IMAGE" <<'PYEOF'
import sys, tarfile
with tarfile.open(sys.argv[1], "r:") as t:
    for m in t.getmembers():
        print(m.name)
PYEOF
) || abort "cannot list the container tar members"
	bd=$(printf '%s\n' "$members" | sed -n 's#^\(sysupgrade-[A-Za-z0-9._-]*\)/*$#\1#p' | sort -u)
	count=$(printf '%s\n' "$bd" | grep -c . || true)
	[ "$count" -eq 1 ] || abort "container has $count sysupgrade-*/ board directories (want exactly 1)"
	BOARD_DIR=$bd

	control=$("$PY" - "$IMAGE" "$BOARD_DIR/CONTROL" <<'PYEOF'
import sys, tarfile
with tarfile.open(sys.argv[1], "r:") as t:
    sys.stdout.write(t.extractfile(sys.argv[2]).read().decode("ascii", "replace"))
PYEOF
) || abort "container is missing $BOARD_DIR/CONTROL"
	printf '%s\n' "$control" | grep -qx "BOARD=$BOARD_NAME" || abort "CONTROL BOARD does not match $BOARD_NAME"
	printf '%s\n' "$control" | grep -qx "TARGET=$TARGET_NAME" || abort "CONTROL TARGET does not match $TARGET_NAME"
	say "  identity:    BOARD=$BOARD_NAME TARGET=$TARGET_NAME"

	KERNEL_FILE="$WORK/kernel"
	ROOT_FILE="$WORK/root"
	"$PY" - "$IMAGE" "$BOARD_DIR/kernel" "$KERNEL_FILE" <<'PYEOF' || abort "cannot extract the kernel member"
import sys, tarfile
with tarfile.open(sys.argv[1], "r:") as t:
    data = t.extractfile(sys.argv[2]).read()
open(sys.argv[3], "wb").write(data)
PYEOF
	"$PY" - "$IMAGE" "$BOARD_DIR/root" "$ROOT_FILE" <<'PYEOF' || abort "cannot extract the root member"
import sys, tarfile
with tarfile.open(sys.argv[1], "r:") as t:
    data = t.extractfile(sys.argv[2]).read()
open(sys.argv[3], "wb").write(data)
PYEOF
	"$PY" - "$IMAGE" "$BOARD_DIR/fip-manifest.txt" "$WORK/manifest" <<'PYEOF' || abort "cannot extract fip-manifest.txt"
import sys, tarfile
with tarfile.open(sys.argv[1], "r:") as t:
    data = t.extractfile(sys.argv[2]).read()
open(sys.argv[3], "wb").write(data)
PYEOF
	"$PY" - "$IMAGE" "$BOARD_DIR/INSTALL-STATUS.txt" "$WORK/install-status" <<'PYEOF' || abort "cannot extract INSTALL-STATUS.txt"
import sys, tarfile
with tarfile.open(sys.argv[1], "r:") as t:
    data = t.extractfile(sys.argv[2]).read()
open(sys.argv[3], "wb").write(data)
PYEOF
	[ -s "$KERNEL_FILE" ] || abort "kernel member is empty"
	[ -s "$ROOT_FILE" ] || abort "root member is empty"

	KERNEL_SIZE=$(file_size "$KERNEL_FILE")
	ROOT_SIZE=$(file_size "$ROOT_FILE")
	say "  members:     kernel $KERNEL_SIZE B, root $ROOT_SIZE B"
	[ "$KERNEL_SIZE" -le "$KERNEL_SLOT_SIZE" ] || abort "kernel member is $KERNEL_SIZE B, over the $KERNEL_SLOT_SIZE B kernel slot"
	[ "$ROOT_SIZE" -le "$ROOTFS_IMAGE_BUDGET" ] || abort "rootfs member is $ROOT_SIZE B, over the $ROOTFS_IMAGE_BUDGET B image budget"
	[ "$((ROOT_SIZE % UBI_PEB_SIZE))" -eq 0 ] || abort "rootfs UBI size $ROOT_SIZE B is not a whole number of $UBI_PEB_SIZE B PEBs"

	[ "$(be32_hex "$KERNEL_FILE" 0)" = 27051956 ] || abort "kernel member does not start with a legacy uImage magic (0x27051956)"
	local gate_off gate_magic man_size man_sha man_limit man_gate_off
	man_size=$(manifest_get slice-size "$WORK/manifest")
	man_sha=$(manifest_get slice-sha256 "$WORK/manifest")
	man_limit=$(manifest_get slot-limit "$WORK/manifest")
	man_gate_off=$(manifest_get gate-offset "$WORK/manifest")
	[ "$man_size" = "$KERNEL_SIZE" ] || abort "fip-manifest slice-size '$man_size' does not match the kernel member ($KERNEL_SIZE)"
	[ "$man_limit" = "$KERNEL_SLOT_SIZE" ] || abort "fip-manifest slot-limit '$man_limit' is not the measured $KERNEL_SLOT_SIZE"
	[ -n "$man_sha" ] || abort "fip-manifest has no slice-sha256"
	KERNEL_SHA=$(file_sha "$KERNEL_FILE")
	[ "$man_sha" = "$KERNEL_SHA" ] || abort "fip-manifest slice-sha256 does not match the kernel member"
	[ -n "$man_gate_off" ] || abort "fip-manifest has no gate-offset"
	gate_off=$(hexval "$man_gate_off") || abort "fip-manifest gate-offset is not numeric"
	[ "$gate_off" -lt "$KERNEL_SIZE" ] || abort "fip-manifest gate-offset $man_gate_off is outside the kernel member"
	gate_magic=$(be32_hex "$KERNEL_FILE" "$gate_off")
	[ "$gate_magic" = "$GATE_MAGIC" ] || abort "no FIP gate magic 0x$GATE_MAGIC at kernel offset $gate_off (read 0x${gate_magic:-none})"
	say "  kernel:      uImage magic OK; FIP gate 0x$GATE_MAGIC at 0x$(printf '%x' "$gate_off"); sha256 $KERNEL_SHA"

	[ "$(be32_hex "$ROOT_FILE" 0)" = 55424923 ] || abort "rootfs member does not start with the UBI# EC magic"
	[ "$(be32_dec "$ROOT_FILE" 16)" = "$UBI_VID_HDR_OFFSET" ] || abort "rootfs UBI vid_hdr_offset is not the measured $UBI_VID_HDR_OFFSET"
	[ "$(be32_hex "$ROOT_FILE" "$UBI_VID_HDR_OFFSET")" = 55424921 ] || abort "rootfs member has no UBI! VID header at the measured offset"
	ROOT_SHA=$(file_sha "$ROOT_FILE")
	say "  rootfs:      UBI#/UBI! headers OK (p=$UBI_PEB_SIZE O=$UBI_VID_HDR_OFFSET); sha256 $ROOT_SHA"

	KERNEL_SLOT_SHA=$(slot_sha "$KERNEL_FILE" "$KERNEL_SLOT_SIZE" "kernel slot") || abort "cannot compute the expected kernel-slot read-back hash"
	ROOT_PART_SHA=$(slot_sha "$ROOT_FILE" "$ROOTFS_PART_SIZE" "rootfs partition") || abort "cannot compute the expected rootfs-partition read-back hash"
	ROOT_PEB0_SHA=$(dd if="$ROOT_FILE" bs="$UBI_PEB_SIZE" count=1 2>/dev/null | sha256sum | cut -d' ' -f1)
	say "  read-back:   expected kernel slot sha256 $KERNEL_SLOT_SHA"
	say "               expected rootfs part sha256 $ROOT_PART_SHA (PEB0 $ROOT_PEB0_SHA)"

	if grep -q 'NOT FLASHABLE' "$WORK/install-status" 2>/dev/null; then
		warn "the container carries the NOT FLASHABLE provenance marker (it has never booted)."
		warn "This attended first-install is the step that closes that marker; the risk is taken deliberately."
	fi
	say "  image:       PASS (independent read-back of the container bytes)"
}

# ---- device-side script -----------------------------------------------------
write_device_script() {
	DEVICE_SCRIPT="$WORK/first-install-device.sh"
	cat >"$DEVICE_SCRIPT" <<'FI_DEVICE_SCRIPT'
#!/bin/sh
# first-install-device.sh - device-side half of tools/first-install-stock.sh.
# Fed to sh -s over the project's rsh transport; runs on the STOCK vendor firmware.
# Re-derives every partition from /proc/mtd by LABEL, re-verifies the staged member
# hashes, and refuses on any mismatch. It never writes the env blocks, the active
# pair, rootfs_data, upgrade, or any vendor data partition. FI_ROOT is a mocked-test
# seam only (empty on the device).
set -u
R=${FI_ROOT:-}
KERNEL_SLOT_SIZE=8650752
ROOTFS_PART_SIZE=24379392
ROOTFS_IMAGE_BUDGET=24313856
UBI_PEB_SIZE=131072
UBI_VID_HDR_OFFSET=2048
MEASURED_LABELS="kernela kernelb rootfsa rootfsb rootfs_data upgrade enva envb"

die() { echo "FI_FAIL: $*"; exit 1; }

mtd_lookup() {
	awk -v want="\"$1\"" '
		$1 ~ /^mtd[0-9]+:$/ {
			name = $4
			for (i = 5; i <= NF; i++) name = name " " $i
			if (name == want) { print substr($1, 1, length($1) - 1), $2; found++ }
		}
		END { exit(found == 1 ? 0 : 1) }
	' "$R/proc/mtd"
}
mtd_label() {
	label=$(awk -v want="$1:" '
		$1 == want {
			name = $4
			for (i = 5; i <= NF; i++) name = name " " $i
			print name; found++
		}
		END { exit(found == 1 ? 0 : 1) }
	' "$R/proc/mtd") || return 1
	label=${label#\"}
	label=${label%\"}
	[ -n "$label" ] || return 1
	echo "$label"
}
mtd_size_dec() {
	case "$1" in ''|*[!0-9a-fA-F]*) return 1 ;; esac
	echo "$((0x$1))"
}
hex32() { hexdump -v -n 4 -s "$2" -e '1/1 "%02x"' "$1" 2>/dev/null; }
be32() { local h; h=$(hex32 "$1" "$2"); [ "${#h}" -eq 8 ] || return 1; echo "$((0x$h))"; }
file_sha() { sha256sum "$1" | cut -d' ' -f1; }
file_size() { wc -c < "$1" | tr -d ' '; }
region_sha() {
	dd if="$1" bs=$UBI_PEB_SIZE count=$(( ($2 + UBI_PEB_SIZE - 1) / UBI_PEB_SIZE )) 2>/dev/null \
		| head -c "$2" | sha256sum | cut -d' ' -f1
}
normreg() { echo "$1" | tr 'A-F' 'a-f' | sed 's/^0x//; s/[^0-9a-f].*//' | sed 's/^0*//; s/^$/0/'; }
pair_value() { [ "$1" = a ] && echo 10 || echo 11; }
other_pair() { [ "$1" = a ] && echo b || echo a; }
tool_present() { command -v "$1" >/dev/null 2>&1 && echo 1 || echo 0; }

probe() {
	[ -r "$R/proc/mtd" ] || die "no /proc/mtd on this system"
	BOOT_ID=$(cat "$R/proc/sys/kernel/random/boot_id" 2>/dev/null | head -1)
	UPTIME=$(cut -d. -f1 "$R/proc/uptime" 2>/dev/null | head -1)
	KREL=$(sed -n 's/^Linux version \([^ ]*\).*/\1/p' "$R/proc/version" 2>/dev/null | head -1)
	OPENWRT=$(cat "$R/etc/openwrt_release" 2>/dev/null | tr '\n' ';' | tr ' ' '_')
	HAS_HSAN_APPM=0; [ -e "$R/etc/init.d/hsan_appm" ] && HAS_HSAN_APPM=1
	VENDOR_KO_COUNT=$(ls "$R/lib/hisilicon/ko/"*.ko 2>/dev/null | wc -l | tr -d ' ')
	HI_MODULES=$(grep -c '^hi_' "$R/proc/modules" 2>/dev/null || true)
	case "$HI_MODULES" in ''|*[!0-9]*) HI_MODULES=0 ;; esac
	CUSTOM_MARKER=0; [ -e "$R/etc/custom-firmware-version" ] && CUSTOM_MARKER=1
	OMO=$(ls "$R"/lib/modules/*/*.omo-off 2>/dev/null | wc -l | tr -d ' ')
	WIPHY=$(ls "$R/sys/class/ieee80211" 2>/dev/null | wc -l | tr -d ' ')
	CAL2=$(dmesg 2>/dev/null | grep -c 'hwifi_rf_cali_file_load_2g succ' || true)
	CAL5=$(dmesg 2>/dev/null | grep -c 'hwifi_rf_cali_file_load_5g succ' || true)
	case "$CAL2$CAL5" in *[!0-9]*) CAL2=0; CAL5=0 ;; esac
	BOOTFLAG=$(fw_printenv bootflag 2>/dev/null | sed -n 's/^bootflag=//p' | head -1)
	BOOT_REG_RAW=$(cat "$R/sys/devices/platform/sysenv/boot_reg" 2>/dev/null | head -1)
	BOOT_REG=$(normreg "$BOOT_REG_RAW")
	RECOVERY_IFACE=0
	[ -r "$R/sys/devices/platform/sysenv/boot_reg" ] && [ -w "$R/sys/devices/platform/sysenv/boot_reg" ] && RECOVERY_IFACE=1

	for label in $MEASURED_LABELS; do
		entry=$(mtd_lookup "$label") || die "no unique /proc/mtd partition named $label"
		dev=${entry%% *}
		size=$(mtd_size_dec "${entry#* }") || die "cannot read the size of $label"
		echo "FI_SLOT_${label}_DEV=$dev"
		echo "FI_SLOT_${label}_SIZE=$size"
	done

	UBI_NUM=$(cat "$R/sys/class/ubi/ubi0/mtd_num" 2>/dev/null | awk '{print $1}')
	BOOTED_LABEL=""
	if [ -n "$UBI_NUM" ]; then BOOTED_LABEL=$(mtd_label "mtd$UBI_NUM" 2>/dev/null || true); fi
	BOOTED_PAIR=unknown
	case "$BOOTED_LABEL" in
	rootfsa) BOOTED_PAIR=a ;;
	rootfsb) BOOTED_PAIR=b ;;
	esac
	ACTIVE_PAIR=$BOOTED_PAIR
	TARGET_PAIR=unknown
	[ "$ACTIVE_PAIR" = a ] && TARGET_PAIR=b
	[ "$ACTIVE_PAIR" = b ] && TARGET_PAIR=a
	RUNNING_VALUE=$(pair_value "$ACTIVE_PAIR")
	RECORDED_OK=0
	[ "$ACTIVE_PAIR" != unknown ] && [ "$BOOT_REG" = "$RUNNING_VALUE" ] && RECORDED_OK=1

	TMP_FREE_KB=$(df -k "$R/tmp" 2>/dev/null | awk 'NR == 2 { print $4 }')
	case "$TMP_FREE_KB" in ''|*[!0-9]*) TMP_FREE_KB=0 ;; esac

	AK_ENTRY=$(mtd_lookup "kernel$ACTIVE_PAIR" 2>/dev/null || true)
	AR_ENTRY=$(mtd_lookup "rootfs$ACTIVE_PAIR" 2>/dev/null || true)
	TK_ENTRY=$(mtd_lookup "kernel$TARGET_PAIR" 2>/dev/null || true)
	TR_ENTRY=$(mtd_lookup "rootfs$TARGET_PAIR" 2>/dev/null || true)
	if [ -n "$AK_ENTRY" ]; then ACTIVE_KERNEL_SHA=$(region_sha "$R/dev/${AK_ENTRY%% *}" "$KERNEL_SLOT_SIZE"); else ACTIVE_KERNEL_SHA=none; fi
	if [ -n "$AR_ENTRY" ]; then ACTIVE_ROOTFS0_SHA=$(region_sha "$R/dev/${AR_ENTRY%% *}" "$UBI_PEB_SIZE"); else ACTIVE_ROOTFS0_SHA=none; fi
	if [ -n "$TK_ENTRY" ]; then TARGET_KERNEL_SHA=$(region_sha "$R/dev/${TK_ENTRY%% *}" "$KERNEL_SLOT_SIZE"); else TARGET_KERNEL_SHA=none; fi
	if [ -n "$TR_ENTRY" ]; then TARGET_ROOTFS0_SHA=$(region_sha "$R/dev/${TR_ENTRY%% *}" "$UBI_PEB_SIZE"); else TARGET_ROOTFS0_SHA=none; fi

	echo "FI_BOOT_ID=$BOOT_ID"
	echo "FI_UPTIME=$UPTIME"
	echo "FI_KERNEL_RELEASE=$KREL"
	echo "FI_OPENWRT=$OPENWRT"
	echo "FI_HAS_HSAN_APPM=$HAS_HSAN_APPM"
	echo "FI_VENDOR_KO_COUNT=$VENDOR_KO_COUNT"
	echo "FI_HI_MODULES=$HI_MODULES"
	echo "FI_CUSTOM_MARKER=$CUSTOM_MARKER"
	echo "FI_OMO=$OMO"
	echo "FI_WIPHY=$WIPHY"
	echo "FI_CAL2=$CAL2"
	echo "FI_CAL5=$CAL5"
	echo "FI_BOOTFLAG=$BOOTFLAG"
	echo "FI_BOOT_REG_RAW=$BOOT_REG_RAW"
	echo "FI_BOOT_REG=$BOOT_REG"
	echo "FI_RECOVERY_IFACE=$RECOVERY_IFACE"
	echo "FI_UBI_MTD_NUM=$UBI_NUM"
	echo "FI_BOOTED_ROOTFS_LABEL=$BOOTED_LABEL"
	echo "FI_BOOTED_PAIR=$BOOTED_PAIR"
	echo "FI_ACTIVE_PAIR=$ACTIVE_PAIR"
	echo "FI_TARGET_PAIR=$TARGET_PAIR"
	echo "FI_RUNNING_VALUE=$RUNNING_VALUE"
	echo "FI_BOOT_REG_RECORDED_OK=$RECORDED_OK"
	echo "FI_ACTIVE_KERNEL_SHA=$ACTIVE_KERNEL_SHA"
	echo "FI_ACTIVE_ROOTFS0_SHA=$ACTIVE_ROOTFS0_SHA"
	echo "FI_TARGET_KERNEL_SHA=$TARGET_KERNEL_SHA"
	echo "FI_TARGET_ROOTFS0_SHA=$TARGET_ROOTFS0_SHA"
	echo "FI_TMP_FREE_KB=$TMP_FREE_KB"
	for t in mtd ubiformat sha256sum dd hexdump head sync fw_printenv dmesg; do
		echo "FI_TOOL_$t=$(tool_present $t)"
	done
	echo "FI_PROBE_OK=1"
}

slot_pair_checks() { # <expected-active> <target>
	[ "$1" = a ] || [ "$1" = b ] || die "bad expected active pair '$1'"
	[ "$2" = a ] || [ "$2" = b ] || die "bad target pair '$2'"
	[ "$2" = "$(other_pair "$1")" ] || die "target pair $2 is not the inactive pair of $1"
	probe >/dev/null || die "probe failed inside slot_pair_checks"
	[ "$ACTIVE_PAIR" = "$1" ] || die "active pair is now $ACTIVE_PAIR, expected $1 (box rebooted or state changed)"
	if [ -n "${FI_BOOT_ID_EXPECT:-}" ] && [ "$BOOT_ID" != "$FI_BOOT_ID_EXPECT" ]; then
		die "boot_id changed (expected $FI_BOOT_ID_EXPECT, got $BOOT_ID)"
	fi
	EM_ENTRY=$(mtd_lookup "kernel$2") || die "no kernel$2"
	ER_ENTRY=$(mtd_lookup "rootfs$2") || die "no rootfs$2"
	EM_KSIZE=$(mtd_size_dec "${EM_ENTRY#* }") || die "cannot read kernel$2 size"
	ER_RSIZE=$(mtd_size_dec "${ER_ENTRY#* }") || die "cannot read rootfs$2 size"
	[ "$EM_KSIZE" -eq "$KERNEL_SLOT_SIZE" ] || die "kernel$2 is $EM_KSIZE B, not the measured $KERNEL_SLOT_SIZE"
	[ "$ER_RSIZE" -eq "$ROOTFS_PART_SIZE" ] || die "rootfs$2 is $ER_RSIZE B, not the measured $ROOTFS_PART_SIZE"
	KDEV="$R/dev/${EM_ENTRY%% *}"
	RDEV="$R/dev/${ER_ENTRY%% *}"
	[ -e "$KDEV" ] || die "missing device for kernel$2: $KDEV"
	[ -e "$RDEV" ] || die "missing device for rootfs$2: $RDEV"
	[ -r "$KDEV" ] && [ -w "$KDEV" ] || die "kernel$2 device is not read/write"
	[ -r "$RDEV" ] && [ -w "$RDEV" ] || die "rootfs$2 device is not read/write"
}

verify_member() { # <path> <size> <sha256> <what>
	[ -f "$R$1" ] || die "$4 not staged on the device: $1"
	VSIZE=$(file_size "$R$1")
	[ "$VSIZE" = "$2" ] || die "$4 size is $VSIZE B, expected $2"
	VSHA=$(file_sha "$R$1")
	[ "$VSHA" = "$3" ] || die "$4 sha256 $VSHA != expected $3"
}

write_pair() { # <boot-id> <active> <target> <kpath> <ksize> <ksha> <kslot-sha> <rpath> <rsize> <rsha> <rpart-sha>
	[ "$#" -eq 11 ] || die "write_pair needs 11 arguments"
	FI_BOOT_ID_EXPECT=$1; EA=$2; T=$3; KP=$4; KS=$5; KH=$6; KSLOT=$7; RP=$8; RS=$9; RH=${10}; RPART=${11}
	[ "$KS" -gt 0 ] && [ "$KS" -le "$KERNEL_SLOT_SIZE" ] || die "kernel member size $KS is over the slot"
	[ "$RS" -gt 0 ] && [ "$RS" -le "$ROOTFS_IMAGE_BUDGET" ] || die "rootfs member size $RS is over the image budget"
	slot_pair_checks "$EA" "$T"
	verify_member "$KP" "$KS" "$KH" "kernel member"
	verify_member "$RP" "$RS" "$RH" "rootfs member"
	[ "$(hex32 "$R$KP" 0)" = 27051956 ] || die "kernel member is not a legacy uImage"
	[ "$(hex32 "$R$RP" 0)" = 55424923 ] || die "rootfs member is not a UBI image"
	[ "$(be32 "$R$RP" 16)" = "$UBI_VID_HDR_OFFSET" ] || die "rootfs member vid_hdr_offset is not measured"
	[ "$(hex32 "$R$RP" "$UBI_VID_HDR_OFFSET")" = 55424921 ] || die "rootfs member has no UBI! VID header"

	FREE_NOW=$(df -k "$R/tmp" 2>/dev/null | awk 'NR == 2 { print $4 }')
	case "$FREE_NOW" in ''|*[!0-9]*) FREE_NOW=0 ;; esac
	[ "$FREE_NOW" -ge 8192 ] || die "/tmp free space ${FREE_NOW} KiB is below the 8192 KiB staging floor"

	echo "FI_WRITE_BEGIN active=$EA target=$T kernel=$KP rootfs=$RP"
	echo "FI_KERNEL_WRITE_START kernel$T=$EM_KSIZE"
	mtd erase "kernel$T" >"$R/tmp/fi-erase-kernel.log" 2>&1 \
		|| die "mtd erase kernel$T failed: $(tail -2 "$R/tmp/fi-erase-kernel.log" 2>/dev/null)"
	mtd write "$R$KP" "kernel$T" >"$R/tmp/fi-write-kernel.log" 2>&1 \
		|| die "mtd write kernel$T failed: $(tail -2 "$R/tmp/fi-write-kernel.log" 2>/dev/null)"
	KREAD=$(region_sha "$KDEV" "$KERNEL_SLOT_SIZE")
	[ "$KREAD" = "$KSLOT" ] || die "kernel$T read-back mismatch (got $KREAD, expected $KSLOT); selector still on the active pair"
	echo "FI_KERNEL_WRITE_OK readback=$KREAD"

	echo "FI_ROOTFS_WRITE_START rootfs$T=$ER_RSIZE"
	ubiformat "$RDEV" -y -f "$R$RP" >"$R/tmp/fi-ubiformat.log" 2>&1 \
		|| die "ubiformat rootfs$T failed: $(tail -3 "$R/tmp/fi-ubiformat.log" 2>/dev/null)"
	if grep -qi 'bad block' "$R/tmp/fi-ubiformat.log" 2>/dev/null; then
		die "ubiformat reported bad block(s) on rootfs$T; the written layout cannot be trusted - selector still on the active pair"
	fi
	RREAD=$(region_sha "$RDEV" "$ROOTFS_PART_SIZE")
	[ "$RREAD" = "$RPART" ] || die "rootfs$T read-back mismatch (got $RREAD, expected $RPART); selector still on the active pair"
	echo "FI_ROOTFS_WRITE_OK readback=$RREAD"
	sync
	echo "FI_WRITE_OK"
}

handover_pair() { # <boot-id> <active> <target> <kslot-sha> <rpart-sha>
	[ "$#" -eq 5 ] || die "handover_pair needs 5 arguments"
	FI_BOOT_ID_EXPECT=$1; EA=$2; T=$3; KSLOT=$4; RPART=$5
	slot_pair_checks "$EA" "$T"
	[ "$BOOTED_PAIR" = "$EA" ] || die "booted rootfs pair $BOOTED_PAIR != expected active $EA"
	[ -n "$BOOTFLAG" ] || die "cannot read env bootflag; the locked selector state cannot be trusted"
	[ "$BOOTFLAG" = "$EA" ] || die "env bootflag '$BOOTFLAG' != active pair $EA; the locked selector state cannot be trusted"
	[ "$RECORDED_OK" -eq 1 ] || die "boot_reg 0x$BOOT_REG is not the running-pair record 0x$RUNNING_VALUE (boot_done window or manual value); refusing to move the selector"
	[ "$(region_sha "$KDEV" "$KERNEL_SLOT_SIZE")" = "$KSLOT" ] || die "kernel$T no longer matches the written bytes; refusing the handover"
	[ "$(region_sha "$RDEV" "$ROOTFS_PART_SIZE")" = "$RPART" ] || die "rootfs$T no longer matches the written bytes; refusing the handover"
	VALUE=$(pair_value "$T")
	echo "FI_HANDOVER_BEGIN active=$EA target=$T value=0x$VALUE"
	printf '%s\n' "0x$VALUE" >"$R/sys/devices/platform/sysenv/boot_reg" 2>/dev/null \
		|| die "could not write the boot selector (sysenv boot_reg is not writable)"
	NEW=$(normreg "$(cat "$R/sys/devices/platform/sysenv/boot_reg" 2>/dev/null | head -1)")
	if [ "$NEW" != "$VALUE" ]; then
		printf '0x%s\n' "$RUNNING_VALUE" >"$R/sys/devices/platform/sysenv/boot_reg" 2>/dev/null || true
		die "selector read-back 0x$NEW != 0x$VALUE; restored the active pair record"
	fi
	AFTER_FLAG=$(fw_printenv bootflag 2>/dev/null | sed -n 's/^bootflag=//p' | head -1)
	if [ "$AFTER_FLAG" != "$EA" ]; then
		printf '0x%s\n' "$RUNNING_VALUE" >"$R/sys/devices/platform/sysenv/boot_reg" 2>/dev/null || true
		die "env bootflag changed to '$AFTER_FLAG' during the handover; restored the active pair record"
	fi
	sync
	echo "FI_HANDOVER_OK selector=0x$VALUE env_bootflag=$AFTER_FLAG"
}

cancel_handover() { # <active-pair>
	EA=$1
	[ "$EA" = a ] || [ "$EA" = b ] || die "bad active pair '$EA'"
	probe >/dev/null || die "probe failed in cancel"
	RESTORE=$(pair_value "$EA")
	printf '%s\n' "0x$RESTORE" >"$R/sys/devices/platform/sysenv/boot_reg" 2>/dev/null \
		|| die "could not restore the selector"
	NEW=$(normreg "$(cat "$R/sys/devices/platform/sysenv/boot_reg" 2>/dev/null | head -1)")
	[ "$NEW" = "$RESTORE" ] || die "selector restore read-back 0x$NEW != 0x$RESTORE"
	echo "FI_CANCEL_OK selector=0x$RESTORE"
}

do_reboot() {
	echo "FI_REBOOT_BOOT_ID=${BOOT_ID:-unknown}"
	sync || die "sync failed before reboot"
	echo "FI_REBOOT_ISSUED"
	reboot
	exit 0
}

case "${1:-}" in
probe) probe ;;
verify)
	[ "$#" -eq 4 ] || die "verify needs path size sha256"
	verify_member "$2" "$3" "$4" "staged member"
	echo "FI_VERIFY_OK path=$2 size=$3 sha256=$4"
	;;
write) shift; write_pair "$@" ;;
handover) shift; handover_pair "$@" ;;
cancel) shift; cancel_handover "$@" ;;
reboot) do_reboot ;;
*) die "unknown device subcommand '${1:-}'" ;;
esac
FI_DEVICE_SCRIPT
	chmod +x "$DEVICE_SCRIPT"
	sh -n "$DEVICE_SCRIPT" || abort "generated device script fails sh -n (this is a bug in the tool)"
	say "  device:      helper script $(file_sha "$DEVICE_SCRIPT") (sh -n PASS; fed over ssh stdin, not stored in the repo)"
}

device_run() { # <subcommand> [args...]
	local sub=$1
	shift
	"$RSH" "sh -s $sub $*" <"$DEVICE_SCRIPT"
}

parse_probe() {
	local line k v
	P=()
	while IFS= read -r line; do
		case "$line" in
		FI_*=*)
			k=${line%%=*}
			v=${line#*=}
			P["$k"]=$v
			;;
		esac
	done <<EOF
$1
EOF
}

pget() { printf '%s' "${P[$1]:-}"; }

require_probe_keys() {
	local key
	for key in FI_PROBE_OK FI_BOOT_ID FI_KERNEL_RELEASE FI_ACTIVE_PAIR FI_TARGET_PAIR FI_BOOTFLAG \
		FI_BOOTED_ROOTFS_LABEL FI_BOOT_REG FI_ACTIVE_KERNEL_SHA FI_TARGET_KERNEL_SHA \
		FI_SLOT_kernela_SIZE FI_SLOT_kernelb_SIZE FI_SLOT_rootfsa_SIZE FI_SLOT_rootfsb_SIZE \
		FI_SLOT_rootfs_data_SIZE FI_SLOT_upgrade_SIZE FI_SLOT_enva_SIZE FI_SLOT_envb_SIZE; do
		[ -n "$(pget "$key")" ] || abort "device probe output is missing $key"
	done
	[ "$(pget FI_PROBE_OK)" = 1 ] || abort "device probe did not complete"
}

# ---- device state report / readiness ---------------------------------------
stock_readiness() {
	STOCK_READY=1
	[ "$(pget FI_KERNEL_RELEASE)" = 5.10.201 ] || { STOCK_READY=0; BLOCKERS=$((BLOCKERS + 1)); say "  BLOCKER: kernel $(pget FI_KERNEL_RELEASE) is not the stock 5.10.201"; }
	[ "$(pget FI_HAS_HSAN_APPM)" = 1 ] || { STOCK_READY=0; BLOCKERS=$((BLOCKERS + 1)); say "  BLOCKER: no vendor init marker /etc/init.d/hsan_appm (not stock vendor userspace)"; }
	[ "$(pget FI_VENDOR_KO_COUNT)" -ge 10 ] 2>/dev/null || { STOCK_READY=0; BLOCKERS=$((BLOCKERS + 1)); say "  BLOCKER: only $(pget FI_VENDOR_KO_COUNT) vendor .ko under /lib/hisilicon/ko (not stock)"; }
	[ "$(pget FI_HI_MODULES)" -ge 5 ] 2>/dev/null || { STOCK_READY=0; BLOCKERS=$((BLOCKERS + 1)); say "  BLOCKER: only $(pget FI_HI_MODULES) hi_* modules loaded (vendor stack not up)"; }
	[ "$(pget FI_CUSTOM_MARKER)" = 0 ] || { STOCK_READY=0; BLOCKERS=$((BLOCKERS + 1)); say "  BLOCKER: /etc/custom-firmware-version present: already-customised system, not stock"; }
	[ "$(pget FI_WIPHY)" -ge 2 ] 2>/dev/null || { STOCK_READY=0; BLOCKERS=$((BLOCKERS + 1)); say "  BLOCKER: fewer than 2 wiphys ($(pget FI_WIPHY)): stock radio health not proven"; }
	if [ "$(pget FI_CAL2)" -ge 1 ] 2>/dev/null && [ "$(pget FI_CAL5)" -ge 1 ] 2>/dev/null; then :; else
		STOCK_READY=0; BLOCKERS=$((BLOCKERS + 1)); say "  BLOCKER: Wi-Fi calibration [SUCC] not present on both bands"
	fi
	[ "$(pget FI_OMO)" = 0 ] || { STOCK_READY=0; BLOCKERS=$((BLOCKERS + 1)); say "  BLOCKER: $(pget FI_OMO) .omo-off leftover(s) hidden in the vendor module tree"; }
}

check_probe() { # <mode: inspect|write|handover>
	local mode=$1 label
	ACTIVE_PAIR=$(pget FI_ACTIVE_PAIR)
	TARGET_PAIR=$(pget FI_TARGET_PAIR)
	BOOT_ID=$(pget FI_BOOT_ID)
	BOOTFLAG=$(pget FI_BOOTFLAG)

	say ""
	say "== device state (read-only probe) =="
	say "  kernel:      $(pget FI_KERNEL_RELEASE)  uptime: $(pget FI_UPTIME)s  boot_id: $BOOT_ID"
	say "  openwrt:     $(pget FI_OPENWRT)"
	say "  booted:      ubi0/mtd_num=$(pget FI_UBI_MTD_NUM) label=$(pget FI_BOOTED_ROOTFS_LABEL) -> pair $(pget FI_BOOTED_PAIR)"
	say "  env:         bootflag=$(pget FI_BOOTFLAG)  (never written by this tool)"
	say "  selector:    boot_reg raw='$(pget FI_BOOT_REG_RAW)' low=0x$(pget FI_BOOT_REG)  running-record=0x$(pget FI_RUNNING_VALUE) recorded_ok=$(pget FI_BOOT_REG_RECORDED_OK)"
	say "  active pair: $ACTIVE_PAIR kernel $(pget FI_SLOT_kernel"$ACTIVE_PAIR"_DEV) / rootfs $(pget FI_SLOT_rootfs"$ACTIVE_PAIR"_DEV)  kernel sha256 $(pget FI_ACTIVE_KERNEL_SHA)"
	say "  target pair: $TARGET_PAIR kernel $(pget FI_SLOT_kernel"$TARGET_PAIR"_DEV) / rootfs $(pget FI_SLOT_rootfs"$TARGET_PAIR"_DEV)"
	say "  vendor:      hs_appm=$(pget FI_HAS_HSAN_APPM) vendor_ko=$(pget FI_VENDOR_KO_COUNT) hi_modules=$(pget FI_HI_MODULES) custom_marker=$(pget FI_CUSTOM_MARKER)"
	say "  health:      wiphys=$(pget FI_WIPHY) cal2=$(pget FI_CAL2) cal5=$(pget FI_CAL5) omo_off=$(pget FI_OMO)"
	say "  storage:     /tmp free=$(pget FI_TMP_FREE_KB) KiB"
	for label in $MEASURED_LABELS; do
		say "  slot $label: $(pget FI_SLOT_"$label"_DEV) $(pget FI_SLOT_"$label"_SIZE) B"
	done

	[ "$(pget FI_SLOT_kernela_SIZE)" = "$KERNEL_SLOT_SIZE" ] || { BLOCKERS=$((BLOCKERS + 1)); say "  BLOCKER: kernela is not the measured $KERNEL_SLOT_SIZE B"; }
	[ "$(pget FI_SLOT_kernelb_SIZE)" = "$KERNEL_SLOT_SIZE" ] || { BLOCKERS=$((BLOCKERS + 1)); say "  BLOCKER: kernelb is not the measured $KERNEL_SLOT_SIZE B"; }
	[ "$(pget FI_SLOT_rootfsa_SIZE)" = "$ROOTFS_PART_SIZE" ] || { BLOCKERS=$((BLOCKERS + 1)); say "  BLOCKER: rootfsa is not the measured $ROOTFS_PART_SIZE B"; }
	[ "$(pget FI_SLOT_rootfsb_SIZE)" = "$ROOTFS_PART_SIZE" ] || { BLOCKERS=$((BLOCKERS + 1)); say "  BLOCKER: rootfsb is not the measured $ROOTFS_PART_SIZE B"; }
	[ "$(pget FI_SLOT_enva_SIZE)" = 262144 ] || { BLOCKERS=$((BLOCKERS + 1)); say "  BLOCKER: enva is not the measured 0x40000 B"; }
	[ "$(pget FI_SLOT_envb_SIZE)" = 262144 ] || { BLOCKERS=$((BLOCKERS + 1)); say "  BLOCKER: envb is not the measured 0x40000 B"; }
	case "$ACTIVE_PAIR" in
	a|b) ;;
	*) BLOCKERS=$((BLOCKERS + 1)); say "  BLOCKER: cannot identify the booted rootfs pair (ubi0/mtd_num + /proc/mtd label)"; ACTIVE_PAIR=""; TARGET_PAIR="" ;;
	esac
	if [ -n "$ACTIVE_PAIR" ]; then
		[ "$(pget FI_BOOTED_PAIR)" = "$ACTIVE_PAIR" ] || { BLOCKERS=$((BLOCKERS + 1)); say "  BLOCKER: booted pair disagrees with the probe"; }
		[ "$BOOTFLAG" = "$ACTIVE_PAIR" ] || { BLOCKERS=$((BLOCKERS + 1)); say "  BLOCKER: env bootflag '$BOOTFLAG' != booted pair $ACTIVE_PAIR (inconsistent selector state)"; }
		[ "$TARGET_PAIR" = "$(other_pair "$ACTIVE_PAIR")" ] || { BLOCKERS=$((BLOCKERS + 1)); say "  BLOCKER: cannot derive the inactive pair"; }
		if [ -n "$EXPECT_ACTIVE" ] && [ "$EXPECT_ACTIVE" != "$ACTIVE_PAIR" ]; then
			BLOCKERS=$((BLOCKERS + 1)); say "  BLOCKER: booted pair $ACTIVE_PAIR != --expect-active $EXPECT_ACTIVE"
		fi
	fi

	if [ "$mode" = inspect ]; then
		stock_readiness
		if [ "$BLOCKERS" -gt 0 ]; then
			say ""
			err "inspection found $BLOCKERS blocker(s); the box is NOT ready for a first install"
			FINALIZED=1
			exit 1
		fi
		if [ "$STOCK_READY" -ne 1 ]; then
			say ""
			err "the box is reachable but NOT the expected stock/healthy state; no install should start"
			FINALIZED=1
			exit 1
		fi
		ACTIVE_KERNEL_SHA0=$(pget FI_ACTIVE_KERNEL_SHA)
		ACTIVE_ROOTFS0_SHA0=$(pget FI_ACTIVE_ROOTFS0_SHA)
		print_plan
		say ""
		say "RESULT: INSPECTION PASS - the box and the image are ready for an attended --write/--handover run."
		say "        No flash write was performed. NAND writes are wear-limited; do not repeat them casually."
		FINALIZED=1
		exit 0
	fi

	stock_readiness
	if [ "$BLOCKERS" -gt 0 ] || [ "$STOCK_READY" -ne 1 ]; then
		say ""
		abort "refusing the $mode: $BLOCKERS readiness blocker(s) and stock_ready=$STOCK_READY (no flash write was performed)"
	fi
	local t
	for t in mtd ubiformat sha256sum dd hexdump head sync fw_printenv dmesg; do
		[ "$(pget "FI_TOOL_$t")" = 1 ] || abort "required device tool missing: $t"
	done
	[ "$(pget FI_RECOVERY_IFACE)" = 1 ] || abort "the sysenv boot_reg interface is missing/not writable; the measured handover is unavailable"
	[ "$(pget FI_TMP_FREE_KB)" -ge 8192 ] 2>/dev/null || abort "device /tmp has $(pget FI_TMP_FREE_KB) KiB free; need at least 8192 KiB to stage the members"
	[ "$(pget FI_TARGET_KERNEL_SHA)" = none ] && abort "cannot fingerprint the inactive kernel slot"
	[ "$(pget FI_TARGET_ROOTFS0_SHA)" = none ] && abort "cannot fingerprint the inactive rootfs slot"
	if [ "$mode" = handover ]; then
		[ "$(pget FI_BOOT_REG_RECORDED_OK)" = 1 ] || abort "boot_reg 0x$(pget FI_BOOT_REG) is not the running-pair record 0x$(pget FI_RUNNING_VALUE); the handover would be unsafe (boot_done window or manual value) - use --write only and re-inspect after a fresh boot"
	fi
	ACTIVE_KERNEL_SHA0=$(pget FI_ACTIVE_KERNEL_SHA)
	ACTIVE_ROOTFS0_SHA0=$(pget FI_ACTIVE_ROOTFS0_SHA)
	say ""
	say "  readiness:   PASS for mode $mode (active pair $ACTIVE_PAIR, target pair $TARGET_PAIR)"
}

print_plan() {
	local sel_value
	[ "$TARGET_PAIR" = b ] && sel_value=11 || sel_value=10
	say ""
	say "== plan (NOT executed in this mode) =="
	say "  1. host: validate the sysupgrade container (luofu-image.py check + independent byte checks)"
	say "  2. device: write the kernel slice to kernel$TARGET_PAIR (mtd erase + mtd write), verify the full-slot sha256"
	say "  3. device: ubiformat rootfs$TARGET_PAIR with the UBI image, verify the full-partition sha256"
	say "  4. device: re-probe; both read-backs and the active-pair fingerprints must be unchanged"
	say "  5. device: last step - write 0x$sel_value (the recorded value of the written pair $TARGET_PAIR)"
	say "     into /sys/devices/platform/sysenv/boot_reg and verify the whole-cell read-back. The env blocks"
	say "     (mtd3/mtd4) are NOT written; the loader's mismatch path re-stamps bootflag on the next boot."
	say "  6. sync, reboot: the loader sees env=$ACTIVE_PAIR + cell=0x$sel_value, prints"
	say "     'boot from kernel$ACTIVE_PAIR failed, change to kernel$TARGET_PAIR', saves the env and boots"
	say "     kernel$TARGET_PAIR/rootfs$TARGET_PAIR. If our image never reaches userspace, the cell keeps the"
	say "     opposite marker and the next boot fails back to the active pair."
	say "  recovery: physical RESET+TFTP only (human); tools/recovery-card.sh --arm before any write."
}

# ---- stage / write / handover / reboot ------------------------------------
stage_member() { # <local> <remote-name> <size> <sha> <what>
	local local_path=$1 remote=$2 size=$3 expected_sha=$4 what=$5
	say ""
	say "== stage $what =="
	[ -f "$local_path" ] || abort "missing local $what: $local_path"
	local got_size got_sha
	got_size=$(file_size "$local_path")
	[ "$got_size" = "$size" ] || abort "local $what size $got_size B != expected $size B"
	got_sha=$(file_sha "$local_path")
	[ "$got_sha" = "$expected_sha" ] || abort "local $what sha256 $got_sha != expected $expected_sha"
	say "  scp:         $local_path -> $REMOTE_HOST:$remote ($size B)"
	"$RSCP" "$local_path" "$REMOTE_HOST:$remote" >"$WORK/scp.log" 2>&1 || {
		cat "$WORK/scp.log" >&2 || true
		abort "scp of the $what to the box failed (is the stock root shell reachable over the project key?)"
	}
	device_run verify "$remote" "$size" "$expected_sha" >"$WORK/verify.log" 2>&1 || {
		cat "$WORK/verify.log" >&2 || true
		abort "device-side sha256 verification of the staged $what failed"
	}
	say "  staged:      device sha256 $expected_sha verified"
}

do_write() {
	local out
	say ""
	say "== write the inactive pair ($TARGET_PAIR): kernel + rootfs, read-backs =="
	say "  writes kernel$TARGET_PAIR and rootfs$TARGET_PAIR ONLY; the active pair ($ACTIVE_PAIR) is fingerprinted and must not change"
	out=$(device_run write "$BOOT_ID" "$ACTIVE_PAIR" "$TARGET_PAIR" \
		"$REMOTE_KERNEL" "$KERNEL_SIZE" "$KERNEL_SHA" "$KERNEL_SLOT_SHA" \
		"$REMOTE_ROOT" "$ROOT_SIZE" "$ROOT_SHA" "$ROOT_PART_SHA" 2>&1) || {
		printf '%s\n' "$out" >&2 || true
		STATE=kernel_written
		case "$out" in *FI_KERNEL_WRITE_OK*) STATE=rootfs_written ;; esac
		abort "device-side write failed (selector still on the active pair, active pair untouched)"
	}
	printf '%s\n' "$out" | grep '^FI_' | sed 's/^/  /'
	printf '%s\n' "$out" | grep -qx 'FI_WRITE_OK' || abort "device write did not report FI_WRITE_OK; treating as failure"
	STATE=verified

	local out2
	out2=$(device_run probe) || abort "post-write probe failed"
	parse_probe "$out2"
	require_probe_keys
	[ "$(pget FI_BOOT_ID)" = "$BOOT_ID" ] || abort "the box rebooted during the write (boot_id changed); selector NOT moved - re-inspect before retrying"
	[ "$(pget FI_ACTIVE_KERNEL_SHA)" = "$ACTIVE_KERNEL_SHA0" ] || abort "the ACTIVE kernel slot changed during the write - this must never happen"
	[ "$(pget FI_ACTIVE_ROOTFS0_SHA)" = "$ACTIVE_ROOTFS0_SHA0" ] || abort "the ACTIVE rootfs slot changed during the write - this must never happen"
	[ "$(pget FI_TARGET_KERNEL_SHA)" = "$KERNEL_SLOT_SHA" ] || abort "post-write probe of kernel$TARGET_PAIR does not match the written bytes"
	[ "$(pget FI_TARGET_ROOTFS0_SHA)" = "$ROOT_PEB0_SHA" ] || abort "post-write probe of rootfs$TARGET_PAIR PEB0 does not match the written UBI header"
	say "  active pair: unchanged (kernel $ACTIVE_KERNEL_SHA0, rootfs PEB0 $ACTIVE_ROOTFS0_SHA0)"
	say "  target pair: kernel$TARGET_PAIR == the written slice; rootfs$TARGET_PAIR PEB0 == the written UBI header"
}

do_handover() {
	local out
	say ""
	say "== handover: move the selector to pair $TARGET_PAIR (the env is never written) =="
	out=$(device_run handover "$BOOT_ID" "$ACTIVE_PAIR" "$TARGET_PAIR" "$KERNEL_SLOT_SHA" "$ROOT_PART_SHA" 2>&1) || {
		printf '%s\n' "$out" >&2 || true
		# once the device prints BEGIN it may already have written the cell; treat the
		# selector state as uncertain (conservative recovery plan) unless it clearly refused
		case "$out" in *FI_HANDOVER_BEGIN*) SELECTOR_MOVED=1 ;; esac
		abort "device-side handover failed; check the selector state before rebooting"
	}
	printf '%s\n' "$out" | grep '^FI_' | sed 's/^/  /'
	case "$out" in *FI_HANDOVER_BEGIN*) SELECTOR_MOVED=1 ;; esac
	printf '%s\n' "$out" | grep -q '^FI_HANDOVER_OK' || abort "handover did not report FI_HANDOVER_OK; check the selector state before rebooting"
	SELECTOR_MOVED=1
	say "  selector:    moved to the written pair $TARGET_PAIR (recorded value 0x$(pair_value "$TARGET_PAIR"))"
	say "  next boot:   env bootflag=$ACTIVE_PAIR + cell 0x$(pair_value "$TARGET_PAIR") -> loader failover path:"
	say "               'boot from kernel$ACTIVE_PAIR failed, change to kernel$TARGET_PAIR' -> env re-stamped -> boots $TARGET_PAIR"
}

do_reboot() {
	local out
	say ""
	say "== reboot into the written pair (attended; read-only UART capture must be running) =="
	say "  expected UART (loader): bootflag $ACTIVE_PAIR bootreg 0x$(pair_value "$TARGET_PAIR")"
	say "    -> boot from kernel$ACTIVE_PAIR failed, change to kernel$TARGET_PAIR"
	say "    -> Saving Environment to NAND... / Erasing ... NAND... (the loader re-stamps bootflag)"
	say "    -> bootreg offset: c08 / boot regval: 0x$(pair_value "$ACTIVE_PAIR")"
	say "    -> Image Name: Linux-<our version>   (OUR image; only the stock 4,294,096-byte image prints 'Uncompressing Linux')"
	say "    -> our kernel console, then userspace. Verify from the capture, not from this tool."
	out=$(device_run reboot 2>&1) || true
	printf '%s\n' "$out" | grep '^FI_' | sed 's/^/  /' || true
	say "  reboot issued; polling for a return (up to $((POLL_ATTEMPTS * POLL_INTERVAL))s)"
	[ "$REBOOT_DELAY" -gt 0 ] && sleep "$REBOOT_DELAY"
	poll_after_reboot
}

poll_after_reboot() {
	local i out rc
	for i in $(seq 1 "$POLL_ATTEMPTS"); do
		out=$(device_run probe 2>/dev/null)
		rc=$?
		if [ "$rc" -eq 0 ]; then
			parse_probe "$out"
			if [ -n "$(pget FI_PROBE_OK)" ]; then
				classify_return
				return 0
			fi
		fi
		[ "$POLL_INTERVAL" -gt 0 ] && sleep "$POLL_INTERVAL"
	done
	say ""
	say "RESULT: UNVERIFIED - the box did not return over SSH within the poll window."
	say "  That is expected when OUR image booted (the target image is not expected to accept this"
	say "  key) or when it crashed before userspace. Read the UART capture: our kernel console and"
	say "  our boot markers mean the image ran; nothing / a silent reset / the stock fallback means"
	say "  it did not. Do NOT repeat the write or handover. Recovery is physical if needed."
	print_recovery_plan "post-reboot: no SSH return (outcome must be read from the UART console)"
	FINALIZED=1
	exit 3
}

classify_return() {
	local krel booted
	krel=$(pget FI_KERNEL_RELEASE)
	booted=$(pget FI_BOOTED_PAIR)
	say ""
	if [ "$(pget FI_BOOT_ID)" = "$BOOT_ID" ]; then
		say "RESULT: NO REBOOT DETECTED - the box answered with the same boot_id; it is still running stock."
		say "  The reboot command did not take (or was blocked). The selector state is unchanged from"
		say "  the handover; a true power cycle returns to the active pair. Investigate before retrying."
		print_recovery_plan "post-reboot: no reboot detected"
		FINALIZED=1
		exit 1
	fi
	if [ "$booted" = "$TARGET_PAIR" ]; then
		say "RESULT: TARGET PAIR RESPONDED OVER SSH - pair $TARGET_PAIR is booted (kernel $krel)."
		say "  That is only possible if our image accepted the project key (not expected for a"
		say "  stock-built target image). Verify from the UART capture and the booted rootfs before"
		say "  treating the install as proven."
		FINALIZED=1
		exit 0
	fi
	say "RESULT: STOCK FALLBACK OBSERVED - the box returned on the ACTIVE pair $ACTIVE_PAIR (kernel $krel)."
	say "  The loader took the failover path back to the untouched stock pair, which is the safe"
	say "  failure mode: the written pair $TARGET_PAIR never reached a successful userspace, or it"
	say "  booted but did not record the running pair. The active pair is intact; collect the UART"
	say "  capture as evidence before any retry. Do not repeat blindly."
	print_recovery_plan "post-reboot: stock fallback observed (safe; the written pair did not become stable)"
	FINALIZED=1
	exit 3
}

# ---- main ------------------------------------------------------------------
parse_args "$@"
WORK=$(mktemp -d "${TMPDIR:-/tmp}/first-install.XXXXXX") || { err "cannot create a work dir"; FINALIZED=1; exit 1; }

say "=================================================================="
say " first-install-stock: stock firmware -> our generated image"
say " mode=$MODE dry_run=$DRY_RUN attended=$ATTENDED recovery_armed=$RECOVERY_ARMED"
say "=================================================================="

host_preflight
if [ -n "$IMAGE" ]; then
	validate_image
else
	warn "no --image given: the container is not validated; the run can only inspect"
fi

write_device_script
say ""
say "== connect to the stock box (rsh) =="
say "  transport:   $RSH"
say "  remote:      $REMOTE_HOST"
probe_raw=$(device_run probe) || {
	printf '%s\n' "$probe_raw" >&2 || true
	abort "device probe failed (is the stock root shell reachable over the project key?)"
}
parse_probe "$probe_raw"
require_probe_keys
check_probe "$MODE"

if [ "$MODE" = inspect ]; then
	abort "internal: inspect mode returned from check_probe without exiting"
fi
if [ "$DRY_RUN" -eq 1 ]; then
	say ""
	say "RESULT: DRY RUN - all read-only checks ran; no flash write, selector move or reboot was performed."
	print_plan
	FINALIZED=1
	exit 0
fi

REMOTE_KERNEL="/tmp/first-install-$TAG-kernel.bin"
REMOTE_ROOT="/tmp/first-install-$TAG-rootfs.ubi"

stage_member "$KERNEL_FILE" "$REMOTE_KERNEL" "$KERNEL_SIZE" "$KERNEL_SHA" "kernel slice"
stage_member "$ROOT_FILE" "$REMOTE_ROOT" "$ROOT_SIZE" "$ROOT_SHA" "rootfs UBI"

do_write

if [ "$MODE" = write ]; then
	say ""
	say "RESULT: WRITE COMPLETE - pair $TARGET_PAIR staged and verified; the ACTIVE pair $ACTIVE_PAIR is unchanged."
	say "  The selector is STILL on the active pair: the box keeps booting stock until a handover."
	say "  Next attended step (recovery armed):"
	say "    tools/first-install-stock.sh --handover --attended --recovery-armed --image $IMAGE --tag $TAG"
	FINALIZED=1
	exit 0
fi

probe_raw=$(device_run probe) || abort "pre-handover probe failed; the selector was not moved"
parse_probe "$probe_raw"
require_probe_keys
[ "$(pget FI_BOOT_ID)" = "$BOOT_ID" ] || abort "the box rebooted during the write (boot_id changed); the selector was not moved - re-inspect before retrying"
[ "$(pget FI_ACTIVE_PAIR)" = "$ACTIVE_PAIR" ] || abort "the booted pair changed during the write; the selector was not moved"
[ "$(pget FI_ACTIVE_KERNEL_SHA)" = "$ACTIVE_KERNEL_SHA0" ] || abort "the ACTIVE kernel slot changed before the handover; the selector was not moved"
[ "$(pget FI_ACTIVE_ROOTFS0_SHA)" = "$ACTIVE_ROOTFS0_SHA0" ] || abort "the ACTIVE rootfs slot changed before the handover; the selector was not moved"

do_handover

if [ "$MODE" = handover ]; then
	say ""
	say "RESULT: HANDOVER COMPLETE - the selector names the written pair $TARGET_PAIR; nothing has rebooted yet."
	say "  The box is still running stock. To return to the active pair without booting the new one:"
	say "  do a TRUE POWER CYCLE (the SYSCTRL cell is cleared at POR, so the active pair boots), or write"
	say "  the active pair record 0x$(pair_value "$ACTIVE_PAIR") back to /sys/devices/platform/sysenv/boot_reg."
	say "  A warm reboot takes the loader failover path to the written pair."
	say "  To boot the written pair now (attended, capture armed):"
	say "    tools/first-install-stock.sh --reboot --attended --recovery-armed --image $IMAGE --tag $TAG"
	FINALIZED=1
	exit 0
fi

do_reboot
abort "internal: reboot mode returned without a classification"
