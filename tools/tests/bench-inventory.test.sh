#!/usr/bin/env bash
# bench-inventory.test.sh - mock tests for tools/bench-inventory.sh.
#
# The suite runs the real inventory script inside a throw-away sandbox root that contains
# stubbed tools/rsh.sh, tools/bench-link.sh and tools/recovery-card.sh plus fixture device
# output. No real SSH, no device, no router, no network: every "remote" answer comes from
# fixtures under the sandbox. The tests assert:
#   - the static allowlist (print-plan, explain-address, RC misc window excluded)
#   - fail-closed refusal without each gate (attended, bench link, recovery, UART, transport,
#     stock health, read path)
#   - parsing, stability, expected-value diff and JSON/TSV/SHA output
#   - allowlist enforcement on emitted commands and NO write command ever emitted
#   - timeout, truncation, unexpected-address and partial-failure handling
#
# usage: tools/tests/bench-inventory.test.sh
# Exit status: 0 if every assertion passed, 1 otherwise.
set -uo pipefail

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
TOOL="$ROOT/tools/bench-inventory.sh"
SANDBOX=$(mktemp -d /tmp/bench-inventory-test.XXXXXX)
SB=$SANDBOX
PASS=0
FAIL=0
TESTS=0
INV_RC=0
OUTPUT=
INV_ENV=
UART_PID=
PLAN_COUNT=0

cleanup() {
    if [ -n "$UART_PID" ]; then kill "$UART_PID" 2>/dev/null || true; fi
    rm -rf "$SANDBOX"
}
trap cleanup EXIT

pass() {
    TESTS=$((TESTS + 1)); PASS=$((PASS + 1))
    echo "ok $TESTS - $*"
}

fail() {
    TESTS=$((TESTS + 1)); FAIL=$((FAIL + 1))
    echo "not ok $TESTS - $*"
}

assert_rc() {
    if [ "$INV_RC" -eq "$1" ]; then pass "$2 (rc=$1)"; else fail "$2 (want rc=$1, got $INV_RC)"; fi
}

assert_out_has() {
    case $OUTPUT in
        *"$1"*) pass "$2" ;;
        *) fail "$2 (output missing: $1)" ;;
    esac
}

assert_out_lacks() {
    case $OUTPUT in
        *"$1"*) fail "$2 (output unexpectedly has: $1)" ;;
        *) pass "$2" ;;
    esac
}

assert_eq() {
    if [ "$1" = "$2" ]; then pass "$3"; else fail "$3 (got '$1', want '$2')"; fi
}

assert_ge() {
    if [ "$1" -ge "$2" ]; then pass "$3"; else fail "$3 (got $1, want >= $2)"; fi
}

assert_no_device_contact() {
    if [ -s "$SB/run/rsh-calls.log" ]; then
        fail "$1 (rsh was called: $(head -c 120 "$SB/run/rsh-calls.log"))"
    else
        pass "$1"
    fi
}

assert_no_register_read() {
    if grep -qF "BENCH_INV_BATCH" "$SB/run/rsh-calls.log" 2>/dev/null; then
        fail "$1 (the tool sent a register-read batch)"
    else
        pass "$1"
    fi
}

