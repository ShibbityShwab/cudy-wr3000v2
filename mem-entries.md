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

**Follow-up - gicsend** (`build/register-dumps/exp/20261004-180736/`, round 2; round 1
`.../20261004-180114/` kept with `aliasing-note.txt`): the post-SEND iteration gic-view dispatched (variant
`gicsend`, blob md5 `326619bed125e65930a0a62bc6abdd47`, one cycle PASS). A third trampoline at the firmware's
own `out[1]` post (file `0x86f5a`) samples ISPENDR2/HPPIR/ISACTIVER2 right after the store. **BRANCH-S**: at
that post the GIC mechanism is alive (word 2 bit 5, id `0x45`, is pending) while source `0x4c`'s line does
not show pending - D0 = D4 = `0x00000020` (bit 12 clear, bit 5 set, ALIAS view, both pages agree), D1
(HPPIR) = `0x3FF`, D2 (ISACTIVER2) = `0x0`, S/D markers = `0x50AA7E49`; `[sig]` 9/9, `out[1]` `0x0 -> 0x4`
at t=500ms. The send-site cells sit above an upper-address **aliasing boundary** (BAR0-direct reads `0x0`,
the ACP alias `BAR0+0x6b8000` carries the stores; pinned between `0x103ffc` agreeing and `0x104004`
diverging; mechanism UNEXPLAINED and accepted as a device fact), so D values are quoted from the ALIAS
ONLY and the `0x50AA7E49` sentinels prove the stores ran. Claim phrased precisely: "not pending at the post
instant", not "never". Bounds: one-shot timing; ISPENDR2/ISACTIVER2 rest on the GIC-400 relative layout;
the alias mechanism is unexplained; the host-ring/id-6 hop is untested; id `0x45` recorded, not explained.
Verifier CONFIRMED (high), acceptance 49/49, pads independently disassembled, frozen probe/scratch/gicview
md5s unchanged, device clean. **Next:** the `0x4c` line's routing/mask inside the chip - a vendor boot with
the same instrumented blob, or the two dynamic enable sites / an id `0x45` probe.

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

**Follow-up - gicpost** (`build/register-dumps/exp/20261004-190222/`, variant `gicpost`,
blob md5 `a4e69d74c172d856dd0e336a64482fbd`, one cycle PASS, 147 s): the conditional-enable test. The enable
write is the CONDITIONAL `strlo.w r4,[r3,r2,lsl #2]` at file `0x8702c` (executes iff C = 0 and Z = 0), and
every prior sample of it was PRE-write, so a failed condition would have been a root-cause candidate
upstream of everything. The gate pad now deposits the APSR it captures -> E3, and a post-store trampoline at
file `0x87036` (pad file `0xc8558`, the firmware's own `bl #0xbdf50` swapped for a pad that holds no `bl` and
ends `b.w #0xbdf50` with `lr` untouched -> resumes at `0x8703a`) matches/clears the `0xe2e2e2e2` request,
re-arms the sentinel `0x50AA7E49` -> E2, and reads CA `0x40161108` -> E0 (POST-write ISENABLER2 word 2) and
CA `0x40161208` -> E1. **BRANCH-P: the conditional store EXECUTED and TOOK; the silent-condition root cause
is EXONERATED.** E0 = `0x00001001` bit 12 SET (bit 0 = the prior id-`0x40` enable) at BOTH views, a LATCHED
register readback rather than a timing sample; E3 = `0x80000093` (N=1 Z=0 C=0 V=0 -> LO HELD); E1 = `0x0`
(the `0x4c` line not pending at that instant); E2 = `0x50AA7E49` (both-pad handshake fired). Sanities:
S1/S1+4/S2/S2+4 re-verify BRANCH-1; C0 = `0x1` is the same register PRE-write with bit 12 clear (the 0 -> 1
happened in this pass); C2/C5 = `0x3FF`; D3/D5 markers present; `[sig]` 9/9. The E cells sit in the
sub-boundary band (`0x103fb8`..`0x103ff8`) where both views agree. The chain now reads registered (L1) ->
enabled-and-taken (E0) -> not pending at the enable instant (E1) nor at the firmware's own post (BRANCH-S
D0 = D4 = `0x00000020`, word 2 carrying id `0x45`, HPPIR = `0x3FF`) => the break is DOWNSTREAM of the enable
register: the delivery/mask path for the `0x4c` line. Bounds: E1 is an instant, not a window ("not pending at
that instant", never "never"); the gate cannot see an enable that never reached the bitmap path; the gate
bitmap `0x1000` admits id `0x4c` (word 2) and `0x2c` (word 1), and a landed word-2 bit 12 is an id-`0x4c`
pass; the map rests on the GIC-400 relative layout (IAR `0x4016010c` never read, `0x400392f0` untouched,
`0x10161000` never read); the above-`0x104000` BAR0/alias disagreement is unexplained (this run stays
sub-boundary); no doorbell rung (host-ring / id-6 hop untested); no pre-cycle calibration snapshot (the lane
writes no calibration data); and the run proves the WRITE landed, not the downstream cause. Verifier
CONFIRMED (high): values independently parsed, acceptance 47/47, all five variant md5s regenerated identical
and `gicpost` deterministic, capstone confirmed the site swap (stock `36f08bff` -> patched `41f08ff8` `bl
#0xc8558`, pad tail `b.w #0xbdf50`, no `bl` inside the pad, `lr` preserved), the handshake logic proven
(E2 = sentinel requires both pads), live device clean (stock md5, 3 pstore records, 6 ifaces, `[SUCC]`); one
nit noted: the acceptance script would label P1 even if LO were false, not triggered by the observed pair.
**Next:** probe the distributor delivery/target/priority words and the CPU-interface mask for the `0x4c` line
(takeover instrumented, safe), or a vendor-stack boot with the same instrument (needs lead authorization,
carries the task-12 abort risk).

**Follow-up - gicmask** (`opensource/docs/phase49/gic-view.md` ADDENDUM 3, `build/register-dumps/exp/20261004-194824/`,
variant `gicmask`, +608/-13, blob md5 `2d354bd297270d6a64056bf2fc663dc2`, one cycle PASS, 150 s, acceptance
67/67 `ALL_OK`, gm_check 55/55): the DELIVERY-CONFIGURATION test. Instead of another pending-word sample, the
send-site pad additionally reads and stores ten words F0..F9, and the run reads the three candidate delivery
roots device-side at the firmware's own post. **BRANCH-M (label BRANCH-M4): all three candidate roots are
EXCLUDED; the delivery configuration is fully ARMED, and the missing piece is the EVENT ASSERTION (ctrl-rb ->
GIC).** Values (F cells above the `0x104000` boundary, quoted from the ACP alias; F8/F9 = `0x50AA7E49` prove
the pads ran; sentinels): F0 `0x40160100` GICC_CTLR = `0x1` (EnableGrp0 SET, CPU interface enabled); F1
`0x40160104` GICC_PMR = `0xF0` (passes `0x4c`'s priority `0x50`); F2 `0x4016184C` ITARGETSR = `0x01010101`
(byte 0 = `0x01`, CPU 0); F3 `0x4016144C` IPRIORITYR = `0xF050F050` (id `0x4c` -> `0x50`); F4 `0x40161C10`
ICFGR = `0x55555555` (all `0b01` = EDGE); F5 `0x400392E8` glue HOST_INTR_MASK = `0x20` (bit 0 = 0, H2D line
UNMASKED); F6 `0x400392E4` raw status = `0x0`; F7 `0x400392EC` post-mask = `0x0`. F6/F7 clear is the EXPECTED
reading of a boot with no ring rung, so it cannot separate "never asserts" from "asserts but is dropped". TWO
BRIEF CORRECTIONS (disasm-verified): (a) "mask `0x3d8`" is a MASK CONSTANT (`ldr r4,[r3,#0x2ec]` at
`hi5622v100_plat.ko` file `0x833c`, `ands r4,r4,#0x3d8` at `0x8344`), NOT an address; the real mask register is
CA `0x400392E8` (+0x2E8, 1 = masked); (b) the F addresses rest on firmware literals (`0x8309c` =
`0x40160100`, `0x83010` = `0x4016010c`, `0x83020` = `0x40160110`, `0x7174` = `0x40161800`, `0x7170` =
`0x40161400`, `0x715c` = `0x40161c00`, `0x86fb4` = `0x40039000`), with the verifier's nit that `0x83098` =
`0x40160104` is also a literal, so F1 is literal-anchored, not layout-derived (the instrument's prose
contradicted its own table; conservative, no value changed). OWN FINDINGS: the BAR0 view LAGS the alias (F9
BAR0 = `0xE2E2E2E2`, the gate pad's earlier request, vs alias = the send pad's sentinel) - the boundary
phenomenon has content, a lag not a decode difference; F1 = `0xF0` while the image's only PMR writer stores
`0xff` (file `0x8304e`/`0x83054`; unexplained, immaterial, both pass `0x50`); no `0xffffffff` anywhere.
Verifier CONFIRMED (high): values reproduced (44 view-reads), acceptance 67/67 + gm_check 55/55, six variants
regenerate (five frozen pins unchanged, `gicmask` deterministic), the mask constant and literals confirmed by
capstone, live device clean. TWO inherited conventions flagged as RESIDUAL RISKS: (i) the F5 mask POLARITY
(1 = masked) is inherited from a sibling header + the vendor live value, not re-derived (an inversion would
resurrect the "the glue masks it" root); (ii) GICC_CTLR bit 0 is read as "enabled" without checking the
interrupt's GROUP (no IGROUPR check; a Group-1 SPI with only EnableGrp0 would keep a variant alive). Also:
the acceptance ladder prints F1..F4 without pinning them (only F0/F5/F6 gate the branch), a noted weakness, the
values independently pinned; and "no ring -> expected clear" is correct and conceals nothing. **Next (one
line):** a ring-instrumented run (doorbell + event-assertion sampling) AND the two convention checks (F5
polarity via a known-masked line; IGROUPR for id `0x4c` + EnableGrp1), all takeover-safe.

**Follow-up - gicking** (`opensource/docs/phase49/gic-view.md` ADDENDUM 4, `build/register-dumps/exp/20261005-053936/`,
variant `gicking`, +670/-20, blob md5 `0f2e431f8e32c040b8ad7e7001f8ab57`, one cycle PASS, 150 s): the
ASSERTION TRIO, the ring-instrumented run that addendum-3's next line named, answering all three open
questions in one boot and paying the polarity fixture forward. The send pad rings the H2D doorbell CA
`0x400392d4` <= `0x1` exactly once, holds the glue mask MASKED (CA `0x400392e8` <= `0x21`), samples, then
restores it OPEN (`0x20`) and reads again. **BRANCH-GICK.** RING: the ring LEAVES THE HOST and latches the
glue raw status (F6 `0x400392e4` bit 0 = `0x1`, against gicmask's `0x0` on the same pad with no ring; the
firmware dispatcher writes `0x8` = bit 3, and F6 has bit 3 clear, so the new raw bit 0 is the ring's), but
the ring -> GIC step is UNDECIDED: the post-ring ISPENDR2 word-2 samples (D0 = D4 = `0x00000020`, id `0x4c`
bit 12 clear) were taken with the mask DELIBERATELY held MASKED (F5 = `0x21`, F7 = `0x0`), so a line the
mask gates is expected to leave ISPENDR clear; the mask reopens only after the D samples and there is no
post-unmask ISPENDR2 read, so neither "the ring reaches the GIC" nor "it does not" is supported. GROUP: the
group gate DIES - G2 GICD_IGROUPR word 2 (`0x40161088`, layout-derived) bit 12 = `0`, id `0x4c` is Group 0,
and F0 GICC_CTLR = `0x1` (EnableGrp0 SET, EnableGrp1 = 0) is exactly what Group 0 needs; E0 = `0x1001`
re-proves the enable landed; the residual root is the EVENT ASSERTION side (addr.md row B), closing
addendum-3's residual risk (ii). POLARITY: "1 = masked" is CONFIRMED in-run (closing residual risk i) by the
F6/F7/G0 triple in the same boot - F6 bit 0 = 1 (raw, masked instant), F7 bit 0 = 0 (post-mask, same
instant), G0 bit 0 = 1 (status once open) - which EXCLUDES the inverted model (F7 = 1 while masked) and the
independent-raw-latch model; the raw bit was already 1 at F6, read before F7, so F7 = 0 is not a latency
artifact, and F5 = `0x21` read at the same instant proves the mask was really set. `[sig]` 9/9, done marker,
out[1] witness present; no `0xffffffff`; window sanity `0xE59FF018`; sentinels F8 = F9 = D3 = D5 = G3 =
S2+4 = `0x50AA7E49`. Bounds: one-shot instants; the D/F/G cells are alias-only (above `0x104000`); no
post-unmask GIC sample (the top bound); the G2 address is layout-derived (the read is the check); the run's
own `interp.txt`/`acceptance.txt`/`cleanup.txt`/`pstore-check.txt` were never produced
(`pack-gicking-evidence.sh` did not run). Two verifiers CONFIRMED (neither ran the cycle): the runtime one
(`build/register-dumps/diffs/20261005-053936-vrun/verdict.txt`, independent acceptance 108/108 `ALL_OK`,
polarity re-derived, G2 = row B) declared R1/R2/R3 - R2 is the ring -> GIC confound (masked ISPENDR), and
R3 is the staged `.omo-pat` LEFT BY THE RUN because its pack-cleanup never ran, which the verifier then
removed under the HARD RULE (post-remove: 3 stock firmware entries, stock md5
`0e530b976d5a20e87358671f1a577695`, `pat_after` = 0); the instrument one
(`build/register-dumps/diffs/20261005T054100Z-vtool/verdict.txt`) regenerated the blob 6x identical to the
staged blob, capstone-audited the pads (ring CA `0x400392d4` <= `0x1` exactly once, mask `0x21` -> `0x20`,
every CA->cell pair, `changed bytes OUTSIDE 4 sites + 4 pads: 0`, originals preserved, no forbidden CA).
Health after the cycle and the mandated cleanup: `WIFI=1 PLAT=1 WIPHY=2 IFACE=6 CAL_SUCC=1 OMO_OFF=0
STAGED=0 LOADER=0 RECOVER=0`, 2 wiphys, 6 interfaces, cal `[SUCC]` on both bands, 3 pstore records (no new
crash), no leftovers. **Next (one line):** one follow-up cycle with an ISPENDR2 word-2 read for source
`0x4c` AFTER the mask is restored open (or a compile-time open mask), paired with HPPIR and ISACTIVER2 at
the same post - the sample this boot is missing - takeover-safe, serial/detached via `tools/exp.sh`.

**Follow-up - gicunmask** (`opensource/docs/phase49/gic-view.md` ADDENDUM 5, `build/register-dumps/exp/20261005-072450/`, variant `gicunmask`, +639/-4, blob md5 `a68d5fed68b3015ab97c63ca7a394c28`, one cycle PASS, acceptance 60/0, `gu_verify` 36/36): the POST-UNMASK ring test, the R2 follow-up that fixes gicking's confound by opening the glue mask BEFORE the ring. The send pad re-sequences to: entry read H5 (ISPENDR2 word 2), drive the glue mask OPEN (CA `0x400392E8` <= `0x20`; `0x21` NEVER written this run), ring the H2D doorbell ONCE (CA `0x400392D4` <= `0x1`), then sample H0..H4 with sentinels H6/H7 (`0x50AA7E49`). **BRANCH A: THE RINGED EVENT REACHES THE GIC - the wire is ALIVE.** H0 = `0x00001020` (ISPENDR2 word 2: BIT 12 SET = id `0x4c` pending, plus bit 5); H1 = `0x0000004C` (HPPIR returns id `0x4c`, the CPU interface reports it as THE pending interrupt); H2 = `0x00000000` (not yet active, IAR never read); H3 = `0x00000001` (glue raw latch); H4 = `0x00000001` (status passes the OPEN mask); H5 = `0x00000020` (bit 12 CLEAR at the next send-site visit). Two ends agree (distributor pending bit 12 AND HPPIR = `0x4c`) and the glue latched and passed (H3/H4 = 1), so the device-internal ctrl-rb -> GIC WIRE IS ALIVE; phase-48's dead-link hypothesis is REFUTED, and the earlier zeros mean the NATURAL FIRMWARE POSTS NEVER RING THE DOORBELL (a TRIGGER problem, not a dead wire). The dead-link and delayed-delivery branches are EXCLUDED by H0 bit 12 SET (both require it clear). Sanities: S1 = `0x1000`, S1+4 = `0x40161108`, S2 = `0x1`, S2+4 = marker; C0 = `0x1`, C1 = `0x0`, C2 = `0x3FF`, C3 = `0x0`, C4 = `0x0`, C5 = `0x3FF`; E0 = `0x1001`, E1 = `0x0`, E2 = marker, E3 = `0x80000093`; WIN = `0xE59FF018`; `[sig]` 9/9; staged `a68d5fed...` / stock `0e530b97...`. Bounds: instant samples (H0..H4 one-shot after the ring); the H cells are alias-only above the `0x104000` boundary and the alias model is INHERITED from gicsend/gicmask this boot (support: sentinels intact, H1 decodes a valid unique id, two CAs agree; not re-demonstrated by a BAR0-direct H read); H2 = pre-acknowledgement state; H0 bit 5 (`0x20`) is a second pending line, reported not attributed; H5's bit-12-clear is RECORDED, the "consumed / ran again" inference is weak (bit 5 could already have been set; does not affect Branch A); the ring actor is DEVICE-side, so the vendor's natural trigger is not reproduced. Verifier CONFIRMED (high): raw capture re-read, acceptance 60/0 + `gu_verify` 36/36 re-run, capstone showed the exact sequence (H5-entry -> mask OPEN `0x20` with NO `0x21` anywhere -> ring `0x92d4` ONCE -> H0..H4 -> sentinels; forbidden CAs absent in all pads, `0x8702c` preserved, 513 changed bytes confined); live device clean (no `.omo-pat`, stock md5, 0/0/3, 6 ifaces, `[SUCC]`); noted the two non-load-bearing items above. **Next (one line):** what natural firmware action should ring the H2D doorbell (the trigger), and whether the host ISR vision now follows a firmware-side ring.

**Follow-up - trigring + the two plans** (`opensource/docs/phase49/gic-view.md` ADDENDUM 6, `build/register-dumps/exp/20261005-075136/`, variant `trigring`, blob md5 `0769eed122c0506d3afca6b5a8bd8ae9` (an uncommitted working-tree addition on HEAD `140caee`), one cycle PASS, 07:51:35Z -> 07:54:07Z, `run-trigring.log`): the trigger test, the follow-up that fixes gicunmask's confound by taking the pre and post GIC samples in the SAME straight-line visit with the glue mask already OPEN, so the one ring store is the only actor between them. The send pad (site file `0x86f5a`) reproduces the natural `out[1]` post, holds the mask open (CA `0x400392E8` <= `0x20`; `0x21` NEVER written), samples T0..T3 PRE-ring, rings the H2D doorbell ONCE (CA `0x400392D4` <= `0x1`), then samples T4..T7 POST-ring and returns to the natural D2H notify. **BRANCH T4-BIT12: the ring -> GIC delta now stands alone.** T0 = `0x00000020` (ISPENDR2 word 2, bit 12 CLEAR, bit 5 set) -> T4 = `0x00001020` (BIT 12 SET = id `0x4c` pending); T5 = `0x0000004C` (HPPIR names id `0x4c`); T2/T3 = `0x0` -> T6/T7 = `0x1` (glue raw latched and passed the OPEN mask); sentinels T8 = T9 = `0x50AA7E49`. Three-way attribution: same-visit PRE/POST with the mask open across both; T6 bit 0 rising is independent proof the ring left the pad (the doorbell CA is write-only and self-clearing); and a T4-only artifact is excluded because gicpost/gicmask/gicking (same pads, frozen params, NO bit-0 ring) never showed bit 12 after their posts. Reproduces gicunmask's exact signature (`0x1020` / `0x4c`), now with a same-visit pre sample gicunmask lacked. Sanities: S1 = `0x1000`, S1+4 = `0x40161108`, S2 = `0x1`, S2+4 = marker; C0 = `0x1`, C1 = `0x0`, C2 = `0x3FF`, C3 = `0x0`, C4 = `0x0`, C5 = `0x3FF`; E0 = `0x1001`, E1 = `0x0`, E2 = marker, E3 = `0x80000093`; WIN = `0xE59FF018`; `[sig]` 9/9; staged `0769eed1...` / stock `0e530b97...`. HOST-SIDE WITNESS (from `build/tmp/trigger-spec/hostisr.md` section 2, run in the same cycle): `/proc/interrupts` has NO `207:`/`209:` line and no `omo-drv1` action, both `pci_dev->irq` read `255`, no `[isr]` dmesg line, and the done line carries no `irq0=/isr0=` fields. That is `hostisr.md` table ROW B (LINE ASSERTED WITHOUT HOST DELIVERY), but the port registers NO `request_irq` handler, so the null host witness is the expected absence of an instrument and settles INTA in NEITHER direction; ROW A (ISR FIRED) and its complement are both UNSUPPORTED. Bounds: T cells are one-shot instants, not a timing window; the T cells are alias-only above the `0x104000` boundary and the alias model is inherited from gicsend/gicmask (sentinels intact, HPPIR decodes a valid unique id); T0 bit 5 (`0x20`) is a second pending line, recorded not attributed; the host-side half is NOT decided (the named next branch, `hostisr.md`, needs the port to register `request_irq` and to drop the forbidden-IAR `irqwin=1` param); the ring actor is DEVICE-side, so the vendor's natural trigger is not reproduced; `interp.txt` was not produced, so the branch labels are read from the manifest's declared set plus `trigger.md` section 3. TWO VERIFIERS CONFIRMED (neither ran the cycle): the runtime one (`build/register-dumps/diffs/20261005-075136-vrun2/verdict.txt`, independent re-parse 70/0, acceptance 62/0, `trigring_verify.py` ALL PASS, and it removed the staged `.omo-pat` under the HARD RULE as R3) and the instrument one (`build/register-dumps/diffs/20261005T075346Z-vtool2/verdict.txt`, double regeneration byte-identical to the staged blob and to the frozen pin, the eight earlier variant pins byte-identical to HEAD `140caee`, capstone showing the ring CA `0x400392d4` <= `0x1` exactly once and mask `0x20` never `0x21`, `changed bytes OUTSIDE 4 sites + 4 pads: 0`, originals preserved, no forbidden CA, hook read-only with 39 devmem reads and no write). Health after the cycle: `WIFI=1 PLAT=1 WIPHY=2 IFACE=6 CAL_SUCC=1 OMO_OFF=0 STAGED=0 LOADER=0 RECOVER=0`, stock md5 re-verified, no `.omo-pat` or `.omo-off` leftovers, cal `[SUCC]` on both bands. The same session wrote **two first-class docs**: `opensource/docs/HYBRID-IMAGE-PLAN.md` (the graft plan from `build/tmp/trigger-spec/hybrid.md`: keep/graft lists, build inputs and steps, the A/B-safe flashing procedure, acceptance gates G1-G7, open decisions) and `opensource/docs/TOOLING-IMPROVEMENTS.md` (the ranked 9-item harness list from `build/tmp/trigger-spec/tooling.md` plus the top-3 quick wins). **Next (one line):** the HOST ISR acceptance test (`build/tmp/trigger-spec/hostisr.md`), registering the port's `request_irq` and dropping `irqwin=1`, to decide ROW A versus ROW B on the same boot.

- **Follow-up - trignat + the plans reframed** (`opensource/docs/phase49/gic-view.md` ADDENDUM 7, `build/register-dumps/exp/20261005-084742/`, variant `trignat`, blob md5 `845188343f70cff9de29e77aea464021` (uncommitted on HEAD `411831a`), NO branch: the capture never landed): the natural-post ring test's instrument (Pad A at the firmware's own `out[1]` post, Pad B the device-dispatcher consumption read) and the endpoint-IRQ port change (`virq2.md`; `struct pci_driver` + `request_irq`, CI run `37284211791`, artifact md5 `359d39572c6057e52bedd4afb309a14d`) were both built and staged, but **no trignat cell was captured**. The parent RUN failed on a HOST-SIDE cause (`tools/exp.sh` gates step 4 on `lsmod | grep '^wifidrv1-isr '` while the ko's internal name is `wifidrv1`), so the capture step never ran (evidence dir `.../exp/20261005-083612/` never created); the ONE authorised re-run (same module bytes, renamed to `wifidrv1.ko` so the gate matches) loaded and completed (`init done ... irq0=0 isr0=0`) but its capture hook was reset by the peer, leaving `capture-cmd.txt` at 0 bytes. Every trigger2.md section-4 input (`A_S3`, `A_S4`, `A_S5`, `A_S7`, `A_S8`, `B_D0`, `B_D2`, `B_P3`) is ABSENT, so TRIGNAT-COMPLETE / RING-PENDING-NOT-TAKEN / GLUE-ONLY / NOTHING are all UNSUPPORTED and the `PAD-DID-NOT-RUN` the parsers print is a null classification, not a measured value. Surviving dmesg only: `[sig] 9/9`, and the port's poll saw `out[0] 0x0 -> 0x8` / `out[1] 0x0 -> 0x4` at t=500 ms (no consumption witness). **VIRQ OUTCOME: NOT DELIVERED** (`pci_dev->irq=0`, `of_irq_parse_pci rc=-22`, no `request_irq`, `irq0=0 isr0=0`, no `207:`/`209:` line) = `hostisr.md` ROW B; the port change did not reproduce `pci_assign_irq() -> 207`. Verification `build/register-dumps/diffs/20261005-083612-vrun3/verdict.txt` (independent re-parse 15/53, acceptance 2/74, one live read-only probe: healthy). Device left healthy (stock md5, 0 `.omo-pat` auto-deleted by recover, 0 `.omo-off`, 2 wiphy / 6 ifaces, `[SUCC]` both bands). THE PLANS REFRAMED (lead's directive 2026-10-05, no vendor kernel): **`opensource/docs/UPSTREAM-PORT-PLAN.md` is NEW** (the subsystem inventory, the four-stage roadmap, the honest scale of ~2 years dominated by the Wi-Fi half, and the six bench actions we can start today, from `build/tmp/upstream-spec/upstream.md`), and **`HYBRID-IMAGE-PLAN.md` is DEMOTED** (a `STATUS: FALLBACK (not the goal)` header: retained only as a labeled fallback; the goal is our own fully-current OpenWrt, our kernel + our drivers). **Next (one line):** re-run `trignat` on the SAME blob with a capture that survives (stage under `wifidrv1.ko` or split the hook), and give the port a `pci_driver` path that actually assigns the INTx virq.

- **Amendment - the trignat retry, salvaged** (`opensource/docs/phase49/gic-view.md` "ADDENDUM 7 - AMENDMENT (2026-10-05)", `build/register-dumps/exp/20261005-090644-salvage/`, variant `trignat`, blob md5 `845188343f70cff9de29e77aea464021`, acceptance 88/0): the driver died mid-cycle at step `[4/7]`, the takeover boot stayed live, and the hardening paid off - the detached device-side hook wrote its output to a device file, so the orchestrator pulled a COMPLETE capture post-hoc (`capture-cmd.txt`, 25,766 bytes, provenance in `SALVAGE-NOTE.txt`). **BRANCH = PAD-DID-NOT-RUN** (`trigger2.md` section 4, the `-` row): Pad A rang and the ringed id `0x4c` reached the device GIC (`A_S3` = `0x00001020`, ISPENDR2 w2 bit 12 SET; `A_S4` = `0x0000004C` HPPIR; `A_S1` = `0x20` pre-ring; sentinels `A_P1`/`A_P2` = `0x50AA7E49`), but Pad B, the dispatcher-consumption pad, never executed: `B_D0..B_D3` = `0` and the `B_P3` sentinel ABSENT (an untouched all-zero page, where a live ISPENDR2 read would be `0x3FF`-class). Both pad calls ARE in the staged blob (file `0x86F5A` = `41f01df9`, file `0x86F7E` = `41f0f2f9`), so the gap is RUNTIME REACHABILITY - the `0xcece` handshake wait at `0x86F74` precedes Pad B's site, so it is a sequencing finding, not a patch defect. The device-dispatcher consumption question stays OPEN and no numbered row closes; `out[0] = 8` persisting the full 8000 ms poll is a datum, not `B_D0`. **VIRQ: NEGATIVE, with a concrete cause hint** - the port's new `pci_driver` path ran and reported `irq=0` (`of_irq_parse_pci rc=-22`; `irq0=0 isr0=0`; `request_irq` never called; ISR never executed = `hostisr.md` ROW B), so the task brief's wording "the port's ISR code ran" is corrected on the record. KNOBSET note: the module's internal name is `wifidrv1` (49152), not `wifidrv1-isr`. Recovery = two device mutations only (`touch /tmp/omo-exp.done`, then `/bin/sh /root/recover-exp.sh`): `touch` cancelled the armed watchdog (EXP_DONE_FLAG), and `recover-exp.sh` re-ran exp.sh's own step `[6/7]` recovery protocol - which had ALREADY run the identical recovery on the device (run-trignat-2.log: `recovery : ran`, health `omo_off=0` on the fresh boot) - so the manual re-run just repeated that same protocol to finish the orphaned cycle; fresh boot verified (stock md5, 0 leftovers, 6 ifaces, `[SUCC]`, 3 pstore). **Next (one line):** complete the `0xcece` handshake (or move Pad B's read to a reached site) so `B_D0`/`B_D2` get a producer and a numbered row closes, and assign the INTx virq so `request_irq` actually runs.

- **Follow-up - the consumption-gate retry + the virq root cause** (`opensource/docs/phase49/gic-view.md` "ADDENDUM 8 (2026-10-05)", `build/tmp/dt-spec/padb.md`, `build/tmp/dt-spec/virq3.md`, variant `trigcons`): the Pad-B gate fix and the host-side virq fix. The gate is a host-side handshake scratch word: the announce routine spins on `*(CA 0x4000010c) == 0x0000cece` (the value is written 0 times in the image and in every held `.ko`), and the register is the host-visible pair-mate of the release, BAR0+`0x3b810c`, so Pad B's stock site behind the wait is unreachable (`padb.md` option (a)). The `trigcons` variant MOVES Pad B onto the wait's own `movw r3,#0xcece` at file `0x86F74` and doubles the B pagination, so Pad B is now guaranteed to run and the B cells get a producer, though the read stays pre-consumption (row 2 ceiling). The protocol-truth companion is option (c): the HOST writes `0x0000CECE` to BAR0+`0x3b810c` after the release, the only fix that can reach row 1 TRIGNAT-COMPLETE. The virq negative's real cause is recorded: the `-22` is the port's own `of_irq_parse_and_map_pci` fallback (a dead end here, no `interrupt-map` and no endpoint OF node), and the port THREW AWAY the 207 the core had already assigned (`pci_assign_irq()` runs before `.probe`; `hi_pcie_map_irq` returns the RC's `radm` line, SPI 59 = GIC 91 = 207) because the module is cross-built against vanilla 5.10 headers where `struct pci_dev->irq` sits at 0x1ac while the vendor kernel has it at 0x184. Fix: read the line back through `PCI_INTERRUPT_LINE` (submodule commit `3ac4820`, `omo/phase22-hccaccept` only); boot witness is a `207: N N GIC-0 91 Level omo-drv1` line whose counter moves with the ring. Hard rules held: no write of CA `0x400392f0`, no read of `0x10161000`, no read of the IAR `0x4016010c` (the gate register `0x4000010c` is a different address). No device cycle was run for this record.

- **Amendment - the corrected trigcons-2 run** (`opensource/docs/phase49/gic-view.md` "ADDENDUM 8 - AMENDMENT (2026-10-05)", `build/register-dumps/exp/20261005-103047/`, variant `trigcons`, `EXP RESULT: PASS`, acceptance 92/0, verifier CONFIRMED `build/register-dumps/diffs/20261005T1022Z-vtool5/verdict.txt`): the retry the earlier ADDENDUM 8 could not stage LANDED and changed both halves. **DEVICE ROW = ROW 2 RING-PENDING-NOT-TAKEN** - the moved Pad-B drain-point site at file `0x86F74` (`TRIGCONS_SITE_B`; stock bytes `4cf6ce63` -> `bl #0x108366`) RAN (`B_P3` = `0x50AA7E49`), the ring reached the device GIC (`A_S3` = `0x00001020` bit 12; `A_S4` = `0x0000004C` HPPIR) and was STILL PENDING at the drain point (`B_D0` = `0x8`, `B_D1` = `0x4`, `B_D2` = `0x00001020`, `B_D3` = `0x0000004C`), so the device dispatcher did not consume within the observed window (`not yet` per the bounds; the ROW-2 branch string's `never ran` wording is stronger than the bounds support). **HOST ROW = VIRQ 207 OWNED, NO ISR OBSERVED** - the struct-layout-proof fix (submodule `3ac4820`: read `PCI_INTERRUPT_LINE`; the vanilla-vs-vendor `pci_dev->irq` offset mismatch `0x1ac` vs `0x184` had thrown away the core-assigned 207) gives `dmesg` `init done ... irq0=207 isr0=0`, `request_irq(207, IRQF_SHARED) rc=0`, `/proc/interrupts` `207: 0 0 GIC-0 91 Level omo-drv1` (freshness via `interrupts-pre.txt`, the vendor's `hisi_pci_intx` action before staging). TWO SETUP FIXES made the run valid: stage the artifact as `wifidrv1.ko` (the module's internal name; the old `wifidrv1-isr` filename made `exp.sh`'s wait grep the wrong name, the root cause of several earlier `timeouts`) and a TS-gated capture recovery (the old selector grabbed the stale salvage dir). PROVENANCE: the artifact zip's sha256 == the API digest for CI 37295389630, `.ko` md5 `1f0e80ed9a02b80ab2deb337d288e781` at submodule `3ac4820`. REMAINING UNKNOWNS: (a) the device dispatcher's non-consumption, bounded to the window; (b) the D2H/INTA host-facing path, why a device post has not fired the owned line 207. RISKS CARRIED: the ROW-2 branch string's `never ran` vs the bounds' `not yet` tension; the gitignored runner's broken recovery selector (safety held, scratch removed manually); `PACKED.txt` frozen before `health.txt`; CRLF/LF mixing in evidence text (cosmetic); pre-existing `register_netdevice` WARNs. Health after recovery `WIPHY=2 IFACE=6 CAL_SUCC=1 OMO_OFF=0 STAGED=0 LOADER=0 RECOVER=0`, stock md5 `0e530b976d5a20e87358671f1a577695`, 3 pstore records (no new crash), no takeover leftovers.

- **Correction - ADDENDUM 9 was written about the wrong run; the real `inta` run is `110922`** (`opensource/docs/phase49/gic-view.md` "ADDENDUM 9 - CORRECTION (2026-10-05): the real inta run (110922)"; `build/register-dumps/exp/20261005-110922/`, variant `inta`, `EXP RESULT: PASS`, `exp_rc=0`, acceptance 108/0 `ALL_OK`, adversarial verifier `build/register-dumps/diffs/20261005-110921-vrun6/verdict.txt` FINAL CONFIRMED medium-high with two recorded deviations, instrument verifier `build/register-dumps/diffs/20261005T1115Z-vtool6/verdict.txt` CONFIRMED): the ADDENDUM 9 block in `gic-view.md` re-told the `trigcons-2` story under the new heading and cited `build/register-dumps/exp/20261005-103047/` as "this run", so the block is SUPERSEDED (not deleted) for everything it says about the `inta` variant; its `trigcons-2` content stands as ADDENDUM 8 - AMENDMENT, and the `phase49/README.md` pointer was adjusted to the corrected block. INSTRUMENTS: the port's `intapost` knob (submodule `b5f6aac`, "lab(wifidrv1): post-release D2H/INTA ring knob (intapost)", `omo/phase22-hccaccept` only) plus the fw blob `build/tmp/fw-patched/inta.bin` (md5 `bcf14dbeefe45bcfce8df279c06776bd`, re-hashed this session). FOUR `[intapost]` STEPS: step `0x8` natural-post wrote `0x0000cece` to CA `0x4000010c` (`rb=0xcece`, the designed unlock of the device's masked park) and the glue LATCHED, raw `0x0` -> `0x8` (bit 3), status `0x0` -> `0x18` (bits 3+4); steps `0x1` (CA `0x400392d4` <= `0x1`), `0x2` (CA `0x400392d4` <= `0x8`), and `0x4` (CA `0x40101434` <= `0x1`) each produced raw `0x8` -> `0x8`, status `0x18` -> `0x18`, isr `0` -> `0` (delta 0), waited 2000 ms each; glue mask `0x20` on every step. **HOST ROW 2 = GLUE LATCHED, NO HOST DELIVERY**: the glue latched (status `0x18`) but `/proc/interrupts` `207:          0          0     GIC-0  91 Level     omo-drv1` stayed count 0 and `isr0=0` (freshness via `interrupts-pre.txt`, the vendor's `hisi_pci_intx` action before staging), so the assertion/forward hop (glue -> endpoint INTx -> RC -> host GIC 91) is THE remaining gate. DEVICE: `B_D2` (ISPENDR2 w2) = `0x1020` pending persists, `B_D4` (ISACTIVER2 w2) = `0x0` not taken, `B_D5` (CPSR) = `0x20000193` with I = 1 (IRQs masked at the drain), `B_D6` GICC_CTLR = `0x1`, `B_D7` PMR = `0xf0`; the unlock LANDED - Pad L ran ONCE (`L_CNT=1`, the loop EXITED) - but the delayed `L2` samples are all 0 (`L2_ISP` bit 12 clear, `L2_OU0` = 0) because nothing re-visited the park; sentinels `A_P1`/`A_P2`/`B_P3`/`B_P4`/`L_SNT` all `0x50AA7E49`. TWO VRUN6 DEVIATIONS (carried as caveats on the branch labels): (1) the host-path row is reached on the `0x8` natural-post provenance, not the `0x2`/`0x4` steps the row names (their deltas are 0; the acceptance's bit-3 predicate reads post-state already latched by `0x8`); (2) `devcpu.md` section 5 ROW 2's literal predicate is NOT satisfied (`L2_ISP` bit 12 clear, `L2_OU0` = 0, and ROW 4 fails its own clause too), so the named row is a meaning-based classification on the drain instant, and "parked in the `0xcece` handshake" is contradicted by this run's own `L_CNT=1`, which proves the unlock exited the loop. HEALTH and hard rules: live device healthy (stock md5 `0e530b976d5a20e87358671f1a577695`); IAR `0x4016010c` never read; the gate CA `0x4000010c` is the only `0x...10c` touched; `patch_fw_scratch.py --selftest` PASS with the new `inta` pin. NEXT (one line): the forward hop is the gate now, so read the endpoint's INTx config-space state (Command Interrupt Disable, Device Control 2 INTx signalling disable, the RC bridge INTx control), take a post-unlock device sample, and re-visit for the `L2` delayed cells.

- **Amendment - the dual-sided INTA test** (`opensource/docs/phase49/gic-view.md` "ADDENDUM 9 (2026-10-05): the dual-sided INTA test", `build/register-dumps/exp/20261005-103047/`, variant `trigcons`, `EXP RESULT: PASS`, acceptance 92/0 `ALL_OK`, `run-trigcons-2.log` 10:30:46Z -> 10:33:18Z, verifier CONFIRMED `build/register-dumps/diffs/20261005T1022Z-vtool5/verdict.txt` plus the record check `20261005T102701Z-vrec4/verdict.txt`; NOTE: this block's heading names the `inta` test but its evidence is the `trigcons-2` run, see the correction bullet above): the trigcons-2 run repeats ADDENDUM 8's amendment with both setup fixes BUILT INTO the instruments (no hand-renamed artifact, no hand-picked capture dir), so this is the first cycle to test the interrupt on BOTH sides at once. **DEVICE ROW = ROW 2 RING-PENDING-NOT-TAKEN** - the ring reached the GIC (`A_S3` = `0x00001020`, ISPENDR2 w2 bit 12 SET; `A_S4` = `0x0000004C` HPPIR) and the moved Pad-B drain-point site at file `0x86F74` (`TRIGCONS_SITE_B`; stock bytes `4cf6ce63` -> `bl #0x108366`; old announce-exit site `0x86F7E` left stock) RAN (`B_P3` = `0x50AA7E49`), but the id was STILL PENDING at the drain point (`B_D0` = `0x8` out[0], `B_D1` = `0x4` out[1], `B_D2` = `0x00001020` bit 12 SET, `B_D3` = `0x0000004C` HPPIR), so the dispatcher did not consume within the observed window (`not yet` per the bounds; the ROW-2 branch string's `never ran` wording is stronger than the bounds support). **HOST ROW = VIRQ 207 OWNED, NO ISR OBSERVED** - the struct-layout-proof port (submodule `3ac4820`, branch `omo/phase22-hccaccept`; reads `PCI_INTERRUPT_LINE` because the vanilla-vs-vendor `pci_dev->irq` offsets `0x1ac` vs `0x184` mismatch had thrown away the core-assigned 207) gives `request_irq(207, IRQF_SHARED) rc=0`, done line `irq0=207 isr0=0`, and `/proc/interrupts` row `207: 0 0 GIC-0 91 Level omo-drv1` (freshness via `interrupts-pre.txt`, the vendor's `hisi_pci_intx` action before staging). Carried-forward re-checks: `S1` = `0x1000`, `S1+4` = `0x40161108`, `S2` = `0x1`, `S2+4` = `0x50aa7e49`; sentinels `A_P1` = `A_P2` = `B_P3` = `0x50AA7E49`. BOUNDS: the drain-point read is a single `not yet` instant, not a proof of permanent non-consumption; `isr0=0` is a count at two instants, so VIRQ OWNED is ownership plus a registered handler, not a delivery, and the D2H/INTA path stays unobserved; the A_*/B_* cells are alias-only (above the `0x104000` boundary, BAR0 view reads 0) with the alias mechanism UNEXPLAINED; ROW 2 is a suffix of `trigger2.md` section 4's ROW 2, so row 1 TRIGNAT-COMPLETE stays out of reach; disclosed risks carried (the `never ran` vs `not yet` tension, the gitignored runner's broken recovery selector with safety held and the scratch removed by hand, `PACKED.txt` frozen before `health.txt`, CRLF/LF mixing, pre-existing `register_netdevice` WARNs); hard rules respected (no write of CA `0x400392f0`, no read of `0x10161000`, no read of the IAR `0x4016010c`; the gate register `0x4000010c` is a different address). PROVENANCE: the `trigcons` blob regenerates byte-identical (size 928920 B, md5 `5fb51acd68c62699435d2e1fd823d900` pinned in `tools/patch_fw_scratch.py`), the 726 changed bytes all sit inside the five sites and five pads, no forbidden CA is touched, the artifact zip's sha256 == the API digest for CI run 37295389630 with `.ko` md5 `1f0e80ed9a02b80ab2deb337d288e781` at submodule `3ac4820`; `knobset-digest.txt` records the frozen knob-set hash `541060a8...`; health after recovery `WIPHY=2 IFACE=6 CAL_SUCC=1 OMO_OFF=0 STAGED=0 LOADER=0 RECOVER=0`, stock md5 `0e530b976d5a20e87358671f1a577695`, 3 pstore records (no new crash), no takeover leftovers. THE TWO SETUP FIXES (now paid forward into the instruments): stage the artifact as `wifidrv1.ko` (the module's internal name; the old `wifidrv1-isr` filename made `exp.sh`'s wait grep the wrong name, the root cause of several earlier `timeouts`) and a TS-gated capture recovery (the old selector grabbed the stale salvage dir). REMAINING UNKNOWNS: (a) the device dispatcher's non-consumption, bounded to the window; (b) the D2H/INTA host-facing path, why a device post has not fired the owned line 207.

- **The INTA knob v2 + the inta2 run - the 209 witness and the post-exit take** (`opensource/docs/phase49/gic-view.md` "ADDENDUM 10 (2026-10-05): the forward-hop probe + the post-unlock take", `build/register-dumps/exp/20261005-115837/`, variant `inta2`, one `exp.sh` cycle, staged blob `build/tmp/fw-patched/inta2.bin` md5 `545e77a5b12b4e0da8a6923eea29672c`, staged `.ko` md5 `4d56a0ae3c6f860c86b20a7c3c819605` at submodule `0398e20` (CI run 37305885971, run log `run-inta2.log`), adversarial verifier `build/register-dumps/diffs/20261005-115836-vrun7/verdict.txt` NOT CONFIRMED as a positive, instrument verifier `build/register-dumps/diffs/20261005T1200Z-vtool7/verdict.txt` 5/5 artifact checks CONFIRMED with one functional defect found live; specs `build/tmp/inta-spec/{intx.md,take2.md,devcpu.md}`): the run that answered ADDENDUM 9 - CORRECTION's two named next threads in one boot. KNOB V2 (two new `intapost` bits, no 42nd knob): `0x10` `dual-line` claims the sibling `0001:00:00.0`, reads its `PCI_INTERRUPT_LINE`, and `request_irq`s it `IRQF_SHARED` as `omo-drv1-ep1` with a second counter `omo_isr2_n`; `0x20` `snapshot` prints the read-only config/glue comparison around each documented write. Port commits `3089cb7` + `0398e20` (the one re-run fixed a zero-variadic `OMO_SM` macro with `##__VA_ARGS__`, a named host-side cause), `omo/phase22-hccaccept` only. THE FOUR `[intx2]` STEPS: baseline A; step B wrote the `0xcece` unlock to CA `0x4000010c` (`rb=0xcece`), the glue LATCHED (raw `0x1` -> `0x8`, stat `0x11` -> `0x18`) and out[0] fell `0x8` -> `0x0`; steps C (CA `0x400392d4` <= `0x1`), D (CA `0x400392d4` <= `0x8`), E (CA `0x40101434` <= `0x1`) each left raw/stat pinned with isr delta 0 (2000 ms each); E1/E2/E3 all printed `ok` (no conditional enable write fired). **HOST = NO ROW** - the port's `omo_dual_line_attach` read the sibling's config `PCI_INTERRUPT_LINE` as `0xff` (`[intx2] no sibling INTx virq (irq=255)`) and skipped `request_irq(209)`, so no 209 measurement exists (`isr209` stays 0 but VACUOUS, no `209:` line, no `[isr2]`); the SAME capture shows the kernel owns 209 (sysfs `0001:00:00.0 irq=209`, lspci pin A -> IRQ 209) and the pre-run snapshot had it live (`209: 158016 0 GIC-0 95 Level hisi_pci_intx`), so no `intx.md` section 4.5 row is satisfied and ROW 5's premise (both lines enabled) is FALSE; the fix is to source the sibling virq from `omo_ep1_dev->irq`. **DEVICE = SITE F RAN, SITE N VOID** - Site F (the `0xcece` gate's fall-through file `0x86F7E`, stock `bde8f843` replaced) ran (`F_SNT` = `0x50AA7E49`) and is a coherent pre-take baseline (`F_ISP` = `0x1020` bit 12 SET pending, `F_ACT` = `0x0` not active, `F_HPP` = `0x4C`, `F_OU0` = `0x8` unconsumed, `F_PSR` = `0x60000193` I = 1), i.e. take2.md section 4 ROW 3 in form and the take still UNWITNESSED; all six `N_*` cells read `0x0` including the constant `N_SNT` and the live `N_PSR`, and the send pad is a straight-line block whose LATE deposits (`A_S0..A_S8`, `A_P1`/`A_P2`) are all present, so the acceptance's "single-visit boot" cause is CONTRADICTED - page 14 (runtime `0x157000`, alias `0x4080E000`) did not RETAIN the pad's writes, a cell-selection/mapping defect (pages 9/10/11/12/13 all retain theirs). Kept baseline: `B_D4` = `0x0`, `B_D5` = `0x20000193` (I = 1), `A_S3` = `0x1020`, `A_S4` = `0x4C`. TWO MIS-ATTRIBUTIONS recorded (the module's "209 unavailable" as a hardware fact; the acceptance's single-visit cause). PROVENANCE: the `inta2` blob regenerates byte-identical (928920 B, pin `545e77a5...`), the changed bytes all sit inside the six sites and seven pads, no forbidden CA, the artifact zip's sha256 == the API digest for CI 37305885971, `patch_fw_scratch.py --selftest` PASS with the new `INTA2_MD5`. Acceptance re-run 100 passed / 4 failed (the four are the honest N_SNT + 209 consequences). Health `WIPHY=2 IFACE=6 CAL_SUCC=1 OMO_OFF=0 STAGED=0 LOADER=0 RECOVER=0`, stock md5 `0e530b976d5a20e87358671f1a577695`, 3 pstore records; git carries the two expected tracked changes, both masters untouched, submodule `0398e20` in sync. NEXT (one line): source the sibling virq from `omo_ep1_dev->irq` so the forward-hop row is testable, re-pick the Site-N page with a writability check, and sample a later boot phase for the take.

- **The twin/ETE probe: the run FAILED with no capture, the twin hypothesis is BLOCKED** (`opensource/docs/phase49/gic-view.md` "ADDENDUM 11 (2026-10-05): the twin/ETE probe + the corrected witnesses", `build/register-dumps/exp/20261005-130020/`, variant `inta3`, one `exp.sh` cycle via `run-inta3.sh`, `EXP RESULT: FAIL`, `exp_rc=1`, start 2026-10-05T13:00:19Z, staged blob `build/tmp/fw-patched/inta3.bin` md5 `eee1f67370b56eca42316f6eeb490c45` == the boot's `/lib/firmware/hi_wifi/FIRMWARE.bin.omo-pat`, staged `.ko` md5 `e20bf7e571c5a57823e76b7fa849ebf8` at submodule `73b1230` (CI run 37312967151), adversarial verifier `build/register-dumps/diffs/20261005-131645-vrun8/verdict.txt` FINAL CONFIRMED with the parent's own `CYCLE-FAILED.txt` central claim REFUTED, instrument verifier `build/register-dumps/diffs/20261005T1315Z-vtool8/verdict.txt` 5/5 artifact checks CONFIRMED with one accepted spec deviation; specs `build/tmp/inta-spec/{twin.md,witness2.md,dtc.md}`): the run the ADDENDUM 10 next threads named, on the twin/ETE layer the vendor host never touches. KNOB V3 (same `intapost` bitmask, no 42nd knob): v2's `0x10` `dual-line` (the CORRECTED 209 witness - the source is now the kernel's IRQ for `0001:00:00.0` with a guarded `pci_get_domain_bus_and_slot()->irq` read and a compile-time offset guard, the config `INTERRUPT_LINE` byte printed only as a cross-check) and `0x20` `snapshot` (WIDENED with copy B's raw/mask/status CA `0x40039ae4/0xae8/0xaec` and the ETE group's mask/clr/status CA `0x40039508/0x50c/0x510`, plus W3 the vendor's own ETE clear) are joined by `0x40` `twin-stim` (W1 CA `0x40039ae8 <= rd & 0xfffffc20`, the vendor's own copy-A constant, and W2 CA `0x40039ad4 |= 0x8`, the mirror of copy A's D2H set - the ONE new candidate, a hypothesis not a reproduction) and `0x80` `msi-test` (a read-only PROBE, MEASURED platform limit `CONFIG_PCI_MSI=n`: the CI's vanilla headers set it `=y`, so the first artifact arrived with three UNDEFINED MSI symbols and `insmod` would have failed; vtool8 accepted the deviation). Permitted new writes: CA `0x40039ae8` (W1), `0x40039ad4` (W2), `0x4003950c` (W3). FIRMWARE `inta3` (witness2.md FLAW 2): inta2 byte-for-byte EXCEPT the six Site-N cells moved off the non-retaining page 14 (`0x157000`) onto page 10 (`0x150000`, the band that retained across the last two runs) at `0x150058..0x150080`, with `N_SNT` = `0x50AA7E49` kept as a retention sentinel (the six cells `N_ACT/N_ISP/N_HPP/N_OU0/N_PSR/N_SNT` read ISACTIVER2/ISPENDR2/HPPIR/out[0]/CPSR/sentinel); exactly 12 bytes differ from inta2, all inside Pad A(N). **ALL THREE BRANCH TABLES ARE NO-ROW**: the cycle died at step `[4/7]` (the done marker never appeared within the 600 s bound), so `capture-cmd.txt` never landed and there is no capture to re-parse - a NEGATIVE ON DATA, not a negative on the hypothesis; the forward hop (twin.md section 6 rows 1-9), the corrected 209 witness (FLAW 1) and the retention-band cells (FLAW 2) are all UNSUPPORTED, and the twin hypothesis ("copy B drives `0000:00:00.0`'s pin") stays BLOCKED, not decided. **THE PARENT'S SELF-REPORT IS REFUTED**: a NEW pstore panic record (`dmesg-pstore_blk-3`, 69,508 B) appeared in the window whose ONLY device cycle is this RUN (the pstore set changed from `{blk-0,blk-1,blk-2}` at 2026-10-05T12:04:12Z to `{blk-2,blk-3}` at this run's pstore check) and IS this run's dump - `Panic#1 Part1`, `Comm: insmod`, `wifidrv1` frames (`register_netdevice <- omo_add_virtual_intf <- omo_wifidrv1_init`), the inta2 boot's shape with the timeline shifted +2.81 s / +3.11 s (consistent with v3's extra steps having run), and the DECISIVE DELTA vs inta2 `isr0=0` versus `isr0=6511173` plus ~350 `[isr] irq=207 ... status=0x00000018` lines (~2.3e6 IRQ/s) to t=244 s. So the boot PANICKED on a 207 IRQ STORM with the glue copy-A post-mask status latched (`0x18`) that the port's ISR could not clear; the record's window begins after the knob's print points (the storm's ~31 KB of `[isr]` output evicted everything earlier), so it CANNOT name the step - `CYCLE-FAILED.txt`'s candidate list (a)-(e) stays a hypothesis, and its "no data exists" premise and "not from this run" attribution are dead. THE ONE RE-RUN RULE WAS HONORED: the failure is device-side (the box reset while the takeover module was up), not a named host-side cause, so no re-run was made. vtool8 NOTE 1 records the one new undefined symbol (`simple_strtol`, an unconditional `EXPORT_SYMBOL` in 5.10) that local artifacts could not resolve but which is almost certainly fine. HEALTH after recovery (3 read-only ssh probes, no write, no reboot): stock FIRMWARE.bin md5 `0e530b976d5a20e87358671f1a577695`, zero `.omo-pat`/`.omo-off`/staged-ko/loader leftovers, lsmod `hi5622v100_plat + hi5622v100_wifi` with no `wifidrv1`, `WIPHY=2 IFACE=6`, `[SUCC]` both bands, pstore 2 records (blk-2 + the new blk-3), 209 live again (`hisi_pci_intx`), 207 reading 0; hard rules held (no write of CA `0x400392f0` or `0x40039af0`; no read of the IAR `0x4016010c` or RC misc `0x10161000`). Git carries the two expected tracked changes (the `opensource` gitlink `4ee616e -> 73b1230` and `tools/patch_fw_scratch.py`, +208/-11), master untouched, submodule `73b1230` in sync on `omo/phase22-hccaccept`. NEXT (one line): re-open the inta3 FAIL against blk-3 as EVIDENCE (correct the mis-attribution), isolate ONE v3 delta at a time so a future storm can be attributed to a named step, and re-test the corrected 209 caller plus the page-10 cells once a capture lands.

- **The max-parallel sweep - the storm mode, the ladder, the 209 witness, the DTS + driver skeleton** (`opensource/docs/phase49/gic-view.md` ADDENDUM 13, `build/register-dumps/exp/20261005-135624/` (quiesce baseline), `build/register-dumps/exp/20261005-160844/` (`MAXPAR=8`), `build/register-dumps/exp/20261005-171233/` (variant v5, `MAXPAR=1`), submodule `2507a42` on `omo/phase22-hccaccept` only): the bound is now exercised, not only statically verified. The deliberate storm (`quiesce=0x7|0x8 qbound=16`) tripped `IRQ_DISABLED_BOUND irq=207 n=16 glue=00000018`, and the ladder resolved to `QUIESCED_BY_MASKCLOSE` (CONSUME and FWACK left the glue status latched). The 209 witness moved its source to `omo_ep1_dev->irq` so `request_irq(209)` runs. The clocks half landed as files: `docs/soc/luofu-r116.dts` folds `clk:`+`rst:` into one `crg: clock-reset-controller@14880000` node (`", "syscon", "simple-mfd"`, `#clock-cells=<1>`, `#reset-cells=<2>`, 23 insertions / 33 deletions, uncommitted) and `lab/luofu-clk/` carries the NOT-YET-COMPILED driver skeleton. Bounds: the storm, the ladder and the 209 rows are NOT-IN-CAPTURE (report-only, no independent parser), the bound tripped once, the deliberate storm is not the ADDENDUM 11 storm, and the DTS is uncommitted. **Next (one line):** pack the two sweep captures so the storm, ladder and 209 rows get re-derived from bytes, and build `lab/luofu-clk/` for real.
 (`opensource/docs/phase49/gic-view.md` "ADDENDUM 12 (2026-10-05): the quiesce probe", `build/register-dumps/exp/20261005-135624/`, variant `quiesce`, one detached `exp.sh` cycle via `run-quiesce.sh`, start 2026-10-05T13:56:23Z end 13:59:05Z, `EXP RESULT: PASS`, `exp_rc=0`, staged blob `build/tmp/fw-patched/inta3.bin` md5 `eee1f67370b56eca42316f6eeb490c45` == the boot's `/lib/firmware/hi_wifi/FIRMWARE.bin.omo-pat`, staged `.ko` md5 `91fba1dc512536c94bfd1e419173c046` at submodule `2507a42` (CI run 37320054878, `omo/phase22-hccaccept` only), adversarial verifier `build/register-dumps/diffs/20261005-135623-vrun9/verdict.txt` CONFIRMED with THREE recorded corrections, instrument verifier `build/register-dumps/diffs/20261005T1401Z-vtool9/verdict.txt` 6/6 artifact checks CONFIRMED with the mandatory bound present and structurally sound; specs `build/tmp/inta-spec/{quiesce.md,bisect.md,clocks2.md}`): **KNOB V4** adds four module params beside the frozen `intapost` set (`quiesce` bitmask, `qbound` clamped `1..64`, `qwait_ms` clamped `<=5000`, and `bisect`) and THE HARD BOUND - both ISRs test `qbound` BEFORE any MMIO and `disable_irq_nosync()` the line(s) they own after K entries, printing `IRQ_DISABLED_BOUND` with the count (verified in the shipped object: `disable_irq_nosync` x3 / `enable_irq` x2 relocations, the bound in force from the first entry, and the ISR's own log bounded to 1 line / 256 entries so the instrument can never printk-storm); `qbound` can never be 0 when the ISR runs. This boot armed `quiesce=0x7 qbound=64 qwait_ms=5000 bisect=5`. **BRANCH 1 = NO-STORM, LATCH-HELD, NOT-QUIESCED**: the ladder and the bound both armed from the first entry (`mode=0x7 bound=64`), but the 207 line never fired - `isr0=0` at `init done`, `isr_n=isr2_n=0` at every `[qsv]` BEFORE/AFTER, `/proc/interrupts` `207: 0 0 GIC-0 91 Level omo-drv1`, zero `[qsv] entry` lines - and the ladder runs INSIDE the ISR, so with no interrupt NO mechanism executed; the supervisor was a pure arm-and-wait, the glue held `raw=0x1 mask=0x20 stat=0x11` the whole 5000 ms (`bounded=0/0`), and it ended `quiesced=0 winner=- irq=enabled maskrestored=0` (`NOT QUIESCED`, left enabled). THE HARD BOUND HELD VACUOUSLY (armed, never exercised; `IRQ_DISABLED_BOUND` never printed); NO numbered quiesce.md sec.6 row is literally satisfied - row 6's "glue clear" is only HALF met (`stat=0x11`, not clear), hence the unnumbered label - and the storm did NOT reproduce under `bisect=5`. **BRANCH 2 = B5 CONFIGURED, STIMULUS UNEXECUTED (the single-variable boot HOLDS, but the 209 witness did not ARM)**: the ring line read `intapost ring knob 0x0 (bisect=5 effective=0x10, post-release)`, with 3 `[intx2]` lines and 0 `[intx3]` lines, so the `0x40` twin/ETE snapshot + stimulus did not run; BUT vrun9's load-bearing correction stands - the 209 bit was COMPILED IN and its RUNTIME stimulus did not arm: `omo_dual_line_attach()` fell to its `else` and returned `-ENODEV` because the sysfs virq read `255`, so there is no `[intx2] request_irq(209 ... rc=0` line (the port's compiled `pci_dev->irq` offset is still `0x1ac`, the vendor's `0x184`, so it took the sysfs fallback). THE BISECT CULPRIT IS UNRESOLVED and this boot rules only that neither `0x10` NOR `0x40` is a SUFFICIENT cause on this boot (`0x40` absent, `0x10` inert, no storm), by `bisect.md` sec.3's single-variable design; bisect.md sec.0 already settled that the pstore storm record is an OLDER wifidrv1 boot, NOT the knob-v3 run, so no `intapost` bit is proven to have fired it and the candidate set (a) the widened twin-copy-B read, (b) the W2 doorbell, (c) the W1 mask, (d) the 209 shared-ISR path, (e) the MSI probe (dead by design) survives as a hypothesis list. **BRANCH 3 = the corrected 209 WITNESS UNAVAILABLE**: three `[intx2]` lines (`compiled pci_dev->irq at 0x1ac (vendor 0x184) - using the sysfs virq`; `sibling irq(irq=255) cfg INTERRUPT_LINE=0xff (cfg read is not the witness)`; `no sibling INTx virq (irq=255) - the 209 witness is unavailable`), so `request_irq(209)` was skipped and a 209 counter of 0 is VACUOUS (no `209: ... omo-drv1-ep1` line, no `[isr2]`); the CORRECTED 209 SOURCE still does not name the right line. THE 255 ANOMALY IS REAL AND UNEXPLAINED: the SAME capture shows the host owning 209 (sysfs `0001:00:00.0 irq=209`, `Interrupt: pin A routed to IRQ 209`, and `interrupts-pre.txt` with the vendor's `209: ... hisi_pci_intx`), so vrun9 replaced the run's "not a usable line at the probe instant" (an unsupported claim about the environment) with the defensible "the PORT's read returned 255, so `request_irq(209)` was skipped"; the root cause is not determinable read-only. **BRANCH 4 = RETAINED - THE PAGE-10 CELLS FINALLY LAND** (witness2.md FLAW 2 validated): the six `N_*` cells on page 10 (`0x150000`, the band that retained across the last two runs, at `0x150058..0x150080`) all read back as DEPOSITS - `N_ACT=0x0` (not active), `N_ISP=0x20` (bit 12 pending), `N_HPP=0x3ff` (nothing pending for the CPU), `N_OU0=0x0` (consumed), `N_PSR=0x20000193` (I=1, IRQs masked), and `N_SNT=0x50AA7E49` with the same-page sentinels `A_P2=B_P3=0x50AA7E49` intact (`F_SNT` on page 13 = 0, this boot's Site-F pad did not deposit) - against inta2 where all six read 0 including the constant sentinel, so ADDENDUM 11's page-selection defect is FIXED and the retention guard is now a real witness; the take is STILL UNWITNESSED (`N_ACT=0`, `N_PSR` I=1 at the fall-through). PSTORE DELTA: the set is UNCHANGED (`{blk-2 50916 B, blk-3 69508 B}`), so the bound did not trip and no crash dump exists. VERIFICATION: the shipped acceptance re-runs to PASS (`EXP RESULT: PASS`, 14/14; item 4's PASS is vacuously true because the line never fired, disclosed in interp.txt) and `gen_quiesce_evidence.py` reproduces the shipped `KNOBSET.txt`/`interp.txt`/`acceptance.txt` BYTE-IDENTICAL; vrun9 CONFIRMS the capture, the counters, the cells and the witnesses (the `[sig]` 9/9, the staged blob `eee1f673...` ON DEVICE, the stock blob `0e530b97...` UNCHANGED, `[qsv]` `glue=00000011` held) plus a live read-only device check (3 probes, no write, no reboot: `WIPHY=2 IFACE=6 CAL_SUCC=1 OMO_OFF=0 STAGED=0 LOADER=0`, `PSTORE_COUNT=2` unchanged, `207: 0`, and 209 live again as `hisi_pci_intx`), with THREE corrections (BRANCH 2's "armed" -> "CONFIGURED, STIMULUS UNEXECUTED"; BRANCH 3's reason; BRANCH 1's row labelling); vtool9 CONFIRMS 6/6 artifact checks (the commit + its pushed branch, the re-fetched CI `.ko`, the bound diff, the selftest + ALL frozen pins + the `INTA3_MD5`, two byte-identical regenerations, the capstone of the inta3 sites, the hook + TS gate) with one accepted spec deviation (the bound prints `bound=%u` plus `n=`) and notes (the `omo_intapost_run` refactor wording, the unexercised bound, the unsettled 255), and flags the 13 pre-existing `register_netdevice` WARNINGs as NOT run-specific (identical 13 in three earlier dirs). HEALTH after recovery: stock md5 `0e530b976d5a20e87358671f1a577695`, `WIPHY=2 IFACE=6 CAL_SUCC=1`, no `.omo-pat*`/`.omo-off`/staged-ko/loader leftovers, the staged `.omo-pat` auto-deleted; hard rules held (no write of CA `0x400392f0`/`0x40039af0`, no read of the IAR `0x4016010c` or RC misc `0x10161000`; the gate CA `0x4000010c` is a different address; the ko was staged as `wifidrv1.ko`). Git carries the pending `opensource` gitlink bump only, master untouched, submodule `2507a42` in sync on `omo/phase22-hccaccept`. NEXT (one line): make the 209 source deliver a live line (source the sibling virq from the port's own `omo_ep1_dev->irq`), walk the bisect rows from the control up so a future storm can be NAMED to a step, exercise the bound on purpose at least once, and re-sample the take now that page 10 is a proven home.

- **The full-reversal sprint - the 209 witness armed, the twinclose rung clears the twin, luofu-clk cross-compiles green** (`opensource/docs/phase49/gic-view.md` "ADDENDUM 15 (2026-10-05)", specs `build/tmp/inta-spec/{h2d2,credit2,twinsem,chipdeep,superfix,twinq,ladder3,ep1,twinclear,realchain,ep1fix,crgci-result,dtslint,stage2}.md`, boots `build/register-dumps/exp/{20261005-181512,182024,182537,185140}/`, verdicts `diffs/{20261005T1814Z-vtool11,20261005T1829Z-vrun11,20261005T1855Z-vrun12}`, CI commit `dff5925`, ko pins storm-close `028f9d12...` / twin-close `4e8088e8...`): four chained sessions, one question each, and each one answered. RUN 1 (storm close, ADDENDUM 14) held 3/3 boots with the fixed supervisor and measured the ladder: CONSUME retires glue bit 4 (`0x18 -> 0x08`), FWACK retires nothing (`0x18 -> 0x18`), MASKCLOSE filters bit 3 (`0x18 -> 0x10`), so the residual `0x08` is the twin copy-B bit. RUN 3 (chip-deep, offline disasm) settled three things: (a) H2D delivery is gated by the DEVICE CPU's TAKE - the take's third precondition (reading the IAR with IRQs live) is never observed, every CPSR carries I = 1 and ISACTIVER2 bit 12 stays 0, and the vendor's difference is SEQUENCING (handshake `0xcece`, ETE bring-up, release, THEN the mask lift), so `0xcece` is necessary and its sufficiency is unmeasured; (b) the old "152 moves / 0 filled" DR-ring line is VOID on both legs (moves = credit turnover; "filled" read word1 which the DR path never writes) and the real completion test is the buffer header `buf+0x0a == 0x5a5a` and `buf+4 != 0`; (c) the twin = copy B of the ctrl-rb (CA `0x40039800` = copy A + `0x800`), firmware-programmed and host-silent, and the vendor's ONLY doorbell site writes bit 3 into INTR_SET then POLLS SELF-CLEAR. RUN 4 (twin-close, `build/register-dumps/exp/20261005-185140/`, variant `vrun12` CONFIRMED with D1-D6, staged ko md5 `4e8088e8...`) delivered: (a) THE EP1/209 WITNESS ARMED - `request_irq(209, IRQF_SHARED)` `rc=0` (the sibling-probe claim fixed the earlier `rc=-19` x2), and the line caught `isr2_n=9` before its own bound of 8 (`IRQ_DISABLED_BOUND irq=209 n=9 bound=8`); (b) THE TWINCLOSE RUNG WORKS - the twin mask write CA `0x40039ae8` `0x20 -> 0x28` cleared the TWIN's status `0x08 -> 0x00` (`twin_residual=0x0`) while the glue stayed `0x18`, so the FULL quiesce = CONSUME (retires glue bit 4) + TWINCLOSE (retires the twin's bit 3) and THE COMBINED RUNG IS THE NEXT EXPERIMENT, designed by data; (c) static - copy B HAS its clear (CA `0x40039af0` = copy-A `0x2f0` + `0x800`) but NO vendor code writes it anywhere, and the copy-A clear `0x400392f0` stays forbidden because a host write of `out[5] <= 8` HUNG the endpoint (the rule's origin); (d) safety - the bound held on both lines, zero panics, pstore delta none, router healthy. RUN 2 (upstream-compile, orchestrator-verified): (a) `luofu-clk.ko` CROSS-COMPILES GREEN in CI (`gh run list` on `dff5925` = success x2, after the honest `bed58e5` fail -> block-comment fix -> success cycle), THE FIRST CROSS-BUILD OF OUR OWN DRIVER CODE; (b) the edited DTS lints PASS (dtc 1.7.2; dtb 4,506 B sha256 `732104b1818945b69100dc7ad45612360fec0c5297c6ef0ed91689297b5b3946`; errors 0, three cosmetic unit-name warnings); (c) `build/tmp/inta-spec/stage2.md` = the ranked stage-2 driver inventory (CRG -> pinctrl -> PCIe RC -> endpoint -> glue -> wifidrv) with Kconfig symbols. KNOWN AUX GAPS: the verify-node artifact gap recurred (`vrec10` and `v-run2` wrote no verdict dir; `v-chip`'s landed in the wrong dir and was relocated), and run 4's boot used `tools/finish-evidence.sh` for the first time, generating KNOBSET/cleanup/interp while the worker files (acceptance/rows/MATRIX) stayed missing (D1). QUEUE: (a) the COMBINED QUIESCE RUNG (CONSUME + TWINCLOSE in one boot) then the bounded re-enable probe; (b) the real-chain stimulus (`intapost` `0x100` hook exists, unexercised); (c) stage-2's first driver (pinctrl per `stage2.md`); (d) the device-firmware lane (fw-load path).

- **The combined quiesce + the real chain - the combo boot lands PARTIAL (only the device-consume bit remains) and the real-chain boot proves consumption without the take - the instrument's first spend** (`opensource/docs/phase49/gic-view.md` "ADDENDUM 16 (2026-10-05)", specs `build/tmp/inta-spec/{combod.md,realchain2.md}`, runners `build/tmp/wifidrv1-art/run-{combo,realchain}.sh`, verdicts `build/register-dumps/diffs/{20261005T1946Z-vtool12,20261005T1954Z-vrun13}`, submodule commit `553342d` on `omo/phase22-hccaccept` only, CI run `37365078637`): knob v8 adds rung 7 `Q_COMBO` (TWINCLOSE first, then the vendor CONSUME order), the sec.3 second-bound re-enable PROBE, and the real-chain preamble opt-in `Q_RC_PRE` (quiesce bit `0x1`, default off), +128/-24 on `lab/wifidrv1/wifidrv1.c`. BOTH intended boots are BLOCKED, not failed: no `run-combo.log`/`run-realchain.log` exists, a tree-wide grep for `rung=7|rung=COMBO|[realchain]|QUIESCED_BY_COMBO|QUIESCED_CONFIRMED` matches only `build/tmp/{combo,realchain}-selftest/` fixtures, and the newest boot on disk is still the twin-close `20261005-185140`, so `QUIESCED` is NOT ESTABLISHED and the take observation is ABSENT (a different thing from realchain2.md's device-ABSENT branch). The stale-ko discriminator worked: `verify-ko-combo.py` scored the still-staged v7 ko 57 passed / 11 failed, all eleven the v8-only features, so a combo boot on it would have been a silent `case 7` no-op. The artifact LANDED after the window (CI `37365078637` success 19:54:36Z, md5 `3f87f1e9fe5ed9666f27d1f784d34535`, vermagic `5.10.201 SMP mod_unload ARMv7`, 7/7 v8 strings, no store of `0x400392f0`/`0x40039af0`). Supervisor discipline re-derived from source: both ISRs self-disable at their bound before any MMIO, `enable_irq` exists only inside `omo_sv_probe` (sole call site the both-levels-clean branch) under the tighter second bound with both counters reset, and a re-assert is FINAL (`IRQ_LEFT_DISABLED reason=probe-rearmed`). The probe was never spent, so the second bound has still never tripped on device. Router healthy (2 wiphys, 6 interfaces, cal `[SUCC]` both bands, `OMO_OFF=0 STAGED=0`, no new pstore, stock md5 `0e530b976d5a20e87358671f1a577695`). Two skeletons left as TODOs (`20261005T1931{Z,-}toolverify{,2}`) and the superproject gitlink still points at `f12209a`. Next: fetch, verify and run the two boots against the recorded branch tables (combod.md sec.2, realchain2.md sec.5), then spend the second bound.
- **ADJUDICATION 16a/16b (2026-10-05, appended): both boots RAN and their verdicts land** (`opensource/docs/phase49/gic-view.md` "ADDENDUM 16a/16b", evidence `build/register-dumps/exp/{20261005-195626,20261005-200139}/`): the COMBO boot = **PARTIAL** - the storm refired (bound n=65/9), TWINCLOSE then CONSUME retired glue bit 4 (stat `0x18 -> 0x08`) and cleared the twin fully (`0x08 -> 0x00`), residual = the glue's copy-A bit 3 alone (the device-consume bit; `quiesced=0`, the probe not armed, no panic); the REAL-CHAIN boot = **a fourth, unenumerated combination** - the device CONSUMED the posted message (`out[0] 8 -> 0` live + `N_OU0=0`; doorbell self-cleared `rb=0`) while the take-gated interrupt path never engaged (`N_ACT=0`, `N_ISP` bit12 SET, `HPP=0x3ff`, zero ISR delta, the glue's D2H-RX bit not retired) - **mailbox consumption and interrupt dispatch are provably SEPARATE device-side paths** (the inta2 hint, now measured); the sentinel cells held (`F_SNT=0x50AA7E49`, `WIN=0xE59FF018`); pstore delta empty; the cycle closed via `tools/finish-evidence.sh` (the D6 cure's second real use).

- **The take probe - the IRQ-vector canary fires: the CPU DOES take the IRQ, the mask lifts, and the IAR names 0x1D/0x40, never 0x4c** (`opensource/docs/phase49/gic-view.md` "ADDENDUM 17 (2026-10-05)", specs `build/tmp/inta-spec/{fwprobe,takeseq,giccpu}.md`, runner `build/tmp/wifidrv1-art/run-take1.sh`, verdict `build/register-dumps/diffs/20261005T2026Z-vtool13/verdict.txt`, evidence `build/register-dumps/exp/20261005-202555/`): variant `take1` (+792/-6 vs HEAD `18bb1ab`, uncommitted) = the inta3 pads plus fwprobe.md's three sites (the IRQ-vector canary `V_SITE 0x82EFC` -> `V_MAGIC`/`V_PSR`/`V_CNT`; the two CPSR milestones `M1_SITE 0x82F4A` -> `M1_PSR`, `M2_SITE 0x8270A` -> `M2_PSR`) and giccpu.md's cell pad (`C_GRP0/C_GRP1/C_GRP2/F_BPR` + `C_SNT`); blob `build/tmp/fw-patched/take1.bin` md5 `0c681650de28488ab75fb5755684f0c7`, size 928920. One cycle, `TAKE1 RESULT: PASS`, `exp_rc=0`, 20:25:54Z -> 20:28:38Z, reusing the v8 ko of `553342d` (`3f87f1e9...`, no ko commit, no CI) with `intapost=0x100 quiesce=0x1 rung=0 qbound=64 qbound209=8`, so the take is asked under the reproduced twin storm. **MATCHED BRANCH = fwprobe.md sec.6 ROW 1, VECTOR ENTERED**: `V_MAGIC = 0xA4A4A4A4`, `V_PSR = 0x00000193` (I=1, M[4:0]=`0x13` SVC, T=1, the take signature), `V_CNT = 4` (the ISR was entered four times), and `M1_PSR = 0x20000113` (I=0) proves the handler's live `cpsie i` window actually ran. So the device CPU DOES take the interrupt and read the IAR, and the mask DOES lift at points in the boot; the flat "the CPU never takes the IRQ" reading that 16b left open on `N_ACT=0` alone is RETIRED. **THE LOAD-BEARING REFINEMENT IS IN HPPIR**: the row-1 cross-check predicted `F_ACT`/`N_ACT` bit 12 SET and `out[0]` 8 -> 0, and those DON'T agree (`N_ACT=F_ACT=0`, `N_OU0=F_OU0=0x8`); the reconciling reads are `C_GRP1`/`N_HPP`/`A_S4` = `0x0000001D` and `F_HPP` = `0x00000040`, i.e. **the HPPIR word (CA `0x40160118`) names id `0x1D` and then `0x40`, and names `0x4c` NOWHERE**, while `N_ISP`/`F_ISP` = `0x00001021` keeps bit 12 pending. The four entries serviced a higher-priority source, so `0x4c`'s dispatcher never ran and its bit stayed pending. `0x1D` is a fresh id, absent from every earlier record in the file (`fn_array[0x1D]` is a non-null default at file `0x6E84`); the twin storm preamble is the standing candidate for it, stated as an open mechanism. **SAMPLED GATES** (all alias-only, page 10, `C_SNT = 0x50AA7E49` proves the pad ran): `C_GRP0` (`0x40160114`) = 0, `C_GRP2` (`0x4016011C`) = 0, `F_BPR` (`0x40160108`) = 3 (matches the image's only writer, file `0x8305A`), `F_CTLR` (`B_D6`, `0x40160100`) = 1 (EnableGrp0 SET, no bit2/bit3 quirk), `F_PMR` (`B_D7`) = `0xF0` (above the source priority `0x50`, so no PMR block), `C_PSR` (`B_D5`) = `0x20000193` (I=1 at the drain). **SEQUENCING VERDICT (takeseq.md, refined)**: the mask is a per-CPU counter and the lift lives in the release helper's caller (`0x82730`/`0x82B7A` -> `0x826E0`), not the ETE bring-up, so our takeover never completes step 8; this run's `M2_PSR = 0` says the release guard `0x8270A` was never reached, i.e. the release body never issued this boot, exactly the predicted miss. The gate is not a stuck mask (the ISR ran) - the wall is which source the arbitration serves. **BOUNDS**: one-shot latched samples, not a trace (`V_CNT` races a nested entry, undercount <= 1); the four entries are NOT source-attributed (the vec pad fires on any firmware IRQ entry, so `V_CNT=4` counts the shared stub, and with `0x45`/`0x1D`/`0x40` in play the run doesn't say how many were `0x4c`; the HPPIR reads are what argue none were); HPPIR names the highest-priority pending id and does not by itself prove the IAR read returned it; the run's own `interp.txt` landed TODO and this block is the interpretation. **VERIFICATION**: `vtool13` CONFIRMED (selftest rc 0 with every frozen pin, two regenerations byte-identical to the staged `0c681650...`, an independent 174-check byte re-derivation `174 passed / 0 failed`, hard-rule audit clean, one non-inverting D1 note that the m2 site/pad sits 4 bytes off fwprobe.md's stale sec.3/4 numbers); run facts: `[sig]` 9/9, done marker `irq0=207 isr0=65`, window sanity `0xE59FF018`, staged `.omo-pat` == the host blob md5, stock md5 re-verified `0e530b976d5a20e87358671f1a577695`, host witness `207: 65 ... omo-drv1` / `209: 9 ... omo-drv1-ep1`, the mandatory bound tripped on both storm lines (`n=65/n=9`) with no `enable_irq` after the trip; health `WIFI=1 PLAT=1 WIPHY=2 IFACE=6 CAL_SUCC=1 OMO_OFF=0 STAGED=0 LOADER=0 RECOVER=0`, no new pstore, 2 wiphys / 6 interfaces, cal `[SUCC]` both bands. **Next (one line):** read the `IPRIORITYR` bytes for `0x4c`/`0x1D`/`0x40` (CA `0x40161400 + 4*id`) to measure the arbitration, add a per-entry IAR-id bank to attribute the four entries, and drive takeseq.md's step-8 release so `0x4c` rings with the storm quiet.

- **The upstream arm B - the second stage-2 driver lands and its CI smoke is GREEN: `lab/luofu-pinctrl`** (`opensource/docs/UPSTREAM-PORT-PLAN.md` status block, `opensource/docs/phase49/README.md` ADDENDUM 18, spec `build/tmp/inta-spec/pinctrl.md`, submodule commit `d4875e6` on `omo/phase22-hccaccept` only, CI run `37371987343`): stage-2 driver #2 (the pinctrl row of the `stage2.md` inventory, right after CRG) exists as `lab/luofu-pinctrl/{luofu-pinctrl.c,Makefile,README.md}` - a platform driver for the vendor `hsan,luofu-peri-pinctrl` (`of_match_table` + `module_platform_driver` probe/remove + `pinctrl_register`) over the geometry transcribed from `hi_kpinctrl.ko` (37 pins / 24 groups / 24 functions; lsmod use count 5; the pinned DT split is `reg=<0x14900100 0x3c 0x14940000 0x100>` mux+cfg with `reg-names = "mux" "cfg"`, `luofu-r116-pinned.dts:1270`). `set_mux` and the pinconf setters are DELIBERATE NO-OPS and the skeleton performs no register write at all, so the bootloader's mux state survives stage 2; the probe maps the two windows read-only and logs the transcribed geometry; `dt_node_to_map` stays NULL so the core falls back to `pinconf_generic_dt_node_to_map()`; the reset deassert is held back because it is a reset write. CI, both lanes: `lab-module-build.yml` (the `omo/**` lane) becomes a `fail-fast: false` matrix over `[luofu-clk, luofu-pinctrl]` with a per-module build step, `vermagic` line and `<module>-ko` artifact, and the `master`-triggered `build-load-test-module.yml` gets the matching `build luofu-pinctrl module` step, its `vermagic` line and the `luofu-pinctrl-ko` upload. **SMOKE RESULT: CI GREEN** - run `37371987343` (push, head `d4875e6`, started 2026-10-05T20:48:08Z) has job `build (luofu-pinctrl)` **success** (2026-10-05T20:54:03Z -> 20:55:34Z, every step including `show vermagic` and the artifact upload green), and the sibling `build (luofu-clk)` job is green too, so the skeleton cross-compiles against the vanilla 5.10.201 arm headers the same way `luofu-clk` did at `dff5925` - the second cross-build of our own driver code. BOUNDS: the lane has no `Module.symvers`/`vmlinux` dump, so the unresolved-symbol check is skipped and the real test stays loading the `.ko` against the vendor tree; the `.ko` was never loaded on the device and that task ran no device cycle (no device action was needed, so the serial rule was never in play). Next: the per-group pin lists, the per-pin `drv_data {reg_off, shift, func}` behind `set_mux`, the `"cfg"` bitfield map behind `pin_config_set`, then the reset deassert.

- **The arm-A take probe (take2) - the 0x4c priority flip lands but the take never moves: the IAR never names 0x4c** (`opensource/docs/phase49/gic-view.md` "ADDENDUM 18 (2026-10-05)", `opensource/docs/phase49/README.md` ADDENDUM 19, specs `build/tmp/inta-spec/{gicv2,select}.md`, runner `build/tmp/wifidrv1-art/run-take2.sh`, verdict `build/register-dumps/diffs/20261005T2101Z-vtool14/verdict.txt`, evidence `build/register-dumps/exp/20261005-210057/`): variant `take2` (blob md5 `eeeb252f20392f2b0cb861336feb6411`) = the `gicv2` IAR-source canary (the `vec` pad reads the IAR into r7 and logs the returned id, MPIDR, a 4-deep ring and the entry count) layered on take1, plus the discriminator's three priority stores (id 0x1d/0x40 -> 0xF0, id 0x4c -> 0x00) and the readback block (P_ID/P_40/P_4C/G_GRP0/N_EN0 + X_HPP/X_ISP/X_ACT/X_OU0). One cycle, `TAKE2 RESULT: PASS`, 21:00:56Z -> 21:03:41Z, the v8 ko of `553342d` (`3f87f1e9...`), bound n=65/9 both lines. THE FLIP LANDED BUT THE TAKE DID NOT MOVE: `P_4C` byte0 = `0x00` and `P_40` byte0 = `0xF0` (the stores stick), yet `X_HPP` still names `0x1D`, `X_ACT` bit12 = 0 (never acknowledged), `X_OU0` = `0x8` (never consumed), and `V2_ID`'s four samples return small ids plus the invalid `0x402`, never `0x4c`; at the send site `F_HPP = 0x4C`, so the destination is reachable and the ranking moved while the four ISR entries still did not serve it. THE 0x1D RESIDUAL HARDENED: `P_ID` byte1 reads back `0xE0` (the authored PPI byte, lower priority than 0x4c's 0x50) and HPPIR still names 0x1D while 0x4c sits at 0x00, so priority-first does not explain it; `G_GRP0` bit29 = 0 kills the group explanation (the PPI and SPIs share group 0), leaving a banked-PPI priority that is not compared as an SPI's is. BOUNDS: one shot / four entries / one boot, the flip's stores read back but not proven atomic vs the pad's read instant, and one IAR return (`0x402`) is not a valid GIC id, so this boot's per-entry ids are suspect - the flip must be re-run clean. Next: re-run with only 0x4c -> 0x00, then mask 0x1D (ISENABLER0 bit29) and 0x40 (ISENABLER2 bit0) to measure arbitration with the competitors out of the set. Health: bound held both lines, no new pstore, 2 wiphys / 6 interfaces, calibration [SUCC] both bands.
- **The tie-break (take3) - the 0x4C promotion held to the END, the 0x1D competitor-disable never landed (an emitter bug): ROW 5, the blocker stays unseparated** (`opensource/docs/phase49/gic-view.md` "ADDENDUM 19 (2026-10-05)", `opensource/docs/phase49/README.md` ADDENDUM 20, spec `build/tmp/inta-spec/tiebreak.md`, runner `build/tmp/wifidrv1-art/run-take3.sh`, verdict `build/register-dumps/diffs/20261005T2130Z-vrun16/verdict.txt` (ROW 5, 8/8 CONFIRMED), evidence `build/register-dumps/exp/20261005-212711/`): variant `take3` (blob md5 `072de986879bdbad00f339b2ad21ebd7`, the reused v8 ko `3f87f1e9...`) = take2's `selpre`/`selpost` sites with the synchronized protocol (competitor-disable `ICENABLER0/ICPENDR0` for the banked TWD PPI `0x1D` and `ICENABLER2/ICPENDR2` for `0x40`/`0x45`; `0x4C` source-disable -> priority `0x00` -> source-enable with `dsb sy`; re-ring) plus a new twelve-cell END-STATE block. The promotion LANDED and HELD (`E_P4C` byte0 `0x00`, `E_EN2` bit12 SET, `E_CTLR` RWP 0) and the `0x40`/`0x45` mask landed (`E_EN2` = `0x5000`), but the `0x1D` disable was a NO-OP: the emitter `write_ca_block()` (`tools/patch_fw_scratch.py:1779`) writes `movw r0,#0` for the mask `0x20000000` and never emits the `movt`, so `ICENABLER0`/`ICPENDR0` got `0x00000000` and `E_EN0` bit29 reads SET (`0x2000FFFF`). So the boot does NOT test `0x4C` promoted AND `0x1D` masked; it reproduces take2's out-ranking under the tighter mask - ROW 5, the pad/site fault, NAMED. The take never moved (`E_ISP` bit12 set, `E_ACT` bit12 CLEAR, `E_OU0` = `0x8`, `E_HPP` = `0x1D`, `V2_ID` = `0x00000402`, ring `0,1,2,0x402`), and the take2 prediction is now MEASURED: `E_P4C` = `0x00` with `0x4C` pending and the two SPI competitors masked still yields no `0x4C` take, so `0x4C` cannot move from priority alone, but "priority is not the comparator" STAYS BLOCKED because the source that out-ranks it, the banked PPI `0x1D`, was never removed from the ENABLED set. `E_P1D` byte1 still reads `0xE0` while `E_HPP` names `0x1D`; `E_EN2` bit14 (`0x4E`) is SET though no pad writes it (ADDENDUM 18's R3 late-writer residual); the build's own self-check passes because it counts `write_ca_block(...)` through the buggy encoder, and `vtool15`'s verdict is still an unfilled skeleton, so the take3 build was never adjudicated in writing. Bounds: one shot / four entries, the `0x402` id is this boot's suspect word, and `interp.txt` is the finish-evidence skeleton. Next: fix `write_ca_block()` (`movt r0, value>>16` when `value > 0xFFFF`) and re-run take3 unchanged - a rerun whose `E_EN0` bit29 reads CLEAR is the first boot that actually tests `tiebreak.md`'s lever. Health: bound held both lines (`207 n=65/64`, `209 n=9/8`), no new pstore, 2 wiphys / 6 interfaces, calibration `[SUCC]` both bands.
- **The separation (take4) - the emitter fix LANDED and the `0x4C` promotion HELD, yet the take still did not move: the residual is the SGI bank** (`opensource/docs/phase49/gic-view.md` "ADDENDUM 20 (2026-10-06)", `opensource/docs/phase49/README.md` ADDENDUM 21, specs `build/tmp/inta-spec/{sep.md,sginote.md,emitter.md}`, runner `build/tmp/wifidrv1-art/run-take4.sh`, verdicts `build/register-dumps/diffs/20261006T1246Z-vrun17/verdict.txt` (C1-C8 CONFIRMED) and `build/register-dumps/diffs/20261006T1243Z-vtool16/verdict.txt`, evidence `build/register-dumps/exp/20261006-124348/`): variant `take4` (blob md5 `000a26af4d7b12e84d4191ae51dbad6d`, the reused v8 ko `3f87f1e9...`, one `tools/exp.sh` cycle serial/detached, `TAKE4 RESULT: PASS`, `exp_rc=0`) = take3's program with the encoder fixed (`write_ca_block()` now emits the `movt` half for values above `0xFFFF`) plus a physical presence check. The fix is MEASURED on-device: `E_EN0` = `0x0000FFFF`, bit29 CLEAR, so the banked TWD PPI `0x1D` really LEFT the ENABLED set where take3 read `0x2000FFFF` - take3's named blocker is retired and `sep.md` rows 3/4 (mask-did-not-take / emitter-bug) are excluded. The `0x40`/`0x45` mask and the `0x4C` promotion held to the end (`E_EN2` = `0x5000`, `E_P4C` byte0 `0x00`, `E_CTLR` RWP 0), and still the take did NOT move: the IAR ring stayed SGI-owned (`V2_ID` = `0x00000402`, `& 0x3ff` = 2; ring `0,1,2,0x402`), `E_ACT` bit12 CLEAR, `E_OU0` = `0x8`, `E_ISP` bit12 SET - `0x4C` pending, never acked, never consumed. Row 1 (SEPARATED) is FALSE; rows 5/6/7/8 are excluded by the E block. With the PPI gone, `0x4C` is now the top *enabled* source (`F_HPP` = `0x4C` at the later Site F epoch), so the blocker has SHIFTED from the PPI axis to the SGI (bank) axis, exactly where `sginote.md` sec.4 pointed. One line `sep.md` sec.2 has no row for: `E_HPP` = `0x3FF` while `0x4C` is pending AND enabled - two readings fit and the capture does not separate them, a transient (nothing signalled at that instant) or a group enable gate (`E_CTLR` = `0x1`, EnableGrp1 = 0; if `0x4C` is Group 1 it is pending+enabled yet not signalled). SGI note (from `sginote.md`): ids `0..15` are SGIs raised by a core writing `GICD_SGIR` (`0x40161F00`), the ring's `0`/`1`/`2` are the standard IPI triad (wakeup / timer-broadcast / reschedule), the only SGIR writer in the image is file `0x820C0` and its cross-core raise is always SGI 1, and the CPU-interface-init callers set the SGI bank to priority byte `0x00` (`set_prio(0,0)` @`0x8305C`, `set_prio(2,0)` @`0x83070`), so any pending SGI out-ranks `0x4C` (priority `0x50`) - an SGI is not a competitor for `0x4C`, it is higher in the same queue. The SPI priority axis is exhausted; the next lever is the BANK axis (mask/quiesce SGI ids `0..6`, or re-rank bank-0 bytes `0x40161400..0x4016140F`). Bounds: one shot / four entries; the `0x402` id is still the suspect word (not a valid GIC id); `E_EN2` bit14 (`0x4E`) is SET with no pad writing it (the file `0x7edd8` late-writer residual); `E_P40` = `0xF050F050` differs from take2's `0xF050F0F0`, so the authored bytes are per-boot state and the mask evidence is `E_EN2`; `interp.txt` is the finish-evidence skeleton. Health: bound held both lines (`207 n=65/64` glue `00000011`, `209 n=9/8`), no new pstore, 2 wiphys / 6 interfaces, calibration `[SUCC]` both bands, no `.omo-pat`/`.omo-off` leftovers. Next: move to the bank axis - quiesce the SGI bank rather than write another SPI-priority byte, and sample `GICD_IGROUPR` for the SPI bank to separate the `E_HPP` = `0x3FF` residual.
- **The bracket (take5) - the instrument is built and verified, the boot never ran: NO-SAMPLE, a harness/run failure** (`opensource/docs/phase49/gic-view.md` ADDENDUM 21, `opensource/docs/phase49/README.md` ADDENDUM 22, specs `build/tmp/inta-spec/{bracket.md,brk3.md,sgi3.md}`, runner `build/tmp/wifidrv1-art/run-take5.sh`, hook `build/tmp/wifidrv1-art/take5-capture.hook`, verifier `build/tmp/wifidrv1-art/take5-verify.py`, verdicts `build/register-dumps/diffs/20261006T1342Z-vtool17/verdict.txt` (instrument, CONFIRMED) and `build/register-dumps/diffs/20261006T1353Z-vrun18/verdict.txt` (boot, NO-SAMPLE); evidence: NONE, the dir `build/register-dumps/exp/20261006-134012/` was never created). THE INSTRUMENT: take5 (blob `build/tmp/fw-patched/take5.bin` md5 `a5143c84a10b8e9182be70ba48a634a3`, 928920 B, size-preserving; the reused v8 ko `wifidrv1.ko` md5 `3f87f1e9fe5ed9666f27d1f784d34535`) rides take4 byte-for-byte and adds only READ-ONLY samplers: the same decisive words (`GICC_RPR` `0x40160114`, `GICD_ISPENDR0` `0x40161200`, and id `0x4C`'s group bit `GICD_IGROUPR2` `0x40161088` at the ring and the gate-fall) plus the page sentinel `0x50AA7E49` at THREE instants of one boot - `E5_*` the ring (chained after the retained `selpost_e`, cells `0x150144..0x150150`, returns to `0x86f5e`), `I5_*` the ISR's post-EOI instant (a NEW site at file `0x82f58`, entered by `bl`, re-emitting the two replaced instructions `ldr r3,[r4,#0x74]` + `mov r5,r0`, branches to `0x82f5c`, cells `0x150154..0x15015C`) and `F5_*` the `0xcece` gate's fall-through (chained after the retained Site F pad, cells `0x150160..0x15016C`, returns to `0x86f82`). `vtool17` CONFIRMED it: pins hold, two independent regenerations byte-identical, the emitted-bytes check PASS 8/8 on take5 and still REJECTS take3, every new pad read-only with NO store to a device CA, no pad or blob references a forbidden CA (`0x400392f0`/`0x40039af0`/`0x10161000`/the ack IAR `0x4016010c`/the aliased `0x40160120`/`GICD_SGIR` `0x40161f00`), and the whole take5-vs-take4 delta is 175 bytes inside the three pads, the one ISR site and the two retargeted tails, 0 outside; two spec deviations recorded (padding is only 274 B in fragments of <=76, so each instant is one 52/58-byte pad reading the decisive words instead of `bracket.md`'s 27-word block; `brk3.md`'s early site at file `0x82732` was dropped after take4 read `M2_PSR = 0x00000000`, so the post-EOI instant replaces it). THE BOOT: `run-take5.sh` -> `tools/exp.sh`, RUN_TS `20261006-134010`, 13:40:10Z to 13:52:14Z, `TAKE5 RESULT: FAIL`, `exp_rc=1`; preflight clean (staged blob == pin, ko == pin, `stock_md5=0e530b97...`, leftovers 0, freshness uptime 3260 s), the device returned at uptime 32 s and then `!! FAIL [run] device did not return fresh or experiment never finished` at `[4/7]`, no `omo-drv1: init done` line, no evidence dir (the harness's own `health.txt` write failed), and the capture gate correctly refused an older dir (`capture MISSING: no evidence dir at TS >= 20261006-134010`). So `E5_*`/`I5_*`/`F5_*` do not exist, every `brk3.md` sec.4 row is `-`/NO-SAMPLE because it guards on a sentinel, AND NO NUMBERED ROW CLOSES - the honest label is a HARNESS/RUN FAILURE (`brk3.md` row 11, extended: not even the module ran), not an arbitration result, and take4's conclusion (ADDENDUM 20) stands unchanged. Health: `wiphy=2/2 iface=6/6 cal_succ=1 omo_off=0 staged=0 loader=0`, pstore unchanged at 3 records, `stock_md5` unchanged, the leftover `/root/omo-take5-cap.txt` probed to 0; hard rules held (no write of `0x400392f0`/`0x40039af0`, no read of `0x10161000`, no host read of the ack IAR `0x4016010c`, `wifidrv1.ko` staged as named, cycle serial/detached with the bound armed). **Next:** re-run the take5 cycle (same pinned blob and ko) to get the three instants; if the stall recurs, diagnose the S99omo loader's `insmod` point before reading any cell; then read `brk3.md` sec.4 against the sentinels (the SGI window separates 'window' from 'arbitration').
- **The stuck-active (take6) - the gate 21a named is a PRIORITY-0 SOURCE HELD ACTIVE, retired by the EOI and, when the ISR doesn't run, never retired: the SGI bank and the group enable are REFUTED, `RPR` is the comparator, and the fast sampler that would NAME the source stalled at the same `[4/7]` marker the take5 bracket did** (`opensource/docs/phase49/gic-view.md` ADDENDUM 22, `opensource/docs/phase49/README.md` ADDENDUM 23, specs `build/tmp/inta-spec/{stk3.md,eoir.md,stuck.md}`, instrument verdict `build/register-dumps/diffs/20261006T1432Z-vtool18/verdict.txt` (take6 sampler CONFIRMED, C1-C8), boot log `build/tmp/wifidrv1-art/run-take6.log`). THE STATE, read straight from 21a's three-instant bracket, ONE boot (`build/register-dumps/exp/20261006-135935/capture-cmd.txt`): `E5_RPR` (the ring) = `0x00000000` (a priority-0 source is ACTIVE), `I5_RPR` (the ISR's post-EOI at file `0x82f58`) = `0x000000FF`, `F5_RPR` (the `0xcece` gate's fall-through) = `0x000000FF`; `HPPIR` tracks `RPR` exactly (`E_HPP`/`X_HPP`/`N_HPP` = `0x3FF` while `0x4C` pending+enabled+promoted, then `F_HPP` = `0x4C` the instant `RPR` idles). The take is NOT attempted-and-lost - with `RPR` = `0x00` the promoted `0x4C` fails the strict `>` test, so at the `0x00` instants it is never attempted; the instant the ISR's own EOI (file `0x82f52`) drops `RPR` to `0xFF`, the same boot reads `F_HPP` = `0x4C`. THE REFUTED ALTERNATIVES: the SGI bank cannot be the comparator at that instant (`E5_SGIP`/`I5_SGIP` = `0`, and `F5_SGIP` = `0x20000000` only at the fall-through, post-EOI), and the group enable is not the gate (`E5_GRP2` = `F5_GRP2` = `0` with `E_CTLR` = `0x1`, so EnableGrp0 covers `0x4C`); `RPR` is the comparator. THE HOLDER, a word-0 SGI/PPI: `E_ACT` = `0` at every vein (no SPI-class source active, so no SPI is the holder), and the firmware's own `set_prio` prices only SGI `0` (file `0x8305C`) and SGI `2` (`0x83070`) at `0x00` - a CANDIDATE set `{0, 2}`, not a sample, since no cell in take1..take5 reads the word-0 `GICD_ISACTIVER0` `0x40161300` bank. THE RELEASE: the epoch's exit is counter-gated - `M2_PSR` = `0x00000000` means the release guard's `0x8270A` sample never ran, so the release returned early (or was never called) and a priority-0 source can be left active across the whole forward attempt. THE INSTRUMENT: `take6` (blob md5 `18d8e2ff0eb6954aadc3ef2f24deec52`, the reused v8 ko `3f87f1e9...`) rides take4 byte-for-byte with the four redundant take5 pads dropped (their sites back to stock) and adds ONE read-only pad `pad_stk_fast` (172 B, chained after the retained E block at `0xc80a8`): `GICC_RPR` `0x40160114` x16 into `STK_0..STK_15` (`0x150170..0x1501AC`) ANDed into `STK_STICKY` (`0x1501B0`, `0` iff an `RPR` = `0x00` sample existed), plus one read of `GICD_ISACTIVER0` `0x40161300` into `STK_ACT` (`0x1501B4`) and `GICC_HPPIR` into `STK_HPP` (`0x1501B8`); no device write at all; `vtool18` CONFIRMED it (pins hold, two regenerations byte-identical, emitted-bytes 8/8 and still REJECTS take3, every store a page-10 cell, no forbidden CA). THE BOOT: `run-take6.log`, RUN_TS `20261006-143344`, 14:33:44Z, stalled at `[4/7] wait for the completion marker` with no `omo-drv1` line and no evidence dir - the SAME harness/run failure the take5 bracket met (`brk3.md` row 11 extended), so `STK_*` do not exist and the source stays a candidate. Bounds: `CA 0x40160114` = `GICC_RPR` is a GICv2 CPU-interface-convention prediction with 0 image literals, so the model rests on the `E5`/`I5`/`F5` differential, not the name; the id is a candidate from `set_prio`, never a measured read; the release-counter story is NAMED by re-derived disassembly (`0x826E0`/`0x82730`), not measured. Health: no device cycle run by this record; the take5 re-run's bound held, no new pstore, `stock_md5` unchanged, 2 wiphys / 6 interfaces, calibration `[SUCC]` both bands. **Next:** diagnose the loader's `insmod` point (the take5 stall's named open residual) before waiting on another `take6` reading; then read `STK_STICKY`/`STK_ACT` to NAME the holder, and only then build the gated `take6f` EOIR force (`GICC_EOIR` `0x40160110` of a measured id) for the capping proof.
- **The CRG forced-probe smoke #2 (crgprobe) - the driver READS the real CRG: PASS, with one non-fatal driver WARN at unload** (`build/tmp/inta-spec/crgprobe.md`, runner `build/tmp/wifidrv1-art/run-crgprobe.sh`, log `build/tmp/wifidrv1-art/run-crgprobe.log`, raw `build/tmp/wifidrv1-art/crgprobe/crgprobe-run-raw.txt`, ko md5 `b1a60c988c5dd704a500159cdc9483d2` from CI `lab-module-build`/luofu-clk): gate OK (`boot_id=fec0f09c...`, uptime 1244s, 0 leftovers, 2 wiphys, 6 interfaces, cal `[SUCC]` 2g+5g) -> one serial action `insmod force_probe=1` -> `rmmod`. `INSMOD_RC=0`; the forced body ran against the live CRG with no DT match and logged `[0x090] CRG_STATUS = 0x6a010008 (PLL cpu-lock=1 lsw-lock=1, rst_reason=4)` (lock mask `0x48000000` fully set) and `[0x100] WDT_ISTATUS = 0x00000000`, then `FORCED probe PASS: 2/2 status regs read, 0 writes`; `RMMOD_RC=0`, `LUOFU_AFTER_RMMOD=0`, `STAGED_LEFT=0`, post-health `POST_WIPHY=2 POST_IFACE=6 POST_CAL2G=1 POST_CAL5G=1 POST_LUOFU=0 POST_LEFTOVERS=0`, `boot_id` unchanged. FINDING (sec. 6 of the receipt): the synthetic `luofu-crg` platform_device has no `.release`, so `platform_device_unregister()` in `luofu_crg_exit` fires `WARNING ... drivers/base/core.c:1836 device_release` on every unload (traces at uptime 1066.49 and 1248.14; taint gains `W`) - synchronous in `rmmod` but after the device-side dmesg snapshot, so the runner's checks missed it; fix is a driver-source change (fdev `.dev.release` / `platform_device_register_simple`), needs a CI rebuild, out of scope here. Cross-check note: the vendor `hsan,rstinfo` node exposes no `reset_reason` attribute (`hi_krstinfo.ko` not loaded), so the consistency check is the two reads (0x6a090008 @15:07Z / 0x6a010008 @15:10Z) agreeing on lock bits 30/27 and `rst_reason=4`.
- **The upstream arm B - the PCIe RC design lands (spec + DT node, no code yet): stage-2 row 3 gets a register-level design and `luofu-pcie` enters the tree** (`build/tmp/inta-spec/pcierc.md`, `opensource/docs/UPSTREAM-PORT-PLAN.md` status block, submodule `fa11572` on `omo/phase22-hccaccept`): task `st_01a111be` read the vendor `hi_pcie.ko` (full `.symtab`, disassembled with `lab/ko_disasm.py`) against the pinned DTS and fixed the RC's shape - the five-window layout (`dbi 0x10160000`, `misc 0x10161000` WRITE-ONLY, `cfg 0x50000000`, `mem 0x40000000`, `io 0x48000000`; RC1 `+0x4000`/`+0x18000000`), the verbatim `iatu_rc` table (3 viewports: CFG0 `0x50000000`, MEM `0x40000000`, IO `0x48000000`, all host==bus) written to `DBI+0x900+0x200*i`, and the 14-step `hi_pcie_probe @0xb8c` init order (clk_bulk_enable -> 4 `reset_control_deassert` -> `misc+0x00 = 0x40000000` RC mode -> iATU -> endpoint power -> `DBI+0x04 = 7` -> LTSSM; per-step vendor offsets recorded). THE DECISION: a from-scratch host controller (`pci_scan_root_bus_bridge` + our `pci_ops` over the dedicated 4 KB `cfg` window), NOT a drop-in DWC core, because the `misc` block is non-DWC and the vendor config path is not ECAM - reuse DWC only for the iATU register LAYOUT and `pcie-histb.c` for the SHAPE. Three port-only constraints: clocks/resets from `&crg`, link-up polled via `DBI+0x82`/`cfg+0x82` DL_ACTIVE instead of the read-forbidden `misc+0x100`, and `misc` WRITES only (never reads). THE LANDED ARTIFACT: `opensource/docs/soc/luofu-r116.dts` already carries `pcie0: pcie@10160000 { compatible = "hisilicon,luofu-pcie"; ... status = "disabled"; }` with the five `reg`/`reg-names`, `interrupts = <0 0x3b 4> (radm, SPI 59) / <0 0x45 4> (linkdown, SPI 69)`, `<&crg LUOFU_CLK_PCIE0>`, the four `&crg 0x34 0xc..0xf` resets and the never-read `misc` note (committed at `fa11572`); the `pcie1` sibling and the `iatu_rc`/`iatu_ep`/`pcie-gpios` properties stay spec-only (`pcierc.md` sec.3). NO CODE, NO CI: there is no `lab/luofu-pcie/`, no `luofu-pcie-ko` artifact and no workflow matrix entry, and the design was not adjudicated in writing beyond the receipt - the next step is the skeleton (misc-write-only, log the transcribed `iatu_rc`, no DT match on a vendor boot so no probe runs, same shape as `luofu-clk`), then the CI lane, then the no-DT-match window-prove lab module. Hard rules honoured in the design: never write CA `0x400392f0`, never read the RC `misc` `0x10161000`, host-side IAR `0x4016010c` reads forbidden, ko staged as `wifidrv1.ko`.
- **The take6f capstone (take6f) - the vendor stack took the endpoint, so the ranked EOIR force was never spent: NO-SAMPLE BY CONSTRUCTION, and the harness now FAILs closed** (`opensource/docs/phase49/gic-view.md` ADDENDUM 23, `opensource/docs/phase49/README.md` ADDENDUM 25, specs `build/tmp/inta-spec/{stk3.md,eoir.md,stuck.md,layoutdiff.md}`, runner `build/tmp/wifidrv1-art/run-take6f.sh`, hook `build/tmp/wifidrv1-art/take6f-capture.hook`, instrument verdict `build/register-dumps/diffs/20261006T1519Z-vtool19/verdict.txt` (CONFIRMED, C1-C6), boot verdict `build/register-dumps/diffs/20261006T1523Z-vrun20/verdict.txt` (NO-SAMPLE BY CONSTRUCTION), evidence `build/register-dumps/exp/20261006-152035/`). THE BUILD: `take6f.bin` (blob md5 `2c1ae79f892e922d0df0583f87fb1a2c`, 928920 B, the reused v8 ko `3f87f1e9fe5ed9666f27d1f784d34535`, no ko commit, no CI) = take6's retained read-only frame + the read-only fast sampler `pad_stk_fast` (172 B @ `0xc8348`: `GICC_RPR` x16 + the ANDS sticky + the word-0 active bank `GICD_ISACTIVER0` `0x40161300` + `HPPIR` + the sentinel) + the ranked 66-B EOIR force `pad_stk_eoir` (54 B as built + the 12-B post-force `HPPIR` deposit @ `0xcb8e4`: `GICC_EOIR` `0x40160110 <= 0x2`, `dsb sy`, then `RPR`/`HPPIR` re-read into `STK_RPR1`/`STK_HPP1`, `b.w 0x86f5e`). `vtool19` CONFIRMED it: `--selftest` PASS with both frozen pins (take6 `18d8e2ff...`, take6f `2c1ae79f...`), `--check-emitted take6f.bin` 10/10 PASS (take6 8/8; the EOIR op and the HPPIR deposit ABSENT from take6), two regenerations byte-identical to the shipped blob, both pads capstone-verified against `layoutdiff.md` sec.4, and the runner's gate fails CLOSED (no `--eoir-id` -> rc 1, a mismatched id -> rc 1, no device contact; the builder refuses a bare take6f rc 2). THE BOOT: `EOIR_ID=0x2 run-take6f.sh` over `tools/exp.sh` (RUN_TS `20261006-152033`, `TAKE6F RESULT: FAIL`, `exp_rc=1`) - the instance the vendor's PCIe glue took BOTH endpoints (`[PCIEL]request pcie intx irq 209/207 succ`) and uploaded its own image at 13.16 s, so our module logged `hardware attach failed (no endpoint bound) - continuing without it` and `init done ... regs=absent irq0=0 isr0=0` (no `BAR0 base=0x40000000`, no `request_irq(207) rc=0`, the 207 line stayed `hisi_pci_intx`). With no BAR0 the `.omo-pat` blob (staged md5 `2c1ae79f...`, MATCH) was never read into the chip, so NO pad (fast sampler, E block, or EOIR force) executed: every cell `0x00000000` and every sentinel (`STK_SNT`/`E_SNT`/`X_SNT`/`N_SNT`/`B_P3`/`B_P4`/`F_SNT`/`C_SNT`) reads `0x0`, none `0x50aa7e49`, while `WIN 0xE59FF018` and `S2+4 0x40103EB8 = 0x00104427` prove the window is alive (`0x0` = pad did not run, not dead window). `vrun20` labels the boot NO-SAMPLE BY CONSTRUCTION (`layoutdiff.md` row 6): the take6f hypothesis (the capping proof BY TRANSITION: `RPR` `0x00->0xFF`, then `HPPIR` `0x3FF->0x4C`) stays UNTESTED, `STK_ACT` is still unread, and the third pad-less boot of the take class fails upstream of the pad layout (`layoutdiff.md` sec.2: no take6-vs-take4 structural defect; the cause was the vendor stack resident on the other `rootfs` slot, `rootfsa` vs take4/take5's `rootfsb`). THE ONE LINE THAT MOVED: the HARNESS. The take6f runner's `EXP_DONE_CMD` now requires the instrument's own execution lines (`BAR0 base=0x40000000`, the `.omo-pat size=928920 bytes` upload, `request_irq(207, IRQF_SHARED) rc=0`) and forbids `regs=absent`/`INI_DRV:D]ini_cfg_init`, so a vendor-stack boot FAILs closed (`INSTRUMENT_GATE=NOT_HELD_NO_SAMPLE_BY_CONSTRUCTION`) while keeping the all-zero cells - the first boot to prove the gate is the verdict, not the read. Hard rules held: no write of CA `0x400392f0`/`0x40039af0`, no read of `0x10161000` or the ack IAR `0x4016010c`/`0x40160120`, `GICD_SGIR 0x40161f00` never read, ko staged as `wifidrv1.ko`, cycle serial/detached with the HARD BOUND armed (inert: no endpoint, no IRQ, `[qsv] no message window - supervisor skipped`), recover after; router healthy (2 wiphys / 6 interfaces / cal `[SUCC]` both bands, 0 `.omo-off`, 3 pstore records, no crash). Next: get the vendor stack out of the boot's way (the `.omo-off` hide vs the actual `rootfs` slot) and re-run the SAME take6f to read `STK_ACT`; wire the `--eoir-id` ONLY once the id is measured.
- **The upstream arm B2 - the PCIe RC skeleton lands, goes CI-green, and its forced smoke PANICS at one misaligned read: the RC is live with the link UP, but the run is a FAILURE and the fix is a register-table defect** (`build/tmp/inta-spec/{pciskel.md,pciskel-ci.md,pciskel-smoke.md}`, `opensource/docs/UPSTREAM-PORT-PLAN.md` status block, submodule `5079cc1` on `omo/phase22-hccaccept`): the read-only `lab/luofu-pcie/` skeleton (maps `dbi`+`cfg` READ-ONLY, `misc 0x10161000` NOT mapped, ZERO writes - the read-only bar proved at the INSTRUCTION level because `readl()` inlines to a plain `ldr`, 49 stores none a window base) cross-builds GREEN on the first push (workflow `lab-module-build`, run `37488653830`, success, `vermagic=5.10.201 mod_unload ARMv7`, artifact `luofu-pcie-ko` md5 `503f9580c29f555a47755ca93e61feeb`), and the smoke runner `build/tmp/wifidrv1-art/run-pciskel.sh` ships with a fail-closed gate + self-test. THE SMOKE (evidence `build/register-dumps/exp/20261006T1540Z-pciskel/`, pstore `dmesg-pstore_blk-2` "Panic#2 Part1"): gate CLEAN (`boot_id=518f5479-81d7-4e59-8955-0e08e661a1bc`, uptime 1071s, pat=0, 0 leftovers, 2 wiphys, 6 ifaces, cal `[SUCC]` 2g+5g, stock md5 pinned), one serial `insmod force_probe=1` - the probe DID read the live vendor-owned RC with 0 writes, then took an **imprecise external abort at the misaligned Link Status read `dbi+0x082`** (`readl()` at a 2-byte-aligned PCIe-cap register; the fault address `0xc800a082` = the mapped DBI base +0x82), so the kernel panic'd and the box rebooted (NEW `boot_id=7afb325f-9dfe-43f4-8ca6-e1eae66c5585`, router healthy). Values: the DBI IS live PCI config space with the link UP (`dbi+0x004` = `0x00100007`, Command=0x7 = the vendor's write; the aligned `dbi+0x080` word carries `Link Status = 0x7012` = **DL_ACTIVE bit 13 set**, 2.5 GT/s x1 = the `pcierc.md` sec 4b safe link-up witness), while everything at/past `dbi+0x082` (the iATU readback `0x900+`, the `cfg` inventory) was never reached. Fix for a rerun: `readw()` for the 16-bit cap regs (`0x082`; `0x07c`/`0x080` are Link Capabilities / Link Control in the PCIe cap layout), re-pin the `0x080` predictor (ASPM off -> `0x0`, so `expect 0x3` is a BAD PREDICTION - the `match=NO` is a lost prediction, not a lost measurement), and take link status from the aligned `0x080` upper half or the `cfg` copy; do NOT re-run the `503f9580...` ko, it panics deterministically. The defect is the skeleton's register TABLE, not the RC design. Hard rules held: no read of `0x10161000`, no host read of the IAR `0x4016010c`, no write of CA `0x400392f0`; ko staged ALWAYS as `wifidrv1.ko`; the reboot gated on a NEW `boot_id`; push authorization respected (submodule `omo/phase22-hccaccept` only, never `master`).
- **The take6f capstone RE-RUN (take6f) - the instrument RAN: the takeover bound the endpoint, the sampler NAMED the stuck id as SGI 2, the EOIR force HALF-LANDED (`RPR 0x00 -> 0xFF`), and the gate refused the wrong image slot (GATE-REFUSED, not NO-SAMPLE)** (`opensource/docs/phase49/gic-view.md` "ADDENDUM 24 (2026-10-06): the take6f capstone, RE-RUN", `opensource/docs/phase49/README.md` ADDENDUM 26, specs `build/tmp/inta-spec/{race.md,stk3.md,eoir.md,stuck.md,layoutdiff.md}`, runner `build/tmp/wifidrv1-art/run-take6f.sh`, hook `build/tmp/wifidrv1-art/take6f-capture.hook`, boot verdict `build/register-dumps/diffs/20261006T1557Z-vrun21/verdict.txt`, runner verdict `build/register-dumps/diffs/20261006T1545Z-vtool20/verdict.txt` (CONFIRMED), evidence `build/register-dumps/exp/20261006-154734/`). The SECOND take6f boot, under the `race.md` sec.5 mitigation: `HIDE_MOVED=2` hid the vendor loader's literal path, so no `hi5622v100_{plat,wifi}` loaded, OUR module bound `59e7:0005` (`request_irq(207, IRQF_SHARED) rc=0`, `BAR0 base=0x40000000`, the 928 920 B `.omo-pat` uploaded), and every active pad deposited its `0x50AA7E49` sentinel (`STK_SNT`, `E_SNT`, `F_SNT`, `B_P3`, `B_P4`, `C_SNT`). THE NAMING: the 16 `GICC_RPR` samples `STK_0..STK_15 = 0x00000000` (16/16), `STK_STICKY = 0x00000000`, `STK_ACT` (`GICD_ISACTIVER0` `0x40161300` w0) = `0x00000004` -> with the sticky zero the set bit NAMES the priority-0 holder, **SGI 2 (id `0x2`)**; the same boot's v2 IAR ring agrees (`V2_RING0/1/2/3 = 0,1,2,0x402`, `V2_ID = 0x00000402`), and `STK_HPP = 0x3FF` at `RPR = 0x00` is the model (`0x4C` pending, `E_ISP = 0x1021`, not signalable while a priority-0 source runs). THE FORCE: fired with the id the SAME boot had named (`0x2`), retiring a genuinely ACTIVE interrupt and DROPPING `RPR` (`STK_RPR1 = 0x000000FF` against `STK_15 = 0x00000000`, the capping proof's first half BY TRANSITION); the second half did not land inside the pad (`STK_HPP1 = 0x3FF`) but is one site over in the SAME boot (`F_HPP = 0x0000004C` with `F_ISP = 0x1021`, `F_ACT = 0x0`), so it is HALF, not MISSED. THE REFUSAL: the cycle boot attached `mtd13 "rootfsa"` (stock 2.4.15, from a sibling lane's crash-reboot) instead of `mtd14 "rootfsb"`, so the runner's image gate refused it (`INSTRUMENT_GATE=NOT_HELD_WRONG_IMAGE_SLOT`, `TAKE6F RESULT: FAIL`); the cells are a GATE-REFUSED READ, the first complete take6/take6f reading of the arc, and the take6f hypothesis moves from UNTESTED to MEASURED-BUT-UNCERTIFIED. The retained take4 frame still reads as take5 left it (`E_EN0=0xFFFF`, `E_EN2=0x5000`, `E_P4C=0xF050F000`, `E_CTLR=0x1`); the mandatory bound armed and hit with no residue (`IRQ_DISABLED_BOUND irq=207 n=65 bound=64`, `irq=209 n=9 bound=8`, `SUPERVISOR DONE quiesced=0 state=IDLE`). Health: `WIPHY=2 IFACE=6 CAL_SUCC=1 OMO_OFF=0 STAGED=0 LOADER=0 RECOVER=0`, stock md5 `0e530b976d5a20e87358671f1a577695` unchanged, no new pstore, boot_id moved (pre `7afb325f-...` -> post `e8e60346-...`). Hard rules held: no read of `0x10161000`, no host read of the IAR `0x4016010c`, no write of CA `0x400392f0`/`0x40039af0`; the only device write is the single `GICC_EOIR 0x2` store; ko staged ALWAYS as `wifidrv1.ko`; no reboot outside the cycle. NEXT: restore slot B (`race.md` sec.6) and re-run the SAME take6f to certify the naming and the force; the builder already refuses a bare or mismatched `--eoir-id`, so a wrong-id force cannot be spent by accident.
- **The official take6f capstone - the SLOT GATE lands (the preflight now REFUSES a wrong-slot boot before anything is armed), the boot-id-gated reboot does NOT move the slot, and the SGI-2 naming plus the half-force stay MEASURED-BUT-UNCERTIFIED pending a `rootfsb` boot** (`opensource/docs/phase49/gic-view.md` "ADDENDUM 25 (2026-10-07): the official take6f capstone", `opensource/docs/phase49/README.md` ADDENDUM 27, specs `build/tmp/inta-spec/{slotgate.md,race.md}`, runner `build/tmp/wifidrv1-art/run-take6f.sh` md5 `41272389eb340815f0397230de1183f5`, tool verdict `build/register-dumps/diffs/20261007T0044Z-vtool21/verdict.txt` (slot gate CONFIRMED, 7 claims), boot verdict `build/register-dumps/diffs/20261007T0050Z-vrun22/verdict.txt` (the ADDENDUM-24 re-run, C1-C8 CONFIRMED, branch T6-1), slot-evidence `build/register-dumps/exp/20261007-004820-slotrefusal/{slotgate-refusal.txt,reboot-attempt.log,bootflag-mechanism-and-health.txt}`). THE GATE (built, verified, and reachable): a block inside `EXP_PREFLIGHT_CMD`, which `tools/exp.sh` runs at `[0/7]` before the watchdog is armed and before anything is staged, keying on `/sys/class/ubi/ubi0/mtd_num` + that `mtdN`'s name in `/proc/mtd` (`13` -> `rootfsa` stock 2.4.15, `14` -> `rootfsb` custom 2.5.24) and cross-checking the boot's own `ubi0: attached mtd1[34]` dmesg line, with four refuse arms (unidentifiable / ident-conflict / wrong-image-slot / the pre-existing literal-path arm); `vtool21` drove all 7 decision arms and proved a refusal costs ZERO device contact (shimmed `ssh` -> `ssh_calls=0`), and re-derived the identification independently, rejecting `/proc/cmdline` (no `root=` token) and `boot_reg` (volatile inside a boot). THE LIVE REFUSAL (exact, byte-for-byte the runner's own string run read-only): `preflight booted_slot=mtd13 name=rootfsa dmesg_attach=13 rom=/dev/ubiblock0_0` then `PREFLIGHT_FAIL_wrong_image_slot: booted_slot=mtd13:rootfsa want=mtd14:rootfsb (the CUSTOM image)`, `PREFLIGHT_RC=1`. THE REFUTED REMEDY: the one permitted boot-id-gated reboot was taken and MOVED the id (`e8e60346-...` -> `f47bbc77-...`, uptime reset, box healthy) yet the box came back on `mtd13 "rootfsa"` again; the reason is now measured, not guessed - `fw_printenv` shows `bootcmd=mtd read kernel${bootflag} ${loadaddr};bootfip ${loadaddr}` with `bootflag=a` (u-boot loads `kernela` -> slot A every boot), and the in-boot `/sys/devices/platform/sysenv/boot_reg` (reads `10`) is OVERWRITTEN by the sysenv driver at ~16 s on BOTH slots, which is why `race.md`'s "0x10 -> rootfsb" map was a coincidence; moving to slot B needs `bootflag=b` (the B env block into mtd3+mtd4, `build/custom/FLASH-PLAN.md` "Slot switch recipe"), a flash/env mutation that was raised as a decision, NOT taken (the task's hard rule is ABORT on `mtd13/rootfsa`). THE STANDING RESULT: no new cells were added, so ADDENDUM 24's readings stand unchanged - `STK_STICKY = 0x00` with `STK_ACT = 0x00000004` names **SGI 2 (id `0x2`)**, and the ranked EOIR force dropped the running priority (`STK_RPR1 = 0xFF` against `STK_15 = 0x00`) with its second half one site over (`STK_HPP1 = 0x3FF`, `F_HPP = 0x4C`), all from the GATE-REFUSED boot, hence MEASURED-BUT-UNCERTIFIED; the certification is a `rootfsb` boot that re-runs the SAME `take6f` sealed with `--eoir-id 0x2` (the builder already refuses a bare or mismatched id). NOTE: `build/register-dumps/diffs/20261007T0051Z-vrunB4/verdict.txt` is a minted skeleton with no findings filed, so nothing is claimed from it. Hard rules held: no write of CA `0x400392f0`/`0x40039af0`, no read of `0x10161000`, no host read of the ack IAR `0x4016010c`; NO device cycle ran this session (so the mandatory bound was not spent) and the only device mutation was the boot-id-gated reboot; ko not staged (nothing staged); no commit, no push. Health: `WIPHY=2 IFACE=6 CAL2G=1 CAL5G=1`, `PAT=0 OMO_OFF=0 WIFIDRV1=0`, stock md5 `0e530b976d5a20e87358671f1a577695` unchanged, no new pstore, boot_id `f47bbc77-...` on `mtd13`. NEXT: flash `bootflag=b` (its own gate + its own dumps) and reboot, confirm `ubi0: attached mtd14 (name "rootfsb"`, then re-run the SAME take6f and seal it with the measured id.

- **The upstream arm B3 - the RC probe's run is a GATE-REFUSED on the image slot, and the slot rule is now inside the runner; the full read set incl. the Link Status stays unspent** (`build/tmp/inta-spec/pciskel-smoke2.md`, raw `build/tmp/wifidrv1-art/pciskel2/{_bootB3-gate-run.log,RESULT.txt,_bootB3-dryrun.txt}`, `opensource/docs/UPSTREAM-PORT-PLAN.md` status block, task `st_01a113d1`): the width-fixed `pciskel2` skeleton (ko md5 `51376f7608d6e5d60b0bb6fe09eb068e`, CI run `37553187016`, submodule `6e4cc73` on `omo/phase22-hccaccept` only) reached the `insmod force_probe=1` lane with `SELFTEST PASS` (A-F), then STOPPED at THE SLOT CHECK before any mutation - `GATE FAILED: SLOT(want=mtd14:rootfsb got=mtd13:rootfsa)`, `boot_id=f47bbc77...`, uptime 335 s, `slot=mtd13:rootfsa (rom=/dev/ubiblock0_0 dmesg_attach=13)`, cross-checked three ways (`/sys/class/ubi/ubi0/mtd_num`=13, `/proc/mtd` mtd13=`rootfsa`, boot dmesg `ubi0: attached mtd13`). The device was NOT touched (nothing staged, no insmod, no rmmod, no reboot) and the health half was GREEN at the same instant (0 `.omo-pat`, 0 `.omo-off`, 0 leftovers, `luofu_pcie`/`wifidrv1` absent, `hi_pcie` + vendor pair loaded, 2 wiphys, 6 ifaces, cal `[SUCC]` 2g+5g, `STOCK_MD5` at the pin): the refusal is the slot alone. FINDING (2nd observation, after `race.md` sec.6): a boot-id-gated reboot does NOT flip the slot - the sibling lane `st_01a113cf` rebooted 00:42:54Z (`boot_id` `e8e60346` -> `f47bbc77`) and the box returned on `NEW_MTD_NUM=13 rootfsa`, `NEW_ATTACH=mtd13`, `boot_reg=10`. The gate now lives in `run-pciskel.sh` (line 167ff + selftest F): `slot_fail()` demands `mtd_num`=14 + the `/proc/mtd` name `rootfsb` + an agreeing dmesg attach, ABORTs on `mtd13`/`rootfsa`, an empty `mtd_num` or an ident conflict, and ARM-A seriality re-reads up to 12x10 s = 120 s while a cycle marker is present (never a 2nd device action). THE READ SET the probe will deliver (fixed by `pciskel2`, unspent on the device): `readw()` on the 16-bit cap registers (the misaligned `readl` at `dbi+0x082` was the v1 external abort), the whole DBI + `cfg` inventory through one width-aware accessor, and the **Link Status** at `dbi+0x082`/`cfg+0x082` (`expect 0x2000 mask 0x2000` = DL_ACTIVE), with `cfg+0x000` re-pinned to `0x000059e7 mask 0x0000ffff` and `dbi+0x07c` correctly W32 `Link Capabilities` - proven at the byte and instruction level (the decoded `.rodata` tables, 5x `ldrh` in the inlined accessor, store census: no MMIO store). UNBLOCK: a flash/env lever with its own gate, not a reboot - restore slot B per `build/custom/FLASH-PLAN.md` "Slot switch recipe" (B env block to mtd3+mtd4 + the selector in `/sys/devices/platform/sysenv/boot_reg`), reboot, confirm `attached mtd14`, then `bash build/tmp/wifidrv1-art/run-pciskel.sh`. Hard rules held: no write of CA `0x400392f0`, no read/map of `0x10161000`, no host read of the IAR `0x4016010c`, serial + gate-checked, ko staged ALWAYS as `wifidrv1.ko`, router left healthy. ASSUMPTION carried: the brief's GATE names THE SLOT CHECK, so it was applied literally instead of probing the read-only, slot-agnostic module on the stock image.

- **The vrec20 record verification - ADDENDUM 25's official take6f capstone is CONFIRMED as recorded: the slot gate, the live refusal, and the reboot-lever refutation all hold, and the SGI-2 naming plus the half-force stay MEASURED-BUT-UNCERTIFIED** (verdict `build/register-dumps/diffs/20261007T0053Z-vrec20/verdict.txt`, task `st_01a113da`; read-back source `opensource/docs/phase49/gic-view.md` "ADDENDUM 25 (2026-10-07): the official take6f capstone", `opensource/docs/phase49/README.md` ADDENDUM 27, `mem-entries.md`): one ADDENDUM-25 record verifier, READ-ONLY and HOST-ONLY (no ssh, no devmem, no device cycle, no commit, no push). C1-C7 CONFIRMED with nothing inverting a load-bearing claim: (1) the SLOT GATE lands in `build/tmp/wifidrv1-art/run-take6f.sh` (md5 `41272389eb340815f0397230de1183f5`, 37 869 B) as a block inside `EXP_PREFLIGHT_CMD` at `tools/exp.sh` `[0/7]`, before the watchdog and before staging, keying on `/sys/class/ubi/ubi0/mtd_num` + the `/proc/mtd` name + the boot's own `ubi0: attached mtd1[34]` line, with four refuse arms; (2) the LIVE REFUSAL is exact and byte-for-byte the runner's own string (`preflight booted_slot=mtd13 name=rootfsa dmesg_attach=13 rom=/dev/ubiblock0_0` then `PREFLIGHT_FAIL_wrong_image_slot: booted_slot=mtd13:rootfsa want=mtd14:rootfsb (the CUSTOM image)`, `PREFLIGHT_RC=1`), corroborated against `build/register-dumps/exp/20261007-004820-slotrefusal/slotgate-refusal.txt`; (3) THE REBOOT LEVER REFUTES ITSELF - the one boot-id-gated reboot moved the id (`e8e60346-...` -> `f47bbc77-...`) yet returned to `mtd13 "rootfsa"`, and `fw_printenv` names `bootflag=a` as the lever, the in-boot `boot_reg` (`10`) a red herring overwritten by the sysenv driver at ~16 s on BOTH slots; (4) NO NEW CELLS - every quoted register value is ADDENDUM 24's from the GATE-REFUSED boot `build/register-dumps/exp/20261006-154734/`, so `STK_STICKY = 0x00000000` + `STK_ACT = 0x00000004` (SGI 2 / id `0x2`) and the force's RPR drop (`STK_RPR1 = 0x000000FF` vs `STK_15 = 0x00000000`, second half `STK_HPP1 = 0x3FF` / `F_HPP = 0x4C`) stay MEASURED-BUT-UNCERTIFIED, the certification being a `rootfsb` boot sealed with `--eoir-id 0x2`; (5) the pointers exist and agree (vtool21 slot gate CONFIRMED, vrun22 boot GATE-REFUSED/T6-1, vrunB4 an empty skeleton claimed from by nothing). Bounds carried: the PASS arm is a fixture, only the REFUSE arm is a live read; `bootflag=a` is read via `fw_printenv` and the write path (mtd3/mtd4) was NOT exercised; the reboot is evidence of a negative, not proof no reboot ever could. Hard rules held: no write of CA `0x400392f0`/`0x40039af0`, no read of `0x10161000`, no host read of the ack IAR `0x4016010c`, NO device cycle run (the bound was not spent), no reboot, nothing staged, no commit, no push; the router stays as the addendum left it (`WIPHY=2 IFACE=6 CAL2G=1 CAL5G=1`, `PAT=0 OMO_OFF=0 WIFIDRV1=0`, stock md5 `0e530b976d5a20e87358671f1a577695`, boot_id `f47bbc77-...` on `mtd13`). NEXT: flash `bootflag=b` (its own gate + its own dumps), reboot, confirm `ubi0: attached mtd14 (name "rootfsb"`, then re-run the SAME `take6f` sealed with `--eoir-id 0x2` to certify the naming and the force.

- **The upstream arm B4 - the RC inventory is COMPLETE: the aligned-dword fix WORKS ON THE DEVICE, both RCs' full DBI+CFG inventories ran with NO FAULT and a clean unload, and the read that killed both prior kos now RETURNS** (`build/tmp/inta-spec/pciskel-smoke3.md`, `build/tmp/wifidrv1-art/pciskel3/{README.md,RESULT.txt,KO.md5,SELFTEST.txt,run-pciskel.log,pciskel-dmesg.txt,pciskel-post-raw.txt}`, `opensource/docs/UPSTREAM-PORT-PLAN.md` status block, verdict `build/register-dumps/diffs/20261007T0135Z-vrunB5/verdict.txt` (ALL THREE CLAIMS CONFIRMED), task `st_01a11400`): the fix is submodule commit `c35af1a` on `omo/phase22-hccaccept` (CI `lab-module-build` run `37556699784` completed/success, headSha `c35af1a7...` == the tracked submodule HEAD == origin), ko md5 `976a706a3184bdf32fd63b858cd67315`, and it is the CONCLUSIONS of the width theory being WRONG: the v2 `readw()` ko (`51376f76...`) re-crashed at the SAME RC0 `dbi+0x082` address (`0xc800a082`) on an `ldrh`, so the DBI/CFG window answers only 4-byte-ALIGNED accesses - `luofu_pcie_read()` now does ONE `readl(base + (off & ~3u))`, shifts by `(off & 3u) * 8` and masks to the field width, with `readl()` again the module's ONLY MMIO op (proved at the instruction level: `bic r0, r3, #3`, a 32-bit `ldr` + `dsb sy` for every MMIO field, every `ldrh`/`ldrb` a fixed table-row read, no write token - `_ko-bar.txt` KO BAR: PASS, and the two live pstore records `_ko-bar.txt`/`pstore-blk-2-v1.txt`/`pstore-blk-0-v3.txt` name both crashes). THE RUN (the gate ADMITTED it this time - `GATE OK: SLOT=mtd14:rootfsb`, `boot_id=131068c7-45e4-4480-a1c1-3f64e2ff8e21`, uptime 1377 s, 2 wiphys / 6 ifaces / cal `[SUCC]` 2g+5g / 0 leftovers; host 2026-10-07T01:34:07Z -> 01:34:15Z; ONE serial `insmod force_probe=1` -> `rmmod`; ko staged AS `/tmp/wifidrv1.ko`): BOTH RCs ran their FULL DBI + `cfg` inventories to `FORCED probe PASS: dbi 3 predicted regs matched, cfg 4 matched, 0 writes` with NO kernel fault anywhere, and THE HEADLINE is the register both prior kos external-aborted on (imprecise abort `0x1406`) now returning a VALUE - `rc0 dbi+0x082 = 0x7012 match=YES` and `rc1 dbi+0x082 = 0x7012 match=YES` (`DL_ACTIVE` bit 13 SET, `link-training=1 neg-speed=2 (5GT/s)`), plus `dbi+0x000 = 0x0000`, `dbi+0x004 = 0x0007`, `dbi+0x07c = 0x734c12`, `dbi+0x080 = 0x0000` and `dbi+0x80c = 0x012c` on both. NEW LIVE VALUES: `rc1`'s DBI answers EXACTLY as `rc0`'s (identical `0x0000`/`0x0007`/`0x734c12`/`0x0000`/`0x7012`/`0x012c`), so the aligned-dword read is proven on BOTH domains and the rc1 arm `rcfix.md` flagged as "never reached live" HAS NOW RUN; the iATU selector `[0x900] = 0x00000002` with `iatu_rc[2]` `0x48000000`/`0x4fffffff` (rc0) and `0x60000000`/`0x67ffffff` (rc1), both `match=YES`; and the CFG windows no prior ko ever reached read `cfg+0x000 = 0x59e7`, `cfg+0x004 = 0x0006`, `cfg+0x008 = 0x2800000`, `cfg+0x02c = 0x19e5` on BOTH RCs, all four `match=YES`. THE ONE OPEN SPLIT, flagged not explained: both RCs' `cfg+0x082` reads `0x1012` (`DL_ACTIVE`=0, the endpoint's OWN Link Status) while the DBI's reads `0x7012` (=1) - the endpoint-side `cfg+0x080` dword is not the DBI's word, and the `match=NO` is a PREDICTOR disagreement (link still training), NOT a lost measurement or a fault. UNLOAD + STATE: `RMMOD_RC=0`, `LUOFU_AFTER_RMMOD=0`, `STAGED_LEFT=0`, `RUN_DONE`, `POST_BOOT=131068c7...` (the SAME boot id the run started on - the fix does not crash), `POST_WIPHY=2`, `POST_IFACE=6`, `POST_CAL2G=1`, `POST_CAL5G=1`, `POST_LUOFU_PCIE=0`, `POST_VENDOR_WIFI=1`, `POST_VENDOR_PLAT=1`, `POST_OMO_PAT=0`, `POST_LEFTOVERS=0`; `PCISKEL RESULT: PASS` (`RESULT.txt` = `PASS`, `SELFTEST PASS`); `STOCK_MD5 = 0e530b976d5a20e87358671f1a577695` at the pin (the verifier re-read it live). THE UNBLOCK WAS EXECUTED FIRST: the slot was restored via the record's own verified recipe (`build/custom/env-bootflag-b.bin` into BOTH env copies + `boot_reg 0x21`; the fw_setenv path is a trap - the bootloader's selector is the sysenv register) and the SAME take6f capstone boot served both halves (`gic-view.md` ADDENDUM 25a; the arm-B3 lane's literal slot check had refused `mtd13:rootfsa` an hour earlier, `diffs/20261007T0051Z-vrunB4`). BOUND: N/A, and decisively - `luofu-pcie` is a read-only status inventory (`readl()` the only MMIO op, no IRQ handler, no quiesce, no bound), so the runner's only safety controls are the GATE (device health + SLOT CHECK + arm-A seriality) and the read-only code path, both GREEN; this verifier armed nothing and ran no cycle of its own (ONE read-only health/slot probe: `MTD=14`, `WIPHY=2`, `IFACE=6`, `C2G=1`, `C5G=1`, `STOCK=0e530b97...`, `VENDOR=4`, 0 leftovers). Hard rules held: CA `0x400392f0` never written; `0x10161000` never read or mapped (the ko carries it only as a `%lx` argument); the host-side IAR `0x4016010c` never read; serial + gate-checked; ko staged ALWAYS as `wifidrv1.ko`; no commit, nothing pushed by the verifier. What remains for the stage-2 RC driver is the FROM-SCRATCH host controller itself (iATU programming, LTSSM, `cfg` accessors) - not another measurement.

- **The bank/group gate (arm A) - `RPR` is drop-able but NOT the comparator, so the residual moves to the group/bank layer: rank 1 the force's id-mismatched EOIR, rank 2 an `0x4C` GROUP stamp, rank 3 the SGI/PPI BANK, and the one-boot read set (take7) decides** (`opensource/docs/phase49/gic-view.md` ADDENDUM 26, `opensource/docs/phase49/README.md` ADDENDUM 28, specs `build/tmp/inta-spec/{bankgate.md,bg2.md}`, tasks `st_01a113ee`/`st_01a113ef`, evidence base `build/register-dumps/exp/20261007-010906/`). THE NEGATIVE: the official capstone dropped `RPR` to `0xFF` yet `STK_HPP1` stayed `0x3FF` while the SAME boot's Site F read `F_HPP = 0x4C`, so the comparator sits BELOW the `RPR` register. `GICC_HPPIR` is a THREE-WAY signature (`0x3FF` = nothing pending / the top pending's group disabled at the CPU interface / the top is Group 0 read Non-secure; ARM IHI0048), which names exactly three surviving layers, ranked: rank 1 = the force wrote a bare `0x2` to `GICC_EOIR` `0x40160110` while the last valid IAR value was `0x402` (`V2_ID`), so it ran in the spec's UNPREDICTABLE clause and left the priority-0 epoch unretired (priority dropped, interface's view not); rank 2 = an `0x4C` Group stamp against `EnableGrp1 = 0` (`GICC_CTLR = 0x1`, `GICD_CTLR = 0x1`), with the only capstone group read `G_GRP0` being the SGI bank, and every `IGROUPR` w2 read on record putting `0x4C` in Group 0 - but never at the post-force instant; rank 3 = the SGI/PPI ACTIVE bank (`STK_ACT = 0x4`, SGI 2 named). `F_HPP = 0x4C` in the same boot rules out any STATIC config gate, and the image's GIC-literal census finds NO `IGROUPR` write anywhere, so the stamp is inherited from reset. THE DESIGN (take7, nothing built): the capstone frame byte-for-byte plus the corrected EOIR `0x40160110 <= 0x402` (emitted only if a pre-read reads `RPR = 0x00` with `ISACTIVER0` bit 2 set - the pad's own self-gate) and the non-acknowledging post-force read set R1..R14 (`TG_ACT0` `0x40161300` w0 bit 2, `TG_GRP2` `0x40161088` w2 bit 12, `TG_GRP0`, the CTLR pair, `TG_TGT`, the PMR/ABPR pair, `TG_SNT`); `take7` observes, `take7f` intervenes, md5-pinned apart so observation never shares a verdict with intervention. THE BRANCH TABLE (bg2 sec.4): (1) `STK_HPP1 = 0x3FF` + `GRP_I2` bit12 `= 1` + `GRP_CTLR` bit1 `= 0` - GROUP GATE CONFIRMED; (2) `take7f` moved `0x4C` into the enabled group and the IAR read it - THE FINAL PROOF (`RPR` idle + `HPPIR = 0x4C` + the take); (3) `STK_HPP1 = 0x3FF` + group ENABLED + `GRP_I2` bit12 `= 0` - NOT GROUP, NOT RPR: THE BANK OWNS IT (next: the `.ko` `ICENABLER0/1` quiesce); (4) `GRP_PMR < 0xC0` - PMR MASK; (5) `GRP_ACT2` bit12 or the IAR names `0x4C` - TAKEN (transient); (6) `GRP_WR` read-back != written - FORCE MISSED (a build/visibility fault); (7) `E_CTLR` bit1 `= 1` while `STK_HPP1 = 0x3FF` and `GRP_I2` bit12 `= 1` - CONTRADICTION, re-measure; (8) any `GRP_*`/`STK_*` sentinel `!= 0x50AA7E49` - NO-SAMPLE. The DEFERRED levers: rank 2's group enable (`GICC_CTLR -> 0x3`) ships only on a rank-2 read, because it admits the already-pending `0x40`/`0x45`/`0x4C` (`E_ISP = 0x1021`) into the vendor ISR at once; the rank-3 bank quiesce is last because it risks the Wi-Fi doorbell (`F5_SGIP = 0x20000000`). BOUNDS: design only, no new cell (every value is the capstone's); `GICC_HPPIR = 0x3FF` is a three-way signature, never one thing; the group stamp `0x40161088` was read only in OTHER boots; `X_*` cells are NO-SAMPLE in take6-era boots; `TG_AHPP` `0x40160128` is layout-derived and must be re-verified against the spec table; take7's byte budget depends on dropping the retained `selpost_e` pad (152 B). NOTE: `bg2.md` records `bankgate.md` as absent at its read time and notes rather than fabricates it; both files exist now. NO device action: the two arm-A tasks and this record are read-only/host-only, the ko is unchanged (`3f87f1e9fe5ed9666f27d1f784d34535`, no ko commit, no CI, no push), and the router is untouched and healthy (`WIPHY=2 IFACE=6 CAL2G=1 CAL5G=1`, `PAT=0 OMO_OFF=0 WIFIDRV1=0`, stock md5 `0e530b976d5a20e87358671f1a577695`, slot B). Hard rules held: no write of CA `0x400392f0`/`0x40039af0`, no read of `0x10161000` or the ack IAR `0x4016010c`/AIAR `0x40160120`, no `GICD_SGIR` read. NEXT (one line): build take7, run the observation variant once, read `TG_GRP2`/`TG_ACT0`, then gate the rank-2 group enable on that read and the rank-3 bank quiesce last.

- **The upstream arm B5 - the arm-B RC measurement phase CLOSES: the adversarial verdict CONFIRMS all three claims, the aligned-dword read that panicked both prior kos RETURNS on BOTH RCs live, and what remains is the from-scratch host controller, not another measurement** (`build/register-dumps/diffs/20261007T0135Z-vrunB5/verdict.txt` "ALL THREE CLAIMS CONFIRMED", tasks `st_01a11400` (verifier) / `st_01a113fa` (run), report `build/tmp/inta-spec/pciskel-smoke3.md`, runner `tools/finish-evidence.sh --verdict vrunB5`). C1 the device receipts EXIST and are artifact-backed: the fixed ko md5 `976a706a3184bdf32fd63b858cd67315` ran on the LIVE RC at `mtd14:rootfsb` (`GATE OK: SLOT=mtd14:rootfsb`, `boot_id=131068c7-45e4-4480-a1c1-3f64e2ff8e21`, 2026-10-07T01:34:07Z -> 01:34:15Z, one serial `insmod force_probe=1` -> `rmmod`, staged AS `/tmp/wifidrv1.ko`) with NO fault - both RCs' full DBI+CFG inventories, `rc0/rc1 dbi+0x082 = 0x7012 match=YES` (the `DL_ACTIVE` bit-13 read that external-aborted ko `503f9580` at a `readl` and ko `51376f76` at a `readw` now RETURNS on both domains), `rc1` reached live for the FIRST time, `dbi+0x004=0x0007`, `dbi+0x07c=0x734c12`, `dbi+0x080=0x0000`, `dbi+0x80c=0x012c`, iATU `[0x900]=0x00000002` with `iatu_rc[2]` match=YES (rc0 `0x48000000`/`0x4fffffff`, rc1 `0x60000000`/`0x67ffffff`), cfg identity all four match=YES - plus the clean unload (`RMMOD_RC=0`, `LUOFU_AFTER_RMMOD=0`, `STAGED_LEFT=0`, `PCISKEL RESULT: PASS`) and the same-boot device-up state (`WIPHY=2`, `IFACE=6`, cal `[SUCC]` 2g+5g, `LEFTOVERS=0`); C2 CI green at the arm head `lab-module-build` run `37556699784` headSha `c35af1a` (`omo/phase22-hccaccept`) = completed/success; C3 the fix is real at the instruction level (`bic r0, r3, #3` = the `off & ~3` step, the only MMIO op a 32-bit `ldr` + `dsb sy`, no write token, both `0x082` still W16, `KO BAR: PASS`). ONE OPEN SPLIT flagged not explained: both RCs' `cfg+0x082` reads `0x1012` (`DL_ACTIVE`=0, endpoint-side) vs the DBI's `0x7012` (=1) - a `match=NO` PREDICTOR disagreement, not a lost measurement. Hard rules held: CA `0x400392f0` never written, `0x10161000` never read/mapped, host IAR `0x4016010c` never read, serial + gate-checked, ko ALWAYS `wifidrv1.ko`, push to `omo/phase22-hccaccept` only, router left healthy on `mtd14:rootfsb`.

- **The take7b force (arm A) - the self-gate POLARITY is cured in the blob and the store STILL did not fire: the one-byte `cbz`->`cbnz` repair is present and capstone-proven, the boot is clean everywhere BUT the experiment, and `TG_RPR = 0x00` leaves the rank-1-vs-rank-2 question OPEN as an UNEXPLAINED skip** (`opensource/docs/phase49/gic-view.md` ADDENDUM 27, `opensource/docs/phase49/README.md` ADDENDUM 29, specs `build/tmp/inta-spec/{gfix.md,bankgate.md,bg2.md}`, fix task `st_01a11411`, cycle task `st_01a11417`, verdict `build/register-dumps/diffs/20261007T0212Z-vrun24/verdict.txt`, evidence `build/register-dumps/exp/20261007-020643/`). THE FIX: take7 shipped `cbz r5, dsb_at` (skip when `GICC_RPR == 0x00` - the exact state the force exists to retire; the emitter's comment said `CBNZ` while the opcode said `cbz`, and the selftest asserted the wrong op), so take7 (vrun23) never fired; `gfix.md` emits `cbnz r5, dsb_at` and `take7b.bin` (blob md5 `f5f5309fab9ae76518b9e1368a9ca768`) differs from `take7.bin` (`b41b0aacfbd46bd8619d71f197431f49`) at EXACTLY file `0xcb8fd` (`b1 -> b9`), same pad size/slot/`dsb_at`/cells, ko `3f87f1e9fe5ed9666f27d1f784d34535` unchanged (no CI, no push). THE BOOT: `TAKE7B RESULT: PASS`, `exp_rc=0`, `INSTRUMENT_GATE=HELD`, all seven sentinels `0x50AA7E49`, SGI-2 naming intact (`STK_STICKY = 0` over 16/16 `GICC_RPR` samples, `STK_ACT = 0x4`, `V2_ID = V2_RING3 = 0x402`), bound armed+tripped (`n=65/64`, `n=9/8`), no new pstore, router healthy on `mtd14:rootfsb`. THE NEGATIVE: `TG_RPR = 0x00000000` and `TG_HPP = 0x000003FF` = the UNFORCED state; the one device write did not take effect. Its neighbours measured the FIRING pre-state (`STK_ACT = 0x04`, `TG_ACT0 = 0x04`, bit 2 SET) and take6f's UNGATED force DROPPED `RPR` (`STK_RPR1 = 0xFF`) on that SAME pre-state, so the correct gate did not help and the skip is not the gate's shape. The controller's C4 FAIL: three candidates stay open, none provable from the cells - (a) an instantaneous `ISACTIVER0`-bit-2 transient the neighbours cannot see, (b) the store fired and `0x402` did not drop `RPR` (disfavoured, ADDENDUM 21a), (c) the level SGI-2 re-asserted and was re-taken inside the `dsb` window. The D2 gap (the pad deposits NO pre-force `RPR`, so `RPR == 0x00` at the gate is INFERRED, not cell-proven) is what blocks the split, and no branch-table row closes (`TG_GRP2 = 0x00` bit 12 CLEAR = `0x4C` is a GROUP-0 source, `TG_CCTLR = 0x01` bit 1 CLEAR, so even a fired force would have matched neither the group row nor the bank row). THE PASS IS THE INSTRUMENT GATE, NOT THE EXPERIMENT. Not a safety failure, not a build fault, not a NO-SAMPLE: a verified NEGATIVE and an OPEN residual. NEXT: a take7c pad that deposits the PRE-force `RPR` (or a matched pre/post pair) to settle (a)/(b)/(c) before any rank lever; the group-enable write and the bank quiesce stay deferred. Hard rules held: `0x400392f0` never written, `0x10161000` never read/mapped, host IAR `0x4016010c` never read, serial + gate-checked, ko staged as `wifidrv1.ko`, no commit, no push, router left healthy on `mtd14:rootfsb`.

- **The vrec22 record verification - ADDENDUM 27's take7b record is CONFIRMED as recorded: the heading and the NINE branch rows are QUOTED in both carriers, the negative (`TG_RPR = 0x00`, the store did NOT fire) is stated with its take6f contrast, and the PASS is labelled the INSTRUMENT gate, not the experiment** (verdict `build/register-dumps/diffs/20261007T0215Z-vrec22/verdict.txt`, task `st_01a11424`; read-back source `opensource/docs/phase49/gic-view.md` "ADDENDUM 27 (2026-10-07): the take7b force", `opensource/docs/phase49/README.md` ADDENDUM 29, `mem-entries.md` line 408, boot `build/register-dumps/exp/20261007-020643/`, official verdict `build/register-dumps/diffs/20261007T0212Z-vrun24/verdict.txt`): one ADDENDUM-27 record verifier, READ-ONLY and HOST-ONLY (no ssh, no devmem, no device cycle, no commit, no push). C1-C9 CONFIRMED with nothing inverting a load-bearing claim: (1) the heading at `gic-view.md:4493` is quoted verbatim (the blob cured + the store did NOT fire + `TG_RPR` reads `0x00` + the rank-1-vs-rank-2 question OPEN as an UNEXPLAINED skip), and the mem row reproduces the same sentence; (2) the branch table's heading line and rows T7-0..T7-8 are quoted in full, each with its condition AND its outcome reading, closing "One boot, no row closes. The honest label is the residual, not a verdict."; (3) those quoted row conditions match `capture-cmd.txt` lines 182-189 VERBATIM (row 1 `TG_RPR == 0x00000000 -> NOFORCE` ... row 8 `TG_ISP2 bit12 CLEAR -> a racing clear`), so no row is invented or softened; (4) the load-bearing cells are quoted and are the UNFORCED state (`TG_RPR = 0x00000000`, `TG_HPP = 0x000003FF`, plus `TG_GRP2 = 0x00` bit 12 clear, `TG_CCTLR = 0x01` bit 1 clear, `TG_ACT0 = 0x4`, `TG_ISP2 = 0x1021`); (5) the load-bearing contrast is real and quoted - take6f's UNGATED force DROPPED `RPR` (`STK_RPR1 = 0xFF`) on the SAME measured pre-state (16/16 `GICC_RPR = 0x00` + `ISACTIVER0` bit 2 SET) while take7b's CORRECTED self-gated full-word force did not; (6) the record labels the PASS the INSTRUMENT gate (`INSTRUMENT_GATE=HELD`) and forbids reading it as "the force landed"; (7) the one-byte fix + unchanged ko are recorded and DISK-MATCHED (`take7b.bin` md5 `f5f5309fab9ae76518b9e1368a9ca768`, ko `3f87f1e9fe5ed9666f27d1f784d34535`, no rebuild/CI/push); (8) the record adopts vrun24's C4 FAIL and does not inflate it; (9) the mem row names the correct carrier pair (`gic-view.md` 27 + README 29), not README 27 (which is the take6f-capstone pointer) - the README's own numbering slip is named in terms. Bounds carried: G1 the README numbering slip (real, self-declared); G2 the (a)/(b)/(c) split is NOT decidable from the cells and the record says so (candidate (b) marked DISFAVOURED, not refuted); G3 "SATISFIED" on T7-1 is `TG_RPR = 0x00`, the NOFORCE cell - the only row that closes and it is the residual, and the record says the row's stated reading is "internally strained"; G4 all `TG_*`/`STK_*` values are quoted from the cycle's boot artifact, not re-measured by this host-only verifier (the sentinel `TG_SNT = 0x50AA7E49` is the guard). Hard rules held: no write of CA `0x400392f0`/`0x40039af0`, no read of `0x10161000`, no host read of the ack IAR `0x4016010c`/AIAR `0x40160120`, no `GICD_SGIR` read, NO device cycle run, nothing staged, no commit, no push; the router stays as the cycle left it (`WIPHY=2 IFACE=6 CAL2G=1 CAL5G=1`, `PAT=0 OMO_OFF=0 WIFIDRV1=0`, stock md5 `0e530b976d5a20e87358671f1a577695`, on `mtd14:rootfsb` 2.5.24, boot_id `ab073ef2-d57d-42ad-971d-c42bc92f80b8`). NEXT: unchanged - build the pre-force-`RPR` deposit (take7c), run it once, and only then re-put the rank-1-vs-rank-2 question to the chip.

- **The upstream arm A (the CRG WRITE PATH) - STAGE 1 RAN and its no-op claim FAILED on ONE gate, so the write half stops at stage 1 and the stage-2 `pcie0_clk` flip stays QUEUED** (tasks `st_01a1142c` (worker) + `st_01a11437` (verifier); receipts `build/tmp/wifidrv1-art/crgwrite/{crgwrite-run-raw.txt,crgwrite-dmesg.txt,crgwrite-gate-raw.txt,crgwrite-post-raw.txt,RESULT.txt,KO.md5}`; reports `build/tmp/inta-spec/{wrspec.md,wrdesign.md,crgwrite-smoke.md}`; verdict `build/register-dumps/diffs/20261007T0236Z-vrunW/verdict.txt`, C2 = FAIL on the no-op with C1/C3/C4/C5 CONFIRMED; status block `opensource/docs/UPSTREAM-PORT-PLAN.md`). THE CODE + CI: submodule commit `5419532` on `omo/phase22-hccaccept` (`opensource/lab/luofu-clk/luofu-clk.c` the only file touched) cross-builds CI GREEN (`lab-module-build` run `37562151645` = success, artifact `luofu-clk-ko`, ko md5 `eca78db418dc420932114fec064e3651` = the KO.md5 pin, `vermagic=5.10.201 SMP mod_unload ARMv7`); census PASS - every store goes through one `luofu_crg_rmw()` that REFUSES past `LUOFU_WRITE_BUDGET` (`16*3 + 2 = 50`, compiled in), REFUSES unaligned offsets (`off & 3`), carries exactly ONE store through the arg0-derived CRG base (`str r6, [r4]`), and has `WRITE_FLIP` (the stage-2 rank write) compiled OUT while `WRITE_TEST` is in. THE RUN (one serial `insmod force_probe=1 write_test=1` -> dmesg -> `rmmod`, ko staged AS `/tmp/wifidrv1.ko`, NO reboot): gate CLEAN (`boot_id=ab073ef2-...`, `GATE_MTD_NUM=14 GATE_MTD_NAME=rootfsb`, `INSMOD_RC=0`), 16 `[STEP]` lines over the 16 `luofu_gates[]` entries (5 at `0x14`, 11 at `0x20`), 48 bounded dword-aligned stores, no refusal, no fault; result `WRITE_TEST FAIL 15/16 gates no-op (1 flips), 48 stores`, `RESULT.txt` = `FAIL [a-gate-read-back-flipped] [write_test-pass]`. THE MISMATCH: gate 4 `led_pwm` (`0x14` bit `0x0e`) is WRITE-1-SETTABLE but NOT WRITE-0-CLEARABLE - `pre 0x01360ef1 -> set 0x01364ef1 -> clear 0x01364ef1 -> back 0x01364ef1 (FLIP)` - so the set took and neither the clear nor the restore-pre took, leaving `0x14880014 = 0x01364ef1` (bit `0x0e` set). The lesson on the record: the other gates' "0 flips" MASKS a non-taking store (the `0x20` group already reads `0x02f8300b` with b0/b1/b3/b12/b13 set; `0x14`'s other four bits did not take the SET at all), so a gate table's EQUALITY is not the same as its write LANDING. THE BOX: `POST_BOOT` UNCHANGED (`ab073ef2-...`, no reboot), `RMMOD_RC=0`, `LUOFU_AFTER_RMMOD=0`, `STAGED_LEFT=0`, 2 wiphys, 6 interfaces, cal `[SUCC]` 2g+5g, `mtd14:rootfsb` on 2.5.24, `POST_OMO_PAT=0`, `POST_LEFTOVERS=0`, `CRG_STATUS = 0x6a010008` (PLLs locked, `rst_reason=4`), `WDT_ISTATUS = 0x00000000`; the leftover is a cosmetic `led_pwm` latch that clears on the next SoC reset. Hard rules held: CA `0x400392f0` never written, the RC misc `0x10161000` never read or mapped, the host-side IAR `0x4016010c` never read, dword-aligned accesses throughout, ko staged ALWAYS as `wifidrv1.ko`, push used only on `omo/phase22-hccaccept`. REMAINS (all three gates named by `crgwrite-smoke.md` sec 5): a build whose CLEAR is proven on `0x14` b`0x0e` (or that table entry re-derived against the pinned DTS), a stage-1 re-run returning `WRITE_TEST PASS 16/16` on a FRESH boot, and only then the stage-2 flip - refused anyway today because its precondition (`0x20` bit `0x0c` must PRE-read 0) sees `0x02f8300b` with bit `0x0c` already 1, and because the current artifact has `LUOFU_CRG_FLIP` compiled out. Do NOT re-run ko `eca78db418...` expecting a clean stage 1: it fails deterministically on gate 4.

- **The gated pad's structure (arm A) - the take7b skip's defect is NAMED and the fix is WRITTEN and HOST-VERIFIED, and the boot is still QUEUED: guard 2 (the toggling SGI-2 ACTIVE bit, sampled ONCE) is the only term that can skip in BOTH complementary polarities, the gate deposits nothing about what it read (vrun24 D2) and it introduced the chain's first `GICD` read -> `GICC` write pair with the only `dsb` AFTER the store, so `take7c` restructures the SAME 76-byte pad at the SAME slot `0xcb8e4` with four deltas (the guard's OWN `TG_PRERPR`/`TG_PREACT` deposits + a cross-interface `dsb sy` + the store made page-relative through `r2`)** (`opensource/docs/phase49/gic-view.md` "ADDENDUM 28 (2026-10-07): the gated pad's structure", branch `PAD-STRUCTURE`, spec `build/tmp/inta-spec/padstruct.md` (task `st_01a1142a`), emitter `tools/patch_fw_scratch.py` (`pad_stk_eoir_take7c`, `NOTE_TAKE7C`, `TG2_CELLS`), blob `build/tmp/fw-patched/take7c.bin` md5 `60e0af1cb7fb32ea9e58178f754dfbf3`). THE DEFECT: take7 shipped `cbz` and take7b the corrected `cbnz`, so on a stable operand EXACTLY one of the two boots must have fired and neither did; `TG_RPR = 0x00` pins pre-`RPR` to `0x00`, so guard 1 passed and guard 2 (`GICD_ISACTIVER0` bit 2) decided against both of its bracketing reads (`TG_ACT0 = STK_ACT = 0x04`), i.e. a TOGGLING bit tested ONCE - the pad's own fast sampler already OR-folds 16 `GICC_RPR` reads for exactly this reason, and the gate is also evidence-free, so a skipped store and a store that did not land are indistinguishable. THE FIX: (1) `TG_PRERPR 0x150204` <- the `GICC_RPR` the guard ITSELF read, deposited BEFORE the `cbnz`; (2) `TG_PREACT 0x150208` <- the `GICD_ISACTIVER0` word the guard ITSELF read, deposited inside the fall-through; (3) a `dsb sy` between the guard's Distributor read and the CPU-interface store (the access pair the FIRING take6f pad never had); (4) the store page-relative through `r2` (`str r0,[r2,#0x10]`), 8 B cheaper and funding (1)-(3) at exactly 76 B, so no pad/cell/slot/site/chain link moves and the post-force `TG_RPR`/`TG_HPP` instant (hence ADDENDUM 27's pre-store-`RPR` argument) is untouched. VERIFIED HOST-SIDE ONLY: three regenerations byte-identical, `--check-emitted` PASS 10/10 ops (take7b 9/9 and take7 9/9 UNCHANGED), `--selftest` PASS with the frozen `TAKE7_MD5`/`TAKE7B_MD5` and the canonical-form negative fixture, the take7c-vs-take7b delta 26 bytes at file `0xcb8fc..0xcb919` ALL inside the force pad, and the two new cells zero at BOTH barmap views. QUEUED: the take7c boot (the take7b cycle verbatim on `mtd14:rootfsb` with ONLY the staged blob swapped and the two new hook cells added; a NEW `boot_id` before any reboot, the watchdog armed before the hide, `recover`, then health 2 wiphys / 6 ifaces / cal `[SUCC]` / no `.omo-off`) has NOT run - the branch table it closes (row 3 `TG_PRERPR == 0` + `TG_PREACT` bit 2 CLEAR = GUARD 2 HELD, CELL-PROVEN; row 5 bit 2 SET + `TG_RPR = 0x00` = THE STORE DID NOT LAND) is exactly the D2 split no prior cell could carry, so NO rank lever is spent until it lands. No device action, no commit.

- **The upstream arm B (the REVERSIBLE CRG FLIP) - the armed stage-2 flip RAN on the LIVE CRG and is CONFIRMED, and it FAILED CLOSED: the CLEAR was IGNORED (the write-1-set-only latch class now confirmed on a SECOND gate), so the target bit was left bit-for-bit as found (`pre == clear read-back == set-back == 0x01364ef1`, bit `0x18` = 1) INSIDE the 50-store budget with no refusal and no third store, and the router is healthy on the SAME `boot_id`** (task `st_01a1144c` worker + `st_01a11450` verifier; verdict `build/register-dumps/diffs/20261007T1005Z-vrunF/verdict.txt` (all six claims CONFIRMED, host-only, NO device cycle, NO commit, NO push), sibling `build/register-dumps/diffs/20261007T0236Z-vrunW/verdict.txt` (arm A, C2 = FAIL), `opensource/docs/UPSTREAM-PORT-PLAN.md` status block (arm B), evidence `build/tmp/wifidrv1-art/crgflip/` (`RESULT.txt` = `PASS`, `SELFTEST.txt` = `SELFTEST PASS`), runner `build/tmp/wifidrv1-art/run-crgflip.sh`, spec `build/tmp/inta-spec/flip.md`, submodule commit `3d2e4cdf640d943d2a7d86c7f7056e2f64529b38` on `omo/phase22-hccaccept`, the only file touched `opensource/lab/luofu-clk/luofu-clk.c`, CI `lab-module-build` run `37564223517` **success** at that head, ko md5 `84a2f1f461cf18b95670c85e10051617` == `KO.md5` pin == staged, `vermagic=5.10.201 SMP mod_unload ARMv7`). THE CODE (the stage ARM A left QUEUED, armed as `flip.md` sec 6 requires): the benign rank-1 gate `0x14` bit `0x18` (`i2c0_clk`), the sequence `read -> REFUSE unless the bit is SET -> CLEAR (store 1) -> OBSERVE (0x90/`0x100`, read-only) -> SET-BACK (store 2) -> PASS iff `post == pre``, the bound `LUOFU_FLIP_WRITES = 2` on top of stage 1's 48 = `LUOFU_WRITE_BUDGET` 50 (`cmp #0x32` compiled in, unchanged at 2), the retired `pcie0_clk` target ABSENT from the artifact, and `CRGFLIP-CENSUS: PASS` over the ko (bound + dword-alignment guard `tst r1, #3` compiled in, exactly ONE store site through the arg0-derived CRG base `str r6, [r4]` in `luofu_crg_rmw`, exactly five RMW call sites = stage 1's three + the flip's two, gate offsets only from `.rodata` `0x14`/`0x20`, probe carrying `0x1000000`/`0x14`/`0x90`/`0x100`). THE RUN (ONE serial `insmod force_probe=1 write_flip=1` -> dmesg -> `rmmod`, detached + gate-checked, ko staged ALWAYS as `/tmp/wifidrv1.ko`, NO reboot, 2026-10-07T03:00:43Z -> 03:00:50Z): gate CLEAN at `boot_id=faef074c-987f-4d9f-9c90-4feb75152120` (uptime 545s), slot `mtd14:rootfsb` (2.5.24), guard 0; the precondition HELD (pre-read bit `0x18` SET); then verbatim `WRITE_FLIP i2c0_clk off=0x14 bit=0x18 pre=0x01364ef1 store 1/2 = the clear`, `WRITE_FLIP clear read-back=0x01364ef1 i2c0 bit=1 (the clear was IGNORED - write-1-set latch confirmed on a second gate)`, `WRITE_FLIP i2c0_clk: pre=0x01364ef1 -> clear=0x01364ef1 -> set-back=0x01364ef1: PASS post == pre (50 stores total)`, `WRITE_FLIP rc=0`, `FORCED probe PASS: 2/2 status regs read, 50 writes`. THE FINDING: the CLEAR (`pre & ~BIT(0x18) = 0x00364ef1`) did not take - the SAME write-1-set-only class ARM A found on `led_pwm` bit `0x0e`, now confirmed on a second gate - so a real driver must program this CRG latch class by SET + an external reset, never by a clear (the `flip.md` sec 4 premise, measured); because the clear did not take the instrument failed CLOSED (nothing changed, `LUOFU_FLIP_WRITES = 2` admits no retry, dmesg carries no `write budget ... exhausted, refusing RMW` refusal line and no `FAIL post != pre`), `0x14880020` reads `pre -> post 0x02f8300b -> 0x02f8300b` unchanged, and the OBSERVE words are dynamic not flip evidence (`0x14880090 0x6a090008 -> 0x6a010008`, PLLs locked, `rst_reason=4`; `0x14880100` = `0x00000000` WDT_ISTATUS). THE ONE NAMED RESIDUAL: `0x14` ENTERED at ARM A's post-stage-1 `0x01364ef1`, not the pristine `0x01360ef1`, because stage 1's sweep had already SET `led_pwm` (`[STEP 4] led_pwm off=0x14 bit=0x0e pre=0x01360ef1 -> set=0x01364ef1 -> clear=0x01364ef1 -> back=0x01364ef1 (FLIP)`, `WRITE_TEST FAIL 15/16 gates no-op (1 flips), 48 stores`) - a cosmetic, non-restorable bit that clears on the next SoC reset, on a DIFFERENT bit from the flip target, so `post == pre` is a genuine measurement and not a tautology of a wrong baseline. THE HEALTH (one `boot_id` across gate/post/final, UNCHANGED, `F_UPTIME=588`, `F_REV=2.5.24`): `POST_WIPHY=2 POST_IFACE=6 POST_CAL2G=1 POST_CAL5G=1 POST_VENDOR_WIFI=1 POST_VENDOR_PLAT=1 POST_LEFTOVERS=0`, `RMMOD_RC=0 LUOFU_AFTER_RMMOD=0 STAGED_LEFT=0 RUN_DONE`, zero `wifidrv1`/`luofu`/guard/`.omo-*` leftovers, no kernel fault (the final probe's `F_FAULT=1` is its crude regex counting the BOOT-TIME info line `[ 7.569200] pstore_zone: registered pstore_blk as backend for kmsg(Oops,panic_write)`, named not hidden). THE VERDICT: C1 the flip ran and the equality holds, C2 the restoration is exact, C3 the health block holds, C4 the CI artifact is real and IS the artifact the run fetched, C5 the code matches `flip.md` sec 6's arming change, C6 the hard bars were held - ALL CONFIRMED => arm B CONFIRMED, the write half's stage 2 now MEASURED rather than merely queued. HONEST COUNTERWEIGHTS: the flip observed only the CLEAR-IGNORED outcome, so the "the clear TOOK -> a real, exactly-restored flip" branch is present in the code and the selftest's mutation C but is NOT exercised; the verdict skeleton was filled by hand from the `vrec23` template (`tools/finish-evidence.sh` was NOT re-run against that dir); the run's follow-up CI run `37565449816` ("close the flip lane") is NOT asserted by the verdict, whose C4 rests on the RUN's own `37564223517` / md5 `84a2f1f4...`; and a clean `post == pre` against the PRISTINE `0x01360ef1` baseline (a fresh boot with stage 1 skipped, or a stage-1 re-run returning `WRITE_TEST PASS 16/16`) is still owed. Hard rules held: CA `0x400392f0` never written; the RC misc `0x10161000` never read or mapped; the host-side IAR `0x4016010c` never read; dword-aligned accesses; the device action serial + gate-checked (the runner refused to proceed until a stale zero-byte `/tmp/omo-t7-hide.done` from the CLOSED take7 lane was cleared, so no mutation preceded a clean gate); ko staged ALWAYS as `wifidrv1.ko`; push authorization used ONLY on `omo/phase22-hccaccept`, never `master`. No device action by this recorder, no commit.

- **The upstream arm B's DESIGN - the reversible CRG flip: the gate latches are SET-ONLY (the write-0 clear is inert on 16/16 bits), so the only direction whose undo is a store this part honours is the CLEAR, the rank-1 target is `0x14` b`0x18` `i2c0_clk`, the sequence is `read -> refuse-unless-set -> CLEAR -> OBSERVE 0x90/0x100 -> SET-BACK -> PASS iff post == pre` inside a 2-store budget (48 + 2 = 50), and the class set-only verdict makes a clock gate un-flippable in software - the RC dependency** (`build/tmp/inta-spec/flip.md` sec 0-7, task `st_01a1143f`, design only - no code, no build, no device action; `opensource/docs/UPSTREAM-PORT-PLAN.md` status block (arm B), ADDENDUM 29a; sources the inta-spec siblings `{wrdesign,wrspec,crgwrite-smoke,crgbind,crgprobe,clocks2,stage2,slotgate}.md`, `luofu-clk.c` (flip path `:367-392`, gate table `:128-145`, `rmw` `:312`, budget `:299-301`), `luofu-r116-pinned.dts` (`clk@14880000` `:201-365`, `i2c0` `:1013-1022`), the raw receipt `.../crgwrite/crgwrite-dmesg.txt`, a live-boot `dmesg.txt`, capstone over `rootfs-2.4.15/.../hi_clk.ko`; CRG base `0x14880000` + `0x1000` = `pinned:205`, the 16 gate bits re-verified against the pinned DTS `bit = <...>` properties). SEC 1 FIND 1, THE SET-ONLY LATCH: the smoke's raw STEP lines carry a `clear=` column its summary hid - every clear (`v & ~BIT`) left the register identical, including the four `0x14` 1-bits and the eleven reconstructed `0x20` bits, and the sole store that took (1/1) was the SET of `0x14` bit `0x0e` `led_pwm` (`0x01360ef1 -> 0x01364ef1`), so the vendor's own write-0 `hi_clk_gate_disable` shape (`hi_clk.ko` @0x1184, one offset + `BIT(bit)` + value 0) is a NO-OP on this part and the gates simply stay as U-Boot left them; the corollary is that the stage-1 "15/16 no-op'd exactly" is VACUOUS for all 15 (a bit already reading 1 cannot show a set and its clear is inert, so `pre == post` holds by construction - the 15 are NOT proven non-latching). SEC 2 FIND 2, THE DIRECTION IS FORCED: the SET's undo is the ignored write-0, the CLEAR's undo IS the proven SET, so the flip must launch in the CLEAR direction - the only direction whose undo this part is known to honour, and one that fails CLOSED (when the clear does not take, nothing changed at all). SEC 3, THE CANDIDATES RANKED BY BLAST RADIUS (live map from a boot `dmesg.txt`): 1 (pick) `0x14` b18 `i2c0_clk` - driver bound but NO i2c client node in the tree and no `i2c` line in any boot log -> no bus traffic, no periodic MMIO, blast radius none; 2 `0x20` b13 `gemac_clk0` - no netdev line, unbound, but "no line" is weaker than "no client node" and it sits in the RECONSTRUCTED `0x20` group; 3 `0x14` b14/b15 `gpio0/1_clk` - the board overlay adds `gpio-keys-polled` (poll 20 ms) + `gpio-leds`, so an access every 20 ms -> dwapb MMIO on an unclocked block = the external-abort/panic class (`pcie-gpios` ride these lines); 4 `0x20` b03 `mdio_clk0` - `phylib` `(irq=POLL)` on eth0..eth3 -> the same abort class within ~1 s; 5 `0x20` b0c/b0d `pcie0/1_clk` - `cfg+0x000 = 0x59e7` on both RCs and DBI `0x082` `DL_ACTIVE=1` -> a wiphy drop per RC and a wedged DWC link, NOT benign (the `wrdesign.md` sec 4 rank-1 pick, OVERTURNED); 6 `0x20` b00/b01 `lsw_dp/pfe_clk0` - the LAN/WAN path (our ssh) dies; 7 `0x20` b14..b17 `gemac_clk1..4` - the live data path; 8 `0x20` b19 `pie_clk0` - live but unmeasured; `0x14` b00 `sfc_clk` - the SPI-NAND rootfs, NEVER. SEC 4, THE TARGET AND THE EXACT SEQUENCE: `pre = readl(base + 0x14)` (dword-aligned; `INFO_assert(!(off & 3))`), REFUSE with 0 stores if the bit is already 0 (bit 0 = the one-way SET, not permitted), then store 1 = the CLEAR (`luofu_crg_rmw(base, 0x14, 0x18, 0)`), OBSERVE `readl(base + 0x90)` / `readl(base + 0x100)` (the only two words the pinned tree licenses as pure reads, `:376/:388`, `:1406`, `:1519`), store 2 = the SET-BACK (the restore IS the proven set), `PASS iff post == pre` and no fault and the post-health holds, refuse any 3rd store; the OBSERVE honesty bars: `0x90` bit 19 (`0x80000`) moved inside the smoke (`0x6a090008` -> `0x6a010008`) but also reads 1 in one boot and 0 in another with NO store (`crgprobe.md` sec 3), so it is DYNAMIC and must never be attributed to the flip, and the gated block (`0x10111000`) must never be read while cleared (the `readw.md` / `0x10161000` external-abort class). SEC 5, THE RECOVERY BULLETS: the watchdog is armed BEFORE anything is staged (`tools/exp.sh` [0/7], `EXP_WATCH:=1800`, the SoC's own `hsan-watchdog-driver 14880000.watchdog: Hsan watchdog timeout=30 sec, nowayout=1`), a hung CRG write means a deterministic reset and pstore (`mtdpstore`/`pstore_blk`/`pstore_zone`) carries the last kmsg across it, and A REBOOT GATES ON A NEW `boot_id` - never "it came back, so it worked"; the slot gate (require `mtd_num=14`/`rootfsb` + `dmesg_attach=14`, ABORT with nothing staged on a conflict, restore slot B per `build/custom/FLASH-PLAN.md` "Slot switch recipe" after a recovery boot, then confirm `attached mtd14`); serial + gate-checked (one serial device action, ko always `/tmp/wifidrv1.ko`, `recover` deletes `.omo-pat`, the vendor modules are NEVER `rmmod`ed, the stack ends on 2.5.24 with 2 wiphys / 6 interfaces / cal `[SUCC]` both bands). SEC 6, THE COMPILE-GATED PATH DOES NOT MATCH AND THE EXACT ARMING CHANGE: `luofu-clk.c:367-392` (`#ifdef LUOFU_CRG_FLIP`, submodule `5419532`) flipped `0x20` b`0x0c` `pcie0_clk` and refused unless `!(pre & BIT(0x0c))`, then `set -> clear` - THREE independent mismatches: its precondition is FALSE live (`0x20 = 0x02f8300b`, bit `0x0c` = 1 -> the `-EBUSY` refusal at `:379-382` with no store, which is why the smoke's `write_flip=1` could not run, `crgwrite-smoke.md` sec 5), its restore is the ignored write-0 (even with the precondition satisfied the "restore" could not restore, leaving RC0's clock gate SET one-way), and its target is rank 5 (a live wifi endpoint); the fix, all inside the existing `#ifdef` so a default artifact still carries no rank store: target `0x20`/`0x0c` -> `0x14`/`0x18` (the gate already exists at `luofu-clk.c:132` `i2c0_clk`), polarity inverted to proceed `if (pre & BIT(0x18))` and refuse otherwise (because the permitted flip is the CLEAR), sequence `pre -> clear -> obs(0x90,0x100) -> set-back -> post` with `PASS iff post == pre`, bound unchanged at 2 (`LUOFU_FLIP_WRITES` `:300`), the `write_test` gate loop untouched. SEC 7, OPEN ITEMS NOT ASSERTED: whether a companion DISABLE register exists for this latch class (Hisi's `clkgate-separated.c` pattern, `clocks2.md` sec 1) - a read-only neighbour scan (`0x10`/`0x18`/`0x1c`/`0x24`/`0x28`) would answer it, but an undocumented CRG read is itself unproven-safe, and the vendor `hi_clk.ko` data carries NO (offset,bit) gate table (capstone scan this session), so the pinned DT is the only geometry source, one offset per gate; the `0x2c`/`0x30`/`0x34` reset bits are a DIFFERENT class (`hi_kreset`: assert = clear, deassert = set, `wrdesign.md` sec 0) and were never read, so a reset-class flip is the natural follow-on instrument once this one has run clean; the `0x20` group's offsets remain RECONSTRUCTED (`clocks2.md` sec 2 caveat) while the `0x14` target's do not. THE DESIGN WAS THEN EXECUTED (naming, not re-measuring: this recorder ran no device action) - the armed flip (`st_01a1144c`) failed CLOSED exactly as sec 4's outcome #1 predicts (`pre 0x01364ef1 -> clear 0x01364ef1 -> set-back 0x01364ef1`, `WRITE_FLIP rc=0`, 50 stores, `boot_id` unchanged), verdict `build/register-dumps/diffs/20261007T1005Z-vrunF/verdict.txt` all six claims CONFIRMED. THE NEXT STAGE this design sets: do NOT re-run `write_flip=1` against a set-only latch (a measured no-op repeats), aim at a NON-LATCHING target (the reset class) or a companion disable register if one is ever proven, still owed is a stage-1 re-run returning `WRITE_TEST PASS 16/16` on a FRESH boot with `0x14` measured from the PRISTINE `0x01360ef1` (so `post == pre` is shown against a pristine baseline and not ARM A's post-sweep value), and the real PCIe/i2c0 work is the subsystem table's `from-scratch` items rather than another CRG probe. THE RC DEPENDENCY: the pcie0/pcie1 gates are `0x20` b0c/b0d, and because the class is set-only a clock gate can never be flipped back in software, so a driver that needs a gate OFF must use the reset class (or a companion disable register) - the from-scratch DWC RC (the five windows / `iatu_rc` table / LTSSM already measured by arm-B4/B5) cannot rely on the CRG gate-clear path. Hard rules carried by the design and untouched by it: never write CA `0x400392f0`; never read the RC misc `0x10161000`; never read the IAR `0x4016010c`; dword-aligned accesses; ko staged ALWAYS as `wifidrv1.ko`; leave the router healthy on 2.5.24; push authorization ONLY on `omo/phase22-hccaccept`, never `master`. No device action by this recorder, no commit.
- **The take7c re-run (arm A) - the capture LANDS, BOTH guards PASS cell-proven, and the EOIR store STILL does not land: the pad-structure / `GICD`->`GICC` ordering hypothesis is REFUTED as the cause, the residual is PAST the pad, and the rank-1-vs-rank-2 arc question stays OPEN** (`opensource/docs/phase49/gic-view.md` "ADDENDUM 30 (2026-10-07): the take7c re-run", `opensource/docs/phase49/README.md` ADDENDUM 31, specs `build/tmp/inta-spec/{padstruct.md,hookfix.md}`, runner `build/tmp/wifidrv1-art/run-take7c.sh`, hook `build/tmp/wifidrv1-art/take7c-capture.hook`, verdict `build/register-dumps/diffs/20261007T0320Z-vrun26/verdict.txt`, evidence `build/register-dumps/exp/20261007-031654/`). THE CURE: take7c's FIRST boot (ADDENDUM 29a, `exp/20261007-024805/`) read a 414-B receipt with zero cells because the staged capture hook was CRLF-corrupted (md5 `f16458b66ea31c632c1b47d20138e4ec`, 313 CR) so busybox ash died on line 1; the run staged the LF-cured hook (md5 `7e695f93ce23453c83e878116b78ecfe`, 0 CR / 313 LF) and the capture landed in 1 s (`capture-writer: waited=1s done=yes`, `hook-done banners: 1`), so THIS is the first take7c boot whose cells exist to be read. THE RESULT: every sentinel ran (`TG_SNT = STK_SNT = N_SNT = B_P3 = B_P4 = F_SNT = C_SNT = 0x50AA7E49`; `E_SNT`/`X_SNT` are NO-SAMPLE BY CONSTRUCTION - `selpost_e`/`selpost` dropped), and the pad's OWN operands prove BOTH guards passed - `TG_PRERPR = 0x00000000` (guard 1, the force pad's own `GICC_RPR` read: 0 = PASSED) and `TG_PREACT = 0x00000004` (guard 2's own `GICD_ISACTIVER0` w0 read, bit 2 SET = PASSED, so the store was ATTEMPTED) - yet the post-force witness `TG_RPR = 0x00000000` and `TG_HPP = 0x000003FF`: the single `GICC_EOIR 0x40160110 <= 0x402` write retired NOTHING. That is the runner's row T7C-D ("THE STORE DID NOT LAND"), the exact split `vrun24` D2 said no cell could carry, so the take7c hypothesis (`padstruct.md` sec. 2.4, the cross-interface ordering hazard) is REFUTED as the CAUSE - adding the `dsb sy` + the page-relative store changed nothing, and the residual sits PAST the pad. THE CONTRAST: take6f's UNGATED force DROPPED `RPR` (`STK_RPR1 = 0xFF`) on the SAME measured pre-state (`exp/20261007-010906/`), while take7c's gated full-word `0x402` store did not - the gate is provably not the discriminator. THE POST SET is the UNFORCED snapshot (`TG_ACT0 = 0x04`, `TG_ISP2 = 0x1021` bit 12 = `0x4C` still pending, `TG_ACT2 = 0x00`, `TG_GRP2 = 0x00`, `TG_CCTLR = 0x01`), matching `vrun24`'s take7b set value-for-value; `TG_GRP2` bit 12 clear / `TG_CCTLR` bit 1 clear must NOT be read as a group verdict (rows T7-2/3/4 need `TG_RPR == 0xFF`). The runner's PASS is the INSTRUMENT GATE + health, NOT the force (`TG_RPR` reads `0x00`, exactly as `vrun24` warned). OFFICIAL VERDICT `build/register-dumps/diffs/20261007T0320Z-vrun26/verdict.txt` (task `st_01a1145d`, host-only, NO device cycle): C1-C7 CONFIRMED, C8 REPORTED as row T7C-D; the arc's rank-1 (id) vs rank-2 (group) question is therefore NOT ANSWERED. The `--check-emitted` gate held 10/10 ops in op order; the four take7c deltas are confined to the 76-B force pad (file `0xcb8fc..0xcb919`, 26 B), take7b's blob byte-UNCHANGED; a NEW `boot_id 5f52bdef-e9b7-4eb1-839a-372e3ab2de77` proves the reboot was real; the bound held (qbound=64/8, tripped n=65/9, self-disabled) and the literal pair was restored (`RESTORE_DONE`); no new pstore; the router is HEALTHY on `mtd14:rootfsb` (2.5.24): `WIPHY=2 IFACE=6 CAL2G=1 CAL5G=1`, `OMO_OFF=0 STAGED=0 LOADER=0`, stock md5 `0e530b976d5a20e87358671f1a577695` untouched. Blob `take7c.bin` md5 `60e0af1cb7fb32ea9e58178f754dfbf3`; ko `wifidrv1.ko` md5 `3f87f1e9fe5ed9666f27d1f784d34535`. Hard rules held: no write of CA `0x400392f0`/`0x40039af0`, no read of `0x10161000`, no host read of the ack IAR `0x4016010c` / AIAR `0x40160120`, no `GICD_SGIR` read, dword-aligned accesses only, THE BOUND MANDATORY, ko staged as `wifidrv1.ko`, no commit and no push. Next: deposit a matched PRE/POST `RPR` pair (or a sticky/OR-folded ACTIVE term) to separate "the store retires nothing" from "the epoch re-forms in the window", then re-put the rank-1-vs-rank-2 question to the chip.
- **The gated store's RCA (arm A) - PAD-RCA: the stale-flags hypothesis is REFUTED on the bytes, every other difference between the one EOIR write that LANDED and the three that did not is ELIMINATED by measured cells, the residue is NAMED as the written word's `[12:10]` source-PE/CPUID field, the one-byte fix (`take7d`) is WRITTEN and HOST-VERIFIED, and the ONE-VARIABLE BOOT stays QUEUED** (`opensource/docs/phase49/gic-view.md` "ADDENDUM 31 (2026-10-07): the gated store's RCA", RCA `build/tmp/inta-spec/padrca.md` (task `st_01a1146a`), emitter `tools/patch_fw_scratch.py`, host-only - NO device action, NO ko, NO commit, NO push). THE REFUTATION: the shipped 76-byte force pad's guards are `cbnz r5` (compares `r5` vs ZERO - NEVER reads APSR) and `blo` (tests the C its OWN `lsls r5,r1,#0x1e` set one instruction above), so the premise ("an MRS does not set flags -> an arbitrary guard") is false and the proposed `tst`/`cmp` fix is a NO-OP; the bank pad (112 B) and fast sampler (172 B) carry NO guard at all. THE ELIMINATION TABLE (10 rows, all REFUTED): stale flags; the guards branch PAST the store (both resolve to the post-store `dsb` at `0xcb91a`); a clobbered guard register (`r5` only re-used AFTER guard 1 decides); a wrong store address (`0x40160110` == GICC_EOIR, the CA the image's own pool holds at `0x83020`); the store not emitted (`--check-emitted` 10/10 op-ordered); the `dsb sy`; the `GICD` read before the `GICC` write (take6f's own chain does it and landed); the gate skipped (`TG_PRERPR = 0x00` + `TG_PREACT = 0x04` cell-proven PASS); the ID field `[9:0]` (`0x2` on both sides); and the epoch re-forming (`TG_PEND0 = 0x00`, `V2_CNT = 4` both boots, `TG_ACT0` bit 2 still SET). THE RESIDUE: the ONLY operand difference between take6f's LANDING write (`0x2` = id 2, source PE 0) and the three that retired nothing (`0x402` = id 2, source PE 1) is the `[12:10]` source-PE field; COUNTER-EVIDENCE recorded not hidden - the firmware's own EOI (`0x82f52 str r7,[r3]`) writes the same `0x402` and take5's I5 site reads `RPR = 0xFF` after it, so the field is NOT PROVEN to be the comparator (the queued boot is the ONE-variable test). THE FIX: `take7d` = take7c's entire pad with `movw r0,#0x2` (the `[12:10]` CLEARED - the bare-10-bit-id form); the take7c-vs-take7d blob delta is EXACTLY ONE byte, file `0xcb917`: `0x40 -> 0x00`; blob md5 `55120820882e07919ba98fedf6695b1b`; the emitter REFUSES any `[12:10]`-SET value (rc=2), the emitted check rebuilds the store AND its `r2` page setup independently (10/10), and `--selftest` PASSES (same slot, exactly offset 51, `0x402` ABSENT, five source-PE-SET values refused). THE QUEUED BOOT (NOT run - take7d has not booted): the take7c cycle VERBATIM (`tools/exp.sh` serial/detached, `mtd14:rootfsb`, NEW `boot_id`, watchdog before the hide, ko ALWAYS `wifidrv1.ko` = `3f87f1e9fe5ed9666f27d1f784d34535`, then health) with EXACTLY two changes (the staged `.omo-pat` = `take7d.bin`, cells unchanged) -> row 1 `TG_RPR = 0xFF` = THE FIELD WAS THE COMPARATOR / row 2 `TG_RPR = 0x00` = THE OPERAND IS EXONERATED and the residual is past the pad. Coincident with the take7c record ADDENDUM 30 in `gic-view.md` and `opensource/docs/phase49/README.md`.

- **The 2026-10-07 code sprint (six lanes) - SPRINT RESULT: COMPLETE: the port's open threads became loadable (and compilable) code across six lanes, five CI-green, four smoked live on 2.5.24 with three clean load/unload pairs, one benign kernel refusal, and no reboot, no data path, and no vendor-register write anywhere in the class** (records `opensource/docs/phase49/gic-view.md` ADDENDUM 33 ("the code sprint - six lanes"), `opensource/README.md` pointer rows, `opensource/docs/UPSTREAM-PORT-PLAN.md` sprint status block; smoke receipts `build/tmp/inta-spec/{sprint-smokes.md,dtsx.md,drvcrg.md,drvpin.md,drvwifi.md,drvpcie.md,kcfg.md}`, runner `build/tmp/wifidrv1-art/sprint/run-sprint-smoke.sh`; task `st_01a114c1`). THE LANES, EACH AN ARTIFACT + A CI + WHERE A SMOKE RAN + THE NEXT RUNG: (1) **DT** `opensource/docs/soc/luofu-r116.dts`, 20 new nodes (CRG full with 2 PLLs/2 muxes and the binary-only `rstinfo` folded in, `pinctrl_peri`, `pcie0`/`pcie1` with their `iatu_rc`/`iatu_ep` tables, `uart0`/`uart1`, `fmc` + 17 A/B partitions, 4 gemacs + `mdio0` + 5 PHYs, the 3 LSW blocks, `pie`), the `LUOFU_CLK_*` block grown 7 -> 16 gates, every new vendor node `status = "disabled"`; CI `tools/dtc-check.sh` under dtc 1.7.2 -> `PASS size=10807 sha256=c3b2c607409b1c10a9b4864e67fc973426dee8cd7e60567a9e7fef4202549ee1 errors=0 warnings=3` (the 3 pre-existing `unit_address_vs_reg` nits); no smoke (not a module); next = the `mach-luofu` Kconfig entry + the in-tree `crg-luofu.c` landing. (2) **CRG** `opensource/lab/luofu-clk/` (1,014 lines + the binding note): the pinned 16-gate/2-mux/2-PLL geometry in structs through the generic `clk-provider.h` API, all clocks `CLK_IGNORE_UNUSED`, a DT onecell provider; CI `lab-module-build` run `37573235229` on head `4f0373f` (success, artifact `luofu-clk-ko`) with the `CRG rule census` (one `writel()` = the RMW primitive, no sub-word stores, `off & 3` guard); SMOKE `sprint-smokes.md` sec.1: ko md5 `763c346a78d9b549edc787c1efd620e1`, `insmod force_probe=1` rc=0 / `rmmod` rc=0, banner `write_test=0 write_flip=0 rst_flip=0 read-only`, `[0x090] CRG_STATUS = 0x6a010008` + `[0x100] WDT_ISTATUS = 0x00000000`, `0 writes`; next = the `reset_controller_dev` (the DEASSERT direction is live - `0x2c` b`0x18` `i2c0_rst` cleared and restored exactly in the stage-2b run - while the `0x14` gate class is set-only), the PLL/mux rate math, and the move into `drivers/clk/hisilicon`. (3) **pinctrl** `opensource/lab/luofu-pinctrl/` (611 lines): the placeholder replaced by the vendor's real tables cited to `.ko` offsets (37 pins `.data+0x428`, 24 groups `.data+0x68` with pins `.rodata+0x32c..0x3e4`, 24 functions `.rodata+0x20c`, 37 x 5 mux `drv_data` `.data+0x644..0xf84`), `set_mux`/pinconf still no-op stubs; CI run `37573603109` on head `5a049e15` green after one repair (`5a049e1`: `pinctrl_utils_free_map` is not exported in vanilla 5.10 -> `pinconf_generic_dt_node_to_map_all` + `pinconf_generic_dt_free_map`); SMOKE sec.2: ko md5 `3a09887a62a52e9c43218d46a320e9fa`, `insmod` rc=16 with `Error: Driver 'luofu-pinctrl' is already registered, aborting...` - the vendor `hi_kpinctrl` owns that exact platform-driver name and is bound to the same live DT node, so nothing loaded and the device was untouched (a NAMING finding, not an anomaly); next = rename `.driver.name` (or drop the DT match) and re-run. (4) **wifi** `opensource/lab/luofu-wifi/` (822 lines): our own `struct pci_driver` for `59e7:0005` - four pages of the region-3 inbound window, the announce/handshake state machine, the glue/mailbox on copy A + twin, the SR/DR ring and credit bookkeeping, all through the aligned accessor with no store expression in the source - plus the ETE register-block correction (`SR {0x400,0x450,0x4a0}`, `DR {0x590,0x5e0,0x630,0x680}`, 0x50 apart, not the `0x114`/`0x6c` host struct strides `credit2.md` sec.5 retracts); CI `lab-module-build` `37573603109` (the master-only lane not exercised, mirrors mechanically); SMOKE sec.3: ko md5 `2fb63afedc8bc335f8a4c4a0eca92309`, `insmod`/`rmmod` rc=0 on the default `hw=0` path (registration/ABI only, zero PCI contact; `hw=1` deliberately not exercised - both domains vendor-bound); next = the glue ISR (`request_irq` the bound endpoint's INTx virq, status mask `0x3d8`, in-ISR bound), then the H2D/D2H service, the rings, the wiphy. (5) **PCIe** `opensource/lab/luofu-pcie/` (1,005 lines): the platform frame + dword-aligned read AND write accessors, the LTSSM read-state machine over DBI `PORT_LOGIC_DEBUG0/1`, `luofu_pcie_check_aligned()` BUILD_BUG_ONs on every raw-dword offset, the `misc` window mapped WRITE-ONLY and never read; CI `37573603109` with the new `alignment rule` step (fail on any `readb/readw/writeb/writew` or a misaligned raw literal); SMOKE sec.4: ko md5 `385fc736ca6088c7b8ebe14cd59d4549`, `insmod force_probe=1`/`rmmod` rc=0, DBI 3/3 + cfg 4/4 matched, `rc0 [0x082] = 0x7012` read through the aligned accessor (the exact word whose `readw` panicked the box), the aggregate `link DOWN` the AND of two `DL_ACTIVE` predicates while the DWC LTSSM reads L0; next = wire the CRG/pinctrl providers, then the staged write path + `pci_host_probe`. (6) **kernel config** `opensource/lab/luofu-kernel/{luofu.fragment,README.md}` + `.github/workflows/luofu-kernel-config.yml`: a delta on `multi_v7_defconfig` at 5.10.201, `=y`, 47 non-`LUOFU` symbols + 13 new with vendor evidence; CI run 1 `37572753552` FAILED (the lane's own assert caught `merge_config.sh`'s inner `make alldefconfig` resolving a HOST x86 config -> fix `78823b3` `export ARCH=arm`), run 2 `37572932947` CAUGHT A REAL FINDING (`PSTORE_BLK depends on BROKEN`, promptless, so pstore-on-MTD is unreachable in a vanilla tree without the vendor patch -> fix `c40637a`), run 3 `37573150202` SUCCESS (47/47 `=y`, 13 `LUOFU` to-do); no device smoke (a config file); next = the 13 Kconfig entries with their `select`s. THE LIVE PASS: clk, pinctrl, wifi, pcie in that order, ONE serial device action per module, each preceded by its OWN gate (health + SLOT CHECK `mtd14`/`rootfsb` + no active cycle) - 3 clean load/unload, 1 kernel refusal; `boot_id 4f8f2940-d1f3-41d7-a61d-67f00de1e41c` UNCHANGED end to end, NO reboot, every ko staged AS `/tmp/wifidrv1.ko`, final state `WIPHY=2 IFACE=6 CAL2G=1 CAL5G=1`, `PAT=0 OMO_OFF=0 LEFTOVERS=0`, stock md5 `0e530b976d5a20e87358671f1a577695` at pin. THE CLASS'S HONEST LIMIT: the five module lanes were not byte-frozen into one shared artifact set (they share the submodule and the CI head), which is the closest a single-checkout sprint gets to frozen artifacts - and none of the six lanes has a data path, an ISR, or a write to any vendor register. Hard rules held: no write of CA `0x400392f0`, no read of the RC misc `0x10161000`, no host read of the IAR `0x4016010c`, dword-aligned accesses throughout (CI-gated in `luofu-pcie`/`luofu-clk`), the take-family ko staged ALWAYS as `wifidrv1.ko`, push authorization used ONLY on `omo/phase22-hccaccept` (never `master`), router left healthy ON 2.5.24. No commit by this recorder.

- **The kernel-console prep (arm A) - the FIRST own-kernel boot is prepped end to end and the flash phase is QUEUED, not run: the build delta (a `mach-luofu` + our DTB + three config groups) is itemized and NONE of it exists yet, the 8,650,752-B kernel-partition shape is read off the real uImage header, the no-console observation strategy is three ssh-read signals each with its own limit, and the flash/rollback commands are pinned with hashes - all host-side, no device action** (`build/tmp/inta-spec/kprep.md`, task `st_01a114cf`; status block in `opensource/docs/UPSTREAM-PORT-PLAN.md`). THE BUILD STATE: the CI lane `luofu-kernel-config` produces a VALIDATED `.config` (green run `37573150202` on `c40637a` = 47/47 non-`LUOFU` symbols `=y`, the 13 `CONFIG_*_LUOFU` ones the to-do) and its opt-in `kernel` job (`build_kernel: true`, `make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- -j zImage dtbs`) is EVALUATION BOILERPLATE - with no luofu mach and no luofu DTS in the tree the zImage is the vanilla `multi_v7_defconfig` kernel and `dtbs` builds vanilla boards; the delta to a bootable image is (1) `arch/arm/mach-luofu/` (`ARCH_LUOFU`, `DT_MACHINE_START(.dt_compat = "hisilicon,luofu-r116"/"hisilicon,luofu")`) + its `arch/arm/Kconfig` entry, with the SMP op for `enable-method = "hisilicon,hsan_smp"` having no mainline method (`luofu-r116.dts:88-90`) so the first boot goes UP at `maxcpus=1`; (2) our DTB compiled from the expanded 20-node `opensource/docs/soc/luofu-r116.dts` keeping `aliases{serial0/console -> &uart1}`, `chosen{stdout-path="serial0:115200n8"}` and `memory@80500000`; (3) the three config groups - console/earlycon (the console is `uart1@0x1010f000`, `snps,dw-apb-uart`, mainline match `drivers/tty/serial/8250/8250_dw.c`, with the bootargs staying OUT of our DTS because U-Boot passes `console=ttyS0,115200 earlycon ...` and a missed DT lookup needs `earlycon=uart,mmio32,0x1010f000`), clocks (`COMMON_CLK`/`RESET_CONTROLLER`/`MFD_SYSCON` + `CLK_LUOFU` or `CLK_IGNORE_UNUSED`, else the `uart1` APB gate can be turned off at late init and the console goes SILENT - a `no console` that is not a crash), and rootfs mount (the `ubi.mtd=`/auto-attach hook the vendor's `ubi0: attached mtd14 (name "rootfsb")` proves is custom) plus the NEW `MTD_NAND_LUOFU` (`hsan,fmc`, the hardest storage item). THE IMAGE SHAPE, read this session from the real header (LOCAL `gunzip`+sha256 of `dumps/mtd12-kernelb.gz`, NO device): payload `4,294,096 B`, `load = ep = 0x80608000`, `os=5`, `arch=2`, `type=2`, `comp=0 none`, `Linux-5.10.201`, header+payload `4,294,160` = `0x418610` = EXACTLY where the 31,220-B base DTB begins - so the partition's 8,650,752 B is a `mkimage`'d zImage PLUS a DTB tail and writing a bare uImage makes the bootloader SKIP the slot and fall back to A (a `no crash` that reads as a pass); U-Boot patches the DTB at runtime (`bootcmd=mtd read kernel${bootflag} ${loadaddr};bootfip ${loadaddr}`) and packing needs the ARM cross toolchain absent locally, so it belongs to CI. THE THREE SIGNALS (no serial console this phase): (a) ssh-availability timing on a bounded FRESH-answer wait (300 s / 3 s, no fixed sleeps) proves kernel+rootfs+init+net but NOT our kernel - slot A's stock image answers too - so every answer pairs with an identity read (`/proc/version`, `/proc/modules` without the vendor `hi_*` set, the slot pair); (b) pstore - mtd10 `pstore` (`0x40000 @ 0xd40000`) registers too late (7.4 s) for an early panic AND `PSTORE_BLK` `depends on BROKEN` promptless in 5.10.201, so the first boot's instrument is `PSTORE_RAM` + a ramoops `reserved-memory` node (`CONFIG_PSTORE_RAM=y` already in the fragment) read via `ls -l /sys/fs/pstore/`; (c) a userspace sentinel (`S99` hook appending `$(date) $(uname -r) $(cat /proc/uptime)` + `.omo-kboot`, or a line into the mtd10 pstore partition) proves init was reached, by which kernel, and how far - and only that. THE FLASH/ROLLBACK: preconditions read-only (`/proc/mtd` = `mtd12` kernelb / `mtd3`+`mtd4` env / `mtd10` pstore / `mtd14` rootfsb; the slot gate demands `mtd14:rootfsb` + an agreeing `ubi0: attached mtd1[34]`; health `WIPHY=2 IFACE=6 CAL2G=1 CAL5G=1`, `PAT=0 OMO_OFF=0 LEFTOVERS=0`), the calibration snapshot BEFORE any device work, **`scp -O` only** (`cat > file` over ssh corrupted the kernel image twice) with both ends md5, the flash one `mtd erase`+`mtd write` of the 8,650,752-B slice plus a `dd | md5sum` read-back, and the env lever (`env-bootflag-b.bin` into mtd3+mtd4 + `boot_reg 0x21`) whose value map is CONTESTED (`0x10 -> rootfsb`, `0x11 -> rootfsa`, reads back `10` after being set to `11`) so no decision keys on it; ROLLBACK is `build/custom/kernelb-2.5.24-full.img` (8,650,752 B, sha256 `98b11f29...`) and NOT `dumps/mtd12-kernelb.gz`, which this session PROVED byte-identical to `dumps/mtd11-kernela.gz` (both 8,650,752 B, sha256 `039c7877...`, both STOCK) - the 2.5.24 rootfs with an older kernel panics at boot (`The ShuangTa ep device must enable gpio-timing-quirk`), so the stock dump is the wrong rollback for slot B; the stock floor is the `env-bootflag-a.bin` lever + `boot_reg 0x10` + a `mtd13` verification, and UART (ttyS0, 115200 8N1) is the last resort only if BOTH slots are bad (hence exactly ONE slot is ever written). GO gates (seven, all before the flash): image sha256 pinned + host-verified, the full slice not the uImage, a kernelb backup matching `98b11f29...`, the calibration snapshot taken, the read-only slot/health gate passed, the observation loop armed, the rollback commands pre-written; NO-GO if any is unanswered, the box is not on `mtd14:rootfsb`, a vendor module is unloaded, or the state is already unknown. THE QUEUED PHASE'S SHAPE: ONE serial, gate-checked, DETACHED window (watchdog armed before anything is staged) with a single flash -> observe -> decide cycle, and it ends where the router must stay - healthy on 2.5.24 slot B, re-flashing the known-good kernelb and re-probing health in EVERY outcome; step 2 is BUILD STATE FIRST, because a first flash of today's zImage boots vanilla and proves nothing. Hard rules carried: no write of CA `0x400392f0`, no read of the RC misc `0x10161000`, no host read of the ack IAR `0x4016010c`, dword-aligned MMIO everywhere (the unaligned `readw` panicked the box), serial + gate-checked with ABORT on conflict, the take-family's ko staged ALWAYS as `/tmp/wifidrv1.ko`, never `rmmod` a vendor module. This recorder ran NO device action (host-side only, nothing staged) and made NO commit.
- **The upstream arm C (the RC WRITE ARM) - the RC write path is ARMED (a bounded RMW helper + `rc_write_test`/`rc_write_flip`, CI-green, the ko store-census + a capstone disassembly proving the bar), the stage-B no-op census RAN live and came back EXACT (the FIRST-EVER read of the RC reset word `0x14880034 = 0x000ff309` with all four RC0 resets out of reset, and the gate word `0x14880020 = 0x02f8300b` re-confirmed; both written back UNCHANGED, `pre == back`, 2/2 no-op stores, zero state change, `boot_id` unchanged), and the MEANINGFUL write (stage C) stays QUEUED because the design itself ranks it unsafe while the vendor stack holds the RC link UP** (task `st_01a114d0`; evidence `build/tmp/wifidrv1-art/rcwrite/` (`RCWRITE.md`, `RESULT.txt` = `FAIL [rc0-pass-line-2-writes]` pre-fix, `RESULT-verify.txt` = `PASS outcome=CENSUS`, `SELFTEST.txt` = `SELFTEST PASS`, `KO.md5`/`RUN.head.txt`/`rcwrite-{run-raw,dmesg,gate-raw,post-raw}.txt`), spec `build/tmp/inta-spec/rcwrite.md`, smoke report `build/tmp/inta-spec/rcwrite-smoke.md`, status block in `opensource/docs/UPSTREAM-PORT-PLAN.md`, submodule commit `10fdaf5652eb1a459b3e218f84a8679da659a1c5` on `omo/phase22-hccaccept` (the only file touched `opensource/lab/luofu-pcie/luofu-pcie.c`), CI `lab-module-build` run `37576597389` **success** at that head, artifact `luofu-pcie-ko`, ko md5 `4592015ec0abfb439555a871b72c02f1` == the `KO.md5` pin == the staged file, `vermagic=5.10.201 SMP mod_unload ARMv7`). THE CODE: the read-only frame is untouched (a bare `insmod` still performs 0 stores) and the write path is three primitives - `luofu_rc_store()` (the file's ONLY bounded store primitive: refuses `off & 3u` with the dword-alignment bar, refuses past `LUOFU_RC_WRITE_BUDGET = 2 + 3 = 5`, does exactly ONE dword-aligned `writel()` and returns the settle-time read-back), `luofu_rc_rmw()` (the masked one-word RMW) and `luofu_rc_write_same()` (the idempotent write-same) - i.e. the vendor `hi_crg`/`hi_kreset` shape; `rc_write_test=1` = STAGE B, the no-op census on the RC's OWN CRG words (the first read of `0x34` + the `0x20` pre-census, each written back unchanged and read back, `PASS iff back == pre`, 2 stores, fails CLOSED with 0 stores if the RC's own DBI link already reads DOWN); `rc_write_flip=1` = STAGE C, the meaningful write (rank 1 `SET`(deassert) of the RC0 reset bits `0x0c..0x0f`, a one-way liveness; then rank 2 the real flip: assert (`CLEAR`) `apb_rst` -> observe -> deassert (`SET`), `PASS iff post == pre`, 3 stores) admitted ONLY on a QUIESCED RC (its link reads DOWN) and refusing with 0 stores under the live vendor stack; compile gate `LUOFU_RC_WRITE` (default 1, the `LUOFU_CRG_FLIP` pattern), both knobs 0-default and forced-path-only, RC0 only because the CRG words carry both domains' bits, `BUILD_BUG_ON`s over the two offsets + the page, and the CRG page `devm_ioremap`'d on the forced path (a mapping performs no bus access). THE INSTRUCTION-LEVEL PROOF (bar asserted, not assumed): `rcwrite-tools/_storecensus.py` -> `luofu_rc_store` holds exactly 2 real stores - the MMIO store `str r6, [r4]` and the bound's ledger (`add r3, r3, #1` -> `str r3, [r5]`) - while `luofu_rc_rmw.constprop.0` has 0 stores (it funnels into the bounded primitive, and the two instruments were inlined into `luofu_pcie_probe`); `rcwrite-tools/_dis_rcstore.py` -> `.text.unlikely @0x134 size=100` shows the bound compiled in (`cmp r3, #4` / `bls #0x170`, then `dsb st` -> `bl arm_heavy_mb` -> `str r6, [r4]` -> the read-back `ldr r0, [r4]`) with the refusal string `write budget %u exhausted, refusing store at +` LIVE in the ko; the `off & 3u` guard is folded AWAY by the compiler because every call site passes a compile-time-aligned constant (`0x34`/`0x20`), so it survives as a source bar + a `BUILD_BUG_ON` + the runner's source preflight (`--preflight` PASS), and the CI `alignment rule (luofu-pcie)` gate PASSes in-workflow (no `readb/readw/writeb/writew`, no misaligned raw literal - `readl()` is the module's only MMIO op). THE LIVE RUN (ONE serial device action `insmod force_probe=1 rc_write_test=1` -> dmesg -> `rmmod`, detached + gate-checked, ko staged ALWAYS as `/tmp/wifidrv1.ko`, NO reboot, 2026-10-07T05:35:44Z -> 05:35:51Z): the gate's FIRST run ABORTED with NOTHING staged on `GATE_LEFTOVERS=1` = a stale zero-byte `/tmp/omo-t7-hide.done` from the CLOSED take7 lane (a done-flag; `GATE_PAT=0 GATE_OMO_OFF=0 GATE_GUARD=0`, vendor pair loaded -> no active cycle), the SAME inert residue the crgflip / crgstage2 / pciskel-smoke4 receipts removed under precedent - that ONE file was removed and nothing else was touched; the second gate CLEAN at `boot_id=4f8f2940-d1f3-41d7-a61d-67f00de1e41c` (uptime 5887 s), slot `mtd14:rootfsb` (`rom=/dev/ubiblock0_0`, `dmesg_attach=14`), release `2.5.24`, 0 pat/omo-off/leftovers/guard, `wifidrv1`/`luofu_pcie` absent, vendor pair loaded, 2 wiphys, 6 interfaces, cal `[SUCC]` 2g+5g, stock `FIRMWARE.bin` md5 `0e530b976d5a20e87358671f1a577695` at the pin. THE CENSUS, verbatim: `RC_WRITE_TEST[1/2] off=0x34 RC0 reset word pre=0x000ff309 (apb/pcs/phy/ctrl bits 0x0c..0x0f = 1111) store 1/2 = write-same`, `RC_WRITE_TEST[1/2] off=0x34 back=0x000ff309 (no change)`, `RC_WRITE_TEST[2/2] off=0x20 gate word pre=0x02f8300b (pcie0_clk b0x0c=1, pcie1_clk b0x0d=1) store 2/2 = write-same`, `RC_WRITE_TEST[2/2] off=0x20 back=0x02f8300b (no change)`, `RC_WRITE_TEST PASS: pre34=0x000ff309 back34=0x000ff309 pre20=0x02f8300b back20=0x02f8300b, 2/2 no-op stores, 2 stores total`, `RC_WRITE_TEST rc=0`, `RC_WRITE after: crg[0x20]=0x02f8300b crg[0x34]=0x000ff309 (2 stores total)`, `FORCED probe PASS: dbi 3 predicted regs matched, cfg 4 matched, link DOWN, 2 writes` (the rc1 half printed `the RC write path runs on RC0 only (the CRG words carry both domains' bits); skipped`, same 2 writes). THE FINDING: the RC's reset word `0x14880034` is READ here for the FIRST time in this line and reads `0x000ff309` - all four RC0 resets (`apb/pcs/phy/ctrl` bits `0x0c..0x0f`) read 1, i.e. out of reset, exactly as a vendor-held RC must - and the `0x20` gate pre-census re-confirms `0x14880020 = 0x02f8300b` with BOTH RC clock gates set (`pcie0_clk` b`0x0c`, `pcie1_clk` b`0x0d`); more important than the data is that the RC's own STORE bus does not abort (2 dword-aligned stores, no fault). THE RESTORATION: the instrument IS a strict write-same (each store writes the word's own `pre` back), so both words are bit-for-bit unchanged and restored state == as-found state (`crg[0x20]=0x02f8300b`, `crg[0x34]=0x000ff309`), zero state change, exactly the design's 2-store budget, no `write budget ... exhausted` refusal. THE MEANINGFUL WRITE (STAGE C) IS QUEUED, NOT RUN: the task gate says proceed only if the no-op is exact AND `rcwrite.md` ranks the meaningful write safe-with-the-vendor-live, and `rcwrite.md` sec 2b/sec 3 Stage C ranks it NOT safe vendor-live - it needs a QUIESCED RC (link DOWN) - so the knob was left at 0 and would have refused with 0 stores anyway, because the live RC's own link reads UP (`dbi+0x082 = 0x7012`, `DL_ACTIVE=1`, DWC LTSSM `0x728 = 0x11` L0); the state-changing store is one CLEAR away from a wedged DWC link, and the gate/reset is owned by the vendor's `hi_clk`/`hi_kreset` refcounts (`lsmod hi_clk .. 21`) so an out-of-band clear is INVISIBLE to the framework and nothing re-enables it - only a watchdog/reboot recovers (the `crgnext.md` sec 3 rank 5 note). THE HONEST ORDERING NOTE: stage A's class question (is the CRG reset class reversible at all?) is already answered by the crgstage2/crgflip receipts (the reset class honours BOTH directions: `0x2c` b`0x18` `i2c0_rst` cleared then restored EXACTLY) while the `0x14`/`0x20` GATE class is SET-ONLY, so the RC's `0x34` reset bits - unlike its `0x20` clock gates - are the class a real driver can program both ways. THE RUNNER DEFECT FOUND AND FIXED (host-side, NOT the module): the verifier's `rc0-pass-line-2-writes` literal required `link UP` on the rc0 PASS line, so the otherwise-exact run first came back `RCWRITE RESULT: FAIL [rc0-pass-line-2-writes]`; the literal is WRONG because the driver's summary prints `link_up = report_link(dbi) & report_link(cfg)` and live rc0 has DBI UP (`0x7012`) with the endpoint `cfg` DOWN (`0x1012`) -> `link DOWN`, identical to the prior live pciskel run (`link DOWN, 0 writes` for rc0) with only the store count moved (0 -> 2); the literal was corrected to `link (UP|DOWN), 2 writes`, the fixture's rc0 line made faithful (`link DOWN`), and a HOST-ONLY `--verify` mode added so the captured bytes were re-verified with no device contact (`--selftest` PASS A-G, `--verify` -> `PASS (outcome=CENSUS)`); the live `RESULT.txt` still records the pre-fix FAIL and `RESULT-verify.txt` records the corrected PASS (a gitignored-runner literal fix - the crgwrite-smoke sec 0 class - NOT a change to the module or to the fetched ko). THE HEALTH (read-only probes, `boot_id` UNCHANGED - NO reboot): `POST_BOOT=4f8f2940-...` (same), `POST_WIPHY=2 POST_IFACE=6 POST_CAL2G=1 POST_CAL5G=1 POST_LUOFU_PCIE=0 POST_VENDOR_WIFI=1 POST_VENDOR_PLAT=1 POST_OMO_PAT=0 POST_LEFTOVERS=0 POST_MTD_NUM=14`, `RMMOD_RC=0 LUOFU_AFTER_RMMOD=0 STAGED_LEFT=0 RUN_DONE`, the follow-up probe reading `rev=2.5.24 wiphy=2 iface=6 cal=1/1 luofu=0 wifidrv1=0 vendor_wifi=1 vendor_plat=1 mtd=14 tmp_omo=0 tmp_ko=0 guard=0`, NO kernel fault in the capture (no `Unable to handle`/`Oops`/`BUG:`/`Call trace`/`Kernel panic`, no `INSMOD_RC=124`), so the router is left HEALTHY on 2.5.24: 2 wiphys, 6 interfaces, cal `[SUCC]` both bands, `mtd14:rootfsb`, 0 leftovers, 0 guard, the staged ko removed. WHAT REMAINS: (1) Stage C (the meaningful write) only in a quiesced/takeover context where the RC's own link reads DOWN - the knob and its bound are already committed and gate-checked, so it is a one-command re-run, not new code; (2) the RC's own next stage is the FROM-SCRATCH host controller (iATU programming, LTSSM, `cfg` accessors) - the write path is now armed FOR it, i.e. the RC no longer owes a measurement, only the driver; (3) the `luofu-crg` synthetic `platform_device` `.release` fix (else `platform_device_unregister()` warns at `drivers/base/core.c:1836` on every unload, needing a CI rebuild) and the `reset_controller_dev` the CRG driver still owes; (4) the `0x2c`-class reset instrument (`crgnext`) stays prepared and queued on its own lane. Hard rules held this lane: CA `0x400392f0` never written; the RC `misc` window `0x10161000`/`0x10165000` never read or mapped (the ko carries `0x10161000` only as a `%lx` argument and its own line says `misc mapped WRITE-ONLY (frame, 0 writes)`); the host-side IAR `0x4016010c` never read; dword-aligned accesses only; no PLL (`0x198`/`0x1e0`), mux (`0x138`), softrst (`0x84`), watchdog (`0x50`/`0x64`/`0x70`) or reboot (`0x00`) register; THE BOUND mandatory (the module's own counter, `LUOFU_RC_WRITE_BUDGET = 5`, self-terminating with no loop and no sweep); the device action serial + gate-checked (health + SLOT CHECK `mtd14:rootfsb` + no active cycle, ABORT on conflict); ko staged ALWAYS as `wifidrv1.ko`; push authorization used ONLY on the submodule branch `omo/phase22-hccaccept`, never `master`; the router left healthy ON 2.5.24. No device action by this recorder, no commit.
- **The first own-kernel window - the FLASH PHASE IS QUEUED and the window ABORTED: a truthful NO-GO, not a flash** (worker task `st_01a1151b` + verifier `st_01a1151d`; receipts `build/tmp/kboot/` (`kboot-GONOGO.txt`, `kboot-candidate.txt`, `kboot-gate-raw.txt`, `kboot-rollback-source.txt`, `kboot-final-health.txt`), verdict `build/register-dumps/diffs/20261007T0648Z-vkboot/verdict.txt`, spec `build/tmp/inta-spec/firstkboot.md`, prep `kprep.md` sec.3-4, gate pass `gogate.md`). THE HEADLINE: the port's first own-kernel boot is still OWED, because the CI candidate cannot fit the partition and the runner FAILED CLOSED with ZERO device mutation - this window was never a flash, and the negative IS the result. THE GATES (all evaluated live, read-only): `G1 kernelb backup exists + matches live mtd12 ... GO`; `G2 device healthy on slot B ... GO` (`WIPHY=2 IFACE=6 CAL2G=1 CAL5G=1 PAT=0 OMO_OFF=0 LEFTOVERS=0 GUARD=0 LUOFU=0 WIFIDRV1=0`, vendor pair 1/1, `STOCK_MD5=0e530b976d5a20e87358671f1a577695`, `bootflag=b`); `G3 boot recipes (boot_reg 0x21 + env mtd3/mtd4) ... GO`; `G4 observation tooling (ssh-timing + pstore + sentinel) ... GO`; `G5 rollback ready ... GO`; the slot gate `PASS  mtd_num=14 name=rootfsb dmesg_attach=14 rom=/dev/ubiblock0_0`; `no active cycle: PASS  (ps witness empty)`. THE DECISIVE NO-GO, verbatim: `kernelb mtd12 = 0x00840000 = 8,650,752 B            (live /proc/mtd)` against `candidate luofu-uImage      = 10,142,272 B  -> +1,491,520 B over` and `required slice (uImage+DTB) = 10,153,079 B  -> +1,502,327 B over`, so `kprep.md` sec.4 gate `(2) the image is the full 8,650,752-byte slice ........... **NO-GO**`; the escape hatch is closed by a repo-wide scan - `A repo-wide scan found NO luofu kernel image <= 8,650,752 B: the only 8,650,752 B images are the two 2.5.24 rollback files (= the current live kernelb)` - and the CI lane says the same in its own step (`luofu-kernel-config.yml` "kernelb slice arithmetic (does this image fit?)" -> `::warning:: the image does not fit kernelb`). WHY THE SHAPE GATE IS THE RIGHT PLACE TO STOP: `kprep.md` sec.3.2 requires the uImage+DTB slice because a bare uImage (or a bare zImage) makes U-Boot's `bootfip` skip the slot and silently fall back to A (`FLASH-PLAN.md`), i.e. a truncated write yields a "no crash" that is not a result and may leave kernelb corrupt. THE DECISION, verbatim: `DECISION: **ABORT the flash.** Fail closed per the HARD RULES. No device mutation was performed: nothing staged, no mtd erase, no mtd write, no env write, no boot_reg write, no reboot.` The verifier write-scanned the run's own probes (`gate.sh` / `final-health.sh` / `pstore-check.sh`) and found every line a read (`cat`, `ls`, `sha256sum`, `dd if=/dev/mtd12`) plus two `fw_printenv -n bootflag` reads - there is NO `mtd write`, NO `flash_eraseall`, NO `echo ... boot_reg`, NO `reboot` anywhere in the scripts. THE BACKUP AND THE ROLLBACK: verified READY BEFORE any (non-)write - host `build/custom/kernelb-2.5.24-full.img  size=8650752  sha256=98b11f2960da6fb4772407c52a46feb9a1934b764966ed121505dbf3d55fea2d` and device `dd if=/dev/mtd12 bs=4096 count=2112 | sha256sum` returning the SAME `98b11f29...` (`MATCH: True`), with the stale stock dump `dumps/mtd12-kernelb.gz = STOCK 039c7877...` named and EXCLUDED (a stock kernelb under the 2.5.24 rootfs is the wrong pairing); the rollback was NOT needed and NOT executed because kernelb was never touched, and it stays ready for the next window. THE END STATE: `FINAL_BOOT=4f8f2940-d1f3-41d7-a61d-67f00de1e41c   (unchanged from the gate - no reboot)`, `FINAL_SLOT=14:rootfsb`, `FINAL_WIPHY=2 FINAL_IFACE=6 FINAL_CAL2G=1 FINAL_CAL5G=1`, `FINAL_VENDOR=2 FINAL_OMO_OFF=0 FINAL_WIFIDRV1=0`, `FINAL_BOOTFLAG=b`, `FINAL_STAGED_KERNELB=0`, `FINAL_KERNELB_SHA=98b11f29... (== live mtd12, unwritten)`, `=> NO new pstore record, NO new kernel fault, NO reboot, NO leftovers. Device HEALTHY on 2.5.24.` THE BRANCHES THE WINDOW DID NOT TAKE, named honestly: the BOOT branch is NOT ATTEMPTED (`firstkboot.md` sec.3: `There was no boot to observe. Steps (1) stage, (2) flash, (2b) DTB tail, (3) boot slot B, (4) the bounded observation loop were all skipped - a boot of an unwritten/truncated kernelb proves nothing and risks stranding the router.`), so all three prep signals (the ssh-timing identity read, the pstore/ramoops record, the userspace sentinel) read N/A; the ROLLBACK branch is verified-ready and unspent. WHAT REMAINS: ONE number moves the window from ABORT to GO - the `uImage + DTB` slice must land at or under 8,650,752 B - and that is a BUILD-LANE job (a trimmed config, or an image that drops what the box never reads), not a flash-window job; the acceptance is already encoded in `gogate.md`, so the re-run is an artifact swap once CI emits a candidate that fits, in the same single serial, gate-checked, DETACHED shape this window's sibling describes (the watchdog armed before anything is staged, the backup verifying before any write, the flash touching `/dev/mtd12` kernelb ONLY, the rollback pre-written with hashes, the box ending healthy on 2.5.24 slot B). BOUNDS, declared: (1) the window proves a NEGATIVE and the negative IS the result - nothing was flashed and nothing booted, so nothing about our kernel on this SoC has been measured yet; (2) `build/tmp/kboot/` carries TWO CI stamps - the pinned `70e46d4` candidate (`zImage 6f04a5a3...`) and an EARLIER sibling under `run-37578879647/` (`efdab959`, `zImage ff97a3cc...`) - and both zImages are 10,142,208 B and both overflow kernelb, so the ABORT holds either way (the verdict names this as D1); (3) the receipts live in gitignored local state rather than a `build/register-dumps/exp/<TS>/` dir, disclosed for a later auditor. Hard rules held by the window AND its verifier: CA `0x400392f0` never written; CA `0x40039af0` never written; the host-side IAR `0x4016010c` never read; the RC misc `0x10161000` never read; no device cycle run by either; NOTHING staged, erased, written to mtd, written to env, written to `boot_reg`, and no reboot; the backup verified before any flash; the flash would have touched `/dev/mtd12` (kernelb) ONLY; the rollback stayed ready; ko staged ALWAYS as `wifidrv1.ko` (no ko in this window at all - it is a kernel lane); push authorization used ONLY on the submodule branch `omo/phase22-hccaccept`, never `master`; the router left healthy ON 2.5.24 slot B with `kernelb` sha256 `98b11f29...` unwritten. No device action by this recorder, no commit, no push.
- **The slot restore - the vendor sysupgrade put STOCK 2.5.24 into the inactive slot and rebooted onto it: the box is back on the stock pair, slot A on stock 2.4.15 and slot B on stock 2.5.24 with its own factory `kernelb` (`98b11f29...`) UNTOUCHED, the custom rootfs is gone, and the box ends healthy** (record `build/tmp/slotrestore/restore.md`, task `st_01a1155b`; recipe `build/tmp/slotrestore/recipe.md`; verdict `build/register-dumps/diffs/20261007T0822Z-vrestore/verdict.txt`, task `st_01a11573`, C1-C4 CONFIRMED with C5 UNAVAILABLE; full record `opensource/docs/phase49/gic-view.md` ADDENDUM 35, `opensource/docs/phase49/README.md` ADDENDUM 32). THE FLOW, one serial sequence through the vendor's OWN code path: login to `/cgi-bin/luci/admin/wizard` (the double-sha256 `luci_password = sha256(sha256(plain+salt)+token)`), upload the `.bin` to `/cgi-bin/luci/admin/system/upgrade`, then `sysupgrade -T /tmp/fw.bin` (`"firmware verify ok"`, RC=0) and `/sbin/sysupgrade /tmp/fw.bin` (`"Commencing upgrade. Closing all shell sessions."`); the recipe states the UI's own reboot/apply button issues the identical flow, both through `/lib/upgrade`. Flash requested `2026-10-07T08:05:16Z`, pre-state `boot_id ec1ab9e0-f402-49ec-8634-53eb6a964014`, `rom_version 2.4.15-20251030-114751`, `bootflag=a`, `mtd_num=13` (rootfsa), `WIPHY=2 IFACE=6 CAL2G=[SUCC] CAL5G=[SUCC]`, `.omo-off=0`, staged ko 0. A UI repair was a PRECONDITION, not a side effect: every `/cgi-bin/luci` path returned HTTP 500 `module 'bdinfo' not found` because an earlier session's overlay shadowed the stock LuCI tree with an incomplete 2.5.24 copy, so 26 files were restored from `/rom` after backing the tree up to `/tmp/omo-luci-bak/luci.tgz` (tmpfs, so the repair is no longer reversible from the box). THE RECEIPTS: the upload's own confirm view quotes `MD5: bc40580943e8a9865bb8288d3294f687` and `Size: 21.00 MB (22024351 B)`, and the verifier re-hashed the host image itself (sha256 `ded2d835...2f72`, md5 `bc405809...`, 22,024,351 B); the device's own syslog holds exactly ONE boot log and attaches the OTHER rootfs, `ubi0: attached mtd14 (name "rootfsb", size 23 MiB)` where the pre-slot was mtd13 `"rootfsa"`, with the in-boot `boot_reg` mirrored the other way (`10 -> 11` against the old slot's `11 -> 10`); `/etc/rom_version` and the live UI footer both read `2.5.24-20260727-122111`, and `/www`'s Last-Modified moved from 30 Oct 2025 to 27 Jul 2026. SLOT A'S BOOK-KEEPING, stated precisely: slot A carries STOCK 2.4.15 again because a wrong-slot boot earlier in the day had attached mtd13 and the mechanism writes the slot opposite the RUNNING flag; its rootfs was never erased, so the box holds the stock 2.4.15 rootfs it booted on, on slot A, while slot B's factory `kernelb` was never touched and the custom 2.5.24 rootfs is gone. THE GATE THAT COULD NOT BE READ: the restored slot does not listen on port 22, so `/proc/sys/kernel/random/boot_id` was UNREADABLE post-flash and the ssh health probe could not run either; the reboot is carried by convergent indirect witness (the ssh session reset at `08:05:17Z`, the release change 2.4.15 -> 2.5.24, the release-dependent `/www` mtime, a ~12-minute uptime, a single fresh boot log, the slot switch mtd13/rootfsa -> mtd14/rootfsb), and the verdict files that as a precision gap in the GATE, not in the outcome. WHAT IT WAS NOT: no lab cycle, no ko staged, no devmem, no register window, no bound to trip; the restore used the vendor's own mechanism on a verified image and the rollback (boot the other slot) is inherent to the slot pair. HEALTH: 4 hostapd vaps `AP-ENABLED` (vap0/vap3/vap8/vap11), `alg:[SUCC]` x14, `netlink_info_cnt:6`, no `.omo-off`, box live on 80/443, stock `FIRMWARE.bin` md5 `0e530b976d5a20e87358671f1a577695` unchanged; the device ends HEALTHY on stock 2.5.24. HARD RULES HELD by the restore, its verifier and its recorder: CA `0x400392f0` never written; CA `0x40039af0` never written; the RC misc `0x10161000` never read; the host-side IAR `0x4016010c` never read; the device action serial and gate-checked; nothing staged as a module (the subject is a firmware image); the recorder ran NO device action of its own (the restore did the one reboot, flash-gated), no commit, no push. NEXT (one line): when the port lane 2.5.24 is back with ssh, read `/proc/sys/kernel/random/boot_id` and compare it against `ec1ab9e0-...` - that single read turns the gate into a plain CONFIRMED without re-flashing anything.

- **The custom-bin restore - the prepared image is VERIFIED and the vendor UI REFUSES it at its RSA gate: `omo-custom.bin` is CONFIRMED as the 2.5.24 container shape carrying the 0.3 rootfs on the stock 5.10.201 kernel, the upload leg works (the UI's confirm block quotes our own `MD5: 83745b6db1524cb94b565fa227a21d83` and `Size: 21.13 MB (22155423 B)`), the apply leg is refused by `oem-check` (`rsa_verify: rsa verify failed: -1`, the unchanged stock RSA-2048 block at 0x80000), no write reaches a partition, no reboot, and the box ends HEALTHY and unmodified on stock 2.5.24** (builder task `st_01a115bc` + adversarial verifier `st_01a115c9` + UI attempt `st_01a115cb`; build `build/tmp/custombin/build.md`, verdict `build/register-dumps/diffs/20261007T0955Z-vbin/verdict.txt` (C1-C3 CONFIRMED, one defect R4 named and bounded), attempt record `build/tmp/custombin/flash.md`, driver `build/tmp/custombin/ui.sh`, captures `build/tmp/custombin/rcpt/`, full record `opensource/docs/phase49/gic-view.md` ADDENDUM 36, `opensource/docs/phase49/README.md` ADDENDUM 33). THE ARTIFACTS, pinned: container `omo-custom.bin` 22,155,423 B sha256 `5ee732d6...b086ce` = the stock 22,024,351 B plus exactly one PEB (+131,072 B, the 0.3 squashfs is one LEB larger), raw volume `omo-custom.ubi` 16,646,144 B sha256 `94bf00c0...` (the `ubiformat` vehicle), and demux payload `omo-custom.pkg` 21,627,513 B md5 `77dbc0e59aa8d7040f07768ffcc119c9`; the build writes the UBI volume by hand (`mkcustombin.py`, no `ubinize`/`mksquashfs`/`unsquashfs` in the repo) from the re-measured stock geometry and its self-test re-derives the stock UBI byte for byte. THE VERDICT: C1 the container keeps the 2.5.24 shape - `[0:0x4A2C94]` and `[0x1462C94:]` stock-identical except nine FIT/descriptor bytes and four `hash@1` bytes, each exactly what the +131,072 move forces (`totalsize` 0x014807ac -> 0x014a07ac, `size_struct`/`off_strings`/`data` length each +131,072, descriptor UBI size 0x00fc0000 -> 0x00fe0000 = 126 -> 127 PEB, descriptor CRC 0xc423aa02 -> 0xda0ad29a, `hash@1` @0x1500b74 -> @0x1520b74 0x6e93800e -> 0x8d7f5ce1) with both CRCs recomputing to their stored fields; C2 the extracted squashfs is the 0.3 rootfs (15,751,790 B sha256 `1f59bddf...ced2a`, the marker `/etc/custom-firmware-version = omo-minimal-0.3 stock-2.5.24-20260727-122111` and the ssh layer `init.d/omosshd` + `S95omosshd` + `config/dropbear` + two `authorized_keys` + an md5-crypt root hash, all ABSENT from stock, the control); C3 the kernel slice is the stock 5.10.201 uImage at 0x080E5C (4,292,080 B, load = ep = 0x80608000), zero kernel bytes in the diff; the ONE defect is R4, the unchanged stock RSA-2048 block at 0x80000, which fails `oem-check` by construction since no Cudy private key exists here - not a build fault. WHAT THE UI DID: login 302 + `sysauth`, the upload ACCEPTED (the browser multipart shape needs `cbid.upgrade.1.firmware.upload=true`; without it the file is dropped - reproduced, then fixed), Proceed 200 + `X-CBI-State: 1` + `File is invalid. Please retry.` where the genuine image returns 302 to the reboot page, and the syslog names `rsa_verify: rsa verify failed: -1`; a failed check returns before `image_demux`, so nothing staged a write. WHY THE SHELL-FREE BYPASS IS CLOSED, MEASURED not argued: the upgrade model deletes `/tmp/upgrade_check_done` on EVERY upload (`decomp/auditB/model__cbi__system__upgrade.lua.txt`), proven live (a stock upload then Proceed gives 302 and the sentinel persists through a second Proceed; the custom upload removes it and Proceed gives 200 + `File is invalid`), and the payload can only reach `/tmp/firmware.img` through an upload, so sentinel and payload cannot coexist over HTTP; out of band, port 22 is closed and the authenticated `systime` injection is INERT on 2.5.24 (`'; touch /www/omo-rce-test; #` -> 200, marker ABSENT, matching the gist and `PLAN-UART.md`). HEALTH: 4 hostapd vaps `AP-ENABLED` (vap0/vap3/vap8/vap11), `alg:[SUCC]` x14, 6 netdevs, no `.omo-off`, nothing staged as a module, live on 80/443 (`Firmware Version 2.5.24 US`); the recorder's ONE device interaction was a read-only HTTP health probe (`LOGIN-OK`, `http:200`), no commit, no push. HARD RULES HELD by the builder, the verifier, the attempt and the recorder: CA `0x400392f0` never written; CA `0x40039af0` never written; the RC misc `0x10161000` never read; the host-side IAR `0x4016010c` never read; the device action serial; nothing staged as a module (staged ko 0). NEXT (one line): get a shell on the restored slot (the port lane's access layer, NOT this container), then `touch /tmp/upgrade_check_done` and `sysupgrade /root/omo-custom.bin` (or `ubiformat /dev/mtd13 -y -f omo-custom.ubi`), switch the slot and boot - the payload the vendor writer parses is already prepared as `omo-custom.pkg`.


- **The decode run (the TR6560-cousin night, 2026-10-09 UTC) - PLATFORM RESOLVED, EIGHT LANES PASS, and the guard boundary NAMED but not closed: our Cudy WR3000 v2 is TR6560-class Triductor/HiSilicon silicon, the Banana Pi THG6500-TAX2 BSP is the cousin-chip open-source stack, every SoC-identity node lands on the same MMIO address in both device trees, the pre-entry refusal is the DTBO/overlay container magic at `fdt_end` and NOT any checksum on the u-boot boot path, and the z[0x20..] content check stays UNRESOLVED** (report `opensource/docs/phase42-decode/report.md`, verdict `build/tmp/bsp-notes/verify/VERDICT.md` with `reexec-*.out.txt` beside it; lanes tailblob `st_01a11ce1`, bootblob `st_01a11ce2`, drivdiff `st_01a11ce3`, ubootguard `st_01a11ce4`, dtscmp `st_01a11ce5`, flashinfo `st_01a11ce6`, GPL letter, BSP CI; independent verifier `st_01a11ced`; NO device action, NO ko, NO commit). THE PLATFORM: our base DTB (`build/tmp/uboot-art/vendor_base.dtb`, sha256 `947ec62d...`, 176 nodes, root `compatible = "hsan-luofu"`) and the BSP trees (`triductor-tr6560.dtsi` 49 nodes, `THG6500-TAX2.dts` 16) share one memory map - GIC `0x10181000`/CPU iface `0x10180100`, SCU `0x10180000`, L2 `0x7f000000`, TWD `0x10180600`, SP804 `0x10104000`, UART0/1 `0x1010e000`/`0x1010f000`, FMC `0x10a20000`, PCIe RC/EP `0x10160000`/`0x10164000` (config `0x10161000`), GPIO `0x10106000`/`0x10107000`, sysctrl `0x10100000`, CRG `0x14880000`, iomux `0x14900000`, tvsensor `0x14900500`, flashinfo reserve `0x80600000` - Cudy names it `hsan,`, the BSP names it `tri,`, same addresses throughout, Cudy describing a superset (176 nodes vs 49+16) with the five `hsan,mac` gemac blocks, `lsw_dp`/`lsw_pfe`, `ledpwm`, `jent-rng` and the efuse family absent from the BSP (`build/tmp/bsp-notes/dtscmp/delta.md`). THE BSP: cloned at `build/tmp/bsp` from `https://github.com/BPI-SINOVOIP/THG6500-TAX2-OPENWRT-BSP.git` at `daeb1eab`, OpenWrt 22.03 for `target/linux/tr6560` with `DEVICE_THG6500-TAX2` in its committed 284002-B `.config`; the CI lane `bsp-tr6560-build.yml` parses as YAML, is `workflow_dispatch`-only, `runs-on ubuntu-22.04`, 9 steps, and its build step's `.config` assumption holds. THE WIFI STACK: our `hi5622v100_wifi.ko`+`hi5622v100_plat.ko` and the BSP's `peanut_wifi.ko`+`peanut_plat.ko` are ONE HiSilicon/Triductor HCC family (`hmac_*` 1403, `wal_*` 677, `mac_*` 304, `alg_*` 162 shared; platform `oal_*` 155, `hcc_*` 73, `pcie_*` 72), differing in kernel identity (`vermagic=5.10.201` vs `5.10.138 SMP preempt`) but keeping the same module contract, and `credit`/`mbox`/`mailbox`/`doorbell` are ZERO in all four `.ko` (`build/tmp/bsp-notes/drivdiff/map.md`). THE GUARD BOUNDARY (carried from the boot-matrix night, on `build/tmp/kboot/mtd12-pre-2415.bin`, sha256 `64ae2ffa...`): `z[0x00-0x1f]` is FREE, `z[0x20..]` is GUARDED, the content verification is REAL, and the MECHANISM IS UNRESOLVED. WHAT THE NIGHT DID FIND: the pre-entry gate is the DTBO/overlay container check in `FUN_800743ec` (file `0x343ec`) which requires magic `0xd7b7ab1e` (literal at file `0x34668`) at `fdt_end`; only the three vendor-content images carry it there while every refused candidate carries its own plain FDT magic `0xd00dfeed` (or `past-end`); the kernel entry is taken ONLY when the applier returns 0, else "boot apply overlay fail" and no jump (`build/tmp/bsp-notes/ubootguard/hunt.md`). EVERY verify-shaped primitive is OFF the boot path: the uImage hcrc/dcrc verifier `FUN_80042830` NOT reachable from `FUN_800736dc`, two SHA-1 engines NOT reachable, RSA-verify `FUN_80069eb8` recovery-only, three CRC-32 tables and the FIT hash verifier all NOT reachable, and SHA-256 `0x6a09e667` / AES sbox absent from the image entirely; `dcrc20.bin` carries a deliberately wrong `ih_dcrc` AND the plain `0xd00dfeed` at the container offset, so a data-CRC check cannot be what refused it. THE TAIL: a 628-byte (`0x274`) obfuscated structure at file `0x42258c` (even offsets `0xCC`+-bits, odd `0x66`+-bits, i.e. a 2-byte-repeating XOR key to first order), followed by a 4315136-byte `0xFF` run to the partition end; the SAME code round-trips the uImage's own `hcrc 112cee61`/`dcrc cf4ae686`/`size 004185d0` byte-for-byte, yet across 8 decode models it finds ZERO fields matching any crc32/crc16/sum/md5/sha1/sha256 of any covered range (`build/tmp/bsp-notes/tailblob/decode.md`). THE LIVE CROSS-CHECK CAME BACK UNRELATED: a read-only 16-KB `/dev/mem` capture of `0x80600000` (`live-80600000-16k.bin`, sha256 `823631c5...`) shares ZERO 8-byte and ZERO 16-byte sequences with the mtd12 tail slice, is ARM `.text` (14374/16384 nonzero, 0 strings), and does not even contain the plaintext word `devmem` returned at the same address (`cc66cc76` absent), so the expected mirror does not exist (`build/tmp/bsp-notes/flashinfo/dump.md`). THE BOOT CHAIN HAS A NAMED STAGE: the BSP's `TR6560-bootimage_nodtb.bin` is a 69625-B bootram at base `0xc0030000` whose LZMA1 stream at `0x19c8` unpacks to exactly 148000 bytes (sha256 `c4e4aeb4...`) and stages the next stage at `0x80600000`; that second stage carries the whole SDK command set (`load_boot`, `load_image`, `rcs`/`ccs` A/B flag, `reg_write`, `setup_boot_atags`, `tri_bootm_linux`) (`build/tmp/bsp-notes/bootblob/analysis.md`). THE GPL LETTER: `JETON-GPL-EMAIL.txt` was rewritten (4905 B) so it names the vendor `/lib/hisilicon/ko` modules (`hi5622v100_wifi.ko`/`hi5622v100_plat.ko` plus the platform/clock/reset/efuse/flash/acp/kipc/kcfe families), the `/lib/firmware/hi_wifi` files, the esbc+U-Boot boot chain with both U-Boot slots, and the private `luofu_V200` target; the verifier re-listed the real rootfs (58 modules, 14 `hi_kcfe_*`) and confirmed every named module exists, so the task's deviation hunt FAILED to find a bad name - but the letter's own CHANGELOG carries a false "rootfs unavailable" caveat, a false "all names appear in tracked text" claim (0 occurrences for `hi_basic.ko`/`hi_crg.ko`/`hi_efuse.ko`/`hi_flash.ko`/`hi_acp.ko`/`hi_kipc.ko`), and a Wi-Fi license over-claim (only `hi5622v100_plat.ko` carries the literal `GPL v2`; `hi5622v100_wifi.ko` carries `GPL`). OPEN ITEMS (nothing UNVERIFIED or FAIL at lane level): the z[0x20..] inspecting code is unnamed (runner-up: the kernel-side self-extractor/gzip CRC); the tail's meaning; the `0x80600000` relationship now disproven as a mirror; the Ghidra reachability verdicts and the bootblob 615-function count NOT re-executed; the second u-boot build at `C:/Users/ShibbityShwab/AppData/Local/Temp/uboota.bin` (md5 `3d942555...`) uninspected; the mtd0 esbc blob (`build/tmp/uboot-art/esbc`) undisassembled as the one place a hardware trust chain could hide; the device-side experiment logs never written to the repo. NEXT (one line): find the z[0x20..] check on the kernel side, then disassemble the esbc blob before declaring the u-boot side exhausted.


## 2026-10-09 - THE GUARD DECODED; OUR KERNEL'S FIRST INSTRUCTION RAN (fires fixed2/fixed4)

The night's matrix + a fresh look at the loader's decompile found THE GUARD: the bootfip's last
pre-jump check is FUN_800743ec (the DTBO applier) requiring 0xd7b7ab1e at
fdt_end = 0x40 + ih_size + dtb_totalsize - a container header (magic + total 0x2588 + two
{off,size} DTBO entries, container-relative) that the vendor's slice carries in a 0x60-byte gap
after the main DTB. Every hand-built image since the piggy put d00dfeed there and was refused
before entry; the ZGC booted because it preserved the region. NOT a content verifier.

Fires (protocol: full-partition write, [0x418610..] vendor-verbatim, only [0:0x418610] replaced
by [their uImage header + the vendor's decompressor prefix z2 + payload]; env a-pair + reg 0x10 +
C18 sentinel):
- fixed2 (= their prefix + the head crumb 0xC0DE0008 + OUR single-block xz stream + pad + our
  u32): C18 = 0xC0DE0008 -> the vendor decompressor ran within OUR stream.
- Host proof (xz-embedded userspace/boottest + a 16MB harness = the kernel's own
  decompress_unxz): our stream (single-block and the 4-block MT default) and the exact padded
  boot input all decode ret=0. xz 5.8 auto-MT block split exonerated; -T1 used for fidelity.
- fixed4 (= the CI v9 image with the new stext crumb 0xC0DE0004, kernel-tree.patch): C18 =
  0xC0DE0004 -> THE DECOMPRESSED KERNEL'S FIRST INSTRUCTION EXECUTED. chain proven:
  loader -> container -> their prefix -> our stream -> handoff -> our kernel.
- GAP: stext fires, mach crumbs (0xC0DE0001/0002/0003) do not -> death between stext and
  .init_early. v10 pushed (9b17257): 0xC0DE0005 after __create_page_tables (pre-MMU, raw physical
  store), 0xC0DE0006 as __mmap_switched's first instruction (first post-MMU; mapping probe -
  the early page tables probably do NOT cover 0x10100C18, so a fault there is itself the datum).

Evidence: build/tmp/bsp-notes/ubootguard/hunt.md (the guard decode), build/tmp/xzem (decoder
harness + mytest.exe), build/tmp/kboot/{fixed2,fixed3,fixed4}-full.bin, make-fixed4.py,
fire-fixed4.sh, ci-37832374733/ (v9 artifacts).


## 2026-10-09 - THE OWN KERNEL BOOTS ON THE HARDWARE (C18=0xC0DE0020)

The full ladder fired, live: stext -> __vet_atags -> __fixup_smp -> __fixup_pv_table
(after TEXT_OFFSET=0x608000) -> __create_page_tables -> proc-init -> __enable_mmu ->
last pre-MMU insn -> MMU ON -> __mmap_switched -> start_kernel -> setup_arch ->
init_early (0001) -> init_machine (0002) -> THE WATCHDOG DISARM (0003) -> early_initcall
(0010) -> late_initcall (0020). The box then panicked on the missing rootfs and the bootreg
machinery failed over to the vendor by itself (~100 s). No dance needed.

Two walls on the way were MY OWN breadcrumbs, not the kernel:
- 0xC0DE0006 stored to IO post-MMU (unmapped early) - removed.
- 0xC0DE0005 clobbered r4 (the __create_page_tables output the TTBRs are built from) -
  moved to r5/r6; that fix booted to 0020.
The one real kernel-side wall was TEXT_OFFSET: the SoC's kernels link at 0x80608000 (above
the 6 MB napt reserve); mainline's 0x8000 made the PV delta 0xC0600000 (16MiB-unaligned).
CI: instrumented head files now travel as whole-file copies; the patch is 3 stable sections.

NEXT: the NAND/MTD driver + UBI for a real rootfs, then the Wi-Fi driver, then persistence.

### 2026-10-09 (later) - the mcr-transition lottery (the current frontier)

The 0020 boot landmark is reproducible (the 6d904f5 binary fires 0020 on demand), but
ANY small content change (the NAND stack, a 50-byte string) flips some builds to 0017:
death at the MMU-enable. Fresh instruments (C18 poisoned per fire; RAM captures at
0x80600F00, below the vendor kernel's span) prove: the pre-mcr block runs in full with
canonical inputs (r0=0x18C5387D, r4=r8=0x8060406A, r13=0xC0E00460), and a post-mcr store
to the same page NEVER lands. Only the mcr sits between. The transition is
content-deterministic per binary, not per boot. Next pass: bisect the content class
systematically; the NAND/rootfs lane waits on a boot that stays in the 0020 class.

### 2026-10-09 (night close) - the 0017 condition: deterministic, narrowed, mechanism open

Re-fires reproduce outcomes byte-for-byte: no-dt_rewrite builds boot (0020-class, 4/4);
dt_rewrite-present builds die at the mcu transition (0017-class, 3/3 - even after shrinking
it to ~80 bytes with no libc).  A 29-byte rodata string does not flip it.  The cache
protocol fix (full clean+invalidate + explicit SCTLR.C disable at stext, verified in the
image) does not fix it either.  Byte-diffs: everything executed pre-mcr is identical;
the only content deltas are a descriptor whose bounds shift consistently (+0xD0) and an
843-entry alternatives table whose 2 differing entries still patch identical values to
shifted (correct) sites.  => identical pre-MMU code + different data => different fate.
The consumer of that descriptor is __fixup_smp's late half feeding the pair-patch walker.
Next pass: instrument which alternative words actually get patched (read the sites back
from inside the kernel), and test the non-coherent A9's I/D-cache view of patched
instruction words.  The NAND/rootfs lane waits on a boot that stays 0020-class.

### 2026-10-09 (latest) - site-readback: the walk's stores measured; the dice model confirmed

Built a guarded readback instrument (post-__fixup_smp) over several fires: the
alternatives descriptor moves between builds (found by scanning early .text for
(A-W) ~ 0xC0000000 AND word2-word1 == 0x1A58); a 0x260 lookalike exists; an inverted
guard band killed a boot until fixed; the readback cells themselves were cache-held
until DCCMVAC-cleaned.  Result (0017 class, expectations validated against THAT build):
the three sampled sites read STOCK words - __fixup_smp's stores do not reach RAM in the
dying class.  CAVEAT: the instrument flips the class itself (reverted dt_rewrite, still
0017 with it in) => ANY sizable text change flips it; the "dice" model stands.  The
0020-class cell read needs a smaller-footprint reader (a C-level one in luofu.c).

### 2026-10-09 (dice campaign close) - six instrumented throws, all 0017; the framing fix

Six instrumented builds (C readers in three shapes, the asm readback, 192B text pads,
string perturbations) all died 0017.  Key realization: the current tree carries the
sweep + C-disable block (~+300 bytes vs the 0020 baseline), so the instrument was never
added to "the verified 0020 content" - the budget framing was contaminated.
Clean sequence for a fresh session: revert to the exact 6d904f5 content; add ONLY a
minimal inline-asm reader (hardcoded descriptor 0x2E8/VA 0xC06082E8 in the pad-less
tree - verified); fire; if 0020 read cells at 0x8F000F20; then re-introduce the sweep,
C-disable, dice one at a time with a fire each.

### 2026-10-09 (MEASUREMENT COMPLETE) - the walk's patches are absent in BOTH classes

The working instrument, finally: exact 6d904f5 baseline + a 12-instruction inline reader
at the 0x17 site (descriptor hardcoded 0x80608244), cells at 0x80600F20/24 in the
proven-surviving zone (0x8F000F20 is zeroed by the vendor boot - measured with a
sentinel-reboot test).  It boots 0020; its cells read 0x00000001 (STOCK) and 0xC0000000
(the delta, exactly as predicted - instrument validated).  => the alternative-site word
is STOCK in the booting class too; the class difference is NOT about the walk's patches.
Chain for the absence: walk stores -> D-cache (C=1 legacy) -> v7_invalidate_l1 (in
v7_setup, invalidate-only) discards the dirty lines -> patches never reach RAM in ANY
boot.  The reader survives because it runs after that invalidate.  Remaining question,
now cleaner: why the same patchless code survives the mcr in one layout and not another
(the byte-diff facts: descriptor bounds shift + post-0xF94CC layout).


---

## Phase 50 (2026-10-09): THE NAND/FMC PORT OPENS - the controller spec, the stage-A driver, and the symbol that left the TODO list

**Context.** The own kernel's ladder is already complete (C18 = 0xC0DE0020, watchdog
disarmed, every rung live-verified) and the only thing between "boots and runs" and
"mounts a rootfs" is the flash driver: the vendor box reaches its rootfs through
`hi_flash` bound to `hi_nfc` at `10a20000.fmc`, and our kernel has never had a driver
for that block. This phase starts it.

**The spec (`opensource/docs/phase50/nand-fmc-port-spec.md`, task st_01a121d8).** The
whole controller decoded from three independent artifacts - the public Triductor BSP
objects (`tri_fmc.o` + the `nfc_tr6560/` set, capstone + DWARF), the vendor
`hi_flash.ko` that actually runs on the box, and the vendor u-boot `stage2` - and
pinned against the live register dump. It lands on the point that makes the port
cheap: **the die is an ESMT F50L1G41LC and it is already in mainline**
(`drivers/mtd/nand/spi/esmt.c`, `esmt_8c`, memorg 2048/64/64/1024, on-die ECC 1/512),
so stage B is a thin controller driver, not a chip driver. `struct tri_fmc_reg_s`
gives all 24 named members 0x00-0xac; the command recipes and the DMA recipes
(`op_ctrl` types 1/3/0x11, the 0x2200 buffer split 8K data + 512B OOB) are tabled; and
the completion semantics were recovered for both code bases.

**THE ONE PLACE THE TWO IMPLEMENTATIONS DISAGREE, and the decision.** The BSP's
`tri_fmc_status_check()` polls **FMC_CFG bit 0** - and cfg reads `0x00001823` at idle
on this board (live dump), so bit 0 is SET at rest and that poll would spin to its
100000-iteration timeout on the first operation. The vendor polls **FMC_OP (0x3c) bit
0** for the command engine (`hi_fmc_status_check`) and **FMC_OP_CTRL (0x68) bit 0**
for the DMA engine (`hi_fmc_status_check_dma_status`). The driver follows the vendor,
because it is the implementation the live hardware runs, and the choice is recorded in
the file header so it is not "fixed" back later.

**Stage A, written and wired (`opensource/lab/luofu-kernel/nand/luofu/`).**
`luofu-fmc.c` maps the controller and its 1 MiB window, resets the die (0xff / op
0x81, then the OIP wait), reads the 5-byte READ ID (0x9f, 1 dummy, op 0x185) and reads
back the status and configuration feature registers (0x0f / op 0xc5). It compiles in
**no write path at all** - no write-enable, no erase, no program - so its read-only
property is structural rather than promised, and it registers no `mtd_info`.
`Kconfig` defines `MTD_NAND_LUOFU` (bool, depends on `ARCH_LUOFU || COMPILE_TEST`);
`docs/soc/luofu-r116.dts` turns the `fmc` node to `status = "okay"` so the probe runs.
The lane wires it in by **copying the directory and appending two lines** to
`drivers/mtd/nand/{Kconfig,Makefile}` in both CI jobs - an append has no upstream
context to drift against, unlike a patch hunk - and the image job now hard-asserts
`CONFIG_MTD_NAND_LUOFU=y` beside the rest of the storage path.

**Evidence, CI run `37974424274` on `d4280df`.** The fast `config` job is **GREEN**
and its own log carries the decisive lines:
`drivers/mtd/nand/Makefile:11:obj-$(CONFIG_MTD_NAND_LUOFU) += luofu/` and
`OK    CONFIG_MTD_NAND_LUOFU=y` - i.e. the symbol has LEFT the driver-less TODO list
(it was one of thirteen), the Kconfig is valid against the real 5.10.201 tree, and the
patch still applies cleanly to the pristine sources. The `kernel` job (the image lane,
the actual cross-compile of the driver) was still building when this entry was
written; its result is the next line to add, and the artifact to fetch is
`luofu-kernel-image`.

**The BSP land, for the record (`docs/phase50/bsp-build-status.md`).** The public
Triductor BSP is **half source and half binaries**: `target/linux/tr6560/files-5.10/`
holds 2 `.c`, 33 `.h` and 10 prebuilt `.o` - every NAND/FMC file is an object with no
`.c` anywhere - and the SoC platform drivers are 21 prebuilt `.ko` built for
**5.10.138** with no `__versions`. Their compatible strings are `tri,*`; `grep -rl hsan`
over the whole tree hits 6 files. So the BSP is a **reference and toolchain host, not a
drop-in firmware for our board** - which is exactly why the spec above was decoded from
the objects and why our own driver is written from scratch rather than ported by
dropping the DTS in.

**What this is NOT.** No device cycle ran this phase - nothing was flashed, staged,
booted or read on the router, and the box is untouched. Stage A is a *compiling*
driver with a *specified* register layer; nothing has yet been observed on hardware.
The five low-order unknowns the spec could not close (cfg bits 1/8-12, global_cfg bits
7/19, the pwidth/opidle provenance, the ecctype enum, the op bits 3/4) stay UNKNOWN
with the observation that would settle each, and the stage-A run is what turns the
ID read from "expected 8C 2C" into a measurement.


---

## Phase 50a (2026-10-09): THE FIRST STAGE-A FIRE - the driver compiled, the probe never ran, and the cause is that the kernel boots the VENDOR's devicetree

**The builds.** Both CI runs are GREEN: `37974424274` on `d4280df` (the driver +
spec) and `37974960956` on `08cdb42` (the crum-cell fix). The first one's artifact
is the one that was fired: `config` and `kernel` both **success**, and the log
carries the decisive lines - `drivers/mtd/nand/Makefile:11:obj-$(CONFIG_MTD_NAND_LUOFU)
+= luofu/` and `OK    CONFIG_MTD_NAND_LUOFU=y`, so the symbol has left the
driver-less TODO list (one of thirteen) and the driver cross-compiles. The image
is comfortably inside the budget: `zImage` 3,608,600 B, `uImage` 3,608,664 B
against the 8,650,752-byte kernelb partition, ~5 MB of margin.

**The fire.** `build/tmp/kboot/fire-nand.sh` - the proven `fire-fixed4.sh`
sequence with both cells poisoned and the poison re-read before the reboot, a
`boot_id`-changed freshness gate, and the two env writes dropped because the
files they read (`/tmp/a{1,2}.bin`) do not exist and never did in any prior fire.
Both gates passed: kernela's md5 still equalled the image last fired, and the
cells read back `0xFEEDFACE`/`0xFACEFEED`. The slice went in, the box rebooted,
and the vendor system came back by itself with a moved `boot_id`.

**The measurement, and it is a NEGATIVE with a named cause.** `C18 = 0xC0DE0020`
(every initcall completed) and `C1C = 0x18C5387D`. That second value is not a
driver value: `patched-head.S` writes a **pair** at its `0x0017` site - the crumb
to `0x10100C18` and then `str r0,[ip,#4]`, which lands r0 into `0x10100C1C` - and
r0 there is `0x18C5387D`. So the cell still held the last thing the head code
wrote, and **the probe never ran**. Two controls make that reading safe: a poison
written to c1c on the running vendor system held for 60 s, so nothing else writes
that cell, and c1c survives a warm reset.

**Why the probe never ran, and it is a fact the record already held.** The
mach's `dt_compat` carries `"hsan-luofu"`; our own DTS root is
`"hisilicon,luofu-r116", "hisilicon,luofu"` - a string the mach does NOT carry -
and the kernel still boots and stamps its crumbs. So the tree in use is the
**vendor's**, handed over by the u-boot bootfip, exactly as
`lab/luofu-kernel/README.md` recorded when it added that dt_compat entry. In that
tree the node is `fmc@10a20000 { compatible = "hsan,fmc"; }` with no `status`
property. Our match table had only `hisilicon,luofu-fmc`, so nothing probed.
**Corollary, recorded because it is easy to waste a fire on: editing our DTS
changes nothing at boot today - a `status = "okay"` there is inert.**

**The fix, committed as `8f610c6`.** `"hsan,fmc"` goes FIRST in the match table
(our own binding stays second for the day the appended tree is the one used); the
report cell is mapped and the ENTRY stamped before any resource can fail, because
"the probe was called at all" is the one fact that separates a missing DT match
from a failure inside the function; and c1c becomes self-describing -
`0x5000000n` = entered step n, `0xE000000n` = failed at step n, `0x8C2Cxxyy` =
PASS, `0x18C5387D` = the never-ran signature, documented in the header.

**Health.** The router is healthy throughout: it came back on 2.4.15 by itself,
6 interfaces, the vendor's wifi modules loaded, no leftovers. The only device
mutation was the kernela write and its reboot, and kernela is the project's own
deployment surface (its prior content is reproducible from
`build/tmp/kboot/mtd12-pre-2415.bin` plus the vendor container).

**What this is NOT.** Not a hardware finding: the register layer was never
executed, so nothing about the FMC's behaviour was measured. The stage-A claim
("the die answers 0x8C2C") is still OWED, and it is owed exactly one fire after
the match fix builds.


---

## Phase 50b (2026-10-09): STAGE-A PASS - THE FMC COMMAND ENGINE RUNS IN OUR OWN KERNEL AND THE DIE ANSWERS 0x8C2C

**The build.** CI run `37976313132` on `ed6376a` - both jobs **success** - after a
failed round on `8f610c6` that was my own bug and is worth its own line: the
match-fix edit touched four blocks of `luofu-fmc.c` in one call, the first
block's replacement text ended with the comment's closing `*/` while the text it
replaced stopped short of one, so the file carried two terminators and gcc
stopped at `luofu-fmc.c:88:3: error: expected identifier or '(' before '/'
token`. The other three blocks were intact, which is exactly what makes the
class dangerous to eyeball. There is no C compiler on this workstation, so the
first reader of a `.c` file is a 30-minute CI job - the fix is one deleted
token, and the lesson is the one already recorded for this project, now with a
second instance.

**The fire, and it is the measurement the phase was for.** `fire-nand.sh` on
run `37976313132`. Both gates passed again (kernela still the image last fired,
both cells poisoned AND re-read). The box came back by itself, `boot_id` moved
`e323f3cd-...` -> `1c8010f0-...`, and the cells read:

```
C18 = 0xC0DE0020     every initcall in OUR kernel completed
C1C = 0x8C2C0000     the NAND driver's result
```

**`0x8C2C` is the die's signature.** `C1C` decodes as
`id[0]<<24 | id[1]<<16 | config<<8 | status` = `0x8C 0x2C 0x00 0x00`: the two ID
bytes the mainline ESMT table keys on (`SPINAND_ID(SPINAND_READID_METHOD_OPCODE_ADDR,
0x2C)`, manufacturer `0x8C` = ESMT), then the configuration register (`0xb0`)
reading `0x00` - which is what a die that has just been reset by this driver
should read, since the quad-enable bit is set by the vendor's own driver and
this one deliberately does not write features - and the status register
(`0xc0`) reading `0x00`, i.e. not busy, no failure bits, exactly the state
after a successful RESET plus the OIP wait.

**So four things are now measured on real hardware, not inferred:** the FMC
register window at `0x10a20000` maps and reads in our kernel; the data window
at `0x1c000000` reads; the command engine accepts the decoded recipes (RESET
`0xff`/op `0x81`, GET FEATURES `0x0f`/op `0xc5`, READ ID `0x9f`/op `0x185`) and
its completion poll settles; and the die on chip select 1 answers with the
identity the spec predicted from the BSP objects and the vendor module. The
reading is stable across four samples taken over ~2 minutes, and the second
sample was taken through a different probe, so it is not a one-instant artifact.

**Health, by the project's own probe.** `FINAL_WIPHY=2 FINAL_IFACE=6`,
`FINAL_CAL2G=1 FINAL_CAL5G=1`, `FINAL_VENDOR=2`, `OMO_OFF=0`, `STAGED=0`,
`PSTORE=3` (the baseline set, unchanged), on `mtd14:rootfsb` with `bootflag=b`.
Zero leftovers. The only device mutation in the whole phase was the `kernela`
write and the reboots it caused, and `kernela` is this project's own deployment
surface.

**What this does NOT say, and the next link.** Stage A read the chip's identity
through the command engine; it did NOT transfer a page. The page path is the DMA
engine (`op_ctrl`, op types 1/3/0x11, the 0x2200-byte buffer split 8 KiB data +
512 B OOB), and its `op_cfg` operands (`read_if_type`, `read_addr_cycle`,
`read_dummy_num`) come from the bootloader's flash-spec ATAG table, which is the
one input stage A does not consume. So stage B is: get those three operands -
either by reading the ATAG the u-boot leaves in RAM, or by deriving them from
the mainline spinand table - then read a page and check for the UBI magic at the
start of `rootfsa` (chip offset `0x1e00000` = row `0xF00`). That is the next
fire, and it is a read-only one.


---

## Phase 50c (2026-10-09): STAGE B'S OPERAND SOURCE IS LOCATED - the bootloader's flash-spec ATAG, and it names our die

Stage B needs three operands the DMA page read cannot be issued without
(`read_if_type`, `read_addr_cycle`, `read_dummy_num`), and the spec says they come
from a flash-spec table the bootloader leaves behind. This step found that table
and captured it.

**Where the table actually is, which the spec had wrong.** The spec's own text
pointed at the reserved-memory node at `0x80800000`, and an earlier capture noted
that reading it back gave ARM code rather than a parameter block - and that is
what it gives, because that is not where the table is. The live devicetree node
`/proc/device-tree/reserved-memory/flashinfo@0x80800000/` carries two properties:

```
reg         = 80 60 00 00  00 00 40 00   -> base 0x80600000, size 0x400000
atag-offset = 00 00 10 00                -> 0x1000
```

so the ATAG chain is at **0x80600000 + 0x1000 = 0x80601000**, and the `atag-offset`
property is the piece the earlier attempt was missing. Reading there gives a clean
tag chain: `ATAG_CORE` (`0x54410001`), `ATAG_SERIAL` (`0x54410006`), then the
vendor tag **`0x5441000a` with size `0x61`** (97 words) - the flash table.

**The payload corroborates stage A from an independent direction.** Its printable
runs are a **table of SPI-NAND part numbers**, and the FIRST entry is literally:

```
F50L1G41LC     <- the die stage A's READ ID named (0x8C 0x2C), now named again
S34ML02G1      S34ML02G2   S34ML04G2   MX35LF1GE4AB   MX35LF2G14
```

So the bootloader's own table knows this exact part, from a source that shares
nothing with our kernel's RDID path - the u-boot flash table versus our command
engine. The stage-A reading is now doubly confirmed.

**Captured.** The full payload is `build/tmp/nand-spec/flashinfo-atag.txt` (100
words from `0x80601024`, the tag header plus its payload), so the remaining decode
is offline work and needs no further device access.

**Still owed, and it is the last thing before the page read:** decode the 52-byte
`tri_nand_spec` record out of that payload - specifically `read_if_type` (the bus
width code), `read_addr_cycle`, and `read_dummy_num`. The record is not at a
trivially-aligned offset in the payload (the leading words look like a selector
byte plus a 0x18-byte record, which matches the spec's own note that the payload
is "byte index -> 0x18-byte records"), so it needs the disassembly of
`tri_nand_probe`'s copy loop read against the captured bytes rather than a guess.

**Health.** No device mutation whatsoever in this step: read-only `devmem` and
`/proc/device-tree` reads. The router is as phase 50b left it - `WIPHY=2 IFACE=6`,
cal `[SUCC]` both bands, `PSTORE=3` unchanged, zero leftovers.


---

## Phase 50d (2026-10-09): THE DMA OPERANDS ARE RECOVERED - the bootloader's flash-spec record, decoded and cross-checked

Stage B needed `read_if_type`, `read_addr_cycle` and `read_dummy_num`. All three are
now recovered, with a decode chain in which every step is checked against the geometry
it must produce.

**How the payload is laid out, from the consumer.** `tri_nand_probe` disassembles as:
`index = *(u8 *)tri_get_flash_tag_info()`, then the record lives at
`tag_info + 0x18 * index + 2`, and 52 bytes (`0x34`) of it are copied into the chip's
spec, with a separate `0xa20`-byte blob memcpy'd from `spec + 0x34`. On this board the
index byte is `0`, so the record is at **`0x8060102e`** - inside the tag `0x5441000a`
found in phase 50c.

**The record, read straight out of `/dev/mem`, field by field:**

| off | field | value | cross-check |
|---|---|---|---|
| 0x00 | options | `0x40000400` | - |
| 0x04 | tri_size | `0x08000000` | 128 MiB - the chip's size |
| 0x08 | block_size | `0x00020000` | 128 KiB - the erase unit |
| 0x0c | page_size | `0x00000800` | 2048 - matches UBI's I/O unit |
| 0x10 | oob_size | `0x00000040` | 64 |
| 0x14 | page_shift | `11` | 2^11 = 2048 ✓ |
| 0x18 | erase_shift | `17` | 2^17 = 131072 ✓ |
| 0x1c | bbt_erase_shift | `17` | - |
| 0x20 | bbt_len | `0x100` | 1024 blocks / 4 blocks-per-byte ✓ |
| 0x24 | ecc_type | `1` | - |
| 0x28 | read_addr_cycle | **`5`** | |
| 0x29 | write_addr_cycle | `5` | |
| 0x2a | erase_addr_cycle | `3` | 0xd8 takes 3 address bytes ✓ (and the erase path hardcodes `0x30` = 3 cycles, agreeing) |
| 0x2c | read_if_type | **`3`** | quad |
| 0x2d | read_cmd | **`0x6b`** | READ FROM CACHE x4 |
| 0x2e | read_dummy_num | **`1`** | |
| 0x2f | write_if_type | `3` | |
| 0x30 | write_cmd | `0x32` | PROGRAM LOAD x4 |
| 0x31 | write_dummy_num | `0` | |

**Why this is a decode and not a guess.** Three independent checks land at once:
every size/shift field reproduces exactly the geometry mainline's `esmt_8c` entry gives
for the F50L1G41LC (128 MiB / 128 KiB / 2048 / 64); the `erase_addr_cycle` value is
corroborated by the erase code path hardcoding the same 3; and the whole thing is the
record the vendor's own working driver consumes. The field *offsets* were not inferred
either - they come from the DMA routine's own loads (`spec+0x28` and `spec+0x29` for the
read/write address cycles, `+0x2c`/`+0x2d`/`+0x2e` for the read interface type, command
and dummy).

**The consequence that shapes stage B's implementation.** The device is configured for
**quad** I/O (`read_if_type = 3`, `read_cmd = 0x6b`), and quad requires the die's
configuration register (`0xb0`) to have its QE bit set - which the vendor's own driver
does at boot via `enable-quad-mode`. Stage A's read showed `config = 0x00` precisely
because this driver resets the die and writes no features. So the page read needs one
SET FEATURES (`0xb0 |= 0x01`) first - a write to the die's *configuration* register,
not to the flash array, and the same write the vendor performs on every boot.

**The plan for the page read, and its pass condition.** Read the page at the start of
`rootfsa` (chip offset `0x1e00000`, row `0xF00`) through the DMA engine and stamp its
first four bytes into the result cell: if the path works and the partition really
carries a UBI volume, that word is **`0x23494255`** = the ASCII `"UBI#"` of UBI's EC
header magic. That makes the pass value self-describing - it is the data itself, not a
proxy for it.

**Health.** No device mutation in this step beyond what phase 50b left: the reads are
`/dev/mem` and `/proc/device-tree`. Router unchanged.


---

## Phase 50e (2026-10-09): STAGE-B PASS - THE DMA PAGE READ RETURNS REAL FLASH CONTENT, AND rootfsa BEGINS WITH "UBI#"

**The build.** CI run `37978032314` on `7f4337d` - both jobs **success**. The image is
3,610,504 B against the 8,650,752-byte kernelb partition, ~5 MB of margin.

**The fire.** `fire-nand.sh` on that artifact. Both gates passed (kernela still the image
last fired at `2e24d4e2...`, both cells poisoned AND re-read), the box came back by itself
with `boot_id` moving `1c8010f0-...` -> `00bc47a3-...`, and the cells read:

```
C18 = 0xC0DE0020     every initcall in OUR kernel completed
C1C = 0x23494255     the ASCII "UBI#"
```

**`0x23494255` is the ASCII `UBI#`, UBI's erase-counter header magic.** The driver's
last act in probe() is to read the first page of the `rootfsa` partition through the DMA
engine (chip offset `0x1e00000`, row `0xF00`) and stamp that page's first four bytes into
the result cell - so the pass value is not a proxy for the read, it is the bytes the read
returned. Reproduced in a second sample taken through a different probe.

**What that one word establishes, link by link.** The flash-spec operands parsed out of
the bootloader's own ATAG table at runtime are the correct ones, because the read they
configured returned the right data; the quad configuration works, because that is the
interface the operands describe (`read_if_type = 3`, `read_cmd = 0x6b`) and it needed this
driver's one SET FEATURES to turn the die's QE bit on; the DMA engine's buffer setup,
row addressing (`addrh/addrl = row << 16`) and `op_ctrl` trigger all work, because a
specific page came back with the content that page must have; and the `rootfsa` partition
genuinely carries a UBI volume, which is the volume the rootfs will be mounted from.

**So the flash controller is now demonstrated end to end in our own kernel**: the register
window, the data window, the command engine (stage A's READ ID), and the DMA page
transfer. The thing that phase 50 opened as "the one thing between boots-and-runs and
mounts-a-rootfs" now reads the rootfs.

**Health, by the project's own probe.** `FINAL_WIPHY=2 FINAL_IFACE=6`,
`FINAL_CAL2G=1 FINAL_CAL5G=1`, `FINAL_VENDOR=2`, `OMO_OFF=0`, `STAGED=0`, `PSTORE=3`
unchanged, on `mtd14:rootfsb` with `bootflag=b`. Zero leftovers. The only device mutation
across 50b/50e was the `kernela` write and the reboots it caused.

**What this does NOT yet say.** Reading a page is not mounting a filesystem. Nothing is
registered with MTD yet: there is no `mtd_info`, no partition table, no UBI attach and no
mount, so the kernel still panics on the missing rootfs and folds back to the vendor. What
changed is that the hard part - the controller - is measured, so what remains is the
mainline integration the spec's section (f) always named: an MTD device over these
primitives, the 17 partitions from the devicetree, then UBI on top.

**A note on the instrument, because it matters for the next phase.** This driver's
readback cell holds the LAST thing the probe wrote, so it now reports stage B and no
longer stage A; stage A's `0x8C2C` reading is preserved in phase 50b. Extending the
protocol again means re-reading the header's table, not assuming the old meaning.


---

## Phase 50f (2026-10-09): WHY THE ROOTFS IS STILL MISSING - the vendor boots an INITRAMFS, and the two routes from here

Stage B proved the kernel can read flash. It still panics on the missing rootfs, and this
step establishes exactly why - which changes the next phase's plan.

**The vendor kernel is never told where its root is.** Its effective command line is:

```
noinitrd cma=0 console=ttyS0,115200 earlycon maxcpus=2 nr_cpus=2 additional_cpus=1
```

There is **no `root=`**. And the running system's mounts are:

```
/dev/ubiblock0_0   /rom      squashfs  ro
/dev/mtdblock15    /overlay  jffs2     rw
overlayfs:/overlay /         overlay   rw
```

`/` is an **overlayfs built by userspace**, not a filesystem the kernel mounted. So
something mounted `/rom` first and then handed over - i.e. the vendor kernel boots with a
**built-in initramfs**, whose OpenWrt preinit finds the rootfs volume, mounts it and sets
up the overlay. The absence of `root=` is not an omission; it is what an initramfs boot
looks like from `/proc/cmdline`.

**Our kernel cannot do that, by construction.** `luofu-shrink.fragment` carries
`CONFIG_BLK_DEV_INITRD=n` ("no initramfs in the slice"), so there is no preinit to find a
rootfs and no `root=` for the kernel to use. The panic is therefore not the storage path
failing - it is the boot posture being incomplete. That distinction matters, because the
storage half is now measured working.

**Two routes, and the second is the one to take first.**

(a) *Turn the initramfs back on* and build an OpenWrt-style preinit into it. Faithful to
how the vendor does it, but it means `CONFIG_BLK_DEV_INITRD=y`, an `CONFIG_INITRAMFS_SOURCE`
tree with OpenWrt's `/init` + `mount_root`, and it grows the image - the exact thing the
shrink fragment exists to prevent.

(b) *Skip the initramfs and tell the kernel directly.* `CONFIG_CMDLINE_EXTEND=y` plus a
built-in command line naming the device chain:

```
ubi.mtd=rootfsb ubi.block=0,0 root=/dev/ubiblock0_0 rootfstype=squashfs rootwait
```

`EXTEND` rather than `FORCE`, so the bootloader's `earlycon` and the rest survive and ours
is appended. This uses mainline's own UBI auto-attach and ubiblock, needs no userspace
before the mount, and its pass condition is unambiguous: the kernel either mounts a
squashfs root or it does not. Use the partition NAME (`rootfsb`) rather than `mtd14`, so
our partition registration order does not have to match the vendor's numbering.

**What (b) still needs first, and it is the real work:** the driver must register an
`mtd_info` with read/write/erase/OOB over the primitives that are now measured, plus the
17 partitions from the devicetree, and `CONFIG_MTD_UBI` must actually attach. Until then
there is no `mtd` for `ubi.mtd=` to name. So the next phase is: the MTD device, then the
partition table, then route (b)'s command line.

**Health.** Read-only step. Router unchanged: `WIPHY=2 IFACE=6`, cal `[SUCC]` both bands,
`mtd14:rootfsb`, `PSTORE=3`, zero leftovers.


---

## Phase 50g (2026-10-09): THE ROOT-DEVICE MECHANISM, SETTLED FROM SOURCE - and why the root= fire needs its own plan

Stage C registers the MTD device (phase 50h's commit). This step settles what the kernel
will need to actually MOUNT a root from it, by reading the sources rather than assuming.

**1. A write-protected MTD is enough for UBI.** From v5.10 `drivers/mtd/ubi/build.c`,
verbatim:

```c
	if (!(ubi->mtd->flags & MTD_WRITEABLE)) {
		ubi_msg(ubi, "MTD device %d is write-protected, attach in read-only mode",
			ubi->mtd->index);
		ubi->ro_mode = 1;
	}
```

So UBI does not refuse a read-only device, it attaches in read-only mode. That is what
lets stage C register an `mtd_info` with **no `_write`, no `_erase`, no `_write_oob`** and
`MTD_WRITEABLE` cleared, and it means the rootfs path needs no flash-modifying code at
all: nothing in this driver can write the flash, and the mount still has what it needs.

**2. `ubi.mtd=` accepts a partition NAME.** `ubi_mtd_param_parse()` stores the token and
`open_mtd_device()` falls back to `get_mtd_device_nm()` when the token is not a number -
so `ubi.mtd=rootfsb` names the partition rather than depending on our registration order
matching the vendor's mtd numbering.

**3. `root=/dev/ubiblock0_0` does resolve in vanilla 5.10.** `name_to_dev_t()` strips
`/dev/`, then calls `blk_lookup_devt("ubiblock0_0", 0)`, which walks `block_class` and
matches `dev_name()` - and a ubiblock device is named `ubiblock%d_%d` by construction. The
timing also works: `ubi_init` (build.o) and `ubiblock_init` (block.o) are both
`module_init`, and `prepare_namespace()` runs after all initcalls, so the device exists
before the root is resolved.

**4. OpenWrt's own mechanism is a patch set we do not have, and that is why the command
line is the route.** The BSP carries the three patches that make a rootfs work without a
`root=` at all - `420` sets `ROOT_DEV` to the mtdblock of a partition named "rootfs",
`490` auto-attaches an MTD named "ubi" or "data" after checking its `UBI#` magic, `491`
auto-creates a ubiblock for a UBI volume named "rootfs" that is not UBIFS, all gated on
`CONFIG_MTD_ROOTFS_ROOT_DEV`. We build **vanilla 5.10.201 + our fragment**, so none of
them are present. Re-creating them is route (a); naming the chain on the command line is
route (b), and (b) uses mainline mechanisms only.

**5. Why the `root=` fire still needs its own plan - a real risk, named before it is
taken.** Today the box is safe because our kernel *panics* on the missing rootfs, and
`panic=5` plus the mach's `.restart` reboots it, after which the bootreg machinery folds
back to the vendor. **A successful mount removes that recovery.** Our kernel has no
network driver, so a kernel that reaches userspace would be reachable by neither ssh nor
the failover, and the only way back would be a power cycle - which is the user's hands,
not mine. So the `root=` fire must be designed so that success is still self-recovering
and still observable. The candidate: add `init=/nonexistent` alongside the root chain, so
that a mount which succeeds proceeds to run init, fails to find it, and panics anyway -
kernel log line "No working init found", then `panic=5` -> reboot -> vendor failover. The
mount's success would then be readable as a DIFFERENCE in behaviour (how long the box is
away, and where it ends up) rather than as a silent hang. That design gets its own step,
deliberately, rather than being bolted onto this one.

**Read-only step.** No device mutation; the router is as phase 50e left it.


---

## Phase 50h (2026-10-09): THE FIRST MTD FIRE - the instrument named the step, the source named the cause, and the fix is one flag

**The fire, and it was deliberately a safe one.** CI `37979479321` on `bfc54f0` built green
(uImage 3,611,400 B, ~5 MB inside budget). The fire ran the same two gates as always -
kernela still the image last fired at `8351bdd0...`, both cells poisoned AND re-read - the
box came back by itself with `boot_id` `00bc47a3-...` -> `a48df242-...`, and the cells read:

```
C18 = 0xC0DE0020     every initcall in OUR kernel completed
C1C = 0xE0000009     FAILED AT STEP 9
```

**What that says, precisely.** Step 9 is `luofu_fmc_register_mtd()` - the `mtd_info`
registration itself. Steps 1-8 all ran, so the operand parse, the quad enable, the DMA
page read and the `rootfsa` read all still work; what failed is only the step that exposes
them to the rest of the kernel. The instrument earned its keep here: without the step
byte this would have been an ambiguous "the driver didn't do everything".

**Why it failed, from the kernel source.** `drivers/mtd/mtdcore.c`, `add_mtd_device()`:

```c
	if (WARN_ON((!mtd->erasesize || !master->_erase) &&
		    !(mtd->flags & MTD_NO_ERASE)))
		return -EINVAL;
```

The driver registers **read-only**, so it has no `->_erase` - deliberately, because it must
not modify the flash at all - and it did not declare `MTD_NO_ERASE` either, so
`mtd->flags` was `MTD_CAP_NANDFLASH & ~MTD_WRITEABLE` = **0**. The check therefore refused
the registration. In one line: the driver was rejecting itself for being exactly what it is
meant to be, and the flag it needed is the one MTD defines for "this device has no erase".

**The fix, and why it is safe for UBI.** `mtd->flags` now carries `MTD_NO_ERASE` (committed
`4417f43`). That the change cannot disturb UBI was checked against its source rather than
assumed: `drivers/mtd/ubi/build.c` mentions `MTD_NO_ERASE` **zero** times and tests only
`MTD_WRITEABLE`, which is the one that selects read-only attach mode.

**Every other check in `add_mtd_device` was already satisfied, so nothing else is
outstanding:** `writesize` is non-zero (2048); the driver provides `->_read` but no
`->_read_oob`, and the check rejects providing *both* of a pair; `->_write` and
`->_write_oob` are both absent; and `mtd->dev.type` is NULL, so the already-registered check
passes. Reading the function rather than guessing is what turns "try again" into a
single-variable change.

**Operational note: this fire could not have stranded the box, by design.** No `root=` was
added, so the kernel still panics on the missing rootfs and the bootreg machinery folds back
to the vendor - which is exactly what happened. That is the safety posture phase 50g
recorded, and it is why the root= step is still held back for its own fire with its own
`init=/nonexistent` net.

**Health.** The router came back on 2.4.15 by itself and is unchanged. This is the third
consecutive fire in which the only device mutation was the `kernela` write and its reboot.


---

## Phase 50i (2026-10-09): THE SECOND MTD FIRE - the registration works, and the panic it exposed was one unallocated field

**Two results in one fire, and both are progress.**

**1. The MTD device now registers.** CI `37980541714` on `4417f43` built green and was
fired. The cells read:

```
C18 = 0xC0DE5009     the driver's step-9 crumb
C1C = 0x50010009     the step-9 PROGRESS marker - NOT a failure
```

`0x50010009` is `LUOFU_RPT_STAGEB(9)`, the "step reached" value, not `0xE0000009`. So
`luofu_fmc_register_mtd()` **returned success**: `MTD_NO_ERASE` was the whole of that
problem, and the device tree's 17 partitions are now being parsed.

**2. And the kernel then panicked in step 10 - the crumbs said where.** `C18` stayed at
`0xC0DE5009`, the driver's step-9 crumb, which means the mach's `late_initcall` crumb never
ran: the kernel died between the step-9 write and the step-10 write. The only code in that
gap is `get_mtd_device_nm("rootfsb")`, and reading `mtdcore.c` cleared it - that function
cannot block (it returns `-ENODEV`), and `mtd_read_oob_std()` passes the **master** mtd to
`->_read`, so `mtd->priv` is our `fmc` and the offset translation is correct.

**The bug was one field, and it was mine.** `luofu_mtd_read()` reads into
`fmc->page_buf`, and `page_buf` was **never allocated**: the probe allocated a *local*
`page` for the stage-B read and left the struct member NULL. So `mtd_read()` reached
`memcpy_fromio()` with a NULL destination and the kernel panicked. Fixed by
`fmc->page_buf = page`, so the stage-B frame and the mtd read hook's frame are one
allocation, assigned before either the stage-B read call or the registration can use it
(commit `e99fdc3`). The other fields the hook touches were checked and are all set.

**The second symptom, now explained.** This fire took roughly **ten minutes** to come back
instead of the usual two. C18 = 0xC0DE5009 says the kernel never reached `late_initcall`,
so a hang is excluded - it must have panicked, and `panic=5` plus the mach's `.restart`
reboots. Ten minutes is several panic/reboot cycles before the bootreg machinery flipped to
the vendor, versus the single cycle the earlier fires needed.

**Why this is the crumb protocol working, not failing.** The step-by-step markers have now
converted two silent failures into located ones: the first fire's `0xE0000009` named the
step that failed, and this one named a bug **by where it did not write** - the missing
step-10 crumb is what proves the death was between the two writes. A single "did it work"
cell could not have carried either.

**Health.** The router came back on 2.4.15 by itself and is healthy; the only device
mutation was the `kernela` write and its reboots. The fire's wait loop tolerated the longer
recovery without intervention, which is worth knowing for future firmware that panics
earlier in the boot.


---

## Phase 50j (2026-10-09): STAGE-C PASS - OUR OWN KERNEL HAS AN MTD DEVICE, THE VENDOR'S PARTITION TABLE IS PARSED, AND THE ROOTFS PARTITION READS THROUGH THE MTD LAYER

**The build.** CI `37981524117` on `e99fdc3` - both jobs green.

**The fire, and both halves of the signature are exactly what was predicted.**

```
C18 = 0xC0DE0020     the mach's late_initcall crumb - ALL INITCALLS COMPLETED
C1C = 0x23494255     the ASCII "UBI#", read THROUGH the mtd layer from the partition "rootfsb"
```

`C18 = 0xC0DE0020` is itself a result this time, not just setup: it is the value the mach
stamps at `late_initcall`, which can only be written if the kernel survived the driver's
probe. In the previous fire C18 froze at a `0xC0DE5xxx` step crumb because the probe
panicked; now it is the mach's own value, so **the page_buf fix removed the panic and the
probe runs clean**. The recovery was back to a single fast cycle (~2 minutes, versus the
previous fire's ~ten) for the same reason.

`C1C = 0x23494255` is `"UBI#"` read out of the partition through `mtd_read()`. Four things
are therefore true at once, and this is what the instrument was built to prove:

1. the `mtd_info` registered - `mtd_device_parse_register()` succeeded;
2. `ofpart` parsed the **vendor devicetree's** 17-partition table off the fmc node;
3. the partition exists under **exactly the name** `ubi.mtd=` will be handed (`rootfsb`);
4. the read path survives the mtd page arithmetic - partition offset to master offset, then
   page-index and in-page offset, then the DMA read.

Reproduced in a second sample and again through an independent probe. Health by the
project's own script: `FINAL_WIPHY=2 FINAL_IFACE=6`, `FINAL_CAL2G=1 FINAL_CAL5G=1`,
`FINAL_VENDOR=2`, `OMO_OFF=0`, `STAGED=0`, `PSTORE=3` unchanged, on `mtd14:rootfsb`.

**What this changes about the remaining work.** The storage stack our kernel needs for a
rootfs is now, in order: FMC controller (measured), DMTA page read (measured), mtd device +
partition table (measured), and then **UBI and the root device**. The last item is no longer
a driver question - it is `ubi.mtd=rootfsb ubi.block=0,0 root=/dev/ubiblock0_0
rootfstype=squashfs rootwait`, all mainline mechanisms, whose one unknown was whether the
partition would be there under that name. It is.

**And the safety question is unchanged and still binding.** The box is currently safe
*because* our kernel panics on the missing rootfs, and `panic=5` plus the mach's `.restart`
returns it to the vendor - which is what happened in this fire, in one cycle. A successful
mount would end that, and with no network driver in our kernel the machine would then be
reachable by neither ssh nor failover. So the `root=` step still gets its own fire with its
own `init=/nonexistent` net, exactly as phase 50g specified, and it is the next step.

**Device mutation.** The same as every fire since 50b: the `kernela` write and its reboots.
Nothing else was touched, and nothing in this driver can write the flash.


---

## Phase 50k (2026-10-09): THE ROOT DEVICE, AND THE SAFETY NET THAT GOES WITH IT

Stage C measured everything a rootfs mount needs. This step adds the root device itself -
and the net that makes firing it safe - in one commit (`7e1da9c`, CI `37982351933`).

**The command line**, appended to the loader's by `CONFIG_CMDLINE_EXTEND`:

```
ubi.mtd=rootfsb ubi.block=0,0 root=/dev/ubiblock0_0 rootfstype=squashfs rootwait
```

All mainline mechanisms: `ubi.mtd=` takes a partition NAME (so our registration order need
not match the vendor's numbering), `ubi.block=` creates the ubiblock for the rootfs volume,
and `name_to_dev_t()` resolves `/dev/ubiblock0_0` through `blk_lookup_devt()` against the
ubiblock disk's own name.

**A near-miss caught in review, and it is the sharpest one in this phase.** The fragment
already carried `CONFIG_CMDLINE="panic=5"`, and the first version of this change added a
**second** `CONFIG_CMDLINE` line. `CONFIG_CMDLINE` is a *string* symbol: a second line does
not extend it, it **replaces** it. So that version would have silently dropped `panic=5` -
and a panicking kernel without `panic=5` **hangs instead of rebooting**, which is precisely
the mechanism that returns this box to the vendor after every fire. Losing it is the one
change here that could have stranded the router, and it would have looked like a successful
push. Both values now live in ONE string, and a duplicate-symbol scan over the whole
fragment reports none. Worth generalising: in a fragment, a repeated key is not a merge.

**The safety net, `init=/nonexistent-init`, is not a typo.** Our kernel has no network
driver, so a boot that SUCCEEDS in mounting a rootfs would reach a userspace reachable by
neither ssh nor the bootreg failover - a power cycle, and therefore the user's hands, would
be the only way back. Naming an init that cannot exist means a successful mount still ends
in "Requested init ... failed", then `panic=5`, then the mach's `.restart` - the same path
that returns the box today. **Both outcomes self-recover**, which is what makes this step
something that can be fired at all.

**And the part that makes it observable (stage D).** A `late_initcall_sync` hook opens the
volume named `rootfs` through UBI's **public** API and reads its first four bytes into the
reader cell. The *attach* is left to the kernel's own `ubi.mtd=` because
`ubi_attach_mtd_dev()` is deliberately not public; the hook runs at `late_initcall_sync`,
after every `late_initcall` and so after UBI's `module_init` has attached. A squashfs
superblock begins with the magic `"hsqs"`, which as a little-endian word is
**`0x73717368`** - so, like stages B and C, the pass value is the data itself.

**What the fire will distinguish.** `0x73717368` means UBI attached to our mtd AND the
rootfs volume reads through it - i.e. the whole storage stack, with the only remaining
question being whether the kernel then mounts it. A `0xE000000B` means UBI did not attach.
Either way `C18` should hold the mach's `0xC0DE0020`, because both paths complete the
initcalls before the mount is attempted.


---

## Phase 50l (2026-10-09): THE ROOT-DEVICE FIRE - the hook ran, the volume name was my assumption, and what the cells cannot say

**First, the artifact confirmed the near-miss fix.** The built config in the artifact carries
`CONFIG_CMDLINE="panic=5 ubi.mtd=rootfsb ubi.block=0,0 root=/dev/ubiblock0_0
rootfstype=squashfs rootwait init=/nonexistent-init"` - **`panic=5` is present**, so the
duplicate-key trap recorded in phase 50k is genuinely closed, checked in the thing that was
built rather than in the file that was edited.

**The fire.** Both gates passed, the box came back by itself in the usual single cycle, and
the cells read:

```
C18 = 0xC0DE500B     the driver's step-11 crumb - the late_initcall_sync hook RAN
C1C = 0xE000000B     failed at step 11: ubi_open_volume_nm(0, "rootfs", UBI_READONLY)
```

So the root-device command line did not stop the kernel, UBI did not stop the kernel, and
the stage-D hook executed and reported honestly. What failed is the hook's own lookup.

**The volume is named `squashfs`, not `rootfs`.** One command on the live system answered
it - `/sys/class/ubi/ubi0_0/name` reads **`squashfs`** (volume 0, static, 14,864,384 bytes),
with `/sys/block/ubiblock0_0` present - and the offline check corroborates it from a
different direction: the string `rootfs` occurs **zero** times in a decompressed dump of
the partition. The volume was there all along; the hook was asking for a name I had
assumed.

**The fix removes the assumption rather than correcting it.** Open **by ID** -
`ubi_open_volume(0, 0, UBI_READONLY)` - because "volume 0 is the rootfs" is the stable
fact. And the same cell now answers both halves: the value is the squashfs magic `0x73717368`,
**plus one** when `blk_lookup_devt("ubiblock0_0", 0)` resolves - the very call
`name_to_dev_t()` makes for `root=/dev/ubiblock0_0`. So `0x73717368` means "the volume reads
through UBI and the device root= names is resolvable", and `0x73717369` means "reads, but
the block device does not resolve" (commit `4aee946`).

**What this fire CANNOT say, stated plainly rather than glossed.** It cannot distinguish a
mount that **succeeded** and then died at `init=/nonexistent-init` from a mount that
**failed**. Both end in a panic, `panic=5`, and the vendor failover - which is exactly the
design - and the cells look identical either way. That is the cost of the safety net: it
makes the step safe to fire and it buys the ability to tell the cases apart with a separate
observation. The next fire's cell is that observation: if the magic lands *and* the `+1`
lands, then UBI attached, the volume reads, and the ubiblock device exists - and the mount
itself is then mainline code with nothing board-specific left in it.

**Device mutation.** Unchanged: the `kernela` write and its reboots. The router came back on
2.4.15 healthy, as in every fire since 50b.


---

## Phase 50m (2026-10-09): THE NAME WAS ONE PROBLEM, NOT THE ONLY ONE - so the failure value now carries the diagnosis

**The volume-by-ID fire returned the same failure.** `C18 = 0xC0DE500B`, `C1C = 0xE000000B`:
`ubi_open_volume(0, 0, UBI_READONLY)` failed too. So opening by ID did not fix it, which
means the name was *one* problem and not the only one - **UBI is not up by the time the hook
runs**, or `ubi0` does not exist at all.

**Rather than guess a third time.** Two 40-minute round trips have now been spent on
single-hypothesis fixes to this one call, and each taught something but neither located the
cause. So the failure value itself now carries the diagnosis - on a failed open it stamps
`0xE0000000` plus two independent facts:

| bit | fact |
|---|---|
| 1 | can the mtd partition UBI was TOLD to attach still be resolved by name (`get_mtd_device_nm("rootfsb")`)? |
| 0 | does the ubiblock device exist? |

The second bit is the interesting one: `ubiblock0_0` is created by `ubiblock_init()` from
`ubi.block=0,0`, and it can only exist if **ubi0 attached AND volume 0 opened for it** - so
its presence is evidence about UBI that does *not* travel through this hook's own open call.
The four outcomes then read:

```
0xE0000000  neither        -> the partition is not there any more
0xE0000001  ubiblock only  -> UBI IS up; this hook failed for some other reason
0xE0000002  partition only -> UBI did NOT attach
0xE0000003  both           -> UBI is up and volume 0 is readable
```

**Why this shape and not another guess.** The step crumbs have now converted three
ambiguous failures into located ones, and the pattern that makes them work is the same each
time: make the instrument answer *which* of the candidate causes it is, in one observation,
instead of testing one hypothesis per device cycle. The cost of a fire is the scarce
resource here, not the code.

**Still true, and still binding:** the safety net means a successful mount and a failed one
are indistinguishable in the cells - both panic, both `panic=5`, both return the vendor. And
`C18 = 0xC0DE500B` continues to show the hook itself runs and the kernel completes its
initcalls, so nothing about the root= command line is implicated yet.

**Device mutation.** Unchanged: the `kernela` write and its reboots.


---

## Phase 50n (2026-10-09): UBI IS NOT ATTACHING - the partition is there, and two explanations are ruled out from source

**The diagnostic fire answered.** `C1C = 0xE0000002`: **bit 1 set** - the mtd partition
`rootfsb` still resolves by name at `late_initcall_sync` - and **bit 0 clear** - no ubiblock
device. By the encoding that means **UBI did not attach**. So the partition exists and is
findable, and UBI is refusing it. One fire, one located fact, no guessing.

**Two candidate causes were then eliminated from the source rather than by another fire.**

*Link order is fine.* `drivers/mtd/Makefile` puts `obj-y += ... nand/ ...` **before**
`obj-$(CONFIG_MTD_UBI) += ubi/`, so our driver's `device_initcall` probe registers the mtd
and its partitions before `ubi_init` runs. Had it been the other way round, the fix would
have been a one-line initcall level change - and it would have been wrong.

*Init level is fine.* `ubi_init` is a **`late_initcall`** (and it calls `ubiblock_init()`
itself rather than the latter having its own init), while this hook is
`late_initcall_sync` - which runs after every `late_initcall`. So the kernel's own attach
has already been attempted by the time the hook looks, and the hook is not racing it.

**What remains is that the attach itself fails**, so the hook now asks instead of inferring:
when the volume will not open it calls `ubi_attach_mtd_dev()` on our own mtd and stamps the
outcome.

```
0xE1000000 | errno    the attach refuses, and the errno names the cause exactly
0x500B0000 | ubi_num  the attach SUCCEEDED here - so the kernel's command-line attach is
                      what did not take, not UBI
```

and on that success path it goes on to open the volume, so a working read still reports the
squashfs magic `0x73717368`.

**The honest accounting.** This is the third device cycle spent on this one call: the first
taught the volume's name, the second taught that the name was not the whole story, the third
located the failure to "UBI did not attach" and eliminated two of its explanations from
source. Each fire has narrowed the space rather than repeated it, which is the property worth
keeping - but the pattern to note is that I have been fixing one hypothesis per cycle rather
than instrumenting for the answer first, and the last two commits have moved toward the
latter. That is what the next fire reads: an errno, not a coin flip.

**Device mutation.** Unchanged: the `kernela` write and its reboots.


---

## Phase 50o (2026-10-09): THE EINVAL HUNT - every path accounted for, the geometry cleared from the flash itself, and a flaw in my own instrument

**The errno fire.** `C1C = 0xE1000016` = `0xE1000000 | 0x16` = **errno 22 = `EINVAL`** from
`ubi_attach_mtd_dev()`.

**The source audit, and it came up empty.** Every `EINVAL` on the attach path was enumerated
across `build.c`, `io.c`, `vmt.c`, `wl.c`, `scan.c` and `eba.c`, and each one is either
unreachable for us or arithmetically satisfied:

- `io_init()`'s checks: `min_io_size` = `writesize` = 2048 is a power of two; `max_write_size`
  = `writebufsize` = 2048 is equal to it and a power of two; `vid_hdr_offset` resolves to
  `ec_hdr_alsize = ALIGN(64, 2048) = 2048`; `leb_start = ALIGN(2048 + 64, 2048) = 4096`;
  `vid_hdr_shift` is never set (0, so `% 4` passes); `numeraseregions` is 0.
- the type checks (`MTD_UBIVOLUME`, `MTD_MLCNANDFLASH`), the `ubi_num`/`max_beb_per1024`
  range checks: all fine with `UBI_DEV_NUM_AUTO` and a device `MDT_NANDFLASH`.
- `vmt.c`'s and `wl.c`'s `EINVAL`s are sysfs, resize, erase and bitflip paths - not attach.

**And the geometry was cleared from the flash itself, not from reasoning.** The partition
dump's EC headers read `magic 0x55424923`, `version 1`, **`vid_hdr_offset 2048`**,
**`data_offset 4096`**, `ec 0` - which is exactly what our kernel computes from our mtd's
writesize. So `validate_ec_hdr()` has nothing to object to, and the "our geometry disagrees
with the image" hypothesis is dead: it was checked against the image, offline, for free.

**Then the flaw in my own instrument.** The diagnostic called
`ubi_attach_mtd_dev(fmc->mtd, ...)` on the **master** - while the kernel's `ubi.mtd=rootfsb`
attaches the **partition**. They are different mtd devices: the master spans the whole
128 MiB chip including kernel, u-boot and parameter regions that are **not UBI at all**, so
UBI's scan of it can fail for reasons the partition never would. **The errno I measured is
therefore not necessarily the kernel's error**, and that is worth stating plainly rather than
building on it.

**Fixed** (`bab9e32`): the diagnostic now does `get_mtd_device_nm("rootfsb")` and attaches
*that*, mirroring the kernel's own call, and then opens volume 0. The reading keeps its
shape - `0xE1<errno>` if it refuses, `0x500B<ubi_num>` if it attaches but the volume will not
open, `0xE2000000` if the partition is missing, and the squashfs magic `0x73717368` if it all
works.

**The honest tally.** Four instrument revisions on this one call. Three measured something
real; this fourth corrects a mistake in the measuring rather than a hypothesis about the
kernel, which is the more expensive kind to find late. The lesson worth keeping: when an
instrument returns an error code, check that it is asking the same question the kernel asks -
a diagnostic that uses a different input than the code under test reports its own error, and
it looks exactly like the kernel's.

**Device mutation.** Unchanged: the `kernela` write and its reboots.


---

## Phase 50p (2026-10-09): THE ERRNO IS THE KERNEL'S, THE FLASH IS VALID - so the suspect is our READ, and the test is now aimed there

**The corrected diagnostic settled the instrument question.** Attaching the **partition**
(not the master) returns the **same `EINVAL`**, so `0xE1000016` is the kernel's error and
not an artefact of my call.

**And the flash itself is clean.** Every UBI-bearing PEB in a dump of that partition was
checked, not a sample: **all 120** carry a valid EC header - `magic 0x55424923`, `version 1`,
`vid_hdr_offset 2048`, `data_offset 4096`, `ec 0` - and the CRC checks out.

**A convention worth writing down, because getting it wrong made the flash look broken.**
UBI's `crc32()` is initialised with `0xFFFFFFFF` and carries **no final inversion**, so the
value stored on the flash equals **zlib's `crc32` XOR `0xffffffff`**. Checking the dump with
zlib alone reported **120 of 120** EC headers as corrupt when all 120 were fine. That is the
same class as the offset errors this project has paid for before: a wrong *convention* returns
a plausible wrong answer, and it is only caught by cross-checking against something that must
agree. It is now a named constant in the driver (`LUOFU_UBI_CRC32_INIT`).

**What remains, and it is now a narrow question.** UBI's attach rejects our partition with
`EINVAL`; every `EINVAL` on that path has been accounted for from source and none should trip
for this geometry; and the data on the flash is valid. The remaining suspect is **what our
read path hands UBI**. So the hook now asks the flash directly: on a failed volume open it
walks the first 32 PEBs of the partition and applies exactly `ubi_io_read_ec_hdr()`'s
acceptance test - magic, version, `vid_hdr_offset`, `data_offset`, `ec` range and the CRC over
the first 60 bytes.

```
0x5C2000FF              all 32 accepted -> the read path is fine
0x5C<pass><first bad>   it stopped at that PEB
0xE0000000 | errno      mtd_read() itself refused
```

The expected answer is known from the dump, so this is a comparison against a reference rather
than a probe: the first 120 PEBs are valid, therefore **`0x5C2000FF` is the pass**, and any
other value localises the fault - to the read path as a whole, or to one named PEB.

**Caught before pushing, and worth the two minutes it took:** an earlier block replacement had
dropped the `#define` for `LUOFU_ROOTFS_VOL_ID` while leaving both of its uses in place. That
is a compile error, and with a 35-minute build cycle it is the expensive kind - the same class
as the duplicated comment terminator three phases ago, and found this time by checking that
every symbol the file uses is defined rather than by the compiler.

**Device mutation.** Unchanged: the `kernela` write and its reboots.


---

## Phase 50q (2026-10-09): THE READ PATH IS PROVEN AND THE FLASH IS PROVEN - and UBI still says EINVAL, so the next move is to make the kernel's own log readable

**The read-path test passed, and it is the strongest verification this driver has had.**

```
C1C = 0x5C2000FF      pass count 0x20 = 32 PEBs accepted, first-bad 0xFF = none
```

The driver walked the first 32 PEBs of the partition and applied **exactly**
`ubi_io_read_ec_hdr()`'s acceptance test - magic `0x55424923`, `version 1`, `vid_hdr_offset`,
`data_offset`, the `ec` range and the CRC over the first 60 bytes - reading through the MTD
layer. **All 32 passed.** So our reads deliver byte-perfect data, verified against an
independent reference rather than against themselves.

**And the whole partition was then validated offline, header by header:**

- **120 EC headers**, all valid: magic, version 1, `vid_hdr_offset 2048`, `data_offset 4096`,
  `ec 0`, CRC correct.
- **120 VID headers**, all valid: magic `0x55424921`, version 1, and **zero CRC mismatches**.
- The **layout volume** is correct: `vol_id = 0x7FFFEFFF = UBI_LAYOUT_VOLUME_ID`,
  `vol_type = DYNAMIC`, `lnum 0..1`, `compat = 5 = UBI_COMPAT_REJECT =
  UBI_LAYOUT_VOLUME_COMPAT`.
- The **rootfs volume** is correct: `vol_id 0`, `vol_type = STATIC`, 118 PEBs, `lnum 0..117`,
  `data_size 126976`, `used_ebs 118` - which is exactly 118 x 126976 = 14,983,168 bytes for
  the 14,864,384-byte squashfs the live system reports.

**Two of my own readings were wrong along the way, and both were caught by checking the
source instead of trusting recall.** First the CRC convention (UBI's `crc32` omits the final
inversion, so the stored value is `zlib.crc32 XOR 0xffffffff` - checking the dump naively
reported 120 of 120 headers corrupt). Then the compat constant: I was sure
`UBI_COMPAT_REJECT` was 4 and the flash's 5 was therefore invalid; `ubi-media.h` says
**5**, so the flash was right and I was wrong. Both are the same lesson this project has paid
for repeatedly - **a remembered constant is a hypothesis, and the artifact outranks it.**

**So where this stands, honestly.** The flash is valid, our reads are valid, and every
`EINVAL` on UBI's attach path has been read from source and is either unreachable or
arithmetically satisfied for this geometry. UBI still returns `EINVAL`. **Static analysis has
reached its limit here**, and the next move is not another inference - it is to make the
kernel's own log readable, which UBI fills with the exact reason ("bad write buffer size",
"validation failed for PEB %d", "bad vol_id", ...).

**The route to a readable log, and the constraints that shape it.** pstore_blk is out: it
writes to the pstore MTD partition, and this driver has no write path - by design. ramoops is
in play because `CONFIG_PSTORE_RAM` needs a reserved-memory node only when the devicetree is
ours, and **the kernel boots the vendor's devicetree**, so it must be configured by command
line instead: `ramoops.mem_address=` / `ramoops.mem_size=`. The region has to satisfy two
things - it must not collide with the flashinfo ATAG at `0x80601000`, and it must live **below
`0x80608000`**, which is the zone the record already established as surviving the vendor
kernel's return. A deliberate panic then captures dmesg there, and `devmem` reads it back.

**Device mutation.** Unchanged: the `kernela` write and its reboots. The router is healthy.


---

## Phase 50r (2026-10-09): GIVING THE KERNEL A VOICE - ramoops on the command line, because every failure so far has been inferred rather than read

**The problem this fixes, stated plainly.** This board has no console. Every failure in this
phase - the step-9 rejection, the NULL `page_buf`, the `EINVAL` from UBI's attach - has been
localised by instrumenting the driver and reading blank cells, because the kernel's own
explanation went to a printk buffer nobody can see. UBI has been writing the answer to
`printk` the entire time: `"bad write buffer size"`, `"validation failed for PEB %d"`,
`"bad vol_id"`, `"bad compat"`. Stage C's step crumbs narrowed the search; a readable log
would have ended it.

**ramoops is the instrument, and the reason it works here is the reason it had to be RAM.**
pstore_blk is out: it writes to the pstore MTD partition and this driver has no write path,
by design. ramoops backs printk with a RAM console, and RAM needs no `_write` at all - so it
is compatible with the read-only property the driver has kept since stage A.

**Configured from the COMMAND LINE, not the devicetree,** because the kernel boots the
vendor's devicetree - the same fact that cost a fire back in phase 50:

```
ramoops.mem_address=0x80602000   ramoops.mem_size=0x4000
ramoops.record_size=0x1000       ramoops.console_size=0x2000
ramoops.ftrace_size=0            ramoops.pmsg_size=0
```

**The region satisfies three constraints that were each already established:** it sits inside
the flashinfo reserved area (`0x80600000` + 4 MiB), which **both** kernels' devicetrees
reserve so neither allocates it; it is clear of the flash-spec ATAG at `0x80601000`; and it
is **below `0x80608000`**, the zone already measured to survive the vendor kernel's return -
which matters because the log is read back with `devmem` from the vendor system after this
kernel folds over, exactly as every other result in this phase has been.

**And the sizes are checked against ramoops' own arithmetic rather than guessed.** Reading
`ramoops_probe` shows:

```c
	dump_mem_sz = cxt->size - cxt->console_size - cxt->ftrace_size - cxt->pmsg_size;
	err = ramoops_init_przs("dmesg", dev, cxt, &cxt->dprzs, &paddr, dump_mem_sz, cxt->record_size, ...);
	err = ramoops_init_prz("console", dev, cxt, &cxt->cprz, &paddr, cxt->console_size, 0);
```

so `0x4000 - 0x2000 = 0x2000` of dmesg zones (two of `0x1000`) followed by the `0x2000`
console - exactly the `0x4000` reserved, with each zone 4 KiB-aligned as ramoops requires.
That check is the same discipline that caught the CRC convention and the compat constant:
read the code, do not trust the recollection of it.

`ignore_loglevel` joins the command line so nothing is filtered on the way to the zone, and
`CONFIG_PSTORE`, `CONFIG_PSTORE_CONSOLE` and `CONFIG_PSTORE_RAM` were already in the fragment
and asserted by the image job - so the whole change is one string.

**What the next fire should produce.** Not a crumb value but a transcript: after our kernel
fails and hands over, `devmem 0x80602000` on the vendor system should show the printk text -
including, specifically, whichever UBI message explains the `EINVAL`. That converts the
remaining question from an inference into a reading, and it makes every subsequent failure in
this project legible rather than measurable.

**Device mutation.** Unchanged: the `kernela` write and its reboots.


---

## Phase 50s (2026-10-09): THE FIRST RAMOOPS ATTEMPT KILLED THE EARLY BOOT - the crumbs localised it to a window, and two things were wrong

**What the fire returned, and it was not a log.** `C18 = 0xC0DE0003`, `C1C = 0x18C5387D`, and
the readback of both ramoops zones was empty.

**Read against the mach file, those two values say exactly where the kernel died.**
`LUOFU_CRUMB_DONE = 0xc0de0003` is stamped at the **end of `luofu_init_machine`**
(`mach-luofu/luofu.c:138`) - and `C18` never reached `0xC0DE0010`, the `early_initcall`
crumb. So this kernel **died between machine init and the very first initcall**, long before
the driver's probe; and `C1C` still holding the head code's own `0x0018...` leftover confirms
that nothing of ours ever ran. The empty log follows: `ramoops_init` is a `postcore_initcall`
and had not been reached.

**So the crumb protocol earned its keep for the fourth time** - a boot that produced no
output at all still reported *which window* it died in, from two words in sysctrl.

**Two things were wrong, and both are now fixed.**

**1. The ramoops region was inside our own kernel.** `0x80602000` looked free because the
record says cells below `0x80608000` survive the **vendor** - but that is a statement about
the vendor not clobbering them, and it says nothing about our own image. Our `Image` is
**9,984,344 bytes loaded at `0x80008000`**, so it spans to about **`0x8098D4D8`**, and an
8 KiB log buffer at `0x80602000` would be written into the very code doing the writing. The
flashinfo reserved area runs `0x80600000..0x80A00000`, so the window between our image's end
and that ceiling is the one place that is **both** outside our kernel **and** reserved by the
vendor's devicetree as well - which is what makes it survive the handover to be read back.
The zone moves to **`0x809A0000`**.

**2. `ignore_loglevel` is gone.** Its action lands in exactly the window where the kernel
died - it floods the console path during early boot - and it is **unnecessary**: pstore's
console callback receives everything at or above the console loglevel, and UBI's `ubi_err()`
messages are `KERN_ERR`, so they arrive without it. It was a gratuitous addition made "for
completeness", and it is removed rather than defended.

**The lesson worth keeping, because it recurs in this project.** A region can be safe from
the *other* kernel and fatal to *this* one, and the two questions are separate: "will the
vendor preserve it?" was answered and correct, while "does our own image already live
there?" was never asked. The `Image` size was printed in every manifest this phase produced.

**Device mutation.** Unchanged: the `kernela` write and its reboots. The router is healthy.


---

## Phase 50t (2026-10-09): THE ARTIFACT DIFF NAMED THE KILLER - the ramoops cmdline params - and the capture moves to a kmsg_dumper that needs none

**The second ramoops attempt died identically.** `C18 = 0xC0DE0003` again, never reaching
`0xC0DE0010`, and the readback empty again. So neither of my two fixes was the cause, and the
death is still between `init_machine` and the first initcall.

**Then the diff settled it in one line.** The two build artifacts - the EC-scan build that
booted fine and the ramoops build that did not - **differ in exactly ONE config line out of
2914: `CONFIG_CMDLINE`.** Everything else is byte-identical.

```
< CONFIG_CMDLINE="panic=5 ubi.mtd=rootfsb ubi.block=0,0 root=/dev/ubiblock0_0 rootfstype=squashfs rootwait init=/nonexistent-init"
> ...same... + ramoops.mem_address=... mem_size=... record_size=... console_size=... ftrace_size=... pmsg_size=...
```

So the six ramoops parameters alone were fatal. And they act exactly where the crumbs had
already placed the death: `parse_args()` runs **after `setup_arch` (hence after
`init_machine`) and before any initcall** - the precise window `C18 = 0xC0DE0003` reports.

**Two earlier guesses were real defects but not this one,** and both are worth keeping as
such: the first region *was* inside our own kernel image, and `ignore_loglevel` *was* a
gratuitous addition that would flood the early console path. They were right to fix and wrong
to blame, which is the difference between a defect and a cause - and the way to tell them
apart was to compare two artifacts rather than to reason about the code a third time.

**So the mechanism changes rather than the parameters.** `ramoops` is out and the driver
registers a **kmsg_dumper**:

- it takes **no command-line parameters at all**, so the fatal path is never touched;
- it fires on the **panic this kernel already takes at the rootfs mount**, which happens
  *after* UBI has had its say at `late_initcall` - so the message we want is in the log;
- and it writes to the same `0x809A0000`, chosen the same way: above our own `Image`
  (9,984,344 bytes from `0x80008000`, ending about `0x8098D4D8`) and below the `0x80A00000`
  ceiling of the flashinfo reserved window, so it is **both** outside our kernel **and**
  reserved by the vendor's devicetree.

The buffer is 128 KiB, the walk is bounded by that size so a long log cannot overrun it, and
registration is the **last** thing `probe()` does so a missing buffer cannot spoil any
measurement above it. The API was checked against 5.10's own `kernel/printk/printk.c`
(`kmsg_dump_register`, `kmsg_dump_get_line`, `kmsg_dump_rewind`, all with the
`struct kmsg_dumper` signatures) rather than recalled.

**The generalisable move, because it is now twice in one phase:** when a change breaks boot
and more than one thing changed, **diff the two artifacts** before theorising about which
change did it. A 2914-line config diff answered in one command what three rounds of reasoning
had got wrong.

**Device mutation.** Unchanged: the `kernela` write and its reboots.


---

## Phase 50u (2026-10-09): THE DUMPER BOOTS, THE LOG IS SCRUBBED - and I applied one rule while ignoring another from the same record

**The boot is fixed.** `C18 = 0xC0DE500B` and `C1C = 0x5C2000FF`: the probe ran, the EC scan
still passes 32 of 32, and the kernel completes its initcalls. That confirms what the
artifact diff said - **the ramoops command-line parameters were the cause** of the two
earlier early-boot deaths - and it clears the `kmsg_dumper` code of suspicion.

**But its log read back EMPTY at `0x809A0000`, and the record had already said so.**
Verbatim, from the earlier work: *"A cell for post-boot readback must live BELOW 0x80608000
(the vendor kernel's own image span scrubs everything above on its return)."* I chose
`0x809A0000` by applying the **"outside our own kernel"** rule - correct as far as it goes,
since our `Image` spans `0x80008000` to about `0x8098D4D8` - and **ignored the "survives the
vendor" rule that the same document had established.** Two rules, one applied.

**And they CONFLICT for anything large.** The vendor-preserved zone is below `0x80608000`;
our own image covers all of it. For a 4-byte cell that was workable - the old instrument
wrote `0x80600F20` and it survived - but nothing of that size fits a log.

**So both regions get a buffer, 8 KiB each, and the panic path writes both:**

| address | why | expected |
|---|---|---|
| `0x809A0000` | outside our kernel | scrubbed by the vendor |
| `0x80606000` | vendor-preserved | survives - but it is inside our `.data` |

Writing into our own `.data` would corrupt a running kernel at any normal time; **at panic
time it does not matter**, because the kernel is dead and its only remaining job is to
reboot. So **nothing is written at registration** - the buffers are touched only from the
panic path - and each opens with a magic word (`0xC0DE1055`) written *before* the log, so the
readback distinguishes three cases that were previously indistinguishable: magic + text (ran
and survived), magic with no text (ran, log empty), or all zeros (never ran, or scrubbed).

The copy is circular - it wraps to the start when full - so what survives is the **newest**
log, where the UBI message and the mount panic are, rather than the oldest boot messages.
Writing both at once means one fire reports which region survives rather than needing two.

**The pattern worth naming, because it is the third time in this phase:** the answer was
already in my own notes and I applied half of it. The artifact diff found the ramoops cause
the same way - by consulting evidence already on disk instead of reasoning forward again.

**Device mutation.** Unchanged: the `kernela` write and its reboots.


---

## Phase 50v (2026-10-09): NEITHER BUFFER HOLDS THE MARK - so the dumper never wrote, and zeroes could not say why

**The two-buffer fire booted cleanly** (`C18 = 0xC0DE500B`, `C1C = 0x5C2000FF` - probe ran, EC
scan still 32/32) and then returned something I had not allowed for:

```
MAGIC_B (0x80606000) = 0x00000000
MAGIC_A (0x809A0000) = 0xE34C1094
```

**Neither buffer holds the panic mark `0xC0DE1055`.** The A value is **ARM code**, not a number
this driver ever wrote - so the vendor scrubbing the region above `0x80608000` is consistent
with the record, and that half is explained. But **ZERO at B is not**: B is *below* `0x80608000`,
the zone the record measured as surviving the vendor, so a successful write there should still
be readable.

**Both markless means the dumper never wrote at all** - so either both `devm_ioremap()` calls
returned NULL, or `kmsg_dump_register()` failed, and the previous code could not tell either of
those apart from "it ran and got erased". That is the same class of gap the step crumbs closed
earlier in this phase: **an absence that cannot name its own cause.**

**So each buffer now gets an ARMED mark (`0xC0DE10A0`) written at REGISTRATION time**, while the
kernel is alive, which makes a single readback tell the three cases apart:

| readback | meaning |
|---|---|
| `0xC0DE10A0` | the buffer was mapped - the mapping works, the dumper did not run |
| `0xC0DE1055` | the dumper ran (it writes this over the armed mark) |
| neither | the mapping failed, or the region was scrubbed |

Four bytes per buffer, written once, and deliberately the size a previous instrument already
proved survivable in exactly this region: the older breadcrumbs wrote 4-byte cells at
`0x80600F20` inside the same `.data` for many fires without harm. The panic path is unchanged
and still writes the log itself.

**Device mutation.** Unchanged: the `kernela` write and its reboots. The router is healthy.


---

## Phase 50w (2026-10-09): ioremap REFUSES RAM ON ARM - which is why no mark ever appeared, and why every crumb always did

**The armed-mark fire put the answer in the ABSENCE of the marks.** `0x80606000` read
`0x00000000` and `0x809A0000` read `0xE34C1094` - an ARM instruction. The armed mark is
written at **registration time, while the kernel is alive**, so its absence can only mean that
`devm_ioremap()` returned **NULL for both buffers**: the dumper had nothing to write to and
never wrote anything. The values being read were simply whatever RAM happened to hold.

**The cause.** On ARM, `ioremap()` **refuses valid RAM outright** -
`__arm_ioremap_pfn_caller()` contains `WARN_ON(pfn_valid(pfn))`, "Don't allow RAM to be
mapped" - and both of these buffers are RAM. `memremap()` exists for exactly this case and is
what `ramoops` itself uses.

**And that single fact explains the whole shape of this phase's instruments:**

| address | type | worked? |
|---|---|---|
| `0x10100C18` sysctrl crumb cell | **I/O** - `devm_ioremap` maps it happily | **yes, reliably, all along** |
| `0x80600F20` old RAM cells | RAM | worked then, but written by a different route |
| `0x80606000`, `0x809A0000` log buffers | RAM | **no - ioremap returned NULL** |

Same function, different memory type, and I had been treating them as interchangeable. The
breadcrumbs have reported reliably for this entire phase precisely because sysctrl is an I/O
region, so nothing about them ever hinted at this.

**The fix:** `memremap(MEMREMAP_WB)` with plain pointer writes - the mapping is memory, not
I/O, so `memcpy` rather than `memcpy_toio`. Cached writes are fine here: the previous
instrument wrote 4-byte cells into this same region and those values survived a reboot and
were read back with `devmem`, so cached writes do reach DRAM on this reset path. The
armed/panic marks are unchanged, so the readback still distinguishes mapped, ran, and scrubbed.

**The meta-lesson, and it is the third framing of the same thing in this phase:** an absence
has to be made to name its own cause. The crumbs did it for the boot, the artifact diff did it
for the ramoops parameters, and the armed mark did it here - each time by writing something
that *should* be there if the mechanism worked, so that its absence means one specific thing.

**Device mutation.** Unchanged: the `kernela` write and its reboots.


---

## Phase 50x (2026-10-09): THE FIRST BOOT THAT COMPLETED EVERY INITCALL - and two placement errors it exposed

**The memremap build booted further than any before it.** `C18 = 0xC0DE0020` is the mach's
**late_initcall** crumb, meaning **every initcall completed** - and then the kernel died before
`late_initcall_sync`, leaving `C1C` at its earlier stage-B value (`0x23494255`, the ASCII
"UBI#") so the stage-D hook never ran at all. The armed marks read:

```
ARMED_B (0x80606000) = 0x00000000
ARMED_A (0x809A0000) = 0xE34C1094   (ARM code, not a mark)
```

**Two placement errors, both now fixed, and one piece of good news.**

**1. Writing B while the kernel was alive is what killed it.** The armed mark went into our own
`.data`, where four live bytes break a structure the kernel reads later - which is exactly why
the death *moved forward* to late_initcall time rather than disappearing. Nothing is written at
registration now; both buffers are written **only from the panic path**, when the kernel is
already dead and corrupting its data can cost nothing but the reboot it is about to perform.

**2. The vendor's scrub line is lower than `0x80608000`.** B read back **zero**, and the record's
boundary had been treated as exact. The address actually *proven* to survive is the old
breadcrumb cell at **`0x80600F20`** - so the buffer moves to **`0x80600000`, 4 KiB**, a window
that ends at `0x80601000` and so stays clear of the flash-size ATAG the vendor itself reads
there, while containing the proven address.

**And the good news, which is the important half:** the armed write to B **did happen** - that is
precisely what killed the kernel. **So `memremap()` returned non-NULL and the mapping mechanism
now works.** The `ioremap`-refuses-RAM diagnosis was right, the fix took, and what remains is
purely *where* and *when* to write. The instrument is sound.

**The armed mark is retired** - a mark that only ever gets scrubbed, or only ever corrupts the
kernel, teaches nothing that the panic log will not teach more directly. The panic mark
`0xC0DE1055` is unchanged.

**Device mutation.** Unchanged: the `kernela` write and its reboots. The router is healthy.


---

## Phase 50y (2026-10-09): THE FIFTH FAULT - the panic path only ever dumps EMERG, so PANIC filtered out the dumper

**The placement fix worked.** The boot is back to full operation - `C18 = 0xC0DE500B`,
`C1C = 0x5C2000FF`: the stage-D hook ran and the EC scan still passes 32 of 32, so **every
initcall now completes**. And the panic buffer still held no mark (`0x76CC66CC` at
`0x80600000`, which is neither of mine).

**So the dumper was registered, the mapping worked, the address survived - and it was still
never called.** The reason is in the kernel's own source, not in anything I wrote:

```c
	if (reason > max_reason)
		continue;			/* kmsg_dump()'s filter */

	void emergency_restart(void)
	{
		kmsg_dump(KMSG_DUMP_EMERG);	/* the ONLY dump this kernel performs */
		machine_emergency_restart();
	}
```

and **`panic()` never calls `kmsg_dump` at all** - `printk.c` contains no such call outside
`kmsg_dump`'s own definition. The enum runs `UNDEF, PANIC, OOPS, EMERG, SHUTDOWN, MAX`, so
`EMERG` is **3** and `PANIC` is **1**: `max_reason = KMSG_DUMP_PANIC` filtered out the only
dump that ever happens. **The dumper was armed against an event that never fires.**

`max_reason` is now `KMSG_DUMP_MAX`, so the dump that actually happens - `EMERG` from
`emergency_restart()` - is accepted.

**And this is the fifth distinct fault in ONE instrument,** worth naming because the pattern
matters more than any single fix:

| # | fault | the evidence that separated it |
|---|---|---|
| 1 | six ramoops cmdline params were fatal | the artifact diff (2914 config lines, one differs) |
| 2 | the region was inside our own kernel | the record's own scrub rule |
| 3 | `ioremap` refuses RAM on ARM | the absent armed mark |
| 4 | a live write into our own `.data` killed the boot | the late_initcall crumb |
| 5 | `max_reason` filtered out the only dump | the kernel's own source |

**Every fix was correct and none was sufficient alone, because the instrument had five
independent ways to fail silently** - and a silent failure of a log-capture instrument is
indistinguishable from "there was nothing to log". That is the cost of building a new
instrument rather than reading a document, and the compensations are that each fault is now
understood rather than guessed, and that the same instrument will serve every remaining
failure in this phase.

**Device mutation.** Unchanged: the `kernela` write and its reboots. The router is healthy.


---

## Phase 50z (2026-10-09): FIVE FIXES AND STILL AN EMPTY BUFFER - so stop asking how the log is written and ask whether the panic happens at all

**The `max_reason` fix did not land either.** The boot is still full-op (`C18 = 0xC0DE500B`,
`C1C = 0x5C2000FF`) and `0x80600000` still read `0x76CC66CC` - not the mark.

**Step back and look at what the five fixes had in common.** The ramoops parameters, the
region, `ioremap` vs RAM, the live write, the reason filter - **every one of them was about
HOW the log gets written.** Not one established the thing underneath: **that the panic happens
at all, and that a hook on that path actually runs.** Five correct repairs to a mechanism
whose trigger was never verified.

**So the next instrument uses the one channel in this phase that has never once failed.** A
**panic notifier**, whose first act is a **crumb to the SYSCtrl cell** - I/O, not RAM, which is
exactly why the breadcrumbs have reported reliably since the first fire of this phase:

| readback | meaning |
|---|---|
| crumb 42 appears | the panic **happened** and a panic-time hook **runs** — any remaining fault is inside the log-writing code |
| crumb absent | the kernel **never panicked**, and every RAM theory so far was about the wrong event |

Either answer is specific, which is the whole point. The notifier also performs the log
capture itself, making it a second, independent trigger alongside the `kmsg_dumper`.

**And buffer B moves once more - to `0x80600c00`, 1 KiB, straddling `0x80600F20`.** My previous
choice, `0x80600000`, was a kilobyte *below* the only address ever measured, and it read back
zeroes; u-boot may well scratch the first pages of that window before the vendor kernel runs
at all. **Anchoring on the measured point instead of on my inferred boundary** - which is the
same correction I had to make once already in this phase, when `0x80608000` turned out to be a
guideline rather than a line.

**Device mutation.** Unchanged: the `kernela` write and its reboots. The router is healthy.


---

## Phase 50aa (2026-10-09): THE KERNEL NEVER PANICS - six faults, all real, all about a moment that never arrives

**The panic notifier answered its own question by NOT firing.** `C18` stayed at the stage-D
hook's crumb (`0xC0DE500B`) instead of becoming step 42, and the buffer was empty again. By
the rule written into that instrument, **an absent crumb means the kernel never entered
`panic()` at all.**

**That reframes the whole exercise.** The kernel does not die - it **hangs** where the root
device never appears: UBI refuses to attach, so `ubiblock0_0` never exists and `rootwait`
keeps it waiting. Something then resets the box. **A hang calls neither `kmsg_dump()` nor any
notifier**, which is why every panic-based design returned an empty buffer no matter how many
of its own faults were repaired.

**Six faults, every one real, every one about a moment that never arrives:**

| # | fault | separated by |
|---|---|---|
| 1 | ramoops cmdline params were fatal | the artifact diff |
| 2 | the region was inside our own kernel | my own scrub rule, applied halfway |
| 3 | `ioremap` refuses RAM on ARM | the armed mark's absence |
| 4 | a live write into our `.data` killed the boot | the late_initcall crumb |
| 5 | `max_reason` filtered out the only dump | the kernel's own source |
| 6 | **the panic never happens** | the panic notifier's absent crumb |

**So the capture stops waiting for a die.** A 3-second timer schedules a workqueue job that
snapshots the current log into the buffer - so whatever the kernel is doing when it finally
goes down, **the buffer already holds the most recent log, because it was written while the
kernel was still running.** A workqueue rather than the timer callback directly, because
`kmsg_dump_get_line` takes printk's internal lock and must not run in softirq context.

**And the vendor's own memory map explains the preservation rule as a plain fact:**

```
80600000-87ffffff : System RAM
  80608000-80fdcfff : Kernel code
```

**The vendor's kernel does not load at `0x80008000` - it decompresses to `0x80608000`.** That
is why everything below that address survives a vendor boot, and it is the first **external**
confirmation of the address choice, which until now rested on a single cell from our own
earlier work. Buffer B at `0x80600c00` straddles the proven `0x80600F20` and sits wholly below
the vendor's kernel.

**The generalisable lesson, and it is the sharpest one in this phase:** when an instrument
fails silently, its *trigger* must be verified before its *mechanism* is repaired. Six
correct repairs to the mechanism taught nothing, because the event being instrumented never
occurred. One crumb on the trigger channel settled it.

**Device mutation.** Unchanged: the `kernela` write and its reboots. The router is healthy.


---

## Phase 50ab (2026-10-09): BOTH MAPPING APIS RETURN NULL FOR THIS RAM - so address it through `__va`

**The snapshot-timer build booted full-op and the buffer was still untouched.**
`0x80600c00` read `0x66EC66CC`, and every word around it carried the repeating `66CC` pattern
of RAM nothing has ever written.

**That could only mean `luofu_log_b` was itself NULL** - because the timer fires three seconds
after the probe, and each of the two candidate excuses was checked and eliminated from the
kernel's own source rather than argued:

- **the timer path is safe** - `kmsg_dump_get_line()` takes `logbuf_lock` via
  `logbuf_lock_irqsave`, and `logbuf_lock` is a **`DEFINE_RAW_SPINLOCK`**: taken with interrupts
  off, it neither sleeps nor needs process context, so a timer callback may call it;
- **the workqueue was running** - `init/main.c` calls `workqueue_init()` at line **1511**,
  before `do_basic_setup()` at **1526** and `prepare_namespace()` at **1538**, so workers exist
  long before the root-device wait.

**So both mapping APIs failed on this RAM.** `ioremap()` refusing RAM is documented ARM
behaviour; `memremap()` turned out to be no better here. **Two APIs, two failures, and no mark
to show for either** - and the earlier inference that "the armed write corrupted the kernel,
therefore the mapping works" was wrong for the same reason: with no write possible, that death
had another cause entirely.

**Both are now gone; the buffers are reached through `__va()`.** These addresses are ordinary
RAM inside the devicetree's memory node - the vendor's own map shows `80600000-87ffffff` as
System RAM - so the linear map already covers them and `__va()` is simply where that memory
lives from kernel code. **No new mapping to fail, no cache-type to get wrong.**

Cached writes through the linear map are acceptable for a **measured** reason: an earlier
instrument in this phase wrote 4-byte breadcrumbs into this same region through this same kind
of mapping, and those values survived a reset and were read back with `devmem` from the vendor
system.

The workqueue is gone too - the copy now runs directly in the timer callback, removing a
moving part. Buffer B stays at `0x80600c00` with 1 KiB, ending exactly at `0x80601000` and so
never touching the ATAG the vendor itself reads there.

**Device mutation.** Unchanged: the `kernela` write and its reboots. The router is healthy.


---

## Phase 50ac (2026-10-09): THE MARK LANDS - `__va` was the answer, and one boolean was hiding the text

**`0x80600c00` read `0xC0DE1055`.** After seven instrument designs, the mark is in the buffer:
**`__va()` reaches this RAM where both `ioremap` and `memremap` returned NULL**, the timer runs
while the kernel is alive, and the buffer survives the vendor's return. **The instrument is
real** - but the words after the mark were still the `66CC` pattern of untouched RAM.

**The reason is one guard in `printk.c`:**

```c
	if (!dumper->active)
		goto out;			/* returns false, *len = 0 */
```

and `active` is set in **exactly one place** - `kmsg_dump()` itself, on its way into a dumper's
callback. **A dumper whose callback is never invoked - which is this kernel, because it never
panics - stays inactive forever**, so the very first call to `kmsg_dump_get_line()` returns
false and the loop body never runs. The mark was written, the buffer was refreshed every three
seconds, and the log was silently empty.

The timer now sets `active` around its walk. That is safe: it is this dumper's own iterator
state, nothing else walks it, `kmsg_dump()` re-sets it on the panic path, and
`kmsg_dump_get_line()` takes `logbuf_lock` itself - so this neither holds a lock across the
walk nor disturbs a concurrent panic.

**And there is the phase in one line:** this whole stretch has been a fight against absences
that could mean two different things - an empty buffer, a missing crumb, a zero where a mark
should be - each of which had to be made to name its own cause. The last one was a single
boolean.

**Device mutation.** Unchanged: the `kernela` write and its reboots. The router is healthy.


---

## Phase 50ad (2026-10-09): ONE TOKEN EXPLAINS EVERYTHING - `rootwait` spins forever, so the kernel never panics and the capture never runs

**The mark was there and the text still was not** - and `B1` read `0x62C46600`, **byte-identical to
the previous fire's `W1`**, which is what proved those bytes were stale RAM rather than output.
So `kmsg_dump_get_line` still returned false even with `active` set by hand.

**Then `init/do_mounts.c` supplied the answer, in five lines:**

```c
	if ((ROOT_DEV == 0) && root_wait) {
		while (driver_probe_done() != 0 ||
		       (ROOT_DEV = name_to_dev_t(saved_root_name)) == 0)
			msleep(5);
	}
```

**`/dev/ubiblock0_0` can never appear, because UBI refuses to attach. So with `rootwait` on the
command line the kernel SPINS THERE FOR EVER** - it does not panic, does not die, does not
reboot. It waits.

**And that single fact accounts for every anomaly of the last four fires, with no conjecture:**

| observation | explanation |
|---|---|
| the panic notifier's crumb was **absent** | the kernel genuinely never entered `panic()` - exactly what that instrument was built to report |
| the dumper was never invoked | `kmsg_dump()` runs only from the panic path |
| setting `active` by hand produced **no text** | the iterator's real precondition was never satisfied either |
| the box still **returned** | something resets a hung board - which is why every fire looked like a kernel that had "died" |

**The fix is to remove `rootwait`.** The same failure then reaches `mount_block_root()`, every
filesystem fails, and the kernel **panics** - the path this entire mechanism was designed for,
and the one on which `kmsg_dump()` initialises the iterator itself. UBI's message, logged at
`late_initcall` *before* the wait, is then in the ringbuffer and gets captured. `panic=5` stays
in the same single `CONFIG_CMDLINE` value, so the panic still reboots and returns the box, and
the timer remains as a second independent path.

**The lesson, and it is the last one this instrument has to teach:** every one of the eight
designs failed for a *different* reason, and the reason the *trigger* never fired was a single
command-line token that had been sitting in the string since the very first fire. **Verifying
that the trigger occurs is worth more than any amount of repairing the mechanism** - and the
sound of a trigger that never fires is silence, which looks exactly like a mechanism that works
and finds nothing to say.

**Device mutation.** Unchanged: the `kernela` write and its reboots. The router is healthy.


---

## Phase 50ae (2026-10-09): THE KERNEL PANICS NOW - removing `rootwait` was the trigger fix - and the capture moves to a console

**`C18 = 0xC0DE502A`, `C1C = 0xC0DE1042` - crumb step 42 and the panic marker.** For the first
time in this phase, **the kernel panics**, and the panic notifier fired and stamped its crumb
while the box still returned under `panic=5`. **Removing `rootwait` was what changed it**, and
the trigger question is now answered from the trigger itself rather than from an inference.

**The text still did not arrive, and the mark is now attributable.** It came from the
**notifier**, where `dumper->active` is false - so it wrote the mark and the loop yielded
nothing. But the **timer** sets `active` and produced no text either, and `_prb_read_valid`
catches up when a sequence is behind the tail, so the iteration *should* have worked.

**Rather than reason a third time about that API's preconditions** - `active`, `cur_seq`,
`clear_seq`, record size - **the design stops using it.** The driver now registers a
**console**:

```c
static struct console luofu_console = {
	.name  = "luofu",
	.write = luofu_console_write,
	.flags = CON_PRINTBUFFER | CON_ENABLED,
};
```

`CON_ENABLED` means printk uses it from the moment it registers; `CON_PRINTBUFFER` hands it
everything printed before that, which is the boot-time text wanted. **This is what pstore's
console backend does**, and it is the direct route: printk calls the callback for every message
that passes the console loglevel, so UBI's `ubi_err()` lines arrive by the same path they would
reach a serial port. **No ringbuffer to iterate, no cursor to position, no flag to set first.**

The copy is circular so the newest text survives, and the write is a `memcpy` in console
context - it cannot sleep and takes no locks of its own. The `kmsg_dumper`, the panic notifier
and the timer all stay as independent extra paths; the console is simply the one that does not
depend on any of them behaving.

**The arc, stated plainly:** nine designs. Six fixed real faults in how the log was written;
the seventh found that the event never happened (`rootwait`); the eighth made it happen; the
ninth stops reading the log back at all and simply keeps what printk hands over.

**Device mutation.** Unchanged: the `kernela` write and its reboots. The router is healthy.


---

## Phase 50af (2026-10-09): THE LOG IS CAPTURED, AND UBI'S OWN SENTENCE NAMES THE FAULT - our read is wrong at the VID header, not the EC header

**Nine designs, and the console capture works.** printk text now lands in RAM at `0x80600c00` and
is read back with `devmem` from the vendor system. That fight is over, and it is worth naming
what ended it: not another repair to the log-reading API, but **stopping the read-back entirely
and registering a console that keeps whatever printk hands it.**

**And the captured text contains UBI's own words:**

```
<4>error: ubi_attach_mtd_dev: failed to attach mtd14, error -22
```

**with a `ubi_dump_vid_hdr()` field dump right beside it** - `vol_type 102`, `upd_marker 138`,
`name_len 1873`, a blank volume name. **Garbage.** UBI is not rejecting an EC header; it is
rejecting a **VID header**.

**Ground truth, read from the vendor's own MTD driver** (`/dev/mtd14`, which `/proc/mtd` shows
as `rootfsb`, size `0x01740000`, matching our partition exactly):

```
EC  @   0: 55 42 49 23 01 ... "UBI#"   vid_hdr_offset = 2048   data_offset = 4096   VALID
VID @2048: 55 42 49 21 01 01 00 05 7f ff ef ff ... "UBI!"  vol_type=1  compat=5  vol_id=0x7FFFEFFF   VALID
    @4096: 00 00 00 76 00 00 00 01 ... 73 71 75 61 73 68 66 73   "squashfs"
```

**So the flash is correct at offset 2048 and our kernel reads it as garbage.** The fault is in
**our read path at the VID header's offset**, while offset 0 reads perfectly.

**Why every earlier check missed it.** The stage-D hook's EC scan read `mtd_read(part, i *
block_size, 64, ...)` - **always offset 0 of each PEB**, 32 times, and all 32 passed. The
offline dump validated both EC and VID headers and found them perfect. **Neither exercise ever
asked our read path for a byte that was not at a PEB boundary**, so a fault at offset 2048 was
invisible to both. `luofu_mtd_read()` itself looks right - it computes `row = pos / writesize`
and the offset within the page - so the fault is one layer down, in the page read.

**And a capability unlocked by the same result, which changes the pace of everything left:**
the driver can now **print** and I can **read it**. The 32-bit crumb channel is no longer the
only way for the kernel to speak.

**Device mutation.** Unchanged: the `kernela` write and its reboots. The router is healthy.


---

## Phase 50ag (2026-10-09): THE KERNEL CAN SPEAK NOW - a driver that prints, and a read that is wrong only away from the PEB boundary

**The capability that changes the pace of everything left.** With the console capture working,
the driver can **print** and the output is read back with `devmem`. **The 32-bit crumb channel
is no longer the only way for the kernel to say anything** - which for this whole phase has
meant compressing every question into a single word and reading the answer out of a scratch
register. A driver that can write a paragraph and have it read back is a different instrument
entirely.

**The first thing spent on it** is the measurement that could never be made before: the stage-D
hook now reads **32 bytes at offset 0** and **32 bytes at offset 2048** of the same PEB and
prints both with `pr_err`, side by side. That is the first question worth asking, because:

- **UBI's own captured words** say `failed to attach mtd14, error -22`, beside a
  `ubi_dump_vid_hdr()` dump full of garbage - so it rejects a **VID header**, not an EC header;
- **the vendor's own MTD driver** returns a perfectly valid VID header at 2048 of the same
  flash - `55 42 49 21` ("UBI!"), `vol_type 1`, `compat 5`, `vol_id 0x7FFFEFFF`;
- and **the EC scan passed 32 of 32 because it only ever read offset 0** (`i * block_size`),
  as did every earlier validation of this read path. **A fault at offset 2048 was invisible by
  construction, not by bad luck.**

**So the fault is now bounded precisely:** our read path is correct at a PEB boundary and wrong
away from it, and `luofu_mtd_read()` already computes `row = pos / writesize` and the within-page
offset correctly - so the defect is one layer down, in the page read.

**Device mutation.** Unchanged: the `kernela` write and its reboots. The router is healthy.


---

## Phase 50ah (2026-10-09): `-EINVAL` COMES ONLY FROM `validate_vid_hdr` - so the magic read fine and a FIELD failed

**The first diagnostic fire answered half the question.** The captured output contained:

```
[    3.977322] FMC: read off0 err=0 rl=32 5542492306816...
[    3.632146] UBI: ... 4 bytes read back 55 42 49 2...
```

**Our read at PEB offset 0 returns `55 42 49 23` - "UBI#" - exactly what the vendor's own MTD
driver returns at the same offset.** The read path is right where it has always been tested;
the offset-2048 line did not survive the panic dump.

**And `ubi-io.c` narrows the fault further than the captured log could.** In
`ubi_io_read_vid_hdr()`, a **wrong magic returns `UBI_IO_BAD_HDR` - not `-EINVAL`.** The only
`-EINVAL` on that path is:

```c
	err = validate_vid_hdr(ubi, vid_hdr);
	if (err) {
		ubi_err(ubi, "validation failed for PEB %d", pnum);
		return -EINVAL;
	}
```

**So the VID header's magic READ CORRECTLY** - consistent with that `55 42 49 2` fragment -
**and a field inside it failed validation.** That moves the suspicion away from the read and
toward **what `validate_vid_hdr()` compares those fields against**: `ubi->leb_size`,
`ubi->peb_count`, and the geometry this driver hands UBI. A header that is byte-perfect on the
flash can still fail validation if the driver's geometry makes UBI's own checks unsatisfiable.

**Why the bytes now go to fixed addresses instead of the log.** The lines land in the newest
kilobyte of the console buffer, and **the panic that follows dumps a partition list and a stack
trace straight over them** - the printed copies are unreliable by construction. The driver now
writes the two 32-byte reads to `0x80600e00` and `0x80600e80`, plus err/retlen to
`0x80600ec0`, where `devmem` reads them with no interleaving at all.

The console buffer shrinks to 512 bytes so it ends exactly where those diagnostics begin,
keeping every region clear of the flash-spec ATAG: console `0x80600c00-0x80600e00`,
diagnostics `0x80600e00-0x80600ed0`, ATAG at `0x80601000`. All of it in the same 4 KiB that
hundreds of printk writes per boot have already proven inert.

**Device mutation.** Unchanged: the `kernela` write and its reboots.


---

## Phase 50ai (2026-10-09): THE BUILD CAUGHT WHAT MY CHECK MISSED - presence is not scope

**The diagnostic build failed to compile, and the reason was mine:**

```
luofu-fmc.c:884:53: error: 'LUOFU_DIAG_AT0' undeclared (first use in this function)
luofu-fmc.c:885:53: error: 'LUOFU_DIAG_AT2K' undeclared
luofu-fmc.c:893:61: error: 'LUOFU_DIAG_META' undeclared
```

I put the three addresses next to the console buffer in the **stage-E** block, which sits
**below** the stage-D hook that writes them. **The identifiers were present in the file - so the
check I ran, which counted occurrences, passed - and they were not yet in scope.**

**This is the "an edit that reports success is not a verified edit" class**, and the lesson is
about the checker rather than the edit: a count proves a name exists somewhere, never that it is
visible where it is used. **So the validation changed with the code** - it now extracts every
`LUOFU_*` `#define`, finds each macro's first non-comment use, and fails if any use precedes its
definition. It reports **43 macros, all defined before use, no duplicates.**

The addresses move up beside the other stage-D constants, where the hook can see them.

**And the diagnosis from the previous phase stands unchanged:** `-EINVAL` on UBI's VID-header
path comes only from `validate_vid_hdr()`, a wrong magic returns a different code, and the
captured fragment shows the magic read correctly - **so a field failed validation, and the
suspicion is on the geometry this driver hands UBI rather than on the read.**

**Device mutation.** Unchanged: the `kernela` write and its reboots. The router is healthy.


---

## Phase 50aj (2026-10-09): THE READ PATH IS EXONERATED, AND THE REJECTION HAS A NAMED LINE

**The parked bytes settled it, and they settled it in the read path's favour:**

```
META:      err0=0 rl0=32   err1=0 rl1=32
AT0  @   0: 55 42 49 23 01 ...                        "UBI#"   - matches the vendor exactly
AT2K @2048: 55 42 49 21 01 01 00 05 7f ff ef ff       "UBI!" version 1 vol_type 1 compat 5 vol_id 0x7FFFEFFF
```

**Also matching the vendor exactly.** So the flash is right, the driver reads it right at both offsets,
and **`validate_vid_hdr()` is rejecting a byte-perfect header** - which is the one outcome that
puts the whole fault on the *comparison*, not the bytes.

**And the comparison has a named line.** In 5.10:

```c
	if (vol_id >= UBI_INTERNAL_VOL_START && compat != UBI_COMPAT_DELETE &&
	    compat != UBI_COMPAT_RO && compat != UBI_COMPAT_PRESERVE &&
	    compat != UBI_COMPAT_REJECT) {			/* the set is {0,1,2,3} */
		ubi_err(ubi, "bad compat");
		goto bad;
	}
```

**Our header carries `compat = 5`, and the vendor's own dump shows the same `05`** - so the
vendor's UBI accepts a value this kernel's does not. For a vendor-written flash, that is a
plausible shape for the whole failure.

**But the captured log showed a DIFFERENT PEB failing** - its `ubi_dump_vid_hdr()` reported
`vol_type 102`, a value no valid header ever carries, and that was not the PEB just verified.
**So rather than patch on an inference, the next fire scans every PEB's VID header** (the 128 the
region covers), mirroring `validate_vid_hdr()`'s own checks - magic, `vol_type` in {1,2},
`compat` in {0..3}, header CRC - and parks pass count, first failing PEB, and that PEB's fields
at `0x80600e00`, away from the console buffer the panic dump overwrites.

**And a defect of mine caught before it shipped:** the first version of that block reused `part`
after the earlier `put_mtd_device()` had already released it - a use-after-free. The scan now
re-acquires the device and releases it on every exit path, and **the validation checks
acquisition/release counts rather than structure alone** - the same gap as the declaration-order
failure one phase earlier: the check has to test the property that actually matters.

**Device mutation.** Unchanged: the `kernela` write and its reboots.


---

## Phase 50ak (2026-10-09): THE BLOCKER IS NAMED, VERIFIED, AND FIXED - `compat = 5` on the layout volume

**Four measurements, each one ruling something out, and together they name a single field.**

**1. The scan found the failure at PEB 0 and nowhere else first:**
`pass_count = 0`, `first_bad_peb = 0`, and that PEB's header reported `magic 0x55424921` ("UBI!"),
`vol_type 1`, `lnum 0`, `data_size 0` - all valid - with **`compat = 5`** as the one deviation.

**2. The CRC verifies.** Read straight from the vendor's `mtd14`, computed with UBI's own
convention (init `0xFFFFFFFF`, no final inversion):

```
stored hdr_crc : 0xB82564A8
calculated     : 0xB82564A8
```

**The header is byte-perfect in every field UBI validates, except `compat`.**

**3. The flash survey shows exactly one check needs widening.** PEBs 0 and 1 - the **layout
volume** - carry `compat = 5`; **every data PEB carries `0` and passes already.** The layout
volume is the one that hits the `vol_id >= UBI_INTERNAL_VOL_START` branch of
`validate_vid_hdr()`:

```c
	if (vol_id >= UBI_INTERNAL_VOL_START && compat != UBI_COMPAT_DELETE &&
	    compat != UBI_COMPAT_RO && compat != UBI_COMPAT_PRESERVE &&
	    compat != UBI_COMPAT_REJECT) {		/* the set is {0,1,2,3} */
		ubi_err(ubi, "bad compat");
```

**4. The vendor's own UBI attaches this flash without complaint, so it accepts the value.** The
factory flash was written by the vendor's tools, which is exactly the shape of a vendor-private
compatibility marker.

**The fix is a one-line widening**, delivered through the mechanism the CI already uses -
`lab/luofu-kernel/kernel-tree.patch`, applied with `patch -p1` to a pristine 5.10.201 tree.
**It was dry-run and then applied against the pristine source before being committed: `rc=0`
both ways.**

**Why it is safe, stated plainly: `compat` tells a *writer* whether it may touch a volume, and
this driver has no write path at all** - `MTD_NO_ERASE` and no `_write` callback, deliberately,
since stage A. This kernel only ever **reads** the volume.

**And an honesty note about the readings that led here.** The scrambled 1 KB console buffer had
earlier appeared to show a `ubi_dump_vid_hdr()` with `vol_type 102`, `upd_marker 138`,
`name_len 1873` - and those field names **do not exist in 5.10's UBI dumps at all**. They were
artifacts of fragment interleaving in a wrapping buffer, and I read them as a coherent dump when
they were not. **The reliable data came only from the fixed-address reads**, which is why the
bytes were moved there.

**What the next fire should show:** with UBI attaching, the stage-D hook takes its **success
path** and stamps **`0x73717368`** - the squashfs superblock magic `"hsqs"` - **plus one if
`blk_lookup_devt("ubiblock0_0")` resolves.** That single value would mean **the rootfs is
readable through our own driver**, which is the thing this entire phase has been for.

**Device mutation.** Unchanged: the `kernela` write and its reboots.


---

## Phase 50al (2026-10-09): THE COMPAT PATCH WAS NECESSARY BUT NOT SUFFICIENT - and I cannot read UBI's reason for a size reason

**The patched kernel booted, and CI's own log shows the patch reaching the build:**

```
config  apply our in-tree additions: checking file drivers/mtd/ubi/io.c
config  apply our in-tree additions: patching file drivers/mtd/ubi/io.c
```

**And UBI still refuses:** `ubi0 error: ubi_attach_mtd_dev: failed to attach mtd14, error -22`.

**So `compat = 5` was necessary but not sufficient, and I should say plainly that the previous
phase's "blocker named, verified and fixed" was premature in its final word.** The field is real -
the CRC verifies, it is the only deviation my scan finds - and widening it moved nothing.

**The scan reports the same raw fields because it carries MY check, not UBI's.** It fails on
`cp > 3` by construction, so it can never tell me whether *UBI* is satisfied; it only reports
what the header contains.

**And the reason I cannot simply read UBI's specific complaint is a size problem, cleanly
stated:** the console ring is **512 bytes, roughly eight messages**, and an entire boot passes
between UBI's attach attempt at `late_initcall` and the panic that follows the failed mount.
**UBI's message is long overwritten by the time the panic notifier could copy anything out** -
which is why every reading so far shows the attach *failing* without showing *which check*
failed, even though UBI prints exactly that line.

**So the console callback now keeps only chunks that contain "ubi".** UBI's messages are few, so
a ring of those holds all of them however long the boot runs afterwards. **The match is loose on
purpose** - printk may hand a message over in more than one piece, and the pieces around the
keyword carry the detail.

**This is a measurement fix rather than a theory:** the next fire either shows UBI's specific
complaint, or shows that UBI said nothing specific at all - and both are answers the last four
fires could not give.

**Device mutation.** Unchanged: the `kernela` write and its reboots. The router is healthy.


---

## Phase 50am (2026-10-09): UBI'S OWN WORDS - `vtbl_check: bad CRC at record 6` - and a correction about fields I dismissed

**The instrument fix paid for itself immediately.** Keeping only chunks containing `"ubi"` in the
console ring turned four identical readings into a specific one:

```
[    3.545553] ubi0 error: vtbl_check: bad CRC at record 6: 0xaae09698, not 0x000000
[    3.482402] UBI error: cannot attach mtd14
```

**`vtbl_check` - the volume table, not the VID header.** Which means two things at once:

- **the compat widening DID work**: UBI read the layout volume and got all the way to validating
  its records, then rejected record 6. The previous phase's patch moved the failure *forward*
  even though it did not end it;
- **and the fields I dismissed two phases ago were real all along.** I called `upd_marker 138`
  and `name_len 1873` artifacts of a scrambled buffer. **They are `ubi_vtbl_record` fields**, and
  I misattributed them to a VID header without checking. The instrument was noisy and my reading
  of it was wrong, and both were mine to fix - the first by parking bytes at fixed addresses, the
  second by checking a field name against the source before calling it noise.

**Ground truth from the vendor's own MTD driver at the record's offset (5128):** the record is
**EMPTY - all zeros - with a VALID CRC of `0xF116C36B`.** UBI instead computed `0xaae09698` and
saw a stored CRC of **zero**. **So what this read path returns at byte 5128 differs from what is
on the flash.**

**And 5128 is the interesting number:** it is `4096 + 6 * 172` - record 6 of the layout volume's
first LEB, at the EC header's `data_offset`. **Every offset this driver has ever been checked at,
0 and 2048, is a page boundary. This one is not.** A partial offset within a page is exactly what
`luofu_mtd_read()` computes and **nothing has ever verified**.

The diagnostic now parks our own 172-byte read of that record, with err and retlen ahead of it,
where `devmem` can compare it against the vendor's all-zero-plus-CRC.

**Device mutation.** Unchanged: the `kernela` write and its reboots. The router is healthy.


---

## Phase 50an (2026-10-09): THE INSTRUMENT WAS CORRUPTING THE DRIVER - a whole line of readings was my own cross-talk

**The parked record came back containing my own console ring:**

```
29 0a 0a 3c 34 3e 5b 20 20 20 20 34        ")  \n\n<4>[    4"
```

**And the FMC driver allocates its DMA landing zone like this:**

```c
	fmc->dma_buf = dmam_alloc_coherent(dev, 0x2200, &fmc->dma_addr, GFP_KERNEL);
	writel(fmc->dma_addr, fmc->regs + FMC_SADDR_D0);
	memcpy_fromio(data, fmc->dma_buf, fmc->spec.page_size);
```

**The allocator picked `0x80600c00` - the very region I had chosen as "proven-inert"
because a 4-byte breadcrumb cell at `0x80600f20` had survived there for many fires.**
The hardware reads each flash page into that buffer; **my 512-byte console ring was rewritten
over it on every single printk**, so `luofu_fmc_read_page()` copied my log out instead of the
page. **UBI's `vtbl_check` complaint, and the garbage header fields before it, were produced by
the instrument observing them.**

**The reasoning error, stated plainly: I generalised "a small write here survived" into "this
region is free", without ever asking who *else* owns it.** A 4-byte breadcrumb between reads is
harmless; a kilobytes-per-second ring inside a DMA landing zone is not.

**Both buffers now come from `dmam_alloc_coherent()` and collide with nothing.** The log ring's
physical address is stamped into a crumb (step 44) - the channel that has never lied, being I/O
rather than RAM - and the log itself prints the diagnostic buffer's address, so **one 32-bit
value bootstraps the whole readback with no hard-coded address left in the file.**

**What this does to earlier conclusions, honestly:**

| reading | status |
|---|---|
| offsets 0 and 2048 matching the vendor exactly | **still trustworthy** - those matched independent ground truth, which corruption could not have produced |
| the record-6 garbage read, the `vtbl_check` bad CRC | **mine, not the device's** - withdrawn as evidence about UBI |
| "the read path returns wrong data at non-boundary offsets" | **withdrawn** - it read my log, not flash |

**And the important consequence: the compat patch has never once been tested on a clean
instrument.** The next fire is the first that is, so **its reading - attach or refusal - is the
first trustworthy measurement of UBI's real behaviour** rather than of my own cross-talk.

**Device mutation.** Unchanged: the `kernela` write and its reboots. The router is healthy.


---

## Phase 50ao (2026-10-09): THE SAME DECLARATION-ORDER CLASS AGAIN - and a crumb that is stamped too early to read

**The clean-instrument build failed to compile:**

```
luofu-fmc.c:922:29: error: 'luofu_diag_buf' undeclared (first use in this function)
```

**The same mistake the constants made one phase earlier**, in a place the check does not look:
the buffer statics went beside the console code that allocates them, and the stage-D hook that
writes into the diagnostic buffer sits further up the file. **The validator caught macro order
and said nothing at all about variables** - so a file with four globals out of scope passed it.

**The statics move up beside `luofu_ubi_fmc`, and the validator now covers variables:** it finds
every file-scope static, locates the hook, and fails if any global used inside the hook is
declared after it. **That is the check that would have caught both of these** - the earlier fix
taught the lesson and did not generalise it, which is why the same class came back a few turns
later.

**And a design flaw spotted while waiting, which the next fire would otherwise have wasted a
cycle on:** the log ring's physical address is stamped as crumb **step 44** from
`luofu_log_register`, but the **panic notifier stamps step 42 later in the same boot** - and the
crumb cell holds one value, last write wins. **So the address I need is overwritten by the
notifier's marker before I can read it.** The fix is to have the *later* writer carry the useful
value, or to recover the address by probing for the mark; either way it is cheaper to know now
than to discover it from an empty read.

**Device mutation.** Unchanged: the `kernela` write and its reboots. The router is healthy.


---

## Phase 50ap (2026-10-09): THE CLEAN INSTRUMENT BOOTS - and the log's address cannot be predicted, so the last crumb writer carries it

**The rebuilt instrument compiled and booted clean** - the declaration-order fix took - and the
probe for the ring's mark found **nothing in `0x80600000`..`0x80620000`**. The coherent
allocations are not near the driver's old landing zone after all.

**And they cannot be predicted.** This kernel has **no CMA**, so `dmam_alloc_coherent()` is
served from the **page allocator** and the address is simply whatever pages it was handed.
Finding it by scanning would mean walking 128 MB a word at a time.

**So the crumb carries the address - and that change also fixes a design mistake I caught before
it cost a cycle.** The log's address was stamped at **step 44** from `luofu_log_register`, but the
panic notifier stamps **step 42 later in the same boot**, and the crumb cell holds one value:
**last write wins.** The address was therefore overwritten by a marker before it could ever be
read - **and that marker told me nothing I could not already infer from the box having panicked
at all.** The notifier now stamps its step with `(u32)(uintptr_t)luofu_log_dma`, and being the
last writer to touch the crumb in a boot, its value is the one that survives.

**Device mutation.** Unchanged: the `kernela` write and its reboots. The router is healthy.


---

## Phase 50aq (2026-10-09): THE CRUMB WORKS, A COHERENT BUFFER DOES NOT SURVIVE, AND THE FIXED ADDRESS WAS RIGHT ALL ALONG

**The crumb mechanism works.** `C1C = 0x820F2000` - the panic notifier's stamp survived and gave
the log ring's physical address exactly as designed.

**And the read there returned the vendor's own kernel text:**

```
"evices/platform/mtd/mtd0/mtdbl"
"boot_done"
```

**Nothing in it contains "ubi", which the ring's filter guarantees if the ring were intact.** So
the coherent allocation was **reclaimed by the vendor's kernel** when it booted. This kernel has
no CMA, so `dmam_alloc_coherent()` is served from **ordinary System RAM** - and **a buffer in
plain RAM does not survive a vendor boot.**

**Which means the fixed address was the right answer all along.** The window below
`0x80608000` survives every vendor boot because that is where the vendor's kernel does **not**
load - a breadcrumb cell at `0x80600f20` there has survived dozens of fires. **The corruption
that sent this phase sideways was never the address. It was that the FMC driver's DMA landing
zone had been allocated *into* those same bytes**, so a console ring rewritten on every printk
overwrote the staging buffer the hardware reads flash pages into.

**So: fixed addresses in the surviving window** (`0x80602000`, clear of the ATAG at
`0x80601000`), **and the driver checks at registration that they do not overlap its own DMA
buffer, shifting up a slot if they do.** The chosen address is stamped into the crumb, so the
readback never has to guess. The log keeps only UBI's output, so its small ring holds every UBI
line however long the boot runs.

**Two wrong answers, both measured, and the right one bracketed by them.** That is the shape of
this whole phase: each failure was real, and only the pair of them together identified the
region where neither applies.

**Device mutation.** Unchanged: the `kernela` write and its reboots. The router is healthy.


---

## Phase 50ar (2026-10-09): THE LOG IS TRUSTWORTHY, UBI'S COMPLAINT IS REAL, AND THE FAULT IS OFFSET-DEPENDENT

**The instrument finally works end to end.** The crumb gave the ring's address
(`0x80603000` - **shifted from the `0x80602000` base, which means the collision check fired
and moved it clear of the driver's DMA on its very first run**). The mark `0xc0de1055` was
intact after a full vendor boot, the filter held, and **UBI's own words arrived clean:**

```
[    3.536281] ubi0: scanning is finished
[    3.542833] ubi0 error: vtbl_check: bad CRC at record 6: 0xaae09698, not 0x000000
[    3.620510] ubi0 error: ubi_read_volume_table: ...
[    3.287525] ... attach_mtd_dev: failed to attach mtd14, error -22
```

**`scanning is finished` is the important half:** every VID header passed, **so the compat patch
did its job**, and the failure is in the **volume table's data**.

**And read through our driver with the clean diagnostic buffer, the fault is clear:**

| offset | our read | vendor's flash |
|---|---|---|
| 0 | `"UBI#"` ✓ | `"UBI#"` ✓ |
| 2048 | `"UBI!" 01 01 00 05 7f ff ef ff` ✓ | same ✓ |
| **5128** (record 6) | **`66 CC` pattern of stale RAM**, `err=0`, `retlen=172` | **all zeros, CRC `f116c36b`** |

**A read that claims success and returns memory instead of flash.** Not a header, not a CRC, not
the instrument - a page read that is wrong for some offsets and right for others.

**So the self-inflicted episode is closed and the real bug is now measured:** the diagnostic
samples four offsets across the first PEB's page structure - 0, 2048, 4096 and 5128, each with
its own err and retlen - to separate "a particular row is wrong" from "a particular within-page
offset is wrong" from "the buffer is stale for repeated reads."

**Device verified healthy after the fire:** 2 wiphys, 6 VAP interfaces, `OpenWrt` on the vendor
stack, **zero `.omo-*` leftovers**, uptime 1 minute. `kernela` md5 `627436504c370da82ea61c2c9018b2ab`.
