# STATUS - Cudy WR3000 v2.0

**Updated:** 2026-11-15
**Pins are not written here.** Derive them with `git rev-parse --short HEAD` and
`git -C opensource rev-parse --short HEAD`.
**This is the only live status page.** Regenerate it; do not append to it.

## 1. Bench

- Box: **unreachable since 16:05** (host clock). Last contact 16:04: the stock vendor
  userspace with `bootflag=b` and `boot_reg=21`, `kernelb` holding the 3df slice verified
  byte-exact (`mtd verify` rc 0, 2,766,628 bytes, md5 `9e4015cadd2aa507a1763615b6ac914e`).
  A broker `sync; reboot` was issued at 16:03 to hand control to that slice. Since then the
  box answers no ARP, the host's USB Ethernet keeps carrier with zero received packets,
  and the broker, telnet and SSH ports stay closed. There is no console: the UART RX path
  is dead (J10 pin 3). Recovery is the TFTP path in `RUNBOOK.md` section 6 and needs a
  physical power cycle with RESET held; `tftp/recovery.bin` and `tools/tftp_server.py`
  are present on the host.
- Access: SSH key `.omo-secrets/router_ed25519`. There is no `.sshwrap/` in this
  checkout. The broker channel is `tools/box-provision.sh` with
  `dumps/router-20261108/bdinfo.bin`.
- Latest build (local-only): `build/linux-kbuild/luofu-slice-phase3df.bin`
  (2026-11-15 14:33, 2,766,628 bytes, md5 `9e4015cadd2aa507a1763615b6ac914e`). It
  carries the `wfile()` instrumentation, and that instrument is in the image: the XZ
  kernel stream decompresses to an initramfs whose single `init` is byte-identical to
  the tracked source's current compile. Two broker fires wrote and verified `kernelb`
  (15:29 and 15:52) and the box booted the stock kernel (`#0 SMP Nov 25 2023`) both
  times; the 16:03 reboot after setting `boot_reg` is the first one that could hand
  control to the slice. Fire 6 (19:29) wrote and verified the slice again and set
  `bootflag=b` and `boot_reg=21`, but its own reboot did not run and the box stayed on
  the stock kernel at uptime 46,050 s. A power cycle is what boots the slice now. See
  `build/linux-kbuild/waves/3df/fire6.md` and section 3.
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

**3df is GREEN: the shadow writes land.** Fire 7 (2026-11-16 05:32) is the first 3df boot
captured on a working console. U-Boot printed `bootflag b bootreg 21` and
`Reading 8650752 byte(s)`, so the B slot was read because the handover was set. Our kernel
reached userspace and the 3df init printed all seven verdict lines, every one `OK`:

```
/vendor/upper/etc/rc.d/S10boot OK          /vendor/upper/etc/rc.d/S18hyfibrd OK
/vendor/upper/etc/init.d/luofu OK          /vendor/upper/etc/rc.d/S20network OK
/vendor/upper/etc/rc.d/luofu OK            /vendor/upper/etc/rc.d/S95done OK
/vendor/upper/pstore-check.txt OK
```

The kernel hooks agree in the same boot: `seed test ... wret=0 res=c0def000` and
`overlay test j1=0 j2=0 j3=0 wr=0 res=c0de9d0f`, the success tag with all four status bits.
So the `/vendor` mount is not read-only on this strap and the earlier silence was the stock
userspace winning the boot. Receipt: `build/linux-kbuild/waves/3df/fire7.md` and
`build/uart-logs/20261116T052813Z-fire7-3df.log`.

The blocker is now the **module loader's PLT gate**. Every vendor module fails with
`module PLT section(s) missing`, `hi_kpinctrl` included, so the pins, MDIO and Ethernet
never come up and the boot is unreachable on the LAN even though procd starts. The
console makes each attempt readable now, which is what was missing for the whole file.

The console itself works only with the swapped UART pins (`HARDWARE-IDENTITY.md`,
2026-11-16 update), and captures must write to an absolute path.

## 4. Next actions

1. **PLT module gate.** Userland modules die with `module PLT section(s) missing`
   (`hi_kpinctrl`, `hi_swa`, `hi_kmsgcenter`, `hi_netif`, `gpio-generic`, `gpio-dwapb`,
   `leds-gpio`, `nf_nat_*`). The loader tolerates a missing PLT only under specific build
   conditions; the archived loader notes name the frob tolerance and the `get_module_plt`
   guard. Each attempt is now readable on the console, so bisect against a capture.
2. Read the console for every fire. Capture to an ABSOLUTE path from a root shell:
   `sudo stty -F /dev/ttyUSB0 115200 cs8 -cstopb -parenb -crtscts raw -echo;
   sudo sh -c 'exec 3<>/dev/ttyUSB0; timeout N cat <&3 > /abs/log'`.
   The adapter only reads with the swapped pins.
3. The box currently runs our kernel without networking (`hi_kpinctrl` never loads), so
   recovery is RESET + TFTP (`tftp/recovery.bin`, `tools/tftp_server.py`), proven twice.
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
