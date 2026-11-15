#!/bin/sh
# fire-device.sh - write the staged slice to kernelb and reboot.
set -e

SLICE=${SLICE:-/tmp/slice.bin}
MTD=${MTD:-kernelb}
MTD_DEV=${MTD_DEV:-/dev/mtd12}

[ -f "$SLICE" ] || { echo "missing slice: $SLICE" >&2; exit 1; }

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
/tmp/fw_setenv bootflag b
echo 0x21 > /sys/devices/platform/sysenv/boot_reg
devmem 0x10100C94 32 0xDEAD0000

# bootcmd is "mtd read kernel${bootflag} ...", so the variable alone selects the slot. Without
# the register write and the C94 word above, the vendor userspace's own boot handler still
# boots stock from kernelb (#0, jenkins@cudyrd1): the 15:29 3df fire did exactly that.
printf 'bootflag='; fw_printenv bootflag | cut -d= -f2
printf ' boot_reg='; cat /sys/devices/platform/sysenv/boot_reg; echo

sync
reboot
