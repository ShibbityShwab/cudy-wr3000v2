- **Phase 19 - THE RELEASE IS FOUND: the `0x5a5a` write to device CA `0x40000108` BOOTS THE CHIP (2026-10-01, lead-verified).**

- **Phase 22g - the custom layer is BAKED INTO the slot-B squashfs, not overlay-only (2026-10-02).** Device-side probe of /rom vs /overlay/upper for every injected file: `/etc/init.d/omosshd`, `/etc/rc.d/S95omosshd`, `/usr/lib/lua/luci/model/cbi/system/systime.lua`, `/usr/bin/opkg` and `/root/.ssh/authorized_keys` are all **rom=YES**; `systime-stock.lua` and `/etc/custom-firmware-version` are **rom=YES, overlay=no**. So the access + hardening layer ships inside the flashed image and survives a jffs2 overlay wipe or factory-style reset of the data partition, rather than living in the mutable upper layer. Together with slot A being provably stock (no marker, 2.4.15, no omosshd) this closes the deployment integrity question: the running system is the flashed artifact, and the rollback slot is untouched stock.

- **Phase 22f - STABILITY VERIFIED on the deployed slot-B image; port surface measured (2026-10-02).** Stability re-probe after the phase-22d experiment and recovery: uptime 6 min, load 1.13, **WIPHY=2 IFACE=6**, calibration \[SUCC\] on **both** bands, OMO_OFF=0, zero staged artifacts (no omo loader/watchdog/batch-list/module), **0 real kernel faults** (excluding the known benign pstore-registration lines), **pstore unchanged** (blk-0/1/2 mtimes still 10:41/14:37/14:37, all from before the test), memory 109 MB total / 23 free / 59 available, overlay 27%, 5 core services running. Deployed image remains byte-identical to build 0.3 (/dev/ubiblock0_0 sha256 55f5c5b4...) with slot A stock (no marker, DISTRIB_REVISION 2.4.15, no omosshd) as rollback. Port surface MEASURED (opensource/docs/PORT-SURFACE.md, commit 6dc4832): the shipped hi5622v100_wifi.ko is NOT a mac80211 driver (0 ieee80211_ symbols, 15 cfg80211/wiphy symbols, registers netdevs directly) and carries its own 4,330-symbol wal_/oal_/hcc_/bal_/hmac_/dmac_ MAC stack; it imports **211 symbols through the vendor-only import_ns=HW_RTOS_NS** (cfg80211/mac80211/plat import none), so any modern-kernel port fails at LINK TIME without the vendor's kernel patches - the decisive argument for Path A (vendor GPL sources) and a concrete Path-A check: extract the HW_RTOS_NS provider. Repo state: root repo committed clean at 2cb65f5 (AGENTS.md x3, CUSTOM-FIRMWARE-PLAN.md, tools/ep0win-detached.sh, ledger, .omo/ now ignored); submodule at 6dc4832.

