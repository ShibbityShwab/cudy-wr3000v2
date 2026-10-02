#!/bin/bash
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HOST=root@192.168.10.1
SSH_OPTS=(-o PubkeyAuthentication=no -o PreferredAuthentications=password -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10)
export SSH_ASKPASS=/tmp/askpass.sh SSH_ASKPASS_REQUIRE=force DISPLAY=:0
printf '#!/bin/sh\necho <ROUTER-SSH-PASSWORD>\n' > /tmp/askpass.sh
chmod +x /tmp/askpass.sh

SNAP="${1:-}"
APPLY="${2:-}"
if [ -z "$SNAP" ] || [ ! -f "$SNAP/MANIFEST.sha256" ]; then
	echo "usage: wifi-cal-restore.sh <snapshot-dir> [--apply]"
	echo "default is a dry run that lists every write it would perform"
	exit 1
fi

echo "== verifying snapshot integrity =="
( cd "$SNAP" && sha256sum -c MANIFEST.sha256 ) || { echo "MANIFEST CHECK FAILED - aborting"; exit 1; }

echo
echo "== restore plan =="
echo "factory calibration files that would be written back to /usr/local/factory:"
for f in wifi.cal hi5622v100.cal wifi_cali_data.kv wifi_cali_data_2g.kv; do
	[ -f "$SNAP/$f" ] && echo "  $SNAP/$f -> $HOST:/usr/local/factory/$f"
done
echo "chip calibration values that would be re-applied through 'iwpriv Hisilicon0 alg set_*':"
awk '/^=== get_/{cmd=$2} /^Hisilicon0  alg:/{ if (cmd != "") { print "  " cmd "  (value: " substr($0, index($0,"alg:")+4) ")"; cmd="" } }' "$SNAP/alg-values.txt" | head -30

if [ "$APPLY" != "--apply" ]; then
	echo
	echo "DRY RUN - nothing written. Re-run with --apply to perform the writes above."
	exit 0
fi

echo
echo "== applying (factory files) =="
for f in wifi.cal hi5622v100.cal wifi_cali_data.kv wifi_cali_data_2g.kv; do
	if [ -f "$SNAP/$f" ]; then
		scp -O "${SSH_OPTS[@]}" "$SNAP/$f" "$HOST:/usr/local/factory/$f" && echo "wrote $f"
	fi
done
echo "note: set_* command re-application is intentionally manual; copy each value from the plan above"
echo "      into: ssh $HOST 'iwpriv Hisilicon0 alg set_<name> <value>' after confirming the value"
