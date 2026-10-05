#!/usr/bin/env bash
# finish-evidence.sh <evidence-dir> [--variant NAME] [--ko PATH] [--interp-source CMD]
#
# The worker-files finisher.  tools/pack-evidence.sh --require KNOBSET.txt interp.txt
# acceptance.txt cleanup.txt only WARNS when a worker file is missing (it is read-only and
# never creates anything); six device cycles shipped their harness files without those four
# and each needed a bespoke corrective script.  This tool is the reusable, host-side finisher:
# it reconstitutes the three files that CAN be derived from the dir + the frozen repo inputs,
# and leaves the fourth (acceptance.txt) to the dir's own accept script, which it runs when
# present.
#
# It generates INTO <evidence-dir>, NEVER overwriting an existing file:
#   KNOBSET.txt   the template header + the frozen knob-set sha256 + this run's module .ko md5
#                 + the LOADED/STOCK firmware blob md5s + the insmod params string, all lifted
#                 from the dir's capture-cmd.txt / run-*.log, followed by the frozen knob-set
#                 body verbatim (tools/params/definitive-run.params).
#   cleanup.txt   the standard read-only post-cycle probe set + the receipts this dir already
#                 carries (health.txt / health-raw.txt / the EXP RESULT line / the capture
#                 recovery note).  With --live it also runs the probe set read-only over ssh.
#   interp.txt    a SKELETON: numbered branch-table stubs (one TODO row per mechanism) + a
#                 facts block TODO.  A human/worker fills the verdicts; this tool never guesses.
#
# Then it runs the dir's accept script (accept*.py / accept*.sh in the dir) if one exists.
#
# Required inputs (a run exits non-zero, code 3, when one of these is missing):
#   * KNOBSET.txt to be generated   -> tools/params/definitive-run.params AND a resolvable .ko
#   * interp.txt to be generated    -> a capture context (capture-cmd.txt or run-*.log) in the dir
# The dir itself must exist and be a directory (usage error, code 2).
#
# Host-only by default: the only device I/O is the optional --live probe set (read-only
# ls/md5sum/cat/iw/iwpriv/lsmod through .sshwrap/rsh.sh).  Never writes CA 0x400392f0, never
# reads 0x4016010c or 0x10161000, never stages anything -- see the hard rules in AGENTS.md.
#
# 2026-10-05 - built for task st_01a10c6f (cures the recurring worker-files gap).
set -uo pipefail

FE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FE_ROOT="$(cd "$FE_DIR/.." && pwd)"
PARAMS_FILE="$FE_ROOT/tools/params/definitive-run.params"
PINNED_KO="$FE_ROOT/build/tmp/wifidrv1-art/wifidrv1.ko"
KVER=5.10.201

fe_usage() {
	cat <<'EOF'
usage: finish-evidence.sh <evidence-dir> [--variant NAME] [--ko PATH] [--interp-source CMD]

  <evidence-dir>        one build/register-dumps/exp/<TS>/ directory (required)
  --variant NAME        name the firmware/port variant for the KNOBSET header and the interp
                        facts block (default: auto-detected from capture-cmd.txt, else the dir)
  --ko PATH             the module .ko whose md5 goes into KNOBSET.txt (default: a *.ko inside
                        the dir, else build/tmp/wifidrv1-art/wifidrv1.ko)
  --interp-source CMD   the source(s) the interp skeleton's branch table must be filled from
                        (default: "capture-cmd.txt + dmesg.txt in this dir")
  --live                also run the standard read-only post-cycle probe set over ssh and append
                        its raw output to cleanup.txt (default: receipts only, no device I/O)
  -h|--help             this text

generates KNOBSET.txt / cleanup.txt / interp.txt into the dir, NEVER overwriting an existing
file; runs the dir's accept*.py|accept*.sh when present; prints a summary.  Exits 0 when every
target file is present (pre-existing or generated), 2 on usage error, 3 when a required input
for a file that must still be generated is missing.
EOF
}

