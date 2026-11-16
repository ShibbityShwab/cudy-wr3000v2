# Current truths (2026-11-16)

Curated summary. The ledger is the long form; the latest dated entry wins.

- The live status page is `STATUS.md`; the procedure is `RUNBOOK.md`.
- G1 through G4 and G6 are green as of 2026-11-14; G5 is vendor-only.
- The PLT gate no longer blocks the vendor stack on this board: the patched module set (zero-size
  `.plt`/`.init.plt`, `tools/box-provision.sh --stage lab`) plus the near-region `module_alloc`
  loads it, and 3dh's capture shows `eth2` up at 1Gbps (`Hi-GEMAC`, `Hisilicon Genius Phy`).
  The 3df boot at 05:32 that refused every module had the unpatched set.
- Open item: the box is unreachable after each of today's fires while the stack loads, so the
  question is what stops eth2 in the same boot, not whether the modules load.
- 3dk (built, not fired) prints one `<6>load <mod> fd=.. ret=..` kmsg line per vendor module, so a
  single console capture carries the loader verdict: `build/linux-kbuild/waves/3dk/build.md`.
- The console reads only with the swapped UART pins; captures write to an absolute path.
- The latest dated entry wins over any earlier claim. The ledger is append-only.
- The old Wi-Fi reversal wall (phase 48) is history, not the current blocker.
- Calibration snapshot before any experiment; never restore without a verified
  `MANIFEST.sha256`.
