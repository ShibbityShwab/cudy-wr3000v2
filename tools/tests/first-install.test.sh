#!/usr/bin/env bash
# first-install.test.sh - host-side mocked tests for tools/first-install-stock.sh.
#
# STATUS: host-only. No router, UART, TFTP, flash or bench tool is touched. Every
# device interaction goes through fake rsh/rscp helpers that resolve the tool's
# stdin-fed device script against a fixture tree (fake /proc/mtd, fake mtd devices,
# fake /sys, a synthetic sysupgrade container, shims for the mutating tools).
#
# WHAT IS EXERCISED
#   - default read-only inspection (no write, no flash tool call) and dry-run;
#   - the attended/recovery/image gates (refusal BEFORE any device contact);
#   - pair selection in both directions: A active -> writes B, B active -> writes A;
#   - write order: kernel (mtd erase + write) BEFORE rootfs (ubiformat) BEFORE the
#     selector move; active pair / rootfs_data / upgrade / env devices untouched;
#   - size checks on the image members and on the /proc/mtd slot sizes;
#   - image container refusals (tampered manifest/sha, wrong board, oversize kernel,
#     external check tool refusal) before any device access;
#   - device-state refusals (not stock, already customised, selector/booted-pair
#     mismatch, manual/opposite boot_reg, wrong --expect-active, too little /tmp);
#   - read-back failures (kernel corruption, rootfs corruption, bad block) -> abort
#     safely, selector untouched, recovery plan printed, no reboot;
#   - selector handling: A->0x11, B->0x10, env bytes NEVER written, read-back
#     verified, manual 0x21 refused, missing sysenv interface refused;
#   - reboot classification: stock fallback, no reboot detected, unverified/no
#     return; no flash write happens without the explicit attended flags.
#
# USAGE:
#   bash tools/tests/first-install.test.sh [--keep] [--real-container PATH]
#
#   --keep            keep the fixture tree for inspection
#   --real-container  additionally run the real luofu-image.py check on a built
#                     sysupgrade container (host-built artifact; optional)
#
# EXIT: 0 all assertions pass, 1 at least one failed.

set -u

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
REPO=$(cd "$SCRIPT_DIR/../.." && pwd)
TOOL="$REPO/tools/first-install-stock.sh"
TMP=$(mktemp -d "${TMPDIR:-/tmp}/first-install-test.XXXXXX") || exit 1
KEEP=0
REAL_CONTAINER=""

while [ $# -gt 0 ]; do
	case "$1" in
	--keep) KEEP=1 ;;
	--real-container) REAL_CONTAINER=${2:-}; shift ;;
	-h|--help) sed -n '2,38p' "$0"; exit 0 ;;
	*) echo "unknown argument: $1" >&2; exit 2 ;;
	esac
	shift
done

[ -f "$TOOL" ] || { echo "missing tool: $TOOL" >&2; exit 2; }

PASS=0
FAIL=0
CASE=""
OUT=""
ERR=""
RC=0

cleanup() {
	if [ "$KEEP" -eq 1 ]; then
		echo "fixtures kept in $TMP" >&2
	else
		rm -rf "$TMP"
	fi
}
trap cleanup EXIT

ok() { PASS=$((PASS + 1)); printf 'ok %d - %s\n' "$PASS" "$*"; }
not_ok() { FAIL=$((FAIL + 1)); printf 'not ok %d - %s\n' "$FAIL" "$*"; }
note() { printf '  # %s\n' "$*"; }

assert_rc() { # <want> <desc>
	if [ "$RC" = "$1" ]; then ok "$2 (rc=$RC)"; else not_ok "$2 (rc=$RC, want $1)"; sed -n '1,25p' "$OUT" | sed 's/^/    /'; sed -n '1,12p' "$ERR" | sed 's/^/    /'; fi
}
assert_out() { # <fixed string> <desc>
	if grep -qF -- "$1" "$OUT"; then ok "$2"; else not_ok "$2 (not found: [$1])"; sed -n '1,30p' "$OUT" | sed 's/^/    /'; fi
}
assert_err() { # <fixed string> <desc>
	if grep -qF -- "$1" "$ERR"; then ok "$2"; else not_ok "$2 (not found in stderr: [$1])"; sed -n '1,20p' "$ERR" | sed 's/^/    /'; fi
}
assert_file() { # <path> <expected> <desc>
	local got
	got=$(cat "$1" 2>/dev/null)
	if [ "$got" = "$2" ]; then ok "$3"; else not_ok "$3 (file $1 = [$got], want [$2])"; fi
}
assert_sha() { # <path> <sha> <desc>
	local got
	got=$(sha256sum "$1" | cut -d' ' -f1)
	if [ "$got" = "$2" ]; then ok "$3"; else not_ok "$3 (sha $got, want $2)"; fi
}
assert_cmdlog() { # <fixed string> <desc>
	if grep -qF -- "$1" "$CASE/cmdlog" 2>/dev/null; then ok "$2"; else not_ok "$2 (not in cmdlog: [$1])"; fi
}
assert_no_cmdlog_re() { # <basic regex> <desc>
	if grep -Eq -- "$1" "$CASE/cmdlog" 2>/dev/null; then
		not_ok "$2 (matched [$1])"; grep -E -- "$1" "$CASE/cmdlog" | sed 's/^/    /'
	else
		ok "$2"
	fi
}
assert_before() { # <fixed earlier> <fixed later> <desc>
	local a b
	a=$(grep -nF -- "$1" "$CASE/cmdlog" 2>/dev/null | head -1 | cut -d: -f1)
	b=$(grep -nF -- "$2" "$CASE/cmdlog" 2>/dev/null | head -1 | cut -d: -f1)
	if [ -n "$a" ] && [ -n "$b" ] && [ "$a" -lt "$b" ]; then
		ok "$3"
	else
		not_ok "$3 (earlier=[$1] line ${a:-none}, later=[$2] line ${b:-none})"
	fi
}

