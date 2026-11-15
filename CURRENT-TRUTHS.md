# Current truths (2026-11-15)

Curated summary. The ledger is the long form; the latest dated entry wins.

- The live status page is `STATUS.md`; the procedure is `RUNBOOK.md`.
- G1 through G4 and G6 are green as of 2026-11-14; G5 is vendor-only.
- Current blocker: the initramfs `/vendor` mount can be read-only on this strap, so
  shadow writes are silent. The 3de fire (2026-11-15 13:33) is negative: `C18=0`
  (the mount errno is clean) and no `boot.log`/`mod-load.log`; the vendor `hi_kphy`
  wins. The next step is the `wfile()` instrumentation from the 04:10 entry.
- The latest dated entry wins over any earlier claim. The ledger is append-only.
- The old Wi-Fi reversal wall (phase 48) is history, not the current blocker.
- Calibration snapshot before any experiment; never restore without a verified
  `MANIFEST.sha256`.
