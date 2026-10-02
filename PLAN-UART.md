# WR3000 V2.0 — UART session plan (prepared 2026-09-30)

Everything here is verified against the extracted stock firmware (2.4.15). Nothing is flashed until dumps exist.

## What to buy
- USB to TTL serial cable, **3.3V** logic (CH340G / CP2102 / FT232RL), female dupont ends. ~$8-12.
- Small Phillips screwdriver for the case.

## Wiring (3 wires only; do NOT connect VCC)
- Adapter GND  -> router UART GND
- Adapter RX   -> router UART TX
- Adapter TX   -> router UART RX
- Adapter 3V3  -> leave unconnected (router is powered normally)
- Serial settings: **115200 8N1, no flow control**

## UART console facts
- U-Boot: bootdelay=1; default console 115200; bootmenu entries (rootfs/kernel/uboot/esbc/bdinfo updates via TFTP).
- u-boot env defaults (from image): ipaddr=192.168.1.1  serverip=192.168.1.88  loadaddr=0x83200000
- Update commands (run from the u-boot prompt with a TFTP server on 192.168.1.88):
  - `run bdinfoupdate_eth`   (bdinfo.bin    -> mtd erase/write bdinfo)
  - `run rootfsupdate_eth`   (rootfs.rw.img -> mtd erase/write rootfsa + rootfsb)
  - `run squashfsupdate_eth` (rootfs.ro.img -> rootfsa + rootfsb)
  - `run fipupdate_eth`      (kernel.images -> kernela + kernelb)
  - `run ubootupdate_eth`, `run esbcupdate_eth`, `run rebootuboot`
- Linux console login (stock): root / `admin` (factory password, cracked from the image hash).

## Session order (first contact)
1. PC: set Ethernet static 192.168.1.88/24 (netsh works from the agent shell, verified).
2. Start the TFTP server (`tools/tftp_server.ts`) serving `router-openwrt/tftp/`.
3. Attach adapter -> open serial terminal at 115200 -> power-cycle the router.
4. Press a key at "Hit any key to stop autoboot" -> u-boot prompt.
5. `printenv` — capture the LIVE env (differs from defaults? note net settings, bootargs).
6. Read bdinfo (get the fleet secret), safest first options:
   - `nand read <addr> <bdinfo_off> <len>` + `md.b <addr> <len>` (print over console), or
   - `tftpput` if available. Offsets from the live `mtdparts` (printenv / `mtdparts`).
7. Decrypt the dump on the PC: `pyenv/Scripts/python.exe tools/decrypt_bdinfo.py dump.bin` (pipeline round-trip tested).
8. With `secret`: MQTT root (forge JWT, publish router/<id>/<id>/router/command) and/or backup crypto — software control.
9. Then (optional, same session): boot the stock kernel with `init=/bin/sh` via edited bootargs for a root console,
   dump all MTD partitions to the PC, and only then consider any flash write.
10. Recovery: everything here is read-only until step 9's dumps exist; u-boot TFTP update commands are the recovery path.

## Verified security facts (why this is the only path)
- No injectable web endpoint found in a systematic audited sweep (diag quoted; ping validated; servicectl logs only;
  uploads validated at upload; rpc auth walled; backup/MQTT keyed by the bdinfo `secret`; firmware imgs RSA-verified;
  cwmp exists but is disabled + ACS-HMAC-gated and its helpers still hit crypto/RSA walls).
- SSH/telnet gated by `bdinfo dbg` (libbdinfo also honors /etc/rom_dbg presence); failsafe was stripped.
- The fleet `secret` unlocks: mosquitto JWT (CVE-2026-71960/71961 -> root exec via command.lua) and `crypt` backups.

## Workspace
- firmware/ (2.4.15 + 2.5.24 zips + 2.4.15.bin), rootfs-2.4.15/, tools/ (scan_image.py, decrypt_bdinfo.py,
  mk_fake_bdinfo.py, crack.py, tftp_server.py, tftp_test.py), pyenv/, pages/, CREDENTIALS.txt (web admin `<ROUTER-WEB-PASSWORD>`).

## TFTP server (for the u-boot session)
- Serve dir: `router-openwrt/tftp/`; WRQ uploads land in `router-openwrt/tftp/inbox/`.
- Start: `router-openwrt/pyenv/Scripts/python.exe router-openwrt/tools/tftp_server.py 6969`
- Self-test: `router-openwrt/pyenv/Scripts/python.exe router-openwrt/tools/tftp_test.py 6969` (GET+PUT round trip).
- The PC must hold 192.168.1.88/24 on the wired NIC (u-boot `serverip`); u-boot fetches by the names its commands
  expect (`bdinfo.bin`, `rootfs.rw.img`, `rootfs.ro.img`, `kernel.images`).
