## STATE AFTER THE 2026-10-30 SESSION - read this before touching the kernel

### ★★★★ 2026-10-30 LATE: ubi0 ATTACHES, ubiblock RESOLVES - AND THE BOX IS DARK

**Beyond the wall, three facts and one open question.**

1. **UBI attaches and `ubiblock0_0` resolves** (`C9C = 0x1EB500C8`). The root device exists.
2. **The kernel does not panic.** The panic notifier was found unregistered - it sat BELOW
   `if (!luofu_log_b) return -ENOMEM;` in `luofu_log_register()`, so the log-ring fix silently
   disabled it and every boot since showed its absence. Moved above the guard; a re-fire still shows
   **no `0xC0DE502E`**, so the boot **hangs**, it does not fault. `C18 = 0xC0DE50E5` (the log-ring
   workqueue) is the last writer.
3. **An 8 KiB ECC-on read returns** (`C9C = 0x1EFF00AF`, checksum `0x49`), so large sequential reads
   are NOT the hang. That was the leading hypothesis and it is dead.

**The question: where does it hang?** Three crumbs were placed in `init/main.c` - `0x1EB70A` at
`kernel_init`, `0x1EB70B` after `prepare_namespace()`, `0x1EB70C` before `exec`.

**AND THAT INSTRUMENT STRANDED THE BOX, WHICH IS ITSELF EVIDENCE.** The helper was declared
`static void __init`, but `kernel_init()` calls `free_initmem()` and `mark_readonly()` *before* the
third site - so `0x1EB70C` jumps into freed, read-only memory. **For the boot to reach that call at
all, `prepare_namespace()`/`mount_root` must already have returned successfully** - so the rootfs muy
likely MOUNTED, and the dark box is the instrument's own fault, not the kernel's. Fixed: the helper is
no longer `__init`; the corrected image is built (`39d914c6`) and waiting.

**BOX STATE: DARK / STRANDED.** No ssh for over 10 minutes, longer than any boot tonight. Slot A is
untouched (`27051956`); the TFTP door is armed on `192.168.1.88:69` with `recovery.bin`
(md5 `421114c8`). **A RESET-hold needs the person** - it is the one step that cannot be done in
software. A background watcher is polling for the box to return on its own.

**LESSON, THIRD TIME TONIGHT:** an instrument that cannot speak reads exactly like a negative result.
`C70` was the FMC hardware's cell, `C9C` was overwritten by two `vtbl.c` writers, and now the panic
notifier was unreachable behind an early return. **Before trusting an instrument's silence, prove it
can speak.** And an `__init` helper called after `free_initmem()` is an instrument that kills its own
experiment.

### ★★★ 2026-10-30 [wecc/wpost2] THE UBI WALL IS DOWN - ubi0 ATTACHES AND ubiblock0_0 RESOLVES

**Root cause, and it was ONE LINE:** `static bool luofu_read_ecc_off = true` in `luofu-fmc.c`.
With the ECC engine DISABLED, every read de-interleaved the controller's 14-byte spare splice at
offset 1040 and left the page's trailing word as the driver's `memset` zeros. `vtbl_check()` therefore
read record 118's stored CRC as `0xF1160000` instead of `0xF116C36B`, returned `-EINVAL`, `ubi0` never
attached, `ubiblock0_0` was never created, and `mount_root` had no root device.

**The fix was already written in the driver and never switched on.** The comment above the read path
quotes the identical error (`bad CRC at record 118: 0xf116c36b, not 0xf1160000`), records the vendor's
DMA output as `f1 16 c3 6b at offset 2032`, and says the vendor never sees it because its reads run
with ECC ON. The de-interleave branch's own note admits it accepts **117 of 118** records - the one it
lost was the blocker. Setting `luofu_read_ecc_off = false` (leave the engine on, copy the page plainly)
fixes it.

**Receipts:**

| measurement | value | meaning |
|---|---|---|
| `C9C` / `C8C` | `0xF116C36B` / `0xF116C36B` | record 118's CRC is CORRECT, from a 4-byte and a 256-byte read alike |
| `C9C` (post-UBI probe) | `0x1EB500C8` | `0x80` ran + `0x40` `ubi_get_device_info(0) == 0` (**ubi0 ATTACHED**) + `0x08` `blk_lookup_devt("ubiblock0_0")` **RESOLVED** |
| boot return | `t=70s` (was 310s) | the kernel is past UBI and dies somewhere later |

**How it was found**, after every flash-level hypothesis had been excluded by its own fire: both copies
of the volume table (PEB0 and PEB1) returned the *same* wrong value, so it was not media/ECC damage;
and the same wrong value came back for 4-byte, 172-byte and 4096-byte reads, so it was not the copy
loop. It was the page fetch.

**REMAINING:** the kernel still falls back to the vendor before userspace (UNAME is the vendor's build
string), and `C18 = 0xC0DE50E5` (the log-ring workqueue) with **no panic crumb** (`0xC0DE502E`), so the
post-ubiblock failure is a **HANG**, most likely in the large sequential reads `mount_root` makes
through ubiblock. Next instrument: a crumb BEFORE and AFTER an 8-32 KiB ECC-on read
(`0x1EB6B0` before / `0x1EB6AF` after) - only the BEFORE crumb means that read hangs.

### ★★ 2026-10-30 [wnocorrupt] THE KILLER WAS OURS: AN UNRESERVED FIXED-ADDRESS LOG RING

**This is the finding that unblocked the boot, and it should be read before anything else here.**

`LUOFU_LOG_BASE = 0x80602000`, `LUOFU_LOG_SIZE = 0x4000`. The FMC claimed that physical window,
`__va()`'d it into kernel memory, and `luofu_kmsg_to()` wrote up to 16 KiB of kernel log into it.
**Nothing ever reserved it** - no `memblock_reserve`, no `request_mem_region`. That range sits inside
the DT memory node (`0x80500000 + 0x7b00000`), just below the kernel image at `0x80608000`, so to
the allocator it was free RAM. Whatever memblock handed out from there got silently overwritten.

Disabling it (`luofu_log_b = NULL; luofu_diag_buf = NULL;` - every writer already null-guards) moved
the boot from **`t=70s` dying in `device_initcall`** to **`t=310s` with level 7 reached**:
`C8C = 0x80604000` ( = `virt_to_phys(swapper_pg_dir)`, the value `luofu_late_crumb`'s own comment
documents as correct) and `C9C = 0x80C837E8`, both primed to `0x55555555` before the boot.

**Why it defeated six driver bisects:** removing the watchdog, GMAC, MDIO, smccc, pl353 and LEDs all
produced *identical* results, because none of them was the fault - they were all downstream of the
overwrite. A corruption of free RAM appears in whatever happened to be allocated there.

> **STILL LIVE:** `luofu-gmac.c:565` hardcodes `LUOFU_LOGRING_PHYS = 0x80603000u`, inside the same
> unreserved window. It is compiled out in the bisect config but present in the shipping one.

### ★ 2026-10-30 THE WALL NOW: UBI finds no layout volume (the original wall, finally reachable)

With every initcall completing, `C18 = 0xC0DE5247` says `ubiblock0_0` did not resolve and
`mount_root` has no root device. UBI's test is `ubi_find_av(ai, UBI_LAYOUT_VOLUME_ID)` (`0x7fffefff`):
valid PEBs found but no layout volume -> `-EINVAL`, "the layout volume was not found".

**THE FLASH HAS NOW BEEN PROVEN CORRECT END TO END, AND UBI STILL REFUSES IT.** Four fires, each a
bitmask in `C18` (the one cell proven to survive a primed write):

| fire | `C18` | proves |
|---|---|---|
| `wubi` | `0xC0DE52A0` | partition `rootfsb` found by name; EC magic `UBI#`; `vid_hdr_offset = 0x800`; `PEB0+0x800` reads `'U'` |
| `wubi2` | `0xC0DE52A1` | a layout-volume VID header with valid magic, **valid CRC** and `vol_id = 0x7fffefff` exists in PEB0-3 |
| `wubibm` | `0xC0DE5284` | **EC header CRC is VALID** (no `0x20` bit) - the 2026-10-21 "reads zeros at 0x800" does NOT reproduce |
| `wvtbl` | `0xC0DE52F4` | **VOLUME 0 EXISTS**: VTBL record 0 has a valid CRC (`0x40`), `reserved_pebs != 0` (`0x20`) and a name (`0x10`) |
| `wfar` | `0xC0DE52E4` | the read path is **uniform across the whole partition** (`0x40` last PEB and `0x20` middle PEB both read valid EC headers) - UBI is not seeing a different flash than we are |

So every byte UBI reads to decide there is a rootfs is present and valid, and `ubiblock0_0` still
does not appear. **The data we serve is not the fault.**

