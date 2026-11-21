# RUNBOOK - build, fire, read, recover

The kernel lane on the bench box. The old Wi-Fi module lane moved to `tools/archive/`; it
is history and must not be used for kernel work.

**Before anything:** `BENCH-FACTS.md` (physical invariants), `STATUS.md` section 4 (the
only source of a delivery plan), `LESSONS.md`. If `STATUS.md` does not name a delivery
plan, there is no fire; only preparation and reading.

## 0. Preconditions and gate

- Bench link PASS: `tools/bench-link.sh` (adapter unmanaged, both addresses, carrier up).
- Recovery door READY: `tools/recovery-card.sh` (recovery.bin md5, host 192.168.1.88,
  TFTP on UDP 69) and a human who can power-cycle the box and hold RESET.
- Read-only UART capture armed: `tools/uart-capture.sh start --label <label>`.
- Box reachable: `tools/session-brief.sh` (vendor stock must show 2 wiphys, calibration
  `[SUCC]`, no `.omo-off`).
- Fire gate: `tools/fire-preflight.sh --slice <slice> --slot a|b --attended` must PASS.
  `tools/fire.sh` runs it automatically and refuses on failure.
- Kernel tree `build/linux-kbuild/linux-5.10.201` (gitignored, source of truth), toolchain
  `build/linux-kbuild/toolchain/bin/arm-none-linux-gnueabihf-`, Python via
  `.provision-venv/bin/python`.
- The shadow guard must pass before any fire: `tools/check-init-shadow.sh`. It is a
  **source-level** guard (the shadow must keep `hi_kpinctrl` and the switch); it is not an
  artifact proof.

## 1. Build

```sh
KB="$PWD/build/linux-kbuild"
SRC="$KB/linux-5.10.201"
cd "$SRC"
make ARCH=arm CROSS_COMPILE="$KB/toolchain/bin/arm-none-linux-gnueabihf-" \
  -j16 zImage dtbs < /dev/null
```

`make zImage` does not rebuild the DTB. Run `dtbs` explicitly; a stale DTB was a real defect.

## 2. Assemble the slice

The current pattern is `build/linux-kbuild/build-3dl.sh` (3dh DTB + 3dk init). The generic
shape is:

```sh
cat arch/arm/boot/zImage arch/arm/boot/dts/luofu-r116.dtb > "$KB/phase-payload.bin"
mkimage -A arm -O linux -T kernel -C none \
  -a 0x80608000 -e 0x80608000 -n Linux-5.10.201 \
  -d "$KB/phase-payload.bin" "$KB/phase-uImage.bin"
cat "$KB/phase-uImage.bin" "$KB/slice-trailer-40732.bin" > "$KB/luofu-slice-phaseX.bin"
tail -c 40732 "$KB/luofu-slice-phaseX.bin" | cmp - "$KB/slice-trailer-40732.bin"
```

The 40,732-byte trailer is fixed FIP/DTBO evidence (`slice-trailer-40732.bin`, sha256
`336b07920e915fac30c3b90d57925b880d430ac7ed94a81963d52af10c102953`). It is local evidence,
not published (vendor-derived). **Never rebuild it from an arbitrary slice**; if it is
missing, rebuild and validate from a known stock image, and fail closed rather than writing an
unvalidated slice.

## 3. Guard

```sh
tools/check-init-shadow.sh    # must print PASS
```

## 3a. Calibration

```sh
tools/wifi-cal-snapshot.sh
```

It writes `build/linux-kbuild/cal-snapshots/<TS>/` with `MANIFEST.sha256`. A snapshot that
could not pull every payload file is marked `FACTORY_CAL_STATUS` = incomplete; the restore
script refuses it. Restore is a dry run by default:

```sh
tools/wifi-cal-restore.sh build/linux-kbuild/cal-snapshots/<TS>
```

`--apply` is allowed only after the script's own manifest check passes. Never bypass it.

## 4. Fire

Only after `STATUS.md` section 4 names the delivery plan and preflight PASSes. Device cycles
are always detached, attended, and one variable.

### SSH lane (slot decision explicit)