- **Phase 22e - DEPLOYMENT DECISION + slot verification: the deployed image is byte-identical to the verified build, slot A is provably stock (2026-10-02).** Reversing closure: the phase-22d run showed the SR descriptor fetch already works, and `docs/phase22/h2d-accept.md` (20 hypotheses + the out[5] arm) shows the firmware's own H2D dispatcher is never entered and no host-writable register arms it - the remaining work is device-side (firmware trace or the vendor's message-context/ISR binding), not another register poke; the vendor ready handshake contains NO host->device write (docs/phase19/fw-handshake.md), so it cannot be closed by inventing a reply. Deployment truth (opensource/docs/DEPLOYMENT-DECISION.md): the board is `hsan luofu/R116` per its own device tree, DISTRIB_TARGET `hisilicon/luofu`; there is NO upstream OpenWrt target and none close (only WR3000 v1 / mediatek-filogic exists; forum posts describing the v2 as Triductor contradict this unit's DT), and the 5.10.201 module ABI forbids vendor binaries on a 6.12 kernel. Live slot verification: active slot B (bootflag=b, boot_reg 0x21, mtd_num=14), `/dev/ubiblock0_0` sha256 **55f5c5b4...** = byte-identical to the recorded build-0.3 artifact; layer present (omosshd S95, dropbear running, 514-byte authorized_keys, systime wrapper + systime-stock.lua 4467 bytes, opkg 433 packages, 5 signed feeds, check_signature on). Slot A (mtd13, attached read-only and detached again) carries **no** omo marker and reports 2.4.15 stock with no omosshd -> the rollback guarantee holds. Router healthy: WIPHY=2, IFACE=6, cal [SUCC] 2G+5G, OMO_OFF=0, no staged module/loader/watchdog/batch-list.

- **Phase 22d - THE H1-H4 BOOT RAN: H1 is killed as a sufficient cause, the fetch already works; the blocker is the host message-service contract (2026-10-02).** Tools: `tools/ep0win-detached.sh` (new; corrects sr-carrier's literal `stage` argument and its stale artifact path), CI build 37002219665, artifact `hccaccept-ko` (vermagic 5.10.201). One boot, 4 hypotheses, `stopfirst=0`: BATCH RESULT: PASS hypotheses=4, out0_cleared_yes=0. Both endpoints claimed (domain 0 = `0000:00:00.0` BAR0 0x40000000/BAR2 0x41800000; domain 1 = `0001:00:00.0` BAR0 0x58000000/BAR2 0x59800000), six inbound viewports on each (all readback match=YES), and EP0's outbound viewport 0 programmed to the vendor's live values (0x80000000/0x80000000/0xffffffff/0x80000000). Every entry read identically: `sr1c=0x00000400` (the FETCHED index - so the descriptor fetch is NOT the blocker), `out0_cleared=n`, `glue=0x00000000`, irq ~21 deliveries per entry. The chip is released and speaks (BSS zeroed, `out[1] CA 0x40039014 = 0x4`), our recovered host half runs against it (ACK out[3] `0x40101438`, CLEAR out[1], REARM out[4] `0x40101414`) but **those writes read back 0 - the endpoint does not latch them** - and the log names the concrete gap: `id=2 has no handler (unregistered)`, i.e. a dispatch-table entry the vendor's pcie_msg_init installs. irq accounting: 207 `irq_taken=0`; **209 `irq_taken=100085 irq_handled=7`** - the completion interrupt fires and is taken exactly as on a vendor boot, so "irq_taken=0 in takeover" is half-solved/half-ill-posed. Report: `opensource/docs/phase22/ep0win-run.md`. Router left healthy: WIPHY=2 IFACE=6, cal [SUCC] on BOTH bands, OMO_OFF=0, no staged module/loader/watchdog/batch-list, slot B still omo-minimal-0.3. CA 0x400392f0 never written; 0x10161000 never read.
  Writing `0x00005a5a` to device CA `0x40000108` (host BAR0+0x3b8108, decoded region 3) is the boot trigger: the lead
  read the capture - `kick readback: 0x00005A5A`, then 9/30 sampled registers change (firmware BSS zeroed
  `0x40080000/0x25/0x1110/0x8 -> 0`, the frozen `0xffffffff` analog regs go live, `tcxo_pll_mux_sel 0->1`,
  `tcxo_pll_status 1->2`), and within 3 s the chip writes its FIRST HCC mailbox word:
  `msg out[1] CA 0x40039014 = 0x4`. The value was the vendor's untaken-branch write for a different chip variant.
  Report: `docs/phase19/release-attempts.md`. RESET HUNT (same report): no host-side reset exists in either module
  (no config `0x3e` write, no FLR, `pcie_via_gpio_rst_device` is a stub, no `pci_reset_*`/`gpiod_*`/`pinctrl_*`
  imports); the only "reset" paths are host->firmware HCC events `0xf9`/`0x1e1`.
- **Phase 19b - the firmware runs and says hello once (2026-10-01).** `lab/fwhs` released the chip and logged 15 s:
  exactly ONE mailbox word (`out[1]=0x4`, bit 2, the inferred id-2 "DEVICE READY") at +1.85 s; the firmware zeroed
  98278/98304 words of its BSS; the handshake did not advance because a takeover boot has no IRQ/HCC service to
  read, ack or reply. The vendor handshake = two device->host HCC messages registered by
  `plat_init_bal_hcc_excp -> hcc_msg_register_tab_chip(chip=4, table=.data+0x2660, count=5)`: id 1 ->
  `device_plat_ready_msg_process`, id 2 -> `host_ready_msg_process` (copies <=0x62 payload bytes into
  `g_dmac_to_hmac_read_msg[core]`); the host's only acts are host-side `bal_irq_enable` + read-only
  `dev_status_check`, i.e. NO host mailbox write answers step 1. Report: `docs/phase19/fw-handshake.md`.
- **Phase 20 - the message service, measured to the field (2026-10-01).** `docs/phase20/message-service.md`: IRQ
  shared via `request_threaded_irq(pci_dev->irq, oal_pcie_intx_isr, ...)`, enable is host-side only (`enable_irq`);
  ISR -> `oal_pcie_transfer_done` (glue status `+0x2ec & 0x3d8`); `pcie_msg_handle`: pending when `*(ctx+4)!=0`,
  then clear it, `*(ctx+0xc)=1` ack, `*(ctx+0x10)=1` re-arm, dispatch the lowest set bit; the six mailbox CAs map to
  `out[0..5]` (`+0x2c..0x40`); **the payload is NOT in the mailbox** - it is DMA'd through the ETE DR ring into
  host memory then skbed to `hcc_msg_process`. In a takeover the endpoint has NO IRQ line
  (`PCI_INTERRUPT_LINE=0xff`) and `request_irq(207)` takes 0 interrupts; a vendor boot shows
  `207: GIC-0 91 hisi_pci_intx` and `209: GIC-0 95` (lead-verified in /proc/interrupts; 209 had served 7812).
- **Phase 20b - the runtime context + rings built, and the firmware REACTED (2026-10-01).**
  `docs/phase20/runtime-msg.md`: the runtime ctx is a static 0x78-byte per-controller object
  (`.LANCHOR0 + 0x78*ctrl`) with the six mailbox CAs at `+0x2c..0x40` and an 11-entry handler table at `+0x4c`;
  SR/DR channels 3+4, depth 32, 8-byte nodes; DR descriptor word0 = device address, word1 = `(len<<16)|0xd2b`.
  Correction: the ETE block is a DEVICE CA reached through the region-3 viewport, so its BAR0 offset is `0x3f2000`,
  not `0x3a000`. With our rings programmed the firmware sends TWO words: `out[1] 0->0x40` (bit 6 =
  `pcie_trigger_ete_sending_handle`) then `->0x04` - it accepted our rings and tried to send an ETE message. Still
  no payload, `irq_taken=0`.
- **Phase 20c - THE DEVICE->HOST WINDOW IS MATCHED TO THE VENDOR (2026-10-01).** `docs/phase20/host-window.md`:
  `pcie_hostca_to_devva` resolves through a 0x18-byte per-chiptype descriptor at `chip->[4]->[0xc4]` =
  `.data+0x1fb8` (`devva_base = hostca_base = 0x80000000`, `devva_end = 0xffffffff`), and
  `oal_pcie_set_inbound`'s outbound block @`0x9a38` programs endpoint iATU viewport 0 at BAR2+`0x000`; a live
  vendor boot reads `base/limit/target = 0x80000000/0xffffffff/0x80000000`, a takeover leaves it at reset.
  `lab/hostwin` programs it and now MATCHES the vendor word-for-word, yet no payload lands and `irq_taken=0` - the
  remaining blocker is the HOST half of the message service (the ack/re-arm CAs and the real id-6 handler), not the
  window. HAZARD (documented): a read-only `devmem` of the RC misc window (`0x10161000`) PANICKED the box once -
  measure through the endpoints' BAR0/BAR2 only. Commits `60aeeda`, `b353d96`. NEXT MILESTONE RUNNING:
  `docs/phase20/msg-host-half.md` (`lab/msghalf`) - the ack/re-arm CAs, the id-6 handler's action list, and the
  interrupt source arming.

## Phases 23-25 (2026-10-02/03) - the port runs end to end, and three corrections

The published reports are in `opensource/docs/phase23`, `phase24` and `phase25` (27 documents). The
short version, in the order the findings arrived:

- **Phase 23x - THE MESSAGE WINDOW BASE WAS ONE PAGE LOW.** The port read `BAR0+0x3f0000`; the message
  registers are at `0x3f1000`. Every "the firmware is silent" result before this was measuring the wrong
  page, and the bug survived because the wrong address returned *plausible* values (`0x40000004`) and both
  the driver and the vendor boot agreed on them - two readings of the same wrong address, which is not
  verification. `docs/phase23/ROOT-CAUSE-window-base.md`.
- **Phase 23y - THE FIRMWARE SPEAKS.** With the corrected window the port loads FIRMWARE.bin (`diffs=0`),
  releases the CPU (**9/9 CPU-start signature**, `dcoldo_vset 0xffffffff -> 0x260d4184`, BSS zeroed) and
  reads the first word `out[1] 0 -> 0x04`. `docs/phase23/firmware-speaks.md`.
- **Phase 24c - THE HOST HALF EXECUTES.** dispatch, ack (`out[3]`, self-clearing), clear (`out[1]`, takes
  and holds), re-arm (`out[4]`, self-clearing) - all readback-verified on the real registers.
- **Phase 24i - THE SR DESCRIPTOR POST IS THE TRIGGER FOR THE id-6 WORD**, proven by A/B against the
  recorded `fwaccept` artifact (id 6 -> id 2 with a post; id 2 alone without).
- **Phase 24q - THE DEVICE'S PLAT READY IS id 2, NOT id 1.** An earlier claim that no such word arrives was
  wrong in its id and wrong in conclusion; `id 2` is the persistent `0x04` bit every run receives.
- **Phase 24y - `plat.ko` IS A TX SHIM; the device-facing transfer is a `wifi.ko` function** reached as
  object `+0x18` from `bal_port_start_xfer`, so the port's H2D path reimplements a routine this project
  has never read (and `wifi.ko` hardcodes none of the mailbox CAs - they arrive as pointers).
- **Phase 25b/c - A HOST ANNOUNCE IS ONLY READ IF IT IS PENDING AT RELEASE.** The firmware clears the
  message registers during its own boot: an announce written before the release is **consumed**, and every
  post-release send in phases 24d-24t was posted too late to be seen. This is the first host->device write
  the device has ever taken here. The dialogue is unchanged, so consuming the announce is necessary but not
  sufficient. `docs/phase25/in-post-announce-consumed.md`.
- **Phase 25d/e - the framing is settled; the CONTENT is what remains.** The node layout is verified against
  the vendor's own `get_dscr_len`/`get_dscr_flag` decoders, the announced length is confirmed irrelevant
  under corrected timing, and the chip interface is mapped by name as `g_st_pcie_bus_driver`. What is left
  is the bytes the firmware expects the message to carry.

**Nine host-side candidates were tested and eliminated along the way** (the window, the host half, poll
resolution, the DR producer commit, `out[5]`, the re-arm value, the descriptor length twice, and the
zero-credit hypothesis). The notebook's value is as much in that record of eliminations as in what works.

**Hard-won process rules** (all three earned by real failures): derive a register address from the
documented CA plus the translation rule and confirm the register *behaves* as documented; **absence of
change is not evidence of absence**; and run `opensource/lab/wifidrv1/tools/prebuild-check.js` before every
build - a hand-maintained identifier list missed two declaration-order bugs that CI then caught.


## 2026-10-03 - phases 27-28: H1 confirmed, the DR ring is free-running, the firmware half settled

**H1 confirmed - the mailbox announce is irrelevant.** With `sr_announce=0` (verified from the live
process's own command line, zero ANNOUNCE lines in dmesg) the firmware still runs the **full** id-6 then
id-2 dialogue and 9/9 CPU-start. **The SR ring alone is sufficient.** This retires the whole phase-25
announce line of work: those measurements are true, but they were characterising a signal the firmware
does not need. Indicator: `out[0]` never set at all, yet `out[1]` bit 6 at t=25 ms.
`opensource/docs/phase27/h1-ring-alone-elicits-dialogue.md`.

**The vendor's live ring shape** (read-only, normal operation): the vendor uses **ch0 only** - every other
SR/DR channel is at reset (ch2 holding garbage). DR depth matches SR, so the port's ring geometry is the
vendor's. `opensource/docs/phase27/vendor-live-ring-shape.md`.

**The DR ring is free-running, not event-driven.** Index-change counts over equal 20 s windows:
quiet 50, scanning 53, quiet 46. **Ring motion is uncoupled from reception**, so the "no DR deposit"
observation that earlier phases read as evidence of a device-side gate is **neither evidence of a gate nor
of its absence**. `opensource/docs/phase27/dr-ring-free-running.md`.

**Three instruments lied first** - this is the phase's real lesson. A device ping to the host went over
Ethernet (the bridge routed wired, so the radio saw nothing); `rx_packets` never increments for received
frames on this chip, so it can certify neither validity nor invalidity; and derived "slots advanced"
arithmetic wrapped and produced invented activity (1023/18/2042). Only the count of index value changes
could not be miscomputed. **Recorded as invalid experiments, not as negatives.**
`opensource/docs/phase27/traffic-experiment-invalid.md`.

**The firmware half is settled by measurement.** The curated in-place upgrade is a no-op (433 packages
installed, **0 upgradable** within 22.03.6 - the base is already current). So every firmware path is
measured-closed (A), declined (B, 2026-10-03), or waiting on the vendor (C).
`opensource/docs/phase28/firmware-half-settled.md`.


## 2026-10-04 - phases 42-48: the gate located to the mechanism level, the host-side space closed

42-43: the window theory retracted (rings are host DRAM, the port already posts the right nodes);
the channel map verified (20-word 2g/5g MAC array, ETE rings at CA 0x4003a000, DR ch0-3).
44: H1/H2 eliminated - the DR channels match the vendor's live state word-for-word.
45-46: the sibling GPLv2 map (phase 45) revealed the luofu message block IS the PCIE_CTRL_RB
family - and the RAW interrupt status (0x2e4) became the new observable.  Phase 46's measurement:
the doorbell sets the raw AND masked status - THE H2D INTERRUPT FIRES.
47: source 0x4C is registered AND enabled (file 0x9800/0x9816) - the last link is the
device-internal ctrl-rb -> GIC wire, not a missing enable.
48: both masks written readback-verified; the ack still never flips.  The host-side space is
closed at the mechanism level; the remaining instruments (JTAG, vendor source) are confirmed
unavailable.

**Strike, 2026-10-04 - the phase-48 ack headline is vacuous and is superseded.**  CA `0x400392f0`
is the ctrl-rb `HOST_INTR_CLR` register, write-to-clear: the sibling map makes it the bit-0 clear of
the 12-source host-intr group, and the H2D dispatcher writes 1 to clear it (`THE-GATE-MAP.md`
section 1: `0x818b2 movs r7,#1` / `0x818b8 str r7,[r2]`, phase 32).  A W1C register reads 0 before
AND after any dispatcher run, so "the ack never flips" decides nothing and every readback-based
"byte-identical" claim resting on it proves decode/storage only, never device effect.  Correction
blocks added at the top of `opensource/docs/phase48/host-side-closed.md` and in
`opensource/docs/phase47/THE-LAST-LINK.md` section 3; no original text deleted and the
never-write-`0x400392f0` rule is unchanged.  The valid observable set is the raw status CA
`0x400392e4` and masked status CA `0x400392ec` (phase 46 measured), with the device-side signatures
(pending id CA `0x4016010c`) as the real delivery witness.


## 2026-10-04 - phase 49: the forward lane - register(0x4c) ran, enable(0x4c) executed, the delivery hop is the last link

The wifi-forward plan's five device lanes (tasks 9-13), each closing with a healthy router. Reports:
`opensource/docs/phase49/` (read-boot, probe-boot, scratch-boot, vendor-loader, viewport, README).

**Read boot (task 9, `build/register-dumps/exp/20261004-163526/`).** CA `0x4017D560` = **`0x00040295`**
(the `fn_array[0x4c]` fn-pool pointer), control `0x4017D4E4` = `0x000462F9`, window sanity `0x406B8000` =
`0xE59FF018`; all SEVEN live reads match the frozen normal-op barmap word for word -> **firmware
`register(0x4c)` ran in the takeover boot.** The `[intrsamp]` block reproduced phase 46 exactly: doorbell
`0x400392d4` bit 0 -> raw `0x2e4` `0x0 -> 0x1`, masked `0x2ec` `0x10 -> 0x11`; bit 3 ring -> raw `0x1 ->
0x9`, masked `0x11 -> 0x19`; ack unmoved (W1C, decides nothing). `[sig] 9/9`, readback `diffs=0`.

**Probe boot (task 10, `build/register-dumps/exp/20261004-164113/`).** One-byte probe at file `0xe2c97`
(OUTSIDE the `0xCC0CC` loaded image) accepted: dmesg names `/lib/firmware/hi_wifi/FIRMWARE.bin.omo-pat`,
readback `diffs=0`, `[sig] 9/9`, no panic, no new pstore, `.omo-pat` removed and stock md5 verified. The
load path carries a modified blob without bricking the takeover boot (GATE G3 auto-continue).

**Scratch boot (task 11, `build/register-dumps/exp/20261004-165139/`).** BOTH scratch stores executed, at
BOTH BAR0 aliases: `S1=0x00001000` (bit-12 bitmap word -> id `0x4c`), `S1+4=0x40161108` (the destination),
`S2=0x00000001`, `S2+4=0x50AA7E49` (the scratch marker, asserted BY EQUALITY because task 9 fixed `S2+4` as
static frozen-image content, baseline `0x00104427`). The plan table's **BRANCH-1**: `enable(0x4c)`
EXECUTED. The enable half is settled; the remaining failure is the device-internal delivery hop. Round 1
(no dir) was a harness/loader stall, not a branch; the round-2 poller pinned the sequence live
(`build/register-dumps/exp/20261004-165044-diag/`).

**Vendor-loader (task 12, `build/register-dumps/exp/20261004-165759-vendorloader/`).** Verdict
**rejected** (Wi-Fi never came up; chip `EXCP_PANIC`/`EXCP_DABT` 81.5 s after a 34.4 s device_ready
timeout, code 35629), BUT the plan's validation assumption is FALSIFIED: the loader logged `version check
skip` and loaded OUR bytes verbatim (patch sites `0x406FEED4`/`0x4077F024` = scratch) and the patched code
executed (the S1/S2 cells fired). The fence is firmware runtime, not loader validation - the lane is dead
as-is for this patch. Residual ambiguity declared (stores vs trampoline liveness). Full recovery, stock
restored and verified before reboot.

**Viewport (task 13, `build/register-dumps/exp/20261004-171523/`; CI run 37218448504).** Spare viewports
6/7 programmed (14/14 readbacks), P3 six named viewports unchanged=YES; one doorbell; B control decoded
(raw `0x2e4` `0x0 -> 0x1` bit 0). **A reads ALL `0xffffffff`**: CA `0x40160000` (the GIC block) is NOT
host-reachable through an inbound spare viewport -> expected-negative, **GATE G5 default branch**. The
parameters are the measurement.

**Gates:** G1 blessed the frozen knob-set as-is; G2 proceeded (L1 `0x00040295` nonzero, user confirmed); G3
auto-continued on `9/9`; G4 authorized task 12 on preconditions; G5 took the default branch.
`.omo/ulw-execute/ledger.jsonl:30,54,60,66,67,73`.

**Branch recommendation for THE-LAST-LINK section 3.** `0x40161108` bit 12 = 0 is ELIMINATED (task 11:
`enable(0x4c)` executed) and `register(0x4c)` ran (task 9), so the distributor side is armed. The GIC is
host-invisible (task 13), so the deciding read CA `0x4016010c` is **device-side only** - a trace across one
doorbell ring reading distributor bit 12 and IAR. The vendor-loader lane is not that instrument (dead
as-is). The cheap leading indicator stays the masked-status latch at CA `0x400392ec` bit 0.

**Plan-text defects recorded by the executors (from the ledger):** the S1/S2 range `[0xE7000,0xFFF00]`
was unsatisfiable (extended to `0x1BFFFF`); the probe rule was vacuous by construction (byte outside the
loaded image); the host-window overlap with region 4 (spec's P3 mitigation); the `EXP_DONE_CMD` default
mismatch (`omo-drv1: init done`); `module-log.txt` vs `dmesg.txt` wording; `rox_pci0` is a bound PCIe
driver, not an lsmod entry; the harness reboot-freshness gate (`uptime < 180` could accept a stale boot);
and the capture-hook remote/local path bug (fixed and reverified).


**Follow-up (2026-10-04) - gic-view** (`opensource/docs/phase49/gic-view.md`,
`build/register-dumps/exp/20261004-174357/`): the post-plan lane that flips the sensor on task 13. Patched
firmware (`tools/patch_fw_scratch.py` variant `gicview`; blob `b6b7faa9b2682d959cce6d0fb2bae315`, one
cycle PASS) reads the GIC itself into host-readable cells. **BRANCH-G**: the device CAN read the GIC, and at
both sampled init instants nothing was pending or active for the CPU. Values (BAR0 == ACP alias for all ten
cells): C0 = `0x00000001` (ISENABLER word 2 at CA `0x40161108`, a PRE-write read - a real host-invisible
register the device sees, host reads `0xffffffff` there); C1 = C3 = `0x00000000` (ISPENDR2 CA
`0x40161208` at the enable point and the bring-up end); C4 = `0x00000000` (ISACTIVER2 CA `0x40161308`); C2
= C5 = `0x000003FF` (GICC HPPIR CA `0x40160118`, nothing pending for the CPU); S1/S1+4/S2/S2+4 re-verify
BRANCH-1; window `0x406B8000` = `0xE59FF018`; `[sig]` 9/9. **MAP CORRECTION, load-bearing:** the brief's
ISPENDR2/ISACTIVER2 `0x40160208`/`0x40160308` sit in the GICC page's read-as-zero area and would have
faked "nothing pending"; the vendor-layout siblings are `0x40161208`/`0x40161308`, with GICD base
`0x40161000` anchored by the firmware's own CTLR literal (file `0x716c` -> written at `0x6ed4`), ISENABLER
`0x40161100` (literal file `0x87044`), ICENABLER `0x40161180`, ICPENDR `0x40161280`. Bounds declared: C0 is
pre-write; NO doorbell was rung, so a clear pending word does NOT falsify a late/latch-triggered assert
(rows NOT TESTED); a zero cell cannot tell "clear" from "RAZ" by value alone (anchors: the firmware's own
write targets plus the C0/C2 positive controls); ISACTIVER2's address rests on the relative layout.
Independent verifier CONFIRMED (high), map-correction grade RIGHT and bounds HONEST; acceptance 54/54
ALL_OK; frozen probe/scratch md5s unchanged (`2a9a9f1d...`/`b08699bd...`); original ISENABLER write at file
`0x8702c` byte-identical; device clean after (stock md5, no `.omo-pat`, no new pstore/chip dumps). **Next
branch:** a post-SEND sampling iteration - sample ISPENDR2/HPPIR at the moment the FIRMWARE itself posts to
the host (its `out[1]` writes), which is exactly when the missing ctrl-rb -> GIC wire would have to assert;
dispatched 2026-10-04.

