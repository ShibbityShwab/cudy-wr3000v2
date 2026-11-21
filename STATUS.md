# STATUS - Cudy WR3000 v2.0

**Updated:** 2026-11-22 00:10 +07
**Pins are not written here.** Derive them with `git rev-parse --short HEAD` and
`git -C opensource rev-parse --short HEAD`.
**This is the only live status page.** Regenerate it; do not append to it. The physical
invariants live in `BENCH-FACTS.md`; the procedure is `RUNBOOK.md`.

## 1. Bench (re-verified 2026-11-21 12:50 +07)

- **Box: running OUR image (canonical 2-CPU baseline 974e6ca6), healthy.** OpenWrt 6.18.60,
  smp: Brought up 1 node, 2 CPUs (online 0-1, CPU1 mpidr 80000001), br-lan 192.168.1.1/24 up,
  SSH works, /overlay on ubifs rw, 15-min soak 0 failures, reboot returns with 2 CPUs (pair b
  recorded). No Oops/panic/BUG/WARNING (only the literal panic=0 cmdline text).
- **Host bench link:** enp195s0f3u1 UP at 1 Gbps, NetworkManager-unmanaged, carrying
  192.168.1.88/24 (TFTP) and 192.168.10.44/24 (stock LAN/broker). Re-applied 2026-11-21 after an
  overnight carrier/IP loss looked like a box hang - the box was alive (UART heartbeat); bench
  rule: check carrier/bench-link.sh before attributing a hang to the kernel.
- **Recovery door: READY host-side, physical trigger.** TFTP listens on UDP 69 and
  tftp/recovery.bin matches md5 421114c8ea999c925b7aa79cc548af81; trigger is the physical RESET
  counter on a true power-on reset, then recovery.bin. UART capture is stopped; start it with
  tools/uart-capture.sh for any attended boot. Stock pair A is still available if a stock boot is
  needed (write boot selector a / cell 0x10 and reboot).
- **Images on flash:** pair B = canonical 974e6ca6 (our 6.18 target); pair A = vendor stock. The
  boot-pair recorder re-records the running pair so our image survives reboot. Debug builders
  (canonical / maxcpus=1 / lockdep) are archived in staging-fi/ as diagnostics only.

## 2. Gates (bench-reversal history, 2026-11-14)

| gate | state | receipt |
| --- | --- | --- |
| **G1** FMC reads real flash | GREEN | page-0 magic `UBI#`; level-7 MTD probe found the partition, the EC magic, `vid_hdr_offset = 0x800`, and `PEB0+0x800 = 'U'` |
| **G2** program path | GREEN | a page written by our kernel read back byte-exact through the vendor driver |
| **G3** our kernel + real rootfs + userspace | GREEN 2026-11-14 | vendor preinit, `mount_root`, procd and the full rc.d chain run on our kernel from the squashfs root |
| **G4** Ethernet on our kernel | GREEN via vendor modules | vendor switch/MDIO/PHY/MAC modules load as patched modules; `eth2` up 1 Gbps, `br-lan` 192.168.10.1, ping 3/3 on the 2026-11-14 stack. Our `luofu-mdio`/`luofu-gmac` also carry a link, but **M2 ("no vendor network modules") is NOT met** |
| **G5** Wi-Fi on our kernel | vendor-only | the vendor modules provide the radio; no wiphy from our driver |
| **G6** sustained uptime | GREEN 2026-11-14 | the reset was a userspace watchdog race, not a panic; the initramfs keeper holds the 25-minute timer |

These are bench-reversal gates. They are **not** upstream artifacts; see section 5.

## 3. Current state: bench line at its documented ceiling; the upstream design docs now exist

**Bench lab-kernel line (v6-v17, 2026-11-17/18):** our kernel boots the vendor userspace, the full
vendor module stack loads (`ret=0`, including `hi_kpie`, `hi_swa`, the `hi_lsw_*`/`hi_kcfe_*`
chain, `hi_netif`/`hi_kmsgcenter`/`hi_kipc`), eth2 comes up at 1 Gbps and `br-lan` is created.
v17 removed the HYFI crash (no hyfi preload, ABI-correct bridge hook pointer variables) but HSLINK
then created/destroyed `br-lan` in a loop and userspace went silent; the vendor HYFI/bridge
contract needs the vendor `sk_buff` ABI (+0x74/+0x78) and the vendor bridge patches (hook call
sites, `net_bridge` cache), i.e. a multi-step port. The full evidence trail is in
`EVIDENCE-INDEX.md` and the ledger entries 2026-11-17 08:45/10:15/18:00/18:55/20:15/20:40 and
2026-11-18 06:50.

**Upstream track (2026-11-18):** the missing design layer now exists, but there is still **no
OpenWrt target, board DTS, image recipe, driver series or upstream submission**.

- `opensource/docs/TARGET-DESIGN.md` - concrete design: `target/linux/hisilicon` + `luofu`
  subtarget, FIP trailer/dual-slot/sysupgrade recipe, DTS conversion plan, per-driver upstream
  readiness, acceptance criteria.
- `opensource/docs/ROADMAP-OPENWRT.md` - refreshed to the 2026-11-18 reality (phase plan +
  status notes; superseded claims point at the ledger).
- `opensource/docs/GPL-REQUEST.md` - status 2026-11-18: original request sent 2026-10-01, still
  no reply or evidence copy; ready-to-send follow-up, escalation ladder, tracking table and an
  updated requested-artifacts checklist.
- `opensource/docs/VENDOR-SKB-BRIDGE-PORT.md` - feasibility/design spec for the optional hybrid
  vendor HYFI/bridge lane (ABI deltas, options, offset probe, staged fires, acceptance criteria).
- `opensource/docs/DOCUMENTATION-HUNT.md` - refreshed open-gaps table.
- `opensource/target-skeleton/` + `opensource/docs/TARGET-SKELETON.md` - target files from the
  design (target/linux/hisilicon/luofu Makefiles/Kconfig/profile/board.d, a draft DTS, the
  `fip-slice.py` tool, **and a kernel platform patch series**). Status: **structure + kernel-config
  validated, not compiled into a correct image** - copied into OpenWrt `main` (commit `27663a0`):
  `make defconfig` PASS, `make target/linux/prepare` RC=0 (kernel 6.18.60); patches-6.18/ adds
  arch/arm/mach-hisilicon (clean UP-only machine descriptor, ARCH_LUOFU via the existing
  ARCH_HISI) + Kconfig/textofs; `config-6.18` was canonically re-derived (281-symbol delta,
  idempotent) with the tree's own GCC 14.4 toolchain and the machine code compiles with it. Patch `003` fixes the last compile blocker
  (`TEXT_OFFSET=0x00608000` is not an ARM rotated immediate) with the kernel's own `mov_l`
  idiom, and **`make target/linux/compile` now reaches RC=0** with the real offset, no
  workarounds: zImage produced (local-only evidence, sha256 `45ad00d5...`), linked/load
  address verified as `0x80608000` (mkimage `-a/-e 0x80608000`). This is still **not a
  deliverable image**: no FIP slice, rootfs, target image, dtbs_check or boot
  (`opensource/docs/SKELETON-SMOKE.md`).
- **FIP trailer decoded and generation implemented (2026-11-18, offline):** U-Boot `bootfip`
  fully decoded (gate, 96-byte descriptor, 11-row vendor/board match table, applier validation
  order; uImage CRCs are not checked). `target-skeleton/tools/fip-slice.py make-trailer` now
  generates a fail-closed trailer from user-supplied base DTB + overlays and reproduces the vendor
  2.4.15 (40,828 B) and 2.5.24 containers byte-for-byte; the bench lane still copies its fixed
  40,732-byte artifact. A novel generated trailer still needs **one attended boot**.
  Details: `opensource/target-skeleton/docs/TRAILER-FORMAT.md`.

- **First own-artifact FIP kernel slice assembled and structurally validated (2026-11-18, host-only).**
  `target-skeleton/tools/build-kernel-slice.sh` compiles our draft DTB + a loader-match stub
  overlay (`vendor_id=hsan`, `hsan-luofu`, `board_id=3`, no-op fragment), builds the uImage
  (`-a/-e 0x80608000`, `Linux-6.18.60`), generates a 9,278 B trailer with `fip-slice.py
  make-trailer`, assembles the slice and validates it: size 3,214,542 B, gate `0xd7b7ab1e` at
  `0x310ba8`, 5,436,210 B under the slot limit, reproducible byte-for-byte. This is **not a
  deliverable image and has never been booted**; the bench fire preflight still expects the fixed
  40,732-byte vendor trailer, so adopting this lane needs one attended boot plus preflight/recipe
  updates. Details: `opensource/docs/SKELETON-SMOKE.md` (2026-11-18 slice section).

- **First drivers ported to 6.18 with bindings (2026-11-18, host-only).** `patches-6.18/004`
  adds the CRG clock+reset controller (`drivers/clk/hisilicon/crg-luofu.c`, 16 gate clocks,
  2-cell reset controller, `include/dt-bindings/clock/hisilicon,luofu-crg.h`, YAML binding) and
  `005` adds the watchdog (`drivers/watchdog/luofu-wdt.c`, 6.18 watchdog API, syscon regmap child,
  YAML binding). The shared `0x14880000` page is modelled as one `syscon`+`simple-mfd` node, so
  neither driver maps/claims the MMIO region; no restart handler yet (vendor restart path still
  documented as TODO). Verified in the clone: pristine patch dry-run + OpenWrt prepare RC=0,
  **full `make target/linux/compile` RC=0** (zImage sha256 `50cd07a1...`), both drivers built-in
  with zero warnings from the new files, `dt_binding_check` PASS, DTS compiles with zero warnings
  (8,944 B DTB), clock-ID cross-check 16/16, no lab/bench breadcrumbs. Not hardware-tested; gate
  offsets for one group and reset polarity remain provisional. Details:
  `opensource/docs/SKELETON-SMOKE.md` (driver section).

- **FMC/SPI-NAND and network drivers ported (2026-11-18, host-only).** `patches-6.18/006` adds a
  SPI-MEM controller + SPI-NAND stack for the board's ESMT F50L1G41LC die (17 partitions, CRG
  clock/reset); it relies on OpenWrt's generic v6.19 ESMT support backport for that chip entry, so
  an upstream submission needs that entry or a kernel bump. `007`-`009` add the MDIO bus
  controller (clock + 7 CRG resets) and the Genius PHY (PHYLIB, ID `0x20669a00`/mask
  `0xffffff00`) complete, and GEMAC as an **honest partial** (binding + resource validation; probe
  refuses; DTS nodes disabled; no rings/DMA/NAPI). Per-lane verified: pristine dry-run RC=0,
  prepare RC=0, **full compile RC=0** (zImage shas `51f340ad...`/`2749c294...`), zero warnings from
  the new files, `dt_binding_check` PASS, zero-warning DTS. The combined tree (patches 004-009,
  both lanes merged) compiles its DTS cleanly (9,659 B). Unverified: hardware behaviour (FMC
  ECC/DMA, MDIO handshake, PHY link/autoneg, GEMAC data path). No bench/boot.