# ---- the standard read-only post-cycle probe set (never a write; .omo-pat must be gone) ----
read -r -d '' STD_PROBE <<'PROBE' || true
ls -l /lib/firmware/hi_wifi/FIRMWARE.bin.omo-pat 2>&1                     # expect: No such file
ls -1 /lib/firmware/hi_wifi/                                              # expect 3 entries, no .omo-pat
md5sum /lib/firmware/hi_wifi/FIRMWARE.bin                                 # expect stock 0e530b976d5a20e87358671f1a577695
ls /lib/firmware/hi_wifi/*.omo-pat 2>/dev/null | wc -l                    # expect 0
ls /lib/modules/<K>/*.omo-off 2>/dev/null | wc -l                         # expect 0 (vendor modules restored)
ls /etc/init.d/omo-* /etc/rc.d/S99omo-* /lib/modules/<K>/wifidrv1.ko /root/recover-exp.sh 2>/dev/null | wc -l   # expect 0
lsmod | grep -E 'wifidrv1|hi5622v100'                                     # expect hi5622v100_plat + hi5622v100_wifi, NO wifidrv1
iw phy 2>/dev/null | grep -c '^Wiphy'                                     # expect 2
iw dev 2>/dev/null | grep -c 'Interface'                                  # expect 6
iwpriv vap0 alg get_2g_power_param 2>/dev/null | grep -c '\[SUCC\]'       # expect 1
iwpriv vap1 alg get_5g_power_param 2>/dev/null | grep -c '\[SUCC\]'       # expect 1
cut -d. -f1 /proc/uptime                                                  # recovered-boot uptime
PROBE

DIR=""; VARIANT=""; KO=""; INTERP_SRC=""; LIVE=0
while [ $# -gt 0 ]; do
	case "$1" in
		--variant)       shift; VARIANT="${1:-}" ;;
		--ko)            shift; KO="${1:-}" ;;
		--interp-source) shift; INTERP_SRC="${1:-}" ;;
		--live)          LIVE=1 ;;
		-h|--help)       fe_usage; exit 0 ;;
		-*) echo "finish-evidence.sh: unknown option: $1" >&2; fe_usage >&2; exit 2 ;;
		*)  if [ -z "$DIR" ]; then DIR="$1"; else
				echo "finish-evidence.sh: unexpected argument: $1" >&2; fe_usage >&2; exit 2
			fi ;;
	esac
	shift
done
[ -n "$DIR" ] || { fe_usage >&2; exit 2; }
[ -d "$DIR" ] || { echo "finish-evidence.sh: no such evidence dir: $DIR" >&2; exit 2; }
DIR="$(cd "$DIR" && pwd)"
TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
DIRNAME="$(basename "$DIR")"

# ---- resolve inputs -----------------------------------------------------------------------
MISSING=()

# capture context = any capture-cmd.txt or run-*.log in the dir
CAP="$DIR/capture-cmd.txt"
[ -f "$CAP" ] || CAP=""
RUNLOG=""
for f in "$DIR"/run-*.log; do [ -f "$f" ] && { RUNLOG="$f"; break; }; done
[ -n "$CAP$RUNLOG" ] || MISSING+=("capture context: no capture-cmd.txt or run-*.log in $DIR")

# the frozen params file (always needed for the digest + body)
[ -f "$PARAMS_FILE" ] || MISSING+=("frozen knob set: $PARAMS_FILE")

# module .ko: --ko, else a *.ko in the dir, else the pinned artifact
if [ -n "$KO" ]; then
	:
elif [ -z "$KO" ]; then
	for f in "$DIR"/*.ko; do [ -f "$f" ] && { KO="$f"; break; }; done
fi
if [ -z "$KO" ] && [ -f "$PINNED_KO" ]; then KO="$PINNED_KO"; fi
if [ -z "$KO" ] || [ ! -f "$KO" ]; then
	MISSING+=("module .ko: pass --ko PATH (none in the dir, no pinned $PINNED_KO)")
fi

# variant: --variant, else auto-detect, else the dir name
if [ -z "$VARIANT" ]; then
	if [ -n "$CAP" ]; then
		VARIANT="$(sed -n 's/^=== omo capture hook (\([^,)]*\)[,)].*/\1/p' "$CAP" | head -1)"
	fi
	[ -n "$VARIANT" ] || VARIANT="(unspecified)"
