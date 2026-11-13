# PLAN - full reversal and custom firmware for the WR3000 v2 (luofu)

Status: active. Owner: the bench session. Started 2026-11-10.
Supersedes nothing; extends `PLAN-OVERLAY-FINISH.md` (the overlay lane) with the whole reversal.

## Goal and definition of done

Replace the vendor kernel on this board with our own, keeping the vendor userspace usable, then
replace the userspace too. A reversal is DONE when all of the following hold on one image:

1. Our kernel boots from the B slot and reaches a real root: the vendor squashfs as `/`, overlaid
   with our persistent jffs2 upper, running the vendor `/sbin/init` (procd).
2. The system survives 1 hour with no watchdog reset, no `.omo-off` files, and a writable overlay
   that persists a file across a reboot.
3. Ethernet works as the vendor's does (address, ARP, ping both ways).
4. Wi-Fi works on OUR kernel: 2 wiphys, 6 interfaces, calibration `[SUCC]` on both bands, and a
   client can associate. This is the hardest gate and the one that decides whether the reversal is
   usable.
5. The image is clean: lab instruments disabled, no debug cells or seed tests in the release build,
   `MANIFEST.sha256` written, and the vendor A slot plus the TFTP recovery door verified as rollback.
6. The ledger (`mem-entries.md`), `STATUS.md`, and this plan are updated with the evidence.

The vendor userspace on our kernel is milestone M5; our own OpenWrt rootfs is M6 (post-reversal,
optional but the original ambition).

## Current state (verified evidence)

| area | state | evidence |
| --- | --- | --- |
| Kernel boot | our kernel boots, userspace runs (initramfs `/init`) | `C94=0xC0DE9B00|ret`, step0/0b |
| Verdict readout | TRUSTED: C94 survives the vendor boot | `step0b`: C94=0xC0DE9D00 |
| FMC read path | GREEN for data pages; jffs2 seed scans and mounts | `C88=0x1FA` (506 reads), `mem-entries` |
| FMC write path | GREEN for a single page (erase/program/read) | upgrade page 163, `0xC0DEA00C` |
| jffs2 upper | GREEN read-write in the mount test | verdict bit 1 from `step1c` on |
| overlayfs assembly | GREEN with the vendor squashfs lower (bits 2 and 4 together) | `phase2c`: C94=0xC0DE9D07 |
| squashfs lower | GREEN: UBI attach, ubiblock0_0, and the vendor squashfs all mount | `phase2b` (attach, record 118) and `phase2c` (0xC0DE9D07, C88=8,385 reads) |
| UBI content | vendor attaches mtd14 and sees volume 0 `squashfs` | `ubiattach -m 14 -d 1`, `ubinfo` |
| Ethernet | ONE defect from green (ARP resolves, ping 0/3) | `STATE.md:731` |
| Wi-Fi | vendor-only modules, not in our image | `STATE.md:4032`, `luofu.fragment` |
| Sustained uptime | unconfirmed on our kernel | `STATE.md:344`; the pet/procd wall |

The vendor's mtd14 geometry, read from the vendor's sysfs: writesize 2048, oobsize 64,
erasesize 131072, size 24379392. The UBI EC header at offset 0 says vid_hdr_offset 2048 and
data_offset 4096; the VID header at 2048 reads `UBI!` and the volume table record at 4096 names
`squashfs`. So the UBI metadata is in-band data pages, not OOB bytes.

## Operating rules (non-negotiable)

- One variable per fire. Every kernel change is built, disassembled to prove the change is in the
  image, assembled into a slice, flashed, and read back after the vendor returns.
- The device cycle is detached. The watchdog pet is bounded; the vendor returns at ~705 s. The box
  must end healthy: 2 wiphys, 6 interfaces, cal SUCC, 0 hidden modules.
