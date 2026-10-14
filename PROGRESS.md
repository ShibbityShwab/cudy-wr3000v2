# PROGRESS - one honest ledger for the whole project

Generated 2026-10-11, **audited 2026-10-11 against the artifact record**. This is the single file that
answers "how much is left?". Every score carries a *receipt* - the artifact that verified it.
It is measured from the artifacts in this repo (214 phase reports, 425 tracked
submodule files, ~140 lab programs, mem-entries.md), not from memory. The
machine-readable twin is `progress-data.json`; the visual version is
`PROGRESS.html` (open in a browser).

There is no build step and no test suite for this repo, so a "score" here means:
**how far the artifact record proves this subsystem has been carried.**

---

## The one number

| | score |
| --- | --- |
| **REVERSAL** (reading the closed Wi-Fi stack) | **~68%** |
| **REBUILD** (our own kernel + our own OpenWrt: sections C+D) | **~45%** |
| **OVERALL** toward the stated goal | **~56%** |

**2026-10-14: the Ethernet wall fell.** C7 went from "not started" to working - the MAC is
configured from a live PHY link for the first time (`mac_link_up` fires, 100 Mbps). C and the
REBUILD total move with it. What now gates the goal is no longer the NIC but **boot survival**:
our kernel runs ~78 s and returns, and nothing answers on the wire yet.

The goal you set (2026-10-05): *our own fully-current OpenWrt - our kernel + our
drivers, no vendor kernel.* Measured against that, the **reversal** (reading the
hardware) is most of the way done; the **rebuild** (writing our own kernel and
Wi-Fi stack) is roughly a third and is the multi-month item.

---

## A. Reversal - reading the hardware (~84%, the strong half)

| # | subsystem | score | state | evidence |
| --- | --- | --- | --- | --- |
| A1 | Device/SoC identification | 100% | done | DT `hsan-luofu/R116`, 2x PCIe `59e7:0005`; `DRIVER-BLACKBOX.md` |
| A2 | Wi-Fi firmware blob opened | 95% | done | 928,920 B md5 `0e530b97` disassembled+symbolised; `phase4`, `phase6`; 77 handlers `phase25` |
| A3 | Register / BAR map | 90% | done | both EPs' BARs; viewports byte-identical to live vendor boot; `phase11`, `phase18`, `phase23` |
| A4 | Vendor config API (alg table) | 100% | done | all 414 entries extracted; `phase3/alg-commands.md` |
| A5 | Radio calibration store | 95% | done | store + populator mapped, `calread`/`calwrite` run live; `phase7-13` |
| A6 | HCC message protocol | 90% | done | envelope + 6 tables/77 handlers + full vocabulary; `phase5`, `phase25`, `phase37` |
| A7 | ETE SR/DR ring map | 90% | done | 3 SR + 4 DR decoded, 8-byte node format verified; `phase13`, `phase42`, `phase43` |
| A8 | FMC/NAND controller spec | 85% | done | full `tri_fmc_reg_s` map from DWARF + live readbacks; `phase50` |
| A9 | Interrupt path (ctrl-rb -> GIC) | 70% | **blocked** | every host-side move landed; device-internal delivery never fires; `phase48/host-side-closed.md` |
| A10 | Wi-Fi host<->device dialogue | 55% | **blocked** | id6->id2 + 9/9 CPU-start elicited, but the H2D dispatcher is never entered; 20+ host hypotheses eliminated; `phase24` |

**A9/A10 are the same wall seen twice**: the last hop is *inside the chip*, past
anything a PCIe host can touch. Two instruments could open it and **both are
confirmed unavailable**: JTAG/ROM-monitor (no hardware evidence the board
exposes it) and the vendor source (requests to Cudy and Jeton unanswered).

## B. Wi-Fi driver - our own (`wifidrv` line) (~48%)

| # | subsystem | score | state | evidence |
| --- | --- | --- | --- | --- |
| B1 | wiphy registration | 100% | done | `wifidrv0` registers `omo-drv0` **and** netdev `omowl0` on device; `PORT-STATUS.md` |
| B2 | Endpoint claim + viewports | 85% | done | both EPs claimed, six iATU viewports programmed to vendor values; `phase23` |
| B3 | Firmware load + CPU release | 90% | done | `diffs=0`, `0x5a5a` release, CPU-start 9/9; `phase23/firmware-speaks.md` |
| B4 | SR post + ring exchange | 70% | partial | SR post consumes (id6 trigger proven); DR commit measured, device never deposits; `phase24` |
| B5 | H2D message send | 40% | **blocked** | write lands, device won't accept - needs the vendor chip-layer TX-credit callback a takeover never installs; `phase24/tx-credit-flow-control.md` |
| B6 | Data path (RX/TX) + cfg80211 ops + TXBF/rate/DFS | 10% | **not started** | never reached; the vendor MAC is 1.24 MB / 3,847 functions; `DRIVER-BLACKBOX.md` |

**B5/B6 are gated on A9/A10 and on B6 being genuinely enormous** - the vendor MAC
is a full 802.11 stack (`hmac_` 1,853 fns, `wal_` 990, `hdpp_` 208, `alg_` 199),
not a thin mac80211 driver.

## C. SoC / kernel bring-up - our own kernel (~45%, moved from 34% on 2026-10-14 by C7)

