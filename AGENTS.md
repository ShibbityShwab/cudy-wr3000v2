# PROJECT KNOWLEDGE BASE

**Updated:** 2026-11-16
**Read first:** `BENCH-FACTS.md` (physical invariants), `STATUS.md` (only live state),
`RUNBOOK.md` (procedure), `LESSONS.md` (rules that cost fires).
**This file holds no volatile state.** If a state claim appears here, it is a bug: fix the
doc instead of acting on it.

## OVERVIEW

Offensive-research notebook for a Cudy WR3000 v2.0 router, HiSilicon luofu v2-class board:
Hi5671YV200 SoC (2x Cortex-A9), Hi5622v100 Wi-Fi, 128 MB NAND, 128 MB DDR3, stock OpenWrt
22.03.6 on kernel 5.10.201. The enclosure label may say WR3000 v1; the PCB is the luofu v2
design, **not** the MediaTek MT7981 v1. Read `HARDWARE-IDENTITY.md` before any UART/firmware work.

Two tracks, deliberately separated:
1. **Bench reversal** (`PLAN-FULL-REVERSAL.md`): our kernel + the vendor userspace on this
   unit. This is the current work and the hybrid image is a research instrument, not a release.
2. **Upstream submission** (`opensource/docs/ROADMAP-OPENWRT.md`): own OpenWrt target,
   clean-room drivers, accepted in `openwrt/openwrt`. **Not on track today**: no target,
   DTS, image recipe or driver series exists, and the Wi-Fi + LAN-switch + GPL source
   questions are open. Do not present bench gates as upstream progress.

The published half is the `opensource/` submodule. The root repo is private research
material and must stay private until the publish-boundary cleanup in
`EVIDENCE-INDEX.md` is done (it tracks vendor-derived binaries/Lua and dumps).

## START OF SESSION (do this, in order)

1. `tools/session-brief.sh` - one-screen git/doc/bench state, including warnings.
2. Read `BENCH-FACTS.md`, then `STATUS.md` (only `## Next action`), then `LESSONS.md`.
3. If the task touches the device: `tools/bench-link.sh` must PASS and the recovery door
   must be READY (`tools/recovery-card.sh`). No human at the bench = no fire.
4. Never trust memory, chat history, or a doc's stale paragraph over a live check. The newest
   dated `mem-entries.md` entry wins over any older claim; `STATUS.md` wins over
   `CURRENT-TRUTHS.md`, `README.md`, and `PLAN-FULL-REVERSAL.md`.

## HARD RULES (physical - breaking one has stranded the box)

- **UART is READ-ONLY.** Router TX reaches the host with the swapped pins; host-to-router TX is
  dead (burnt resistor) and must never be attempted. No typing, no `echo`/`printf` to the tty,
  no `screen`/`minicom`/`picocom`, no U-Boot abort-key floods, no read-write tty open
  (the `3<>` form). Capture with
  `tools/uart-capture.sh` (read-only) and to an absolute path.
- **Bench link:** router LAN port `eth2` <-> host USB-Ethernet `enp195s0f3u1`; keep it
  NetworkManager-unmanaged with `192.168.1.88/24` (TFTP recovery) and `192.168.10.44/24`
  (vendor LAN). Check/fix with `tools/bench-link.sh`.
- **Recovery is physical:** power-off + RESET held through the counter + TFTP
  (`tools/recovery-card.sh`). An agent cannot recover alone; every fire is human-attended with
  the recovery door armed first.
- **No blind flash writes:** the slot pair and handover must be validated
  (`tools/fire-preflight.sh` + `tools/fire-device.sh`), and `STATUS.md` must name the delivery
  plan. A fire written to the wrong slot or with the wrong handover costs a recovery cycle.
- Never flash a WR3000 v1 / MediaTek image.
- Never write CA `0x400392f0`. Never read the RC misc window `0x10161000`. Never `rmmod`
  the vendor modules.
- Never replace `/etc/rc.d/luofu` wholesale; `hi_kpinctrl` is load-bearing.
  `tools/check-init-shadow.sh` must PASS before any fire (it is a source guard, not an
  artifact proof).
- Snapshot calibration before an experiment; never restore without a verified
  `MANIFEST.sha256`. A snapshot marked incomplete must not be applied.
- Never commit credentials or vendor binaries/objects. Live values come from `.omo-secrets/`
  (gitignored). The published `opensource/` half must never contain vendor `.o/.ko`,
  firmware blobs, calibration data, or extracted DTS.

## ENVIRONMENT (THIS CHECKOUT)

- Linux workstation, repo root here. Device `root@192.168.10.1`; key
  `.omo-secrets/router_ed25519`; use `tools/rsh.sh`/`tools/rscp.sh`.
- Python: `.provision-venv/bin/python` for the dependency tools
  (`tools/requirements.txt`; stock `python3` is 3.14 and lacks the packages).
- Kernel working tree: `build/linux-kbuild/linux-5.10.201` (gitignored, source of truth).
  Tracked mirror: `tools/lab-src` (`tools/check-lab-src.sh`).
- Toolchain: `build/linux-kbuild/toolchain/bin/arm-none-linux-gnueabihf-`.
- Slice build: `build/linux-kbuild/build-3dl.sh` (zImage + `luofu-r116.dtb` + fixed 40,732-byte
  trailer). The trailer is local evidence only and must never be rebuilt from an arbitrary slice.
- Fire entrypoint: `tools/fire.sh` (preflight-gated). Per-phase scripts under
  `build/linux-kbuild/` are gitignored.

## WHERE TO LOOK

| Task | Location |
| --- | --- |
| Physical facts, UART, bench link, recovery, slots | `BENCH-FACTS.md` |
| Live state, gates, blocker, next action | `STATUS.md` |
| Build, fire, readout, recover | `RUNBOOK.md` |
| Durable rules | `LESSONS.md` |
| Claim -> artifact -> regeneration | `EVIDENCE-INDEX.md` |
| Bench reversal plan | `PLAN-FULL-REVERSAL.md` |
| Upstream roadmap / GPL request / publication | `opensource/docs/` |
| Session brief / checks / teardown | `tools/session-brief.sh`, `tools/check-repo.sh`, `tools/bench-teardown.sh` |
| UART capture (read-only) | `tools/uart-capture.sh` |
| Fire gate / recovery card | `tools/fire-preflight.sh`, `tools/recovery-card.sh` |
| Kernel source (live / tracked) | `build/linux-kbuild/linux-5.10.201` / `tools/lab-src` |
| Firmware unpack / Lua bytecode | `tools/extract_firmware.py`, `patched/`, `tools/luadump.py` |
| History (not instructions) | `docs/archive/README.md` |

## CONVENTIONS

- The ledger is append-only: append a dated entry to `mem-entries.md` and regenerate the index
  with `python3 tools/gen-ledger-index.py`. The newest dated entry wins.
- Evidence goes under `build/` (gitignored); phase evidence in
  `build/linux-kbuild/waves/<phase>/`, console captures in `build/uart-logs/`. `/tmp`
  is not evidence. If a claim matters, add it to `EVIDENCE-INDEX.md` with a regeneration command.
- End of session: `tools/bench-teardown.sh --apply` (drop stale log writers/HTTP servers;
  leave TFTP only if a recovery is genuinely armed), regenerate `STATUS.md`, add the ledger entry,
  run `tools/check-repo.sh`, commit.
- Scratch and retired tools live in `tools/archive/`. `docs/archive/` is history; do not act on it.
