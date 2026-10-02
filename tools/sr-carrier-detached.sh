#!/bin/sh
# sr-carrier-detached.sh - detached driver for the phase-22 SR-carrier (H1) experiment.
#
# One long-lived, agent-independent process:
#   1. run-exp-detached.sh  -> arm /root/rd-watch.sh on the DEVICE first, deploy
#      /tmp/restore-now.sh, hide the vendor modules (the staging phase)
#   2. batch.sh              -> arm recover-exp.sh, stage the H1 module + the
#      hypothesis list, reboot into the takeover boot, wait for batch.done,
#      capture the evidence, cancel the watchdog, restore, verify health
#
# Run it with `nohup ... &` / a background tool session so no agent death can
# strand the router: the device-side watchdog is armed before anything is
# staged, and the harness restores on its own if this process dies.
#
# Usage: sh tools/sr-carrier-detached.sh
W=/c/Users/ShibbityShwab/router-openwrt
OUT="$W/build/register-dumps/detached"
LOG="$OUT/sr-carrier.log"
mkdir -p "$OUT"
: > "$LOG"

MODULE="$W/opensource/build/tmp/phase22/hccaccept-h1/hccaccept.ko"
LIST="$W/opensource/lab/hccaccept/batch-h1.list"
PARAMS="domain=0 domain2=1 program=1 outwin=1 devvabase=0x80000000 devvaend=0xffffffff hostcabase=0x80000000 release=1 useirq=1 irq=207 hostirq=207 useirq2=1 irq2=209 hostirq2=209 rings=1 acpoff=0 enable=0 intr=0 srctrl=0 seq=0 svc=0 scanlen=0 hccwin=1500 stopfirst=0"

{
	echo "=== sr-carrier detached runner start $(date -Iseconds) ==="
	echo "module=$MODULE"
	echo "list=$LIST"
	echo "params=$PARAMS"
	echo
	echo "=== phase 1: run-exp-detached.sh (arm device watchdog first, then hide vendor modules) ==="
	sh "$W/tools/run-exp-detached.sh" stage
	echo "=== phase 1 exit=$? $(date -Iseconds) ==="
	echo
	echo "=== phase 2: batch.sh full cycle (arm, stage module+list, boot, capture, recover, health) ==="
	bash "$W/tools/batch.sh" --module "$MODULE" --params "$PARAMS" "$LIST"
	echo "=== phase 2 exit=$? $(date -Iseconds) ==="
	echo "=== sr-carrier detached runner end $(date -Iseconds) ==="
} >> "$LOG" 2>&1
