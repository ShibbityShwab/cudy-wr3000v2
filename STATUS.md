# STATUS - Cudy WR3000 v2.0

**Updated:** 2026-11-17 08:10 +07
**Pins are not written here.** Derive them with `git rev-parse --short HEAD` and
`git -C opensource rev-parse --short HEAD`.
**This is the only live status page.** Regenerate it; do not append to it. The physical
invariants live in `BENCH-FACTS.md`; the procedure is `RUNBOOK.md`.

## 1. Bench (re-verified read-only 2026-11-17 07:35 +07)

- **Box: vendor stock, healthy.** OpenWrt 22.03.6 revision 2.4.15, stock kernel
  `5.10.201 #0 SMP Sat Nov 25 18:18:57 2023`, 2 wiphys (`phy0`/`phy1`), 40 `hi_` modules,
  calibration loaded and written on both bands (`hwifi_rf_cali_file_load_{2g,5g} succ`),
  SSH on the project key. Verified: `bootflag=b`, `boot_reg=0x11`, no `.omo-off`
  leftovers, overlay upper empty of staged modules (a recovery emptied it).
- **Host bench link:** `enp195s0f3u1` UP at 1 Gbps, NetworkManager-unmanaged, carrying
  `192.168.1.88/24` and `192.168.10.44/24`. Verified with `tools/bench-link.sh` (PASS).
  NetworkManager re-managed the adapter overnight despite the drop-in; `bench-link.sh --apply`
  now also reloads NetworkManager so the drop-in takes effect immediately. The stale broker HTTP
  server that had been serving the repo root on :8000 since 2026-11-15 was stopped on 11-17
  (`tools/bench-teardown.sh --apply`).
- **Recovery door: READY host-side, physical trigger.** A TFTP server from the previous session
  is still listening on UDP 69 and `tftp/recovery.bin` matches md5
  `421114c8ea999c925b7aa79cc548af81`; treat it as armed only after
  `tools/recovery-card.sh` says READY. Recovery itself is physical (RESET counter +
  power-on) - `BENCH-FACTS.md` section 4.
- **UART: READ-ONLY.** `/dev/ttyUSB0` exists; router console output reaches the host with the
  swapped pins, host-to-router TX is dead (burnt resistor). Use `tools/uart-capture.sh` and
  never transmit - `BENCH-FACTS.md` section 3.
- **Latest build (local only, NOT fired):** `build/linux-kbuild/luofu-slice-phase3dl.bin`
  (3,005,396 bytes, md5 `f7b2eb41a074df9fd6017e6179a446b0`): the 3dh device tree
  (`336ba39e...`) plus the console-logging init (`6464a08d...`). Rebuild with
  `build/linux-kbuild/build-3dl.sh`, which refuses to run unless the DTB is the 3dh blob.
- **Guards:** `tools/check-init-shadow.sh` PASS; `tools/check-lab-src.sh --manifest-only`
  PASS (36 files). Both are source-level guards, not artifact proofs.

## 2. Gates (2026-11-14)

| gate | state | receipt |
| --- | --- | --- |
| **G1** FMC reads real flash | GREEN | page-0 magic `UBI#`; level-7 MTD probe found the partition, the EC magic, `vid_hdr_offset = 0x800`, and `PEB0+0x800 = 'U'` |
| **G2** program path | GREEN | a page written by our kernel read back byte-exact through the vendor driver |
| **G3** our kernel + real rootfs + userspace | GREEN 2026-11-14 | vendor preinit, `mount_root`, procd and the full rc.d chain run on our kernel from the squashfs root |
| **G4** Ethernet on our kernel | GREEN via vendor modules | vendor switch/MDIO/PHY/MAC modules load as patched modules; `eth2` up 1 Gbps, `br-lan` 192.168.10.1, ping 3/3. Our `luofu-mdio`/`luofu-gmac` also carry a link, but the bound PHY driver is the vendor's `hi_kphy`: **M2 ("no vendor network modules") is NOT met** |
| **G5** Wi-Fi on our kernel | vendor-only | the vendor modules provide the radio; no wiphy from our driver |
| **G6** sustained uptime | GREEN 2026-11-14 | the reset was a userspace watchdog race, not a panic; the initramfs keeper holds the 25-minute timer |

These are bench-reversal gates. They are **not** upstream artifacts; see section 5.

## 3. Current blocker: the 3dh-class kernel does not start (this is not a slot/delivery problem)

Corrected 2026-11-17 from the captures already on the host plus an offline payload analysis. No
new fire was run to establish this.

**3df and 3dg ran our kernel on hardware.** Their captures contain our kernel's own banners and
our init's own output: `luofu-fmc 10a20000.spi-nand`, `luofu-gmac` and the `luofu: seed test` /
`overlay test` lines. 3df (fire 7, 05:28) reached userspace and the shadow writes landed
(`build/linux-kbuild/waves/3df/fire7.md`); 3dg (14:31 capture) ran our kernel with the vendor
modules refusing on 130+ unknown symbols.

**3dh, 3di and 3dk never started, in any captured attempt.** U-Boot reads our uImage every time
(`Image Name: Linux-5.10.201`, `Data Size` 2,964,240 / 2,964,334 / 2,965,176, load/ep
`0x80608000`), then the box resets with no kernel output and no U-Boot failure string. Every
`Uncompressing Linux` in those captures is the stock 4,294,096-byte fallback image, which then
panics 10-15 s later on the fallback DTBO path.

The variables that are **not** the cause:
- Boot path: the successful 3df attempts and the failing 3dh attempts used the same
  `bootflag=b`, `boot_reg=0x21`. Countdown vs fallback is not the variable.
