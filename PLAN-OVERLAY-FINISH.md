# PLAN - finish the WR3000 v2 overlay firmware

## Where it stands (2026-11-10)

- Our kernel boots and userspace runs (initramfs `/init`, raw syscalls).
- jffs2 mount on `rootfs_data`: PROVEN. Seeded 364-byte mkfs image; 506-read scan on the 1 MB partition;
  the mount test's result read back as `0xC0DE9B00`.
- squashfs mount on `rootfsa`: PROVEN via the fs_context block (the 0x100 bit in the same verdict).
- overlayfs: enabled in config (`CONFIG_OVERLAY_FS=y`), kernel ~2.70 MB; the namespace assembly is
  attempted but its verdict has not been observed yet.
- Writes: FMC single-page write proven on upgrade page 163; the jffs2 write-buffer path is untested.
- Wi-Fi: vendor-only modules, not in our image (separate lane).

## The blocker: cell observability

C94/C98/C04/C18 do not reliably retain our writes across a boot. The mach's early write, the mount
test's deposit and the userspace markers all vanish, while the read path's own C98 values appear. The
vendor boot may also touch some cells (C8C was clobbered). Until one trustworthy readout exists, every
verdict is guesswork.

## Step 0 - establish ONE trustworthy readout (do this first)

Options, in order of confidence:
1. Kernel panic after the verdict with pstore/ramoops enabled, so the console is captured and readable
   from the vendor boot (`/sys/fs/pstore`).
2. `initcall_debug` plus the same panic capture, to see whether the mount test's initcall runs at all.
3. Verify what actually writes `0xC0DE9B00` to C94 (a hardware/vendor source would explain every
   vanished stamp).

## Then, in order

1. Overlay assembly: three `init_mount`s (jffs2 at /overlay, squashfs at /mnt/lower, overlay at
   /mnt/new with lowerdir/upperdir/workdir) and a verdict of `0xC0DE9D07`.
2. Write through the overlay: create a file under the overlay, confirm it lands in the jffs2 upper via
   the wbuf path, and read it back from the vendor.
3. Real root: mount the vendor squashfs as `/`, overlay it with our jffs2 upper, run the vendor init,
   and compare against the known procd-hang wall.
4. Wi-Fi lane: evaluate the vendor `luofu-wifi` module under our kernel.
5. Docs: STATUS, mem-entries and the memory fact file updated on every fire.
