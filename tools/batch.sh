#!/usr/bin/env bash
# batch.sh - run N device hypotheses in ONE boot with the exp.sh harness.
#
#   tools/batch.sh [--dry-run] [--module <ko>] [--params "<base params>"] <list>
#
# <list> is a text file of hypotheses, one per line:
#
#     <label>|<param>[,<param>...]
#
#   # comments and blank lines are ignored.  <label> matches [A-Za-z0-9._-]+ and
#   names the evidence sub-directory; <param> is a comma-separated set of
#   key=value module parameters appended to the run's base parameters for that
#   hypothesis only.
#
# The module is staged ONCE by exp.sh with the device-side batch parameters
#
#     batch=/tmp/omo-batch/list batchdir=/tmp/omo-batch <base params>
#
# and the batch list is copied to /tmp/omo-batch/list.  The module-side contract
# (see docs/phase22/exp-harness.md) is that the module walks the list, re-arms
# its base state between entries, and writes per-hypothesis results under
# /tmp/omo-batch/, ending with /tmp/omo-batch/batch.done.  batch.sh then pulls
# /tmp/omo-batch inside the normal evidence tar and folds the per-hypothesis
# observables (out[0] cleared by device y/n, SR+0x1c, glue status, irq count)
# into <evidence>/report.txt.
#
# --dry-run prints the full ordered command sequence (batch prep + the shared
# exp.sh sequence + the report step) and does not touch the device.
#
# 2026-10-02 - built for the phase-22 experiment-harness task (st_01a0fbe0).
set -uo pipefail

BATCH_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=tools/exp.sh
. "$BATCH_DIR/exp.sh"

BATCH_LIST=""
BATCH_BASE_PARAMS="${OMO_BATCH_PARAMS:-}"
BATCH_LOCAL_LIST="/tmp/omo-batch-list"
# The device list MUST live on the persistent overlay: exp.sh reboots into the
# takeover boot and /tmp is tmpfs, so a /tmp list does not survive the reboot
# (found on the first real run).  Results can stay in /tmp - they are pulled
# before recovery in the same takeover boot.
BATCH_DEV_LIST="/root/omo-batch-list"
BATCH_DEV_DIR="/tmp/omo-batch"
BATCH_N=0

batch_usage() {
	cat <<'EOF'
usage: batch.sh [--dry-run] [--module <ko>] [--params "<base params>"] <list>

  <list>            file of "<label>|<param>[,<param>...]" lines
  --module <ko>     batch-capable module (default $OMO_MODULE or
                    build/tmp/omo-batch/omo-batch.ko)
  --params "<p>"    base key=value params applied to every hypothesis
  --dry-run         print the ordered command sequence, touch nothing

The module-side convention is documented in docs/phase22/exp-harness.md.
EOF
}

batch_parse_list() {
	local file="$1" lineno=0 raw label params n=0
	[ -f "$file" ] || { echo "batch.sh: list not found: $file" >&2; return 1; }
	while IFS= read -r raw || [ -n "$raw" ]; do
		lineno=$((lineno + 1))
		case "$raw" in
			''|'#'*) continue ;;
		esac
		case "$raw" in
			*'|'*) label="${raw%%|*}"; params="${raw#*|}" ;;
			*) echo "batch.sh: line $lineno: missing '|': $raw" >&2; return 1 ;;
		esac
		case "$label" in
			*[!A-Za-z0-9._-]*|'') echo "batch.sh: line $lineno: bad label: $label" >&2; return 1 ;;
		esac
		case "$params" in
			*[!A-Za-z0-9_./:=,+@-]*) echo "batch.sh: line $lineno: unsafe params: $params" >&2; return 1 ;;
		esac
		n=$((n + 1))
	done < "$file"
	[ "$n" -ge 1 ] || { echo "batch.sh: no hypotheses in $file" >&2; return 1; }
	BATCH_N="$n"
	return 0
}

