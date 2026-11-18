# STATUS - Cudy WR3000 v2.0

**Updated:** 2026-11-18 07:40 +07
**Pins are not written here.** Derive them with `git rev-parse --short HEAD` and
`git -C opensource rev-parse --short HEAD`.
**This is the only live status page.** Regenerate it; do not append to it. The physical
invariants live in `BENCH-FACTS.md`; the procedure is `RUNBOOK.md`.

## 1. Bench (re-verified read-only 2026-11-18 07:35 +07)

- **Box: vendor stock, healthy, idle.** Vendor OpenWrt 22.03.6, stock kernel
  `5.10.201 #0 SMP Sat Nov 25 18:18:57 2023`, uptime ~39 min, `bootflag=a`, both kernel slots
  restored to the stock image (md5 `b553da8ea24b38cb1e796b6a6430ccf7`), 2 wiphys, SSH on the
  project key. Bench fires are **stopped**; UART capture is stopped after teardown.
- **Host bench link:** `enp195s0f3u1` UP at 1 Gbps, NetworkManager-unmanaged, carrying
  `192.168.1.88/24` and `192.168.10.44/24`. Re-applied with `tools/bench-link.sh --apply`
  this morning after NetworkManager re-managed the adapter overnight; PASS at 07:20.
- **Recovery door: READY host-side, physical trigger.** TFTP is listening on UDP 69 and
  `tftp/recovery.bin` matches md5 `421114c8ea999c925b7aa79cc548af81`; the trigger remains the
  physical RESET counter on a true power-on reset (`BENCH-FACTS.md` section 4).
- **UART: READ-ONLY.** `/dev/ttyUSB0` (FT232R, 115200 8N1); host-to-router TX is dead (burnt
  resistor) and must never be attempted. Capture with `tools/uart-capture.sh` only; it now
  restarts `cat` on USB-serial EIO and kills its process group on stop.
- **Latest fired slice (local only, NOT a release):**
  `build/linux-kbuild/luofu-slice-phase3dq.bin` v17 = 2,906,100 B, md5
  `8342ccb9c0167766529277719330f43c` (zImage `a08ffc66`, init `74033a38`, DTB
  `336ba39e`, 59 patched modules staged for that run). Rebuild with
  `build/linux-kbuild/build-3dq.sh`.
- **Guards:** `tools/check-init-shadow.sh` PASS; `tools/check-lab-src.sh` PASS (43 modified
  source files); `tools/check-repo.sh` PASS before this page was regenerated. These are
  source-level guards, not artifact proofs.

## 2. Gates (bench-reversal history, 2026-11-14)

| gate | state | receipt |
| --- | --- | --- |
| **G1** FMC reads real flash | GREEN | page-0 magic `UBI#`; level-7 MTD probe found the partition, the EC magic, `vid_hdr_offset = 0x800`, and `PEB0+0x800 = 'U'` |
| **G2** program path | GREEN | a page written by our kernel read back byte-exact through the vendor driver |
| **G3** our kernel + real rootfs + userspace | GREEN 2026-11-14 | vendor preinit, `mount_root`, procd and the full rc.d chain run on our kernel from the squashfs root |
| **G4** Ethernet on our kernel | GREEN via vendor modules | vendor switch/MDIO/PHY/MAC modules load as patched modules; `eth2` up 1 Gbps, `br-lan` 192.168.10.1, ping 3/3 on the 2026-11-14 stack. Our `luofu-mdio`/`luofu-gmac` also carry a link, but **M2 ("no vendor network modules") is NOT met** |
| **G5** Wi-Fi on our kernel | vendor-only | the vendor modules provide the radio; no wiphy from our driver |
| **G6** sustained uptime | GREEN 2026-11-14 | the reset was a userspace watchdog race, not a panic; the initramfs keeper holds the 25-minute timer |

These are bench-reversal gates. They are **not** upstream artifacts; see section 5.

## 3. Current state: bench line at its documented ceiling; the upstream design docs now exist

