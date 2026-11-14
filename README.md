# Cudy WR3000 v2.0 - reversal + port

Offensive-research notebook for a **Cudy WR3000 v2.0** router (HiSilicon Hi5671Y
"luofu", board R116, dual Cortex-A9, 128 MB NAND + 128 MB DDR3; Wi-Fi
Hi5622V100 on PCIe; stock OpenWrt 22.03.6 / kernel 5.10.201, ~60 binary-only
modules and a closed 928,920-byte Wi-Fi firmware blob).

**Hardware identity note (2026-11-08):** the enclosure of the test unit may say WR3000 v1, but
the PCB is the HiSilicon luofu v2-class design (Hi5671YV200 + Hi5622v100). The v1 is a MediaTek
MT7981 board and cannot boot the v2 firmware. The v1 FCC filing and board photos do not apply.
See [`HARDWARE-IDENTITY.md`](HARDWARE-IDENTITY.md) before using the label, FCC data or photos to
identify the unit, and before any UART or firmware work.

**The goal (set 2026-10-05):** our own, fully-current OpenWrt on this board -
our kernel, our drivers, no vendor kernel.

**Where the work lives:**

- **`STATE.md` - the one page: the current wall, the next three experiments, the box state. Start here.**
- **`HARDWARE-IDENTITY.md` - the unit identity (v1 label vs luofu v2 PCB), correct firmware, and measured UART/U-Boot limits.**
- `AUDIT-2026-10-22.md` - the structural audit (score model, record, plan) and the restructure.
- `START-HERE.md` - operational handoff (device, secrets, harness, hard rules).
- `mem-entries.md` - the evidence ledger, phase by phase (history; last dated entry 2026-10-22).
- `PROGRESS.md` / `PROGRESS.html` / `progress-data.json` - the 2026-10-15 lane snapshot, **superseded**
  by the gate table in `STATE.md`; kept as history.
- `opensource/` - git submodule, the published half (docs + lab modules).

---

## Progress at a glance (updated 2026-11-14)

**The headline is the gate table in [`STATE.md`](STATE.md).** This section restates it for readers who
will not open another file; where the two disagree, `STATE.md` wins. The structural audit is
[`AUDIT-2026-10-22.md`](AUDIT-2026-10-22.md).

| gate | state | receipt |
| --- | --- | --- |
| **G1** FMC reads real flash | **GREEN** | page-0 magic `UBI#` at the probe; and a level-7 probe through the MTD layer found the partition by name, the EC magic, `vid_hdr_offset = 0x800`, and `PEB0+0x800` reading `'U'` |
| **G2** program path | **GREEN** | a page written by our kernel read back byte-exact through the vendor driver |
| **G3** our kernel + real rootfs + userspace | **GREEN (2026-11-14)** | the vendor's own preinit, `mount_root`, procd and the full rc.d chain run on our kernel from the squashfs root, proven by kernel-version breadcrumbs `#162`..`#199` in `/boot.log` plus the `S95done` shadow |
| **G4** Ethernet on our kernel | **blocked on the PHY** | the four MACs probe, take clocks and resets and create their phylink, then defer at `phylink_of_phy_connect`: no PHY exists because the MDIO controller never completes a transfer (see the module table below) |
| **G5** Wi-Fi on our kernel | vendor-only | the lab `wifidrv`/`hccaccept` line builds and loads; no wiphy yet |
| **G6** sustained uptime | **GREEN (2026-11-14)** | the reset was below the kernel (no panic ever captured) and its cause was a userspace watchdog race; the initramfs keeper now holds the full 25-minute home timer on surviving boots |

### Vendor module/driver reversal status (2026-11-14)

Percentages mean: how much of that vendor module's job our own kernel reproduces well enough to run a
box. The vendor ships ~60 binary modules; these are the ones the boot and the network depend on.

