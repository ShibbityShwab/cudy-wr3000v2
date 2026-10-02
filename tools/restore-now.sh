#!/bin/sh
cd /lib/modules/5.10.201 || exit 1
for f in *.omo-off; do [ -e "$f" ] || continue; mv -f "$f" "${f%.omo-off}"; done
rm -f /etc/init.d/omo-* /etc/rc.d/S99omo-*
rm -f /lib/modules/5.10.201/hccaccept.ko /lib/modules/5.10.201/srcarrier.ko /lib/modules/5.10.201/bothep.ko /lib/modules/5.10.201/srpump.ko
echo LEFT=$(( $(ls /lib/modules/5.10.201/ | grep -c omo-off) ))
echo INITD=$(( $(ls /etc/init.d/ | grep -c 'omo-') ))
sync
echo RESTORED
