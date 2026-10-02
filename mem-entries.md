- **Phase 19 - THE RELEASE IS FOUND: the `0x5a5a` write to device CA `0x40000108` BOOTS THE CHIP (2026-10-01, lead-verified).**
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