# ---------------------------------------------------------------------------
# fixture construction
# ---------------------------------------------------------------------------
write_shims() {
	mkdir -p "$CASE/bin"
	cat >"$CASE/bin/mtd" <<'SHIM'
#!/bin/sh
R=${FI_ROOT:?}
echo "mtd $*" >>"$R/.cmdlog"
cmd=$1; shift
devpath() {
	awk -v want="\"$1\"" '
		$1 ~ /^mtd[0-9]+:$/ {
			name = $4
			for (i = 5; i <= NF; i++) name = name " " $i
			if (name == want) { print substr($1, 1, length($1) - 1); found++ }
		}
		END { exit(found == 1 ? 0 : 1) }
	' "$R/proc/mtd"
}
case "$cmd" in
erase)
	dev=$(devpath "$1") || exit 1
	entry=$(awk -v n="$dev:" '$1 == n { print $2 }' "$R/proc/mtd")
	[ -n "$entry" ] || exit 1
	head -c "$((0x$entry))" /dev/zero | tr '\0' '\377' >"$R/dev/$dev" || exit 1
	;;
write)
	src=$1; label=$2
	[ -f "$src" ] || { echo "mtd: no source $src" >&2; exit 1; }
	dev=$(devpath "$label") || exit 1
	dd if="$src" of="$R/dev/$dev" bs=4096 conv=notrunc 2>/dev/null || exit 1
	if [ -f "$R/.mock-corrupt-kernel" ]; then
		printf 'XX' | dd of="$R/dev/$dev" bs=1 seek=64 conv=notrunc 2>/dev/null
	fi
	;;
*) echo "mtd: unsupported: $cmd" >&2; exit 2 ;;
esac
SHIM
	cat >"$CASE/bin/ubiformat" <<'SHIM'
#!/bin/sh
R=${FI_ROOT:?}
echo "ubiformat $*" >>"$R/.cmdlog"
dev=$1; shift
img=""
while [ $# -gt 0 ]; do
	case "$1" in
	-f) img=$2; shift ;;
	-y) ;;
	esac
	shift
done
[ -f "$img" ] || { echo "ubiformat: no image $img" >&2; exit 1; }
total=$(stat -c %s "$dev")
size=$(stat -c %s "$img")
{
	cat "$img"
	head -c "$((total - size))" /dev/zero | tr '\0' '\377'
} >"$dev" || exit 1
if [ -f "$R/.mock-corrupt-rootfs" ]; then
	printf 'XX' | dd of="$dev" bs=1 seek=100 conv=notrunc 2>/dev/null
fi
if [ -f "$R/.mock-badblock" ]; then
	echo "ubiformat: bad block detected at PEB 4 (fixture)"
fi
if [ -f "$R/.mock-ubiformat-fail" ]; then
	exit 1
fi
SHIM
	cat >"$CASE/bin/sync" <<'SHIM'
#!/bin/sh
echo "sync" >>"${FI_ROOT:?}/.cmdlog"
SHIM
	cat >"$CASE/bin/reboot" <<'SHIM'
#!/bin/sh
R=${FI_ROOT:?}
echo "reboot" >>"$R/.cmdlog"
if [ ! -f "$R/.mock-no-reboot" ]; then
	: >"$R/.reboot-requested"
fi
SHIM
	cat >"$CASE/bin/fw_printenv" <<'SHIM'
#!/bin/sh
R=${FI_ROOT:?}
if [ "${1:-}" = bootflag ]; then
	printf 'bootflag=%s\n' "$(cat "$R/.bootflag" 2>/dev/null)"
fi
SHIM
	cat >"$CASE/bin/dmesg" <<'SHIM'
#!/bin/sh
cat "${FI_ROOT:?}/.dmesg" 2>/dev/null
SHIM
	cat >"$CASE/bin/df" <<'SHIM'
#!/bin/sh
R=${FI_ROOT:?}
free=$(cat "$R/.tmp-free-kb" 2>/dev/null || echo 250000)
printf 'Filesystem     1K-blocks  Used Available Use%% Mounted on\n'
printf 'fixture           262144  1000 %s 1%% /tmp\n' "$free"
SHIM
	chmod +x "$CASE/bin/"*

	cat >"$CASE/bin/bench-link" <<'SHIM'
#!/bin/sh
if [ -f "${FIRST_INSTALL_TEST_CASE:?}/.mock-bench-fail" ]; then echo "bench link FAIL (fixture)"; exit 1; fi
echo "bench link PASS (fixture)"
SHIM
	cat >"$CASE/bin/recovery-card" <<'SHIM'
#!/bin/sh
if [ -f "${FIRST_INSTALL_TEST_CASE:?}/.mock-recovery-fail" ]; then echo "recovery NOT READY (fixture)"; exit 1; fi
echo "recovery READY (fixture)"
SHIM
	cat >"$CASE/bin/uart-check" <<'SHIM'
#!/bin/sh
if [ -f "${FIRST_INSTALL_TEST_CASE:?}/.mock-uart-fail" ]; then echo "no capture"; exit 1; fi
echo "capture armed (fixture)"
SHIM
	cat >"$CASE/bin/image-check" <<'PYSTUB'
import os, sys
marker = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".mock-image-check-fail")
if os.path.exists(marker):
    sys.stderr.write("luofu-image: FAIL: corrupted (fixture)\n")
    sys.exit(1)
print("check-container: PASS (fixture stub; the harness also exercises the independent byte checks)")
print("  control:         BOARD=cudy_wr3000-v2 TARGET=hisilicon/luofu VERSION=fixture")
print("  kernel slice:    2048 B, load/ep 0x80608000/0x80608000, gate 0xd7b7ab1e at 0x400")
print("  rootfs UBI:      393216 B, volume 'squashfs' (static), used_ebs 1")
print("  install status:  NOT FLASHABLE marker present")
sys.exit(0)
PYSTUB
	chmod +x "$CASE/bin/"*

	# fake rsh: execute the stdin-fed device script against the fixture tree
	cat >"$CASE/bin/rsh" <<'SHIM'
