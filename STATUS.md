# STATUS - Cudy WR3000 v2.0

**Updated:** 2026-11-15
**Pins are not written here.** Derive them with `git rev-parse --short HEAD` and
`git -C opensource rev-parse --short HEAD`.
**This is the only live status page.** Regenerate it; do not append to it.

## 1. Bench

- Box: the last known state is the stock 2.4.15 image, recovered and provisioned.
  Root telnet on 23, Wi-Fi `cudy-lab`, LAN `192.168.10.1`.
- Access: SSH key `.omo-secrets/router_ed25519`. There is no `.sshwrap/` in this
  checkout. The broker channel is `tools/box-provision.sh` with
  `dumps/router-20261108/bdinfo.bin`.
- Latest build (local-only): `build/linux-kbuild/luofu-slice-phase3df.bin`
  (2026-11-15 14:33, 2,766,628 bytes, md5 `9e4015cadd2aa507a1763615b6ac914e`). It
  carries the `wfile()` instrumentation, and that instrument is in the image: the XZ
  kernel stream decompresses to an initramfs whose single `init` is byte-identical to
  the tracked source's current compile. The 15:29 broker fire (attempt 4) wrote and
  verified `kernelb` and rebooted, and the box came back on the stock kernel (`#0
  SMP Nov 25 2023`), so the instrument never ran. See section 3 for why and
  section 4 for the next fire.
- The latest SSH fire script (local-only) is `build/linux-kbuild/run-phase3dc.sh`;
  3dd, 3de and 3df have slices but no run scripts. The broker lane is
  `tools/box-provision.sh --stage fire` and now defaults to the newest
  `luofu-slice-phase*.bin`; pass `SLICE=` to pin one. The per-phase run scripts are
  bench-local; the tracked generic `fire.sh ssh` driver covers a fresh clone. The
  dynamic default and the HTTP path changes are code-verified and dry-run checked,
  not device-verified; the next fire tests them.

## 2. Gates (2026-11-14)

| gate | state | receipt |
| --- | --- | --- |
| **G1** FMC reads real flash | GREEN | page-0 magic `UBI#`; level-7 MTD probe found the partition, the EC magic, `vid_hdr_offset = 0x800`, and `PEB0+0x800 = 'U'` |
| **G2** program path | GREEN | a page written by our kernel read back byte-exact through the vendor driver |
| **G3** our kernel + real rootfs + userspace | GREEN 2026-11-14 | vendor preinit, `mount_root`, procd and the full rc.d chain run on our kernel from the squashfs root; kernel-version breadcrumbs `#162` to `#199` |
| **G4** Ethernet on our kernel | GREEN 2026-11-14 | vendor switch/MDIO/PHY/MAC modules load as patched modules; `eth2` up at 1 Gbps with the Hisilicon Genius PHY, `br-lan` 192.168.10.1, ping 3/3. Our own `luofu-mdio` and `luofu-gmac` also carry a 1 Gbps link (M2) |
| **G5** Wi-Fi on our kernel | vendor-only | the lab `wifidrv`/`hccaccept` line builds and loads; no wiphy from our driver |
| **G6** sustained uptime | GREEN 2026-11-14 | the reset was a userspace watchdog race, not a panic; the initramfs keeper holds the 25-minute timer |

G4 is met by the vendor's modules. The clean-room drivers reach the same link, but the
radio (G5) is still the vendor's.

## 3. Current blocker

The initramfs `/vendor` mount can come up read-only on this strap. When it does, the
init's `wfile()` shadow writes are silent: no `boot.log`, no `mod-load.log`, no
`net-dump-final.txt`, and `/etc/rc.d/luofu` stays the vendor's original script. The
vendor's own `hi_kphy` then wins the PHY match.