```
vendor module                reversed
---------------------------- ----------------------------------------
hi_flash    (NAND FMC)       [###################-]  95%  reads, writes, erases; MTD/UBI/squashfs/jffs2
hi_crg      (clocks/resets)  [##################--]  90%  16 gate clocks + reset provider registered
hi_wdt      (watchdog)       [####################] 100%  registered, vendor register map, 30 s, petted
hi_kmac     (Ethernet MAC)   [##############------]  70%  probes, clocks, resets, phylink; no PHY to attach
hi_kmdio    (MDIO)           [############--------]  60%  frame, handshake and bus-op map decoded; no transfer completes
hi_pcie     (PCIe host)      [########------------]  40%  link + BAR enumeration experiments (phases 19-22)
hi5622      (Wi-Fi)          [######--------------]  30%  service map + hcc/wifidrv lab probes build and load
lsw_dp/pfe  (internal switch)[###-----------------]  15%  clocks and resets only; its init gates the PHYs
hi_kpinctrl (pinmux)         [##------------------]  10%  no driver; the DT pins are untouched
hi_kphy     (the five PHYs)  [--------------------]   0%  nothing registers them; every MAC waits here
```

| module | what it does | our driver | what is measured |
| --- | --- | --- | --- |
| `hi_flash` / FMC | NAND controller | `luofu-fmc` | page reads return `UBI#`; writes verified byte-exact; the vendor rootfs mounts from it |
| `hi_crg` / `hi_clk` | gate clocks + resets | `luofu-crg` | 16 gates and the reset controller register; every consumer resolves |
| `hi_wdt` | hardware watchdog | `luofu-wdt` | registered with the vendor's hwver-2 map, 30 s timeout |
| `hi_kmac` | Ethernet MAC (5) | `luofu-gmac` | probe crumbs `6001`..`6013`, then `6f07` deferring on the PHY |
| `hi_kmdio` | MDIO controller | `luofu-mdio` | clock 100 MHz; vendor frame `0x8000` + `reg<<8` + `phy`; four-phase handshake; bus-op map `0x20/0x2c/0x30/0x38` |
| `hi_swa`, `hi_lsw_dp`, `hi_lsw_pfe` | internal LSW switch | none | `hi_swa` is switchdev glue; the init lives in the two big LSW modules (~120 KB) |
| `hi5622v100_plat/wifi` | Wi-Fi MAC/PHY stack | our `opensource/lab` line | five modules build with matching vermagic; read-only service skeleton |

**Reading the two tables together:** the reversal of the *hardware* is far ahead of the port of
*drivers*. The flash, clocks, watchdog and the vendor userspace are done; what remains is the
network path, and it is blocked at exactly one place - the PHYs, which need the MDIO controller,
which in turn needs the internal switch brought up.

**2026-10-30: THE BOOT NOW COMPLETES EVERY INITCALL - and the blocker was ours.** Five defects were
hiding each other. The device tree was **never actually appended** (`mkimage` packaged the bare
`zImage` while `CONFIG_ARM_APPENDED_DTB=y`), so every DTS edit this project had ever made was
compiled and discarded and the kernel ran the vendor's tree. Behind that: the CRG registered **zero
clocks** because a range check compared the bank against the gate index; the reset provider supplied
no `of_xlate`, so the core forced `of_reset_n_cells = 1` against two-cell specs and every consumer
failed; and the flash driver claimed **16 KiB of physical memory at `0x80602000` and never reserved
it**, writing the kernel log into whatever `memblock` had put there. That last one is why six driver
bisects all returned identical results - every suspect was downstream of the corruption, none of
them the cause. With it removed the boot goes from dying at 70 s in `device_initcall` to running the
full 310 s with correct page tables at level 7 (`virt_to_phys(swapper_pg_dir) = 0x80604000`).
**What gates the goal now is a single question: why UBI finds no layout volume on `rootfsb`.**