#!/usr/bin/env bash
R=${FAKE_DEVICE_ROOT:?}
HOSTPATH=$PATH
echo "rsh $*" >>"$R/.cmdlog"
if [ -f "$R/.reboot-requested" ]; then
	outcome=$(cat "$R/.mock-reboot-outcome" 2>/dev/null || echo none)
	rm -f "$R/.reboot-requested"
	case "$outcome" in
	stock)
		echo "sim-boot-id-stock" >"$R/proc/sys/kernel/random/boot_id"
		printf 'Linux version 5.10.201 (fixture stock fallback) #1 SMP\n' >"$R/proc/version"
		echo a >"$R/.bootflag"
		echo "0x10" >"$R/sys/devices/platform/sysenv/boot_reg"
		echo 13 >"$R/sys/class/ubi/ubi0/mtd_num"
		;;
	target)
		echo "sim-boot-id-target" >"$R/proc/sys/kernel/random/boot_id"
		printf 'Linux version 6.18.60 (fixture target image) #1 SMP\n' >"$R/proc/version"
		echo b >"$R/.bootflag"
		echo "0x11" >"$R/sys/devices/platform/sysenv/boot_reg"
		echo 14 >"$R/sys/class/ubi/ubi0/mtd_num"
		;;
	none)
		: >"$R/.down"
		;;
	esac
fi
if [ -f "$R/.down" ]; then
	exit 255
fi
set -- $1
cmd=$1; shift
if [ "$cmd" = sh ] && [ "${1:-}" = "-s" ]; then shift; fi
tmp=$(mktemp "$R/../rsh-stdin.XXXXXX") || exit 1
cat >"$tmp"
env FI_ROOT="$R" PATH="$R/bin:$R/../bin:$HOSTPATH" FAKE_DEVICE_ROOT="$R" sh "$tmp" "$@"
rc=$?
rm -f "$tmp"
exit $rc
SHIM
	cat >"$CASE/bin/rscp" <<'SHIM'
#!/usr/bin/env bash
R=${FAKE_DEVICE_ROOT:?}
echo "rscp $*" >>"$R/.cmdlog"
src=$1; dst=$2
rel=${dst#*:}
dest="$R$rel"
mkdir -p "$(dirname "$dest")" || exit 1
cp "$src" "$dest" || exit 1
SHIM
	chmod +x "$CASE/bin/"*
}

write_mtd_table() { # <active: a|b>
	local active=$1
	mkdir -p "$CASE/root/proc" "$CASE/root/sys/class/ubi/ubi0" "$CASE/root/sys/devices/platform/sysenv"
	cat >"$CASE/root/proc/mtd" <<EOF
dev:    size   erasesize  name
mtd0: 00040000 00020000 "esbc"
mtd1: 00100000 00020000 "uboota"
mtd2: 00100000 00020000 "ubootb"
mtd3: 00040000 00020000 "enva"
mtd4: 00040000 00020000 "envb"
mtd5: 00200000 00020000 "fac"
mtd6: 00040000 00020000 "bdinfo"
mtd7: 00200000 00020000 "cfga"
mtd8: 00200000 00020000 "cfgb"
mtd9: 00440000 00020000 "log"
mtd10: 00040000 00020000 "pstore"
mtd11: 00840000 00020000 "kernela"
mtd12: 00840000 00020000 "kernelb"
mtd13: 01740000 00020000 "rootfsa"
mtd14: 01740000 00020000 "rootfsb"
mtd15: 01600000 00020000 "rootfs_data"
mtd16: 01d80000 00020000 "upgrade"
EOF
	if [ "$active" = a ]; then
		echo 13 >"$CASE/root/sys/class/ubi/ubi0/mtd_num"
		echo a >"$CASE/root/.bootflag"
		echo "0x10" >"$CASE/root/sys/devices/platform/sysenv/boot_reg"
	else
		echo 14 >"$CASE/root/sys/class/ubi/ubi0/mtd_num"
		echo b >"$CASE/root/.bootflag"
		echo "0x11" >"$CASE/root/sys/devices/platform/sysenv/boot_reg"
	fi
}

make_devices() {
	local i sizehex size
	mkdir -p "$CASE/root/dev"
	while read -r line; do
		case "$line" in
		mtd[0-9]*)
			i=$(echo "$line" | sed -n 's/^mtd\([0-9]*\):.*/\1/p')
			sizehex=$(echo "$line" | awk '{ print $2 }')
			case "$sizehex" in
			''|*[!0-9a-fA-F]*) continue ;;
			esac
			size=$((0x$sizehex))
			truncate -s "$size" "$CASE/root/dev/mtd$i" 2>/dev/null \
				|| dd if=/dev/zero of="$CASE/root/dev/mtd$i" bs=4096 count=$(( (size + 4095) / 4096 )) 2>/dev/null
			printf 'seed-mtd%s' "$i" | dd of="$CASE/root/dev/mtd$i" bs=1 seek=0 conv=notrunc 2>/dev/null
			;;
		esac
	done <"$CASE/root/proc/mtd"
}

