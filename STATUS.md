# STATUS - Cudy WR3000 v2.0

**Updated:** 2026-11-16
**Pins are not written here.** Derive them with `git rev-parse --short HEAD` and
`git -C opensource rev-parse --short HEAD`.
**This is the only live status page.** Regenerate it; do not append to it.

## 1. Bench

- Box: **in a boot loop, and the loop is the whole blocker.** The 17:30 reset exposed it: U-Boot's
  `bootflag` fallback faults on our slot-A image (`data abort` inside U-Boot, after the header,
  `r5=0x834d3bae`), falls to slot B, the stock 4.1 MB kernel starts and panics at 10.8 s on the
  ShuangTa PCIe quirk, and the watchdog resets it. The countdown path that loads slot A correctly
  (`alias console=`, `Uncompressing Linux...`) is only reached when `bootreg` is 0, and the fallback
  sets it to non-zero. Evidence: `build/uart-logs/20261116T103014Z-recover-3dk.log`.
- **The U-Boot prompt is unreachable by serial** (2026-11-08 floods, with and without
  `bootstopkey`; the router-side RX pad never receives, `HARDWARE-IDENTITY.md`), and this loader
  accepts only a FIP package (`bootfip` is `bootcmd`, and `fipupdate_eth` writes both slots with one
  image). So the only way back is the vendor recovery, not a slice.