- Never write CA `0x400392f0`; never read the RC misc window `0x10161000`; never rmmod vendor modules.
- A verdict is a single value with a single last writer. The current scheme: the mount test sets
  `luofu_overlay_verdict`; the mach pet republishes it; `init/main.c` publishes it when exec returns 0.
  Failure layouts are `0x9D0000xx`; success is `0xC0DE9D07`.
- Every fire appends a timestamped entry to `mem-entries.md`. `STATUS.md` is the current state.
- Builds are local. `make ARCH=arm CROSS_COMPILE=... zImage` in
  `build/linux-kbuild/linux-5.10.201`; the slice is uImage plus the fixed 40,732-byte trailer.

## Phase A - UBI attach (immediate blocker)

Objective: `ubi_attach_mtd_dev("rootfsb")` returns a UBI number, `ubiblock0_0` exists, and squashfs
mounts at `/mnt/lower`, producing `0xC0DE9D07`.
Status: DONE (`phase2c`, C94=0xC0DE9D07, C88=8,385 reads). Two fixes closed it: the read path now
forces the vendor's ECC type 1 instead of restoring a possibly-zero `saved` value, and the block
node is created with `new_encode_dev(dt)` because `init_mknod()` decodes with `new_decode_dev()`.

Evidence already collected:
- Our attach returns -EINVAL after ~1,100 reads (`step1f`, C94=0x9D16000D, C88=0x641).
- The vendor's attach of the same mtd14 succeeds and volume 0 is a static 14.2 MiB `squashfs`.
- The geometry is standard: writesize 2048, oobsize 64, erasesize 128 KiB; EC/VID headers at
  0 and 2048, LEB data at 4096.
- `phase2a` (C94=0x9D16006D) compared the metadata CRCs through our read path: EC and VID headers
  match the vendor, vtbl record 118 does not. The driver's own ECC comment names the cause: with
  ECC off the controller splices 14 spare bytes at 1040 and the record CRC becomes `f1160000`.
  The read path restored the FMC_CFG ECC_TYPE instead of forcing the vendor's on value (0x1823,
  ECC_TYPE=1), so a prior erase/write can leave the engine off. `phase2b` forces ECC type 1 for
  every data read.

Hypotheses, in order:

A1. The data our FMC read path returns for the UBI metadata differs from the vendor's. The vtbl
    record CRC is the first victim. Experiment: dump mtd14 offsets 0..4096 and the layout-volume
    LEBs through our `mtd_read`, compute CRC32, and compare with the vendor's identical ranges.
    If they differ, the read path is the defect. If they match, A2.
A2. The UBI geometry derived from the EC header differs from our device. Experiment: instrument
    `ubi_io_read_ec_hdr`/`ubi_read_volume_table` with crumbs (or a temporary printk ring) to log
    `vid_hdr_offset`, `data_offset`, `leb_start`, and the failing `vtbl_check` reason.
A3. The attach fails at a specific layout-volume LEB or vtbl record. Experiment: walk the layout
    volume LEBs (the PEBs whose VID header has vol_type=layout) and validate each 4096-byte record's
    CRC in a kernel-side test, depositing the first failing record index.
A4. The read path mishandles a multi-page or partition-relative read (the `mtd_get_master_ofs`
    translation, a page that crosses a 2048-byte boundary, or the ECC-on copy shape). Experiment:
    read a known-good 128 KiB PEB through both the vendor and our kernel and diff every page.

Success: ubi0 attaches; `ubiblock0_0` is created (or created by the test); squashfs mounts from
`/dev/ubiblock0_0`; verdict `0xC0DE9D07`. Rollback: the vendor returns on the watchdog; no vendor
partition is written by the test.

## Phase B - overlay write-through and persistence

Objective: prove the persistent upper, then use it.

