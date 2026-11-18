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
| 3dk: the console-logging init was built and md5-verified, but its `load hi_*` lines were **never observed on hardware** | `build/linux-kbuild/waves/3dk/build.md`, `build-3dk.sh`, `waves/3dk/init-extracted`; ledger 18:25 and 2026-11-17 08:00 | slice and log local; source in `tools/lab-src/kbuild/init-vendorroot.c` | **SUPERSEDED 2026-11-17**: the 3dh-class root cause was captured and fixed (`luofu_early` ioremap before `mm_init`, commit `0f8044e`); the fixed `3dn` slice booted on hardware and later builds repeated it (ledger 2026-11-17 08:45; capture `build/uart-logs/20261117T012608Z-uart-3dn.log`) |
| Recovery trigger is the RESET counter on a true power-on reset | `build/uart-logs/20261116T115756Z-recover-stock.log`; ledger 2026-11-16 19:05 | log local; ledger committed | power-off + hold RESET through the counter; log `Resetting...` -> `recovery button press` |
| Vendor TFTP recovery is the way back | `build/linux-kbuild/waves/3dk/recovery-3dk.md` (history); `tftp/recovery.bin` md5 `421114c8ea999c925b7aa79cc548af81`, 20,975,775 B | procedure committed elsewhere; firmware local | `tools/recovery-card.sh`; RRQ `recovery.bin` then `RRQ sent 20975775 bytes` |
| Broker fire path and the 3de result | `build/linux-kbuild/fire-phase3de-broker*.log`; `tools/box-provision.sh` | script committed; logs local | `tools/fire.sh broker --attended` (preflight-gated); the box's own `mtd verify` is the receipt; the lane writes `kernelb` only |
| Broker/JWT root channel | `gist-cudy-wr3000v2-mqtt-jwt.md`; `tools/forge_jwt.py`; `tools/mqtt_takeover.py` | committed | forge a token from the bdinfo secret and read the box's response |
| Web-UI RCE sink | `gist-cudy-wr3000v2-systime-rce.md`; `patched/*.lua`; `rpc_inj.json` | committed | replay the JSON-RPC payload against a stock image |
| Register and BAR maps | `opensource/docs/phase4/mmio-map.md`; `phase11/barmap.md`; `phase43/*` | committed | re-run the register dump and diff |
| Vendor modules load on our kernel | `opensource/docs/VENDOR-STACK-ON-MAINLINE.md` | committed | add zero-size `.plt` sections and load in the vendor's order |
| Vendor GPL obligation is real (58/58 modules report `license=GPL`) | `rootfs-2.5.24/lib/hisilicon/ko` (local); `opensource/docs/GPL-REQUEST.md`; `JETON-GPL-EMAIL.txt` | rootfs local; request doc committed | `strings <mod>.ko \| grep license=` on a local dump; do not publish the modules |
| Upstream submission has a concrete design doc but still **no target/DTS/image recipe/driver series** | `opensource/docs/TARGET-DESIGN.md`; `opensource/docs/ROADMAP-OPENWRT.md`; absence of `target/linux/` | design docs committed in the opensource submodule 2026-11-18; no code tree | `ls opensource/docs/TARGET-DESIGN.md`; `git -C opensource ls-files \| grep -E 'target/linux|image/Makefile'` returns nothing - do not claim upstream progress without an image + reviewable DTS |
| The upstream target skeleton's **structure** was accepted by OpenWrt main, but nothing was compiled/imaged/booted | `opensource/target-skeleton/`; `opensource/docs/SKELETON-SMOKE.md`; `opensource/docs/TARGET-SKELETON.md` | files committed 2026-11-18; clone `openwrt main` `27663a0`: `make defconfig` PASS with `CONFIG_TARGET_hisilicon_luofu_DEVICE_cudy_wr3000-v2=y`, `make target/linux/prepare` RC=0 (kernel 6.18.60); no compile/image/boot | reproduce per SKELETON-SMOKE.md; a real build needs the kernel platform patch + image-chain wiring |
| Kernel platform patch series applies; canonical 6.18 config derives idempotently; **full kernel compile reaches RC=0 with the real TEXT_OFFSET and correct load address** | `opensource/target-skeleton/target/linux/hisilicon/patches-6.18/` (001/002/003); `.../luofu/config-6.18`; `opensource/docs/SKELETON-SMOKE.md` (later-session section) | patches committed 2026-11-18 (sha256 996bf896.../278bb1a0.../407352b8...); OpenWrt clone `27663a0` + linux-6.18.60, GCC 14.4.0: prepare RC=0, kernel_oldconfig RC=0 twice byte-identical, `make target/linux/compile` RC=0, zImage sha256 `45ad00d5...`, load/entry verified `0x80608000`; local evidence `build/linux-kbuild/waves/upstream-6.18-{patches,textoffset}-20261118/` | re-run SKELETON-SMOKE commands; this is an intermediate compile product, **not an image/boot evidence** |
| First own-artifact FIP kernel slice assembled and structurally validated (never booted) | `opensource/target-skeleton/tools/build-kernel-slice.sh`; `opensource/target-skeleton/dts/luofu-r116-overlay.dts`; `opensource/docs/SKELETON-SMOKE.md` (slice section); local evidence `build/linux-kbuild/waves/upstream-6.18-slice-20261118/` | script+overlay committed 2026-11-18; slice 3,214,542 B sha256 `3311a3e5...`, trailer 9,278 B, gate at `0x310ba8`, run1/run2 byte-identical, independent dtc/fdtget/fdtoverlay re-checks; no vendor inputs | run `opensource/target-skeleton/tools/build-kernel-slice.sh --out <dir>` from a clone with the compiled 6.18 kernel; a stock loader accepting a novel trailer still requires one attended boot |
| FIP trailer format decoded; `make-trailer` reproduces both vendor containers byte-for-byte | `opensource/target-skeleton/docs/TRAILER-FORMAT.md`; `opensource/target-skeleton/tools/fip-slice.py`; local-only artifacts `dumps/router-20261108/uboot{a,b}.bin`, `build/linux-kbuild/slice-trailer-40732.bin`, vendor firmware images | docs+tool committed 2026-11-18; offline tests: `check-trailer` on the local 40,732 B trailer; `make-trailer` from split local base+overlays equals the local trailer + 96 zero bytes (40,828 B); negatives fail closed | rebuild the positive test by splitting the local trailer (base 31220, ov1 4592, ov2 padded to 4920) and diffing; one attended boot of a novel trailer still required |
| GPL follow-up is drafted and ready to send; the 2026-10-01 request has no reply or evidence copy | `opensource/docs/GPL-REQUEST.md` (status block, tracking table, follow-up letter, escalation ladder) | docs committed 2026-11-18; the sent copy/receipt is the open evidence gap | read the tracking table; after sending, save the sent message + receipt in the repo |
| The vendor sk_buff/bridge port has a concrete feasibility spec but is not attempted | `opensource/docs/VENDOR-SKB-BRIDGE-PORT.md`; `opensource/docs/TARGET-DESIGN.md` | docs committed 2026-11-18; no code | the spec names the ABI deltas and a host-first E0 probe; do not fire before that probe exists |
| Bench lab-kernel line (v6-v17) supports the reversal report but is not an upstream artifact | `EVIDENCE-INDEX.md` section "Bench kernel line, 2026-11-17/18"; captures under `build/uart-logs/` (local) | this page; slices local under `build/linux-kbuild/` | read the section below; rebuild via `build-3dq.sh`, do not publish vendor artifacts |

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