# ---------------------------------------------------------------------------
# sandbox: stubs + fixtures
# ---------------------------------------------------------------------------
make_sandbox() {
    rm -rf "$SANDBOX"
    mkdir -p "$SB/tools" "$SB/.omo-secrets" "$SB/build/uart-logs" "$SB/fixtures" "$SB/run"
    cp "$TOOL" "$SB/tools/bench-inventory.sh"
    chmod +x "$SB/tools/bench-inventory.sh"
    : > "$SB/.omo-secrets/router_ed25519"

cat > "$SB/tools/bench-link.sh" <<'STUB'
#!/bin/sh
echo "bench link: MOCK"
if [ "$GATE_LINK_FAIL" = "1" ]; then echo "FAIL: mock bench link"; exit 1; fi
echo "PASS: mock bench link (unmanaged, both addresses, carrier up)"
exit 0
STUB
chmod +x "$SB/tools/bench-link.sh"

cat > "$SB/tools/recovery-card.sh" <<'STUB'
#!/bin/sh
if [ "$GATE_RECOVERY_FAIL" = "1" ]; then echo "STATUS: recovery door is NOT ready"; exit 1; fi
echo "STATUS: recovery door is READY (mock host + image + server)"
exit 0
STUB
chmod +x "$SB/tools/recovery-card.sh"

cat > "$SB/tools/rsh.sh" <<'STUB'
#!/bin/sh
SB=$BENCH_INV_SB
cmd=$1
mkdir -p "$SB/run"
echo "===RSH===" >> "$SB/run/rsh-calls.log"
echo "$cmd" >> "$SB/run/rsh-calls.log"
case $cmd in
    *BENCH_INV_HEALTH*)
        n=0
        [ -f "$SB/run/health-count" ] && n=$(cat "$SB/run/health-count")
        n=$((n + 1))
        echo "$n" > "$SB/run/health-count"
        if [ "$MOCK_HEALTH_FAIL" = "1" ]; then exit 255; fi
        if [ "$n" -gt 1 ] && [ -n "$MOCK_POST_BOOT_ID" ]; then
            awk -v id="$MOCK_POST_BOOT_ID" 'BEGIN { FS = "=" } $1 == "boot_id" { print "boot_id=" id; next } { print }' "$SB/fixtures/health.txt"
        else
            cat "$SB/fixtures/health.txt"
        fi
        ;;
    *BENCH_INV_CONTEXT*)
        if [ "$MOCK_CONTEXT_FAIL" = "1" ]; then exit 255; fi
        cat "$SB/fixtures/context.txt"
        ;;
    *BENCH_INV_BATCH*)
        bfile=$SB/run/batch-count
        bn=0
        [ -f "$bfile" ] && bn=$(cat "$bfile")
        bn=$((bn + 1))
        echo "$bn" > "$bfile"
        if [ -n "$MOCK_FAIL_BATCH" ]; then
            case ",$MOCK_FAIL_BATCH," in
                *",$bn,"*) exit 255 ;;
            esac
        fi
        if [ -n "$MOCK_SLOW_BATCH" ] && [ "$MOCK_SLOW_BATCH" = "$bn" ]; then sleep 8; fi
        addrs=$(echo "$cmd" | awk '/for a in / { line=$0; sub(/^.*for a in /, "", line); sub(/; do.*/, "", line); print line; exit }')
        passes=$(echo "$cmd" | awk '/for p in / { line=$0; sub(/^.*for p in /, "", line); sub(/; do.*/, "", line); print line; exit }')
        [ -n "$passes" ] || passes=1
        for p in $passes; do
            echo "# BENCH_INV_PASS $p"
            for a in $addrs; do
                if [ -n "$MOCK_ERR_ADDR" ] && [ "$a" = "$MOCK_ERR_ADDR" ]; then
                    echo "ERR $p $a mock-read-failed"
                    continue
                fi
                if [ -n "$MOCK_DROP_ADDR" ] && [ "$a" = "$MOCK_DROP_ADDR" ]; then
                    continue
                fi
                val=$(awk -v a="$a" '$1 == a { print $2; exit }' "$SB/fixtures/regs.txt")
                [ -n "$val" ] || val=0xdeadbeef
                echo "VAL $p $a $val"
            done
            if [ -n "$MOCK_EXTRA_ADDR" ]; then echo "VAL $p $MOCK_EXTRA_ADDR 0x1"; fi
        done
        if [ -n "$MOCK_TRUNCATE_BATCH" ] && [ "$MOCK_TRUNCATE_BATCH" = "$bn" ]; then exit 0; fi
        echo "# BENCH_INV_BATCH_END"
        ;;
    *)
        echo "MOCK-UNKNOWN-COMMAND"
        exit 9
        ;;
esac
STUB
chmod +x "$SB/tools/rsh.sh"

    health_ok
    context_ok
    make_regs
}