Remaining asymmetry, and the fire in flight tests it: this probe has only ever read **PEB0-3**, while
UBI scans the whole partition (~186 PEBs of `0x20000`). If the read path degrades at high offsets,
UBI's scan sees a different flash than our low-offset reads do. `[wfar]` reads the EC header of the
**LAST** and the **MIDDLE** PEB (two 64-byte reads, the size the diag already performs safely):
`0x40` last PEB valid, `0x20` middle PEB valid, `0x80` ran, `0x04` layout VID found, `0x08` ubiblock
resolved. Expected `0xE4` if the read path is uniform across the partition.

**`wfar` returned exactly that: `0xC0DE52E4`.** The read path is uniform, so the flash is ruled out
entirely and the fault must be inside UBI's attach or in `ubiblock_create`.

### ★★ THE INSTRUMENT ERROR THAT EXPLAINS THE WHOLE UBI INVESTIGATION

**Every diagnostic above runs BEFORE UBI does.** The initcall map is unambiguous:

```
__initcall_luofu_fmc_ubi_diag7   c0cadf04
__initcall_ubi_init7             c0cadf08      <- 4 bytes LATER, so it runs AFTER us
```

So no probe tonight could ever observe UBI's decision - they could only prove the flash is correct,
which they now have, exhaustively. **The first probe that runs after UBI and ubiblock is
`luofu_ubi_post` (`late_initcall_sync`, `__initcall_luofu_ubi_post7s`).** It asks:

- `0x40` `ubi_get_device_info(0)` returned 0 -> **ubi0 IS attached**
- `0x20` it returned `-ENODEV` -> **ubi0 never attached**
- `0x08` `blk_lookup_devt("ubiblock0_0")` resolved

**Why this is the right question:** `ubiblock_create_from_param()` calls
`ubi_open_volume(0, 0, UBI_READONLY)` for `ubi.block=0,0`. If ubi0 is not attached that call fails
and NO block device appears - exactly the symptom - while every byte of flash checks out.

### ★★ ANSWERED: ubi0 NEVER ATTACHED, and the attach fails INSIDE ubi_read_volume_table

`[wpost]` (`C18 = 0xC0DE52A0`) proved ubi0 absent after `ubi_init`. The crumb ladder then walked
UBI's own code - but only after TWO instrument defects were fixed:

1. **`ubi_crumb()` wrote to `C70`, which reads `0x00001F40` after every boot** - the FMC's own
   constant. Every crumb was invisible. It now writes `0xc0de9a00 | low byte` to **`C04`**, the
   carrier `luofu_restart` folds into `C18`.
2. The post-UBI probe had to be **disabled** for the ladder fires: it also writes `C04` at `7s`
   and would overwrite the deepest crumb.

Ladder, deepest crumb wins (`C04` -> `C18` = `0xC0DE52<byte>`):

| crumb | stage |
|---|---|
| `0x01` | `ubi_init` entry |
| `0x02` | `open_mtd_device` |
| `0x04` | `ubi_attach_mtd_dev` |
| `0x06` | `ubi_attach` |
| `0x08` | `scan_peb` |
| `0x09` | `scan_all` completed |
| `0x0a` / `0x0b` / `0x0c` | volume table OK / wear-levelling OK / EBA OK (attach succeeded) |
| `0x30|x` | `ubi_read_volume_table` FAILED, `x` = `(-err) & 0xf` |

**Measured: `[wcrmb]` = `0xC0DE5208` and `[wstage]`/`[wscan]` = `0xC0DE5236`.**

Decoded: `ubi.mtd=rootfsb` DOES resolve, attach DOES start, and `scan_all` DOES complete. The failure
is `ubi_read_volume_table` returning **`-EINVAL`** (`0x36` = `0x30 | 6`, and `-EINVAL` is 22 whose low
nibble is 6 - do NOT read this as `-ENXIO`). `-EINVAL` from that function is only reached when
`ai->is_empty` is **false**, i.e. UBI DID find valid EC headers - so its PEB stride matches ours and it
is reading our flash correctly.

### ★★★ NARROWED TO THE VOLUME TABLE CONTENTS

`[wvis]` (`C18 = 0xC0DE521B`) set BOTH visibility bits: UBI **read a valid VID header** AND **saw
`vol_id = 0x7fffefff`**. `[wcount]` (`C9C = 0x1EB00002`, a self-identifying carrier primed each fire)
proved the layout volume has **exactly 2 LEBs** - the permitted number - and that `ubi_find_av()` DOES
return an AV. So "the layout volume was not found" is a MISLEADING message: it is found.

That kills every remaining return path in `ubi_read_volume_table` except one:

```c
av = ubi_find_av(ai, UBI_LAYOUT_VOLUME_ID);   /* FOUND, leb_count == 2 */
...
ubi->vtbl = process_lvol(ubi, ai, av);        /* <- this returns -EINVAL */
```

`process_lvol()` calls **`vtbl_check()`**, which validates EVERY record `0..ubi->vtbl_slots-1` (128 of
them, ~22 KB read from each of the two layout LEBs). **Every previous probe checked only record 0** -
which is valid (CRC ok, `reserved_pebs != 0`, name present). A failure at ANY later record is invisible
to those probes and returns `-EINVAL`.

`vtbl_check`'s own classes: `1` bad CRC on a record, **`2` a `reserved_pebs == 0` record that is not
byte-identical to `empty_vtbl_record`** (the erased-`0xFF`/trailing-garbage signature), `3..9` the field
checks, `10+` the `reserved_pebs` accounting.

**The instrument for this (`[wvtc]`) writes `C9C = 0x1EB1_0000 | (err << 8) | record_index`** from inside
`vtbl_check`'s `bad:` label and from its bad-CRC return - so it names which record fails and why.

### ★ 2026-10-30 [wfix/wclk] THE REAL BLOCKER: A DTS SHAPE THAT DID NOT MATCH OUR DRIVER TOPOLOGY

**The flash was never being probed at all.** Not a broken read path, not the DMA, not row arithmetic.

I split `0x14880000` into the vendor's two nodes - `crg@` (resets) and `clk@` ("hsan,clk" + 20 gate
children) - because that is what the vendor's own tree looks like. But **the vendor has TWO drivers
(`hi_crg`, `hi_clk`) and this tree has ONE** (`luofu-crg`), which builds its clock gates by walking
`dev->of_node`'s children and registers the clock and reset providers from them.

With the children moved to a `"hsan,clk"` node that **no driver matches**:

1. `luofu_crg_probe` found no children, returned `-ENODEV` -> **no clock provider, no reset provider**
2. `devm_clk_get(dev, "sfc_clk")` in `luofu_fmc_probe` returned `-EPROBE_DEFER`
3. the probe did `return -EPROBE_DEFER` -> **it never ran, and never would**
4. no mtd device -> `ubi.mtd=rootfsb` had nothing to open -> no `ubiblock0_0` -> `mount_root` failed

Every observation fits: the initcall tower still completed (a deferred probe is not an error), every
flash "read" returned zeros (the flash was never probed), and `C18 = 0xC0DE0000` from the row probe
(it lived INSIDE the probe that never executed). Four fires chased a hardware fault that was a
device-tree/driver mismatch.

**Receipt that the fix works: `[wfix]` gave `C1C = 0x23494255` = "UBI#" with `C18 = 0xC0DE50E1`.**
The probe RAN and read page 0 correctly for the first time with our own appended device tree.

**Two durable rules:**
- **Match the DRIVER topology, not the vendor's tree shape.** A DTS that mirrors a vendor tree without
the vendor's driver split silently unplugs whole subsystems.
- **A probe must never defer forever on this bench.** A provider that never appears turns `-EPROBE_DEFER`
into a permanent, silent unplug. The FMC now logs and continues, because u-boot already clocks the block.

### ★ 2026-10-30 [wgate] THE CRG REGISTERED ZERO CLOCKS - ONE VARIABLE REUSED

After the topology fix the boot finally reached the GMAC probe and died in `devm_clk_bulk_get_all`.
The cause was in `luofu_crg_probe`:

```c
for (i = 0; i < LUOFU_CRG_MAX_BANKS; i++) { ... }   /* counts BANKS into i */
...
i = 0;                                               /* i reused as the GATE INDEX */
...
if (bank >= i || bit > 31) { continue; }             /* compares bank against the INDEX */
```

The first gate evaluates `0 >= 0` and is skipped; so is every one after it. `data->num = n` was set but
no `hws[]` entry was ever filled, so `of_clk_hw_onecell_get` returned an **invalid index for every
consumer** - gmac, mdio, pcie, i2c. Fixed by capturing `crg->nbanks` before `i` is reused.

Second half: **the 16 gate children were missing from the DTS entirely.** The node carried only 4
PLL/mux children, none with `reg-offset`+`bit`, so nothing could register. The provider indexes clocks
by **child order**, so the gates must come FIRST in the node and in `LUOFU_CLK_*` order:
index 0 = SFC, 6 = GMAC0, 10 = MDIO, 15 = PIE.

**Receipt: `C94 = 0xC0DE6003` - the GMAC received 3 clocks.** That value had never been produced before.

### ★ 2026-10-30 [wxlat] THE RESET PROVIDER HAD NO of_xlate - every consumer failed

`drivers/reset/core.c:reset_controller_register()`:

