> **ARCHIVED 2026-11-15.** This file is history. Its state claims are not current.
> The live status page is [`STATUS.md`](../../STATUS.md); the procedure is [`RUNBOOK.md`](../../RUNBOOK.md).

# Start here

## Current state (2026-11-15) - recovery is proven, the network path is ours

The stock 2.4.15 firmware is back on the box and provisioned (Wi-Fi `cudy-lab`, admin password set by
`tools/box-provision.sh`, root telnet on 23). The lab kernel and drivers are all committed; the next
fire is `build/linux-kbuild/run-phase3dc.sh` (the filtered-shadow image, `7c6a2b3`).

What was proven and what it cost:

- Our `luofu-mdio` completes real C22 transfers and our `luofu-gmac` trains `eth2` to 1Gbps; the PHY
  IDs read back `0x20669a09`. The only vendor piece left in that path was `hi_kphy`.
- A shadow that replaced `/etc/rc.d/luofu` with a no-op took the box off the network (no `hi_kpinctrl`
  means no pinmux, no MDIO, no Ethernet, no Wi-Fi). Never do that: `tools/check-init-shadow.sh` must
  print PASS before any fire, and it verifies that the filter keeps everything except the three modules
  our drivers own.
- Recovery, proven twice: hold reset during power-on, the U-Boot prints `recovery button press`, and it
  tftpboots `recovery.bin` from `192.168.1.88` (run `tools/tftp_server.py 69`; the official image is at
  `tftp/recovery.bin`). The stock LAN comes up at `192.168.10.1` on a LAN port.
- Root on stock, no SSH: `tools/box-provision.sh --bdinfo dumps/router-20261108/bdinfo.bin ...` uses the
  broker's JWT channel and returns command output. The stock image has neither dropbear nor opkg.
- A recovery flash wipes `rootfs_data`, so the patched vendor modules must be re-pushed before a fire.

The safe fire protocol from here: check the guard, re-push the patched modules, fire, and if the box
does not answer, the web admin password plus the systime RCE or the broker channel gets root back, and
`fw_setenv bootflag a` returns the box to stock without a reset-hold.

## Current state (2026-11-12) - read this block before anything below

The kernel work is in `build/linux-kbuild/linux-5.10.201` (a gitignored working tree, the source of
truth) and drives the "overlay finish" lane. `STATUS.md` is the current gate table and
`PLAN-FULL-REVERSAL.md` is the phase plan; both are newer than the phase docs below. The device
cycle is `build/linux-kbuild/run-phase*.sh` (detached, ~12.5 min per fire); read the verdict cells
from `C94` after the vendor returns. `.sshwrap/` does not exist in this checkout; the fire scripts
use `.omo-secrets/router_ed25519` directly.

As of 2026-11-12: our kernel boots from the B slot, the vendor squashfs mounts through `ubiblock0_0`,
the jffs2 upper mounts, and overlayfs assembles. The write path was closed by two fixes - jffs2's
write buffer enabled by typing `rootfs_data` as NOR at probe, and the erase-complete marker routed
through that buffer - with the full ladder and receipts in `mem-entries.md` (2026-11-11/12) and
`opensource/docs/phase54-jffs2-write-path.md`. Next: prove the file persists across a reboot, then
run the vendor `/sbin/init` on our kernel (Phase C, including the vendor-init variant in the plan).

## Older handoff (2026-10-03)

Work from THIS directory. Earlier sessions ran in the user home directory, which is not a git
checkout, so `task.isolation.enabled` could never apply and DAG nodes / isolated swarms were refused.
From this repo they work.

    cd C:/Users/ShibbityShwab/Documents/GitHub/cudy-wr3000v2
    # Linux workstation: /home/shibbityshwab/Documents/GitHub/cudy-wr3000v2

## Layout

- `tools/` - `exp.sh` (one full device cycle), `batch.sh` (N hypotheses in ONE boot),
  `run-exp-detached.sh` (survives agent death), `restore-now.sh` (returns the router to stock),
  `wifi-*.sh`, `wifictl.sh`
- `opensource/` - git SUBMODULE -> `ShibbityShwab/cudy-wr3000v2-open-firmware` (the published
  payload: `docs/phase*/` analyses, `lab/` modules, `.github/workflows` build job)
- `build/`, `dumps/`, `firmware/`, `stock/`, `rootfs-*/`, `decomp/`, `pyenv/`, `jtools/` - ignored:
  binaries and dumps
- `.omo-secrets/` - ignored: `CREDENTIALS.txt`, the router SSH keys, scratch u-boot files

## Hardware identity (2026-11-08)

The label may say WR3000 v1, but the PCB is the HiSilicon luofu v2-class board (Hi5671YV200 +
Hi5622v100), not the MediaTek MT7981 v1. The v1 FCC filing and photos do not apply, and the
WR3000 v2 firmware is the correct one. The UART console cannot stop U-Boot on this build:
`input <abort key>` is a keyed-autoboot prompt with no stop key in the default environment;
Enter and Ctrl+C fail, and the reset button triggers Linux `PRESET RESET`, not U-Boot. See
`HARDWARE-IDENTITY.md` for the evidence and the measured limits.

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

**Where it stands (updated 2026-10-04, through phase 48).** The port owns EP0, programs the viewports and
rings, loads and verifies the firmware, releases the CPU (9/9 signature), posts SR descriptors that the
device consumes, and elicits the firmware's dialogue (`out[1]` id 6 then id 2). **The host side is now
closed by measurement at the mechanism level** - the verified chain (phases 42-48) is: the doorbell
write sets the ctrl-rb raw AND masked interrupt status (0x2e4/0x2ec bit 0, phase 46), the mask is open
(the vendor's own 0x20), interrupt source 0x4C is registered AND enabled by the firmware (phase 47,
verified), both masks are written readback-verified (phase 48) - and the firmware's ack (0x400392f0)
still never flips. The gate is the device-internal delivery from the ctrl-rb's latched status to the
GIC input, inside the block phase 34 proved PCIe-invisible. Every host-side action the verified maps
name is performed to the vendor's own values; the remaining instruments are a device-side trace
(JTAG/ROM-monitor - no hardware) and the vendor source (unresponsive), both confirmed unavailable.
`opensource/docs/phase48/host-side-closed.md` and `opensource/docs/phase47/THE-LAST-LINK.md` carry
the full mechanism-level chain; `opensource/docs/phase32/THE-GATE-MAP.md` and
`opensource/docs/phase42/THE-RING-MAP.md` carry the earlier elimination tables.

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

Local, not CI. The ARM cross-toolchain is in `build/linux-kbuild/toolchain/` and the prepared tree is
`build/linux-kbuild/linux-5.10.201`. From the tree:

    make ARCH=arm CROSS_COMPILE=$PWD/../toolchain/bin/arm-none-linux-gnueabihf- -j16 zImage < /dev/null

The slice is `cat zImage arch/arm/boot/dts/luofu-r116.dtb > payload`, then `mkimage -A arm -O linux
-T kernel -C none -a 0x80608000 -e 0x80608000`, then the fixed 40,732-byte trailer from the previous
slice. `build/linux-kbuild/run-phaseNN.sh` does the flash/reboot/read-back. A `make` that sits in
`syncconfig` is waiting on stdin: redirect `< /dev/null`. Do not push to GitHub Actions to check a build.

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