Status: WRITE-THROUGH GREEN on 2026-11-12 (`phase3s`: C94=0xC0DE9D0F, `/overlay/upper/persist.txt`
= `LUFU-PERSIST` read back from the vendor). The persistence half is `phase3u` (seed disabled for one
boot; the mount test reads the file back instead of writing it). `phase2d` returned C94=0xC0DE9D07 (all three mounts up) but the write bit is clear
and raw mtd15's first megabyte on the vendor contains neither `persist.txt` nor `LUFU-PERSIST`, so
the create/write/fsync failed before anything reached flash. `phase2e` returned C94=0x9E001E07:
all three mounts up, write errno 30 (-EROFS). `phase2f` returned C94=0x9E001E27: the jffs2
superblock is still read-write, the OVERLAY superblock is read-only, and the MTD erase/program/
readback hook test FAILED. The write wall is the MTD hook path below jffs2, not the overlay itself.
`phase2g` encodes the failing hook step in bits 16-23 of the 0x9E layout: 0x10|errno erase,
0x20|errno write, 0x30|errno read, 0x40 mismatch, 0 = hooks clean. It returned C94=0x9E401E27:
erase and write returned 0 but the readback mismatched. The vendor's mtd16 at 0x20000 still carries
the old `HSPQ` header, with our XOR pattern from 0x38 onward, the exact AND of the old bytes with
our buffer. So the block was never erased and the program wrote over it: the MTD erase hook is a
silent no-op on upgrade block 1. `phase2h` moved the same test to block 2 (offset 0x40000), the
block the raw page-163 write test proved erasable and writable, and returned C94=0x9E401E27 again:
block 1 was not special and the MTD erase hook no-ops regardless of block. The raw driver erases and
programs the same block, so the defect is specific to the `mtd_erase` path. The next experiment is a
direct `luofu_fmc_erase_block()` against `mtd_erase()` on the same block, with `instr->addr`, the
computed row and the return encoded in the verdict, so the address convention is measured rather
than assumed. `phase2i` returned 0x8E4040: the raw and MTD paths both mismatch on upgrade block 2,
so that block is the confound. `phase2j` returned the same 0x8E4040 on rootfs_data block 7: the
failure follows the block, and block 7 is suspect because the seed test does not verify its erases
and LUFU/a5 remnants remain in later blocks. `phase2k` moves the comparison to block 0, the only
block this bench has proven erasable and writable (the seed lands there every boot), to separate the
erase hook from a bad-block confound. `phase2k` returned 0x8E4040 on block 0 too, so the block and
the erase are not the cause: the read is racing the asynchronous program because the driver's
post-kick wait was deliberately removed. `phase2l` adds `msleep(20)` between program and readback on
both paths; 0x8E0000 would mean the hooks and the raw path are fine and every earlier mismatch was
the test's timing. `phase2l` still returned 0x8E4040 with the 20 ms settle, so timing is dead.
`phase2m` encodes the raw and MTD readback first bytes in the verdict (pattern 0x5a, seed 0x85,
erased 0xff) to establish what the page actually holds after the erase and program. `phase2m`
returned 0x8E400000: both readback bytes are 0x00, so the reads succeed and return zeros. Root cause
found in the write path: `luofu_fmc_write_page()` never set the on-die ECC type, while
`luofu_fmc_read_page()` forces type 1, and `luofu_fmc_erase_block()` restores its own entry value, so
a program could go out with ECC off and read back as garbage. The write now saves the ECC type, sets
type 1 for the program, and restores it; `phase2n` reruns the block-0 comparison. `phase2n` still
returned 0x8E400000, and the C88 self-test showed the real defect: the bootloader spec record
overrides the program operands with wr_cmd 0x00 and wr_addr_cyc 0, so every program went out with no
command byte and no address and the page stayed erased. The write operands are now pinned to the
measured-good defaults (0x32/3/5/0) after the record parse, and `phase2o` verifies the block-0
comparison. `phase2o` was unchanged because the write computes the spec OP_CFG and then overwrites
it with a hardcoded 0x9A0 - the shape the driver's own comments call "accepted, array unchanged".
The 0x9D0 shape is the one behind the page-163 LUFU proof; the write now uses 0x9D0 and `phase2p`
verifies. `phase2p` still failed, and the vendor's own read of rootfs_data page 0 settled it: mtd15
page 0 has the md5 of 2048 bytes of 0xff, so the erase works and the program never lands. The
vendor's live register dump after a real write holds FMC_CMD = 0x10, the program-execute command,
which this path never sends; `phase2q` issues it after the load. `phase2q` still left page 0
all-0xff, so the execute alone is not the answer. The ledger's proven page-163 write (C88
0x04327400, self-test read clean) had neither an explicit write enable nor a separate execute; the
vendor's controller performs both. `phase2r` removes both additions and restores the proven shape:
OP_CFG 0x9D0, OP_CTRL low 3 with wr_cmd 0x32, the address, the data, the INT poll, nothing else.
`phase2r` still left rootfs_data page 0 all-0xff, while the upgrade pages are known to take writes
(the 0x20000 page carried our buffer ANDed with the old header). `phase2s` moves the same test to
the upgrade page 163 (offset 0x51800) to separate the write path from the target. `phase2s` proved
the write works: the vendor's upgrade page 163 reads our 0x5a^i pattern ANDed with the old LUFU/0xa5
bytes, and C94=0x8E404848 shows the read path returning programmed content. The split is now
partition-level: rootfs_data refuses writes while the unmounted upgrade accepts them, which matches
the vendor locking the filesystem blocks. `phase2t` issues a global block unlock (0x7b) before the
rootfs_data block-0 erase/write and the vendor's dd of mtd15 page 0 is the readout. `phase2t` still
left page 0 all-0xff, so the 0x7b op is either wrong for this chip or the lock is not the cause. Two
rootfs_data blocks (0 and 7) have refused programs while upgrade block 790 accepted one, which is
equally a bad-block signature. `phase2u` tests rootfs_data block 3 (offset 0x60000, vendor dd page
192) and checks `mtd_block_isbad()` first; a bad block returns the verdict 0x8E0B0B. `phase2u`
returned 0x8E005A5A - the readbacks matched the pattern, but the vendor's page 192 is all-0xff, so
the read path echoed the write's own DMA buffer. Every in-kernel readback is now suspect unless a
vendor dd corroborates it. Block 3 is not bad; the write still fails on the mounted partition.
`phase2v` reads the NAND's feature status (0xA0) and config (0xB0) into the verdict and tries the
per-block unlock (0x7f) with the block's row before the same erase/write; the vendor dd of page 192
remains the ground truth. `phase2v` returned status 0x00 (no NAND lock), and the vendor's module
supplied the answer: `hi_fmc_wp_en_set`/`hi_fmc_wp_en_check` toggle bit 6 of `FMC_GLOBAL_CFG`, and
the vendor clears it before every write and erase. Our probe's line whose comment says "clear the
write-protect bit" actually ORs the bit IN with `| BIT(6)` - the driver turned the flash write
protection ON at every boot, so accepted programs left the array untouched. Fixed to
`& ~FMC_GCFG_WP_EN`; `phase2w` reruns the rootfs_data block-3 write and the vendor dd of page 192.
`phase2w` returned 0x9D0000E3, the failure layout: j1 (jffs2) and j2 (squashfs) mounted, j3 (the
overlay mount) failed, so the write test never ran. The WP fix made the seed test's erase/seed real
and the jffs2 read-write; the overlay mount is now the refusal. `phase2x` carries the j3 errno in the
verdict. `phase2x` returned 0x9D1600E3: the j3 errno is 22 (EINVAL), and the cause is in the test
itself - it creates /overlay, /mnt, /mnt/lower and /mnt/new but never /overlay/upper or
/overlay/work, so the overlay mount depended on the seed image and on a stale workdir from the last
unclean reset. `phase2y` creates both directories on the freshly seeded jffs2 before the overlay
mount. `phase2y` returned 0x8E00005A, which is only reachable when j1, j2 and j3 are all zero and
the write test fails: THE OVERLAY MOUNT IS UP. The write test is now the single failing step and
`phase2z` carries its errno in the high byte (0x8E | -wr << 16 | raw/mtd bits). `phase2z` returned
0x8E1E005A: -wr = 30, EROFS. The kernel's overlayfs forces the superblock read-only when the index
feature is on and the jffs2 upper cannot host the index directory. `phase3a` mounts with `index=off`;
if the sb comes up read-write the write test runs and the success tag is 0xC0DE9D0F. `phase3a`
returned the same EROFS, so the index branch was not the cause. `phase3b` reads both superblocks and
returns 0x8F | wr_err << 16 | sb_flags << 8 | 0xAA, where bit 0 means the jffs2 on /overlay is
read-only and bit 1 means the overlay on /mnt/new is; that separates an MTD/JFFS2 mount problem from
overlayfs's own workdir logic. `phase3b` returned 0x8F1E02AA: the jffs2 is read-write and the overlay
is read-only, so overlayfs itself is refusing the superblock. `phase3c` reads the private
`struct ovl_fs` from the mounted overlay and adds bit 4 (the upper mount is set) and bit 8 (the
workdir is set); whichever pointer is missing names the read-only source directly.