health_ok() {
cat > "$SB/fixtures/health.txt" <<'FIX'
BENCH_INV_HEALTH_OK=1
uname_r=5.10.201
uname_v=#0 SMP Sat Nov 25 18:18:57 2023
release=22.03.6
boot_id=11111111-1111-1111-1111-111111111111
uptime=605
bootflag=a
boot_reg_sysfs=10
wiphy=2
hi_mods=40
omo_off=0
overlay_ko=0
cal2g=1
cal5g=1
mtd11=1
mtd12=1
mtd13=1
mtd14=1
mtd_names=kernela,kernelb,rootfsa,rootfsb
rootfs_mtd_num=13
devmem=/sbin/devmem
devmem_sbin=yes
dd=/bin/dd
od=/bin/od
mem_readable=yes
devmem_probe=0x6a010008
FIX
}

context_ok() {
cat > "$SB/fixtures/context.txt" <<'FIX'
BENCH_INV_CONTEXT_OK=1
DTROOT=/proc/device-tree
BIN model 435544592d5752333030302d76322e3000
BIN lsw_dp/reg 87b000000040000087f00000001000001100000000800001128000000080000112000000008000011100000000800001108000000080000
BIN lsw_pfe/reg 1210000000080000121800000008000012280000000800001238000000080000124000000008000012080000000800001118000000080000120000000008000011380000000800001248000000080000
MISSING pie@0x10a70000/gro_ring
BEGIN /proc/mtd
dev:    size   erasesize  name
mtd11: 00840000 00020000 "kernela"
mtd12: 00840000 00020000 "kernelb"
mtd13: 03d40000 00020000 "rootfsa"
mtd14: 03d40000 00020000 "rootfsb"
END /proc/mtd
BEGIN /sys/devices/platform/sysenv/boot_reg
10
END /sys/devices/platform/sysenv/boot_reg
BEGIN /sys/kernel/debug/clk/clk_summary
   clock                     enable_cnt  prepare_cnt  rate           accuracy   phase
   osc                        5           5            20000000       0          0
END /sys/kernel/debug/clk/clk_summary
BENCH_INV_CONTEXT_END
FIX
}

make_regs() {
    "$TOOL" --print-plan 2>/dev/null | awk -F'\t' 'NF >= 7 && $3 ~ /^0x/ { print $3 "\t0x" substr($3, 3) }' > "$SB/fixtures/regs-default.txt"
cat > "$SB/fixtures/regs-overrides.txt" <<'FIX'
0x10100c08	0x00000010
0x10100c00	0x80608000
0x10100c10	0x00000000
0x14880090	0x6a010008
0x14880014	0x01360ef1
0x14880020	0x02f8300b
0x14880034	0x000ff309
0x14880100	0x00000000
0x10a71000	0x000001c0
0x10a73204	0x00000000
0x10a73208	0x0000007d
0x10a72000	0x80000000
0x10a72004	0x0000000c
0x10a72008	0x00000000
0x10a7200c	0x00000000
0x10a73000	0x90000000
0x10a73004	0x0000000a
0x10a73504	0x00000100
FIX
    cat "$SB/fixtures/regs-overrides.txt" "$SB/fixtures/regs-default.txt" > "$SB/fixtures/regs-all.txt"
    awk -F'\t' '!seen[$1]++' "$SB/fixtures/regs-all.txt" > "$SB/fixtures/regs.txt"
}

start_capture() {
    stop_capture
    sleep 600 &
    UART_PID=$!
    echo "$UART_PID" > "$SB/build/uart-logs/uart-test.pid"
}

stop_capture() {
    if [ -n "$UART_PID" ]; then kill "$UART_PID" 2>/dev/null || true; fi
    UART_PID=
    rm -f "$SB/build/uart-logs/uart-test.pid"
}

run_inv() {
    rm -f "$SB/run/rsh-calls.log" "$SB/run/batch-count"
    : > "$SB/run/health-count"
    set +e
    # shellcheck disable=SC2086
    OUTPUT=$(env BENCH_INV_SB="$SB" $INV_ENV bash "$SB/tools/bench-inventory.sh" "$@" 2>&1)
    INV_RC=$?
    set -u
}