```c
if (!rcdev->of_xlate) {
	rcdev->of_reset_n_cells = 1;          /* OVERWRITES this driver's 2 */
	rcdev->of_xlate = of_reset_simple_xlate;
}
```

Setting `of_reset_n_cells = 2` WITHOUT an `of_xlate` leaves the controller believing it takes ONE
cell, while every node here passes TWO (`resets = <&crg 0x30 0x11>`). Each lookup trips
`WARN_ON(args_count != n_cells)` and returns `-EINVAL`, so **no network driver ever got a reset**.
Fixed by supplying `luofu_crg_of_xlate` (decodes `(reg-offset, bit)`) and assigning it BEFORE
`devm_reset_controller_register`. Two temporary bypasses in gmac/mdio were **reverted** - the
provider was the defect, not the consumers.

**Receipt: `C94 = 0xC0DE6F07`** - the GMAC got past the fetch and deferred on the PHY, which is correct.

### ★ 2026-10-30 [wnowdt] THE WATCHDOG PROBE WAS STOPPING THE BOOT AT device_initcall

With the flash, clocks and resets working, the boot still died at 70 s with `C18 = 0xC0DE50FF`
(FMC exit marker) and `C1C = 0xC0DE5FFF` (FMC payload) - so the death was in the **device_initcall**
phase, among only four built-in lab drivers. `CONFIG_LUOFU_WATCHDOG=y`; the record already carried a
note titled *"death inside luofu_wdt_probe"*. Removed (verified `0` `luofu_wdt` symbols in vmlinux):

| | before | after |
|---|---|---|
| reach | device_initcall | **late_initcall_sync** (`C1C = 0x18C5387D` carries `0x18000000`) |
| `C18` | `0xC0DE50FF` | `0xC0DE0017` (UNEXPLAINED - see below) |

**`C18 = 0xC0DE0017` has NO literal writer anywhere in `opensource/lab`** and both sysctrl bases are
`0x10100000`, so it is not a mis-based `C04` write either. It decodes numerically as `0xC0DE0000 | 0x17`
(i.e. `err = -23 = -ENFILE`) but that is a coincidence until a writer is found. **Do not name it.**

> **TO RESTORE:** `kb.sh`'s `merge_config` re-enables `CONFIG_LUOFU_WATCHDOG` on every normal build.
> The `wnowdt` slice was built by disabling it AFTER the merge. A routine build silently restores the
driver that stops the boot at `device_initcall`.

### The gates

| gate | state | receipt |
|---|---|---|
| G1 FMC reads real flash | **GREEN** | stage-B crumb `C1C = 0x23494255` = "UBI#"; and on 2026-10-30 a level-7 probe through the MTD layer returned `C18 = 0xC0DE52A0` - partition found, EC magic `UBI#`, `vid_hdr_offset = 0x800`, `PEB0+0x800` reads `'U'` |
| G2 program path | **GREEN** | page written by our kernel read back byte-exact through the vendor driver (2026-10-27) |
| G3 our kernel + real rootfs + userspace | **RE-OPENED 2026-10-30** | The old "GREEN, 5 of 6 boots" receipt came from the archived `wreal` slice (`8aa5e67e`), a DIFFERENT configuration. Current builds complete **every initcall** and reach level 7 (`C8C = 0x80604000`, `C9C = 0x80C837E8`) but `C18 = 0xC0DE5247` says `ubiblock0_0` does not resolve, so `mount_root` has no root and no userspace starts. |
| G4 Ethernet on our kernel | **ONE DEFECT FROM GREEN** | inside-the-kernel probe: ARP resolves `192.168.10.2 -> 10:ff:e0:c7:f0:26` REACHABLE, bridge answers its own 192.168.10.1 in 0.17 ms, **tx 45->179, rx 97->261, tx_dropped=0, tx_errors=0, rx_errors=0, rx_dropped=3**, host ping still 0/3 |
| G5 Wi-Fi on our kernel | vendor-only | - |
| G6 sustained uptime | **CHANGED SHAPE 2026-10-30** | The old "resets at ~70 s" was the unreserved log-ring corruption (see above). With it removed the boot runs the full **310 s** and restarts on the `mount_root` failure, not on a random initcall. |

### The three findings that change how the next session works

**1. THE CABLE IS ON eth2, NOT eth0.** The vendor proves it: `eth2 carrier=1 tx=661`, while `eth0/eth1/eth3` are all `carrier=0 state=down`. Nine falsified G4 hypotheses were tested against an unplugged port. Our kernel brings `eth2` up, bridges it into `br-lan` with `192.168.10.1/24`, and moves hundreds of frames - so "nothing leaves the interface" is false.

**2. THERE IS A USERSPACE INSTRUMENT CHANNEL, AND IT WORKS.** `/etc/rc.local` runs under BOTH kernels because they share the rootfs. A script there can write to `/www/OUT` on the overlay, which persists across the boot and is readable over ssh afterwards. No crumb, no free cell, no flash write on the boot path - the three things that failed all session. This is how the G4 answer above was obtained.

**3. CELLS ARE ALL CONTESTED; STOP ADDING THEM.** Measured last writers: `C18` restart path, `C90`/`C94` `luofu_boot_stage`, `C1C` the mach ladder ORs stage bits but the FMC tick and the probe crumb both write it, `C84` GMAC, `C74` not writable, `C9C` GMAC. The tick writes only when `luofu_crumb_base` is non-NULL and it is NULL - so the tick has been silent for days, which is why every fire reads a probe crumb instead of `system_state`.

### What the tree is, and what it is not

- Tree and repo are byte-identical at `dfb38b15`; `CONFIG_ETHERNET`, `CONFIG_LUOFU_GMAC`, `CONFIG_LUOFU_WATCHDOG` all enabled; the fatal `ioremap`-in-beat block and the deleted `#define LUOFU_SYSCTRL_BASE` both repaired.
- **The tree DOES reproduce G3 - the "cannot reproduce" claim was a false alarm (settled 2026-10-29).** Today's
  builds from the current tree (`wg4`, `wep`, `wwr1`) are byte-identical to the archived `wreal` slice:
  same zImage length 2,678,832, same slice md5 **`8aa5e67e`**. The `wethup`/`wethip` builds that "wrote
  nothing" were never a kernel regression: both report the SAME kernel read function (`1ef70ad`) as
  `wreal`, and both were built with an **initramfs init replaced by `mk_init2.py`/`mk_init3.py`**, which
  `pause()`s forever. So the box booted our kernel, ran the replacement init, and sat in `pause()` - which
  looks exactly like "userspace never started". `CONFIG_ETHERNET` was never involved either.
  **There is no 17-minute bisect to run. The tree is good.**
- `CONFIG_ETHERNET` disabled was tested and is NOT the regression.

### ★ 2026-10-30 [wdtb] BREAKTHROUGH - THE INITCALL TOWER COMPLETES

**Every prior fire booted the VENDOR's device tree.** `CONFIG_ARM_APPENDED_DTB=y`, but every packaging
script ran `mkimage ... -d arch/arm/boot/zImage` with **nothing appended**. So every DTS edit ever made
(compatible strings, the `crg@`/`clk@` split, `#reset-cells`, the gate children) was compiled into a DTB
and discarded at packaging - while the build reported `BUILD_OK` and `BUDGET: PASS`.

`[wdtb]` is the first image that appends it, with the append **verified**
(`zImage 2659928 + dtb 11560 = combined 2671488`, asserted). Slice `e713b710`, slot B byte-exact.

| cell | value | meaning |
|---|---|---|
| `C94` | **`0xC0DE9A01`** | written by `luofu_boot_stage` (a **`late_initcall_sync`**) - its own table says this means **the kernel got past ALL late initcalls** |
| `C18` | **`0xC0DE5245`** | `luofu_restart()` - `machine_restart` ran afterwards |
| `C1C` | `0x58000001` | top byte `0x58` carries the ladder's `0x18` LATESYNC bit |
| - | **`BACK at t=310s`** | not 70 s - the box lived 4.4x longer |

**The initcall wall is gone.** The boot now completes every late initcall and dies in the **userspace
handoff** (`kernel_init_freeable` / `mount_root`) - exactly what the `0xC0DE9A01` table predicts. That is a
different failure, later in the boot than anything measured before.

### The 70 s reset

**2026-10-30 (later) - two further hypotheses falsified; the watchdog is exonerated at three levels.**