- **Machine restart driver ported (2026-11-18, host-only; provisional reset command).** `patches-6.18/010`
  adds `drivers/power/reset/luofu-reboot.c` (+ bindings for the reboot and the SYSCTRL syscon node):
  it saves the stock boot selector with a read-back/write-same (only on the measured `0x10`/`0x11`
  values; never invents it), writes the vendor CRG `softrst_val0/1` pair to the reboot word, and
  falls back to a bounded 1 s watchdog arm if the reset does not take - never parks. Both pages are
  shared syscon regmaps; probe touches no register. Verified: pristine dry-run RC=0, prepare RC=0,
  **full compile RC=0** (zImage `e548bc7b...`, both YAML bindings pass `dt_binding_check`, DTB
  9,891 B zero warnings, config derivation 297/297 symbols idempotent, checkpatch clean). The CRG
  reset command itself is **PROVISIONAL** (vendor-DT values/offset; write order/width never
  measured) and the selector protocol remains [U]; **nothing has run on hardware**.
- **Remaining-driver plan (2026-11-18).** `opensource/docs/REMAINING-DRIVERS.md` (914 lines) is an
  evidence-graded plan for the five blocks with no driver source: pinctrl, thermal, PCIe host
  (Wi-Fi endpoint [X]), internal LSW switch (switchdev, not DSA) and the GEMAC data path. Key
  structural finding: the wired data path lives in **hi_kpie (PIE rings/NAPI/DMA)**, not hi_kmac,
  which only tail-calls it; the internal switch is switchdev and has no source in either tree.
  Estimate: 32-55 focused host sessions + 11-19 attended bench sessions; bench is currently
  blocked (no 6.18 image/install path, fires stopped), so the offline order starts with
  thermal+pinctrl, then PCIe host, then PIE/GEMAC, then LSW.

- **Pinctrl and thermal ported (2026-11-18, host-only).** `011` adds
  `drivers/pinctrl/hisilicon/pinctrl-luofu.c` (+ YAML): vendor pin tables re-verified from
  `hi_kpinctrl.ko` (37 pins/24 groups/24 functions, 5-hit mux, cfg_off=4*pin), six pinconf params
  decoded, probe writes nothing, consumer states still [U]. `012` adds
  `drivers/thermal/luofu_tvsensor.c` (+ YAML): read-only vendor v4 conversion, 6.18 of-thermal API,
  DTS `cls0-thermal` with the vendor trips (115/125 C, 3 C hysteresis, 1 s poll) and no cooling
  map; threshold/IRQ/enable/trim registers undecoded and unwritten. Per lane: pristine dry-run,
  prepare, **full compile RC=0** (zImages `a4686a41...`/`34ed6116...`), 0 warnings, both YAMLs
  `dt_binding_check` PASS, zero-warning DTS (DTBs 9,887/9,799 B), config re-derivation
  idempotent, checkpatch clean. Never booted; no bench.

- **PCIe host, CRG reset-polarity fix, PIE data-path spec (2026-11-18, host-only).** `013` adds
  `drivers/pci/controller/dwc/pcie-luofu.c` (+ YAML): DWC host glue, CRG clock + 4 resets, RC
  mode/iATU from DT `ranges`, aligned-dword DBI accesses, `pci_host_probe`; the hard rules are
  encoded (never read the misc window), RC/endpoint nodes stay disabled (Wi-Fi endpoint `[X]`).
  The lane found a real defect in `004`: the vendor reset class is **active-low** (assert clears,
  deassert sets; measured `0x14880034 = 0x000ff309` with both RCs up), so `014` swaps the reset
  operations and inverts `reset_control_status`. `docs/PIE-DATAPATH.md` (743 lines) specifies the
  real wired data path (the MAC owns netdev/phylink, **PIE owns rings/DMA/NAPI**), correcting the
  earlier layering note. Combined verification: series 001-013 full compile **RC=0** (zImage
  `8654b99a...`, 0 warnings/errors, all CONFIG_LUOFU_* symbols, DTS 10,133 B zero warnings); `014`
  compiles as the changed driver object in the same tree. Nothing booted.

- **PIE packet-engine draft (015) and LSW switch spec (2026-11-18, host-only).** `015` adds
  `drivers/net/ethernet/hisilicon/luofu-pie.c` (+ YAML): validates window/clock/reset/4 named
  IRQs/`dma-coherent`, allocates coherent RX/TX ring bookkeeping, then **refuses to probe**
  (`-EOPNOTSUPP`) - no register access, clock, reset, IRQ or NAPI, because the read-only P3
  inventory is not captured; DTS node disabled. Lane-validated: prepare/compile RC=0 (zImage
  `5231214b...`), zero warnings, `dt_binding_check` PASS, DTB 10,193 B zero warnings, config 307
  symbols idempotent, checkpatch clean. Combined whole-series verification (patches 001-015 applied
  from the repo in a scratch tree): prepare RC=0, **full compile RC=0** with 0 warnings/errors,
  zImage `c82d0ffe...`, all `CONFIG_LUOFU_*` drivers built in (including the polarity-fixed CRG),
  combined DTS 10,193 B with zero warnings. `opensource/docs/LSW-SPEC.md` (1,375 lines) decodes the
  internal switch: module layering, synthetic module-id register map, port/queue/qid model, table
  formats, and two corrections - the vendor switchdev handlers are **stubs** in the shipped build
  and its rootif write is a userspace compatibility layer, not a hardware API; recommended shape
  is switchdev over per-port netdevs, D0-D2 plan. No driver for the switch yet.

- **First real target image built (2026-11-18, host-only; never flashed).** The image recipe is
  now wired (`image/luofu.mk` real `Build/` stages, `luofu-ubinize.cfg`, `platform.sh` with a
  real structural `platform_check_image` and a refusing `platform_do_upgrade`,
  `opensource/target-skeleton/tools/luofu-image.py`,
  `KERNELNAME:=zImage`). In an isolated OpenWrt main clone, `make world -j16` reached **RC=0**,
  producing `openwrt-hisilicon-luofu-cudy_wr3000-v2-squashfs-sysupgrade.bin` (6,185,262 B, sha256
  `362ca4ec...`) with the own FIP kernel slice (3,285,206 B, `e0826f8e...`), rootfs UBI (2,883,584 B,
  `97ba0488...`), generated trailer (10,958 B `0cf73b47...`) and manifest; the first (001-015) build
  was byte-reproducible and the final corrected (001-017 + selector/recorder) build also reached RC=0. The
  container and all structural fields were independently re-read (`luofu-image.py check-container`
  PASS; real `platform_check_image` PASS; corrupted/wrong-board/foreign images refused). **Nothing has been flashed or booted**;
  the A/B install path is implemented and mock-tested (never executed on hardware) and the
  factory/first-install path remains [U].

- **A/B selector + install path implemented (2026-11-18, host-only; hardware-unproven).** `017`
  adds `drivers/soc/hisilicon/luofu-selector.c` (+ YAML/ABI doc): a syscon-regmap interface on the
  existing SYSCTRL node (no second ioremap) exposing `current_pair` (`a`=0x10, `b`=0x11,
  `manual-b`=0x21, uninitialised/unknown), `raw`, and a write-only `next_pair` that accepts only
  `a`/`b`, does a low-byte RMW preserving the upper 24 bits and verifies the whole-cell read-back;
  probe touches no register. The 0x21 research (`SELECTOR-0x21.md`) corrected the provenance: the
  env `bootflag` is the actual pair selector, the cell is the failure record, 0x21 is the project's
  bench value (the vendor writes only 0x10/0x11), and a successful boot requires userspace to
  re-record the running pair.
  `platform_do_upgrade` is now implemented: two-witness active-pair detection (selector +
  booted rootfs slot), label-only inactive slot selection (`kernelb`+`rootfsb` after A, vice
  versa), slot-size validation, `mtd write` kernel + `ubiformat` rootfs with read-back, sync, then
  the selector store (last step, A pair preserved on failure); it never touches the active pair,
  `rootfs_data` or the env blocks, and refuses 0x21/unknown/mismatch/oversize/foreign images.
  A boot-time recorder (`/etc/init.d/luofu_record_pair`, S96) now re-records the running pair from
  the booted rootfs slot, closing the silent-rollback gap for our image. Mocked harness passes
  **94/94** fixture assertions and **100/100** against the real rebuilt container (A→B and B→A
  slot choice, kernel→rootfs→sync→selector order, recorder scenarios, every refusal path). Full
  001-017 series compiles cleanly; the corrected image is the final build above. **No write has
  been executed on the router**; the in-boot cell/env re-stamp, NAND writes and first boot of the
  written pair are the remaining attended validations.

- **Reversal report and review-form submission series (2026-11-18, host-only).**
  `REVERSAL-REPORT.md` (1,543 lines) consolidates the whole reversal with an evidence map and the
  remaining gates. `opensource/upstream/series-6.18/` is the 001-017 series in submission form:
  cover letter, 17 commit messages, MAINTAINERS proposal, tree-placement rationale, sequential
  `git am`/`patch(1)` validation on pristine linux-6.18.60 (RC=0, identical trees) and checkpatch
  (0 errors; 46 warnings / 4 strict checks, all enumerated). Pre-submission work is documented:
  split bindings from drivers, add MAINTAINERS, fold `014` into `004` for bisectability, DCO
  identity/provenance, regenerate `008` on mainline. **Not submitted**, nothing booted.

- **MAC source resolved; remaining SoC blocks decided (2026-11-18, host-only).**
  `opensource/docs/MISC-SOC-BLOCKS.md` (1,146 lines) decodes the remaining SoC blocks. Key result:
  the **factory MAC is in the encrypted `bdinfo` partition** (mtd6) with a plaintext 6-byte copy at
  `0xde00` (vendor userspace uses `mtd_get_mac_binary bdinfo 0xde00`; WAN = base+1); the efuse has
  **no MAC cell**, `fac` has no plaintext MAC, and U-Boot `ethaddr` is a random locally-administered
  address, not the factory MAC. Other decisions: eFuse write path not to be ported (one-way
  fences/key material), RNG is a software jitterentropy wrapper (drop), LED PWM is absent on this
  board, PMU PWM is the `vdd_logic` pwm-regulator (optional attended power-rail work), and the CRG
  parents/PLLs/muxes are decoded for a future clock-model extension (the vendor's real parents are
  recorded; patch `004`'s "provisional 0x20 offsets" are resolved in the decoded table). No
  bindings invented; TARGET-DESIGN open question 5 is now resolved.

- **SMP vendor bring-up decoded; draft platsmp patch 018 (2026-11-18, host-only).**
  `opensource/docs/SMP-RE.md` decodes the vendor `hisilicon,hsan_smp` method from the stock kernel
  (recovered vmlinux + kallsyms): a `CPU_METHOD_OF_DECLARE` entry with only `smp_boot_secondary`,
  which maps SYSCTRL/CRG, writes `secondary_startup`'s physical address to the SYSCTRL pen word
  (`+0xc00`), RMW-clears the core's two CRG resume bits (`0x16/0x18` CPU0, `0x17/0x19` CPU1 at
  `CRG+0x38`) and sends the wakeup IPI - **no SMC/HVC/PSCI** anywhere (correcting the earlier
  "pen/smc" assumption; pen [V], SMC [X]). Patch `018` adds `arch/arm/mach-hisilicon/platsmp.c`
  (`CPU_METHOD_OF_DECLARE(luofu_smp, "hisilicon,luofu-smp")`, fail-safe `-ENODEV` when nodes are
  missing), the machine refactor and the DTS `enable-method` via the shared patch. Validated:
  001-018 series applies and compiles (RC=0, zImage `ae59d998...`, zero warnings attributable to
  the new files, `platsmp.o`/method table linked, TEXT_OFFSET unchanged), dt_binding_check/DTS
  clean, config derivation idempotent. **The release has never run on our kernel**; pen consumer,
  CRG-bit semantics, SCU pre-state, TWD/GIC and secure-world traps are the attended gates. For the
  UP-first submission the DTS enable-method hunk is dropped (driver inert/fail-safe without it).

