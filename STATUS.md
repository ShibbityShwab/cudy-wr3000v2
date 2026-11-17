# STATUS - Cudy WR3000 v2.0

**Updated:** 2026-11-17 08:50 +07
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

## 3. Current blocker: our kernel now boots, but userspace wedges after procd init

The 3dh regression is FIXED and validated on hardware. The crash was a NULL deref in
`luofu_early()`: the mach `.init_early` hook called `ioremap()` from `setup_arch` before `mm_init()`
created the kmalloc caches; with the new `CONFIG_SLAB`+`CONFIG_TRACING` config, `kmalloc` goes through
`kmem_cache_alloc_trace(kmalloc_caches[..])` and the NULL cache pointer faulted. `3df`/`3dg` booted
because they had no `CONFIG_TRACING`. The ioremap/crumb/bootreg-flip work now happens in
`luofu_early_crumb()` (early_initcall, after `mm_init`), and the fixed slice `3dn` (md5
`984b0ac9...`) booted our kernel: earlycon, `luofu-fmc` probe, 18 partitions, `Run /init` at 14.45 s,
the seven `/vendor/upper ... OK` shadow lines, and `procd: - init -` at 19.5 s.

The new blocker, measured in that same boot: after procd init there is no further userspace output and
at 108 s / 171 s the kernel reports `rcu_sched` stalls with CPU0 stuck (the lab watchdog pet timer keeps
the hardware watchdog fed, so the box does not reset). `procd` stalled before rc.d, so even the guarded
auto-recovery hook never ran. The box is currently hung on the `3dn` kernel and needs the physical
RESET + TFTP recovery (running card below). This is a userspace-stage bug, not the early-boot one.

## 4. Next action

1. **Recover the box** with the physical RESET + TFTP card (`tools/recovery-card.sh`); the TFTP server
   is armed with `recovery.bin` (md5 `421114c8...`). After recovery the overlay is wiped: restart
   dropbear through the broker lane and reinstall the project key.
2. Diagnose the post-procd RCU stall. Compare with the healthy `3df` boot (no TRACING/SLAB); suspects
   are the TRACING/TASKS_RCU config block and the lab pet/watchdog interplay. Instrument one variable
   at a time; use the earlycon slice as the base.
3. For unattended test builds, make a hang self-resetting: stop petting the hardware watchdog in
   diagnostic builds so a hang becomes a 30 s reset -> U-Boot failover -> healthy stock, instead of a
   box that must be touched.
4. Only then re-fire for the vendor-stack goal (stage the patched modules first so a booting kernel
   brings its network up).
5. Keep the recovery door armed and never fire without a written single-variable plan.

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