- **Correction:** `watchdog_init` is `__initcall_watchdog_init4s` (**level 4s**), so by level 6
  `wtd_deferred_reg_done` is already true and registration runs **INLINE**. My earlier withdrawal ("it only
  `list_add_tail`s and returns") is itself withdrawn. Read an initcall's level from `nm -n vmlinux`, never
  from the source spelling.
- **`[wnorb]`:** removing `watchdog_stop_on_reboot()` (the only mutex path - `register_reboot_notifier`)
  left `C18 = 0xC0DE7D05` unchanged. Falsified.
- **`[wcore]`:** instrumenting the kernel core with stamps around `cdev_device_add()` gave
  **`C18 = 0xC0DE7E02`** - the call **returned**. `device_add`/sysfs/devtmpfs are fine. Falsified.

So the watchdog core registers successfully and returns; the boot still dies before the driver's next
statement. That window touches no hardware, so the death is **not in the watchdog path at all** - it is
the same stop that kills `late_initcall`. The question is unchanged: **what stops the initcall tower at
the level-6 -> level-7 boundary.**

**2026-10-30 bisect - the boot stops at the level-6 -> level-7 transition, and it is NOT the watchdog.**

Full chain, every link a stamped fire verified in the built object first:

| step | reading | conclusion |
|---|---|---|
| `[wexit]` | `C18 = 0xC0DE50FF` | the FMC probe **returns** |
| `[wlate]` | no `0xC0DE1414` | `late_initcall` (level 7) **never runs** |
| `[wgm]` | `C94 = 0xC0DE6F04` | GMAC enters and **error-returns** at its reset lookup - no hang, and it has never had a reset provider, which is a separate G4 defect |
| `[wwd2]` | `C18 = 0xC0DE7D01` | watchdog probe **enters** (first time ever observed) |
| `[wwd4]` | `C18 = 0xC0DE7D04` | ioremap + all 12 DT reads OK |
| `[wwd5]` | `7D06`/`7D07` absent | core never calls `->set_timeout` |
| `[wwd6]` | `C18 = 0xC0DE7D05` | `devm_watchdog_register_device` is **reached** |

**Withdrawn:** I said the death was inside `devm_watchdog_register_device`. Reading
`drivers/watchdog/watchdog_core.c`, that call does `list_add_tail` + `return 0` at `device_initcall`
time - the real registration is deferred to a **`late_initcall`**, which never runs. It cannot hang.

**So one event stops the tail of level 6 and all of level 7.** Consequences: the four `hi_wdg.ko` fixes
are **exonerated** (they never execute - nothing opens `/dev/watchdog`), and `luofu-wdt` is **not** the
executioner. The open question is what stops the initcall tower, not which driver.

**2026-10-30 `wdprobe` fire - VOID as a watchdog measurement, and my first reading of it was WRONG.**

`build/tmp/luofu-uImage-wnospet-slice` (`1e174d4c`, the four `luofu-wdt` fixes) was fired with a full
pre-flight (vendor `SEL=0x10`, both rootfs `UBI#`, recovery payload `421114c8`, slot B verified byte-exact,
slot A untouched). It returned `BACK at t=70s` with **`C18 = 0xC0DE50E1`**.

**WITHDRAWN:** I published "`luofu_fmc_probe` never returns" from the absence of the probe-end markers.
That is false - the `0x99` (line 6392) and `0xFE` (line 6419) markers sit **after `return 0;` at line
6375**, so they are unreachable code, not unreached code. Their absence proves nothing, and `0xE1` is
fully consistent with the probe **returning normally**.

**What SURVIVES, from the cell's writers instead:** `C1C` has three possible writers with distinguishable
top bytes - the FMC crumb payload (`0x23`), the tick (`0xC0`), the mach ladder (`0x11/0x12/0x14/0x18`).
Measured `0x23494255` = top byte `0x23` = the 0xE1 payload, so **nothing wrote C1C after the probe**: the
tick never fired and the ladder never stamped. **The boot stops after `luofu_fmc_probe` writes 0xE1 and
before the first `late_initcall`.** Detail and both retractions:
`notes/facts/2026-10-30-boot-stop-localisation-and-two-retractions.md`.

What the fire does establish: every register reading taken *after* the `BACK` line came from the
**vendor** (proved by `/proc/kallsyms` having no `luofu_wdt_*` and major 253 being `hi_wdg`), so the
watchdog question is still **unmeasured**, not answered. The`/proc/124/fd/3 -> /dev/watchdog` line in
that dump is the vendor's own feeder, not a survivor of the one disabled for the fire.

**2026-10-29 (later, via `tools/ko_decomp.py`) - the watchdog lane was re-opened with a complete reversal of
`hi_wdg.ko`, and our own driver had FOUR defects that made it program the hardware wrong:**

1. `luofu_wdt_ping`/`_pet` wrote **`0`** to `clr-offset`. The vendor's `hi_wdt_hw_clear` writes **`reset_val0`
   then `reset_val1`** to the same address, so the register is left holding `reset_val1` - which is exactly
   the `0xAA55A5A5` the live vendor reads at `0x14880070`. The earlier "does the ping expect the magic?"
   question is now a derivation, not a hypothesis.
2. `luofu_wdt_set_timeout` implemented **only the hwver-0** field. **This board is hwver 1**: the live
   `set-offset` (`0x14880050`) reads `0x30007400`, whose bits[10:19] are 29 = `2*15-1` for the vendor's own
   15 s. Read the hwver-0 way, bits[3:11] give 128 -> 129 s. `timeout_field` was **declared and read but
   never assigned**, so it was permanently the wrong case.
3. No `hwver` was read from the DT at all.
4. enable/disable write order was ever both-ascending; the vendor writes **val1 then val0 for enable** and
   **val0 then val1 for disable**, with a delay between.

All four are fixed and built (`rc=0`, 8,520 B), and verified **in the object**: `luofu_wdt_ping` now loads
`[r4,#0x8c]` and stores it; `set_timeout` emits three distinct `bfi` paths. The **kernel** build carrying
them is `zImage` md5 `240f8a6b`, slice `build/tmp/luofu-uImage-wnospet-slice` = **`1e174d4c`**, and the
box-side proof is `drivers/watchdog/luofu-wdt.o` disassembling to the same `[r4,#0x8c]` load.
Detail: `notes/facts/2026-10-29-hi_wdg-full-reversal.md`.

**This does NOT name the executioner.** It makes our driver match the vendor bit-for-bit. The
discriminating next measurement: read `set-offset` under OUR kernel through the rc.local channel and
compare with `0x30007400` - if we now write the same value and still die at 70 s, the watchdog is not the
reset source and G6 should be re-scoped.

> **Superseded reading, kept for the trail:** earlier text here said `hi_wdt_hw_clear` "reads its offset
> from a LANCHOR slot rather than the DT `clr-offset`". That was a misreading. `[1]` is the **ioremap
> base** (probe stores `r0` at `ctx+0x74`), and the offset is `LANCHOR0[10]` = the DT `clr-offset`. There
> is no shadow offset anywhere in the module.

Also excluded: a panic (`panic=5` returns in 5 s), `hung_task_panic` (removed, no change), the kernel watchdog pet (disabling made it worse: 36 beats -> 1), the pet register value (reset magic vs zero, no change), and a userspace feeder holding `/dev/watchdog` (ran, still reset). **The empty `/sys/class/watchdog/watchdog0` is NORMAL - the vendor is identical.**

### Tooling (2026-10-29)

**CHANGELOG CORRECTION (this session): the "tree cannot reproduce G3" claim above was WRONG and is now
struck.** Today's builds from the current tree reproduce `wreal` byte-for-byte (`wg4`, `wep`, `wwr1` all md5
`8aa5e67e`, zImage 2,678,832 B - identical to the archived good slice). The `wethup`/`wethip` builds that
"wrote nothing" carry the **same kernel read function `1ef70ad`** as `wreal`; they differ only in the
**initramfs**, which `mk_init2.py`/`mk_init3.py` replaced with a C stub that `pause()`s forever (and probes
`eth0`, the uncabled port). So there is **no 17-minute bisect to run - the tree is good.**

**Two drivers were never reaching the kernel.** `build/tmp/wsl_build_kernel.sh` copied the FMC, gmac, mdio
and `luofu-clk.c`, but **never** `luofu-wdt.c` (the tree held a stale manual copy, md5 `bcc1ca83` vs repo
`2f1194c3`, so every watchdog edit was a silent no-op) and **never** `luofu-crg.c` (split out of
`luofu-clk.c`, so the `grep luofu_crg_probe` guard aborted every build after the split). Both copy steps are
fixed, destructive, CRLF-normalised and guarded. **The first correct kernel build is `240f8a6b`.**

Ghidra is **not** installed and there is no JVM, so a Ghidra headless lane is not available on this host.
`tools/ko_decomp.py` (miasm + pyelftools, both in `pyenv/`) replaces it: `--list` for functions, a function
name for a body with every relocation resolved to `SYMBOL = "the string it points at"`, `--fields` for the
`[reg, #offset]` table. This is what turned the `hi_wdg.ko` reversal from a manual read into a mechanical
one. Keep `ko_disasm.py` for quick capstone listings; reach for `ko_decomp.py` when the question is
"what does this touch".

### G4 - what the KPIE comparison now establishes

Reversed `hi_kpie.ko`'s transmit half with the same lane and diffed it against `luofu-gmac.c`. **Every
parameter our driver sets already matches the vendor:**

