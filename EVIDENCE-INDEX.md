# Evidence index

Each row is a claim, the artifact that backs it, and how to regenerate or re-check it.
Artifacts under `build/` and `dumps/` are local-only; a local-only artifact is not a receipt on
a fresh clone, so regenerate it before relying on it. `STATUS.md` is the live state page.

| claim | artifact | status | regenerate |
| --- | --- | --- | --- |
| Unit is the luofu v2 board, not the MediaTek v1 | `HARDWARE-IDENTITY.md`; `dumps/router-20261108/uboot_capture6.log` | doc committed; capture local | re-read the U-Boot banner and the live DTS compatible |
| **UART is read-only** (router TX reaches host with swapped pins; host->router TX dead, burnt resistor) | `HARDWARE-IDENTITY.md`; `BENCH-FACTS.md`; `build/uart-logs/` | committed doc; logs local | read-only marker test with `tools/uart-capture.sh`; **never** a key-flood test |
| Bench link: router eth2 <-> host `enp195s0f3u1`, unmanaged, 192.168.1.88/24 + 192.168.10.44/24 | `BENCH-FACTS.md`; `tools/session-brief.sh` output | doc + tool committed | `tools/bench-link.sh` |
| G1: FMC reads real flash | `mem-entries.md` 2026-10-30; `dumps/router-20261108/ubi-readpath-report.md` | ledger committed; report local | boot a probe image and read page 0 and `PEB0+0x800` |
| G2: program path is byte-exact | `opensource/docs/phase53-write-path-proof.md`; `mem-entries.md` 2026-11-08 | committed | write a page, read it through the vendor kernel |
| G3: vendor userspace runs on our kernel | `mem-entries.md` 2026-11-13/14; `build/linux-kbuild/fire-*.log` | ledger committed; logs local | boot a Phase C image and read the kernel-version breadcrumb |
| G4: Ethernet and the vendor stack run on our kernel | `mem-entries.md` 2026-11-14; `opensource/docs/VENDOR-STACK-ON-MAINLINE.md` | committed | load the patched modules and check `eth2`, `br-lan`, ping |
| G4 clean-room path + M2 caveat: MDIO/GEMAC carry 1 Gbps, but the bound PHY driver is vendor `hi_kphy`, so M2 is NOT met | `mem-entries.md` 2026-11-14 23:15; `tools/lab-src/drivers/net/ethernet/luofu/` | committed | build `luofu-mdio`/`luofu-gmac`, read PHY ID `0x20669a09`, and check which PHY driver bound |
| G5: Wi-Fi is vendor-only on our kernel | `opensource/docs/phase49/README.md`, `phase49/gic-view.md`; `mem-entries.md` 2026-11-14 | committed | load the lab line and check for a wiphy; there is none |
| G6: reset was a userspace watchdog race | `mem-entries.md` 2026-11-13/14; `STATUS.md` | committed | boot the keeper image and hold the 25-minute timer |
| **Blocker: the 3dh-class kernel never starts; 3df/3dg did (2026-11-17 correction)** | booting: `build/uart-logs/20261116T052813Z-fire7-3df.log`, `...T073113Z-3dg2.log` (our `luofu-fmc` banners + init output); non-booting: `...T075623Z-3dh-fire.log`, `...T111510Z-fire-3dk.log` (uImage read, silent reset, only stock `Uncompressing` boots); `mem-entries.md` 2026-11-17 08:00 | logs local; ledger committed | `grep -a 'luofu-fmc 10a20000' <capture>` proves our kernel; `grep -a 'Data Size' <capture>` shows what U-Boot read; the offline payload decodes to a valid 9,810,020-byte Image (3dh) vs 8,135,904 (3df) |
| 3dk: the console-logging init was built and md5-verified, but its `load hi_*` lines were **never observed on hardware** | `build/linux-kbuild/waves/3dk/build.md`, `build-3dk.sh`, `waves/3dk/init-extracted`; ledger 18:25 and 2026-11-17 08:00 | slice and log local; source in `tools/lab-src/kbuild/init-vendorroot.c` | rebuild after the kernel-boot regression is fixed; the 3dk kernel class does not start (see the blocker row) |
| Recovery trigger is the RESET counter on a true power-on reset | `build/uart-logs/20261116T115756Z-recover-stock.log`; ledger 2026-11-16 19:05 | log local; ledger committed | power-off + hold RESET through the counter; log `Resetting...` -> `recovery button press` |
| Vendor TFTP recovery is the way back | `build/linux-kbuild/waves/3dk/recovery-3dk.md` (history); `tftp/recovery.bin` md5 `421114c8ea999c925b7aa79cc548af81`, 20,975,775 B | procedure committed elsewhere; firmware local | `tools/recovery-card.sh`; RRQ `recovery.bin` then `RRQ sent 20975775 bytes` |
| Broker fire path and the 3de result | `build/linux-kbuild/fire-phase3de-broker*.log`; `tools/box-provision.sh` | script committed; logs local | `tools/fire.sh broker --attended` (preflight-gated); the box's own `mtd verify` is the receipt; the lane writes `kernelb` only |
| Broker/JWT root channel | `gist-cudy-wr3000v2-mqtt-jwt.md`; `tools/forge_jwt.py`; `tools/mqtt_takeover.py` | committed | forge a token from the bdinfo secret and read the box's response |
| Web-UI RCE sink | `gist-cudy-wr3000v2-systime-rce.md`; `patched/*.lua`; `rpc_inj.json` | committed | replay the JSON-RPC payload against a stock image |
| Register and BAR maps | `opensource/docs/phase4/mmio-map.md`; `phase11/barmap.md`; `phase43/*` | committed | re-run the register dump and diff |
| Vendor modules load on our kernel | `opensource/docs/VENDOR-STACK-ON-MAINLINE.md` | committed | add zero-size `.plt` sections and load in the vendor's order |
| Vendor GPL obligation is real (58/58 modules report `license=GPL`) | `rootfs-2.5.24/lib/hisilicon/ko` (local); `opensource/docs/GPL-REQUEST.md`; `JETON-GPL-EMAIL.txt` | rootfs local; request doc committed | `strings <mod>.ko \| grep license=` on a local dump; do not publish the modules |
| Upstream submission is not started (no OpenWrt target, DTS, image recipe, or driver series) | `opensource/docs/ROADMAP-OPENWRT.md`; absence of `target/linux/` | committed roadmap; gap audit in ledger 2026-11-17 | `git -C opensource ls-files \| grep -E 'target/linux|image/Makefile'` returns nothing; re-run the gap audit before claiming progress |

## Publish boundary (2026-11-17)

The root repo is private research material and must not be published until cleaned:

- `patched/*.lua` are de-crypted vendor LuCI files; `dumps/`, `firmware/`, `rootfs-*/`,
  `build/` are vendor-derived or local evidence (gitignored).
- `tools/vendor-mods/*.ko` were untracked on 2026-11-17 (vendor GPL object code). Keep them as
  local fixtures only.
- The published `opensource/` half still contains 10 tracked vendor `.o` files from the
  TR6560 BSP under `lab/luofu-kernel/nand/`; removing them from the working tree is done, but
  they remain in the published history. **History rewrite/purge is required before making the
  half public.** See `opensource/NOTICE.md` and `opensource/README.md`.

Rule: if a claim has only a local artifact, do not present it as a fresh-clone receipt. Either
commit a small reproducible artifact or write the regeneration command into this table.