**Bench lab-kernel line (v6-v17, 2026-11-17/18):** our kernel boots the vendor userspace, the full
vendor module stack loads (`ret=0`, including `hi_kpie`, `hi_swa`, the `hi_lsw_*`/`hi_kcfe_*`
chain, `hi_netif`/`hi_kmsgcenter`/`hi_kipc`), eth2 comes up at 1 Gbps and `br-lan` is created.
v17 removed the HYFI crash (no hyfi preload, ABI-correct bridge hook pointer variables) but HSLINK
then created/destroyed `br-lan` in a loop and userspace went silent; the vendor HYFI/bridge
contract needs the vendor `sk_buff` ABI (+0x74/+0x78) and the vendor bridge patches (hook call
sites, `net_bridge` cache), i.e. a multi-step port. The full evidence trail is in
`EVIDENCE-INDEX.md` and the ledger entries 2026-11-17 08:45/10:15/18:00/18:55/20:15/20:40 and
2026-11-18 06:50.

**Upstream track (2026-11-18):** the missing design layer now exists, but there is still **no
OpenWrt target, board DTS, image recipe, driver series or upstream submission**.

- `opensource/docs/TARGET-DESIGN.md` - concrete design: `target/linux/hisilicon` + `luofu`
  subtarget, FIP trailer/dual-slot/sysupgrade recipe, DTS conversion plan, per-driver upstream
  readiness, acceptance criteria.
- `opensource/docs/ROADMAP-OPENWRT.md` - refreshed to the 2026-11-18 reality (phase plan +
  status notes; superseded claims point at the ledger).
- `opensource/docs/GPL-REQUEST.md` - status 2026-11-18: original request sent 2026-10-01, still
  no reply or evidence copy; ready-to-send follow-up, escalation ladder, tracking table and an
  updated requested-artifacts checklist.
- `opensource/docs/VENDOR-SKB-BRIDGE-PORT.md` - feasibility/design spec for the optional hybrid
  vendor HYFI/bridge lane (ABI deltas, options, offset probe, staged fires, acceptance criteria).
- `opensource/docs/DOCUMENTATION-HUNT.md` - refreshed open-gaps table.
- `opensource/target-skeleton/` + `opensource/docs/TARGET-SKELETON.md` - target files from the
  design (target/linux/hisilicon/luofu Makefiles/Kconfig/profile/board.d, a draft DTS, the
  `fip-slice.py` tool, **and a kernel platform patch series**). Status: **structure + kernel-config
  validated, not compiled into a correct image** - copied into OpenWrt `main` (commit `27663a0`):
  `make defconfig` PASS, `make target/linux/prepare` RC=0 (kernel 6.18.60); patches-6.18/ adds
  arch/arm/mach-hisilicon (clean UP-only machine descriptor, ARCH_LUOFU via the existing
  ARCH_HISI) + Kconfig/textofs; `config-6.18` was canonically re-derived (281-symbol delta,
  idempotent) with the tree's own GCC 14.4 toolchain and the machine code compiles with it. Patch `003` fixes the last compile blocker
  (`TEXT_OFFSET=0x00608000` is not an ARM rotated immediate) with the kernel's own `mov_l`
  idiom, and **`make target/linux/compile` now reaches RC=0** with the real offset, no
  workarounds: zImage produced (local-only evidence, sha256 `45ad00d5...`), linked/load
  address verified as `0x80608000` (mkimage `-a/-e 0x80608000`). This is still **not a
  deliverable image**: no FIP slice, rootfs, target image, dtbs_check or boot
  (`opensource/docs/SKELETON-SMOKE.md`).
- **FIP trailer decoded and generation implemented (2026-11-18, offline):** U-Boot `bootfip`
  fully decoded (gate, 96-byte descriptor, 11-row vendor/board match table, applier validation
  order; uImage CRCs are not checked). `target-skeleton/tools/fip-slice.py make-trailer` now
  generates a fail-closed trailer from user-supplied base DTB + overlays and reproduces the vendor
  2.4.15 (40,828 B) and 2.5.24 containers byte-for-byte; the bench lane still copies its fixed
  40,732-byte artifact. A novel generated trailer still needs **one attended boot**.
  Details: `opensource/target-skeleton/docs/TRAILER-FORMAT.md`.