- **Factory-MAC provisioning implemented (2026-11-18, host-only).** The target image now reads
  the factory MAC from the encrypted `bdinfo` partition at **`0xde00`** via OpenWrt's
  `mtd_get_mac_binary bdinfo 0xde00` (fallback: label-based `/dev/mtdN` read), validates it
  (rejects non-MAC/all-zero/all-ff/multicast/locally-administered/`00:00:00`/WAN-wrap), derives
  LAN = base and WAN = base+1 with OpenWrt `macaddr_add` semantics, applies via `board.d`
  `ucidef_set_interface_macaddr`, and falls back to a logged locally-administered random pair when
  bdinfo is missing/corrupt (never writes factory data, never mixes in U-Boot `ethaddr`). Mocked
  harness: **103/103** assertions (both read paths, label-not-index, exact offset with decoys, all
  rejections, derivation, random fallback); isolated clone `make world -j16` RC=0 with the scripts
  installed byte-identically in the image (sha256 `54652e56...`, `check-container` PASS). Interfaces
  remain placeholders until the switch port map exists, so MACs currently reach `board.json` only;
  nothing booted.

- **CRG gate parents + fixed clocks + read-only PLL/mux model (019, 2026-11-18, host-only).**
  `019` extends the CRG driver with the real decoded gate parents (`ahb`, `gemacN`, `lsw_dp`,
  `lsw_pfe`), two **read-only** PLLs (0x198/0x1e0: `.recalc_rate`/`.is_enabled` only, no
  `.set_rate`; the vendor PLL write protocol was decoded but deliberately not implemented because a
  wrong store can hang the core), two **read-only** muxes (0x138: `.get_parent` only; CPU mux never
  writable) and the missing fixed clocks (`gemacN` 125 MHz, `lsw_dp` 166 MHz, `lsw_pfe` 333 MHz,
  `efuse_ring` 20 MHz). The vendor `hi_clk.ko` rate equation is reproduced: parent * (int +
  frac/2^24) / fbdiv with divider-select fields; probe stays register-free. Validated in an isolated
  clone (series 001-019): prepare/compile RC=0, zImage `4456b0ec...`, zero warnings, TEXT_OFFSET
  unchanged, `dt_binding_check` PASS, DTS zero warnings (11,346 B), config idempotent, checkpatch
  0/0. **PLL rates/mux parents are decoded, never measured**; attended read-only `clk_summary`
  check remains.

- **Public-strategy pivot (2026-11-18): curated public repos + notebook cleanup.** Owner decision:
  the work is intentionally public for career purposes, so novel work is published as curated repos
  with fresh histories while the root notebook is kept as the raw record. Published: 
  **https://github.com/ShibbityShwab/cudy-wr3000v2-cve** (public, MIT, 13 files; CVE-2026-71960/71961
  and systime-RCE writeups + sanitized demo PoCs, no secrets/per-unit data; API-verified) and
  **https://github.com/ShibbityShwab/cudy-wr3000v2-openwrt** (public, fresh history, 5 curated
  commits/138 files: showcase README, 14 design/RE docs, target-skeleton with patches 001-019,
  image/A-B install layer, 19-patch review-form series, tools/tests; MIT+GPL-2.0 split; no vendor
  binaries; API/fresh-clone verified clean). Root notebook: local redaction in
  progress (exposed lab password and per-unit MACs in HEAD) plus PUBLISH.md policy and curated links;
  **not pushed yet** pending owner approval. Legacy `open-firmware` submodule remains public with 10
  vendor `.o` blobs in history/tree (B0) and the full history-purge plan is documented in
  `opensource/docs/PUBLISH-PREP.md` (non-destructive; owner-gated). Security note: the lab web-admin
  password in old public history must be treated as compromised (rotation recommended; the current
  stock build no longer accepts it).

- **First-install-from-stock tooling ready (2026-11-18, host-only; not run on device).**
  `tools/first-install-stock.sh` is a fail-closed, attended installer: read-only inspection by
  default; `--write`/`--handover`/`--reboot` require `--attended --recovery-armed` and a validated
  `--image`; it writes **only the inactive pair** (kernel via `mtd erase`+`mtd write`, rootfs via
  `ubiformat`) with full-region sha256 read-back, aborts on bad blocks, never writes the active
  pair/rootfs_data/env/vendor data, and performs the selector handover using only the measured
  `SELECTOR-0x21` semantics (A=0x10/B=0x11, selector last, env-unchanged check; 0x21 never used).
  Mocked harness: **144/144 assertions**, including the real built container through
  `luofu-image.py check-container`; design/recovery/rollback in `opensource/docs/FIRST-INSTALL.md`
  and the RUNBOOK pointer. **Nothing has been written to the device.**

- **Public publishing completed (2026-11-18).** The owner approved publication: the root notebook
  was fast-forward pushed (`master` 359ee59..51049b9) after removing the last vendor-derived
  artifacts from HEAD (`patched/*.lua` are now local-only/gitignored), and the legacy submodule was
  pushed to a clean tip (`7ff9242..9978723`; its pre-policy history still contains the vendor `.o`
  files - optional purge plan in `opensource/docs/PUBLISH-PREP.md`). Remote trees verified clean
  (no `.ko/.o/.bin/.img/.dtb/.ubi`, or `.lua` in root). Live curated repos:
  `cudy-wr3000v2-openwrt` (portfolio: docs + 001-019 series + tools) and `cudy-wr3000v2-cve`
  (security research). The exposed lab credential was confirmed by the owner to be the vendor's
  stock/default password (low risk; optional rotation remains hygiene).

- **First read-only silicon inventory COMPLETE (2026-11-18, attended, no writes).** The bench
  inventory ran end-to-end: **600/600 allowlisted reads, one boot, 0 errors, 0 failed batches**,
  40 expected-value checks pass and 16 PIE expected-token corrections; post-run health fine. Live
  measurements closed the big `[U]` items: **PIE only channels 0/1 are active** on stock wired-only
  (TX bases 0x825c0000/0x82600000, RX 0x82420000/0x82518000, configs 0xc/0x8; ch2/3 ring regs 0 and
  RX IRQ masked; DT tx_ring=[0xc,2], rx_ring=[8,0x600]x2); **LSW qid table A** has 72/128 words -
  ports 4..12, 8 slots, qids `0x101..0x148`, table B zero; **queue/flow DDR windows** resolved to
  `0x80000000`/4 MiB and `0x80400000`/1 MiB from the live U-Boot overlay; CRG gates/resets/mux/PLL
  raw words captured and `clk_summary` shows CPU 1.2 GHz, lsw_dp 166 MHz, lsw_pfe 333 MHz, gemacN
  125 MHz, ahb 200 MHz, apb 100 MHz, osc 20 MHz (the decoded PLL equation reproduces 1.2 GHz);
  **SYSCTRL pen word = 0x80609680**, exactly SMP-RE's `secondary_startup` target (validates patch
  018), selector `0x10`, reset record `0x82000000`, cmdline `maxcpus=2 nr_cpus=2`. The tool's
  context capture was empty because stock busybox lacks `od`; fixed to use `hexdump` with `od`
  fallback (145/145 tests pass) and the DT values were re-read read-only into a provenance-stamped
  `followup/` sub-bundle. Bench torn down afterwards (TFTP/broker down); box stock and pingable.
  Analysis/spec updates land in `opensource/docs/INVENTORY-2026-11-18.md`, `PIE-DATAPATH.md`,
  `LSW-SPEC.md`, `MISC-SOC-BLOCKS.md`, `SMP-RE.md`.
- **Read-only bench inventory tool ready (2026-11-18, host-only; never run on hardware).**
  `tools/bench-inventory.sh` performs **600 static allowlisted 32-bit reads** (LSW/PIE/CRG/SYSCTRL)
  under fail-closed gates (attended/transport/no-active-fire/bench-link PASS/recovery READY/
  read-only UART/stock health) with re-scanned read-only scripts, a denylist for the RC misc window
  and forbidden CA, aligned dwords only, batching/timeouts, and PARTIAL/INVALID handling. Evidence
  bundles carry spec-mapped JSON/TSV, raw batches, DT/mtd/cmdline/UBI/clk context and SHA256SUMS;
  the attended procedure and expected-value tables are in
  `opensource/docs/BENCH-READONLY-INVENTORY.md`. Mocked suite: **145/145** assertions PASS, shellcheck
  clean. This is the first step of the next attended session (it closes the LSW D1b baseline, PIE P3,
  clk-rate and SYSCTRL [U] items without any write).

- **PIE datapath ring engine + GEMAC front end implemented (020, 2026-11-18, host-only).**
  Patch 020 turns the patch-015 PIE scaffold into a real datapath built on the measured baseline:
  coherent 32-byte descriptor rings for the **measured 2 RX / 2 TX channels** (log2 8 RX + 1536 B
  buffers, log2 12 TX), recovered v250 init sequence (mask-all → unmask-active, global RX enable
  via 0x3200 bit0), four IRQs with the recovered schedule/mask/ack order, NAPI RX polling that
  recycles completions but **does not decode the still-`[U]` status/length words**, TX producer
  with poll completion, and read-back verification that tears the engine down on mismatch. The
  probe is **fail-closed**: it refuses with `-EOPNOTSUPP` before any register write/clock/reset/IRQ
  unless `luofu_pie.arm=1` is on the cmdline, and the DTS nodes remain disabled. GEMAC becomes a
  phylink/netdev front end only when armed and writes only the measured 1 Gbps link words.
  Validated in an isolated clone: series 001-020 applies RC=0, prepare/compile RC=0 with **zero
  warnings under `CONFIG_WERROR=y`** (zImage `dfc7b753...`), TEXT_OFFSET unchanged,
  `dt_binding_check` PASS, board DTS zero-warning, config idempotent, checkpatch 0/0/0. **Never
  run on hardware** - attended ring/IRQ/descriptor checks remain.

