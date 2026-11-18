# Cudy WR3000 v2.0 - reversal + port

Offensive-research notebook for a Cudy WR3000 v2.0 router: HiSilicon luofu v2-class board
(Hi5671YV200 SoC, Hi5622v100 Wi-Fi, 128 MB NAND, 128 MB DDR3, stock OpenWrt 22.03.6 on kernel
5.10.201). The enclosure may say WR3000 v1; the PCB is the luofu v2 design, **not** the
MediaTek MT7981 v1. Read [`HARDWARE-IDENTITY.md`](HARDWARE-IDENTITY.md) before any UART or
firmware work.

This file is a pointer, not a status page. **The only live state page is
[`STATUS.md`](STATUS.md).** Physical invariants are in [`BENCH-FACTS.md`](BENCH-FACTS.md);
the procedure is [`RUNBOOK.md`](RUNBOOK.md).

## Curated public repos

This is an **intentionally public research notebook**: the ledger, tools, negative results and
analysis are published on purpose. The policy, licenses and provenance live in
[`PUBLISH.md`](PUBLISH.md). The curated surfaces are:

- **[cudy-wr3000v2](https://github.com/ShibbityShwab/cudy-wr3000v2)** - this repository: the
  bench reversal record, harness/tools and analysis. No vendor binaries, no credentials.
- **[cudy-wr3000v2-openwrt](https://github.com/ShibbityShwab/cudy-wr3000v2-openwrt)** - the
  curated port repo: OpenWrt target skeleton, board DTS, 19-patch kernel series, image recipe and
  a host-validated A/B install path. Host-validated only - nothing booted or flashed, and not an
  accepted upstream target.
- **[cudy-wr3000v2-cve](https://github.com/ShibbityShwab/cudy-wr3000v2-cve)** - the CVE writeups
  (CVE-2026-71960, CVE-2026-71961) with sanitized PoCs and mitigation.

The `opensource/` submodule points at **`cudy-wr3000v2-open-firmware`**, a legacy pre-policy
public repo that is superseded by `cudy-wr3000v2-openwrt`; its history is not clean (vendor `.o`
files). See [`PUBLISH.md`](PUBLISH.md).

## The two tracks

1. **Bench reversal** ([`PLAN-FULL-REVERSAL.md`](PLAN-FULL-REVERSAL.md)): our kernel with the
   vendor userspace on this unit. This is the current bench work; the hybrid image is a
   research instrument, not a release. The lab-kernel line is at its documented v17 ceiling
   (vendor HYFI/bridge ABI; `STATUS.md` section 3) and bench fires are stopped; the upstream
   driver/image work is a separate host-only track.
2. **Upstream OpenWrt submission** ([`opensource/docs/TARGET-DESIGN.md`](opensource/docs/TARGET-DESIGN.md),
   [`ROADMAP-OPENWRT.md`](opensource/docs/ROADMAP-OPENWRT.md)): own target, clean-room drivers,
   accepted upstream. **Still not on track as a submission**: the concrete target/DTS/image design
   and the GPL follow-up now exist (2026-11-18); the target skeleton's structure was accepted by
   OpenWrt main (`make defconfig` + `target/linux/prepare`), the kernel platform patches now
   compile the 6.18 kernel with the correct load address, the FIP trailer format is decoded with
   a byte-exact generator, an own-artifact FIP kernel slice was assembled and validated
   structurally, a **real target image now builds end-to-end** (`make world` RC=0, reproducible,
   host-only - never flashed or booted), and an **A/B install path exists** (selector driver +
   platform_do_upgrade implemented and mock-tested; never executed on hardware) - but no DTS was
   `dtbs_check`ed,
   CRG clock/reset + watchdog, FMC/SPI-NAND, MDIO/PHY, pinctrl, thermal, a provisional
   machine-restart driver, the PCIe host and a refusing PIE packet-engine draft are ported and
   compile (GEMAC is an honest partial; the CRG reset polarity was corrected); the internal switch
   and the PIE data-path bring-up remain, with `opensource/docs/REMAINING-DRIVERS.md`,
   `opensource/docs/LSW-SPEC.md` and `opensource/docs/PIE-DATAPATH.md` as the plans, and the Wi-Fi
   + LAN-switch + unanswered GPL source request remain the gating programme. Bench gates are not
   upstream progress.

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
| Consolidated engineering reversal report | [`REVERSAL-REPORT.md`](REVERSAL-REPORT.md) |
| Review-form kernel submission series (001-017) | [`opensource/upstream/series-6.18/README.md`](opensource/upstream/series-6.18/README.md) |
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
| `patched/` | de-crypted stock LuCI bytecode (LuaQ); evidence, not source - vendor-derived, not redistributable |
| `opensource/` | git submodule: legacy open-firmware half (docs, lab modules, vendor-stack recipe; superseded by `cudy-wr3000v2-openwrt`; pre-policy history is not clean) |
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
- **Never commit credentials or vendor binaries/objects.** The root repo is a public
  notebook: live values belong in gitignored `.omo-secrets/`, tracked text carries placeholders
  only, and per-unit identifiers use documentation values. Pre-policy public history still
  contains an older lab credential and vendor objects - see [`PUBLISH.md`](PUBLISH.md). Public
  means published forever: redact in HEAD, record it in the ledger, rotate.
