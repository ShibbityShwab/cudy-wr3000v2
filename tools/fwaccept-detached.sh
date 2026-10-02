#!/bin/sh
# fwaccept-detached.sh - fine-poll A/B against the module that observed the id-6 word.
#
# Runs the recorded fwaccept artifact (md5 55165b75c6ac0e4b3e23b02a25574b46, phase 20 CI 36907688150)
# with pollms lowered from 100 to 25. wifidrv1 emits only id 2 at 25 ms resolution; fwaccept posts SR
# descriptors and wifidrv1 deliberately does not. id 6 appearing here and not there makes the SR post
# the trigger; id 6 absent here too means the trigger is something else in fwaccept's configuration.
#
# Usage: sh tools/fwaccept-detached.sh   (background it; never foreground)
W=/c/Users/ShibbityShwab/Documents/GitHub/cudy-wr3000v2
OUT="$W/build/register-dumps/detached"
LOG="$OUT/fwaccept.log"
MODULE="$W/opensource/build/tmp/fwaccept-ko2/fwaccept.ko"
mkdir -p "$OUT"
: > "$LOG"

export EXP_DONE_CMD="dmesg | grep -q 'omo-fwaccept: done'"
export EXP_RUN_TIMEOUT=180
export EXP_RESULT_LABEL=FWACCEPT

{
	echo "=== fwaccept detached takeover run start $(date -Iseconds) ==="
	echo "module=$MODULE"
	echo "params: program=1 outwin=1 rings=1 release=1 acpoff=0 pollms=25 polldur=4000"
	echo "EXP_DONE_CMD=$EXP_DONE_CMD"
	echo
	bash "$W/tools/exp.sh" "$MODULE" \
		domain=0 program=1 outwin=1 devvabase=0x80000000 devvaend=0xffffffff \
		hostcabase=0x80000000 release=1 rings=1 acpoff=0 \
		pollms=25 polldur=4000 scanbase=0x7d8000 scanlen=0
	echo "=== exp.sh exit=$? $(date -Iseconds) ==="
	echo "=== fwaccept detached takeover run end $(date -Iseconds) ==="
} >> "$LOG" 2>&1
