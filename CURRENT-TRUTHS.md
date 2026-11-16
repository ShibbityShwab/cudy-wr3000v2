# Current truths (2026-11-17)

Curated summary. `STATUS.md` is the only live status page and wins over this file; the
ledger is the long form and the newest dated entry wins. Physical invariants: `BENCH-FACTS.md`.

- **UART is READ-ONLY.** Router console output reaches the host with the swapped pins; the
  host-to-router TX path is dead (burnt resistor). Never transmit: no typing, no
  a read-write tty open (`3<>`), no key floods. Capture read-only with
  `tools/uart-capture.sh`.
- **Bench link:** router LAN port `eth2` is cabled to host USB-Ethernet `enp195s0f3u1`.
  Keep it NetworkManager-unmanaged with `192.168.1.88/24` (TFTP recovery) and
  `192.168.10.44/24` (vendor LAN), or the board's ARP fails. `tools/bench-link.sh`.
- **Recovery is physical:** power-off, hold RESET through the counter
  (`0/1/2 second(s)` -> `Resetting...` -> `recovery button press`), then TFTP
  `recovery.bin` from `192.168.1.88`. An agent cannot do it alone; every fire is
  human-attended with the recovery door armed.
- **Box state (2026-11-16 23:52):** vendor stock 22.03.6 rev 2.4.15, kernel 5.10.201,
  2 wiphys, calibration `[SUCC]` both bands, SSH on the project key, `bootflag=b`,
  `boot_reg=0x11`, no `.omo-off`. The stale broker HTTP server was stopped.
- **Gates G1-G4/G6** are green on the bench (2026-11-14). G4 is met by the vendor's modules;
  the bound PHY driver is `hi_kphy`, so M2 ("no vendor network modules") is not met.
  G5 (Wi-Fi) is vendor-only.
- **The delivery lane is unresolved.** U-Boot reads our uImage (`Data Size` 2,964,240 /
  2,965,176, `Image Name: Linux-5.10.201`) but no kernel output follows; every
  `Uncompressing Linux` in the captures is the stock 4,294,096-byte fallback image.
  `luofu-slice-phase3dl.bin` is built (md5 `f7b2eb41...`) and NOT fired. Do not fire until
  `STATUS.md` section 4 names the delivery plan.
- **Validity markers:** ours is an uncompressed uImage and does not print
  `Uncompressing Linux`; stock does. A fire is valid only when our uImage identity and our
  kernel output are in the capture (`LESSONS.md` 20).
- **The NAND is degraded** (ECC errors, JFFS2 read/erase failures). Flash writes are
  wear-limited; no undirected fire cycles.
- **Upstream is a separate, unfinished track:** no OpenWrt target, DTS, image recipe or
  driver series exists; Wi-Fi + LAN switch + unanswered GPL source request are the gating
  blockers. Bench gates are not upstream progress.
- **Publish boundary:** `opensource/` is the published half; the root repo is private
  research material (vendor-derived binaries/Lua, dumps) and must not be published until
  cleaned. No vendor `.o/.ko`, firmware blobs, or calibration data in the published half.
- Calibration snapshot before any experiment; never restore without a verified
  `MANIFEST.sha256`; an incomplete snapshot must not be applied.
- The old Wi-Fi reversal lane and its device-mutating scripts are archived under
  `tools/archive/`; do not use them.