- Recovery: RESET held through power-on, `recovery.bin` (md5 `421114c8ea999c925b7aa79cc548af81`) over
  TFTP from `192.168.1.88`. Host lane self-tested on UDP 69 and ufw allows it. Procedure:
  `build/linux-kbuild/waves/3dk/recovery-3dk.md`; vendor steps
  (https://www.cudy.com/en-gb/blogs/faq/how-to-recovery-the-cudy-router-from-openwrt-firmware-to-cudy-official-firmware).
  The stock partitions are also degraded (JFFS2 refuses to erase, the squashfs lower returns ECC
  errors), which the recovery fixes in the same pass.
- Access: SSH key `.omo-secrets/router_ed25519`. There is no `.sshwrap/` in this
  checkout. The broker channel is `tools/box-provision.sh` with
  `dumps/router-20261108/bdinfo.bin`.
- Latest build (local-only): `build/linux-kbuild/luofu-slice-phase3dk.bin`
  (3,005,972 bytes, md5 `15d24e455c9ea17ca90e7c9adbfff040`), the 3dj kernel and DTB with an
  init that prints one `load <mod> fd=.. ret=..` kmsg line per vendor module. Rebuild with
  `build/linux-kbuild/build-3dk.sh`. Before it: 3di (15:12), 3dh (14:36, the boot whose
  capture shows `eth2` at 1Gbps) and 3dg (13:50), all fired today without a ledger entry
  until the 15:45 entry.
- Module staging: the vendor modules must carry zero-size `.plt`/`.init.plt`
  (`tools/box-provision.sh --stage lab` pushes the patched set to the overlay upper). The
  3df boot at 05:32 loaded the unpatched set and every module was refused.
- The broker lane is `tools/box-provision.sh --stage fire` and defaults to the newest
  `luofu-slice-phase*.bin`; pass `SLICE=` to pin one. The tracked generic `fire.sh ssh`
  driver covers a fresh clone.

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

**The vendor bootloader cannot boot our slot A and cannot be prompted, so nothing of ours can be
fired until the bootloader is replaced.** The PLT question is settled (3dh loaded the whole vendor
stack and brought `eth2` up at 1Gbps); what blocks the bench now is delivery.

- U-Boot's `bootflag` fallback (`boot from kernela failed, change to kernelb`) prints the image
  header and then faults **inside U-Boot** (`data abort`, `r5=0x834d3bae`). It does this for a
  2.78 MB (3dg) and a 2.96 MB (3di) kernel alike, so size is not the variable.
- The countdown path loads the same kind of image correctly (`alias console=...`,
  `Uncompressing Linux...`) but is only reached when `bootreg` is 0, and the fallback sets it.
- The serial prompt cannot be reached (`HARDWARE-IDENTITY.md`, 2026-11-08), and this loader takes
  only FIP packages (`bootfip` is `bootcmd`; `fipupdate_eth` writes both slots with one image).

Evidence: `build/uart-logs/20261116T103014Z-recover-3dk.log`; the mechanism, the recovery steps and
the way back to the kernel lane are in `build/linux-kbuild/waves/3dk/recovery-3dk.md`.

The 3dh capture below is what the kernel lane looks like once the box can boot again:

```
swa_netdevice_event 215:event:36, name:eth2
[DFX]ETH [3]eth2 phyid:4 1Gbps Full 0x0:1140 0x4:05e1
Hi-GEMAC 14480000.gemac eth2
```

Those modules carried zero-size `.plt`/`.init.plt` sections (`tools/box-provision.sh --stage lab`),
so the loader accepts them and the near-region `module_alloc` never needs a PLT. The same capture
shows procd restarting the network stack (destroy + `Starting TDR` on eth2), which is the open
kernel-side question of why the stack comes down after it loads.

The init's own module-load verdict is on the console: **3dk** emits `<6>load <mod> fd=.. ret=..`
per module (`build/linux-kbuild/waves/3dk/build.md`, slice `luofu-slice-phase3dk.bin` md5
`15d24e455c9ea17ca90e7c9adbfff040`). The 3df slice's module failures at 05:32 were the unpatched
module set, not the loader.

The console works only with the swapped UART pins (`HARDWARE-IDENTITY.md`, 2026-11-16 update), and
captures must write to an absolute path.

## 4. Next actions

1. **Vendor recovery** (`recovery.bin` over TFTP, RESET held through power-on). It is the unlock and
   it also repairs the degraded stock partitions (JFFS2 refuses to erase, the squashfs lower returns
   ECC errors). Host lane is armed and self-tested.
2. Then fire 3dk over SSH and read `load hi_*` lines from the capture.
3. **PCIe quirk / pinctrl node** is the next driver-level item: `hi_pcie` panics unless the pinctrl
   block exposes the named lines (`build/linux-kbuild/waves/3df/pcie-quirk.md`). 3di/3dj were
   property edits and are inert.
4. Keep the Wi-Fi lane (G5) separate. The vendor modules own the radio on our kernel.

### What the 05:32 boot said (history)

The kernel hooks agree in the same boot: `seed test ... wret=0 res=c0def000` and
`overlay test j1=0 j2=0 j3=0 wr=0 res=c0de9d0f`, the success tag with all four status bits.
So the `/vendor` mount is not read-only on this strap and the earlier silence was the stock
userspace winning the boot. Receipt: `build/linux-kbuild/waves/3df/fire7.md` and
`build/uart-logs/20261116T052813Z-fire7-3df.log`.

That boot refused every vendor module (`module PLT section(s) missing`) because its module
set carried no `.plt` sections. The patched set fixes that, and 3dh's capture shows the
result.

## 4. Reading the console
`sudo stty -F /dev/ttyUSB0 115200 cs8 -cstopb -parenb -crtscts raw -echo;
sudo sh -c 'exec 3<>/dev/ttyUSB0; timeout N cat <&3 > /abs/log'`. The adapter only reads
with the swapped pins.

The full procedure, including recovery and the 3dk fire, is in
`build/linux-kbuild/waves/3dk/recovery-3dk.md` and [`RUNBOOK.md`](RUNBOOK.md).
`build-3dk.sh` rebuilds the 3dk slice; `tools/fire.sh ssh --slice ... --label 3dk --detach`
fires it once the vendor slot is up.

## 5. How to run

## 6. Evidence

[`EVIDENCE-INDEX.md`](EVIDENCE-INDEX.md) maps each gate and blocker to its artifact.
[`CURRENT-TRUTHS.md`](CURRENT-TRUTHS.md) is the curated summary;
[`mem-entries-INDEX.md`](mem-entries-INDEX.md) is the ledger index. The ledger is
append-only; the latest dated entry wins over any earlier claim.

## 7. History

[`docs/archive/README.md`](docs/archive/README.md). The most relevant retired pages are
`STATE-2026-10-30.md`, `STATUS-2026-11-12.md`, `START-HERE-2026-11-15.md`, and
`PROGRESS-2026-10-15.md`.