json_field() {
    python3 - "$1" "$2" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
value = eval(sys.argv[2], {"d": d})
print(value)
PY
}

json_entry_field() {
    python3 - "$1" "$2" "$3" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
for e in d["entries"]:
    if e["addr"] == sys.argv[2]:
        print(e[sys.argv[3]])
        break
PY
}

# ---------------------------------------------------------------------------
# 1. CLI surface
# ---------------------------------------------------------------------------
make_sandbox
start_capture

run_inv --help
assert_rc 0 "help exits 0"
assert_out_has "READ-ONLY" "help states the tool is read-only"
assert_out_has "usage:" "help prints usage"
assert_no_device_contact "help never contacts the device"

run_inv --print-plan
assert_rc 0 "print-plan exits 0"
PLAN_COUNT=$(echo "$OUTPUT" | awk -F'\t' 'NF >= 7 && $3 ~ /^0x/ {n++} END {print n + 0}')
assert_ge "$PLAN_COUNT" 500 "print-plan lists the full allowlist ($PLAN_COUNT reads)"
assert_out_lacks "0x10161000	" "print-plan contains no RC misc window row"
assert_out_has "lsw" "print-plan has LSW rows"
assert_out_has "pie" "print-plan has PIE rows"
assert_out_has "crg" "print-plan has CRG rows"
assert_out_has "sysctrl" "print-plan has SYSCTRL rows"
assert_out_has "NEVER read" "print-plan documents the hard exclusions"
assert_no_device_contact "print-plan never contacts the device"

# ---------------------------------------------------------------------------
# 2. address allowlist decisions
# ---------------------------------------------------------------------------
for addr in 0x10100c08 0x10100c00 0x10100c10 0x12442800 0x14880090 0x14880198 0x10a71000 0x1100001c 0x12180000 0x11281008; do
    run_inv --explain-address "$addr"
    assert_rc 0 "explain allows $addr"
    assert_out_has "ALLOW" "explain prints ALLOW for $addr"
done
for addr in 0x10161000 0x10161004 0x10165000 0x1016ffff 0x400392f0 0xdeadbeef 0x10a70003 0x11000000 0x10100c09 0x14880001; do
    run_inv --explain-address "$addr"
    assert_rc 1 "explain denies $addr"
    assert_out_has "DENY" "explain prints DENY for $addr"
done
run_inv --explain-address 0x10161000
assert_out_has "RC misc window" "denial explains the RC misc window rule"

# ---------------------------------------------------------------------------
# 3. fail-closed gates (no device contact when a local gate fails)
# ---------------------------------------------------------------------------
INV_ENV=
run_inv --out "$SB/out-noattended"
assert_rc 2 "refuses without --attended"
assert_out_has "attended" "refusal names the attended gate"
assert_no_device_contact "no device contact without --attended"

INV_ENV="GATE_LINK_FAIL=1"
run_inv --attended --check-only --out "$SB/out-nolink"
assert_rc 2 "refuses when the bench link gate fails"
assert_out_has "bench-link" "refusal names the bench-link gate"
assert_no_device_contact "no device contact when the bench link fails"
INV_ENV=

INV_ENV="GATE_RECOVERY_FAIL=1"
run_inv --attended --check-only --out "$SB/out-norecovery"
assert_rc 2 "refuses when the recovery door gate fails"
assert_out_has "recovery-door" "refusal names the recovery-door gate"
assert_no_device_contact "no device contact when recovery is not ready"
INV_ENV=

stop_capture
run_inv --attended --check-only --out "$SB/out-nouart"
assert_rc 2 "refuses without a read-only UART capture"
assert_out_has "UART capture" "refusal names the UART capture gate"
run_inv --attended --check-only --no-uart --out "$SB/out-nouart-ok"
assert_rc 0 "--no-uart allows the run with a warning"
assert_out_has "WARN  uart-capture" "--no-uart is recorded as a warning"
start_capture

