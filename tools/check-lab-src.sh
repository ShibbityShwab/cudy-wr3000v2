#!/bin/sh
# check-lab-src.sh - fail if the tracked kernel snapshot has drifted from the live tree.
#
# The live tree is build/linux-kbuild/linux-5.10.201 (gitignored). The tracked
# mirror is tools/lab-src. This check is the guard against restoring an old MDIO,
# Kconfig, Makefile, or init from the snapshot.
set -eu

MODE=${1:-}
ROOT=$(cd "$(dirname "$0")/.." && pwd)
SNAP="$ROOT/tools/lab-src"
SRC="$ROOT/build/linux-kbuild/linux-5.10.201"
KB="$ROOT/build/linux-kbuild"

[ -f "$SNAP/FILES" ] || { echo "FAIL: missing $SNAP/FILES" >&2; exit 1; }
[ -d "$SRC" ] || { echo "FAIL: missing build tree $SRC" >&2; exit 1; }

fail=0
n=0
while IFS= read -r rel; do
    [ -n "$rel" ] || continue
    n=$((n + 1))
    if [ ! -f "$SNAP/$rel" ]; then
        echo "MISSING snapshot: $rel"
        fail=1
        continue
    fi
    if [ ! -f "$SRC/$rel" ]; then
        echo "MISSING build tree: $rel"
        fail=1
        continue
    fi
    if ! cmp -s "$SNAP/$rel" "$SRC/$rel"; then
        echo "DRIFT: $rel"
        fail=1
    fi
done < "$SNAP/FILES"

for pair in "kbuild/init-vendorroot.c:$KB/init-vendorroot.c" "config/kernel.config:$SRC/.config"; do
    s=${pair%%:*}
    t=${pair#*:}
    n=$((n + 1))
    if [ ! -f "$SNAP/$s" ] || [ ! -f "$t" ]; then
        echo "MISSING: $s or $t"
        fail=1
    elif ! cmp -s "$SNAP/$s" "$t"; then
        echo "DRIFT: $s"
        fail=1
    fi
done

if [ "$fail" -eq 0 ]; then
    echo "PASS: $n snapshot files match the build tree"
else
    echo "FAIL: the snapshot is stale; run tools/sync-lab-src.sh" >&2
    exit 1
fi

if grep -q '^CONFIG_INITRAMFS_SOURCE="/' "$SNAP/config/kernel.config"; then
    echo "WARN: config/kernel.config has an absolute CONFIG_INITRAMFS_SOURCE; rewrite it on a new host" >&2
fi

if [ "$MODE" = "--manifest-only" ]; then
    echo "WARN: manifest only; completeness not checked" >&2
else
    "$ROOT/tools/check-lab-src-complete.sh"
fi
