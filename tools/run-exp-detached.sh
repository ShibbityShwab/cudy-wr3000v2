#!/bin/sh
set -u
W=/c/Users/ShibbityShwab/Documents/GitHub/cudy-wr3000v2
OUT="$W/build/register-dumps/detached"
mkdir -p "$OUT"
LOG="$OUT/run-$(date +%Y%m%d-%H%M%S).log"
exec >"$LOG" 2>&1
echo "=== run-exp-detached start $(date -Iseconds) ==="
echo "module=$*"

printf '#!/bin/sh\necho <ROUTER-SSH-PASSWORD>\n' > /tmp/askpass.sh
chmod +x /tmp/askpass.sh

SSHBASE="cd /tmp && SSH_ASKPASS=/tmp/askpass.sh SSH_ASKPASS_REQUIRE=force DISPLAY=:0"
SSH="$SSHBASE timeout 120 ssh -o PubkeyAuthentication=no -o PreferredAuthentications=password -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null root@192.168.10.1"
SCP="$SSHBASE timeout 180 scp -O -o PubkeyAuthentication=no -o PreferredAuthentications=password -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"

reachable() {
  sh -c "$SSH 'echo REACHABLE' 2>/dev/null" | grep -q REACHABLE
}

wait_reachable() {
  n=0
  while [ "$n" -lt 40 ]; do
    if reachable; then echo "reachable after ${n} polls"; return 0; fi
    n=$((n+1)); sleep 5
  done
  echo "UNREACHABLE after 40 polls"; return 1
}

restore() {
  echo "--- restore $(date -Iseconds) ---"
  sh -c "$SSH 'sh /tmp/restore-now.sh 2>&1 | tail -4' 2>/dev/null" || true
  sh -c "$SSH 'sh /tmp/restore-now.sh >/dev/null 2>&1; (sleep 2; reboot) >/dev/null 2>&1 & echo REBOOTED' 2>/dev/null" || true
  sleep 60
  wait_reachable || true
}

health() {
  echo "--- health $(date -Iseconds) ---"
  sh -c "$SSH \"iw phy 2>/dev/null | grep -c Wiphy; iw dev 2>/dev/null | grep -c Interface; iwpriv vap0 alg get_2g_power_param 2>&1 | head -1 | cut -c1-30; iwpriv vap8 alg get_5g_power_param 2>&1 | head -1 | cut -c1-30; ls /lib/modules/5.10.201/*.omo-off 2>/dev/null | wc -l\" 2>/dev/null"
}

if ! wait_reachable; then echo "DEVICE NOT REACHABLE - aborting"; exit 1; fi

sh -c "$SCP $W/tools/restore-now.sh root@192.168.10.1:/tmp/restore-now.sh 2>&1 | tail -1"

# ORDER IS SAFETY-CRITICAL: the device-side watchdog must be armed before the vendor modules are hidden,
# or a dead runner leaves the router without Wi-Fi (this happened twice on 2026-10-02).
sh -c "$SSH 'cat > /root/rd-watch.sh <<EOS
#!/bin/sh
sleep 900
if [ -f /tmp/rd.done ]; then exit 0; fi
/tmp/restore-now.sh
sync
reboot
EOS
chmod +x /root/rd-watch.sh; rm -f /tmp/rd.done; /usr/sbin/start-stop-daemon -S -b -m -x /root/rd-watch.sh; echo WATCH_ARMED' 2>/dev/null"

# 2. stage
sh -c "$SSH 'cd /lib/modules/5.10.201 && for f in hi5622v100_wifi.ko hi5622v100_plat.ko; do [ -e \$f ] && mv -f \$f \$f.omo-off; done; ls *.omo-off | wc -l' 2>/dev/null"

echo "=== STAGE COMPLETE - module staging from the caller happens here ==="
echo "=== run-exp-detached end-of-scaffold $(date -Iseconds) ==="
