# PROJECT KNOWLEDGE BASE

**Generated:** 2026-10-02
**Commit:** 9c8514b
**Branch:** master

## OVERVIEW
Offensive-research notebook for a **Cudy WR3000 v2.0** router (HiSilicon "luofu", OpenWrt 22.03.6, kernel 5.10.201): web-UI RCE writeup, firmware unpacking/crypto tooling, and a live device experiment pipeline for snarfing a Wi-Fi chip out of the stock firmware. Not a buildable product - a tool + evidence repo. The published half lives in the `opensource/` submodule.

## STRUCTURE
```
cudy-wr3000v2/
├── tools/        # experiment harness (.sh), crypto/RE CLIs (.py), js probes; the working surface
├── patched/      # de-crypted stock LuCI bytecode (LuaQ) - injection sinks, NOT source
├── opensource/   # git SUBMODULE -> cudy-wr3000v2-open-firmware (docs/lab/build, GH Actions)
├── wordlists/    # Git LFS pointers only (14 bytes each) - not real wordlists
├── START-HERE.md PLAN-UART.md mem-entries.md gist-*.md   # handoff docs; read these first
├── tmp_manifest.txt rpc_inj.json                          # generated artifact / raw payload
└── {build,dumps,firmware,stock,rootfs-*,decomp,pages,pyenv,jtools,tftp,ulw}/  # IGNORED
```

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| Run a module experiment | `tools/exp.sh` | arms device watchdog first; prints `EXP RESULT: PASS\|FAIL` |
| N hypotheses, one boot | `tools/batch.sh` | list format `<label>\|<params>`; report in evidence dir |
| Survive agent death | `tools/run-exp-detached.sh` | older path; the `sr-carrier-detached.sh` wrapper is likely stale |
| Undo experiment | `tools/restore-now.sh` | unhides vendor mods, rm loaders; then reboot |
| Calibration safety | `tools/wifi-cal-snapshot.sh` / `wifi-cal-restore.sh` | snapshot BEFORE experiments; restore is dry-run by default |
| bdinfo secret | `tools/decrypt_bdinfo.py` | DES-CBC; yields fleet `secret` + `deviceid` |
| MQTT/JWT takeover | `tools/forge_jwt.py` -> `tools/mqtt_takeover.py` | passive by default; `--cmd` publishes |
| Unpack firmware | `tools/extract_firmware.py` | hboot1tag -> uImage -> UBI -> squashfs |
| Read Lua bytecode | `tools/luadump.py` | Lua 5.1 disassembler; used on `patched/*.lua` |
| Injection payload | `rpc_inj.json` | `login` params carry `x'; echo PWN1 > ...` |
| Build the .ko | `opensource/.github/workflows/build-load-test-module.yml` | no local ARM toolchain |
| Research narrative | `opensource/docs/phase*/` | phase19-22 = PCIe/HCC bring-up |

## CODE MAP
No LSP applies (shell + standalone python + Lua bytecode). Centrality by reference:

| Symbol / file | Type | Location | Refs | Role |
|---------------|------|----------|------|------|
| `exp_run` / `exp_arm_recovery` | shell fns | tools/exp.sh:517 / :219 | 4 | device cycle engine; sourced by batch.sh |
| `parity` + DES string-to-key | python fn | 6 copies (decrypt_bdinfo.py:31/41 keeper) | 6 | bdinfo crypto |
| `forge` | python fn | tools/forge_jwt.py:34 | 1 | only cross-file .py import (mqtt_takeover.py:25) |
| movw/movt resolver | python fn | 4 copies (dis_bootreg2.py:9) | 4 | ARM ref resolution |
| `rpc_auth` / `action_backup` | luci handler | patched/rpc.lua, patched/backup.lua | - | injection surface |

## CONVENTIONS
- Tracked text carries **placeholders only**: `<ROUTER-SSH-PASSWORD>`, `<ROUTER-WEB-PASSWORD>`, `<DEVICE-SECRET>`. Live values come from gitignored `.omo-secrets/` or the environment at runtime.
- `tools/*.sh` call the device through `.sshwrap/rsh.sh` and `.sshwrap/rscp.sh` - never raw ssh.
- Long device runs go DETACHED and the device-side watchdog is armed BEFORE vendor modules are hidden.
- Experiment evidence lands in `build/register-dumps/exp/<UTC-timestamp>/` (or `.../detached/`), never in the repo root.
- `--dry-run` is expected on harness scripts and prints the exact ssh/scp shape without touching anything.
- Scratch variants keep a `…2/…3/…4` suffix; the highest number is the most developed.

## ANTI-PATTERNS (THIS PROJECT)
- Never write CA `0x400392f0`. Never read the RC misc window `0x10161000` (a read-only `devmem` there PANICKED the box). Measure through the endpoints' BAR0/BAR2 only. Never `rmmod` the vendor modules.
- Never commit a real credential: no keys, passwords, or per-unit values in tracked text (they were scrubbed before the first commit).
- Never run the device cycle in the foreground - a dead agent strands the router in takeover config with Wi-Fi down.
- Never restore calibration without first verifying `MANIFEST.sha256` against a snapshot.
- Never `rm -rf` or hand-edit `.omo-secrets/`, `.sshwrap/`.
- Leave the router healthy: 2 wiphys, 6 interfaces, calibration `[SUCC]` on both bands, no `.omo-off` leftovers.

## UNIQUE STYLES
- The whole research log is a **timestamped markdown ledger**: `mem-entries.md` (phases + hazards), `opensource/docs/phaseNN/*.md` (per-experiment reports), `START-HERE.md` (operational handoff). Update the ledger, not the code comments, with findings.
- Discoveries are described as register-level observations with the evidence path (e.g. `docs/phase19/release-attempts.md`), never as conclusions alone.
- `patched/*.lua` are annotated **bytecode dumps**; treat their content as data, not source.

## COMMANDS
```bash
bash tools/exp.sh --dry-run <module.ko> [params]      # verify the cycle without touching the device
bash tools/exp.sh <module.ko> [params]                # full cycle -> EXP RESULT: PASS|FAIL
bash tools/batch.sh tools/batch-hypotheses.example    # N hypotheses in one boot
bash tools/wifi-cal-snapshot.sh                       # BEFORE any experiment
pyenv/Scripts/python.exe tools/decrypt_bdinfo.py dumps/bdinfo.bin
pyenv/Scripts/python.exe tools/extract_firmware.py <image.bin> --out rootfs-2.4.15
pyenv/Scripts/python.exe tools/luadump.py patched/system.lua -c | grep -n 'date -s'
```

## NOTES
- There is no build step and no test suite for the repo itself; `tools/tftp_test.py` is the only test file.
- `tools/tftp_server.py` is an unauthenticated UDP server that writes uploads into `tftp/inbox` - local lab only.
- `tmp_manifest.txt` is a generated sha256 manifest of the device's `/lib/modules/5.10.201/*.ko`; do not hand-edit.
- `wordlists/*.txt` are 14-byte Git LFS pointers; the real lists are not resolvable from a plain checkout.
- Python tooling targets the repo-local venv (`pyenv/`) where capstone, pycryptodome, pyelftools, PyJWT, paho-mqtt and passlib are already installed.
- Everything under `build/ dumps/ firmware/ stock/ rootfs-*/ decomp/ pages/ jtools/ ulw/ tftp/` is gitignored local state - it may be large or absent, and code that assumes it will fail on a fresh clone.
