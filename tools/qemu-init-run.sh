#!/bin/bash
# qemu-init-run.sh - boot our kernel in QEMU and run the tracked init as PID 1.
#
# This is the off-device debugger for the initramfs init. It builds a QEMU-capable
# kernel in build/linux-kbuild/qemu-src (a copy; the device tree is never touched),
# compiles tools/lab-src/kbuild/init-vendorroot.c static, and runs it as rdinit.
#
# The 3df init's wfile() verdict reaches /dev/kmsg, so every call prints on this
# console. That is the readout the bench could not see: the box has no console, and
# the pstore ring is scrubbed by the stock boot.
#
# usage: tools/qemu-init-run.sh [--keep]
#   --keep  reuse the existing qemu-src build instead of reconfiguring it
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
KB=$ROOT/build/linux-kbuild
SRC=$KB/qemu-src
TC=$KB/toolchain/bin/arm-none-linux-gnueabihf-
export ARCH=arm CROSS_COMPILE=$TC
KEEP=0
[ "${1:-}" = "--keep" ] && KEEP=1

if [ -d "$SRC" ] && [ "$KEEP" -eq 1 ]; then
    :
elif [ -d "$SRC" ]; then
    make -C "$SRC" -s zImage
else
    cp -a "$KB/linux-5.10.201" "$SRC"
    ( cd "$SRC" && make -s mrproper )
    cp "$SRC/arch/arm/configs/hisi_defconfig" "$SRC/.config"
    cd "$SRC"
    scripts/config --enable ARCH_LUOFU --enable ARCH_VEXPRESS \
        --enable SERIAL_AMBA_PL011 --enable SERIAL_AMBA_PL011_CONSOLE \
        --enable MTD_UBI --enable MTD_UBI_BLOCK --enable MTD_PSTORE \
        --enable PSTORE --enable PSTORE_BLK --enable MTD_RAW_NAND --enable MTD_NAND_LUOFU \
        --disable GCC_PLUGINS --enable DEVTMPFS --enable DEVTMPFS_MOUNT \
        --enable BLK_DEV_INITRD \
        --set-str CMDLINE "console=ttyAMA0 earlycon=pl011,0x9000000 rdinit=/init"
    make -s olddefconfig
    make -s -j"$(nproc)" zImage
fi

R=/tmp/qir-3df
rm -rf "$R" && mkdir -p "$R"
"$TC"gcc -static -nostdlib -Os -march=armv7-a -mfloat-abi=hard \
    -o "$R/init" "$ROOT/tools/lab-src/kbuild/init-vendorroot.c"
( cd "$R" && find . -print0 | cpio --null -o -H newc 2>/dev/null | gzip -9 > /tmp/qir-3df.cpio.gz )

exec timeout 45 qemu-system-arm -machine virt -cpu cortex-a15 -m 512M -smp 1 \
    -nographic -no-reboot -kernel "$SRC/arch/arm/boot/zImage" \
    -initrd /tmp/qir-3df.cpio.gz \
    -append "console=ttyAMA0 earlycon=pl011,0x9000000 rdinit=/init"
