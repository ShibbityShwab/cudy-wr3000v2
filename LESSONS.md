# Lessons

Durable rules from the ledger. Each one cost at least one fire or one wrong conclusion.

1. **A fire must prove its own validity.** Check that the boot actually happened, that
   the slot identity is unchanged, and that the crumb was sampled inside the window.
   Every ambiguous result in this project came from missing one of those three.

2. **A single sample cannot prove "no change".** Use the same n>=5 rate test before
   claiming a fix did nothing. One pair of runs cannot separate "intermittent" from
   "one measurement was invalid".

3. **Compare like with like.** A whole-image md5 and a first-1-MB md5 are different
   numbers. A verification that compares them declares every run VOID.

4. **Read the provenance, not just the value.** A cell is evidence only when you know
   its last writer. `0xC0DE502D` is our tick; `0xC0DE5004` is our step-4 crumb.

5. **An unowned cell is not a safe cell.** "No driver writes it" says nothing about
   what the address does in hardware. Three marks on unowned sysctrl cells stranded the
   box on 2026-11-01.

6. **A self-test that reads its own write buffer is circular.** The FMC write self-test
   compared against a buffer copied from the same source, so `mismatches = 0` was
   guaranteed. That is why the flash question survived several windows.

7. **Declaration order matters.** Moving a block means moving all of it, and a build
   can fail on function order in a way a source grep cannot catch.

8. **`make zImage` does not rebuild the DTB.** Run `make dtbs`. A stale DTB disabled
   four MAC nodes in every image for a day.

9. **Presence is not scope.** A symbol present in the source is not proof it is linked,
   enabled, or reachable in the built artifact. Check the image, not the tree.

10. **A mount can fail silently.** A read-only `/vendor` looks like a code regression
    until you read the mount flags and the errno. Tag the errno into a cell before the
    writes.

11. **A shadow of a vendor script must be a filtered copy, never a replacement.**
    `/etc/rc.d/luofu` starts with `hi_kpinctrl`; removing it loses the pinmux, MDIO,
    Ethernet, and Wi-Fi. `tools/check-init-shadow.sh` is the gate.

12. **Vendor modules need `.plt` sections and a near allocation.** Add zero-size
    `.plt`/`.init.plt` with `objcopy`; do not teach the loader to tolerate their
    absence. The tolerant loader broke the boot 5/5 while the controls booted 3/3.

13. **Procd owns the watchdog.** Kernel-side petting is a debugging shim, not a fix.
    The vendor init hands the watchdog fd to procd through `WDTFD`.

14. **A fallback to the vendor slot leaves `boot_reg = 0x10` and the box on slot A.**
    Wi-Fi then reads 0 wiphys. That is a consequence of the fire, not a separate fault.

15. **The forbidden list is absolute.** Never write CA `0x400392f0`; never read the RC
    misc window `0x10161000`; never `rmmod` the vendor modules.

16. **The latest dated ledger entry wins.** The ledger is append-only; a correction
    2,000 lines later supersedes the hypothesis above it. Read the index and the tail,
    not the first occurrence of a claim.
