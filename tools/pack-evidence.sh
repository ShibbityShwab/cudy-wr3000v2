#!/usr/bin/env bash
# pack-evidence.sh <evidence-dir> [--require NAME ...]
#
# Host-side inventory + completeness gate for one experiment's evidence dir. It
# lists the directory (sorted), records the timestamp and - when capture-cmd.txt
# shows a staged *.omo-pat context - the matching host blob md5s, then checks a
# required set and writes PACKED.txt into the directory. It exits non-zero when
# a required artifact is missing, printing the names as "MISSING: ...".
#
# The required set defaults to the files the harness itself writes
# (capture-cmd.txt health.txt dmesg.txt lsmod.txt interrupts.txt uptime.txt
# module-log.txt device-tar.txt evidence.tar.gz).  --require adds names such as
# the worker-delivered KNOBSET.txt interp.txt acceptance.txt cleanup.txt.
#
# Read-only on the device: it never calls ssh/scp and only touches PACKED.txt.
#
# 2026-10-05 - built for the tooling-quick-wins task (st_01a10b16, item #4).
set -uo pipefail

PK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PK_ROOT="$(cd "$PK_DIR/.." && pwd)"
DEFAULT_REQUIRED="capture-cmd.txt health.txt dmesg.txt lsmod.txt interrupts.txt uptime.txt module-log.txt device-tar.txt evidence.tar.gz"

pk_usage() {
	cat <<'EOF'
usage: pack-evidence.sh <evidence-dir> [--require NAME ...]

  <evidence-dir>   one build/register-dumps/exp/<TS>/ directory
  --require NAME   add NAME to the required set (repeatable; several names may
                   follow one --require: --require A B C).  Defaults to the
                   harness files: capture-cmd.txt health.txt dmesg.txt lsmod.txt
                   interrupts.txt uptime.txt module-log.txt device-tar.txt
                   evidence.tar.gz

Writes <evidence-dir>/PACKED.txt; exits non-zero when a required artifact is
missing (listed as "MISSING: ...").
EOF
}

DIR=""
EXTRA=()
while [ $# -gt 0 ]; do
	case "$1" in
		--require)
			shift
			while [ $# -gt 0 ] && [ "${1#--}" = "$1" ]; do
				EXTRA+=("$1"); shift
			done
			continue ;;
		-h|--help) pk_usage; exit 0 ;;
		-*) echo "pack-evidence.sh: unknown option: $1" >&2; pk_usage >&2; exit 2 ;;
		*)
			if [ -z "$DIR" ]; then DIR="$1"
			else echo "pack-evidence.sh: unexpected argument: $1" >&2; exit 2
			fi ;;
	esac
	shift
done
[ -n "$DIR" ] || { pk_usage >&2; exit 2; }
[ -d "$DIR" ] || { echo "pack-evidence.sh: no such evidence dir: $DIR" >&2; exit 2; }
TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
PACKED="$DIR/PACKED.txt"

# required set = defaults + --require additions (dedup, order preserved)
REQ=()
for n in $DEFAULT_REQUIRED; do REQ+=("$n"); done
for n in ${EXTRA[@]+"${EXTRA[@]}"}; do
	seen=0
	for r in "${REQ[@]}"; do [ "$r" = "$n" ] && seen=1; done
	[ "$seen" = 1 ] || REQ+=("$n")
done

# sorted top-level inventory (PACKED.txt itself excluded so re-runs are stable)
INV=()
while IFS= read -r n; do
	[ -n "$n" ] && [ "$n" != "PACKED.txt" ] && INV+=("$n")
done < <(ls -1A -- "$DIR" 2>/dev/null | LC_ALL=C sort)

# staged-.omo-pat context: device-reported md5s quoted in the capture hook
DEV_MD5S=""
if [ -f "$DIR/capture-cmd.txt" ]; then
	DEV_MD5S="$(sed -n 's|^\([0-9a-fA-F]\{32\}\)[[:space:]]\+/lib/firmware/hi_wifi/\([^[:space:]]*\.omo-pat\).*|\1 \2|p' "$DIR/capture-cmd.txt" | LC_ALL=C sort -u)"
fi

P=0
M=0
MISS=()
{
	echo "# PACKED.txt - evidence inventory (tools/pack-evidence.sh)"
	echo "# timestamp : $TS"
	echo "# evidence  : $DIR"
	echo "#"
	echo "# inventory (sorted, top-level):"
	if [ "${#INV[@]}" -gt 0 ]; then
		for n in "${INV[@]}"; do echo "$n"; done
	else
		echo "#   (empty)"
	fi
	echo "#"
	echo "# host blob md5s:"
	if [ -z "$DEV_MD5S" ]; then
		echo "#   (no staged .omo-pat context detected in capture-cmd.txt)"
	else
		printf '%s\n' "$DEV_MD5S" | while IFS=' ' read -r dmd5 dname; do
			[ -n "$dmd5" ] || continue
			echo "#   device /lib/firmware/hi_wifi/$dname md5=$dmd5"
			hfound=0
			for cd in "$PK_ROOT/build/tmp/fw-patched" "$PK_ROOT/build/tmp"; do
				[ -d "$cd" ] || continue
				for hf in "$cd"/*.bin; do
					[ -f "$hf" ] || continue
					hmd5="$(md5sum "$hf" 2>/dev/null | awk '{print $1}')"
					if [ "$hmd5" = "$dmd5" ]; then
						echo "#   host   ${hf#"$PK_ROOT"/} md5=$hmd5 MATCH"
						hfound=1
					fi
				done
			done
			[ "$hfound" = 1 ] || echo "#   host   (no host blob with this md5 under build/tmp; cleaned or absent)"
		done
	fi
	echo "#"
	echo "# completeness (required vs present vs missing):"
	echo "# $(printf '%-24s %-8s %s' NAME RESULT SOURCE)"
	for n in "${REQ[@]}"; do
		src="--require"
		for d in $DEFAULT_REQUIRED; do [ "$d" = "$n" ] && src="default"; done
		if [ -f "$DIR/$n" ]; then
			P=$((P + 1)); res="PRESENT"
		else
			M=$((M + 1)); res="MISSING"; MISS+=("$n")
		fi
		echo "# $(printf '%-24s %-8s %s' "$n" "$res" "$src")"
	done
	echo "#"
	echo "REQUIRED: ${#REQ[@]}  PRESENT: $P  MISSING: $M"
} > "$PACKED"

printf 'PACKED: %s\n' "$PACKED"
printf 'REQUIRED: %d  PRESENT: %d  MISSING: %d\n' "${#REQ[@]}" "$P" "$M"
if [ "$M" -gt 0 ]; then
	printf 'MISSING: %s\n' "${MISS[*]}"
	exit 1
fi
exit 0
