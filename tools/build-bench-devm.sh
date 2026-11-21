#!/bin/bash
# build-bench-devm.sh - build the static /dev/mem tool and place it into the
# luofu image base-files (so CONFIG_DEVMEM=y images boot with it in /usr/bin).
# usage: tools/build-bench-devm.sh [openwrt-build-clone]
set -u
CL=${1:-~/openwrt-lab-selectorfix-img}
TC=$(echo "$CL"/staging_dir/toolchain-*/bin/*-gcc)
CC=$(ls $TC 2>/dev/null | head -1)
[ -n "$CC" ] || { echo "toolchain gcc not found under $CL/staging_dir/toolchain-*"; exit 2; }
SRC=$(dirname "$(readlink -f "$0")")/devmem.c
OUT=build/linux-kbuild/bench-devm
mkdir -p "$(dirname "$OUT")"
"$CC" -O2 -static -o "$OUT" "$SRC" || exit 1
file "$OUT" || true
strip "$OUT" 2>/dev/null || true
DEST="$CL"/target/linux/hisilicon/base-files/usr/bin
mkdir -p "$DEST"
cp -f "$OUT" "$DEST"/devmem
chmod 755 "$DEST"/devmem
echo "installed $DEST/devmem"
ls -l "$DEST"/devmem
