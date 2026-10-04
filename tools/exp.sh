#!/usr/bin/env bash
# exp.sh - one-shot device experiment harness for the hi5622v100 bring-up work.
#
#   tools/exp.sh <module.ko> [module params]
#   tools/exp.sh --dry-run <module.ko> [module params]
#
# One invocation does the whole manual cycle:
#   1. arm the DEVICE-side self-recovery FIRST (mandatory, before any staging)
#   2. hide hi5622v100_{wifi,plat}.ko as .omo-off, stage the module, install a
#      one-shot /etc/init.d loader that self-deletes
#   3. reboot and wait for SSH (bounded poll, no fixed sleeps)
#   4. capture dmesg, lsmod, /proc/interrupts, the module's log lines and any
#      files it wrote into build/register-dumps/exp/<timestamp>/
#   5. cancel the watchdog, restore both vendor modules, remove the loader and
#      the staged module, rmmod, reboot
#   6. verify health (2 wiphys, 6 interfaces, calibration [SUCC], 0 .omo-off)
#   7. print one PASS/FAIL line and the evidence path
#
# It fails SAFE: a failure in any step still runs the recovery and reports it.
#
# 2026-10-02 - built for the phase-22 experiment-harness task (st_01a0fbe0).
# The recipe is transcribed from docs/phase21/sr-trigger.md (Part B) and
# docs/phase15/unload-patch.md (section 0/5).  The router is NOT touched by
# --dry-run.
#
# This file is also sourceable: batch.sh sources it and reuses exp_run().
# Env knobs (all optional): EXP_WATCH EXP_BOOT_TIMEOUT EXP_RUN_TIMEOUT EXP_POLL
#   EXP_KVER EXP_EVID_SUFFIX EXP_EXTRA_STAGE EXP_EXTRA_PULL EXP_DONE_CMD
#   EXP_CAPTURE_CMD EXP_RESULT_LABEL
set -uo pipefail

EXP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXP_ROOT="$(cd "$EXP_DIR/.." && pwd)"
EXP_RSH="$EXP_ROOT/.sshwrap/rsh.sh"
EXP_RSCP="$EXP_ROOT/.sshwrap/rscp.sh"
EXP_HOST="root@192.168.10.1"

: "${EXP_WATCH:=1800}"                 # device watchdog window (s)
: "${EXP_BOOT_TIMEOUT:=300}"           # wait for a fresh SSH after a reboot (s)
: "${EXP_RUN_TIMEOUT:=180}"            # wait for the module's done marker (s)
: "${EXP_HEALTH_TIMEOUT:=180}"         # wait for the recovered vendor stack to come up (s)
: "${EXP_POLL:=3}"                     # poll interval between probes (s)
: "${EXP_KVER:=5.10.201}"
: "${EXP_EVID_SUFFIX:=}"
: "${EXP_EXTRA_STAGE:=}"               # newline list of "local:remote" files to stage
: "${EXP_EXTRA_PULL:=}"                # newline list of remote paths to pull
: "${EXP_DONE_CMD:=dmesg | grep -q ': done ('}"  # remote test: experiment finished
# NOTE: the pattern is ': done (' not 'done (' - the device's S95 init script
# logs 'S95done (5809): drop_caches: 3' at boot, which the loose pattern
# matched, so exp.sh captured and recovered before the S99 loader even ran
# (found on the first real BOOT B run 2026-10-02).
: "${EXP_CAPTURE_CMD:=}"                   # optional remote cmd run after the done
#   marker and before the capture step; stdout+stderr land in capture-cmd.txt.
#   Empty (default) = no hook. A non-zero exit records a FAILURE but is
#   non-fatal: exp.sh still captures, recovers and reports FAIL.
: "${EXP_RESULT_LABEL:=EXP}"

EXP_RECOVER_SCRIPT="/root/recover-exp.sh"
EXP_DONE_FLAG="/tmp/omo-exp.done"
EXP_PIDFILE="/tmp/omo-exp.timer.pid"
EXP_TIMER_LOG="/tmp/omo-exp.timer.log"
EXP_CAPTURE_TAR="/tmp/omo-exp-capture.tar.gz"

