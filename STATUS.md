# STATUS - Cudy WR3000 v2.0

**Updated:** 2026-11-19 14:20 +07
**Pins are not written here.** Derive them with `git rev-parse --short HEAD` and
`git -C opensource rev-parse --short HEAD`.
**This is the only live status page.** Regenerate it; do not append to it. The physical
invariants live in `BENCH-FACTS.md`; the procedure is `RUNBOOK.md`.

## 1. Bench (re-verified read-only 2026-11-18 07:35 +07)

- **Box: vendor stock, healthy, idle.** Vendor OpenWrt 22.03.6, stock kernel
  `5.10.201 #0 SMP Sat Nov 25 18:18:57 2023`, uptime ~39 min, `bootflag=a`, both kernel slots
  restored to the stock image (md5 `b553da8ea24b38cb1e796b6a6430ccf7`), 2 wiphys, SSH on the
  project key. Bench fires are **stopped**; UART capture is stopped after teardown.
- **Host bench link:** `enp195s0f3u1` UP at 1 Gbps, NetworkManager-unmanaged, carrying
  `192.168.1.88/24` and `192.168.10.44/24`. Re-applied with `tools/bench-link.sh --apply`
  this morning after NetworkManager re-managed the adapter overnight; PASS at 07:20.
- **Recovery door: READY host-side, physical trigger.** TFTP is listening on UDP 69 and
  `tftp/recovery.bin` matches md5 `421114c8ea999c925b7aa79cc548af81`; the trigger remains the
  physical RESET counter on a true power-on reset (`BENCH-FACTS.md` section 4).
- **UART: READ-ONLY.** `/dev/ttyUSB0` (FT232R, 115200 8N1); host-to-router TX is dead (burnt
  resistor) and must never be attempted. Capture with `tools/uart-capture.sh` only; it now
  restarts `cat` on USB-serial EIO and kills its process group on stop.
- **Latest fired slice (local only, NOT a release):**
  `build/linux-kbuild/luofu-slice-phase3dq.bin` v17 = 2,906,100 B, md5
  `8342ccb9c0167766529277719330f43c` (zImage `a08ffc66`, init `74033a38`, DTB
  `336ba39e`, 59 patched modules staged for that run). Rebuild with
  `build/linux-kbuild/build-3dq.sh`.
- **Guards:** `tools/check-init-shadow.sh` PASS; `tools/check-lab-src.sh` PASS (43 modified
  source files); `tools/check-repo.sh` PASS before this page was regenerated. These are
  source-level guards, not artifact proofs.

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

The published half is **NOT READY** for publication (`opensource/docs/PUBLISH-READINESS.md`:
vendor `.o` files remain in git history; history purge pending). Do not present it as
submission-ready.

## 4. Next action

1. **GPL source: optional accelerator only - not a project gate (decision 2026-11-18).** The
   2026-10-01 request got no reply and needs no further follow-up for this project. The record is
   kept for provenance/optional leverage (a source drop would mainly accelerate LSW/PIE/Wi-Fi); the
   work proceeds by our own reverse engineering. No waiting, no enforcement org.
2. **Finish the driver/binding series** (host-side): CRG/watchdog, FMC/SPI-NAND, MDIO/PHY,
   pinctrl, thermal, PCIe host and the provisional restart are ported (GEMAC partial); the
   remaining blocks are the internal switch driver and the PIE data-path bring-up - the PIE half
   has a refusing draft (`015`), spec in `opensource/docs/PIE-DATAPATH.md` and the switch spec in
   `opensource/docs/LSW-SPEC.md`; PIE needs the attended read-only P3 inventory before arming
   rings, and the switch needs its D1 implementation.
   Prune the `[D-default]` other-SoC Hisilicon drivers and run `dtbs_check` per binding. After
   that, wire the custom image chain
   (`luofu-uimage` -> `fip-slice` with the generated trailer -> `fip-manifest` -> UBI ->
   sysupgrade), resolve the board-compatible mismatch (`cudy,wr3000-v2` vs
   `hisilicon,luofu-r116`), write `platform.sh`/install, then the first attended boot of a full
   image (bench step, human-attended).
3. **Boot/install are now the only gates for the image**: run the final 001-017 build, then an
   attended A/B validation on a recovered unit (upgrade -> boot the written pair -> confirm the
   other rootfs slot attaches and `current_pair` matches -> switch back), read `fw_printenv
   bootflag` to close the env re-stamp question, and validate the first boot of a novel generated
   trailer, rootfs/overlay mount and boot-arg hand-off. NAND writes under this FMC/ECC geometry and
   the 0x21 manual state are also attended checks.
4. **Consolidate the reversal evidence**: EVIDENCE-INDEX rows for the v6-v17 line, publish-readiness
   purge plan, and the reversal report.
4. **Optional, only if resumed:** the vendor `sk_buff`/bridge/HYFI port strictly per
   `VENDOR-SKB-BRIDGE-PORT.md` - E0 host probe first, no bench fires before that. Bench fires stay
   stopped until then.

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
