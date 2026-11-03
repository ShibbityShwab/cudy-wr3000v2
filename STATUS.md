# STATUS - Cudy WR3000 v2.0

Regenerated, never appended. Last edit 2026-11-03 (the write-path session).
Current state: this file. The dated record is [`STATE.md`](STATE.md) and `mem-entries.md`; it is history
and is not a starting point. The claim-by-claim audit behind this page is
`build/audit/lane-e/DRIFT-MATRIX.md` (gitignored).

Pins are not written here. Derive them: `git rev-parse --short HEAD` and
`git -C opensource rev-parse --short HEAD`.

## 0. BENCH STATE - read this before trusting any "box healthy" line below

**As of 2026-11-01 the router is RECOVERED and HEALTHY on the vendor image.** It came back **on its own**
(no RESET hold was needed) after a strand caused by three `luofu_verdict_cell()` marks on sysctrl offsets
`C00`, `C10`, `C14` - cells the cell map lists as having **no writer**. That was read as "safe" and it is
not: unowned means no driver writes it, which says nothing about what the address does in hardware.
Record: `notes/facts/2026-11-01-safe-cells-stranded-the-box-unowned-is-not-safe`.

Verified over ssh after recovery:

| measurement | value |
| --- | --- |
| `SEL` (`0x10100C08`) | **`0x00000010`** - vendor slot |
| `/etc/openwrt_release` | `DISTRIB_RELEASE='22.03.6'` |
| kernel | `5.10.201` |
| wiphys | **2** (`phy0`, `phy1`) |
| `wifi-iface` sections | 8 |
| uptime at check | 820 s, no resets |
| ssh / http / https | open |

### The recovery left the box FACTORY-RESET, and the ssh failure was NOT a password problem

After the strand the box served the **first-run wizard** (`/cgi-bin/luci/` posts to
`/cgi-bin/luci/admin/wizard` with a per-page `salt`/`token`), and **root had no password at all** -
`passwd` reported *"password for root is already unlocked"*, so dropbear refused every login. Two traps,
both now measured:

- `chpasswd` **does not exist** on this image; `sh: chpasswd: not found`.
- The ssh host key change was **not** a factory-reset signature on its own - it was our kernel's key being
  replaced by the vendor's when the box returned to the vendor slot.

Working restore sequence: complete the wizard with the salted hash (`sha256(sha256(pw+salt)+token)`), then
use the authenticated `admin/system/systime` session to run
`(echo PW; echo PW) | passwd root; /etc/init.d/dropbear restart`. The systime field executes arbitrary
shell and its effect is readable over HTTP (write to `/www/`), which makes it a full root command channel.
`tools/web_login.sh` has the **wrong** salt hardcoded and targets the decoy wizard form - use the live
page's `salt`/`token`.

**Recovery door: armed and PROVEN.** `tftp/recovery.bin` - 20,975,775 B, md5
`421114c8ea999c925b7aa79cc548af81`; TFTP on UDP `0.0.0.0:69` verified by a real RRQ returning DATA block 1
starting `hboot1ta`; host `192.168.1.88` on `Ethernet`. Door procedure: **hold RESET ~15 s while powered**
(the documented hold is 15, not 10). A plain power cycle re-boots the slot the selector points at.

**Any statement below about the box being on the vendor image is still correct**, but the credential is new:
the working root password is in `.omo-secrets/ssh-password.txt`.

## 1. The goal
Our own, fully-current OpenWrt on this board: our kernel, our drivers, no vendor kernel. Set 2026-10-05.
Where it stands: **the FMC write path is proven** (2026-11-03) - direct page program, the mtd write
hook with the master mtd, multi-page/consecutive writes, and partial writes (the JFFS2 cleanmarker
shape) all land and read back from the vendor. The persistent overlay does not mount yet; the
remaining gate is `mtd_volume_identify`'s 4-byte read at offset 0 under our kernel (a raw read of a
mounted partition returns `ff` on this board and is void). The write-path evidence is
[`opensource/docs/phase53-write-path-proof.md`](opensource/docs/phase53-write-path-proof.md).

### ★ THE BOOT ORACLE IS NOT TRUSTED YET - read this before interpreting any fire

