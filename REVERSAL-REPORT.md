# REVERSAL REPORT — Cudy WR3000 v2.0 (HiSilicon luofu, board R116)

**Status:** consolidated engineering reversal report, 2026-11-18. **Host-only synthesis:** no
router, UART, TFTP, flash or bench tool was touched to produce it; every statement below is
derived from the committed record or from local read-only artifacts named in
[Section 10](#10-evidence-map-paths-and-commands).

**Pins:** root repository `beea531` (`beea531114d752aef196451dedb8ae73ce2e36c2`), published
submodule `4a2eddc` (`4a2eddc48d4f46c44dbd0bbcc27f0c7a2eb134cb`), both 2026-11-18 15:45 +07.
**Live state:** [`STATUS.md`](STATUS.md) is the only live status page; this report consolidates the
record at the pins above and must not be read as current bench state.

> **Addendum (2026-11-18 16:55, after the pins above).** The 0x21/slot-selector evidence review
> ([`opensource/docs/SELECTOR-0x21.md`](opensource/docs/SELECTOR-0x21.md)) corrected patch 017
> (low-byte RMW, bench-value provenance for 0x21) and added the target's boot-time pair recorder.
> The current final 001-017 container is 6,185,262 B sha256 `362ca4ec...`, kernel slice
> `e0826f8e...`, rootfs UBI `97ba0488...`; the `e869f105...`/`ea268be9...`/`1ae08540...` hashes
> in Section 8 describe the pre-correction build. Nothing has been booted or flashed either way. Physical invariants:
[`BENCH-FACTS.md`](BENCH-FACTS.md). Claim→artifact map: [`EVIDENCE-INDEX.md`](EVIDENCE-INDEX.md).
The append-only ledger is [`mem-entries.md`](mem-entries.md) (index:
[`mem-entries-INDEX.md`](mem-entries-INDEX.md)); the newest dated ledger entry wins over any older
claim.

> **Publication boundary.** This file lives in the private research repository. The published half
> ([`opensource/`](opensource/)) is **NOT READY** for publication: the vendor-object history purge
> is pending and the checklist in [`opensource/docs/PUBLISH-READINESS.md`](opensource/docs/PUBLISH-READINESS.md)
> is open. This report contains no vendor binaries, blobs, calibration data or credentials; it
> cites numeric offsets, symbol names and hash/size facts as reverse-engineering findings, which is
> the repository's existing evidence policy ([`opensource/NOTICE.md`](opensource/NOTICE.md),
> [`EVIDENCE-INDEX.md`](EVIDENCE-INDEX.md) "Publish boundary").

---

## 0. Executive summary (facts only)

1. **The board is not the MediaTek "WR3000 v1".** The enclosure label may say v1, but the PCB and
   firmware are the HiSilicon **luofu v2-class** design (board R116): Hi5671YV200 SoC (2× Cortex-A9),
   Hi5622v100 Wi-Fi over PCIe, 128 MB NAND, 128 MB DDR3, stock OpenWrt 22.03.6 on kernel 5.10.201.
   A WR3000 v1 (MediaTek MT7981) image cannot boot this board.
   [V] [`HARDWARE-IDENTITY.md`](HARDWARE-IDENTITY.md) "Identity"; [`BENCH-FACTS.md`](BENCH-FACTS.md) §1.
2. **The stock loader boots only FIP slices.** U-Boot 2022.07 runs
   `mtd read kernel${bootflag} ${loadaddr}; bootfip ${loadaddr}`; `bootfip` requires a uImage
   followed by a trailer containing the board DTB and DTBO overlays, and refuses to enter the kernel
   unless an overlay applies. The gate magic (`0xd7b7ab1e`), the 96-byte descriptor and the overlay
   match rule are decoded and implemented in a generator that reproduces both vendor containers
   byte-for-byte. **One attended boot of a *novel generated* trailer and full image is still owed.**
   [V] bootfip decode: [`opensource/target-skeleton/docs/TRAILER-FORMAT.md`](opensource/target-skeleton/docs/TRAILER-FORMAT.md)
   §2–§7; [U] novel-trailer acceptance.
3. **The stock firmware ships 58 GPL-declared kernel modules with no published source.** The GPLv2 §3
   request was sent 2026-10-01; no reply and no sent-copy/receipt is held. The follow-up letter is
   written and ready for the human to send. [V] [`opensource/docs/GPL-REQUEST.md`](opensource/docs/GPL-REQUEST.md)
   "Status", "Request tracking"; [`opensource/NOTICE.md`](opensource/NOTICE.md) "GPL note".
4. **The bench reversal reached its documented ceiling at lab kernel v17.** Our 5.10.201 kernel boots
   the vendor userspace, all 19 preloaded vendor modules return `ret=0`, `eth2` comes up at 1 Gbps
   and `br-lan` is created; then HSLINK creates/destroys `br-lan` in a loop (t≈33–35 s) and the
   console goes silent (≈54 s). The remaining gap is the vendor HYFI/bridge userspace contract: the
   vendor `sk_buff` ABI (+0x74/+0x78; `data` 0x118 vs 0xa0) plus vendor bridge patches (four hook
   call sites and a `net_bridge` cache) that are not in our tree. Bench fires are **stopped**
   (2026-11-18 06:50). [V] [`STATUS.md`](STATUS.md) §3; [`opensource/docs/VENDOR-SKB-BRIDGE-PORT.md`](opensource/docs/VENDOR-SKB-BRIDGE-PORT.md)
   §0–§3; ledger 2026-11-18 06:50. [U] whether a vendor-source arrival or a further port is needed.