make_root_fixture() { # <active: a|b>
	local active=$1
	mkdir -p "$CASE/root"/proc/sys/kernel/random \
		"$CASE/root"/etc/init.d \
		"$CASE/root"/lib/hisilicon/ko \
		"$CASE/root"/lib/modules/5.10.201 \
		"$CASE/root"/sys/class/ieee80211 \
		"$CASE/root"/sys/class/ubi/ubi0 \
		"$CASE/root"/sys/devices/platform/sysenv \
		"$CASE/root"/tmp
	printf 'Linux version 5.10.201 (fixture stock) #1 SMP PREEMPT\n' >"$CASE/root/proc/version"
	echo "12345.67 1.00" >"$CASE/root/proc/uptime"
	echo "fixture-boot-id-initial" >"$CASE/root/proc/sys/kernel/random/boot_id"
	{
		i=1
		while [ "$i" -le 12 ]; do
			echo "hi_mod$i 12345 0 - Live 0xbf000000"
			i=$((i + 1))
		done
	} >"$CASE/root/proc/modules"
	printf "DISTRIB_ID='OpenWrt'\nDISTRIB_RELEASE='22.03.6'\nDISTRIB_TARGET='hisilicon/luofu'\n" >"$CASE/root/etc/openwrt_release"
	: >"$CASE/root/etc/init.d/hsan_appm"
	i=1
	while [ "$i" -le 12 ]; do
		: >"$CASE/root/lib/hisilicon/ko/hi_mod$i.ko"
		i=$((i + 1))
	done
	mkdir -p "$CASE/root/sys/class/ieee80211/phy0" "$CASE/root/sys/class/ieee80211/phy1"
	printf 'line hwifi_rf_cali_file_load_2g succ\nline hwifi_rf_cali_file_load_5g succ\n' >"$CASE/root/.dmesg"
	echo 250000 >"$CASE/root/.tmp-free-kb"
	write_mtd_table "$active"
	make_devices
}

new_case() { # <name> [active]
	CASE="$TMP/$1"
	[ -d "$CASE" ] && rm -rf "$CASE"
	mkdir -p "$CASE/root" "$CASE/bin"
	: >"$CASE/cmdlog"
	write_shims
	local active=${2:-a}
	make_root_fixture "$active"
	: >"$CASE/root/.cmdlog"
}

run_tool() { # <args...>
	OUT="$CASE/out.txt"
	ERR="$CASE/err.txt"
	: >"$CASE/root/.cmdlog"
	env \
		FAKE_DEVICE_ROOT="$CASE/root" \
		FIRST_INSTALL_TEST_CASE="$CASE" \
		FIRST_INSTALL_RSH="$CASE/bin/rsh" \
		FIRST_INSTALL_RSCP="$CASE/bin/rscp" \
		FIRST_INSTALL_IMAGE_TOOL="$CASE/bin/image-check" \
		FIRST_INSTALL_BENCH_LINK_CMD="$CASE/bin/bench-link" \
		FIRST_INSTALL_RECOVERY_CARD_CMD="$CASE/bin/recovery-card" \
		FIRST_INSTALL_UART_CHECK_CMD="$CASE/bin/uart-check" \
		FIRST_INSTALL_REMOTE_HOST="root@fixture" \
		FIRST_INSTALL_POLL_ATTEMPTS=3 \
		FIRST_INSTALL_POLL_INTERVAL=0 \
		FIRST_INSTALL_REBOOT_DELAY=0 \
		"$TOOL" "$@" >"$OUT" 2>"$ERR"
	RC=$?
	cp "$CASE/root/.cmdlog" "$CASE/cmdlog" 2>/dev/null || : >"$CASE/cmdlog"
}

# build a synthetic but structurally valid sysupgrade container
build_image() { # <path> <variant>
	python3 - "$1" "${2:-ok}" <<'PYEOF'
import hashlib, os, struct, sys, tarfile, tempfile, shutil
path, variant = sys.argv[1], sys.argv[2]
board = "sysupgrade-cudy_wr3000-v2"
tmp = tempfile.mkdtemp(prefix="fi-img-")
try:
    bdir = os.path.join(tmp, board)
    os.makedirs(bdir)
    kernel = bytearray(2048)
    kernel[0:4] = bytes.fromhex("27051956")
    gate = 0x400
    kernel[gate:gate + 4] = bytes.fromhex("d7b7ab1e")
    if variant == "gate":
        kernel[gate:gate + 4] = bytes.fromhex("00000000")
    root = bytearray(3 * 131072)
    root[0:4] = b"UBI#"
    root[16:20] = struct.pack(">I", 2048)
    root[2048:2052] = b"UBI!"
    if variant == "rootmagic":
        root[0:4] = b"XXXX"
    manifest = (
        "manifest-version: 2\n"
        "slice-size: %d\n"
        "slice-sha256: %s\n"
        "slot-limit: 8650752\n"
        "gate-offset: 0x%x\n"
        "gate-magic: 0xd7b7ab1e\n"
        "trailer-size: 128\n"
    ) % (len(kernel), hashlib.sha256(bytes(kernel)).hexdigest(), gate)
    name = board if variant != "board" else "sysupgrade-wrong_board"
    bdir = os.path.join(tmp, name)
    if not os.path.isdir(bdir):
        os.makedirs(bdir)
    open(os.path.join(bdir, "CONTROL"), "w").write(
        "BOARD=%s\nTARGET=hisilicon/luofu\nVERSION=fixture\n"
        % ("cudy_wr3000-v2" if variant != "board" else "wrong_board"))
    open(os.path.join(bdir, "INSTALL-STATUS.txt"), "w").write(
        "fixture container - STATUS: NOT FLASHABLE\n")
    open(os.path.join(bdir, "fip-manifest.txt"), "w").write(manifest)
    open(os.path.join(bdir, "kernel"), "wb").write(bytes(kernel))
    open(os.path.join(bdir, "root"), "wb").write(bytes(root))
    if variant == "tamper":
        with open(os.path.join(bdir, "kernel"), "r+b") as f:
            f.seek(100)
            f.write(b"TAMPER")
    if variant == "oversize":
        big = bytearray(8650752 + 4096)
        big[0:4] = bytes.fromhex("27051956")
        big[gate:gate + 4] = bytes.fromhex("d7b7ab1e")
        open(os.path.join(bdir, "kernel"), "wb").write(bytes(big))
    with tarfile.open(path, "w", format=tarfile.USTAR_FORMAT) as t:
        t.add(bdir, arcname=name)
finally:
    shutil.rmtree(tmp, ignore_errors=True)
PYEOF
}

