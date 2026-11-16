# STATUS - Cudy WR3000 v2.0

**Updated:** 2026-11-16
**Pins are not written here.** Derive them with `git rev-parse --short HEAD` and
`git -C opensource rev-parse --short HEAD`.
**This is the only live status page.** Regenerate it; do not append to it.

## 1. Bench

- Box: **on vendor stock, healthy.** OpenWrt 22.03.6 revision 2.4.15, stock kernel
  `5.10.201 #0 SMP Sat Nov 25 18:18:57 2023`, 40 `hi_` modules, 2 wiphys (`phy0`, `phy1`), both
  bands' calibration loaded and written (`hwifi_rf_cali_file_load_{2g,5g} succ`), `192.168.10.1`
  answering, SSH working on the project key. Restored 19:05 by the vendor TFTP recovery; see the
  19:05 ledger entry.
- **Recovery trigger (correction): the RESET counter.** The loader prints
  `RESET button is pressed for: 0/1/2 second(s)`, `Resetting...`, and only then, after the
  countdown, `recovery button press` and the TFTP client. A plain hold that is released early leaves
  it at `0 second(s)` and the box boots normally. The counter appears only on a true power-on reset.
- **Host lane gotcha: NetworkManager strips the bench port's addresses.** `enp195s0f3u1` must be
  `nmcli device set enp195s0f3u1 managed no`, then `ip addr add 192.168.1.88/24` and
  `192.168.10.44/24`. Without it the board's ARP for the server is unanswered
  (`ARP Retry count exceeded`).
- Access: SSH key `.omo-secrets/router_ed25519`; after any recovery, install the key again and start
  dropbear with `-R` after deleting the zero-byte host keys. The broker channel is
  `tools/box-provision.sh` with `dumps/router-20261108/bdinfo.bin`.
- Latest build (local-only, NOT fired): `build/linux-kbuild/luofu-slice-phase3dl.bin`
  (3,005,396 bytes, md5 `f7b2eb41a074df9fd6017e6179a446b0`): the 3dh device tree
  (`336ba39e...`) with the console-logging init (`6464a08d...`). Rebuild with
  `build/linux-kbuild/build-3dl.sh`, which refuses to run unless the DTB is the 3dh blob.
- 3dk (3,005,972, the same init on the 3di/3dj PCIe DTB) was fired and the fire wrote `kernelb`
  while the bootable slot is the AB one, so nothing about our kernel was learned from it
  (18:25 ledger entry).
- Module staging: the vendor modules must carry zero-size `.plt`/`.init.plt`
  (`tools/box-provision.sh --stage lab` pushes the patched set to the overlay upper; a recovery
  empties the overlay, so stage again after one). The 3df boot at 05:32 loaded the unpatched set and
  every module was refused.
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

**Delivery, not the kernel.** The PLT question is settled (3dh loaded the whole vendor stack and
brought `eth2` up at 1Gbps). What blocks the bench is that a fire writes `kernelb` while the slot
U-Boot boots cleanly on this board is the AB one.

- `tools/fire-device.sh` writes `kernelb` and sets `bootflag=b`. The 3dk fire verified that write
  and the console then reset on the handover under the hardware watchdog, never running the slice;
  every kernel that started in that capture was the stock 4.1 MB image. **A fire has to target the
  slot the countdown path uses, and the capture has to show `Uncompressing Linux` for our image
  before anything is concluded from it.**
- U-Boot's `bootflag` fallback (`boot from kernela failed, change to kernelb`) prints the image
  header and then faults **inside U-Boot** (`data abort`, `r5=0x834d3bae`), for a 2.78 MB and a
  2.96 MB kernel alike.
- The serial prompt cannot be reached (`HARDWARE-IDENTITY.md`, 2026-11-08), and this loader takes
  only FIP packages (`bootfip` is `bootcmd`). The way back after a bad fire is the vendor recovery
  (section 1).

Evidence: `build/uart-logs/20261116T111510Z-fire-3dk.log`; mechanism and recovery steps in
`build/linux-kbuild/waves/3dk/recovery-3dk.md`.

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

1. **Write 3dl to the slot U-Boot boots** (`/dev/mtd11` `kernela`, not `kernelb`), then read
   `load hi_*` from the console. That is the single-variable test: 3dh's kernel and DTB, the
   console-logging init as the only delta. Before staging, re-push the patched modules
   (`tools/box-provision.sh --stage lab`), because the restore emptied the overlay upper.
2. The vendor recovery is the way back whenever a fire leaves the box unreachable; the trigger is
   the RESET counter, not a short hold (section 1), and the host port must be unmanaged with
   `192.168.1.88` on it.
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
