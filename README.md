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
boot survival:** our kernel runs ~78 s and returns, and nothing answers on the wire yet.

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

### What is left, in order

1. **Un-strand the board** - it is sitting in our kernel with Ethernet down; the
   recovery door is armed. Bound the NAND erase-verify loop to a sample so boot
   cannot hang before the safety timer (`mem-entries.md` PHASE 50fn).
2. **Finish C6 NAND** - erase race + UBI/JFFS2 attach. Blocks any from-source boot.
3. **C7 Ethernet/switch driver** - the 0% item nobody started.
4. **Fill the stub drivers** - clk `set_parent`, pinctrl `set_mux`, PCIe LTSSM writes.
5. **The Wi-Fi wall + data path** - split by what a host can still do vs what
   needs the vendor source or a device-side trace.

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

- Never write CA `0x400392f0`. Never read the RC misc window `0x10161000`
  (a read-only `devmem` there PANICKED the box). Never `rmmod` the vendor modules.
- Tracked text carries placeholders only: `<ROUTER-SSH-PASSWORD>`,
  `<ROUTER-WEB-PASSWORD>`, `<DEVICE-SECRET>`. Live values come from gitignored
  `.omo-secrets/` at runtime.
- Long device runs go DETACHED, with the device-side watchdog armed BEFORE the
  vendor modules are hidden.
- Leave the router healthy: 2 wiphys, 6 interfaces, calibration `[SUCC]` on both
  bands, no `.omo-off` leftovers.
