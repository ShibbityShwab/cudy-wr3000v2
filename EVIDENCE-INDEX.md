# Evidence index

Each row is a claim, the artifact that backs it, and whether that artifact is committed
or local-only. A local-only artifact is not a receipt on a fresh clone; regenerate it
with the command in the last column before relying on it.

| claim | artifact | status | regenerate |
| --- | --- | --- | --- |
| Unit is the luofu v2 board, not the MediaTek v1 | `HARDWARE-IDENTITY.md`; `dumps/router-20261108/uboot_capture6.log` | doc committed; capture local | re-read the U-Boot banner and the live DTS compatible |
| UART is output-only; U-Boot cannot be stopped | `HARDWARE-IDENTITY.md`; `build/uart-logs/` | doc committed; logs local | repeat the key-flood test only if the wiring changes |
| G1: FMC reads real flash | `mem-entries.md` 2026-10-30; `dumps/router-20261108/ubi-readpath-report.md` | ledger committed; report local | boot a probe image and read page 0 and `PEB0+0x800` |
| G2: program path is byte-exact | `opensource/docs/phase53-write-path-proof.md`; `mem-entries.md` 2026-11-08 | committed | write a page, read it through the vendor kernel |
| G3: vendor userspace runs on our kernel | `mem-entries.md` 2026-11-13 and 2026-11-14; `build/linux-kbuild/fire-*.log` | ledger committed; logs local | boot a Phase C image and read the kernel-version breadcrumb |
| G4: Ethernet and the vendor stack run on our kernel | `mem-entries.md` 2026-11-14; `opensource/docs/VENDOR-STACK-ON-MAINLINE.md` | committed | load the patched modules and check `eth2`, `br-lan`, and ping |
| G4 clean-room path: MDIO and GEMAC carry 1 Gbps | `mem-entries.md` 2026-11-14 23:15; `tools/lab-src/drivers/net/ethernet/luofu/` | ledger and source committed | build `luofu-mdio`/`luofu-gmac` and read the PHY ID `0x20669a09` |
| G5: Wi-Fi is vendor-only on our kernel | `opensource/docs/phase49/README.md`, `phase49/gic-view.md`; `mem-entries.md` 2026-11-14 | committed | load the lab line and check for a wiphy; there is none yet |
| G6: reset was a userspace watchdog race | `mem-entries.md` 2026-11-13 and 2026-11-14; `STATUS.md` | committed | boot the keeper image and hold the 25-minute timer |
| Current blocker: the box is unreachable after a boot that loaded the vendor stack | `build/uart-logs/20261116T075623Z-3dh-fire.log`; `build/linux-kbuild/fire-dh1.out.log`, `fire-di1.out.log`; `mem-entries.md` 2026-11-16 15:45 | logs local; ledger committed | boot with the patched modules and read the console for what destroys `eth2` |
| 3dk: the init reports every vendor-module load on kmsg | `build/linux-kbuild/waves/3dk/build.md`, `build-3dk.sh`, `waves/3dk/init-extracted` | slice and log local; source in `tools/lab-src/kbuild/init-vendorroot.c` | `build-3dk.sh`, then grep `load hi_` in the UART capture |
| The vendor loader cannot boot our slot A and cannot be prompted | `build/uart-logs/20261116T103014Z-recover-3dk.log`; `dumps/router-20261108/{uboota.bin,enva.bin}`; `HARDWARE-IDENTITY.md` | log and dumps local; ledger committed | read a boot capture for `data abort` after the header, and `bootfip`/`fipupdate_eth` in the U-Boot blob |
| Vendor TFTP recovery is the way back | `build/linux-kbuild/waves/3dk/recovery-3dk.md`; `tftp/recovery.bin` md5 `421114c8ea999c925b7aa79cc548af81` | procedure committed; firmware local | RESET held through power-on, RRQ `recovery.bin` in the TFTP log |
| Broker fire path and the 3de result | `build/linux-kbuild/fire-phase3de-broker*.log`; `/tmp/poll-3de.log`; `build/linux-kbuild/http-fire.log`; `tools/box-provision.sh` | script committed; logs local | `tools/box-provision.sh --stage fire`; the host must allow TCP 8000 from the lab subnet; the box's own `mtd verify` is the receipt |
| Recovery works | `mem-entries.md` 2026-11-12 (RECOVERY); `HARDWARE-IDENTITY.md`; `RUNBOOK.md` | committed | reset-hold plus TFTP, or the broker lane |
| Broker/JWT root channel | `gist-cudy-wr3000v2-mqtt-jwt.md`; `tools/forge_jwt.py`; `tools/mqtt_takeover.py`; `dumps/router-20261108/evidence/` | doc and tools committed; dumps local | forge a token from the bdinfo secret and read the box's response |
| Web-UI RCE sink | `gist-cudy-wr3000v2-systime-rce.md`; `patched/*.lua`; `rpc_inj.json` | committed | replay the JSON-RPC payload against a stock image |
| Register and BAR maps | `opensource/docs/phase4/mmio-map.md`; `phase11/barmap.md`; `phase43/*` | committed | re-run the register dump and diff |
| Vendor modules load on our kernel | `opensource/docs/VENDOR-STACK-ON-MAINLINE.md` | committed | add zero-size `.plt` sections and load in the vendor's order |

Rule: if a claim has only a local artifact, do not present it as a fresh-clone receipt.
Either commit a small reproducible artifact or write the regeneration command into this
table.