- **LSW read-only D1b baseline probe implemented (021, 2026-11-18, host-only).** Patch 021 adds
  a register-map driver and a **read-only** probe of the measured baseline: new
  `luofu-switch-regs.h` with every offset/value graded in-line and a 17-window model (15 MMIO
  windows mapped; the measured DDR windows `queue=0x80000000/4 MiB` and `flow=0x80400000/1 MiB`
  validated from DT and never ioremapped), variant `hwver=0x250` match data (no ID register was
  measured, so none is invented), a fail-closed powered-state gate through the CRG syscon gate
  bits + corrected active-low resets (refuses without touching the block), validation of the 30
  measured baseline words, word-for-word re-derivation of both qid maps (384 words), the
  `port_bitmap <0xf01 0x1ff0>` baseline check and port-ownership resolution without netdev
  registration. **It performs no writes at all** (no `writel`); the qid-table write recipes are
  documented as the D1b W2 set but not executed, and the probe always exits `-EOPNOTSUPP`.
  Validated in an isolated clone: series 001-021 applies RC=0, prepare/compile RC=0 with **zero
  warnings under `CONFIG_WERROR=y`** (zImage `96b927d3...`), TEXT_OFFSET unchanged,
  `dt_binding_check` PASS, board DTS zero warnings, config symbol-identical/idempotent,
  checkpatch 0/0/0, inventory cross-check 0 mismatches. **Never run on ARM** - W3/W4/W5/W6 are the
  attended write-stage checks.

- **Submission form now 001-021; curated repo synced (2026-11-18).** The review-form series was
  extended with **020** (PIE datapath + GEMAC: fail-closed `luofu_pie.arm=1` gate, coherent
  measured rings, RX decode still `[U]`) and **021** (read-only LSW D1b probe, no writes, W2-W6
  attended campaign owed), revalidated on pristine linux-6.18.60: **patch(1) 21/21 and git am
  21/21 RC=0 with identical trees**, checkpatch **0 errors** (53 warnings/6 strict CHECKs), 42/42
  hashes OK. Both sit in the RFC/partial-drafts "do not merge" group with their dependencies
  documented. The curated public repo **cudy-wr3000v2-openwrt** was synced to source HEAD
  `6bcea12` (push `ee5b882`): new inventory + bench-inventory docs, measured spec updates,
  patches 020/021, port notes and status tables; API/fresh-clone verified clean; a follow-up sync
  brings its review-form copy to 001-021. The remaining review gaps are mechanical/documentary
  (binding split, MAINTAINERS entry, 0014->0004 fold, DCO identity, second-boot stability sample).

- **MILESTONE 2026-11-19: our kernel 6.18.60 + our OpenWrt rootfs booted to userspace on the
  WR3000 v2.** U-Boot failover booted kernelb (1 CPU: the image carries series 001-017, SMP patch 018 was not in this build), UBI attached rootfsb, ubiblock0_0 ->
  squashfs mounted, /sbin/init -> preinit -> procd -> kmodloader -> urngd -> overlayfs ->
  console prompt. Fixes: built-in CONFIG_CMDLINE_FORCE (loader supplies no cmdline; DTB bootargs
  crashed U-Boot), 4 KiB squashfs padding (ubiblock rounds to 512 B), CONFIG_XZ_DEC_ARM=y
  (squashfs uses XZ ARM BCJ), semantic UBI-volume read-back verification (ubiformat rewrites
  image_seq), single-write selector recipe. Evidence: build/evidence-firstboot/
  (uart-boot8-SUCCESS.log, SUCCESS.md). The box is running the debug-CRC kernel (slot sha
  897d4926...); a clean production image e893c388... (config-verified) was rebuilt but not yet
  re-flashed. Remaining gaps: no network (LSW/PIE/GEMAC netdevs not wired), no persistent overlay
  (no rootfs_data volume; tmpfs fallback), /lib/functions/board.sh missing for board_detect.

- **Minimum connectivity path implemented (022/023, 2026-11-19, compile-validated only).**
  Patch 022 adds the gated LSW write path: default stays the 021 read-only probe; luofu_lsw.arm=1
  runs W3 (gate clocks + resets, powered-state verify, read-only snapshot, no LSW writes), and
  +luofu_lsw.qidmap=1 runs W4/W5 (conformance gate, W2 qid-table programming for table A ports
  4-12 and table B ports 40-43, word-by-word read-back, restore on mismatch). Patch 023 makes GEMAC
  register netdevs only when PIE is armed and the switch is ready (and fixes the 020 draft's
  PHYLINK_DEV type to PHYLINK_NETDEV, which would have kept carrier dead). DTS enables
  lsw/pie/gmac1-4 with measured port ids. Validated in an isolated clone: **23/23 patches apply,
  compile RC=0 with zero warnings under WERROR** (zImage 5903db04...), bindings/DTS/config clean,
  checkpatch 0/0/0. **Never executed on hardware** - the next attended boot must run W3 -> W4/W5 ->
  PIE arm and then test carrier/DHCP; PIE RX decode and TX-to-LSW-egress mapping remain [U].

- **Final full-series image with persistent overlay ready (2026-11-19, host-validated, not flashed).**
  Image 6,205,742 B sha256 15dae772... built from the **full 001-023 series** (SMP, clock tree,
  PIE datapath, LSW probe, gated LSW W2/W3/W4/W5 writes, GEMAC netdev readiness) plus the boot
  fixes (CMDLINE_FORCE, XZ_DEC_ARM, 4 KiB padding). Rootfs UBI now carries a dynamic
  **rootfs_data** volume (reserved_pebs 9, autoresize) so mount_root gets a persistent UBIFS
  overlay instead of tmpfs; the stale board.sh reference was removed and a build-time guard
  checks board.d helper sources. Marker: BOOT-VERIFIED RECIPE / NOT FLASHABLE-UNTIL-INSTALLED
  (records the earlier 001-017 userspace boot; this rebuild is untested on hardware). Harnesses:
  first-install 144/144, abinstall 100/100, MAC 103/103, check-container PASS. **The next attended
  boot is the first test of SMP/CPU1, the persistent overlay and the connectivity gates** - the
  box still runs the proven 001-017 image.

- **Review-form series finalized at [PATCH 00/23]** (2026-11-19): 022 (gated LSW write path:
  default read-only; W3/W4/W5 behind luofu_lsw.arm=1 and +qidmap=1, conformance gate, readback,
  restore-on-mismatch, never executed) and 023 (GEMAC netdev readiness, PHYLINK_NETDEV fix,
  registers only when PIE armed + switch ready) regenerated with cover/mapping/MAINTAINERS/
  rationale/validation; pristine-6.18.60 revalidation patch(1) 23/23 and git am 23/23 RC=0 with
  identical trees, checkpatch 0 errors/56 warnings/6 strict checks, 46/46 hashes OK. Both are
  RFC/do-not-merge drafts; the attended W3/W4/W5/PIE gates are unexecuted.

- **All surfaces synced and current (2026-11-19).** Curated public repo
  cudy-wr3000v2-openwrt was synced to the final state and pushed (tip 1b53485): full 001-023
  series, overlay image recipe, final image facts 15dae772..., connectivity gate plan and honest
  caveats; independently revalidated 23/23. All repos are committed and pushed; no work is in
  flight. The box runs the proven 001-017 image (console-only); the final 001-023 image is staged
  for the next attended session (SMP/CPU1 + persistent overlay + LSW/PIE gates).

- **Egress (025) + bdinfo-MAC nvmem (026) integrated; final image rebuilt to 001-026**
  (2026-11-19). Patch 025 adds the gated W4 egress/dp/eqm/ips init write stage (vendor order,
  conformance gate, readback/restore; W3 -> W4 -> W5 order) and closed the port_bitmap/EQM
  command-word decode; per-frame TX carries zero LSW writes, but EQM queue tables and qid->egress
  remain [U]. Patch 026 exposes the factory MAC at bdinfo+0xde00 as read-only MTD nvmem with
  mac-base cells for the GEMAC nodes, plus board.d LAN/WAN mapping ahead of the unchanged
  userspace provisioner. Final image 6,205,742 B sha256 aa642862... (001-026 + rootfs_data
  overlay, check-container PASS, harnesses 144/100/103/82) supersedes 15dae772; still NOT
  flashed. Remaining network unknowns: PIE RX decode never executed, LSW EQM queue tables/
  qid->egress [U], nvmem MAC read unverified.

- **PIE completion/TX decode (024) integrated; final image rebuilt to 001-026 with the PIE DTS**
  (2026-11-19). Patch 024 decodes RX completion length/status/port and the full normal non-TSO TX
  descriptor from the vendor module, delivers frames via napi_gro_receive to the per-port netdev,
  implements ring pointer/doorbell/reclaim semantics, and requires hisilicon,port (8..12) in the
  DT; bindings updated. Validated: 001-024 apply 24/24, compile RC=0 zero warnings, cross-lane
  fully-clean 001-026 compile RC=0. Final image 6,205,742 B sha256 26dde6fe... (kernel slice
  3,307,134 B with the port properties, rootfs squashfs + dynamic rootfs_data; harnesses
  144/100/103/82, check-container PASS) supersedes aa642862/15dae772; still NOT flashed.
  Remaining network unknowns: EQM qid->egress mapping [U], nvmem MAC read unverified, and the
  attended W3/W4/W5/PIE-gate run.

- **Review-form series finalized at [PATCH 00/26]** (2026-11-19): 024 (PIE RX completion/TX
  descriptor decode, arm-gated), 025 (gated LSW W4 egress/dp/eqm/ips write stage), 026 (bdinfo
  MAC read-only MTD nvmem + board.d map) added with regenerated cover/mapping/MAINTAINERS/
  rationale/validation; pristine-6.18.60 revalidation patch(1) 26/26 and git am 26/26 RC=0 with
  identical trees (63 files, +10,276/-4), checkpatch 0 errors/58 warnings/6 strict checks,
  52/52 hashes OK. All three are RFC/do-not-merge drafts; attended decode/egress/nvmem gates
  unexecuted.

- **All surfaces final and clean (2026-11-19).** Curated cudy-wr3000v2-openwrt pushed to f74ce61
  (001-026 series, patches 024-026, final image facts 26dde6fe..., gates/[U]s, independently
  verified 26-patch/52-hash/harnesses clean). All repos committed and pushed; no work in flight.
  Box runs the proven 001-017 image (console-only); final 001-026 image 26dde6fe is host-validated
  and staged for the next attended session (SMP/CPU1 + persistent overlay + gated LSW/PIE path).