**2026-10-14: the Ethernet wall fell.** The NIC went from "0%, not started" to working - the MAC
is configured from a live PHY link (`mac_link_up` fires, SPEED_100, PHY BMSR 0xCDEF). Four bugs had
to fall in order: MDIO resets never deasserted; the MAC link callbacks were empty stubs; the
MAC<->PHY map was shifted by one so the wired port pointed at the wrong PHY; and the netdev was
never opened, so phylink never polled the PHY at all. **What gates the goal now is not the NIC but
boot survival.**

**2026-10-15: THE BOOT GUARD FELL - OUR OWN KERNEL NOW EXECUTES ON THIS BOARD.** Every prior fire
of a self-built image was refused *before its first instruction*; the session found why. The loader
requires (a) a **DTBO container** - magic `0xd7b7ab1e` at `main_dtb + be32(main_dtb+4)`, confirmed
byte-for-byte on the live vendor slot - and (b) a main DTB carrying the `vendor_id`/`board_id` the
overlay applier matches on. Using the vendor's DTB with our kernel is what finally booted.
**Measured boot narrative:** our kernel runs past every driver probe and past `late_initcall` with
**correct page tables** (`swagger_pg_dir` -> `0x80604000`), then panics. See
`build-guard-dtbo-container.md` and `own-kernel-boot-narrative.md`.

**The instrument that hid all of this was circular:** the driver's write self-test compares its
write buffer against a read that copies from that same buffer, so `mismatches = 0` was guaranteed
regardless of hardware - which is why the flash question outlived every previous window.
See `fmc-data-path-position.md` and `sysctrl-cell-map.md`.

This is **two projects wearing one repo's clothes**: the reversal (phases 2-49)
is most of the way done and hits a genuine hardware wall; the rebuild (the
`lab/luofu-*` drivers + phases 50-*) is a third done and is the multi-month
programme.

### A. Reversal - reading the hardware (~84%)

| subsystem | score | state |
| --- | --- | --- |
| Device / SoC identification | 100% | done |
| Wi-Fi firmware blob (opened + symbolised) | 95% | done |
| Register / BAR map | 90% | done |
| Vendor config API (alg table, 414 entries) | 100% | done |
| Radio calibration store | 95% | done |
| HCC message protocol (77 handlers) | 90% | done |
| ETE SR/DR ring map | 90% | done |
| FMC/NAND controller spec | 85% | done |
| Interrupt path (ctrl-rb -> GIC) | 70% | **blocked** |
| Wi-Fi host<->device dialogue | 55% | **blocked** |

### B. Wi-Fi driver - our own `wifidrv` line (~48%)

| subsystem | score | state |
| --- | --- | --- |
| wiphy registration (`omo-drv0` + `omowl0`) | 100% | done |
| Endpoint claim + viewports | 85% | done |
| Firmware load + CPU release (9/9) | 90% | done |
| SR post + ring exchange | 70% | partial |
| H2D message send | 40% | **blocked** |
| Data path + cfg80211 ops + TXBF/rate/DFS | 10% | **not started** |

### C. SoC / kernel bring-up - our own kernel (~45%, the long pole)

| subsystem | score | state |
| --- | --- | --- |
| Device tree (`luofu-r116`, 647 lines) | 85% | **now actually applied** - the DTB was never appended before 2026-10-30 |
| Kernel config fragment (12 symbols left) | 75% | partial |
| CRG clock/reset driver | 75% | **registers 16 gates + the reset provider**; a bank-vs-index bug meant zero clocks until 2026-10-30 |
| Pinctrl / IOMUX driver | 40% | code exists |
| PCIe host driver (DWC) | 25% | code exists |
| NAND / FMC controller driver | 85% | **reads real flash, verified at level 7**; the write path is proven byte-exact |
| Ethernet GMAC / MDIO / switch driver | 70% | MACs probe and phylink exists; **blocked on the PHY**: the MDIO controller completes no transfer and the internal LSW is not ported. The vendor link (eth2, 1 Gbps) runs only on the vendor kernel |
| Boot chain / U-Boot source | 10% | **not started** |
| UART / GPIO / watchdog / thermal | 20% | partial |