```sh
tools/fire.sh ssh --slice "$PWD/build/linux-kbuild/luofu-slice-phaseX.bin" \
  --label phaseX --slot b --attended --detach
tools/fire.sh status phaseX
```

- Slot B: `MTD=kernelb`, `/dev/mtd12`, `bootflag=b`, `boot_reg=0x21` (the only manual
  handover value established on this board).
- Slot A: requires a measured `BOOT_REG=<value>` from a written plan. `fire.sh` refuses
  without it, and `fire-device.sh` refuses before erasing. Never invent the value.
- `fire-device.sh` validates the MTD name/device pair before `flash_eraseall` (the old
  one-variable trap erased `kernelb` while writing `kernela`). It prints the target and the
  pre/post `bootflag`/`boot_reg`.
- `fire-ssh.sh` verifies the trailer, forwards the slot env, and only declares the box back
  when `boot_id` changes and uptime is fresh (uptime alone can pass without a reboot).

### Broker lane (no SSH)

```sh
SLICE="$PWD/build/linux-kbuild/luofu-slice-phaseX.bin" \
  tools/fire.sh broker --attended
```

This runs preflight, then `tools/box-provision.sh --stage fire`. The broker lane writes
`kernelb` only, verifies size/md5/trailer, `mtd erase/write/verify`, `bootflag=b`,
`boot_reg=0x21`, and reboots. It serves only `build/linux-kbuild/http-root/` (not the repo
root) on the auto-detected host address (usually 192.168.10.44:8000); the host firewall must
allow TCP 8000 from 192.168.10.0/24. Two old traps: the chain's immediate `mtd verify` can
fail while the box's own verify returns 0 (re-verify); the image has no `/bin/fw_setenv`
(use the `ln -sf /bin/fw_printenv /tmp/fw_setenv` symlink).

### Per-phase lane

`tools/fire.sh run <phase> --detach --attended` is the historical per-phase dispatcher. It
now runs preflight too. Do not add new per-phase scripts without a written plan.

### First install from stock (host-side design; not a fire lane)

The stock-to-image first-install path is documented in
[opensource/docs/FIRST-INSTALL.md](opensource/docs/FIRST-INSTALL.md) and implemented as
`tools/first-install-stock.sh` (read-only by default; writes only with
`--write|--handover|--reboot --attended --recovery-armed --image <container>`; mocked
tests `tools/tests/first-install.test.sh`). It writes only the inactive pair, verifies
both regions with full-region sha256 read-backs and moves the selector last; the env blocks
and the active pair are never written. It has never run on hardware. Read the document
(preconditions, expected loader/UART output, rollback cost, [U] list) before using it; a
`--reboot` is fire-class and still needs the recovery door armed, a read-only UART
capture and a human at the bench.

### First install over the stock telnet shell (verified 2026-11-21)

The bench transport that actually ran is `tools/stock-telnet-install.sh` (fixed in `6e69aa3`):
read-only inspect by default; `--apply --attended --recovery-armed` writes pair **b** only
(kernelb + rootfsb), verifies uploads/read-backs/active-pair-unchanged, sets and reads back the
U-Boot env `bootflag`, moves the selector cell, reboots, and requires the booted cmdline to
contain `ubi.mtd=rootfsb` and the project marker.  Rules learned on the unit:

- after a RESET-hold recovery, set the U-Boot env `bootflag` **together with** the selector
  cell - the loader reads the kernel slot named by the env bootflag, and a cell-only handover can
  mix kernel and rootfs pairs;
- our image's cmdline hardcodes `ubi.mtd=rootfsb`, so it may only be written to pair b;
  pair-a writes after recovery create a mixed our-kernel/stock-rootfs state;
- the broker channel (CVE-2026-71961) only works on a consistent vendor kernel+rootfs pair
  (vendor `/proc/sys/dev/flash_uuid` for bdinfo checkuuid); the mixed state disables both
  the vendor web wizard and cmagent.  Recovery from it is physical RESET-hold + TFTP stock
  image, then a consistent env-bootflag + selector handover.

### Validity (read this before interpreting a capture)

- Ours is an **uncompressed uImage**: U-Boot prints `Image Name: Linux-5.10.201` and our
  `Data Size` (2,964,240 for 3dh, 2,965,176 for 3dk) and **then kernel output**.