- DTB and trailer: every slice has the same `luofu-r116.dtb` (md5 `336ba39e...`) and the same
  fixed 40,732-byte FIP/DTBO trailer.
- Corrupt image: the 3dh payload decompresses offline to a valid 9,810,020-byte Image (3df:
  8,135,904 bytes), and its xz stream is complete (no `Uncompressing Linux` is expected from
  our build; the decompressor's `putstr` is compiled out of this config).
- Delivery lane / slot: U-Boot loads the image from the slot it was told to read.

**The variable is the kernel build.** The kernel C source is identical between the 3df-era commit
and the 3dh-era commit; the only delta is the kernel `.config` captured in commit `cca5be5`:
`CONFIG_COMPILE_TEST=y` (with its broad side effects), `CONFIG_SLAB=y` instead of SLUB,
`CONFIG_TRACING`/`CONFIG_FTRACE`/`FRAME_POINTER`/`UNWINDER_FRAME_POINTER`, and the cache
allocator/frame-pointer changes those imply. The first kernel built with that set (3dh) never
boots. The failure is a silent early-boot crash **before the kernel registers its console at
~2.6 s** - the U-Boot cmdline has a bare `earlycon` with no address and the earlycon lookup
fails, so 0.0-2.6 s output is lost, not absent.

Consequences for the record:
- The 2026-11-16 15:45 claim that 3dh loaded the vendor stack on our kernel is a **stock-boot
  misattribution** (the stock image loads the same vendor modules); the ShuangTa PCIe panic in
  the 17:35 entry belongs to the stock fallback boot. The ledger correction is appended below
  this STATUS update.
- The 18:25 "write 3dl to `kernela`" next step cannot work: 3dl is built from the same 3dk
  kernel class and would fail to start in any slot. Do not fire it.
- The last kernel known to run on this hardware is the 3df/3dg class. A booting kernel must be
  recovered before the PCIe/pinctrl and vendor-stack work can continue.

## 4. Next action

1. **Diagnostic slice is built and ready (host-side).** `3dm` = the 3dl kernel plus one
   behavioural delta, an explicit earlycon in the built-in cmdline:
   `build/linux-kbuild/luofu-slice-phase3dm.bin`, 3,005,748 bytes, md5
   `ba5fd5b2fd9146157cf5d03c4a7b69dc` (zImage `95ce2f31...`, init `6464a08d...` = the 3dk
   console-logging init, DTB `336ba39e...`, trailer verified). Build script:
   `build/linux-kbuild/build-3dm.sh`; it restores the 3dl `.config` afterwards and
   `check-lab-src` PASSes. This is a diagnostic artifact, not a release candidate.
2. **One attended fire of `3dm`** (human at the bench; physical RESET/TFTP is the way back):
   - preconditions: `tools/bench-link.sh` PASS, `tools/recovery-card.sh` READY, a read-only
     capture armed, and `fire-preflight.sh` PASS (it enforces all of these + `--attended`);
   - optional resilience: stage the patched vendor modules first (`--stage lab`) so a booting
     kernel brings its network up and the box can be restored over SSH instead of TFTP;
   - command: `tools/fire.sh ssh --slice "$PWD/build/linux-kbuild/luofu-slice-phase3dm.bin"
     --slot b --label 3dm --attended --detach`, then read
     `build/uart-logs/<ts>-uart-3dm.log`.
   Outcomes: (a) earlycon output appears -> the crash point is named and the fix is local;
   (b) still dark -> the crash is before earlycon setup (decompressor/very early stub), and the
   next diagnostic is a DEBUG_LL build plus the 3df-era `.config` as the positive control.
   Do not repeat the fire without a new variable.
3. Only after a kernel boots: bring up the vendor stack (the real reason `SLAB`/`GENERIC_PINCONF`
   were wanted), then the 3dk per-module kmsg logging, then the PCIe/pinctrl node. The
   slot/delivery question (B vs A) is not the blocker and becomes relevant only after a kernel
   starts.
4. Re-stage the patched modules only when the test needs the vendor stack:
   `SLICE=... tools/box-provision.sh --bdinfo dumps/router-20261108/bdinfo.bin --stage lab`
   (needs `/tmp/vmods` or `PATCHED=`; pull the stock set read-only from the box).
5. Keep the stock-health checks; no fire unattended, and no fire without a written plan.

## 5. Reading the console (read-only)

```sh
tools/uart-capture.sh start --label <label> --timeout 900   # detached, absolute log path
tools/uart-capture.sh check
```

The script opens the tty read-only and never sends bytes. Do not use
a read-write open of the tty (the `3<>` form), `screen`, `minicom`, or a typed key:
host-to-router TX is dead and
must not be attempted. A capture is evidence only when the log line that identifies the image
is quoted (uImage `Data Size`/`Image Name`, or `Uncompressing Linux` for stock).

## 6. Evidence

[`EVIDENCE-INDEX.md`](EVIDENCE-INDEX.md) maps claims to artifacts and regeneration commands.
[`CURRENT-TRUTHS.md`](CURRENT-TRUTHS.md) is the curated summary; the ledger
(`mem-entries.md`, index in `mem-entries-INDEX.md`) is the long form. The newest dated
entry wins over any older claim.

## 7. History

[`docs/archive/README.md`](docs/archive/README.md). Retired pages include
`STATE-2026-10-30.md`, `STATUS-2026-11-12.md`, `START-HERE-2026-11-15.md`, and
`PROGRESS-2026-10-15.md`.