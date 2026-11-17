# STATUS - Cudy WR3000 v2.0

**Updated:** 2026-11-18 06:50 +07
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

## 3. Bench line ceiling reached: v17 boots the vendor userspace and creates br-lan, but the vendor HYFI/bridge userspace contract is a multi-step port

v17 (no hyfi-bridging preload, ABI-correct bridge hook pointer variables, bridge/netfilter/WEXT/
tracepoints config, WAN-rootif bypass) fired cleanly: no U-Boot abort, all 19 modules ret=0,
S20network OK, eth2 up, br-lan created. Then HSLINK repeatedly created and destroyed br-lan
(t=34-35 s) and userspace went silent (~54 s), no network. The RE established why: hyfi_bridging
needs the vendor sk_buff ABI (+0x74/+0x78) and vendor bridge patches (hook call sites,
net_bridge cache) that our tree does not contain - a multi-step port, not a single fire.

The box currently needs the physical RESET+TFTP recovery. Bench fires are stopped.

## 4. Next action

1. Recover the box (RESET-hold TFTP; server armed) and leave it on clean stock.
2. Non-bench deliverables: OpenWrt target/DTS/image recipe and the GPL source request; evidence
   consolidation (EVIDENCE-INDEX, captures, slices) for the reversal report.
3. Optional separate project: the vendor sk_buff + bridge/HYFI port, with a kbuild offsetof probe
   and staged single-variable fires; do not resume bench fires before that design exists.

## 4. Next action

1. Offline (in progress): reverse hyfi_bridging's init/netlink path and the vendor bridge hooks;
   determine the real contract (tables/callbacks/net_device fields), then implement or patch.
   No bench fires until that report gives a single concrete change.
2. Then one single-variable fire: same kernel line + hook implementation. Expected: br-lan forms
   and the LAN/wifi userspace reaches its normal state. Stock fallback is safe (transient masks,
   clean overlay handling).
3. Upstream track remains untouched: OpenWrt target/DTS/image recipe and GPL-source request are the
   next non-bench deliverables.

## 4. Next action

1. Recover the box (RESET-hold TFTP). Do not refire until a new single-variable change is written.
2. Offline: reverse the hi_swa rootif check (the "failed to add rootif" path) and the wifi/HSLINK
   app sequence around the ~33 s hang; decide whether the lab gmac can satisfy rootif directly.
3. Next fire options: (a) lab gmac kept + vendor wifi app masked, to isolate LAN bring-up from the
   wifi userspace; or (b) rootif requirement implemented. One variable per fire, with the
   persistent capture running.

## 4. Next action

1. Recover the box (RESET-hold TFTP; server armed). Re-stage the 58 patched modules and the overlay
   (kmodloader no-op, S99nft-qos mask, rc.local keepalive), then continue.
2. v9 lane: give the netdevs to the vendor driver - add hsan,himac / hsan,mdio compatibles to the
   gmac/mdio DT nodes, disable CONFIG_LUOFU_GMAC/MDIO/PHY, preload hi_kmdio -> hi_kphy -> hi_kmac,
   and check whether HSLINK rootif accepts them. If the vendor gmac driver cannot probe from our
   DT, reverse the rootif check in hi_swa.ko and make the lab gmac satisfy it.
3. Write the v6/v7/v8 results into EVIDENCE-INDEX with the capture logs; keep the watchdog claim
   honest (selector works, reset does not yet).

## 4. Next action

1. Recover the box: power off, hold RESET, power on holding, hold through the counter -> TFTP
   recovery (server is armed, recovery.bin md5 421114c8...). Then restore SSH via the broker and
   re-stage the patched modules (the recovery wipes the overlay).
2. Install the early bootflag=a fallback rc.d script, arm the guarded hook, and fire 3dq v2
   (slice md5 77606ead...). Expected: ksecurec then the hi_* chain load; if eth2/br-lan answers,
   SSH on our kernel confirms the first vendor-userspace boot on our own kernel.
3. If the chain still breaks, the next dependency order is derived from the module kmsg lines; do
   not fire without a new single-variable writing.
4. Then the upstream track (target/DTS/image recipe) and the ledger/commit backlog.

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