### D. Userland + deployment (~33%)

| subsystem | score | state |
| --- | --- | --- |
| Custom image + A/B flashing (slot B live) | 90% | done |
| Vendor web RCE + SSH lane | 100% | done |
| Modern userland on vendor kernel | 75% | proven |
| Upstream OpenWrt target (`hisilicon/luofu`) | 0% | **not started** |
| Vendor GPL source access | 0% | **blocked** |

### The wall

Every host-side move the verified maps name has been performed to the vendor's
own values. The last hop - the Wi-Fi chip's ctrl-rb delivering its latched
interrupt to the GIC - is **inside the device**, unreachable from the host by
every mechanism this bench contains (`opensource/docs/phase48/host-side-closed.md`).
Only two instruments could open it and **both are confirmed unavailable**: JTAG
(no hardware) and the vendor source (Cudy + Jeton requests both silent).

### What is left, in order (updated 2026-10-15)

**0. THE CURRENT CHAIN, MEASURED 2026-10-22 (it replaces the 2026-10-15 `init_eaccess` reading,
which is withdrawn).**

The kernel log, read out of mtd9 on the box itself, now shows the boot dying at the rootfs mount:

```
6.471  FMC: rootfs_data is mtd15 ... read=0 got=8: 00 00 00 00 00 00 00 00
5.909  ubi0: attaching mtd14
6.086  ubi0: scanning is finished
6.090  ubi0 error: ubi_read_volume_table: the layout volume was not found
6.097  ubi0 error: ubi_attach_mtd_dev: failed to attach mtd14, error -22
6.520  VFS: Cannot open root device "ubiblock0_0" ... error -6
6.79   Kernel panic - not syncing: VFS: Unable to mount root fs
```

**UBI reads flash through our own FMC driver, and that read path returns zeros.** Measured: the row
is correct, `FMC_CFG` matches the vendor, the SFC clock/reset are correct, the operation reports
completion, and the DMA buffer is never written (`buf=0`). Leading hypothesis (2026-10-22): the box
is **SPI-NAND**, and the read path writes the parallel-NAND literal `OP_CFG=0x50` where the SPI
encoding is the packed `0x9A1` the live vendor register showed. Detail:
`fmc-read-path-degradation-2026-10-21.md`.

The earlier `init_eaccess` / "userspace handoff" reading is **withdrawn**: it came from a build whose
log was not readable, and the readable log now shows the VFS panic.

**1. FIX THE FMC READ PATH.** The single blocking bug for the goal. Evidence (2026-10-21/22):
`dma_buf` is never written, the row and config are correct, the operation completes - the read is
aimed at the wrong SPI interface. **No rootfs until this reads correctly - and no userspace until
there is a rootfs.** (The 2026-10-15 `C70` line was withdrawn: `0xC70` is the driver's own read
deposit, not scratch.)

2. **Reachability once it survives.** The NIC driver is written and works (under the vendor); what
   is untested is whether our kernel brings it up. Needs (1).
3. **Fill the stub drivers** - **AUDITED 2026-10-15, and the answer differs per driver:**
   - **clk** (`luofu-clk.c`): TODOs are **STALE** - `set_parent`, gate/vgate/pll ops, AND a full reset
     controller (`reset`/`assert`/`deassert` + `of_xlate`) are already implemented; the TODO that
     says "register the reset controller" sits directly above the code that does it.
   - **pinctrl** (`luofu-pinctrl.c`): **MOSTLY STALE** - `set_mux` and the full `pinctrl_ops` map are
     implemented; only the `pinconf` ops are genuine, and they are documented no-ops.
   - **PCIe** (`luofu-pcie.c`): TODOs were **ACCURATE** - and are now **WRITTEN**. The bring-up
     (CRG handshake, RC mode, iATU/cfg setup, LTSSM link training) is real code, gated behind
     `rc_bringup=1`, and **compiles clean** (`luofu-pcie.ko`, 21,864 B, zero warnings).
     See `pcie-bringup-written.md`.
