# RUNBOOK - build, fire, read, recover

This is the current kernel lane on the bench box. The old Wi-Fi module lane
(`tools/exp.sh`, `tools/batch.sh`) is history; it was built around a `.sshwrap/`
directory that is not in this checkout. A tracked fallback now exists, but the lane is
still historical and is not the kernel cycle.

## 0. Preconditions

- Box reachable at `192.168.10.1`; SSH key `.omo-secrets/router_ed25519`.
- Kernel tree at `build/linux-kbuild/linux-5.10.201` (gitignored, the source of truth).
- Toolchain at `build/linux-kbuild/toolchain/bin/arm-none-linux-gnueabihf-`.
- For the broker lane: `dumps/router-20261108/bdinfo.bin` and
  `tools/box-provision.sh`.
- The guard must pass before any fire: `tools/check-init-shadow.sh`.

## 1. Build

```sh
KB="$PWD/build/linux-kbuild"
SRC="$KB/linux-5.10.201"
cd "$SRC"
make ARCH=arm CROSS_COMPILE="$KB/toolchain/bin/arm-none-linux-gnueabihf-" \
  -j16 zImage dtbs < /dev/null
```

`make zImage` does not rebuild the DTB. Run `dtbs` explicitly; a stale DTB was a real
defect in this project.

## 2. Assemble the slice

```sh
cat arch/arm/boot/zImage arch/arm/boot/dts/luofu-r116.dtb > "$KB/phase-payload.bin"
mkimage -A arm -O linux -T kernel -C none \
  -a 0x80608000 -e 0x80608000 -n Linux-5.10.201 \
  -d "$KB/phase-payload.bin" "$KB/phase-uImage.bin"
cat "$KB/phase-uImage.bin" "$KB/slice-trailer-40732.bin" > "$KB/luofu-slice-phaseX.bin"
tail -c 40732 "$KB/luofu-slice-phaseX.bin" > /tmp/slice-trailer.check
cmp /tmp/slice-trailer.check "$KB/slice-trailer-40732.bin"
```

The 40,732-byte trailer is fixed. Do not rebuild it from an arbitrary slice.

## 3. Guard

```sh
tools/check-init-shadow.sh
```

It must print `PASS`. It checks that the filtered shadow keeps `hi_kpinctrl`, the
switch, and the other load-bearing modules, and drops only `hi_kphy`, `hi_kmdio`, and
`hi_kmac`. A wholesale replacement of `/etc/rc.d/luofu` took the box off the network
once. Do not repeat it.

## 3a. Calibration

Before any experiment:

```sh
tools/wifi-cal-snapshot.sh
```

It writes `build/linux-kbuild/cal-snapshots/<TS>/` with `MANIFEST.sha256`. Restore is
a dry run by default:

```sh
tools/wifi-cal-restore.sh build/linux-kbuild/cal-snapshots/<TS>
```

`--apply` is allowed only after the manifest check passes. The restore script performs
that check itself; never bypass it.

## 4. Fire

### SSH lane

```sh
tools/fire.sh run <phase> --detach
tools/fire.sh status <phase>
```

`run` executes the existing `build/linux-kbuild/run-phase<phase>.sh` detached and
writes a log. Those per-phase scripts are gitignored; the dispatcher is the stable
entry point.

### Broker lane (no SSH)

```sh
SLICE="$PWD/build/linux-kbuild/luofu-slice-phaseX.bin" \
  tools/box-provision.sh --bdinfo dumps/router-20261108/bdinfo.bin --stage fire
```

The broker lane serves the slice from the host, has the box `wget` it, verifies the
trailer, size, and md5, writes `kernelb`, runs `mtd verify`, sets `bootflag=b`, and
reboots. It also runs the guard internally. These verification steps are code-reviewed
and dry-run checked, not device-verified; the first fire after this change validates
them.

The SSH lane's per-phase run scripts are bench-local. A fresh clone has no run script;
use the broker lane, or add a tracked host driver before relying on `fire.sh run`.
To refresh the patched vendor modules first:

```sh
tools/box-provision.sh --bdinfo dumps/router-20261108/bdinfo.bin --stage lab
```

## 5. Read the verdict

```sh
tools/fire.sh verdict
```

or directly, read-only:

```sh
ssh -i .omo-secrets/router_ed25519 \
  -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
  root@192.168.10.1 \
  'for c in C04 C18 C1C C70 C88 C90 C94 C98 C9C; do printf "%s=" $c; devmem 0x10100$c 32; done'
```

- `C18` carries the restart path and the init mount tag/errno.
- `C94` is the main verdict cell.
- `C88` is the read count.
- `C9C` is the exec marker.

A verdict is one value with one last writer. If you do not know the writer, the value
is not evidence. Never read `0x10161000`; a read-only `devmem` there panicked the box.

## 6. Recover

- Vendor slot, reachable: `fw_setenv bootflag a` and reboot.
- Vendor slot, broker only: `tools/box-provision.sh --bdinfo ... --stage base`.
- Unreachable: hold RESET during power and TFTP-boot `recovery.bin` from
  `192.168.1.88`. Serve it with `sudo python3 tools/tftp_server.py 69` (port 69 is
  privileged); the official image is `tftp/recovery.bin`. The stock LAN comes up at
  `192.168.10.1`.
- On the device, `tools/restore-now.sh` unhides `.omo-off` files and removes the
  loader plus four hardcoded modules. Other staged `.ko` files can survive; check the
  module directory. `tools/restore-vendor.sh` restores missing stock files from `/rom`
  and never overwrites.

After recovery, verify: 2 wiphys, 6 interfaces, calibration `[SUCC]` on both bands, and
no `.omo-off` leftovers.

## 7. Log

Evidence goes under `build/linux-kbuild/evidence/` (the old `build/register-dumps`
path is historical and not writable on this checkout). Append a dated entry to
`mem-entries.md` with the phase, the result, and the evidence path. If the claim
matters beyond the session, add it to `EVIDENCE-INDEX.md` with a regeneration command.
Refresh the index with:

```sh
python3 tools/gen-ledger-index.py
```

## Safety

- Never run a device cycle in the foreground.
- Arm the device watchdog before hiding vendor modules.
- Never `rmmod` the vendor modules.
- Never write CA `0x400392f0`; never read the RC misc window `0x10161000`.
- Never flash a WR3000 v1 image.
- Never commit credentials; tracked text carries placeholders.
