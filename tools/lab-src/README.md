# Lab kernel sources (snapshot, 2026-11-13)

The kernel work for this project lives in `build/linux-kbuild/linux-5.10.201`, which is
gitignored. This directory is the tracked copy of every file this project has modified or
added to that tree, so the work survives a fresh clone and a wiped `build/`.

It is a snapshot, not a patch: the files here are the complete sources as they stand.

## Layout

    arch/arm/mach-luofu/            luofu.c (mach, crumbs, watchdog pet shim, panic notifier)
                                    crg.c (clock gate + reset provider), Makefile, Kconfig
    arch/arm/boot/dts/              luofu-r116.dts (gmac/mdio enabled, rootfs_data 22 MiB)
    arch/arm/include/asm/           vermagic.h (drops the p2v8 tag so vendor modules match)
    drivers/watchdog/               luofu-wdt.c (vendor register map, hwver 2, 30 s)
    drivers/net/ethernet/luofu/     the GEMAC/MDIO/switch drivers
    drivers/net/ethernet/           Kconfig + Makefile entries for the above
    config/kernel.config            the exact .config of the last build (phase3bk)
    kbuild/init-vendorroot.c        the initramfs init (Phase C, keeper, dump shadow)

## Restoring into a kernel tree

Copy each file back over the same relative path in a vanilla 5.10.201 tree (or the vendor's
GPL drop), then:

    scripts/config --file .config ...   # or copy config/kernel.config to .config
    make ARCH=arm CROSS_COMPILE=<...> olddefconfig
    make ARCH=arm CROSS_COMPILE=<...> -j16 zImage

The initramfs init is compiled freestanding and embedded through CONFIG_INITRAMFS_SOURCE:

    arm-none-linux-gnueabihf-gcc -static -nostdlib -Os -march=armv7-a -mfloat-abi=hard \
        -o initramfs-site/init kbuild/init-vendorroot.c
    (cd initramfs-site && find . -print0 | cpio --null -o -H newc > ../initramfs-site.cpio)

## Build state at the time of this snapshot

phase3bk was the last image: CONFIG_EMBEDDED off, CONFIG_ARM_MODULE_PLTS=n, the vermagic.h
tag dropped. It does not boot on this board (see mem-entries.md, 2026-11-13 17:25). The last
image that boots and reaches the vendor userspace is phase3bi (PLTS=y), which is the same
sources with CONFIG_ARM_MODULE_PLTS=y.