| # | subsystem | score | state | evidence |
| --- | --- | --- | --- | --- |
| C1 | Device tree | 70% | partial | 647 lines / 23.6 KB reconstructed DTS (1,581 counted comments); `docs/soc/luofu-r116.dts` |
| C2 | Kernel config fragment | 75% | partial | `luofu.fragment` CI-checked; 12 driver-less `CONFIG_*_LUOFU` remain; `lab/luofu-kernel` |
| C3 | CRG clock/reset driver | 45% | code exists | `luofu-clk.c`: 16 gates/2 muxes/2 PLLs, real clk_ops, CI builds `.ko`; `set_parent` stubbed |
| C4 | Pinctrl/IOMUX driver | 40% | code exists | 37 pins/24 groups/24 fns transcribed; compiles; `set_mux`+pinconf are **no-op stubs** |
| C5 | PCIe host driver (DWC) | 25% | code exists | `luofu-pcie.c` 1,367 lines; LTSSM/mode/IATU writes all **commented out** (lines 1229-1262); read-only |
| C6 | NAND/FMC controller driver | 55% | code exists | `luofu-fmc.c` 3,422 lines; **erase measured working** (WREN 0x06 + `FMC_OP` 0x81); open = erase race + UBI/JFFS2; board stranded |
| C7 | Ethernet GMAC/MDIO/switch driver | 75% | **working - link up, MAC configured** | four bugs fixed 2026-10-14: MDIO resets never deasserted (-EIO); MAC link config was an empty stub; MAC<->PHY mapping shifted by one; netdev never opened so phylink never polled. MEASURED: `mac_link_up` fires with `SPEED_100`, PHY BMSR 0xCDEF (link + autoneg), `phylink_of_phy_connect` returns 0 |
| C8 | Boot chain / U-Boot source | 10% | **not started** | blobs only (no source); A/B flashing recipe de-risked |
| C9 | UART/GPIO/watchdog/thermal | 20% | partial | UART/GPIO reuse mainline; watchdog+thermal from-scratch (small); none written |

**C7 is the invisible giant**: three Ethernet/switch drivers that nobody has
started, each comparable to the PCIe or NAND work.

## D. Userland + deployment (~34%)

| # | subsystem | score | state | evidence |
| --- | --- | --- | --- | --- |
| D1 | Custom image + A/B flashing | 90% | done | `omo-minimal-0.3` flashed to slot B, verified 3 ways; `FLASH-PLAN.md` |
| D2 | Vendor web RCE + SSH lane | 100% | done | systime RCE writeup; ssh lane restored |
| D3 | Modern userland on vendor kernel | 75% | proven | 24.10.5 binary + ubus IPC round trip measured on vendor 5.10.201; `phase26` |
| D4 | Upstream OpenWrt target | 0% | **not started** | no target exists or is close; needs ALL of C plus B6; `DEPLOYMENT-DECISION.md` |
| D5 | Vendor GPL source access | 0% | **blocked** | both requests unanswered; port blocked at link time without it (211 `import_ns` symbols); `PORT-SURFACE.md` |

---

## Why the project felt "out of hand" - and what actually happened

It is not one project. It is **two**, run in the same repo by the same agent:

1. **The reversal** (phases 2-49) - read the closed Wi-Fi stack. This is ~84%
   done and its frontier is a genuine hardware wall (A9/A10), not disorganisation.
2. **The rebuild** (lab/luofu-* + phases 50-*) - write our own kernel + Wi-Fi
   stack for a SoC with **zero mainline support**. This is ~34% done and is the
   multi-month programme.

The sprawl is real: 50 phases, 214 reports, 140 lab programs, three overlapping
plan docs (`PORT-PLAN`, `UPSTREAM-PORT-PLAN`, `HYBRID-IMAGE-PLAN`) and a ledger
8,418 lines long. **That volume is the record of a genuine research campaign,
but nothing was ever rolled up into a single scoreboard** - which is exactly the
gap this file closes.

## What is genuinely left, in priority order

1. **Un-strand the board** (immediate, engineering). The device is stuck in our
   kernel with Ethernet down; the recovery door is armed and has fetched once.
   The fix already decided: bound the erase-verify loop to a sample (~22 reads,
   not 176) so boot cannot hang before the safety timer. `mem-entries.md` PHASE 50fn.
2. **C6 NAND finishing** - erase race + JFFS2/UBI attach. Blocks any from-source boot.
3. **C7 Ethernet/switch driver** - the 5% item that gates a usable network.
4. **C3/C4/C5 fill-in** - turn the stubs (clk `set_parent`, pinctrl `set_mux`,
   PCIe LTSSM writes) into working drivers.
5. **A9/A10 + B5/B6** - the Wi-Fi wall and the data path. Split the ceiling in
   two: what a host can still do vs what needs the vendor source or JTAG.

## The honest ceiling

The Wi-Fi deliverable is **not achievable on this hardware without one of**:
the vendor source (both requests silent), or a device-side trace (no JTAG). Every
host-side avenue is measured-closed (`phase48/host-side-closed.md`). The SoC
rebuild deliverable is achievable but is research-scale - the plan's own estimate
is single-digit person-months for the kernel half and three times that for the
Wi-Fi datapath.