- **BENCH MILESTONE (2026-11-19): full 001-027 gate image boots with persistent overlay; W3/W4/W5
  accepted on silicon; PIE armed; GEMAC netdevs up with 1 Gbps carrier.** W4 probe config
  programmed+verified (dp+0x1c=0x10000 ... fam+0x504=0x2000), W5 qid map programmed, eth2 in
  br-lan forwarding. ARP/ping still fails (no frame traverses the PIE RX/TX datapath yet); SMP
  still 1 CPU (pen 0x8070a000, CPU1 failed even with all resume bits cleared). The earlier CRG
  regression was fixed (read-only mux .set_parent violates 6.18 clk-core rules). Box runs the gate
  image (console-only, recovery proven); next is a PIE TX/RX trace image, then SMP.

- **PIE trace (2026-11-19): TX descriptors are accepted/consumed by the engine, but no frame
  reaches the wire and no RX is delivered.** Trace image 36da0bd8 (patches 001-030) reproduced the
  gate milestone (W3/W4/W5 accepted, PIE armed, GEMAC netdevs, 1G carrier); TX doorbells written
  and the TX read pointer advances (1,3,5,...,0xb), so submission works. Host sniff sees only its
  own ARP requests (no box frames) and the PIE RX trace is empty. Blocker: the EPS channel map/
  companions and EQM queue tables (W3 snapshot: eps ch7=0x0 vs vendor 0x83090, companions 0x0 vs
  0x8000ffff/0x8001ffff, eqm+0x40=0x0 vs 0x80000000) were never programmed - exactly the [U]
  area the egress lane excluded. Next: decode/gate those writes + RX poll counters.

- **W6 EPS channel-map gate (2026-11-19): accepted and verified, but the data path still does not
  pass frames.** Image 1db10314 (001-031) programmes the measured EPS channel-map/companion words
  (readback-verified) and still reports READY with GEMAC netdevs; TX descriptors are consumed
  (doorbells + TX read pointer advance) but no box frame reaches the wire, and the new RX-poll
  trace never fires (no PIE RX interrupts at all). Conclusion: EPS maps alone are insufficient;
  the next layer is the queue-manager/EQM init (queue tables + per-port MAC<->EPS deque config),
  which must be decoded from the vendor before another write attempt. SMP still 1 CPU. Box runs
  the EPS image (console-only, recovery proven 6x); evidence under
  build/evidence-bench-gates/2026-11-19/.

- **CPU1 release diagnosed; patch 033 ready as a one-boot measurement (2026-11-19).** The pen
  value 0x8070a000 is correct (our secondary_startup = _text+0x102000 due 6.18 STRICT_KERNEL_RWX
  layout; vendor used _text+0x1680) and the stock U-Boot polls the pen with MMU off, so the IPI is
  not the release. Remaining: CPU1 never consumes the pen vs dies in the 6.18 secondary entry.
  Patch 033 adds default-off attended gates: diag (SCU/pen/resume re-reads), a pen-probe stub that
  prints MPIDR+“P” then branches to secondary_startup (proves consumption), SCU power-mode,
  all-bits/force-pen/retries, with vendor two-bit release semantics + explicit ordering. Validate
  001-033 host-side only; next boot makes the failure measurable. SMP still 1 CPU until then.

- **W7 queue-manager init integrated; combined W7+SMP-probe image built (2026-11-19).** Patch 032
  (submodule 32f16b7) decodes the EQM indirect engine and the full queue-manager init set (tables
  19/32/35/17/16/34, 169 entries/845 words for qids 1..72) and adds luofu_lsw.qminit=1: EQM-idle
  refusal, two-read snapshot, write via the decoded engine, readback of all 845 words, full restore
  on mismatch; ready() requires the complete W3-W7 set. Host-validated 001-032 apply/prepare/compile
  RC=0 zero warnings. Combined bench image 6,205,742 B sha256 14791958... bakes all five switch
  gates + PIE arm + SMP diag/probe into the cmdline (patches 001-033); NOT flashed yet (box still
  on the EPS image 1db10314). Next attended boot: W7 verified + pen-probe "1P" + one ping/tcpdump.

- **W7 run (2026-11-19): fail-closed refusal at the first EQM readback (safe, no partial path).**
  Snapshot 169 entries/845 words stable, EQM idle; table 19 entry 0 word 0 read back 0x3fff vs
  expected 0xffffffff -> full restore, readiness refused, GEMAC registered no netdev (fail-closed
  works). The QM lane is fixing the write/readback implementation. **SMP probe: no pen
  consumption** - diag shows pen 0x8070a000, resume 02a00000 (mask 02800000), SCU status 00, no
  "1P" stub output, CPU1 offline; the SMP lane is preparing the next single-variable variant
  (SCU power/CRG measurements). Box runs the W7 image (console-only), recovery proven 7x; evidence
  under build/evidence-bench-gates/2026-11-19/.

- **SMP diagnosis corrected; patch 034 ready (2026-11-19).** The W7-run "no 1P" was invalid: the
  built-in module_param tokens were silently unknown (correct names would be platsmp.*), and SCU
  status 00 means NORMAL, not dormant. Patch 034 uses bare __setup knobs, dumps SYSCTRL/CRG/SCU
  unconditionally at prepare/pre/+1 ms/+21 ms (read-only), and makes a marker-backed pen stub the
  default (prints MPIDR nibble + "P", then branches to secondary_startup; luofu_smp_probe=0 is the
  plain-entry control). Host-validated 001-034 apply/prepare/compile RC=0. Next boot: marker/1P =
  pen consumed -> direct-entry control or instrument __secondary_switched; no marker = core never
  consumes it -> cold boot, clear_mask variants, earlier pen write. QM lane still fixing W7.

- **W7 verification fixed (table 19 write-only) and final combined image built (2026-11-19).**
  Patch 032 revision acknowledges the write-only table-19 record (same vendor bytes, completion
  verified, read view logged) and verifies the other tables only on the fields the vendor's own
  readers consume (per-field masks, restore skips write-only entries). Combined image
  6,205,742 B sha256 5d2c5476... carries patches 001-034, the five switch gates + PIE arm, and the
  default-on SMP pen-probe/dumps from 034 (no cmdline token needed). Host-validated; NOT flashed.
  Next boot: W7 expected 168 verified on vendor-read fields + 1 write-only acknowledged, 034
  dumps/marker/1P, then ping/sniff. Box runs the failed-W7 image (console-only, recovery 7x).

- **Final image 5d2c5476 run (2026-11-19): W7 table-19 ack works; table-17 read-view mapping bug
  caused restore/refuse; SMP probe marker mapping failed but pen untouched.** W3-W6 verified;
  W7 169-entry snapshot stable and table 19 acknowledged write-only; table 17 entry 17 word 0 read
  0x0 vs expected 0xbb8 with expected words visible in read-view slots 1..3 -> EQM read/write
  data-word mapping/order off by one; driver restored, powered down, refused (GEMAC no netdevs).
  034 dumps ran; SCU ctrl=3 config=0x511 status=0x03030000 cpu0/1=0; prep pen 0 (loader state),
  write 0x81195000 remained, marker ioremap failed, no 1P -> CPU1 likely never consumed pen (probe
  instrumentation to fix). Both lanes reopened; box on this image (console-only, recovery 8x);
  evidence uart-w7smp-final.log sha f27437b2....

