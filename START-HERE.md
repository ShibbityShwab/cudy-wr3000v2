# Start here

Work from THIS directory. Earlier sessions ran in the user home directory, which is not a git
checkout, so `task.isolation.enabled` could never apply and DAG nodes / isolated swarms were refused.
From this repo they work.

    cd C:/Users/ShibbityShwab/Documents/GitHub/cudy-wr3000v2

## Layout

- `tools/` - `exp.sh` (one full device cycle), `batch.sh` (N hypotheses in ONE boot),
  `run-exp-detached.sh` (survives agent death), `restore-now.sh` (returns the router to stock),
  `wifi-*.sh`, `wifictl.sh`
- `opensource/` - git SUBMODULE -> `ShibbityShwab/cudy-wr3000v2-open-firmware` (the published
  payload: `docs/phase*/` analyses, `lab/` modules, `.github/workflows` build job)
- `build/`, `dumps/`, `firmware/`, `stock/`, `rootfs-*/`, `decomp/`, `pyenv/`, `jtools/` - ignored:
  binaries and dumps
- `.omo-secrets/` - ignored: `CREDENTIALS.txt`, the router SSH keys, scratch u-boot files

## Research state (2026-10-03) - read this before acting on anything older

The investigation ran from phase 1 to phase 25. **Three findings in phases 23-25 invalidate conclusions that
earlier docs still state**, so check them against the phase docs before relying on an older claim:

1. **The message window base was one page low.** Phases 23-24 found the port reading `BAR0+0x3f0000`
   where the message registers are at `BAR0+0x3f1000`, so *every* "the firmware is silent" result before
   that was measuring the wrong page. Root cause and the circular-verification story:
   `opensource/docs/phase23/ROOT-CAUSE-window-base.md`.
2. **The device's "plat ready" is id 2, not id 1** - and every run receives it. An older note said no
   such word arrives; that was wrong in its id and wrong in conclusion. The id map:
   `opensource/docs/phase24/handler-table.md`.
3. **A host announcement is only read if it is pending AT RELEASE.** The firmware clears the message
   registers during its own boot, so the `out[0]` announce must be written before the release - every
   post-release send in phases 24d-24t was posted too late to be seen:
   `opensource/docs/phase25/in-post-announce-consumed.md`.
4. **The announcement turns out not to matter at all** (phase 27, newer than the entry above). With
   `sr_announce=0` - the mailbox completely untouched - the **SR ring alone** still elicits the full id-6
   then id-2 dialogue and 9/9 CPU-start: `opensource/docs/phase27/h1-ring-alone-elicits-dialogue.md`.
   So the phase-25 "consumption" was a side-effect of the firmware's own boot touching the mailbox, not a
   trigger. Point 3 remains true as a measurement; it is simply not load-bearing.

**Where it stands (updated 2026-10-04, through phase 35).** The port owns EP0, programs the viewports and
rings, loads and verifies the firmware, releases the CPU (9/9 signature), posts SR descriptors that the
device consumes, and elicits the firmware's dialogue (`out[1]` id 6 then id 2). **The host side is now
closed by measurement** - the message content (14 candidates, including byte-exact copies of both real
vendor frames), the announce, the ring geometry, the DR ring, the doorbell value (1 and 8), and the
endpoint (EP0 AND EP1) have all been eliminated:
`opensource/docs/phase27/dr-ring-free-running.md` and `CUSTOM-FIRMWARE-PLAN.md` section 6 carry the table
of *what closed each candidate*. The verified static lanes (phase 32) located the firmware's real
interrupt chain - the H2D dispatcher's interrupt line is **id 0x4C** (fn 0x40295 via the stub at file
0x294->0x818AC), and the vendor rings the H2D doorbell through **EP1** (phy_devid-keyed dev[0]) - then
the live runs closed the rest: the interrupt block (pending 0x4016010C, enables 0x40161100) is
**PCIe-unreachable** (a spare iATU viewport returns the no-decode signature), and the dispatcher's ack
**never pulses even at 100us** across the announce consumption, which is a boot reset of the message
block, not a message read (`opensource/docs/phase35/dispatcher-never-runs.md`). The gate is the
device-internal forwarding from the mailbox doorbell to interrupt line 0x4C; the remaining instruments
are a **device-side trace (JTAG/ROM-monitor)** or the **vendor source** (the Jeton request, set aside by
the human's 2026-10-04 decision to finish self-contained).
`opensource/docs/phase32/THE-GATE-MAP.md` carries the verified chain and the priority list.

The **firmware half** is settled too (`opensource/docs/phase28/firmware-half-settled.md`): the curated
in-place upgrade is a measured no-op (433 packages installed, 0 upgradable), the wholesale modern rootfs
was declined on 2026-10-03, and the from-source build needs the vendor. `opensource/docs/PORT-STATUS.md`
remains the current summary.

**Before every build**, run `node opensource/lab/wifidrv1/tools/prebuild-check.js` in the module
directory. It sweeps for declarations used before they are declared, unbalanced braces, unlabelled
`goto` targets, and any write to the forbidden CA - each of those has cost a real build failure.

## Secrets

Tracked text carries markers only: `<ROUTER-SSH-PASSWORD>`, `<ROUTER-WEB-PASSWORD>`,
`<DEVICE-SECRET>`. Read the live value from `.omo-secrets/` (or the environment) at runtime; never
paste one back into a file git tracks. Build an askpass at runtime rather than storing one.

## Device experiments

    bash tools/exp.sh <module.ko> [params]        # full cycle, prints EXP RESULT: PASS|FAIL
    bash tools/batch.sh <list>                   # N hypotheses, ONE boot, per-entry result.txt

Run the device cycle DETACHED (`tools/run-exp-detached.sh`) so a dead agent cannot strand the router
in takeover configuration with Wi-Fi down. The router-side watchdog must be armed BEFORE hiding the
vendor modules; that ordering is enforced in the runner.

## Builds

No local ARM toolchain: push to a feature branch and let the GitHub Actions job build the `.ko`
(`opensource/.github/workflows/build-load-test-module.yml`). `gh.exe` is at `~/.local/gh/gh.exe`.

## Tools added in phases 23-25 (in `opensource/`, not here)

- `lab/wifidrv1/` - the port driver: claim, viewports, rings, SR post, firmware load, release, mailbox
  service, H2D send, ring watch. Its params are the experiment surface (`srpost`, `sr_desclen`,
  `sr_announce`, `drpost`, `msgsvc`, `send`, `rearm_val`, `pollms`).
- `lab/wifidrv1/tools/prebuild-check.js` - the pre-build sweep above.
- `build/tmp/dis3.py`-style symbol disassembly: `pyenv/Scripts/python.exe dis3.py <ko> <symbol> [n]
  [thumb]` (handles a string `st_shndx` that trips the older `disas2.py`).
- `docs/phase24/` and `docs/phase25/` - 27 reports, including the negative results; the notebook's value
  is as much in what has been **eliminated** as in what works.

## Hard rules

- Never write CA `0x400392f0`. Never read the RC misc window `0x10161000`. Never rmmod the vendor
  modules.
- Router must end healthy: 2 wiphys, 6 interfaces, calibration `[SUCC]` on both bands, no `.omo-off`
  leftovers.