1. Create `/mnt/new/persist.txt` through the assembled overlay (kernel-side `filp_open`/`kernel_write`
   or the userspace `/init`).
2. Read it back from the vendor by mounting the jffs2 partition and reading `upper/persist.txt`.
3. Reboot and show the file survives the whole cycle (the seed test must be disabled for this fire,
   or narrowed so it does not erase the file).
4. Verdict: a new bit or a dedicated cell; the file itself is the primary evidence.

### The 2026-11-11 ladder to the write-buffer root cause

`phase3c` through `phase3k` walked the write failure from overlayfs down into jffs2:

| fire | C94 | what it proved |
| --- | --- | --- |
| `phase3c` | `0x8F1E06AA` | overlay is RO, the upper mount is set, the workdir pointer is NULL |
| `phase3d` | `0x8F1E16AA` | workbasedir is set too, so `ovl_workdir_create`'s mkdir is the failing step |
| `phase3e` | `0x8F1116AA` | that mkdir is EEXIST: a stale `/overlay/work/work` is cleaned and refused |
| `phase3f` | `0x9D0200E3` | a fresh `/overlay/wk2` basedir is not resolvable (ENOENT) |
| `phase3g` | `0x9D1C11E3` | upper is EEXIST, fresh wk2 is ENOSPC: rootfs_data was 1 MiB |
| `phase3h` | `0x9D1611E3` | with 8 MiB, wk2 becomes EINVAL: the space problem was hiding a write-path problem |
| `phase3i` | `0x9D1611E3` | the highest_ino probe never reached its reporting branch; the seed's numbering is clean |
| `phase3j` | `0x9D1C11E3` | a real mkfs.jffs2 seed still hits ENOSPC: the appended DTB was stale |
| `phase3k` | `0x9E801616` | the booted kernel sees 8 MiB (`0x80`); both mkdirs are EINVAL |
| `phase3l` | `0x9E801C1C` | partition typed NOR -> write buffer active -> both mkdirs are ENOSPC |
| `phase3o` | `0xC0DE9A01` | no verdict: the mount test died before its C94 write; the marker-through-wbuf shape is unsound because the erase path has `c->nextblock == NULL` |
| `phase3s` | `0xC0DE9D0F` | WRITE-THROUGH GREEN: all mounts plus the write test; `persist.txt` is in the jffs2 upper |
| `phase3u` | pending | persistence: seed disabled, read-back of the 13 bytes `phase3s` wrote |