- **First own-artifact FIP kernel slice assembled and structurally validated (2026-11-18, host-only).**
  `target-skeleton/tools/build-kernel-slice.sh` compiles our draft DTB + a loader-match stub
  overlay (`vendor_id=hsan`, `hsan-luofu`, `board_id=3`, no-op fragment), builds the uImage
  (`-a/-e 0x80608000`, `Linux-6.18.60`), generates a 9,278 B trailer with `fip-slice.py
  make-trailer`, assembles the slice and validates it: size 3,214,542 B, gate `0xd7b7ab1e` at
  `0x310ba8`, 5,436,210 B under the slot limit, reproducible byte-for-byte. This is **not a
  deliverable image and has never been booted**; the bench fire preflight still expects the fixed
  40,732-byte vendor trailer, so adopting this lane needs one attended boot plus preflight/recipe
  updates. Details: `opensource/docs/SKELETON-SMOKE.md` (2026-11-18 slice section).

The published half is **NOT READY** for publication (`opensource/docs/PUBLISH-READINESS.md`:
vendor `.o` files remain in git history; history purge pending). Do not present it as
submission-ready.

## 4. Next action

1. **Send the GPL follow-up** (human action): the letter is ready in `opensource/docs/GPL-REQUEST.md`;
   record the sent copy, `To:` header and receipt in the repo so the evidence gap closes.
2. **Fix `TEXT_OFFSET` and complete the kernel/image build** (host-side): write the clean
   early-boot assembly patch for `TEXT_OFFSET=0x00608000` (four sites in
   `arch/arm/kernel/head.S`/`arch/arm/boot/compressed/head.S`; alternative: pick an encodable
   offset and update the load-address assertions), then wire the custom image chain
   (`luofu-uimage` -> `fip-slice assemble` with the now-decoded trailer generator ->
   `fip-manifest` -> UBI -> sysupgrade), resolve the board compatible mismatch
   (`cudy,wr3000-v2` vs `hisilicon,luofu-r116`), the watchdog/CRG same-page unit-address
   collision, and `platform.sh`/install. Then `dtbs_check`/build. The first generated-trailer
   boot is a bench step and must be attended.
3. **Consolidate the reversal evidence**: EVIDENCE-INDEX rows for the v6-v17 line, publish-readiness
   purge plan, and the reversal report.
4. **Optional, only if resumed:** the vendor `sk_buff`/bridge/HYFI port strictly per
   `VENDOR-SKB-BRIDGE-PORT.md` - E0 host probe first, no bench fires before that. Bench fires stay
   stopped until then.

## 5. Reading the console (read-only)

```sh
tools/uart-capture.sh start --label <label> --timeout 900   # detached, absolute log path
tools/uart-capture.sh check
```

The script opens the tty read-only and never sends bytes. Do not use a read-write open of the tty
(the `3<>` form), `screen`, `minicom`, or a typed key: host-to-router TX is dead and must not be
attempted. A capture is evidence only when the log line that identifies the image is quoted
(uImage `Data Size`/`Image Name`, or `Uncompressing Linux` for stock).

## 6. Evidence

[`EVIDENCE-INDEX.md`](EVIDENCE-INDEX.md) maps claims to artifacts and regeneration commands.
[`CURRENT-TRUTHS.md`](CURRENT-TRUTHS.md) is the curated summary; the ledger
(`mem-entries.md`, index in `mem-entries-INDEX.md`) is the long form. The newest dated
entry wins over any older claim.

## 7. History

[`docs/archive/README.md`](docs/archive/README.md). Retired pages include
`STATE-2026-10-30.md`, `STATUS-2026-11-12.md`, `START-HERE-2026-11-15.md`, and
`PROGRESS-2026-10-15.md`.
