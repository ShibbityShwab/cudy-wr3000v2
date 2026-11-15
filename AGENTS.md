# PROJECT KNOWLEDGE BASE

**Updated:** 2026-11-15
**Status authority:** `STATUS.md`
**Procedure:** `RUNBOOK.md`

## OVERVIEW

Offensive-research notebook for a Cudy WR3000 v2.0 router, HiSilicon luofu v2-class
board: Hi5671YV200 SoC, Hi5622v100 Wi-Fi, 128 MB NAND and 128 MB DDR3, stock OpenWrt
22.03.6 on kernel 5.10.201. The goal is our own OpenWrt on this board: our kernel, our
drivers, no vendor kernel. This is a tool and evidence repo, not a buildable product.
The published half is the `opensource/` submodule.

The enclosure may say WR3000 v1. The PCB is the luofu v2 design, not the MediaTek
MT7981 v1. Read `HARDWARE-IDENTITY.md` before any UART or firmware work.

## READ THIS FIRST

1. `STATUS.md` - the only live status page.
2. `CURRENT-TRUTHS.md` - the curated summary; the ledger is the long form.
3. `RUNBOOK.md` - the current build, fire, readout, and recovery loop.
4. `LESSONS.md` - the durable rules that have cost real fires.
5. `HARDWARE-IDENTITY.md` - unit identity and the measured UART limits.
6. `EVIDENCE-INDEX.md` - claim, artifact, and how to regenerate it.
7. `PLAN-FULL-REVERSAL.md` - the active plan.
8. `mem-entries.md` - append-only history. Use `mem-entries-INDEX.md`, not a linear read.

`docs/archive/` is history. Do not act on its state claims.

## ENVIRONMENT (THIS CHECKOUT)

- Linux workstation. Repo: `/home/shibbityshwab/Documents/GitHub/cudy-wr3000v2`.
- Device: `root@192.168.10.1`. Key: `.omo-secrets/router_ed25519`. There is no
  `.sshwrap/` and no `pyenv/` here. Use the key directly, or `tools/rsh.sh` and
  `tools/rscp.sh`.
- Python: use `.provision-venv/bin/python` for the dependency tools (see
  `tools/requirements.txt`). Stock `python3` is 3.14 and lacks pycryptodome,
  PyJWT, paho-mqtt, and passlib.
- Kernel working tree: `build/linux-kbuild/linux-5.10.201` (gitignored; this is the
  source of truth).
- Tracked snapshot: `tools/lab-src` (a mirror; `tools/check-lab-src.sh` checks the
  manifest and completeness, `--manifest-only` is the quick check).
- Toolchain: `build/linux-kbuild/toolchain/bin/arm-none-linux-gnueabihf-`.
- Slice: `zImage` + `luofu-r116.dtb` + `mkimage` + the fixed 40,732-byte trailer. The
  pattern is `build/linux-kbuild/next-persist.sh`.
- Fire entrypoint: `tools/fire.sh`. The per-phase scripts under
  `build/linux-kbuild/` are gitignored.

## WHERE TO LOOK

| Task | Location | Notes |
| --- | --- | --- |
| Current state | `STATUS.md` | the only live status page |
| Build, fire, recover | `RUNBOOK.md`, `tools/fire.sh` | exact commands |
| Unit identity / UART | `HARDWARE-IDENTITY.md` | v1 label vs luofu v2 PCB |
| Durable rules | `LESSONS.md` | read before a device action |
| Evidence | `EVIDENCE-INDEX.md`, `mem-entries-INDEX.md` | claim to artifact |
| Kernel source (live) | `build/linux-kbuild/linux-5.10.201` | gitignored working tree |
| Kernel source (tracked) | `tools/lab-src` | mirror, drift-checked |
| Lab drivers | `opensource/lab/luofu-*` | published modules |
| Vendor stack on our kernel | `opensource/docs/VENDOR-STACK-ON-MAINLINE.md` | working recipe |
| Upstream roadmap | `opensource/docs/ROADMAP-OPENWRT.md` | plan after the hybrid |
| Web RCE / broker | `tools/forge_jwt.py`, `tools/mqtt_takeover.py`, `tools/box-provision.sh` | LAN only |
| Firmware unpack | `tools/extract_firmware.py` | hboot1tag to squashfs |
| Lua bytecode | `patched/`, `tools/luadump.py` | data, not source |
| History | `docs/archive/README.md` | do not act on it |

## CURRENT WORK

- G1 through G4 and G6 are green as of 2026-11-14; G5 is vendor-only. The gate table
  and the receipts are in `STATUS.md`.
- Current blocker: the initramfs `/vendor` mount can come up read-only on this strap,
  so the init's shadow writes are silent. The 2026-11-15 04:10 ledger entry names the
  fix: mount jffs2 with the `rw` option, check the result, and remount `rw` if needed.
  The `phase3de` slice was assembled at 11:49 from the tree with that change, but it
  has no fire log or ledger entry yet.
- The vendor's own driver stack runs on our kernel as patched modules. The recipe is
  `opensource/docs/VENDOR-STACK-ON-MAINLINE.md`.
- The old Wi-Fi reversal lane (`tools/exp.sh`, `tools/batch.sh`, `.sshwrap`) is not the
  current cycle. Do not use it for kernel work.

## HARD RULES

- Never flash a WR3000 v1 (MediaTek) image.
- Never replace `/etc/rc.d/luofu` wholesale; `hi_kpinctrl` is load-bearing.
  `tools/check-init-shadow.sh` must print PASS before any fire.
- Never write CA `0x400392f0`. Never read the RC misc window `0x10161000`. Never
  `rmmod` the vendor modules.
- Never run a device cycle in the foreground. Use `tools/fire.sh run <phase> --detach`
  or the broker lane.
- Snapshot calibration before any experiment; never restore without a verified
  `MANIFEST.sha256`.
- Arm the device watchdog before hiding vendor modules.
- Never commit credentials. Tracked text carries placeholders; live values come from
  `.omo-secrets/`.
- Leave the router healthy: 2 wiphys, 6 interfaces, calibration `[SUCC]` on both bands,
  and no `.omo-off` leftovers.

## CALIBRATION AND RECOVERY

- Before any experiment: `tools/wifi-cal-snapshot.sh` writes
  `build/linux-kbuild/cal-snapshots/<TS>/` with `MANIFEST.sha256`.
- `tools/wifi-cal-restore.sh <snap>` is a dry run; `--apply` only after the manifest
  check. Never restore without a verified manifest.
- `tools/restore-now.sh` unhides `.omo-off` files and removes the loader plus four
  hardcoded modules; other staged modules can survive. Check the module directory.
- Long runs go detached. Arm the device watchdog before hiding vendor modules.

## CONVENTIONS

- The ledger is append-only. Add a dated entry to `mem-entries.md`; the latest dated
  entry wins over any earlier claim.
- Evidence goes under `build/` (gitignored). If a claim matters, add it to
  `EVIDENCE-INDEX.md` with a regeneration command.
- Scratch tools live in `tools/archive/`. Do not resurrect them into the live surface.
- `docs/archive/` is history, not instructions.
