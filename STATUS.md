# STATUS - Cudy WR3000 v2.0

**Updated:** 2026-11-17 00:05 +07
**Pins are not written here.** Derive them with `git rev-parse --short HEAD` and
`git -C opensource rev-parse --short HEAD`.
**This is the only live status page.** Regenerate it; do not append to it. The physical
invariants live in `BENCH-FACTS.md`; the procedure is `RUNBOOK.md`.

## 1. Bench (verified read-only 2026-11-16 23:52 +07)

- **Box: vendor stock, healthy.** OpenWrt 22.03.6 revision 2.4.15, stock kernel
  `5.10.201 #0 SMP Sat Nov 25 18:18:57 2023`, 2 wiphys (`phy0`/`phy1`), 40 `hi_` modules,
  calibration loaded and written on both bands (`hwifi_rf_cali_file_load_{2g,5g} succ`),
  SSH on the project key. Verified: `bootflag=b`, `boot_reg=0x11`, no `.omo-off`
  leftovers, overlay upper empty of staged modules (a recovery emptied it).
- **Host bench link:** `enp195s0f3u1` UP at 1 Gbps, NetworkManager-unmanaged, carrying
  `192.168.1.88/24` and `192.168.10.44/24`. Verified with `tools/bench-link.sh` (PASS).
  The stale broker HTTP server that had been serving the repo root on :8000 since
  2026-11-15 was stopped during this audit (`tools/bench-teardown.sh --apply`).
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

## 3. Current blocker: the delivery lane is unresolved

What is measured (read from captures on this host, no new fire):

- U-Boot **does read our uImage**. The 3dk capture
  (`build/uart-logs/20261116T111510Z-fire-3dk.log`) prints
  `Image Name: Linux-5.10.201`, `Data Size: 2965176`, `Load Address: 80608000` 37 times;
  the 3dh capture prints `Data Size: 2964240`. Stock is `4,294,096` and prints
  `Uncompressing Linux`.
- **No kernel console output follows our uImage load.** The `3dk` init's
  `<6>load hi_* fd=.. ret=..` lines were never observed (`grep -c 'load hi_'` = 0); every
  cycle that reaches `Uncompressing Linux` is the stock fallback boot. The ShuangTa PCIe
  panic in the 17:35 entry belongs to that stock fallback boot, not to our kernel.
- **Correct validity rule:** our slice is an uncompressed uImage and does not print
  `Uncompressing Linux`; only the stock image does. A reading is ours only when U-Boot
  prints **our** `Data Size`/`Image Name` and kernel output follows. `LESSONS.md` rule 20.
- The last fire (3dk, 18:15 local) wrote `kernelb` with `bootflag=b`, `boot_reg=0x21`;
  it is a non-result for the kernel question and cost one recovery cycle (19:05 entry).

What is **not** established, and is the open question:

- The 18:25 ledger entry says the next step is to write 3dl to `/dev/mtd11` (`kernela`),
  claiming "the path that boots cleanly is the AB one". `build/linux-kbuild/waves/3dk/
  recovery-3dk.md` (17:35) says no image of ours can be loaded until the bootloader is
  replaced. Both cannot be true. Neither is proven by a receipt.
- There is no measured slot-A manual handover value. `tools/fire-device.sh` now refuses a
  slot-A fire unless `BOOT_REG` is supplied from a written plan; do not invent one.
- The NAND is degraded (ECC errors, JFFS2 read/erase failures in the captures). Flash writes
  are wear-limited; every fire must be written down before it is run.

## 4. Next action

1. **Resolve the delivery mechanism on paper, no fire.** Compare the 3dh
   (`20261116T075623Z-3dh-fire.log`) and 3dk (`20261116T111510Z-fire-3dk.log`) cycles and
   write into this section: target slot, `bootflag`, `boot_reg`, the exact expected marker
   (our uImage `Data Size` + kernel line), which path reaches the slice (countdown vs
   fallback), and what is single-variable about the next test. If it requires a cold power-on
   reset, say so explicitly. Until that is written here, do not fire.
2. Re-stage the patched vendor modules only if the next test needs the vendor stack:
   `SLICE=... tools/box-provision.sh --bdinfo dumps/router-20261108/bdinfo.bin --stage lab`.
   This needs the module set at `/tmp/vmods` or `PATCHED=` (pull it read-only from the box;
   see the script's error text).
3. Then one fire, attended, with `tools/fire-preflight.sh` PASS, a read-only UART capture
   running, the recovery card READY, and a human able to power-cycle the box.
4. **Upstream track (separate, not blocked by the bench):** no OpenWrt target/DTS/image
   recipe/driver series exists; the Wi-Fi + LAN-switch + GPL source questions are the gating
   programme, and the published half still needs its vendor-object cleanup and GPL status
   reconciliation. See `opensource/docs/ROADMAP-OPENWRT.md` and `EVIDENCE-INDEX.md`.

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