`phase3l` carries the first root cause: 5.10 hardcodes `jffs2_cleanmarker_oob()` to 0, the write buffer is only
set up for `MTD_NORFLASH` without `MTD_BIT_WRITEABLE`, and with type `MTD_NANDFLASH` jffs2 issued direct
unaligned node writes that `luofu_mtd_write()` refuses with -EINVAL. The rootfs_data partition is retyped
at probe; the master keeps `MTD_NANDFLASH` for UBI.

`phase3t` carries the second: the erase-complete marker is a 12-byte direct write, and a NAND page is
programmed whole, so the driver now merges partial writes (read the page, overlay, program the page).
The only partial write jffs2 issues lands on a freshly erased page, so the merge is exact.

This is the first test of the jffs2 write-buffer path. If it hangs, the verdict is the last progress
code and the jffs2 wbuf is the lane.

## Phase C - real root and vendor init

Objective: mount the vendor squashfs as `/`, overlay it with our jffs2 upper, run the vendor
`/sbin/init`, and keep the box alive past the procd hand-off.

1. Repoint the overlay: lower = ubiblock0_0, upper = our jffs2, merged root used as `/` (pivot_root
   or init_mount + init_chroot).
2. The watchdog: procd must receive the WDTFD and reach its event loop. The kernel pet shim is a
   debug instrument; the real fix is on the userspace/procd side (the known wall: procd never
   reaches its event loop, the 30 s watchdog expires).
