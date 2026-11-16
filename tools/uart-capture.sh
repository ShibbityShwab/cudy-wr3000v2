#!/usr/bin/env bash
# uart-capture.sh - READ-ONLY console capture for the WR3000 v2 bench.
#
# The UART on this bench is read-only: router TX -> host RX works with the swapped pins,
# host TX -> router RX is dead (burnt resistor). This script NEVER writes data to the
# adapter. It configures termios with stty (ioctls only) and opens the tty with a
# read-only redirection. Do not replace it with 'screen', 'minicom', 'picocom', or an
# 'exec 3<>' open; those can send bytes and are forbidden.
#
# usage:
#   tools/uart-capture.sh start [--label NAME] [--timeout SECONDS]   # detached; prints log
#   tools/uart-capture.sh stop  [--label NAME]
#   tools/uart-capture.sh check
#
# The log is always an absolute path under build/uart-logs/ (a relative path inside
# 'sudo sh -c' silently produced zero-byte files on 2026-11-16).
set -uo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
export LC_ALL=C   # keep log timestamps Gregorian
DEV=${UART_DEV:-/dev/ttyUSB0}
BAUD=${UART_BAUD:-115200}
LOG_DIR="$ROOT/build/uart-logs"
LABEL=capture
TIMEOUT=900
CAPTURE_CMD=""

usage() {
	sed -n '3,21p' "$0" | sed 's/^# \{0,1\}//'
}

pidfile() { printf '%s/uart-%s.pid' "$LOG_DIR" "$LABEL"; }

parse_common() {
	while [ $# -gt 0 ]; do
		case "$1" in
			--label) LABEL=$2; shift 2 ;;
			--timeout) TIMEOUT=$2; shift 2 ;;
			-h|--help) usage; exit 0 ;;
			*) echo "unknown argument: $1" >&2; usage; exit 2 ;;
		esac
	done
	case "$LABEL" in
		''|*[!A-Za-z0-9_-]*) echo "error: --label must use only [A-Za-z0-9_-]" >&2; exit 2 ;;
	esac
}

cmd_check() {
	echo "adapter: $DEV"
	if [ -c "$DEV" ]; then
		stat -c '  device: %n %F %a %U:%G' "$DEV"
	else
		echo "  MISSING: $DEV (is the FT232R plugged in?)"
	fi
	local found=0 line
	while IFS= read -r line; do
		echo "  running: $line"
		found=1
	done < <(pgrep -af 'cat < /dev/ttyUSB' 2>/dev/null || true)
	[ "$found" -eq 0 ] && echo "  no read-only capture process is running"
	echo "captures (newest first):"
	local f
	ls -1t "$LOG_DIR"/*.log 2>/dev/null | head -5 | while IFS= read -r f; do
		printf '  %9s bytes  %s\n' "$(stat -c %s "$f")" "$f"
	done
	echo
	echo "REMINDER: the UART is READ-ONLY. Never type, echo, printf, or open it read-write."
}

cmd_start() {
	[ -c "$DEV" ] || { echo "error: no serial device at $DEV" >&2; exit 1; }
	if ! sudo -n true 2>/dev/null; then
		echo "error: UART access needs root and 'sudo -n' is not available;" >&2
		echo "       this user is not in the device's uucp group. Run the capture from a" >&2
		echo "       shell where sudo is already authenticated, or add a udev rule." >&2
		exit 1
	fi
	mkdir -p "$LOG_DIR" || exit 1
	local pf log
	pf=$(pidfile)
	log="$LOG_DIR/$(date -u +%Y%m%dT%H%M%SZ)-uart-$LABEL.log"
	if [ -f "$pf" ] && kill -0 "$(cat "$pf")" 2>/dev/null; then
		echo "error: a capture with label '$LABEL' is already running (pid $(cat "$pf"))" >&2
		exit 1
	fi
	# stty only configures termios; the data path is 'cat <' (O_RDONLY). timeout bounds it.
	CAPTURE_CMD="echo \$\$ > '$pf'; stty -F '$DEV' $BAUD cs8 -cstopb -parenb -crtscts raw -echo; exec timeout $TIMEOUT cat < '$DEV'"
	setsid nohup sudo -n sh -c "$CAPTURE_CMD" >"$log" 2>/dev/null < /dev/null &
	sleep 1
	if [ ! -f "$pf" ] || ! kill -0 "$(cat "$pf")" 2>/dev/null; then
		echo "error: capture failed to start; inspect $log" >&2
		[ -s "$log" ] && tail -5 "$log" >&2
		exit 1
	fi
	echo "capture started (READ-ONLY): pid $(cat "$pf")"
	echo "log: $log"
	echo "stop: tools/uart-capture.sh stop --label $LABEL  (or let it time out after ${TIMEOUT}s)"
}

cmd_stop() {
	local pf pid
	pf=$(pidfile)
	[ -f "$pf" ] || { echo "no capture with label '$LABEL' is recorded"; return 0; }
	pid=$(cat "$pf")
	if kill -0 "$pid" 2>/dev/null; then
		kill "$pid" 2>/dev/null || true
		sleep 0.5
		kill -9 "$pid" 2>/dev/null || true
		echo "stopped capture pid $pid"
	else
		echo "capture pid $pid is not running"
	fi
	rm -f "$pf"
}

cmd=${1:-check}
[ $# -gt 0 ] && shift
parse_common "$@"
case "$cmd" in
	start) cmd_start ;;
	stop) cmd_stop ;;
	check) cmd_check ;;
	*) usage; exit 2 ;;
esac
