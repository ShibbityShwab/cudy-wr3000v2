# Bench facts - physical invariants

**Read this before any device action.** These are measured, hardware-level facts. They do not
change from session to session. If one of them conflicts with the newest dated entry in
`mem-entries.md`, the hardware or wiring may have changed: STOP, tell the user, and verify
physically. Do not guess and do not act on memory.

**Updated:** 2026-11-17 (bench re-verified read-only during the harness audit)
**See also:** `HARDWARE-IDENTITY.md` (identity and UART history), `STATUS.md` (live state),
`RUNBOOK.md` (procedure), `LESSONS.md` (rules that cost fires).

## 1. The unit

- Cudy WR3000 v2.0, HiSilicon luofu v2-class board: Hi5671YV200 SoC (2x Cortex-A9), Hi5622v100
  Wi-Fi, 128 MB NAND, 128 MB DDR3. Stock OpenWrt 22.03.6, kernel 5.10.201.
- The enclosure may say WR3000 v1. It is **not** the MediaTek MT7981 v1. Never flash a
  WR3000 v1 / MediaTek image: the v1 image cannot boot this board.

## 2. Bench network: router eth2 <-> host USB Ethernet

- The router LAN port whose Linux netdev is **`eth2`** (a `br-lan` member) is cabled to the
  host's **USB-to-Ethernet adapter `enp195s0f3u1`**. That cable is the only host<->router link.
- 1 Gbps, no DHCP for this lane. Both sides use static IPv4.
- The host adapter must carry two addresses:
  - `192.168.1.88/24` - TFTP recovery server address (the loader's `serverip`).
  - `192.168.10.44/24` - host address on the vendor LAN (broker HTTP :8000, SSH source).
- NetworkManager must **not** manage the adapter. If it does, it retries DHCP, strips
  hand-added addresses minutes later, and the board's ARP for `192.168.1.88` goes unanswered
  (`ARP Retry count exceeded; starting again`).
  `nmcli device set enp195s0f3u1 managed no` is **runtime-only** - during the 2026-11-17 audit
  NetworkManager reclaimed the adapter mid-session and stripped `192.168.1.88`. Use
  `tools/bench-link.sh --apply`, which also writes the drop-in
  `/etc/NetworkManager/conf.d/99-bench-unmanaged.conf` (persistent across NM restarts), and
  re-check every session.
- Router address: **`192.168.10.1`**. SSH key `.omo-secrets/router_ed25519`, used by
  `tools/rsh.sh` and `tools/rscp.sh`.
- After a TFTP recovery the overlay is empty: reinstall the project key and start dropbear with
  `-R` after deleting the zero-byte host keys.

## 3. UART is READ-ONLY - NEVER TRANSMIT

- Adapter: FT232R at `/dev/ttyUSB0`; 115200 8N1; GND + TXD + RXD only, no VCC, 3.3 V logic.
- The working wiring is the **swapped** pin pair. The router's console output reaches the host,
  but the **host -> router direction is dead**: one line's resistor is burnt. The user has ruled
  out repair; treat it as permanently read-only.
- Therefore there is **no serial input of any kind**. The U-Boot prompt is unreachable and must
  not be chased. Do not send: typed keys, `echo`/`printf`/`cat >` to the tty,
  `screen`/`minicom`/`picocom`, U-Boot abort-key floods, serial-login attempts, or serial
  recovery input. Do not open the tty read-write (the `3<>` form is forbidden).
- Allowed: configuring termios with `stty` (configuration ioctls, not data) and reading bytes.
  Capture with `tools/uart-capture.sh`, which opens the tty READ-ONLY and writes an absolute
  log path under `build/uart-logs/`.
- A zero-byte capture means the capture command, permissions, or wiring is wrong - it is never
  a reason to start writing to the tty.

## 4. Power, RESET, recovery

- The recovery trigger is the **RESET-button counter**, not a short hold: power off, hold RESET,
  power on still holding. The console then prints
  `RESET button is pressed for: 0/1/2 second(s)`, `Resetting...`, and only then
  `recovery button press` followed by the TFTP client. A hold released early leaves it at
  `0 second(s)` and the box boots normally. The counter appears only on a true power-on reset,
  never on the watchdog resets the box performs itself.
- Recovery requires hands on the box. **An agent cannot power-cycle or hold RESET.** Treat every
  fire as a human-attended bench operation with a pre-armed recovery.
- Recovery image: `tftp/recovery.bin`, 20,975,775 bytes, md5
  `421114c8ea999c925b7aa79cc548af81`. Serve it with
  `sudo -n python3 tools/tftp_server.py 69`; the host needs `192.168.1.88/24` and UDP 69
  allowed. Full card: `tools/recovery-card.sh`.
- After recovery the stock LAN comes back at `192.168.10.1`; verify 2 wiphys, 6+ interfaces,
  calibration `[SUCC]` on both bands, and no `.omo-off` leftovers.

## 5. Flash slots, selectors, and the delivery lane

- `/proc/mtd`: `mtd11 kernela` and `mtd12 kernelb` (8,650,752 B each), `mtd13/14
  rootfsa/rootfsb`, `mtd15 rootfs_data`, `mtd16 upgrade`.
- U-Boot: `bootcmd=mtd read kernel${bootflag} ${loadaddr}; bootfip ${loadaddr}`.
  `bootfip` accepts a full slice (`uImage + the fixed 40,732-byte trailer`), and a failed boot
  leaves a status word that makes `bootfip` reject that slot until it is erased and rewritten.
- `bootflag` env selects the slot (`a`=kernela, `b`=kernelb). `boot_reg` sysfs is the
  boot status/handover word (`0x10`=hardware failover to slot A, `0x11`=slot B booted,
  `0x21`=manual slot-B request). Read both; never infer a slot from memory.
- **The delivery lane is not proven as of 2026-11-16.** Both 3dh and 3dk had their uImage read by
  U-Boot (`Data Size` 2,964,240 and 2,965,176, `Image Name: Linux-5.10.201`) but no kernel
  console output followed. Do not fire until `STATUS.md` names a delivery plan that passes
  `LESSONS.md` rule 1 and `tools/fire-preflight.sh`.
- **Fire-validity marker (corrected 2026-11-16):** our slice is an uncompressed uImage and does
  **not** print `Uncompressing Linux`; only the stock 4,294,096-byte image prints that. A valid
  reading of our slice is U-Boot printing **our** `Data Size` / `Image Name` followed by our kernel
  output. `Uncompressing Linux` in a capture is evidence of the stock fallback boot, not of us.
- **The NAND is degraded.** Captures show ECC errors and JFFS2 read/erase failures on
  `rootfs_data` and `upgrade`, and one recovery had to fight the flash. Every fire is a
  wear-limited write; never cycle the box for an experiment that was not written down first.

## 6. Hard forbidden list

- Never flash a WR3000 v1 / MediaTek image.
- Never write CA `0x400392f0`. Never read the RC misc window `0x10161000`. Never `rmmod` the
  vendor modules.
- Never replace `/etc/rc.d/luofu` wholesale; `hi_kpinctrl` is load-bearing.
  `tools/check-init-shadow.sh` must print PASS before any fire.
- Never write a flash slot without a recovery plan, the fire preflight gate, and a human at the
  bench.
- Never transmit on the UART.
- Never commit credentials; tracked text carries placeholders, live values live in
  `.omo-secrets/` only.
