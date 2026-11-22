# mem-entries index

Generated from `mem-entries.md` by `tools/gen-ledger-index.py`. Do not hand-edit.

The latest dated entry wins. Read the latest table first, then grep the ledger for the phase you need.

## Latest 40 dated entries

| date | phase | title | line |
| --- | --- | --- | --- |
| 2026-11-21 |  | 2026-11-21 18:55 - Recovery succeeded but the subsequent handover left a MIXED kernel/userland system: our 6.18 kernel (cmdline luofu_switch.*) booted with the stock 5.10 rootfs (rootfsb). Stock LuCI then refuses the wizard ("Invalid board info!", bdinfo checkuuid needs the vendor kernel's /proc/sys/dev/flash_uuid) and the MQTT broker path is silent. | `mem-entries.md:26696` |
| 2026-11-21 |  | 2026-11-21 19:05 - FLASHINFO LOADER TEST PASSED over the broker channel: the loader accepts hisilicon,luofu-flashinfo first, performs the full staging handoff and boots our image with 2 CPUs - the last upstream blocker is closed (zero blockers). | `mem-entries.md:26722` |
| 2026-11-21 |  | 2026-11-21 19:35 - E0-b complete: read-only stock-vs-ours runtime captures (9,488 words each) and the classifier diff are captured; box is back on our image with env bootflag=b / selector 0x11. | `mem-entries.md:26732` |
| 2026-11-21 |  | 2026-11-21 19:55 - E0-b decode + reviewed M1a probes: tagact entry 1 is a tag-DELETE action (not CPU-punt), L2 diffs are DFX counters, pfe_glb+0x2c is a flow-engine uplink attribute - write replays expected null; the decisive next step is the read-only stock decoded procfs capture. | `mem-entries.md:26759` |
| 2026-11-21 |  | 2026-11-21 20:10 - M1a replay probes both NULL: tagact entry write is ignored by the hardware (readback mismatch, auto-reverted) and the pfe_glb up_port write succeeds but changes no CPU delivery (eth2 delta stays 531 = mirror copies only). Write experiments stop; the decisive next step is the read-only stock procfs decoded-table capture. | `mem-entries.md:26783` |
| 2026-11-21 |  | 2026-11-21 20:25 - Stock decoded procfs captured (137 files): the CPU-punt path is IFC->tocpu (ifc_hit=992, ifc_tocpu=104, cpu_spec_send=718) but the readable IFC/L3/flow shadow tables are empty - the rules live in the CFE/flow-engine state; M1a write probes closed (both null). | `mem-entries.md:26804` |
| 2026-11-21 |  | 2026-11-21 20:45 - CPU-punt mechanism resolved: IFC->NAPT path; our NAPT is uninitialized (all config words 0), so unicast dies inside the flow engine before PIE. Vendor hi_pfe_napt_init decoded as a register-only sequence and prepared as a fail-closed replay. | `mem-entries.md:26827` |
| 2026-11-21 |  | 2026-11-21 21:00 - BREAKTHROUGH: replaying the decoded hi_pfe_napt_init sequence makes the flow engine punt unicast to the CPU. With the mirror still on, eth2 RX delta was 1122 for 500 pings (~2x) and napt up_tocpu rose from 0x2e to 0x261 (+563) while ping stayed 0% loss - the native CPU-delivery signal M1a was looking for. | `mem-entries.md:26859` |
| 2026-11-21 |  | 2026-11-21 21:20 - M1a PROVEN: native CPU delivery with the CPU-copy mirror OFF. Proof image 5800c9ab (canonical adopted tree + cmdline cpu_mirror=0/luofu_napt_init=1/rxdiag=1 + probe boot-time NAPT-init script) boots, applies NAPT init, and SSH/ping work with no mirror; native RXDIAG status=77 frames are delivered. | `mem-entries.md:26884` |
| 2026-11-21 |  | 2026-11-21 21:40 - W22 kernel drafts + M1b plan delivered: NAPT-init as a driver stage (patch 0001) + native exception/status-class delivery in PIE (patch 0002), compiled/checkpatch-clean; exact release-integration and M1b per-port plan documented. | `mem-entries.md:26906` |
| 2026-11-21 |  | 2026-11-21 22:00 - W22 kernel implementation landed in the release line and verified on hardware: canonical image 50023446 boots with the driver NAPT init (no mirror tokens), ping/SSH work, reboot determinism passes. | `mem-entries.md:26931` |
| 2026-11-21 |  | 2026-11-21 22:15 - Curated openwrt repo synced to the W22 release state (214c893, fresh-clone verified, all checks green); fallback-image build/test and soak are the remaining bench steps. | `mem-entries.md:26965` |
| 2026-11-21 |  | 2026-11-21 22:45 - Fallback-image test hit an env handover race: the broker write of bootflag=b/selector 0x11 did not survive to the next boot (U-Boot booted stock pair a, bootflag a/bootreg 10), and the vendor userspace then re-normalised the selector; the box is now running vendor userspace with no management IP (stock LAN unreachable). Needs one physical RESET-hold recovery. | `mem-entries.md:26983` |
| 2026-11-21 |  | 2026-11-21 23:00 - Telnet install flashed the ACTIVE pair and failed: after recovery the stock booted from pair b (env bootflag=b), so ubiformat /dev/mtd14 targeted the mounted rootfsb, failed, and the result was again our 6.18 kernel with the vendor rootfs (mixed: no management IP on 192.168.1.1, vendor wizard 403 invalid board info, broker silent). One more physical RESET-hold recovery needed. | `mem-entries.md:27008` |
| 2026-11-22 |  | 2026-11-22 00:05 - W22 canonical image re-installed successfully with the corrected two-stage procedure: stock switched to pair a first, then the image written to the inactive pair b via the broker with atomic env+reboot. Boot verified, link-flap recovers, 15-min soak started. | `mem-entries.md:27030` |
| 2026-11-22 |  | 2026-11-22 00:35 - 15-min W22 soak PASS (900/900, 0% loss, 0 errors). Fallback-image test went wrong again (build/cmdline caching suspected, then no management IP); box needs one more physical RESET-hold recovery. The fallback path will be documented as a known limitation rather than a formal bench step. | `mem-entries.md:27054` |
| 2026-11-22 |  | 2026-11-22 00:55 - W22 canonical re-installed and verified after recovery #5 using the two-stage procedure (stock pair a -> broker write inactive pair b atomic). Box healthy: 6.18.60, 2 CPUs, naptinit=1, no mirror tokens, W22 init verified, 0 errors. M1b per-port native delivery test starting with cable moves. | `mem-entries.md:27076` |
| 2026-11-22 |  | 2026-11-22 01:15 - M1b-1 PASS: per-port native CPU delivery verified on all four jacks (eth0/port9 far-right, eth1/port10 second-right, eth2/port11 bench, eth3/port12 leftmost WAN) with the W22 image and no mirror. | `mem-entries.md:27091` |
| 2026-11-22 |  | 2026-11-22 01:40 - M1b-3 LAN-to-LAN forwarding PASS: with a second USB-Ethernet adapter on eth0 and the bench adapter on eth2, the software bridge forwards broadcast and learned unicast in BOTH directions (eth0<->eth2); FDB learns both MACs on the correct ports. Native multi-port LAN forwarding works with W22 and no hardware L2 offload. | `mem-entries.md:27107` |
| 2026-11-22 |  | 2026-11-22 02:00 - Multi-port LAN complete: LAN-to-LAN forwarding also PASS on the second port pair eth2<->eth1 (broadcast + learned unicast, both directions), FDB learns both host MACs on the correct ports. Native multi-port LAN (all four jacks delivery + bridge forwarding over both LAN port pairs) is now fully bench-verified with W22 and no hardware L2 offload. | `mem-entries.md:27127` |
| 2026-11-22 |  | 2026-11-22 02:20 - WAN L3 path PASS: with the second adapter on the leftmost jack (eth3/WAN), the box obtained DHCP lease 192.168.50.115/24 from a host dnsmasq, installed default via 192.168.50.1 dev eth3, pinged the gateway 5/5 and replied to host ping 4/4 - the WAN port has a complete native L2/L3 path. | `mem-entries.md:27144` |
| 2026-11-22 |  | 2026-11-22 02:40 - Four full-reversal lanes delivered: CFE/switch model + our-side dump validation (95bea9e), vendor userspace fully decompiled (42a431a), Wi-Fi/thermal feasibility (8b8ace5), loader/recovery/upgrade formats (628c4b1). Stock /dev/mem read() is blocked but mmap via a static physdump binary works, so the stock stock-runtime CFE dump is now being transferred via broker wget+physdump+nc. | `mem-entries.md:27164` |
| 2026-11-22 |  | 2026-11-22 03:00 - Full-reversal phase: all four lanes delivered and integrated; stock runtime CFE tables successfully captured via an mmap dumper (vendor /dev/mem read() is blocked but mmap works). Thermal fix is now implementable from the decoded formula; tasking W23. Stock package: build/evidence-bench-gates/cfe-stock/cfe-stock-full.tar.gz (sha256 202aca42f6038245a1c994bf4b03101756ad2bc961741df1bef6b322a484b312). | `mem-entries.md:27199` |
| 2026-11-22 |  | 2026-11-22 03:20 - W23 thermal fix integrated and bench-PROVEN: gate off raw=0/ENODATA; enable -> raw 0x25e = 59000 mC (formula exact), registers match, no IRQ, 0 warnings; CPU load 59->63 C with cooling. Release line now L0 66 / L1 55 (manifest 2bb7413e), validator PASS 55/55, target build PASS. Stock routed-phase dump captured for the CFE lane (box-terminated traffic -> flow arenas empty, explained; true forwarded-traffic recipe recorded). | `mem-entries.md:27209` |
| 2026-11-22 |  | 2026-11-22 03:40 - TRUE forwarded-traffic stock phase captured (netns split: root LAN 192.168.10.44, netns wan 192.168.50.1; box WAN DHCP 192.168.50.115; host->box->WAN ping 5/5 + curl 200). First time the vendor pub window changed vs p0 (tagact/l3intf bank populated): fwd-win15-pub sha 32ca3d39 vs p0 f3b58f7b; sent to the CFE lane for the final slot-format/M2 decode. Box returned to W23 (6.18.60, 2 CPUs, thermal gate 0, W22 init once, 0 errors); host netns/route cleaned up. | `mem-entries.md:27235` |
| 2026-11-22 |  | 2026-11-22 04:00 - CFE forwarded-phase decode complete: vendor L3/neighbour/tag tables decoded (l3intf[1] LAN MAC d4:0d:ab:64:1c:73 sip 0.0.0.0 tagact_id 2 mtu 1500, l3intf[2] sip 192.168.50.115 WAN, nhp[1] 192.168.10.44 host MAC, nhp[2] second host NIC, tagact[2]=0x0000b000 selector 3; layout from l3intf_write/nhp_write disassembly). NAPT DDR v4/v6 arenas EMPTY even with true forwarded NAT traffic (0 bytes changed; match counters non-zero: dn_match 134, up_match 91) -> M2-A hardware flow cache CLOSED (do not implement; vendor doesn't use the DDR cache in this config), M2-B data-backed documentation only. Release path unchanged: W22/M1b; nothing blocks. | `mem-entries.md:27244` |
| 2026-11-22 |  | 2026-11-22 04:15 - SESSION CLOSE-OUT: full-reversal program at its accessible ceiling; W23 thermal bench-proven and published; M2 hardware offload closed; curated repo final at 4bd4360 (324 files, all checks PASS). Bench torn down (stale HTTP killed; no TFTP/UART writers); box final: W23 image, 6.18.60, 2 CPUs, naptinit=1, thermal gate 0, selector 0x11, 0 errors. | `mem-entries.md:27258` |
| 2026-11-22 |  | 2026-11-22 06:40 - Wi-Fi TRY concluded with a QUANTIFIED NO-GO for the 6.18 binary port; the full swarm is complete. Wi-Fi works on this box only via the vendor 5.10 stack; the interface contract is now fully documented and the GPL follow-up is the single remaining unlock. | `mem-entries.md:27279` |
| 2026-11-22 |  | 2026-11-22 07:20 - Wi-Fi framework census complete: GPL-2.0 hi3881 source covers 23.9% (name) / 28.5% (byte) of our 4,946-function driver pair; a 892 KB skeleton (libsec+frw+oal+oam+mac/common, 28 objects) COMPILES against 6.18.60; the hi5622 delta is mapped (3,763 unique names, 1,014,560 B): transport pcie_/bal_ ~391 fns, shuangta_ 173, hdpp_ 238, hal_ 91, alg_ 222, hmac/wal ko-only ~2,409. 33/39 cfg80211_ops and 12/44 D2H handlers name-match the framework. ROOT-CAUSE FIND: oal_util.h pins LINUX_VERSION_CODE=kernel_version(3,10,0) (the vendor driver silently ran 3.10 API branches; unpinning exposes the real 6.18 drift: timespec64, timer_delete, set_fs removal, sched_setattr_nocheck, netlink cb_mutex, fortify/strlen clash). hcc_* renamed between chips (1/87 shared - SDIO/ADMA vs PCIe mailbox/ETE). | `mem-entries.md:27308` |
| 2026-11-22 |  | 2026-11-22 08:40 - Wi-Fi transport slice REBUILT: hi5622_pciet.ko (93,468 B, GPL, vermagic 6.18.60, 0 warnings under -Werror) implements the firmware-upload/ETE-ring/mailbox contract as original clean-room code and compiles against our built 6.18.60 tree (commit 99d9c8f, docs/incoming/wifi-transport-port/). First bench milestone defined: attended sysfs-step upload -> 0x5a5a release -> 0xcece announce -> HCC ready ids 1/2 (bitmap 0x2 / 0x4 = out[1]=0x4). Findings: no MSI on luofu 6.18 (msi_init returns 0) and no INTx demux (status in never-read misc window) -> skeleton polls the D2H bitmap; host-side delta patch build/luofu-host-618-delta.patch adds dma-ranges identity to both pcie nodes (bench prerequisite); twin-word gating left [U]. Transport group (pcie+bal+shuangta+hal = 391 fns / 67,432 B) = 6.6% of the ko-only delta; next slices in size order: hdpp_ 238 (dpe_ twin in hongmengkernel hi1105) -> alg_ 222 (densest) -> hal_ 91 -> shuangta_ 173 -> hmac_ ko-only 1,503 -> wal_ ko-only 684. Framework-lane build text files force-added (bare build/ gitignore rule). | `mem-entries.md:27321` |
| 2026-11-22 |  | 2026-11-22 10:10 - Wi-Fi data-path slice: hdpp/alg mapped and scaffolded. hdpp_ (238 fns) -> dpe_ twin: 3 exact-name (1.3%); alg_ (239) -> twins: 17 exact (7.1%, generic cfg-command core in wal/wal_config_alg_cfg.c) + 51 same-subfamily; combined 20/477 (4.2%) - the engines are family-level twins with fully diverged naming. Call-graph evidence (27,255 resolved bl edges; 108 hdpp + 64 alg call targets). Scaffold re-exports all 60 vendor ksymtab exports (46 hdpp_stat_* + 6 alg_* + 8 g_alg_*, ABI pinned by wifi_debug.ko imports) and compiles into hi5622_hdpp_alg_skel.ko (73,404 B, 6.18.60, -Werror tree). 12-point bench-probe list written (init dispatch, sync-write D2H acks, counter layouts, D2H TWT/ERSRU payloads, stat dfx params, alg table contract). Next slice: alg_cfg + wal config-command port (host-testable against the 17 twins as oracle), then hdpp object model (needs transport bench stage B2). hongmengkernel reference clone kept outside git (no license grant - reference-only honored). | `mem-entries.md:27325` |
| 2026-11-22 |  | 2026-11-22 12:40 - Wi-Fi alg_cfg slice: the generic config-command codec is ported and ORACLE-VERIFIED. hi5622_alg_cfg_codec.ko (97,364 B, GPL, vermagic 6.18.60, -Werror) compiles from the committed tree; the host harness runs the 17 exact twins and the port output is byte-identical to the reference (17/17 PASS, 0 failures, including the waterfilling_limit int8-wrap quirk). LICENSE CORRECTION: the twin codec exists only in the NO-license hongmengkernel hi1105 tree (wal_config_alg_cfg.c is absent from the GPL-2.0 hi3881 tree) - per the clean-room rules the codec is committed as ORIGINAL GPL-2.0 text pinned from our binary disassembly (414-row process table, 176B-per-command 416-entry LUT at .data+0x4934, 40-entry param-size table, 13/13/2 value tables, runtime-patched 4608-pair name fixup list, error codes 100/101/1009/1014/1017/35629), with the hi1105 file used as a local execution oracle only. The genuinely vendored GPL-2.0 text is the hi3881 wal command layer (vendor/hi3881-wal/). 120 hi5622-specific cfg families annotated (30 spectral, 6 smartant, 5 ulsch, 5 trigger parsers + 10 formatters, 3 ersru, 2 sounding, 60 formatter-shaped, atf/mumimo/ns_aggr/ofdma/tpc/obss/urp/ppet). Commit 3d1ad9b, docs/incoming/wifi-algcfg-slice/. | `mem-entries.md:27329` |
| 2026-11-22 |  | 2026-11-22 14:45 - Wi-Fi wal-glue slice: the 6.18 wal config-command front end compiles. hi5622_wal_cfg.ko (222,528 B, GPL, vermagic 6.18.60, depends cfg80211, 0 errors/0 warnings) wires the oracle-verified codec: vendor-exact entry names (wal_wlan_cfg_module_process_entry + host/device legs), hipriv-style wal_hipriv_alg_cfg*, sysfs /sys/kernel/wal_cfg/ surface, cfg80211 vendor-command provider (6.18 alloc_reply_skb; CONFIG_CFG80211=n provider symvers mirroring the vendor imports), hmac cfg dispatch stubs (22 vendor names incl. hmac_event_config_syn / hcc_msg_register_tab 12->16B merge), LUT/name-fixup loader (416x176B LUT key (type<<16)\|id, 4608-pair fixup list, runtime descriptor from the algcfg offsets), 22 exports vendor-exact. Commit 422c8c9, docs/incoming/wifi-wal-glue/ (+ probes/bench-probes.md P0-P5). | `mem-entries.md:27338` |
| 2026-11-22 |  | 2026-11-22 12:25 - PCIe bring-up bench (W24 series): the COMPLETE vendor RC sequence is now implemented in patch 013 and the link still does not train - the remaining difference is endpoint-side hardware. Big milestone: our 6.18 kernel now has a probing PCIe host with the full recorded vendor bring-up (pre-init words, RC mode, gated cmd/speed, LTSSM-enable with the DBI gate preserved (D1 0x2800), vendor-layout 8-word iATU viewports per RC, steady 0x02200800, stage-2 retrain moved post-link (D2), ACP gate polarity corrected to SET bits 25/26 (hi_acp.ko inverted-value semantics; live 0x06210321), framework pre-link SPEED_CHANGE neutralized, static CFG0 map_bus, 1ms reset pacing). | `mem-entries.md:27349` |
| 2026-11-22 |  | 2026-11-22 12:45 - PCIe adversarial round: every verifiable register on our image now matches the vendor's live state, and the link still does not train. VERIFIED (our image): misc+0x1c = 0x02200800 (both RCs; writes land - the steady state is byte-exact), ACP 0x10100174 = 0x06210321 (bits 25/26 SET), DBI PCI_COMMAND = 0x00100107 (IO\|MEM\|BME), LNKCAP dbi+0x7c = 0x734c12 (speed=2), dbi+0xa0 speed=2. STOCK live target captured: DEBUG0 dbi+0x728 = 0x03f4a611 (LTSSM[5:0]=0x11 L0), cfg window 0x50000000 = 0x59e7 (endpoint answering), ACP 0x06210321, misc link-status words 0x10161100=0x00808028 / 0x10161110=0x20468aa6. OUR image: DEBUG0 LTSSM=0x00, cfg=0xffffffff. Full vendor sequence (doc steps 1-20) diffed: our port covers 1-16 faithfully (17/18 are post-link irq steps; 14 skipped correctly, no aspm-enable). Ordering (host_init before framework DBI) verified in 6.18 source. LTSSM field is 6 bits (GENMASK(5,0) per sibling pcie-histb) - still 0x00 on ours. CONCLUSION: RC-side software is exhausted and register-verified; the failure is endpoint-side hardware (rail/PERST/refclk to the Hi5622). Multimeter procedure is next; recovery door armed, stock pair a healthy, box on W24n. | `mem-entries.md:27366` |
| 2026-11-22 |  | 2026-11-22 13:20 - PCIe: SPEED_CHANGE write-path and LTSSM ordering fixed (W24o/p/q/r), 0x80c now = 0x12c byte-identical to stock, LTSSM enabled LAST (vendor order), phase diagnostics added - and the LTSSM machine STILL never leaves detect.quiet. Root causes found this round: (1) the framework's dw_pcie_setup_rc sets PORT_LOGIC_SPEED_CHANGE after host_init (my earlier clear was overwritten) and runs dw_pcie_dbi_ro_wr_dis() so post-setup DBI writes need 0x8bc-bit0; (2) LTSSM was enabled before the framework's DBI batch (vendor enables it after ALL DBI writes). Both fixed: start_link now does ro_wr_en -> viewports -> clear SPEED_CHANGE -> ro_wr_dis -> LTSSM enable -> steady; post_init retrain is conditional on link_up. Diagnostics: "link training armed DEBUG0=0x003d4900" -> "post-link check DEBUG0=0x001c6200" - LTSSM[5:0] stays 0x00 while DEBUG0 higher fields churn (PHY alive). Live-DTB check: identical (sha 947ec62d; capability=0x03 is a runtime fixup by the vendor driver, not a flash delta). Userspace: gpio_switch empty, hsan scripts write nothing, shuangta branch has no GPIO step. Clock parent verified (pcie0_clk <- apb_clk == LUOFU_SRC_APB). Remaining: PORT_DEBUG0 field decode (ours 0x725000 vs stock-live 0x03f4a611) and the multimeter rail/PERST measurements. | `mem-entries.md:27370` |
| 2026-11-22 |  | 2026-11-22 13:45 - PCIe educated-guess space EXHAUSTED: bundle 1 (reset pulse+50ms settles, RC-header restore, mode re-assert) and bundle 2 (0x8bc bit0 left set, reg_int re-assert, LTSSM re-kick) both NEGATIVE. W24t (2bb45e9e) boots clean; 0x80c = 0x12c (stock-identical), LTSSM stays 0x00, config window 0xffffffff. All six remaining hypotheses consumed; every readable register matches the vendor live state; the write paths are verified. The failure is now conclusively endpoint-side physical: Hi5622 rails / PERST# / refclk. Multimeter procedure is the only path left. Box on W24t, stock pair a intact, recovery door armed. | `mem-entries.md:27374` |
| 2026-11-22 |  | 2026-11-22 14:10 - PHOTOS CRACK IT OPEN: the board is a TRIDUCTOR TR6560+TR5220 platform (= rebadged HiSilicon Hi5671Y + Hi5622V100). Silkscreen "WR-3000 2.0 / 300100297", main SoC marked TR6560PRCB ("TRIDUCTOR" brand), Wi-Fi marked TR5220GCF with 3x U.FL (J50/J51/J21), power section bottom-right: 2x 470uF 10V bulk caps + 242 buck inductor + barrel jack. Web research: Banana Pi BPI-WiFi6 Mini uses TR6560+TR5220 and has a PUBLIC OpenWrt BSP (github.com/nhz-io/BPI-WiFi6_Mini-THG6500-TAX2-OPENWRT-BSP) with target/linux/tr6560 (1227 files), tr6560 board DTS (reset_pcieN/power_pcieN/vol_en/wl_en/pmu_pwron GPIO model), prebuilt tri_pcie.ko (NOT stripped, 23 functions: tri_hal_crg_wifi_cfg, tri_hal_pcie_dev_reset_tr5220, tri_hal_pcie_reg_init, check_link...) and the SoC dtsi pcie@0x10145000 node with tri,pcie + iatu tables. CRG check: 0x14880020/34/40 identical stock-vs-ours (CRG+0x40=0 both; tri driver's crg_wifi_cfg = gate bits 12/13 at +0x20 which we already set). GPIO diff stock-vs-ours decodes as LED pins (20=wlan5g LED active-low on reference design), not Wi-Fi power - Cudy DTB has no board node and hi_pcie.ko has zero hardcoded GPIO/register addresses (all DT-driven), pcie-gpios empty. Hardware probe guide prepared: docs/incoming/hardware-probe/board-multimeter.jpg (annotated). Next: multimeter rails + disassemble tri_pcie.ko init/reg_init for any step our port misses. | `mem-entries.md:27378` |
| 2026-11-22 |  | 2026-11-22 14:30 - tri_pcie.ko (Triductor SDK, same silicon) fully decoded; last software variant (mode bit 22) tested (W24v) - STILL negative. SDK findings: install = unreset (CRG+0x28 bits 12/13, CRG+0x34 resets 12-19, misc+0x20 bit5) -> misc+0x1c \|= 0x800 (LTSSM enable, BEFORE mode/DBI) -> check_link -> reg_init (misc+0x04=0x200000, misc+0x18=0x08000000, misc+0x00=0x40200000 BIT22, misc+0x1c \|= 0x2000 gate, DBI cmd 0x00100007, iATU index-select writes, gate off, \|=0x02200000, mode restore 0x40000000, reg_int=0). Verified on hardware: CRG+0x28=0x02f8300b, CRG+0x2c/0x30, misc+0x20=0x20, misc+0x24/0x28 ALL IDENTICAL stock-vs-ours (U-Boot sets them). Cudy vendor hi_pcie.ko has zero hardcoded addresses (all DT-driven) and its set_mode = channel<<28. Mode bit22 variant W24v (bfdfbe8f) -> LTSSM still 0x00. SOFTWARE REGISTER PATH NOW EXHAUSTED. Remaining options: (a) build the tr6560 BSP baseline (software-only, heavy: adapt vendor DTB compatibles to tri,* drivers, wrap kernel for Cudy U-Boot), or (b) multimeter rail/PERST measurement. User prefers to avoid multimeter. | `mem-entries.md:27382` |
| 2026-11-22 |  | 2026-11-22 16:20 - BSP-kernel PCIe experiment: booted Triductor SDK kernel on the WR3000 v2, module route dead-ended; box restored. Path: cloned nhz-io/BPI-WiFi6_Mini-THG6500-TAX2-OPENWRT-BSP (1.2 GB, dl/ vendored); built target tr6560 (THG6500-TAX2, kernel 5.10.138) with OUR toolchain after disabling CONFIG_ATA (gcc-14 BUILD_BUG_ON in libahci) and CONFIG_MTD_TRIDUCTOR_NAND (tri_fmc_atags_parse oops at boot); wrapped zImage+THG6500 dtb into the Cudy kernel container (uImage + fip-slice.py make-trailer with BSP DTB as base - loader accepted it). Findings: (1) BSP kernel BOOTS on this board (SMP, console ttyS1, UBI) - hard confirmation TR6560 = HiSilicon Hi5671; (2) initramfs experiments: kernel has CONFIG_VFP=n (hard-float userspace SIGILL), CONFIG_DEVTMPFS=n, CONFIG_DEVMEM=n (no /dev/mem - register dumps impossible); freestanding soft-float init with mknod + ttyS1(minor 65!)+direct UART eventually printed via ttyS1; (3) tri_pcie.ko needs symbol tri_irq_set_affinity which NOTHING in the BSP provides (declared only in tri_os.h) - we added an exported in-kernel shim; (4) after the shim, init_module STILL fails rc=-22 (EINVAL) - prebuilt SDK module rejected by our kernel's loader (toolchain/config ABI); 6 RESET+TFTP recovery cycles consumed. Decision: stop BSP-kernel route (their kernel config blocks devmem/modules; more cycles needed for low value). Box restored: stock pair a (bootflag a), our image W24v on pair b; TFTP/captures stopped. | `mem-entries.md:27386` |

## All dated entries

| date | phase | title | line |
| --- | --- | --- | --- |
| 2026-10-02 |  | Phases 23-25 (2026-10-02/03) - the port runs end to end, and three corrections | `mem-entries.md:54` |
| 2026-10-03 |  | 2026-10-03 - phases 27-28: H1 confirmed, the DR ring is free-running, the firmware half settled | `mem-entries.md:95` |
| 2026-10-04 |  | 2026-10-04 - phases 42-48: the gate located to the mechanism level, the host-side space closed | `mem-entries.md:125` |
| 2026-10-04 | 49 | 2026-10-04 - phase 49: the forward lane - register(0x4c) ran, enable(0x4c) executed, the delivery hop is the last link | `mem-entries.md:151` |
| 2026-10-09 |  | 2026-10-09 - THE GUARD DECODED; OUR KERNEL'S FIRST INSTRUCTION RAN (fires fixed2/fixed4) | `mem-entries.md:435` |
| 2026-10-09 |  | 2026-10-09 - THE OWN KERNEL BOOTS ON THE HARDWARE (C18=0xC0DE0020) | `mem-entries.md:465` |
| 2026-10-09 |  | 2026-10-09 (later) - the mcr-transition lottery (the current frontier) | `mem-entries.md:484` |
| 2026-10-09 |  | 2026-10-09 (night close) - the 0017 condition: deterministic, narrowed, mechanism open | `mem-entries.md:495` |
| 2026-10-09 |  | 2026-10-09 (latest) - site-readback: the walk's stores measured; the dice model confirmed | `mem-entries.md:510` |
| 2026-10-09 |  | 2026-10-09 (dice campaign close) - six instrumented throws, all 0017; the framing fix | `mem-entries.md:522` |
| 2026-10-09 |  | 2026-10-09 (MEASUREMENT COMPLETE) - the walk's patches are absent in BOTH classes | `mem-entries.md:533` |
| 2026-10-09 | 50 | Phase 50 (2026-10-09): THE NAND/FMC PORT OPENS - the controller spec, the stage-A driver, and the symbol that left the TODO list | `mem-entries.md:550` |
| 2026-10-09 | 50a | Phase 50a (2026-10-09): THE FIRST STAGE-A FIRE - the driver compiled, the probe never ran, and the cause is that the kernel boots the VENDOR's devicetree | `mem-entries.md:623` |
| 2026-10-09 | 50b | Phase 50b (2026-10-09): STAGE-A PASS - THE FMC COMMAND ENGINE RUNS IN OUR OWN KERNEL AND THE DIE ANSWERS 0x8C2C | `mem-entries.md:684` |
| 2026-10-09 | 50c | Phase 50c (2026-10-09): STAGE B'S OPERAND SOURCE IS LOCATED - the bootloader's flash-spec ATAG, and it names our die | `mem-entries.md:748` |
| 2026-10-09 | 50d | Phase 50d (2026-10-09): THE DMA OPERANDS ARE RECOVERED - the bootloader's flash-spec record, decoded and cross-checked | `mem-entries.md:802` |
| 2026-10-09 | 50e | Phase 50e (2026-10-09): STAGE-B PASS - THE DMA PAGE READ RETURNS REAL FLASH CONTENT, AND rootfsa BEGINS WITH "UBI#" | `mem-entries.md:869` |
| 2026-10-09 | 50f | Phase 50f (2026-10-09): WHY THE ROOTFS IS STILL MISSING - the vendor boots an INITRAMFS, and the two routes from here | `mem-entries.md:923` |
| 2026-10-09 | 50g | Phase 50g (2026-10-09): THE ROOT-DEVICE MECHANISM, SETTLED FROM SOURCE - and why the root= fire needs its own plan | `mem-entries.md:986` |
| 2026-10-09 | 50h | Phase 50h (2026-10-09): THE FIRST MTD FIRE - the instrument named the step, the source named the cause, and the fix is one flag | `mem-entries.md:1047` |
| 2026-10-09 | 50i | Phase 50i (2026-10-09): THE SECOND MTD FIRE - the registration works, and the panic it exposed was one unallocated field | `mem-entries.md:1103` |
| 2026-10-09 | 50j | Phase 50j (2026-10-09): STAGE-C PASS - OUR OWN KERNEL HAS AN MTD DEVICE, THE VENDOR'S PARTITION TABLE IS PARSED, AND THE ROOTFS PARTITION READS THROUGH THE MTD LAYER | `mem-entries.md:1154` |
| 2026-10-09 | 50k | Phase 50k (2026-10-09): THE ROOT DEVICE, AND THE SAFETY NET THAT GOES WITH IT | `mem-entries.md:1205` |
| 2026-10-09 | 50l | Phase 50l (2026-10-09): THE ROOT-DEVICE FIRE - the hook ran, the volume name was my assumption, and what the cells cannot say | `mem-entries.md:1256` |
| 2026-10-09 | 50m | Phase 50m (2026-10-09): THE NAME WAS ONE PROBLEM, NOT THE ONLY ONE - so the failure value now carries the diagnosis | `mem-entries.md:1305` |
| 2026-10-09 | 50n | Phase 50n (2026-10-09): UBI IS NOT ATTACHING - the partition is there, and two explanations are ruled out from source | `mem-entries.md:1350` |
| 2026-10-09 | 50o | Phase 50o (2026-10-09): THE EINVAL HUNT - every path accounted for, the geometry cleared from the flash itself, and a flaw in my own instrument | `mem-entries.md:1395` |
| 2026-10-09 | 50p | Phase 50p (2026-10-09): THE ERRNO IS THE KERNEL'S, THE FLASH IS VALID - so the suspect is our READ, and the test is now aimed there | `mem-entries.md:1444` |
| 2026-10-09 | 50q | Phase 50q (2026-10-09): THE READ PATH IS PROVEN AND THE FLASH IS PROVEN - and UBI still says EINVAL, so the next move is to make the kernel's own log readable | `mem-entries.md:1491` |
| 2026-10-09 | 50r | Phase 50r (2026-10-09): GIVING THE KERNEL A VOICE - ramoops on the command line, because every failure so far has been inferred rather than read | `mem-entries.md:1546` |
| 2026-10-09 | 50s | Phase 50s (2026-10-09): THE FIRST RAMOOPS ATTEMPT KILLED THE EARLY BOOT - the crumbs localised it to a window, and two things were wrong | `mem-entries.md:1606` |
| 2026-10-09 | 50t | Phase 50t (2026-10-09): THE ARTIFACT DIFF NAMED THE KILLER - the ramoops cmdline params - and the capture moves to a kmsg_dumper that needs none | `mem-entries.md:1650` |
| 2026-10-09 | 50u | Phase 50u (2026-10-09): THE DUMPER BOOTS, THE LOG IS SCRUBBED - and I applied one rule while ignoring another from the same record | `mem-entries.md:1702` |
| 2026-10-09 | 50v | Phase 50v (2026-10-09): NEITHER BUFFER HOLDS THE MARK - so the dumper never wrote, and zeroes could not say why | `mem-entries.md:1747` |
| 2026-10-09 | 50w | Phase 50w (2026-10-09): ioremap REFUSES RAM ON ARM - which is why no mark ever appeared, and why every crumb always did | `mem-entries.md:1787` |
| 2026-10-09 | 50x | Phase 50x (2026-10-09): THE FIRST BOOT THAT COMPLETED EVERY INITCALL - and two placement errors it exposed | `mem-entries.md:1828` |
| 2026-10-09 | 50y | Phase 50y (2026-10-09): THE FIFTH FAULT - the panic path only ever dumps EMERG, so PANIC filtered out the dumper | `mem-entries.md:1868` |
| 2026-10-09 | 50z | Phase 50z (2026-10-09): FIVE FIXES AND STILL AN EMPTY BUFFER - so stop asking how the log is written and ask whether the panic happens at all | `mem-entries.md:1920` |
| 2026-10-09 | 50aa | Phase 50aa (2026-10-09): THE KERNEL NEVER PANICS - six faults, all real, all about a moment that never arrives | `mem-entries.md:1955` |
| 2026-10-09 | 50ab | Phase 50ab (2026-10-09): BOTH MAPPING APIS RETURN NULL FOR THIS RAM - so address it through `__va` | `mem-entries.md:2008` |
| 2026-10-09 | 50ac | Phase 50ac (2026-10-09): THE MARK LANDS - `__va` was the answer, and one boolean was hiding the text | `mem-entries.md:2050` |
| 2026-10-09 | 50ad | Phase 50ad (2026-10-09): ONE TOKEN EXPLAINS EVERYTHING - `rootwait` spins forever, so the kernel never panics and the capture never runs | `mem-entries.md:2085` |
| 2026-10-09 | 50ae | Phase 50ae (2026-10-09): THE KERNEL PANICS NOW - removing `rootwait` was the trigger fix - and the capture moves to a console | `mem-entries.md:2133` |
| 2026-10-09 | 50af | Phase 50af (2026-10-09): THE LOG IS CAPTURED, AND UBI'S OWN SENTENCE NAMES THE FAULT - our read is wrong at the VID header, not the EC header | `mem-entries.md:2177` |
| 2026-10-09 | 50ag | Phase 50ag (2026-10-09): THE KERNEL CAN SPEAK NOW - a driver that prints, and a read that is wrong only away from the PEB boundary | `mem-entries.md:2222` |
| 2026-10-09 | 50ah | Phase 50ah (2026-10-09): `-EINVAL` COMES ONLY FROM `validate_vid_hdr` - so the magic read fine and a FIELD failed | `mem-entries.md:2252` |
| 2026-10-09 | 50ai | Phase 50ai (2026-10-09): THE BUILD CAUGHT WHAT MY CHECK MISSED - presence is not scope | `mem-entries.md:2299` |
| 2026-10-09 | 50aj | Phase 50aj (2026-10-09): THE READ PATH IS EXONERATED, AND THE REJECTION HAS A NAMED LINE | `mem-entries.md:2331` |
| 2026-10-09 | 50ak | Phase 50ak (2026-10-09): THE BLOCKER IS NAMED, VERIFIED, AND FIXED - `compat = 5` on the layout volume | `mem-entries.md:2378` |
| 2026-10-09 | 50al | Phase 50al (2026-10-09): THE COMPAT PATCH WAS NECESSARY BUT NOT SUFFICIENT - and I cannot read UBI's reason for a size reason | `mem-entries.md:2438` |
| 2026-10-09 | 50am | Phase 50am (2026-10-09): UBI'S OWN WORDS - `vtbl_check: bad CRC at record 6` - and a correction about fields I dismissed | `mem-entries.md:2478` |
| 2026-10-09 | 50an | Phase 50an (2026-10-09): THE INSTRUMENT WAS CORRUPTING THE DRIVER - a whole line of readings was my own cross-talk | `mem-entries.md:2517` |
| 2026-10-09 | 50ao | Phase 50ao (2026-10-09): THE SAME DECLARATION-ORDER CLASS AGAIN - and a crumb that is stamped too early to read | `mem-entries.md:2566` |
| 2026-10-09 | 50ap | Phase 50ap (2026-10-09): THE CLEAN INSTRUMENT BOOTS - and the log's address cannot be predicted, so the last crumb writer carries it | `mem-entries.md:2598` |
| 2026-10-09 | 50aq | Phase 50aq (2026-10-09): THE CRUMB WORKS, A COHERENT BUFFER DOES NOT SURVIVE, AND THE FIXED ADDRESS WAS RIGHT ALL ALONG | `mem-entries.md:2621` |
| 2026-10-09 | 50ar | Phase 50ar (2026-10-09): THE LOG IS TRUSTWORTHY, UBI'S COMPLAINT IS REAL, AND THE FAULT IS OFFSET-DEPENDENT | `mem-entries.md:2660` |
| 2026-10-09 | 50as | Phase 50as (2026-10-09): THE SAMPLE PRODUCED SOMETHING OUR DRIVER CANNOT DO - "rootfsb" may not be our device | `mem-entries.md:2699` |
| 2026-10-09 | 50at | Phase 50at (2026-10-09): THE CI CAUGHT A WRONG API BEFORE A FIRE WAS SPENT | `mem-entries.md:2732` |
| 2026-10-09 | 50au | Phase 50au (2026-10-09): `mtd14` - THE ANSWER HAS BEEN IN UBI'S MESSAGE THE WHOLE TIME | `mem-entries.md:2758` |
| 2026-10-09 | 50av | Phase 50av (2026-10-09): THE CHECKER WAS THE BUG - twice, and both times it reported "none" | `mem-entries.md:2795` |
| 2026-10-10 | 50aw | Phase 50aw (2026-10-10): OUR MTD IS INDEX 0, UBI USES mtd14 - AND THE CONFIG CORRECTS MY READING OF IT | `mem-entries.md:2834` |
| 2026-10-10 | 50ax | Phase 50ax (2026-10-10): CONFIRMED - THE VENDOR'S PARTITION TABLE IS ON OUR DEVICE | `mem-entries.md:2865` |
| 2026-10-10 | 50ay | Phase 50ay (2026-10-10): MTD_OF_PARTS REPLACES THE MASTER - and the number I called evidence was a stale field | `mem-entries.md:2894` |
| 2026-10-10 | 50az | Phase 50az (2026-10-10): THREE OF FOUR MATCH EXACTLY - THE FAULT IS A SHORT PAGE FILL | `mem-entries.md:2933` |
| 2026-10-10 | 50ba | Phase 50ba (2026-10-10): THREE OF FOUR MATCH - AND MY "ALL ZEROS" WAS AN ASSUMPTION, NOT A MEASUREMENT | `mem-entries.md:2969` |
| 2026-10-10 | 50bb | Phase 50bb (2026-10-10): THE DIFF NAMES THE BYTES - 18 OF THEM, AND ONE IS THE CRC | `mem-entries.md:3003` |
| 2026-10-10 | 50bc | Phase 50bc (2026-10-10): THE BOUNDARY IS PER-PAGE AT 1040 - AND `page_buf` WAS NEVER CHECKED | `mem-entries.md:3035` |
| 2026-10-10 | 50bd | Phase 50bd (2026-10-10): THE ADDRESSES KILLED THE COLLISION THEORY - AND THE WINDOW CHANGES BETWEEN READERS | `mem-entries.md:3074` |
| 2026-10-10 | 50be | Phase 50be (2026-10-10): THE BUSY POLL RACED THE DMA START - the driver bug, found by reading the code | `mem-entries.md:3107` |
| 2026-10-10 | 50bf | Phase 50bf (2026-10-10): THE RACE FIX CHANGED NOTHING - the bad data is deterministic | `mem-entries.md:3149` |
| 2026-10-10 | 50bg | Phase 50bg (2026-10-10): THE TWO READS AGREE - stable wrong data, and both theories closed by experiment | `mem-entries.md:3182` |
| 2026-10-10 | 50bh | Phase 50bh (2026-10-10): THE CONTROLLER LEAVES ZERO REGIONS UNWRITTEN - and every read returned stale memory there | `mem-entries.md:3217` |
| 2026-10-10 | 50bi | Phase 50bi (2026-10-10): THE CONTROLLER SPLICES 14 SPARE BYTES AT OFFSET 1040 - and record 6 is exactly what straddles it | `mem-entries.md:3258` |
| 2026-10-10 | 50bj | Phase 50bj (2026-10-10): THE PAGE READS EXACTLY - and UBI moved on to record 118 | `mem-entries.md:3292` |
| 2026-10-10 | 50bk | Phase 50bk (2026-10-10): UBI COMPUTES THE RIGHT CRC - the stored field's last two bytes were stale | `mem-entries.md:3324` |
| 2026-10-10 | 50bl | Phase 50bl (2026-10-10): THE WIDENED MEMSET CHANGED NOTHING - the zeros are the hardware's | `mem-entries.md:3359` |
| 2026-10-10 | 50bm | Phase 50bm (2026-10-10): ONE DIFFERENCE IN SIXTEEN SAMPLES - and it is the record's CRC field | `mem-entries.md:3390` |
| 2026-10-10 | 50bn | Phase 50bn (2026-10-10): THE SENTINEL SURVIVED - the transfer length register was never programmed | `mem-entries.md:3426` |
| 2026-10-10 | 50bo | Phase 50bo (2026-10-10): THE LENGTH WRITE WAS NOT ENOUGH - and the vendor's full read names two registers I never touch | `mem-entries.md:3468` |
| 2026-10-10 | 50bp | Phase 50bp (2026-10-10): THE READ-BACK PROVED THE WRITE LANDS - and the register map names FMC_DATA_NUM | `mem-entries.md:3505` |
| 2026-10-10 | 50bq | Phase 50bq (2026-10-10): THE READ-BACK CAUGHT MY MISTAKE - 0x38 is a counter, not a count | `mem-entries.md:3547` |
| 2026-10-10 | 50br | Phase 50br (2026-10-10): THE CONFIG ISN'T IT - and the counter that corrected me becomes the instrument | `mem-entries.md:3587` |
| 2026-10-10 | 50bs | Phase 50bs (2026-10-10): 0x38 IS STATIC - every per-operation register is now ruled out | `mem-entries.md:3620` |
| 2026-10-10 | 50bt | Phase 50bt (2026-10-10): THE OOB BUFFER IS LIVE - and it plus 0x38 both say SIXTEEN bytes per sector | `mem-entries.md:3657` |
| 2026-10-10 | 50bu | Phase 50bu (2026-10-10): THE COMPLAINT MOVED BACKWARD - 16 was wrong, 14 at 1040 was right | `mem-entries.md:3690` |
| 2026-10-10 | 50bv | Phase 50bv (2026-10-10): THE VENDOR'S TWO DMA OPERATIONS BOTH USE 0x40 - and my read matches theirs | `mem-entries.md:3723` |
| 2026-10-10 | 50bw | Phase 50bw (2026-10-10): THE VENDOR'S LIVE REGISTERS - my configuration matches it exactly, and the length is a PAGE COUNT | `mem-entries.md:3753` |
| 2026-10-10 | 50bx | Phase 50bx (2026-10-10): ONE DESTINATION - the vendor's spare was never in the flash, it was in my wiring | `mem-entries.md:3794` |
| 2026-10-10 | 50by | Phase 50by (2026-10-10): ONE DESTINATION MOVED THE FAULT - and FMC_DATA_NUM is the last value differing | `mem-entries.md:3830` |
| 2026-10-10 | 50bz | Phase 50bz (2026-10-10): THE TWO CHANGES OVERLAPPED - and the sentinel test ran under the old wiring | `mem-entries.md:3865` |
| 2026-10-10 | 50ca | Phase 50ca (2026-10-10): THE COMBINATION RESTORES THE BASELINE - and the copy already looks past 2048 | `mem-entries.md:3897` |
| 2026-10-10 | 50cb | Phase 50cb (2026-10-10): THE REGISTER SPACE IS ELIMINATED - the difference is in the SEQUENCE | `mem-entries.md:3935` |
| 2026-10-10 | 50cc | Phase 50cc (2026-10-10): THE POLL MATCHES TOO - and the caller has one step left to trace | `mem-entries.md:3965` |
| 2026-10-10 | 50cd | Phase 50cd (2026-10-10): FMC_CMD checked - and the state is exact | `mem-entries.md:4002` |
| 2026-10-10 | 50ce | Phase 50ce (2026-10-10): ★ THE VENDOR'S RAW DMA BUFFER IS CLEAN - the splice is entirely mine ★ | `mem-entries.md:4032` |
| 2026-10-10 | 50cf | Phase 50cf (2026-10-10): ★ THE FULL DUMP FOUND FIFTEEN REGISTERS MY DRIVER NEVER WRITES ★ | `mem-entries.md:4061` |
| 2026-10-10 | 50cg | Phase 50cg (2026-10-10): THE CONFIG BLOCK MADE NO DIFFERENCE - and one tension I have not resolved | `mem-entries.md:4113` |
| 2026-10-10 | 50ch | Phase 50ch (2026-10-10): THE VENDOR'S RAW IS CLEAN WHERE MINE IS SPLICED - the tension is measured, not hypothetical | `mem-entries.md:4147` |
| 2026-10-10 | 50ci | Phase 50ci (2026-10-10): ★ THE HARDWARE DOES NOT SPLICE - my de-interleave has been compensating for my own defect ★ | `mem-entries.md:4181` |
| 2026-10-10 | 50cj | Phase 50cj (2026-10-10): THE PLAIN COPY FELL TO RECORD 6 - the splice is real here, the vendor's is clean | `mem-entries.md:4211` |
| 2026-10-10 | 50ck | Phase 50ck (2026-10-10): ★★★ I HAD BEEN READING THE WRONG FUNCTION - the vendor waits on the DMA INTERRUPT ★★★ | `mem-entries.md:4239` |
| 2026-10-10 | 50cl | Phase 50cl (2026-10-10): THE INTERRUPT ATTEMPT FAILED INFORMATIVELY - and it exposed a real bug in my own change | `mem-entries.md:4282` |
| 2026-10-10 | 50cm | Phase 50cm (2026-10-10): THE INTERRUPT REPLACES THE BUSY POLLS - that is why step 8 failed | `mem-entries.md:4314` |
| 2026-10-10 | 50cn | Phase 50cn (2026-10-10): THE INTERRUPT WORKS AND IS NEUTRAL - the completion mechanism is eliminated | `mem-entries.md:4349` |
| 2026-10-10 | 50co | Phase 50co (2026-10-10): THE ADDRESSES MATCH TOO - the column is zero on both sides | `mem-entries.md:4380` |
| 2026-10-10 | 50cp | Phase 50cp (2026-10-10): ★★★ THE SYMBOL TABLE HAD A GAP AT 0x2d80 - and behind it, feature 0xB0 ★★★ | `mem-entries.md:4420` |
| 2026-10-10 | 50cq | Phase 50cq (2026-10-10): FEATURE 0xB0 SET, RESULT UNCHANGED - eliminated | `mem-entries.md:4456` |
| 2026-10-10 | 50cr | Phase 50cr (2026-10-10): THE VENDOR'S READ PATH IS A DEEP CHAIN - and every level compared matches | `mem-entries.md:4492` |
| 2026-10-10 | 50cs | Phase 50cs (2026-10-10): ★★★★ THE RELOCATION TABLE NAMED THE CALLS - the vendor's page read writes FIVE registers, mine wrote SEVEN ★★★★ | `mem-entries.md:4527` |
| 2026-10-10 | 50ct | Phase 50ct (2026-10-10): THE FIVE WRITES ALONE FAILED - because the vendor's INIT sets what mine never did | `mem-entries.md:4572` |
| 2026-10-10 | 50cu | Phase 50cu (2026-10-10): SETTING THEM EARLIER IN THE PROBE DID NOT SURVIVE EITHER | `mem-entries.md:4604` |
| 2026-10-10 | 50cv | Phase 50cv (2026-10-10): THREE BUILDS SAY THIS CONTROLLER NEEDS THOSE TWO WRITTEN PER OPERATION | `mem-entries.md:4635` |
| 2026-10-10 | 50cw | Phase 50cw (2026-10-10): MY "INIT-TIME" THEORY WAS WRONG - they are per-operation registers | `mem-entries.md:4680` |
| 2026-10-10 | 50cx | Phase 50cx (2026-10-10): THE BASELINE GOT LOST - restored from a measured-working commit | `mem-entries.md:4712` |
| 2026-10-10 | 50cy | Phase 50cy (2026-10-10): THE RESTORE IS FAITHFUL - 117 records are back, and the tree is trustworthy | `mem-entries.md:4750` |
| 2026-10-10 | 50cz | Phase 50cz (2026-10-10): ★★★★★ THE ECC ENGINE - THE PAGE READ WAS DISABLING IT ★★★★★ | `mem-entries.md:4785` |
| 2026-10-10 | 50da | ★★★★★ PHASE 50da (2026-10-10): UBI ATTACHED - THE ROOTFS VOLUME IS READABLE ★★★★★ | `mem-entries.md:4828` |
| 2026-10-10 | 50db | Phase 50db (2026-10-10): A REAL INIT, GUARDED BY A KERNEL TIMER RATHER THAN A FAKE ONE | `mem-entries.md:4867` |
| 2026-10-10 | 50dc | ★★★★★ PHASE 50dc (2026-10-10): OUR KERNEL MOUNTS THE ROOTFS AND RUNS USERSPACE ★★★★★ | `mem-entries.md:4905` |
| 2026-10-10 | 50dd | ★★★★★ PHASE 50dd (2026-10-10): OPENWRT 25.12.5 IS ON THE DEVICE - OUR OWN ROOTFS ★★★★★ | `mem-entries.md:4950` |
| 2026-10-10 | 50de | Phase 50de (2026-10-10): THE LOG TOLD US THE MOUNT WORKED AND COULD NOT SHOW IT | `mem-entries.md:5004` |
| 2026-10-10 | 50df | ★★★★★ PHASE 50df (2026-10-10): THE VENDOR'S KERNEL MOUNTS OUR IMAGE - OURS FAULTS IN THE MOUNT ★★★★★ | `mem-entries.md:5046` |
| 2026-10-10 | 50dg | ★★★★★ PHASE 50dg (2026-10-10): THE INSTRUMENT WAS READING A 4 KiB LOG AND OVERWRITING THE CONSOLE ★★★★★ | `mem-entries.md:5111` |
| 2026-10-10 | 50dh | ★★★★★ PHASE 50dh (2026-10-10): THE CONSOLE NEVER CAPTURED ANYTHING ★★★★★ | `mem-entries.md:5168` |
| 2026-10-10 | 50di | Phase 50di (2026-10-10): THE BUILD FAILED ON FUNCTION ORDER - AND THE VALIDATOR COULD NOT HAVE CAUGHT IT | `mem-entries.md:5215` |
| 2026-10-10 | 50dj | Phase 50dj (2026-10-10): THE SAME CLASS AGAIN - MOVING A BLOCK MEANS MOVING ALL OF IT | `mem-entries.md:5256` |
| 2026-10-10 | 50dk | Phase 50dk (2026-10-10): THE RING CANNOT ANSWER THE QUESTION - SO STAMP IT | `mem-entries.md:5310` |
| 2026-10-10 | 50dl | Phase 50dl (2026-10-10): AN INSTRUMENT WHOSE ADDRESS IS UNCERTAIN REPORTS ABSENCE | `mem-entries.md:5359` |
| 2026-10-10 | 50dm | Phase 50dm (2026-10-10): A PHYSICAL ADDRESS IS NOT A POINTER - AND THE FILE SAID SO | `mem-entries.md:5408` |
| 2026-10-10 | 50dn | Phase 50dn (2026-10-10): THE GUESSED ADDRESS HUNG THE BOOT - STAMP IN THE RING INSTEAD | `mem-entries.md:5451` |
| 2026-10-10 | 50do | ★★★★★ PHASE 50do (2026-10-10): EVERY WORKING IMAGE ON THIS BENCH USES 128 KiB BLOCKS ★★★★★ | `mem-entries.md:5512` |
| 2026-10-10 | 50dp | ★★★★★ PHASE 50dp (2026-10-10): THE BLOCK-SIZE HYPOTHESIS IS WRONG - THE 256 KiB IMAGE READS PERFECTLY | `mem-entries.md:5573` |
| 2026-10-10 | 50dq | ★★★★★ PHASE 50dq (2026-10-10): THE VENDOR'S OWN PATH - A COMPLETE OPENWRT ROOTFS IN A UBI VOLUME ★★★★★ | `mem-entries.md:5614` |
| 2026-10-10 | 50dr | Phase 50dr (2026-10-10): SIX RAM ADDRESSES DID NOT LAND - ASK THROUGH I/O INSTEAD | `mem-entries.md:5680` |
| 2026-10-10 | 50ds | ★★★★★ PHASE 50ds (2026-10-10): THE TIMER RUNS 46 TIMES - AND THE BOOT HANGS, NOT PANICS ★★★★★ | `mem-entries.md:5743` |
| 2026-10-10 | 50dt | Phase 50dt (2026-10-10): THE THIRD ORDER FAILURE - AND THE CHECKER ITSELF HAD THE GAP | `mem-entries.md:5804` |
| 2026-10-10 | 50du | ★★★★★ PHASE 50du (2026-10-10): THE MUTEX FIXED THE HANG ★★★★★ | `mem-entries.md:5862` |
| 2026-10-10 | 50dv | ★★★★★ PHASE 50dv (2026-10-10): THE WALK RETURNS 230 LINES - THE CONSOLE WAS EATING THEM ★★★★★ | `mem-entries.md:5909` |
| 2026-10-10 | 50dw | ★★★★★ PHASE 50dw (2026-10-10): THE RING WORKS - MY EXTRACTION WAS THE BUG ★★★★★ | `mem-entries.md:5952` |
| 2026-10-10 | 50dx | ★★★★★ PHASE 50dx (2026-10-10): A MUTEX WHERE ONLY A SPINLOCK IS LEGAL - THAT IS THE HARD HANG ★★★★★ | `mem-entries.md:6014` |
| 2026-10-10 | 50dy | ★★★★★ PHASE 50dy (2026-10-10): THE PERIODIC DUMP WAS STRANGLING THE KERNEL ★★★★★ | `mem-entries.md:6074` |
| 2026-10-10 | 50dz | ★★★★★ PHASE 50dz (2026-10-10): THE HANG IS GONE, A REAL PANIC APPEARED, AND THE RING FINALLY HAS A REASON ★★★★★ | `mem-entries.md:6126` |
| 2026-10-10 | 50ea | ★★★★★ PHASE 50ea (2026-10-10): EVERY I/O WRITE STICKS AND EVERY RAM WRITE VANISHES ★★★★★ | `mem-entries.md:6177` |
| 2026-10-10 | 50eb | ★★★★★ PHASE 50eb (2026-10-10): THE PHYSICAL ADDRESS WAS RIGHT ALL ALONG - `__va` IS THE QUESTION ★★★★★ | `mem-entries.md:6234` |
| 2026-10-10 | 50ec | ★★★★★ PHASE 50ec (2026-10-10): THE POINTER IS RIGHT AND THE TRANSLATION IS RIGHT ★★★★★ | `mem-entries.md:6282` |
| 2026-10-10 | 50ed | ★★★★★ PHASE 50ed (2026-10-10): THE TWO PATHS MEET - AND THE RING STOPS AT 4 KB ★★★★★ | `mem-entries.md:6331` |
| 2026-10-10 | 50ee | ★★★★★ PHASE 50ee (2026-10-10): UBI ATTACHES, AND A WARNING'S TRACE - BUT THE TEXT IS SPLICED ★★★★★ | `mem-entries.md:6374` |
| 2026-10-10 | 50ef | ★★★★★ PHASE 50ef (2026-10-10): THE LOCK WAS STARVING EVERYTHING ★★★★★ | `mem-entries.md:6424` |
| 2026-10-10 | 50eg | ★★★★★ PHASE 50eg (2026-10-10): THE FRONTIER MOVED, AND THE SLIDE WAS CUTTING LINES IN HALF ★★★★★ | `mem-entries.md:6484` |
| 2026-10-10 | 50eh | ★★★★★ PHASE 50eh (2026-10-10): THE ROOTFS MOUNTS - AND THE HOLES WERE UNFLUSHED CACHE ★★★★★ | `mem-entries.md:6540` |
| 2026-10-10 | 50ei | ★★★★★ PHASE 50ei (2026-10-10): THE ROOTFS MOUNTS, INIT RUNS - AND THE USERSPACE WAS FOR THE WRONG CPU ★★★★★ | `mem-entries.md:6610` |
| 2026-10-10 | 50ej | ★★★★★ PHASE 50ej (2026-10-10): THE A9 ROOTFS DIES THE SAME WAY - SO THE FAULT IS IN THE KERNEL'S FPU ★★★★★ | `mem-entries.md:6703` |
| 2026-10-10 | 50ek | ★★★★★ PHASE 50ek (2026-10-10): THIS PART HAS NO USABLE FPU - AND THE VENDOR KNEW IT ★★★★★ | `mem-entries.md:6784` |
| 2026-10-10 | 50el | ★★★★★ PHASE 50el (2026-10-10): THE SOFT-FLOAT ROOTFS USES NOTHING THIS SILICON LACKS ★★★★★ | `mem-entries.md:6875` |
| 2026-10-10 | 50em | PHASE 50em (2026-10-10): ★ THE USERSPACE RAN ★ - our kernel boots OpenWrt on the WR3000 v2 | `mem-entries.md:6916` |
| 2026-10-10 | 50en | PHASE 50en (2026-10-10): ★★★★★ OpenWrt 25.12.5 IS RUNNING ON OUR OWN KERNEL ★★★★★ | `mem-entries.md:6971` |
| 2026-10-10 | 50eo | ★★★★★ PHASE 50eo (2026-10-10): THE VENDOR'S FLASH RECIPE SET, RECOVERED ★★★★★ | `mem-entries.md:7050` |
| 2026-10-10 | 50ep | ★★★★★ PHASE 50ep (2026-10-10): THE WRITE PATH, TAKEN FROM THE VENDOR'S OWN SYMBOL TABLE ★★★★★ | `mem-entries.md:7147` |
| 2026-10-10 | 50eq | PHASE 50eq (2026-10-10): THE WRITE PATH COMPILES - AFTER THE COMPILER CORRECTED ME ON AN API | `mem-entries.md:7225` |
| 2026-10-10 | 50er | ★★★★★ PHASE 50er (2026-10-10): THE WRITE WROTE NOTHING, AND NOBODY SAID SO ★★★★★ | `mem-entries.md:7264` |
| 2026-10-10 | 50es | PHASE 50es (2026-10-10): THE TICK CARRIES THE WRITE'S REPORT | `mem-entries.md:7358` |
| 2026-10-10 | 50et | ★★★★★ PHASE 50et (2026-10-10): `writes = 0` - AND UBIFS NEVER FORMATS ANYTHING ★★★★★ | `mem-entries.md:7396` |
| 2026-10-10 | 50eu | ★★★★★ PHASE 50eu (2026-10-10): THE WRITE PATH WORKS - AND THE READ PATH IS BYTE-EXACT ON THIS VOLUME | `mem-entries.md:7466` |
| 2026-10-10 | 50ev | ★★★★★ PHASE 50ev (2026-10-10): OPENWRT ONLY MOUNTS rootfs_data - AND MY IMAGE MISSED `-F` ★★★★★ | `mem-entries.md:7534` |
| 2026-10-10 | 50ew | ★★★★★ PHASE 50ew (2026-10-10): THE OVERLAY PARTITION HAS BEEN IN OUR DEVICETREE ALL ALONG ★★★★★ | `mem-entries.md:7594` |
| 2026-10-10 | 50ex | ★★★★★ PHASE 50ex (2026-10-10): MOUNT_ROOT DOES NOT PROBE - A UBI VOLUME MEANS UBIFS, FULL STOP | `mem-entries.md:7654` |
| 2026-10-10 | 50ey | PHASE 50ey (2026-10-10): THE UBIFS IMAGE MAPPED - AND `7:41` IS NOT A BUG | `mem-entries.md:7711` |
| 2026-10-10 | 50ez | PHASE 50ez (2026-10-10): THE DIAGNOSTIC WAS RIGHT AND ITS OUTPUT WAS DISCARDED | `mem-entries.md:7766` |
| 2026-10-10 | 50fa | ★★★★★ PHASE 50fa (2026-10-10): FSTOOLS IDENTIFIES THE OVERLAY BY FOUR BYTES - AND THEY WERE ff ff ff ff | `mem-entries.md:7820` |
| 2026-10-10 | 50fb | PHASE 50fb (2026-10-10): WHY OPENWRT'S OWN MARKING NEVER LANDED - NO OOB WRITE PATH | `mem-entries.md:7886` |
| 2026-10-10 | 50fc | ★★★★★ PHASE 50fc (2026-10-10): THE MARKER WORKED, AND JFFS2 REFUSED ON ONE MISSING FIELD | `mem-entries.md:7920` |
| 2026-10-10 | 50fd | PHASE 50fd (2026-10-10): THE MARKER WAS WRITTEN, AND JFFS2 ASKED FOR THE OOB NEXT | `mem-entries.md:7981` |
| 2026-10-10 | 50fe | PHASE 50fe (2026-10-10): JFFS2 SCANS THE PARTITION - A WRONG CRC FLAVOUR AND 1.5 MB OF LEFTOVER DATA | `mem-entries.md:8026` |
| 2026-10-10 |  | AND THE BUILD CAUGHT THE SAME CLASS AGAIN: `__aeabi_uldivmod` (2026-10-10) | `mem-entries.md:8069` |
| 2026-10-10 | 50ff | PHASE 50ff (2026-10-10): THE ERASE WAS A NO-OP - WRONG ADDRESS ENCODING | `mem-entries.md:8086` |
| 2026-10-10 | 50fg | PHASE 50fg (2026-10-10): THE ERASE ADDRESS IS A BLOCK NUMBER - AND BLOCK 0 HID IT | `mem-entries.md:8125` |
| 2026-10-10 | 50fh | PHASE 50fh (2026-10-10): A READ-BACK OF ERASED FLASH PROVES NOTHING | `mem-entries.md:8159` |
| 2026-10-10 | 50fi | PHASE 50fi (2026-10-10): THE SELF-TEST SETTLED THE ERASE ENCODING | `mem-entries.md:8198` |
| 2026-10-10 | 50fj | PHASE 50fj (2026-10-10): THE SELF-TEST'S OWN FIRST READ WAS THE ANOMALY | `mem-entries.md:8230` |
| 2026-10-10 | 50fk | PHASE 50fk (2026-10-10): JFFS2 READ BACK MY PLANTED PATTERN | `mem-entries.md:8266` |
| 2026-10-10 | 50fl | ★★★★★ PHASE 50fl (2026-10-10): THE MISSING WRITE ENABLE - WHY EVERY ERASE DID NOTHING | `mem-entries.md:8296` |
| 2026-10-10 | 50fm | ★★★★★ PHASE 50fm (2026-10-10): ERASE WORKS - AND A RACE ATE PART OF THE PARTITION | `mem-entries.md:8336` |
| 2026-10-10 | 50fn | PHASE 50fn (2026-10-10): THE BOARD IS STRANDED - WHAT IS READY, AND THE HAZARD I INTRODUCED | `mem-entries.md:8373` |
| 2026-10-11 | 51 | PHASE 51 (2026-10-11): LOCAL BUILD LANE + THE STRAND FIX VERIFIED LOCALLY | `mem-entries.md:8423` |
| 2026-10-11 | 52 | PHASE 52 (2026-10-11): THE NON-WIFI LANES - LEDGER | `mem-entries.md:8468` |
| 2026-10-11 | 53 | PHASE 53 (2026-10-11): TWO NEW DRIVERS + THE MISSING THERMAL NODE | `mem-entries.md:8559` |
| 2026-10-11 | 54 | PHASE 54 (2026-10-11): EVERY LOCAL-ONLY LANE CLOSED - THE FLASH IS THE ONLY STEP LEFT | `mem-entries.md:8625` |
| 2026-10-11 | 55 | PHASE 55 (2026-10-11): THE FIRE - OUR KERNEL FLASHED, AND IT DID NOT REACH USERSPACE | `mem-entries.md:8694` |
| 2026-10-11 | 56 | PHASE 56 (2026-10-11): THE FIRE'S AFTERMATH - BOARD FULLY RESTORED AND HEALTHY | `mem-entries.md:8747` |
| 2026-10-11 | 57 | PHASE 57 (2026-10-11): ★ THE FIRE'S FAILURE IS EXPLAINED - AND IT WAS MY OWN "COMPILE FIX" ★ | `mem-entries.md:8797` |
| 2026-10-11 | 58 | PHASE 58 (2026-10-11): ★ CORRECTION - PHASE 57's ROOT CAUSE WAS WRONG; THE REAL ONE IS THE ERASE LOOP VS THE SAFETY TIMER ★ | `mem-entries.md:8852` |
| 2026-10-11 | 58b | PHASE 58b (2026-10-11): THE BUILD CARRIED THE WRONG SOURCE - `cp -r` MERGES | `mem-entries.md:8964` |
| 2026-10-11 | 58d | PHASE 58d (2026-10-11): THE GATE IS COMPLETE - VERIFIED BY POSITION, NOT BY IMPRESSION | `mem-entries.md:8998` |
| 2026-10-11 | 58e | PHASE 58e (2026-10-11): LOCAL WORK IS EXHAUSTED - THE FIRE IS THE ONLY REMAINING STEP | `mem-entries.md:9017` |
| 2026-10-11 | 59 | PHASE 59 (2026-10-11): FIRE 2 - THE SWITCH WORKED, THE KERNEL DIED BEFORE ITS FIRST BREADCRUMB | `mem-entries.md:9048` |
| 2026-10-11 | 60 | PHASE 60 (2026-10-11): ★ THE FIRE'S FAILURE IS THE KNOWN MMU-TRANSITION CLASS - AND MY C18=0 READING WAS UNCONTROLLED ★ | `mem-entries.md:9105` |
| 2026-10-11 | 61 | ★★★★★ PHASE 61 (2026-10-11): THE CONTROLLED READ - OUR KERNEL NEVER EXECUTES ★★★★★ | `mem-entries.md:9175` |
| 2026-10-11 | 62 | PHASE 62 (2026-10-11): THE BISECT FOUND A MEASURABLE DIFFERENCE - OUR Image IS 204 KB SMALLER THAN THE KNOWN-GOOD | `mem-entries.md:9215` |
| 2026-10-11 | 63 | PHASE 63 (2026-10-11): THE BISECT'S FIRST CANDIDATE IS RULED OUT - `dt_rewrite` IS ABSENT FROM BOTH BUILDS | `mem-entries.md:9266` |
| 2026-10-11 | 64 | ★★★★★ PHASE 64 (2026-10-11): THE CONTROL FIRE - THE NAND DRIVER IS EXONERATED ★★★★★ | `mem-entries.md:9326` |
| 2026-10-11 | 65 | PHASE 65 (2026-10-11): `CONFIG_CMDLINE` IS EXONERATED BY THE RECORD - NO FIRE SPENT | `mem-entries.md:9386` |
| 2026-10-11 | 66 | ★★★★★ PHASE 66 (2026-10-11): FIRE 5 - THE CONFIG IS EXONERATED TOO ★★★★★ | `mem-entries.md:9438` |
| 2026-10-11 | 67 | ★★★★★ PHASE 67 (2026-10-11): FIRE 6 - THE HEAD READER IS EXONERATED; ONE CANDIDATE LEFT ★★★★★ | `mem-entries.md:9495` |
| 2026-10-11 | 68 | ★★★★★ PHASE 68 (2026-10-11): THE REMAINING VARIABLE IS THE COMPILER - AND IT WAS NEVER CONTROLLED ★★★★★ | `mem-entries.md:9561` |
| 2026-10-11 | 69 | ★★★★★ PHASE 69 (2026-10-11): FIRE 7 - THE COMPILER IS EXONERATED TOO. THE SEARCH IS OUT OF SOURCE-SIDE CANDIDATES. ★★★★★ | `mem-entries.md:9616` |
| 2026-10-11 | 70 | PHASE 70 (2026-10-11): ★ THE BUG IS FOUND - I WAS FLASHING A BARE uImage ★ | `mem-entries.md:9687` |
| 2026-10-11 | 71 | PHASE 71 (2026-10-11): FIRE 8 - THE FULL SLICE ALSO DOES NOT RUN. TAKING STOCK HONESTLY. | `mem-entries.md:9748` |
| 2026-10-11 | 72 | PHASE 72 (2026-10-11): ★ THE PATH TEST - THE MANUAL FLASH WORKS; OUR BUILDS ARE THE PROBLEM ★ | `mem-entries.md:9819` |
| 2026-10-11 | 73 | PHASE 73 (2026-10-11): THE FRAME IS NOW CLEAN - HEADERS MATCH, SIZES ARE SANE, THE CODE IS THE VARIABLE | `mem-entries.md:9872` |
| 2026-10-11 | 74 | PHASE 74 (2026-10-11): THE BISECT'S BASELINE IS FULLY CHARACTERISED (and a build-infrastructure lesson) | `mem-entries.md:9919` |
| 2026-10-11 | 75 | PHASE 75 (2026-10-11): THE BUILD IS REPRODUCIBLE - AND THE nop SWING IS COMPRESSION, NOT CODE | `mem-entries.md:9959` |
| 2026-10-11 | 76 | ★★★ PHASE 76 (2026-10-11): THE MEASUREMENT IS NOT AS CONTROLLED AS I SAID - AND THE nop LEVER IS NOT CLEAN ★★★ | `mem-entries.md:9994` |
| 2026-10-11 | 77 | PHASE 77 (2026-10-11): FIXED TREES - THE SIZE DRIFT VANISHES, THE nop LEVER IS CONFIRMED NON-ISOLABLE | `mem-entries.md:10039` |
| 2026-10-11 | 78 | PHASE 78 (2026-10-11): THE KNOWN-GOOD CONTROL HAS A NUMERIC PREDICTION - 9,984,344 B | `mem-entries.md:10079` |
| 2026-10-11 | 79 | PHASE 79 (2026-10-11): ★★★ THE KNOWN-GOOD BINARY DOES NOT BOOT EITHER ★★★ | `mem-entries.md:10114` |
| 2026-10-11 | 80 | PHASE 80 (2026-10-11): THE FULL SLICE ALSO FAILS - THE LAYOUT IS NOT THE ANSWER EITHER | `mem-entries.md:10181` |
| 2026-10-11 | 81 | PHASE 81 (2026-10-11): ★★★ THE COMPLETE A/B - IT IS THE IMAGE'S SIZE/SHAPE, NOT THE CONTENT ★★★ | `mem-entries.md:10230` |
| 2026-10-11 | 82 | PHASE 82 (2026-10-11): THE PADDED SLICE FAILS TOO - AND A HARD LOOK AT WHERE THIS IS GOING | `mem-entries.md:10281` |
| 2026-10-11 | 83 | PHASE 83 (2026-10-11): THE SLOT CONTENT IS EXACTLY WHAT WE WROTE - THE WRITE IS FAIR | `mem-entries.md:10344` |
| 2026-10-11 | 84 | PHASE 84 (2026-10-11): ★★★ THE LENGTH CONTROL - THE DIFFERENCE IS THE PAYLOAD CONTENT ★★★ | `mem-entries.md:10389` |
| 2026-10-11 | 85 | PHASE 85 (2026-10-11): ★★★★★ FOUND IT - THE KERNEL COMPRESSION FORMAT ★★★★★ | `mem-entries.md:10440` |
| 2026-10-11 | 86 | PHASE 86 (2026-10-11): THE XZ FIRE (15) WAS CONFOUNDED - AND WHAT THE SESSION'S REAL PATTERN IS | `mem-entries.md:10497` |
| 2026-10-11 | 87 | PHASE 87 (2026-10-11): THE COMPRESSION FORMAT IS EXONERATED (PROPERLY) | `mem-entries.md:10535` |
| 2026-10-11 | 88 | PHASE 88 (2026-10-11): ★★★★★ FOUND IT - OUR BREADCRUMB OCCUPIES THE zImage ENTRY POINT ★★★★★ | `mem-entries.md:10576` |
| 2026-10-11 | 90 | PHASE 90 (2026-10-11): THE ENTRY-POINT FIX DID NOT BOOT IT - HONEST STATUS | `mem-entries.md:10680` |
| 2026-10-11 | 91 | PHASE 91 (2026-10-11): ★★★★★ THE SLICE STRUCTURE - A 96-BYTE DESCRIPTOR TABLE I NEVER BUILT ★★★★★ | `mem-entries.md:10734` |
| 2026-10-11 | 92 | PHASE 92 (2026-10-11): ★★★★★★★ OUR KERNEL EXECUTED - FOR THE FIRST TIME IN 18 FIRES ★★★★★★★ | `mem-entries.md:10794` |
| 2026-10-11 | 93 | PHASE 93 (2026-10-11): ★★★★★★★ THE ROOT CAUSE - A 1 GB LINK/L0AD ADDRESS MISMATCH ★★★★★★★ | `mem-entries.md:10851` |
| 2026-10-11 | 94 | PHASE 94 (2026-10-11): FIRE 20 HUNG THE BOARD - the record's own last-fired artifact | `mem-entries.md:10911` |
| 2026-10-11 | 95 | PHASE 95 (2026-10-11): ★ VERIFIED AGAINST BYTES - WHAT u-boot DOES WITH THE SLOT ★ | `mem-entries.md:10950` |
| 2026-10-11 | 96 | PHASE 96 (2026-10-11): FOUR MORE CANDIDATES TESTED AND ELIMINATED (host-side, no fire) | `mem-entries.md:11034` |
| 2026-10-11 | 97 | PHASE 97 (2026-10-11): ★ THE 0xC0DE000B -> stext MECHANISM, COMPUTED END TO END ★ | `mem-entries.md:11074` |
| 2026-10-11 | 98 | ★★★★★ PHASE 98 (2026-10-11): ★ THE MECHANISM, DISASSEMBLY-CONFIRMED - AND A PRIOR HUNT ALREADY FOUND IT ★★★★★ | `mem-entries.md:11146` |
| 2026-10-11 | 99 | PHASE 99 (2026-10-11): ★ THE GATE IS FULLY CHARACTERISED AND OUR ARTIFACT PASSES IT ★ | `mem-entries.md:11222` |
| 2026-10-11 | 100 | PHASE 100 (2026-10-11): ★★★★★★★★ THE r4 BUG - OUR BREADCRUMB DESTROYED THE JUMP TARGET ★★★★★★★★ | `mem-entries.md:11312` |
| 2026-10-11 | 101 | PHASE 101 (2026-10-11): THE r4 FIX VERIFIED AT THE INSTRUCTION LEVEL IN THE LINKED BINARY | `mem-entries.md:11405` |
| 2026-10-11 | 102 | PHASE 102 (2026-10-11): PRE-FIRE AUDIT COMPLETE - r4 REACHES THE JUMP INTACT | `mem-entries.md:11451` |
| 2026-10-12 | 103 | ★★★★★ PHASE 103 (2026-10-12): THE WEB DOOR IS OPEN - AND THE ACCESS SITUATION IS FULLY MAPPED | `mem-entries.md:11487` |
| 2026-10-12 | 104 | PHASE 104 (2026-10-12): THE VENDOR SYSUPGRADE'S KERNEL SITS AT OUR EXACT LOAD ADDRESS | `mem-entries.md:11556` |
| 2026-10-12 | 105 | PHASE 105 (2026-10-12): THE COMPLETE CONTAINER LAYOUT AND THE REBUILD PLAN | `mem-entries.md:11604` |
| 2026-10-11 | 106 | PHASE 106 (2026-10-11): THE CONTAINER IS SIGNED AND THE KERNEL SITS INSIDE THE VERIFIED FIT | `mem-entries.md:11657` |
| 2026-10-11 | 107 | PHASE 107 (2026-10-11): THE REBUILD ARTIFACTS ALL SURVIVE - AND THERE IS A WORKING SLOT-IMAGE TEMPLATE | `mem-entries.md:11709` |
| 2026-10-11 | 108 | PHASE 108 (2026-10-11): ★ THE COMPLETE SLOT IMAGE IS BUILT AND VERIFIED - ALL SEVEN CHECKS PASS ★ | `mem-entries.md:11753` |
| 2026-10-11 | 109 | ★★★★★ PHASE 109 (2026-10-11): ACCESS RESTORED - THE SHELL IS BACK AND IT IS DURABLE ★★★★★ | `mem-entries.md:11793` |
| 2026-10-11 | 110 | PHASE 110 (2026-10-11): ★★★★★ FIRE 21 - OUR KERNEL REACHED USERSPACE AND RAN ITS TIMER ★★★★★ | `mem-entries.md:11853` |
| 2026-10-11 | 111 | PHASE 111 (2026-10-11): ★★★★★ THE TWO ANSWERS WERE ALREADY IN MY OWN NOTES - AND BOTH ARE CONFIRMED LIVE ★★★★★ | `mem-entries.md:11913` |
| 2026-10-11 | 112 | PHASE 112 (2026-10-11): FIRE 22 - OUR KERNEL IN kernela: THE BOARD WENT DARK | `mem-entries.md:11979` |
| 2026-10-11 | 113 | PHASE 113 (2026-10-11): FIRE 22'S OUTCOME AND THE RECOVERY SETUP | `mem-entries.md:12025` |
| 2026-10-11 | 114 | PHASE 114 (2026-10-11): ★★★★★ `0xC0DE502D` IS DEFINED - THE TIMER RAN, AND THAT IS NOT A HANG ★★★★★ | `mem-entries.md:12063` |
| 2026-10-11 | 115 | PHASE 115 (2026-10-11): ★★★★★ WE REPRODUCED THE EXACT CRUMB OF THE RECORDED SUCCESSFUL BOOT ★★★★★ | `mem-entries.md:12124` |
| 2026-10-12 | 116 | PHASE 116 (2026-10-12): ★★★★★ THE SOFT-FLOAT ROOTFS IS IDENTIFIED AND VERIFIED ★★★★★ | `mem-entries.md:12178` |
| 2026-10-12 | 117 | PHASE 117 (2026-10-12): EVERY HOST-SIDE INPUT IS VERIFIED - THE NEXT FIRE IS FULLY SPECIFIED | `mem-entries.md:12233` |
| 2026-10-12 | 118 | PHASE 118 (2026-10-12): THE MOUNT CHAIN IS FULLY SUPPORTED - THE GAP IS THE VOLUME'S CONTENT | `mem-entries.md:12274` |
| 2026-10-12 | 119 | PHASE 119 (2026-10-12): ★★★★★ THE UBI IMAGE IS BUILT AND FULLY VERIFIED ★★★★★ | `mem-entries.md:12317` |
| 2026-10-12 | 120 | PHASE 120 (2026-10-12): ★ mtd16 SURVIVES THE RECOVERY - READ FROM THE DEVICE'S OWN UPGRADE CODE ★ | `mem-entries.md:12375` |
| 2026-10-12 | 121 | PHASE 121 (2026-10-12): THE COMPLETE VERIFIED PLAN - EVERY RISK CHECKED, EVERY ARTIFACT HASHED | `mem-entries.md:12417` |
| 2026-10-12 | 122 | PHASE 122 (2026-10-12): ★★★★★ GOAL CRITERION 2 MET - 6/6 CLAIMS INDEPENDENTLY VERIFIED, AND I REPRODUCED THEM MYSELF ★★★★★ | `mem-entries.md:12466` |
| 2026-10-12 | 123 | PHASE 123 (2026-10-12): THE CRC CLAIM, RESTATED PRECISELY - THE VERIFIER'S FLAG WAS RIGHT | `mem-entries.md:12541` |
| 2026-10-12 | 124 | PHASE 124 (2026-10-12): ★★★★★ THE UBI IMAGE'S VID HEADERS PARSED - AND A COMPATIBILITY DEPENDENCY CONFIRMED ★★★★★ | `mem-entries.md:12594` |
| 2026-10-12 | 125 | PHASE 125 (2026-10-12): ★ THE WHOLE CHAIN VERIFIED END TO END - AND A SELF-CAUGHT PARSE ERROR ★ | `mem-entries.md:12647` |
| 2026-10-12 | 126 | PHASE 126 (2026-10-12): ★ THE ENTIRE MOUNT CHAIN VERIFIED LINK BY LINK - NO HOST-SIDE UNKNOWNS LEFT ★ | `mem-entries.md:12703` |
| 2026-10-12 | 127 | PHASE 127 (2026-10-12): ★ A THIRD SELF-CORRECTION - ubiblock DOES NOT REQUIRE A STATIC VOLUME ★ | `mem-entries.md:12756` |
| 2026-10-12 | 128 | PHASE 128 (2026-10-12): THE REFINED DEPLOY PLAN - TWO ROUTES, RANKED BY PROOF | `mem-entries.md:12804` |
| 2026-10-12 | 129 | PHASE 129 (2026-10-12): ★ I BROKE THE RECOVERY DOOR WITH MY OWN VERIFICATION - AND THE RULE THAT PREVENTS IT ★ | `mem-entries.md:12860` |
| 2026-10-12 | 130 | PHASE 130 (2026-10-12): THE DEPLOY TOOLCHAIN VERIFIED PRESENT IN THE STOCK ROOTFS | `mem-entries.md:12906` |
| 2026-10-12 | 131 | PHASE 131 (2026-10-12): THE POST-RESET SEQUENCE IS NOW SCRIPTED - NOT IMPROVISED | `mem-entries.md:12933` |
| 2026-10-12 | 132 | PHASE 132 (2026-10-12): THE SHELL-RESTORE STEP VERIFIED AT THE BYTECODE LEVEL | `mem-entries.md:12964` |
| 2026-10-12 | 133 | PHASE 133 (2026-10-12): ★★★★★ TWO LOAD-BEARING FACTS RECOVERED FROM THE HISTORICAL RECORD - BOTH VERIFIED AGAINST OUR BUILD ★★★★★ | `mem-entries.md:13015` |
| 2026-10-12 | 134 | PHASE 134 (2026-10-12): THE INITCALL ORDERING VERIFIED IN THE BINARY - AND A TREE-CONFUSION ERROR CAUGHT | `mem-entries.md:13072` |
| 2026-10-12 | 135 | PHASE 135 (2026-10-12): ★ CHAIN OF CUSTODY CLOSED - THE FIRED ARTIFACT PROVABLY CONTAINS THE VERIFIED KERNEL | `mem-entries.md:13112` |
| 2026-10-12 | 136 | PHASE 136 (2026-10-12): ★★★★★ THE RESET WORKED, THE SHELL IS BACK, AND THE ROOTFS SURVIVED AND MOUNTS ★★★★★ | `mem-entries.md:13144` |
| 2026-10-12 | 137 | PHASE 137 (2026-10-12): FIRE 23 - THE FULL STACK DEPLOYED, AND THE BOARD REVERTED. HONEST OUTCOME. | `mem-entries.md:13213` |
| 2026-10-12 | 138 | PHASE 138 (2026-10-12): THE ACCESS SITUATION AFTER FIRE 23 - EVERY DOOR RE-PROBED | `mem-entries.md:13265` |
| 2026-10-12 | 139 | PHASE 139 (2026-10-12): FIRE 23's REVERT, ANALYSED AS FAR AS THE HOST CAN - THREE BRANCHES, ONE UNBLOCKED | `mem-entries.md:13312` |
| 2026-10-12 | 140 | PHASE 140 (2026-10-12): GOAL BLOCKED - STATED PRECISELY | `mem-entries.md:13362` |
| 2026-10-12 | 141 | PHASE 141 (2026-10-12): THE CREDENTIAL HUNT - WHAT I EXHAUSTED, AND THE ONE PATH THAT NEEDS NOTHING FROM THE USER | `mem-entries.md:13416` |
| 2026-10-12 | 142 | PHASE 142 (2026-10-12): ★★★★★★★★★★ FIRE 23'S VERDICT READ: C18 = 0xC0DE502D - OUR KERNEL RAN ★★★★★★★★★★ | `mem-entries.md:13478` |
| 2026-10-12 | 143 | PHASE 143 (2026-10-12): THE CMDLINE_FORCE VARIANT - BUILT AND VERIFIED AT THE INSTRUCTION LEVEL | `mem-entries.md:13581` |
| 2026-10-12 | 144 | PHASE 144 (2026-10-12): ★★★★★ FIRE 24 - THE CMDLINE_FORCE VARIANT NEVER RAN. A CLEAN NEGATIVE, AND AN IMPORTANT ONE. ★★★★★ | `mem-entries.md:13649` |
| 2026-10-12 | 145 | PHASE 145 (2026-10-12): FIRE 25 (`EXTEND` + `rootwait`) = 0xA5A5A5A5 - AND A CONTRADICTION I MUST NOT SMOOTH OVER | `mem-entries.md:13715` |
| 2026-10-12 | 146 | PHASE 146 (2026-10-12): THE REPRODUCIBILITY GAP, MEASURED - AND A RE-FIRE OF THE EXACT ARTIFACT THAT RAN | `mem-entries.md:13773` |
| 2026-10-12 | 147 | PHASE 147 (2026-10-12): ★★★★★ THE FIRE-23-vs-24/25/26 CONTRADICTION RESOLVED: `bootflag` ★★★★★ | `mem-entries.md:13831` |
| 2026-10-12 | 58 | PHASE 58 (2026-10-12): REPO HYGIENE - THE WORK WAS INVISIBLE, NOW IT IS NOT | `mem-entries.md:13912` |
| 2026-10-12 | 148 | PHASE 148 (2026-10-12): FIRE 27 = OUR KERNEL INTO `kernelb`, THE SLOT `bootcmd` ACTUALLY READS | `mem-entries.md:13969` |
| 2026-10-12 | 59 | PHASE 59 (2026-10-12): HOUSEKEEPING - AND A DEVICE I CANNOT SEE | `mem-entries.md:14019` |
| 2026-10-12 | 150 | PHASE 150 (2026-10-12): THE DARK STATE IS A **HANG, NOT A PANIC** - AND THE CRUMB SURVIVES TO PROVE IT | `mem-entries.md:14090` |
| 2026-10-12 | 151 | PHASE 151 (2026-10-12): THE COMPLETE CRUMB LADDER, WITH SOURCE ATTRIBUTION | `mem-entries.md:14139` |
| 2026-10-12 | 152 | PHASE 152 (2026-10-12): THE FIRE 27 CRUMB READ 0x00000000 - AND THE INSTRUMENT IS BEING CALIBRATED | `mem-entries.md:14186` |
| 2026-10-12 | 60 | PHASE 60 (2026-10-12): THE RECOVERY RESET - AND WHAT IT DID AND DID NOT SETTLE | `mem-entries.md:14243` |
| 2026-10-12 | 153 | PHASE 153 (2026-10-12): THE "MYSTERY WRITER" WAS MY OWN SENTINEL - AND THE INSTRUMENT IS NOW PROPERLY CALIBRATED | `mem-entries.md:14305` |
| 2026-10-12 | 154 | PHASE 154 (2026-10-12): ★★★★★ FIRE 28 - A CLEAN, UNMEDIATED READING: C18 = 0xC0DE502D. OUR KERNEL RAN. ★★★★★ | `mem-entries.md:14359` |
| 2026-10-12 | 155 | PHASE 155 (2026-10-12): ★ THE CRUMB CELL IS A RICHER INSTRUMENT THAN I HAVE BEEN USING - `C1C` IS A BITFIELD | `mem-entries.md:14429` |
| 2026-10-12 | 61 | PHASE 61 (2026-10-12): THE WEB LOGIN - WHAT I TRIED, AND THE ONE FACT I NEED | `mem-entries.md:14485` |
| 2026-10-12 | 62 | PHASE 62 (2026-10-12): THE LOGIN WAS ALREADY SOLVED - I WAS GUESSING PASSWORDS INSTEAD OF READING THEM | `mem-entries.md:14549` |
| 2026-10-12 | 63 | PHASE 63 (2026-10-12): ★★★★★ THE BOOT FAILURE IS FOUND AND FIXED - AND IT WAS MY OWN "COMPILE FIX" ★★★★★ | `mem-entries.md:14601` |
| 2026-10-12 | 64 | PHASE 64 (2026-10-12): THE FIX IS RIGHT, THE FIRES WERE MIS-READ, AND I TOOK THE BOX DOWN | `mem-entries.md:14697` |
| 2026-10-12 | 65 | PHASE 65 (2026-10-12): RECOVERED - AND TWO THINGS ABOUT THE FACTORY-FRESH BOX WORTH KEEPING | `mem-entries.md:14761` |
| 2026-10-12 | 66 | PHASE 66 (2026-10-12): HOST-SIDE COMPARISON - THE +1 MB WAS ONLY THE COMPRESSOR, AND THE FIRES NOW HAVE A COHERENT MODEL | `mem-entries.md:14832` |
| 2026-10-12 | 67 | PHASE 67 (2026-10-12): ★★★★★ THE SLOT SELECTOR IS FOUND BY REVERSING, NOT BY FIRING ★★★★★ | `mem-entries.md:14889` |
| 2026-10-12 | 68 | PHASE 68 (2026-10-12): WEB RESEARCH - WHERE THIS PROJECT SITS, AND WHAT ELSE IS POSSIBLE | `mem-entries.md:14978` |
| 2026-10-12 | 69 | PHASE 69 (2026-10-12): "WHY NOT JUST REVERSE THE BLOB?" - WE DID, AND THE THING WE NEVER DID IS RUN IT | `mem-entries.md:15060` |
| 2026-10-12 | 70 | PHASE 70 (2026-10-12): THE iATU REGION TABLE - AND A CONFESSION | `mem-entries.md:15132` |
| 2026-10-12 | 71 | PHASE 71 (2026-10-12): THE HiSilicon REGISTER MAP VS OURS - IT CONFIRMS US, AND ONE BASE DISAGREES | `mem-entries.md:15191` |
| 2026-10-12 | 72 | PHASE 72 (2026-10-12): A BUILD-HARNESS BUG THAT WAS SILENTLY DISCARDING EVERY mach-luofu EDIT | `mem-entries.md:15255` |
| 2026-10-12 | 73 | PHASE 73 (2026-10-12): THE FALLBACK ARM - FIRES ARE NOW SELF-RECOVERING | `mem-entries.md:15301` |
| 2026-10-12 | 74 | PHASE 74 (2026-10-12): THE FALLBACK ARM IS PROVEN LIVE - NO RESET WAS NEEDED | `mem-entries.md:15357` |
| 2026-10-12 | 75 | PHASE 75 (2026-10-12): CRUMB-FIRST FIRE - NO CRUMB AT ALL, SO NOT EVEN THE HEAD RUNS | `mem-entries.md:15421` |
| 2026-10-12 | 76 | PHASE 76 (2026-10-12): THE FIRE PATH WORKS - AND THE SLOT NEEDS A DTB WE STOPPED BUILDING | `mem-entries.md:15477` |
| 2026-10-12 | 77 | ★★★★★ PHASE 77 (2026-10-12): OUR OWN KERNEL BOOTED OPENWRT - THE ROOTFS MOUNTED AND INIT RAN ★★★★★ | `mem-entries.md:15527` |
| 2026-10-12 | 78 | PHASE 78 (2026-10-12): OPENWRT'S procd RUNS ON OUR KERNEL - AND THE REMAINING GAP IS THE NETWORK | `mem-entries.md:15601` |
| 2026-10-12 | 79 | PHASE 79 (2026-10-12): THE NETWORK IS BLOCKED ON THE CLOCK/RESET PROVIDER, NOT ON THE NIC | `mem-entries.md:15654` |
| 2026-10-12 | 80 | PHASE 80 (2026-10-12): A SCHEDULER OOPS IN userspace, AND AN INSTRUMENT THAT STILL WILL NOT READ | `mem-entries.md:15704` |
| 2026-10-12 | 81 | PHASE 81 (2026-10-12): THE SMP HYPOTHESIS - WELL-FOUNDED, BUT THE INSTRUMENT STILL CANNOT SEE IT | `mem-entries.md:15771` |
| 2026-10-12 | 82 | PHASE 82 (2026-10-12): THE OOPS IS GONE WITH A SINGLE CPU - THE SMP HYPOTHESIS IS CONFIRMED | `mem-entries.md:15837` |
| 2026-10-12 | 83 | PHASE 83 (2026-10-12): THE READOUT WORKS AT LAST - CRG REGISTERED, NO eth0 | `mem-entries.md:15892` |
| 2026-10-12 | 84 | PHASE 84 (2026-10-12): THE NIC FAILURE IS MEASURED - mdio DIES ON devm_clk_get | `mem-entries.md:15946` |
| 2026-10-12 | 85 | PHASE 85 (2026-10-12): TWO BUGS, ONE OF THEM MINE - AND A RESTART PATH THAT STRANDED THE BOARD | `mem-entries.md:15993` |
| 2026-10-12 | 86 | PHASE 86 (2026-10-12): THE CRG NOW PROBES ("hsan,crg") - AND THE REMAINING GAP IS THE CLOCK MODEL | `mem-entries.md:16167` |
| 2026-10-12 | 87 | PHASE 87 (2026-10-12): THE CRG BINDS AND REGISTERS ITS CLOCK TREE - THE GATE WALK IS STILL WRONG | `mem-entries.md:16233` |
| 2026-10-12 | 88 | PHASE 88 (2026-10-12): WHERE THE NIC QUESTION ACTUALLY STANDS - HONEST ACCOUNTING | `mem-entries.md:16299` |
| 2026-10-12 | 89 | PHASE 89 (2026-10-12): THE DEVICE CORRECTS TWO OF MY CONCLUSIONS | `mem-entries.md:16359` |
| 2026-10-12 | 90 | PHASE 90 (2026-10-12): THE 0xC9C INSTRUMENT IS UNSOUND - EVERY READING FROM IT IS VOID | `mem-entries.md:16409` |
| 2026-10-12 | 91 | PHASE 91 (2026-10-12): THE ORDER BUG WAS MINE, THE LOOKUP IS REAL | `mem-entries.md:16463` |
| 2026-10-12 | 92 | PHASE 92 (2026-10-12): THE ACTIVE TREE IS ON DISK - AND THE CLOCK NODES ARE EXACTLY WHERE WE EXPECT | `mem-entries.md:16520` |
| 2026-10-12 | 93 | PHASE 93 (2026-10-12): *** THE CLOCK BUG IS FIXED - THE NICs ARE PAST THE CLOCK GATE *** | `mem-entries.md:16575` |
| 2026-10-12 | 94 | PHASE 94 (2026-10-12): THE RESET MODEL - WHAT THE TREE SAYS, AND WHAT IT DOES NOT | `mem-entries.md:16627` |
| 2026-10-12 | 95 | PHASE 95 (2026-10-12): *** THE NIC PROBE NOW PASSES RESETS AND REACHES phylink_create *** | `mem-entries.md:16662` |
| 2026-10-12 | 96 | PHASE 96 (2026-10-12): WHICH TREE IS ACTIVE - SETTLED. AND THE phylink BUG NEEDS ONE MORE READ | `mem-entries.md:16699` |
| 2026-10-12 | 97 | PHASE 97 (2026-10-12): *** eth0 EXISTS ON OUR KERNEL *** | `mem-entries.md:16742` |
| 2026-10-12 | 98 | PHASE 98 (2026-10-12): CORRECTION - THE LIVE NETDEVS I INSPECTED ARE THE VENDOR'S | `mem-entries.md:16796` |
| 2026-10-12 | 99 | PHASE 99 (2026-10-12): WHAT IS PROVEN, AND WHAT IS NOT | `mem-entries.md:16844` |
| 2026-10-12 | 100 | PHASE 100 (2026-10-12): THE LIVE KERNEL IS THE VENDOR'S - `luofu_pinctrl` IS THE VENDOR'S OWN | `mem-entries.md:16894` |
| 2026-10-12 | 101 | PHASE 101 (2026-10-12): OUR KERNEL BOOTS FULLY - THE REMAINING GAP IS THE PHY LINK | `mem-entries.md:16948` |
| 2026-10-13 | 102 | PHASE 102 (2026-10-13): phy-handle WAS NOT ENOUGH - NEXT TARGET IS THE MDIO READ PATH | `mem-entries.md:16981` |
| 2026-10-13 | 103 | PHASE 103 (2026-10-13): *** ROOT CAUSE FOUND - of_mdiobus_register() FAILS *** | `mem-entries.md:17026` |
| 2026-10-13 | 104 | PHASE 104 (2026-10-13): WHY of_mdiobus_register CAN FAIL - THE SOURCE'S OWN FAILURE MODES | `mem-entries.md:17075` |
| 2026-10-13 | 105 | PHASE 105 (2026-10-13): THE REGISTRATION RETURN CODE IS -EIO (-5), NOT -ENODEV AND NOT -EINVAL | `mem-entries.md:17137` |
| 2026-10-13 | 106 | PHASE 106 (2026-10-13): -EIO IS NOT ON THE C22 PATH - THE NEXT MOVE IS A CRUMB, NOT A READ | `mem-entries.md:17181` |
| 2026-10-13 | 107 | PHASE 107 (2026-10-13): THE OVERLAY FAILURE WAS MY OWN UNFORMATTED UBI VOLUME | `mem-entries.md:17227` |
| 2026-10-14 | 108 | PHASE 108 (2026-10-14): ★★★★★ TWO INDEPENDENT BUGS IN THE RING CHANNEL - IT HAS NEVER ONCE WORKED ★★★★★ | `mem-entries.md:17271` |
| 2026-10-14 | 109 | PHASE 109 (2026-10-14): ★ THE RING IS **UNREACHABLE BY DESIGN** - AND THE PSTORE CHANNEL IS THE RIGHT ONE, ALREADY ENABLED | `mem-entries.md:17340` |
| 2026-10-14 | 110 | PHASE 110 (2026-10-14): NIC VERIFY - CONFIRMED IN THE FIRED BINARY, AND CROSS-CHECKED LIVE | `mem-entries.md:17413` |
| 2026-10-14 | 111 | PHASE 111 (2026-10-14): THE PSTORE CHAIN TRACED - THE WIRING IS HALF DONE, AND THE HALF THAT IS MISSING IS NAMED | `mem-entries.md:17476` |
| 2026-10-14 |  | 2026-10-14 - THE BOOT GUARD FELL: OUR KERNEL EXECUTES ON THIS BOARD | `mem-entries.md:17547` |
| 2026-10-15 |  | 2026-10-15 - THE BOOT-STAGE FRONTIER NARROWED, AND THE INSTRUMENTATION DOCTRINE CORRECTED | `mem-entries.md:17637` |
| 2026-10-15 |  | 2026-10-15 (later) - THE SLOT-SELECTOR BUG, AND A NEGATIVE ON THE FIX | `mem-entries.md:17693` |
| 2026-10-15 |  | 2026-10-15 (final) - THE BOOT PANIC IS IN THE USERSPACE HAND-OFF, AND THE PCIE BRING-UP IS WRITTEN | `mem-entries.md:17744` |
| 2026-10-15 |  | 2026-10-15 (close) - THE FLASH CHANNEL LOCALISED THE DEATH TO A GAP, NOT THE HAND-OFF | `mem-entries.md:17802` |
| 2026-10-15 |  | 2026-10-15 (evening) - SOLVED: THE FMC DATA PATH *IS* THE BOOT PANIC | `mem-entries.md:17847` |
| 2026-10-15 |  | 2026-10-15 (late) - VERIFIED NEGATIVE: the addr_cyc fix was in the image and did not work | `mem-entries.md:17915` |
| 2026-10-15 |  | 2026-10-15 (night) - RESEARCH + PLAN: the SFC is a DOCUMENTED IP FAMILY, and the plan is written | `mem-entries.md:17967` |
| 2026-10-15 |  | 2026-10-15 (late) - THE FIRE HARNESS WAS LYING, AND THAT IS THE SESSION'S REAL RESULT | `mem-entries.md:18005` |
| 2026-10-15 |  | 2026-10-15 (close) - ★ THE BOOT IS INTERMITTENT, AND THAT INVALIDATES EVERY SINGLE-FIRE COMPARISON | `mem-entries.md:18051` |
| 2026-10-16 |  | 2026-10-16 - SESSION HANDOFF: two config-drift fixes, and the UBI question left with a named gap | `mem-entries.md:18105` |
| 2026-10-16 |  | 2026-10-16 (session 2) - THE LOG WINDOW'S TRUE SHAPE, AND FOUR INSTRUMENT DELIVERY FAILURES | `mem-entries.md:18161` |
| 2026-10-14 |  | ★ THE 15 KiB WINDOW IS A CLEAN NEGATIVE (reproducing the 2026-10-14 one, with the scratch excluded) | `mem-entries.md:18203` |
| 2026-10-16 |  | ★★ THE VERDICT, MEASURED 2026-10-16 (fire `tickv`): UBI HAS NO DEVICE, AND THE CHANNEL NOW WORKS | `mem-entries.md:18279` |
| 2026-10-16 |  | ★★★ THE ATTACH ITSELF REFUSES THE PARTITION - MEASURED (fire `attach`, 2026-10-16) | `mem-entries.md:18312` |
| 2026-10-16 |  | PROCESS NOTE (2026-10-16): A `tail -F` MONITOR LEAKS ITS SESSION ON EVERY FIRE | `mem-entries.md:18367` |
| 2026-10-16 |  | ★★★★ THE WALL, MEASURED END TO END (fire `ecwalk`, 2026-10-16) | `mem-entries.md:18395` |
| 2026-10-16 |  | ★★★★ ROOT CAUSE OF THE ROOTFS WALL - OUR READ PATH RETURNS ZEROS (fire `ec2`, 2026-10-16) | `mem-entries.md:18440` |
| 2026-10-17 |  | 2026-10-17 - PICKUP: THE UBI ATTACH NEVER RAN, AND THE BOOT DIES INSIDE `ubi_init` | `mem-entries.md:18492` |
| 2026-10-18 |  | 2026-10-18 .. 2026-10-22 - the log channel, UBI's verdict, and the read-path wall | `mem-entries.md:18600` |
| 2026-11-08 |  | 2026-11-08 - the U-Boot abort key is not the gate; the serial RX path is | `mem-entries.md:18687` |
| 2026-11-08 |  | 2026-11-08 (later) - the UART RX path is dead; network root and full dump | `mem-entries.md:18739` |
| 2026-11-08 |  | 2026-11-08 (later) - CVE-2026-71960 confirmed on the live Mosquitto broker | `mem-entries.md:18780` |
| 2026-11-08 |  | 2026-11-08 (later still) - CVE-2026-71961 proven; UBI read-path source regression | `mem-entries.md:18801` |
| 2026-11-08 |  | 2026-11-08 - local Linux kernel lane rebuilt; the built read-page is the ECC-on shape | `mem-entries.md:18852` |
| 2026-11-08 |  | 2026-11-08 - slot-B fires: the full slice is required, and the kernel now runs to its own breadcrumbs | `mem-entries.md:18904` |
| 2026-11-08 |  | 2026-11-08 - C94 ladder: the kernel reaches the init hand-off and kernel_execve returns | `mem-entries.md:18951` |
| 2026-11-08 |  | 2026-11-08 - CORRECTION and milestone: kernel_execve returns 0, userspace starts | `mem-entries.md:18989` |
| 2026-11-08 |  | 2026-11-08 - the watchdog wall is broken; the box now survives to ~98 s, and the wall moves to userspace | `mem-entries.md:19010` |
| 2026-11-08 |  | 2026-11-08 - RECOVERY: the RESET-hold TFTP door restored the box | `mem-entries.md:19042` |
| 2026-11-08 |  | 2026-11-08 - recovery complete: root SSH restored, slot A, and the write path reverted | `mem-entries.md:19059` |
| 2026-11-08 |  | 2026-11-08 - WRITE PATH PROVEN: the post-kick wait_ready was the wall | `mem-entries.md:19077` |
| 2026-11-08 |  | 2026-11-08 - OVERLAY WALL BROKEN: mtd15 is a mounted jffs2 overlay; boot-time note | `mem-entries.md:19095` |
| 2026-11-08 |  | 2026-11-08 (late) - OVERLAY FIRE 1: slice re-flashed onto a formatted rootfs_data | `mem-entries.md:19116` |
| 2026-11-08 |  | 2026-11-08 (late) - OVERLAY FIRE 1 RESULT: +481 s, vendor A again, died in prepare_namespace | `mem-entries.md:19129` |
| 2026-11-08 |  | 2026-11-08 (late) - NO-TEST FIRE RESULT: the head.S site reader was the early-death cause | `mem-entries.md:19154` |
| 2026-11-09 |  | 2026-11-09 - SITE-READER FIRE RESULT: KERNEL REACHES USERSPACE (C94=0xC0DE9B00) | `mem-entries.md:19170` |
| 2026-11-09 |  | 2026-11-09 - INITRAMFS PROOF: /init ran; the jffs2 mount hung ~430 s in the FMC read path | `mem-entries.md:19187` |
| 2026-11-09 |  | 2026-11-09 - READ-PROBE RESULT: last read is in rootfsb; init path still ambiguous | `mem-entries.md:19204` |
| 2026-11-09 |  | 2026-11-09 - INIT-RUN PROBE: neither START nor POST; /init usage still unproven | `mem-entries.md:19221` |
| 2026-11-09 |  | 2026-11-09 - INIT-REBOOT TEST: no fast return; 470 s fallback repeats | `mem-entries.md:19233` |
| 2026-11-09 |  | 2026-11-09 - INIT-VISIBILITY RESULT: C18=0xC0DE5245, the wrong fold prefix | `mem-entries.md:19248` |
| 2026-11-09 |  | 2026-11-09 - INIT-BRANCH RESULT: C18=0xC0DE5207 - the /init CHECK PASSES | `mem-entries.md:19259` |
| 2026-11-09 |  | 2026-11-09 - EXEC PROOF RESULT: C18=0xC0DE4B00 - the /init EXEC LANDS | `mem-entries.md:19275` |
| 2026-11-09 |  | 2026-11-09 - MOUNT MARKER RESULT: C18=0xC0DE5207, no LUFU marker - the mount restarts the box | `mem-entries.md:19291` |
| 2026-11-09 |  | 2026-11-09 - MTDCHAR READ PROBE: C18=0xC0DE5207, no marker, no mtd15 FMC row | `mem-entries.md:19306` |
| 2026-11-09 |  | 2026-11-09 - RAW INIT RESULT: mtdchar read WORKS; C98 row 0x9900, sequence +1 | `mem-entries.md:19321` |
| 2026-11-09 |  | 2026-11-09 - MTDBLOCK READ WORKS: C98 row 0x9907, sequence +32 | `mem-entries.md:19337` |
| 2026-11-09 |  | 2026-11-09 - JFFS2 RO MOUNT: no mtd15 reads; C98 stays at the UBI rows | `mem-entries.md:19351` |
| 2026-11-09 |  | 2026-11-09 - JFFS2 BLOCK MOUNT INSIGHT: vanilla jffs2 wants an MTD source | `mem-entries.md:19362` |
| 2026-11-09 |  | 2026-11-09 - MTD-SOURCE JFFS2 MOUNT: still no mtd15 read | `mem-entries.md:19374` |
| 2026-11-09 |  | 2026-11-09 - JFFS2 CRUMB2: C98=0x9A000003 - the scan is entered, its first read never happens | `mem-entries.md:19385` |
| 2026-11-09 |  | 2026-11-09 - SCAN DEPTH: C98=0x9A000006 - stalls at the eraseblock entry, before the data read | `mem-entries.md:19397` |
| 2026-11-09 |  | 2026-11-09 - READ BOUNDARY: C98=0x9A000006 - the cleanmarker OOB path is the wall | `mem-entries.md:19409` |
| 2026-11-09 |  | 2026-11-09 - NO-OOB FIX DID NOT CHANGE THE STALL; C98 still 0x9A000006 | `mem-entries.md:19426` |
| 2026-11-09 |  | 2026-11-09 - OOBAVAIL /dev/mem CHANNEL FAILED; C98 stayed at the UBI rows | `mem-entries.md:19438` |
| 2026-11-09 |  | 2026-11-09 - MTDCHAR PAGE PROOF FAILED; mmap is the next cell channel | `mem-entries.md:19448` |
| 2026-11-09 |  | 2026-11-09 - MMAP CELL CHANNEL ALSO FAILED; force the in-band cleanmarker instead | `mem-entries.md:19459` |
| 2026-11-09 |  | 2026-11-09 - IN-BAND FIX WORKS: jffs2 scan now READS mtd15 (C98 row 0xA1C0, +36 reads) | `mem-entries.md:19472` |
| 2026-11-09 |  | 2026-11-09 - PSTORED KERNEL LOG: the "mtd15" mount scanned a 34-block WRONG partition | `mem-entries.md:19485` |
| 2026-11-09 |  | 2026-11-09 - CORRECTION: pstore logs are the VENDOR's; rootfs_data is all FF (empty) | `mem-entries.md:19502` |
| 2026-11-09 |  | 2026-11-09 - SEEDED JFFS2 LANDED; mount scan still stalls at page 0xA0FE | `mem-entries.md:19523` |
| 2026-11-09 |  | 2026-11-09 - CRUMB 0x9D039904: the read returned; the hang is jffs2 node processing | `mem-entries.md:19540` |
| 2026-11-09 |  | 2026-11-09 - SCAN CASE CRUMB 0x9A1311F0: dirent processed at 0x11F0, hang after it in the scan loop | `mem-entries.md:19553` |
| 2026-11-09 |  | 2026-11-09 - LOOP CRUMB 0x9A14121C: hang in the scan body at 0x121C; the flash there is FF, so it was STALE VENDOR NODES | `mem-entries.md:19568` |
| 2026-11-10 |  | 2026-11-10 - CLEAN SCAN 0x9A145BA4: seed stays, scan reaches the FF region, hangs in the scan body | `mem-entries.md:19583` |
| 2026-11-10 |  | 2026-11-10 - 0x9A18121C: prealloc returns; hang is in the post-prealloc segment of the scan body | `mem-entries.md:19596` |
| 2026-11-10 |  | 2026-11-10 - 0x9A1B0000: magic word is NOT FF; hang in the switch's cleanmarker/unknown path | `mem-entries.md:19614` |
| 2026-11-10 |  | 2026-11-10 - 0x9A1F121C: default/unknown node case - our jffs2 lacks XATTR, the vendor's has it | `mem-entries.md:19631` |
| 2026-11-10 |  | 2026-11-10 - XATTR FIX WORKS: scan passes unknown-node wall, reads 1,657 pages, reaches 0xA35F | `mem-entries.md:19649` |
| 2026-11-10 |  | 2026-11-10 - 0x9D039900: read exit at block 0 page 0, hang in the POST-READ caller path | `mem-entries.md:19660` |
| 2026-11-10 |  | 2026-11-10 - 0x9E030044: mtd_read RETURNS 68 bytes; hang is inside jffs2_scan_inode_node | `mem-entries.md:19673` |
| 2026-11-10 |  | 2026-11-10 - 8,612 reads: scan ~79% through; stop right after a 68-byte inode-header read | `mem-entries.md:19690` |
| 2026-11-10 |  | 2026-11-10 - 1,638 vs 8,612 reads across boots at a constant 705 s: the scan is SLOW and the watchdog kills it | `mem-entries.md:19700` |
| 2026-11-10 |  | 2026-11-10 - 705 s is the PET's stop, not the scan: 360 beats consumed by ~627 s (~1.74 s/beat) | `mem-entries.md:19714` |
| 2026-11-10 |  | 2026-11-10 - The pet bound is really 600 in the image, yet the reset stays at ~704 s | `mem-entries.md:19725` |
| 2026-11-10 |  | 2026-11-10 - C8C is the VENDOR's cell (0x80004000 after its boot); move the pet counter to C94 | `mem-entries.md:19737` |
| 2026-11-10 |  | 2026-11-10 - C94 readback was the ladder value 0xC0DE9B00: pet-cell probe inconclusive | `mem-entries.md:19745` |
| 2026-11-10 |  | 2026-11-10 - Read speed lever: switch completion from INT_STATUS bit 0 to the vendor's OP_CTRL clear | `mem-entries.md:19762` |
| 2026-11-11 |  | 2026-11-11 - MOUNT SUCCESS: the seeded jffs2 mounts on our kernel (C94=0xC0DE9B00) | `mem-entries.md:19773` |
| 2026-11-11 |  | 2026-11-11 - SQUASHFS LOWER MOUNTS TOO: C94=0xC0DE9B00 (both layers mount) | `mem-entries.md:19786` |
| 2026-11-10 |  | 2026-11-10 - C94 verdict is overwritten by our own exec ladder; the ladder must publish it | `mem-entries.md:19798` |
| 2026-11-10 |  | 2026-11-10 - STEP 0 VERIFIED: C94=0xC0DE9D00, the mount test's verdict survives the vendor boot | `mem-entries.md:19818` |
| 2026-11-10 |  | 2026-11-10 - STEP 1 PARTIAL: C94=0xC0DE9D05, jffs2 and overlay mount; squashfs source was wrong | `mem-entries.md:19842` |
| 2026-11-10 |  | 2026-11-10 - STEP 1b: C94=0xC0DE9D01, devtmpfs mounted but squashfs and overlay still failed | `mem-entries.md:19861` |
| 2026-11-10 |  | 2026-11-10 - STEP 1c: C94=0x9D160005 - overlays fixed, squashfs source is a UBI container | `mem-entries.md:19880` |
| 2026-11-10 |  | 2026-11-10 - STEP 1d: C94=0x9D13000D - ubiblock0_0 was not registered | `mem-entries.md:19901` |
| 2026-11-10 |  | 2026-11-10 - STEP 1e: C94=0x9D13000D - no ubi0, so the cmdline attach never produced a device | `mem-entries.md:19917` |
| 2026-11-10 |  | 2026-11-10 - STEP 1f: C94=0x9D16000D - the UBI attach itself returns -EINVAL | `mem-entries.md:19934` |
| 2026-11-10 |  | 2026-11-10 - PHASE A DIAGNOSTIC: C94=0x9D16006D - headers read clean, vtbl record 118 does not | `mem-entries.md:19956` |
| 2026-11-10 |  | 2026-11-10 - PHASE A BREAKTHROUGH: ECC on fixes record 118 and the UBI attach; the ubiblock node had a dev_t bug | `mem-entries.md:19976` |
| 2026-11-10 |  | 2026-11-10 - PHASE A CLOSED: C94=0xC0DE9D07 - the full overlay assembly mounts on hardware | `mem-entries.md:19994` |
| 2026-11-10 |  | 2026-11-10 - PHASE B FIRST FIRE: C94=0xC0DE9D07 - the overlay write did not reach flash | `mem-entries.md:20016` |
| 2026-11-10 |  | 2026-11-10 - PHASE B: C94=0x9E001E07 - the overlay create returns -EROFS | `mem-entries.md:20030` |
| 2026-11-10 |  | 2026-11-10 - PHASE B DIAGNOSTIC: C94=0x9E001E27 - jffs2 rw, overlay sb ro, MTD hook test failed | `mem-entries.md:20050` |
| 2026-11-10 |  | 2026-11-10 - PHASE B DIAGNOSTIC 2: C94=0x9E401E27 - the MTD erase returned 0 but did not erase block 1 | `mem-entries.md:20067` |
| 2026-11-10 |  | 2026-11-10 - PHASE B DIAGNOSTIC 3: C94=0x9E401E27 on block 2 too - the MTD erase hook no-ops | `mem-entries.md:20085` |
| 2026-11-10 |  | 2026-11-10 - PHASE B COMPARISON 1: 0x8E4040 - both raw and MTD fail on upgrade block 2 | `mem-entries.md:20104` |
| 2026-11-10 |  | 2026-11-10 - PHASE B COMPARISON 2: 0x8E4040 on rootfs_data block 7 too | `mem-entries.md:20118` |
| 2026-11-10 |  | 2026-11-10 - PHASE B COMPARISON 3: 0x8E4040 on block 0 too - the read races the program | `mem-entries.md:20132` |
| 2026-11-10 |  | 2026-11-10 - PHASE B COMPARISON 4: 0x8E4040 persists with a 20 ms settle | `mem-entries.md:20148` |
| 2026-11-10 |  | 2026-11-10 - PHASE B COMPARISON 5: 0x8E400000 - zeros, and the write path never set ECC | `mem-entries.md:20160` |
| 2026-11-10 |  | 2026-11-10 - PHASE B COMPARISON 6: ECC was not it - the program operands are invalid | `mem-entries.md:20177` |
| 2026-11-10 |  | 2026-11-10 - PHASE B COMPARISON 7: the operands were dead code - the write hardcodes 0x9A0 | `mem-entries.md:20193` |
| 2026-11-10 |  | 2026-11-10 - PHASE B VERDICT: the vendor itself reads the page as all-0xff | `mem-entries.md:20206` |
| 2026-11-10 |  | 2026-11-10 - PHASE B COMPARISON 8: the execute did not land - back to the proven shape | `mem-entries.md:20220` |
| 2026-11-10 |  | 2026-11-10 - PHASE B COMPARISON 9: the proven shape still misses on rootfs_data page 0 | `mem-entries.md:20236` |
| 2026-11-10 |  | 2026-11-10 - PHASE B BREAKTHROUGH: the write lands on the upgrade page 163 | `mem-entries.md:20250` |
| 2026-11-10 |  | 2026-11-10 - PHASE B COMPARISON 10: the global unlock changed nothing; test a third block | `mem-entries.md:20269` |
| 2026-11-10 |  | 2026-11-10 - PHASE B COMPARISON 11: 0x8E005A5A is a read-path false positive | `mem-entries.md:20282` |
| 2026-11-10 |  | 2026-11-10 - PHASE B ROOT CAUSE: the probe SETS the FMC write-protect the vendor clears | `mem-entries.md:20297` |
| 2026-11-10 |  | 2026-11-10 - PHASE B AFTER THE WP FIX: 0x9D0000E3 is the OVERLAY MOUNT failing | `mem-entries.md:20317` |
| 2026-11-10 |  | 2026-11-10 - PHASE B: j3 = EINVAL (22); the test never created the overlay dirs | `mem-entries.md:20329` |
| 2026-11-10 |  | 2026-11-10 - PHASE B: THE OVERLAY MOUNT IS UP - the write test is the only failure left | `mem-entries.md:20342` |
| 2026-11-10 |  | 2026-11-10 - PHASE B: wr = EROFS (30) - the overlayfs INDEX feature forces the read-only sb | `mem-entries.md:20353` |
| 2026-11-10 |  | 2026-11-10 - PHASE B: index=off did not help - name the read-only superblock | `mem-entries.md:20374` |
| 2026-11-10 |  | 2026-11-10 - PHASE B: jffs2 is RW, overlay is forced RO by overlayfs itself | `mem-entries.md:20386` |
| 2026-11-11 |  | 2026-11-11 - PHASE B: the workdir pointer is NULL; overlayfs, not the index, forces RO | `mem-entries.md:20399` |
| 2026-11-11 |  | 2026-11-11 - PHASE B: the work mkdir is EEXIST; a stale /overlay/work/work is cleaned and refused | `mem-entries.md:20408` |
| 2026-11-11 |  | 2026-11-11 - PHASE B: upper is EEXIST and wk2 is ENOSPC; rootfs_data was 1 MiB | `mem-entries.md:20420` |
| 2026-11-11 |  | 2026-11-11 - PHASE B: highest_ino is not the EINVAL; the seed is clean but the write path is not | `mem-entries.md:20432` |
| 2026-11-11 |  | 2026-11-11 - PHASE B: the kernel sees 8 MiB; the EINVAL survives the clean seed | `mem-entries.md:20445` |
| 2026-11-12 |  | 2026-11-12 - PHASE B ROOT CAUSE: 5.10 never gives jffs2 a write buffer on this MTD | `mem-entries.md:20452` |
| 2026-11-12 |  | 2026-11-12 - PHASE B: C94 cannot carry a cross-boot latch; the persistence fire uses a build switch | `mem-entries.md:20479` |
| 2026-11-12 |  | 2026-11-12 - PHASE B: the write buffer works; the ERASE MARKER is refused and every block goes bad | `mem-entries.md:20496` |
| 2026-11-12 |  | 2026-11-12 - PHASE C DESIGN: run the VENDOR init on our kernel, from the vendor squashfs root | `mem-entries.md:20520` |
| 2026-11-12 |  | 2026-11-12 - PHASE D PREP: the ethernet driver is back in the tree and links built-in | `mem-entries.md:20546` |
| 2026-11-12 | 3o | 2026-11-12 - PHASE B: phase3o hung inside the mount test; the erase path now needs a crumb ladder | `mem-entries.md:20564` |
| 2026-11-12 |  | 2026-11-12 - PHASE B: the marker belongs in the DRIVER, not in jffs2's write buffer | `mem-entries.md:20597` |
| 2026-11-12 |  | 2026-11-12 - PHASE B WRITE-THROUGH IS GREEN: 0xC0DE9D0F and the file is in the jffs2 upper | `mem-entries.md:20621` |
| 2026-11-12 |  | 2026-11-12 - PHASE B PERSISTENCE: the file survives a reboot; the seed-off boot stalls before its verdict | `mem-entries.md:20649` |
| 2026-11-12 |  | 2026-11-12 - PHASE B IS CLOSED: both write-path fixes are green, and the file persists | `mem-entries.md:20671` |
| 2026-11-12 | 3w | 2026-11-12 - PHASE C FIRE (phase3w) AND THE INJURY: the vendor came back with DNS only | `mem-entries.md:20688` |
| 2026-11-12 |  | 2026-11-12 - PHASE C REWORK: the lab overlay moves off the vendor's config partition | `mem-entries.md:20713` |
| 2026-11-12 |  | 2026-11-12 - RECOVERY: the box came back with the first-run wizard, and the web session restored SSH | `mem-entries.md:20734` |
| 2026-11-12 | 3x | 2026-11-12 - Phase C on the vendor init: `phase3x` returned the box on the vendor kernel, and the partition table explains why | `mem-entries.md:20761` |
| 2026-11-12 |  | 2026-11-12 - WHY NO CELL FROM THE INIT: /dev/mem write() returns EFAULT, mmap is the only working door | `mem-entries.md:20786` |
| 2026-11-12 |  | 2026-11-12 - Phase C instrumented: the init RUNS; mounts were never the problem, the pivot is | `mem-entries.md:20809` |
| 2026-11-12 | 3ai | 2026-11-12 - phase3ai: the init's first real stage word, and a second factory reset | `mem-entries.md:20828` |
| 2026-11-12 | 3ak | 2026-11-12 - phase3ak: the vendor fs mounts (mtd:rootfs_data), but its FIRST WRITE never returns | `mem-entries.md:20852` |
| 2026-11-12 | 3al | 2026-11-12 - phase3al: the stall is BEFORE the /dev move, and a shadow-free run leaves the config intact | `mem-entries.md:20875` |
| 2026-11-12 | 3am | 2026-11-12 19:39 - phase3am and the state of the vendor-init path at the end of this session | `mem-entries.md:20900` |
| 2026-11-12 |  | 2026-11-12 20:31 - The stall is ABOVE the driver: no page program and no erase were ever attempted | `mem-entries.md:20923` |
| 2026-11-12 |  | 2026-11-12 21:01 - PHASE C CLOSED: the vendor's own procd reached the end of boot on our kernel | `mem-entries.md:20944` |
| 2026-11-13 |  | 2026-11-13 05:37 - CORRECTION: the Phase C "closure" evidence is ambiguous, and the fix is a kernel-version check | `mem-entries.md:20967` |
| 2026-11-13 | 3ar | 2026-11-13 06:33 - phase3ar: the vendor's preinit never reaches its own boot scripts on our kernel | `mem-entries.md:20992` |
| 2026-11-13 |  | 2026-11-13 07:06 - PHASE C CONFIRMED WITH KERNEL-VERSION EVIDENCE, and Phase D's exact failure in hand | `mem-entries.md:21009` |
| 2026-11-13 | 3au | 2026-11-13 07:38 - phase3au (#164): the vendor boot scripts ran on our kernel again, but the box reset after done and the marker's writes never flushed | `mem-entries.md:21047` |
| 2026-11-13 | 3av | 2026-11-13 08:08 - phase3av (#165): vendor userspace ran on our kernel again, and the tolerant-clock patch is what kills the box after done | `mem-entries.md:21074` |
| 2026-11-13 |  | 2026-11-13 08:37 - The luofu-crg driver is written; #166 runs the vendor userspace to S95done and dies ~6 s later | `mem-entries.md:21098` |
| 2026-11-13 |  | 2026-11-13 09:30 - Bisect result: neither the MACs nor the MDIO bus cause the post-done reset; the log ring is scrubbed | `mem-entries.md:21133` |
| 2026-11-13 |  | 2026-11-13 10:20 - The panic capture wrote nothing; the crash leaves no pstore record | `mem-entries.md:21159` |
| 2026-11-13 |  | 2026-11-13 12:00 - pstore IS registered, the crash is not a stored panic, and #168 dies 4 s into the vendor's rc.d | `mem-entries.md:21183` |
| 2026-11-13 |  | 2026-11-13 12:18 - The reset is BELOW the kernel: the panic notifier never ran | `mem-entries.md:21213` |
| 2026-11-13 |  | 2026-11-13 14:02 - #170: the disarm did not save it; the vendor's own driver names the watchdog | `mem-entries.md:21239` |
| 2026-11-13 |  | 2026-11-13 14:05 - #171: the real watchdog driver did not stop the reset either | `mem-entries.md:21269` |
| 2026-11-13 |  | 2026-11-13 14:09 - #172: pet shim plus real driver extends the lifetime to ~90 s | `mem-entries.md:21288` |
| 2026-11-13 | 3bf | 2026-11-13 14:36 - A userspace keeper in the init (phase3bf) | `mem-entries.md:21300` |
| 2026-11-13 |  | 2026-11-13 15:05 - #174: the shadow reaches S95done and the dump is real | `mem-entries.md:21312` |
| 2026-11-13 |  | 2026-11-13 16:00 - The dump names all three causes; the vermagic is the lever | `mem-entries.md:21332` |
| 2026-11-13 |  | 2026-11-13 16:29 - #177: vermagic fixed, watchdog registered, and a new module wall (PLT) | `mem-entries.md:21362` |
| 2026-11-13 |  | 2026-11-13 16:57 - #178 never booted: CONFIG_EMBEDDED was collateral damage | `mem-entries.md:21382` |
| 2026-11-13 |  | 2026-11-13 17:25 - #179: ARM_MODULE_PLTS=n does not boot either | `mem-entries.md:21395` |
| 2026-11-13 |  | 2026-11-13 18:01 - The wireless route is our own lab line, and it builds | `mem-entries.md:21410` |
| 2026-11-13 |  | 2026-11-13 19:22 - C80 is a live register: writing 0xc0de60xx there hangs the boot | `mem-entries.md:21429` |
| 2026-11-13 |  | 2026-11-13 21:41 - Criterion 1 PASS: the MAC probe stops at the resets (c0de6f04, -EINVAL) | `mem-entries.md:21445` |
| 2026-11-13 |  | 2026-11-13 21:14 - The stale DTB: why no MAC ever probed | `mem-entries.md:21467` |
| 2026-11-13 |  | 2026-11-13 22:13 - The keeper race: a failed open left the armed watchdog unfed | `mem-entries.md:21476` |
| 2026-11-13 |  | 2026-11-13 23:37 - The MDIO controller never completes a read (named blocker) | `mem-entries.md:21488` |
| 2026-11-14 |  | 2026-11-14 00:06 - The MDIO clock is obtained and the transfers still time out; the gate index is next | `mem-entries.md:21512` |
| 2026-11-14 | 3cb | 2026-11-14 00:09 - phase3cb died early again; the gate-rate evidence needs a surviving run | `mem-entries.md:21540` |
| 2026-11-14 |  | 2026-11-14 00:39 - MDIO: the clock is 100 MHz, our writes land, the controller never starts | `mem-entries.md:21558` |
| 2026-11-14 |  | 2026-11-14 00:40 - The vendor MDIO read, disassembled: our poll polarity was inverted | `mem-entries.md:21581` |
| 2026-11-14 |  | 2026-11-14 01:08 - The handshake order was necessary but not sufficient; the frame word is next | `mem-entries.md:21606` |
| 2026-11-14 |  | 2026-11-14 01:56 - The vendor frame decoded: 0x8000 \| (reg << 8) \| phy | `mem-entries.md:21632` |
| 2026-11-14 |  | 2026-11-14 02:23 - The frame fix did not help, and 0xff92 is the timeout code, not data | `mem-entries.md:21649` |
| 2026-11-14 |  | 2026-11-14 02:56 - The two frame words differ: the second is the command phase | `mem-entries.md:21667` |
| 2026-11-14 |  | 2026-11-14 03:23 - Two-phase frames still time out; the vendor passes a FLAGS-encoded command | `mem-entries.md:21681` |
| 2026-11-14 |  | 2026-11-14 03:57 - The register map came from a DEAD code path; the real one is 0x20/0x2c/0x30/0x38 | `mem-entries.md:21702` |
| 2026-11-14 |  | 2026-11-14 04:24 - All four MDIO hypotheses tested; the remaining suspect is the switch in front of it | `mem-entries.md:21725` |
| 2026-11-14 |  | 2026-11-14 04:25 - The vendor's own 0x14000000 region reads as instruction words | `mem-entries.md:21749` |
| 2026-11-14 |  | 2026-11-14 05:57 - Both remaining routes scoped: bit-bang closed, the switch port is the only path | `mem-entries.md:21772` |
| 2026-11-14 |  | 2026-11-14 12:22 - Why the vendor's modules could not load: our kernel placed them FAR | `mem-entries.md:21788` |
| 2026-11-14 |  | 2026-11-14 13:44 - Near-only allocation did not stop the PLT errors, and its print never appeared | `mem-entries.md:21804` |
| 2026-11-14 |  | 2026-11-14 14:27 - The module loader refused every module that had no .plt, before checking whether one was needed | `mem-entries.md:21833` |
| 2026-11-14 |  | 2026-11-14 15:50 - A/B: the PLT-tolerance change breaks the boot; the control boots | `mem-entries.md:21855` |
| 2026-11-14 |  | 2026-11-14 16:31 - Bisect step 1 also fails: the loader edit is not the mechanism, the kernel's layout is | `mem-entries.md:21877` |
| 2026-11-14 |  | 2026-11-14 17:03 - Layout control boots: image size is not the hazard; the frob edit is implicated | `mem-entries.md:21902` |
| 2026-11-14 |  | 2026-11-14 17:30 - The frob-only slice fails again (4/4 with the edit, 3/3 without) | `mem-entries.md:21924` |
| 2026-11-14 |  | 2026-11-14 17:35 - The symbol maps are IDENTICAL between a booting and a failing build | `mem-entries.md:21946` |
| 2026-11-14 |  | 2026-11-14 18:17 - Console-free probe: the init stamps the crash partition before anything else | `mem-entries.md:21964` |
| 2026-11-14 |  | 2026-11-14 20:11 - Three observation channels tried; none can see a failing boot on this bench | `mem-entries.md:21982` |
| 2026-11-14 |  | 2026-11-14 20:17 - The other way: patch the modules, not the kernel | `mem-entries.md:22006` |
| 2026-11-14 |  | 2026-11-14 20:44 - The module patch works: hi_swa loads past the PLT gate | `mem-entries.md:22023` |
| 2026-11-14 |  | 2026-11-14 20:48 - The init loads the vendor stack in the vendor's own order | `mem-entries.md:22047` |
| 2026-11-14 |  | 2026-11-14 22:13 - EINVAL explained: the ARM finit_module number is 379, not 350 | `mem-entries.md:22067` |
| 2026-11-14 |  | 2026-11-14 22:41 - MILESTONE: the vendor stack runs on our kernel, network live on both paths | `mem-entries.md:22088` |
| 2026-11-14 |  | 2026-11-14 23:5x - The MDIO controller protocol, decoded from the live driver | `mem-entries.md:22123` |
| 2026-11-14 |  | 2026-11-14 23:15 - M2 core proven: our MDIO and GEMAC carry a real 1Gbps link | `mem-entries.md:22168` |
| 2026-11-15 |  | 2026-11-15 01:30 - The no-op shadow was a mistake: hi_kpinctrl is load-bearing | `mem-entries.md:22196` |
| 2026-11-15 |  | 2026-11-15 03:30 - The broker-staged fire works; the shadow writes do not land | `mem-entries.md:22223` |
| 2026-11-15 |  | 2026-11-15 04:10 - The init's /vendor mount is read-only on this strap | `mem-entries.md:22251` |
| 2026-11-15 |  | 2026-11-15 13:07 - 3de broker fire, attempt 1: the host firewall blocked the slice download | `mem-entries.md:22275` |
| 2026-11-15 |  | 2026-11-15 13:33 - 3de broker fire: the image boots, the shadow writes are still silent | `mem-entries.md:22284` |
| 2026-11-15 |  | 2026-11-15 14:36 - 3df fire: no captured readout, the shadow writes are undecided | `mem-entries.md:22308` |
| 2026-11-15 |  | 2026-11-15 14:39 - 3df broker fire ended at SIZE_FAIL: the box never ran 3df | `mem-entries.md:22361` |
| 2026-11-15 |  | 2026-11-15 16:05 - 3df broker fire 4: the instrument shipped, the box booted stock | `mem-entries.md:22396` |
| 2026-11-15 |  | 2026-11-15 16:20 - The box went silent after the first handover reboot; recovery needs a physical power cycle | `mem-entries.md:22439` |
| 2026-11-15 |  | 2026-11-15 18:30 - Bench recovered by TFTP; the calibration snapshot is real now, and 3df stays unmeasured | `mem-entries.md:22477` |
| 2026-11-15 |  | 2026-11-15 18:45 - 3df debugged off the box: the wfile channel works, and it is the kmsg line nobody read | `mem-entries.md:22506` |
| 2026-11-15 |  | 2026-11-15 19:05 - Emulation closes the init-side question: the shadow writes work when /vendor mounts | `mem-entries.md:22545` |
| 2026-11-15 |  | 2026-11-15 19:20 - Emulation closes the init-side question: it is correct, only the mount can fail | `mem-entries.md:22584` |
| 2026-11-16 |  | 2026-11-16 00:00 - 3df fire 6: the slice is written and the handover is set, but the reboot never ran | `mem-entries.md:22619` |
| 2026-11-16 |  | 2026-11-16 05:40 - 3df is GREEN on hardware: the shadow writes land; the blocker was never the mount | `mem-entries.md:22647` |
| 2026-11-16 |  | 2026-11-16 15:45 - Picked up the PLT thread: STATUS is stale, the stack loads, and the init now reports every load on the console | `mem-entries.md:22687` |
| 2026-11-16 |  | 2026-11-16 17:35 - The bench lost its only write path: the vendor loader cannot boot our slot A and cannot be prompted | `mem-entries.md:22729` |
| 2026-11-16 |  | 2026-11-16 18:25 - 3dk fired and read: the fire wrote a slot U-Boot does not boot for us, so the slice was never run | `mem-entries.md:22767` |
| 2026-11-16 |  | 2026-11-16 19:05 - Vendor stock restored; the recovery trigger was the RESET counter, and NetworkManager was stripping the host address | `mem-entries.md:22799` |
| 2026-11-17 |  | 2026-11-17 00:20 - Harness audit: bench re-verified, physical invariants encoded, fire lane gated, publish/upstream gaps recorded | `mem-entries.md:22835` |
| 2026-11-17 |  | 2026-11-17 00:30 - NetworkManager reclaimed the bench adapter mid-audit; the unmanage is now persistent | `mem-entries.md:22911` |
| 2026-11-17 |  | 2026-11-17 08:05 - THE 3dh-CLASS KERNEL NEVER BOOTED: the blocker is a kernel-config regression, not the slot; 3df/3dg were the last running kernels | `mem-entries.md:22925` |
| 2026-11-17 |  | 2026-11-17 08:45 - ROOT CAUSE FOUND AND FIXED: the 3dh kernel died in luofu_early's ioremap; 3dn boots to userspace, then wedges in a new userspace-stage problem | `mem-entries.md:22981` |
| 2026-11-17 |  | 2026-11-17 10:15 - 3dq: our kernel boots the vendor stack far enough to bring eth2 up at 1 Gbps; module dependency ordering is the next fix | `mem-entries.md:23031` |
| 2026-11-17 |  | 2026-11-17 17:45 - v6/v7/v8: EVERY vendor module now loads and eth2 comes up on our kernel; the LAN blocker moved to HSLINK rootif (vendor gmac driver mismatch) | `mem-entries.md:23077` |
| 2026-11-17 |  | 2026-11-17 18:00 - v9/v10: vendor MAC lane (hsan,himac + port) still ends in a userspace-stage hang at ~33 s; the blocker is the vendor HSLINK/wifi userspace interface, not symbol loading | `mem-entries.md:23114` |
| 2026-11-17 |  | 2026-11-17 18:55 - v13: WEXT net_device ABI fix, non-persistent init masks, and the U-Boot bootfip data-abort that blocks the vendor-DT lane | `mem-entries.md:23142` |
| 2026-11-17 |  | 2026-11-17 20:15 - v14-v16: bridge stack enabled, rootif bypassed, hyfi_bridging loads; crash moved into hyfi_netlink_receive (vendor bridge hooks need real implementations) | `mem-entries.md:23179` |
| 2026-11-17 |  | 2026-11-17 20:40 - RE verdict: hyfi_bridging crash is a vendor sk_buff ABI mismatch, not the bridge hooks; v17 drops hyfi preload and fixes the hook variable ABI | `mem-entries.md:23217` |
| 2026-11-18 |  | 2026-11-18 06:50 - v17 fire: no crash with hyfi removed, but br-lan is created/destroyed in HSLINK cycles and userspace goes silent; bench network needs the multi-step vendor bridge port | `mem-entries.md:23245` |
| 2026-11-18 |  | 2026-11-18 07:45 - Upstream design layer delivered: concrete OpenWrt target/DTS/image design, GPL follow-up pack, vendor sk_buff/bridge port spec | `mem-entries.md:23268` |
| 2026-11-18 |  | 2026-11-18 07:55 - First upstream artifact: schematic OpenWrt target skeleton delivered (untested) with a fail-closed FIP tool | `mem-entries.md:23327` |
| 2026-11-18 |  | 2026-11-18 08:35 - FIP trailer decoded + generator implemented (byte-exact vs both vendor containers); target skeleton's structure accepted by OpenWrt main (defconfig + kernel prepare) | `mem-entries.md:23368` |
| 2026-11-18 |  | 2026-11-18 08:55 - Kernel platform patch series + canonical 6.18 config delivered; machine code compiles with OpenWrt GCC 14.4; sole kernel blocker = TEXT_OFFSET non-immediate | `mem-entries.md:23422` |
| 2026-11-18 |  | 2026-11-18 09:15 - TEXT_OFFSET early-boot fix (patch 003): full 6.18 kernel compile RC=0 with the real, non-encodable offset; load address verified 0x80608000 | `mem-entries.md:23478` |
| 2026-11-18 |  | 2026-11-18 09:30 - First own-artifact FIP kernel slice assembled and structurally validated (host-only, never booted) | `mem-entries.md:23525` |
| 2026-11-18 |  | 2026-11-18 09:55 - First drivers ported to 6.18 with DT bindings: CRG clock+reset controller and watchdog; full kernel compile RC=0, dt_binding_check PASS | `mem-entries.md:23580` |
| 2026-11-18 |  | 2026-11-18 10:55 - FMC/SPI-NAND and network drivers ported; driver series at six patches (004-009) with bindings | `mem-entries.md:23643` |
| 2026-11-18 |  | 2026-11-18 11:10 - Machine-restart driver (patch 010, provisional reset) and remaining-driver evidence plan delivered; driver series 001-010 integrated | `mem-entries.md:23702` |
| 2026-11-18 |  | 2026-11-18 11:45 - Pinctrl (011) and thermal (012) drivers ported and integrated; driver series now 001-012 | `mem-entries.md:23757` |
| 2026-11-18 |  | 2026-11-18 12:10 - PCIe host driver (013), CRG reset-polarity fix (014), PIE data-path spec; series 001-014 integrated and combined-verified | `mem-entries.md:23808` |
| 2026-11-18 |  | 2026-11-18 13:05 - PIE packet-engine refusing draft (015) and LSW switch RE spec integrated; whole series 001-015 combined-verified | `mem-entries.md:23880` |
| 2026-11-18 |  | 2026-11-18 15:20 - LSW D1a draft (016) integrated; image recipe wired and first real OpenWrt image built (make world RC=0, reproducible, host-only) | `mem-entries.md:23936` |
| 2026-11-18 |  | 2026-11-18 15:55 - A/B selector driver (017) and install path implemented; final 001-017 image build RC=0 with 58/58 mocked install assertions on the real container | `mem-entries.md:24006` |
| 2026-11-18 |  | 2026-11-18 16:20 - Consolidated reversal report and review-form upstream submission series (001-017) delivered and integrated | `mem-entries.md:24078` |
| 2026-11-18 |  | 2026-11-18 16:55 - 0x21 selector semantics integrated, patch 017 corrected, boot-time pair recorder added, final image rebuilt (362ca4ec) and install harness 100/100 | `mem-entries.md:24117` |
| 2026-11-18 |  | 2026-11-18 17:40 - GPL request de-scoped as a project action (optional accelerator only); own-RE continuation approved | `mem-entries.md:24181` |
| 2026-11-18 |  | 2026-11-18 18:05 - Remaining SoC blocks decoded: MAC source resolved (bdinfo 0xde00); efuse/RNG/LED-PWM/PMU-PWM/CRG-parents decisions recorded | `mem-entries.md:24199` |
| 2026-11-18 |  | 2026-11-18 18:25 - SMP vendor bring-up decoded; draft platsmp patch 018 integrated; review-form series extended to 18 patches | `mem-entries.md:24246` |
| 2026-11-18 |  | 2026-11-18 18:55 - Factory-MAC provisioning from bdinfo 0xde00 implemented and image-validated (mock 103/103) | `mem-entries.md:24288` |
| 2026-11-18 |  | 2026-11-18 19:10 - CRG clock tree completed (019): real gate parents, fixed clocks, read-only PLL/mux providers; duplicate SKELETON-SMOKE session fixed | `mem-entries.md:24326` |
| 2026-11-18 |  | 2026-11-18 19:23 - PUBLISH POLICY: the root notebook goes intentionally public; lab web-admin credential and per-unit MACs redacted in HEAD (history not rewritten) | `mem-entries.md:24370` |
| 2026-11-18 |  | 2026-11-18 19:35 - Publication pivot integrated: curated repos live, root notebook policy/redaction committed locally, first-install tooling integrated; push awaits owner approval | `mem-entries.md:24426` |
| 2026-11-18 |  | 2026-11-18 19:55 - Notebook and legacy submodule pushed (fast-forward); public trees verified clean | `mem-entries.md:24473` |
| 2026-11-18 |  | 2026-11-18 20:05 - Read-only bench inventory tool completed and integrated (145/145 mocked tests); host-side backlog finished | `mem-entries.md:24501` |
| 2026-11-18 |  | 2026-11-18 20:15 - First read-only silicon inventory COMPLETE (600/600 reads); PIE/LSW/CRG/SYSCTRL unknowns closed; tool context-capture bug fixed | `mem-entries.md:24543` |
| 2026-11-18 |  | 2026-11-18 21:10 - PIE datapath ring engine + GEMAC front end implemented (patch 020), built from the measured 2026-11-18 baseline | `mem-entries.md:24592` |
| 2026-11-18 |  | 2026-11-18 21:25 - LSW read-only D1b baseline probe implemented (patch 021) and integrated | `mem-entries.md:24631` |
| 2026-11-18 |  | 2026-11-18 21:40 - Review-form series extended to 001-021; curated public repo synced (port + inventory docs) | `mem-entries.md:24673` |
| 2026-11-18 |  | 2026-11-18 21:50 - Curated repo review form synced to 001-021; publication and driver surfaces all current | `mem-entries.md:24707` |
| 2026-11-19 |  | 2026-11-19 13:45 - MILESTONE: our kernel 6.18.60 + our OpenWrt rootfs BOOTED TO USERSPACE on the WR3000 v2 (attended) | `mem-entries.md:24731` |
| 2026-11-19 |  | 2026-11-19 14:10 - Correction to the 2026-11-19 milestone entry: the booted kernel was UP (1 CPU), not SMP (2 CPUs) | `mem-entries.md:24777` |
| 2026-11-19 |  | 2026-11-19 14:20 - Minimum connectivity path implemented (022/023): gated LSW W2/W3/W4/W5 write stages + GEMAC netdev readiness | `mem-entries.md:24797` |
| 2026-11-19 |  | 2026-11-19 14:35 - Final full-series image with persistent overlay ready (15dae772...), validated; next attended boot is its first hardware test | `mem-entries.md:24832` |
| 2026-11-19 |  | 2026-11-19 14:45 - Review-form series finalized at [PATCH 00/23] (022/023 added and revalidated) | `mem-entries.md:24869` |
| 2026-11-19 |  | 2026-11-19 14:50 - Curated public repo synced to the final state (001-023 + overlay image + series); all surfaces current | `mem-entries.md:24890` |
| 2026-11-19 |  | 2026-11-19 15:20 - Egress (025) and bdinfo-MAC nvmem (026) integrated; final image rebuilt to 001-026 (aa642862...) | `mem-entries.md:24915` |
| 2026-11-19 |  | 2026-11-19 15:35 - PIE completion decode (024) integrated; final image rebuilt to 001-026 with hisilicon,port DTS (26dde6fe...) | `mem-entries.md:24954` |
| 2026-11-19 |  | 2026-11-19 15:45 - Review-form series finalized at [PATCH 00/26] | `mem-entries.md:24982` |
| 2026-11-19 |  | 2026-11-19 15:50 - Final curated sync (001-026 + image 26dde6fe); all surfaces current and clean | `mem-entries.md:25006` |
| 2026-11-19 |  | 2026-11-19 17:10 - BENCH MILESTONE: full 001-027 gate image boots with overlay; W3/W4/W5 accepted; PIE armed; GEMAC netdevs up with 1G carrier; ARP still fails; SMP 1 CPU | `mem-entries.md:25029` |
| 2026-11-19 |  | 2026-11-19 17:40 - PIE trace: TX descriptors consumed by the engine, but no egress frame and no RX delivery; EPS channel map/EQM tables are the remaining blockers | `mem-entries.md:25067` |
| 2026-11-19 |  | 2026-11-19 18:15 - W6 EPS channel-map gate: accepted/verified, but still no wire egress and zero RX interrupts; queue-manager init is the next layer | `mem-entries.md:25095` |
| 2026-11-19 |  | 2026-11-19 18:45 - SMP CPU1 release diagnosed offline; patch 033 turns it into a one-boot measurement | `mem-entries.md:25121` |
| 2026-11-19 |  | 2026-11-19 18:50 - W7 queue-manager init integrated; combined W7+SMP-probe bench image built (14791958...) | `mem-entries.md:25144` |
| 2026-11-19 |  | 2026-11-19 19:10 - W7 queue-manager init exercised: snapshot+idle gates pass, first EQM readback mismatch -> restore/refuse (fail-closed); SMP probe shows no pen consumption, SCU status 00 | `mem-entries.md:25176` |
| 2026-11-19 |  | 2026-11-19 19:25 - SMP W7-run diagnostic corrected: probe knobs were rejected; patch 034 makes dumps unconditional and probe default-on | `mem-entries.md:25200` |
| 2026-11-19 |  | 2026-11-19 19:40 - W7 verification contract fixed (table 19 write-only); final combined image 5d2c5476 built (001-034) | `mem-entries.md:25222` |
| 2026-11-19 |  | 2026-11-19 21:00 - Final image 5d2c5476 run: W7 table-19 ack works, table-17 read-view mapping mismatch -> restore/refuse; SMP probe marker ioremap failed but pen untouched and no 1P | `mem-entries.md:25241` |
| 2026-11-19 |  | 2026-11-19 21:15 - SMP probe marker fixed (035); pen-0 explained; probe still unrun but now measurable | `mem-entries.md:25264` |
| 2026-11-19 |  | 2026-11-19 21:20 - Image 75868fe0 built: W7 tiered verification (032 rev3) + SMP marker fix (035) | `mem-entries.md:25287` |
| 2026-11-20 |  | 2026-11-20 09:45 - W7 rev3 completes: queue-manager init accepted, data path ARMED, GEMAC netdevs + 1G carrier; but traffic still does not move; SMP probe definitive consumed=no | `mem-entries.md:25302` |
| 2026-11-20 |  | 2026-11-20 10:00 - Cold-boot SMP test: same consumed=no; CPU1 does not consume the pen on cold or warm boot | `mem-entries.md:25331` |
| 2026-11-20 |  | 2026-11-20 10:20 - Image 6cb3d908 built: PFE forwarding-engine base init W8 (036) + SMP loader-window reserve test (037) | `mem-entries.md:25351` |
| 2026-11-20 |  | 2026-11-20 10:35 - W8 PFE base init verified; tier counters fixed; traffic still dead; reserve_low1m does not revive CPU1 | `mem-entries.md:25368` |
| 2026-11-20 |  | 2026-11-20 10:45 - Image a6b57361 built: seven-gate chain incl. W9 MAC max-frame init + SMP early probe | `mem-entries.md:25392` |
| 2026-11-20 |  | 2026-11-20 11:05 - W9 clean run: boot stable, W9 verified on all GEMACs, but the first traffic attempt reset the box to stock; W9/TX hang regression under analysis | `mem-entries.md:25408` |
| 2026-11-20 |  | 2026-11-20 11:30 - W9 read-only diag + early_probe=2 run: no W9 write, TX still wedges the box after one frame; stock reference registers captured | `mem-entries.md:25433` |
| 2026-11-20 |  | 2026-11-20 12:05 - Heartbeat added: the "idle hang" and several "hung box" conclusions were false alarms; the box was alive but silent | `mem-entries.md:25461` |
| 2026-11-20 |  | 2026-11-20 12:35 - macconf (vendor MAC link sequence) executed cleanly; box stable via heartbeat; traffic still dead | `mem-entries.md:25485` |
| 2026-11-20 |  | 2026-11-20 13:10 - W10 IFC default-classification table programmed and verified on hardware; full W3-W10 chain armed; heartbeat stable; traffic still dead | `mem-entries.md:25505` |
| 2026-11-20 |  | 2026-11-20 13:35 - W11 stock-vs-ours LSW diff: found a wrong W10 tab128 value set + 16 unprogrammed EPS channel-map words + dp+0x1c difference | `mem-entries.md:25532` |
| 2026-11-20 |  | 2026-11-20 13:50 - W12 verified: corrected W10 tab128 slots/allocator id + stock EPS/DP words; full W3-W12 chain armed; heartbeat stable; traffic STILL dead | `mem-entries.md:25558` |
| 2026-11-20 |  | 2026-11-20 14:05 - W13 PIE/GMAC dump: the RX smoking gun is pie 0x3404 (ours 0x0 vs stock 0x1b04); everything else matches | `mem-entries.md:25583` |
| 2026-11-20 |  | 2026-11-20 14:25 - W13 RXCFG written and verified (pie+0x3404 0x0 -> 0x1b04) but RX STILL never fires | `mem-entries.md:25610` |
| 2026-11-20 |  | 2026-11-20 14:35 - W14 all-window page scan: stock has many runtime table pages that our armed image leaves zero (pe/eqm/eps/ifc/mcc/opp), and fam+0x1000/0x41000 values differ | `mem-entries.md:25631` |
| 2026-11-20 |  | 2026-11-20 14:50 - GEMAC stock-vs-ours diff: four un-decoded MAC config words differ plus max-frame 1536 vs our 1518 | `mem-entries.md:25656` |
| 2026-11-20 |  | 2026-11-20 15:05 - RX path is functionally alive after W16: PIE RX completions arrive, but our decoder drops them (status 0x25, port 0) and host traffic still is not forwarded to the CPU | `mem-entries.md:25679` |
| 2026-11-20 |  | 2026-11-20 15:30 - FIRST REAL TRAFFIC: box accepts a punted ARP exception on eth2 and sends an ARP reply on the wire | `mem-entries.md:25705` |
| 2026-11-20 |  | 2026-11-20 15:25 - PARTIAL SUCCESS: first ICMP echo replies received (4/18 ping) during the W17 mirror sweep; sweep bug only covered dst 4-8 | `mem-entries.md:25732` |
| 2026-11-20 |  | 2026-11-20 17:55 - static CPU-copy dst 8 alone: ARP still answered but 50/50 ping lost; RXSTROKE shows only one RX completion - the mirror is programmed before eth2 link-up, so it is likely lost/reset | `mem-entries.md:25757` |
| 2026-11-20 |  | 2026-11-20 18:30 - W19 post-link mirror works mechanically (applied every 2 s, pre/post stable) but dst 8 is NOT the CPU port: ARP answered, ICMP 98 B never reaches the CPU | `mem-entries.md:25778` |
| 2026-11-20 |  | 2026-11-20 18:40 - DWELL SWEEP IDENTIFIES THE CPU PORT: mirror destination 4. Host ICMP then arrives as NORMAL-path completions (status=0, port=0) which our driver drops because port 0 has no netdev | `mem-entries.md:25802` |
| 2026-11-20 |  | 2026-11-20 18:55 - WORKING DATA PATH: our OpenWrt 6.18 image passes SSH and sustained ping with a persistent UBIFS overlay (mirror dst=4 + port-0 CPU-copy delivery) | `mem-entries.md:25826` |
| 2026-11-20 |  | 2026-11-20 19:15 - reboot from our working image falls back to stock slot A: boot-selector/env handling is not implemented in our 6.18 userspace (overlay persistence across reboot untestable until fixed) | `mem-entries.md:25850` |
| 2026-11-20 |  | 2026-11-20 20:20 - development acceleration base: live /dev/mem MMIO over SSH, baked boot-pair recorder (reboot+overlay persistence [V]), automated install path; plus one incident (slot-A kernel push -> silent box -> recovery) | `mem-entries.md:25870` |
| 2026-11-20 |  | 2026-11-20 20:35 - first live-MMIO diagnostics on the DEVMEM image: full SCU/GIC/SYSCTRL/CRG/PIE state read over SSH, pen mismatch confirmed | `mem-entries.md:25900` |
| 2026-11-20 |  | 2026-11-20 21:05 - live-MMIO round 2: native forwarding conclusion (NAPT carveout unsafe/absent -> mirror stays), CPU1 late-bring-up trigger (patch 059), all live CPU1 variants consumed=no | `mem-entries.md:25923` |
| 2026-11-20 |  | 2026-11-20 21:30 - stock SMP reference captured; CRG deltas proven PCIe (no CPU1 effect); SCU CONFIG bit5 is a CPU1-ran monitor; next decisive probe is pre-decompressor handoff (patch 060) | `mem-entries.md:25963` |
| 2026-11-20 |  | 2026-11-20 21:50 - SMP HANDOFF PROBE: CPU1 IS ALIVE - it consumed the kernel-stext stub (B=0x66cc66cc) but not the decompressor-entry stub (A=0). Stock reads captured (DT/handoff facts, flashinfo window, kernel-slot size). | `mem-entries.md:25996` |
| 2026-11-20 |  | 2026-11-20 22:00 - sentinel probe 061: CPU1 never entered either stub - definitively NOT polling the pen on our loader path; loader-side is the root cause | `mem-entries.md:26036` |
| 2026-11-20 |  | 2026-11-20 22:20 - SMP SOLVED: 2 CPUs online and persistent. Root cause was the U-Boot handoff staging being aborted by missing DT nodes (console alias + flashinfo reserved-memory), not the kernel release path. | `mem-entries.md:26067` |
| 2026-11-20 |  | 2026-11-20 22:40 - 2-CPU image hung after ~23 minutes (silent, no Oops output); stability debugging needed. Canonical post-fix image built (974e6ca6). | `mem-entries.md:26099` |
| 2026-11-20 |  | 2026-11-20 22:50 - stability test image set built for the 2-CPU hang: canonical 974e6ca6, maxcpus=1 d101f96b, lockdep debug 18b3cb1d | `mem-entries.md:26125` |
| 2026-11-21 |  | 2026-11-21 11:45 - RETRACTION: the "2-CPU hang" was a host bench-link outage, not a kernel hang. The canonical 2-CPU image is stable and verified (soak in progress). | `mem-entries.md:26146` |
| 2026-11-21 |  | 2026-11-21 12:00 - FINAL: canonical 2-CPU image 974e6ca6 stable (15-min soak, 0 failures) and persistent across reboot; SMP task closed. | `mem-entries.md:26171` |
| 2026-11-21 |  | 2026-11-21 12:25 - 6.18 RELEASE LINE consolidated and independently validated: 51 included patches (11 bench diagnostics excluded), loader hand-off DTS contract checked as release-critical; canonical 2-CPU baseline 974e6ca6. | `mem-entries.md:26194` |
| 2026-11-21 |  | 2026-11-21 12:40 - release-line cleanup complete: 052/053 pair fixed (0 fuzz, strict-clean), monotonic 062-065, DTS-0001 companion validated | `mem-entries.md:26221` |
| 2026-11-21 |  | 2026-11-21 13:15 - Board feature bring-up phase started: curated repos synced, device feature inventory delivered, LEDs/keys DTS+config in progress. | `mem-entries.md:26246` |
| 2026-11-21 |  | 2026-11-21 13:35 - LEDs + buttons + watchdog sysfs brought up on hardware (image 7f270b8c); unaligned-DTB gate-word bug found and fixed. | `mem-entries.md:26272` |
| 2026-11-21 |  | 2026-11-21 13:50 - Quiet canonical image 7421bb7a: periodic W17/W19/HB dmesg spam removed; thermal ENODATA root-caused; LEDs/keys/watchdog verified. | `mem-entries.md:26301` |
| 2026-11-21 |  | 2026-11-21 14:05 - Install-path finding: stock vendor image has no SSH/dropbear/opkg, so the automated first-install tool cannot run as written; manual path re-verified with quiet image 7421bb7a. | `mem-entries.md:26321` |
| 2026-11-21 |  | 2026-11-21 14:30 - Automated install path CLOSED: new telnet installer verified end-to-end on the data (stock pair A -> our image pair B). | `mem-entries.md:26341` |
| 2026-11-21 |  | 2026-11-21 14:45 - HARDWARE REGRESSION in the cleaned DTS (538377c): boot stalls in MTD partition registration and resets via the U-Boot watchdog; rolled back to image 7421bb7a. | `mem-entries.md:26364` |
| 2026-11-21 |  | 2026-11-21 14:55 - Cleaned-DTS regression RESOLVED: conservative comment-only cleanup (7ae18f2) reproduces the known-good image byte-for-byte. | `mem-entries.md:26388` |
| 2026-11-21 |  | 2026-11-21 15:05 - Far-right port identified as a non-eth2 LAN port: box alive (UART heartbeat, IPv6 RAs reach the host) but host-to-box frames are not delivered because the CPU-copy mirror workaround covers eth2/switch-port 11 only. | `mem-entries.md:26412` |
| 2026-11-21 |  | 2026-11-21 15:20 - Multi-port Ethernet analysis: far-right jack is a LAN port; CPU-copy path reports port 0 and has no confirmed source-port id, so a per-port delivery decision needs the documented RX-source experiment or the native bridge. | `mem-entries.md:26432` |
| 2026-11-21 |  | 2026-11-21 15:35 - Multi-port probe image built and staged (a91ebcf0): mirror source-port mask parameter + RXDIAG cmdline tokens, ready for the source-port experiment when the cable is back on eth2. | `mem-entries.md:26454` |
| 2026-11-21 |  | 2026-11-21 16:20 - Multi-port source-port experiment RESULT: no source identifier in CPU-copy completions -> native L2/VLAN bridge is required for multi-port LAN/WAN. | `mem-entries.md:26473` |
| 2026-11-21 |  | 2026-11-21 16:35 - Physical verification: all six LEDs confirmed lit by the user; RESET button press captured as EV_KEY KEY_RESTART. | `mem-entries.md:26498` |
| 2026-11-21 |  | 2026-11-21 16:45 - WPS button verified: EV_KEY KEY_WPS_BUTTON press/release captured. Both board buttons and all six LEDs are now physically verified. | `mem-entries.md:26513` |
| 2026-11-21 |  | 2026-11-21 16:55 - Watchdog telemetry/arming verified indirectly: /dev/watchdog is already held open (Resource busy) with state=active/timeout=30, so the hardware watchdog is armed and serviced by userspace (procd), and the box stays up across minutes -> keepalive path works. | `mem-entries.md:26526` |
| 2026-11-21 |  | 2026-11-21 17:10 - Upstream blocker #6 (TWD timer IRQ flags): hardware read done on the unit - GICD_ICFGR1 for TWD PPI13/ID29 reads 0b11 (read-only SoC-fixed); standard A9 DTs use LEVEL_HIGH. | `mem-entries.md:26544` |
| 2026-11-21 |  | 2026-11-21 17:25 - TWD timer level-high delta adopted after hardware boot test: /proc/interrupts now reports "GIC-0 29 Level twd", both CPUs ticking, no stalls. | `mem-entries.md:26561` |
| 2026-11-21 |  | 2026-11-21 17:40 - TWD adoption artifacts verified independently; publish runbook committed; notebook publication hygiene fixed with a checker gate. | `mem-entries.md:26580` |
| 2026-11-21 |  | 2026-11-21 17:55 - Upstream blockers 3/4/5 boot-tested PASS in one image (MAC nvmem removal, switch MMIO-first reg order, compatible order): image c3ef2a50. | `mem-entries.md:26606` |
| 2026-11-21 |  | 2026-11-21 18:10 - E0-a native-delivery experiment: with the CPU mirror disabled the unit boots and receives native-path completions on port 11, but every frame is status=37 err=1 and IP is dead -> native CPU delivery is error-flagged/misconfigured; mirror workaround still required. | `mem-entries.md:26627` |
| 2026-11-21 |  | 2026-11-21 18:20 - test-mac-nvmem.sh updated to the adopted 6.18 MAC path: 77/77 pass (was 64/82 after the nvmem-cell removal). | `mem-entries.md:26652` |
| 2026-11-21 |  | 2026-11-21 18:35 - Upstream: switch binding MMIO-first adopted into the series, review form rerun PASS, ONE blocker left (flashinfo loader acceptance); flashinfo test image pre-built. Native-forwarding refined: E0-a status=37 is the exception/punt class, IP death is missing unicast-to-CPU coverage. | `mem-entries.md:26666` |
| 2026-11-21 |  | 2026-11-21 18:55 - Recovery succeeded but the subsequent handover left a MIXED kernel/userland system: our 6.18 kernel (cmdline luofu_switch.*) booted with the stock 5.10 rootfs (rootfsb). Stock LuCI then refuses the wizard ("Invalid board info!", bdinfo checkuuid needs the vendor kernel's /proc/sys/dev/flash_uuid) and the MQTT broker path is silent. | `mem-entries.md:26696` |
| 2026-11-21 |  | 2026-11-21 19:05 - FLASHINFO LOADER TEST PASSED over the broker channel: the loader accepts hisilicon,luofu-flashinfo first, performs the full staging handoff and boots our image with 2 CPUs - the last upstream blocker is closed (zero blockers). | `mem-entries.md:26722` |
| 2026-11-21 |  | 2026-11-21 19:35 - E0-b complete: read-only stock-vs-ours runtime captures (9,488 words each) and the classifier diff are captured; box is back on our image with env bootflag=b / selector 0x11. | `mem-entries.md:26732` |
| 2026-11-21 |  | 2026-11-21 19:55 - E0-b decode + reviewed M1a probes: tagact entry 1 is a tag-DELETE action (not CPU-punt), L2 diffs are DFX counters, pfe_glb+0x2c is a flow-engine uplink attribute - write replays expected null; the decisive next step is the read-only stock decoded procfs capture. | `mem-entries.md:26759` |
| 2026-11-21 |  | 2026-11-21 20:10 - M1a replay probes both NULL: tagact entry write is ignored by the hardware (readback mismatch, auto-reverted) and the pfe_glb up_port write succeeds but changes no CPU delivery (eth2 delta stays 531 = mirror copies only). Write experiments stop; the decisive next step is the read-only stock procfs decoded-table capture. | `mem-entries.md:26783` |
| 2026-11-21 |  | 2026-11-21 20:25 - Stock decoded procfs captured (137 files): the CPU-punt path is IFC->tocpu (ifc_hit=992, ifc_tocpu=104, cpu_spec_send=718) but the readable IFC/L3/flow shadow tables are empty - the rules live in the CFE/flow-engine state; M1a write probes closed (both null). | `mem-entries.md:26804` |
| 2026-11-21 |  | 2026-11-21 20:45 - CPU-punt mechanism resolved: IFC->NAPT path; our NAPT is uninitialized (all config words 0), so unicast dies inside the flow engine before PIE. Vendor hi_pfe_napt_init decoded as a register-only sequence and prepared as a fail-closed replay. | `mem-entries.md:26827` |
| 2026-11-21 |  | 2026-11-21 21:00 - BREAKTHROUGH: replaying the decoded hi_pfe_napt_init sequence makes the flow engine punt unicast to the CPU. With the mirror still on, eth2 RX delta was 1122 for 500 pings (~2x) and napt up_tocpu rose from 0x2e to 0x261 (+563) while ping stayed 0% loss - the native CPU-delivery signal M1a was looking for. | `mem-entries.md:26859` |
| 2026-11-21 |  | 2026-11-21 21:20 - M1a PROVEN: native CPU delivery with the CPU-copy mirror OFF. Proof image 5800c9ab (canonical adopted tree + cmdline cpu_mirror=0/luofu_napt_init=1/rxdiag=1 + probe boot-time NAPT-init script) boots, applies NAPT init, and SSH/ping work with no mirror; native RXDIAG status=77 frames are delivered. | `mem-entries.md:26884` |
| 2026-11-21 |  | 2026-11-21 21:40 - W22 kernel drafts + M1b plan delivered: NAPT-init as a driver stage (patch 0001) + native exception/status-class delivery in PIE (patch 0002), compiled/checkpatch-clean; exact release-integration and M1b per-port plan documented. | `mem-entries.md:26906` |
| 2026-11-21 |  | 2026-11-21 22:00 - W22 kernel implementation landed in the release line and verified on hardware: canonical image 50023446 boots with the driver NAPT init (no mirror tokens), ping/SSH work, reboot determinism passes. | `mem-entries.md:26931` |
| 2026-11-21 |  | 2026-11-21 22:15 - Curated openwrt repo synced to the W22 release state (214c893, fresh-clone verified, all checks green); fallback-image build/test and soak are the remaining bench steps. | `mem-entries.md:26965` |
| 2026-11-21 |  | 2026-11-21 22:45 - Fallback-image test hit an env handover race: the broker write of bootflag=b/selector 0x11 did not survive to the next boot (U-Boot booted stock pair a, bootflag a/bootreg 10), and the vendor userspace then re-normalised the selector; the box is now running vendor userspace with no management IP (stock LAN unreachable). Needs one physical RESET-hold recovery. | `mem-entries.md:26983` |
| 2026-11-21 |  | 2026-11-21 23:00 - Telnet install flashed the ACTIVE pair and failed: after recovery the stock booted from pair b (env bootflag=b), so ubiformat /dev/mtd14 targeted the mounted rootfsb, failed, and the result was again our 6.18 kernel with the vendor rootfs (mixed: no management IP on 192.168.1.1, vendor wizard 403 invalid board info, broker silent). One more physical RESET-hold recovery needed. | `mem-entries.md:27008` |
| 2026-11-22 |  | 2026-11-22 00:05 - W22 canonical image re-installed successfully with the corrected two-stage procedure: stock switched to pair a first, then the image written to the inactive pair b via the broker with atomic env+reboot. Boot verified, link-flap recovers, 15-min soak started. | `mem-entries.md:27030` |
| 2026-11-22 |  | 2026-11-22 00:35 - 15-min W22 soak PASS (900/900, 0% loss, 0 errors). Fallback-image test went wrong again (build/cmdline caching suspected, then no management IP); box needs one more physical RESET-hold recovery. The fallback path will be documented as a known limitation rather than a formal bench step. | `mem-entries.md:27054` |
| 2026-11-22 |  | 2026-11-22 00:55 - W22 canonical re-installed and verified after recovery #5 using the two-stage procedure (stock pair a -> broker write inactive pair b atomic). Box healthy: 6.18.60, 2 CPUs, naptinit=1, no mirror tokens, W22 init verified, 0 errors. M1b per-port native delivery test starting with cable moves. | `mem-entries.md:27076` |
| 2026-11-22 |  | 2026-11-22 01:15 - M1b-1 PASS: per-port native CPU delivery verified on all four jacks (eth0/port9 far-right, eth1/port10 second-right, eth2/port11 bench, eth3/port12 leftmost WAN) with the W22 image and no mirror. | `mem-entries.md:27091` |
| 2026-11-22 |  | 2026-11-22 01:40 - M1b-3 LAN-to-LAN forwarding PASS: with a second USB-Ethernet adapter on eth0 and the bench adapter on eth2, the software bridge forwards broadcast and learned unicast in BOTH directions (eth0<->eth2); FDB learns both MACs on the correct ports. Native multi-port LAN forwarding works with W22 and no hardware L2 offload. | `mem-entries.md:27107` |
| 2026-11-22 |  | 2026-11-22 02:00 - Multi-port LAN complete: LAN-to-LAN forwarding also PASS on the second port pair eth2<->eth1 (broadcast + learned unicast, both directions), FDB learns both host MACs on the correct ports. Native multi-port LAN (all four jacks delivery + bridge forwarding over both LAN port pairs) is now fully bench-verified with W22 and no hardware L2 offload. | `mem-entries.md:27127` |
| 2026-11-22 |  | 2026-11-22 02:20 - WAN L3 path PASS: with the second adapter on the leftmost jack (eth3/WAN), the box obtained DHCP lease 192.168.50.115/24 from a host dnsmasq, installed default via 192.168.50.1 dev eth3, pinged the gateway 5/5 and replied to host ping 4/4 - the WAN port has a complete native L2/L3 path. | `mem-entries.md:27144` |
| 2026-11-22 |  | 2026-11-22 02:40 - Four full-reversal lanes delivered: CFE/switch model + our-side dump validation (95bea9e), vendor userspace fully decompiled (42a431a), Wi-Fi/thermal feasibility (8b8ace5), loader/recovery/upgrade formats (628c4b1). Stock /dev/mem read() is blocked but mmap via a static physdump binary works, so the stock stock-runtime CFE dump is now being transferred via broker wget+physdump+nc. | `mem-entries.md:27164` |
| 2026-11-22 |  | 2026-11-22 03:00 - Full-reversal phase: all four lanes delivered and integrated; stock runtime CFE tables successfully captured via an mmap dumper (vendor /dev/mem read() is blocked but mmap works). Thermal fix is now implementable from the decoded formula; tasking W23. Stock package: build/evidence-bench-gates/cfe-stock/cfe-stock-full.tar.gz (sha256 202aca42f6038245a1c994bf4b03101756ad2bc961741df1bef6b322a484b312). | `mem-entries.md:27199` |
| 2026-11-22 |  | 2026-11-22 03:20 - W23 thermal fix integrated and bench-PROVEN: gate off raw=0/ENODATA; enable -> raw 0x25e = 59000 mC (formula exact), registers match, no IRQ, 0 warnings; CPU load 59->63 C with cooling. Release line now L0 66 / L1 55 (manifest 2bb7413e), validator PASS 55/55, target build PASS. Stock routed-phase dump captured for the CFE lane (box-terminated traffic -> flow arenas empty, explained; true forwarded-traffic recipe recorded). | `mem-entries.md:27209` |
| 2026-11-22 |  | 2026-11-22 03:40 - TRUE forwarded-traffic stock phase captured (netns split: root LAN 192.168.10.44, netns wan 192.168.50.1; box WAN DHCP 192.168.50.115; host->box->WAN ping 5/5 + curl 200). First time the vendor pub window changed vs p0 (tagact/l3intf bank populated): fwd-win15-pub sha 32ca3d39 vs p0 f3b58f7b; sent to the CFE lane for the final slot-format/M2 decode. Box returned to W23 (6.18.60, 2 CPUs, thermal gate 0, W22 init once, 0 errors); host netns/route cleaned up. | `mem-entries.md:27235` |
| 2026-11-22 |  | 2026-11-22 04:00 - CFE forwarded-phase decode complete: vendor L3/neighbour/tag tables decoded (l3intf[1] LAN MAC d4:0d:ab:64:1c:73 sip 0.0.0.0 tagact_id 2 mtu 1500, l3intf[2] sip 192.168.50.115 WAN, nhp[1] 192.168.10.44 host MAC, nhp[2] second host NIC, tagact[2]=0x0000b000 selector 3; layout from l3intf_write/nhp_write disassembly). NAPT DDR v4/v6 arenas EMPTY even with true forwarded NAT traffic (0 bytes changed; match counters non-zero: dn_match 134, up_match 91) -> M2-A hardware flow cache CLOSED (do not implement; vendor doesn't use the DDR cache in this config), M2-B data-backed documentation only. Release path unchanged: W22/M1b; nothing blocks. | `mem-entries.md:27244` |
| 2026-11-22 |  | 2026-11-22 04:15 - SESSION CLOSE-OUT: full-reversal program at its accessible ceiling; W23 thermal bench-proven and published; M2 hardware offload closed; curated repo final at 4bd4360 (324 files, all checks PASS). Bench torn down (stale HTTP killed; no TFTP/UART writers); box final: W23 image, 6.18.60, 2 CPUs, naptinit=1, thermal gate 0, selector 0x11, 0 errors. | `mem-entries.md:27258` |
| 2026-11-22 |  | 2026-11-22 06:40 - Wi-Fi TRY concluded with a QUANTIFIED NO-GO for the 6.18 binary port; the full swarm is complete. Wi-Fi works on this box only via the vendor 5.10 stack; the interface contract is now fully documented and the GPL follow-up is the single remaining unlock. | `mem-entries.md:27279` |
| 2026-11-22 |  | 2026-11-22 07:20 - Wi-Fi framework census complete: GPL-2.0 hi3881 source covers 23.9% (name) / 28.5% (byte) of our 4,946-function driver pair; a 892 KB skeleton (libsec+frw+oal+oam+mac/common, 28 objects) COMPILES against 6.18.60; the hi5622 delta is mapped (3,763 unique names, 1,014,560 B): transport pcie_/bal_ ~391 fns, shuangta_ 173, hdpp_ 238, hal_ 91, alg_ 222, hmac/wal ko-only ~2,409. 33/39 cfg80211_ops and 12/44 D2H handlers name-match the framework. ROOT-CAUSE FIND: oal_util.h pins LINUX_VERSION_CODE=kernel_version(3,10,0) (the vendor driver silently ran 3.10 API branches; unpinning exposes the real 6.18 drift: timespec64, timer_delete, set_fs removal, sched_setattr_nocheck, netlink cb_mutex, fortify/strlen clash). hcc_* renamed between chips (1/87 shared - SDIO/ADMA vs PCIe mailbox/ETE). | `mem-entries.md:27308` |
| 2026-11-22 |  | 2026-11-22 08:40 - Wi-Fi transport slice REBUILT: hi5622_pciet.ko (93,468 B, GPL, vermagic 6.18.60, 0 warnings under -Werror) implements the firmware-upload/ETE-ring/mailbox contract as original clean-room code and compiles against our built 6.18.60 tree (commit 99d9c8f, docs/incoming/wifi-transport-port/). First bench milestone defined: attended sysfs-step upload -> 0x5a5a release -> 0xcece announce -> HCC ready ids 1/2 (bitmap 0x2 / 0x4 = out[1]=0x4). Findings: no MSI on luofu 6.18 (msi_init returns 0) and no INTx demux (status in never-read misc window) -> skeleton polls the D2H bitmap; host-side delta patch build/luofu-host-618-delta.patch adds dma-ranges identity to both pcie nodes (bench prerequisite); twin-word gating left [U]. Transport group (pcie+bal+shuangta+hal = 391 fns / 67,432 B) = 6.6% of the ko-only delta; next slices in size order: hdpp_ 238 (dpe_ twin in hongmengkernel hi1105) -> alg_ 222 (densest) -> hal_ 91 -> shuangta_ 173 -> hmac_ ko-only 1,503 -> wal_ ko-only 684. Framework-lane build text files force-added (bare build/ gitignore rule). | `mem-entries.md:27321` |
| 2026-11-22 |  | 2026-11-22 10:10 - Wi-Fi data-path slice: hdpp/alg mapped and scaffolded. hdpp_ (238 fns) -> dpe_ twin: 3 exact-name (1.3%); alg_ (239) -> twins: 17 exact (7.1%, generic cfg-command core in wal/wal_config_alg_cfg.c) + 51 same-subfamily; combined 20/477 (4.2%) - the engines are family-level twins with fully diverged naming. Call-graph evidence (27,255 resolved bl edges; 108 hdpp + 64 alg call targets). Scaffold re-exports all 60 vendor ksymtab exports (46 hdpp_stat_* + 6 alg_* + 8 g_alg_*, ABI pinned by wifi_debug.ko imports) and compiles into hi5622_hdpp_alg_skel.ko (73,404 B, 6.18.60, -Werror tree). 12-point bench-probe list written (init dispatch, sync-write D2H acks, counter layouts, D2H TWT/ERSRU payloads, stat dfx params, alg table contract). Next slice: alg_cfg + wal config-command port (host-testable against the 17 twins as oracle), then hdpp object model (needs transport bench stage B2). hongmengkernel reference clone kept outside git (no license grant - reference-only honored). | `mem-entries.md:27325` |
| 2026-11-22 |  | 2026-11-22 12:40 - Wi-Fi alg_cfg slice: the generic config-command codec is ported and ORACLE-VERIFIED. hi5622_alg_cfg_codec.ko (97,364 B, GPL, vermagic 6.18.60, -Werror) compiles from the committed tree; the host harness runs the 17 exact twins and the port output is byte-identical to the reference (17/17 PASS, 0 failures, including the waterfilling_limit int8-wrap quirk). LICENSE CORRECTION: the twin codec exists only in the NO-license hongmengkernel hi1105 tree (wal_config_alg_cfg.c is absent from the GPL-2.0 hi3881 tree) - per the clean-room rules the codec is committed as ORIGINAL GPL-2.0 text pinned from our binary disassembly (414-row process table, 176B-per-command 416-entry LUT at .data+0x4934, 40-entry param-size table, 13/13/2 value tables, runtime-patched 4608-pair name fixup list, error codes 100/101/1009/1014/1017/35629), with the hi1105 file used as a local execution oracle only. The genuinely vendored GPL-2.0 text is the hi3881 wal command layer (vendor/hi3881-wal/). 120 hi5622-specific cfg families annotated (30 spectral, 6 smartant, 5 ulsch, 5 trigger parsers + 10 formatters, 3 ersru, 2 sounding, 60 formatter-shaped, atf/mumimo/ns_aggr/ofdma/tpc/obss/urp/ppet). Commit 3d1ad9b, docs/incoming/wifi-algcfg-slice/. | `mem-entries.md:27329` |
| 2026-11-22 |  | 2026-11-22 14:45 - Wi-Fi wal-glue slice: the 6.18 wal config-command front end compiles. hi5622_wal_cfg.ko (222,528 B, GPL, vermagic 6.18.60, depends cfg80211, 0 errors/0 warnings) wires the oracle-verified codec: vendor-exact entry names (wal_wlan_cfg_module_process_entry + host/device legs), hipriv-style wal_hipriv_alg_cfg*, sysfs /sys/kernel/wal_cfg/ surface, cfg80211 vendor-command provider (6.18 alloc_reply_skb; CONFIG_CFG80211=n provider symvers mirroring the vendor imports), hmac cfg dispatch stubs (22 vendor names incl. hmac_event_config_syn / hcc_msg_register_tab 12->16B merge), LUT/name-fixup loader (416x176B LUT key (type<<16)\|id, 4608-pair fixup list, runtime descriptor from the algcfg offsets), 22 exports vendor-exact. Commit 422c8c9, docs/incoming/wifi-wal-glue/ (+ probes/bench-probes.md P0-P5). | `mem-entries.md:27338` |
| 2026-11-22 |  | 2026-11-22 12:25 - PCIe bring-up bench (W24 series): the COMPLETE vendor RC sequence is now implemented in patch 013 and the link still does not train - the remaining difference is endpoint-side hardware. Big milestone: our 6.18 kernel now has a probing PCIe host with the full recorded vendor bring-up (pre-init words, RC mode, gated cmd/speed, LTSSM-enable with the DBI gate preserved (D1 0x2800), vendor-layout 8-word iATU viewports per RC, steady 0x02200800, stage-2 retrain moved post-link (D2), ACP gate polarity corrected to SET bits 25/26 (hi_acp.ko inverted-value semantics; live 0x06210321), framework pre-link SPEED_CHANGE neutralized, static CFG0 map_bus, 1ms reset pacing). | `mem-entries.md:27349` |
| 2026-11-22 |  | 2026-11-22 12:45 - PCIe adversarial round: every verifiable register on our image now matches the vendor's live state, and the link still does not train. VERIFIED (our image): misc+0x1c = 0x02200800 (both RCs; writes land - the steady state is byte-exact), ACP 0x10100174 = 0x06210321 (bits 25/26 SET), DBI PCI_COMMAND = 0x00100107 (IO\|MEM\|BME), LNKCAP dbi+0x7c = 0x734c12 (speed=2), dbi+0xa0 speed=2. STOCK live target captured: DEBUG0 dbi+0x728 = 0x03f4a611 (LTSSM[5:0]=0x11 L0), cfg window 0x50000000 = 0x59e7 (endpoint answering), ACP 0x06210321, misc link-status words 0x10161100=0x00808028 / 0x10161110=0x20468aa6. OUR image: DEBUG0 LTSSM=0x00, cfg=0xffffffff. Full vendor sequence (doc steps 1-20) diffed: our port covers 1-16 faithfully (17/18 are post-link irq steps; 14 skipped correctly, no aspm-enable). Ordering (host_init before framework DBI) verified in 6.18 source. LTSSM field is 6 bits (GENMASK(5,0) per sibling pcie-histb) - still 0x00 on ours. CONCLUSION: RC-side software is exhausted and register-verified; the failure is endpoint-side hardware (rail/PERST/refclk to the Hi5622). Multimeter procedure is next; recovery door armed, stock pair a healthy, box on W24n. | `mem-entries.md:27366` |
| 2026-11-22 |  | 2026-11-22 13:20 - PCIe: SPEED_CHANGE write-path and LTSSM ordering fixed (W24o/p/q/r), 0x80c now = 0x12c byte-identical to stock, LTSSM enabled LAST (vendor order), phase diagnostics added - and the LTSSM machine STILL never leaves detect.quiet. Root causes found this round: (1) the framework's dw_pcie_setup_rc sets PORT_LOGIC_SPEED_CHANGE after host_init (my earlier clear was overwritten) and runs dw_pcie_dbi_ro_wr_dis() so post-setup DBI writes need 0x8bc-bit0; (2) LTSSM was enabled before the framework's DBI batch (vendor enables it after ALL DBI writes). Both fixed: start_link now does ro_wr_en -> viewports -> clear SPEED_CHANGE -> ro_wr_dis -> LTSSM enable -> steady; post_init retrain is conditional on link_up. Diagnostics: "link training armed DEBUG0=0x003d4900" -> "post-link check DEBUG0=0x001c6200" - LTSSM[5:0] stays 0x00 while DEBUG0 higher fields churn (PHY alive). Live-DTB check: identical (sha 947ec62d; capability=0x03 is a runtime fixup by the vendor driver, not a flash delta). Userspace: gpio_switch empty, hsan scripts write nothing, shuangta branch has no GPIO step. Clock parent verified (pcie0_clk <- apb_clk == LUOFU_SRC_APB). Remaining: PORT_DEBUG0 field decode (ours 0x725000 vs stock-live 0x03f4a611) and the multimeter rail/PERST measurements. | `mem-entries.md:27370` |
| 2026-11-22 |  | 2026-11-22 13:45 - PCIe educated-guess space EXHAUSTED: bundle 1 (reset pulse+50ms settles, RC-header restore, mode re-assert) and bundle 2 (0x8bc bit0 left set, reg_int re-assert, LTSSM re-kick) both NEGATIVE. W24t (2bb45e9e) boots clean; 0x80c = 0x12c (stock-identical), LTSSM stays 0x00, config window 0xffffffff. All six remaining hypotheses consumed; every readable register matches the vendor live state; the write paths are verified. The failure is now conclusively endpoint-side physical: Hi5622 rails / PERST# / refclk. Multimeter procedure is the only path left. Box on W24t, stock pair a intact, recovery door armed. | `mem-entries.md:27374` |
| 2026-11-22 |  | 2026-11-22 14:10 - PHOTOS CRACK IT OPEN: the board is a TRIDUCTOR TR6560+TR5220 platform (= rebadged HiSilicon Hi5671Y + Hi5622V100). Silkscreen "WR-3000 2.0 / 300100297", main SoC marked TR6560PRCB ("TRIDUCTOR" brand), Wi-Fi marked TR5220GCF with 3x U.FL (J50/J51/J21), power section bottom-right: 2x 470uF 10V bulk caps + 242 buck inductor + barrel jack. Web research: Banana Pi BPI-WiFi6 Mini uses TR6560+TR5220 and has a PUBLIC OpenWrt BSP (github.com/nhz-io/BPI-WiFi6_Mini-THG6500-TAX2-OPENWRT-BSP) with target/linux/tr6560 (1227 files), tr6560 board DTS (reset_pcieN/power_pcieN/vol_en/wl_en/pmu_pwron GPIO model), prebuilt tri_pcie.ko (NOT stripped, 23 functions: tri_hal_crg_wifi_cfg, tri_hal_pcie_dev_reset_tr5220, tri_hal_pcie_reg_init, check_link...) and the SoC dtsi pcie@0x10145000 node with tri,pcie + iatu tables. CRG check: 0x14880020/34/40 identical stock-vs-ours (CRG+0x40=0 both; tri driver's crg_wifi_cfg = gate bits 12/13 at +0x20 which we already set). GPIO diff stock-vs-ours decodes as LED pins (20=wlan5g LED active-low on reference design), not Wi-Fi power - Cudy DTB has no board node and hi_pcie.ko has zero hardcoded GPIO/register addresses (all DT-driven), pcie-gpios empty. Hardware probe guide prepared: docs/incoming/hardware-probe/board-multimeter.jpg (annotated). Next: multimeter rails + disassemble tri_pcie.ko init/reg_init for any step our port misses. | `mem-entries.md:27378` |
| 2026-11-22 |  | 2026-11-22 14:30 - tri_pcie.ko (Triductor SDK, same silicon) fully decoded; last software variant (mode bit 22) tested (W24v) - STILL negative. SDK findings: install = unreset (CRG+0x28 bits 12/13, CRG+0x34 resets 12-19, misc+0x20 bit5) -> misc+0x1c \|= 0x800 (LTSSM enable, BEFORE mode/DBI) -> check_link -> reg_init (misc+0x04=0x200000, misc+0x18=0x08000000, misc+0x00=0x40200000 BIT22, misc+0x1c \|= 0x2000 gate, DBI cmd 0x00100007, iATU index-select writes, gate off, \|=0x02200000, mode restore 0x40000000, reg_int=0). Verified on hardware: CRG+0x28=0x02f8300b, CRG+0x2c/0x30, misc+0x20=0x20, misc+0x24/0x28 ALL IDENTICAL stock-vs-ours (U-Boot sets them). Cudy vendor hi_pcie.ko has zero hardcoded addresses (all DT-driven) and its set_mode = channel<<28. Mode bit22 variant W24v (bfdfbe8f) -> LTSSM still 0x00. SOFTWARE REGISTER PATH NOW EXHAUSTED. Remaining options: (a) build the tr6560 BSP baseline (software-only, heavy: adapt vendor DTB compatibles to tri,* drivers, wrap kernel for Cudy U-Boot), or (b) multimeter rail/PERST measurement. User prefers to avoid multimeter. | `mem-entries.md:27382` |
| 2026-11-22 |  | 2026-11-22 16:20 - BSP-kernel PCIe experiment: booted Triductor SDK kernel on the WR3000 v2, module route dead-ended; box restored. Path: cloned nhz-io/BPI-WiFi6_Mini-THG6500-TAX2-OPENWRT-BSP (1.2 GB, dl/ vendored); built target tr6560 (THG6500-TAX2, kernel 5.10.138) with OUR toolchain after disabling CONFIG_ATA (gcc-14 BUILD_BUG_ON in libahci) and CONFIG_MTD_TRIDUCTOR_NAND (tri_fmc_atags_parse oops at boot); wrapped zImage+THG6500 dtb into the Cudy kernel container (uImage + fip-slice.py make-trailer with BSP DTB as base - loader accepted it). Findings: (1) BSP kernel BOOTS on this board (SMP, console ttyS1, UBI) - hard confirmation TR6560 = HiSilicon Hi5671; (2) initramfs experiments: kernel has CONFIG_VFP=n (hard-float userspace SIGILL), CONFIG_DEVTMPFS=n, CONFIG_DEVMEM=n (no /dev/mem - register dumps impossible); freestanding soft-float init with mknod + ttyS1(minor 65!)+direct UART eventually printed via ttyS1; (3) tri_pcie.ko needs symbol tri_irq_set_affinity which NOTHING in the BSP provides (declared only in tri_os.h) - we added an exported in-kernel shim; (4) after the shim, init_module STILL fails rc=-22 (EINVAL) - prebuilt SDK module rejected by our kernel's loader (toolchain/config ABI); 6 RESET+TFTP recovery cycles consumed. Decision: stop BSP-kernel route (their kernel config blocks devmem/modules; more cycles needed for low value). Box restored: stock pair a (bootflag a), our image W24v on pair b; TFTP/captures stopped. | `mem-entries.md:27386` |