DRY=0
MODULE=""
PARAMS=""
MODBASE=""
MODNAME=""
TS=""
EVID=""
FAILURE=""
RECOVERY_ARMED=0
RECOVERY_STATUS="not-needed"
HEALTH_OK=0
HEALTH_SUMMARY=""
EXP_PREFLIGHT_ERR=""

# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------
exp_usage() {
	cat <<'EOF'
usage: exp.sh [--dry-run] <module.ko> [module params]

  <module.ko>      staged into /lib/modules/<kver>/ and insmod'd by a one-shot
                   boot loader; the two vendor hi5622v100 modules are hidden
                   as .omo-off for the duration of the experiment boot.
  [module params]  space-separated key=value words passed verbatim to insmod.

  --dry-run        print the full ordered command sequence and exit without
                   touching the device (no ssh, no scp, no reboot).
EOF
}

exp_hr()   { printf '\n== %s ==\n' "$1"; }
exp_note() { printf '# %s\n' "$1"; }

# print the exact scp/ssh shape a real run uses; a real run executes it.
exp_put() { # local remote
	if [ "$DRY" = 1 ]; then
		printf '$ scp -O %s %s:%s\n' "$1" "$EXP_HOST" "$2"
	else
		"$EXP_RSCP" "$1" "$EXP_HOST:$2"
	fi
}
exp_get() { # remote local
	if [ "$DRY" = 1 ]; then
		printf '$ scp -O %s:%s %s\n' "$EXP_HOST" "$1" "$2"
	else
		"$EXP_RSCP" "$EXP_HOST:$1" "$2"
	fi
}
exp_remote() { # note script
	if [ "$DRY" = 1 ]; then
		printf '\n# %s\n$ ssh %s <<'"'"'EOS'"'"'\n' "$1" "$EXP_HOST"
		printf '%s\n' "$2"
		printf 'EOS\n'
	else
		printf -- '-- %s\n' "$1"
		"$EXP_RSH" "$2"
	fi
}

exp_fail() { # step reason
	FAILURE="${FAILURE:+$FAILURE; }$1: $2"
	printf '!! FAIL [%s] %s\n' "$1" "$2" >&2
}

# --------------------------------------------------------------------------
# device-side scripts (same text used to build, print and install)
# --------------------------------------------------------------------------
exp_recover_body() {
	sed -e "s|__MOD__|$MODBASE|g" -e "s|__MODNAME__|$MODNAME|g" \
	    -e "s|__DONE_FLAG__|$EXP_DONE_FLAG|g" \
	    -e "s|__TIMER_LOG__|$EXP_TIMER_LOG|g" \
	    -e "s|__CAPTURE_TAR__|$EXP_CAPTURE_TAR|g" <<'EOF'
#!/bin/sh
# device-side self-recovery for the omo experiment harness (tools/exp.sh).
#   recover-exp.sh          restore the vendor stack and reboot now
#   recover-exp.sh --watch  detached watchdog: wait WATCH s, then recover
#                           unless the done flag has been posted
# Armed with start-stop-daemon BEFORE anything is staged; cancelled by
# touching the done flag and running this script by hand.
MOD=__MOD__            # staged module basename
MODNAME=__MODNAME__    # staged module name (no .ko)
WATCH="${WATCH:-1800}"
DONE=__DONE_FLAG__
LOG=__TIMER_LOG__
if [ "$1" = "--watch" ]; then
	echo "watchdog armed $(date -u) pid=$$ wait=${WATCH}s" > "$LOG"
	sleep "$WATCH"
	if [ -f "$DONE" ]; then
		echo "watchdog cancelled: done flag present $(date -u)" >> "$LOG"
		exit 0
	fi
	echo "watchdog FIRING: no done flag, recovering $(date -u)" >> "$LOG"
fi
KVER=$(uname -r)
cd "/lib/modules/$KVER" 2>/dev/null
[ -f hi5622v100_wifi.ko.omo-off ] && mv -f hi5622v100_wifi.ko.omo-off hi5622v100_wifi.ko
[ -f hi5622v100_plat.ko.omo-off ] && mv -f hi5622v100_plat.ko.omo-off hi5622v100_plat.ko
rm -f "/etc/rc.d/S99omo-$MODNAME"
rm -f "/etc/init.d/omo-$MODNAME"
rmmod "$MODNAME" 2>/dev/null
rm -f "/lib/modules/$KVER/$MOD"
rm -f "/tmp/$MOD"
# batch.sh stages its hypothesis list on the persistent overlay; remove it too
rm -f /root/omo-batch-list
rm -rf /root/omo-batch
rm -f __CAPTURE_TAR__
rm -f "$DONE" "$LOG"
rm -f /root/recover-exp.sh
sync
reboot
EOF
}

