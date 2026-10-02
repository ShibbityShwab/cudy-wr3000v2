#!/bin/sh
n=0
for f in $(find /rom/usr/lib/lua/luci /rom/www /rom/sbin -type f 2>/dev/null); do
	t=${f#/rom}
	if [ ! -e "$t" ]; then
		mkdir -p "$(dirname "$t")"
		cp -a "$f" "$t"
		n=$((n+1))
	fi
done
echo "restored files: $n"
for l in $(find /rom/usr/lib/lua/luci /rom/www -type l 2>/dev/null); do
	t=${l#/rom}
	if [ ! -e "$t" ]; then
		mkdir -p "$(dirname "$t")"
		cp -a "$l" "$t"
	fi
done
ls -la /www/index.html /www/cgi-bin/luci /usr/lib/lua/luci/sys.lua 2>&1 | head -4
