# tools/ - current harness, transport, and CLIs

## OVERVIEW

The live surface is small. `fire.sh` is the device-cycle entry point,
`check-init-shadow.sh` is the fire guard, `box-provision.sh` is the broker lane, and
`rsh.sh`/`rscp.sh` are the SSH transport. Everything in `archive/` is historical
scratch and is not part of the live surface.

## WHERE TO LOOK

| Task | File | Notes |
| --- | --- | --- |
| Fire cycle | `fire.sh` | `list`, `latest`, `guard`, `run <phase> --detach`, `status`, `verdict`, `broker` |
| Shadow guard | `check-init-shadow.sh` | must print PASS before any fire |
| Broker provision | `box-provision.sh` | `--stage base`, `lab`, `fire`; no SSH required |
| SSH transport | `rsh.sh`, `rscp.sh` | project key `.omo-secrets/router_ed25519` |
| Snapshot sync | `sync-lab-src.sh` | copy the live kernel changes into `tools/lab-src` |
| Snapshot check | `check-lab-src.sh` | manifest checks plus full-tree completeness; `--manifest-only` is the quick check |
| Snapshot completeness | `check-lab-src-complete.sh` | diff the live tree against the vanilla tree; needs `VANILLA_TREE` or the tarball |
| Evidence completeness | `pack-evidence.sh` | inventories an evidence dir into `PACKED.txt` |
| Evidence skeleton (old lane) | `finish-evidence.sh` | old Wi-Fi lane helper; `pack-evidence.sh` is the generic one |
| Firmware patch scratch | `patch_fw_scratch.py` | variant builder for scratch images |
| Legacy module cycle | `exp.sh`, `batch.sh` | old Wi-Fi lane; not for kernel work |
| Legacy detached | `run-exp-detached.sh` | old Wi-Fi module lane; not for kernel work |
| Un-hide vendor modules | `restore-now.sh` | `mv *.omo-off` back, remove loaders, sync; caller reboots. Removes four hardcoded `.ko` names; other staged modules survive |
| Restore stock files | `restore-vendor.sh` | copies missing files from `/rom`; never overwrites |
| Calibration snapshot | `wifi-cal-snapshot.sh` | read-only; writes `build/linux-kbuild/cal-snapshots/<TS>/`; run before any experiment |
| Calibration restore | `wifi-cal-restore.sh <snap> [--apply]` | dry-run by default |
| Web login | `web_login.sh` | salted SHA256 via node |
| systime RCE probe | `rce_probe.sh` | default payload `'; touch /tmp/omo-rce-test; #` |
| systime RCE flow | `web_rce_test.js` | wizard login, CSRF, POST payload |
| Absolute-URL proxy | `proxy.js` | listens `127.0.0.1:8899` |
| bdinfo secret | `decrypt_bdinfo.py` | DES-CBC; yields `secret`, `deviceid` |
| Forge broker JWT | `forge_jwt.py` | `--deviceid --secret` or `--demo` |
| MQTT takeover | `mqtt_takeover.py` | passive by default; `--cmd` publishes |
| Unpack firmware | `extract_firmware.py` | hboot1tag, uImage, UBI, squashfs |
| Explore an image | `scan_image.py` | logs UBI volumes and DES blob hits |
| Lua 5.1 bytecode | `luadump.py` | `python3 luadump.py <file.luac> -c` |
| Crack shadow hashes | `crack.py` | md5crypt and sha512crypt; needs passlib (in `requirements.txt`) |
| TFTP serve/test | `tftp_server.py`, `tftp_test.py` | unauthenticated; LAN only |
| Fake bdinfo fixture | `mk_fake_bdinfo.py` | round-trip fixture for `decrypt_bdinfo.py` |
| Ledger index | `gen-ledger-index.py` | regenerate `mem-entries-INDEX.md` |
| Vendor fixtures | `vendor-mods/` | two vendor `.ko` files for the `.plt` recipe |
| Historical scratch | `archive/` | not live; do not use for current work |

## CONVENTIONS

- `.sh` headers: `# <name> - <purpose>` plus a usage block. This is required; the
  comment hook flags it, and it is intentional.
- Harnesses use `set -uo pipefail`; `set -e` only where no recovery is needed.
- Device I/O goes through `rsh.sh`/`rscp.sh`, or a script's own `ssh` with the project
  key. There is no `.sshwrap/` in a plain checkout; `exp.sh` and `finish-evidence.sh`
  fall back to the tracked wrappers.
- Python: use `.provision-venv/bin/python` for `decrypt_bdinfo.py`, `forge_jwt.py`,
  `mqtt_takeover.py`, `mk_fake_bdinfo.py`, `crack.py`, and `scan_image.py`. Stock
  `python3` is 3.14 and lacks pycryptodome, PyJWT, paho-mqtt, and passlib. Install
  with `.provision-venv/bin/pip install -r tools/requirements.txt`.
- Credentials are placeholders. Live values come from `.omo-secrets/`.
- Scratch goes in `archive/`; do not add a new variant to the live surface.

## ANTI-PATTERNS

- Never run a device cycle in the foreground. `fire.sh run <phase> --detach`, or the
  broker lane. Arm the device watchdog before hiding vendor modules.
- `check-lab-src.sh --manifest-only` is not a completeness check; use the default
  full check before trusting the snapshot.
- `restore-now.sh` removes four hardcoded modules; check for other staged `.ko`
  files.
- Never replace `/etc/rc.d/luofu` wholesale. Run `check-init-shadow.sh`.
- Never write CA `0x400392f0`; never read `0x10161000`; never `rmmod` vendor modules.
- `exp.sh` and `batch.sh` are the old Wi-Fi module lane, not the kernel cycle. The
  fallback wrappers keep them runnable, but do not use them for kernel work.
- `tftp_server.py` is unauthenticated and writes uploads under `tftp/inbox`; LAN only.
- No flash writes in this set except `box-provision.sh --stage fire`, which writes
  `kernelb` through the broker. Recovery is the TFTP path in `RUNBOOK.md`.