exp_loader_body() {
	sed -e "s|__MOD__|$MODBASE|g" -e "s|__MODNAME__|$MODNAME|g" \
	    -e "s|__PARAMS__|$PARAMS|g" <<'EOF'
#!/bin/sh /etc/rc.common
# One-shot boot loader installed by tools/exp.sh. It self-deletes, re-arms the
# device-side watchdog inside this boot, then insmods the staged module once.
START=99
start() {
	rm -f "/etc/rc.d/S99omo-__MODNAME__"
	if [ -f /root/recover-exp.sh ]; then
		start-stop-daemon -S -b -m -p /tmp/omo-exp.timer.pid \
			-x /bin/sh -- /root/recover-exp.sh --watch
	fi
	insmod "/lib/modules/$(uname -r)/__MOD__" __PARAMS__
}
EOF
}

exp_health_body() {
	sed -e "s|__MODNAME__|$MODNAME|g" <<'EOF'
K=$(uname -r)
MODS=$(lsmod)
echo "WIFI=$(printf '%s\n' "$MODS" | grep -c '^hi5622v100_wifi ')"
echo "PLAT=$(printf '%s\n' "$MODS" | grep -c '^hi5622v100_plat ')"
echo "WIPHY=$(iw phy 2>/dev/null | grep -c '^Wiphy')"
echo "IFACE=$(iw dev 2>/dev/null | grep -c 'Interface')"
CAL=$(iwpriv vap0 alg get_2g_power_param 2>/dev/null)
echo "CAL_SUCC=$(printf '%s' "$CAL" | grep -c '\[SUCC\]')"
echo "OMO_OFF=$(ls /lib/modules/$K/*.omo-off 2>/dev/null | wc -l)"
echo "STAGED=$(ls /lib/modules/$K/__MODNAME__.ko 2>/dev/null | wc -l)"
echo "LOADER=$(ls /etc/init.d/omo-__MODNAME__ /etc/rc.d/S99omo-__MODNAME__ 2>/dev/null | wc -l)"
echo "RECOVER=$(ls /root/recover-exp.sh 2>/dev/null | wc -l)"
EOF
}

# --------------------------------------------------------------------------
# steps
# --------------------------------------------------------------------------
exp_preflight() {
	EXP_PREFLIGHT_ERR=""
	[ -f "$MODULE" ] || { EXP_PREFLIGHT_ERR="module not found: $MODULE"; return 1; }
	command -v md5sum >/dev/null || { EXP_PREFLIGHT_ERR="md5sum not on PATH"; return 1; }
	return 0
}

exp_arm_recovery() {
	local body
	body="$(exp_recover_body)"
	local lmd5
	lmd5="$(md5sum "$0" 2>/dev/null | awk '{print $1}')"
	if [ "$DRY" = 1 ]; then
		exp_hr "1/7 arm DEVICE-side self-recovery (MANDATORY, before any staging)"
		exp_note "cancels via the done flag $EXP_DONE_FLAG; reboots on expiry"
		printf '$ cat > /tmp/recover-exp.sh <<'"'"'OMO_RECOVER'"'"'\n'
		printf '%s\n' "$body" | sed 's/^/  /'
		printf 'OMO_RECOVER\n'
		exp_put "/tmp/recover-exp.sh" "$EXP_RECOVER_SCRIPT"
		exp_remote "chmod + syntax-check + start the watchdog detached" \
"chmod 755 $EXP_RECOVER_SCRIPT
sh -n $EXP_RECOVER_SCRIPT && echo RECOVER_SYNTAX_OK
start-stop-daemon -S -b -m -p $EXP_PIDFILE -x /bin/sh -- $EXP_RECOVER_SCRIPT --watch
sleep 1
cat $EXP_TIMER_LOG
kill -0 \$(cat $EXP_PIDFILE) 2>/dev/null && echo WATCHDOG_ALIVE"
		RECOVERY_ARMED=1
		return 0
	fi
	printf -- '-- [1/7] arm device-side self-recovery (mandatory)\n'
	printf '%s\n' "$body" > /tmp/recover-exp.sh || return 1
	"$EXP_RSCP" /tmp/recover-exp.sh "$EXP_HOST:$EXP_RECOVER_SCRIPT" || return 1
	"$EXP_RSH" "chmod 755 $EXP_RECOVER_SCRIPT
sh -n $EXP_RECOVER_SCRIPT" >/dev/null || return 1
	"$EXP_RSH" "start-stop-daemon -S -b -m -p $EXP_PIDFILE -x /bin/sh -- $EXP_RECOVER_SCRIPT --watch
sleep 1
cat $EXP_TIMER_LOG
kill -0 \$(cat $EXP_PIDFILE) 2>/dev/null && echo WATCHDOG_ALIVE" | grep -q WATCHDOG_ALIVE || return 1
	RECOVERY_ARMED=1
	return 0
}