extract_device_script() { # <output>
	sed -n "/<<'FI_DEVICE_SCRIPT'/,/^FI_DEVICE_SCRIPT\$/p" "$TOOL" | sed '1d;$d' >"$1"
}

# ---------------------------------------------------------------------------
# scenarios
# ---------------------------------------------------------------------------
t_syntax() {
	echo "# tool syntax / generated device script"
	CASE="$TMP/syntax"
	mkdir -p "$CASE"
	extract_device_script "$CASE/device.sh"
	if [ -s "$CASE/device.sh" ]; then ok "embedded device script extracted"; else not_ok "embedded device script missing"; fi
	if sh -n "$CASE/device.sh" 2>"$CASE/sh-n.err"; then ok "embedded device script passes sh -n"; else not_ok "embedded device script fails sh -n"; sed 's/^/    /' "$CASE/sh-n.err"; fi
	if bash -n "$TOOL"; then ok "tool passes bash -n"; else not_ok "tool fails bash -n"; fi
}

t_inspect_ok() {
	echo "# read-only inspection: healthy stock A + valid image"
	new_case inspect_ok a
	build_image "$CASE/image.bin" ok
	run_tool --inspect --image "$CASE/image.bin"
	assert_rc 0 "inspection passes"
	assert_out "INSPECTION PASS" "inspection summary"
	assert_out "active pair" "device state printed"
	assert_out "target pair: b" "inactive pair derived as B"
	assert_no_cmdlog_re '^(mtd|ubiformat|reboot|rscp) ' "no flash tool or scp was called"
	assert_no_cmdlog_re '^sync$' "no sync"
	assert_file "$CASE/root/sys/devices/platform/sysenv/boot_reg" "0x10" "selector unchanged by inspection"
}

t_inspect_no_image() {
	echo "# read-only inspection without an image"
	new_case inspect_noimg a
	run_tool --inspect
	assert_rc 0 "inspection without --image passes"
	assert_out "INSPECTION PASS" "readiness summary"
	assert_err "no --image given" "missing-image warning"
	assert_no_cmdlog_re '^(mtd|ubiformat|reboot|rscp) ' "no flash tool or scp was called"
}

t_write_gates() {
	echo "# write gates: attended / recovery / image are all mandatory"
	new_case gate1 a
	build_image "$CASE/image.bin" ok
	run_tool --write --image "$CASE/image.bin"
	assert_rc 2 "--write without --attended refuses (usage)"
	assert_no_cmdlog_re '^rsh ' "no device access without --attended"
	new_case gate2 a
	build_image "$CASE/image.bin" ok
	run_tool --write --attended --image "$CASE/image.bin"
	assert_rc 2 "--write without --recovery-armed refuses (usage)"
	assert_no_cmdlog_re '^rsh ' "no device access without --recovery-armed"
	new_case gate3 a
	run_tool --write --attended --recovery-armed
	assert_rc 2 "--write without --image refuses (usage)"
	assert_no_cmdlog_re '^rsh ' "no device access without an image"
}

t_write_a_to_b() {
	echo "# write mode: stock A active -> writes kernelb/rootfsb only"
	new_case write_ab a
	build_image "$CASE/image.bin" ok
	run_tool --write --attended --recovery-armed --image "$CASE/image.bin"
	assert_rc 0 "write completes"
	assert_out "WRITE COMPLETE" "write summary"
	assert_out "pair b staged and verified" "target pair reported"
	assert_cmdlog "mtd erase kernelb" "kernelb erased by label"
	assert_cmdlog "mtd write" "kernel written"
	assert_cmdlog "ubiformat" "rootfs ubiformatted"
	assert_before "mtd erase kernelb" "ubiformat " "kernel write happens before the rootfs write"
	assert_no_cmdlog_re 'kernela' "active kernel slot not targeted"
	assert_no_cmdlog_re 'rootfsa' "active rootfs slot not targeted"
	assert_no_cmdlog_re '^reboot$' "write mode does not reboot"
	assert_file "$CASE/root/sys/devices/platform/sysenv/boot_reg" "0x10" "selector not moved in write mode"
	python3 - "$CASE/image.bin" "$CASE/expected-kernel" "$CASE/expected-root" <<'PYEOF'
import sys, tarfile
with tarfile.open(sys.argv[1], "r:") as t:
    names = t.getnames()
    bd = names[0].split("/")[0]
    open(sys.argv[2], "wb").write(t.extractfile(bd + "/kernel").read())
    open(sys.argv[3], "wb").write(t.extractfile(bd + "/root").read())
PYEOF
	assert_sha "$CASE/root/dev/mtd12" "$(python3 - "$CASE/expected-kernel" <<'PYEOF'
import hashlib, sys
h = hashlib.sha256()
h.update(open(sys.argv[1], "rb").read())
h.update(b"\xff" * (8650752 - 2048))
print(h.hexdigest())
PYEOF
)" "kernelb holds the written slice + erased tail"
	assert_sha "$CASE/root/dev/mtd14" "$(python3 - "$CASE/expected-root" <<'PYEOF'
import hashlib, sys
h = hashlib.sha256()
h.update(open(sys.argv[1], "rb").read())
h.update(b"\xff" * (24379392 - 3 * 131072))
print(h.hexdigest())
PYEOF
)" "rootfsb holds the written UBI + erased tail"
	assert_no_cmdlog_re 'fw_setenv' "no env writer is invoked"
	assert_file "$CASE/root/.bootflag" "a" "env bootflag file unchanged"
	local n
	for n in 11 13 15 16 3 4 5 6 7 8 9 10 0 1 2; do
		case "$(head -c 8 "$CASE/root/dev/mtd$n")" in
		seed-mtd*) ok "mtd$n fixture prefix still present (untouched by the write)" ;;
		*) not_ok "mtd$n changed during a write that must not touch it" ;;
		esac
	done
}

