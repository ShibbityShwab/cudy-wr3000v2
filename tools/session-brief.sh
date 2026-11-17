#!/usr/bin/env bash
# session-brief.sh - deterministic context packet for any agent starting a bench session.
#
# Prints the current git/doc/bench state in one screen so a fresh agent does not have to
# reconstruct it from memory or from ten overlapping docs. Read-only: it runs no device
# write, no flash write, no UART write, and no network change.
#
# usage:
#   tools/session-brief.sh              # full brief (asks the router over SSH)
#   tools/session-brief.sh --offline    # host + docs only (no SSH)
set -uo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT" || exit 1
export LC_ALL=C   # the desktop locale here is th_TH; %Y must stay Gregorian (2026, not 2569)
OFFLINE=0
[ "${1:-}" = "--offline" ] && OFFLINE=1

WARNINGS=()
warn() { WARNINGS+=("$*"); }

short_head() { git rev-parse --short HEAD 2>/dev/null || echo '?'; }
dirty_count() { git status --porcelain 2>/dev/null | wc -l | tr -d ' '; }

# ---- repo ----
GIT_HEAD=$(short_head)
GIT_DIRTY=$(dirty_count)
SUB_HEAD=$(git -C opensource rev-parse --short HEAD 2>/dev/null || echo '?')
SUB_DIRTY=$(git -C opensource status --porcelain 2>/dev/null | wc -l | tr -d ' ')
SUB_AB=$(git -C opensource rev-list --left-right --count origin/master...HEAD 2>/dev/null | awk '{print "ahead "$2" behind "$1}' || true)
[ -n "$SUB_AB" ] || SUB_AB='(no origin ref)'

# ---- docs freshness ----
STATUS_UPDATED=$(sed -n 's/^\*\*Updated:\*\* *//p' STATUS.md 2>/dev/null | head -1)
LATEST_LEDGER=$(grep -oE '^## [0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}' mem-entries.md 2>/dev/null | tail -1 | sed 's/^## //')
[ -n "$STATUS_UPDATED" ] || warn "STATUS.md has no '**Updated:**' line"
[ -n "$LATEST_LEDGER" ] || warn "could not read the newest dated entry from mem-entries.md"
if [ -n "$STATUS_UPDATED" ] && [ -n "$LATEST_LEDGER" ]; then
	LEDGER_DAY=${LATEST_LEDGER%% *}
	if [[ "$LEDGER_DAY" > "$STATUS_UPDATED" ]]; then
		warn "newer ledger entry ($LATEST_LEDGER) than STATUS.md updated ($STATUS_UPDATED); run tools/check-repo.sh and refresh STATUS"
	fi
fi

# ---- local guards ----
if "$ROOT/tools/check-init-shadow.sh" >/dev/null 2>&1; then GUARD_SHADOW=PASS; else GUARD_SHADOW=FAIL; warn "shadow guard FAILED (tools/check-init-shadow.sh)"; fi
if "$ROOT/tools/check-lab-src.sh" --manifest-only >/dev/null 2>&1; then GUARD_SNAP=PASS; else GUARD_SNAP=FAIL; warn "tracked kernel snapshot FAILED (tools/check-lab-src.sh --manifest-only)"; fi

# ---- host bench link ----
IFACE=${BENCH_IFACE:-enp195s0f3u1}
HOST_LINE=''
if [ -d "/sys/class/net/$IFACE" ]; then
	NMSTATE=$(nmcli -t -f DEVICE,STATE device status 2>/dev/null | awk -F: -v d="$IFACE" '$1==d {print $2; exit}')
	CARRIER=$(cat "/sys/class/net/$IFACE/carrier" 2>/dev/null || echo '?')
	SPEED=$(cat "/sys/class/net/$IFACE/speed" 2>/dev/null || echo '?')
	ADDRS=$(ip -4 -o addr show dev "$IFACE" 2>/dev/null | awk '{print $4}' | tr '\n' ' ')
	HOST_LINE="$IFACE carrier=$CARRIER speed=${SPEED}Mb nm=${NMSTATE:-?} addrs=${ADDRS:-<none>}"
	case " $ADDRS " in
		*" 192.168.1.88/24 "*) ;;
		*) warn "host adapter $IFACE is missing 192.168.1.88/24 (TFTP recovery will fail); run tools/bench-link.sh --apply" ;;
	esac
	case " $ADDRS " in
		*" 192.168.10.44/24 "*) ;;
		*) warn "host adapter $IFACE is missing 192.168.10.44/24 (broker/HTTP lane will fail); run tools/bench-link.sh --apply" ;;
	esac
	[ "$NMSTATE" = "unmanaged" ] || warn "host adapter $IFACE is managed by NetworkManager (state ${NMSTATE:-?}); it strips the addresses"