Evidence: commits `e81b407` and `359ee59`; `mem-entries.md` 2026-11-15 03:30, 04:10,
13:33, 14:36, 14:39, and 16:05. The 3de fire (2026-11-15 13:33) is negative: `C18=0`,
`C94=0`, no `boot.log` or `mod-load.log` in `/overlay/upper`, and the vendor `hi_kphy`
still resident, so the rw-mount fix did not resolve the silent `wfile()`. The 3df
slice (the `wfile()` open() return instrumentation) was fired four times on the broker
lane. Attempts 1-3 failed on lane bugs: a box-side `stat` that does not exist on this
userland, a JSON envelope split by an inner quote, and backslash continuations that
do not survive the device's JSON decode. Attempt 4 (15:29) wrote and verified
`kernelb` and rebooted, but the box booted the stock kernel (`#0 SMP Nov 25 2023`):
`bootcmd` is `mtd read kernel${bootflag} ...`, `bootflag` was `b`, and the stock
vendor userspace still boots its own image from `kernelb`. The audit's `C98` read is
`0x00000000`, the "nothing was written" row, which is exactly what a stock-kernel boot
produces; it is not a mount verdict. The shadow writes are therefore unmeasured, not
negative. Receipt: `build/linux-kbuild/waves/3df/verify.md`.
The same partition is writable from userspace through `/overlay`, so this is a mount
strap, not a code regression. C18 is not a tag cell: the FMC's 5 s tick rewrites it,
so the mount errno was never observable there.

The 3df fire's receipt is `build/linux-kbuild/waves/3df/verify.md`.

What is not the blocker: FMC read and write, UBI, squashfs, overlay assembly, Phase C,
Ethernet, and the watchdog are green or have a working vendor path.

## 4. Next actions

1. The broker lane now writes `/sys/devices/platform/sysenv/boot_reg` (`0x21`) and the
   `C94 0xDEAD0000` word, exactly as `tools/fire-device.sh` always did; that redirect
   is what hands control to the slice. In this session's one fire made before that
   fix, the vendor userspace booted stock from `kernelb` anyway. The next fire must
   require `cat /proc/version` to show our banner, not `#0`, before any cell is read.
2. Read the `wfile-audit.md` section 4.2 verdict under our kernel:
   `/sbin/devmem 0x10100C98 32` alone (`C98` decides), then `/vendor/upper/wfile.log`
   and `dmesg | grep wfile` in separate `--cmd` calls, since a broker reply is cut
   near 400 bytes. Record it in `waves/3df/verify.md` and the ledger.
3. If the writes are still silent under our kernel, go back to the 04:10 plan (mount
   flags and errno, then the `rootfs_data` path). Do not re-run 3dc; its result is in
   the ledger.
4. Keep the Wi-Fi lane (G5) separate. The vendor modules own the radio on our kernel.

## 5. How to run

```sh
tools/check-init-shadow.sh
SLICE="$PWD/build/linux-kbuild/luofu-slice-phase3df.bin" \
  tools/box-provision.sh --bdinfo dumps/router-20261108/bdinfo.bin --stage fire
# 3df has no run script; the tracked generic SSH driver is available when SSH is:
tools/fire.sh ssh --slice "$PWD/build/linux-kbuild/luofu-slice-phase3df.bin" --label 3df --detach
tools/fire.sh verdict
```

The full procedure, including recovery, is in [`RUNBOOK.md`](RUNBOOK.md).

## 6. Evidence

[`EVIDENCE-INDEX.md`](EVIDENCE-INDEX.md) maps each gate and blocker to its artifact.
[`CURRENT-TRUTHS.md`](CURRENT-TRUTHS.md) is the curated summary;
[`mem-entries-INDEX.md`](mem-entries-INDEX.md) is the ledger index. The ledger is
append-only; the latest dated entry wins over any earlier claim.

## 7. History

[`docs/archive/README.md`](docs/archive/README.md). The most relevant retired pages are
`STATE-2026-10-30.md`, `STATUS-2026-11-12.md`, `START-HERE-2026-11-15.md`, and
`PROGRESS-2026-10-15.md`.
