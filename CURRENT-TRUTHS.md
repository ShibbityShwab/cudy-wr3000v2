# Current truths (2026-11-15)

Curated summary. The ledger is the long form; the latest dated entry wins.

- The live status page is `STATUS.md`; the procedure is `RUNBOOK.md`.
- G1 through G4 and G6 are green as of 2026-11-14; G5 is vendor-only.
- Current blocker: the initramfs `/vendor` mount can be read-only on this strap, so
  shadow writes are silent. The 3de fire (2026-11-15 13:33) is negative: `C18=0`
  (the mount errno is clean) and no `boot.log`/`mod-load.log`; the vendor `hi_kphy`
  wins. The 3df slice (the `wfile()` open() instrumentation) was fired at 14:34 and
  never reached flash: the box-side size check failed (`SIZE_FAIL`, 14:38:49), so the
  box never rebooted onto 3df. The shadow writes are undecided, not landed, and why the
  box's file was the wrong size is still open. The receipt is
  `build/linux-kbuild/waves/3df/verify.md`.
- The latest dated entry wins over any earlier claim. The ledger is append-only.
- The old Wi-Fi reversal wall (phase 48) is history, not the current blocker.
- Calibration snapshot before any experiment; never restore without a verified
  `MANIFEST.sha256`.