| item | vendor | ours |
|---|---|---|
| kick | `writel(wptr, base + 0x2008)` (`hi_pie_tx_set_wptr`) | same |
| channel stride | `chan << 4`, chans 0..7 only | same |
| init order | base, len, then **wptr = 0 last** | same |
| ring len | 0x0c entries | 0x0c |
| desc stride | 44 (`MLA idx,#44`) | 44 |
| desc byte 3 | `(b3 & 0x3b) \| 0x44` | 0x54 |

So no remaining register-level difference explains "nothing reaches the wire". The unresolved candidate is
the one the driver's own comment names: the PIE engine cannot be un-gated from our kernel (the DT `resets`
claim drops the boot to ~1 s, the clock claim likewise). That is a power/clock-domain question, not a
descriptor question, and it should be attacked by reading what `hi_pie_probe` does to the CRG before it
programs a channel.

### Rules paid for this session

- three self-inflicted file corruptions all compiled `ERRORS=0`; check the function head, not the build result
- the kernel tree is not the source tree; a revert applied to the repo does not reach the tree
- **never flash an image that disables the watchdog** - it removes the only way home (cost a strand and a power cycle)
- u-boot RETRIES the recorded slot, so a non-booting image is permanent until the RESET-hold TFTP door (`tftp/recovery.bin` = `firmware/2.4.15.bin`, host alias 192.168.1.88) restores it
- **compare against the vendor before calling a measurement anomalous** - I withdrew and re-issued the same conclusion twice in twenty minutes for want of one ssh command
- a reply outside the pre-`BACK` window is the vendor, not our kernel; timestamp-gate every reply
- `grep -oE` output carries a trailing carriage return on this host and breaks shell patterns

## ★ AUTONOMOUS RUN - 2026-10-29 (overnight, person asleep 8-10 h)

**Directive:** work until the complete goal is met; do not stop on anything less.

**Goal:** current OpenWrt on OUR kernel, rootfs mounted from our own NAND driver, Ethernet up, Wi-Fi last.

**Where the wall is, exactly (measured, not inferred):**
`kernel_execve("/init")` HANGS. Not a failure - the post-exec marker never fires, and a `reboot()`
syscall inside that init never runs. Excluded in one pass: initramfs contents (a ONE-FILE initramfs
fails identically), binary-format support (`BINFMT_ELF=y`, `MMU=y`, `load_elf_binary` linked), the
`.init` use-after-free (`luofu_handoff_stage` is at `c0add770` = .text, zero modpost mismatches),
and a panic (`panic=5` returns in 5 s; these return at the 310 s watchdog).

**THE BISECT BASELINE IS ON DISK.** `build/tmp/luofu-uImage-wclean-slice` = **`8cb60f4c`**, the build
the record says reported `C1C = 0x5AC00102` (tag 0x5A, `luofu_where = 12`, pid 1,
**`system_state = 2` = SYSTEM_RUNNING**). Fire it `build/tmp/fire_wgood.sh`.

**Two candidate regressions named by the cell itself:**
- `C1C = 0x5AC00102` is a TICK payload -> the FMC 5-second timer was RUNNING in the good build.
  Today `C1C = 0x11` -> **no tick**, and `0x73717369` is the stage-D PASS. So the tick is the first
  thing to compare.
- `where = 12` in the good build means every instrumented stage finished.

**Rules for this run (each paid for once already):**
- every edit to `luofu-fmc.c` or mach `luofu.c` gets a structural check BEFORE a build (`sed` the
  function head, declarations before statements); three self-inflicted corruptions this session all
  compiled `ERRORS=0`
- both files are UNTRACKED by git - the repo copy is the only copy; restore from it, never patch a
  damaged tree
- build scripts copy the REPO file into the kernel tree, so an edit made only in the tree is silently
  discarded at the next build (this cost two contradictory readings)
- report through cells whose last writer is known: `C18` = restart path, `C90`/`C94` =
  `luofu_boot_stage` in `late_initcall_sync`; `C1C` is vendor-overwritten, `C84` is GMAC-owned,
  `C74` is not writable
- one fire's cell value is a SAMPLE; the boot is deterministic (3/3 identical) but a DIFFERENT binary
  is a different population

# STATE - the one page

Updated 2026-10-26 (13:25Z). This file is rewritten at the end of every session; if it disagrees with
any other document, this file wins and the other one is stale.

## ★ CURRENT SITUATION (2026-10-27 18:25Z) - WHY THIS IS BLOCKED, PRECISELY

**Green and receipted:** G1 (stage-D PASS: volume magic + `ubiblock0_0` resolves), G2 (live tick `where = 12`,
header readback, vendor-verified pattern), and G3 in substance - `SYSTEM_RUNNING` with pid 74 on the real
rootfs, resting on the session's real find:

> `free_initmem()` poisons `.init` BEFORE `run_init_process()` calls our `__init` handoff function, so every
> boot executed freed memory - no panic, no hung-task report, just a CPU that never returns. modpost printed
> the section mismatch on every build. Dropping `__init` gives zero mismatches and takes the kernel from a
> 6.2 s death to ~16 s of life with init running.

**G4 is blocked by TOOLING, and the blocker is specific.** The interface configures and nothing leaves it.
Established: the ARP cache is not the cause (deleted before every poll, still silent); the host never sees a
second MAC (so no frame is emitted at all); the built `luofu_gmac_xmit` is a real KPIE transmit with the
channel programmed and barriers in place; the descriptor valid bit is now `0x54` per the vendor's own
disassembly. What is missing is any way to see INSIDE our running kernel:

- sysctrl cells are last-writer-wins - even `C70`, the one cell the map certifies as scratch, is overwritten
  by a later deposit in the same boot;
- the flash write sites have not executed across four attempts (driver path and userspace path, with and
  without an erase);
