# Cudy WR3000 v2.0 - reversal + port

Offensive-research notebook for a Cudy WR3000 v2.0 router: HiSilicon luofu v2-class
board (Hi5671YV200 SoC, Hi5622v100 Wi-Fi, 128 MB NAND and 128 MB DDR3, stock OpenWrt
22.03.6 on kernel 5.10.201). The goal is our own OpenWrt on this board: our kernel, our
drivers, no vendor kernel. This repo is the tool and evidence record; the published
half is the `opensource/` submodule.

The enclosure may say WR3000 v1. The PCB is the luofu v2 design, not the MediaTek
MT7981 v1. Read [`HARDWARE-IDENTITY.md`](HARDWARE-IDENTITY.md) before any UART or
firmware work.

## Current state

The live gate table and the current blocker are in [`STATUS.md`](STATUS.md). This file
is a router, not a status page. Where this summary and STATUS.md disagree, STATUS.md
wins.

| gate | state | receipt |
| --- | --- | --- |
| **G1** FMC reads real flash | GREEN | page-0 magic `UBI#`; level-7 MTD probe found the EC magic and `vid_hdr_offset = 0x800` |
| **G2** program path | GREEN | a page written by our kernel read back byte-exact through the vendor driver |
| **G3** our kernel + real rootfs + userspace | GREEN 2026-11-14 | vendor preinit, `mount_root`, procd and the full rc.d chain run on our kernel from the squashfs root |
| **G4** Ethernet on our kernel | GREEN 2026-11-14 | vendor switch/MDIO/PHY/MAC modules load as patched modules; `eth2` up at 1 Gbps, `br-lan` 192.168.10.1, ping 3/3. Our own `luofu-mdio`/`luofu-gmac` also carry a 1 Gbps link |
| **G5** Wi-Fi on our kernel | vendor-only | the vendor modules provide the radio; the lab `wifidrv`/`hccaccept` line builds and loads but has no wiphy of its own |
| **G6** sustained uptime | GREEN 2026-11-14 | the reset was a userspace watchdog race; the initramfs keeper holds the 25-minute timer |

## Start here

| what | where |
| --- | --- |
| Current state and blocker | [`STATUS.md`](STATUS.md) |
| Curated current truths | [`CURRENT-TRUTHS.md`](CURRENT-TRUTHS.md) |
| Build, fire, read, recover | [`RUNBOOK.md`](RUNBOOK.md) |
| Rules that have cost real fires | [`LESSONS.md`](LESSONS.md) |
| Claim to evidence | [`EVIDENCE-INDEX.md`](EVIDENCE-INDEX.md) |
| Ledger index | [`mem-entries-INDEX.md`](mem-entries-INDEX.md) |
| Active plan | [`PLAN-FULL-REVERSAL.md`](PLAN-FULL-REVERSAL.md) |
| Unit identity and UART limits | [`HARDWARE-IDENTITY.md`](HARDWARE-IDENTITY.md) |
| History | [`docs/archive/README.md`](docs/archive/README.md) |

## Repository map

| path | what |
| --- | --- |
| `tools/` | current harness and CLIs: `fire.sh`, `check-init-shadow.sh`, `box-provision.sh`, `rsh.sh`, crypto and RE tools; `requirements.txt` pins the Python deps |
| `tools/lab-src/` | tracked mirror of the modified kernel sources; run `tools/check-lab-src.sh` |
| `tools/archive/` | historical scratch tools; not part of the live surface |
| `build/linux-kbuild/` | gitignored kernel tree, toolchain, slices, fire logs, calibration snapshots, and evidence; the source of truth |
| `patched/` | de-crypted stock LuCI bytecode (LuaQ); evidence, not source |
| `opensource/` | git submodule, the published half: docs, lab modules, the vendor-stack recipe, the roadmap |
| `docs/archive/` | retired status pages and plans; history only |
| `mem-entries.md` | append-only evidence ledger; use the index |

## Hard rules

- A fire must prove its own validity before its reading is believed: the boot actually
  happened, the slot identity is unchanged, and the crumb was sampled inside the window.
- A rate, not a value: "fix X did nothing" needs the same n>=5 rate test.
- Compare like with like: a whole-image md5 and a first-1-MB md5 are different numbers.
- Read the cell's provenance, not just its value: which writer wrote it last.
- Never flash a WR3000 v1 image. Never replace `/etc/rc.d/luofu` wholesale.
- Never write CA `0x400392f0`, never read `0x10161000`, never `rmmod` vendor modules.
- Snapshot calibration before any experiment; never restore without a verified
  `MANIFEST.sha256`.
- Long device runs go detached, with the device-side watchdog armed first.
- Tracked text carries placeholders only; live values come from `.omo-secrets/`.

The full procedure is in [`RUNBOOK.md`](RUNBOOK.md); the lessons and their receipts are
in [`LESSONS.md`](LESSONS.md).

## Published half

`opensource/` is a git submodule. Its docs are a snapshot, not the live status. The
current working recipes are
[`opensource/docs/VENDOR-STACK-ON-MAINLINE.md`](opensource/docs/VENDOR-STACK-ON-MAINLINE.md)
and [`opensource/docs/ROADMAP-OPENWRT.md`](opensource/docs/ROADMAP-OPENWRT.md).
