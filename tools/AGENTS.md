# tools/ - live harness, transport, and CLIs

## OVERVIEW

The live surface is small and fire-related. `fire.sh` is the only fire entry point and it runs
`fire-preflight.sh` before anything is staged. `bench-link.sh`, `recovery-card.sh`,
`uart-capture.sh`, `session-brief.sh`, `check-repo.sh` and `bench-teardown.sh` are the
session/bench guardrails. `box-provision.sh` is the broker lane and `rsh.sh`/`rscp.sh` the
SSH transport. `archive/` is retired scratch, including the old Wi-Fi lane; do not use it.

Read `../BENCH-FACTS.md` and `../STATUS.md` before touching a device.

## WHERE TO LOOK

| Task | File | Notes |
| --- | --- | --- |
| Session start | `session-brief.sh` | read-only one-screen git/doc/bench state + warnings |
| Repo consistency | `check-repo.sh` | static drift/retired-claim/vendor-binary/publish checks |
| Bench link | `bench-link.sh` | check; `--apply` unmanages NM and adds the two addresses |
| Read-only console | `uart-capture.sh` | `start/stop/check`; opens the tty READ-ONLY; never sends bytes |
| Recovery door | `recovery-card.sh` | checks + prints the physical RESET/TFTP card; `--arm`, `--stop` |
| Fire gate | `fire-preflight.sh` | fail-closed checks; `--slice --slot a|b --attended` |
| Fire cycle | `fire.sh` | `ssh`, `run`, `broker` are preflight-gated; `list/latest/status/verdict` |
| First install from stock (design + tool) | `first-install-stock.sh`, `../opensource/docs/FIRST-INSTALL.md` | read-only by default; writes only the inactive pair and needs `--attended --recovery-armed`; mocked tests `tests/first-install.test.sh`; never executed on hardware; not a fire lane |
| First install over stock telnet (bench tool) | stock-telnet-install.sh, telnet-exec.py | read-only inspect by default; --apply --attended --recovery-armed writes pair b only (kernelb+rootfsb), refuses env-bootflag/selector disagreement and pair-a targets, sets+reads back the env bootflag with the selector, verifies uploads/read-back/active-pair-unchanged, and requires the booted cmdline ubi.mtd=rootfsb + project marker; verified end-to-end 2026-11-21; exists because the vendor image has no SSH/dropbear/opkg; not a fire lane; after a RESET-hold recovery the env bootflag and selector must be set together and only a consistent vendor pair supports the broker channel (CVE-2026-71961) |
| Read-only bench inventory | `bench-inventory.sh` | 600 allowlisted 32-bit reads (LSW/PIE/CRG/SYSCTRL), fail-closed gates (attended/transport/bench-link/recovery/UART/stock health), never writes, never reads the RC misc window; `--check-only`, `--print-plan`, `--explain`; tests `tests/bench-inventory.test.sh`; procedure `../opensource/docs/BENCH-READONLY-INVENTORY.md` |
| Generic SSH fire | `fire-ssh.sh` | trailer fail-closed, slot env forwarded, boot_id-verified return |
| Device-side fire | `fire-device.sh` | runs ON THE BOX; validates MTD/device pair and handover before erasing |
| Shadow guard | `check-init-shadow.sh` | source-level PASS/FAIL; not an artifact proof |
| Broker provision | `box-provision.sh` | `--stage base|lab|fire`; `--cmd` for one read-only command; serves only `build/linux-kbuild/http-root/`; host firewall must allow TCP 8000 |
| SSH transport | `rsh.sh`, `rscp.sh` | project key `.omo-secrets/router_ed25519` |
| Teardown | `bench-teardown.sh` | find/kill stale fire-log writers and broker HTTP servers; `--all` also stops TFTP/capture |
| Snapshot sync / check | `sync-lab-src.sh`, `check-lab-src.sh`, `check-lab-src-complete.sh` | tracked kernel mirror vs live tree |
| Evidence packing | `pack-evidence.sh` | inventory a directory into `PACKED.txt` |
| Off-device init run | `qemu-init-run.sh` | runs the tracked init as PID 1 under qemu-system-arm |
| Calibration | `wifi-cal-snapshot.sh`, `wifi-cal-restore.sh <snap> [--apply]` | snapshot marks incomplete payload sets; restore refuses them; dry-run by default |
| Restore helpers | `restore-now.sh`, `restore-vendor.sh` | run ON THE BOX; copy them over and run with `sh` |
| bdinfo/broker crypto | `decrypt_bdinfo.py`, `forge_jwt.py`, `mqtt_takeover.py` | use `.provision-venv/bin/python`; LAN only |
| Firmware / Lua / RE | `extract_firmware.py`, `scan_image.py`, `luadump.py`, `crack.py`, `ghidra/`, `vendor-mods/` | `vendor-mods/*.ko` are untracked local fixtures, never published |
| TFTP | `tftp_server.py`, `tftp_test.py` | RRQ only by default; `--allow-wrq` is opt-in; blksize path untested against this U-Boot |
| Ledger index | `gen-ledger-index.py` | `python3 tools/gen-ledger-index.py` |
| Archived | `archive/` | old Wi-Fi module lane and scratch; not live; do not run |

## CONVENTIONS

- `.sh` headers: `# <name> - <purpose>` plus a usage block (the comment hook expects it).
- Harnesses use `set -uo pipefail`; `set -e` only where no recovery is needed.
- Device I/O goes through `rsh.sh`/`rscp.sh` (or the script's own ssh with the project key).
  No `.sshwrap/` exists in this checkout.
- Python dependency tools use `.provision-venv/bin/python` (`tools/requirements.txt`;
  `tools/setup-python.sh` creates it). Stock `python3` is 3.14 and lacks the packages.
- Evidence under `build/linux-kbuild/waves/<phase>/` and `build/uart-logs/`; `/tmp` is not
  evidence. Never commit credentials; live values come from `.omo-secrets/`.
- New live tools need: header, usage, read-only default where possible, a row here, and a
  mention in `check-repo.sh` if they are part of the gate.

## ANTI-PATTERNS

- **Never transmit on the UART.** No `echo`/`printf` to `/dev/ttyUSB0`, no `screen`/
  `minicom`/`picocom`, no read-write tty open (the `3<>` form), no typed keys or U-Boot
  abort-key floods. Use
  `uart-capture.sh`; the host->router line is dead (burnt resistor).
- Never fire without `fire-preflight.sh` PASS, a READY recovery door, a running read-only
  capture, and a human at the bench.
- Never run `fire-device.sh` on the host; it runs on the box. Never set `MTD` without the
  matching `MTD_DEV`; the script validates and refuses.
- Never restart a per-phase script through an old documented command: per-phase scripts are
  gitignored history; use `fire.sh`.
- Never serve the repo root over HTTP (the broker used to); only
  `build/linux-kbuild/http-root/` is served.
- Never replace `/etc/rc.d/luofu` wholesale; run `check-init-shadow.sh`.
- Never write CA `0x400392f0`, read `0x10161000`, or `rmmod` vendor modules.
- Never commit vendor binaries/objects or credentials. `tools/vendor-mods/*.ko` are local
  fixtures; the `opensource/` half must not carry vendor `.o/.ko`.
- Archived tools (`exp.sh`, `batch.sh`, `run-exp-detached.sh`, `finish-evidence.sh`,
  `rce_probe.sh`, old HTML pages) are not the live lane.