fi

# ---- derived facts ------------------------------------------------------------------------
DIGEST=""
[ -f "$PARAMS_FILE" ] && DIGEST="$(awk '1;/^# --- end of params body ---$/{exit}' "$PARAMS_FILE" | sha256sum | awk '{print $1}')"

KO_MD5=""; KO_REL=""
if [ -n "$KO" ] && [ -f "$KO" ]; then
	KO_MD5="$(md5sum "$KO" | awk '{print $1}')"
	KO_REL="${KO#"$FE_ROOT"/}"
fi

BLOB_LOADED=""; BLOB_STOCK=""
if [ -n "$CAP" ]; then
	BLOB_LOADED="$(sed -n 's|^\([0-9a-fA-F]\{32\}\)[[:space:]]\+/lib/firmware/hi_wifi/FIRMWARE\.bin\.omo-pat.*|\1|p' "$CAP" | head -1)"
	BLOB_STOCK="$(sed -n 's|^\([0-9a-fA-F]\{32\}\)[[:space:]]\+/lib/firmware/hi_wifi/FIRMWARE\.bin[[:space:]]*$|\1|p' "$CAP" | head -1)"
	[ -n "$BLOB_STOCK" ] || BLOB_STOCK="$(sed -n 's|^\([0-9a-fA-F]\{32\}\)[[:space:]]\+/lib/firmware/hi_wifi/FIRMWARE\.bin\(\.[^ ]*\)\?.*|\1|p' "$CAP" | head -1)"
fi

PARAMS_STR=""
if [ -n "$RUNLOG" ] || [ -n "$CAP" ]; then
	PARAMS_STR="$(grep -hoE 'params=\[[^]]*\]' "$RUNLOG" "$CAP" 2>/dev/null | head -1 | sed 's/^params=\[//; s/\]$//')"
fi

# safe placeholder words (never put a quote or ${:-} inside a heredoc default: bash treats a
# stray apostrophe there as an opening quote and the whole heredoc dies with 'bad substitution')
V_LOADED="$BLOB_LOADED"; [ -n "$V_LOADED" ] || V_LOADED="<TODO: no staged-blob md5 in capture-cmd.txt>"
V_STOCK="$BLOB_STOCK";   [ -n "$V_STOCK" ]  || V_STOCK="<TODO: no stock-blob md5 in capture-cmd.txt>"
V_PARAMS="$PARAMS_STR";  [ -n "$V_PARAMS" ] || V_PARAMS="<TODO: no params line in this capture log>"
V_DIGEST="$DIGEST";      [ -n "$V_DIGEST" ] || V_DIGEST="<TODO: unfrozen/unreadable knob set>"
V_KO_MD5="$KO_MD5";      [ -n "$V_KO_MD5" ] || V_KO_MD5="<TODO: no module .ko md5>"

# ---- summary accumulators -----------------------------------------------------------------
declare -A RESULT=()
RESULT[KNOBSET.txt]=""
RESULT[cleanup.txt]=""
RESULT[interp.txt]=""
ACCEPT_RC=""
ACCEPT_SCRIPT=""

fe_refuse() { printf '%s already exists - NOT overwritten\n' "$1"; }

# ============================ KNOBSET.txt ==================================================
if [ -e "$DIR/KNOBSET.txt" ]; then
	RESULT[KNOBSET.txt]="REFUSED (exists)"
	fe_refuse "KNOBSET.txt"
