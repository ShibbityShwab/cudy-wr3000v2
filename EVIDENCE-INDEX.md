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
| Current blocker: `/vendor` can be read-only | commits `e81b407`, `359ee59`; `mem-entries.md` 2026-11-15 03:30 and 04:10 | committed | fire an image with a kmsg-visible mount and read C18 |
| Recovery works | `mem-entries.md` 2026-11-12 (RECOVERY); `HARDWARE-IDENTITY.md`; `RUNBOOK.md` | committed | reset-hold plus TFTP, or the broker lane |
| Broker/JWT root channel | `gist-cudy-wr3000v2-mqtt-jwt.md`; `tools/forge_jwt.py`; `tools/mqtt_takeover.py`; `dumps/router-20261108/evidence/` | doc and tools committed; dumps local | forge a token from the bdinfo secret and read the box's response |
| Web-UI RCE sink | `gist-cudy-wr3000v2-systime-rce.md`; `patched/*.lua`; `rpc_inj.json` | committed | replay the JSON-RPC payload against a stock image |
| Register and BAR maps | `opensource/docs/phase4/mmio-map.md`; `phase11/barmap.md`; `phase43/*` | committed | re-run the register dump and diff |
| Vendor modules load on our kernel | `opensource/docs/VENDOR-STACK-ON-MAINLINE.md` | committed | add zero-size `.plt` sections and load in the vendor's order |

Rule: if a claim has only a local artifact, do not present it as a fresh-clone receipt.
Either commit a small reproducible artifact or write the regeneration command into this
table.
