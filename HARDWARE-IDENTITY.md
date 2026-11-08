# Hardware identity and UART limits (2026-11-08)

This page exists because the enclosure, the FCC filing and the posted board photos do not
identify this unit. Read it before treating the board as a WR3000 v1 or planning any UART or
U-Boot work.

## Identity

- The enclosure and label say **WR3000 v1**. That label is not a reliable hardware identifier.
- The PCB and firmware are the **HiSilicon "luofu" v2-class design**: Hi5671YV200 SoC plus
  Hi5622v100 Wi-Fi, 128 MB NAND and 128 MB DDR3, OpenWrt 22.03.6, kernel 5.10.201.
- Evidence from the live boot log: `U-Boot 2022.07 ... for luofu`; `hi_crg`, `hi-reset`,
  `hi_pcie`, `HSAN FMC Controller`, `hsan-watchdog-driver`, `hi5622v100_wifi.ko`; the DTS
  compatible is `hsan-luofu`. The stock image is `WR3000V2-R116-2.4.15-20251030-114751`, and it
  boots.
- The WR3000 v1 is a **MediaTek MT7981 (Filogic 820)** design and cannot boot the v2 image. The
  v1 FCC filing and board photos belong to that MediaTek board, which is why they do not match
  this PCB.
- The same HiSilicon luofu reference design is sold as the **Jeton AX3000 Core**
  (Hi5671YV200 + Hi5622v100) and the **V-SOL HG5013-4G** (`wrt_hg5013_4g_h2`); the Cudy
  WR3000 v2 is the same platform family. White-label units may not carry the Cudy FCC ID or
  Cudy board photos.
- The **Triductor TR6560** BSP is the same silicon family under the `triductor,tr6560` naming;
  this unit's own tree uses `hsan-luofu`. The BSP is a public source reference for the shared
  U-Boot logic, not evidence that this unit is the MediaTek v1 or a different board.

## Correct firmware

- Use the **WR3000V2-R116** image. A WR3000 v1 (MediaTek) image is wrong for this board.
- Recovered on 2026-11-08: official 2.4.15 and 2.5.24 images in `firmware/` (gitignored),
  rootfs extracted to `rootfs-2.4.15/` and `rootfs-2.5.24/`. `libbdinfo.so` and
  `auth_plugin_jwt.so` sha256 match the live `tmp_manifest.txt`.
- `.omo-secrets/` is absent from this checkout; the web admin password is not in the repo.

## UART and U-Boot, measured

Wiring: GND, TXD, RXD only, no VCC, 3.3V logic, 115200 8N1, FT232R at `/dev/ttyUSB0`.

The boot log shows:

    input <abort key> to stop autoboot in  1s

That is `CONFIG_AUTOBOOT_KEYED`. In stock U-Boot 2022.x (`common/autoboot.c`), the abort requires
`bootdelaykey` or `bootstopkey` from the environment, or the compiled
`CONFIG_AUTOBOOT_DELAY_STR` / `CONFIG_AUTOBOOT_STOP_STR`. `doc/README.autoboot` states that if
neither is specified there is no way to stop autoboot. The default environment in the 2.4.15
image sets `bootdelay=1`, `baudrate=115200`, `ipaddr=192.168.1.1`, `serverip=192.168.1.88`,
`bootcmd` and the bootmenu entries, but **no** `bootdelaykey` and **no** `bootstopkey`. Ctrl+C
only works with `CONFIG_AUTOBOOT_KEYED_CTRLC`, which this build does not have.

Measured:

- Enter and sustained Ctrl+C before and during the 1 s window do not abort; the kernel boots.
- Holding reset during power prints `RESET button is pressed for:  0 second(s)` and boots. A
  30 second hold triggers Linux `PRESET RESET` (`all led quick`, `PRESET RESET`,
  `reboot: Restarting system`). The button is handled by gpio-keys/userspace, not U-Boot.
- The Linux image starts no getty on `ttyS0`; after boot the console is output-only.

Conclusion: there is no general TTL key, break or timing trick. The only TTL key that could work
is the exact live-environment `bootstopkey` if the factory environment contains one, and that is
a vendor secret. Ways in are root over the LAN (the systime RCE) to read or set the environment,
a rebuilt U-Boot with a known stop key or `CONFIG_AUTOBOOT_KEYED_CTRLC`, or a hardware NAND read.

Evidence (gitignored, recreate if absent):

- `build/uart-logs/20261107T191003Z-poweron-uboot.log`
- `build/uart-logs/20261107T191715Z-uboot-ctrlc.log`
- `build/uart-logs/20261107T200727Z-button-test.log`

## Static analysis of the U-Boot image

- The U-Boot 2022.07 blob is inside the sysupgrade image at file offset `0x4000`, loaded at
  `0x80040000`.
- The abort message is entry ID `0x0b` in a data table at `0x8007d920`. Ghidra 12.2 (full
  decompile, 970 functions), rizin 0.8.2 and capstone find no code reference to that table; the
  analyzed code region ends at `0x8007bf0c` and the table is in data after it. Do not assume a
  direct string reference.
- The source-level behavior is from stock U-Boot 2022.x in the public TR6560 BSP
  (`https://github.com/BPI-SINOVOIP/THG6500-TAX2-OPENWRT-BSP`,
  `dl/u-boot-2022-03-15-0625aad7.tar.xz`, `common/autoboot.c`, `doc/README.autoboot`). The
  Cudy/Jeton U-Boot source itself is not published: Cudy's GPL page returns 404, and
  `JETON-GPL-EMAIL.txt` has no reply.
- A reference-walking helper is at `tools/ghidra/FindAbort.java`.

## Toolchain

Ghidra 12.2 with JDK 25 is installed at `/opt/ghidra_12.2_PUBLIC`; `ghidra` and
`ghidra-headless` are in `/usr/local/bin`. The repo lane reproduced the `hi_wdg.ko`
`hi_wdt_hw_set_timeout` calibration. See `tools/ghidra/README.md`.

## Practical consequences

- Do not flash a WR3000 v1 (MediaTek) image.
- Do not spend time on a TTL key without reading the live environment first; the default
  environment has none.
- The reset button is a configuration reset, not a bootloader entry.
- The practical root paths are the LAN RCE, a reflashed U-Boot, or a hardware NAND read.