elif [ -f "$PARAMS_FILE" ] && [ -n "$KO" ] && [ -f "$KO" ]; then
	{
		cat <<EOF
# KNOBSET.txt -- mandatory header for every device evidence dir (plan task 5 / IS-4).
# GENERATED by tools/finish-evidence.sh $TS  (the worker-files finisher; pre-existing files are
# NEVER overwritten, so if you are reading this line the fields below are this tool's harvest
# from the dir, not a human's device read - fill any TODO before the dir is treated as IS-4.)
# variant            : $VARIANT
#
# knob-set sha256    : $DIGEST
#   recipe: awk '1;/^# --- end of params body ---\$/ {exit}' tools/params/definitive-run.params | sha256sum
#   NOTE the frozen knob set is not widened by this run; it MUST equal the footer digest of
#        tools/params/definitive-run.params or the run used an unfrozen set.
# firmware blob md5  : LOADED = $V_LOADED  (staged .omo-pat, read from capture-cmd.txt)
#                      STOCK  = $V_STOCK  (/lib/firmware/hi_wifi/FIRMWARE.bin)
# module .ko md5     : $KO_MD5
#   source  : $KO_REL
# module .ko params  : $V_PARAMS
EOF
		if [ -z "$PARAMS_STR" ]; then echo "#                      (no run-*.log carried the EXP RESULT params=[...] line; read it from the run console)"; fi
		cat <<EOF
# boot context - lsmod         : see lsmod.txt in this dir (the takeover/recovered state)
# boot context - init scripts  : see health.txt / cleanup.txt (STAGED/LOADER/OMO_OFF counters)
# boot context - uptime        : see uptime.txt in this dir
# boot context - station state : see health.txt (WIPHY/IFACE/CAL_SUCC x2)
# capture utc        : $DIRNAME (dir TS, UTC)
#
# TODO before IS-4: replace every <TODO...> above with the device read; delete this line.
# hard rules         : never write CA 0x400392f0; never read the IAR CA 0x4016010c or the RC
#                      misc CA 0x10161000; measure through the endpoints' BAR0/BAR2 only.
# --- frozen knob-set body (verbatim from tools/params/definitive-run.params; do not edit) ---
EOF
		cat "$PARAMS_FILE"
	} > "$DIR/KNOBSET.txt"
	RESULT[KNOBSET.txt]="GENERATED (digest=$DIGEST ko=$KO_MD5)"
else
	RESULT[KNOBSET.txt]="SKIPPED (required input missing)"
fi

# ============================ cleanup.txt ===================================================
if [ -e "$DIR/cleanup.txt" ]; then
	RESULT[cleanup.txt]="REFUSED (exists)"
	fe_refuse "cleanup.txt"
