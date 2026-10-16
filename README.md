# Cudy WR3000 v2.0 - reversal + port

Offensive-research notebook for a **Cudy WR3000 v2.0** router (HiSilicon Hi5671Y
"luofu", board R116, dual Cortex-A9, 128 MB NAND + 128 MB DDR3; Wi-Fi
Hi5622V100 on PCIe; stock OpenWrt 22.03.6 / kernel 5.10.201, ~60 binary-only
modules and a closed 928,920-byte Wi-Fi firmware blob).

**The goal (set 2026-10-05):** our own, fully-current OpenWrt on this board -
our kernel, our drivers, no vendor kernel.

**Where the work lives:**

- `PROGRESS.md` - the canonical progress ledger (text). **Start here for "how much is left?".**
- `PROGRESS.html` - the visual version of the same ledger (open in a browser).
- `progress-data.json` - the machine-readable twin.
- `START-HERE.md` - operational handoff (device, secrets, harness, hard rules).
- `mem-entries.md` - the 8,400-line evidence ledger, phase by phase.
- `opensource/` - git submodule, the published half (docs + lab modules + CI).

---

## Progress at a glance

Measured 2026-10-11 from the artifact record: 214 phase reports, 425 tracked
submodule files, ~140 lab programs. A "score" means **how far the artifact
record proves a subsystem was carried** - there is no build/test suite in this
repo, so this is evidence-graded, not test-verified. Each score carries a receipt
(a phase report, a byte/line count, or source grep'd this session); the audit
found and corrected three scores - see `PROGRESS.md`.

| | score |
| --- | --- |
| **REVERSAL** (reading the closed Wi-Fi stack) | **~68%** |
| **REBUILD** (our own kernel + our own OpenWrt) | **~45%** |
| **OVERALL** toward the stated goal | **~56%** |

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
| Device tree (`luofu-r116`, 647 lines) | 70% | partial |
| Kernel config fragment (12 symbols left) | 75% | partial |
| CRG clock/reset driver | 45% | code exists |
| Pinctrl / IOMUX driver | 40% | code exists |
| PCIe host driver (DWC) | 25% | code exists |
| NAND / FMC controller driver | 55% | code exists |
| Ethernet GMAC / MDIO / switch driver | 75% | **working - link up, MAC programmed** |
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

**0. THE ROOT CAUSE IS FOUND, AND TWO "SEPARATE" LANES WERE ALWAYS ONE PROBLEM.**

**The FMC data path IS the boot panic.** Reading `init/main.c` all the way down closes the chain:

```
FMC read path returns 40 1f 00 00 for every page
  -> ubi_init (a late_initcall) RUNS but FAILS TO ATTACH
     (a failed attach is not a panic, so every initcall still completes)
  -> no ubiblock0_0, no root mount
  -> init_eaccess("/init") -> kern_path() walks a root-less mount tree -> FATAL
  -> the loader sees no successful hand-off -> falls back to slot A
```

The kernel's own `CONFIG_CMDLINE` says where the root comes from, and it is NAND through UBI:
`ubi.mtd=rootfsb ubi.block=0,0 root=/dev/ubiblock0_0 rootfstype=squashfs`. **UBI attach reads flash
through our own FMC driver.**

**No fire could have found this.** Every crumb sits in our driver's initcall path or later, while the
death is in `fs/init.c` after all of them - and the kernel never prints its usual *"VFS: Unable to
mount root fs"* because it dies in `init_eaccess` **before** `prepare_namespace()` tries the mount.
That is why the boot was silent and why the panic read as unreachable.
(`boot-panic-is-in-userspace-handoff.md`)

**1. FIX THE FMC READ PATH.** This is now the single blocking bug for the whole goal, not a side
concern. Evidence: `C70 = 40 1f 00 00` across seven fires, in the one sysctrl cell proven to be a
true scratch register, while the vendor's own DMA buffer fills with changing real flash data. **No
rootfs until this reads correctly - and no userspace until there is a rootfs.**

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
| `START-HERE.md`, `PLAN-UART.md`, `mem-entries.md` | handoff + evidence docs |

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
