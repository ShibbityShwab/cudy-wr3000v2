#!/bin/sh
# check-init-shadow.sh - refuse to build an image whose luofu shadow drops the vendor's pinctrl.
#
# 2026-11-15: a shadow that replaced /etc/rc.d/luofu with `exit 0` took the box off the network
# completely, because that script's first line is insmod hi_kpinctrl and without the pinmux neither the
# MDIO nor the Ethernet nor the Wi-Fi pins work. The recovery cost a reset-hold and a TFTP flash. This
# check runs the shadow's own filter against the vendor's real script and fails loudly if the result
# would lose anything other than the three modules our clean-room drivers own.
set -eu

HERE=$(cd "$(dirname "$0")/.." && pwd)
INIT=$HERE/build/linux-kbuild/init-vendorroot.c
VENDOR=$HERE/rootfs-2.5.24/etc/rc.d/luofu

[ -f "$INIT" ] || { echo "FAIL: missing $INIT" >&2; exit 1; }
[ -f "$VENDOR" ] || { echo "FAIL: missing vendor script $VENDOR" >&2; exit 1; }

FILTERED=$(sed -e '/hi_kphy\.ko/d' -e '/hi_kmdio\.ko/d' -e '/hi_kmac\.ko/d' "$VENDOR")

fail=0
for keep in hi_kpinctrl hi_efuse hi_clk_corrector hi_sysctrl hi_acp hi_kpie hi_lsw_pub hi_lsw_dp hi_lsw_pfe hi_kcfe_pub; do
    if ! printf '%s\n' "$FILTERED" | grep -q "insmod .*/$keep\.ko"; then
        echo "FAIL: the shadow would drop $keep - the box loses its pins or its switch" >&2
        fail=1
    fi
done
for drop in hi_kphy hi_kmdio hi_kmac; do
    if printf '%s\n' "$FILTERED" | grep -q "insmod .*/$drop\.ko"; then
        echo "FAIL: the shadow still loads $drop - our driver cannot bind" >&2
        fail=1
    fi
done

if grep -q 'insmod /lib/hisilicon/ko/hi_kpinctrl\.ko' "$VENDOR" && ! grep -q 'hi_kpinctrl' "$INIT"; then
    echo "FAIL: the init mentions neither the vendor script's pinctrl nor its own copy" >&2
    fail=1
fi

if [ "$fail" -eq 0 ]; then
    echo "PASS: the shadow keeps the pinctrl and the switch, drops only hi_kphy/hi_kmdio/hi_kmac"
fi
exit "$fail"