else
	{
		echo "# cleanup.txt - the post-cycle cleanup receipt + read-only probe set (variant: $VARIANT)"
		echo "# GENERATED by tools/finish-evidence.sh $TS (pre-existing files are never overwritten)."
		echo "#   1. VERIFY the staged /lib/firmware/hi_wifi/FIRMWARE.bin.omo-pat is gone (exp.sh step 6)."
		echo "#   2. VERIFY the capture scratch (/root/omo-*) is gone (the capture recovered)."
		echo "#   3. VERIFY the .omo-off hides, the loader/symlink, the staged module and recover-exp.sh are gone."
		echo "#   The stock FIRMWARE.bin is NEVER written by this lane."
		echo
		echo "--- the standard read-only post-cycle probe set (K=$KVER; run it with --live) ---"
		printf '%s\n' "$STD_PROBE" | sed "s/<K>/$KVER/g" | sed 's/^/  /'
		echo
		echo "--- receipts already carried by this dir ---"
		if [ -f "$DIR/health.txt" ]; then
			echo "  [health.txt]"; sed 's/^/    /' "$DIR/health.txt"
		else
			echo "  [health.txt] ABSENT (step 7 health not captured)"
		fi
		if [ -f "$DIR/health-raw.txt" ]; then
			echo "  [health-raw.txt]"; sed 's/^/    /' "$DIR/health-raw.txt"
		fi
		RES="$(grep -hoE 'EXP RESULT: (PASS|FAIL)[^\n]*' "$DIR"/capture-cmd.txt "$DIR"/run-*.log "$DIR"/PACKED.txt 2>/dev/null | head -1)"
		echo "  [EXP RESULT] ${RES:-ABSENT (no EXP RESULT line in capture/run/PACKED)}"
		if [ -n "$RUNLOG" ]; then
			REC="$(grep -hE 'capture hook: ok|capture recovery|scratch removed|hook_rm_rc' "$RUNLOG" 2>/dev/null | sed 's/^/    /')"
			[ -n "$REC" ] && { echo "  [capture recovery]"; printf '%s\n' "$REC"; }
		fi
		echo "  [blob md5s] LOADED=${BLOB_LOADED:-?} STOCK=${BLOB_STOCK:-?}"
		echo
		if [ "$LIVE" = 1 ]; then
			echo "--- live probe output (read-only, via .sshwrap/rsh.sh) ---"
			( cd "$FE_ROOT" && ./.sshwrap/rsh.sh "
K=$KVER
echo 'lsmod (expect hi5622v100_plat + hi5622v100_wifi, NO wifidrv1)'; lsmod | grep -E 'wifidrv1|hi5622v100' || true
echo 'stock md5 (expect 0e530b976d5a20e87358671f1a577695)'; md5sum /lib/firmware/hi_wifi/FIRMWARE.bin
echo '.omo-pat count (expect 0)'; ls /lib/firmware/hi_wifi/*.omo-pat 2>/dev/null | wc -l
echo '.omo-off count (expect 0)'; ls /lib/modules/\$K/*.omo-off 2>/dev/null | wc -l
echo 'loader/staged/recover leftovers (expect 0)'; ls /etc/init.d/omo-* /etc/rc.d/S99omo-* /lib/modules/\$K/wifidrv1.ko /root/recover-exp.sh 2>/dev/null | wc -l
echo 'WIPHY (expect 2)'; iw phy 2>/dev/null | grep -c '^Wiphy'
echo 'IFACE (expect 6)'; iw dev 2>/dev/null | grep -c 'Interface'
echo 'CAL_SUCC 2g (expect 1)'; iwpriv vap0 alg get_2g_power_param 2>/dev/null | grep -c '\[SUCC\]'
echo 'CAL_SUCC 5g (expect 1)'; iwpriv vap1 alg get_5g_power_param 2>/dev/null | grep -c '\[SUCC\]'
echo 'uptime(s)'; cut -d. -f1 /proc/uptime
" 2>&1 ) | sed 's/^/  /'
		else
			echo "--- live probe output ---"
			echo "  (not run: host-only mode.  Re-run with --live to append the read-only probe output.)"
		fi
	} > "$DIR/cleanup.txt"
	CL_LABEL="probe set + receipts"
	[ "$LIVE" = 1 ] && CL_LABEL="$CL_LABEL, live output"
	RESULT[cleanup.txt]="GENERATED ($CL_LABEL)"
fi

# ============================ interp.txt (skeleton) ========================================
if [ -e "$DIR/interp.txt" ]; then
	RESULT[interp.txt]="REFUSED (exists)"
	fe_refuse "interp.txt"
elif [ -n "$CAP$RUNLOG" ]; then
	[ -n "$INTERP_SRC" ] || INTERP_SRC="capture-cmd.txt + dmesg.txt in this dir"
	SRC_NOTE="$INTERP_SRC"
	if [ -f "$INTERP_SRC" ]; then
		SRC_NOTE="$INTERP_SRC ($(wc -l < "$INTERP_SRC" | tr -d ' ') lines, md5=$(md5sum "$INTERP_SRC" | awk '{print $1}'))"
	fi
	{
		cat <<EOF
# interp.txt - $VARIANT - SKELETON generated by tools/finish-evidence.sh $TS
#
# This is a TEMPLATE, not an interpretation: every row below is a TODO.  Fill one named row per
# mechanism with an honest verdict (PASS / FAIL / UNAVAILABLE / NO-ROW) and the load-bearing
# line(s) quoted verbatim.  A witness that legitimately reads UNAVAILABLE / NO-ROW is not a
# failure.  Sources to read: $SRC_NOTE
#
# The official outputs of ONE cycle are the dir's capture-cmd.txt (hook greps + devmem) and
# dmesg.txt (the full ring buffer).  Quote from THOSE, never from memory.

## BRANCH 1 - <mechanism name> - <source doc / section>
  TODO(verdict): <PASS|FAIL|UNAVAILABLE|NO-ROW> + the decisive line(s)
  inputs: TODO (the armed values / counter reads that make the row honest)

## BRANCH 2 - <mechanism name> - <source doc / section>
  TODO(verdict): <...>
  inputs: TODO

## BRANCH 3 - <mechanism name> - <source doc / section>
  TODO(verdict): <...>
  inputs: TODO

## BRANCH 4 - <mechanism name> - <source doc / section>
  TODO(verdict): <...>
  inputs: TODO

## THE LOAD-BEARING LINES (verbatim; from capture-cmd.txt + dmesg.txt)
  TODO: paste the decisive kernel/hook lines, one per quoted block.

## FACTS BLOCK (TODO)
  variant           : $VARIANT
  capture utc       : $DIRNAME (dir TS, UTC)
  module .ko md5    : $V_KO_MD5
  firmware blob     : LOADED=$V_LOADED  STOCK=$V_STOCK
  insmod params     : $V_PARAMS
  knob-set sha256   : $V_DIGEST
  hard rules honoured: never write CA 0x400392f0; never read 0x4016010c / 0x10161000.
EOF
	} > "$DIR/interp.txt"
	RESULT[interp.txt]="GENERATED (skeleton)"
else
	RESULT[interp.txt]="SKIPPED (required input missing)"
fi

# ============================ the dir's accept script ======================================
for s in "$DIR"/accept*.py "$DIR"/accept*.sh; do
	[ -f "$s" ] || continue
	ACCEPT_SCRIPT="$s"
	ACCEPT_LOG="$DIR/.finish-accept.log"
	case "$s" in
		*.py)
			if [ -x "$FE_ROOT/pyenv/Scripts/python.exe" ]; then PY="$FE_ROOT/pyenv/Scripts/python.exe"; else PY="python3"; fi
			( cd "$DIR" && "$PY" "$s" ) > "$ACCEPT_LOG" 2>&1 ;;
		*)  ( cd "$DIR" && bash "$s" ) > "$ACCEPT_LOG" 2>&1 ;;
	esac
	ACCEPT_RC=$?
	break
done

# ============================ summary ======================================================
printf 'finish-evidence: %s\n' "$DIR"
printf '  variant   : %s\n' "$VARIANT"
if [ -n "$KO" ] && [ -f "$KO" ]; then printf '  ko        : %s md5=%s\n' "$KO_REL" "$KO_MD5"; else printf '  ko        : (unresolved)\n'; fi
printf '  KNOBSET.txt : %s\n' "${RESULT[KNOBSET.txt]}"
printf '  cleanup.txt : %s\n' "${RESULT[cleanup.txt]}"
printf '  interp.txt  : %s\n' "${RESULT[interp.txt]}"
if [ -n "$ACCEPT_SCRIPT" ]; then
	printf '  accept      : %s rc=%s (log: %s)\n' "$(basename "$ACCEPT_SCRIPT")" "$ACCEPT_RC" "$(basename "${ACCEPT_LOG:-}")"
	tail -3 "${ACCEPT_LOG:-/dev/null}" 2>/dev/null | sed 's/^/                /'
else
	printf '  accept      : (none found: no accept*.py|accept*.sh in the dir)\n'
fi
if [ "${#MISSING[@]}" -gt 0 ]; then
	printf 'MISSING required input(s):\n'
	for m in "${MISSING[@]}"; do printf '  - %s\n' "$m"; done
	printf 'FAIL: finish-evidence could not derive every file (see above)\n'
	exit 3
fi
printf 'OK\n'
exit 0
