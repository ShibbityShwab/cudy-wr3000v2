# Custom-firmware plan: what "latest OpenWrt on the WR3000 v2.0" actually takes

Written 2026-10-02 against the moved repo (`Documents/GitHub/cudy-wr3000v2`, `master` @ `9c8514b`,
submodule `opensource` @ `omo/phase22-hccaccept` `5ee29b7`). Every claim below is marked with where it
came from. This file is the entry point; the deep detail stays in the submodule docs it cites.

## 1. Deliverable restated

A flashable custom firmware image for the Cudy WR3000 v2.0, as current as the hardware allows, plus the
evidence trail for each step. Three questions must be answered before any flashing: what upstream
support exists, what the kernel/module ABI allows, and what the bring-up + flashing path is.

## 2. What upstream support exists - answer: none, and that is not a temporary gap

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
- Consequence for planning: the only *self-built* images possible today are (a) a custom **rootfs** on
  the vendor kernel - already done, see §5 - or (b) modules built against a vanilla 5.10.201 prepared
  for `multi_v7_defconfig` with the P2V vermagic patch (the CI recipe), which is how every `lab/`
  module that has ever touched this hardware was produced.

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

## 6. The reversal thread (why it is worth continuing)

The Wi-Fi chip can be **released and observed booting** (`0x5a5a` -> CA `0x40000108`; BSS zeroed, live
analog regs, first HCC mailbox word), the SR/DR rings and the device->host iATU window are matched to a
live vendor boot, and the host half of the message service is recovered (`acks`/`re-arm` CAs and the
id-6 handler's action list, `docs/phase20/msg-host-half.md`). The current blocker is split-root-complex:
the descriptor fetch traverses **EP0**'s RC while the completion INTx arrives on **EP1**'s
(`docs/phase22/rc-routing.md`, [measured across two boots]). `docs/phase22/NEXT-EXPERIMENT.md` is
**queued and never run**: one boot, H1 (program EP0 outbound viewport 0) -> H2 (ETE per-channel enable
`0x40039508`) -> H3 (producer-commit variants on `SR+0x18`) -> H4 (H2D arm via `0x400392e8`/`0x400392ec`),
stopping at the first act that moves the chip, module extended from `lab/bothep`.

That thread is what makes Path A or B possible at all: it is the map of the message service a driver
(or a firmware re-implementation) would have to speak.

## 7. Ordered plan

1. **[blocked on one credential]** Restore device access: the SSH lane needs a working password (or an
   installed key) in `.omo-secrets/`; today `.sshwrap/askpass.sh` is still the placeholder and only the
   web password + device secret are stored. Nothing mutating runs until this is fixed.
2. **Run the queued phase-22 boot** (H1-H4) detached via `tools/run-exp-detached.sh`, watchdog armed
   before staging, per `docs/phase22/NEXT-EXPERIMENT.md`. Success = any of the four hypotheses moving
   the chip's state (`SR+0x1c`, `out[0]`, completion index).
3. **Path A trigger**: follow up the GPL request sent to Cudy 2026-10-01 (kernel + u-boot + build
   config; the Wi-Fi module's own `license=GPL` metadata is the lever for the driver source). If it
   lands, build the vendor SDK, diff kernel/modules against our dumps, and produce the first
   **from-source** image into slot B with the 0.3 verification drill.
4. **Keep slot A stock forever**; keep `docs/FLASH-PLAN.md` updated with each build's hashes; refresh
   the calibration snapshot (`tools/wifi-cal-snapshot.sh`) before any experiment that touches the radio.
5. **Only after 1-3**: evaluate a modern userland on the vendor kernel (its own project), and treat a
   clean-room mainline port as the funding decision PORT-PLAN calls it.

## 8. Safety rules that gate every step above

Never write CA `0x400392f0`. Never read the RC misc window `0x10161000` (a read-only `devmem` there
panicked the box). Never `rmmod` the vendor modules (reboot instead). Measure only through the
endpoints' BAR0/BAR2. Never run the device cycle in the foreground. Never restore calibration without
verifying `MANIFEST.sha256`. Never commit real credentials - tracked text carries
`<ROUTER-SSH-PASSWORD>` / `<ROUTER-WEB-PASSWORD>` / `<DEVICE-SECRET>` only. Leave the router healthy:
2 wiphys, 6 interfaces, calibration `[SUCC]` on both bands, no `.omo-off` leftovers.