mv "$SB/.omo-secrets/router_ed25519" "$SB/.omo-secrets/router_ed25519.bak"
run_inv --attended --check-only --out "$SB/out-notransport"
assert_rc 2 "refuses without the SSH transport"
assert_out_has "transport" "refusal names the transport gate"
mv "$SB/.omo-secrets/router_ed25519.bak" "$SB/.omo-secrets/router_ed25519"
assert_no_device_contact "no device contact after the transport refusal"

# ---------------------------------------------------------------------------
# 4. stock-health gate
# ---------------------------------------------------------------------------
INV_ENV="MOCK_HEALTH_FAIL=1"
run_inv --attended --check-only --out "$SB/out-unreachable"
assert_rc 2 "refuses when the box is unreachable"
assert_out_has "stock-health" "refusal names the stock-health gate"
assert_no_register_read "refusal happens before any register read"
INV_ENV=

health_ok
sed -i 's/^uname_r=.*/uname_r=6.1.0/' "$SB/fixtures/health.txt"
run_inv --attended --check-only --out "$SB/out-badkernel"
assert_rc 2 "refuses on a non-stock kernel"
assert_out_has "stock-kernel-release" "refusal names the kernel check"
health_ok

sed -i 's/^boot_reg_sysfs=.*/boot_reg_sysfs=11/' "$SB/fixtures/health.txt"
run_inv --attended --check-only --out "$SB/out-pairmismatch"
assert_rc 2 "refuses when the selector pair does not match bootflag"
assert_out_has "boot-reg" "refusal names the selector check"
health_ok

sed -i 's/^devmem=.*/devmem=/' "$SB/fixtures/health.txt"
sed -i 's/^devmem_sbin=.*/devmem_sbin=no/' "$SB/fixtures/health.txt"
sed -i 's/^mem_readable=.*/mem_readable=no/' "$SB/fixtures/health.txt"
run_inv --attended --check-only --out "$SB/out-noreadpath"
assert_rc 2 "refuses when there is no read path"
assert_out_has "devmem-capability" "refusal names the read-path check"
health_ok

# ---------------------------------------------------------------------------
# 5. check-only mode
# ---------------------------------------------------------------------------
INV_ENV=
run_inv --attended --check-only --out "$SB/out-check"
assert_rc 0 "check-only passes on a healthy stock fixture"
assert_ge "$(json_field "$SB/out-check/inventory.json" 'd["summary"]["entries_total"]')" 0 "check-only JSON has a summary"
assert_eq "$(json_field "$SB/out-check/inventory.json" 'd["result"]')" "CHECK-ONLY-PASS" "check-only result is CHECK-ONLY-PASS"
assert_eq "$(json_field "$SB/out-check/inventory.json" 'd["summary"]["entries_total"]')" "0" "check-only reads no registers"
assert_no_register_read "check-only reads no registers"
assert_eq "$(json_field "$SB/out-check/inventory.json" 'len([g for g in d["gates"] if g["status"]=="PASS"])')" "8" "check-only records eight PASS gates (seven local plus stock-health)"

# ---------------------------------------------------------------------------
# 6. full allowlisted run: parsing, JSON/TSV/SHA, allowlist enforcement, no writes
# ---------------------------------------------------------------------------
check_hashes() {
    ( cd "$1" 2>/dev/null && sha256sum -c SHA256SUMS >/dev/null 2>&1 )
}

