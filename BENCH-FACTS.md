# Bench facts - physical invariants

**Read this before any device action.** These are measured, hardware-level facts. They do not
change from session to session. If one of them conflicts with the newest dated entry in
`mem-entries.md`, the hardware or wiring may have changed: STOP, tell the user, and verify
physically. Do not guess and do not act on memory.

**Updated:** 2026-11-28 (the stock H2D-trace access rules, the pair-switch procedure and the
TFTP shortcut are new; the physical invariants below are unchanged)
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
- Recovery image: `tftp/recovery.bin`, 22,024,351 bytes, md5
  `bc40580943e8a9865bb8288d3294f687` (the official 2.5.24 sysupgrade image - the one proven
  by the 2026-11-23 recovery; the older 2.4.15 image left a broken setup wizard). Serve it with
  `sudo -n python3 tools/tftp_server.py 69`; the host needs `192.168.1.88/24` and UDP 69
  allowed. Full card: `tools/recovery-card.sh`.
- After recovery the stock LAN comes back at `192.168.10.1`; verify 2 wiphys, 6+ interfaces,
  calibration `[SUCC]` on both bands, and no `.omo-off` leftovers.

## 5. Flash slots, selectors, and the delivery lane

- `/proc/mtd`: `mtd11 kernela` and `mtd12 kernelb` (8,650,752 B each), `mtd13/14
  rootfsa/rootfsb`, `mtd15 rootfs_data`, `mtd16 upgrade`.
- U-Boot: `bootcmd=mtd read kernel${bootflag} ${loadaddr}; bootfip ${loadaddr}`.
  `bootfip` accepts a full slice (`uImage + the fixed 40,732-byte trailer`).
- Slot/pair selection facts (updated 2026-11-21): U-Boot reads the **env bootflag** to name the
  kernel slot (`mtd read kernel` + bootflag + `bootfip`); the sysctrl cell
  `0x10100C08`/boot_reg is the handover/fallback record (`0x10` = A pair, `0x11` = B
  pair; a manual slot-B fire writes `0x21`; a manual slot-A handover value is not
  established).  A RESET-hold recovery restores the stock A pair, so a consistent handover must
  set the env bootflag together with the cell; a cell-only edit can mix kernel and rootfs pairs.
  Our image's cmdline hardcodes `ubi.mtd=rootfsb`, so it may only be written to pair b.  The
  failed plain `fw_setenv` was a multi-call symlink issue: it works via a tmp symlink to
  `/bin/fw_printenv` and the verified installer reads it back after setting it.
- A failed handover is followed by a failover read of the other slot; the captures show the same
  slot content re-read on later boots. The older "bootfip rejects the slot until reflashed" claim
  is not supported by the 2026-11-16 captures.
- **The last kernels that ran on hardware are 3df and 3dg (2026-11-16).** The 3dh-class
  kernels (3dh, 3di, 3dk, 3dl) do not start: U-Boot reads their uImage
  (`Data Size` 2,964,240 / 2,965,176, `Image Name: Linux-5.10.201`) and then the box resets
  silently before the kernel console registers. The variable is the kernel `.config` captured
  in commit `cca5be5` (COMPILE_TEST / SLAB / TRACING group), not the slot or the trailer; the
  kernel source and DTB are unchanged from the booting 3df/3dg builds. Do not fire a 3dh-class
  slice. See `STATUS.md` section 3 and `LESSONS.md` rules 24-26.
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

## Host network map (READ BEFORE ANY HOST NETWORK ACTION) - SUPERSEDED by the corrected map below (the phone USB-C tether is the internet)

The host has several network paths; confusing them drops the internet (seen twice, 2026-11-26).

| iface | role | facts |
| --- | --- | --- |
| `wlan0` (MT7922) | **THE INTERNET** | phone hotspot "slowphone", 10.28.90.x, default route metric 600. **Never disconnect, never restart/stop NetworkManager, never `nmcli device disconnect` or `iw connect` on it.** |
| `enp103s0u1u3` (USB-Ethernet) | **THE BOX LINK** | DHCP from the box (192.168.1.190); the box may also offer a default gateway - the NM profile is set `ipv4.never-default yes` so it can never steal the default route. Box work goes ONLY here, with scoped `ip addr ... dev enp103s0u1u3` + `ssh root@192.168.1.1`. |
| `enp195s0f3u1` | old adapter | down/unused; do not add addresses there (route ambiguity). |
| `tailscale0` | VPN | do not touch. |