- **SMP probe marker fixed (2026-11-19, patch 035).** 034's "cannot map marker" was ioremap on
  System RAM being rejected (and the UART poll was unbounded), so the probe was inconclusive; 035
  writes MPIDR to marker word0 on entry, marker word1 = PEN! after a bounded poll, reads back via
  cache maintenance + linear map, and re-reads in late_initcall. Lane also proved loader-left pen 0
  is expected (stock 0x80609680 was the vendor kernel's runtime write; 034 observing 0 proves the
  loader's clear-pen path ran), SCU status 0x03030000 = CPU0/1 NORMAL + CPU2/3 off, SCU ctrl=3/config
  0x511 = 2 cores, CRG resume matches the stock 2-CPU reference. Next boot: consumed=yes -> direct
  entry/__secondary_switched; consumed=no -> cold boot, then probe=0/power=1/clear_mask controls.
  Host-validated 001-035 apply/prepare/compile RC=0. QM lane still fixing EQM read mapping.

- **Combined image 75868fe0 built (2026-11-19): W7 tiered verification + SMP marker fix.** Patches
  001-035; W7 STRICT only on bench-proven fields (table 32 priorities, table 35 word0 bytes1-2,
  table 17 words1..3 = 91 entries), DIAG read views for tables 16/34 (77), ACK for write-only table
  19 (1); expected success line 91/77/1 then GEMAC registration. SMP 035 stores MPIDR on entry and
  PEN! after a bounded UART poll, marker read via linear map + cache maintenance, probe on by
  default. Image 6,205,742 B sha256 75868fe0... (check-container PASS), NOT flashed. Next attended
  boot tests W7 + SMP + traffic; box on previous image, recovery proven.

- **W7 rev3 arms the data path: queue-manager accepted, GEMAC netdevs + 1G carrier, br-lan
  forwarding (2026-11-20).** First boot where the whole switch/PIE init chain is accepted: W4/W5/W6
  verified, W7 169 entries/845 words programmed (168 diag/1 write-only ack; strict count printed 0
  vs expected 91 - tier-count bug, no vendor-read field differed), "connectivity path armed",
  GEMAC registered, eth2 1Gbps/Full, br-lan forwarding. **Traffic still does not move**: host
  sniff sees only its own ARP; PIE TX descriptors consumed but no wire frame and no RX polls ->
  missing MAC<->switch forwarding (LSW port/MAC enable, EPS deque, IFC/L2/VLAN or PIE egress queue
  handle). **SMP definitive: consumed=no** (markers zero, pen 0x81195000 untouched, SCU NORMAL) ->
  CPU1 never consumes the pen on warm boot; next variable is cold power-on, then probe=0/clear_mask.
  Box on the armed image (recovery 9x); evidence uart-r3-armed.log.

- **Cold-boot SMP test (2026-11-20): same consumed=no.** Normal power-cycle boot of the armed image:
  markers stay zero, pen 0x81195000 untouched, SCU CPU0/1 NORMAL, CPU1 offline, late_initcall
  consumed=no. Only difference vs warm boot is SYSCTRL 0x10100c10 (0x02000000 cold vs 0x42000000
  warm, reset-source marker). So CPU1 never consumes the pen on either path; the SMP lane is now
  investigating loader parking vs early-boot resets vs pen semantics, and can use read-only stock
  /sbin/devmem measurements. Network: W7 accepted and the path arms, but traffic still does not
  move; QM lane is decoding the remaining MAC<->switch forwarding layer (port/MAC enable, EPS
  deque, IFC/L2/VLAN, table 38, egress queue handle) and the strict-count bug. Box runs the armed
  image (console-only, recovery 9x); evidence uart-coldboot.log.

- **Image 6cb3d908 built (2026-11-20): PFE W8 forwarding-engine init + SMP loader-window test.**
  Patches 001-037; switch gates arm/egress/qidmap/eps/qminit/pfe + PIE arm; SMP cmdline
  luofu_smp_reserve_low1m=1 (reserve the 0x80500000 window before first allocation - the leading
  hypothesis is the loader parked CPU1 in RAM our kernel treats as free; vendor kernel starts at
  0x80600000 and reserves 0x80600000+16KiB, ours starts at 0x80500000). 036 also fixes the W7
  tier count (91 strict/77 diag/1 ack) and adds the PFE base init after W7 armed. Host-validated;
  NOT flashed. Next boot: W8 verified + CPU1 consumption test + ping/sniff (first forwarded frame).

- **W8 PFE base init verified; traffic still dead; reserve_low1m does not revive CPU1 (2026-11-20).**
  Image 6cb3d908 (001-037): W7 tier counters fixed (91 verified/77 diag/1 ack), W8 PFE base init
  programmed+verified (pe+0x400=2, pfe_glb+0x2c=0x34, pfe_glb+0x204=1, opp+0x110=0), connectivity
  path armed, GEMAC netdevs + 1G carrier + br-lan forwarding. Traffic still does not move (sniff
  only host ARP, zero RX polls, TX descriptors consumed) -> next layer is IFC default-classification
  table / per-port MAC config (hi_mac_hw_config full write set) / L2/VLAN/CFE. SMP
  luofu_smp_reserve_low1m=1 reserved the window but CPU1 still consumed=no; next variable is
  reserve_flashinfo or early_probe modes. Both lanes reopened; box runs the armed image (recovery
  10x); evidence uart-pfe-run.log.

- **Image a6b57361 built (2026-11-20): seven-gate chain incl. W9 MAC max-frame init + SMP early
  probe.** Patches 001-038; gates arm/egress/qidmap/eps/qminit/pfe + PIE + luofu_gmac.hwinit=1 (MAC
  reg 0x100 low14 = MTU+4 with snapshot/readback/restore; the MAC drops over-limit frames both
  ways and our front end never wrote it - prime remaining wire-direction suspect) + SMP
  luofu_smp_early_probe=1 ('E' marker from setup_arch, mode 1 pen only). Host-validated 001-038
  apply/prepare/compile RC=0; image 6,205,742 B sha256 a6b57361... check-container PASS; NOT
  flashed. Next boot: W9 verified -> GEMAC/eth2/br-lan -> ping/sniff (RX poll trace), and EARLY
  probe 'E'/marker for CPU1 pen consumption (or silence -> stock reads next).

- **W9 clean run: W9 verified on all GEMACs, boot stable, but the first traffic attempt reset the
  box to stock (2026-11-20).** Image 45d248ff (001-038, seven gates incl W9, 1 CPU): W7 counters,
  W8 PFE, W9 (0x100 = 0x334005e0 on all four GEMACs), GEMAC netdevs, eth2 1Gbps/Full, br-lan
  forwarding all good. Sending host traffic produced no frames and then a reset/fallback to stock;
  the W9 2-CPU image also reset around its traffic test, while the W8-only image survived the same
  test. So W9/TX is the likely hang trigger (MAC max-frame write arming a TX path that wedges, or
  missing MAC config/egress when a frame is queued). UART captures saved
  (build/evidence-bench-gates/2026-11-20-w9*.log, sha 20e66b11.../02f58c42...) with stock segments
  interleaved. QM/SMP lanes reopened; box is stock and reachable (no recovery needed).

- **W9 read-only diag + early_probe=2 run (2026-11-20).** Image 6cf5de37 (001-040, W9 read-only,
  gmac trace, oops=panic): boot stable, seven gates armed; W9 diag reads 0x334005ee (limit 1518) on
  every GEMAC; early_probe=2 leaves pen 0x81293440, markers 0, consumed=no -> CPU1 never consumes
  the pen even with pen+resume-clear. Traffic test: one xmit (ctrl reads 0x0, maxframe 1518,
  port_mode 0x10c0008), descriptor+doorbell written, then box hangs/falls back to stock with no
  Oops. So the TX wedge is in engine processing/DMA or MAC TX-enable config, not W9. Stock
  reference registers captured (SCU config 0x531 vs ours 0x511, GIC words, SYSCTRL c10=0x0A000000,
  CRG 0x38=0x00200000; evidence 2026-11-20-stock-reads.txt sha dc791481...). Box stock/reachable;
  QM lane pursuing MAC ctrl + no-doorbell diagnostics, SMP lane has the stock reads.

- **Heartbeat liveness probe added; "idle hang"/several "hung box" conclusions were false alarms
  (2026-11-20).** A userspace heartbeat (HB <uptime> to kmsg every ~10 s) now runs in the target
  base-files. Image 5bd06925 (six gates + PFE, W9 inert, heartbeat) ran stable from HB 68 to
  HB 338 (5.6 min) through a traffic test with zero Oops/panic - the box was alive, and silent
  images without a data path had looked "hung". Only the runs with an actual Oops were real
  crashes. Traffic is still dead (host sniff sees only its own ARP; ping fails). Next: macconf
  vendor-MAC-sequence test, corrected W9 single-port write, then IFC table decode; every future
  test has the heartbeat detector.

- **macconf vendor MAC link sequence executed cleanly; box stable; traffic still dead (2026-11-20).**
  Image f58c516e (six gates + PFE, W9 inert, heartbeat, macconf=1): link-up replays the vendor
  sequence (0x14=0x6 speed code, 0x18=0x0, 0x1c 0->1, 0x40=0x10c0008 unchanged; ctrl 0x0 reads 0
  and is not the control word). Heartbeats HB 37..107 through traffic, no Oops; still no frames/RX.
  Next: IFC default-classification table decode (needs vendor table-manager ID sequence), then
  L2/VLAN/CFE; W9 corrected write still untested with heartbeat. Evidence 2026-11-20-macconf.log.

- **W10 IFC classifier programmed and verified on silicon; full W3-W10 chain armed; box stable via
  heartbeat; traffic still dead (2026-11-20).** Image 24794d64: W10 logged 8 entries (command
  engine acknowledged, tab128 readback exact); connectivity-armed line now lists R1/R3/R5, qid
  maps, EPS, EQM, PFE and IFC; GEMAC netdevs/eth2 1Gbps/br-lan forwarding; heartbeat HB 48..103
  through traffic, no Oops. But still no frames/RX: host sniff sees only its own ARP. (The first
  W10 attempt used wrong token luofu_lsw.ifc - patch 044 fixes the spellings to luofu_switch.*.)
  Remaining: L2/VLAN/CFE-rootif contract, PIE per-port queue handle/egress mapping, LSW port/MAC
  enable; QM lane reopened for patch 045. Box stable, running W10 image (heartbeat, no network).

- **W11 stock-vs-ours LSW diff produced the missing state list (2026-11-20).** Our post-W3-W10 dump
  (248 lines/61 windows) was compared against the same stock addresses read with devmem: 35
  differences. Key: IFC tab128 word0 entries 1-7 differ - stock 0x0/0x100800/0x1d01 vs our
  0x100800/0x1d00 (our W10 classifier values are wrong at runtime, the likely reason frames are
  not classified); 16 EPS words at eps+0xb20..0xb3c and eps+0xba0..0xbbc that W6 never wrote
  (0xa0/0x810a0/0x820a0/0x830a0, 0xb0/0x810b0/..., 0x8004ffff/0x8105ffff/...); dp+0x1c ours
  0x10000 vs stock 0x18000; eqm 0x48/0x4c/0x50..0x70 are indirect/data mirrors. Patch 046 will
  correct W10 tab128 + add the missing EPS writes, then traffic-test. Evidence: lsw-dump-ours.txt
  b80d8f2a, stock-lsw.txt 859c3346, lsw-diff.txt ea815b0c.

- **W12 verified: corrected W10 classifier + stock EPS/DP words; full W3-W12 armed; heartbeat
  stable; traffic still dead (2026-11-20).** Image 0a6849ed: in-run W11 dump shows tab128 now
  exactly as stock (0x00100800 at +0x50020, 0x1d01 at +0x50030..70); W12 programmed/verified 16
  EPS words + dp+0x1c=0x18000; connectivity-armed covers all stages through W12; GEMAC/eth2/
  br-lan up; HB 35..110 through traffic, no Oops. Still no frames or RX traces. The dumped-window
  differences are exhausted; remaining candidates are outside them (PIE/MAC RX-enable state - no
  RX interrupt has ever fired - or L2/VLAN runtime tables not in the W11 dump). QM lane reopened.

- **W13 dump found the RX smoking gun: pie 0x3404 ours 0x0 vs stock 0x1b04 (2026-11-20).** Image
  a24ba64e (001-047, heartbeat, W3-W12 chain + read-only PIE/GMAC dumps): the whole PIE state matches
  the stored stock inventory (0x1000 0x000a01c8, 0x2200 0x0045e000, 0x3200 0x00002001, 0x3700
  0xffff, per-channel 0x0180/0x0200/0x0380=1, RX IRQ status 0) EXCEPT pie 0x3404 = 0x0 vs stock
  0x00001b04 - the rx_init_chan per-channel RX-config word our driver never writes; this explains
  why no PIE RX interrupt has ever fired. gmac.dump printed nothing (needs fix) and the GEMAC window
  stock comparison is still pending. Next: patch 048 W13 gated write of the 0x3400 RX-config block
  (stock values; 0x3400/0x340c still to be measured) + traffic test. Box stable running the dump
  image with heartbeat (HB 82+); recovery needed for the next install.

- **W13 RXCFG written+verified (pie+0x3404 0->0x1b04); RX still never fires (2026-11-20).** Image
  28034919: W13_RXCFG programmed/verified the stock value, PIE armed, gmac.dump fix works, full
  W3-W13 chain armed, GEMAC/eth2/br-lan up, heartbeat HB 38..113 through traffic with no Oops.
  But no PIE RX polls and no frames: the 0x3404 value alone does not open RX. Every state we have
  compared now matches stock (PIE except no-writer 0x3400/0x340c, LSW W3-W12 incl corrected
  classifier, MAC link words, W13). Remaining: LSW flow/port state and CFE/rootif runtime tables
  outside the dump windows, plus the pending GEMAC-window stock comparison (ours captured).
  Evidence 2026-11-20-w13.log + gmac-dump-ours.txt; lane reopened.

- **W14 page scan found the missing runtime table pages (2026-11-20).** Image 603fcded (full
  W3-W13 + switch/pie scan + heartbeat) vs a stock devmem page scan: stock has non-zero 4 KiB pages
  at pe+0x1000/0x41000, eqm+0x2000/0x6000/0x42000/0x46000, eps+0x6000, ifc+0x1000 (two windows)
  and ifc+0x40000, opp+0x1000 (x2), mcc+0x1000/0x6000 that our armed image leaves zero; fam+0x1000
  and fam+0x41000 values differ (stock 0x2f9/0x2fa vs ours 0x11). Values like 0x1b6/0x1d1/0x1f1/
  0x3958/0x1110 are [U] (table bases vs counters) and must be classified against the vendor modules
  before replay. These are the CFE-installed runtime tables absent because the vendor modules cannot
  load on 6.18. Next: patch 050 W15 replay/instrumentation for the classified pages. Evidence
  stock-pages/our-pages (SHA256SUMS-pages); box stable on the scan image with heartbeat.

- **GEMAC stock-vs-ours diff: 4 un-decoded MAC config words differ + max-frame 1536 vs our 1518
  (2026-11-20).** Comparing our gmac.dump (eth2/port 11) with a stock devmem read of 0x14480000
  (144 words): 0x1c ours 0 vs stock 1 (macconf was off this image); 0xa4 0x40000 vs 0x30000;
  0xac 0x5800002 vs 0x1c00002; 0xb0 0xc043006 vs 0x1608006; 0xb8 0x210021 vs 0x690069;
  0x100 0x334005ee (limit 1518) vs 0x33400600 (1536). The four config words are MAC data-path
  settings our front end never writes - prime candidates for the dead wire direction. QM lane
  reopened for patch 051 (gated W16 MAC config write). Our gmac dump covered 0x0..0x2fc vs stock
  0x0..0x23c; remaining stock words can be read. Evidence gmac-dump-ours.txt + stock gemac raw.

- **RX path functionally alive after W16: PIE RX completions arrive (first ever), but decoder drops
  them (status 0x25, port 0) and host frames are still not forwarded to the CPU (2026-11-20).**
  Image 437a0766 (001-052, full W3-W16 + rxtrace): W16 verified (0x1c=1, gmac+0x100=0x33400600),
  heartbeat stable; after traffic the PIE RX ch0 polled and completed 60-byte frames every ~1 s
  with desc 6000003c 824600c2 0100b125 00000380 00000000, ret=-EIO because status=0x25 nonzero and
  port=0 has no netdev. These look like switch control/management frames (CPU port 0), not the host
  ARPs; host ping still fails. So RX works for CPU-generated frames; the remaining gap is
  forwarding host ingress frames to the CPU - L2/VLAN/port state (CFE runtime tables) or completion
  status/port semantics. QM lane reopened to decode and plan the next stage. Evidence
  2026-11-20-rxtrace.log.

- **FIRST REAL TRAFFIC (2026-11-20): the box accepted a punted ARP exception on eth2 and sent an ARP
  reply on the wire.** Image e924f8a6 (001-053, full W3-W16 + rxdiag/accepterr + heartbeat): one
  RX exception completion (len=60 status=37 port=11) was accepted and delivered; the host sniff
  saw the box's ARP reply (d4:0d:ab:xx:xx:xx -> 00:e0:4c:63:17:58, len 60). So the full
  wire->PIE RX->CPU->kernel->PIE TX->wire loop works for punted frames. The host's follow-up
  unicast ICMP (98 B, seen on the wire) produced zero further RX completions and ping still fails:
  normal unicast frames are not punted/forwarded to the CPU - the missing CFE L2/VLAN/CPU-port
  forwarding state. Heartbeat stable. Next: QM lane to decode hi_kcara/hi_swa L2/VLAN/CPU-port init
  for a gated W17 stage or a copy-to-CPU experiment. Evidence 2026-11-20-first-traffic.log.

- **PARTIAL SUCCESS: first ICMP echo replies (4/18) during W17 mirror sweep; sweep covered only
  dst 4-8, 40-43 missing (2026-11-20).** Image e9de3f80 (001-054, full W3-W16 + rxdiag/accepterr
  + mirror/sweep + heartbeat): mirror dst 4,5,6,7,8 at 2 s intervals then "sweep complete" (40..43
  not tried - bug); host ping got seq4 reply 1024 ms and seq5-7 at 0.15 ms (4/18, 77.8% loss) and
  the sniff shows the box (MAC 96:18:f3:8b:d8:71) sending ARP + ICMP echo replies during the sweep.
  No RXDIAG/RXERR lines this run (normal RX path delivered; instrumentation gap). Heartbeat stable,
  no Oops. So the mirror/copy path can make traffic work; next: fix sweep (40-43) + correlate dst
  with replies, then make the CPU-port mirror/config stable. Evidence mirror-sweep.log,
  ping-mirror.txt, sniff-mirror.txt.

- **Static CPU-copy dst 8 alone fails (50/50 ping loss) though ARP is answered; mirror was written
  before eth2 link-up and is likely reset (2026-11-20).** Image 851b3721 (001-055, W18 static
  cpu_mirror=1 dst=8 + rxdiag/accepterr/rxstroke): W18 line at 3.2 s, eth2 link 7.7/35.0 s, br-lan
  35.2 s. 60 s ping: 50 sent 0 received; sniff shows box ARP reply + host ICMP frames; RXSTROKE
  shows only one ch0 completion (the ARP), no ICMP deliveries. Heartbeat stable. The earlier sweep
  run got 4/18 replies because its writes landed after link-up; next: re-apply the mirror after
  link-up (or dwell 20 s per destination while pinging). Evidence cpumirror-static.log,
  ping-cpumirror.txt, sniff-cpumirror.txt.

- **W19 post-link mirror verified mechanically but dst 8 is not the CPU port (2026-11-20).** Image
  4e7cab94 (001-056, static cpu_mirror dst=8 + post-link reapply every 2 s + rxdiag/accepterr/
  rxstroke): W19 reapply lines show pre==post stable (d8=0x800 dc=0x6800000 c0=0x40); ping 0/50
  and 0/28 on retry after userspace up; box answers ARP but RXDIAG shows only len=60 status=37
  ARP exceptions - the host's 98-byte ICMP frames never reach the CPU. Heartbeat stable. So dst 8
  is wrong; the W17 burst caught the right destination briefly. Next: W19 dwell sweep 20 s per
  destination 0..15 with the host pinging, one boot identifies the true CPU port. Evidence
  w19-postlink.log/ping-w19b/sniff-w19b.

- **DWELL SWEEP FINDS THE CPU PORT: mirror dst 4; host ICMP then reaches the PIE RX ring as
  normal completions (status=0, port=0) but our driver drops port 0 (2026-11-20).** Image 4a38b497
  (001-056 + W19 dwell 20 s/dst 0..15 + rxdiag/accepterr/rxstroke): dwell steps logged for all
  destinations; 7 len=60 status=37 ARP exceptions (port 11) and 13 len=98 status=0 err=0 port=0
  completions whose timestamps are ALL inside the dst=4 window (69.1-87.5 s); later steps show no
  len=98. Ping: 220 sent, 0 received - because normal-path port=0 has no netdev so the CPU copies
  are dropped. Heartbeat stable through the 6-minute run. Last missing piece is our delivery
  mapping, not the switch: patch 057/W20 = static mirror dst=4 + deliver port-0 CPU copies to the
  mirror source netdev (eth2/11), then sustained ping should work. Evidence dwell-cpuport4.log,
  ping-dwell.txt.

- **WORKING DATA PATH + SSH (2026-11-20): our OpenWrt 6.18 image passes ping at 0% loss and SSH,
  with a persistent UBIFS overlay.** Image 39424b94 (001-057): static CPU-copy mirror dst=4
  (post-link reapply + re-latch) plus port-0 CPU-copy delivery to eth2. Host ping -c50: 50/50
  received, 0% loss; second run 25/25, avg 0.68 ms; sniff shows bidirectional ICMP. SSH:
  OpenWrt 6.18.60 SMP, br-lan 192.168.1.1/24 UP, 112 MB RAM; /dev/ubi0_1 on /overlay ubifs rw
  (14 MB) - persistent overlay works. /proc/cpuinfo: 1 CPU online (SMP bring-up still open).
  This is the first fully working LAN on our own kernel/rootfs; the working path is the attended
  CPU-copy workaround (mirror dst 4 + port-0 delivery), native CFE L2/VLAN forwarding remains the
  clean long-term fix. Evidence w20-working.log, ping-w20.txt, sniff-w20.txt, w20-ssh.txt.

- **Canonical 001-058 image verified working (2026-11-20).** Image af777742 (patches 001-058,
  canonical attended cmdline: full W3-W20 chain incl. cpu_mirror dst=4 + cpucopy_deliver port 11,
  heartbeat): ping 30/30 received 0% loss, SSH to OpenWrt 6.18.60 SMP, br-lan 192.168.1.1/24,
  /dev/ubi0_1 on /overlay ubifs rw; W19 link-up reapply logged; heartbeat stable. (dmesg Oops
  count 1 is the benign "panic=0" string in the kernel cmdline, not a crash.)
- **KNOWN LIMITATION: reboot from our image falls back to the vendor slot A (2026-11-20).**
  Reboot from working image 39424b94 brought the box back on the vendor 5.10 stack (stock reachable
  at 192.168.10.1), i.e. our userspace does not maintain the bootloader selector/env the vendor
  userspace writes; loader failover picked A. Overlay persistence across reboot is therefore
  untestable until boot-selector handover is implemented in our userspace (follow-up task). The
  image itself is fine and reinstall from stock needs no recovery. Evidence reboot-fallback.log.

- **Live-MMIO round 2: native-forwarding closed (mirror stays), CPU1 late-trigger tried, all
  consumed=no (2026-11-20).** Acceleration image 9da53b52 = patches 001-059 + DEVMEM +
  HOTPLUG_CPU + static devmem + boot-pair recorder; SSH live register access, reboot/overlay
  persistence verified. Phase A stock-vs-ours (4309 words) found only the NAPT block + known EQM
  mirrors; NAPT is persistent config pointing at the vendor DDR carveout 0x80400000 that does not
  exist on our image -> do not write 0x130-0x13c; safe non-DDR words were proven harmless and
  restored. Native host forwarding is CFE-software/DDR-carveout state, not MMIO-replayable: the
  CPU-copy mirror + port-0 delivery remains the bench solution. SMP: patch 059 adds a repeatable
  late-time add_cpu(1) sysfs trigger (cpu1 sysfs online is gated by missing .cpu_die); all live
  variants (late add_cpu, IPI storm targeted/broadcast, CRG resume clear, raw pen/IPI, SCU bit5)
  leave consumed=no and 1 CPU -> CPU1 is not polling the pen; next is loader-side decode per lane.
  Automated installer hung once in stock-wait (experimental); manual path used.

- **Stock SMP reference captured; CRG deltas = PCIe (no CPU1 effect); SCU CONFIG bit5 = CPU1-ran
  monitor; next is pre-decompressor handoff probe (2026-11-20).** Stock (2 CPUs) reads saved as
  2026-11-20-stock-smp-dump.txt: SCU 0x3/0x531/0x03030000 vs ours 0x3/0x511/0x03030000; CRG
  +0x20/+0x28 and +0x34 differences decoded as PCIe clock gates/resets (vendor WiFi), not CPU1.
  Live no-op control applying those exact stock values + GICD ISENABLER1 |= 0x5 then add_cpu(1)
  left consumed=no (restored, box healthy). ITARGETSR0 difference is banked-view (stock read ran on
  CPU1), not routing. All release-path variants (late add_cpu, IPI storms, CRG resume clear, raw
  pen) leave consumed=no -> CPU1 never polls the pen on our zImage boot path; patch 060 requested:
  marker stubs before/after decompression (compressed head.S entry + kernel stext) read at
  early_param, plus parallel uncompressed-Image experiment. Next stock boot (for install) will also
  capture DT/interrupts/iomem/flashinfo/low-mem/loader-signature reads per lane.

- **SMP HANDOFF BREAKTHROUGH: CPU1 consumed the kernel-stext stub (B=0x66cc66cc) but not the
  decompressor-entry stub (A=0) (2026-11-20).** Image 202832a2 with patch 060 printed
  'handoff A=00000000 B=66cc66cc pen=80600080 scu_cfg=00000511' and 'verdict decompressor-entry=no
  kernel-stext=CONSUMED'. So CPU1 is alive and responsive during the decompressor window and
  executes our head.S stub; our normal release path simply misses it. Next: patch 061 re-polling
  trampoline at stext (loop on pen) so platsmp/__cpu_up can later hand CPU1 to the real
  secondary_startup with secondary_data set - likely the SMP unlock. Also captured stock DT/handoff
  facts: cpus enable-method 'hisilicon,hsan_smp'; sysctrl smp-offset 0xc00; CRG core-info
  0x16,0x18,0x17,0x19 / resume-offset 0x38; reserved-memory flashinfo reg 0x80600000+0x4000
  atag-offset 0x1000; kernel slot 0x00840000=8,650,752 bytes (uncompressed Image ~12MiB will not
  fit); ITARGETSR8=0x01010101; risky loader reads 0/0xE2066007. Evidence handoff-probe.log,
  stock-reads-{1,2}.txt.

- **Sentinel probe 061: CPU1 never entered either stub -> definitively not polling the pen; loader-side
  root cause (2026-11-20).** Image 83a7ad08 (001-061, handoff_probe=1 trampoline=1): sentinels stayed
  0x600d1a88 at early_param/prep/post-release/late, jump=no, SCU bit5 clear; our flashinfo window shows
  the probe A stub at 0x80600040 and the 17-word trampoline at 0x80600080 installed correctly, while
  stock has loader data + the 66CC66CC pattern. The earlier 060 "B consumed" reading was that pattern,
  now corrected. CPU1 does not execute any kernel-side stub, so the release path cannot fix SMP from
  the kernel side; root cause is loader-side (U-Boot/hboot CPU1 start trigger and its inputs). Next:
  locate U-Boot runtime base (0x80040000 reads 0, it relocates), decode the secondary-core start
  condition, compare flashinfo windows (done), and decode image-type/header/boot-flag inputs.

- **SMP SOLVED: 2 CPUs online and persistent (2026-11-20).** Root cause: the stock U-Boot bootfip
  handoff staging was aborted because our DTB lacked the vendor base DTB's aliases/console and
  reserved-memory/flashinfo node; CPU1 was therefore never set up to poll the pen, and no kernel-side
  release variant could work (sentinel probe 061 proved CPU1 never entered the stubs even though
  U-Boot's in-place poll loop at 0x80040000 is intact). Adding aliases/console and the
  reserved-memory/flashinfo@80600000 node (reg 0x80600000+0x4000, atag-offset 0x1000) to the DTS
  fixed it: U-Boot now prints the stock handoff lines (alias console, serialnr, atag_addr), the
  kernel reports SCU bit5 set, smp: Brought up 1 node, 2 CPUs, CPU1 mpidr 80000001, 2 processors in
  /proc/cpuinfo, CPU0/CPU1 in /proc/interrupts. Reboot persists (pair recorder, 2 CPUs again, ping
  0% loss). Image d61c09e6 is the first 2-CPU image; the canonical post-fix image is being built
  next. Evidence smp-2cpu.log, smp-reboot.log.

- **2-CPU image hung silently after ~23 min; stability debugging next (2026-11-20).** Post-DT-fix
  image d61c09e6 ran ~1395 s with 2 CPUs, 0% loss ping/SSH, then went completely silent (last UART:
  link up 1379.9 s, HB 1394; no Oops/panic output; both IPs down). With oops=panic panic=0 the
  no-output signature points at a hard SMP deadlock (likely our driver concurrency: the W19 mirror
  2 s re-latch workqueue and/or switch/PIE paths racing with CPU1). Physical recovery needed. A
  clean canonical post-fix image was built: 974e6ca6 (DT handoff fix + canonical cmdline + DEVMEM/
  devmem/recorder; no probe tokens). Stability plan: reinstall, soak maxcpus=1 vs 2, then bisect the
  2-CPU hang via existing driver gates; fix locking and re-verify. Evidence smp-hang.log.

- **RETRACTION + 2-CPU stability: the "hang" was a host bench-link outage, not a kernel hang
  (2026-11-21).** Overnight the USB-Ethernet adapter lost carrier/IPs (both pings failed, UART
  capture had ended), which looked like a dead box; after power-cycle it booted normally with
  heartbeat running, and tools/bench-link.sh --apply restored the host link. No Oops/panic/BUG/
  WARNING in the log (only the literal panic=0 cmdline). Canonical image 974e6ca6 installed from
  stock and verified: 2 CPUs (online 0-1, Brought up 2 CPUs, 4000.97 BogoMIPS, CPU1 mpidr
  80000001), br-lan 192.168.1.1/24, ping 20/20 0% loss, SSH, /overlay ubifs rw, clean boot log.
  15-minute soak running. Lesson: check bench-link.sh/box-side vs host-side before declaring a hang.
  maxcpus=1/lockdep images retained as diagnostics only.

- **FINAL SMP VERIFIED: canonical image 974e6ca6 stable with 2 CPUs, network, SSH, rw overlay;
  15-min soak 0 failures, reboot persistent (2026-11-21).** Root cause (closed): U-Boot bootfip
  handoff staging is gated by the DTB's aliases/console and reserved-memory/flashinfo nodes; adding
  them (DTS-only) makes U-Boot complete staging, SCU bit5 sets, CPU1 comes online (mpidr 80000001,
  Brought up 2 CPUs, 4000.97 BogoMIPS). Canonical image verified: /proc/cpuinfo 2, online 0-1, br-lan
  up, ping 20/20 0% loss, SSH, ubifs rw, clean dmesg; 15-min soak 0 failures; reboot returns with 2
  CPUs and pair b recorded. The earlier "2-CPU hang" is retracted (host bench-link carrier/IP loss
  overnight; UART proved the box alive). 060/061 probes are bench diagnostics only; the release SMP
  fix is the DTS change. Evidence 2026-11-21-soak-2cpu.log, -final-reboot-2cpu.log.

- **6.18 release line consolidated + independently validated (2026-11-21).** Submodule commit adds
  upstream/series-6.18/05-release-line.md, release-line/manifest.tsv (62 patches: 51 include,
  11 bench diagnostics excluded, sha256 checked) and opensource/upstream/series-6.18/tools/check-release-line.sh. The loader hand-off
  DTS contract is recorded as THE SMP fix; canonical 2-CPU baseline is image 974e6ca6. Independent
  validator run: patch(1) 51/51 RC=0, 0 rejects; DTS cpp+dtc RC=0, DTB 12296 B sha256 50daf3d0...,
  console/flashinfo/enable-method contract present. 0018 regenerated to state the DTS dependency;
  RELEASE-NOTES + TARGET-DESIGN/ROADMAP/SKELETON docs updated; curated repos untouched. Remaining:
  052/053 pair regeneration, duplicate 042 renumber, upstream DTS series with the two nodes,
  install path on a device, Wi-Fi, native CFE forwarding, upstream review.

- **Release-line cleanup complete and independently validated (2026-11-21).** Submodule c7ffeeb:
  053 regenerated as the post-052 diff (final luofu-pie.c byte-identical; 0 fuzz, strict git apply
  clean); duplicate 042 resolved (042-net stays, 042-arm -> 062; 059/060/061 -> 063/064/065);
  L0 = 62 files 001-058 + 062-065. New DTS-0001 companion
  (dts-series/0001-arm-dts-hisilicon-luofu-r116-loader-handoff.patch sha256 73d93769...) carries
  the board DTS with the measured loader hand-off nodes, byte-identical to the target DTS, and is
  documented/generated/validated (06-dts-series-dependency.md; 0018 names the dependency). Lead
  validator run: 51/51 patch(1), 3 offsets, 0 fuzz, 0 rejects, strict git-apply clean, DTB 12296 B
  sha256 50daf3d0..., DTS-0001 contract checked. Caveat: DTS-0001 is a draft TODO-heavy board DTS,
  only the loader hand-off nodes are final - ships with 0018 after bindings cleanup. Next: curated
  publish sync; install path on device; Wi-Fi; native CFE forwarding; upstream review.

The published half is **NOT READY** for publication (`opensource/docs/PUBLISH-READINESS.md`:
vendor `.o` files remain in git history; history purge pending). Do not present it as
submission-ready.

## 4. Next action

**Current phase (2026-11-22): W22 native forwarding installed and verified on the bench; M1b next.**
Canonical image 50023446 (release line 059/060: driver NAPT/flow-engine init + PIE native
exception-class delivery) is running on the box with NO CPU-copy mirror: 2 CPUs, dmesg
"W22: NAPT/flow engine initialized and verified", SSH/ping work, link-flap recovers, and a
reboot determinism check passed earlier. It was re-installed with the corrected two-stage pair
procedure (switch stock to pair a first, then write inactive pair b; installer guard f188360;
RUNBOOK section added) after a self-inflicted mixed-pair failure during the fallback test.
15-min soak running. Remaining: soak result, fallback-image test (redo atomically or document as a
broker-switch limitation), M1b per-port/LAN-to-LAN (needs one cable move per jack), final curated
resync + STATUS/release-note close-out. Upstream: ZERO blockers (submission package complete, not
sent). History purge owner-only; Wi-Fi/thermal unsupported by design.

## 5. Reading the console (read-only)

```sh
tools/uart-capture.sh start --label <label> --timeout 900   # detached, absolute log path
tools/uart-capture.sh check
```

The script opens the tty read-only and never sends bytes. Do not use a read-write open of the tty
(the `3<>` form), `screen`, `minicom`, or a typed key: host-to-router TX is dead and must not be
attempted. A capture is evidence only when the log line that identifies the image is quoted
(uImage `Data Size`/`Image Name`, or `Uncompressing Linux` for stock).

## 6. Evidence

[`EVIDENCE-INDEX.md`](EVIDENCE-INDEX.md) maps claims to artifacts and regeneration commands.
[`CURRENT-TRUTHS.md`](CURRENT-TRUTHS.md) is the curated summary; the ledger
(`mem-entries.md`, index in `mem-entries-INDEX.md`) is the long form. The newest dated
entry wins over any older claim.

## 7. History

[`docs/archive/README.md`](docs/archive/README.md). Retired pages include
`STATE-2026-10-30.md`, `STATUS-2026-11-12.md`, `START-HERE-2026-11-15.md`, and
`PROGRESS-2026-10-15.md`.