scan_safety() {
    python3 - "$SB/run/rsh-calls.log" "$SB/out-full/commands.txt" "$SB/out-full/plan.tsv" <<'PY'
import re
import sys

calls = open(sys.argv[1]).read()
cmds = open(sys.argv[2]).read()
plan = set()
for line in open(sys.argv[3]):
    f = line.split("\t")
    if len(f) >= 7 and f[3].startswith("0x"):
        plan.add(f[3])

problems = []
for name, text in (("rsh-calls", calls), ("commands", cmds)):
    for bad in ("mtd write", "mtd erase", "fw_setenv", "rmmod", "insmod",
                "modprobe", "flash_erase", "sysctl -w", "wget ", "scp "):
        if bad in text:
            problems.append(name + " contains forbidden token: " + bad)
    if ".omo-secrets" in text:
        problems.append(name + " leaks the SSH key path")
    for i, line in enumerate(text.splitlines()):
        stripped = line.replace("2>/dev/null", "")
        if ">" in stripped:
            problems.append(name + " line " + str(i) + " has an unexpected redirection")

addr_re = re.compile(r"0x[0-9a-f]{8}")
batch_addrs = set()
for line in cmds.splitlines():
    if line.strip().startswith("for a in "):
        for a in addr_re.findall(line):
            batch_addrs.add(a)
if not batch_addrs:
    problems.append("no batch addresses found in commands.txt")
for a in sorted(batch_addrs):
    if a not in plan:
        problems.append("batch script address outside the plan: " + a)

blocks = calls.split("===RSH===")
health_reads = set()
for block in blocks:
    if "BENCH_INV_HEALTH" in block:
        health_reads.update(addr_re.findall(block))
if health_reads != {"0x14880090"}:
    problems.append("unexpected literal address in the health probe: " + repr(sorted(health_reads)))

if problems:
    print("SCAN-FAIL: " + " | ".join(problems[:8]))
    sys.exit(1)
print("SCAN-OK")
PY
}

INV_ENV=
make_regs
run_inv --attended --batch 32 --repeat 1 --out "$SB/out-full"
assert_rc 0 "full allowlisted run completes"
FULL="$SB/out-full/inventory.json"
assert_out_has "RESULT: COMPLETE" "full run reports COMPLETE"
assert_eq "$(json_field "$FULL" 'd["result"]')" "COMPLETE" "JSON result is COMPLETE"
assert_eq "$(json_field "$FULL" 'd["summary"]["entries_total"]')" "$PLAN_COUNT" "JSON has one entry per planned read"
assert_eq "$(json_field "$FULL" 'd["summary"]["status_ok"]')" "$PLAN_COUNT" "every entry has an ok read"
assert_eq "$(json_field "$FULL" 'd["summary"]["status_error"]')" "0" "no read errors in the full run"
assert_eq "$(json_field "$FULL" 'd["summary"]["batches_failed"]')" "0" "no failed batches in the full run"
assert_eq "$(json_field "$FULL" 'd["summary"]["batches_total"]')" "$(( (PLAN_COUNT + 31) / 32 ))" "batch count matches batch size 32"
assert_eq "$(json_field "$FULL" 'd["batch_size"]')" "32" "JSON records the batch size"
assert_eq "$(json_field "$FULL" 'd["repeat"]')" "1" "JSON records the repeat count"
assert_eq "$(json_field "$FULL" 'd["crosschecks"]["boot_reg_crosscheck"]')" "pass" "selector sysfs/devmem cross-check passes"
assert_eq "$(json_entry_field "$FULL" 0x10100c08 check)" "pass" "selector pair expected-value check passes"
assert_eq "$(json_entry_field "$FULL" 0x10100c08 value)" "0x00000010" "selector devmem value is captured"
assert_eq "$(json_entry_field "$FULL" 0x14880090 check)" "pass" "CRG PLL lock mask check passes"
assert_eq "$(json_entry_field "$FULL" 0x14880090 expected)" "mask:0x48000000" "CRG status entry carries its expected mask"
assert_eq "$(json_entry_field "$FULL" 0x10a72004 check)" "pass" "PIE TX ring-size shift expected value matches"
assert_eq "$(json_entry_field "$FULL" 0x10a71000 check)" "pass" "PIE global-control clear/mask check passes"
grep -q "MISC-SOC-BLOCKS.md" "$FULL" && pass "entries map to the spec sections" || fail "entries do not reference the spec docs"
assert_eq "$(wc -l < "$SB/out-full/inventory.tsv" | tr -d ' ')" "$((PLAN_COUNT + 1))" "TSV has a header plus one row per read"
check_hashes "$SB/out-full" && pass "SHA256SUMS verifies" || fail "SHA256SUMS does not verify"
python3 -c 'import json,sys; json.load(open(sys.argv[1]))' "$FULL" && pass "inventory.json is valid JSON" || fail "inventory.json is not valid JSON"