## Bench kernel line, 2026-11-17/18 (v6-v17): reversal evidence

- Slices (root repo, gitignored artifacts): build/linux-kbuild/luofu-slice-phase3dq.bin
  v6/7/8 booted to userspace; v13/v14 WEXT+bridge experiments; v17 final = md5
  8342ccb9c0167766529277719330f43c (zImage a08ffc66, init 74033a38, DTB 336ba39e).
- Console captures (root repo, gitignored): build/uart-logs/20261117T031025Z-uart-3dq.log
  (first vendor-module chain), 20261117T100902Z-uart-3dq8.log (PAN + WEXT era),
  20261117T115050Z-uart-3dq13.log (bridge configs, v14-v16), 20261117T233458Z-uart-v17.log
  (final: br-lan create/destroy loop, no crash).
- Durable findings: 3dh kernel crash root cause (luofu_early ioremap before mm_init);
  post-procd RCU stall = TRACING block; vendor module dependency graph (ksecurec -> hi_basic ->
  hi_kpie -> lsw/kcfe/khslink/swa); WEXT net_device ABI (+8 field shift); vendor sk_buff ABI
  (+0x74/+0x78, skb->data 0x118 vs 0xa0); rootif = /proc/hsan/net/swa/wan_port -> hi_cfe_add_rootif
  -> hi_net_get_port (needs hi_net_dev_probe registration by hi_kmac); br_* are exported pointer
  variables in the vendor bridge, not functions.
- RE reports: subagent sessions held the disassembly results; the committed ledger entries
  2026-11-17 18:00/18:55, 2026-11-17 20:40 and 2026-11-18 06:50 summarize them.