Rules:
- **Check the map first**: `ip -br addr; ip route; nmcli -t -f DEVICE,STATE,CONNECTION device status`.
- **Never** restart NetworkManager or wpa_supplicant for a bench action.
- After any host-network action verify the internet: `ping -c1 1.1.1.1` and the box: `ping -c1 192.168.1.1`.
- Client-side association tests on the host Wi-Fi NEED the Wi-Fi, which is the internet path: use a second radio/dongle for those, or accept that the internet drops - never do it silently.

## Host network map - CORRECTED (2026-11-26 evening, verified live)

The phone's USB-C tether is the internet (the user's intent); the Wi-Fi must stay free for box client tests.

| iface | role | facts |
| --- | --- | --- |
| enp195s0f3u1 | THE INTERNET (phone USB-C tether, HONOR MBH-N49 RNDIS) | 10.31.72.76/24, default via 10.31.72.14 metric 100. NM-managed (the old name-based unmanaged rule was replaced by a MAC rule for the box adapter). |
| enp103s0u1u3 | THE BOX LINK | MAC 00:e0:4c:68:02:14, NM-unmanaged (the MAC rule), static 192.168.1.88/24 (TFTP recovery + our image) + 192.168.10.44/24 (stock LAN). Box work goes here only. |
| wlan0 (MT7922) | BOX TEST CLIENT - free | Must stay free of the phone hotspot; it joins wr3000v2-apstart (or the stock AP) for the client-side association tests. It is NOT the internet anymore. |
| enp195s0f4u1 | (old name) | the phone's RNDIS renames across boots: identify by MAC fa:83:d9:29:58:75, never pin the name. |
| tailscale0 | VPN | do not touch. |

Rules (updated):
- Internet check: ping -c1 1.1.1.1 must go via the tether (enp195s0f3u1 / fa:83:d9:29:58:75), never via wlan0.
- The box tests may use wlan0 freely (it is not the internet path).
- If the tether drops: nmcli general reload conf + nmcli device connect <tether-iface>; find the name with ip -br link (MAC fa:83:d9:29:58:75).
- Do NOT restart NetworkManager; nmcli general reload conf re-reads conf.d without dropping connections.

## 7. Stock ETE/H2D register access: mmap only, and the two aliased windows (2026-11-28)

- **`pread()` on `/dev/mem` cannot reach the ETE MMIO.** On this 32-bit ARM kernel
  `valid_phys_addr_range()` rejects every physical address below `PHYS_OFFSET = 0x80600000`
  with `-EFAULT`. The v1 H2D sampler ignored that error and printed "ring not seen" for any
  window - a guaranteed false negative, not evidence about the ring. **Use `mmap()` only**
  for the ETE window; `pread()` stays valid for the DRAM nodes.