SCAN=$(scan_safety)
assert_eq "$SCAN" "SCAN-OK" "emitted commands are read-only, key-free and fully allowlisted"
assert_out_lacks "MOCK-UNKNOWN-COMMAND" "the tool never sends a command the transport stubs did not expect"

# ---------------------------------------------------------------------------
# 7. repeat passes and stability
# ---------------------------------------------------------------------------
run_inv --attended --groups sysctrl --batch 32 --repeat 2 --out "$SB/out-repeat"
assert_rc 0 "repeat=2 run completes"
REP="$SB/out-repeat/inventory.json"
assert_eq "$(json_field "$REP" 'd["repeat"]')" "2" "JSON records repeat=2"
assert_eq "$(json_entry_field "$REP" 0x10100c08 stable)" "True" "a stable register is marked stable"
assert_eq "$(python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); print(len([e for e in d["entries"] if e["addr"]=="0x10100c08"][0]["reads"]))' "$REP")" "2" "each entry keeps both read passes"

# ---------------------------------------------------------------------------
# 8. batch splitting
# ---------------------------------------------------------------------------
run_inv --attended --groups sysctrl --batch 1 --repeat 1 --out "$SB/out-batch1"
assert_rc 0 "batch=1 run completes"
assert_eq "$(grep -c 'BENCH_INV_BATCH v1' "$SB/run/rsh-calls.log")" "3" "batch=1 produces one SSH call per address"
assert_eq "$(json_field "$SB/out-batch1/inventory.json" 'd["summary"]["batches_total"]')" "3" "JSON records three batches"

# ---------------------------------------------------------------------------
# 9. partial failure: one unreadable register
# ---------------------------------------------------------------------------
INV_ENV="MOCK_ERR_ADDR=0x10100c00"
run_inv --attended --groups sysctrl --batch 32 --repeat 1 --out "$SB/out-partial"
assert_rc 3 "a failed read exits 3"
assert_eq "$(json_field "$SB/out-partial/inventory.json" 'd["result"]')" "PARTIAL" "JSON result is PARTIAL"
assert_ge "$(json_field "$SB/out-partial/inventory.json" 'd["summary"]["status_error"]')" 1 "the failed register is recorded as an error"
assert_eq "$(json_entry_field "$SB/out-partial/inventory.json" 0x10100c00 status)" "error" "the failed entry is marked error"
check_hashes "$SB/out-partial" && pass "partial evidence still verifies by SHA256SUMS" || fail "partial evidence does not verify"
INV_ENV=

# ---------------------------------------------------------------------------
# 10. timeout handling
# ---------------------------------------------------------------------------
INV_ENV="MOCK_SLOW_BATCH=1"
run_inv --attended --groups sysctrl --batch 32 --repeat 1 --ssh-timeout 5 --out "$SB/out-timeout"
assert_rc 3 "a timed-out SSH call exits 3"
assert_out_has "FAILED" "the timeout is reported as a failed batch"
assert_out_has "rc=124" "the timeout is attributed to the timed-out call"
assert_eq "$(json_field "$SB/out-timeout/inventory.json" 'd["result"]')" "PARTIAL" "timeout yields a PARTIAL result"
INV_ENV=

# ---------------------------------------------------------------------------
# 11. truncated output
# ---------------------------------------------------------------------------
INV_ENV="MOCK_TRUNCATE_BATCH=1"
run_inv --attended --groups sysctrl --batch 32 --repeat 1 --out "$SB/out-trunc"
assert_rc 3 "truncated remote output exits 3"
assert_out_has "incomplete or malformed" "truncation is reported"
INV_ENV=