- Stock is `Data Size: 4,294,096` and prints `Uncompressing Linux`; that is the fallback
  boot, not us. A stock fallback can also panic (ShuangTa PCIe) - do not attribute that
  panic to our kernel.
- If the box does not return, the recovery plan is already armed (section 6). Do not repeat
  the fire.

## 5. Read the verdict

```sh
tools/fire.sh verdict
```

or read cells directly (read-only):

```sh
ssh -i .omo-secrets/router_ed25519 -o BatchMode=yes \
  -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null root@192.168.10.1 \
  'for c in C04 C18 C1C C70 C88 C90 C94 C98 C9C; do printf "%s=" $c; devmem 0x10100$c 32; done'
```

- `C18` carries the restart path and the init mount tag/errno; `C94` is the main verdict;
  `C88` is the read count; `C9C` is the exec marker.
- A verdict is one value with one last writer. If you do not know the writer, it is not evidence.
- Never read `0x10161000` (a read-only `devmem` there panicked the box).
- No SSH (stock image may lack dropbear): use the broker `--cmd` lane, one line per call, serial.

## 6. Recover

**Rule: every fire has a recovery plan before it starts.** Recovery of an unreachable box is
physical; the agent prepares and the human acts.

### Reachable box, wrong slot/handover

Do not use a plain `fw_setenv` (the stock rootfs has `/bin/fw_printenv` only). Restore the
pair and reboot:

```sh
# on the box, as root
ln -sf /bin/fw_printenv /tmp/fw_setenv
/tmp/fw_setenv bootflag a
echo 0x10 > /sys/devices/platform/sysenv/boot_reg
sync
reboot
```

Verify after reboot: `fw_printenv bootflag` and `cat /sys/devices/platform/sysenv/boot_reg`.
If that does not restore a boot, go to the TFTP recovery.

### Unreachable box: physical RESET + TFTP recovery

```sh
tools/bench-link.sh --apply          # unmanaged adapter + 192.168.1.88/24 + 192.168.10.44/24
tools/recovery-card.sh --arm         # recovery.bin md5 check + TFTP on UDP 69
tools/uart-capture.sh start --label recover   # read-only console
```

Then the human: power the router OFF, hold RESET, power ON still holding. The console prints
`RESET button is pressed for: 0/1/2 second(s)`, `Resetting...`, then
`recovery button press`; the loader TFTPs `recovery.bin` from `192.168.1.88`. Correct
server log: `RRQ recovery.bin` then `RRQ sent 20975775 bytes`. A release before the counter
reaches 2 s boots normally.

After the flash the stock LAN returns at `192.168.10.1`. The overlay is empty: reinstall the
project key and start dropbear with `-R` after deleting the zero-byte host keys. Then verify
2 wiphys, calibration `[SUCC]` both bands, and no `.omo-off` leftovers.

### Restore helpers (device-side)

`tools/restore-now.sh` unhides `.omo-off` files and removes the loader plus four hardcoded
modules; other staged `.ko` can survive, so check the module directory. `tools/restore-vendor.sh`
copies missing stock files from `/rom` and never overwrites. Both run **on the box**; copy them
there and run with `sh`.

## 7. Log, close, and commit

Evidence goes under `build/linux-kbuild/waves/<phase>/` (phase writeups) and
`build/uart-logs/` (console captures); `/tmp` is not evidence. Update `STATUS.md` (state,
blocker, next action) and append a dated entry to `mem-entries.md`; regenerate
`mem-entries-INDEX.md` with `python3 tools/gen-ledger-index.py`. Then run
`tools/check-repo.sh`, restart `tools/bench-teardown.sh --apply` cleanup decision, and
commit. A session that changes a live doc without an entry is incomplete.

## Safety

- Never run a device cycle in the foreground; never fire unattended.
- Never write a flash slot without a written plan, preflight PASS, and a READY recovery door.
- Never transmit on the UART.
- Never write CA `0x400392f0`; never read the RC misc window `0x10161000`; never `rmmod`
  the vendor modules.
- Never flash a WR3000 v1 image.
- Never commit credentials or vendor binaries; tracked text carries placeholders only.