On 2026-11-01 five builds were fired and **one booted**. The one that booted is the current tree
(baseline + the `if (0)` mark guard), reproducing as `zImage af7013cf` - verified twice, byte-identical.

The four that went dark included two changes that **cannot plausibly make a boot less safe**:

| slice | change | result |
| --- | --- | --- |
| `7e208208` | none (baseline + mark guard) | **returned**, `C9C = 0xDFFE00AF` |
| `ea8fc3cd` | kick `op_ctrl \| 3u` (vendor's OR form) | dark |
| `f5fb6714` | spec-derived `OP_CFG` (`0x2B0`) | dark |
| `f93b24af` | panic path no longer takes an MTD mutex or programs flash | dark |

The last one sets a pointer to `NULL` and removes code. It shipped 416 B SMALLER, so the change reached
the object. **A change that can only remove work also failed**, which means "it came back" is not a clean
oracle on this bench.

**`panic=5` IN THE CMDLINE: a dark box is a HANG, NOT A PANIC.** `CONFIG_CMDLINE` carries `panic=5`, so a
panic reboots after five seconds. A box that stays dark is therefore hanging, and no panic-path mechanism
can explain it - independent grounds on which the panic-notifier theory was wrong, on top of its own
controlled fire.

**AND `ubi.mtd=rootfsb`: OUR KERNEL'S ROOTFS COMES FROM rootfsb (mtd14)** - the partition this project
writes probe rootfs images into. The boot therefore depends on that partition's current contents, which is
state we have been changing all session. Any boot comparison must record what rootfsb held at the time;
a difference there is a confound as large as the driver.

**Rule before any further write-path experiment: fire the SAME booting slice twice and confirm it returns
both times.** If it does not, no result from this lane that depends on "did it come back" is evidence
about the code, and fixing the oracle comes first.

## 2. Gates
One numbering, six rows. Each receipt is a file you can open.

| gate | status | receipt (evidence file) |
| --- | --- | --- |
| G1 FMC reads real flash | GREEN | `STATE.md:466` (`luofu_read_ecc_off = false` was the one-line fix); `STATE.md:2472` (`C88 = 0xE0021985`, a jffs2 dirent) |
| G2 program path | asserted, unlogged | no logged measurement exists. See §3. |
| G3 kernel + rootfs + userspace | PARTIAL: userspace and `rcS` run; overlay does not mount | `STATE.md:2188` (`C90 = "port"` -> `S99port_trigger_d`); `STATE.md:2196` (overlay failure chain); `STATE.md:4072` ("the overlay does not mount yet", in the "Not done, and honestly so" list) |
| G4 Ethernet on our kernel | ONE DEFECT FROM GREEN (2026-10-30) | `STATE.md:731` (ARP resolves, frames move, host ping 0/3) |
| G5 Wi-Fi on our kernel | VENDOR-ONLY | `STATE.md:732` (the gate row); `STATE.md:4036` and `STATE.md:4072` (`luofu-wifi` is not in the kernel fragment, so our image has no wifi driver) |
| G6 sustained uptime | the fix is built and committed, NOT confirmed by a fire | `STATE.md:344` says exactly that. Cause: the unfed watchdog, `/sbin/init` hands the fd to procd and procd never reaches its event loop, so the 30 s timeout expires (`STATE.md:284-290`) |

## 3. The one wall, and the write-path situation
The wall is the persistent overlay. Our kernel reaches userspace and completes `rcS`, but
`rootfs_data` block 0 reads `ff` through the layer fstools uses, so `volume_identify` answers `FS_NONE`,
overlayfs is never attempted, and the tmpfs fallback discards every `/www` write (`STATE.md:2196`).

The write path is ASSERTED-BUT-UNLOGGED in both directions.
- The claim "the current source writes" has no fire log: a search for `p163_nonff` across `build/`
  returns nothing. The number `p163_nonff = 2048 / p164_nonff = 0` does exist, but only in a session
  **transcript** from 2026-11-03 (three occurrences), never in a reproducible artefact under `build/`.
  So the measurement was really taken; it simply cannot be replayed from the repo. One boot that
  appends the `dd ... | wc -c` output to a fire log closes this permanently.
- The claim "the current source writes nothing" has no fire log either. The log for the single fire of slice
  md5 `6b7b28c09253b1572b575289f2145233` that returned reads `rootfs_data` block 0 as `ff ff ff ff`
  (`build/tmp/fire_rN_20261103.log:57`), i.e. page 163 was not programmed. Every other fire in that set
  ended `NO RETURN within 1500s` or aborted (`ABORT_unreachable_before_any_write`) with empty measurement
  sections.
- `build/tmp/fire_baseline_20261104.log` is the same fire from the same slice and says the same: `NO
  RETURN within 1500s`, block 0 `ff` (`:37`). Its mtd16 hexdump at the end is a pre-fire snapshot, which
  the file's own `OUT_PRE=[]` line at `:19` indicates; do not read it as a post-write page.
- `STATE.md:2188` item 3 claims "the FMC write path works through `luofu_mtd_write`", citing a jffs2
  volume on mtd16 written by our kernel. That is the source of the "works" assertion. It was not
  re-measured after the source loss, and no log backs it. Treat it as unverified.

### What the two rWP fires actually proved (2026-11-01)
Slice `eef70d6afa520f99c5d16bc232b9c6bf` carried three changes: probe clears WP instead of setting it,
`write_page` polls `OP_CTRL` bit 0, and no GET-FEATURE after the kick. With the cells primed, the boot
was attributable: `C18=0xC0DE5245` and `C70=0x00001F40` are ours, so the kernel ran. But
`C9C = 0x001EB70A` is one step **below** `0x1EB70F` = `run_init_process()` returned 0, i.e. **userspace
never started**. The rootfs `dd` that is supposed to program page 163 therefore never ran, and
`p163_nonff = 0` is a statement about userspace, not about the driver.

**Rule: a write test whose trigger lives in userspace cannot run on a kernel that never reaches
userspace. Read the boot signature before reading the measurement.**

This also removes the only mechanism the record offers for rM's asserted `p163_nonff = 2048`: that was a
userspace `dd` too. It does not prove rM never wrote, but it means the number cannot have been produced
the way it is described.

### The kernel-side write test, and where it stalls (2026-11-01, three boots)
The boot-path write at line ~6878 was retargeted from `log` page 12 to **`upgrade` page 163** and
enabled, with the existing `LUFU` sentinel pattern. Slices `79cfa129`, `072815b3`, `2494e4ce` all read
`p163_nonff = 0`.

Two attribution cells were added and **neither landed**:
- `C8C = 0x4b450000 | row` was to be written immediately BEFORE the call ("entered");
- `C94 = 0x4b000000 | ret<<8 | row` immediately AFTER it ("returned"), with `0xdead0000` for
  `get_mtd_device_nm("upgrade") == NULL`.

Both read back `0x55555555`, the primed value. So the block either is not reached or the cell channel is
dead there, and the two cannot currently be told apart.

**CORRECTION to an earlier reading in this session:** `C18 = 0xC0DE5245` is NOT this kernel's log tick.
The tick writes `C1C` through `luofu_crumb_base` (`luofu-fmc.c:5369-5370`, `0xc0de5000 | ticks`), and
`luofu_log_timer` is armed from three other sites as well (`5582`, `6238`, `7591`). `C18` is therefore
not evidence that the probe reached line 6833, and no claim here rests on it any more.

**The next instrument must prove itself first.** Write a distinctive value from a site that provably
executes (the `C1C` tick path is the recorded one), confirm it lands, and only then move the write test.
Without that, every `p163 = 0` is ambiguous between "never attempted" and "attempted and failed".

### ★ THE PROBE NEVER PASSES `luofu_fmc_reset_die()` - and that is the real blocker (2026-11-01)
A cell ladder, one deposit per fire, on primed cells:

| deposit site | cell | landed? |
| --- | --- | --- |
| after the MTD registration chain (6533) | `C8C` | **YES** (`0xC0DE5AA3`, partition resolved, row `0xC5A3`) |
| after `luofu_fmc_reset_die()` returns 0 (6558) | `C94` | no |
| after the NAND ID check passes (6590) | `C88` | no |
| at DMA setup (6670) | `C8C` | no |
| the kernel-side write test (after 6710) | `C94` | no |

`fmc->dma_buf` is allocated at **6710** and `page_buf` at **6747** - both after the reset step. So the
MTD device registers (which is why `/proc/mtd` looks fine) but **every read and write falls through
`if (!fmc->dma_buf) return -ENOMEM`**, and `mount_root` hangs on an MTD that exists but cannot transfer
a byte. That is `C9C = 0x001EB70A`.

**Consequence: the three write-path fixes were never exercised.** They are not disproved; the program
path was unreachable.

**RESULT once the path was made reachable (2026-11-01):** allocating `dma_buf`/`page_buf` at the
proven-reachable site and running the write test there gives `C94 = 0xC0DE0022` — **`luofu_fmc_write_page()`
returns 0** — with `C88 = 0xFE327400` (`nz = 0xFE`, the driver's own read-back sees ~2032 non-`ff` bytes)
while the vendor reads `upgrade` page 163 as `ff ff ff ff`. That is the circular oracle in one cell: the
read-back refills from the same DMA buffer the write filled, and the die never changed.

Variants that all reproduced ret 0 / page `ff`: probe WP clear, per-program WP clear (rM item 2), no
`WREN` (item 6), `OP_CTRL` completion poll (item 3), no post-kick GET-FEATURE, `OP_CFG = 0x9D0` (the
value with a positive 2026-10-18 fire behind it), and `OP_CTRL |= 0x006B0000` (the vendor's live
`0x006B3203` upper field). **Seven variants, one result.** None of the five ranked binary-diff
differences, nor the two values with recorded live provenance, makes a program land.

`0x9D0` deserves a note because it was the best-evidenced value in the record: on 2026-10-18 it altered
the vendor's own planted bytes in mtd9 PEB0. It changed nothing here; the source had been switched to
`0x9A0` on a capture whose own table lists `0x9A0` as the program's *transient start value*.

**Withdrawn reading:** `C88 = 0xFE327400` is NOT the write's read-back count. `C88` is foreign-held by an
ASCII-packing writer that increments it every boot (see `reference/cudy-wr3000v2/sysctrl-cell-map`), so
the "circular oracle measured in one cell" claim has no support. The read-back IS still circular by code
inspection (it reads `fmc->dma_buf`, the buffer the write filled) - that was established earlier and does
not rest on this cell.

`OP_CFG = 0x9A0` is deliberate, not a bug: this driver's `FMC_OPCFG_*` macros are in a different layout
from the hardware (macros put cs at bit 11; hardware puts cs at 0-3), so the computed pack decodes to
`cs = 0`, and `0x9A0` is the vendor's own shape (`cs=0, if_type=2, addr_cyc=3, dummy=1`). Note the
unresolved contradiction: the flash spec says `wr_if_type=3` / `wr_addr_cyc=5`.

**Two of the three candidates are now eliminated by measurement (2026-11-01):**

| candidate | test | verdict |
| --- | --- | --- |
| the row is not the page the vendor reads | DTS: `upgrade` at `0x6280000`, row `0xC500`, `+163 = 0xC5A3`, byte `0x62D1800` == `upgrade + 163*2048` | **ELIMINATED** |
| the die is block-protected by its own CONFIG register | `luofu_fmc_get_feature(CONFIG)` deposited on a holding cell: **cfg byte `0x00`**, call returned 0 | **ELIMINATED** (`BP0-BP3` clear) |
| the DMA source is unreachable | `fmc->dma_addr` deposited: **`0x84040000`** | **STANDS** |

### ★ THE DMA-WINDOW THEORY IS WITHDRAWN (same day, before it became a premise)
`fmc->dma_addr` is **`0x84040000`**. The vendor's live `SADDR_D0/D1/OOB` are quoted in
`reference/cudy-wr3000v2/fmc-dma-destination-arming.md` as **`0x820e0000` / `0x820e1000` / `0x820e2000`** —
the **same DRAM region**, 32 MB vs 64 MB into the same bank, which is what two independent coherent
allocations look like. That same note's front matter also carries `0xA0000000` from a different sampling,
contradicting its own body.

So the "different DMA window" reading compared our value against one of two vintages in a record that
disagrees with itself. **The DMA window is UNVERIFIED, not proved**, and no claim here rests on it.

What still stands from this round: the row arithmetic is exact (candidate 1 eliminated) and the die's
CONFIG register reads `0x00` with `BP0-BP3` clear (candidate 3 eliminated). The silent no-op therefore has
no established cause.

**Later the same day, two more things were ruled out by measurement, and one of them by breaking the boot:**

| change | result |
| --- | --- |
| `luofu_jffs2_mark(fmc)` guarded at `luofu_fmc_probe` (slice `7e208208`) | **returns** - `C9C = 0xDFFE00AF`, log tick runs. The probe was dead at this call. |
| the same, plus kick changed to the vendor's OR form `op_ctrl \| 3u` (slice `ea8fc3cd`) | **NO RETURN within 300 s**, box dark -> the OR form is a REGRESSION and is reverted |
| "the completion wait is wrong" (unused `FMC_INT_DMA_DONE_BITS 0x38`) | **retracted** - the earlier variants already polled `!(OP_CTRL & BUSY)` on `0x68`, i.e. the vendor's own shape |

`hi_spi_nand_hw_write` really does compute `(old | 3)`, but our driver is not in the vendor's state at that
line, so preserving bits 2-7 lets a set START/DIR bit through. **Rule earned: matching the vendor
instruction-for-instruction is not matching its state.** Detail: `BACKLOG.md` BL-2,
`notes/facts/2026-11-01-wkick-the-or-form-breaks-the-boot`.

**Starting point for the next attempt** (all measured): the probe reaches line 6603 (`FMC: READ ID 8c 2c …`
is in the record), the die ID matches, `CONFIG` is `0x00`, the row arithmetic is exact, the kernel-side
transfer completes with `ret 0`, and the die does not change. The one instrument the prior-art review names
that no fire has used is `CMD_DATABUF_N` (`0x400 + 4*N`) - command data in registers, **bypassing DMA** -
which separates "the SPI protocol is wrong" from "the DMA path is wrong". Fixing the contradicting vendor sample is the next doc-level task: re-derive
`SADDR_D0/D1/OOB` from ONE live capture and record which vintages exist and why.

**RESOLVED (same day): it is not `reset_die` - it is the probe-time `jffs2_mark` call.** Deposits placed
right after the MTD registration chain land; every deposit placed after **line 6562,
`luofu_jffs2_mark(fmc)` in `luofu_fmc_probe`**, does not. No lock is held there and MMIO reads demonstrably
work, so that one call is what separates a live instrument from a dead one. The record had already called it
the boot-killer once and removed it; it was re-added.

**Measured, with the call disabled:**

| build | `C9C` | `C1C` | `C18` |
| --- | --- | --- | --- |
| mark active (baseline) | `0x001EB70A`, frozen for hours | `0x00001823` | `0xC0DE5245` (stale) |
| mark disabled at 6562 | **`0xDFFE00AF`** | **`0xC0DE5000`** (the log tick's own payload) | **`0xC0DE5280`** |

The probe now runs past the mark, so `dma_buf`/`page_buf` can be allocated and the write path becomes
reachable for the first time. **Caveat kept deliberately:** the first attempt disabled the *wrong* call site
(`str.replace` hit the `luofu_fmc_ubi_probe` copy at line 3900) and produced a byte-identical zImage, which
the stale-image guard caught. Match a call by its enclosing function, never by its text.

`p163_nonff` is still 0 **in that build** because it carried no write test - it was the clean baseline plus
the one disabled call.

**Follow-up fire (same day, write test at its proper site after `page_buf`):** the boot state is identical to
the no-mark build (`C9C = 0xDFFE00AF`, `C1C = 0xC0DE5000`, `C18 = 0xC0DE5280`), but the test's own deposits do
**not** land (`C94 = 0xC0DE6F07`, `C8C = 0x80604000` - other writers) and the page is still `ff`. So the probe
advances past the mark but does **not** yet reach the buffer-allocation site. The next rung is a deposit
between line 6562 and `page_buf` to find where it stops now.

### The leading defect in the write path
The program command and the kick are both present. `luofu_fmc_write_page` reads `OP_CTRL`, writes
`(op_ctrl & ~0xff) | 3` and `(op_ctrl & ~0xff00) | (wr_cmd << 8)`, and stores it. What it also does,
and the vendor does not:

| line | statement | vendor parity |
| --- | --- | --- |
| 1695 | `writel(1, FMC_DMA_LEN)` | vendor never writes this register |
| 1760 | `writel(1, FMC_DATA_NUM)` | vendor never writes this register |
| 1775-1776 | `FMC_INT_EN = 1`, `FMC_INT_CLR = 1` | vendor never touches either |
| 1835 | `op_cfg = 0x9A0u` | discards the geometry computed at 1806-1809 |
| 1871 | polls `FMC_INT_STATUS & 1` | not the vendor's completion bit |
| **1885** | **`luofu_fmc_wait_ready(fmc)` after the kick** | **the vendor issues nothing after the kick** |

`luofu_fmc_wait_ready()` (1490-1514) loops on `luofu_fmc_get_feature_raw()`, so line 1885 sends
`FMC_CMD=0x0f`, `FMC_ADDRL=0xc0`, `FMC_OP_CFG=cs|0x70`, `FMC_DATA_NUM=1`, `FMC_OP=0xc5` into the chip
immediately after the program kick. The vendor's last instruction in its program path is
`pop {r4,r5,r6,pc}` at `0x5e0`.

This is a candidate, not a proven cause: it is a race, so a fast part may complete the program before
the feature read lands, which would explain why the same defect yields a write on one boot and nothing
on the next. The decisive experiment is one boot with the 1885 call removed. The patch is written and
ranked in `build/audit/lane-a/MINIMAL_PATCH.md`, and the reconstructed function is
`build/audit/lane-a/luofu_fmc_write_page.recovered.c`.

No commit is vendor-clean: of the 163 commits touching the driver, 47 contain this function and **all
47** carry the post-kick `wait_ready`. So this defect is not a regression from one bad commit; it has
been in every recorded version.

What the code says, without a measurement: the submodule HEAD contains zero definitions of
`luofu_exec_note` / `luofu_mount_note` while `fs/exec.c` and `fs/namespace.c` in the kernel tree call
both, so HEAD alone does not link. The working tree only links because of an uncommitted 43-line block
that makes both functions inert (`git -C opensource diff --numstat -- lab/luofu-kernel/nand/luofu/luofu-fmc.c`
-> `43 0`).

The current source does build. `build/audit/lane-b/out/build.log` is rewritten by every run of that lane;
its `SUMMARY.txt` records the attested numbers and their md5s. Latest run read: zImage 2,687,792 B (md5
`582383328270d1c0ee613975fc8947ef`), dtb 13,880 B, combined 2,701,672 B, uImage 2,687,856 B (md5
`5c61bbdfec607fdd22ace5001b65be93`), 5,962,896 B left of the 8,650,752 B partition. The log that same
lane wrote minutes earlier read 2,687,592 B for the same fields, so quote the `SUMMARY.txt` you read, not
a remembered number. A symbolized `vmlinux` with md5 `5cf3b20776fd9bd05a516c56d4ca0253` was observed
earlier in this session and does not appear in the current `build.log`. UNKNOWN: which built slice
corresponds to the source in the tree right now; re-run the lane and read its `SUMMARY.txt` to settle it.

## 4. Next three experiments
1. **Issue the write from the KERNEL, not from userspace.** Our kernel stops at `C9C = 0x001EB70A`,
   before `run_init_process()`, so nothing in preinit runs and no userspace test can reach the driver
   (§3). Add a kernel-side trigger and read the page back from the vendor afterwards. rM had exactly
   that: `luofu_proc_work` (`filp_open` + `kernel_read` + `mtd_write`). The current driver contains
   **zero** occurrences of `luofu_proc_work`, `filp_open`, `kernel_read` or `call_usermodehelper`, so
   a kernel-side writer has to be added. Start from
   `build/audit/lane-d/luofu-fmc.recovered-write-path.c`, program one known page of `upgrade`, and
   verify with `dd if=/dev/mtd16 bs=2048 skip=163 count=1 | tr -d '\377' | wc -c` from the vendor.
2. If the page still does not program, remove the three vendor-absent register writes in a single further
   fire - `FMC_DMA_LEN` at 1695, `FMC_DATA_NUM` at 1760, `FMC_INT_EN`/`FMC_INT_CLR` at 1775-1776. These
   are vendor-parity changes with no measurement behind them yet, which is why they are second.
3. If the page programs but the overlay still does not mount, the fault is in `volume_identify`'s path and
   not the program path: re-read `rootfs_data` block 0 through the block-device layer fstools uses and
   log its answer.

## 5. Box state
- Vendor image on the box (`REL=2.4.15`, `SEL=0x10`) as of the last successful preflight,
  `build/tmp/fire_baseline_20261104.log`.
- Only `rootfsb` (mtd14) was ever written by us (`STATE.md:6698`, the objective line: "Box healthy on
  vendor, only rootfsb (mtd14) written").
- The current state after the last fire is UNKNOWN from this machine; the fire logged `NO RETURN`, so the
  box must be checked, with a RESET hold if it does not answer.
- `wiphy 0` on a factory-reset image is the `factory` flag, not a fault: `/usr/local/factory/sysinfo`
  ships `option factory '1'`, which makes `wifi_init.sh` exit silently (`docs/wifi-factory-gate.md`, §Summary).

## 6. Canonical assets
| asset | md5 | state |
| --- | --- | --- |
| `luofu-uImage-rM-slice` | `6b7b28c09253b1572b575289f2145233` | the only slice ever cited with a write measurement behind it, and that measurement is not logged. Preserved at `build/audit/backup-2026-11-01T11-31-21-521Z/luofu-uImage-rM-slice`. |
| `rootfs-rQ.sqfs` | `0669c8d4dbaf0f789daa3f9e9ff56e6e` | content-based test rootfs. Preserved in the same backup directory. |
| `stock/rootfs-live.sqfs` | `75a7530c6d2eb694bd5105be1c482fee` | authoritative vendor rootfs, 14,864,384 B. Same size as rQ, different md5: compare md5, never size. |

Everything else in `build/tmp/` is an experiment. `build/` is gitignored, so these exist on this machine
only; the backup directory is the copy to keep.

## 7. Open hygiene
- The submodule working tree carries uncommitted driver work in 19 files (`git -C opensource diff
  --shortstat` -> `19 files changed, 4552 insertions(+), 3653 deletions(-)`; `-w` -> `4521/3622`). The
  largest: `lab/luofu-wifi/luofu-wifi.c`, `lab/luofu-pcie/luofu-pcie.c`, `lab/luofu-clk/luofu-clk.c`,
  `lab/luofu-gmac/luofu-gmac.c`, plus the 43-line stub block in `luofu-fmc.c`. Preserved at
  `build/audit/backup-2026-11-01T11-31-21-521Z/opensource-diff-whitespace-insensitive.patch` and
  `opensource-diff-raw.patch`.
- The parent repo has 13 untracked paths (`git status --porcelain`), including `docs/`,
  `EVIDENCE-INDEX.md`, `SESSION-HANDOFF.md`.
- `nul` at the repo root is a 46-byte junk file containing a stray bash error. It is referenced by
  nothing; delete it when convenient.
- The kernel log ring is disabled for cause (`LUOFU_LOG_BASE = 0x80602000` was never reserved,
  `STATE.md:502-506`). Do not re-enable it without a `memblock_reserve`.
- `luofu-wifi` builds as a module but is not in the kernel fragment, so our image has no Wi-Fi driver
  (`STATE.md:4036`).

## 8. What is NOT true
- "The current source writes mtd16." No reproducible fire log records `p163_nonff`; the only occurrences
  are in a 2026-11-03 session transcript, not in `build/` (§3).
- "The write path was proven byte-exact." The self-test that produced that claim is circular - it
  compared a buffer against a read of the same buffer, and the vendor read `05 00 01 22` where we wrote
  `A5 A4 A7 A6` (`STATE.md:121-128`).
- "Wi-Fi reads 0 wiphys because of a vendor slot fallback." It is the `factory` flag (§5).
- "The FMC read path is broken." It reads correctly (`STATE.md:2472`).
- "The ~70 s reset was memory corruption." The record's own correction names the watchdog chain
  (`STATE.md:284-290`): init hands the fd to procd, procd never reaches its event loop, the timeout expires.
  A separate unreserved log ring (`STATE.md:502-506`) corrupted RAM and killed the boot earlier. The
  watchdog fix is not fire-confirmed (`STATE.md:344`).
- "All 58 vendor drivers are reversed and working." They are ported to source; only compilation was
  checked (`docs/driver-port-inventory.md:3-5`).
- "G3 is NOT YET." Userspace and `rcS` run (`STATE.md:2188`).
