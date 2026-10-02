#!/bin/sh
# wifidrv1-detached.sh - detached takeover run of wifidrv1 hw=1 (phase 23).
#
# Purpose: run the port's own driver with the endpoint claimed. While the vendor
# stack is loaded, pci_request_mem_regions returns EBUSY (measured, phase 23), so
# the claim can only succeed in a takeover boot where the vendor modules are hidden
# - which is exactly what tools/exp.sh does, with its self-recovery watchdog armed
# BEFORE anything is staged.
#
# Usage: sh tools/wifidrv1-detached.sh   (background it; never foreground)
W=/c/Users/ShibbityShwab/Documents/GitHub/cudy-wr3000v2
OUT="$W/build/register-dumps/detached"
LOG="$OUT/wifidrv1.log"
MODULE="$W/opensource/build/tmp/wifidrv1t/wifidrv1.ko"
mkdir -p "$OUT"
: > "$LOG"

# wifidrv1 prints "omo-drv1: init done ... regs=decoded|absent" and does not use
# the ': done (' marker of the experiment modules, so the harness must wait on
# its own marker.  regs=decoded is the success we are looking for: it means the
# EP0 claim succeeded and the read-only register decode ran.
export EXP_DONE_CMD="dmesg | grep -q 'omo-drv1: init done'"
export EXP_RUN_TIMEOUT=120
export EXP_RESULT_LABEL=WIFIDRV1

{
	echo "=== wifidrv1 detached takeover run start $(date -Iseconds) ==="
	echo "module=$MODULE"
	echo "params: hw=1 program=1 wr=1 (claim EP0, viewports, decode, SR POST + fine poll - does the id-6 word appear?), verbose=1"
	echo "EXP_DONE_CMD=$EXP_DONE_CMD"
	echo
	bash "$W/tools/exp.sh" "$MODULE" hw=1 program=1 wr=1 fw=1 release=1 srpost=1 pollms=25 polldur=4000 verbose=1
	echo "=== exp.sh exit=$? $(date -Iseconds) ==="
	echo "=== wifidrv1 detached takeover run end $(date -Iseconds) ==="
} >> "$LOG" 2>&1
