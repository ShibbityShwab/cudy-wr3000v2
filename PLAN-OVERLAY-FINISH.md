# PLAN - finish the WR3000 v2 overlay firmware

> The full reversal plan is `PLAN-FULL-REVERSAL.md`. This file remains the overlay lane's detail.

## Where it stands (2026-11-10, after the Step 0/1 fire run)

- Our kernel boots and userspace runs (initramfs `/init`, raw syscalls).
- Step 0 (readout): DONE. C94 is the one trustworthy verdict cell; `0xC0DE9D00` survived the vendor
  boot and proved the mount test ran. The exec ladder and the mach pet both publish
  `luofu_overlay_verdict`.
- jffs2 rw mount on `rootfs_data`: PROVEN (verdict bit 1 in every fire from `step1c`).
- overlayfs assembly: PROVEN with the empty /mnt/lower directory as a lower (verdict bit 4). The
  missing pieces were the mount points and the page-sized option buffer.
- squashfs lower: BLOCKED. The vendor rootfs is inside a UBI volume (mtd13/mtd14 start with "UBI#").
  Our kernel's `ubi_attach_mtd_dev("rootfsb")` returns -EINVAL after ~1,100 reads, while the
  vendor's own attach of mtd14 succeeds and its volume 0 is a static squashfs. The next lane is
  `ubi_read_volume_table` / `vtbl_check`.
- Writes: FMC single-page write proven; the jffs2 wbuf path is still untested (Step 2 waits on a
  lower).
- Wi-Fi: vendor-only modules, not in our image (separate lane).

## The blocker (resolved): cell observability

It was never the cells. Three of our own writers shared C94: the mount test's deposit, the mach pet
counter every beat, and init/main.c's exec ladder (`0xC0DE9B00|ret`) after the mount test. The ladder
was the last writer, so the verdict was overwritten by our code, not erased by hardware.

Fix: the mount test sets `luofu_overlay_verdict`; the exec ladder publishes it when non-zero, and the
pet republishes it. Readout values: `0xC0DE9D07` full assembly, `0xC0DE9B00` exec was last,
`0x9F00xxxx` no verdict, `0x9D0000xx` failure layout with j1/j2 errnos.

## Step 0 - establish ONE trustworthy readout: DONE

`C94 = 0xC0DE9D00` after a fire whose mount test deliberately failed on missing mount points; the
value survived the vendor boot and matched the source-level prediction exactly. The pstore/panic
options were not needed: the driver's own history already showed pstore_blk is broken on this board
and the kernel never panics. Evidence: `mem-entries.md` 2026-11-10 and `fire-step0b.log` (local).

## Then, in order

1. Overlay assembly: PARTIAL. jffs2 (bit 1) and overlay (bit 4) mount; squashfs (bit 2) is blocked by
   the UBI attach -EINVAL. Success target remains `0xC0DE9D07`. The three-mount code is in
   `luofu_mount_test_init`; the UBI path is self-contained (scan ubi0..3, attach rootfsb, open volume
   0, create the ubiblock) and reports the attach errno. A scratch squashfs on a GOOD block (the log
   partition, or a DTS partition at upgrade+0x20000) can unblock Step 2 without the vendor UBI;
   mtd16 block 0 is a marked bad block and cannot carry an image at offset 0.
2. Write through the overlay: pending; waits on a working lower.
3. Real root: pending; the UBI attach fix is its prerequisite.
4. Wi-Fi lane: pending.
5. Docs: updated on every fire (`mem-entries.md` carries the full record).