- **Two windows alias the same on-chip registers.** The stock runs the vendor stack on
  **EP1 = `0001:00:00.0`**: BAR0 `0x58000000`, region-3 base `0x583b8000`, **ETE window
  `0x583f2000`** (the stock's own). Our PD4 image enumerates **EP0 = `0000:00:00.0`**:
  region-3 `0x403b8000` -> **`0x403f2000`**. Read the stock's `0x583f2000`; treat
  `0x403f2000` as the documented alias (same registers).
- **The instrument is the v2 mmap sampler**, built from
  `opensource/docs/incoming/wifi-rx-h2d-window/tools/`: static ARM/musl, **54,364 B,
  sha256 cb03ee1b85feb7fdd0a81b3b7a4d97461a8ad2eb1a9459134426ddbbbf352805**. The v1 binary
  is retired; do not rerun it (it fails identically at every `-w`).
- **Mandatory read-only gate before a capture boot** (stock root shell, vendor AP up):
  `/usr/bin/omo_h2dsampler -p -w 0x583f2000` must print `access=mmap`, a non-zero SR0
  base in `0x80000000..0x87ffffff`, `depth=0x1f`, `ring=YES`, and
  `pread_control=FAIL errno=14 (Bad address)` - the last is the **measured v1 defect**,
  expected, not a fault. STOP (no capture boot) if the ring is not visible in both windows.
- **Capture boot:** the aid starts the sampler before the vendor stack loads; sampler args
  `-w 0x583f2000 -W 180 -t 240`. The SR ring is programmed by the `plat.ko` probe ~14.2 s
  after boot (the S08 aid starts ~9.8 s, so `-W 180` is margin). PASS = a valid `M`-message
  list decoded by `tools/decode_h2d.py`. Procedure:
  `opensource/docs/incoming/wifi-rx-h2d-trace/RUNBOOK.md` + the delta in
  `opensource/docs/incoming/wifi-rx-h2d-window/RUNBOOK-DELTA.md`.

## 8. Pair switch (stock pair A <-> our pair B): env bootflag + selector cell together

- **The pair is selected by the U-Boot env `bootflag`**
  (`bootcmd=mtd read kernel${bootflag} ${loadaddr}; bootfip ${loadaddr}`); the SYSCTRL cell
  `0x10100C08` is the loader's failure record and must **match** the env. A mismatch makes
  the next boot print `boot from kernelX failed, change to kernelY` and swap pairs - that is
  why every switch writes both together (`opensource/docs/SELECTOR-0x21.md`).
- **Interfaces:** the stock 5.10 kernel exposes `/sys/devices/platform/sysenv/boot_reg`
  (low byte: `0x10` = pair A, `0x11` = pair B; `0x21` is the fire-device manual-B value,
  normalised by the loader). Our kernel exposes
  `/sys/devices/platform/boot-selector/{raw,current_pair,next_pair}`; a `next_pair` write
  was permission-denied as root in 2026-11-26. `/etc/init.d/luofu-pair-record` re-records the
  running pair in our image, so a correct selection is stable across reboots.
- **Our pair B -> stock pair A:** a plain reboot of our image (the reboot resets the SYSCTRL
  selector, the stock boots). No env write needed.
- **Stock pair A -> our pair B**, from the stock root shell:
  `ln -sf /bin/fw_printenv /tmp/fw_setenv; /tmp/fw_setenv bootflag b;
  echo -n 0x11 > /sys/devices/platform/sysenv/boot_reg; sync; reboot`.
  Verify the U-Boot line `bootflag b bootreg 11` and the image coming up.
- **Two-stage rule after a RESET-hold recovery:** recover first, switch the recovered stock to
  pair A (`bootflag a` + `0x10`, verify), then write our image to the inactive pair B and set
  `bootflag b` + `0x11` in the SAME command (no window for the vendor pair recorder).
  - The running rootfs is `ubi0`; `cat /sys/class/ubi/ubi*/mtd_num` names the active mtd.
    Never `ubiformat` the active rootfs; write the inactive pair.
  - Our image's cmdline hardcodes `ubi.mtd=rootfsb`, so it may be written to pair B only.
- **A pair switch is a bench operation:** recovery card READY, read-only UART capture running,
  human present. Never switch pairs unattended.

## 9. TFTP shortcut: move files between the host and the stock shell

- **Host server:** `sudo -n python3 tools/tftp_server.py 69` (or
  `tools/recovery-card.sh --arm` for the recovery-image path). Start it as a **managed
  background job** - the `setsid nohup` path the recovery card uses has died mid-session and a
  dead server looks like a stock-side timeout.
- **Host firewall:** allow **UDP 69 on the box-link interface** (`enp103s0u1u3` in the
  corrected 2026-11-26 map). A ufw rule pinned to the old `enp195s0f3u1` silently blocks the
  stock because that name is now the internet tether.
- **Stock busybox tftp client** (the stock image has no `nc`/`base64`; this is the way to
  move a binary payload or a log when SSH/the broker is unavailable):
  - fetch: `tftp -g -l /tmp/<file> -r <file> 192.168.10.44`
  - push:  `tftp -p -l <device-file> -r <host-file> 192.168.10.44`
  The vendor-LAN host address is `192.168.10.44`; the U-Boot loader's recovery TFTP is
  `192.168.1.88`. TFTP is unauthenticated: bench link only, never for anything trusted;
  always `sha256sum` after the transfer (the 2026-11-28 trace moved the v2 sampler and the
  logs this way, byte-exact).

