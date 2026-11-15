#!/bin/sh
# check-lab-src-complete.sh - verify FILES covers every modified kernel source.
#
# check-lab-src.sh only compares the paths listed in FILES. This check diffs the
# live tree against an unmodified 5.10.201 tree and fails if any modified or added
# source file is missing from FILES. Set VANILLA_TREE, or let it extract the
# tarball under build/linux-kbuild/dl/.
set -eu

ROOT=$(cd "$(dirname "$0")/.." && pwd)
SNAP="$ROOT/tools/lab-src"
SRC="$ROOT/build/linux-kbuild/linux-5.10.201"
TARBALL="$ROOT/build/linux-kbuild/dl/linux-5.10.201.tar.xz"

[ -d "$SRC" ] || { echo "FAIL: missing build tree $SRC" >&2; exit 2; }
[ -f "$SNAP/FILES" ] || { echo "FAIL: missing $SNAP/FILES" >&2; exit 2; }

TMP=""
MOD=""
cleanup() {
    if [ -n "$MOD" ]; then rm -f "$MOD"; fi
    if [ -n "$TMP" ]; then rm -rf "$TMP"; fi
    return 0
}
trap cleanup EXIT HUP INT TERM

V=${VANILLA_TREE:-}
if [ -z "$V" ]; then
    if [ -d /tmp/linux-5.10.201-vanilla ]; then
        V=/tmp/linux-5.10.201-vanilla
    elif [ -f "$TARBALL" ]; then
        TMP=$(mktemp -d)
        tar -xJf "$TARBALL" -C "$TMP"
        V="$TMP/linux-5.10.201"
    else
        echo "FAIL: completeness not checked; set VANILLA_TREE or provide $TARBALL" >&2
        exit 2
    fi
fi
[ -d "$V" ] || { echo "FAIL: vanilla tree not found: $V" >&2; exit 2; }

MOD=$(mktemp)
cd "$SRC"
find . -type f \( -name '*.c' -o -name '*.h' -o -name '*.S' -o -name 'Makefile' -o -name 'Kconfig' -o -name '*.dts' -o -name '*.dtsi' \) \
    | sed 's|^\./||' \
    | grep -v -E '^(include/generated|include/config|arch/arm/include/generated|scripts|tools|Documentation|usr|samples|certs|debian|snapcraft)/' \
    | grep -v -E '^(\.tmp_|crypto/.*\.asn1\.[ch]$|lib/(crc32table\.h|oid_registry_data\.c)$|net/wireless/shipped-certs\.c$|arch/arm/boot/compressed/(ashldi3|bswapsdi2|hyp-stub|lib1funcs)\.S$|drivers/net/ethernet/luofu/luofu-gmac\.mod\.c$)' \
    | while IFS= read -r rel; do
        if [ -f "$V/$rel" ]; then
            cmp -s "$V/$rel" "$SRC/$rel" || printf '%s\n' "$rel"
        else
            printf '%s\n' "$rel"
        fi
    done | sort > "$MOD"

missing=0
while IFS= read -r rel; do
    [ -n "$rel" ] || continue
    if ! grep -qxF -- "$rel" "$SNAP/FILES"; then
        echo "MISSING FROM FILES: $rel"
        missing=1
    fi
done < "$MOD"

count=$(wc -l < "$MOD")
if [ "$missing" -eq 0 ]; then
    echo "PASS: all $count modified source files are in FILES"
else
    echo "FAIL: add the missing paths to $SNAP/FILES and run tools/sync-lab-src.sh" >&2
    exit 1
fi
