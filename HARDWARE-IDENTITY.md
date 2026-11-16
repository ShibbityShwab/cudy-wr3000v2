# Hardware identity and UART limits

**Updated:** 2026-11-17 (UART section rewritten from the 2026-11-16 swap measurement; earlier
UART text is superseded and kept only where it explains the history).

This page exists because the enclosure, the FCC filing and the posted board photos do not
identify this unit. Read it before treating the board as a WR3000 v1 or planning any UART or
U-Boot work.

## Identity

- The enclosure and label say **WR3000 v1**. That label is not a reliable hardware identifier.
- The PCB and firmware are the **HiSilicon "luofu" v2-class design**: Hi5671YV200 SoC plus
  Hi5622v100 Wi-Fi, 128 MB NAND and 128 MB DDR3, OpenWrt 22.03.6, kernel 5.10.201.
- Evidence from the live boot: `U-Boot 2022.07 ... for luofu`; `hi_crg`, `hi-reset`,
  `hi_pcie`, `HSAN FMC Controller`, `hsan-watchdog-driver`, `hi5622v100_wifi.ko`; the DTS
  compatible is `hsan-luofu`. The stock image is `WR3000V2-R116-2.4.15-20251030-114751`, and
  it boots.
- The WR3000 v1 is a **MediaTek MT7981 (Filogic 820)** design and cannot boot the v2 image. The
  v1 FCC filing and board photos belong to that board, which is why they do not match this PCB.
- The same HiSilicon luofu reference design is sold as the **Jeton AX3000 Core**
  (Hi5671YV200 + Hi5622v100) and the **V-SOL HG5013-4G** (`wrt_hg5013_4g_h2`); the Cudy
  WR3000 v2 is the same platform family. White-label units may not carry the Cudy FCC ID or
  board photos.
- The **Triductor TR6560** BSP is the same silicon family under the `triductor,tr6560` naming;
  this unit's own tree uses `hsan-luofu`. The BSP is a source reference for shared U-Boot
  logic, not evidence that this unit is the MediaTek v1 or a different board.

## Correct firmware

- Use the **WR3000V2-R116** image. A WR3000 v1 (MediaTek) image is wrong for this board.
- Recovered on 2026-11-08: official 2.4.15 and 2.5.24 images in `firmware/` (gitignored),
  rootfs extracted to `rootfs-2.4.15/` and `rootfs-2.5.24/`. `libbdinfo.so` and
  `auth_plugin_jwt.so` sha256 match the live `tmp_manifest.txt`.
- `.omo-secrets/` is present in this checkout and gitignored; the project SSH key is
  `.omo-secrets/router_ed25519`. Live values are never committed.

## UART: READ-ONLY - NEVER TRANSMIT (2026-11-16)

Wiring: GND, TXD, RXD only, no VCC, 3.3 V logic, 115200 8N1, FT232R at `/dev/ttyUSB0`. The
working wiring is the **swapped** pin pair.

Measured facts:

- **Router -> host works.** Five markers written to `/dev/ttyS0` on the box arrived on the host
  at 115200 8N1 with the swapped pins (224 bytes, `build/uart-logs/`).
- **Host -> router is dead.** Pin 3 delivered nothing (`rx:0` after 200 host bytes); the
  fault is the router-side RX path, and the line's resistor is burnt. The user has ruled out
  repair. Treat the link as permanently read-only.
- Earlier text on this page said the UART was "output-only" and suggested repairing the pin-3
  RX path. That suggestion is withdrawn: **do not attempt serial input, do not attempt a repair,
  and do not chase the U-Boot prompt.** The prompt is unreachable.
- Allowed: `stty` termios configuration (ioctls, no data) and reading bytes. Use
  `tools/uart-capture.sh`, which opens the tty read-only and writes an absolute path under
  `build/uart-logs/`. A zero-byte capture means the command/wiring is wrong, never a reason to
  start writing.
- The Linux console gate itself was solved earlier (kept here as history): the stock console
  login is gated by `bdinfo dbg`; `/lib/preinit/99_00_console` deletes the `::askconsole:`
  line unless it returns OK, and `/etc/rom_release` forces FAIL. Patching the overlay copy of
  `libbdinfo.so` so `bdinfo_check_dbg` at `0x2228` returns 0 keeps the line and starts
  `/sbin/askfirst`. That is why console *output* is available; it does not give serial input.
- The practical root path is SSH over the LAN; the recovery path is the physical RESET counter
  plus TFTP (see `BENCH-FACTS.md` section 4).

## RESET button and recovery (corrected 2026-11-16)

- The recovery trigger is the **RESET-button counter on a true power-on reset**: power off,
  hold RESET, power on still holding. The loader prints
  `RESET button is pressed for: 0/1/2 second(s)`, then `Resetting...`, then
  `recovery button press` and starts TFTP. A hold released early leaves `0 second(s)` and the
  box boots normally; the counter never appears on the watchdog resets the box does itself.
- Holding reset while powered on is a configuration reset, not a bootloader entry. The old
  sentence "the reset button is a configuration reset, not a bootloader entry" was true for the
  power-on hold used then; the recovery door is the power-on hold through the counter.
- U-Boot's `bootflag` fallback path is fragile: it has printed the header and then faulted
  inside U-Boot for both a 2.78 MB and a 2.96 MB kernel. Do not rely on the fallback as a
  rollback; the TFTP recovery is the door.

## U-Boot capture / static analysis (historical, still useful)

- The U-Boot 2022.07 blob is inside the sysupgrade image at file offset `0x4000`, loaded at
  `0x80040000`.
- The abort message is entry ID `0x0b` in a data table at `0x8007d920`. Ghidra 12.2 (full
  decompile, 970 functions), rizin 0.8.2 and capstone find no code reference to that table; the
  analyzed code region ends at `0x8007bf0c`. Do not assume a direct string reference.
- Source-level behavior is from stock U-Boot 2022.x in the public TR6560 BSP
  (`https://github.com/BPI-SINOVOIP/THG6500-TAX2-OPENWRT-BSP`,
  `dl/u-boot-2022-03-15-0625aad7.tar.xz`, `common/autoboot.c`, `doc/README.autoboot`). The
  Cudy/Jeton U-Boot source is not published: Cudy's GPL page returns 404 and
  `JETON-GPL-EMAIL.txt` has no reply.
- The loader takes only FIP packages (`bootcmd=mtd read kernel${bootflag} ${loadaddr};
  bootfip ${loadaddr}`); our slice is a uImage plus the fixed 40,732-byte FIP/DTBO trailer.
- A reference-walking helper is at `tools/ghidra/FindAbort.java`.

## Toolchain

Ghidra 12.2 with JDK 25 is installed at `/opt/ghidra_12.2_PUBLIC`; `ghidra` and
`ghidra-headless` are in `/usr/local/bin`. See `tools/ghidra/README.md`.

## Practical consequences

- Never flash a WR3000 v1 (MediaTek) image.
- Never transmit on the UART; capture read-only.
- Do not spend time on a TTL key: the U-Boot prompt is unreachable and the router's RX pad never
  receives.
- The practical root paths are the LAN RCE, a reflashed U-Boot, or a hardware NAND read; the
  recovery path is the physical RESET counter plus TFTP.
