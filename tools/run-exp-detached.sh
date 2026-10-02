#!/bin/sh
set -u
W=/c/Users/ShibbityShwab/Documents/GitHub/cudy-wr3000v2
OUT="$W/build/register-dumps/detached"
mkdir -p "$OUT"
LOG="$OUT/run-$(date +%Y%m%d-%H%M%S).log"
exec >"$LOG" 2>&1
echo "=== run-exp-detached start $(date -Iseconds) ==="
echo "module=$*"

printf '#!/bin/sh\necho %s\n' "${ROUTER_SSH_PASSWORD:?set ROUTER_SSH_PASSWORD, or add an ssh key for the router}" > /tmp/askpass.sh
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

heal(){
  echo "--- recovery $(date -Iseconds) ---"
  sh -c "$SCP $W/tools/restore-now.sh root@192.168.10.1:/tmp/restore-now.sh >/dev/null 2>&1; $SSH 'touch /tmp/rd.done; pkill -f rd-watch; rm -f /root/rd-watch.sh; sh /tmp/restore-now.sh' 2>/dev/null"
  sh -c "$SSH '(sleep 2; reboot) >/dev/null 2>&1 & echo REBOOTING_FOR_RESTORE' 2>/dev/null"
  sleep 70
  wait_reachable || true
}

verify_health(){
  n=0
  while [ "$n" -lt 12 ]; do
    R=$(sh -c "$SSH 'iw phy 2>/dev/null | grep -c Wiphy; iw dev 2>/dev/null | grep -c Interface; iwpriv vap0 alg get_2g_power_param 2>&1 | head -1 | grep -c SUCC; ls /lib/modules/5.10.201/*.omo-off 2>/dev/null | wc -l' 2>/dev/null")
    W=$(echo "$R" | sed -n 1p); I=$(echo "$R" | sed -n 2p); C=$(echo "$R" | sed -n 3p); O=$(echo "$R" | sed -n 4p)
    echo "  health probe $n: wiphy=$W iface=$I cal=$C hidden=$O"
    if [ "$W" = "2" ] && [ "$I" = "6" ] && [ "$C" = "1" ] && [ "$O" = "0" ]; then echo "RECOVERY VERIFIED"; return 0; fi
    n=$((n+1)); sleep 10
  done
  echo "RECOVERY NOT VERIFIED - router may still be on the vendor stack from the last reboot; inspect by hand"
  return 1
}

MODULE="${1:-}"
shift 2>/dev/null || true
PARAMS="$*"
if [ -z "$MODULE" ] || [ ! -f "$MODULE" ]; then
  echo "usage: run-exp-detached.sh <module.ko> [insmod params]"
  exit 2
fi
MODNAME=$(basename "$MODULE" .ko)

if ! wait_reachable; then echo "DEVICE NOT REACHABLE - aborting"; exit 1; fi

sh -c "$SCP $W/tools/restore-now.sh root@192.168.10.1:/tmp/restore-now.sh 2>&1 | tail -1"

# ORDER IS SAFETY-CRITICAL: the device-side watchdog must be armed, with its all-clear flag ABSENT, before the
# vendor modules are hidden - a stale /tmp/rd.done would let it reboot a healthy router at expiry (seen 2026-10-02).
sh -c "$SSH 'cat > /root/rd-watch.sh <<EOS
#!/bin/sh
sleep 900
if [ -f /tmp/rd.done ]; then exit 0; fi
/tmp/restore-now.sh
sync
reboot
EOS
chmod +x /root/rd-watch.sh; rm -f /tmp/rd.done; /usr/sbin/start-stop-daemon -S -b -m -x /root/rd-watch.sh; echo WATCH_ARMED flag_cleared=yes' 2>/dev/null"

sh -c "$SSH 'cd /lib/modules/5.10.201 && for f in hi5622v100_wifi.ko hi5622v100_plat.ko; do [ -e \$f ] && mv -f \$f \$f.omo-off; done; ls *.omo-off | wc -l' 2>/dev/null"

sh -c "$SCP $MODULE root@192.168.10.1:/lib/modules/5.10.201/$MODNAME.ko 2>&1 | tail -1"
sh -c "$SSH 'cat > /etc/init.d/omo-$MODNAME <<EOS
#!/bin/sh /etc/rc.common
START=99
start() {
  insmod /lib/modules/5.10.201/$MODNAME.ko $PARAMS
  rm -f /etc/rc.d/S99omo-$MODNAME
}
EOS
chmod +x /etc/init.d/omo-$MODNAME; ln -sf /etc/init.d/omo-$MODNAME /etc/rc.d/S99omo-$MODNAME; echo LOADER_INSTALLED' 2>/dev/null"

echo "=== STAGED $MODNAME - rebooting into the takeover boot ==="
sh -c "$SSH '(sleep 2; reboot) >/dev/null 2>&1 & echo REBOOTING' 2>/dev/null"
sleep 90
wait_reachable || true

echo "--- capture $(date -Iseconds) ---"
sh -c "$SSH 'dmesg' 2>/dev/null" >"$OUT/$MODNAME-dmesg.txt"
sh -c "$SSH 'lsmod | head -30; echo ---; cat /proc/interrupts | grep -i pci | head -4; echo ---; ls /etc/init.d/ | grep omo-' 2>/dev/null" >>"$OUT/$MODNAME-dmesg.txt"
if grep -q "$MODNAME" "$OUT/$MODNAME-dmesg.txt"; then
  echo "CAPTURE VERIFIED: $MODNAME present in the boot log"
else
  echo "CAPTURE MISS: $MODNAME absent from the boot log - the module did not load in this boot"
fi
echo "captured $OUT/$MODNAME-dmesg.txt"

heal
if verify_health; then echo "EXP FULL CYCLE: PASS module=$MODNAME"; else echo "EXP FULL CYCLE: FAIL module=$MODNAME (recovery unverified)"; fi
echo "=== run-exp-detached end $(date -Iseconds) ==="
