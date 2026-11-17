# recovery-assist.sh - live, human-in-the-loop TFTP recovery watcher.
#
# The TFTP server has never been the fragile part: it serves the full 20,975,775-byte
# recovery.bin every time it is asked. The fragile part is getting U-Boot into recovery mode:
# the loader only samples RESET during early power-on, so the sequence is
#   power OFF -> hold RESET -> power ON while holding -> keep holding through the counter.
#
# This script watches the read-only UART capture and the TFTP server log and prints one clear line
# per stage, so nobody has to guess whether the hold registered or the transfer finished:
#   PHASE power-off    nothing observed yet
#   PHASE hold        RESET press observed by U-Boot, keep holding
#   PHASE release     recovery mode entered, release the button
#   PHASE transfer    recovery.bin transfer complete
#   PHASE stock       the stock image answered on the LAN
#
# Usage:
#   tools/recovery-assist.sh [seconds]
# Defaults to 300 seconds. Requires an active read-only capture (tools/uart-capture.sh start)
# and the armed recovery door (tools/recovery-card.sh --arm). Read-only: it never opens the tty.
set -uo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
LOG_DIR="$ROOT/build/uart-logs"
TFTP_LOG=/tmp/tftp-3dk-20261116T103021Z.log
LIMIT=${1:-300}

CAP=$(ls -t "$LOG_DIR"/*.log 2>/dev/null | head -1 || true)
[ -n "$CAP" ] || { echo "FAIL: no UART capture log under $LOG_DIR (run tools/uart-capture.sh start)" >&2; exit 1; }
BASE=$(stat -c %s "$CAP" 2>/dev/null || echo 0)
TBASE=$(stat -c %s "$TFTP_LOG" 2>/dev/null || echo 0)

echo "recovery-assist: capture=$CAP (from byte $BASE), limit=${LIMIT}s"
echo "Next action: power the box OFF, hold RESET, then power it ON while still holding."

seen=power
start=$(date +%s)
while :; do
	now=$(date +%s)
	[ $((now - start)) -ge "$LIMIT" ] && { echo "TIMEOUT: no recovery state within ${LIMIT}s; check that power was cycled while RESET was held"; exit 2; }

	if [ "$(stat -c %s "$CAP" 2>/dev/null || echo 0)" -gt "$BASE" ]; then
		if grep -aq 'RESET button is pressed' "$CAP" && [ "$seen" = power ]; then
			seen=hold
			echo "CATCH: U-Boot sees the RESET hold - keep holding"
		fi
		if grep -aq 'recovery button press' "$CAP" && [ "$seen" = hold ]; then
			seen=release
			echo "PHASE release: recovery mode entered - you can let go of RESET"
		fi
		if grep -aq 'TFTP from server' "$CAP" && [ "$seen" = release ]; then
			seen=transfer
			echo "PHASE transfer: recovery.bin is downloading - do not power off"
		fi
	fi
	if [ "$(stat -c %s "$TFTP_LOG" 2>/dev/null || echo 0)" -gt "$TBASE" ] && [ "$seen" = transfer ]; then
		if grep -aq 'RRQ sent 20975775 bytes' "$TFTP_LOG"; then
			echo "PHASE done-transfer: 20,975,775 bytes served; the box is flashing the stock image"
			seen=flash
		fi
	fi
	if [ "$seen" = flash ]; then
		if timeout 2 ping -c 1 -W 1 192.168.10.1 >/dev/null 2>&1; then
			echo "PHASE stock: the stock image is back on 192.168.10.1"
			exit 0
		fi
	fi
	sleep 1
done
