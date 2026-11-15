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
- Latest build (local-only): `build/linux-kbuild/luofu-slice-phase3de.bin`
  (2026-11-15 11:49), assembled one minute after the init/cpio rebuild (11:48:55).
  No fire log and no ledger entry for `phase3de` exists, so it is built but
  unverified. Rebuild and compare before treating it as a receipt.
- The latest SSH fire script (local-only) is `build/linux-kbuild/run-phase3dc.sh`;
  3dd and 3de have slices but no run scripts. The broker lane is
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

Evidence: commits `e81b407` and `359ee59`; `mem-entries.md` 2026-11-15 03:30 and 04:10.
The same partition is writable from userspace through `/overlay`, so this is a mount
strap, not a code regression. The 2026-11-15 04:10 entry names the fix: mount jffs2 with
the `rw` data option, check the result, and remount `rw` if needed. The mount errno is
tagged into C18. The 3de slice was assembled after that change (init/cpio
11:48:55, zImage/slice 11:49:01) and has not been fired. Rebuild and compare
before treating it as a receipt.

What is not the blocker: FMC read and write, UBI, squashfs, overlay assembly, Phase C,
Ethernet, and the watchdog are green or have a working vendor path.

## 4. Next actions

1. Fire the 3de slice through the broker or a fresh SSH run script. Read C18 (mount
   errno) and C94 (verdict), then check `/vendor/upper` for `boot.log` and
   `mod-load.log`. `tools/check-init-shadow.sh` must print PASS first.
2. If the mount is still read-only, instrument the mount flags and errno, and try the
   `rootfs_data` path. Do not re-run 3dc; its result is already in the ledger.
3. Keep the Wi-Fi lane (G5) separate. The vendor modules own the radio on our kernel.

## 5. How to run

```sh
tools/check-init-shadow.sh
SLICE="$PWD/build/linux-kbuild/luofu-slice-phase3de.bin" \
  tools/box-provision.sh --bdinfo dumps/router-20261108/bdinfo.bin --stage fire
# 3de has no run script; the tracked generic SSH driver is available when SSH is:
tools/fire.sh ssh --slice "$PWD/build/linux-kbuild/luofu-slice-phase3de.bin" --label 3de --detach
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