4. **The Wi-Fi wall + data path** - split by what a host can still do vs what needs
   a device-side trace.

Full detail, per-lane evidence citations, and the honest ceiling:
**[`PROGRESS.md`](PROGRESS.md)** (the text ledger; `PROGRESS.html` is the same data drawn as a graph).

---

## Layout

| path | what |
| --- | --- |
| `tools/` | experiment harness (`exp.sh`, `batch.sh`), crypto/RE CLIs, web probes |
| `patched/` | de-crypted stock LuCI bytecode (LuaQ) - injection sinks, data not source |
| `opensource/` | git submodule -> the published half (docs, lab modules, GH Actions) |
| `wordlists/` | Git LFS pointers only (14 bytes each) - not real lists |
| `STATE.md`, `START-HERE.md`, `mem-entries.md` | current one-pager + operational handoff + evidence ledger (`PLAN-UART.md` is retired: the bench has no UART) |

Everything under `build/ dumps/ firmware/ stock/ rootfs-*/ decomp/ pages/ pyenv/
jtools/ tftp/ ulw/` is gitignored local state - it may be large or absent.

## Hard rules

- **A FIRE MUST PROVE ITS OWN VALIDITY BEFORE ITS READING IS BELIEVED.** Use
  `build/tmp/fire-verified.sh`, which checks: `boot_id` changed (the box actually rebooted),
  slot B still holds the flashed image (like-with-like md5, AFTER the boot, not only at flash
  time), and the crumb was sampled inside the window. It prints `VALID` / `VOID` / `UNUSABLE`.
  Every ambiguous result in this project has come from missing one of those three checks.
- **THE BOOT IS NOT INTERMITTENT - MEASURED 5/5.** `build/tmp/luofu-uImage-wdt8-slice` reached the
  tick `C18 = 0xC0DE502D` in 5 of 5 valid runs, every run passing the harness's boot_id and
  slot-identity checks. An earlier "intermittent" reading came from ONE pair of runs scored by the
  buggy harness - **a single pair cannot distinguish "intermittent" from "one measurement was
  invalid"**. Rate-test a build (n>=5) before claiming anything about variance.
- **A RATE, NOT A VALUE.** Any claim of the form "fix X did nothing" needs the same n>=5 rate test,
  or it is a single sample asserting equality with another single sample.
- **COMPARE LIKE WITH LIKE.** An md5 of the whole image and an md5 of its first 1 MB are different
  numbers for a good image. A verification that compares them will declare every run VOID - which is
  exactly what happened, twice.
- **Read the cell's PROVENANCE, not just its value.** `0xC0DE502D` is OUR tick crumb (a controlled
  vendor boot does not write it - verified 3 ways); `0xC0DE5004` is OUR step-4 crumb. A crumb cell
  whose writer has not been proven will produce confident nonsense - every sysctrl cell in this
  project except a proven few is shared between the FMC driver and the mach.
- Never write CA `0x400392f0`. Never read the RC misc window `0x10161000`
  (a read-only `devmem` there PANICKED the box). Never `rmmod` the vendor modules.
- Tracked text carries placeholders only: `<ROUTER-SSH-PASSWORD>`,
  `<ROUTER-WEB-PASSWORD>`, `<DEVICE-SECRET>`. Live values come from gitignored
  `.omo-secrets/` at runtime.
- Long device runs go DETACHED, with the device-side watchdog armed BEFORE the
  vendor modules are hidden.
- Leave the router healthy: 2 wiphys, 6 interfaces, calibration `[SUCC]` on both
  bands, no `.omo-off` leftovers.
- **A fallback to the vendor slot leaves `boot_reg = 0x10` and the box on slot A**, which is why
  Wi-Fi reads 0 wiphys / 0 interfaces after a fire. That is a consequence of the fire, not a
  separate fault.
