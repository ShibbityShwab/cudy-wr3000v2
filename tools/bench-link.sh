#!/usr/bin/env bash
# bench-link.sh - show or fix the host side of the router-eth2 <-> USB-Ethernet bench link.
#
# The router LAN port that Linux names eth2 is cabled to the host USB-Ethernet adapter. The
# adapter is auto-detected (known box MAC first, then the USB-Ethernet driver; NEVER the
# phone's RNDIS tether - 2026-11-26: the tether took the old name and was wrongly unmanaged).
# The host must keep that adapter NetworkManager-unmanaged and carry
# 192.168.1.88/24 (TFTP recovery server) and 192.168.10.44/24 (vendor LAN).
# NetworkManager otherwise retries DHCP, strips the addresses, and the board's ARP for
# 192.168.1.88 goes unanswered. This cost a full recovery attempt on 2026-11-16.
#
# usage:
#   tools/bench-link.sh            # check (read-only)
#   tools/bench-link.sh --apply    # unmanage + add addresses + allow recovery ports (sudo -n)
#   tools/bench-link.sh --iface NAME
set -uo pipefail

# The box adapter: known MAC first (stable across renames), then the USB-Ethernet
# driver class (r8152/ax88179/cdc_ncm).  Never the RNDIS phone tether, which is the
# host internet path.  BENCH_IFACE overrides.
BOX_ADAPTER_MAC=00:e0:4c:68:02:14
detect_bench_iface() {
	for n in /sys/class/net/*; do
		[ "$(cat "$n/address" 2>/dev/null)" = "$BOX_ADAPTER_MAC" ] && { basename "$n"; return; }
	done
	for n in /sys/class/net/*; do
		d=$(basename "$(readlink -f "$n/device/driver" 2>/dev/null)" 2>/dev/null)
		case "$d" in r8152|ax88179_178a|cdc_ncm) basename "$n"; return;; esac
	done
	echo enp195s0f3u1
}
IFACE=${BENCH_IFACE:-$(detect_bench_iface)}
APPLY=0
TFTP_SERVER_IP=192.168.1.88
LAN_HOST_IP=192.168.10.44

usage() { sed -n '3,17p' "$0" | sed 's/^# \{0,1\}//'; }

while [ $# -gt 0 ]; do
	case "$1" in
		--apply) APPLY=1 ;;
		--iface) IFACE=$2; shift ;;
		-h|--help) usage; exit 0 ;;
		*) echo "unknown argument: $1" >&2; usage; exit 2 ;;
	esac
	shift
done

[ -d "/sys/class/net/$IFACE" ] || { echo "error: no such interface: $IFACE" >&2; exit 1; }

fail=0
state=$(nmcli -t -f DEVICE,STATE device status 2>/dev/null | awk -F: -v d="$IFACE" '$1==d {print $2; exit}')
carrier=$(cat "/sys/class/net/$IFACE/carrier" 2>/dev/null || echo '?')
speed=$(cat "/sys/class/net/$IFACE/speed" 2>/dev/null || echo '?')
addrs=$(ip -4 -o addr show dev "$IFACE" 2>/dev/null | awk '{print $4}' | tr '\n' ' ')
[ -n "$addrs" ] || addrs='<none>'

echo "bench link: $IFACE"
echo "  NetworkManager state: ${state:-unknown}"
echo "  carrier: $carrier   speed: ${speed} Mb/s"
echo "  addresses: $addrs"

case "$state" in
	unmanaged) echo "  OK: adapter is unmanaged" ;;
	*) echo "  FAIL: adapter is managed (state '${state:-unknown}'); NetworkManager will strip the addresses"; fail=1 ;;
esac
[ "$carrier" = "1" ] || { echo "  FAIL: no carrier; check the cable to the router eth2 port"; fail=1; }
case " $addrs " in
	*" $TFTP_SERVER_IP/24 "*) echo "  OK: $TFTP_SERVER_IP/24 present (TFTP recovery)" ;;
	*) echo "  FAIL: missing $TFTP_SERVER_IP/24 (TFTP recovery server address)"; fail=1 ;;
esac
case " $addrs " in
	*" $LAN_HOST_IP/24 "*) echo "  OK: $LAN_HOST_IP/24 present (vendor LAN / broker HTTP)" ;;
	*) echo "  FAIL: missing $LAN_HOST_IP/24 (vendor LAN host address)"; fail=1 ;;
esac

if command -v ss >/dev/null 2>&1; then
	echo "  listeners:"
	ss -lun 2>/dev/null | grep -E ':(69)[[:space:]]' | sed 's/^/    UDP /' || true
	ss -lnt 2>/dev/null | grep -E ':(8000)[[:space:]]' | sed 's/^/    TCP /' || true
fi

if [ "$fail" -eq 0 ] && [ "$APPLY" -eq 0 ]; then
	echo "PASS: the bench link is in the expected state"
	exit 0
fi

if [ "$APPLY" -eq 0 ]; then
	echo
	echo "fix with:"
	echo "  tools/bench-link.sh --apply"
	echo "or manually:"
	echo "  sudo nmcli device set $IFACE managed no"
	echo "  sudo ip addr replace $TFTP_SERVER_IP/24 dev $IFACE"
	echo "  sudo ip addr replace $LAN_HOST_IP/24 dev $IFACE"
	echo "  sudo ip link set $IFACE up"
	exit 1
fi

if ! sudo -n true 2>/dev/null; then
	echo "error: --apply needs passwordless sudo (sudo -n)" >&2
	exit 1
fi
echo "applying..."
# 'nmcli device set managed no' is runtime-only: NetworkManager reclaimed this adapter during
# the 2026-11-17 audit and stripped 192.168.1.88. Install a drop-in so it stays unmanaged
# across NM restarts as well.
NM_CONF=/etc/NetworkManager/conf.d/99-bench-unmanaged.conf
printf '[keyfile]\nunmanaged-devices=interface-name:%s\n' "$IFACE" | sudo -n tee "$NM_CONF" >/dev/null || exit 1
echo "  wrote $NM_CONF"
# Apply the drop-in now. Without the reload, NM keeps managing the port until its next
# restart and re-applies its profile later (observed overnight 2026-11-16->17).
sudo -n nmcli general reload >/dev/null 2>&1 || sudo -n systemctl reload NetworkManager >/dev/null 2>&1 || true
sleep 1
sudo -n nmcli device set "$IFACE" managed no || exit 1
sudo -n ip addr replace "$TFTP_SERVER_IP/24" dev "$IFACE" || exit 1
sudo -n ip addr replace "$LAN_HOST_IP/24" dev "$IFACE" || exit 1
sudo -n ip link set "$IFACE" up || exit 1

if sudo -n ufw status 2>/dev/null | grep -q '^Status: active'; then
	echo "ufw is active; allowing the recovery and broker ports on $IFACE"
	sudo -n ufw allow in on "$IFACE" from 192.168.1.0/24 to any port 69 proto udp >/dev/null || true
	sudo -n ufw allow in on "$IFACE" from 192.168.10.0/24 to any port 8000 proto tcp >/dev/null || true
fi

echo
exec "$0" --iface "$IFACE"
