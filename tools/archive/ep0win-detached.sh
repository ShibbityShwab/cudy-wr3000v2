#!/bin/sh
# ep0win-detached.sh - detached driver for the phase-22 H1-H4 experiment (EP0 window + ETE arm).
#
# Corrects the defects in sr-carrier-detached.sh:
#   - it does NOT pass the literal string "stage" to run-exp-detached.sh (that
#     script's only mode is a full cycle: <module.ko> [params]); it runs the
#     staged-module cycle directly through exp.sh/batch.sh instead;
#   - it points at the CURRENT CI-built artifact, not the pre-h1 hccaccept-h1 copy.
#
# Safety order, unchanged and non-negotiable: the DEVICE-side watchdog is armed
# (with its all-clear flag absent) BEFORE the vendor modules are hidden, and the
# whole run is one detached, agent-independent process.
#
# Usage: sh tools/ep0win-detached.sh            (background it; never foreground)
W=/c/Users/ShibbityShwab/Documents/GitHub/cudy-wr3000v2
OUT="$W/build/register-dumps/detached"
LOG="$OUT/ep0win.log"
mkdir -p "$OUT"
: > "$LOG"

MODULE="$W/opensource/build/tmp/phase22/ci-art/hccaccept.ko"
LIST="$W/opensource/lab/hccaccept/batch-h1.list"
PARAMS="domain=0 domain2=1 program=1 outwin=1 devvabase=0x80000000 devvaend=0xffffffff hostcabase=0x80000000 release=1 useirq=1 irq=207 hostirq=207 useirq2=1 irq2=209 hostirq2=209 rings=1 acpoff=0 enable=0 intr=0 srctrl=0 seq=0 svc=0 scanlen=0 hccwin=1500 stopfirst=0"

{
	echo "=== ep0win detached runner start $(date -Iseconds) ==="
	echo "module=$MODULE"
	echo "list=$LIST"
	echo "params=$PARAMS"
	echo "H1: EP0 outbound viewport 0 programmed (outwin=1) + both RCs' six inbound viewports."
	echo "H2/H3/H4 ride in the batch list; stopfirst=0 so every entry records observables."
	echo
	echo "=== full cycle: arm watchdog -> stage module+list -> boot -> capture -> recover -> health ==="
	bash "$W/tools/batch.sh" --module "$MODULE" --params "$PARAMS" "$LIST"
	echo "=== batch exit=$? $(date -Iseconds) ==="
	echo "=== ep0win detached runner end $(date -Iseconds) ==="
} >> "$LOG" 2>&1
