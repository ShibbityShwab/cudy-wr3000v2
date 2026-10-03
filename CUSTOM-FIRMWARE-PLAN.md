# Custom-firmware plan: what "latest OpenWrt on the WR3000 v2.0" actually takes

Written 2026-10-02 against the moved repo (`Documents/GitHub/cudy-wr3000v2`, `master` @ `9c8514b`,
submodule `opensource` @ `omo/phase22-hccaccept` `5ee29b7`). Every claim below is marked with where it
came from. This file is the entry point; the deep detail stays in the submodule docs it cites.

## 1. Deliverable restated

A flashable custom firmware image for the Cudy WR3000 v2.0, as current as the hardware allows, plus the
evidence trail for each step. Three questions must be answered before any flashing: what upstream
support exists, what the kernel/module ABI allows, and what the bring-up + flashing path is.

## 2. What upstream support exists - answer: none, and that is not a temporary gap

> **Re-verified 2026-10-03, and now split by half.** The “no fork to join” conclusion holds for the
> **kernel** and was independently re-confirmed by a fresh search (no OpenWrt target, subtarget or device
> profile for the Hi5671; no `luofu`/`hsan` anywhere; no public Hi5622 driver). It does **not** hold for the
> **userland**: the vendor's own firmware is OpenWrt 22.03.6 with a *private target* and **stock upstream
> `arm_cortex-a9` packages**, and a **24.10.5** upstream binary has been measured running on the vendor
> kernel - see `docs/phase26/how-current-userland.md`.

- `opensource/docs/PORT-PLAN.md` (2026-10-01, [proven by inspection of the tree]): OpenWrt 25.12.5 runs
  kernel 6.12 on mainline drivers; this SoC (HiSilicon **Hi5671Y**, platform `hsan luofu`, board R116)
  has **no mainline support at all** - clock, pinctrl, PCIe host, NAND, Ethernet MAC and the internal
  switch would each need a new driver plus a device tree for this board.
- The Wi-Fi chip (Hi5622V100) is **two PCIe endpoints at `59e7:0005`**, 16 MB + 16 KB + 8 MB BARs each
  (`opensource/docs/DRIVER-BLACKBOX.md` §1, `docs/phase22/rc-routing.md` [proven, vendor dmesg + PCI
  enumeration]), with **no open driver and no public register documentation**; the radio firmware runs
  on the chip's own processor and is a closed 928,920-byte blob
  (`/lib/firmware/hi_wifi/FIRMWARE.bin`, `docs/FLASH-PLAN.md`).
- A public web check on 2026-10-02 found no upstream work under `luofu` / `hsan` / `Hi5622V100`
  (results were unrelated Hi3798/Hi1155 documents and board PDFs) - consistent with PORT-PLAN.

So "our own latest OpenWrt" is **not** `git clone openwrt && make menuconfig` for this board. There is
no fork to join; the machine has to be brought up.

## 3. ABI constraints

- The shipped modules declare `vermagic=5.10.201` (read this session from
  `build/tmp/hi5622v100_wifi.ko`); our own CI-built module carries the identical string, which is why
  the workflow pins the kernel, disables MODVERSIONS, and clears LOCALVERSION
  (`opensource/.github/workflows/build-load-test-module.yml` [read this session]).
- Linux has no stable module ABI, so **no vendor 5.10 binary can load into a 6.12 kernel**. Any hybrid
  (modern userland on the vendor kernel, or vendor Wi-Fi on a modern kernel) needs the vendor source to
  recompile and port (`docs/PORT-PLAN.md`), which is exactly what the GPL request is for.
- Consequence for planning (**corrected 2026-10-03**): the earlier text said the only self-built images
  possible are “(a) a custom **rootfs** on the vendor kernel - already done - or (b) modules built against
  a vanilla 5.10.201”. That **understates (a)**: it is not merely a rootfs, it is the **whole userland**,
  and it can be **newer than the vendor's** - a 24.10.5 `arm_cortex-a9` binary was measured running on the
  vendor 5.10.201 kernel (`docs/phase26/how-current-userland.md`). What is *not* replaceable without the
  vendor source is the **kernel** itself and the Wi-Fi modules that match it.