5. **The upstream track now has a design/build layer but no submission.** A target/DTS/image design,
   a 17-patch kernel/binding series (001–017), a decoded trailer generator, a real OpenWrt target
   image built host-side (`make world` RC=0; final 001–017 sysupgrade 6,185,262 B, sha256
   `e869f105…`), a mock-tested A/B install path, and a review-form submission series
   ([`opensource/upstream/series-6.18/`](opensource/upstream/series-6.18/README.md): 17 patches,
   sequential `git am` clean, checkpatch 0 errors / 46 warnings / 4 strict checks, not submitted)
   exist. **Nothing has been flashed, installed or booted; the container carries a NOT FLASHABLE
   marker.** [V] [`STATUS.md`](STATUS.md) §3;
   [`opensource/docs/SKELETON-SMOKE.md`](opensource/docs/SKELETON-SMOKE.md) image/A-B sessions;
   ledger 2026-11-18 15:20/15:55. [U] every hardware gate in [Section 9](#9-remaining-gates).
6. **The published half is not publishable yet.** The ten vendor `.o` files removed from HEAD remain
   in history; the GPL-2.0 text/DCO/attribution work, the GPL receipt and the Wi-Fi/LAN-switch
   statements are open. The root repo stays private. [V] [`opensource/docs/PUBLISH-READINESS.md`](opensource/docs/PUBLISH-READINESS.md);
   [`EVIDENCE-INDEX.md`](EVIDENCE-INDEX.md) "Publish boundary".

---

## 1. Scope, method and evidence grading

### 1.1 Scope

This report covers the **bench reversal** (our kernel + the vendor userspace on this unit) and the
**upstream preparation** that the reversal produced (target/DTS/image design, driver/binding series,
FIP container work). It is not a release note, not a flash procedure, and not a claim that any
artifact is ready for use. The two tracks are deliberately separated:

1. **Bench reversal** — [`PLAN-FULL-REVERSAL.md`](PLAN-FULL-REVERSAL.md): replace the vendor kernel
   with our own while keeping the vendor userspace usable. The hybrid image is a research
   instrument, not a release. [V]
2. **Upstream submission** — [`opensource/docs/ROADMAP-OPENWRT.md`](opensource/docs/ROADMAP-OPENWRT.md),
   [`opensource/docs/TARGET-DESIGN.md`](opensource/docs/TARGET-DESIGN.md): own target, clean-room
   drivers, accepted upstream. **Not on track as a submission:** no target PR, no `dtbs_check`ed
   DTS, no install path executed, no Wi-Fi answer. Bench gates are not upstream progress. [V]

Out of scope here: Wi-Fi data-path bring-up (vendor-only today, [X]); the old device-mutating Wi-Fi
lane under `tools/archive/` (retired, do not use); any instruction to flash or fire.

### 1.2 Evidence grading (used throughout)

| marker | meaning in this repository |
| --- | --- |
| **[V]** | Verified from a named committed document/artifact or from a dated ledger entry, and reproducible host-side from the named path. Where the backing artifact is local-only (gitignored under `build/` or a local rootfs/firmware dump) the text says **local artifact**; that is not a fresh-clone receipt. |
| **[I]** | Inferred or planned: follows from [V] evidence but is not directly measured; a design decision. |
| **[U]** | Unknown/unmeasured. It must be closed by an attended measurement or a committed artifact before being used; do not design around it silently. |
| **[X]** | Externally blocked: vendor GPL source, a missing hardware dependency, or a decision outside this project (e.g. Wi-Fi licensing). |

This is the convention of [`opensource/docs/REMAINING-DRIVERS.md`](opensource/docs/REMAINING-DRIVERS.md) §0.1,
[`opensource/docs/LSW-SPEC.md`](opensource/docs/LSW-SPEC.md) §2.1 and
[`opensource/docs/PIE-DATAPATH.md`](opensource/docs/PIE-DATAPATH.md) intro. Every claim below carries
a source in parentheses; where a claim rests only on a local artifact, the text says so. The ledger
entry dates used as citations are headings in [`mem-entries.md`](mem-entries.md); the index line
numbers in [`mem-entries-INDEX.md`](mem-entries-INDEX.md) are given where they help.

### 1.3 Method (how the facts were obtained)

The reversal used four instruments, in this order of trust:

1. **The vendor's running kernel as the specification.** The only object in the world with this
   silicon doing the right thing is the stock system. Register values, MAC↔PHY mappings and
   netdev/bridge layouts were read from the live vendor system and from its module disassembly, not
   guessed from a schematic. Example: the MAC `PORT_MODE` value on a live 1 Gbps link is
   `0x010C0008` vs `0x000C0408` unlinked — a value the mainline driver for another IP revision would
   not have written. [V] [`opensource/docs/ETHERNET-BRINGUP-FRAMING.md`](opensource/docs/ETHERNET-BRINGUP-FRAMING.md) §3.
2. **Read-only disassembly/symbol analysis of the vendor's GPL-declared modules.** All `.ko` files
   are local, never-committed fixtures; analysis produced call graphs, table layouts, struct offsets
   and register arithmetic. This is GPL-compatible reverse engineering, not "clean-room".
   [V] [`opensource/docs/PIE-DATAPATH.md`](opensource/docs/PIE-DATAPATH.md) §2 and §13.2;
   [`opensource/docs/LSW-SPEC.md`](opensource/docs/LSW-SPEC.md) §2.3.
3. **Single-variable bench fires with a physical recovery door.** Every write was preceded by a
   written hypothesis, `tools/fire-preflight.sh` PASS, a READY recovery door and a human at the
   bench; the UART is read-only. This is the operating rule from [`BENCH-FACTS.md`](BENCH-FACTS.md) §2–§6
   and [`LESSONS.md`](LESSONS.md). [V]
4. **Host build/binding validation of a modern kernel.** The upstream preparation is compile- and
   schema-validated in an isolated OpenWrt `main` clone (commit `27663a0`, `linux-6.18.60`, GCC
   14.4.0, `CONFIG_WERROR=y`), with `dt_binding_check`, zero-warning DTS compiles, checkpatch and
   idempotent config re-derivation. [V] [`opensource/docs/SKELETON-SMOKE.md`](opensource/docs/SKELETON-SMOKE.md)
   sessions 1–13; per-lane `opensource/target-skeleton/docs/port-notes/*/SUMMARY.md`.

Two method rules were learned the hard way and are now enforced (they matter for grading every
boot claim):

- **A U-Boot header is not proof the kernel started.** Our slice is an *uncompressed* uImage and
  never prints `Uncompressing Linux` (stock does). A valid reading is U-Boot printing *our*
  `Data Size`/`Image Name` **followed by our kernel output**; `Uncompressing Linux` in a capture is
  evidence of the stock fallback, not of us. [V] [`BENCH-FACTS.md`](BENCH-FACTS.md) §5;
  [`CURRENT-TRUTHS.md`](CURRENT-TRUTHS.md) "Validity markers"; [`LESSONS.md`](LESSONS.md) rule 20.
- **The boot's last words are normally unreachable.** Our kernel's log dies with its RAM and the
  vendor fallback overwrites memory; pstore never registered on 5.10. This is why the reversal
  depended on surviving evidence cells and console captures. [V]
  [`opensource/docs/ETHERNET-BRINGUP-FRAMING.md`](opensource/docs/ETHERNET-BRINGUP-FRAMING.md) §4.

### 1.4 Provenance and boundaries (short form; details in §11)

- The vendor binaries, firmware blobs, extracted DTS, dumps and de-crypted Lua are **local evidence
  only**; they are gitignored and must never be committed or published. [V]
  [`EVIDENCE-INDEX.md`](EVIDENCE-INDEX.md) "Publish boundary"; [`AGENTS.md`](AGENTS.md) hard rules.
- The published `opensource/` half intentionally contains no vendor `.ko/.o`, blobs, calibration or
  dumps. It is nonetheless **NOT READY** because ten vendor `.o` files from a TR6560 BSP remain in
  its published history. [V] [`opensource/docs/PUBLISH-READINESS.md`](opensource/docs/PUBLISH-READINESS.md);
  [`opensource/NOTICE.md`](opensource/NOTICE.md).
- "Clean-room" was an inaccurate label for drivers transcribed from vendor GPL binary disassembly;
  the honest provenance statement is **GPL-compatible reverse engineering, drivers GPL-2.0**.
  [V] [`opensource/docs/PUBLISH-READINESS.md`](opensource/docs/PUBLISH-READINESS.md) "What was wrong" item 5.

---

## 2. Hardware and boot chain

### 2.1 Identity and hardware

| item | value | evidence |
| --- | --- | --- |
| Board | Cudy WR3000 v2.0, HiSilicon "luofu" v2-class, board **R116**; the retail enclosure/label may say WR3000 **v1** — that label is not a reliable identifier | [V] [`HARDWARE-IDENTITY.md`](HARDWARE-IDENTITY.md) "Identity"; [`BENCH-FACTS.md`](BENCH-FACTS.md) §1 |
| SoC | HiSilicon **Hi5671YV200** (also written Hi5671Y), 2× Arm Cortex-A9 (ARMv7-A), platform string `hsan luofu` | [V] [`HARDWARE-IDENTITY.md`](HARDWARE-IDENTITY.md); [`TARGET-DESIGN.md`](opensource/docs/TARGET-DESIGN.md) §2 |
| RAM | 128 MB DDR3; vendor DT `memory@80500000` reg `<0x80500000 0x7b00000>` (123 MB above the SoC window) | [V] [`TARGET-DESIGN.md`](opensource/docs/TARGET-DESIGN.md) §2; `opensource/docs/soc/vendor-dt-notes.md` §3 |
| NAND | 128 MB, ESMT **F50L1G41LC**: 2048-byte pages, 64-byte OOB, 128 KiB erase blocks; FMC controller at `0x10a20000` plus a 1 MiB window at `0x1c000000` | [V] [`TARGET-DESIGN.md`](opensource/docs/TARGET-DESIGN.md) §2; [`PLAN-FULL-REVERSAL.md`](PLAN-FULL-REVERSAL.md) Phase A (vendor sysfs geometry) |
| Wi-Fi | Hi5622v100 over PCIe: two endpoints `59e7:0005`; vendor modules `hi5622v100_wifi.ko`/`hi5622v100_plat.ko` plus a closed 928,920-byte `FIRMWARE.bin` | [V] [`TARGET-DESIGN.md`](opensource/docs/TARGET-DESIGN.md) §2, §8.3; [`EVIDENCE-INDEX.md`](EVIDENCE-INDEX.md) G5 row |
| Bootloader | **U-Boot 2022.07 for luofu**; accepts only FIP packages; the U-Boot prompt is unreachable on this unit (UART host→router TX dead) | [V] [`HARDWARE-IDENTITY.md`](HARDWARE-IDENTITY.md) "U-Boot capture"; [`BENCH-FACTS.md`](BENCH-FACTS.md) §3, §5 |
| Stock software | OpenWrt **22.03.6** vendor target `hisilicon/luofu`, kernel **5.10.201**, 58 vendor modules under `/lib/hisilicon/ko`, all declaring `license=GPL`; package arch `arm_cortex-a9`/musl | [V] [`STATUS.md`](STATUS.md) §1; [`opensource/docs/GPL-REQUEST.md`](opensource/docs/GPL-REQUEST.md) "Why this request is binding" |
| Kernel slot budget | 8,650,752 B per `kernela`/`kernelb` slot | [V] [`BENCH-FACTS.md`](BENCH-FACTS.md) §5; [`TARGET-DESIGN.md`](opensource/docs/TARGET-DESIGN.md) §3.3 |

Same-family white-label boards exist (Jeton AX3000 Core, V-SOL HG5013-4G), and the Triductor
TR6560 BSP is the same silicon family under different binding names. They are **reference only**:
this unit's own tree is `hsan-luofu`, and the BSP's `target/linux/tr6560` is a different board
family whose drivers bind `tri,*`. [V] [`HARDWARE-IDENTITY.md`](HARDWARE-IDENTITY.md) "Identity";
[`TARGET-DESIGN.md`](opensource/docs/TARGET-DESIGN.md) §4.1.

### 2.2 Physical invariants and forbidden actions

These are measured, not stylistic; breaking one has stranded the box.

- **UART is READ-ONLY.** Adapter FT232R at `/dev/ttyUSB0`, 115200 8N1, GND+TXD+RXD, 3.3 V logic,
  **swapped pin pair**. Router→host console output works; host→router is dead because one line's
  resistor is burnt, and repair is ruled out. Therefore there is no serial input: no typing, no
  `echo`/`printf` to the tty, no `screen`/`minicom`/`picocom`, no U-Boot abort-key floods, no
  read-write tty open (the `3<>` form). Capture with `tools/uart-capture.sh` (read-only, absolute
  log path). [V] [`HARDWARE-IDENTITY.md`](HARDWARE-IDENTITY.md) "UART: READ-ONLY"; [`BENCH-FACTS.md`](BENCH-FACTS.md) §3.
- **Bench link:** router LAN port `eth2` ↔ host USB-Ethernet `enp195s0f3u1`, 1 Gbps, no DHCP.
  The host adapter must carry `192.168.1.88/24` (loader `serverip` for TFTP recovery) and
  `192.168.10.44/24` (vendor LAN); NetworkManager must not manage it (a re-managed adapter strips
  the addresses and the board's ARP fails). Use `tools/bench-link.sh`. [V] [`BENCH-FACTS.md`](BENCH-FACTS.md) §2.
- **Recovery is physical:** power off, hold RESET, power on still holding → the console prints
  `RESET button is pressed for: 0/1/2 second(s)` → `Resetting...` → `recovery button press`, then
  the loader TFTPs `recovery.bin` from `192.168.1.88`. The counter appears only on a true power-on
  reset, never on the box's own watchdog resets. An agent cannot power-cycle or hold RESET: every
  fire is human-attended with the recovery door armed. [V] [`BENCH-FACTS.md`](BENCH-FACTS.md) §4;
  [`HARDWARE-IDENTITY.md`](HARDWARE-IDENTITY.md) "RESET button and recovery".
- **Recovery image:** `tftp/recovery.bin`, 20,975,775 bytes, md5
  `421114c8ea999c925b7aa79cc548af81`. [V] [`STATUS.md`](STATUS.md) §1; [`BENCH-FACTS.md`](BENCH-FACTS.md) §4.
- **Never:** flash a WR3000 v1/MediaTek image; write CA `0x400392f0`; read the RC misc window
  `0x10161000`; `rmmod` the vendor modules; replace `/etc/rc.d/luofu` wholesale (the vendor's
  `hi_kpinctrl` is load-bearing). [V] [`BENCH-FACTS.md`](BENCH-FACTS.md) §6; [`AGENTS.md`](AGENTS.md) hard rules.

### 2.3 Flash layout (stock, 128 MB NAND)

From the vendor base DTB (`opensource/docs/soc/vendor-dt-notes.md` §6; the same table in the lab DTS).
[V]

| # | label | offset | size | # | label | offset | size |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | esbc | 0x0 | 0x40000 | 9 | log | 0x900000 | 0x440000 |
| 1 | uboota | 0x40000 | 0x100000 | 10 | pstore | 0xd40000 | 0x40000 |
| 2 | ubootb | 0x140000 | 0x100000 | 11 | **kernela** | 0xd80000 | 0x840000 |
| 3 | enva | 0x240000 | 0x40000 | 12 | **kernelb** | 0x15c0000 | 0x840000 |
| 4 | envb | 0x280000 | 0x40000 | 13 | **rootfsa** | 0x1e00000 | 0x1740000 |
| 5 | fac | 0x2c0000 | 0x200000 | 14 | **rootfsb** | 0x3540000 | 0x1740000 |
| 6 | bdinfo | 0x4c0000 | 0x40000 | 15 | **rootfs_data** | 0x4c80000 | 0x1600000 |
| 7 | cfga | 0x500000 | 0x200000 | 16 | upgrade | 0x6280000 | 0x1d80000 |
| 8 | cfgb | 0x700000 | 0x200000 | | | | |

`kernela`/`kernelb` are 8,650,752 B each; `rootfsa`/`rootfsb` 24,313,856 B each. The vendor system
formats `rootfs_data` as JFFS2 and uses it as the persistent overlay; the rootfs slots hold a static
squashfs UBI volume named `squashfs`. The lab 5.10 DTS added an 18th scratch partition inside
`upgrade`; that is a bench instrument and must not appear in an upstream DTS.
[V] [`TARGET-DESIGN.md`](opensource/docs/TARGET-DESIGN.md) §3.3; [`PLAN-FULL-REVERSAL.md`](PLAN-FULL-REVERSAL.md)
Phase A; [`BENCH-FACTS.md`](BENCH-FACTS.md) §5.

Relevant MMIO landmarks (orientation only; each is specified in the cited document):

| block | window / fact | source |
| --- | --- | --- |
| SYSCTRL page / A/B selector | `0x10100000`; selector cell `0x10100C08`; 32-bit low byte selects the boot pair | [V] [`TARGET-DESIGN.md`](opensource/docs/TARGET-DESIGN.md) §3.4; `opensource/target-skeleton/docs/port-notes/abinstall/SUMMARY.md` §1 |
| CRG clock/reset | `0x14880000`; shared page modelled as one syscon+simple-mfd; reset class is **active-low** (measured `0x14880034 = 0x000ff309` with both RCs up) | [V] [`STATUS.md`](STATUS.md) §3 (PCIe/014 entry); patch `004`/`014` |
| FMC (SPI-NAND) | `0x10a20000` + 1 MiB window at `0x1c000000` | [V] [`TARGET-DESIGN.md`](opensource/docs/TARGET-DESIGN.md) §2 |
| PIE packet engine | `0x10a70000–0x10a7ffff`, 64 KiB; board `hwver = <0x250>` | [V] [`opensource/docs/PIE-DATAPATH.md`](opensource/docs/PIE-DATAPATH.md) §3 |
| LSW switch | 15 × 512 KiB MMIO windows through a synthetic 256-slot module-id table; queue/flow DDR regions are not MMIO | [V] [`opensource/docs/LSW-SPEC.md`](opensource/docs/LSW-SPEC.md) §5; patch `016` |
| GEMAC / MDIO | `eth2` = `0x14480000` with PHY `mdio0:04`; `0x14380000` is unused by the vendor. Vendor map: `14380000→phy2, 14400000→phy3, 14480000→phy4, 14500000→phy5` | [V] [`opensource/docs/ETHERNET-BRINGUP-FRAMING.md`](opensource/docs/ETHERNET-BRINGUP-FRAMING.md) §2 |
| pinctrl / thermal | pinctrl windows `0x14900100`/`0x14940000`; thermal sensor `0x14900500` (hwver 3) | [V] [`opensource/docs/REMAINING-DRIVERS.md`](opensource/docs/REMAINING-DRIVERS.md) §2, §3 |
| PCIe | two DWC-based root complexes; Wi-Fi endpoints `59e7:0005`; RC misc window is write-only/forbidden to read; unaligned/sub-word accesses fault | [V] [`TARGET-DESIGN.md`](opensource/docs/TARGET-DESIGN.md) §8.2; [`BENCH-FACTS.md`](BENCH-FACTS.md) §6 |

### 2.4 The boot chain, decoded

#### 2.4.1 U-Boot and the FIP package

The stock environment carries `bootcmd=mtd read kernel${bootflag} ${loadaddr};bootfip ${loadaddr}`
with `loadaddr = 0x83200000` and `bootflag = a|b`. A bare uImage is refused before kernel entry:
`bootfip` accepts a **uImage followed by a trailer** that carries the vendor base DTB and a
DTBO/overlay container. [V] [`TARGET-DESIGN.md`](opensource/docs/TARGET-DESIGN.md) §3.1;
[`BENCH-FACTS.md`](BENCH-FACTS.md) §5; same strings in the local env dump `dumps/router-20261108/enva.bin`.

Slice shape:

```
uImage header (0x40 B) | kernel payload (zImage; + appended DTB in the lab lane) | trailer
                                                                                  ^ 0x40 + ih_size
```

The lab uImage identity is `mkimage -A arm -O linux -T kernel -C none -a 0x80608000 -e 0x80608000
-n Linux-5.10.201`; the target lane builds `Linux-6.18.60` with the same load/entry. The loader
stages the slot at `0x83200000`; the decompressor computes the load address as
`(pc & 0xf8000000) + TEXT_OFFSET`, which with `TEXT_OFFSET = 0x00608000` is `0x80608000`.
[V] [`TARGET-DESIGN.md`](opensource/docs/TARGET-DESIGN.md) §3.2; ledger PHASE 93–100 (2026-10-11);
patch `003`.

#### 2.4.2 The pre-entry gate (`bootfip` applier), decoded 2026-11-18

From disassembly of `mtd1/2` U-Boot (`dumps/router-20261108/uboota.bin`, local artifact; U-Boot
2022.07 for luofu), the uImage path is:

1. uImage magic `0x27051956` checked; architecture must be ARM; `ih_size != 0`.
2. `base_dtb = image + 0x40 + ih_size`; its FDT header must be valid.
3. `applier(base_dtb, base_dtb + base_totalsize)` must return 0, otherwise
   `boot apply overlay fail` and **no jump**.
4. The applier reads the gate word at `base_dtb + base_totalsize` and requires it to equal
   **`0xd7b7ab1e`**; it checks container total ≤ 8 MiB, overlay count ≤ 64, and three hard-coded
   `32` fields; for each descriptor entry it validates the overlay FDT (≤ 128 KiB), matches
   `vendor_id` against the environment `vendorid` (stock `hsan`), and matches the overlay's
   `compatible`/`board_id` against an 11-row family table plus the board strap (or numeric env
   `boardid`). The **first matching overlay** is applied with libfdt; later entries are ignored.
   [V] [`opensource/target-skeleton/docs/TRAILER-FORMAT.md`](opensource/target-skeleton/docs/TRAILER-FORMAT.md)
   §3–§6; [`TARGET-DESIGN.md`](opensource/docs/TARGET-DESIGN.md) §3.1–§3.2; ledger PHASE 95/99
   (2026-10-11), 2026-10-14 "The boot guard fell".
5. **uImage hcrc/dcrc are not checked** on this path (only `image_print_contents` is called), and
   `ih_load`/`ih_ep` are printed but never compared. This is why the 96-byte-short 40,732-byte lab
   trailer boots. [V] [`TRAILER-FORMAT.md`](opensource/target-skeleton/docs/TRAILER-FORMAT.md) §4.

The trailer anatomy (2.4.15 vendor container, 40,828 B): 31,220 B vendor base DTB + **96-byte
descriptor** (32-byte header + 2 × 32-byte entries) + overlay 0 (4,592 B, `board_id=0`) + overlay 1
(4,920 B, `board_id=3`, adds `model = "hsan luofu/R116"`). The fixed lab artifact is 40,732 B =
the first 40,732 bytes of exactly that container; the missing 96 bytes are inside the last overlay's
zero padding and contain no FDT structure. Both tail sizes have booted on this bench; **why the lab
artifact was cut to 40,732 is not documented** ([I]: the arithmetic 31,220+4,592+4,920). The
flashed stock slots carry a further 628-byte region after the container (`bootfip` never reads it)
whose meaning is [U]. [V] [`TRAILER-FORMAT.md`](opensource/target-skeleton/docs/TRAILER-FORMAT.md)
§2.1–§2.4, §7–§8; [`TARGET-DESIGN.md`](opensource/docs/TARGET-DESIGN.md) §3.2.

A **byte-exact generator exists**: `opensource/target-skeleton/tools/fip-slice.py make-trailer`
emits a fail-closed trailer from user-supplied base DTB + overlays and reproduces the vendor 2.4.15
(40,828 B) and 2.5.24 (40,968 B) containers byte-for-byte; the vendor 2.5.24 container is a second
data point confirming the layout. [V] [`TRAILER-FORMAT.md`](opensource/target-skeleton/docs/TRAILER-FORMAT.md)
§2.3, §9; [`EVIDENCE-INDEX.md`](EVIDENCE-INDEX.md) FIP row. Remaining [U]: the semantic meaning of
the hard-checked `32` constants, the 628-byte slot region, and **one attended boot of a novel
generated trailer**.

#### 2.4.3 Slot selection, environment and failover

- Selector cell: SYSCTRL `0x10100C08`. Measured values: **`0x10` = A pair** (`kernela` mtd11 +
  `rootfsa` mtd13), **`0x11` = B pair** (`kernelb` mtd12 + `rootfsb` mtd14); **`0x00`** reads at a
  true power-on before the loader initialises it; **`0x21`** is the vendor "sysenv"
  manual/recovery-B handover written by the vendor slot-switch recipe. A manual **A-side** handover
  value (`0x20?`) is **not established** [U]. The loader's own console prints `bootreg init, set 10`
  (A) or `set 11` (B). [V] [`BENCH-FACTS.md`](BENCH-FACTS.md) §5; `opensource/target-skeleton/docs/port-notes/abinstall/SUMMARY.md` §1.
- Environment blocks `enva`/`envb` (mtd3/mtd4, 128 KiB, layout `crc32-LE(4) | flags(1) | data(131,067)`)
  are **re-stamped by the loader from the cell**; the bench found the env `bootflag` to be an
  output, and the "plain `fw_setenv` works" path to be a trap: `/bin/fw_setenv` on this image is a
  symlink to `/bin/fw_printenv`, so an earlier `fw_setenv` was a no-op. Treat the cell/console pair
  as the measured state. The in-boot cell state after a handover and the env re-stamp are [U] for
  the install path. [V] [`BENCH-FACTS.md`](BENCH-FACTS.md) §5; `abinstall/SUMMARY.md` §1.
- Failover: a failed handover is followed by a failover read of the other slot; the older claim
  "a failed boot leaves a status word that makes bootfip reject the slot" is **not supported** by
  the 2026-11-16 captures. Do not build a rollback plan on it; rollback is "keep the other pair
  bootable and switch back". Separately, U-Boot's own `bootflag` fallback path is fragile — it has
  printed the header and then faulted inside U-Boot for both a 2.78 MB and a 2.96 MB kernel.
  [V] [`BENCH-FACTS.md`](BENCH-FACTS.md) §5; [`HARDWARE-IDENTITY.md`](HARDWARE-IDENTITY.md) "RESET button and recovery".

#### 2.4.4 Recovery and the console

Recovery is the physical RESET-counter path plus TFTP (see §2.2). The Linux console itself was
solved earlier: the stock console login is gated by `bdinfo dbg`; `/lib/preinit/99_00_console`
deletes the `::askconsole:` line unless it returns OK and `/etc/rom_release` forces FAIL. Patching
the overlay copy of `libbdinfo.so` so `bdinfo_check_dbg` at `0x2228` returns 0 keeps the line and
starts `/sbin/askfirst` — this is why console *output* is available; it does not give serial input.
[V] [`HARDWARE-IDENTITY.md`](HARDWARE-IDENTITY.md) "UART: READ-ONLY" (history). The practical root
path is SSH over LAN; recovery is the physical door.

#### 2.4.5 Boot-chain unknowns (explicit)

| unknown | status | where it matters |
| --- | --- | --- |
| One attended boot of a **novel generated trailer** (does the stock loader accept the generator's output?) | [U] | target image acceptance, §8–§9 |
| How `root=`/`ubi.*` reaches the kernel; whether the stock loader overrides `/chosen/bootargs` from its environment | [U] | rootfs mount design, [`TARGET-DESIGN.md`](opensource/docs/TARGET-DESIGN.md) §5.6 |
| Semantic names of descriptor fields +8/+12/+20 (values/32-checks known), +24/+28 and entry words +8..+28 | [U] | generator hard-codes required constants; safe today, not understood |
| Meaning of the 628-byte post-container stock region; why the lab tail is 40,732 B | [U]/[I] | reproducibility documentation |
| Exact hardware strap-bit meaning for `board_id` (code path decoded; physical strap source inferred) | [I] | generator must assert `board_id = 3` for this board |
| Whether the stock TFTP `recovery.bin` write path can install an arbitrary image or expects a vendor container | [U] | first-install path, §8.6 |

---

## 3. Stock firmware, GPL obligations and request history

### 3.1 Stock images and versions

- Recovered official images: **2.4.15** (`WR3000V2-R116-2.4.15-20251030-114751`) and **2.5.24**;
  both extracted under `rootfs-2.4.15/` and `rootfs-2.5.24/` (local, gitignored). The live boot
  reports OpenWrt 22.03.6, kernel `5.10.201 #0 SMP Sat Nov 25 18:18:57 2023`, image
  `WR3000V2-R116-2.4.15-20251030-114751`. [V] [`HARDWARE-IDENTITY.md`](HARDWARE-IDENTITY.md) "Correct firmware";
  [`STATUS.md`](STATUS.md) §1.
- The LSW/CFE/PIE modules are byte-identical between the two rootfs trees (`sha256sum` equal for the
  LSW modules plus `hi_kcfe_pub`/`hi_kpie`): the 2.5.24 stock firmware is the same switch/queue
  generation as 2.4.15. [V] [`opensource/docs/LSW-SPEC.md`](opensource/docs/LSW-SPEC.md) §2.2.
- System shape: squashfs UBI rootfs (`squashfs` volume), JFFS2 `rootfs_data` overlay,
  procd/preinit/`mount_root`, vendor rc.d chain, `/etc/rc.d/luofu` module loader, vendor userspace
  (`hsan_*`, `hyfibrd`, `hi_cfm`, LuCI). §4 describes the architecture. [V]
  [`PLAN-FULL-REVERSAL.md`](PLAN-FULL-REVERSAL.md) Phase C; [`opensource/docs/VENDOR-STACK-ON-MAINLINE.md`](opensource/docs/VENDOR-STACK-ON-MAINLINE.md).

### 3.2 The GPL obligation is real and specific

Every vendor kernel module in the stock image declares itself GPL. Measured on the local fixtures
(never committed):

```
$ strings rootfs-2.4.15/lib/hisilicon/ko/hi_kmac.ko | grep license=
license=GPL
```

This is true of the 58 modules under `/lib/hisilicon/ko`, including `hi_kmdio`, `hi_kphy`, `hi_kmac`,
`hi_lsw_pub/dp/pfe`, `hi_swa`, `hi_kcfe_*`, `hi_khslink`, `hi_kpie`, `hi_crg`, `hi_flash`,
`hi_wdt`, `hi5622v100_wifi`, and the rest. They are linked against the Linux kernel, export and
consume kernel symbols, and ship under a GPL declaration: GPLv2 §3 obliges the distributor to
provide corresponding source to recipients. GPL'd userspace components (`hsan_*` scripts,
`hi_appenv` tools, the modified LuCI Lua) are in the same request.
[V] [`opensource/docs/GPL-REQUEST.md`](opensource/docs/GPL-REQUEST.md) "Why this request is binding";
[`EVIDENCE-INDEX.md`](EVIDENCE-INDEX.md) GPL-obligation row; [`opensource/NOTICE.md`](opensource/NOTICE.md)
"GPL note".

### 3.3 Request history (as of the pins)

| date | action | channel | status / evidence |
| --- | --- | --- | --- |
| 2026-10-01 | Original GPLv2 §3(a)/3(b) request sent | email to `support@cudy.com` (address web-verified 2026-11-18) | **SENT** — no sent copy, receipt or reply is held in the repository. Recorded in the parent ledger, `PORT-SURFACE.md`, `PORT-PLAN.md`, `PUBLISH-READINESS.md` item 3. |
| 2026-10-09 | Jeton (same-SoC, separate obligor) letter rewritten | draft email to `support@jeton-tech.ru` | **DRAFT — NOT SENT**; `JETON-GPL-EMAIL.txt` (parent repo). |
| 2026-11-17 | Status reconciled as "sent, not draft"; evidence gap recorded | repository edit | **RECORDED** in `PUBLISH-READINESS.md` item 3 and the published-half commit `fbd4a72`. |
| 2026-11-18 | Follow-up message + escalation ladder written; contact facts re-verified by web | this repository | **READY TO SEND — NOT SENT**. Cudy GPL page `https://www.cudy.com/pages/gpl` returns HTTP 404; the Download Center is script-rendered and a plain fetch shows no product/GPL text. |
| 2026-11-18 | Project owner confirmed in session that the original request was sent at project start and no reply was ever received | direct statement | **CONFIRMED BY SENDER** — still no sent copy/receipt. |
| (pending) | Reply, delivery receipt or auto-reply | — | **NOT RECEIVED**; save it in the repo and update the tracking table. |

[V] [`opensource/docs/GPL-REQUEST.md`](opensource/docs/GPL-REQUEST.md) "Status", "Contact and channel
facts", "Request tracking", "Evidence trail". The **single biggest evidence gap** is that the sent
message, its delivery receipt and any reply are not held; a reviewer will check the tracking table.
The requested-artifacts checklist (11 items) records what is needed and why: items 1–4 unblock the
bench lane (vendor kernel tree/config/patches, GPL module sources, the vendor `net/bridge` patch
series, the vendor `struct sk_buff` definition); items 5–6 unblock the upstream image (DTS/DTBO +
U-Boot/FIP packaging); items 7–8 are for the Wi-Fi decision (driver sources + firmware terms);
items 9–11 cover GPL userspace, build scripts and a written licence statement for anything the
vendor says is not GPL. [V] [`opensource/docs/GPL-REQUEST.md`](opensource/docs/GPL-REQUEST.md)
"Requested artifacts checklist".

### 3.4 What the stock firmware gave the project

- **Root access for research** through two documented stock-level findings: the LuCI `systime` page
  command-injection sink (gist + `patched/*.lua`, `rpc_inj.json`) and the broker/MQTT JWT channel
  forged from the `bdinfo` secret (`gist-cudy-wr3000v2-mqtt-jwt.md`, `tools/forge_jwt.py`,
  `tools/mqtt_takeover.py`). [V] [`EVIDENCE-INDEX.md`](EVIDENCE-INDEX.md) "Broker/JWT root channel",
  "Web-UI RCE sink". These are research/root paths on the stock firmware, not part of the reversal
  deliverable, and must not be published as attack tooling without review.
- **The vendor userspace as a test target**: the bench reversal's milestone M5 is exactly "vendor
  userspace runs on our kernel", and the 2026-11-14 stack reached it (G3/G4/G6).
  [V] [`STATUS.md`](STATUS.md) §2.
- **Calibration data**: Wi-Fi calibration snapshot/restore tooling (`tools/wifi-cal-snapshot.sh`,
  `tools/wifi-cal-restore.sh`, dry-run by default) exists so experiments do not destroy the radio
  calibration; restore requires a verified `MANIFEST.sha256`. [V] [`AGENTS.md`](AGENTS.md) hard rules;
  [`BENCH-FACTS.md`](BENCH-FACTS.md) §4.

---

## 4. Vendor kernel and userland architecture

### 4.1 Boot to userspace

```
U-Boot 2022.07
  -> FIP slice: uImage + trailer (base DTB + DTBO overlays; bootfip gate)
  -> Linux 5.10.201 (vendor kernel)
  -> /sbin/init = procd
       -> preinit, mount_root: rootfs squashfs from rootfsa/rootfsb (UBI volume "squashfs")
          + persistent overlay from rootfs_data (JFFS2)
       -> /etc/rc.d/S10boot ... S18hyfibrd ... S20network ... S95done
       -> /etc/rc.d/luofu: vendor module load order (below)
       -> netifd/OpenWrt userspace: br-lan 192.168.10.1, WiFi vaps, hostapd, dropbear, uhttpd, ...
```

[V] [`PLAN-FULL-REVERSAL.md`](PLAN-FULL-REVERSAL.md) Phase C (vendor preinit/`mount_root`/procd run
to S95done on our kernel, build #162); [`opensource/docs/VENDOR-STACK-ON-MAINLINE.md`](opensource/docs/VENDOR-STACK-ON-MAINLINE.md)
"The load order"; [`STATUS.md`](STATUS.md) §2 G3.

### 4.2 Vendor module dependency graph

The load order in `/etc/rc.d/luofu` **is** the dependency graph; `depends=` fields in the module
fixtures corroborate it. The bench line's dependency findings:

```
ksecurec                      (safe-C memory/string helpers: memcpy_s, sscanf_s, mem_section, ...)
  |
hi_basic                      (hi_dfx printing/registration; base layer)
  |-- hi_kpinctrl  hi_sysctrl  hi_acp  hi_kpie
  |     hi_kpie  -------------> rings/DMA/NAPI, hi_net_dev_* API, g_api_priv port table
  |-- hi_lsw_pub -> hi_lsw_dp -> hi_lsw_pfe        (queue/classification/forwarding engine)
  |-- hi_kmdio  -> hi_kphy  -> hi_kmac             (MDIO bus, PHYs, per-port MAC netdevs)
  |-- hi_kcfe_pub -> hi_kcfe_lrn (+l3/l4/mc/mc_list/vxlan)
  |                    -> hi_kcara -> hi_khslink   (CFE service/learning; PFE adapter; HSLINK)
  |-- hi_swa                                        (switchdev + rootif glue; loaded last)
  |-- hyfi_bridging (+ hi_netif, hi_kmsgcenter, hi_kipc)   (HYFI accelerated-bridge contract)
  └── Wi-Fi: hi5622v100_plat / hi5622v100_wifi (+ hcc/wifidrv components)
```

Measured `depends=` examples: `hi_kmac` → `hi_kpie,hi_basic,ksecurec`; `hi_kpie` →
`ksecurec,hi_basic`; `hi_lsw_pub` → `ksecurec,hi_basic`; `hi_lsw_dp` →
`hi_lsw_pub,hi_basic,hi_kpie,ksecurec`; `hi_lsw_pfe` → `hi_lsw_pub,hi_lsw_dp,hi_basic,ksecurec`;
`hi_kcfe_pub` → `hi_kpie,hi_basic,ksecurec`; `hi_swa` → `hi_kcfe_pub,hi_basic,ksecurec,hi_kpie,hi_kcfe_lrn`.
[V] [`opensource/docs/LSW-SPEC.md`](opensource/docs/LSW-SPEC.md) §2.2 (fixture sizes/`depends=` table);
[`mem-entries.md`](mem-entries.md) 2026-11-17 10:15 (symbol failures in dependency order),
2026-11-17 17:45 (ksecurec/hi_basic prerequisites); [`opensource/docs/VENDOR-STACK-ON-MAINLINE.md`](opensource/docs/VENDOR-STACK-ON-MAINLINE.md)
"The load order".

A subtle but important point for the bench line: `hi_swa` tolerates nothing being absent — without
the CFE/learning base it fails with `Unknown symbol hi_cfe_flush_by_mac`, `hi_net_get_port`,
`hi_cfe_add_subif`, `ppp_get_relate_dev`, `memcpy_s`, `sscanf_s` and more. Consequently the
initramfs init loads the exact vendor sequence by `finit_module` before the pivot.
[V] [`opensource/docs/VENDOR-STACK-ON-MAINLINE.md`](opensource/docs/VENDOR-STACK-ON-MAINLINE.md);
`tools/lab-src/kbuild/init-vendorroot.c`.

### 4.3 Roles in the wired data path (this determines the driver split)

The measured vendor architecture is not "one MAC driver":

```
per-port netdev + phylink           <- hi_kmac (alloc_etherdev_mqs, register_netdev,
   |                                   hi_net_dev_probe(dev,&desc8); ndo_start_xmit tail-calls
   |                                   hi_net_dev_xmit(skb, dev+0x5a8))
   v
PIE packet engine (hi_kpie)         <- DMA rings, NAPI, per-port context table g_api_priv,
   |                                   queue handle + 8-byte port descriptor; unregistered "cpu%d"
   |                                   NAPI-container netdev
   v
internal LSW (hi_lsw_*/hi_kcfe_*)    <- queue manager (EQM/EPS/IPS), port/qid maps,
   |                                   classification/forwarding tables (IFC/L2/...)
   v
GEMAC port -> MDIO PHY -> RJ45

CFE software plane (hi_kcfe_pub + hi_kcfe_lrn* + hi_kcara) sits above and programs the same
PFE tables; HSLINK/HYFI are the userspace-facing management/offload contracts.
```

[V] [`opensource/docs/REMAINING-DRIVERS.md`](opensource/docs/REMAINING-DRIVERS.md) §1.1;
[`opensource/docs/PIE-DATAPATH.md`](opensource/docs/PIE-DATAPATH.md) §2. A clean-room port must
reproduce all four roles with our own drivers (MAC/phylink netdev, PIE rings/DMA/NAPI, LSW
queue/forwarding, and — optionally — its own software forwarding policy); the vendor modules may not
be loaded. [I] [`opensource/docs/LSW-SPEC.md`](opensource/docs/LSW-SPEC.md) §3.

### 4.4 Userspace contracts that leak into the kernel design

| userspace | what it expects from the kernel | evidence |
| --- | --- | --- |
| `hsan_appm`, `wandetect`, hotplug `08-wan-detect` | writes `/proc/hsan/net/swa/wan_port`; expects the rootif chain (`hi_swa_add_rootif` → `hi_cfe_add_rootif` → `hi_net_get_port`) to succeed | [V] [`opensource/docs/VENDOR-SKB-BRIDGE-PORT.md`](opensource/docs/VENDOR-SKB-BRIDGE-PORT.md) §3.4; ledger 2026-11-17 18:55 |
| `hyfibrd` (+ `hyfi_bridging.ko`) | vendor-private netlink protocol; HYFI accelerated-bridge state; four exported `br_*` hook pointer variables; `net_bridge` cache at `netdev_priv+0x10` | [V] [`opensource/docs/VENDOR-SKB-BRIDGE-PORT.md`](opensource/docs/VENDOR-SKB-BRIDGE-PORT.md) §2–§3 |
| HSLINK (`hi_khslink`/`hi_swa`) | owns interface lifecycle: watches netdev events, destroys/recreates interfaces; console tag `[HSLINK]` | [V] same doc §1 glossary, §2.2; ledger 2026-11-18 06:50 |
| `hi_cfm`, `/proc/hsan/*`, `/proc/hsan/cfe/*` | CFE interface/FDB/port dump formats | [V] [`opensource/docs/LSW-SPEC.md`](opensource/docs/LSW-SPEC.md) §9.1, §12.2 |
| netifd/UCI | standard Linux bridge/netdev semantics; the vendor bridge is patched | [V] [`opensource/docs/VENDOR-SKB-BRIDGE-PORT.md`](opensource/docs/VENDOR-SKB-BRIDGE-PORT.md) §3.3–§3.4 |
| `hi_cfm` read-only DFX dumps | live port/queue/interface names, useful for the D0/D1b inventory | [V] [`opensource/docs/LSW-SPEC.md`](opensource/docs/LSW-SPEC.md) §12.2 |

A clean-room port **does not reproduce** the rootif/CFE userspace contract; the design position is
standard Linux switchdev on per-port netdevs, with our own userspace. [I]
[`opensource/docs/LSW-SPEC.md`](opensource/docs/LSW-SPEC.md) §9.1–§9.5.

### 4.5 ABI contracts that dominate the hybrid lane

Two kernel ABI deltas make the vendor modules unloadable/unsafe on a stock 5.10 tree, and one
kernel-patch series cannot be reconstructed offline:

1. **`CONFIG_ARM_MODULE_PLTS` / `.plt` sections.** All ~60 vendor modules were built for
   `CONFIG_ARM_MODULE_PLTS=n` with `-mlong-calls`, so they contain no `.plt`/`.init.plt`. A stock
   multi_v7 kernel rejects them at load (`module PLT section(s) missing`). The working fix adds
   zero-size sections with `objcopy` and constrains `module_alloc` to the near region; patching the
   loader check itself broke boots 5/5 while controls booted 3/3. [V]
   [`opensource/docs/VENDOR-STACK-ON-MAINLINE.md`](opensource/docs/VENDOR-STACK-ON-MAINLINE.md)
   "Why the modules do not load".
2. **`finit_module` syscall number is 379 on ARM, not 350** (350 is x86_64; calling it returns
   `-EINVAL` before the module is read). [V] same doc, "Why finit_module returns EINVAL".
3. **Vendor `net_device`/`sk_buff` layouts and bridge patches** — the subject of §5.2–§5.4.

The lab kernel therefore carries bench-only edits that must not be submitted: near-region
`module_alloc`, boot breadcrumbs/TEXT_OFFSET edits, vermagic tag removal, JFFS2 edits, slab exports,
network ABI edits (`netdevice.h`, `skbuff.h`, `net/core/*`, `net/bridge/br_fdb.c`), WEXT under
`COMPILE_TEST`, UBI `compat=5` acceptance, the lab config and the initramfs vendor-stack loader.
[V] [`TARGET-DESIGN.md`](opensource/docs/TARGET-DESIGN.md) §7.2; `tools/lab-src/FILES`
(43 modified source files, guarded by `tools/check-lab-src.sh`).

---

## 5. RE findings worth publishing

This section collects the reverse-engineering results that are publishable as *findings* (numbers,
names, structures, method) as opposed to vendor binaries. The repository's rule: the `.ko` fixtures
stay local; offsets, symbol names and code shape may be published. [V]
[`opensource/docs/VENDOR-SKB-BRIDGE-PORT.md`](opensource/docs/VENDOR-SKB-BRIDGE-PORT.md) header;
[`opensource/target-skeleton/docs/TRAILER-FORMAT.md`](opensource/target-skeleton/docs/TRAILER-FORMAT.md) header.

### 5.1 HSLINK and the rootif contract (a userspace compatibility layer, not hardware)

**Finding.** The vendor "failed to add rootif" path is a userspace→kernel→software-bookkeeping
chain, not a hardware API. [V] [`opensource/docs/VENDOR-SKB-BRIDGE-PORT.md`](opensource/docs/VENDOR-SKB-BRIDGE-PORT.md)
§3.4; ledger 2026-11-17 18:55.

| step | what happens | evidence |
| --- | --- | --- |
| userspace | `hsan_appm:130`, `wandetect`, hotplug `08-wan-detect` write `/proc/hsan/net/swa/wan_port` | [V] ledger 2026-11-17 18:55 |
| `hi_swa` | `swa_dfx_update_wanif` → `hi_swa_add_rootif` | [V] ledger; `hi_swa.ko` defines both symbols |
| `hi_kcfe_pub` | `hi_cfe_add_rootif` registers a **named Linux netdev** into a 32-entry CFE table | [V] [`opensource/docs/LSW-SPEC.md`](opensource/docs/LSW-SPEC.md) §9.1 |
| `hi_kpie` | `hi_net_get_port(dev,&ports,2)` fails `0x90000000` unless the netdev is in `g_api_priv`; that table is filled only by `hi_net_dev_probe(dev,&desc8)` from `hi_kmac` using the DT port id (ports 8..12) | [V] ledger 2026-11-17 18:55; [`opensource/docs/PIE-DATAPATH.md`](opensource/docs/PIE-DATAPATH.md) §2.2 |
| `hi_cfe` | writes a CFE hook into `dev+0x21c` and assumes the **vendor** `net_device` layout | [V] ledger 2026-11-17 18:55 |

The CFE uses rootif bindings to attach VLAN filters, sub-interfaces, stats rules, tag actions and FDB
entries to bridges/VLANs created by OpenWrt; the userspace hotplug scripts read
`/proc/hsan/cfe/intf/dump_intf`. The shipped `hi_swa` switchdev handlers are **stubs**
(`swa_switchdev_event`, `swa_handle_port_obj_add/del`, `swa_netdevice_check` are each
`mov r0,#0; bx lr`), so the shipped firmware registers the notifier and does nothing with
bridge/VLAN objects — real forwarding is the CFE learning stack through the PFE tables. The
`g_intf_bypass=1` then load-`hi_swa` order confirms the rootif layer is a compatibility layer.
[V] [`opensource/docs/LSW-SPEC.md`](opensource/docs/LSW-SPEC.md) §1, §4.7, §9.1.

**Why it matters.** In v6–v17 the vendor userspace's HSLINK layer tore down interfaces and retried
when the rootif bookkeeping was unsatisfied, which is one of the layers behind the v17 ceiling
(§6.6). A clean-room driver must **not** reproduce it; our contract is Linux bridge/VLAN/switchdev.
[I] [`opensource/docs/LSW-SPEC.md`](opensource/docs/LSW-SPEC.md) §9.2, §9.4.

### 5.2 The WEXT net_device ABI (8-byte shift)

**Finding.** The vendor kernel was built with `CONFIG_WIRELESS_EXT=y`; that inserts
`wireless_handlers`/`wireless_data` (two pointers) into `struct net_device` **before** `netdev_ops`,
shifting every later field by 8 bytes relative to a stock tree without WEXT. The lab kernel fixed
the match by exposing `CONFIG_WIRELESS_EXT` under `COMPILE_TEST`
(`tools/lab-src/net/wireless/Kconfig`), not by patching the vendor modules.

| field | ours after WEXT | vendor | status |
| --- | ---: | ---: | --- |
| `netdev_ops` | 0x128 | 0x128 | [V] |
| `flags` | 0x138 | 0x138 | [V] |
| `priv_flags` | 0x13c | 0x13c | [V] |
| `ALIGN(sizeof(struct net_device), 32)` = `netdev_priv` base | 0x540 | 0x540 | [V], vendor `mac80211.ko` uses `add r4,r5,#0x540` |

[V] [`opensource/docs/VENDOR-SKB-BRIDGE-PORT.md`](opensource/docs/VENDOR-SKB-BRIDGE-PORT.md) §3.2;
`opensource/docs/phase14/abi-match.md`; `opensource/docs/phase14/wifidrv0.md`. **Only those four
offsets are proven.** `hi_net_get_port`/`hi_cfe` also assume the vendor `net_device` fields
(`hi_cfe` writes a CFE hook at `dev+0x21c`; `hyfi_netlink_receive` touches `dev+0x30c`), and
field-by-field equality of the whole 0x540 struct is [U]. The method matters: offsets were read out
of the vendor modules' own instructions, not guessed; a "plausible pointer" is not validation.
[V]/[U] same source, §3.2 and open question Q4.

### 5.3 The vendor sk_buff ABI (the v16 crash and the v17 dirty stack)

**Finding.** The vendor modules were built against a `struct sk_buff` that is **0x78 bytes larger**
from the header fields onward and **0x74 bytes larger** by `len`/`data_len`, with a 4-byte vendor
field between `data_len` and the bitfields. Our stock 5.10 struct is 0xb0 bytes; the vendor's derived
size is 0x128 ([U]: derived, not directly measured).

| field | ours | vendor | delta |
| --- | ---: | ---: | ---: |
| `len` | 0x54 | 0xc8 | +0x74 |
| `data_len` | 0x58 | 0xcc | +0x74 |
| `transport_header` | 0x8e | 0x106 | +0x78 |
| `network_header` | 0x90 | 0x108 | +0x78 |
| `mac_header` | 0x92 | 0x10a | +0x78 |
| `tail` | 0x94 | 0x10c | +0x78 |
| `end` | 0x98 | 0x110 | +0x78 |
| `head` | 0x9c | 0x114 | +0x78 |
| `data` | 0xa0 | 0x118 | +0x78 |
| `sizeof(struct sk_buff)` | 0xb0 | 0x128 (derived, **UNVERIFIED**) | +0x78 |

Anchors used to measure it: `hi_hslink_tx_urarp` (skb_reserve-style update reads `head` 0x114 and
`data` 0x118, writes `network_header` 0x108 and `mac_header` 0x10a); `hyfi_bridge_get_dst`
(EtherType from `head + mac_header`); `mc_find_acl_rule` (`len - data_len`); `hyfi_netlink_receive`
(`skb_clone()` then `[clone+0x118]`; also `dev+0x540`); `hi_hslink_get_skbmacheader`;
`hi_hslink_monitor` (also reads a 16-bit vendor-private field at `0xb4`). [V]
[`opensource/docs/VENDOR-SKB-BRIDGE-PORT.md`](opensource/docs/VENDOR-SKB-BRIDGE-PORT.md) §3.1; ledger
2026-11-17 20:40.

**The crash.** v16 loaded `hyfi_bridging` and oopsed at t≈35 s:
`Unable to handle kernel NULL pointer dereference at virtual address 00000028`, PC
`hyfi_netlink_receive+0x40 [hyfi_bridging]`, process `hyctl`; `panic_on_oops=1` then panicked and
rebooted. The instruction sequence does `skb_clone()`, loads `[clone+0x118]` (vendor `skb->data`) and
stores through it; in our struct `->data` is at 0xa0 and the struct ends at 0xb0. [V]
[`opensource/docs/VENDOR-SKB-BRIDGE-PORT.md`](opensource/docs/VENDOR-SKB-BRIDGE-PORT.md) §2.5;
ledger 2026-11-17 20:15, 20:40; local capture `build/uart-logs/20261117T124213Z-uart-recovA.log`
(local-only).

**Important honesty:** the v17 stack without hyfi was **ABI-dirty, not ABI-clean** — the affected
transmit paths were not reached before HSLINK tore the interfaces down. The layout model (a 0x74-byte
vendor block after `cb` plus a 4-byte field after `data_len`) reproduces the anchors but is a model,
not a decoded vendor struct; the meaning of the vendor's block and the exact position of the 4-byte
field are open [U], and 0x51/0x53/0xb4/0xb8 vendor-private bytes are only partly corroborated
(0xb4 corroborated; the others need the RE notes committed). [V]/[U] same doc §3.1, §9 Q2/Q3.

### 5.4 The four br_* exported bridge symbols (pointer variables, not functions)

**Finding.** In the vendor's patched bridge, `br_get_dst_hook`, `br_port_dev_get_hook`,
`br_notify_hook` and `br_multicast_handle_hook` are **exported pointer variables**. `hyfi_bridging`
only *stores* callbacks into them (`hyfi_bridge_get_dst`, `hyfi_bridge_port_dev_get`,
`hyfi_br_notify`, `mc_process`) — it makes no calls and no reads. Our earlier function stubs were
ABI-wrong: a store would have overwritten the stub's first instruction word. v17 replaced them with
writable, zeroed exported pointers in `tools/lab-src/arch/arm/mach-luofu/luofu.c`, which removed the
crash for the store itself. [V] [`opensource/docs/VENDOR-SKB-BRIDGE-PORT.md`](opensource/docs/VENDOR-SKB-BRIDGE-PORT.md)
§3.3; ledger 2026-11-17 20:40.

**What is missing.** The *consumer* side is the vendor's patched bridge built into the vendor kernel;
those four call sites are not in our tree (the symbols are referenced nowhere under
`tools/lab-src/net/bridge/`). hyfi also computes `netdev_priv = dev + 0x540` and expects a
`net_bridge` cache pointer at `priv+0x10`, populated by the same vendor bridge patches. Trap: in
upstream 5.10 `struct net_bridge`, the field at +0x10 happens to be `dev`, so a nonzero read there
is **not** evidence of a correct cache. [V] same doc §3.3, §5.2; [X] the vendor bridge patch series
is a GPL-source dependency (GPL-REQUEST item 3). No-op stubs were tried in v15 and failed; v17
proved only that writable pointers without hyfi avoid a crash, not that the hooks work. [V]/[X]

### 5.5 PIE / LSW layering and the switch model (switchdev, not DSA)

**Layering [V].** `hi_kmac` owns the per-port netdev and phylink (`alloc_etherdev_mqs`,
`register_netdev`); its `ndo_start_xmit` is a 12-byte tail call `add r1,r1,#0x5a0; add r1,#8;
b hi_net_dev_xmit` — it passes `dev+0x5a8` to PIE and has no ring/DMA code. `hi_kpie` owns the DMA
rings, NAPI and the per-port context table (`g_api_priv`), and allocates a private `cpu%d`
NAPI-container netdev that is never registered. The internal LSW owns egress decision and queue
maps; CFE is an optional software forwarding layer above it. [V]
[`opensource/docs/PIE-DATAPATH.md`](opensource/docs/PIE-DATAPATH.md) §2; [`opensource/docs/REMAINING-DRIVERS.md`](opensource/docs/REMAINING-DRIVERS.md) §1.1.

**PIE facts recovered [V].** Window `0x10a70000–0x10a7ffff`; board `hwver = <0x250>` selects the
v250 ops table; per-channel TX block `0x2000 + ch*0x10`, RX block `0x3000 + ch*0x10`; doorbells are
writes to `+0x08` (write pointer), completion pointers are `+0x0c` (16-bit read pointer); RX
interrupt status `0x300 + ch*4`, mask `0x400 + ch*4`; global enable `0x3200` bit 0. Ring geometry
comes from DT pairs (`rx_ring = <0xa 0x800 ...>`, `tx_ring = <0xc 0x4>`); the driver allocates
`32 B << N` descriptor rings with `1 << N` descriptors (32-byte stride) and uses the second word as
RX buffer size / TX channel count. Four IRQ vectors (SPI 88–91) service **two channels each**
(`pie-ch0,7`, `ch1,6`, `ch2,5`, `ch3,4`) over an 8-channel slot space — assuming 4 IRQs == 4 channels
is a bug. DMA is coherent-only in the vendor design (`dma-coherent`, coherent `dma_alloc_attrs` /
`dma_map_page_attrs`); the ACP coherency question for 0x250 is [U] and bench-only.
[V] [`opensource/docs/PIE-DATAPATH.md`](opensource/docs/PIE-DATAPATH.md) §1, §3–§5, §8.

**LSW facts recovered [V].** The switch is a queue/queue-map engine plus a classification/forwarding
engine; there is no CPU-port tag format anywhere in the five-module symbol set and the vendor
integration is switchdev on per-port netdevs (`hi_swa` imports
`switchdev_handle_port_obj_add/del`), not DSA. Register access uses synthetic addresses
`addr = (module_id << 24) | offset` over a 256-entry `{base, iomem, size}` table: DP registers ids
`0x40..0x44` = `dp/eps/eqm/fam/ips`; PFE registers ids `0,1,3,5,6,7,8,9,0xa,0xb` =
`ifc/l2/napt/mcc/opp/pa/pe/pfe_glb/prbs/pub` (ids 2 and 4 skipped). PIE's "module 6" is PFE `opp`
at `0x12400000`; the two qid-map tables live at `opp+0x42800` and `opp+0x43800`. Port/queue model:
46-entry software port table (56-byte entries: valid flag, port id, qid base, `q_num` default 8), a
96-entry queue bitmap walk, an 8-QIDs-per-port loop, and qid-map table index classes 0–15, 40–47,
>47. Physical port namespace: `port-pie`, `port-prbs/loop`, `port8..port12`, `port0`, `port-xge`,
`port13`, `port-woe`; EPS counter labels `port3(prbs)`, `port4(pie0)..port7(pie3)`. The DT
`port_bitmap = <0xf01 0x1ff0>` is read as a u64 by the DP probe; its semantics are **unknown** and
must be answered by bench reads, not guessed. [V addresses/names; U semantics]
[`opensource/docs/LSW-SPEC.md`](opensource/docs/LSW-SPEC.md) §1, §5–§7.

**Why it matters.** It settles the framework question (**switchdev over per-port netdevs, not DSA**),
corrects the earlier "MAC cannot own a netdev" planning claim (the MAC owns the netdev; PIE owns the
rings), and corrects the interpretation of the vendor rootif write. It is the basis for patch `015`
(PIE refusing draft), patch `016` (LSW D1a probe skeleton) and the D1b/D1c/D1d plan. [V]/[I]
[`opensource/docs/PIE-DATAPATH.md`](opensource/docs/PIE-DATAPATH.md) §12.1;
[`opensource/docs/LSW-SPEC.md`](opensource/docs/LSW-SPEC.md) §9.3, §11.

### 5.6 FMC SPI-NAND: controller behavior and write-path traps

**Geometry and partition facts [V].** ESMT F50L1G41LC, 2048-byte pages, 64-byte OOB, 128 KiB erase
blocks; FMC at `0x10a20000` + 1 MiB window at `0x1c000000`; the stock partition map in §2.3.
The lab 5.10 driver registered the 17 stock partitions (plus its own scratch carve-out in the lab
DTS) and passed UBI/JFFS2. [V] [`PLAN-FULL-REVERSAL.md`](PLAN-FULL-REVERSAL.md) Phase A;
[`TARGET-DESIGN.md`](opensource/docs/TARGET-DESIGN.md) §3.3.

**Bench proofs [V].** G1: FMC reads real flash (page-0 magic `UBI#`; level-7 MTD probe found the
partition, the EC magic, `vid_hdr_offset = 0x800`, and `PEB0+0x800 = 'U'`). G2: a page written by
our kernel read back byte-exact through the vendor driver; the write path was proven for direct page
program, the MTD master hook, multi-page/consecutive writes, and a 12-byte JFFS2-cleanmarker-shaped
short write with read-modify-write. [V] [`STATUS.md`](STATUS.md) §2;
[`opensource/docs/phase53-write-path-proof.md`](opensource/docs/phase53-write-path-proof.md);
[`EVIDENCE-INDEX.md`](EVIDENCE-INDEX.md) G1/G2 rows.

**Traps retired (each measured, each publishable as a finding):**

1. The controller's `FMC_GLOBAL_CFG` write-protect bit 6 was being **set** by our probe while the
   vendor's `hi_spi_nand_hw_init` calls `hi_fmc_wp_en_set(0)`; the comment said "clear", the code did
   the opposite, so accepted programs left the array untouched. [V] phase53.
2. The program `OP_CFG` is the **spec pack** `0x9D0` (`cs=1`), not the transient `0x9A0` the early
   code hard-coded; the write operand spec record from the bootloader could override program operands
   with no command byte/address, so the measured-good operands are pinned after the record parse.
   [V] [`PLAN-FULL-REVERSAL.md`](PLAN-FULL-REVERSAL.md) Phase B.
3. An MTD partition does not inherit `master->priv`; calling the write hook with the partition mtd
   dereferences NULL — the real JFFS2/`dd` path passes the **master**. [V] phase53.
4. Bad pages confound write tests: pages 163–166 and 66/67 of the tested blocks are bad; a
   same-block page 0 can program while p35 stays `ff`. Every earlier "the program never lands"
   conclusion was measured through a bad page. [V] phase53.
5. Reads racing the asynchronous program produce false mismatches; and an in-kernel readback can
   echo the write's DMA buffer (vendor `dd` corroboration is mandatory). [V] phase53;
   [`PLAN-FULL-REVERSAL.md`](PLAN-FULL-REVERSAL.md) Phase B (`phase2u`).
6. `rootfs_data` must be treated as the vendor's config partition, not lab scratch; the lab's
   bench-scratch experiments were moved to `upgrade` after a fire wiped the vendor config.
   [V] [`PLAN-FULL-REVERSAL.md`](PLAN-FULL-REVERSAL.md) Phase C.

**Mainline port shape [V/I].** Patch `006` implements the controller as a **SPI-MEM controller**
(`drivers/spi/spi-luofu-fmc.c`) and lets the mainline SPI-NAND stack own chip detection, on-die ECC,
OOB layout, bad blocks and `fixed-partitions`. Open questions that only hardware can close: whether
`FMC_CFG` ECC type 1 is a host ECC engine or on-die pass-through; the OOB bytes from the DMA engine;
quad-enable state after the SPI-NAND core's die reset (the board runs quad and the mainline ESMT
entry has no QE quirk); whether the 15 undecoded vendor init words are needed; program-execute
ordering with the SPI-NAND core's WREN; and the fact that the ESMT F50L1G41LC chip entry is a v6.19
addition, obtained in this 6.18 target only via OpenWrt's generic backport `434`. [V]/[U]
[`opensource/target-skeleton/docs/port-notes/fmc/SUMMARY.md`](opensource/target-skeleton/docs/port-notes/fmc/SUMMARY.md)
§1, §5; [`STATUS.md`](STATUS.md) §3.

### 5.7 Other publishable findings (index)

| finding | detail | evidence |
| --- | --- | --- |
| Bring-up bug taxonomy and method | two species recurred: **A** = a block present in the DT but bound by nobody, so its clock is never enabled and its reset never released (symptom far from the cause); **B** = the driver registers successfully but configures nothing (empty stub callbacks, a netdev never opened). Detection: name the driver that binds each DT node, and place a value only the missing write can produce where it survives a fallback. The vendor's running kernel is the specification | [V] [`opensource/docs/ETHERNET-BRINGUP-FRAMING.md`](opensource/docs/ETHERNET-BRINGUP-FRAMING.md) §2–§4 |
| MAC↔PHY mapping is shifted from the early lab tree | vendor live map: `14380000→phy2`, `14400000→phy3`, `14480000→phy4` (wired, `eth2`), `14500000→phy5`; `14300000` unused. The lab tree had one port bound to the wrong PHY | [V] [`opensource/docs/ETHERNET-BRINGUP-FRAMING.md`](opensource/docs/ETHERNET-BRINGUP-FRAMING.md) §2 |
| MAC `PORT_MODE` value | `0x010C0008` on a live 1 Gbps link vs `0x000C0408` unlinked; not the mainline value for a different IP revision | [V] same doc §3 |
| MDIO controller protocol | register map `CMD 0x00 / WSTATUS 0x60 / RSTATUS 0x6c / FRAME 0x70 / RDATA 0x74`, recovered from `hi_kmdio.ko`'s own `hi_mdio_read`; live PHY topology PHY 2..5 on `mdio0`; a real C22 read returns id `0x20669a09` | [V] [`opensource/docs/ETHERNET-BRINGUP-FRAMING.md`](opensource/docs/ETHERNET-BRINGUP-FRAMING.md) §3; [`EVIDENCE-INDEX.md`](EVIDENCE-INDEX.md) G4-clean-room row |
| Genius PHY identity | PHYLIB ID `0x20669a00`, mask `0xffffff00`; the vendor per-PHY firmware patch (`lsw/hi_ephy_%xv%x.bin`) is un-decoded [U] | [V]/[U] [`TARGET-DESIGN.md`](opensource/docs/TARGET-DESIGN.md) §7.1; [`STATUS.md`](STATUS.md) §3 |
| CRG reset class is active-low | assert clears, deassert sets; measured `0x14880034 = 0x000ff309` with both RCs up; patch `014` swaps operations and inverts `reset_control_status` | [V] [`STATUS.md`](STATUS.md) §3 (PCIe/014 entry) |
| Thermal conversion verified | sensor `0x14900500`, hwver 3; vendor v4 conversion decoded and numerically verified; trips 115 °C passive / 125 °C critical, 3 °C hysteresis, 1 s poll; threshold/IRQ/trim registers [U] | [V]/[U] [`opensource/docs/REMAINING-DRIVERS.md`](opensource/docs/REMAINING-DRIVERS.md) §3; patch `012` |
| PCIe hard rules | two DWC RCs; per-RC iATU viewports; the RC misc window is write-only and must never be read; only aligned-dword DBI accesses (sub-word/unaligned accesses are a panic class) | [V] [`TARGET-DESIGN.md`](opensource/docs/TARGET-DESIGN.md) §8.2; [`REMAINING-DRIVERS.md`](opensource/docs/REMAINING-DRIVERS.md) §4 |
| Pinctrl tables | 37 pins / 24 groups / 24 functions, 5-hit mux, `cfg_off = 4*pin`, six pinconf parameters decoded from the vendor module's config ops; probe writes nothing | [V] [`STATUS.md`](STATUS.md) §3 (011 entry); patch `011` |
| Vendor kernel config divergences | `CONFIG_ARM_MODULE_PLTS=n` + `-mlong-calls`; `CONFIG_WIRELESS_EXT=y`; no `CONFIG_CPU_SW_DOMAIN_PAN`; no TRACING in the booting builds; a `CONFIG_SLAB`+`CONFIG_TRACING` interaction is what killed the 3dh-class kernels | [V] [`CURRENT-TRUTHS.md`](CURRENT-TRUTHS.md) (3dh resolution); [`VENDOR-STACK-ON-MAINLINE.md`](opensource/docs/VENDOR-STACK-ON-MAINLINE.md) |
| Recovery/console gating facts | RESET-counter+TFTP recovery; `bdinfo dbg` console gate (`bdinfo_check_dbg` at 0x2228); `fw_setenv` is a symlink to `fw_printenv` | [V] [`HARDWARE-IDENTITY.md`](HARDWARE-IDENTITY.md); [`BENCH-FACTS.md`](BENCH-FACTS.md) §4–§5 |
| Wi-Fi port surface (why it is [X]) | the Wi-Fi module is not a mac80211 driver: **0** mac80211 symbols, ~4,330 vendor namespace strings, **211** imports through a vendor `HW_RTOS_NS` namespace; closed 928,920-byte `FIRMWARE.bin`; all 58 modules GPL-declared but source withheld | [V] [`TARGET-DESIGN.md`](opensource/docs/TARGET-DESIGN.md) §8.3; [`opensource/docs/PORT-SURFACE.md`](opensource/docs/PORT-SURFACE.md); [`EVIDENCE-INDEX.md`](EVIDENCE-INDEX.md) G5 |

### 5.8 Publication rules for this material

- Publish **findings**, not fixtures: offsets, symbol names, table layouts, code-shape descriptions
  and numeric measurements are publishable; the `.ko` files, firmware blob, calibration data,
  extracted DTS and dumps are not. [V] [`opensource/docs/VENDOR-SKB-BRIDGE-PORT.md`](opensource/docs/VENDOR-SKB-BRIDGE-PORT.md)
  header; [`opensource/NOTICE.md`](opensource/NOTICE.md).
- Drivers derived from disassembly must be **GPL-2.0 with attribution**, labelled as
  GPL-compatible reverse engineering — not clean-room. [V]
  [`opensource/docs/PUBLISH-READINESS.md`](opensource/docs/PUBLISH-READINESS.md) item 5.
- Numerical constants that exist only in vendor binaries (e.g. register bytes) must be justified by
  a committed RE report or a bench measurement before a driver writes them. This is the "no
  unverified register writes" rule, encoded in patches `015`/`016` by refusing to probe. [V]
  [`opensource/docs/LSW-SPEC.md`](opensource/docs/LSW-SPEC.md) §10.4; patch `015`/`016`.

---

## 6. The bench lab-kernel line v6–v17 (2026-11-17/18)

### 6.1 Purpose and safety design

The lab-kernel line is the bench-reversal instrument: a vanilla 5.10.201 ARM kernel + our DTB +
our drivers, booted from the inactive slot, with the **vendor userspace** as root and the vendor
modules loaded from a patched overlay. It is explicitly **not** an upstream artifact and not a
release. [V] [`STATUS.md`](STATUS.md) §3; [`PLAN-FULL-REVERSAL.md`](PLAN-FULL-REVERSAL.md) goal and
"Operating rules".

Every fire was designed to end healthy and to return to stock if the experiment wedged:

- a bounded watchdog pet (`luofu_pet_beats`; pet limit at ≈155 s in v17), `panic=5`,
  `panic_on_oops=1`;
- a next-boot selector reservation so a power cycle after a userspace hang lands on stock;
- the physical RESET+TFTP recovery door as the only guaranteed way back (self-recovery was never
  proven reliable; a platform restart after mtd I/O could park). [V]
  [`STATUS.md`](STATUS.md) §3; ledger 2026-11-17 10:15 ("restart magic did not take"), 2026-11-18 06:50;
  [`opensource/docs/VENDOR-SKB-BRIDGE-PORT.md`](opensource/docs/VENDOR-SKB-BRIDGE-PORT.md) §7.1.

### 6.2 Bench-reversal gate state (context for the line)

The reversal's own gates, from [`STATUS.md`](STATUS.md) §2 (states last verified 2026-11-14): [V]

| gate | state | receipt |
| --- | --- | --- |
| **G1** FMC reads real flash | GREEN | page-0 magic `UBI#`; level-7 MTD probe found the partition, the EC magic, `vid_hdr_offset = 0x800`, and `PEB0+0x800 = 'U'` |
| **G2** program path | GREEN | a page written by our kernel read back byte-exact through the vendor driver |
| **G3** our kernel + real rootfs + userspace | GREEN 2026-11-14 | vendor preinit, `mount_root`, procd and the full rc.d chain run on our kernel from the squashfs root |
| **G4** Ethernet on our kernel | GREEN **via vendor modules**; M2 ("no vendor network modules") NOT met | `eth2` up 1 Gbps, `br-lan` 192.168.10.1, ping 3/3 on the 2026-11-14 stack; the bound PHY driver was vendor `hi_kphy` |
| **G5** Wi-Fi on our kernel | vendor-only | the vendor modules provide the radio; no wiphy from our driver |
| **G6** sustained uptime | GREEN 2026-11-14 | the reset was a userspace watchdog race, not a panic; the initramfs keeper holds the 25-minute timer |

These are **bench-reversal** gates, not upstream artifacts. Plan milestones: **M5** = vendor
userspace running on our kernel (reached 2026-11-14); **M6** = our own OpenWrt rootfs on the board
(not reached). [V] [`PLAN-FULL-REVERSAL.md`](PLAN-FULL-REVERSAL.md) "Goal and definition of done";
[`STATUS.md`](STATUS.md) §2.

### 6.3 Lineage: what had to be fixed before v6

| version / event | outcome | evidence |
| --- | --- | --- |
| **3df** (2026-11-16 05:40) | first GREEN: our kernel boots the vendor preinit/overlay and the shadow writes land | [V] ledger 2026-11-16 05:40; capture `build/uart-logs/20261116T052813Z-fire7-3df.log` (local) |
| **3dh/3di/3dk** class | U-Boot reads our uImage (`Data Size` 2,964,240 / 2,965,176; `Image Name: Linux-5.10.201`) then the box resets silently **before** the kernel console registers | [V] [`BENCH-FACTS.md`](BENCH-FACTS.md) §5; captures `...075623Z-3dh-fire.log`, `...111510Z-fire-3dk.log` (local) |
| root cause + fix | the mach `.init_early` hook `luofu_early()` called `ioremap()` before `mm_init()` created the kmalloc caches; with `CONFIG_SLAB`+`CONFIG_TRACING` the kmalloc path NULL-dereferenced in `kmem_cache_alloc_trace`. The fix defers the crumb/bootreg flip to an `early_initcall` (commit `0f8044e`); the fixed **3dn** slice booted | [V] [`CURRENT-TRUTHS.md`](CURRENT-TRUTHS.md) "3dh-class"; ledger 2026-11-17 08:05/08:45; capture `build/uart-logs/20261117T012608Z-uart-3dn.log` (local) |
| **3dp / 3dq** | 3dp (no TRACING) ran vendor rc.d to 61 s with no RCU stall; 3dq v2 booted to userspace, brought `eth2` up at 1 Gbps and exposed the remaining missing-symbol dependency chain (`ksecurec` first) | [V] ledger 2026-11-17 10:15 |

Lesson recorded: the post-procd RCU stall was a **TRACING-block effect**, not a generic kernel
problem; and a software restart after mtd I/O is not reliable, so unattended fallback must never
depend on restoring a slot and rebooting from inside our kernel. [V] ledger 2026-11-17 10:15.

### 6.4 Version-by-version table (the v6–v17 line)

The ledger names these builds; the numbering is not contiguous and the table lists what the record
names. Slice identities are given where the ledger records them.

| version | change | result |
| --- | --- | --- |
| **v6/v7** | export `mem_section`/`napi_enable`/`__netdev_alloc_skb_ip_align`, remove colliding `hi_pie` stubs, preload `ksecurec` first, mask `kmodloader` | **all 19 preloaded vendor modules load `ret=0`**; lab GMAC registers `eth0..eth3`; `eth2` up 1 Gbps; vendor rc.d runs. Fault found: vendor userspace writing `hi_basic`'s DFX proc entry oopsed in `arm_copy_from_user` because our build had `CONFIG_CPU_SW_DOMAIN_PAN=y` and the vendor kernel does not. [V] ledger 2026-11-17 17:45 |
| **v8** | `CONFIG_CPU_SW_DOMAIN_PAN` off + `CONFIG_PANIC_ON_OOPS`; slice md5 `1010b35e…` | oops gone. Remaining: HSLINK logs `failed to add rootif eth3` and tears every interface down; our GMAC netdevs are plain ethernet while the rootif path expects the vendor MAC's netdev. [V] ledger 2026-11-17 17:45 |
| **v9** | vendor MAC/MDIO/PHY lane: vendor compatibles in DT, lab GMAC disabled, preload `hi_kmdio → hi_kphy → hi_kmac` | `hi_kphy` loads but `hi_kmdio`'s probe crashes on our DT (`reset_control` lookup) and `hi_kmac` fails `-2`; no netdevs. [V] ledger 2026-11-17 18:00 |
| **v10** | hybrid: lab MDIO/PHY kept, lab GMAC disabled, DT nodes carry `hsan,himac` + vendor port indices, `hi_kmac` preloaded after `hi_kpie` | boots; vendor userspace runs but every run goes silent at ≈33 s after the VAP cleanup/interface-teardown stage; no LAN. [V] ledger 2026-11-17 18:00 |
| **v13** | WEXT `net_device` ABI fix (`CONFIG_WIRELESS_EXT` under `COMPILE_TEST`); non-persistent init masks; slice md5 `adf6e18c…` | U-Boot read our uImage (`Data Size` 2,817,549) and then took a **DATA ABORT inside `bootfip`** — U-Boot's own DT fixups crash on the simplified vendor-MAC nodes added to *our* DTB. Stock fallback came up healthy (the mask design worked). [V] ledger 2026-11-17 18:55 |
| **v14** | revert DT to the last U-Boot-safe version; keep WEXT + kernel fixes; persistent overlay copies of patched `hsan_appm`/`wandetect`/hotplug redirecting the WAN-rootif write to `/dev/null` | booted (no U-Boot abort), 19 modules `ret=0`; transient pre-pivot bind-mounts had failed because only `/vendor/upper` exists at that point, so persistent overlay copies were used. [V] ledger 2026-11-17 20:15 |
| **v15** | bridge + tracepoints + `br_fdb_find_rcu`/`br_forward` exports + `consume_skb` out-of-line + vendor `br_*` hook stubs; `hyfi-bridging` preloaded | boots; `hyfi-bridging` fails `-22` because it registers bridge-netfilter hooks and `CONFIG_BRIDGE_NETFILTER` was missing. [V] ledger 2026-11-17 20:15 |
| **v16** | `CONFIG_BRIDGE_NETFILTER` added; slice md5 `641d8b36…` | `hyfi_bridging` **loads** and HSLINK activity begins; at t≈35 s it oopses in `hyfi_netlink_receive+0x40 [hyfi_bridging]` (NULL deref at 0x28), `panic_on_oops=1` panics and reboots into the same slot. [V] ledger 2026-11-17 20:15; [`opensource/docs/VENDOR-SKB-BRIDGE-PORT.md`](opensource/docs/VENDOR-SKB-BRIDGE-PORT.md) §2.5 |
| **v17** | drop `hyfi-bridging` from the preload; replace the four `br_*` function stubs with **writable zeroed exported pointer variables**; bridge stack on; rootif writes bypassed in userspace; 59 patched modules staged; slice 2,906,100 B md5 `8342ccb9c0167766529277719330f43c` (zImage `a08ffc66…`, init `74033a38…`, DTB `336ba39e…`) | boots normally, 19 modules `ret=0`, S20network OK, lab GMAC `eth2` up 1 Gbps, **no oops/panic** — then HSLINK creates/destroys `br-lan` in a loop (t≈33–35 s) and the console goes silent at ≈54 s; no network. [V] [`STATUS.md`](STATUS.md) §3; ledger 2026-11-18 06:50; [`opensource/docs/VENDOR-SKB-BRIDGE-PORT.md`](opensource/docs/VENDOR-SKB-BRIDGE-PORT.md) §2.2 |

### 6.5 What worked (and is reusable)

- **The module-load gate is solved.** Zero-size `.plt`/`.init.plt` sections added with `objcopy`
  satisfy the loader; `finit_module` must use ARM syscall **379**; the initramfs preloads the exact
  vendor order. [V] [`opensource/docs/VENDOR-STACK-ON-MAINLINE.md`](opensource/docs/VENDOR-STACK-ON-MAINLINE.md).
- **The full 19-module chain loads on our kernel** with the vendor userspace, including
  `hi_kpie`, the `hi_lsw_*`/`hi_kcfe_*` chain and `hi_swa`; on the 2026-11-14 stack a later
  22-module chain produced a working router: `eth2` up, `br-lan` 192.168.10.1/24 with members
  `eth0 vap0 eth1 vap3 vap8 eth2 vap11`, host ping 3/3. [V] [`STATUS.md`](STATUS.md) §2 (G4);
  [`opensource/docs/VENDOR-SKB-BRIDGE-PORT.md`](opensource/docs/VENDOR-SKB-BRIDGE-PORT.md) §2.4; ledger 2026-11-14 22:41.
- **The vendor userspace boot chain runs on our kernel**: preinit, `mount_root`, procd and the full
  rc.d chain to `S95done` (build #162, 2026-11-13), and the 25-minute keeper later verified G6.
  [V] [`PLAN-FULL-REVERSAL.md`](PLAN-FULL-REVERSAL.md) Phase C; [`STATUS.md`](STATUS.md) §2.
- **Our own drivers carry a link.** The lab `luofu-mdio`/`luofu-gmac` worked a real 1 Gbps link
  (PHY id read `0x20669a09`), but the bound PHY driver was the vendor `hi_kphy`: **M2 ("no vendor
  network modules") is NOT met**. [V] [`EVIDENCE-INDEX.md`](EVIDENCE-INDEX.md) G4-clean-room row;
  [`STATUS.md`](STATUS.md) §2.
- **The bench instruments are known and their failure modes are documented** (validity marker,
  surviving cells, read-only UART capture that restarts on EIO, the verdict-cell scheme, and the
  list of instruments that lied). [V]
  [`opensource/docs/ETHERNET-BRINGUP-FRAMING.md`](opensource/docs/ETHERNET-BRINGUP-FRAMING.md) §4;
  [`PLAN-FULL-REVERSAL.md`](PLAN-FULL-REVERSAL.md) "Operating rules".

### 6.6 What failed at v17 — the documented ceiling

The v17 console (local capture `build/uart-logs/20261117T233458Z-uart-v17.log`; ledger 2026-11-18
06:50) reads:

| t (s) | event |
| ---: | --- |
| — | U-Boot reads our uImage (`Data Size` 2,865,304) and boots it; kernel banner `5.10.201 … #261 SMP Tue Nov 17 20:34:15 +07 2026` |
| 8.7 | `luofu-gmac 14480000.ethernet: Link is Up - 1Gbps/Full - flow control rx/tx` |
| 11.3–12.0 | `S18hyfibrd OK`, `S20network OK`, `S95done OK`; 19 modules `load <module> fd=0 ret=0`; `[HSLINK]HSLINK install successfully` |
| 33.3–33.5 | `[HSLINK]dev(eth3/eth2/eth1/eth0) is destroy` |
| 33.7, 34.2–35.6 | `[HSLINK]dev(br-lan) is destroy` (six more) |
| 34.0 / 35.4 | `Could not find PHY for device 'radio0'` / `'radio1'` |
| 44.5 | `done (3432): drop_caches: 3` |
| 53.8 | five `nf_nat_*: module PLT section(s) missing` lines — last console text |
| 155.0 | `luofu: pet limit reached; selected stock A, watchdog will reset` |

After that U-Boot reports a hard power-on reset, re-initialises the selector, boots our slice a
second time, repeats the pattern, and eventually lands on the stock kernel. The box needed the
physical RESET+TFTP recovery and was restored to stock. [V] ledger 2026-11-18 06:50;
[`STATUS.md`](STATUS.md) §1 (stock re-verified 2026-11-18 07:35).

### 6.7 The ceiling, stated and explained

**Documented ceiling (2026-11-18 06:50).** The lab kernel boots the vendor userspace, loads the full
preloaded module set, brings `eth2` up at 1 Gbps and creates `br-lan`; the vendor HYFI/bridge
userspace contract then tears the interface down and the box is unusable. The ledger's decision:
the remaining work is a **multi-step port**, and further recovery cycles were not justified; bench
fires stopped. [V] ledger 2026-11-18 06:50; [`STATUS.md`](STATUS.md) §3.

Why, layer by layer:

1. **HYFI is absent** by necessity: `hyfi_bridging.ko` must not run on our `sk_buff` ABI (v16
   oops), so v17 drops it; the vendor `hyfibrd` userspace therefore has no kernel counterpart for
   its netlink protocol. [V] [`opensource/docs/VENDOR-SKB-BRIDGE-PORT.md`](opensource/docs/VENDOR-SKB-BRIDGE-PORT.md) §2.3.
2. **HSLINK owns interface lifecycle** and repeatedly destroys the netdevs; the created `br-lan`
   never becomes the stable bridge the network config expects. [V] same doc §2.3; ledger 06:50.
3. **The WAN rootif bookkeeping is bypassed in userspace**, so the switch's rootif state is not
   established. [V] same doc §2.3.
4. **Even with the `sk_buff` layout fixed, the four bridge hook consumers and the `net_bridge`
   cache are vendor-kernel patch code we do not have** — a vendor-source dependency
   (GPL-REQUEST item 3), not a config change. [V]/[X] same doc §5.

**The honest counter-example.** On 2026-11-14 a vendor stack **without hyfi** reached a working
router on our kernel when the vendor MAC modules owned the netdevs (`eth2`, `br-lan`,
ping 3/3). The v17 lane changed two things relative to that state: it replaced the vendor MAC
netdevs with the lab GMAC and it bypassed the WAN rootif. Whether the HYFI absence alone, or the
MAC/rootif change, is decisive is **open question Q1** in the port spec; the record does not
resolve it. [V]/[U] [`opensource/docs/VENDOR-SKB-BRIDGE-PORT.md`](opensource/docs/VENDOR-SKB-BRIDGE-PORT.md) §2.4, §9 Q1.

### 6.8 What resuming the line would take

The port spec's staged plan (estimates, not measurements):

| stage | work | estimate |
| --- | --- | --- |
| **E0** host-only | adapt `struct sk_buff` to the measured vendor layout under a config switch + `BUILD_BUG_ON` + offset probe module + negative control | 1–2 focused days |
| **E1** attended fire | no-regression: boot v18 with the layout patch and no hyfi; expect the v17 timeline | 1 attended fire + recovery budget |
| **E2** attended fire | load hyfi; expected to stop at vendor-private skb bytes / `hi_cfe_intf_rx` / hook-consumer faults | 1 attended fire + recovery budget |
| vendor-private field RE (0x51/0x53/0xb4/0xb8, `hi_cfe_intf_rx`) | disassembly days-weeks; RE notes must be committed this time | unbounded until scoped |
| bridge hook + `net_bridge` cache | **blocked on vendor source**; with source, an estimated 1–2 weeks to rebase/integrate | [X] today |

None of the acceptance criteria beyond E0 exist today; criterion 5 (hyfi loads and survives
≥ 5 minutes) failed at v16 and was never reached at v17; the LAN criterion (3/3 ping) was last met
on 2026-11-14 with the **vendor-MAC lane**, not this one. [V]
[`opensource/docs/VENDOR-SKB-BRIDGE-PORT.md`](opensource/docs/VENDOR-SKB-BRIDGE-PORT.md) §8.1, §8.3.
**This lane is not the upstream path and must not be presented as upstream progress.** [V]

### 6.9 What "booted" means here (grading discipline)

- A fire is valid only when the capture has our uImage identity **and** our kernel output; a
  U-Boot header alone proves nothing (`LESSONS.md` 20 / BENCH-FACTS §5).
- "All modules loaded" means the console printed `load <mod> fd=0 ret=0` for each; "eth2 is up" means
  the `Link is Up - 1Gbps/Full` line from *our* driver; "br-lan created" means the HSLINK/br
  console lines — none of these is "the router works".
- Every claim above names a capture or ledger entry; the captures are local-only artifacts and are
  not fresh-clone receipts. [V]
  [`EVIDENCE-INDEX.md`](EVIDENCE-INDEX.md) "Bench kernel line" section.

---

## 7. The 001–017 driver/binding port (host-validated, never booted)

### 7.1 Environment and method

All porting/validation was **host-only** in isolated OpenWrt `main` clones (shared tree untouched):
commit `27663a0`, `linux-6.18.60`, GCC 14.4.0, `CONFIG_WERROR=y`. Each lane ran the same gate set:
patch dry-run against pristine 6.18.60 and against the chained series; `make target/linux/prepare`;
full `make target/linux/compile` with zero warnings; `dt_binding_check` per new YAML; board DTS
compile with the patched kernel's own dtc (zero warnings); `dt-validate` where applicable; canonical
config re-derivation (idempotent, byte-identical on the second run); checkpatch; static scans for
forbidden addresses, lab/bench breadcrumbs and unguarded MMIO. No router, UART, TFTP or flash tool
was used. [V] [`opensource/docs/SKELETON-SMOKE.md`](opensource/docs/SKELETON-SMOKE.md) sessions 1–13;
`opensource/target-skeleton/docs/port-notes/*/SUMMARY.md`.

This is a **build/binding validation**, not hardware validation. The distinction is the point of the
rest of this section.

### 7.2 The series at a glance

| # | patch | what it adds | host status | hardware status |
| --- | --- | --- | --- | --- |
| 001 | `arm-mach-hisilicon-luofu` | new `arch/arm/mach-hisilicon`: `ARCH_LUOFU` Kconfig (depends on `ARCH_HISI`, selects L2X0/SCU/TWD), Makefile, a clean UP-only machine descriptor that only matches the board DT and programs no hardware (no `smp_ops`) | [V] compile/series | [U] never booted |
| 002 | `arm-kconfig-textofs` | platform `TEXT_OFFSET` config wiring in `arch/arm/Kconfig` + `arch/arm/Makefile` | [V] | [U] |
| 003 | `arm-textofs-nonimmediate` | fixes the compile blocker `TEXT_OFFSET = 0x00608000` not being an ARM rotated immediate, using the kernel's own `mov_l` idiom in `head.S`/`compressed/head.S`; load/entry verified `0x80608000` | [V] compile + mkimage/`_text` check; zImage sha `45ad00d5…` | [U] |
| 004 | `arm-clk-reset-luofu-crg` | CRG clock+reset controller (16 gate clocks, 2-cell reset), `dt-bindings/clock/hisilicon,luofu-crg.h`, YAML; shared `0x14880000` page modelled as one `syscon+simple-mfd` (no overlapping MMIO claim) | [V] compile RC=0; zImage `50cd07a1…`, DTB 8,944 B, `dt_binding_check` PASS | [U]; gate offsets for one group and reset polarity were provisional until 014 |
| 005 | `arm-watchdog-luofu-wdt` | watchdog driver (6.18 watchdog API) as a syscon child; magic values/offsets are hwver-2 driver data; no IRQ, no restart handler | [V] compile; YAML PASS | [U] clear/enable ordering, running state |
| 006 | `arm-mtd-nand-luofu-fmc` | SPI-MEM controller for the FMC + mainline SPI-NAND stack for ESMT F50L1G41LC; 17 partitions via `fixed-partitions`; CRG clock/reset. Depends on OpenWrt's generic v6.19 ESMT backport `434` for the chip entry | [V] compile RC=0; zImage `51f340ad…`, DTB 9,163 B, binding PASS | [U] ECC semantics, OOB, QE-after-reset, init words, program ordering; never booted |
| 007 | `net-mdio-luofu` | MDIO bus controller (clock + 7 CRG resets) on the 6.18 MDIO API | [V] compile RC=0; zImage `2749c294…`, DTB 9,459 B, binding PASS | [U] no transfer ever performed on 6.18 |
| 008 | `net-phy-luofu` | PHYLIB driver for the Hisilicon "Genius" PHY (ID `0x20669a00`/mask `0xffffff00`), generic C22 ops; ID-matched, no YAML | [V] compile; binding not applicable | [U] no link trained; per-PHY firmware patch undocumented |
| 009 | `net-gmac-luofu` | GEMAC binding + resource validation, then **refuses to probe** (`-EOPNOTSUPP`); no rings/DMA/NAPI/netdev; DTS nodes `disabled` | [V] compile; honest partial | [U]; data path is PIE (patch 015/spec) |
| 010 | `arm-luofu-restart` | machine-restart driver: saves the stock selector with a read-back/write-same (only the measured 0x10/0x11 values), writes the vendor CRG `softrst_val0/1` pair **provisionally**, falls back to a bounded watchdog arm; never parks; probe touches no register | [V] compile RC=0; zImage `e548bc7b…`, DTB 9,891 B, config 297/297 symbols, both YAMLs PASS, checkpatch clean | [U] reset command/offset/width are **PROVISIONAL**; never run |
| 011 | `pinctrl-luofu` | mainline pinctrl driver: 37 pins / 24 groups / 24 functions re-verified from the vendor module, six pinconf params, probe writes nothing | [V] compile RC=0; zImage `a4686a41…`, DTB 9,887 B, YAML PASS | [U] consumer states not attached; drive-strength mapping open |
| 012 | `arm-thermal-luofu-tvsensor` | thermal sensor (read-only vendor v4 conversion) + `cls0-thermal` zone with vendor trips (115/125 °C, 3 °C hysteresis, 1 s poll), no cooling map | [V] compile RC=0; zImage `34ed6116…`, DTB 9,799 B, YAML PASS | [U] threshold/IRQ/enable/trim registers undecoded and unwritten |
| 013 | `arm-pci-luofu-host` | DWC-based PCIe host glue: clocks, 4 resets, RC mode, DT `ranges`/iATU, aligned-dword DBI accesses, `pci_host_probe()`; the hard rules are encoded (never read the misc window); RC/endpoint nodes disabled | [V] compile RC=0; zImage `392d5861…`; combined 001–013 zImage `8654b99a…`, DTS 10,133 B | [U] enumeration never run; Wi-Fi endpoint [X] |
| 014 | `arm-crg-reset-polarity` | cross-lane fix found by the PCIe lane: the vendor reset class is **active-low** (assert clears, deassert sets; measured `0x14880034 = 0x000ff309`), so reset ops are swapped and `reset_control_status` inverted | [V] object compile in the same tree | [U] never run |
| 015 | `net-pie-luofu` | PIE packet-engine **refusing draft**: validates window/clock/reset/4 named IRQs/`dma-coherent`, allocates coherent RX/TX ring bookkeeping, then refuses to probe (`-EOPNOTSUPP`); no register access, clock, reset, IRQ or NAPI; DTS node disabled | [V] compile RC=0; zImage `5231214b…`, DTB 10,193 B, binding PASS; combined 001–015 zImage `c82d0ffe…` | [U]; needs the attended P3 read-only inventory |
| 016 | `net-lsw-luofu` | internal LSW **D1a probe skeleton**: one switch node with the 15 recovered MMIO windows (vendor `lsw_dp`+`lsw_pfe`), two clocks, four resets, switchdev port model (`ethernet-ports` children with ordering index + GEMAC phandle); validates resources, logs, frees, returns `-EOPNOTSUPP`; zero MMIO accessor in the file; DTS node disabled | [V] chained 001–016 apply/prepare/compile RC=0; zImage `201ba868…`, DTB 10,538 B, YAML PASS, checkpatch 0/0/0 | [U]; D1b inventory is the gate |
| 017 | `soc-luofu-boot-selector` | A/B boot-selector driver: `syscon_regmap` interface on the existing SYSCTRL node (no second mapping), `current_pair`/`raw`/`next_pair` sysfs ABI, probe performs no register access, write = full dword + read-back verification; `next_pair` accepts only `a`→0x10 / `b`→0x11 | [V] chained 001–017 apply/prepare/compile RC=0, 0 warnings under `CONFIG_WERROR`; zImage `a4e4f6c0…`, DTB 10,664 B, config 309/309 symbols, YAML PASS, checkpatch clean | [U] never read/written on hardware; mocked install harness 52/52 + 58/58 |

[V] for the host column: [`EVIDENCE-INDEX.md`](EVIDENCE-INDEX.md) driver rows;
[`STATUS.md`](STATUS.md) §3; [`opensource/docs/SKELETON-SMOKE.md`](opensource/docs/SKELETON-SMOKE.md)
sessions 1–13; the per-lane `port-notes/*/SUMMARY.md` files. [U] for every hardware column: this
series has **never run on the router**; the DTS nodes for GEMAC/PIE/LSW are disabled and the
refusing probes are deliberate.

### 7.3 Combined-series evidence

The series was verified both per lane and as a chain; representative receipts:

- **001–003 kernel platform:** `make defconfig` PASS; `make target/linux/prepare` RC=0 (kernel
  6.18.60); canonical config re-derivation twice byte-identical; full `make target/linux/compile`
  RC=0 with the real TEXT_OFFSET; zImage sha256 `45ad00d5…`; linked/load address verified
  `0x80608000`; mkimage `-a/-e 0x80608000`. [V] [`EVIDENCE-INDEX.md`](EVIDENCE-INDEX.md) kernel-platform row.
- **001–013:** full compile RC=0, zImage `8654b99a…`, 0 warnings/errors, all `CONFIG_LUOFU_*`
  drivers built in, combined DTS 10,133 B with zero warnings. [V]
- **001–015:** prepare RC=0, full compile RC=0, zImage `c82d0ffe…`, 0 warnings/errors; the LSW
  spec and PIE spec were committed alongside. [V] [`STATUS.md`](STATUS.md) §3.
- **001–016 / 001–017:** chained apply (0 `.rej/.orig`), prepare RC=0, full compile RC=0 with
  `CONFIG_WERROR=y`; final board DTB 10,664 B with zero warnings; config delta 309/309 symbols
  idempotent; checkpatch 0/0/0 on the new driver/YAML/ABI doc. [V]
  [`opensource/target-skeleton/docs/port-notes/abinstall/SUMMARY.md`](opensource/target-skeleton/docs/port-notes/abinstall/SUMMARY.md) §6.

### 7.4 What is genuinely missing (and what the drafts refuse to fake)

| block | state | missing |
| --- | --- | --- |
| GEMAC data path | patch `009` is an **honest partial**: binding + resource validation only, probe refuses, nodes disabled | ring/DMA model, NAPI TX/RX, DMA mapping, MAC port-mode programming; the data path is PIE |
| PIE packet engine | patch `015` is a **refusing draft**: resources/ring bookkeeping only | the attended read-only register/channel inventory (P3), then ring/NAPI bring-up |
| internal LSW switch | patch `016` is a **D1a probe skeleton**: validates and refuses | D1b write set (clock/reset/qid-map/EQM), D1c host-queue path, D1d Linux bridge; EQM command word, `port_bitmap`, LSW-vs-MAC port-id mapping, queue/flow DDR base remain [U] |
| PCIe | patch `013` host driver compiles | enumeration/LTSSM/endpoint power sequencing; Wi-Fi endpoint driver [X] |
| Wi-Fi | vendor-only; a cfg80211 wiphy+netdev was registered in an earlier phase, takeover reaches the firmware dialogue | data path gated on a vendor TX credit installed at runtime by the chip layer; no mac80211 path; closed blob [X] |
| SMP | machine descriptor is UP-only | platsmp port (pen/smc release), or a documented UP-first submission |
| MAC address / efuse | no driver; where the unit's MACs come from is [U] | nvmem/efuse or documented MAC source |
| boot args / rootfs mount | image design assumes the trailer DTB can carry the cmdline | [U] one attended boot; §8.6 |

[V]/[U] [`STATUS.md`](STATUS.md) §3; [`opensource/docs/REMAINING-DRIVERS.md`](opensource/docs/REMAINING-DRIVERS.md)
§9 (summary: ~32–55 focused host sessions + 11–19 attended bench sessions for the five remaining
blocks, Wi-Fi excluded).

### 7.5 Lab code that must not be submitted

The tracked mirror `tools/lab-src` (43 modified source files, guarded by `tools/check-lab-src.sh`)
contains bench-only edits: near-region `module_alloc`, boot breadcrumbs/TEXT_OFFSET edits, vermagic
tag removal, JFFS2/UBI hooks, slab exports, network ABI edits, WEXT under `COMPILE_TEST`, and the
initramfs vendor-stack loader. The published `lab/` snapshots are older than the mirror. The
submission series must be built from the clean skeleton patches, not from the lab tree. [V]
[`TARGET-DESIGN.md`](opensource/docs/TARGET-DESIGN.md) §7.2; [`opensource/docs/PUBLISH-READINESS.md`](opensource/docs/PUBLISH-READINESS.md).

---

## 8. Target image and install path

### 8.1 Target layout

```
opensource/target-skeleton/
├── target/linux/hisilicon/
│   ├── Makefile              ARCH:=arm, BOARD:=hisilicon, SUBTARGETS:=luofu, KERNELNAME:=zImage
│   ├── Kconfig               target-level symbols
│   └── luofu/
│       ├── target.mk         BOARDNAME, CPU_TYPE:=cortex-a9, FEATURES, DEFAULT_PACKAGES
│       ├── config-6.18       canonical kernel config delta (309 symbols at 001–017)
│       ├── config-5.10       earlier baseline (history/attempt)
│       ├── image/Makefile    target-level image helpers
│       ├── image/luofu.mk    device stanza + Build/ stages
│       ├── image/luofu-ubinize.cfg   static UBI volume "squashfs", geometry p=131072 m=2048 s=2048 O=2048
│       ├── base-files/lib/upgrade/platform.sh   platform_check_image / platform_do_upgrade
│       └── base-files/etc/board.d/02_network
├── dts/luofu-r116.dts        draft board DTS (stock partition map)
├── dts/luofu-r116-overlay.dtso   loader-match overlay stub (vendor_id hsan, board_id 3)
└── tools/{fip-slice.py, luofu-image.py, build-kernel-slice.sh, test-platform-abinstall.sh}
```

Status: target files, DTS and drivers are **drafts** — host-compile/binding-validated only, never
booted, not reviewed upstream. No OpenWrt submission exists. [V]
[`opensource/docs/TARGET-DESIGN.md`](opensource/docs/TARGET-DESIGN.md) header;
[`opensource/docs/SKELETON-SMOKE.md`](opensource/docs/SKELETON-SMOKE.md);
[`opensource/target-skeleton/README.md`](opensource/target-skeleton/README.md).

### 8.2 Image chain

The image recipe is real OpenWrt idiom, not a hand-assembled artifact:

- **Kernel branch:** `kernel-bin | luofu-check-textofs | append-dtb | uImage none | luofu-fip-slice |
  luofu-fip-manifest`.
- **Rootfs/image branch:** `luofu-rootfs-ubi | luofu-sysupgrade-container | append-metadata`.
- **Load/entry derivation:** `(0x83200000 & 0xf8000000) + 0x00608000 = 0x80608000`, asserted at
  build time against the built kernel's own `_text` and against the assembled uImage header.
- **Trailer:** generated at build time from **our own** DTB + loader-match overlay with
  `fip-slice.py make-trailer` (libfdt apply required); gate magic and descriptor constants are
  asserted; slot budget (`kernel <= 8,650,752 B`) enforced.
- **Manifest:** `fip-manifest.txt` records `ih_size`, `dtb_totalsize`, gate offset+magic, container
  sha256, overlay sizes, slice sha256/length; `platform_check_image` re-verifies manifest against
  bytes.
- The container carries a **NOT FLASHABLE** install-status marker. Every stage fails the build
  closed. [V] [`opensource/docs/SKELETON-SMOKE.md`](opensource/docs/SKELETON-SMOKE.md) image session;
  [`opensource/target-skeleton/docs/port-notes/image/SUMMARY.md`](opensource/target-skeleton/docs/port-notes/image/SUMMARY.md).

### 8.3 Build artifacts (host-only; never flashed or booted)

**Final 001–017 world build** (isolated clone, `make world -j16` RC=0; ledger 2026-11-18 15:55;
[`EVIDENCE-INDEX.md`](EVIDENCE-INDEX.md) image row):

| artifact | size (B) | sha256 |
| --- | ---: | --- |
| sysupgrade `openwrt-hisilicon-luofu-cudy_wr3000-v2-squashfs-sysupgrade.bin` | 6,185,262 | `e869f105ee547a6017a86926ae5629730b51b165a9303d179c7c1fe819f44065` |
| own FIP kernel slice | 3,284,486 | `ea268be93de6ce15660aead24b0308f35416736609f628293d8120dacfd0f9ce` |
| rootfs UBI | 2,883,584 | `1ae085409a6a24d457d7063d37e3f5d0c00e952f82b9611ccae47f679944985a` |
| generated FIP trailer | 10,958 | `0cf73b4739a6600a2df1f9d7da81385a9df5cb14fb05e4bb97707942e7acaed3` |

Derived facts: kernel slice load/entry `0x80608000`/`0x80608000`; gate `0xd7b7ab1e` at `0x321ce0`;
rootfs UBI = static `squashfs` volume, 20 used erase blocks; both slots within budget;
`luofu-image.py check-container` PASS. [V] [`EVIDENCE-INDEX.md`](EVIDENCE-INDEX.md);
[`opensource/docs/SKELETON-SMOKE.md`](opensource/docs/SKELETON-SMOKE.md) image/A-B sessions.

Earlier in the same day (kept for traceability): the **001–015 build** produced a byte-reproducible
container, `6,175,022 B` sha256 `ea143b03d9d248b3e2b21723ef639e42817e66da847285496ebbc46e12756881`,
with own slice `3,283,008 B` sha256 `23c3286b…`, rootfs `2,883,584 B` sha256 `d3c5611c…`, trailer
`10,487 B` sha256 `d9616d26…`, gate at `0x32171a`; a second identical `make world` produced the same
image. The **001–016** build produced `6,185,262 B` sha256 `0303d76a…` with slice `3,285,034 B`
sha256 `dfc53b95…` and trailer `10,832 B` sha256 `beaad4d9…`. [V] ledger 2026-11-18 15:20/15:55;
[`opensource/target-skeleton/docs/port-notes/image/SUMMARY.md`](opensource/target-skeleton/docs/port-notes/image/SUMMARY.md).

### 8.4 Install path (A/B selector + sysupgrade)

Patch `017` adds the selector interface; `base-files/lib/upgrade/platform.sh` implements the upgrade
path. **No write has ever been executed on the router; the container still says NOT FLASHABLE.**

Selector ABI (all measured values, nothing invented): `current_pair` read-only
(`a` = 0x10, `b` = 0x11, `manual-b` = 0x21, `uninitialised` = 0x00, else `unknown`), `raw` read-only,
`next_pair` write-only accepting only `a`→0x10 / `b`→0x11, full-dword write with read-back
verification. Probe performs no register access; the SYSCTRL page stays a shared syscon with the
restart driver (no second mapping, no ownership fight). [V]
[`opensource/target-skeleton/docs/port-notes/abinstall/SUMMARY.md`](opensource/target-skeleton/docs/port-notes/abinstall/SUMMARY.md) §1, §4.

`platform_do_upgrade` sequence: [V] (mocked only)
[`opensource/target-skeleton/docs/port-notes/abinstall/SUMMARY.md`](opensource/target-skeleton/docs/port-notes/abinstall/SUMMARY.md) §3.

1. Re-run `platform_check_image` (defence in depth).
2. Resolve the **active pair** from two independent in-boot witnesses that must agree: the selector
   `current_pair` and the rootfs slot the system booted from
   (`/sys/class/ubi/ubi0/mtd_num` cross-checked with that mtd's `/proc/mtd` label). No slot token
   exists in `/proc/cmdline`.
3. Resolve the **inactive pair** by `/proc/mtd` label only: `kernelb`+`rootfsb` after an A boot,
   `kernela`+`rootfsa` after a B boot; validate the measured sizes (kernel slot 8,650,752 B;
   rootfs partition 24,379,392 B; image budgets 8,650,752 / 24,313,856 B).
4. Extract only the `kernel` and `root` members; re-check the uImage and UBI magic.
5. Write the kernel slot first (`mtd write`: erase+write), read back the exact member length and
   compare md5 with the member; then `ubiformat` the rootfs slot and re-read PEB 0's `UBI#`/`UBI!`
   headers.
6. `sync`, then (and only then) store the selector to the inactive pair and read it back; on any
   failure the selector stays/returns to the active pair, so the next boot still comes up on the
   untouched pair.
7. Return; the framework's `do_stage2` does the reboot. The function never reboots itself, never
   touches the active pair, `rootfs_data` (mtd15) or the env blocks.

It refuses, before any write: selector `0x21`/unknown/missing, selector-vs-rootfs mismatch, a member
over the slot budget, foreign image, failed container re-check, and failures in the kernel write,
rootfs format or selector store. `RAMFS_COPY_BIN` includes `mktemp sha256sum head`; `ubi-utils` is
in `DEFAULT_PACKAGES` because the write path calls `ubiformat`. [V]
[`opensource/target-skeleton/docs/port-notes/abinstall/SUMMARY.md`](opensource/target-skeleton/docs/port-notes/abinstall/SUMMARY.md) §3, §5.

**Mocked validation** (host-only): `opensource/target-skeleton/tools/test-platform-abinstall.sh` sources the real
`platform.sh` against fake `/proc/mtd`, fake `ubi0/mtd_num`, fake selector sysfs and
`mtd`/`ubiformat`/`sync`/`reboot` shims: **52/52** fixture assertions pass and **58/58** pass with
`--container` on the real built image, covering A→B and B→A choice, the required
kernel→rootfs→sync→selector order, and every refusal path. [V]
[`opensource/target-skeleton/docs/port-notes/abinstall/SUMMARY.md`](opensource/target-skeleton/docs/port-notes/abinstall/SUMMARY.md) §5;
[`STATUS.md`](STATUS.md) §3.

### 8.5 What is proven, and what is not

**Proven (host-only):**

- The image recipe is valid OpenWrt idiom and builds end to end in a normal `make world`; every
  artifact is validated from its own bytes at build time and re-validated independently
  (`check-container` PASS; real `platform_check_image` PASS; corrupted/wrong-board/foreign images
  refused). [V]
- The 001–015 build is byte-reproducible; the final 001–017 build reaches RC=0. [V]
- The A/B selector interface and the write-path logic are implemented with measured values and
  verified by a mocked harness against the real container. [V] (mocked)
- The load/entry derivation and FIP gate are asserted at build time and match the decoded loader
  behaviour. [V]

**Not proven (hardware; every one needs an attended, recovery-armed session):**

1. The stock loader accepting a **novel generated trailer** and a full image (vs the vendor trailer).
2. Kernel execution from the built slice; rootfs UBI mount, `rootfs_data` overlay and
   `/chosen/bootargs` hand-off (`root=`/`ubi.*` question).
3. The A/B upgrade path end to end: write inactive pair → boot written pair → confirm `ubi0` attaches
   the other rootfs slot and `current_pair` matches → switch back/rollback.
4. The loader env re-stamp (`fw_printenv bootflag`), the in-boot cell state on both pairs, and the
   `0x21` manual state.
5. NAND writes under the FMC/ECC geometry and bad-block behaviour; ramfs shipping of
   `mtd/ubiformat/sha256sum/mktemp/head`; `platform_check_image` re-run inside the ramfs.
6. The first boot of the written pair, rollback, and interaction of the selector store with the
   restart driver's write-same.
7. The first-install/factory path (§8.6).
8. The package/rootfs scope: feeds were not installed, so the rootfs is the core package set
   (73 packages configured), not a release image; the sketch's `ubifs`/`kmod-mtd-rw` packages were
   not built. [V]/[U]
   [`opensource/target-skeleton/docs/port-notes/image/SUMMARY.md`](opensource/target-skeleton/docs/port-notes/image/SUMMARY.md) "What is NOT proven".

### 8.6 The first-install question (still open)

The stock loader only accepts the FIP container, and this unit's UART cannot type, so the usual
"TFTP rescue console install" is not available. The design questions are: [V]/[U]
[`TARGET-DESIGN.md`](opensource/docs/TARGET-DESIGN.md) §5.5.

1. Can the stock TFTP recovery (RESET-counter entry, `recovery.bin`) write an arbitrary image, or
   does it verify/expect a vendor container? The repo does not characterise its write path. [U]
2. Can the first install be done from the stock vendor userspace (root shell over LAN) with
   `mtd write`/`ubiformat` to the inactive slot, exactly as the project's earlier 0.1–0.3 builds
   did? That path is **measured** for rootfs `ubiformat` and kernel slot writes and is the safest
   documented installer, though it requires temporary root on the vendor firmware. [V]
   [`opensource/docs/FLASH-PLAN.md`](opensource/docs/FLASH-PLAN.md); [`opensource/docs/HYBRID-IMAGE-PLAN.md`](opensource/docs/HYBRID-IMAGE-PLAN.md).
3. Only if both fail: a U-Boot-compatible full-image container for TFTP. [U]

The device page must not be written and the target must not claim installability until one of these
is executed end to end on a recovered unit. [I]

### 8.7 Record discrepancy to resolve

The committed A/B port note quotes the "real built sysupgrade.bin" as `6,185,262 B` sha256
`0303d76a…`, while the 2026-11-18 15:55 ledger entry and [`EVIDENCE-INDEX.md`](EVIDENCE-INDEX.md)
give the **final 001–017** container as `6,185,262 B` sha256 `e869f105…` (the `0303d76a…` value is
the 001–016 build from the 15:20 ledger entry). The `58/58` harness run is described as "on the real
container" without a hash pairing in one of the two places. **Action before citing:** re-run
`opensource/target-skeleton/tools/test-platform-abinstall.sh --container <final-001-017-image>`
and record the pairing; do not assume the hashes are interchangeable. This report uses the ledger
15:55 / EVIDENCE-INDEX values as canonical for the final build. [V]/[U]

---

## 9. Remaining gates

All bench gates require the standing conditions: UART read-only, recovery door READY, a human at
the bench, preflight PASS, one variable per fire, and a written hypothesis. Fires are currently
**stopped**; nothing below authorises a fire. [V] [`BENCH-FACTS.md`](BENCH-FACTS.md) §2–§6;
[`STATUS.md`](STATUS.md) §3.

| gate | what it closes | kind | entry criteria / notes | state |
| --- | --- | --- | --- | --- |
| **G-BOOT-1** novel trailer + kernel slice boot | stock loader accepts a generated trailer; our 6.18 kernel prints its own console; no silent reset; stock fallback verified | attended bench | built slice+trailer+manifest from the 001–017 tree; preflight; recovery READY; capture identifies our `Data Size`/`Image Name` **plus** our kernel output | [U] |
| **G-BOOT-2** rootfs/overlay/bootargs | squashfs-UBI root mounts, `rootfs_data` overlay works or is explicitly wiped, `root=/ubi.*` hand-off confirmed | attended bench | G-BOOT-1 plus the minimal cmdline; decide `/chosen/bootargs` override question | [U] |
| **G-INSTALL-1** attended A/B upgrade | write inactive pair, boot it, confirm `ubi0` attaches the other rootfs slot and `current_pair` matches, switch back/rollback | attended bench | G-BOOT-2; one recovered unit; the two-witness logic and refuse paths already mocked | [U] |
| **G-INSTALL-2** env/cell re-stamp + `0x21` | read `fw_printenv bootflag` before/after; read the in-boot cell on both pairs; measure the `0x21` manual state; establish an A-side manual handover value | attended bench (read-only) | G-INSTALL-1 or a controlled slot switch; stock kernel acceptable for reads | [U] |
| **G-NAND** write/read-back under FMC/ECC/bad blocks | kernel/rootfs writes survive ECC semantics; `ubiformat` on this geometry; a bad-block case; ramfs bin set works | attended bench | G-BOOT-2; the FMC open questions in §5.6 | [U] |
| **G-LSW-D1b** switch inventory + write set | reviewed minimal write set for clock/reset/qid-map/EQM; D1c host-queue path; D1d Linux bridge; M2 ("no vendor network modules") measured | host + 1–2 attended read-only sessions (stock kernel acceptable for reads) | patch `016`; LSW-SPEC §12.2/§12.3 W1/W2; a bootable 6.18 target for the writes | [U] |
| **G-PIE-P3** PIE read-only inventory | register/ring/channel baseline on hardware before any ring programming; then P0–P5 bring-up per spec | attended read-only, then attended writes | patch `015`; PIE-DATAPATH §11–§12; treat every MMIO write as a bench-safety event | [U] |
| **G-PCIE** PCIe enumeration | RC link/enumeration and endpoint binding; Wi-Fi endpoint [X] | attended bench | patch `013`/`014`; hard rules encoded; never read the misc window | [U] |
| **G-WIFI** Wi-Fi decision | source/licence answer, or documented-blob exception, or funded rewrite | external/human | GPL request items 7–8; [X] today | [X] |
| **G-GPL** source request | sent copy + receipt; reply; artefacts 1–4/5–6 | **human action** | follow-up ready in GPL-REQUEST; no agent can send mail | [U]/[X] |
| **G-PUBLISH** publish boundary | history purge; GPL-2.0 text + SPDX/DCO; provenance statement; reproducible trailer recipe; single upstream DTS; Wi-Fi/LAN-switch statement | host | OPEN; the root repo stays private until done | [U] |
| **G-SMP/MAC/bootargs** | platsmp port or documented UP-first plan; MAC address source; bootargs decision | host + attended | optional for a first wired-only submission, but must be stated | [U] |
| **G-INSTALL-0** first-install/factory path | one of the three install paths in §8.6 executed end to end | attended bench | after G-BOOT-2 | [U] |

Suggested order (host work can proceed without the box; bench work is strictly serial and
attended): G-GPL (human, start now) → G-PUBLISH (host, parallel) → G-LSW-D1b/G-PIE-P3 read-only
inventories (the only bench work that is read-only and can inform the write sets) → G-BOOT-1 →
G-BOOT-2 → G-NAND → G-INSTALL-2 → G-INSTALL-1 → G-INSTALL-0 → G-LSW-D1c/D1d and G-PCIE. The
selector/install work has no hardware dependency beyond G-BOOT-2, but it must not be called
validated before G-INSTALL-1. [I] [`opensource/docs/LSW-SPEC.md`](opensource/docs/LSW-SPEC.md) §11;
[`opensource/docs/PIE-DATAPATH.md`](opensource/docs/PIE-DATAPATH.md) §11;
[`STATUS.md`](STATUS.md) §4.

---

## 10. Evidence map (paths and commands)

Two rules from the repository govern this map: **a claim with only a local artifact is not a
fresh-clone receipt**, and every claim that matters should have a regeneration command. [V]
[`EVIDENCE-INDEX.md`](EVIDENCE-INDEX.md) header.

Path convention: a plain path is in the root (private) repository; paths under `opensource/` are in
the published submodule. "Local artifact" means gitignored evidence under `build/`, `dumps/`,
`firmware/`, `rootfs-*/` or `patched/` — present in this checkout, not reproducible from a fresh
clone. Never quote the local artifacts as public receipts.

### 10.1 Claim → evidence table

| claim | committed evidence | local-only evidence | check / regenerate |
| --- | --- | --- | --- |
| live bench state, gates, next action | [`STATUS.md`](STATUS.md) (the only live page) | — | `tools/session-brief.sh`; regenerate STATUS at session end |
| hardware identity (luofu R116, not MT7981 v1) | [`HARDWARE-IDENTITY.md`](HARDWARE-IDENTITY.md); [`BENCH-FACTS.md`](BENCH-FACTS.md) §1 | U-Boot banner capture `dumps/router-20261108/uboot_capture6.log` | re-read the U-Boot banner and the live DTS compatible (device work) |
| UART is read-only (host→router TX dead) | [`HARDWARE-IDENTITY.md`](HARDWARE-IDENTITY.md) "UART: READ-ONLY"; [`BENCH-FACTS.md`](BENCH-FACTS.md) §3 | marker-test logs `build/uart-logs/` | `tools/uart-capture.sh` only; **never** a key-flood test |
| bench link / host addresses | [`BENCH-FACTS.md`](BENCH-FACTS.md) §2 | `tools/session-brief.sh` output | `tools/bench-link.sh` |
| physical recovery (RESET counter + TFTP) | [`BENCH-FACTS.md`](BENCH-FACTS.md) §4; [`HARDWARE-IDENTITY.md`](HARDWARE-IDENTITY.md) | `build/uart-logs/20261116T115756Z-recover-stock.log` | `tools/recovery-card.sh`; `md5sum tftp/recovery.bin` = `421114c8…`; attendance required |
| flash map / slot sizes / selector cell | [`TARGET-DESIGN.md`](opensource/docs/TARGET-DESIGN.md) §3.3–§3.4; [`BENCH-FACTS.md`](BENCH-FACTS.md) §5 | `dumps/router-20261108/full/proc_mtd.txt`, `enva.bin` | read `/proc/mtd`/DT on the device (read-only) |
| G1 FMC reads real flash | [`STATUS.md`](STATUS.md) §2; [`EVIDENCE-INDEX.md`](EVIDENCE-INDEX.md) G1 | `dumps/router-20261108/ubi-readpath-report.md` | boot a probe image and read page 0 / `PEB0+0x800` (attended) |
| G2 FMC write path byte-exact | [`opensource/docs/phase53-write-path-proof.md`](opensource/docs/phase53-write-path-proof.md); [`EVIDENCE-INDEX.md`](EVIDENCE-INDEX.md) G2 | ledger 2026-11-03/08; fire logs | write a page, read it through the vendor kernel (attended) |
| G3 vendor userspace on our kernel | [`STATUS.md`](STATUS.md) §2; [`PLAN-FULL-REVERSAL.md`](PLAN-FULL-REVERSAL.md) Phase C | build #162 captures | boot Phase C image, read the kernel-version breadcrumb |
| G4 Ethernet stack on our kernel; M2 NOT met | [`STATUS.md`](STATUS.md) §2; [`opensource/docs/VENDOR-STACK-ON-MAINLINE.md`](opensource/docs/VENDOR-STACK-ON-MAINLINE.md); [`EVIDENCE-INDEX.md`](EVIDENCE-INDEX.md) G4 | `build/linux-kbuild/fire-*.log` | load the patched modules, check `eth2`/`br-lan`/ping; note the bound PHY driver |
| G5 Wi-Fi is vendor-only | [`STATUS.md`](STATUS.md) §2; [`opensource/docs/phase49/README.md`](opensource/docs/phase49/README.md) | ledger 2026-11-14 | boot the lab line, check for a wiphy — none from our driver |
| G6 reset was a userspace watchdog race | [`STATUS.md`](STATUS.md) §2; ledger 2026-11-13/14 | keeper captures | boot the keeper image and hold the 25-minute timer |
| bench kernel line v6–v17 | [`EVIDENCE-INDEX.md`](EVIDENCE-INDEX.md) "Bench kernel line" section; [`STATUS.md`](STATUS.md) §3; [`opensource/docs/VENDOR-SKB-BRIDGE-PORT.md`](opensource/docs/VENDOR-SKB-BRIDGE-PORT.md) §2 | `build/linux-kbuild/luofu-slice-phase3dq.bin` (v17 md5 `8342ccb9…`); `build/uart-logs/20261117T233458Z-uart-v17.log` | rebuild via `build/linux-kbuild/build-3dq.sh` (gitignored); validate trailer via `tools/fire-preflight.sh`; captures prove only what the quoting line says |
| FIP trailer structure + generator | [`opensource/target-skeleton/docs/TRAILER-FORMAT.md`](opensource/target-skeleton/docs/TRAILER-FORMAT.md); [`EVIDENCE-INDEX.md`](EVIDENCE-INDEX.md) FIP row | `build/linux-kbuild/slice-trailer-40732.bin`; vendor images | `python3 opensource/target-skeleton/tools/fip-slice.py check-trailer build/linux-kbuild/slice-trailer-40732.bin`; split/diff vs `dumps/router-20261108/full/mtd11-kernela.bin` per TRAILER-FORMAT §10 |
| 11-row overlay match table / gate | [`TRAILER-FORMAT.md`](opensource/target-skeleton/docs/TRAILER-FORMAT.md) §3–§6 | U-Boot dumps `dumps/router-20261108/uboota.bin` | `objdump` command in TRAILER-FORMAT §10 item 3 |
| stock firmware versions / 58 GPL modules | [`opensource/docs/GPL-REQUEST.md`](opensource/docs/GPL-REQUEST.md); [`opensource/NOTICE.md`](opensource/NOTICE.md); [`HARDWARE-IDENTITY.md`](HARDWARE-IDENTITY.md) | `rootfs-2.4.15/`, `rootfs-2.5.24/`, `firmware/` | `strings rootfs-2.4.15/lib/hisilicon/ko/hi_kmac.ko \| grep license=` (local fixtures; do not publish) |
| GPL request sent 2026-10-01, no reply/copy | [`opensource/docs/GPL-REQUEST.md`](opensource/docs/GPL-REQUEST.md) "Status"/"Request tracking"; [`opensource/docs/PUBLISH-READINESS.md`](opensource/docs/PUBLISH-READINESS.md) item 3 | — | read the tracking table; the sent copy/receipt is the open gap; sending is a human action |
| vendor module graph / load order | [`opensource/docs/VENDOR-STACK-ON-MAINLINE.md`](opensource/docs/VENDOR-STACK-ON-MAINLINE.md); [`opensource/docs/LSW-SPEC.md`](opensource/docs/LSW-SPEC.md) §2.2 | vendor `.ko` fixtures | `modinfo`/`nm -S`/`readelf -sW` on a local fixture; do not commit |
| HSLINK/rootif chain | [`opensource/docs/VENDOR-SKB-BRIDGE-PORT.md`](opensource/docs/VENDOR-SKB-BRIDGE-PORT.md) §3.3–§3.4; [`opensource/docs/LSW-SPEC.md`](opensource/docs/LSW-SPEC.md) §9.1 | ledger 2026-11-17 18:55 | symbol/string checks on `hi_swa.ko`/`hi_kcfe_pub.ko` locally |
| WEXT net_device ABI | [`opensource/docs/VENDOR-SKB-BRIDGE-PORT.md`](opensource/docs/VENDOR-SKB-BRIDGE-PORT.md) §3.2; `opensource/docs/phase14/abi-match.md`; `phase14/wifidrv0.md` | vendor `mac80211.ko`/`cfg80211.ko` fixtures | read the offsets from the vendor instructions; record the command used |
| vendor sk_buff ABI | [`opensource/docs/VENDOR-SKB-BRIDGE-PORT.md`](opensource/docs/VENDOR-SKB-BRIDGE-PORT.md) §3.1; ledger 2026-11-17 20:40 | `hi_khslink.ko`/`hyfi-bridging.ko` fixtures | `objdump -dr` the named functions; **commit the RE notes** (0x51/0x53/0xb8 still live in session memory only) |
| four br_* pointer variables | [`opensource/docs/VENDOR-SKB-BRIDGE-PORT.md`](opensource/docs/VENDOR-SKB-BRIDGE-PORT.md) §3.3 | `hyfi-bridging.ko` symbol table | `nm` on the fixture; check `tools/lab-src/` for the exported pointers |
| PIE layering/registers/rings | [`opensource/docs/PIE-DATAPATH.md`](opensource/docs/PIE-DATAPATH.md) §1–§8, §13 | `hi_kpie.ko`/`hi_kmac.ko` fixtures; local RE dumps | commands in PIE-DATAPATH §13.2 (`nm`/`readelf`/`objdump`) |
| LSW layering/register map/port model | [`opensource/docs/LSW-SPEC.md`](opensource/docs/LSW-SPEC.md) §1, §5–§9, §14 | LSW/CFE `.ko` fixtures; local RE dumps | commands in LSW-SPEC §2.3/§14 |
| FMC SPI-NAND finding | [`opensource/docs/phase53-write-path-proof.md`](opensource/docs/phase53-write-path-proof.md); [`opensource/target-skeleton/docs/port-notes/fmc/SUMMARY.md`](opensource/target-skeleton/docs/port-notes/fmc/SUMMARY.md) | lab 5.10 driver `tools/lab-src/drivers/mtd/nand/luofu/luofu-fmc.c`; bench fire logs | the G1/G2 checks above; hardware open questions listed in §5.6 |
| driver series 001–017 host validation | [`opensource/docs/SKELETON-SMOKE.md`](opensource/docs/SKELETON-SMOKE.md); per-lane `port-notes/*/SUMMARY.md`; [`EVIDENCE-INDEX.md`](EVIDENCE-INDEX.md) driver rows | local lane dirs `build/linux-kbuild/waves/upstream-6.18-*` | `patch -p1 --dry-run`, `make target/linux/prepare`/`compile`, `dt_binding_check`, `checkpatch.pl`, config re-derivation (see command block) |
| final image + reproducibility | [`EVIDENCE-INDEX.md`](EVIDENCE-INDEX.md) image row; `opensource/target-skeleton/docs/port-notes/image/SUMMARY.md` | isolated clone `~/openwrt-lab-image` (disposable) | `make world -j16`; `python3 opensource/target-skeleton/tools/luofu-image.py check-container <image>` |
| A/B install path + mocked harness | [`opensource/target-skeleton/docs/port-notes/abinstall/SUMMARY.md`](opensource/target-skeleton/docs/port-notes/abinstall/SUMMARY.md); patch `017`; `STATUS.md` §3 | — | `bash opensource/target-skeleton/tools/test-platform-abinstall.sh --container <image>` (see §8.7 for the hash pairing) |
| Wi-Fi port surface / [X] | [`opensource/docs/TARGET-DESIGN.md`](opensource/docs/TARGET-DESIGN.md) §8.3; [`opensource/docs/PORT-SURFACE.md`](opensource/docs/PORT-SURFACE.md); [`EVIDENCE-INDEX.md`](EVIDENCE-INDEX.md) G5 | vendor modules/firmware blob | symbol-census on `hi5622v100_wifi.ko` (0 mac80211 symbols, 211 namespaced imports) |
| publish boundary / NOT READY | [`opensource/docs/PUBLISH-READINESS.md`](opensource/docs/PUBLISH-READINESS.md); [`opensource/NOTICE.md`](opensource/NOTICE.md); [`EVIDENCE-INDEX.md`](EVIDENCE-INDEX.md) "Publish boundary" | vendor history | `git -C opensource rev-list --objects --all \| grep -E '\.(o\|ko)$'` must be empty before publication |

### 10.2 Command reference (host-side, read-only or isolated)

Repository hygiene and state:

```
tools/session-brief.sh
git rev-parse --short HEAD                 # root pin
git -C opensource rev-parse --short HEAD   # published-half pin
tools/check-repo.sh
tools/check-lab-src.sh
tools/check-init-shadow.sh
python3 tools/gen-ledger-index.py
```

FIP trailer (needs the local artifacts named):

```
python3 opensource/target-skeleton/tools/fip-slice.py check-trailer \
  build/linux-kbuild/slice-trailer-40732.bin
# fixed trailer == first 40,732 B of the 2.4.15 vendor container
python3 - <<'PY'
from pathlib import Path
t = Path("build/linux-kbuild/slice-trailer-40732.bin").read_bytes()
v = Path("dumps/router-20261108/full/mtd11-kernela.bin").read_bytes()
ih = int.from_bytes(v[12:16], "big")
print(t == v[0x40+ih:0x40+ih+40732])       # True
PY
# applier disassembly (U-Boot, file 0x344ec region)
build/linux-kbuild/toolchain/bin/arm-none-linux-gnueabihf-objdump -D -b binary -m arm \
  --adjust-vma=0x8003ff00 --start-address=0x800743ec --stop-address=0x800746c0 \
  dumps/router-20261108/uboota.bin
```

Kernel series validation (in an isolated OpenWrt clone; never the shared tree):

```
make defconfig
make target/linux/prepare
make target/linux/compile V=s -j16        # must be RC=0, 0 warnings under CONFIG_WERROR
make ARCH=arm dt_binding_check DT_SCHEMA_FILES=<yaml>
# canonical config re-derivation (must be idempotent / byte-identical twice)
yes '' | make -C target/linux TOPDIR=$PWD oldconfig
# load-address contract
build/linux-kbuild/toolchain/bin/arm-none-linux-gnueabihf-nm vmlinux | grep ' _text$'
```

Image and install-path checks (need the built image from the isolated clone):

```
python3 opensource/target-skeleton/tools/luofu-image.py check-container <sysupgrade.bin>
bash opensource/target-skeleton/tools/test-platform-abinstall.sh --container <sysupgrade.bin>
```

RE reads (local fixtures only; never commit the fixtures):

```
T=build/linux-kbuild/toolchain/bin
K=rootfs-2.4.15/lib/hisilicon/ko
modinfo $K/hi_kpie.ko
$T/arm-none-linux-gnueabihf-nm -S $K/hi_kpie.ko
$T/arm-none-linux-gnueabihf-readelf -sW -rW $K/hi_kpie.ko
$T/arm-none-linux-gnueabihf-objdump -dr --no-show-raw-insn $K/hi_kpie.ko
$T/arm-none-linux-gnueabihf-objdump -s -j .rodata -j .data -j .rodata.str1.4 $K/hi_lsw_pfe.ko
strings -a $K/hi_lsw_pfe.ko | head -200
strings $K/hi_kmac.ko | grep license=
```

Publication checks (must pass before the published half goes public):

```
git -C opensource rev-list --objects --all | grep -E '\.(o|ko)$'   # must be empty after purge
git -C opensource ls-files | grep -E '^target/linux'                # empty until a real target is tracked
```

Bench tools (gated; listed for completeness, **not run for this report**): `tools/bench-link.sh`,
`tools/recovery-card.sh`, `tools/fire-preflight.sh`, `tools/uart-capture.sh`, `tools/fire.sh`.
They require a human at the bench and the recovery door READY; the UART path is read-only. [V]
[`BENCH-FACTS.md`](BENCH-FACTS.md) §2–§6; [`RUNBOOK.md`](RUNBOOK.md).

---

## 11. Limitations, record discrepancies and publication boundary

### 11.1 Limitations of this report and its evidence

1. **Host-only synthesis.** This report was produced without touching the router, UART, TFTP, flash
   or fire tools. It reflects the committed record at the pins in the header; `STATUS.md` is the
   only live state and may have moved since.
2. **Local-only artifacts are not fresh-clone receipts.** Console captures, slices, fire logs,
   dumps, rootfs trees, firmware images and vendor modules are gitignored evidence present in this
   checkout. They back real [V] claims but cannot be regenerated on a fresh clone; the regeneration
   commands above are the substitute. Do not publish or quote the artifacts themselves.
3. **Some RE evidence is only partly committed.** The vendor sk_buff private bytes 0x51/0x53/0xb8
   and the `hi_cfe_intf_rx` expectation were recorded in the ledger/RE session but the disassembly
   notes were not committed; they remain [U] and must be re-derived before being cited as proven.
   Only 0xb4 is corroborated by a committed spot-check. [V]/[U]
   [`opensource/docs/VENDOR-SKB-BRIDGE-PORT.md`](opensource/docs/VENDOR-SKB-BRIDGE-PORT.md) §3.1, §9 Q2–Q3.
4. **The hardware gates are and remain [U].** Nothing in this report may be read as "the image
   boots", "the install works", "the switch forwards", "the PHY links on 6.18", "PCIe enumerates" or
   "Wi-Fi works". The documents that say so in their own headers are correct; the benches are
   stopped.
5. **Some image hashes vary by build stage** (001–015 / 001–016 / 001–017). The canonical final
   001–017 numbers are quoted in §8.3; earlier numbers are kept for traceability, not as
   interchangeable receipts.
6. **The 2026-11-14 LAN-green counter-example is vendor-module-backed.** It proves the vendor stack
   can reach LAN on our kernel in that configuration; it does not prove a clean-room LAN path and it
   does not resolve the v17 causal question (Q1). [V]/[U]
   [`opensource/docs/VENDOR-SKB-BRIDGE-PORT.md`](opensource/docs/VENDOR-SKB-BRIDGE-PORT.md) §2.4.
7. **The "clean-room" label is corrected, not achieved.** The drivers were derived by disassembly of
   vendor GPL binaries; the honest provenance statement is GPL-compatible reverse engineering with
   GPL-2.0 licensing and attribution. Publication review must apply that framing. [V]
   [`opensource/docs/PUBLISH-READINESS.md`](opensource/docs/PUBLISH-READINESS.md).

### 11.2 Known record discrepancies (do not propagate)

| # | discrepancy | resolution |
| --- | --- | --- |
| 1 | A/B port note quotes the "real built" container as `6,185,262 B` sha `0303d76a…`, while the final 001–017 ledger/EVIDENCE-INDEX value is `6,185,262 B` sha `e869f105…` (`0303d76a…` is the 001–016 build) | re-run `opensource/target-skeleton/tools/test-platform-abinstall.sh --container <final image>` and record the pairing; this report treats `e869f105…` as the pre-correction 001–017 container (see the addendum for the post-correction `362ca4ec…`) |
| 2 | root [`README.md`](README.md) two-track bullet still says "Current blocker: the slice-delivery lane"; [`STATUS.md`](STATUS.md) §3 records the bench line at its documented ceiling with fires stopped | STATUS wins (per [`AGENTS.md`](AGENTS.md): STATUS is the only live page); README is a pointer and should be regenerated at session end. Not edited by this report (the deliverable is this new root file only) |
| 3 | [`opensource/docs/TARGET-DESIGN.md`](opensource/docs/TARGET-DESIGN.md) header still describes only "the first two drivers" as drafts, while its §7.1 and [`STATUS.md`](STATUS.md) §3 record the whole 001–017 series | read the per-section status rows and STATUS; the design header predates the later lanes. Not edited by this report |
| 4 | [`opensource/docs/PORT-STATUS.md`](opensource/docs/PORT-STATUS.md), [`DEPLOYMENT-DECISION.md`](opensource/docs/DEPLOYMENT-DECISION.md), [`HYBRID-IMAGE-PLAN.md`](opensource/docs/HYBRID-IMAGE-PLAN.md) are historical/superseded | they carry their own banners; do not use for current state |

### 11.3 The publication boundary (as of the pins)

- **The root repository is private research material and must stay private** until the cleanup in
  [`EVIDENCE-INDEX.md`](EVIDENCE-INDEX.md) "Publish boundary" is done. It tracks vendor-derived
  binaries/objects, de-crypted vendor Lua (`patched/`), dumps, rootfs trees and firmware images.
  [V]
- **The published half (`opensource/`) is NOT READY.** [`opensource/docs/PUBLISH-READINESS.md`](opensource/docs/PUBLISH-READINESS.md)
  lists the open items; the load-bearing ones are:
  - ten vendor `.o` files from a TR6560 BSP remain in **history** (removed from HEAD 2026-11-17) and
    must be purged with a history rewrite, verified empty by the `rev-list` command above;
  - no GPL-2.0 `COPYING` text, per-file SPDX/copyright notices or DCO convention yet (the split is
    MIT for scripts/docs, GPL-2.0 for kernel code under `lab/`);
  - the GPL request has **no sent copy, receipt or reply** in the repository;
  - the provenance statement (GPL-compatible reverse engineering, not clean-room) must replace the
    old label in any submission text;
  - a single upstream-style DTS and the FIP-trailer regeneration recipe are not yet published
    artifacts (the generator exists in the skeleton but the bench lane still copies a fixed trailer);
  - the Wi-Fi/LAN-switch statement must accompany any submission: the radio is vendor-binary with
    a closed 928,920-byte firmware blob and an unanswered GPL request, and the switch driver does
    not exist. [V]
- **Legal/provenance facts to carry forward:** the vendor modules declare `license=GPL` (58/58) and
  the sources are requested under GPLv2 §3; the firmware blob's licence is unresolved; any received
  source must be checked for a GPL-compatible licence before publishing, and non-redistributable
  material stays in the private store. [V] [`opensource/docs/GPL-REQUEST.md`](opensource/docs/GPL-REQUEST.md)
  "What we publish and what we keep private"; [`opensource/NOTICE.md`](opensource/NOTICE.md).
- **Do not present the bench gates as upstream progress, and do not present the upstream drafts as
  a working port.** There is no OpenWrt target PR, no reviewed DTS, no merged driver series, no
  executed install path and no Wi-Fi answer today. [V] [`opensource/docs/PUBLISH-READINESS.md`](opensource/docs/PUBLISH-READINESS.md);
  [`opensource/docs/TARGET-DESIGN.md`](opensource/docs/TARGET-DESIGN.md) §9.

### 11.4 What would change this report

- A reply (or a receipt) to the GPL request: it could convert the bridge/HYFI, sk_buff, LSW and PIE
  rows from RE to port work and change the schedule more than any code decision.
- One attended boot of a novel generated trailer + a full image (G-BOOT-1/2) and one attended A/B
  install (G-INSTALL-1/2): they would retire the largest [U] block in §8.
- The LSW D1b and PIE P3 read-only inventories: they would turn the switch/PIE specs into measured
  register models and set the D1c/D1d and P1–P5 plans on evidence.
- A hardware validation of the 001–017 series (console, FMC, MDIO/PHY, thermal, pinctrl, restart):
  it would move the largest [U] column in §7 to [V] or expose defects (the CRG polarity fix shows
  that hardware validation does find real bugs).

---

## Appendix A — Glossary

| term | meaning |
| --- | --- |
| **FIP / FIP slice** | vendor boot package: uImage + trailer (base DTB + DTBO overlay container). The stock loader `bootfip` only accepts this shape. |
| **DTBO / overlay** | device-tree fragment applied to the base DTB by the loader; matched by `vendor_id`/`compatible`/`board_id`. |
| **gate magic** | `0xd7b7ab1e` at `base_dtb + base_totalsize`; the uImage is entered only if the applier returns 0. |
| **HSLINK** | vendor interface-management layer (console tag `[HSLINK]`; `hi_khslink`/`hi_swa`); owns interface lifecycle and the CFE/rootif bookkeeping. |
| **HYFI** | vendor accelerated/offloaded bridge contract: `hyfi-bridging.ko` + `hyfibrd` userspace over a vendor-private netlink protocol. |
| **rootif** | a named Linux netdev registered into the CFE's 32-entry interface table by `hi_cfe_add_rootif`; a software compatibility construct, not a hardware API. |
| **CFE** | vendor software forwarding/control plane (`hi_kcfe_*`, `hi_kcara`) on top of the LSW/PFE tables. |
| **LSW** | the SoC's internal Ethernet switch: queue/queue-map engine + classification/forwarding tables; vendor drivers `hi_lsw_pub/dp/pfe`. |
| **PIE** | the SoC packet engine (`hi_kpie`): DMA rings, NAPI, per-port contexts; the wired data path, not the MAC. |
| **EQM/EPS/IPS** | LSW sub-blocks: queue manager, egress/ingress port schedulers (module ids in the synthetic register map). |
| **WEXT** | Linux Wireless Extensions; the vendor kernel had `CONFIG_WIRELESS_EXT=y`, adding two pointers to `struct net_device`. |
| **sk_buff ABI** | the measured vendor `struct sk_buff` layout (+0x74/+0x78) the vendor modules were compiled against. |
| **SPI-NAND / FMC** | the NAND flash and its controller; 2048-byte pages, 64-byte OOB, 128 KiB blocks, ESMT F50L1G41LC. |
| **UBI / squashfs** | the rootfs format in each rootfs slot (static UBI volume named `squashfs`); `rootfs_data` is the JFFS2 overlay. |
| **M2** | the bench-reversal milestone "no vendor network modules bound"; **NOT met** (vendor `hi_kphy` was bound in the green 2026-11-14 stack). |
| **G1–G6** | bench-reversal gates (FMC read, FMC program, vendor userspace on our kernel, Ethernet, Wi-Fi, sustained uptime). |
| **[V]/[I]/[U]/[X]** | evidence markers defined in §1.2. |

## Appendix B — Document index (where the long form lives)

| topic | document |
| --- | --- |
| live state / gates / next action | [`STATUS.md`](STATUS.md) |
| claim→artifact map | [`EVIDENCE-INDEX.md`](EVIDENCE-INDEX.md) |
| ledger (append-only) + index | [`mem-entries.md`](mem-entries.md), [`mem-entries-INDEX.md`](mem-entries-INDEX.md) |
| hardware identity / UART | [`HARDWARE-IDENTITY.md`](HARDWARE-IDENTITY.md) |
| physical invariants / bench rules | [`BENCH-FACTS.md`](BENCH-FACTS.md), [`LESSONS.md`](LESSONS.md), [`RUNBOOK.md`](RUNBOOK.md) |
| bench reversal plan | [`PLAN-FULL-REVERSAL.md`](PLAN-FULL-REVERSAL.md) |
| curated truths | [`CURRENT-TRUTHS.md`](CURRENT-TRUTHS.md) |
| upstream target/DTS/image design | [`opensource/docs/TARGET-DESIGN.md`](opensource/docs/TARGET-DESIGN.md), [`opensource/docs/TARGET-SKELETON.md`](opensource/docs/TARGET-SKELETON.md) |
| upstream roadmap | [`opensource/docs/ROADMAP-OPENWRT.md`](opensource/docs/ROADMAP-OPENWRT.md) |
| FIP trailer format + generator | [`opensource/target-skeleton/docs/TRAILER-FORMAT.md`](opensource/target-skeleton/docs/TRAILER-FORMAT.md), [`opensource/target-skeleton/tools/fip-slice.py`](opensource/target-skeleton/tools/fip-slice.py) |
| driver/binding series + validation | [`opensource/docs/SKELETON-SMOKE.md`](opensource/docs/SKELETON-SMOKE.md), `opensource/target-skeleton/docs/port-notes/` |
| vendor stack on mainline | [`opensource/docs/VENDOR-STACK-ON-MAINLINE.md`](opensource/docs/VENDOR-STACK-ON-MAINLINE.md) |
| vendor sk_buff/bridge port | [`opensource/docs/VENDOR-SKB-BRIDGE-PORT.md`](opensource/docs/VENDOR-SKB-BRIDGE-PORT.md) |
| remaining drivers plan | [`opensource/docs/REMAINING-DRIVERS.md`](opensource/docs/REMAINING-DRIVERS.md) |
| PIE data-path spec | [`opensource/docs/PIE-DATAPATH.md`](opensource/docs/PIE-DATAPATH.md) |
| LSW switch spec | [`opensource/docs/LSW-SPEC.md`](opensource/docs/LSW-SPEC.md) |
| Ethernet bring-up framing | [`opensource/docs/ETHERNET-BRINGUP-FRAMING.md`](opensource/docs/ETHERNET-BRINGUP-FRAMING.md) |
| FMC write-path proof | [`opensource/docs/phase53-write-path-proof.md`](opensource/docs/phase53-write-path-proof.md) |
| GPL request | [`opensource/docs/GPL-REQUEST.md`](opensource/docs/GPL-REQUEST.md) |
| publish readiness | [`opensource/docs/PUBLISH-READINESS.md`](opensource/docs/PUBLISH-READINESS.md), [`opensource/NOTICE.md`](opensource/NOTICE.md), [`opensource/README.md`](opensource/README.md) |
| historical pages (not instructions) | [`docs/archive/README.md`](docs/archive/README.md) |

---

*End of report. This document is a synthesis, not a status page: consult [`STATUS.md`](STATUS.md)
before acting, [`BENCH-FACTS.md`](BENCH-FACTS.md) before touching the device, and
[`EVIDENCE-INDEX.md`](EVIDENCE-INDEX.md) before citing a claim.*