t_write_b_to_a() {
	echo "# write mode: stock B active -> writes kernela/rootfsa only"
	new_case write_ba b
	build_image "$CASE/image.bin" ok
	run_tool --write --attended --recovery-armed --image "$CASE/image.bin"
	assert_rc 0 "write completes from B"
	assert_out "pair a staged and verified" "target pair A reported"
	assert_cmdlog "mtd erase kernela" "kernela erased"
	assert_cmdlog "ubiformat" "rootfsa ubiformatted"
	assert_no_cmdlog_re 'kernelb' "active kernelb not targeted"
	assert_no_cmdlog_re 'rootfsb' "active rootfsb not targeted"
	assert_file "$CASE/root/sys/devices/platform/sysenv/boot_reg" "0x11" "selector not moved"
}

t_handover_a_to_b() {
	echo "# handover: A active -> selector 0x11, env never written"
	new_case hand_ab a
	build_image "$CASE/image.bin" ok
	run_tool --handover --attended --recovery-armed --image "$CASE/image.bin"
	assert_rc 0 "handover completes"
	assert_out "HANDOVER COMPLETE" "handover summary"
	assert_out "FI_HANDOVER_OK selector=0x11" "selector reported as 0x11"
	assert_file "$CASE/root/sys/devices/platform/sysenv/boot_reg" "0x11" "selector now names the written pair B"
	assert_file "$CASE/root/.bootflag" "a" "env bootflag file still names the active pair A"
	assert_cmdlog "mtd erase kernelb" "kernel written before handover"
	assert_cmdlog "ubiformat" "rootfs written before handover"
	assert_no_cmdlog_re 'fw_setenv' "env writer never invoked"
	assert_no_cmdlog_re '^reboot$' "handover mode does not reboot"
	local k r h
	k=$(grep -nF 'FI_KERNEL_WRITE_OK' "$CASE/out.txt" | head -1 | cut -d: -f1)
	r=$(grep -nF 'FI_ROOTFS_WRITE_OK' "$CASE/out.txt" | head -1 | cut -d: -f1)
	h=$(grep -nF 'FI_HANDOVER_OK' "$CASE/out.txt" | head -1 | cut -d: -f1)
	if [ -n "$k" ] && [ -n "$r" ] && [ -n "$h" ] && [ "$k" -lt "$r" ] && [ "$r" -lt "$h" ]; then
		ok "write order: kernel read-back < rootfs read-back < selector move"
	else
		not_ok "write order (kernel=$k rootfs=$r handover=$h)"
	fi
}

t_handover_b_to_a() {
	echo "# handover: B active -> selector 0x10"
	new_case hand_ba b
	build_image "$CASE/image.bin" ok
	run_tool --handover --attended --recovery-armed --image "$CASE/image.bin"
	assert_rc 0 "handover from B completes"
	assert_out "FI_HANDOVER_OK selector=0x10" "selector value 0x10 reported"
	assert_file "$CASE/root/sys/devices/platform/sysenv/boot_reg" "0x10" "selector now names the written pair A"
	assert_file "$CASE/root/.bootflag" "b" "env bootflag still names the active pair B"
}

t_handover_refuses_manual_cell() {
	echo "# handover refusal: manual 0x21 cell"
	new_case hand_manual a
	build_image "$CASE/image.bin" ok
	echo "0x21" >"$CASE/root/sys/devices/platform/sysenv/boot_reg"
	run_tool --handover --attended --recovery-armed --image "$CASE/image.bin"
	assert_rc 1 "manual 0x21 cell refuses the handover"
	assert_out "RECOVERY PLAN" "recovery plan printed"
	assert_no_cmdlog_re '^(mtd|ubiformat|reboot) ' "no flash write on the refusal"
	assert_file "$CASE/root/sys/devices/platform/sysenv/boot_reg" "0x21" "cell untouched"
}

t_write_allows_early_cell() {
	echo "# write mode tolerates a fresh-boot opposite-pair cell; handover refuses it"
	new_case early_cell a
	build_image "$CASE/image.bin" ok
	echo "0x11" >"$CASE/root/sys/devices/platform/sysenv/boot_reg"
	run_tool --write --attended --recovery-armed --image "$CASE/image.bin"
	assert_rc 0 "write proceeds with the loader's opposite-pair record"
	assert_cmdlog "mtd erase kernelb" "kernel written"
	new_case early_cell2 a
	build_image "$CASE/image.bin" ok
	echo "0x11" >"$CASE/root/sys/devices/platform/sysenv/boot_reg"
	run_tool --handover --attended --recovery-armed --image "$CASE/image.bin"
	assert_rc 1 "handover refuses the opposite-pair record"
	assert_no_cmdlog_re '^(mtd|ubiformat) ' "refusal before any write"
	assert_file "$CASE/root/sys/devices/platform/sysenv/boot_reg" "0x11" "cell untouched"
}

t_refuse_not_stock() {
	echo "# refusals: not stock / already customised"
	new_case custom a
	build_image "$CASE/image.bin" ok
	: >"$CASE/root/etc/custom-firmware-version"
	run_tool --write --attended --recovery-armed --image "$CASE/image.bin"
	assert_rc 1 "custom marker refuses the install"
	assert_out "already-customised" "custom-marker blocker"
	assert_no_cmdlog_re '^(mtd|ubiformat) ' "no flash write"
	new_case wrongkern a
	build_image "$CASE/image.bin" ok
	printf 'Linux version 6.1.0 (fixture) #1\n' >"$CASE/root/proc/version"
	run_tool --write --attended --recovery-armed --image "$CASE/image.bin"
	assert_rc 1 "non-stock kernel refuses the install"
}