## 4. Bring-up and flashing path (the part that is already de-risked)

- **A/B slots are real and switchable.** `bootcmd=mtd read kernel${bootflag}`, `bootflag=a` in
  u-boot defaults; the live selector is the sysenv register
  `/sys/devices/platform/sysenv/boot_reg` (`0x10` -> slot A, `0x21` -> slot B) plus **both** env copies
  (mtd3/mtd4, block format `crc32-LE(4) | flags(1) | data(131067)`). Prebuilt recipe files exist at
  `build/custom/env-bootflag-{a,b}.bin` (`docs/FLASH-PLAN.md`; layout re-read this session from
  `dumps/uboot-env.txt`).
- **Every partition is dumped locally** (`dumps/mtd0..mtd16`, 38 MB) - the documented recovery path
  alongside UART (ttyS0, 115200 8N1, VCC not connected; bootmenu has TFTP update commands for
  rootfs.rw / rootfs.ro / kernel.images / uboot / esbc / bdinfo).
- **Slot hashes measured this session** (`sha256sum` of the gz dumps): kernela `mtd11` and kernelb
  `mtd12` are byte-identical (`fda36742...`); rootfsa `mtd13` `7874568e...` and rootfsb `mtd14`
  `49493b4b...` differ, so the two slots are not the same image and slot identity matters. mtd3-enva
  (289 B) vs mtd4-envb (802 B) differ in size and hash.
- **Flashing discipline** (non-negotiable, `docs/FLASH-PLAN.md` + `docs/HAZARDS.md`): full dumps before
  any write; **one slot always stock**; write only the *inactive* slot (`ubiformat /dev/mtdNN -y -f`);
  verify the written volume hash before switching; UART is the last resort. Kernel slot writes must
  write the **whole 8,650,752-byte slice** (uImage + FIT tail at `0x4185D0`) or the bootloader silently
  falls back to slot A; use `scp -O` (no sftp-server; `cat >` corrupted images twice).

## 5. What runs today (Path C, verified)

Vendor **2.5.24** base + our layer, built as **0.3** and running from slot B: marker
`omo-minimal-0.3 stock-2.5.24-20260727-122111`, `mtd_num=14`, 6 Wi-Fi interfaces, dropbear, opkg with
402 packages against signed 22.03.6 feeds, the systime injection closed by a plain-text wrapper that
re-loads `systime-stock.lua`, and a tested A/B switch + rollback (`docs/FLASH-PLAN.md`). The router was
left healthy by the last real device run (phase22 `sr-carrier`: `WIPHY=2 IFACE=6 OMOOFF=0`,
`2G=[SUCC] 5G=[SUCC]`, no experiment loader).

One hard-won warning: **do not install official `luci-base`/`luci-compat`/`luci-app-*` on this vendor
fork** - they shadow the vendor LuCI files and removing them leaves overlay whiteouts (502s); repair
with `sh tools/restore-vendor.sh` then `/etc/init.d/uhttpd restart` (`docs/FLASH-PLAN.md`).

## 6. The reversal thread - current state (updated 2026-10-03, phases 23-25)

The Wi-Fi chip can be **released and observed booting** (`0x5a5a` -> CA `0x40000108`; BSS zeroed, live
analog regs, first HCC mailbox word), and the SR/DR rings and the device->host iATU window are matched to a
live vendor boot. **Since this file was written the frontier moved substantially:**

- The phase-22 “split-root-complex” blocker described here was **not the cause**. The real root cause was
  that the message window base was one page low (`BAR0+0x3f0000` vs `0x3f1000`), masked by an interrupt
  register that happened to land correctly (`docs/phase23/ROOT-CAUSE-window-base.md`).
- With it corrected the firmware **speaks**: 9/9 CPU-start signature registers change (the chip leaves ROM
  state) and it emits id 6 then id 2 (`docs/phase23/firmware-speaks.md`).
- A host announce is only read if it is **pending at release**, because the firmware clears the message
  registers during its own boot - the first host->device write this project has ever had **taken**
  (`docs/phase25/in-post-announce-consumed.md`).
