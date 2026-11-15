#!/bin/sh
# sync-lab-src.sh - copy the live kernel modifications into the tracked snapshot.
#
# The live tree is build/linux-kbuild/linux-5.10.201 (gitignored). The tracked
# mirror is tools/lab-src. Run this after editing the live tree, then commit the
# snapshot. tools/check-lab-src.sh verifies the result.
set -eu

ROOT=$(cd "$(dirname "$0")/.." && pwd)
SNAP="$ROOT/tools/lab-src"
SRC="$ROOT/build/linux-kbuild/linux-5.10.201"
KB="$ROOT/build/linux-kbuild"

[ -d "$SRC" ] || { echo "missing build tree: $SRC" >&2; exit 1; }
[ -f "$SNAP/FILES" ] || { echo "missing manifest: $SNAP/FILES" >&2; exit 1; }

n=0
while IFS= read -r rel; do
    [ -n "$rel" ] || continue
    mkdir -p "$SNAP/$(dirname "$rel")"
    cp "$SRC/$rel" "$SNAP/$rel"
    n=$((n + 1))
done < "$SNAP/FILES"

mkdir -p "$SNAP/kbuild" "$SNAP/config"
cp "$KB/init-vendorroot.c" "$SNAP/kbuild/init-vendorroot.c"
cp "$SRC/.config" "$SNAP/config/kernel.config"
sed -i 's|^CONFIG_INITRAMFS_SOURCE=.*|CONFIG_INITRAMFS_SOURCE="../initramfs-site.cpio"|' "$SNAP/config/kernel.config"

echo "synced $n files plus kbuild/init-vendorroot.c and a sanitized config/kernel.config"
