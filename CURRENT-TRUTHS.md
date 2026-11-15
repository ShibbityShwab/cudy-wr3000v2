# Current truths (2026-11-15)

Curated summary. The ledger is the long form; the latest dated entry wins.

- The live status page is `STATUS.md`; the procedure is `RUNBOOK.md`.
- G1 through G4 and G6 are green as of 2026-11-14; G5 is vendor-only.
- Current blocker: the initramfs `/vendor` mount can be read-only on this strap, so
  shadow writes are silent. The 2026-11-15 04:10 entry names the rw-mount fix; the
  `phase3de` slice was assembled after it and is unverified.
- The latest dated entry wins over any earlier claim. The ledger is append-only.
- The old Wi-Fi reversal wall (phase 48) is history, not the current blocker.
- Calibration snapshot before any experiment; never restore without a verified
  `MANIFEST.sha256`.