# ---------------------------------------------------------------------------
# 12. unexpected address in remote output (allowlist enforcement on responses)
# ---------------------------------------------------------------------------
INV_ENV="MOCK_EXTRA_ADDR=0xdeadbeef"
run_inv --attended --groups sysctrl --batch 32 --repeat 1 --out "$SB/out-extra"
assert_rc 3 "an out-of-batch address in the output exits 3"
assert_out_has "outside the batch" "the unexpected address is reported"
INV_ENV=

# ---------------------------------------------------------------------------
# 13. stop after consecutive failed batches
# ---------------------------------------------------------------------------
INV_ENV="MOCK_FAIL_BATCH=1,2"
run_inv --attended --groups pie --batch 32 --repeat 1 --max-failed-batches 2 --out "$SB/out-stop"
assert_rc 3 "two consecutive failed batches exit 3"
assert_out_has "STOPPED" "the run stops after the configured consecutive failures"
assert_ge "$(json_field "$SB/out-stop/inventory.json" 'd["summary"]["status_not_attempted"]')" 1 "unattempted batches are recorded as not-attempted"
INV_ENV=

# ---------------------------------------------------------------------------
# 14. mid-run reboot detection (post-run health)
# ---------------------------------------------------------------------------
INV_ENV="MOCK_POST_BOOT_ID=22222222-2222-2222-2222-222222222222"
run_inv --attended --groups sysctrl --batch 32 --repeat 1 --out "$SB/out-reboot"
assert_rc 3 "a changed boot_id exits 3"
assert_eq "$(json_field "$SB/out-reboot/inventory.json" 'd["result"]')" "INVALID" "a changed boot_id yields INVALID"
assert_out_has "INVALID" "the invalid result is reported"
INV_ENV=

# ---------------------------------------------------------------------------
# 15. context capture controls
# ---------------------------------------------------------------------------
INV_ENV=
run_inv --attended --groups sysctrl --batch 32 --repeat 1 --no-context --out "$SB/out-noctx"
assert_rc 0 "--no-context run completes"
assert_eq "$(json_field "$SB/out-noctx/inventory.json" 'len(d["context"])')" "0" "--no-context records no context"
case "$OUTPUT" in
    *"BENCH_INV_CONTEXT"*) fail "--no-context still sent the context script" ;;
    *) pass "--no-context sends no context script" ;;
esac

INV_ENV="MOCK_CONTEXT_FAIL=1"
run_inv --attended --groups sysctrl --batch 32 --repeat 1 --out "$SB/out-ctxfail"
assert_rc 0 "a failed context capture is a warning, not a failure"
assert_out_has "context: WARN unavailable" "the context failure is reported as a warning"
INV_ENV=

# ---------------------------------------------------------------------------
# 16. group filtering
# ---------------------------------------------------------------------------
run_inv --attended --groups crg --batch 32 --repeat 1 --out "$SB/out-crg"
assert_rc 0 "group-filtered run completes"
assert_eq "$(json_field "$SB/out-crg/inventory.json" 'd["summary"]["entries_total"]')" "13" "crg group has 13 planned reads"
assert_eq "$(json_field "$SB/out-crg/inventory.json" 'len(set(e["group"] for e in d["entries"]))')" "1" "group-filtered run contains only one group"

# ---------------------------------------------------------------------------
# 17. usage errors
# ---------------------------------------------------------------------------
run_inv --groups bogus --attended --check-only --out "$SB/out-badgroup"
assert_rc 1 "an unknown group is a usage error"
run_inv --attended --check-only --batch 0 --out "$SB/out-badbatch"
assert_rc 1 "an out-of-range batch size is a usage error"
run_inv --attended --check-only --label "bad label" --out "$SB/out-badlabel"
assert_rc 1 "an invalid label is a usage error"

# ---------------------------------------------------------------------------
# summary
# ---------------------------------------------------------------------------
echo
if [ "$FAIL" -eq 0 ]; then
    echo "PASS: $PASS/$TESTS assertions passed"
    exit 0
fi
echo "FAIL: $FAIL of $TESTS assertions failed"
exit 1