- there is no console and no UART (the bench is software-only by the person's own instruction);
- the vendor's `/dev/mem` is strict (`Bad address`), so RAM does not survive as a channel;
- our kernel cannot reboot itself - `reboot(RB_AUTOBOOT)` from PID 1 does nothing, so return timing carries
  no information;
- the one clock/reset fix that might explain an unclocked PIE engine (the DT declares `clocks = <0x41>` and
  `resets` on the node, which our driver never claimed) **hangs the kernel within a second** when enabled -
  measured by the beat falling to 10 beats - and had to be reverted.

**G5 and G6 are blocked by the IMAGE SLOT, which is the person's call.** The box boots stock `2.4.15`, whose
rootfs contains no wifi/`hsan` driver files at all - `PHY=0` is the image, not damage. Restoring the healthy
2.5.24 state needs a firmware flash. That was asked and not answered; flashing unattended is the one thing
this project has been burned by, so it is not being done.

**Box left healthy:** `UP=625`, `2.4.15`, `SEL=0x10`, `mtd14`/`mtd13` both `UBI#`, 4 `eth`, 0 `.omo`
leftovers.

**The next move that does not need the person:** build a channel that is not a cell and not a flash write -
`netconsole` needs the network, but a **pstore/ramoops region that survives a warm reset and is read by the
vendor** has not been tried; alternative is a vendor-loaded probe module that dumps the PIE block idle vs
transmitting (the recipe that already worked for the FMC), which names the TX doorbell without our kernel.

## ★ SESSION CLOSE - 2026-10-28 (what is TRUE and what is NOT)

### The Wi-Fi question is ANSWERED

`option factory '1'` in `/usr/local/factory/sysinfo` gates the vendor's entire Wi-Fi bring-up.
`/usr/bin/wifi_init.sh` line 3 reads it and the whole sequence lives inside `[ "${factory:0:1}" == "0" ]`.
Set it to `0` and reboot: **two working radios**, `vap0: Cudy-1C73`, `vap8: Cudy-1C73-5G`, on **both**
2.4.15 and 2.5.24. That is the answer to every `PHY=0` reading since 2026-10-15, and it was one boolean.
Write-up: `docs/wifi-factory-gate.md`.

### All 58 vendor drivers are reversed into our own GPL source

`docs/driver-port-inventory.md` - 58 rows PORTED, seven phases, 62,781 lines of C, 10,850 cited
"vendor function (offset)" references, **every driver rebuilt by me from scratch** (`rc=0 errors=0 ko=1`).
Phase 8 filled the deferred paths (RX, TX, mac80211, firmware, all 37 MAC registers, PHY calibration,
switch classification) and the inventory states each item's stopping point.

### What is still NOT true

- **The box runs the vendor image, not ours.** `REL=2.4.15`, `SEL=0x10`.
- **G4 is blocked.** Nine builds matched the vendor's register values - descriptor `0x54`, channel length as
  a count, 44-byte stride, `rptr` reclamation, availability gate, PIE clock bit, MAC config burst - and
  nothing reached the wire.
- **The vendor-module shortcut is blocked by the memory model.** Loading Cudy's own `.ko` files is real:
  same 5.10.201, `CONFIG_MODULES=y`, vermagic differs only by `p2v8` (now patched out), and 65 of 76
  symbols resolve. **But `hi_kpie` needs `mem_section`, which is SPARSEMEM-only and our kernel is not.**

### The instrumentation lesson, paid for repeatedly

**No sysctrl cell is free.** `C80`/`C84`: three writers (FMC, GMAC, CLK). `C70`: reads `0x1F40` in every
fire - another writer's constant, not ours. `C1C`: the mach ladder ORs stage bits, but the vendor's boot
overwrites it. `C18 = 0xC0DE5245` (`luofu_restart`) is the only value that has survived every fire, and it
is written by our own kernel at the very end.

**And the file itself was the bug twice:** `luofu_fmc_probe`'s head was corrupted by a stray `/*` that
swallowed the opening brace - it compiled, so every instrument inside it was dead code - and two later edits
placed a statement between declarations and deleted `luofu_ladder_late` outright. All three compiled
`ERRORS=0`. **A green build is not a correct file.**

### What the next session should do, in order

1. **Confirm the boot is deterministic** (it was: two runs of one image, both `0x00000011`).
2. **Pick the probe's health as the first question**, and answer it through `C18` - the only surviving
   channel - by having `luofu_restart` encode its finding.
3. **Only then** return to G4's real question: does the KPIE engine consume our descriptor.
4. **Every edit to `luofu-fmc.c` or mach `luofu.c` gets a structural check before a build** -
   `sed` the function head, confirm declarations precede statements, confirm the object recompiled by hash.
   Tonight's three self-inflicted breakages each looked exactly like a hardware result.

## ★★ WI-FI WORKS ON THIS BOARD

**Standalone write-up for publication: [`docs/wifi-factory-gate.md`](docs/wifi-factory-gate.md)** - the gate, the
three traps it cost, and why `wiphy=0` is not evidence of absent hardware.
 (2026-10-27 20:45Z)

**The whole Wi-Fi lane was gated by one config value.** `/usr/bin/wifi_init.sh` reads
`hi_cfm get sysinfo.factory` and only runs the bring-up when it begins with `0`. This unit shipped with
**`option factory '1'`** in `/usr/local/factory/sysinfo`, so the vendor script took its early-exit branch on
every image we have run and started nothing.

Set it to `0`, reboot, and the vendor image brings up **two working radios**:

| | |
|---|---|
| phys | `phy0`, `phy1` (`wiphy=2`) |
| PCI | `0000:00:00.0`, `0001:00:00.0` |
| modules | `hi_pcie`, `hi5622v100_plat`, `hi5622v100_wifi` |
| interfaces | `Hisilicon0 vap0 vap1 vap3 vap8 vap9 vap11` |
| SSIDs | **`Cudy-1C73` (2.4G)**, **`Cudy-1C73-5G` (5G)** |

The board reports `board.wlan24=8`, `board.wlan58=8` - the radios were always provisioned. **The Wi-Fi
hardware was never missing or broken**, and this is the first time it has been up since the project began.

**Correction recorded:** this kernel DOES have PCI (`/sys/bus/pci`, `/proc/bus/pci/{00,0001:00}`, 12 PCI
symbols). My earlier "no PCI driver" line came from grepping `/sys/bus/platform/drivers` - the wrong bus.
`pcie_main_init` calls `__pci_register_driver` at `0x7ac`; the `chip_id[0]` failure was a **missing clock
dependency** (`hi_kwificlk.ko` is absent), not absent PCI.

**What this unblocks for G5:** the project finally has a known-good reference state on this exact board with both
bands broadcasting, and the vendor's `hi5622v100_plat`/`hi5622v100_wifi`/`hi_pcie` on disk to disassemble.

## ★ 2.5.24 IS FLASHED AND VERIFIED (2026-10-27 20:05Z)

`sysupgrade /tmp/2.5.24.bin` over ssh, image md5 verified host-to-device first
(`bc40580943e8a9865bb8288d3294f687`), config backed up to `build/tmp/preflash/cfg-2.4.15.tar.gz`.

| Check | Result |
|---|---|
| version | **`2.5.24`** |
| selector | `SEL=0x10 -> 0x11` (slot A now active) |
| ssh | **intact** - dropbear + `SAVE_CONFIG=1` carried the key |
| rootfs | `mtd13` and `mtd14` both `UBI#` |
| ethernet | 4 `eth` interfaces |
| modules | **207** (2.4.15 had a handful) |
| leftovers | 0 |

### The finding that matters more than the flash

**The vendor's own 2.5.24 image does not bring the radio up either.** On a clean boot: `wiphy=0`,
the Wi-Fi module is not even loaded, and **there are zero PCIe devices**. A manual `insmod` fails in the
vendor's own probe:

    [PCIE][ERR] [pcie_main_init:1362]pcie driver probe failed chip_id[0] probe_count[0]
    bal_init return error code: 35629
    wlan_power_on fail

So the Wi-Fi chip **has never been seen on this board by any software**, vendor image included. That
reframes G5: it is not "our driver lacks Wi-Fi", it is that PCIe/HCC enumeration and the chip's power-on
sequence have to work first - the standing phase19-22 gap, now measured on the very image that was
supposed to demonstrate it working.

**What is now unblocked:** with 2.5.24 running, the vendor's `hi5622v100_plat`/`hi5622v100_wifi` pair and
the PCIe probe are available to study on a live system, and `hi_kpie` is a module we can disassemble from
this image too.

## ★ PROGRESS SNAPSHOT (2026-10-27 19:40Z) - G4's code-level hypothesis space is CLOSED

| Gate | State | Evidence |
|---|---|---|
| **G1** FMC read | **GREEN** | stage-D PASS: volume magic read, `ubiblock0_0` resolves |
| **G2** FMC program | **GREEN** | live tick `where = 12`, header readback, vendor-verified pattern |
| **G3** rootfs mounts | **80%** | `SYSTEM_RUNNING`, pid 74, init exec'd; no shell/ssh on our kernel yet |
| **G4** Ethernet | **BLOCKED (measured)** | full model-conforming build transmits **nothing** - see below |
| **G5** Wi-Fi | **BLOCKED** | needs the 2.5.24 image; 2.4.15 rootfs has no Wi-Fi driver |
| **G6** stability | **BLOCKED** | same slot dependency |

### Why G4 is blocked, exactly

The last fire (`7edeb704`) carried **every element the recovered model and the live vendor measurements
specify**, and the host still never learned a second MAC:

- descriptor valid bit **`0x54`** - from `hi_pie_tx_set_desc`'s own instruction sequence;
- ring length **12** - measured on the running vendor (`len = 0x0c` on every programmed channel);
- free-running **`wptr`** - proved live (`ch0` +76, `ch1` +21, summing to `eth2`'s +97 exactly);
- channel window programmed with `wmb()` barriers (probe does it, not open);
- **`rptr` reclamation** - newly implemented, required by the kernel's own driver checklist.

It returned cleanly (`BACK at t=300 s`, `C1C = 0x80603000`) and transmitted nothing.

**Both candidate gates are unreachable from our kernel**, each measured:
- the PIE **clock** and **reset** hang the kernel within ~1 s when claimed (10 beats, twice - reset-only and
  clock+reset), so the engine cannot be un-gated from our side;
- every observation channel into a running kernel has failed: `ioremap` NULL on DMA RAM,
  `copy_from_kernel_nofault` **-EFAULT**, `__va` faults the box, sysctrl cells last-writer-wins,
  `register_kretprobe` **-ENOSYS**, ftrace kprobe rewriting a raw address to a hash.

### What would move it

1. **A firmware flash to 2.5.24** (the person's call) - it restores a Wi-Fi-bearing vendor fallback and gives a
   working reference for the PIE gate, which is what G5 needs anyway.
2. **Or a gate-discovery experiment** on our own kernel: claim the PIE reset *after* the engine is known idle,
   or find whether the CRG cell needs a different sequence than `reset_control_deassert` performs.

**Box left healthy:** vendor 2.4.15, `SEL=0x10`, `mtd14`/`mtd13` both `UBI#`, 4 `eth`, zero leftovers.

## ★ PROGRESS SNAPSHOT (2026-10-27 19:05Z)

| Gate | State | Evidence |
|---|---|---|
| **G1** FMC read | **GREEN** | stage-D PASS: volume magic read, `ubiblock0_0` resolves |
| **G2** FMC program | **GREEN** | live tick `where = 12`, header readback, vendor-verified pattern |
| **G3** rootfs mounts | **80%** | `SYSTEM_RUNNING`, pid 74, init exec'd; "a shell or ssh on our kernel" not yet |
| **G4** Ethernet | **OPEN** | interface configures, nothing on the wire; descriptor + channel now match the vendor's measured config |
| **G5** Wi-Fi datapath | **BLOCKED** | needs the 2.5.24 image; the 2.4.15 rootfs has no Wi-Fi driver at all |
| **G6** stability | **BLOCKED** | same slot dependency + G4's stop |

**The session's durable win:** `free_initmem()` poisons `.init` before `run_init_process()` calls our
`__init` handoff function, so every boot executed freed memory (no panic, no report - the CPU just never
returns). Dropping `__init` gives zero section mismatches and moves the kernel from a 6.2 s death to
`SYSTEM_RUNNING` with pid 74 and ~16 s of life. modpost had printed it on every build.

**G4's measured state:** channel length **12** (vendor: `len = 0x0c`), free-running `wptr` (proved - `ch0`
+76 and `ch1` +21 = `eth2`'s +97 exactly), descriptor valid bit **`0x54`** from the vendor's own
instruction sequence, channel window programmed with barriers. Still unknown: the exact 32 descriptor bytes,
because the ring lives in DMA carve-out memory (`ioremap` NULL, `copy_from_kernel_nofault` -EFAULT, `__va`
faults the box).

**Next move (researched, not guessed):** **kprobe the vendor's `hi_pie_tx_set_desc`** and dump the descriptor
from the pointer it receives - that memory IS mapped, so the comparison becomes possible without touching the
ring. Second: implement TX reclamation (`rptr` at `+0x200c`), which our driver never does and which the
kernel's own driver checklist calls out as a required behaviour.

Docs: `docs/sessions/2026-10-27.md` (the session) and `docs/sessions/2026-10-27-prior-art.md` (research).

## The goal

Our own, fully-current OpenWrt on the Cudy WR3000 v2 (HiSilicon Hi5671Y "luofu", R116): our kernel,
our drivers, no vendor kernel.

## Gates (the only scores that drive decisions)

| gate | state | receipt |
| --- | --- | --- |
| G1 FMC read returns real flash / ubi0 attaches mtd14 with its layout volume | **GREEN (2026-10-26 13:30Z)** | `fire_wubi`: tick payload `C1C = 0x5A107320` - `ec_passes = 32` (32/32 rootfsa EC headers pass CRC32), `ubi_open_volume(0,0,UBI_READONLY)` succeeded and `ubi_read` returned the squashfs magic's `0x73` |
| G2 FMC program works (mtd9 log page non-blank) | **GREEN, corroborated from a live tick (2026-10-26 15:47Z)** - `C1C = 0x5AC00101` decodes to `luofu_where = 12`, i.e. `luofu_fmc_write_page()` was entered and returned 0; mtd9 offset 0 reads `4c 55 46 55 <lines> 00 00 00` = the snapshot header from a live, non-panicking boot; the panic path returned the whole boot log (`READ ID 8c 2c 8c 2c 8c`, `rootfsa page 0 begins 55 42 49 23`, 17 partitions); a known pattern programmed by our kernel reads back byte-exact through the VENDOR's driver. **Open instrument item**: pages 1+ read back with bits cleared whichever writer is staged, so a THIRD writer exists (the write self-test also calls `luofu_fmc_write_page`); and `hi_nfc: ECC error` on our pages = no parity stored, `ff` x64 spare, which blocks UBI *writes* but not G3 | `fire_werase`, `fire_wmaster`, `fire_wpattern`, `fire_wself`, `fire_wstage`, `fire_wone`, `fire_wrawfix` |
| G3 rootfs mounted / init runs on our kernel | **80 - the mount and init-exec are proven, and the regression was MY instrument**. `fire_wclean` (`8cb60f4c`) removes the snapshot, the kthread and the pattern test (no mtd9 traffic at all) and its tick payload is **`C1C = 0x5AC00102`: `luofu_where = 12`, pid 1, `system_state = 2` = `SYSTEM_RUNNING`** - set at `init/main.c:1474` immediately before `run_init_process`, so `mount_root()` returned and init was exec'd. Every build between `fire_wro` and this one stopped at `SYSTEM_SCHEDULING` because the flash instrument ran on the boot path. **Still missing**: a shell or ssh on our kernel, and the literal `VFS: Mounted root` line (no console) | `fire_wro` (`0x5A600102`), `fire_wrawfix` (`0x5AC00101`, SCHEDULING), **`fire_wclean` (`0x5AC00102`, RUNNING)** |
| G4 Ethernet on our kernel | **0 - BLOCKED BY THE DRIVER, re-measured 2026-10-26 16:20Z**: `luofu_gmac_xmit()` is a stub (`dev_kfree_skb(skb); ndev->stats.tx_dropped++; return NETDEV_TX_OK;`) and the driver has **no TX ring structures at all** - only `TX_IFG`/`TX_PRE` register offsets (lines 64-65), so the header's "the rings are staged" is a comment without code. The vendor's datapath is not in the MAC module either: `hi_eth_diag_tx` (0x735c) calls an ops-table hook `[dev+0x40]+0x48`, and `hi_mac_net_xmit` is a 12-byte trampoline to an undefined `hi_net_dev_xmit` | `luofu-gmac.c:307-313`; `hi_kmac.ko` 0x735c/0x4300; link comes up but no ping/ARP ever answered on 192.168.10.1 or 192.168.1.1. **This is a new multi-session lane (ring + DMA kick + switch port-map) and it also gates G3's shell/ssh evidence form** |

## THE WALL (updated 2026-10-27 06:05Z): the kernel stops ~2.6 s after the probe and the RESTART PATH NEVER RUNS

**The measured core:** a 100 ms beat in `C1C` reads **26 beats = 2.6 s** (`fire_wbeat4`, reproduced by
`fire_wrstrt`) - that is the kernel's life. The box's ~60 s return is the **HARDWARE WATCHDOG**, not `panic=5`.

**What the restart crumb proves, and does not:** `luofu_restart()` stamps `C18 = 0xC0DE5245` as its first
action, and that crumb has never appeared. So the **restart path never ran** - which is consistent with a hang
**and** with a panic whose `panic=5` reboot timer cannot fire because interrupts are off. Say "the restart path
never ran", not "no panic occurred".

**The board is UP-ONLY by construction** - the mach header says the DT's `hisilicon,hsan_smp` "has no mainline
smp_ops yet, so a UP boot". `fire_wsmp` (removing `maxcpus=1 nr_cpus=1`) was therefore **void**: CPU1 never
came up. Scheduler-based detection (hung task, softlockup) can never work until SMP bring-up exists.

**Elimination chain (all measured):** the watchdog driver (four fires); our own instruments / pattern test /
KPIE (the minimal `wclean` build failed identically); `CONFIG_NAMESPACES` (+ UTS/PID/NET/USER); the stage-D
hook's 32 sequential `mtd_read` EC-header walk (`fire_wec1`: one block, same outcome); **deadlock/blocked
task** (`fire_whung`: the detector never fired).

**Panic-channel work is retired:** `fac` row, panic-time mtd9, and `pstore_blk` all returned nothing, and the
restart path never runs - stop building capture mechanisms for a panic that may not happen.

**The honest remaining question:** *where does the kernel stop?* - in the VFS mount of `ubiblock0_0`, or at
the init handoff. With every software detector blind (UP-only, IRQs possibly off), the next instrument must be
one that survives a stopped CPU, and that is the open design problem.

## Evidence-channel rules (paid for four times today, 2026-10-26)

- **Arm the MTD device and the kmsg dumper BEFORE anything that can return early.** Four fires came
  back empty (mtd9 blank, no panic crumb, only the tick's `0xC0DE502D`) because both channels were
  registered at the end of the probe. `luofu_fmc_register_mtd()` + `luofu_log_register()` now run
  right after the geometry is known, ahead of the die reset and the ID read.
- **`luofu_log_snapshot()` cannot run from the timer.** It calls `mtd_erase`/`mtd_write`, which sleep;
  the timer runs in softirq. The 13:18Z inline attempt left mtd9 empty and `C18` at the tick's own
  crumb, never a `0xC0DE5Bxx` snapshot crumb. The tick now only `schedule_work()`s it.
- **`C1C = 0xBFEF0542` is the tick's payload, not the die ID**: flag `0x05` (`ec_h0 == 0x5542`, "UB"
  from rootfsa PEB0) | `luofu_ubi_vols = 0xBEEF` (a sentinel that is never updated) | `kernelb[0..1] =
  0x2705` (uImage magic) & 0xff | `ec_h0 & 0xff`. Decode a crumb against its writer first.
- The sysctrl cells still die with the vendor's fallback boot; the only surviving channels are mtd9
  (panic or workqueue snapshot) and the tick payload.

## Next three experiments (in order, with predictions)

1. **G3's literal lines.** The log instrument now works, so capture a boot past the mount and read
   `VFS: Mounted root` / `Run /sbin/init`. Prediction: with the partition->master fix in place the boot
   passes `mount_root()` and the lines appear; if the capture still stops at the probe, the snapshot's RAM
   ring (`luofu_log_b`) is the suspect, so have the header page carry a self-read of its first 64 bytes.
2. **The spare/ECC mismatch.** The vendor's controller calls every page we write uncorrectable
   (`hi_nfc: ECC error`) although the data is byte-exact. Prediction: our program leaves the spare as `0xff`
   while the controller with ECC ON expects to WRITE its parity there; the fix is to let the controller
   produce the spare (do not pre-fill it) or to disarm ECC for the program and keep the reader raw. This must
   be right before any UBI volume is written.
3. **G4's transmit path.** `luofu_gmac_xmit()` has no transmit; the vendor's frames go through the
   switch/PFE ops table (`hi_eth_diag_tx` calls `[dev+0x40]+0x48`, engines `hi_lsw_dp`/`hi_lsw_pfe`).
   Prediction: a MAC-only register write will move no frame; the first green step is to find the switch's
   port-map/egress register pair and a descriptor ring the engine already accepts.

## Box state (last measured 2026-10-26 16:00Z)

Vendor 2.4.15 / 5.10.201 on slot A, selector `0x10`, ssh up, `mtd14` PEB0 = `UBI#`, **`mtd13` (rootfsa) also begins
`UBI#`** (it is a UBI container, not a raw squashfs), 4 `eth` interfaces, no `.omo` leftovers.

**FIXED THIS SESSION (source, builds clean as `77505176`):** the panic capture used to erase/program row
`960` = byte `0x1E0000`, which is `rootfsa`'s FIRST BLOCK - a UBI EC header. It now targets row `2368` =
`0x4A0000`, fac's last block. Every panic before this fix damaged the rootfs container.

**NO Wi-Fi on this image, and this session did not cause it:** `/lib/modules/5.10.201/` has no
`wifi`/`3881`/`hsan` module files, `/sys/class/ieee80211` is empty, no wifi process runs, `dmesg` has no
wifi lines, and starting the enabled `/etc/init.d/hsan_start` changes nothing. G6's "2 wiphys" belongs to
the `2.5.24` image, not the `2.4.15` one now booting. The vendor's dmesg also carries the pre-existing
`jffs2: Magic bitmask 0x1985 not found` sequence from `rootfs_data`, and `hi_nfc: ECC error` for every page
OUR kernel wrote (see the G2 row - data correct, spare not vendor-valid).

## Where the record lives

- `STATE.md` (this file) - current state and the next three experiments.
- `docs/sessions/2026-10-26.md` - today's vendor disassembly, the 1ef70ad diff, and the captures.
- `EVIDENCE-INDEX.md` - image -> fire -> result.
- `AUDIT-2026-10-22.md` - the structural audit and the restructure.
- `mem-entries.md`, `opensource/docs/phase*` - history (frozen; see the audit).

## The lock-free log programmer (`wraw`, 14:20Z)

The reason no retry budget could ever fix `0xC0DE5B50` is now written down: **the panic happens inside
this driver's own locked region**, so the notifier's `spin_trylock` runs on the CPU that already holds
the lock - and a spinlock cannot be taken twice on one CPU.

So the log takes a second path: the kthread already copies the ring into `luofu_log_b` while the box is
alive (190 lines measured), and `luofu_raw_log_program()` programs that copy straight to the log
partition through `luofu_fmc_erase_block()` / `luofu_fmc_write_page()` - neither of which touches
`luofu_fmc_read_lock`. It is deliberately crude because it exists for a dying box; the cost to watch is
that it writes while the system is alive (sharing `fmc->dma_buf`), so it must not corrupt a concurrent
read.

Slice 2,702,100 B md5 `94e85c88bdd5b84683145b3b7b03d881`.

## Next levers, in order (updated 2026-10-26 16:50Z)

0. **G4 IS GATED BY G6 - fix the ~30 s death first.** The control run shows `reboot -f` takes ~37 s to take
   the vendor down, so our kernel's whole life falls in that sweep's tail and it has ~30 s to boot, mount,
   start netifd and bring up `br-lan` before it could answer anything. The zero replies in `wtxping` are
   therefore **inconclusive, not negative**. The KPIE transmit path is written, builds, and boots
   (`C1C = 0x5AC00102`), but it cannot be tested on the wire until the box lives longer.
1. **The ~30 s death PREDATES every addition today (2026-10-27 00:55Z).** The minimal build
   (`fire_wclean`: no flash instrument, no pattern test, no KPIE code, no watchdog driver) also reached
   `SYSTEM_RUNNING` and also returned at `t = 60 s` - so the death is NOT our scaffolding, NOT the watchdog
   (four fires), and NOT the KPIE path. It lives in the **userspace handoff**, or in a facility this kernel
   lacks. Stop re-testing today's additions for the death.
   **And this bench has NO working panic channel**: `fac` row 2368, mtd9 at panic time, and pstore_blk
   (`PSTORE_BLK=y`, `BLKDEV=/dev/mtdblock10`, `MTD_BLOCK=y`, deliberate panics) all leave nothing. Any future
   capture design must be justified before it is built - three reasonable ones have failed.
   **Next: what does `init`/procd do in the first seconds after `SYSTEM_RUNNING`?** That is now the question,
   not "what panics".
2. **Then re-run ONE ping sweep** with the reboot issued as the sweep starts, ≥180 s of pings, and the
   window taken as [ssh stops answering, ssh answers again]. Only replies inside that interval can be
   attributed to our kernel.
3. G3's literal mount lines still need a text channel; the mtd9 line is closed after five rounds.

## The flash-log instrument: OPEN, fixed 2026-10-26 15:08-15:24Z

This section used to say the path was closed because every trigger left mtd9 all `0xff`. **That verdict was
wrong about the cause and is superseded.** The erase was landing (that is why `0xff` appeared) and the
PROGRAM was silently doing nothing because its `OP_CFG` was `0x9D0`/`0x830` - both encode `cs = 0` in the
layout where the read's proven `0x9A1` has `cs = 1`. With `0x9A1`:

- the panic path returned the whole boot log (`fire_werase`), including `READ ID 8c 2c 8c 2c 8c`;
- the live kthread path wrote its header page, read back as `4c 55 46 55 be 00 00 00` (`fire_wmaster`);
- a known pattern programmed by our kernel read back byte-exact through the VENDOR's driver
  (`fire_wpattern`, page 12 = `00 01 02 03 ... 4f`).

Two instrument bugs were found and fixed on the way: the snapshot passed a PARTITION mtd to the driver's own
`_erase` (its `priv` is not `fmc` - it SIGSEGV'd init at 3.7 s until `mtd_get_master()` was used), and the
panic notifier's "LOCK HELD" crumb was overwriting the kthread's walk count.

**What is still wrong with it, and why this line is CLOSED (2026-10-26 16:05Z):** five rounds (snapshot staging, raw-programmer staging, one-page-only, a late +12 s snapshot, and an in-function write-then-read-back verdict) leave this state: the writer is NON-INTRUSIVE (a +12 s snapshot still reaches `SYSTEM_RUNNING`), the header page always reads back exactly, and the ring pages never do - and the last round's verdict page itself came back all `0xff`, so even that write did not land. It serves only G3's literal mount lines, and G3's substance is already proven by `system_state = 2`, so further rounds are not worth a fire each. If the text is needed later, use a channel with a reader that needs no flash write (netconsole/ramoops backend), not another mtd9 variant.



---

## NEXT THREE EXPERIMENTS (written 2026-10-30, after the corruption fix)

**Box state at the time of writing:** vendor 2.4.15, `SEL=0x10`, slot A untouched (`27051956`),
both rootfs `UBI#`, recovery door armed (`tftp/recovery.bin` = 2.4.15, md5 `421114c8`).
The bench cable is on **eth2**. The host needs the `192.168.1.88` alias for the TFTP door.
**A stranded box looks like: power solid, everything else dark.** The mach leaves the u-boot
watchdog ARMED deliberately (the disarm was removed), so a hung kernel is reset by hardware -
UNLESS the watchdog driver is compiled out, which it is in the bisect config. A bisect slice that
hangs therefore strands the box and needs the RESET-hold TFTP door (host serves on 192.168.1.88:69).

**1. Settle the UBI layout-volume question.** The level-7 probe scans PEB0-3 at `+0x800` for a VID
header with valid magic + CRC and `vol_id == 0x7fffefff`:
`0xC0DE52A1` found -> UBI has no excuse and the fault is inside its scan;
`0xC0DE52A2` CRC mismatch -> we serve plausible-but-wrong bytes;
`0xC0DE52A5` no layout vol_id -> the layout records are somewhere else.

**2. Compare our partition offsets against the vendor own values.** `cat /sys/class/mtd/mtd13/offset`
and `mtd14/offset` on the vendor, against our DTS `rootfsb @ 0x3540000`. An offset wrong by even one
eraseblock produces EXACTLY what we see: valid `UBI#` EC headers (so the region looks like a rootfs)
but no layout volume at LEB 0/1. One ssh, and the cheapest remaining test.

**3. Clean up before publishing.** Remove the diagnostic stamps from `net/ipv4/inet_diag.c`,
`net/ipv6/af_inet6.c`, `net/ipv6/seg6.c` and `net/packet/af_packet.c` - those live in the BUILD TREE
only, the repo is clean of them. Fix the duplicate hardcoded window at `luofu-gmac.c:565`
(`0x80603000`, inside the same unreserved range). Restore the six drivers disabled for bisecting
(`LUOFU_WATCHDOG`, `LUOFU_GMAC`, `LUOFU_MDIO`, `ARM_SMCCC_SOC_ID`, `PL353_SMC`, `LEDS_GPIO`; note
that `kb.sh` merge re-enables them on a normal build). Rebuild with `tools\local-build.bat kernel`
and re-verify that the boot still reaches level 7 before calling anything done.
