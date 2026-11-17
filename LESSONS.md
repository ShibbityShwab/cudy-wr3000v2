# Lessons

Durable rules from the ledger. Each one cost at least one fire, one stranded box, or one wrong
conclusion. Read before a device action.

1. **A fire must prove its own validity.** Check that the boot actually happened, that the slot
   identity is unchanged, and that the crumb was sampled inside the window. Every ambiguous
   result in this project came from missing one of those three.

2. **A single sample cannot prove "no change".** Use the same n>=5 rate test before claiming a
   fix did nothing.

3. **Compare like with like.** A whole-image md5 and a first-1-MB md5 are different numbers.

4. **Read the provenance, not just the value.** A cell is evidence only when you know its last
   writer. `0xC0DE502D` is our tick; `0xC0DE5004` is our step-4 crumb.

5. **An unowned cell is not a safe cell.** "No driver writes it" says nothing about what the
   address does in hardware. Three marks on unowned sysctrl cells stranded the box on 2026-11-01.

6. **A self-test that reads its own write buffer is circular.** The FMC write self-test compared
   against a buffer copied from the same source, so `mismatches = 0` was guaranteed.

7. **Declaration order matters.** Moving a block means moving all of it.

8. **`make zImage` does not rebuild the DTB.** Run `make dtbs`.

9. **Presence is not scope.** A symbol present in the source is not proof it is linked, enabled,
   or reachable in the built artifact. Check the image, not the tree.

10. **A mount can fail silently.** A read-only `/vendor` looks like a code regression until you
    read the mount flags and the errno. Tag the errno into a cell before the writes. (The mount
    itself was later cleared; the rule stays.)

11. **A shadow of a vendor script must be a filtered copy, never a replacement.**
    `/etc/rc.d/luofu` starts with `hi_kpinctrl`; removing it loses pinmux, MDIO, Ethernet,
    and Wi-Fi. `tools/check-init-shadow.sh` is the gate.

12. **Vendor modules need `.plt` sections and a near allocation.** Add zero-size
    `.plt`/`.init.plt` with `objcopy`; do not teach the loader to tolerate their absence.

13. **Procd owns the watchdog.** Kernel-side petting is a debugging shim, not a fix.

14. **A fallback to the vendor slot leaves `boot_reg = 0x10` and the box on slot A.** Wi-Fi then
    reads 0 wiphys; that is a consequence of the fire, not a separate fault.

15. **The forbidden list is absolute.** Never write CA `0x400392f0`; never read the RC misc
    window `0x10161000`; never `rmmod` the vendor modules.

16. **The latest dated ledger entry wins.** The ledger is append-only; a correction 2,000 lines
    later supersedes the hypothesis above it. Read the index and the tail.

17. **UART is READ-ONLY on this bench (2026-11-16).** Router TX reaches the host with the swapped
    pins; the host-to-router TX path is dead (burnt resistor) and repair is out of scope. No
    typing, no `echo`/`printf` to the tty, no `screen`/`minicom`, no U-Boot abort-key
    floods, no read-write tty open (the `3<>` form). Capture read-only with
    `tools/uart-capture.sh`. The U-Boot prompt is
    unreachable and must not be chased.

18. **The bench NIC is a USB Ethernet adapter on the router's eth2 port (2026-11-16).**
    `enp195s0f3u1` must stay NetworkManager-unmanaged and carry `192.168.1.88/24` (TFTP
    recovery) and `192.168.10.44/24` (vendor LAN). Managed, it strips the addresses and the
    board's ARP dies with `ARP Retry count exceeded`. `tools/bench-link.sh`.

19. **Recovery is physical; every fire is human-attended (2026-11-16).** The trigger is the
    RESET-button counter on a true power-on reset, then TFTP from `192.168.1.88`. An agent cannot
    power-cycle or hold RESET. Write the recovery plan **before** the fire, arm the door, and keep
    a human at the bench. A fire that strands the box costs hands-on work, not a retry.

20. **Our uImage is uncompressed; `Uncompressing Linux` is the STOCK marker (2026-11-16).**
    A fire reading is ours only when U-Boot prints our `Image Name: Linux-5.10.201` + our
    `Data Size` (2.96 MB class) and our kernel output follows. `Uncompressing Linux` +
    `Data Size: 4,294,096` is the stock fallback boot; a panic in that boot is not our bug.
    The old rule "the capture must show Uncompressing for our image" was wrong.

21. **A slot write needs a validated slot pair and a measured handover register (2026-11-16).**
    `MTD` (name) and `MTD_DEV` (device) were independent: `MTD=kernela` erased `/dev/mtd12`
    (kernelb) and wrote kernela, destroying the fallback slot. Derive the device from the name,
    validate `/proc/mtd`, and never invent a `boot_reg` value. `tools/fire-device.sh`.

22. **Leftovers are hazards, not harmless state (2026-11-16/17).** A broker HTTP server had been
    serving the repository root (including `.omo-secrets`) on the LAN for over a day, and a
    fire-log writer was still running. End every session with `tools/bench-teardown.sh`, and
    decide deliberately whether the TFTP recovery door stays armed.

23. **A stale "current work" paragraph is worse than no paragraph (2026-11-16).** Two days of
    work chased a retired blocker because `AGENTS.md` restated status. Auto-loaded instruction
    files hold rules and pointers only; `STATUS.md` is the single live state page.

24. **U-Boot printing our uImage header is not proof our kernel ran (2026-11-17).** The 3dh
    capture reads as "the loader rejected our image" or "the vendor stack loaded", but the kernel
    never executed. Identify a kernel by its own markers - our `luofu-fmc`/`luofu-gmac`
    banners, our init's `luofu: seed test` lines, our driver probes - never by the stock
    fallback's `Uncompressing Linux` or by a panic that the stock fallback also produces. The
    3dh "vendor stack loaded" claim was a stock boot misattribution.

25. **No kernel output after the handoff means a pre-console crash, not a quiet success
    (2026-11-17).** This kernel registers its console at ~2.6 s and the fired cmdline's bare
    `earlycon` does not resolve, so everything before 2.6 s is lost. A silent reset is a crash in
    that window. Diagnose with a `CONFIG_CMDLINE_EXTEND` earlycon build (and DEBUG_LL if needed)
    before reading anything into the silence.

26. **The kernel `.config` is part of the artifact (2026-11-17).** 3df and 3dg booted; 3dh, built
    from identical kernel C source, the same DTB and the same trailer, does not. The only delta
    was the `.config` group captured in `cca5be5` (COMPILE_TEST, SLAB, TRACING/FTRACE,
    FRAME_POINTER/UNWINDER). Record the config with every slice and treat a config change as a
    fire-class variable, not a build detail.
