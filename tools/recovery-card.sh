#!/usr/bin/env bash
# recovery-card.sh - print and arm the physical recovery procedure for the bench router.
#
# The WR3000 v2 can only be recovered with hands on the box: a true power-on reset with the
# RESET button held through the counter, then TFTP. An agent cannot do that. This card
# checks the host side, optionally starts the TFTP server, and prints exactly what the
# human must do. It performs no flash write and no UART write.
#
# usage:
#   tools/recovery-card.sh          # check + print the card
#   tools/recovery-card.sh --arm    # also start the TFTP server if it is not running
#   tools/recovery-card.sh --stop   # stop a TFTP server this repo started
set -uo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT" || exit 1
export LC_ALL=C

EXPECTED_MD5=421114c8ea999c925b7aa79cc548af81
EXPECTED_SIZE=20975775
ARM=0
STOP=0
case "${1:-}" in
	--arm) ARM=1 ;;
	--stop) STOP=1 ;;
	-h|--help) sed -n '3,16p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
esac

TFTP_PIDS=$(pgrep -f 'tools/tftp_server[.]py' 2>/dev/null || true)

if [ "$STOP" -eq 1 ]; then
	[ -n "$TFTP_PIDS" ] || { echo "no TFTP server is running"; exit 0; }
	echo "stopping TFTP server: $TFTP_PIDS"
	# shellcheck disable=SC2086
	kill $TFTP_PIDS 2>/dev/null || true
	sleep 0.5
	pgrep -f 'tools/tftp_server[.]py' >/dev/null 2>&1 && echo "warning: a TFTP server is still running" || echo "stopped"
	exit 0
fi

fail=0
echo "== recovery card: Cudy WR3000 v2 (luofu) =="
echo

echo "1. host bench link"
if "$ROOT/tools/bench-link.sh" >/tmp/recovery-bench-link.out 2>&1; then
	echo "   PASS: enp195s0f3u1 is unmanaged, has 192.168.1.88/24 + 192.168.10.44/24, carrier up"
else
	echo "   FAIL: bench link is not ready; fix with tools/bench-link.sh --apply"
	sed 's/^/   /' /tmp/recovery-bench-link.out
	fail=1
fi

echo
echo "2. recovery image"
if [ -f tftp/recovery.bin ]; then
	MD5=$(md5sum tftp/recovery.bin | awk '{print $1}')
	SIZE=$(stat -c %s tftp/recovery.bin)
	if [ "$MD5" = "$EXPECTED_MD5" ] && [ "$SIZE" = "$EXPECTED_SIZE" ]; then
		echo "   PASS: tftp/recovery.bin $SIZE B md5 $MD5"
	else
		echo "   FAIL: tftp/recovery.bin is $SIZE B md5 $MD5 (expected $EXPECTED_SIZE B md5 $EXPECTED_MD5)"
		fail=1
	fi
else
	echo "   FAIL: tftp/recovery.bin is missing"
	fail=1
fi

echo
echo "3. TFTP server (UDP 69)"
if [ -n "$TFTP_PIDS" ]; then
	echo "   PASS: running (pid(s): $TFTP_PIDS)"
elif [ "$ARM" -eq 1 ]; then
	if ! sudo -n true 2>/dev/null; then
		echo "   FAIL: --arm needs passwordless sudo for UDP 69"
		fail=1
	else
		mkdir -p build
		setsid nohup sudo -n python3 tools/tftp_server.py 69 >build/tftp-server.log 2>&1 < /dev/null &
		sleep 1
		if pgrep -f 'tools/tftp_server[.]py' >/dev/null 2>&1; then
			TFTP_PIDS=$(pgrep -f 'tools/tftp_server[.]py' 2>/dev/null || true)
			echo "   PASS: started (pid(s): $TFTP_PIDS; log build/tftp-server.log)"
		else
			echo "   FAIL: server did not start; see build/tftp-server.log"
			fail=1
		fi
	fi
else
	echo "   FAIL: not running; start with: tools/recovery-card.sh --arm"
	fail=1
fi

echo
echo "== THE PHYSICAL STEP (only the human at the bench can do this) =="
cat <<'CARD'
   a. Power the router OFF at the wall.
   b. Hold the RESET button down and keep holding it.
   c. Power the router ON while still holding RESET.
   d. Watch the read-only console: it must print
        RESET button is pressed for:  2 second(s)
        Resetting...
        recovery button press
      Only on a true power-on reset does the counter reach 2 s. A short hold leaves
      0 second(s) and the box boots normally.
   e. The loader then contacts 192.168.1.88: "TFTP from server 192.168.1.88; our IP
      address is 192.168.1.1" and requests recovery.bin. A successful transfer logs
      "RRQ recovery.bin" followed by "RRQ sent 20975775 bytes".
   f. Let it flash. The stock LAN returns at 192.168.10.1 (the box reboots itself).
CARD
echo
echo "== after recovery =="
echo "   - verify: tools/session-brief.sh"
echo "   - the recovered overlay is empty: reinstall the project key and start dropbear"
echo "     with -R after deleting zero-byte host keys (RUNBOOK.md section 6)"
echo "   - verify 2 wiphys, calibration [SUCC] on both bands, no .omo-off leftovers"
echo
if [ "$fail" -eq 0 ]; then
	echo "STATUS: recovery door is READY (host + image + server)."
	exit 0
fi
echo "STATUS: recovery door is NOT ready; fix the failures above before any fire." >&2
exit 1
