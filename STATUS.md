# STATUS - Cudy WR3000 v2.0

**Updated:** 2026-11-16
**Pins are not written here.** Derive them with `git rev-parse --short HEAD` and
`git -C opensource rev-parse --short HEAD`.
**This is the only live status page.** Regenerate it; do not append to it.

## 1. Bench

- Box: **unreachable since 15:39** (host clock). 3di's fire reached the write/verify/vendor
  return and then died with `Connection reset by 192.168.10.1 port 22`; since then no ping,
  the MQTT broker raises `OSError 113 No route to host`, and the host's USB Ethernet keeps
  carrier with no peer. The console adapter is present (`/dev/ttyUSB0`) and reads only with
  the swapped pins, so a boot can be captured, but every fire needs the RESET + TFTP
  recovery in `RUNBOOK.md` section 6 (`tftp/recovery.bin`, `tools/tftp_server.py`).
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

**The PLT gate is bypassed on this board; the open item is which boot reaches the LAN.**

The 3df block below described the 05:32 boot and is kept as history. On the same kernel two
later boots tell a different story: the **3dh** capture
(`build/uart-logs/20261116T075623Z-3dh-fire.log`) shows the vendor stack loaded and running:

```
swa_netdevice_event 215:event:36, name:eth2
[DFX]ETH [3]eth2 phyid:4 1Gbps Full 0x0:1140 0x4:05e1
Hi-GEMAC 14480000.gemac eth2
```

Those modules carried zero-size `.plt`/`.init.plt` sections (`tools/box-provision.sh
--stage lab`), so the loader accepts them and the near-region `module_alloc` never needs a
PLT. The same capture shows procd restarting the network stack (destroy + `Starting TDR` on
eth2), and the box was unreachable after each of today's fires (3dg `VENDOR_DID_NOT_RETURN`,
3dh SSH dropped, 3di SSH reset). So the live question is why the stack comes down after it
loads, not whether it loads.

The init's own module-load verdict is now on the console: **3dk** emits `<6>load <mod>
fd=.. ret=..` per module (`build/linux-kbuild/waves/3dk/build.md`, slice
`luofu-slice-phase3dk.bin` md5 `15d24e455c9ea17ca90e7c9adbfff040`). The 3df slice's module
failure at 05:32 was the unpatched module set, not the loader.

The console itself works only with the swapped UART pins (`HARDWARE-IDENTITY.md`,
2026-11-16 update), and captures must write to an absolute path.

## 4. Next actions

1. **3dk read: `load hi_*` lines from a console capture.** `ret=0` on `hi_kpinctrl` and the
   chain confirms the loader path end to end; a negative value names the errno. Then read the
   same capture for what drops eth2 (devlink/eth restart, `hi_swa` destroy, watchdog).
2. Recovery first: the box is unreachable, so a fire needs RESET + TFTP (`RUNBOOK.md` section
   6, `tftp/recovery.bin`, `tools/tftp_server.py`), proven twice today.
3. **PCIe quirk / pinctrl node** is the next driver-level item if a 3dk boot shows the stack
   loading: `hi_pcie` panics unless the pinctrl block exposes the named lines
   (`build/linux-kbuild/waves/3df/pcie-quirk.md`). 3di/3dj were property edits and are inert.
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

Capture to an ABSOLUTE path from a root shell:
`sudo stty -F /dev/ttyUSB0 115200 cs8 -cstopb -parenb -crtscts raw -echo;
sudo sh -c 'exec 3<>/dev/ttyUSB0; timeout N cat <&3 > /abs/log'`. The adapter only reads
with the swapped pins.

## 5. How to run

The full procedure, including recovery, is in [`RUNBOOK.md`](RUNBOOK.md). `build-3dk.sh`
rebuilds the 3dk slice; `tools/fire.sh ssh --slice ... --label 3dk --detach` fires it when
the vendor slot is up, otherwise `tools/box-provision.sh --stage fire` after a TFTP recovery.

## 6. Evidence

[`EVIDENCE-INDEX.md`](EVIDENCE-INDEX.md) maps each gate and blocker to its artifact.
[`CURRENT-TRUTHS.md`](CURRENT-TRUTHS.md) is the curated summary;
[`mem-entries-INDEX.md`](mem-entries-INDEX.md) is the ledger index. The ledger is
append-only; the latest dated entry wins over any earlier claim.

## 7. History

[`docs/archive/README.md`](docs/archive/README.md). The most relevant retired pages are
`STATE-2026-10-30.md`, `STATUS-2026-11-12.md`, `START-HERE-2026-11-15.md`, and
`PROGRESS-2026-10-15.md`.