t_refuse_size_checks() {
	echo "# refusals: slot size and image member size checks"
	new_case slotsize a
	build_image "$CASE/image.bin" ok
	sed -i 's/^mtd12: 00840000/mtd12: 00800000/' "$CASE/root/proc/mtd"
	run_tool --write --attended --recovery-armed --image "$CASE/image.bin"
	assert_rc 1 "wrong kernelb size in /proc/mtd refuses"
	assert_no_cmdlog_re '^(mtd|ubiformat) ' "no flash write"
	new_case oversize a
	build_image "$CASE/image.bin" oversize
	run_tool --write --attended --recovery-armed --image "$CASE/image.bin"
	assert_rc 1 "oversize kernel member refuses"
	assert_no_cmdlog_re '^rsh ' "refusal happens before any device access"
}

t_refuse_image_checks() {
	echo "# refusals: image validation (external check, tamper, wrong board, root magic)"
	new_case img_check a
	build_image "$CASE/image.bin" ok
	: >"$CASE/.mock-image-check-fail"
	run_tool --write --attended --recovery-armed --image "$CASE/image.bin"
	assert_rc 1 "external check-container refusal stops the run"
	assert_err "check-container REFUSED" "external refusal reported"
	assert_no_cmdlog_re '^rsh ' "no device access after a refused image"
	new_case img_tamper a
	build_image "$CASE/image.bin" tamper
	run_tool --write --attended --recovery-armed --image "$CASE/image.bin"
	assert_rc 1 "tampered kernel (manifest sha mismatch) refuses"
	assert_no_cmdlog_re '^rsh ' "no device access"
	new_case img_board a
	build_image "$CASE/image.bin" board
	run_tool --write --attended --recovery-armed --image "$CASE/image.bin"
	assert_rc 1 "wrong board directory refuses"
	assert_no_cmdlog_re '^rsh ' "no device access"
	new_case img_root a
	build_image "$CASE/image.bin" rootmagic
	run_tool --write --attended --recovery-armed --image "$CASE/image.bin"
	assert_rc 1 "rootfs without the UBI# magic refuses"
	assert_no_cmdlog_re '^rsh ' "no device access"
}

t_refuse_host_preflight() {
	echo "# refusals: host preflight (bench link, recovery door, UART capture)"
	new_case bench a
	build_image "$CASE/image.bin" ok
	: >"$CASE/.mock-bench-fail"
	run_tool --write --attended --recovery-armed --image "$CASE/image.bin"
	assert_rc 1 "bench link failure refuses"
	assert_no_cmdlog_re '^rsh ' "no device access"
	new_case rec a
	build_image "$CASE/image.bin" ok
	: >"$CASE/.mock-recovery-fail"
	run_tool --write --attended --recovery-armed --image "$CASE/image.bin"
	assert_rc 1 "recovery door not ready refuses"
	assert_no_cmdlog_re '^rsh ' "no device access"
	new_case uart a
	build_image "$CASE/image.bin" ok
	: >"$CASE/.mock-uart-fail"
	run_tool --reboot --attended --recovery-armed --image "$CASE/image.bin"
	assert_rc 1 "reboot without an armed UART capture refuses"
	assert_no_cmdlog_re '^rsh ' "no device access"
}

t_refuse_state_checks() {
	echo "# refusals: selector/booted-pair consistency, --expect-active, /tmp"
	new_case mismatch a
	build_image "$CASE/image.bin" ok
	echo b >"$CASE/root/.bootflag"
	run_tool --write --attended --recovery-armed --image "$CASE/image.bin"
	assert_rc 1 "env bootflag != booted rootfs pair refuses"
	assert_no_cmdlog_re '^(mtd|ubiformat) ' "no flash write"
	new_case expect a
	build_image "$CASE/image.bin" ok
	run_tool --write --attended --recovery-armed --image "$CASE/image.bin" --expect-active b
	assert_rc 1 "--expect-active mismatch refuses"
	assert_no_cmdlog_re '^(mtd|ubiformat) ' "no flash write"
	new_case tmpfull a
	build_image "$CASE/image.bin" ok
	echo 100 >"$CASE/root/.tmp-free-kb"
	run_tool --write --attended --recovery-armed --image "$CASE/image.bin"
	assert_rc 1 "too little device /tmp refuses"
	new_case noiface a
	build_image "$CASE/image.bin" ok
	rm -f "$CASE/root/sys/devices/platform/sysenv/boot_reg"
	run_tool --write --attended --recovery-armed --image "$CASE/image.bin"
	assert_rc 1 "missing sysenv interface refuses"
}

t_readback_failures() {
	echo "# failure paths: kernel/rootfs read-back and ubiformat bad block"
	new_case kfail a
	build_image "$CASE/image.bin" ok
	: >"$CASE/root/.mock-corrupt-kernel"
	run_tool --write --attended --recovery-armed --image "$CASE/image.bin"
	assert_rc 1 "kernel read-back mismatch aborts"
	assert_err "kernelb read-back mismatch" "kernel read-back error named"
	assert_out "RECOVERY PLAN" "recovery plan printed"
	assert_no_cmdlog_re '^ubiformat ' "rootfs write not attempted after the kernel failure"
	assert_no_cmdlog_re '^reboot$' "no reboot"
	assert_file "$CASE/root/sys/devices/platform/sysenv/boot_reg" "0x10" "selector untouched"
	new_case rfail a
	build_image "$CASE/image.bin" ok
	: >"$CASE/root/.mock-corrupt-rootfs"
	run_tool --write --attended --recovery-armed --image "$CASE/image.bin"
	assert_rc 1 "rootfs read-back mismatch aborts"
	assert_err "rootfsb read-back mismatch" "rootfs read-back error named"
	assert_out "RECOVERY PLAN" "recovery plan printed"
	assert_no_cmdlog_re '^reboot$' "no reboot"
	assert_file "$CASE/root/sys/devices/platform/sysenv/boot_reg" "0x10" "selector untouched"
	new_case badblock a
	build_image "$CASE/image.bin" ok
	: >"$CASE/root/.mock-badblock"
	run_tool --handover --attended --recovery-armed --image "$CASE/image.bin"
	assert_rc 1 "ubiformat bad-block report aborts before the handover"
	assert_err "bad block" "bad-block cause reported"
	assert_file "$CASE/root/sys/devices/platform/sysenv/boot_reg" "0x10" "selector untouched"
}

