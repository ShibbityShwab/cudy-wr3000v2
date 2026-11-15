# Lab kernel sources (tracked mirror)

The kernel work lives in `build/linux-kbuild/linux-5.10.201`, which is gitignored.
This directory is the tracked mirror of every file this project has modified or added
to that tree, so the work survives a fresh clone or a wiped `build/`.

`FILES` is the manifest. `tools/sync-lab-src.sh` copies the manifest paths from the
live tree. `tools/check-lab-src.sh` compares them and then runs
`tools/check-lab-src-complete.sh`, which diffs the live tree against an unmodified
5.10.201 tree and fails if any modified source file is missing from `FILES`. Use
`tools/check-lab-src.sh --manifest-only` for a quick check; that mode does not prove
completeness. The complete check needs `VANILLA_TREE` or the
`build/linux-kbuild/dl/linux-5.10.201.tar.xz` tarball.

## Layout

- `arch/arm/Makefile`, `arch/arm/boot/dts/Makefile`, `arch/arm/mach-hisi/Kconfig`
  wire the machine and the board into the tree.
- `arch/arm/boot/compressed/head.S`, `arch/arm/kernel/head.S` carry the boot
  breadcrumbs and the TEXT_OFFSET fix.
- `arch/arm/kernel/module.c` keeps `module_alloc` in the near region so the vendor
  modules load without PLT sections.
- `arch/arm/mach-luofu/` is the mach, the clock/reset provider, and the watchdog pet.
- `arch/arm/boot/dts/luofu-r116.dts` is the board tree.
- `arch/arm/include/asm/vermagic.h` drops the p2v8 tag.
- `drivers/mtd/nand/luofu/` is the FMC driver and its Kconfig/Makefile wiring.
- `drivers/mtd/ubi/io.c` carries the `compat = 5` acceptance.
- `drivers/net/ethernet/luofu/` is the GMAC, MDIO, and Genius PHY drivers.
- `drivers/net/phy/Kconfig` exposes the PHYLINK prompt.
- `drivers/watchdog/` is the watchdog driver and wiring.
- `fs/jffs2/` carries the write-path, cleanmarker, and scan changes.
- `config/kernel.config` is the exact build config.
- `kbuild/init-vendorroot.c` is the initramfs init.

## Restore into a vanilla 5.10.201 tree

1. Extract `linux-5.10.201`.
2. Copy every path in `FILES` over the same relative path.
3. Copy `kbuild/init-vendorroot.c` into the build lane. It is compiled freestanding
   and embedded through `CONFIG_INITRAMFS_SOURCE`.
4. Copy `config/kernel.config` to `.config`, run `olddefconfig`, then `zImage` and
   `dtbs`.

`config/kernel.config` contains an absolute `CONFIG_INITRAMFS_SOURCE` path from this
workstation. Rewrite that line for the new host before building. The manifest check
prints a warning while it is absolute.

The initramfs init is built with:

```sh
arm-none-linux-gnueabihf-gcc -static -nostdlib -Os -march=armv7-a -mfloat-abi=hard \
  -o initramfs-site/init kbuild/init-vendorroot.c
(cd initramfs-site && find . -print0 | cpio --null -o -H newc > ../initramfs-site.cpio)
```

## What is not tracked

- Build artifacts (`.o`, `.a`, `.dtb`, `.mod`, `Module.symvers`).
- The two vendor modules used by the lab are in `../vendor-mods/`.
- The current slice and fire logs are under `build/` and are local-only.

This is a working snapshot, not a release image. It includes the lab breadcrumbs and
debug cells that the current experiments use. A release build must remove them; see
`PLAN-FULL-REVERSAL.md`.

## Last build

Do not hardcode a phase here. The live slice, the gate table, and the current blocker
are in [`../../STATUS.md`](../../STATUS.md).
