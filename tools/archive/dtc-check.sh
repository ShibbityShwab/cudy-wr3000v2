#!/usr/bin/env bash
# dtc-check.sh - rerunnable wrapper around the dtc recipe in
# build/tmp/inta-spec/dtc.md (upstream dtc v1.7.2 built with MinGW gcc).
#
# Usage: tools/dtc-check.sh <dts-file> [out.dtb]
#   Preprocesses <dts-file> with cpp, compiles it with dtc.exe (-I dts -O dtb),
#   prints the resulting dtb size + sha256 on success, the compiler error with
#   line numbers on failure.
#
# Exit codes: 0 = compiled (warnings allowed), 1 = compile error, 2 = usage/setup.
set -u

usage() { echo "usage: $0 <dts-file> [out.dtb]" >&2; exit 2; }
[ $# -ge 1 ] || usage
DTS="$1"
[ -f "$DTS" ] || { echo "dtc-check: no such dts file: $DTS" >&2; exit 2; }

REPO="$(cd "$(dirname "$0")/.." && pwd)"
BASE="$(basename "$DTS")"
OUT="${2:-$REPO/build/tmp/inta-spec/${BASE%.dts}.dtb}"
mkdir -p "$(dirname "$OUT")"

DTC="$(command -v dtc.exe || command -v dtc || true)"
if [ -z "$DTC" ]; then
  DTC="$(ls /tmp/dtcbuild/dgibson-dtc-*/dtc.exe 2>/dev/null | head -n1)"
fi
if [ -z "$DTC" ] || [ ! -x "$DTC" ]; then
  echo "dtc-check: dtc.exe not found (PATH or /tmp/dtcbuild/dgibson-dtc-*/dtc.exe)." >&2
  echo "dtc-check: rebuild per the build recipe in build/tmp/inta-spec/dtc.md" >&2
  exit 2
fi
command -v cpp >/dev/null || { echo "dtc-check: cpp not on PATH" >&2; exit 2; }

echo "dtc-check: tool   = $DTC ($("$DTC" --version 2>&1 | head -n1))"
echo "dtc-check: source = $DTS"
echo "dtc-check: output = $OUT"

PP="$(mktemp -t dtccheck.XXXXXX).pp.dts"
LOG="$(mktemp -t dtccheck.XXXXXX).log"
trap 'rm -f "$PP" "$LOG"' EXIT
cpp -nostdinc -undef -x assembler-with-cpp "$DTS" "$PP" || { echo "dtc-check: cpp preprocessing failed" >&2; exit 2; }

"$DTC" -I dts -O dtb -o "$OUT" "$PP" 2>"$LOG"
rc=$?
cat "$LOG"

if [ $rc -ne 0 ] || [ ! -s "$OUT" ]; then
  echo "dtc-check: FAIL (dtc exit $rc) - see errors above" >&2
  exit 1
fi

sz=$(stat -c %s "$OUT" 2>/dev/null || wc -c < "$OUT")
sha=$(sha256sum "$OUT" | cut -d' ' -f1)
errs=$(grep -ci '^Error' "$LOG" 2>/dev/null); errs=${errs:-0}
warns=$(grep -c 'Warning' "$LOG" 2>/dev/null); warns=${warns:-0}
echo "dtc-check: PASS  size=$sz bytes  sha256=$sha  errors=$errs warnings=$warns"
exit 0