3. Evidence: a userspace marker written through the overlay, a 1-hour uptime, no reset.
4. Compare the vendor init's boot against the vendor's own boot log; any driver our kernel lacks
   (Wi-Fi, PCIe, GMAC) shows up here.

### The vendor-init variant (2026-11-12)

**Injury and correction.** `phase3w` ran this path and the box came back with only DNS (53) listening:
the vendor's `dropbear`/`uhttpd` never start because their `/etc/config` entries live in `rootfs_data`,
the partition the seed test has been erasing on every fire. The vendor-init path also let the vendor's
own preinit and `mount_root` run on that partition, which is what finished it off. The correction is
to stop treating `rootfs_data` as lab scratch:

- The lab overlay upper and the seed test move to the **`upgrade` partition** (mtd16, 29.5 MiB at
  0x6280000), which the vendor does not mount at boot. The vendor's `rootfs_data` is then left alone.
- Phase C's proof marker becomes ONE targeted write into the vendor's upper, not a partition erase:
  the initramfs `/init` mounts `/dev/mtdblock15` read-write, writes `upper/etc/rc.local` (the marker
  script), unmounts, then pivots. A single 100-byte file does not endanger the vendor's config.
- Recovery note: if a fire still leaves the vendor unreachable, the door is RESET-hold + TFTP
  (`tftp/recovery.bin`).

The kernel image keeps its initramfs, and the initramfs `/init` does the minimum:

1. mount the vendor's config partition with `mount("mtd:rootfs_data", "/vendor", "jffs2", 0, NULL)`,
   write `upper/etc/rc.local` (the marker script) and detach it. The `mtd:` form is required: the
   initramfs devtmpfs does not carry `/dev/mtdblock15` (nor `/dev/mem`; the init mknods chr 1:1
   itself), so path sources return ENOENT;
2. move devtmpfs onto `/mnt/lower/dev` (the squashfs has an empty `/dev`);
3. `chdir("/mnt/lower")` and `pivot_root(".", ".")`, falling back to `chroot(".")` because an
   initramfs `pivot_root(".", ".")` against the kernel mount test's squashfs mount returns EINVAL;
4. `execve("/sbin/init")` and, if that fails, `execve("/etc/preinit")`.

The squashfs at `/mnt/lower` is the one the kernel mount test (j2) already mounted read-only from
ubiblock0_0; a second mount of that block device while the first is lazily detached fails, so the
init pivots into it instead of mounting its own.