exp_stage() {
	local loader
	loader="$(exp_loader_body)"
	local lmd5 rmd5
	lmd5="$(md5sum "$MODULE" 2>/dev/null | awk '{print $1}')"
	if [ "$DRY" = 1 ]; then
		exp_hr "2/7 stage the module (vendor modules hidden as .omo-off)"
		exp_note "local md5 of $MODULE = ${lmd5:-<not present; md5-checked on a real run>}"
		exp_put "$MODULE" "/tmp/$MODBASE"
		exp_remote "push to the boot path and hide the two vendor modules" \
"L=$lmd5; K=\$(uname -r); cd /lib/modules/\$K || exit 1
R=\$(md5sum /tmp/$MODBASE | cut -d' ' -f1)
[ \"\$R\" = \"\$L\" ] || { echo MD5_MISMATCH local=\$L device=\$R; exit 1; }
[ -f hi5622v100_wifi.ko ] && mv -f hi5622v100_wifi.ko hi5622v100_wifi.ko.omo-off
[ -f hi5622v100_plat.ko ] && mv -f hi5622v100_plat.ko hi5622v100_plat.ko.omo-off
cp /tmp/$MODBASE /lib/modules/\$K/$MODBASE
sync
echo STAGED; md5sum /lib/modules/\$K/$MODBASE; ls -l /lib/modules/\$K/*.omo-off"
		local line
		while IFS= read -r line; do
			[ -n "$line" ] || continue
			exp_note "extra stage: $line"
			exp_remote "ensure the remote directory exists" "mkdir -p \"\$(dirname '${line#*:}')\""
			exp_put "${line%%:*}" "${line#*:}"
		done <<< "$EXP_EXTRA_STAGE"
		exp_note "one-shot loader: /etc/init.d/omo-$MODNAME -> /etc/rc.d/S99omo-$MODNAME"
		exp_remote "install the loader and its boot symlink" \
"cat > /etc/init.d/omo-$MODNAME <<'OMO_LOADER'
$loader
OMO_LOADER
chmod 755 /etc/init.d/omo-$MODNAME
ln -sf ../init.d/omo-$MODNAME /etc/rc.d/S99omo-$MODNAME
sh -n /etc/init.d/omo-$MODNAME && echo LOADER_SYNTAX_OK
ls -l /etc/init.d/omo-$MODNAME /etc/rc.d/S99omo-$MODNAME"
		return 0
	fi
	printf -- '-- [2/7] stage the module\n'
	"$EXP_RSCP" "$MODULE" "$EXP_HOST:/tmp/$MODBASE" || return 1
	local remote_md5
	remote_md5="$("$EXP_RSH" "md5sum /tmp/$MODBASE" | awk '{print $1}')"
	[ "$remote_md5" = "$lmd5" ] || { exp_fail "stage" "md5 mismatch local=$lmd5 device=$remote_md5"; return 1; }
	"$EXP_RSH" "K=\$(uname -r); cd /lib/modules/\$K || exit 1
[ -f hi5622v100_wifi.ko ] && mv -f hi5622v100_wifi.ko hi5622v100_wifi.ko.omo-off
[ -f hi5622v100_plat.ko ] && mv -f hi5622v100_plat.ko hi5622v100_plat.ko.omo-off
cp /tmp/$MODBASE /lib/modules/\$K/$MODBASE
sync" || return 1
	local line
	while IFS= read -r line; do
		[ -n "$line" ] || continue
		local src="${line%%:*}" dst="${line#*:}"
		"$EXP_RSH" "mkdir -p \"\$(dirname '$dst')\"" >/dev/null 2>&1
		"$EXP_RSCP" "$src" "$EXP_HOST:$dst" || return 1
	done <<< "$EXP_EXTRA_STAGE"
	"$EXP_RSH" "cat > /etc/init.d/omo-$MODNAME <<'OMO_LOADER'
$loader
OMO_LOADER
chmod 755 /etc/init.d/omo-$MODNAME
ln -sf ../init.d/omo-$MODNAME /etc/rc.d/S99omo-$MODNAME
sh -n /etc/init.d/omo-$MODNAME" || return 1
	return 0
}

exp_reboot_wait() {
	if [ "$DRY" = 1 ]; then
		exp_hr "3/7 reboot and wait for SSH (bounded poll, no fixed sleeps)"
		exp_remote "reboot into the takeover boot" "sync; reboot"
		exp_note "poll every ${EXP_POLL}s, deadline ${EXP_BOOT_TIMEOUT}s, until a FRESH boot answers"
		exp_remote "fresh-boot probe" "u=\$(cut -d. -f1 /proc/uptime); [ \"\$u\" -lt 180 ] && echo FRESH_BOOT uptime=\$u"
		return 0
	fi
	printf -- '-- [3/7] reboot and wait for SSH\n'
	"$EXP_RSH" 'sync; reboot' >/dev/null 2>&1 || true
	local deadline up
	deadline=$(( $(date +%s) + EXP_BOOT_TIMEOUT ))
	while [ "$(date +%s)" -lt "$deadline" ]; do
		up="$("$EXP_RSH" 'cut -d. -f1 /proc/uptime' 2>/dev/null)"
		if [ -n "$up" ] && [ "$up" -lt 180 ] 2>/dev/null; then
			printf '  device back: uptime=%ss\n' "$up"
			return 0
		fi
		sleep "$EXP_POLL"
	done
	return 1
}

exp_wait_done() {
	if [ "$DRY" = 1 ]; then
		exp_hr "4/7 wait for the experiment's completion marker"
		exp_note "poll every ${EXP_POLL}s, deadline ${EXP_RUN_TIMEOUT}s"
		exp_remote "module loaded + experiment done" \
"lsmod | grep -q '^$MODNAME ' && echo MODULE_LOADED
$EXP_DONE_CMD && echo EXP_DONE"
		return 0
	fi
	printf -- '-- [4/7] wait for the completion marker\n'
	local deadline
	deadline=$(( $(date +%s) + EXP_RUN_TIMEOUT ))
	while [ "$(date +%s)" -lt "$deadline" ]; do
		# Require BOTH the staged module loaded AND its done marker: a bare
		# done-pattern can match a boot message before the S99 loader runs.
		if "$EXP_RSH" "lsmod | grep -q '^$MODNAME ' && { $EXP_DONE_CMD; }" >/dev/null 2>&1; then
			printf '  completion marker seen\n'
			return 0
		fi
		sleep "$EXP_POLL"
	done
	return 1
}

exp_capture() {
	local dir="$EVID"
	local plist="/tmp/omo-$MODNAME"
	local x
	while IFS= read -r x; do
		[ -n "$x" ] && plist="$plist $x"
	done <<< "$EXP_EXTRA_PULL"
	if [ "$DRY" = 1 ]; then
		exp_hr "5/7 capture the evidence"
		printf '$ mkdir -p %s\n' "$dir"
		if [ -n "$EXP_CAPTURE_CMD" ]; then
			exp_note "EXP_CAPTURE_CMD (after done-check, before capture): $EXP_CAPTURE_CMD"
			exp_remote "capture hook (EXP_CAPTURE_CMD)" \
"{ $EXP_CAPTURE_CMD ; } 2>&1"
			# the redirect below is executed LOCALLY and writes the evidence file
			printf '$ ssh %s <<EOS ... > %s/capture-cmd.txt\n' "$EXP_HOST" "$dir"
		fi
		exp_remote "capture dmesg"        "dmesg > $dir/dmesg.txt"
		exp_remote "capture lsmod"        "lsmod > $dir/lsmod.txt"
		exp_remote "capture interrupts"   "cat /proc/interrupts > $dir/interrupts.txt"
		exp_remote "capture module log"   "dmesg | grep -i -- '$MODNAME' > $dir/module-log.txt"
		exp_remote "bundle module-written files" \
"cd /; tar -czf $EXP_CAPTURE_TAR \$(for p in $plist; do [ -e \"\$p\" ] && printf '%s ' \"\$p\"; done) 2>/dev/null
ls -l $EXP_CAPTURE_TAR"
		exp_get "$EXP_CAPTURE_TAR" "$dir/"
		printf '$ tar -xzf %s/%s -C %s\n' "$dir" "$(basename "$EXP_CAPTURE_TAR")" "$dir"
		printf '$ ( cd %s && tar --exclude=./evidence.tar.gz -czf evidence.tar.gz . )\n' "$dir"
		exp_note "evidence dir: $dir   (raw files + evidence.tar.gz)"
		return 0
	fi
	printf -- '-- [5/7] capture the evidence\n'
	mkdir -p "$dir" || return 1
	if [ -n "$EXP_CAPTURE_CMD" ]; then
		printf -- '-- capture hook (EXP_CAPTURE_CMD)\n'
		if "$EXP_RSH" "{ $EXP_CAPTURE_CMD ; } 2>&1" > "$dir/capture-cmd.txt"; then
			printf '  capture hook: ok -> %s/capture-cmd.txt\n' "$dir"
		else
			exp_fail "capture-hook" "EXP_CAPTURE_CMD exited non-zero (see $dir/capture-cmd.txt)"
		fi
	fi
	"$EXP_RSH" 'dmesg'                  > "$dir/dmesg.txt" 2>/dev/null
	"$EXP_RSH" 'lsmod'                  > "$dir/lsmod.txt" 2>/dev/null
	"$EXP_RSH" 'cat /proc/interrupts'   > "$dir/interrupts.txt" 2>/dev/null
	"$EXP_RSH" 'cat /proc/uptime'       > "$dir/uptime.txt" 2>/dev/null
	"$EXP_RSH" "dmesg | grep -i -- '$MODNAME'" > "$dir/module-log.txt" 2>/dev/null
	"$EXP_RSH" "cd /; tar -czf $EXP_CAPTURE_TAR \$(for p in $plist; do [ -e \"\$p\" ] && printf '%s ' \"\$p\"; done) 2>/dev/null; ls -l $EXP_CAPTURE_TAR" > "$dir/device-tar.txt" 2>&1
	"$EXP_RSCP" "$EXP_HOST:$EXP_CAPTURE_TAR" "$dir/" >/dev/null 2>&1 || true
	if [ -f "$dir/$(basename "$EXP_CAPTURE_TAR")" ]; then
		tar -xzf "$dir/$(basename "$EXP_CAPTURE_TAR")" -C "$dir" 2>/dev/null || true
	fi
	( cd "$dir" && tar --exclude='./evidence.tar.gz' -czf evidence.tar.gz . ) 2>/dev/null || true
	printf '  evidence: %s\n' "$dir"
	return 0
}

exp_recover() {
	if [ "$DRY" = 1 ]; then
		exp_hr "6/7 recover (cancel the watchdog, restore, reboot)"
		exp_remote "cancel the watchdog and run the recovery by hand" \
"touch $EXP_DONE_FLAG
$EXP_RECOVER_SCRIPT"
		exp_note "recovery restores both .omo-off modules, removes the loader,"
		exp_note "the rc.d symlink, the staged module, rmmods it, then reboots"
		return 0
	fi
	printf -- '-- [6/7] recover\n'
	if [ "$RECOVERY_ARMED" = 1 ]; then
		"$EXP_RSH" "touch $EXP_DONE_FLAG" >/dev/null 2>&1 || true
		"$EXP_RSH" "$EXP_RECOVER_SCRIPT" >/dev/null 2>&1 || true
	fi
	local deadline up
	deadline=$(( $(date +%s) + EXP_BOOT_TIMEOUT ))
	while [ "$(date +%s)" -lt "$deadline" ]; do
		up="$("$EXP_RSH" 'cut -d. -f1 /proc/uptime' 2>/dev/null)"
		if [ -n "$up" ] && [ "$up" -lt 180 ] 2>/dev/null; then
			RECOVERY_STATUS="ran"
			return 0
		fi
		sleep "$EXP_POLL"
	done
	RECOVERY_STATUS="FAILED to return"
	return 1
}

exp_verify_health() {
	local body out
	body="$(exp_health_body)"
	if [ "$DRY" = 1 ]; then
		exp_hr "7/7 verify health on the recovered boot"
		exp_remote "health probe" "$body"
		exp_note "PASS requires WIPHY=2, IFACE=6, CAL_SUCC=1, OMO_OFF=0, STAGED=0, LOADER=0"
		HEALTH_OK=1
		HEALTH_SUMMARY="wiphy=2/2 iface=6/6 cal=[SUCC] omo_off=0 staged=0 loader=0"
		return 0
	fi
	printf -- '-- [7/7] verify health\n'
	local wiphy iface cal_succ omo_off staged loader out deadline
	# The recovered boot answers SSH before the vendor hi5622v100 modules have
	# loaded and calibrated (~20-30 s), so probe bounded-retry until the stack
	# is up rather than sampling once and calling it a failure (found on the
	# first real batch run 2026-10-02).
	deadline=$(( $(date +%s) + EXP_HEALTH_TIMEOUT ))
	while :; do
		out="$("$EXP_RSH" "$body" 2>/dev/null)"
		wiphy="$(printf '%s\n' "$out" | sed -n 's/^WIPHY=//p')"
		iface="$(printf '%s\n' "$out" | sed -n 's/^IFACE=//p')"
		cal_succ="$(printf '%s\n' "$out" | sed -n 's/^CAL_SUCC=//p')"
		omo_off="$(printf '%s\n' "$out" | sed -n 's/^OMO_OFF=//p')"
		staged="$(printf '%s\n' "$out" | sed -n 's/^STAGED=//p')"
		loader="$(printf '%s\n' "$out" | sed -n 's/^LOADER=//p')"
		if [ "${wiphy:-0}" -eq 2 ] && [ "${iface:-0}" -eq 6 ] && \
		   [ "${cal_succ:-0}" -eq 1 ] && [ "${omo_off:-9}" -eq 0 ] && \
		   [ "${staged:-9}" -eq 0 ] && [ "${loader:-9}" -eq 0 ]; then
			break
		fi
		[ "$(date +%s)" -lt "$deadline" ] || break
		sleep 5
	done
	printf '%s\n' "$out" > "${EVID:-/tmp}/health.txt" 2>/dev/null || true
	HEALTH_SUMMARY="wiphy=${wiphy:-?}/2 iface=${iface:-?}/6 cal_succ=${cal_succ:-?} omo_off=${omo_off:-?} staged=${staged:-?} loader=${loader:-?}"
	HEALTH_OK=1
	[ "${wiphy:-0}" -eq 2 ]     || HEALTH_OK=0
	[ "${iface:-0}" -eq 6 ]     || HEALTH_OK=0
	[ "${cal_succ:-0}" -eq 1 ]  || HEALTH_OK=0
	[ "${omo_off:-9}" -eq 0 ]   || HEALTH_OK=0
	[ "${staged:-9}" -eq 0 ]    || HEALTH_OK=0
	[ "${loader:-9}" -eq 0 ]    || HEALTH_OK=0
	printf '  %s\n' "$HEALTH_SUMMARY"
	return 0
}

exp_summary() {
	local verdict=PASS reason=""
	[ -n "$FAILURE" ] && { verdict=FAIL; reason="$FAILURE"; }
	if [ "$HEALTH_OK" != 1 ]; then
		verdict=FAIL
		reason="${reason:+$reason; }post-recovery health check failed"
	fi
	if [ "$DRY" = 1 ]; then
		exp_hr "summary line printed by a real run"
		printf '%s RESULT: %s module=%s params=[%s] evidence=<evidence-dir>/\n' \
			"$EXP_RESULT_LABEL" PASS "$MODNAME" "$PARAMS"
		printf '# on failure instead:\n'
		printf '%s RESULT: FAIL module=%s reason=<step: reason> evidence=<evidence-dir>/\n' \
			"$EXP_RESULT_LABEL" "$MODNAME"
		return 0
	fi
	printf '\n'
	printf '%s RESULT: %s module=%s params=[%s] evidence=%s/\n' \
		"$EXP_RESULT_LABEL" "$verdict" "$MODNAME" "$PARAMS" "$EVID"
	if [ "$verdict" = FAIL ]; then
		printf '  reason   : %s\n' "$reason"
		printf '  recovery : %s\n' "$RECOVERY_STATUS"
		printf '  health   : %s\n' "$HEALTH_SUMMARY"
	fi
	[ "$verdict" = PASS ]
}

exp_plan() {
	exp_arm_recovery
	exp_stage
	exp_reboot_wait
	exp_wait_done
	exp_capture
	exp_recover
	exp_verify_health
	exp_summary
}

exp_run() {
	if [ "$DRY" = 1 ]; then
		TS="<TS>"
		EVID="$EXP_ROOT/build/register-dumps/exp/$TS$EXP_EVID_SUFFIX"
		exp_plan
		return 0
	fi
	TS="$(date -u +%Y%m%d-%H%M%S)"
	EVID="$EXP_ROOT/build/register-dumps/exp/$TS$EXP_EVID_SUFFIX"
	if ! exp_preflight; then
		FAILURE="preflight: $EXP_PREFLIGHT_ERR"
		exp_summary
		return 1
	fi
	if exp_arm_recovery; then
		if exp_stage; then
			if exp_reboot_wait && exp_wait_done; then
				exp_capture || exp_fail "capture" "evidence capture failed"
			else
				exp_fail "run" "device did not return fresh or experiment never finished"
			fi
		else
			exp_fail "stage" "staging failed"
		fi
	else
		exp_fail "recovery" "device-side self-recovery failed to arm - no staging done"
	fi
	exp_recover
	exp_verify_health
	exp_summary
}

exp_main() {
	local -a args=()
	while [ $# -gt 0 ]; do
		case "$1" in
			--dry-run) DRY=1 ;;
			-h|--help) exp_usage; return 0 ;;
			*) args+=("$1") ;;
		esac
		shift
	done
	if [ "${#args[@]}" -lt 1 ]; then
		exp_usage
		return 2
	fi
	MODULE="${args[0]}"
	PARAMS="${args[*]:1}"
	MODBASE="$(basename "$MODULE")"
	MODNAME="${MODBASE%.ko}"
	case "$MODNAME" in
		*[!A-Za-z0-9._-]*|'') echo "exp.sh: bad module name: $MODNAME" >&2; return 2 ;;
	esac
	local p
	for p in $PARAMS; do
		case "$p" in
			*[!A-Za-z0-9_./:=,+@-]*) echo "exp.sh: refusing unsafe module param: $p" >&2; return 2 ;;
		esac
	done
	if [ "$DRY" = 1 ]; then
		printf '== exp.sh DRY RUN ==\n'
		printf 'module    : %s\n' "$MODULE"
		printf 'module id : %s (staged as /lib/modules/%s/%s)\n' "$MODNAME" "$EXP_KVER" "$MODBASE"
		printf 'params    : [%s]\n' "$PARAMS"
		printf 'evidence  : %s/build/register-dumps/exp/<TS>%s/\n' "$EXP_ROOT" "$EXP_EVID_SUFFIX"
		printf 'host      : %s (via .sshwrap/rsh.sh, .sshwrap/rscp.sh)\n' "$EXP_HOST"
		printf 'watchdog  : WATCH=%ss, boot timeout=%ss, run timeout=%ss, poll=%ss\n' \
			"$EXP_WATCH" "$EXP_BOOT_TIMEOUT" "$EXP_RUN_TIMEOUT" "$EXP_POLL"
		printf '# NOTHING BELOW IS EXECUTED IN --dry-run.  ssh/scp shape is exact.\n'
	fi
	exp_run
}

# sourceable: only run main when executed directly
if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
	exp_main "$@"
	exit $?
fi