batch_report() { # <evidence-dir>
	local dir="$1" found=0
	if [ "$DRY" = 1 ]; then
		exp_hr "report: fold per-hypothesis observables into report.txt"
		exp_note "parse $dir$BATCH_DEV_DIR/batch-summary.txt (or each */result.txt)"
		exp_note "columns: label  out0_cleared  sr1c  glue  irq"
		printf '$ write %s/report.txt\n' "$dir"
		printf '$ BATCH RESULT: PASS|FAIL hypotheses=%s out0_cleared_yes=<n> evidence=%s/\n' "$BATCH_N" "$dir"
		return 0
	fi
	mkdir -p "$dir" 2>/dev/null || true
	{
		printf 'BATCH REPORT %s\n' "$TS"
		printf 'module : %s\n' "$MODULE"
		printf 'list   : %s (%s entries)\n' "$BATCH_LIST" "$BATCH_N"
		printf 'params : batch=%s batchdir=%s %s\n' "$BATCH_DEV_LIST" "$BATCH_DEV_DIR" "$BATCH_BASE_PARAMS"
		printf '\n'
		printf ' #  %-28s %-12s %-12s %-12s %-8s\n' label out0_cleared sr1c glue irq
	} > "$dir/report.txt"
	local f label out0 sr glue irq yes=0 total=0
	# the extracted device tar lands under <dir>/tmp/omo-batch; find dedups
	while IFS= read -r f; do
		[ -f "$f" ] || continue
		found=1
		label="$(sed -n 's/^label=//p' "$f" | head -1)"
		out0="$(sed -n 's/^out0_cleared=//p' "$f" | head -1)"
		sr="$(sed -n 's/^sr1c=//p' "$f" | head -1)"
		glue="$(sed -n 's/^glue=//p' "$f" | head -1)"
		irq="$(sed -n 's/^irq=//p' "$f" | head -1)"
		[ -n "$label" ] || label="$(basename "$(dirname "$f")")"
		total=$((total + 1))
		[ "$out0" = y ] && yes=$((yes + 1))
		printf ' %-3s %-28s %-12s %-12s %-12s %-8s\n' "$total" "$label" "${out0:-?}" "${sr:-?}" "${glue:-?}" "${irq:-?}" >> "$dir/report.txt"
	done <<EOF
$(find "$dir" -type f -path '*/omo-batch/*/result.txt' 2>/dev/null)
EOF
	if [ "$found" = 1 ]; then
		printf '\nBATCH RESULT: %s hypotheses=%s out0_cleared_yes=%s evidence=%s/\n' \
			"$([ -z "$FAILURE" ] && [ "$HEALTH_OK" = 1 ] && echo PASS || echo FAIL)" \
			"$BATCH_N" "$yes" "$dir" >> "$dir/report.txt"
		printf '\n-- %s\n' "$dir/report.txt"
		cat "$dir/report.txt"
	else
		printf '\n!! no per-hypothesis result.txt collected under %s\n' "$dir" >&2
		printf 'BATCH RESULT: FAIL hypotheses=%s reason=no-result-files evidence=%s/\n' "$BATCH_N" "$dir" >> "$dir/report.txt"
		printf 'BATCH RESULT: FAIL hypotheses=%s reason=no-result-files evidence=%s/\n' "$BATCH_N" "$dir"
		return 1
	fi
	return 0
}

batch_main() {
	local -a args=()
	local list="" mod="${OMO_MODULE:-$EXP_ROOT/build/tmp/omo-batch/omo-batch.ko}"
	while [ $# -gt 0 ]; do
		case "$1" in
			--dry-run) DRY=1 ;;
			--module) shift; mod="${1:-}" ;;
			--params) shift; BATCH_BASE_PARAMS="${1:-}" ;;
			-h|--help) batch_usage; return 0 ;;
			*) args+=("$1") ;;
		esac
		shift
	done
	if [ "${#args[@]}" -lt 1 ]; then
		batch_usage
		return 2
	fi
	BATCH_LIST="${args[0]}"
	MODULE="$mod"
	MODBASE="$(basename "$MODULE")"
	MODNAME="${MODBASE%.ko}"
	PARAMS="batch=$BATCH_DEV_LIST batchdir=$BATCH_DEV_DIR $BATCH_BASE_PARAMS"
	EXP_EXTRA_STAGE="$BATCH_LOCAL_LIST:$BATCH_DEV_LIST"
	EXP_EXTRA_PULL="$BATCH_DEV_DIR"
	EXP_DONE_CMD="[ -f $BATCH_DEV_DIR/batch.done ]"
	EXP_EVID_SUFFIX="-batch"
	EXP_RESULT_LABEL="BATCH"

	if [ "$DRY" = 1 ]; then
		if batch_parse_list "$BATCH_LIST"; then :; else BATCH_N="N"; fi
		printf '== batch.sh DRY RUN ==\n'
		printf 'module    : %s (id %s)\n' "$MODULE" "$MODNAME"
		printf 'list      : %s\n' "$BATCH_LIST"
		printf 'base param: [%s]\n' "$BATCH_BASE_PARAMS"
		printf 'device    : params=[%s]\n' "$PARAMS"
		printf 'evidence  : %s/build/register-dumps/exp/<TS>-batch/\n' "$EXP_ROOT"
		printf '# NOTHING BELOW IS EXECUTED IN --dry-run.\n'
		exp_note "validate the list and copy it to a staging path"
		printf '$ batch.sh: validate %s (%s hypotheses)\n' "$BATCH_LIST" "$BATCH_N"
		printf '$ cp %s %s\n' "$BATCH_LIST" "$BATCH_LOCAL_LIST"
		exp_note "the list is staged to the device as $BATCH_DEV_LIST by the"
		exp_note "shared exp.sh staging step (EXP_EXTRA_STAGE)"
		exp_note "the harness then runs the shared exp.sh sequence with:"
		printf '#   EXP_EXTRA_STAGE=%s\n' "$EXP_EXTRA_STAGE"
		printf '#   EXP_EXTRA_PULL=%s\n' "$EXP_EXTRA_PULL"
		printf '#   EXP_DONE_CMD=%s\n' "$EXP_DONE_CMD"
		exp_run
		batch_report "$EVID"
		return 0
	fi

	batch_parse_list "$BATCH_LIST" || { echo "batch.sh: bad list" >&2; return 2; }
	[ -f "$MODULE" ] || { echo "batch.sh: module not found: $MODULE" >&2; return 2; }
	cp "$BATCH_LIST" "$BATCH_LOCAL_LIST" || return 2
	printf '== batch: %s hypotheses in one boot ==\n' "$BATCH_N"
	exp_run
	batch_report "$EVID"
}

if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
	batch_main "$@"
fi