Every stage reports into C94 through an mmap of page 0x10100 (a file-position `write()` to
`/dev/mem` returns EFAULT on this SoC, while an mmap plus a plain store lands). The word is
accumulated: `0x6B000000 | tags`, with the vendor-fs mount errno in bits 4-7, a shadow-written bit
at 8, the devtmpfs move errno in 12-15, the chdir errno in 16-19, the `pivot_root` errno in 20-23,
the `chroot` errno in 24-27 and an exec bit at 28. A top half other than 0xC0DE means the vendor's
own boot wrote the cell afterwards, so only the low half is read as ours.

Instrumented results so far: the init runs (`phase3af` proved the stage tag lands, and its
`fail(1)` showed both squashfs mount sources refused); a pivot into the kernel-mounted squashfs
fails at `pivot_root(".", ".")` (`phase3ah`), which is why the chroot fallback exists; and a
vendor-fs mount by path returns ENOENT (`phase3ai`), which is why the mount source is now
`mtd:rootfs_data`.

A fire that leaves the box factory-default is not necessarily a crash: the vendor's own dmesg shows
it found the config fs corrupt (`Eep. No valid nodes for ino #4335`) and rebuilt it. The reset also
wipes `/etc/dropbear`, so SSH is restored by mknod'ing the host key fresh with `dropbearkey` and
restarting `/usr/sbin/dropbear -p 22 -R` over the web command sink.

Everything else is the vendor's own machinery: `/sbin/init` is procd, and the vendor's preinit
mounts `mtdblock15` at `/mnt`, writes `upper/etc/mount_protect`, and `/sbin/mount_root` builds the
overlay from the squashfs root and the jffs2 upper. That tests the real chain instead of a lab
assembly of it, and it is the shape the release build needs.