t_no_reboot_detected() {
	echo "# reboot classification: no reboot detected"
	new_case noreboot a
	build_image "$CASE/image.bin" ok
	: >"$CASE/root/.mock-no-reboot"
	run_tool --reboot --attended --recovery-armed --image "$CASE/image.bin"
	assert_rc 1 "same boot_id after the reboot command is a failure"
	assert_out "NO REBOOT DETECTED" "classification"
	assert_out "RECOVERY PLAN" "recovery plan printed"
}

t_stock_fallback() {
	echo "# reboot classification: stock fallback (safe failure)"
	new_case fallback a
	build_image "$CASE/image.bin" ok
	echo stock >"$CASE/root/.mock-reboot-outcome"
	run_tool --reboot --attended --recovery-armed --image "$CASE/image.bin"
	assert_rc 3 "stock fallback is an unverified outcome (rc 3)"
	assert_out "STOCK FALLBACK OBSERVED" "classification"
	assert_out "RECOVERY PLAN" "recovery plan printed"
	assert_file "$CASE/root/sys/devices/platform/sysenv/boot_reg" "0x10" "selector state after the simulated failover"
}

t_unverified() {
	echo "# reboot classification: no SSH return (unverified)"
	new_case unverified a
	build_image "$CASE/image.bin" ok
	echo none >"$CASE/root/.mock-reboot-outcome"
	run_tool --reboot --attended --recovery-armed --image "$CASE/image.bin"
	assert_rc 3 "no return is an unverified outcome (rc 3)"
	assert_out "UNVERIFIED" "classification"
	assert_out "RECOVERY PLAN" "recovery plan printed"
}

t_reboot_target() {
	echo "# reboot classification: target pair responded over SSH"
	new_case tgt a
	build_image "$CASE/image.bin" ok
	echo target >"$CASE/root/.mock-reboot-outcome"
	run_tool --reboot --attended --recovery-armed --image "$CASE/image.bin"
	assert_rc 0 "target response is classified as success"
	assert_out "TARGET PAIR RESPONDED OVER SSH" "classification"
}

t_dry_run() {
	echo "# dry-run: full read-only rehearsal, no writes"
	new_case dry a
	build_image "$CASE/image.bin" ok
	run_tool --handover --attended --recovery-armed --image "$CASE/image.bin" --dry-run
	assert_rc 0 "dry-run completes"
	assert_out "DRY RUN" "dry-run summary"
	assert_out "plan (NOT executed" "plan printed"
	assert_no_cmdlog_re '^(mtd|ubiformat|reboot|rscp) ' "no flash tool, scp or reboot"
	assert_file "$CASE/root/sys/devices/platform/sysenv/boot_reg" "0x10" "selector untouched"
}

t_real_container() {
	local container=$1
	echo "# real built container through the real luofu-image.py check (dry-run)"
	new_case real a
	OUT="$CASE/out.txt"; ERR="$CASE/err.txt"
	: >"$CASE/root/.cmdlog"
	env \
		FAKE_DEVICE_ROOT="$CASE/root" \
		FIRST_INSTALL_TEST_CASE="$CASE" \
		FIRST_INSTALL_RSH="$CASE/bin/rsh" \
		FIRST_INSTALL_RSCP="$CASE/bin/rscp" \
		FIRST_INSTALL_BENCH_LINK_CMD="$CASE/bin/bench-link" \
		FIRST_INSTALL_RECOVERY_CARD_CMD="$CASE/bin/recovery-card" \
		FIRST_INSTALL_UART_CHECK_CMD="$CASE/bin/uart-check" \
		FIRST_INSTALL_REMOTE_HOST="root@fixture" \
		FIRST_INSTALL_POLL_ATTEMPTS=3 \
		FIRST_INSTALL_POLL_INTERVAL=0 \
		FIRST_INSTALL_REBOOT_DELAY=0 \
		"$TOOL" --handover --attended --recovery-armed --image "$container" --dry-run >"$OUT" 2>"$ERR"
	RC=$?
	cp "$CASE/root/.cmdlog" "$CASE/cmdlog" 2>/dev/null || : >"$CASE/cmdlog"
	assert_rc 0 "real container validates and the dry-run completes"
	assert_out "luofu-image.py check-container PASS" "real check tool ran"
	assert_out "DRY RUN" "dry-run summary"
	assert_no_cmdlog_re '^(mtd|ubiformat|reboot|rscp) ' "no write"
}

# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
echo "== first-install-stock mocked tests =="
echo "tool: $TOOL"
echo "fixtures: $TMP"
echo

t_syntax
t_inspect_ok
t_inspect_no_image
t_write_gates
t_write_a_to_b
t_write_b_to_a
t_handover_a_to_b
t_handover_b_to_a
t_handover_refuses_manual_cell
t_write_allows_early_cell
t_refuse_not_stock
t_refuse_size_checks
t_refuse_image_checks
t_refuse_host_preflight
t_refuse_state_checks
t_readback_failures
t_no_reboot_detected
t_stock_fallback
t_unverified
t_reboot_target
t_dry_run

if [ -z "$REAL_CONTAINER" ]; then
	for cand in "$HOME"/openwrt-lab-selectorfix-img/bin/targets/hisilicon/luofu/*sysupgrade*.bin; do
		[ -f "$cand" ] && REAL_CONTAINER=$cand && break
	done
fi
if [ -n "$REAL_CONTAINER" ] && [ -f "$REAL_CONTAINER" ]; then
	t_real_container "$REAL_CONTAINER"
else
	echo "# no real built container available; real-tool dry-run scenario skipped"
fi

echo
echo "== results: $PASS passed, $FAIL failed =="
if [ "$FAIL" -ne 0 ]; then
	exit 1
fi
exit 0