- The message **header** is fully characterised from a write-atomic bound capture, and the firmware's own
  messages were read off its live ring; **both** real vendor `0x04000100` frames, byte-exact, were posted -
  and the firmware reads them and continues regardless (`docs/phase25/replica-b-silent-payload-closed.md`).
- The **announce-to-release offset** was made an explicit variable and swept: inert
  (`docs/phase25/announce-offset-inert.md`).

So the current blocker is **not** a host-side byte or a timing. It is that the firmware's receive routine is
**built and armed but never dispatched** - the glue-ISR / `pcie_thread` route that a raw takeover never
enters (`docs/phase20/fw-accept.md` A.2, `docs/phase22/fw-sr-gate.md`, `docs/phase21/sr-trigger.md`).
Whether that dispatch needs the vendor's own service thread is a structural question, and the vendor source
(G004 / `docs/phase25/OPEN-SOURCE-REQUEST.md`) remains the other answer.


## 7. Ordered plan (revised 2026-10-03)

1. ~~[blocked on one credential] Restore device access~~ - **done**. The SSH lane works and has run
   phases 23-26; the credential remains a placeholder in tracked text as required.
2. ~~Run the queued phase-22 boot (H1-H4)~~ - **superseded**. Phases 23-25 answered the question that boot
   was aimed at, and eliminated a further fourteen host-side candidates
   (`docs/phase25/replica-b-silent-payload-closed.md`, `one-variable-negative.md`).
3. **Build the userland half - the concrete, unblocked deliverable.** The vendor kernel stays; the
   userland is replaceable and can be **newer than the vendor's**, measured (24.10.5 runs on 5.10.201,
   `docs/phase26/how-current-userland.md`). This is the path to “a custom, current OpenWrt firmware image”
   that does not depend on the vendor replying: assemble an OpenWrt userland for `arm_cortex-a9`/musl,
   flash it as a rootfs to the inactive slot, and run the 0.3 verification drill (marker, `ubiblock`
   hash, service check, rollback test). **Choose the release deliberately**: 22.03.6 matches the vendor
   exactly, 24.10 is demonstrated and current, 25.12 is a different package container (apk v3) whose
   tooling is extra work for no ABI gain.
4. **Path A trigger**: the GPL request (`docs/phase25/OPEN-SOURCE-REQUEST.md`) is written and ready to
   send. If it lands, build the vendor SDK, diff kernel/modules against our dumps, and produce the first
   **from-source kernel** image into slot B.
5. **Keep slot A stock forever**; keep `docs/FLASH-PLAN.md` updated with each build's hashes; refresh the
   calibration snapshot (`tools/wifi-cal-snapshot.sh`) before any experiment that touches the radio.
6. **Only after 3-4**: treat a clean-room mainline port as the funding decision PORT-PLAN calls it.

**Transfer discipline (added 2026-10-03).** `/usr/bin/scp` on this box is a **symlink to dropbear**, whose
scp emulation **acknowledges a file and exits 0 without writing it** - three “successful” transfers left
nothing, and the file was absent under a fresh `ls` in the same breath. The device has **no `base64`**
(and no busybox decoder, no python/perl). Working path: base64 chunks over the ssh command lane, then
`openssl base64 -d -A` on the device, with an **md5 check on both ends**. Never trust an unverified
transfer to this box.

## 8. Safety rules that gate every step above

Never write CA `0x400392f0`. Never read the RC misc window `0x10161000` (a read-only `devmem` there
panicked the box). Never `rmmod` the vendor modules (reboot instead). Measure only through the
endpoints' BAR0/BAR2. Never run the device cycle in the foreground. Never restore calibration without
verifying `MANIFEST.sha256`. Never commit real credentials - tracked text carries
`<ROUTER-SSH-PASSWORD>` / `<ROUTER-WEB-PASSWORD>` / `<DEVICE-SECRET>` only. Leave the router healthy:
2 wiphys, 6 interfaces, calibration `[SUCC]` on both bands, no `.omo-off` leftovers.
