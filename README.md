# Cudy WR3000 v2.0 - reversal + port

Offensive-research notebook for a Cudy WR3000 v2.0 router: HiSilicon luofu v2-class board
(Hi5671YV200 SoC, Hi5622v100 Wi-Fi, 128 MB NAND, 128 MB DDR3, stock OpenWrt 22.03.6 on kernel
5.10.201). The enclosure may say WR3000 v1; the PCB is the luofu v2 design, **not** the
MediaTek MT7981 v1. Read [`HARDWARE-IDENTITY.md`](HARDWARE-IDENTITY.md) before any UART or
firmware work.

This file is a pointer, not a status page. **The only live state page is
[`STATUS.md`](STATUS.md).** Physical invariants are in [`BENCH-FACTS.md`](BENCH-FACTS.md);
the procedure is [`RUNBOOK.md`](RUNBOOK.md).

## The two tracks

1. **Bench reversal** ([`PLAN-FULL-REVERSAL.md`](PLAN-FULL-REVERSAL.md)): our kernel with the
   vendor userspace on this unit. This is the current bench work; the hybrid image is a
   research instrument, not a release. Current blocker: the slice-delivery lane
   (`STATUS.md` section 3).
2. **Upstream OpenWrt submission** ([`opensource/docs/TARGET-DESIGN.md`](opensource/docs/TARGET-DESIGN.md),
   [`ROADMAP-OPENWRT.md`](opensource/docs/ROADMAP-OPENWRT.md)): own target, clean-room drivers,
   accepted upstream. **Still not on track as a submission**: the concrete target/DTS/image design
   and the GPL follow-up now exist (2026-11-18); the target skeleton's structure was accepted by
   OpenWrt main (`make defconfig` + `target/linux/prepare`), the kernel platform patches now
   compile the 6.18 kernel with the correct load address, the FIP trailer format is decoded with
   a byte-exact generator, and an own-artifact FIP kernel slice was assembled and validated
   structurally (never booted) - but **no target image was built**, no DTS was `dtbs_check`ed,
   CRG clock/reset + watchdog, FMC/SPI-NAND and MDIO/PHY are ported and compile (GEMAC is an honest
   partial), but pinctrl, thermal, PCIe, the internal switch and the GEMAC data path do not exist,
   and the Wi-Fi + LAN-switch + unanswered GPL source request remain the gating programme. Bench
   gates are not upstream progress.

## Start here

| what | where |
| --- | --- |
| One-screen live context | `tools/session-brief.sh` |
| Physical invariants (UART read-only, bench link, recovery, slots) | [`BENCH-FACTS.md`](BENCH-FACTS.md) |
| Live state, gates, blocker, next action | [`STATUS.md`](STATUS.md) |
| Curated summary (STATUS wins) | [`CURRENT-TRUTHS.md`](CURRENT-TRUTHS.md) |
| Build, fire, read, recover | [`RUNBOOK.md`](RUNBOOK.md) |
| Rules that have cost fires | [`LESSONS.md`](LESSONS.md) |
| Claim -> artifact | [`EVIDENCE-INDEX.md`](EVIDENCE-INDEX.md) |
| Bench reversal plan | [`PLAN-FULL-REVERSAL.md`](PLAN-FULL-REVERSAL.md) |
| Unit identity and UART limits | [`HARDWARE-IDENTITY.md`](HARDWARE-IDENTITY.md) |
| Ledger index | [`mem-entries-INDEX.md`](mem-entries-INDEX.md) |
| History (not instructions) | [`docs/archive/README.md`](docs/archive/README.md) |

## Repository map

| path | what |
| --- | --- |
| `tools/` | live harness: `fire.sh` (preflight-gated), `fire-preflight.sh`, `recovery-card.sh`, `uart-capture.sh` (read-only), `bench-link.sh`, `session-brief.sh`, `check-repo.sh`, `box-provision.sh` (broker), `rsh.sh`/`rscp.sh`, crypto/RE tools |
| `tools/archive/` | retired scratch and the old Wi-Fi lane (device-mutating; do not use) |
| `tools/lab-src/` | tracked mirror of the modified kernel sources (`tools/check-lab-src.sh`) |
| `build/linux-kbuild/` | gitignored kernel tree, toolchain, slices, fire logs, calibration snapshots, evidence (source of truth, local) |
| `patched/` | de-crypted stock LuCI bytecode (LuaQ); evidence, not source - private |
| `opensource/` | git submodule, the published half: docs, lab modules, vendor-stack recipe, roadmap |
| `docs/archive/` | retired status pages and plans; history only |
| `mem-entries.md` | append-only evidence ledger; use the index |

## Hard rules (full list in BENCH-FACTS/AGENTS)

- **UART is READ-ONLY** (host->router TX dead, burnt resistor). Capture read-only with
  `tools/uart-capture.sh`; never transmit, never `exec 3<>`, never chase the U-Boot prompt.
- **Bench link:** router `eth2` <-> host USB-Ethernet `enp195s0f3u1`; keep it unmanaged with
  `192.168.1.88/24` + `192.168.10.44/24` (`tools/bench-link.sh`).
- **Recovery is physical** (RESET counter + TFTP) and every fire is human-attended, after
  `tools/fire-preflight.sh` and with the recovery door armed.
- Never flash a WR3000 v1 image. Never write CA `0x400392f0`, never read `0x10161000`, never
  `rmmod` vendor modules. Never replace `/etc/rc.d/luofu` wholesale.
- Snapshot calibration before an experiment; never restore without a verified
  `MANIFEST.sha256` (incomplete snapshots are refused).
- Never commit credentials or vendor binaries/objects. The root repo is private until the
  publish-boundary cleanup in `EVIDENCE-INDEX.md` is complete.