else
	warn "bench interface $IFACE not found"
fi

# ---- UART (read-only) ----
if [ -c ${UART_DEV:-/dev/ttyUSB0} ]; then UART='present (READ-ONLY: never transmit)'; else UART='MISSING (is the FT232R plugged in?)'; warn "UART adapter missing"; fi
ancestor_pids() {
	local p=$$
	while [ -n "$p" ] && [ "$p" -gt 1 ]; do
		printf '%s\n' "$p"
		p=$(ps -o ppid= -p "$p" 2>/dev/null | tr -d ' ')
	done
}
ANCESTORS=$(ancestor_pids | tr '\n' ' ')
matching_pids() {
	local pat=$1 pid
	for pid in $(pgrep -f "$pat" 2>/dev/null || true); do
		case " $ANCESTORS " in *" $pid "*) continue ;; esac
		printf '%s\n' "$pid"
	done
}
capture_pids() {
	local pf pid out=""
	for pf in "$ROOT"/build/uart-logs/*.pid; do
		[ -f "$pf" ] || continue
		pid=$(cat "$pf" 2>/dev/null) || continue
		case "$pid" in ''|*[!0-9]*) continue ;; esac
		if kill -0 "$pid" 2>/dev/null || sudo -n kill -0 "$pid" 2>/dev/null; then
			out="$out $pid"
		else
			sudo -n rm -f "$pf" 2>/dev/null || rm -f "$pf" 2>/dev/null || true
		fi
	done
	for pid in $(matching_pids 'timeout [0-9]+ cat'); do out="$out $pid"; done
	out=${out# }
	[ -n "$out" ] && printf '%s\n' "$out"
}
if [ -n "$(capture_pids | awk '{print $1; exit}')" ]; then CAPTURE='running'; else CAPTURE='not running'; fi
ACTIVE_FIRE=$(matching_pids 'bash .*fire-ssh[.]sh|bash .*fire-device[.]sh|bash .*run-phase[0-9a-z]+[.]sh')
STALE_WRITERS=$(matching_pids 'tee -a .*/fire-')
if [ -n "$ACTIVE_FIRE" ]; then warn "a fire driver is still running (pid(s): $(echo $ACTIVE_FIRE)); do not start another"; fi
if [ -n "$STALE_WRITERS" ]; then warn "stale fire-log writer(s) still running (pid(s): $(echo $STALE_WRITERS)); clean with tools/bench-teardown.sh --apply"; fi

# ---- recovery / broker listeners ----
if ss -lun 2>/dev/null | grep -qE ':(69)[[:space:]]'; then TFTP='UDP 69 LISTENING (recovery armed)'; else TFTP='not listening (arm before any fire)'; fi
if ss -lnt 2>/dev/null | grep -qE ':(8000)[[:space:]]'; then
	HTTP='TCP 8000 LISTENING'
	warn "a broker HTTP server is still running on :8000 (it serves the repo root, including .omo-secrets, to the LAN); stop it with: pkill -f 'http.server 8000'"
else
	HTTP='not listening'
fi
RECOVERY_MD5='missing'
if [ -f tftp/recovery.bin ]; then
	RECOVERY_MD5=$(md5sum tftp/recovery.bin | awk '{print $1}')
	[ "$RECOVERY_MD5" = "421114c8ea999c925b7aa79cc548af81" ] || warn "tftp/recovery.bin md5 is $RECOVERY_MD5, expected 421114c8ea999c925b7aa79cc548af81"
fi

# ---- latest build artifacts ----
SLICE=$(ls -t build/linux-kbuild/luofu-slice-phase*.bin 2>/dev/null | head -1)
if [ -n "$SLICE" ]; then
	SLICE_LINE="$(basename "$SLICE") $(stat -c %s "$SLICE") B md5 $(md5sum "$SLICE" | awk '{print $1}')"
else
	SLICE_LINE='none'
	warn "no luofu-slice-phase*.bin built"
fi
SNAP=$(ls -d build/linux-kbuild/cal-snapshots/*/ 2>/dev/null | tail -1)
if [ -n "$SNAP" ] && [ -f "$SNAP/MANIFEST.sha256" ]; then CAL_LINE="$SNAP (MANIFEST ok)"; else CAL_LINE='none with MANIFEST'; fi

# ---- device ----
DEV_LINE='skipped (--offline)'
if [ "$OFFLINE" -eq 0 ]; then
	PROBE=$(timeout 20 "$ROOT/tools/rsh.sh" 'echo "UP=$(cut -d. -f1 /proc/uptime)"; echo "KERNEL=$(uname -r)"; echo "BOOTFLAG=$(fw_printenv bootflag 2>/dev/null | cut -d= -f2)"; echo "BOOTREG=0x$(cat /sys/devices/platform/sysenv/boot_reg 2>/dev/null)"; echo "WIPHY=$(ls /sys/class/ieee80211 2>/dev/null | wc -l)"; echo "HI=$(lsmod | grep -c "^hi_")"; echo "OMO=$(ls /lib/modules/5.10.201/*.omo-off 2>/dev/null | wc -l)"; echo "OVERLAYKO=$(ls /overlay/upper/lib/hisilicon/ko/*.ko 2>/dev/null | wc -l)"; echo "CAL2=$(dmesg | grep -c "hwifi_rf_cali_file_load_2g succ")"; echo "CAL5=$(dmesg | grep -c "hwifi_rf_cali_file_load_5g succ")"' 2>/dev/null)
	if [ -n "$PROBE" ]; then
		declare -A P=()
		while IFS='=' read -r k v; do [ -n "$k" ] && P["$k"]=$v; done <<< "$PROBE"
		UP=${P[UP]:-0}; HRS=$((UP / 3600)); MINS=$(( (UP % 3600) / 60 ))
		DEV_LINE="192.168.10.1 UP ${HRS}h${MINS}m kernel ${P[KERNEL]:-?} | bootflag=${P[BOOTFLAG]:-?} boot_reg=${P[BOOTREG]:-?} | wiphy=${P[WIPHY]:-?} cal2g=${P[CAL2]:-?} cal5g=${P[CAL5]:-?} hi_mods=${P[HI]:-?} omo-off=${P[OMO]:-?} overlay-ko=${P[OVERLAYKO]:-?}"
		[ "${P[WIPHY]:-0}" -ge 2 ] 2>/dev/null || warn "device reports fewer than 2 wiphys"
		[ "${P[OMO]:-1}" = "0" ] 2>/dev/null || warn "device has .omo-off leftovers; restore before experiments"
		[ "${P[HI]:-0}" -ge 30 ] 2>/dev/null || warn "device reports fewer than 30 hi_ modules (vendor stack not loaded?)"
	else
		DEV_LINE='UNREACHABLE (192.168.10.1: no SSH)'
		warn "router unreachable over SSH; recovery requires hands on the box (tools/recovery-card.sh)"
	fi
fi

# ---- next action from STATUS ----
NEXT=$(awk 'tolower($0) ~ /^## ([0-9]+\. )?next action/ {f=1; next} /^## / {f=0} f && NF {print; n++; if (n>=8) exit}' STATUS.md 2>/dev/null)
[ -n "$NEXT" ] || warn "STATUS.md has no readable '## Next action' section"

# ---- print ----
echo "== BENCH BRIEF $(date '+%Y-%m-%d %H:%M:%S %z') =="
echo "repo:    master @ $GIT_HEAD (dirty files: $GIT_DIRTY) | opensource @ $SUB_HEAD (dirty: $SUB_DIRTY, $SUB_AB)"
echo "docs:    STATUS updated ${STATUS_UPDATED:-?} | newest ledger ${LATEST_LEDGER:-?}"
echo "guards:  shadow $GUARD_SHADOW | lab-src snapshot $GUARD_SNAP"
echo "host:    $HOST_LINE"
echo "uart:    $UART | capture: $CAPTURE (use tools/uart-capture.sh; never transmit)"
echo "recovery: $TFTP | recovery.bin md5 $RECOVERY_MD5"
echo "broker:  $HTTP"
if [ "$OFFLINE" -eq 0 ]; then echo "device:  $DEV_LINE"; fi
echo "slice:   $SLICE_LINE"
echo "cal:     $CAL_LINE"
echo
echo "NEXT ACTION (STATUS.md):"
if [ -n "$NEXT" ]; then printf '%s\n' "$NEXT" | sed 's/^/  /'; else echo "  <none found>"; fi
echo
if [ ${#WARNINGS[@]} -gt 0 ]; then
	echo "WARNINGS:"
	for w in "${WARNINGS[@]}"; do echo "  - $w"; done
else
	echo "WARNINGS: none"
fi
echo
echo "Before a device action: read BENCH-FACTS.md, STATUS.md, LESSONS.md, and run tools/fire-preflight.sh."
