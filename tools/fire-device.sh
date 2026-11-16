#!/bin/sh
# fire-device.sh - write the staged slice to a kernel slot and reboot.
#
# Runs ON THE ROUTER (fire.sh ssh copies it there; do not run it on the host).
# The slot pair is validated: kernela<mtd11, kernelb<mtd12. The slot-B manual handover
# (bootflag=b, boot_reg=0x21) is the only one established on this board. A slot-A fire
# needs a measured BOOT_REG value; there is none in the repo, so it refuses and asks.
#
# env: SLICE=... MTD=kernela|kernelb MTD_DEV=/dev/mtdNN BOOTFLAG=a|b BOOT_REG=0xNN
set -e

SLICE=${SLICE:-/tmp/slice.bin}
MTD=${MTD:-kernelb}

case "$MTD" in
	kernela) DEF_DEV=/dev/mtd11; DEF_FLAG=a; DEF_REG="" ;;
	kernelb) DEF_DEV=/dev/mtd12; DEF_FLAG=b; DEF_REG=0x21 ;;
	*) echo "error: MTD must be kernela or kernelb, got '$MTD'" >&2; exit 2 ;;
esac
MTD_DEV=${MTD_DEV:-$DEF_DEV}
BOOTFLAG=${BOOTFLAG:-$DEF_FLAG}
BOOT_REG=${BOOT_REG:-$DEF_REG}

[ -f "$SLICE" ] || { echo "missing slice: $SLICE" >&2; exit 1; }
case "$MTD:$MTD_DEV" in
	kernela:/dev/mtd11|kernelb:/dev/mtd12) : ;;
	*) echo "error: inconsistent target MTD='$MTD' MTD_DEV='$MTD_DEV'" >&2; exit 2 ;;
esac
[ -n "$BOOT_REG" ] || {
	echo "error: no measured manual-handover BOOT_REG for '$MTD'." >&2
	echo "       The repo only establishes slot B (bootflag=b, boot_reg=0x21)." >&2
	echo "       Do not invent a register value; get a measured plan into STATUS.md first." >&2
	exit 2
}

echo "TARGET slot=$MTD dev=$MTD_DEV bootflag=$BOOTFLAG boot_reg=$BOOT_REG"
echo "PRE  bootflag=$(fw_printenv bootflag 2>/dev/null | cut -d= -f2) boot_reg=$(cat /sys/devices/platform/sysenv/boot_reg 2>/dev/null)"
echo "SLICE $(wc -c < "$SLICE") bytes md5=$(md5sum "$SLICE" | cut -d' ' -f1)"

flash_eraseall "$MTD_DEV" > /tmp/erase-fire.log 2>&1
echo ERASE_OK

mtd write "$SLICE" "$MTD" > /tmp/write-fire.log 2>&1
echo WRITE_OK

if mtd verify "$SLICE" "$MTD" > /tmp/verify-fire.log 2>&1; then
    echo VERIFY_OK
else
    echo VERIFY_FAIL
    exit 1
fi

ln -sf /bin/fw_printenv /tmp/fw_setenv
/tmp/fw_setenv bootflag "$BOOTFLAG"
echo "$BOOT_REG" > /sys/devices/platform/sysenv/boot_reg
devmem 0x10100C94 32 0xDEAD0000

# bootcmd is "mtd read kernel${bootflag} ...", so the variable selects the slot. Without
# the register write and the C94 word above, the vendor userspace's own boot handler still
# boots stock from the other slot (#0, jenkins@cudyrd1): the 15:29 3df fire did exactly that.
printf 'POST bootflag='; fw_printenv bootflag | cut -d= -f2
printf ' boot_reg='; cat /sys/devices/platform/sysenv/boot_reg; echo

sync
reboot
