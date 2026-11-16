#!/usr/bin/env bash
# bench-teardown.sh - find and clean the leftovers a previous bench session left running.
#
# Leftovers are not harmless: a stale broker HTTP server serves the repository root
# (including .omo-secrets) on the LAN, and a stale fire-log writer makes the next agent
# think a fire is still running. This is the teardown step for the end of a session.
#
# usage:
#   tools/bench-teardown.sh              # show leftovers (read-only)
#   tools/bench-teardown.sh --apply      # kill stale fire-log writers and stale HTTP servers
#   tools/bench-teardown.sh --all        # --apply + stop the TFTP server and UART capture
#   tools/bench-teardown.sh --apply --force   # even if a fire driver is running
set -uo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT" || exit 1
export LC_ALL=C

APPLY=0
ALL=0
FORCE=0
for a in "$@"; do
	case "$a" in
		--apply) APPLY=1 ;;
		--all) APPLY=1; ALL=1 ;;
		--force) FORCE=1 ;;
		-h|--help) sed -n '3,16p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
		*) echo "unknown argument: $a" >&2; exit 2 ;;
	esac
done

ancestor_pids() {
	local p=$$
	while [ -n "$p" ] && [ "$p" -gt 1 ]; do printf '%s\n' "$p"; p=$(ps -o ppid= -p "$p" 2>/dev/null | tr -d ' '); done
}
ANCESTORS=$(ancestor_pids | tr '\n' ' ')
matching_pids() {
	local pat=$1 pid
	for pid in $(pgrep -f "$pat" 2>/dev/null || true); do
		case " $ANCESTORS " in *" $pid "*) continue ;; esac
		printf '%s\n' "$pid"
	done
}
show_pids() {
	local pids=$1
	[ -n "$pids" ] || return 0
	for p in $pids; do ps -o pid=,user=,etime=,cmd= -p "$p" 2>/dev/null | sed 's/^/    /'; done
}
kill_pids() {
	local pids=$1 what=$2
	[ -n "$pids" ] || return 0
	echo "  killing $what: $pids"
	# shellcheck disable=SC2086
	kill $pids 2>/dev/null || true
	sleep 0.5
	# shellcheck disable=SC2086
	kill -9 $pids 2>/dev/null || true
}

ACTIVE_FIRE=$(matching_pids 'bash .*fire-ssh[.]sh|bash .*fire-device[.]sh|bash .*run-phase[0-9a-z]+[.]sh')
STALE_TEE=$(matching_pids 'tee -a .*/fire-')
HTTP_PIDS=$(matching_pids 'python3 -m http[.]server 8000')
TFTP_PIDS=$(matching_pids 'tools/tftp_server[.]py')
capture_pids() {
	local pf pid out=""
	for pf in "$ROOT"/build/uart-logs/*.pid; do
		[ -f "$pf" ] || continue
		pid=$(cat "$pf" 2>/dev/null) || continue
		case "$pid" in ''|*[!0-9]*) continue ;; esac
		if kill -0 "$pid" 2>/dev/null; then out="$out $pid"; else rm -f "$pf" 2>/dev/null || true; fi
	done
	for pid in $(matching_pids 'timeout [0-9]+ cat'); do out="$out $pid"; done
	printf '%s\n' "$out"
}
CAPTURE_PIDS=$(capture_pids)

echo "== bench teardown: $(date '+%Y-%m-%d %H:%M:%S %z') =="
echo "fire drivers running:"; show_pids "$ACTIVE_FIRE"; [ -n "$ACTIVE_FIRE" ] || echo "    none"
echo "stale fire-log writers:"; show_pids "$STALE_TEE"; [ -n "$STALE_TEE" ] || echo "    none"
echo "broker HTTP servers:"; show_pids "$HTTP_PIDS"; [ -n "$HTTP_PIDS" ] || echo "    none"
echo "TFTP servers:"; show_pids "$TFTP_PIDS"; [ -n "$TFTP_PIDS" ] || echo "    none"
echo "UART captures:"; show_pids "$CAPTURE_PIDS"; [ -n "$CAPTURE_PIDS" ] || echo "    none"

if [ "$APPLY" -eq 0 ]; then
	echo
	echo "read-only check. Apply the safe cleanups with: tools/bench-teardown.sh --apply"
	exit 0
fi

if [ -n "$ACTIVE_FIRE" ] && [ "$FORCE" -eq 0 ]; then
	echo
	echo "REFUSING: a fire driver is running. Wait for it, or pass --force if it is known dead." >&2
	exit 1
fi

echo
echo "applying:"
kill_pids "$STALE_TEE" "stale fire-log writers"
kill_pids "$HTTP_PIDS" "broker HTTP servers"
if [ "$ALL" -eq 1 ]; then
	if [ -n "$TFTP_PIDS" ]; then
		echo "  stopping TFTP server (the recovery door will be DOWN until re-armed)"
		# shellcheck disable=SC2086
		sudo -n kill $TFTP_PIDS 2>/dev/null || kill $TFTP_PIDS 2>/dev/null || true
		sleep 0.5
	fi
	kill_pids "$CAPTURE_PIDS" "UART captures"
	rm -f build/uart-logs/*.pid 2>/dev/null || true
else
	echo "  (TFTP server and UART capture left alone; use --all to stop them)"
fi
echo
echo "done. Re-check with tools/session-brief.sh."
