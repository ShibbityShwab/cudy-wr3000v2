# Start here

Work from THIS directory. Earlier sessions ran in the user home directory, which is not a git
checkout, so `task.isolation.enabled` could never apply and DAG nodes / isolated swarms were refused.
From this repo they work.

    cd C:/Users/ShibbityShwab/Documents/GitHub/cudy-wr3000v2

## Layout

- `tools/` - `exp.sh` (one full device cycle), `batch.sh` (N hypotheses in ONE boot),
  `run-exp-detached.sh` (survives agent death), `restore-now.sh` (returns the router to stock),
  `wifi-*.sh`, `wifictl.sh`
- `opensource/` - git SUBMODULE -> `ShibbityShwab/cudy-wr3000v2-open-firmware` (the published
  payload: `docs/phase*/` analyses, `lab/` modules, `.github/workflows` build job)
- `build/`, `dumps/`, `firmware/`, `stock/`, `rootfs-*/`, `decomp/`, `pyenv/`, `jtools/` - ignored:
  binaries and dumps
- `.omo-secrets/` - ignored: `CREDENTIALS.txt`, the router SSH keys, scratch u-boot files

## Secrets

Tracked text carries markers only: `<ROUTER-SSH-PASSWORD>`, `<ROUTER-WEB-PASSWORD>`,
`<DEVICE-SECRET>`. Read the live value from `.omo-secrets/` (or the environment) at runtime; never
paste one back into a file git tracks. Build an askpass at runtime rather than storing one.

## Device experiments

    bash tools/exp.sh <module.ko> [params]        # full cycle, prints EXP RESULT: PASS|FAIL
    bash tools/batch.sh <list>                   # N hypotheses, ONE boot, per-entry result.txt

Run the device cycle DETACHED (`tools/run-exp-detached.sh`) so a dead agent cannot strand the router
in takeover configuration with Wi-Fi down. The router-side watchdog must be armed BEFORE hiding the
vendor modules; that ordering is enforced in the runner.

## Builds

No local ARM toolchain: push to a feature branch and let the GitHub Actions job build the `.ko`
(`opensource/.github/workflows/build-load-test-module.yml`). `gh.exe` is at `~/.local/gh/gh.exe`.

## Hard rules

- Never write CA `0x400392f0`. Never read the RC misc window `0x10161000`. Never rmmod the vendor
  modules.
- Router must end healthy: 2 wiphys, 6 interfaces, calibration `[SUCC]` on both bands, no `.omo-off`
  leftovers.