The proof that the vendor userspace ran on our kernel is a shadow of `/etc/rc.local` written into
the jffs2 upper before the overlay is built. The vendor's `/etc/init.d/done` runs `sh /etc/rc.local`
at START=95, and ours deposits `0xC0DE600D` in C94 and writes `/etc/procd-ran`. If the box comes back
with C94 still `0x9F00xxxx` (the pet's no-verdict marker), procd never reached the end of boot.

**CONFIRMED 2026-11-13 07:06 (kernel-version evidence).** The retry of `phase3as` logged, from the
vendor userspace running on OUR kernel: `/boot.log` = `S10boot 1763000383 #162 SMP Fri Nov 13
06:33:52 +07 2026`, then S18hyfibrd, S20network, S95done, and `/kernel-ran.log` = `1763000415 #162
SMP ... 2026`. Build #162 is this tree, so the vendor's preinit, `mount_root`, procd and the whole
rc.d chain ran to the end on our kernel. The enabler was releasing the `/vendor` shadow mount with a
PROPER umount before the chroot: while our mount held the config partition, the vendor's `mount_root`
could not take it and the preinit never reached S10boot (the stock kernel's later fallback boots run
the same shadow, which is what made the C94-only evidence ambiguous). The DTS fix to `rootfs_data`
(`<0x4c80000 0x1600000>`) is what made the shadow write and the proper unmount safe.

## Phase D - Ethernet

Objective: close the last defect from green. The current state: ARP resolves, frames move, host
ping 0/3. Check the GMAC driver's RX path, the PHY link state, and the IP configuration. The vendor's
GMAC driver and the dumps in `dumps/router-20261108` are the references.

State on 2026-11-13: MEASURED on our kernel with the vendor userspace fully up (Phase C confirmed).
The userspace sees only `lo`; the kernel dmesg for build #162 says, four times,
`/ethernet@14380000: Failed to get clk index: 0 ret: -517` (and 14400000/14480000/14500000), i.e. all
four GMAC nodes sit in EPROBE_DEFER waiting for a clock provider that never registers. The vendor's
netifd runs (S20network logged) and the cmdline `ip=192.168.10.1:...:eth2` is present, but eth2 does
not exist, so there is nothing to configure. The Phase D work is therefore the clk provider those
gmac nodes reference, not the MAC driver. Wi-Fi is absent for the known reason: `Could not find PHY
for device 'radio0'/'radio1'`.

State on 2026-11-12: the current image has NO ethernet driver at all. The shrink fragment sets
`# CONFIG_ETHERNET is not set` and the gmac/mdio sources were missing from the build tree (lost in
the same source loss that took the watchdog). Both sources are back in the tree now under
`drivers/net/ethernet/luofu/` with Kconfig/Makefile entries, and the integration BUILDS: with
`CONFIG_ETHERNET=y`, `CONFIG_PHYLINK=y`, `CONFIG_LUOFU_MDIO=y` and `CONFIG_LUOFU_GMAC=y` the whole
`zImage` links with `luofu-gmac.o` and `luofu-mdio.o` built in. One core Kconfig change was needed:
`PHYLINK` had no prompt, so a built-in consumer could never select it as `y` and the gmac could only
be a module; `drivers/net/phy/Kconfig` now gives it `tristate "PHYlink support"`. The next Phase D
fire is therefore an integration fire, not a code fire. The cable is on eth2 (gmac 0x14480000, mdio0:04), not eth0.

The measured target from 2026-10-30: ARP `192.168.10.2 -> 10:ff:e0:c7:f0:26` REACHABLE, the bridge
answers its own `192.168.10.1` in 0.17 ms, tx 45->179, rx 97->261, zero tx/rx errors, and the host
ping still 0/3. The remaining asymmetry is between frames the kernel counts as transmitted and
frames the host receives, which is a TX path or MAC/PHY mapping question, not an ARP one.

## Phase E - Wi-Fi (the gate that decides usability)

Objective: 2 wiphys, 6 interfaces, calibration `[SUCC]` on both bands, on our kernel.

State on 2026-11-12: nothing in the kernel fragment and nothing in the initramfs gives our image a
wifi driver, so this is untouched. The reversed lane is deep and documented in
`opensource/docs/PORT-STATUS.md`: our own cfg80211 driver binds and creates a wiphy and a netdev on
the live device, the endpoint claim, the message window, the ETE rings, the firmware load and
release, the SR-post-triggered id-6 word, and the host half are all proven on hardware. The data
path is gated on a TX credit that the vendor chip layer (`wifi.ko`) installs at runtime, and the
vendor stack cannot be `rmmod`'d (it panics deterministically), so a port must coexist rather than
replace it.

The plan's step 1 is still the cheapest first move: try the VENDOR `luofu-wifi`-family modules under
our kernel. Everything they depend on (PCIe controller, CRG clocks/resets, pinctrl, the HCC window)
is now either present or reversed, and the ABI is the same 5.10.201. If they load and bind, the
calibration store is the remaining question; if they refuse, the refusal names the missing SoC piece.

## Phase F - release and rollback

1. Strip the lab instruments from the release config (seed test, mount test, UBI diag, crumb
   deposits, flash log snapshot, pet debug writes). Keep the crash capture if it is cheap.
2. Build the clean image, write `MANIFEST.sha256`, flash the B slot, and validate all gates.
3. Verify the rollback: the vendor A slot boots, the RESET hold + TFTP recovery door is armed, and
   the box ends healthy.
4. Update `STATUS.md`, `mem-entries.md`, and this plan with the final evidence.

## Order and dependencies

A -> B -> C -> (D and E in parallel) -> F. C depends on A; E depends on C (or at least on the PCIe
and clock drivers C validates); D is independent and can be done while A is being debugged.

## Evidence and receipts

Every phase ends with files: a fire log under `build/linux-kbuild/`, a ledger entry in
`mem-entries.md`, and a gate row in `STATUS.md`. The local fire logs are gitignored; the ledger
entries carry the values and the interpretation, which is the repo's rule.
