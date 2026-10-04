# tools/ - experiment harness, crypto/RE CLIs, probes

## OVERVIEW
Everything that touches the device or the firmware images. Two instrument sets: `*.sh` (live device cycle) and `*.py` (offline crypto / disassembly / CLI). `*.js` are the two web-UI probes.

## WHERE TO LOOK
| Task | File | Notes |
|------|------|-------|
| One experiment, full cycle | `exp.sh` | 7 phases: arm watchdog -> stage -> reboot -> wait done -> capture -> recover -> health. `EXP_RESULT: PASS\|FAIL`; exit code from verdict |
| N hypotheses, ONE boot | `batch.sh` | sources `exp.sh`; list `<label>\|<param>[,<param>]`; folds per-hypothesis results into `report.txt` |
| Detached / unattended | `run-exp-detached.sh` | older cycle, `/root/rd-watch.sh` (900 s); requires env `ROUTER_SSH_PASSWORD` |
| Un-hide vendor modules | `restore-now.sh` | `mv *.omo-off` back, rm loaders + 4 staged `.ko`, sync; caller reboots |
| Restore deleted stock files | `restore-vendor.sh` | copies missing files/symlinks out of read-only `/rom`; never overwrites |
| Calibration snapshot | `wifi-cal-snapshot.sh` | device read-only; writes `build/cal-snapshots/<TS>/` + `MANIFEST.sha256` |
| Calibration restore | `wifi-cal-restore.sh <snap> [--apply]` | dry-run by default; `--apply` scp's 4 factory cal files |
| Web login (cookie jar) | `web_login.sh` | salted SHA256 via node; needs `node` |
| systime RCE probe | `rce_probe.sh` | default payload `'; touch /tmp/omo-rce-test; #` |
| systime RCE, full flow | `web_rce_test.js` | wizard login -> CSRF/token -> POST payload; `node web_rce_test.js [base] [pw] [payload]` |
| Absolute-URL HTTP proxy | `proxy.js` | `node proxy.js [port]` listens `127.0.0.1:8899` |
| bdinfo secret | `decrypt_bdinfo.py` | DES-CBC + string-to-key; yields `secret`, `deviceid` |
| Forge broker JWT | `forge_jwt.py` | `--deviceid --secret` or `--demo`; HS256, exp floor 1577826000 |
| MQTT takeover | `mqtt_takeover.py` | passive by default; `--cmd` publishes (whitelist `id/uname/echo/true`) |
| Unpack sysupgrade | `extract_firmware.py` | `hboot1tag` -> uImage -> UBI PEB reassembly -> squashfs |
| Explore an image | `scan_image.py` | kitchen-sink scanner; logs UBI volumes + DES blob hits |
| Lua 5.1 bytecode | `luadump.py` | `python3 luadump.py <file.luac> [-c]` |
| Crack shadow hashes | `crack.py` | `crack.py [wordlist ...]`; md5crypt + sha512crypt |
| TFTP serve/test | `tftp_server.py` / `tftp_test.py` | serve `tftp/`, WRQ -> `tftp/inbox`; unauthenticated, LAN only |
| Fake bdinfo vector | `mk_fake_bdinfo.py` | round-trip fixture for `decrypt_bdinfo.py` |
| Batch list example | `batch-hypotheses.example` | 4 SR-trigger hypotheses; module contract in `opensource/docs/phase22/exp-harness.md` |

## CONVENTIONS
- `.sh` headers: `# <name> - <purpose>` + usage block; `set -uo pipefail` in the harnesses (never `set -e`), errors accumulated in `FAILURE` so recovery always runs.
- Both harnesses support `--dry-run` (prints the ssh/scp shape, touches nothing) - use it before any real run.
- Device I/O goes through `.sshwrap/rsh.sh` / `.sshwrap/rscp.sh`; target `root@192.168.10.1`; kernel `5.10.201`.
- Env contract on `exp.sh`: `EXP_WATCH=1800 EXP_BOOT_TIMEOUT=300 EXP_RUN_TIMEOUT=180 EXP_HEALTH_TIMEOUT=180 EXP_DONE_CMD` (default `dmesg | grep -q ': done ('`) `EXP_CAPTURE_CMD` (default empty = no hook; when set it runs remotely after `EXP_DONE_CMD` and before the capture step, stdout+stderr saved to `capture-cmd.txt` in the evidence dir, non-zero exit records FAILURE with recovery still running).
- Credentials are placeholders: `PW=<ROUTER-WEB-PASSWORD>`, `echo <ROUTER-SSH-PASSWORD>`, env `ROUTER_SSH_PASSWORD`; real values live in `.omo-secrets/`.
- Python scripts are standalone (no package, no shared module); the only cross-file import is `mqtt_takeover.py -> forge_jwt.forge`. Devices in files named `…2/…3/…4` are scratch variants, the highest number is most developed.
- Python deps live in the repo venv `pyenv/` (capstone, pycryptodome, pyelftools, PyJWT, paho-mqtt, passlib); run with `pyenv/Scripts/python.exe`.

## ANTI-PATTERNS
- Never run `exp.sh`/`batch.sh` foreground; use `run-exp-detached.sh` so a dead agent cannot strand the router. Watchdog MUST be armed before hiding `hi5622v100_wifi.ko` / `hi5622v100_plat.ko`.
- `sr-carrier-detached.sh:33` passes literal `stage` to `run-exp-detached.sh`, which requires an existing `.ko` - that wrapper's phase 1 cannot work as written. Prefer `exp.sh` + `batch.sh`.
- `run-exp-detached.sh:31-37` `restore()` is dead code and its scp at `:87` skips the md5 verify that `exp.sh` does.
- `restore-now.sh:5` removes only 4 hardcoded `.ko` names - other staged modules survive.
- 16 of the `.py` files hardcode `C:/Users/ShibbityShwab/...` paths and execute at import (no `__main__` guard) - they only run on this checkout.
- `dump_payload.py` is unrelated to firmware work (reads an `.omo` agent transcript) and writes `.tmp_payload_*.txt` into the repo root; `try_guess.py`, `bdinfo_sweep*.py`, `cryptbrute*.py`, `cryptdis*.py`, `dis_bootreg*.py`, `find_refs.py` are superseded scratch.
- `tftp_server.py` binds `0.0.0.0` with no auth and writes any WRQ under `tftp/inbox`.
- No flash writes anywhere in this set (no `dd`/`mtd`/`sysupgrade`); recovery is file moves + reboot, so do not invent one.
