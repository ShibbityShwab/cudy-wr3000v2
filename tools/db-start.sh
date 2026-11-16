#!/bin/sh
# db-start.sh - start dropbear detached with generated host keys.
# Lives on the box at /tmp/db-start.sh; safe to re-run (skips if 22 is listening).
LOG=/tmp/db-start.log
: > "$LOG"

if netstat -tln 2>/dev/null | grep -q ':22 '; then
    echo ALREADY_LISTENING >> "$LOG"
    exit 0
fi

ls -l /etc/dropbear >> "$LOG" 2>&1
setsid /usr/sbin/dropbear -R -p 22 >> "$LOG" 2>&1 < /dev/null &
echo "started pid $!" >> "$LOG"

n=0
while [ $n -lt 15 ]; do
    if netstat -tln 2>/dev/null | grep -q ':22 '; then
        echo LISTENING >> "$LOG"
        exit 0
    fi
    n=$((n+1))
    sleep 1
done
echo NOT_LISTENING >> "$LOG"
netstat -tln >> "$LOG" 2>&1
ls -l /etc/dropbear >> "$LOG" 2>&1
exit 1
