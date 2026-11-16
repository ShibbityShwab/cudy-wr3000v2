# Current truths (2026-11-16)

Curated summary. The ledger is the long form; the latest dated entry wins.

- The live status page is `STATUS.md`; the procedure is `RUNBOOK.md`.
- G1 through G4 and G6 are green as of 2026-11-14; G5 is vendor-only.
- The box is on vendor stock: OpenWrt 22.03.6 rev 2.4.15, 2 wiphys, both bands' calibration loaded,
  `192.168.10.1` answering, SSH on the project key (restored 19:05).
- The PLT gate no longer blocks the vendor stack: the patched module set (zero-size
  `.plt`/`.init.plt`, `tools/box-provision.sh --stage lab`) plus the near-region `module_alloc`
  loads it, and 3dh's capture shows `eth2` up at 1Gbps.
- Open item is delivery: `tools/fire-device.sh` writes `kernelb`, but the slot U-Boot boots cleanly
  here is the AB one, so the 3dk fire never ran its slice. A fire must target that slot and the
  capture must show `Uncompressing Linux` for our image before anything is read from it.
- Vendor recovery: the trigger is the RESET counter (`RESET button is pressed for: 0/1/2 second(s)`,
  then `Resetting...`, then `recovery button press`), and the host port must be unmanaged
  (`nmcli device set enp195s0f3u1 managed no`) with `192.168.1.88` on it, or the board's ARP goes
  unanswered.
- 3dl (built, not fired) prints one `<6>load <mod> fd=.. ret=..` kmsg line per vendor module:
  `build/linux-kbuild/waves/3dk/build.md`.
- The console reads only with the swapped UART pins; captures write to an absolute path.
- The latest dated entry wins over any earlier claim. The ledger is append-only.
- The old Wi-Fi reversal wall (phase 48) is history, not the current blocker.
- Calibration snapshot before any experiment; never restore without a verified
  `MANIFEST.sha256`.
