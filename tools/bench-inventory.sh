#!/usr/bin/env bash
# bench-inventory.sh - fail-closed READ-ONLY register/table inventory for the WR3000 v2 bench.
#
# Reads an allowlisted set of LSW, PIE, CRG and SYSCTRL registers over the project SSH
# transport (tools/rsh.sh) and saves the raw reads plus a spec-mapped JSON/TSV under build/.
# It NEVER writes to the device: no devmem write, no mtd write, no sysfs store, no
# rmmod/insmod, no reboot. Every address is a static table entry tied to a spec section;
# argument input cannot add an address. The RC misc window 0x10160000-0x1016ffff
# (includes 0x10161000) is excluded by an explicit denylist in addition to the allowlist.
#
# Every device contact is gated fail-closed: attended, bench link PASS, recovery door READY,
# read-only UART capture running (or --no-uart), and the healthy stock vendor system per
# RUNBOOK.md section 0 and BENCH-FACTS.md. If any gate fails the tool reads nothing and
# exits 2.
#
# Procedure, expected values and interpretation:
#   opensource/docs/BENCH-READONLY-INVENTORY.md
# Mock tests:
#   tools/tests/bench-inventory.test.sh
#
# Version: 1
set -uo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT" || exit 1
export LC_ALL=C

TOOL_VERSION=1
STOCK_KERNEL_RELEASE=5.10.201
STOCK_KERNEL_VER='Sat Nov 25 18:18:57 2023'
STOCK_OPENWRT_RELEASE=22.03.6
DEFAULT_GROUPS=lsw,pie,crg,sysctrl
TAB=$(awk 'BEGIN { printf "%c", 9 }')
LOG=/dev/null
OUT=
PLAN=
LABEL=inventory
SEL_GROUPS=$DEFAULT_GROUPS
ATTENDED=0
NO_UART=0
NO_CONTEXT=0
CHECK_ONLY=0
PRINT_PLAN=0
EXPLAIN_ADDR=
BATCH=16
REPEAT=2
SSH_TIMEOUT=20
CONNECT_TIMEOUT=10
MAX_FAILED_BATCHES=2
MODE=inventory
GATE_FAIL=0
PLAN_COUNT=0
RESULT=
RC=
REASON=
BOOTFLAG_PRE=
BOOTREG_PRE=
UPTIME_PRE=
BATCHES_TOTAL=0
BATCHES_RUN=0
BATCHES_FAILED=0
HEALTH_RC=1
ANCESTORS=
ALLOW_ADDR_FILE=

say() { echo "$*"; echo "$*" >> "$LOG"; }
hr() { say "------------------------------------------------------------"; }

usage() {
cat <<'USAGE'
bench-inventory.sh - fail-closed READ-ONLY register/table inventory for the WR3000 v2 bench.

usage:
  tools/bench-inventory.sh --attended [options]
  tools/bench-inventory.sh --check-only --attended
  tools/bench-inventory.sh --print-plan
  tools/bench-inventory.sh --explain-address 0xADDR

options:
  --attended              human at the bench (MANDATORY for any device contact)
  --label NAME            evidence label, [A-Za-z0-9_-] (default: inventory)
  --out DIR               evidence directory (default: build/bench-inventory/<UTC>-<label>)
  --groups LIST           comma list of lsw,pie,crg,sysctrl (default: all four)
  --batch N               addresses per SSH call, 1..32 (default: 16)
  --repeat N              read passes per address, 1..3 (default: 2)
  --ssh-timeout SECONDS   per-SSH-call timeout (default: 20)
  --connect-timeout SEC   SSH connect timeout passed to rsh.sh (default: 10)
  --max-failed-batches N  stop after N consecutive failed batches (default: 2)
  --no-uart               allow the run without a running read-only UART capture (WARN)
  --no-context            skip the read-only device-tree/proc context capture
  --check-only            run the gates and the device health probe only
  --print-plan            host-only: print the full allowlist and exit
  --explain-address ADDR  host-only: ALLOW/DENY one address (exit 0 allow / 1 deny)
  -h, --help              this help

exit codes:
  0  COMPLETE, CHECK-ONLY-PASS, print-plan, or ALLOW
  1  usage error
  2  REFUSED: a precondition failed or the evidence directory is not writable
  3  PARTIAL or INVALID: reads incomplete, or the box rebooted/degraded mid-run

safety:
  READ-ONLY. The tool has no write path: every device command is generated from a static
  read-only template, checked against the allowlist, and re-scanned for forbidden tokens
  before it is sent. Never add a write to this tool.
USAGE
}

die_usage() {
    echo "error: $*" >&2
    echo >&2
    usage >&2
    exit 1
}

# ---------------------------------------------------------------------------
# static allowlist
#
# One row per 32-bit register read: group, block, base, offset, spec section, field,
# expected token(s), note. The expected tokens are diffed by the analysis pass:
#   unknown / dynamic          -> no automatic verdict (documented [U] or volatile)
#   nonzero                    -> integer value must be non-zero
#   eq:0xVALUE                 -> exact match
#   mask:0xMASK                -> all mask bits must be set
#   clear:0xMASK               -> no mask bit may be set
#   pair                       -> low byte must equal the pair recorded by health
#                                (bootflag a -> 0x10, bootflag b -> 0x11)
# This table is the ONLY source of device addresses; there is deliberately no way to add
# one from the command line. Addresses not in the table are refused by --explain-address
# and never emitted by a normal run.
# ---------------------------------------------------------------------------
E() {
    printf '%s%s%s%s0x%08x%s%s%s%s%s%s%s' "$1" "$TAB" "$2" "$TAB" "$(( $3 + $4 ))" "$TAB" "$5" "$TAB" "$6" "$TAB" "$7" "$TAB"
    echo "$8"
}

pfeblock() {
    local b=$1 base=$2
    E lsw "$b" "$base" 0x00 "LSW-SPEC.md 5.3" "$b+0x00 DFX counter block word 0" unknown "[V] addr; [U] counter names/map"
    E lsw "$b" "$base" 0x1004 "LSW-SPEC.md 5.3" "$b+0x1004 DFX counter block word" unknown "[V] addr; [U] meaning"
    E lsw "$b" "$base" 0x1008 "LSW-SPEC.md 5.3" "$b+0x1008 DFX counter block word" unknown "[V] addr; [U] meaning"
}

emit_allowlist() {
    local ch off last slot entry port sub word exp fld

    # ---- LSW: DP window 0x11000000 (module id 0x40), LSW-SPEC.md 5.2/5.3 ----
    E lsw dp 0x11000000 0x1c "LSW-SPEC.md 5.3" "dp+0x1c probe halfword OR 0x10000" unknown "[V] addr; [U] meaning; W1 baseline (12.3)"
    E lsw dp 0x11000000 0x64 "LSW-SPEC.md 5.3" "dp+0x64 probe 1 then cell-size selector" unknown "[V] addr; [U] meaning; W1 baseline"
    E lsw dp 0x11000000 0x68 "LSW-SPEC.md 5.3" "dp+0x68 memory number" unknown "[V] addr; [U] meaning; W1 baseline"

    # ---- LSW: EPS window 0x11280000 (id 0x41) ----
    E lsw eps 0x11280000 0x1008 "LSW-SPEC.md 5.3" "eps+0x1008 queue/DFX" unknown "[V] addr; [U] meaning; W1 baseline (12.3)"
    for ch in 0 1 2 3 4 5 6 7; do
        E lsw eps 0x11280000 $((0xb00 + ch * 4)) "LSW-SPEC.md 7.4" "eps+0xB00+chN*4 PIE channel map word (ch=$ch)" unknown "[V] code shape; [U] field meaning"
        E lsw eps 0x11280000 $((0xb80 + ch * 4)) "LSW-SPEC.md 7.4" "eps+0xB80+chN*4 channel map companion word (ch=$ch)" unknown "[V] code shape; [U] field meaning"
    done
    off=$((0x2084))
    last=$((0x20b4))
    while [ "$off" -le "$last" ]; do
        fld=$(printf 'eps+0x%x per-port DFX counter (port3..port7 block)' "$off")
        E lsw eps 0x11280000 "$off" "LSW-SPEC.md 5.3" "$fld" unknown "[V] addr; [U] counter mapping"
        off=$((off + 4))
    done
    E lsw eps 0x11280000 0x50000 "LSW-SPEC.md 7.4" "eps+0x50000 tab128 table base (first word)" unknown "[V] tab128 primitive; [U] table format"

    # ---- LSW: EQM window 0x11200000 (id 0x42) ----
    E lsw eqm 0x11200000 0x00 "LSW-SPEC.md 5.3" "eqm+0x00 queue table command/status base" unknown "[V] addr; [U] meaning"
    E lsw eqm 0x11200000 0x18 "LSW-SPEC.md 5.3" "eqm+0x18 queue/cell config" unknown "[V] addr; [U] meaning"
    E lsw eqm 0x11200000 0x38 "LSW-SPEC.md 5.3" "eqm+0x38 queue/cell config" unknown "[V] addr; [U] meaning"
    E lsw eqm 0x11200000 0x40 "LSW-SPEC.md 5.3" "eqm+0x40 probe/service enable word (bit31)" unknown "[V] addr/bit; [U] live"
    E lsw eqm 0x11200000 0x48 "LSW-SPEC.md 7.5" "eqm+0x48 indirect table command/status (bit31 busy, bit5 error)" unknown "[V] bits; W1 baseline (12.3)"
    E lsw eqm 0x11200000 0x5c "LSW-SPEC.md 7.5" "eqm+0x5c indirect table write-data word" unknown "[V] addr; W1 baseline (12.3)"
    E lsw eqm 0x11200000 0xa4 "LSW-SPEC.md 5.3" "eqm+0xa4 queue table config" unknown "[V] addr; [U] meaning"
    E lsw eqm 0x11200000 0x504 "LSW-SPEC.md 5.3" "eqm+0x504 queue/cell counter selector" unknown "[V] addr; [U] meaning"
    off=$((0x2004))
    last=$((0x203c))
    while [ "$off" -le "$last" ]; do
        fld=$(printf 'eqm+0x%x queue/cell counter' "$off")
        E lsw eqm 0x11200000 "$off" "LSW-SPEC.md 5.3" "$fld" unknown "[V] addr; [U] counter mapping"
        off=$((off + 4))
    done
    E lsw eqm 0x11200000 0x600c "LSW-SPEC.md 5.3" "eqm+0x600c queue table word" unknown "[V] addr; [U] meaning"

    # ---- LSW: FAM 0x11100000 (id 0x43) and IPS 0x11080000 (id 0x44) ----
    E lsw fam 0x11100000 0x504 "LSW-SPEC.md 5.3" "fam+0x504 queue-count/cell comparison" unknown "[V] addr; [U] meaning"
    E lsw ips 0x11080000 0x00 "LSW-SPEC.md 5.3" "ips+0x00 probe/config word" unknown "[V] addr; [U] meaning"
    E lsw ips 0x11080000 0x08 "LSW-SPEC.md 5.3" "ips+0x08 probe init value 42" unknown "[V] write 42; [U] meaning"
    E lsw ips 0x11080000 0x10 "LSW-SPEC.md 5.3" "ips+0x10 probe init (bit16)" unknown "[V] addr/bit; [U] meaning"
    E lsw ips 0x11080000 0x1120 "LSW-SPEC.md 5.3" "ips+0x1120 counter read" unknown "[V] addr; [U] meaning"
    E lsw ips 0x11080000 0x1344 "LSW-SPEC.md 5.3" "ips+0x1344 counter read" unknown "[V] addr; [U] meaning"

    # ---- LSW: PFE windows 0x12xxxxxx (ids 0x0..0xb), LSW-SPEC.md 5.2/5.3 ----
    E lsw ifc 0x12100000 0x00 "LSW-SPEC.md 5.3" "ifc+0x00 classifier DFX counter base" unknown "[V] addr; [U] counter mapping"
    pfeblock l2 0x12180000
    pfeblock napt 0x12280000
    pfeblock mcc 0x12380000
    pfeblock opp 0x12400000
    pfeblock pa 0x12080000
    pfeblock pe 0x11180000
    pfeblock pfe_glb 0x12000000
    pfeblock prbs 0x11380000
    pfeblock pub 0x12480000

    # ---- LSW: qid-map tables in the opp window, LSW-SPEC.md 7.3 ----
    # table A: opp+0x42800, one u32 per slot, word index = index + id*8 (ports 0..15)
    off=$((0x42800))
    last=$((0x429fc))
    while [ "$off" -le "$last" ]; do
        slot=$(( (off - 0x42800) / 4 ))
        port=$(( slot / 8 ))
        sub=$(( slot % 8 ))
        fld=$(printf 'opp+0x%x qid table A port %d slot %d word' "$off" "$port" "$sub")
        E lsw opp 0x12400000 "$off" "LSW-SPEC.md 7.3" "$fld" unknown "[V] table shape; [I] 0x100 flag + qid low byte; W1 baseline"
        off=$((off + 4))
    done
    # table B: opp+0x43800, 16-byte entries, 8 slots per port for port class 40..47
    off=$((0x43800))
    last=$((0x43bfc))
    while [ "$off" -le "$last" ]; do
        entry=$(( (off - 0x43800) / 16 ))
        port=$(( 40 + entry / 8 ))
        sub=$(( entry % 8 ))
        word=$(( ((off - 0x43800) % 16) / 4 ))
        fld=$(printf 'opp+0x%x qid table B port %d slot %d word %d' "$off" "$port" "$sub" "$word")
        E lsw opp 0x12400000 "$off" "LSW-SPEC.md 7.3" "$fld" unknown "[V] table shape; [I] 0x100 flag + qid low byte; W1 baseline"
        off=$((off + 4))
    done

    # ---- PIE window 0x10a70000 (64 KiB), PIE-DATAPATH.md 4.1-4.3 / section 11.2 P3 ----
    E pie global 0x10a70000 0x1000 "PIE-DATAPATH.md 4.3" "pie+0x1000 global control (bit0 cleared, bits6-8 set)" "clear:0x1;mask:0x1c0" "[V] write model; [I] live"
    E pie global 0x10a70000 0x2200 "PIE-DATAPATH.md 4.3" "pie+0x2200 DFX counter control (bit21 clear-then-set)" unknown "[V] addr; [U] meaning"
    E pie global 0x10a70000 0x3200 "PIE-DATAPATH.md 4.3" "pie+0x3200 RX enable/mode (bit0 global RX enable)" "mask:0x1" "[V] bit0 write; [I] live RX enabled"
    E pie global 0x10a70000 0x3204 "PIE-DATAPATH.md 4.3" "pie+0x3204 reg_init writes 0" "eq:0x0" "[V] write value"
    E pie global 0x10a70000 0x3208 "PIE-DATAPATH.md 4.3" "pie+0x3208 reg_init writes 0x7d" "eq:0x7d" "[V] write value"
    E pie global 0x10a70000 0x3404 "PIE-DATAPATH.md 4.3" "pie+0x3404 2-bit per-channel field (rx_init_chan)" unknown "[U] cfg[16] and 3 per channel"
    E pie global 0x10a70000 0x3408 "PIE-DATAPATH.md 4.3" "pie+0x3408 large-ring per-channel bitmap (ring over 9600 B)" "eq:0x0" "[I] board RX rings are 32 KiB / 2048 B buffers"
    E pie global 0x10a70000 0x3700 "PIE-DATAPATH.md 4.3" "pie+0x3700 GRO ring size minus 1 (only when a GRO ring is configured)" unknown "[U] board DT has no gro_ring"
    for ch in 0 1 2 3 4 5 6 7; do
        exp=unknown
        if [ "$ch" -lt 4 ]; then exp="eq:0x1"; fi
        E pie chan 0x10a70000 $((0x180 + ch * 4)) "PIE-DATAPATH.md 4.3" "pie+0x180+chN*4 per-channel word (ch=$ch)" "$exp" "[V] reg_init writes 1; [U] meaning"
        exp=unknown
        if [ "$ch" -lt 4 ]; then exp="eq:0x1"; fi
        E pie chan 0x10a70000 $((0x200 + ch * 4)) "PIE-DATAPATH.md 4.3" "pie+0x200+chN*4 per-channel word (ch=$ch)" "$exp" "[V] reg_init writes 1; [U] meaning"
        E pie chan 0x10a70000 $((0x300 + ch * 4)) "PIE-DATAPATH.md 4.2" "pie+0x300+chN*4 RX interrupt status word (bit0)" dynamic "[V] R/W1C; volatile"
        exp=unknown
        if [ "$ch" -lt 4 ]; then exp="eq:0x1"; fi
        E pie chan 0x10a70000 $((0x380 + ch * 4)) "PIE-DATAPATH.md 4.3" "pie+0x380+chN*4 per-channel word (ch=$ch)" "$exp" "[V] reg_init writes 1; [U] meaning"
        exp=unknown
        if [ "$ch" -lt 4 ]; then exp="eq:0x0"; fi
        E pie chan 0x10a70000 $((0x400 + ch * 4)) "PIE-DATAPATH.md 4.2" "pie+0x400+chN*4 RX interrupt mask (1 = masked, ch=$ch)" "$exp" "[V] write 0/1; [I] wired channels unmasked after init"
        exp=unknown
        if [ "$ch" -lt 4 ]; then exp="eq:0x3"; fi
        E pie chan 0x10a70000 $((0x3210 + ch * 4)) "PIE-DATAPATH.md 4.3" "pie+0x3210+chN*4 reg_init per-channel word (ch=$ch)" "$exp" "[V] reg_init writes 3; [U] meaning"
        exp=unknown
        if [ "$ch" -lt 4 ]; then exp="eq:0x2"; fi
        E pie chan 0x10a70000 $((0x3290 + ch * 4)) "PIE-DATAPATH.md 4.3" "pie+0x3290+chN*4 reg_init per-channel word (ch=$ch)" "$exp" "[V] reg_init writes 2; [U] meaning"
        exp=unknown
        if [ "$ch" -lt 4 ]; then exp="eq:0x8"; fi
        E pie chan 0x10a70000 $((0x3310 + ch * 4)) "PIE-DATAPATH.md 4.3" "pie+0x3310+chN*4 reg_init per-channel word (ch=$ch)" "$exp" "[V] reg_init writes 8; [U] meaning"
    done
    for ch in 0 1 2 3; do
        E pie txring 0x10a70000 $((0x2000 + ch * 16)) "PIE-DATAPATH.md 4.1" "pie+0x2000+chN*0x10 TX ring base address (ch=$ch)" nonzero "[V] write; [I] DMA base nonzero after init"
        E pie txring 0x10a70000 $((0x2004 + ch * 16)) "PIE-DATAPATH.md 4.1" "pie+0x2004+chN*0x10 TX channel config / ring-size shift N (ch=$ch)" "eq:0xc" "[I] DT tx_ring first word 0xc"
        E pie txring 0x10a70000 $((0x2008 + ch * 16)) "PIE-DATAPATH.md 4.1" "pie+0x2008+chN*0x10 TX write pointer / doorbell (ch=$ch)" dynamic "[V] volatile; advances with TX"
        E pie txring 0x10a70000 $((0x200c + ch * 16)) "PIE-DATAPATH.md 4.1" "pie+0x200c+chN*0x10 TX read pointer low 16 bits (ch=$ch)" dynamic "[V] volatile"
        E pie rxring 0x10a70000 $((0x3000 + ch * 16)) "PIE-DATAPATH.md 4.1" "pie+0x3000+chN*0x10 RX ring base address (ch=$ch)" nonzero "[V] write; [I] DMA base nonzero after init"
        E pie rxring 0x10a70000 $((0x3004 + ch * 16)) "PIE-DATAPATH.md 4.1" "pie+0x3004+chN*0x10 RX channel config / ring-size shift N (ch=$ch)" "eq:0xa" "[I] DT rx_ring first word 0xa"
        E pie rxring 0x10a70000 $((0x3008 + ch * 16)) "PIE-DATAPATH.md 4.1" "pie+0x3008+chN*0x10 RX write pointer (15:0) and sf pointer (31:16) (ch=$ch)" dynamic "[V] volatile"
        E pie rxring 0x10a70000 $((0x300c + ch * 16)) "PIE-DATAPATH.md 4.1" "pie+0x300c+chN*0x10 RX read pointer low 16 bits (ch=$ch)" dynamic "[V] volatile"
        E pie rxring 0x10a70000 $((0x3504 + ch * 16)) "PIE-DATAPATH.md 4.3" "pie+0x3504+chN*0x10 RX ring-size config (ring size >> 7) (ch=$ch)" "eq:0x100" "[I] 32 KiB RX ring gives 0x100"
    done

    # ---- CRG window 0x14880000 (4 KiB), MISC-SOC-BLOCKS.md 5.2/5.3 + Appendix C ----
    E crg gate 0x14880000 0x14 "MISC-SOC-BLOCKS.md 5.2" "CRG gate word 0x14 (sfc/gpio/i2c/led_pwm group)" unknown "[V] measured fresh-boot ref 0x01360ef1 (2026-10-07); write-1-set latch class"
    E crg gate 0x14880000 0x20 "MISC-SOC-BLOCKS.md 5.2" "CRG gate word 0x20 (gemac/pie/lsw group)" unknown "[V] measured ref 0x02f8300b (2026-10-07)"
    E crg reset 0x14880000 0x2c "MISC-SOC-BLOCKS.md 5.2" "CRG reset word 0x2c" unknown "[V] addr; [U] live bits; never write"
    E crg reset 0x14880000 0x30 "MISC-SOC-BLOCKS.md 5.2" "CRG reset word 0x30 (lsw dp/pfe, pie, mdio)" unknown "[V] LSW/PIE reset bits live here; [U] live bits; never write"
    E crg reset 0x14880000 0x34 "MISC-SOC-BLOCKS.md 5.2" "CRG reset word 0x34 (PCIe RC / efuse / core)" unknown "[V] measured 0x000ff309 with both RCs up (2026-10-07); never write"
    E crg resume 0x14880000 0x38 "SMP-RE.md 4; MISC-SOC-BLOCKS.md 6.3" "CRG resume/softrst word (CPU1 resume bits 0x16/0x18, 0x17/0x19)" unknown "[V] addr from SMP RE; [U] live bits; SMP lane owns semantics; never write"
    E crg pll 0x14880000 0x90 "MISC-SOC-BLOCKS.md 5.2/5.3" "CRG PLL status (bit30 cpu PLL lock, bit27 lsw PLL lock)" "mask:0x48000000" "[V] measured 0x6a010008 / 0x6a090008; lock bits set"
    E crg wdt 0x14880000 0x100 "MISC-SOC-BLOCKS.md 5.3" "CRG watchdog ISTATUS word" "eq:0x0" "[V] measured 0x00000000; read-only"
    E crg mux 0x14880000 0x138 "MISC-SOC-BLOCKS.md 5.2" "CRG clock mux: bit1 efuse source, bit3 CPU source" unknown "[V] addr/polarity; [U] live; never write bit3 (CPU clock)"
    E crg pll 0x14880000 0x198 "MISC-SOC-BLOCKS.md 5.3" "PLL1 control word0 (int bits23:12, fbdiv byte3, divider-select byte0)" unknown "[V] field decode; rate = osc*(int+frac/2^24)/fbdiv; read-only"
    E crg pll 0x14880000 0x19c "MISC-SOC-BLOCKS.md 5.3" "PLL1 control word1 (24-bit fraction bits23:0)" unknown "[V] field decode; read-only"
    E crg pll 0x14880000 0x1e0 "MISC-SOC-BLOCKS.md 5.3" "PLL2 control word0 (int/fbdiv/divider-select)" unknown "[V] field decode; read-only"
    E crg pll 0x14880000 0x1e4 "MISC-SOC-BLOCKS.md 5.3" "PLL2 control word1 (24-bit fraction bits23:0)" unknown "[V] field decode; read-only"

    # ---- SYSCTRL window 0x10100000 (4 KiB), MISC-SOC-BLOCKS.md 6.3 + SELECTOR-0x21.md ----
    E sysctrl smp 0x10100000 0xc00 "MISC-SOC-BLOCKS.md 6.3; SMP-RE.md" "SYSCTRL SMP release/pen word (smp-offset)" unknown "[V] offset/writer; [U] semantics/live; SMP lane owns it; never write"
    E sysctrl selector 0x10100000 0xc08 "SELECTOR-0x21.md 1.1" "SYSCTRL boot selector cell (low byte pair; upper 24 bits unmeasured)" pair "[V] observed 0x00/0x10/0x11 and manual 0x21; writer loader+hi_ksysenv; cross-check sysfs; never write"
    E sysctrl rstinfo 0x10100000 0xc10 "MISC-SOC-BLOCKS.md 6.3" "SYSCTRL reset record cell (rstinfo record_addr)" unknown "[V] writer vendor machine reset code; [U] layout; do not interpret; never write"
}

# decision helper for one address; empty output = inside a window (allowlist membership is
# checked separately). This is what --explain-address and the pre-send self-check use.
addr_reason() {
    local a=$1 n b
    case $a in
        0x[0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]) ;;
        *) echo "not a 0x-prefixed 8-hex-digit 32-bit address"; return 0 ;;
    esac
    case $a in
        *0|*4|*8|*c) ;;
        *) echo "unaligned: only 32-bit aligned reads are allowed"; return 0 ;;
    esac
    n=$((a))
    if [ "$n" -ge $((0x10160000)) ] && [ "$n" -le $((0x1016ffff)) ]; then
        echo "forbidden RC misc window 0x10160000-0x1016ffff, includes 0x10161000 (never read; BENCH-FACTS.md section 6, HAZARDS.md section 9)"
        return 0
    fi
    if [ "$n" -eq $((0x400392f0)) ]; then
        echo "forbidden CA address 0x400392f0 (never write; the CA space is out of scope)"
        return 0
    fi
    if [ "$n" -ge $((0x10100000)) ] && [ "$n" -le $((0x10100fff)) ]; then return 0; fi
    if [ "$n" -ge $((0x10a70000)) ] && [ "$n" -le $((0x10a7ffff)) ]; then return 0; fi
    if [ "$n" -ge $((0x14880000)) ] && [ "$n" -le $((0x14880fff)) ]; then return 0; fi
    for b in 0x11000000 0x11080000 0x11100000 0x11180000 0x11200000 0x11280000 0x11380000 0x12000000 0x12080000 0x12100000 0x12180000 0x12280000 0x12380000 0x12400000 0x12480000; do
        if [ "$n" -ge "$((b))" ] && [ "$n" -lt "$((b + 0x80000))" ]; then return 0; fi
    done
    echo "outside the four allowlisted windows (SYSCTRL 0x10100000, PIE 0x10a70000, LSW 0x11/0x12 windows, CRG 0x14880000)"
}

filter_plan() {
    awk -F"$TAB" -v list=",$SEL_GROUPS," 'index(list, "," $1 ",") > 0'
}

validate_selected_plan() {
    local g b a spec _field exp note reason bad=0
    while IFS="$TAB" read -r g b a spec _field exp note; do
        reason=$(addr_reason "$a")
        if [ -n "$reason" ]; then
            echo "internal allowlist violation: $a: $reason" >&2
            bad=$((bad + 1))
        fi
    done < "$OUT/.allowlist.sel"
    [ "$bad" -eq 0 ]
}

mode_print_plan() {
    local n
    n=$(emit_allowlist | filter_plan | wc -l | tr -d '[:space:]')
    echo "bench-inventory plan v1 (READ-ONLY; no device contact in this mode)"
    printf 'group%sblock%saddr%sspec%sfield%sexpected%snote' "$TAB" "$TAB" "$TAB" "$TAB" "$TAB" "$TAB"
    echo
    emit_allowlist | filter_plan
    echo
    echo "# planned reads: $n"
    echo "# groups selected: $SEL_GROUPS"
    echo "# NEVER read (hard exclusions):"
    echo "#   0x10160000-0x1016ffff  RC misc window, includes 0x10161000 (a read panicked the box)"
    echo "#   0x400392f0             CA write-forbidden address (CA space out of scope)"
    echo "#   any address outside SYSCTRL 0x10100000 / PIE 0x10a70000 / LSW 0x11-0x12 windows / CRG 0x14880000"
    echo "#   any unaligned access; any write of any kind (the tool has no write path)"
    exit 0
}

mode_explain() {
    local addr hit reason
    addr=$(printf '%s' "$EXPLAIN_ADDR" | tr '[:upper:]' '[:lower:]')
    reason=$(addr_reason "$addr")
    if [ -n "$reason" ]; then
        echo "DENY $EXPLAIN_ADDR: $reason"
        exit 1
    fi
    hit=$(emit_allowlist | awk -F"$TAB" -v a="$addr" '$3 == a { if (!found) { line = $1 "/" $2 ": " $5; found = 1 } } END { if (found) print line }')
    if [ -n "$hit" ]; then
        echo "ALLOW $addr: $hit"
        exit 0
    fi
    echo "DENY $addr: not an exact address in the allowlist table (only spec-backed exact addresses are read)"
    exit 1
}

# ---------------------------------------------------------------------------
# argument parsing and validation
# ---------------------------------------------------------------------------
while [ $# -gt 0 ]; do
    case $1 in
        --attended) ATTENDED=1 ;;
        --no-uart) NO_UART=1 ;;
        --no-context) NO_CONTEXT=1 ;;
        --check-only) CHECK_ONLY=1 ;;
        --print-plan) PRINT_PLAN=1 ;;
        --explain-address)
            [ $# -ge 2 ] || die_usage "--explain-address needs an address"
            EXPLAIN_ADDR=$2
            shift
            ;;
        --label)
            [ $# -ge 2 ] || die_usage "--label needs a value"
            LABEL=$2
            shift
            ;;
        --out)
            [ $# -ge 2 ] || die_usage "--out needs a directory"
            OUT=$2
            shift
            ;;
        --groups)
            [ $# -ge 2 ] || die_usage "--groups needs a value"
            SEL_GROUPS=$2
            shift
            ;;
        --batch)
            [ $# -ge 2 ] || die_usage "--batch needs a value"
            BATCH=$2
            shift
            ;;
        --repeat)
            [ $# -ge 2 ] || die_usage "--repeat needs a value"
            REPEAT=$2
            shift
            ;;
        --ssh-timeout)
            [ $# -ge 2 ] || die_usage "--ssh-timeout needs a value"
            SSH_TIMEOUT=$2
            shift
            ;;
        --connect-timeout)
            [ $# -ge 2 ] || die_usage "--connect-timeout needs a value"
            CONNECT_TIMEOUT=$2
            shift
            ;;
        --max-failed-batches)
            [ $# -ge 2 ] || die_usage "--max-failed-batches needs a value"
            MAX_FAILED_BATCHES=$2
            shift
            ;;
        -h|--help) usage; exit 0 ;;
        *) die_usage "unknown argument: $1" ;;
    esac
    shift
done

need_int() {
    case $1 in
        ''|*[!0-9]*) return 1 ;;
    esac
    return 0
}

if [ -n "$EXPLAIN_ADDR" ]; then
    [ "$PRINT_PLAN" -eq 0 ] || die_usage "--print-plan and --explain-address are mutually exclusive"
    mode_explain
fi
if [ "$PRINT_PLAN" -eq 1 ]; then
    [ -z "$OUT" ] || die_usage "--print-plan does not take --out"
    mode_print_plan
fi

case $LABEL in
    ''|*[!A-Za-z0-9_-]*) die_usage "--label must use only [A-Za-z0-9_-]" ;;
esac
need_int "$BATCH" || die_usage "--batch must be an integer"
[ "$BATCH" -ge 1 ] && [ "$BATCH" -le 32 ] || die_usage "--batch must be 1..32"
need_int "$REPEAT" || die_usage "--repeat must be an integer"
[ "$REPEAT" -ge 1 ] && [ "$REPEAT" -le 3 ] || die_usage "--repeat must be 1..3"
need_int "$SSH_TIMEOUT" || die_usage "--ssh-timeout must be an integer"
[ "$SSH_TIMEOUT" -ge 5 ] && [ "$SSH_TIMEOUT" -le 120 ] || die_usage "--ssh-timeout must be 5..120"
need_int "$CONNECT_TIMEOUT" || die_usage "--connect-timeout must be an integer"
[ "$CONNECT_TIMEOUT" -ge 1 ] && [ "$CONNECT_TIMEOUT" -le 60 ] || die_usage "--connect-timeout must be 1..60"
need_int "$MAX_FAILED_BATCHES" || die_usage "--max-failed-batches must be an integer"
[ "$MAX_FAILED_BATCHES" -ge 1 ] && [ "$MAX_FAILED_BATCHES" -le 20 ] || die_usage "--max-failed-batches must be 1..20"

for g in $(printf '%s' "$SEL_GROUPS" | tr ',' ' '); do
    case $g in
        lsw|pie|crg|sysctrl) ;;
        *) die_usage "unknown --groups entry: $g (allowed: lsw pie crg sysctrl)" ;;
    esac
done

if [ "$CHECK_ONLY" -eq 1 ]; then MODE='check-only'; fi

# ---------------------------------------------------------------------------
# evidence directory
# ---------------------------------------------------------------------------
init_out() {
    local ts
    if [ -z "$OUT" ]; then
        ts=$(date -u +%Y%m%dT%H%M%SZ)
        OUT="$ROOT/build/bench-inventory/$ts-$LABEL"
    fi
    if ! mkdir -p "$OUT" 2>/dev/null; then
        if command -v sudo >/dev/null 2>&1 && sudo -n true 2>/dev/null; then
            sudo -n mkdir -p "$OUT" || return 1
            sudo -n chown "$(id -u):$(id -g)" "$OUT" 2>/dev/null || true
        else
            return 1
        fi
    fi
    [ -w "$OUT" ] || return 1
    mkdir -p "$OUT/batches" || return 1
    mkdir -p "$OUT/context" || return 1
    LOG="$OUT/inventory.log"
    : > "$LOG"
    GATE_FILE="$OUT/.gates.tsv"
    : > "$GATE_FILE"
    HEALTHCHK="$OUT/.healthchecks-pre.tsv"
    : > "$HEALTHCHK"
    POSTCHK="$OUT/.healthchecks-post.tsv"
    : > "$POSTCHK"
    READS="$OUT/.reads.tsv"
    : > "$READS"
    ATTEMPTED="$OUT/.attempted.tsv"
    : > "$ATTEMPTED"
    MERGED="$OUT/.merged.tsv"
    : > "$MERGED"
    ANALYSIS="$OUT/.analysis.tsv"
    : > "$ANALYSIS"
    BATCHDIR="$OUT/batches"
    CTXDIR="$OUT/context"
    CONTEXT_IDX="$OUT/.context.idx"
    : > "$CONTEXT_IDX"
    COMMANDS="$OUT/commands.txt"
    : > "$COMMANDS"
    PLAN="$OUT/plan.tsv"
    return 0
}

emit_command_block() {
    echo "== $1 ==" >> "$COMMANDS"
    echo "$2" >> "$COMMANDS"
    echo "== END $1 ==" >> "$COMMANDS"
}

sanitize_line() {
    printf '%s' "$1" | tr '[:cntrl:]' ' ' | tr -s ' '
}

# ---------------------------------------------------------------------------
# fail-closed gates (all local gates run before the first SSH contact; if any local gate
# fails the tool refuses without touching the device)
# ---------------------------------------------------------------------------
gate_check() {
    local name=$1 status=$2 detail
    detail=$(sanitize_line "$3")
    echo "$name$TAB$status$TAB$detail" >> "$GATE_FILE"
    case $status in
        PASS) say "  PASS  $name - $detail" ;;
        WARN) say "  WARN  $name - $detail" ;;
        *) GATE_FAIL=$((GATE_FAIL + 1)); say "  FAIL  $name - $detail" ;;
    esac
}

ancestor_pids() {
    local p=$$
    while [ -n "$p" ] && [ "$p" -gt 1 ]; do
        echo "$p"
        p=$(ps -o ppid= -p "$p" 2>/dev/null | tr -d '[:space:]')
    done
}

matching_pids() {
    local pat=$1 pid
    for pid in $(pgrep -f "$pat" 2>/dev/null); do
        case " $ANCESTORS " in
            *" $pid "*) ;;
            *) echo "$pid" ;;
        esac
    done
}

capture_pids() {
    local pf pid out=
    for pf in "$ROOT"/build/uart-logs/*.pid; do
        [ -f "$pf" ] || continue
        pid=$(cat "$pf" 2>/dev/null) || continue
        case $pid in
            ''|*[!0-9]*) continue ;;
        esac
        if kill -0 "$pid" 2>/dev/null || sudo -n kill -0 "$pid" 2>/dev/null; then
            out="$out $pid"
        fi
    done
    for pid in $(matching_pids 'timeout [0-9]+ cat'); do
        out="$out $pid"
    done
    printf '%s' "$out" | tr -s ' '
}

gate_local() {
    local out pids stale cpid
    ANCESTORS=$(ancestor_pids | tr '[:space:]' ' ')

    if [ "$ATTENDED" -eq 1 ]; then
        gate_check attended PASS "operator marked the bench attended (--attended)"
    else
        gate_check attended FAIL "missing --attended: a human must be at the bench for the whole read (recovery is physical)"
    fi

    if [ -x "$ROOT/tools/rsh.sh" ] && [ -f "$ROOT/.omo-secrets/router_ed25519" ]; then
        gate_check transport PASS "tools/rsh.sh and the project SSH key are present"
    else
        gate_check transport FAIL "missing tools/rsh.sh or .omo-secrets/router_ed25519"
    fi

    pids=$(matching_pids 'bash .*fire-ssh[.]sh|bash .*fire-device[.]sh|bash .*run-phase[0-9a-z]+[.]sh')
    if [ -n "$(printf '%s' "$pids" | tr -d '[:space:]')" ]; then
        gate_check no-active-fire FAIL "another fire driver is running (pids:$pids); never run two device actions at once"
    else
        gate_check no-active-fire PASS "no fire driver is running"
    fi

    if out=$(timeout 60 "$ROOT/tools/bench-link.sh" 2>&1); then
        gate_check bench-link PASS "tools/bench-link.sh PASS"
    else
        printf '%s' "$out" > "$OUT/gate-bench-link.out"
        gate_check bench-link FAIL "tools/bench-link.sh failed: $(printf '%s' "$out" | tail -n 3 | tr '[:space:]' ' ')"
    fi

    if out=$(timeout 60 "$ROOT/tools/recovery-card.sh" 2>&1); then
        case $out in
            *"recovery door is READY"*) gate_check recovery-door PASS "tools/recovery-card.sh reports the recovery door READY (physical trigger)" ;;
            *) printf '%s' "$out" > "$OUT/gate-recovery.out"; gate_check recovery-door FAIL "recovery-card.sh exited 0 but did not report READY" ;;
        esac
    else
        printf '%s' "$out" > "$OUT/gate-recovery.out"
        gate_check recovery-door FAIL "tools/recovery-card.sh failed: $(printf '%s' "$out" | tail -n 3 | tr '[:space:]' ' ')"
    fi

    if [ "$NO_UART" -eq 1 ]; then
        gate_check uart-capture WARN "disabled with --no-uart: a hang cannot be observed; the evidence is not fire-class"
    else
        cpid=$(capture_pids | awk '{ print $1 }')
        if [ -n "$cpid" ]; then
            gate_check uart-capture PASS "read-only UART capture is running (pid $cpid)"
        else
            gate_check uart-capture FAIL "no read-only UART capture; start tools/uart-capture.sh start --label <label> (or pass --no-uart)"
        fi
    fi

    stale=$(matching_pids 'tee -a .*/fire-')
    if [ -n "$(printf '%s' "$stale" | tr -d '[:space:]')" ]; then
        gate_check stale-writers WARN "stale fire-log writer(s) still running (pids:$stale); clean with tools/bench-teardown.sh --apply"
    else
        gate_check stale-writers PASS "no stale fire-log writers"
    fi

    [ "$GATE_FAIL" -eq 0 ]
}

# ---------------------------------------------------------------------------
# device health probe: stock vendor system per RUNBOOK.md section 0 / BENCH-FACTS.md
# ---------------------------------------------------------------------------
health_script() {
cat <<'HS'
# BENCH_INV_HEALTH v1
echo "BENCH_INV_HEALTH_OK=1"
echo "uname_r=$(uname -r 2>/dev/null)"
echo "uname_v=$(uname -v 2>/dev/null)"
echo "release=$(cat /etc/openwrt_release 2>/dev/null | grep '^DISTRIB_RELEASE=' | cut -d= -f2 | tr -d "'")"
echo "boot_id=$(cat /proc/sys/kernel/random/boot_id 2>/dev/null)"
echo "uptime=$(cut -d. -f1 /proc/uptime 2>/dev/null)"
echo "bootflag=$(fw_printenv bootflag 2>/dev/null | grep '^bootflag=' | cut -d= -f2)"
echo "boot_reg_sysfs=$(cat /sys/devices/platform/sysenv/boot_reg 2>/dev/null)"
echo "wiphy=$(ls -1 /sys/class/ieee80211 2>/dev/null | wc -l | tr -d '[:space:]')"
echo "hi_mods=$(lsmod 2>/dev/null | grep -c '^hi_')"
echo "omo_off=$(ls /lib/modules/*/*.omo-off 2>/dev/null | wc -l | tr -d '[:space:]')"
echo "overlay_ko=$(ls /overlay/upper/lib/hisilicon/ko/*.ko 2>/dev/null | wc -l | tr -d '[:space:]')"
echo "cal2g=$(dmesg 2>/dev/null | grep -c 'hwifi_rf_cali_file_load_2g succ')"
echo "cal5g=$(dmesg 2>/dev/null | grep -c 'hwifi_rf_cali_file_load_5g succ')"
echo "mtd11=$(grep -c '^mtd11:' /proc/mtd 2>/dev/null)"
echo "mtd12=$(grep -c '^mtd12:' /proc/mtd 2>/dev/null)"
echo "mtd13=$(grep -c '^mtd13:' /proc/mtd 2>/dev/null)"
echo "mtd14=$(grep -c '^mtd14:' /proc/mtd 2>/dev/null)"
echo "mtd_names=$(grep -E '^mtd(11|12|13|14):' /proc/mtd 2>/dev/null | cut -d'"' -f2 | tr '[:space:]' ',')"
echo "rootfs_mtd_num=$(cat /sys/class/ubi/ubi0/mtd_num 2>/dev/null)"
echo "devmem=$(command -v devmem 2>/dev/null)"
echo "devmem_sbin=$([ -x /sbin/devmem ] && echo yes || echo no)"
echo "dd=$(command -v dd 2>/dev/null)"
echo "hexdump=$(command -v hexdump 2>/dev/null)"
echo "od=$(command -v od 2>/dev/null)"
echo "mem_readable=$([ -r /dev/mem ] && echo yes || echo no)"
DEV=$(command -v devmem 2>/dev/null)
if [ -z "$DEV" ] && [ -x /sbin/devmem ]; then DEV=/sbin/devmem; fi
if [ -n "$DEV" ]; then
    echo "devmem_probe=$($DEV 0x14880090 32 2>/dev/null)"
else
    echo "devmem_probe="
fi
HS
}

probe_health() {
    local tag=$1 out rc
    out=$(timeout 30 "$ROOT/tools/rsh.sh" "$(health_script)" 2>/dev/null)
    rc=$?
    printf '%s' "$out" > "$OUT/health-$tag.raw"
    echo >> "$OUT/health-$tag.raw"
    HEALTH_RC=$rc
    emit_command_block "health-$tag" "$(health_script)"
}

health_get() {
    local file=$1 key=$2 line
    line=$(grep -m1 -F "$key=" "$file" 2>/dev/null) || line=
    printf '%s' "$line" | cut -d= -f2-
}

is_uint() {
    case $1 in
        ''|*[!0-9]*) return 1 ;;
    esac
    return 0
}

check_add() {
    local file=$1 name=$2 status=$3 detail
    detail=$(sanitize_line "$4")
    echo "$name$TAB$status$TAB$detail" >> "$file"
}

check_fails() {
    awk -F"$TAB" '$2 == "FAIL" { n++ } END { print n + 0 }' "$1"
}

norm32() {
    local v len
    v=$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')
    case $v in
        0x*) v=$(printf '%s' "$v" | cut -c3-) ;;
    esac
    case $v in
        ''|*[!0-9a-f]*) return 1 ;;
    esac
    len=$(printf '%s' "$v" | wc -c | tr -d '[:space:]')
    [ "$len" -le 8 ] || return 1
    while [ "$len" -lt 8 ]; do
        v="0$v"
        len=$((len + 1))
    done
    printf '0x%s' "$v"
}

eval_health_pre() {
    local f="$OUT/health-pre.raw" v w c2 c5 hi omo want
    : > "$HEALTHCHK"

    if [ "$HEALTH_RC" -ne 0 ]; then
        check_add "$HEALTHCHK" health-probe FAIL "rsh.sh exited $HEALTH_RC (box unreachable?)"
        return 1
    fi
    if ! grep -qF 'BENCH_INV_HEALTH_OK=1' "$f"; then
        check_add "$HEALTHCHK" health-probe FAIL "health marker missing (unreachable, or the remote shell is not the stock system)"
        return 1
    fi
    check_add "$HEALTHCHK" health-probe PASS "device health probe answered"

    v=$(health_get "$f" uname_r)
    if [ "$v" = "$STOCK_KERNEL_RELEASE" ]; then
        check_add "$HEALTHCHK" stock-kernel-release PASS "uname -r = $v"
    else
        check_add "$HEALTHCHK" stock-kernel-release FAIL "uname -r = '$v', expected stock $STOCK_KERNEL_RELEASE"
    fi

    v=$(health_get "$f" uname_v)
    case $v in
        *"$STOCK_KERNEL_VER"*) check_add "$HEALTHCHK" stock-kernel-build PASS "uname -v carries the stock build stamp" ;;
        *) check_add "$HEALTHCHK" stock-kernel-build FAIL "uname -v = '$v', expected to contain '$STOCK_KERNEL_VER'" ;;
    esac

    v=$(health_get "$f" release)
    if [ "$v" = "$STOCK_OPENWRT_RELEASE" ]; then
        check_add "$HEALTHCHK" stock-userspace PASS "OpenWrt release $v"
    else
        check_add "$HEALTHCHK" stock-userspace FAIL "OpenWrt release = '$v', expected $STOCK_OPENWRT_RELEASE"
    fi

    w=$(health_get "$f" wiphy)
    c2=$(health_get "$f" cal2g)
    c5=$(health_get "$f" cal5g)
    if is_uint "$w" && [ "$w" -ge 2 ] && is_uint "$c2" && [ "$c2" -ge 1 ] && is_uint "$c5" && [ "$c5" -ge 1 ]; then
        check_add "$HEALTHCHK" vendor-wifi PASS "2+ wiphys, calibration [SUCC] on both bands"
    else
        check_add "$HEALTHCHK" vendor-wifi FAIL "wiphy=$w cal2g=$c2 cal5g=$c5 (need wiphy>=2 and both calibration succ lines)"
    fi

    hi=$(health_get "$f" hi_mods)
    if is_uint "$hi" && [ "$hi" -ge 30 ]; then
        check_add "$HEALTHCHK" vendor-modules PASS "$hi hi_ modules loaded"
    else
        check_add "$HEALTHCHK" vendor-modules FAIL "hi_mods=$hi (stock vendor stack expects about 40)"
    fi

    omo=$(health_get "$f" omo_off)
    if [ "$omo" = "0" ]; then
        check_add "$HEALTHCHK" no-omo-off PASS "no .omo-off leftovers"
    else
        check_add "$HEALTHCHK" no-omo-off FAIL "omo_off=$omo; hidden vendor modules mean the box is not stock"
    fi

    if [ "$(health_get "$f" mtd11)" = "1" ] && [ "$(health_get "$f" mtd12)" = "1" ] && [ "$(health_get "$f" mtd13)" = "1" ] && [ "$(health_get "$f" mtd14)" = "1" ]; then
        check_add "$HEALTHCHK" mtd-slots PASS "kernela/kernelb/rootfsa/rootfsb are in /proc/mtd ($(health_get "$f" mtd_names))"
    else
        check_add "$HEALTHCHK" mtd-slots FAIL "one or more of mtd11..mtd14 is missing from /proc/mtd"
    fi

    BOOTFLAG_PRE=$(health_get "$f" bootflag)
    BOOTREG_PRE=$(norm32 "$(health_get "$f" boot_reg_sysfs)")
    case $BOOTFLAG_PRE in
        a|b) check_add "$HEALTHCHK" bootflag PASS "bootflag=$BOOTFLAG_PRE" ;;
        *) check_add "$HEALTHCHK" bootflag FAIL "bootflag='$BOOTFLAG_PRE' (expected a or b)" ;;
    esac
    if [ -z "$BOOTREG_PRE" ]; then
        check_add "$HEALTHCHK" boot-reg FAIL "boot_reg sysfs value is missing or not a 32-bit value"
    else
        v=$((BOOTREG_PRE))
        want=-1
        case $BOOTFLAG_PRE in
            a) want=16 ;;
            b) want=17 ;;
        esac
        if [ "$want" -ge 0 ] && [ "$((v & 255))" -eq "$want" ]; then
            check_add "$HEALTHCHK" boot-reg PASS "selector low byte 0x$(printf '%02x' "$((v & 255))") matches bootflag=$BOOTFLAG_PRE (normal recorded pair)"
        elif [ "$want" -ge 0 ]; then
            check_add "$HEALTHCHK" boot-reg FAIL "bootflag=$BOOTFLAG_PRE but selector low byte is 0x$(printf '%02x' "$((v & 255))"); the box is not in its recorded stock boot state"
        else
            check_add "$HEALTHCHK" boot-reg FAIL "cannot check the pair without a valid bootflag (low byte 0x$(printf '%02x' "$((v & 255))"))"
        fi
    fi

    v=$(health_get "$f" rootfs_mtd_num)
    want=-1
    case $BOOTFLAG_PRE in
        a) want=13 ;;
        b) want=14 ;;
    esac
    if is_uint "$v" && [ "$want" -ge 0 ] && [ "$v" -eq "$want" ]; then
        check_add "$HEALTHCHK" rootfs-slot PASS "running rootfs is mtd$v, consistent with bootflag=$BOOTFLAG_PRE"
    else
        check_add "$HEALTHCHK" rootfs-slot FAIL "running rootfs mtd_num='$v' (expected mtd$want for bootflag=$BOOTFLAG_PRE)"
    fi

    v=$(health_get "$f" devmem)
    w=$(health_get "$f" devmem_sbin)
    if [ -n "$v" ]; then
        check_add "$HEALTHCHK" devmem-capability PASS "devmem present at $v"
    elif [ "$w" = "yes" ]; then
        check_add "$HEALTHCHK" devmem-capability PASS "devmem at /sbin/devmem"
    else
        v=$(health_get "$f" mem_readable)
        if [ "$v" = "yes" ] && [ -n "$(health_get "$f" dd)" ] && [ -n "$(health_get "$f" od)" ]; then
            check_add "$HEALTHCHK" devmem-capability PASS "no devmem; /dev/mem + dd + od fallback is available"
        else
            check_add "$HEALTHCHK" devmem-capability FAIL "no usable read path: devmem missing, /dev/mem not readable or dd/od missing"
        fi
    fi

    UPTIME_PRE=$(health_get "$f" uptime)
    if is_uint "$UPTIME_PRE"; then
        check_add "$HEALTHCHK" uptime-sane PASS "uptime $UPTIME_PRE seconds"
    else
        check_add "$HEALTHCHK" uptime-sane FAIL "uptime='$UPTIME_PRE' is not numeric"
    fi

    [ "$(check_fails "$HEALTHCHK")" -eq 0 ]
}

eval_health_post() {
    local f="$OUT/health-post.raw" v pre_id post_id pre_up post_up
    : > "$POSTCHK"
    if [ "$HEALTH_RC" -ne 0 ] || ! grep -qF 'BENCH_INV_HEALTH_OK=1' "$f"; then
        check_add "$POSTCHK" post-health-probe WARN "post-run health probe failed (rsh.sh exit $HEALTH_RC); uptime/boot_id cannot be verified"
        return 1
    fi
    check_add "$POSTCHK" post-health-probe PASS "post-run health probe answered"

    pre_id=$(health_get "$OUT/health-pre.raw" boot_id)
    post_id=$(health_get "$f" boot_id)
    if [ -n "$pre_id" ] && [ -n "$post_id" ] && [ "$pre_id" = "$post_id" ]; then
        check_add "$POSTCHK" boot-id-unchanged PASS "boot_id unchanged; the reads are from one boot"
    elif [ -n "$pre_id" ] && [ -n "$post_id" ]; then
        check_add "$POSTCHK" boot-id-unchanged FAIL "boot_id changed mid-run ($pre_id -> $post_id); the box rebooted and the inventory is INVALID"
    else
        check_add "$POSTCHK" boot-id-unchanged WARN "boot_id unavailable; cannot prove a single boot"
    fi

    pre_up=$(health_get "$OUT/health-pre.raw" uptime)
    post_up=$(health_get "$f" uptime)
    if is_uint "$pre_up" && is_uint "$post_up" && [ "$post_up" -ge "$pre_up" ]; then
        check_add "$POSTCHK" uptime-monotonic PASS "uptime $pre_up seconds -> $post_up seconds"
    elif is_uint "$pre_up" && is_uint "$post_up"; then
        check_add "$POSTCHK" uptime-monotonic FAIL "uptime went backwards (was $pre_up seconds, now $post_up seconds); the box rebooted and the inventory is INVALID"
    else
        check_add "$POSTCHK" uptime-monotonic WARN "uptime unavailable; cannot prove a single boot"
    fi

    v=$(health_get "$f" wiphy)
    if is_uint "$v" && [ "$v" -ge 2 ] && [ "$(health_get "$f" omo_off)" = "0" ]; then
        check_add "$POSTCHK" post-vendor-health PASS "2+ wiphys and no .omo-off leftovers after the reads"
    else
        check_add "$POSTCHK" post-vendor-health FAIL "wiphy=$v omo_off=$(health_get "$f" omo_off) after the reads; the box is not healthy"
    fi
    return 0
}

# ---------------------------------------------------------------------------
# read-only context capture: device tree AFTER the U-Boot overlay (answers the queue/flow
# DDR base question of LSW-SPEC.md 5.4 without any register access), the /proc/mtd map, the
# selector sysfs shadow, and clk_summary (the clk rate/parent readback of MISC-SOC-BLOCKS.md
# 5.5). Fixed path allowlist only; no globs, no writes.
# ---------------------------------------------------------------------------
context_script() {
cat <<'CTX'
# BENCH_INV_CONTEXT v1
echo "BENCH_INV_CONTEXT_OK=1"
DT=/proc/device-tree
if [ ! -d "$DT" ]; then DT=/sys/firmware/devicetree/base; fi
if [ -d "$DT" ]; then echo "DTROOT=$DT"; else echo "DTROOT="; fi
for f in model lsw_dp/reg lsw_dp/reg-names lsw_dp/port_bitmap lsw_dp/hwver lsw_pfe/reg lsw_pfe/reg-names lsw_pfe/hwver pie@0x10a70000/reg pie@0x10a70000/hwver pie@0x10a70000/rx_ring pie@0x10a70000/tx_ring pie@0x10a70000/interrupts pie@0x10a70000/dma-coherent system-controller@10100000/reg system-controller@10100000/smp-offset sysenv/bootreg-offset rstinfo@0x14880000/record_addr; do
    if [ -r "$DT/$f" ]; then
        b=$(hexdump -v -e '1/1 "%02x"' "$DT/$f" 2>/dev/null | tr -d '[:space:]')
        [ -n "$b" ] || b=$(od -An -tx1 -v "$DT/$f" 2>/dev/null | tr -d '[:space:]')
        echo "BIN $f $b"
    else
        echo "MISSING $f"
    fi
done
echo "BEGIN /proc/mtd"
cat /proc/mtd 2>/dev/null
echo "END /proc/mtd"
echo "BEGIN /proc/cmdline"
cat /proc/cmdline 2>/dev/null
echo "END /proc/cmdline"
echo "BEGIN /sys/devices/platform/sysenv/boot_reg"
cat /sys/devices/platform/sysenv/boot_reg 2>/dev/null
echo "END /sys/devices/platform/sysenv/boot_reg"
echo "BEGIN /sys/class/ubi/ubi0/mtd_num"
cat /sys/class/ubi/ubi0/mtd_num 2>/dev/null
echo "END /sys/class/ubi/ubi0/mtd_num"
echo "BEGIN /sys/kernel/debug/clk/clk_summary"
head -n 400 /sys/kernel/debug/clk/clk_summary 2>/dev/null
echo "END /sys/kernel/debug/clk/clk_summary"
echo "BENCH_INV_CONTEXT_END"
CTX
}

ctx_slug() {
    printf '%s' "$1" | tr '/' '_' | tr -d '[:space:]'
}

ctx_add_index() {
    echo "$1$TAB$2$TAB$3$TAB$4$TAB$5$TAB$6$TAB$7" >> "$CONTEXT_IDX"
}

capture_context() {
    local script rc line state curpath curfile idx dtroot dtlabel nbin nmiss ntxt
    if [ "$NO_CONTEXT" -eq 1 ]; then
        say "context: skipped (--no-context)"
        return 0
    fi
    script=$(context_script)
    if ! assert_read_only_script "$script" "context"; then
        say "context: REFUSED (internal read-only assertion failed)"
        return 1
    fi
    emit_command_block "context" "$script"
    timeout 60 "$ROOT/tools/rsh.sh" "$script" > "$OUT/context-raw.txt" 2> "$OUT/context.err"
    rc=$?
    if [ "$rc" -ne 0 ] || ! grep -qF 'BENCH_INV_CONTEXT_OK=1' "$OUT/context-raw.txt"; then
        say "context: WARN unavailable (rsh.sh exit $rc); the register inventory still stands"
        return 1
    fi

    : > "$CONTEXT_IDX"
    state=
    curpath=
    curfile=
    idx=0
    dtroot=
    nbin=0
    nmiss=0
    ntxt=0
    while IFS= read -r line; do
        if [ "$state" = "text" ]; then
            if [ "$line" = "END $curpath" ]; then
                idx=$((idx + 1))
                ctx_add_index "$idx" "$curpath" "text" "ok" "$curfile" "$(wc -c < "$curfile" | tr -d '[:space:]')" "$(sha256sum "$curfile" | cut -d' ' -f1)"
                ntxt=$((ntxt + 1))
                state=
                curpath=
                curfile=
            else
                echo "$line" >> "$curfile"
            fi
            continue
        fi
        case $line in
            DTROOT=*) dtroot=$(printf '%s' "$line" | cut -d= -f2-) ;;
            'BIN '*)
                set -- $line
                if [ $# -ge 3 ]; then
                    idx=$((idx + 1))
                    nbin=$((nbin + 1))
                    curfile=$(printf '%03d-b-%s.hex' "$idx" "$(ctx_slug "$2")")
                    echo "$3" > "$CTXDIR/$curfile"
                    ctx_add_index "$idx" "$2" "bin" "ok" "$curfile" "$(printf '%s' "$3" | wc -c | tr -d '[:space:]')" "$(sha256sum "$CTXDIR/$curfile" | cut -d' ' -f1)"
                fi
                ;;
            'MISSING '*)
                set -- $line
                if [ $# -ge 2 ]; then
                    nmiss=$((nmiss + 1))
                    ctx_add_index "-" "$2" "bin" "missing" "-" "-" "-"
                fi
                ;;
            'BEGIN '*)
                set -- $line
                if [ $# -ge 2 ]; then
                    state=text
                    curpath=$2
                    idx=$((idx + 1))
                    curfile=$(printf '%03d-t-%s.txt' "$idx" "$(ctx_slug "$2")")
                    : > "$CTXDIR/$curfile"
                fi
                ;;
            'BENCH_INV_CONTEXT_END'|'BENCH_INV_CONTEXT_OK=1'|'') ;;
            *) say "context: WARN unparsed remote line: $(sanitize_line "$line")" ;;
        esac
    done < "$OUT/context-raw.txt"

    printf '%s' "$dtroot" > "$OUT/context-dtroot.txt"
    dtlabel=$dtroot
    if [ -z "$dtlabel" ]; then dtlabel=unavailable; fi
    say "context: $nbin binary properties, $ntxt text files, $nmiss missing (device-tree root: $dtlabel)"
    return 0
}

# ---------------------------------------------------------------------------
# pre-send safety assertions. Every generated device script must pass before it is sent.
# ---------------------------------------------------------------------------
assert_read_only_script() {
    local script=$1 label=$2 line gt ok pat bad
    bad=0
    if printf '%s' "$script" | grep -qF 'BENCH_INV_ALLOW_WRITE'; then
        say "SAFETY: script carries the test-only write marker; refusing"
        return 1
    fi
    while IFS= read -r line; do
        gt=$(printf '%s' "$line" | tr -cd '>' | wc -c | tr -d '[:space:]')
        if [ "$gt" -gt 0 ]; then
            ok=$(printf '%s' "$line" | grep -o -F '2>/dev/null' | wc -l | tr -d '[:space:]')
            if [ "$gt" -ne "$ok" ]; then
                say "SAFETY: unexpected output redirection in $label script: $line"
                bad=1
            fi
        fi
    done <<< "$script"
    for pat in 'devmem[[:space:]]+0x[0-9a-f]{8}[[:space:]]+(8|16|32|64)[[:space:]]+[0-9]+([[:space:]]|$)' 'devmem[[:space:]]+0x[0-9a-f]{8}[[:space:]]+(8|16|32|64)[[:space:]]+0x[0-9a-f]' 'mtd[[:space:]]+(write|erase|unlock|lock|read)' 'flash_erase|fw_setenv|rmmod|insmod|modprobe|reboot|poweroff|halt' 'mount[[:space:]]|umount[[:space:]]' 'dd[[:space:]].*of=' 'tee[[:space:]]|sysctl[[:space:]]+-w|wget[[:space:]]|scp[[:space:]]'; do
        if printf '%s' "$script" | grep -Eq -- "$pat"; then
            say "SAFETY: forbidden token pattern in $label script: $pat"
            bad=1
        fi
    done
    [ "$bad" -eq 0 ]
}

addr_in_full_allowlist() {
    if [ -n "$ALLOW_ADDR_FILE" ] && [ -f "$ALLOW_ADDR_FILE" ]; then
        grep -qxF "$1" "$ALLOW_ADDR_FILE"
        return $?
    fi
    emit_allowlist | awk -F"$TAB" -v a="$1" '$3 == a { found = 1 } END { exit(found ? 0 : 1) }'
}

assert_script_addresses() {
    local script=$1 a
    for a in $(printf '%s' "$script" | grep -o -E '0x[0-9a-f]{8}' | sort -u); do
        if ! addr_in_full_allowlist "$a"; then
            say "SAFETY: address $a is not in the full allowlist; refusing to send"
            return 1
        fi
    done
    return 0
}

assert_batch_addresses() {
    local script=$1 list=$2 a
    for a in $(printf '%s' "$script" | grep -o -E '0x[0-9a-f]{8}' | sort -u); do
        case " $list " in
            *" $a "*) ;;
            *) say "SAFETY: address $a is not in this batch's allowlist; refusing to send"; return 1 ;;
        esac
    done
    return 0
}

# ---------------------------------------------------------------------------
# read engine: one SSH call per batch; the remote script is a fixed read-only template
# with the batch's addresses substituted in; every generated script is re-asserted read-only
# and allowlist-checked before it is sent.
# ---------------------------------------------------------------------------
batch_pass_list() {
    local i=1 out=
    while [ "$i" -le "$REPEAT" ]; do
        out="$out $i"
        i=$((i + 1))
    done
    printf '%s' "$out" | cut -c2-
}

batch_script() {
    local passes=$1 list=$2 base
    base=$(cat <<'BS'
# BENCH_INV_BATCH v1
D=$(command -v devmem 2>/dev/null)
[ -n "$D" ] || { [ -x /sbin/devmem ] && D=/sbin/devmem; }
if [ -n "$D" ]; then
    for p in __PASSES__; do
        echo "# BENCH_INV_PASS $p"
        for a in __ADDRS__; do
            v=$("$D" "$a" 32 2>/dev/null) && echo "VAL $p $a $v" || echo "ERR $p $a devmem-failed"
        done
    done
else
    for p in __PASSES__; do
        echo "# BENCH_INV_PASS $p"
        for a in __ADDRS__; do
            b=$(dd if=/dev/mem bs=4 skip=$((a/4)) count=1 2>/dev/null | od -An -tx4 2>/dev/null | tr -d '[:space:]')
            [ -n "$b" ] && echo "VAL $p $a 0x$b" || echo "ERR $p $a dd-failed"
        done
    done
fi
echo "# BENCH_INV_BATCH_END"
BS
)
    printf '%s\n' "$base" | awk -v p="$passes" -v l="$list" '{ gsub(/__PASSES__/, p); gsub(/__ADDRS__/, l); print }'
}

parse_batch_output() {
    local outfile=$1 afile=$2 label=$3 line pass addr val norm got=0 end=0 bad=0 errs=0 addrs
    addrs=$(awk '{ printf "%s ", $0 }' "$afile")
    while IFS= read -r line; do
        case $line in
            '# BENCH_INV_BATCH_END')
                end=1
                ;;
            'VAL '*)
                set -- $line
                if [ $# -lt 4 ]; then
                    say "WARN $label: malformed VAL line"
                    bad=1
                    continue
                fi
                pass=$2
                addr=$3
                val=$4
                case " $addrs " in
                    *" $addr "*) ;;
                    *)
                        say "WARN $label: output contained an address outside the batch: $addr"
                        bad=1
                        continue
                        ;;
                esac
                if norm=$(norm32 "$val"); then
                    echo "$addr$TAB$pass$TAB$norm$TAB""ok" >> "$READS"
                    got=$((got + 1))
                else
                    say "WARN $label: unparsable value for $addr"
                    bad=1
                fi
                ;;
            'ERR '*)
                set -- $line
                if [ $# -ge 3 ]; then
                    echo "$3$TAB$2$TAB-$TAB""err" >> "$READS"
                    errs=$((errs + 1))
                fi
                ;;
            '# BENCH_INV_PASS '*|'# BENCH_INV_BATCH v1'|'') ;;
            *)
                say "WARN $label: unparsed remote line: $(sanitize_line "$line")"
                ;;
        esac
    done < "$outfile"
    if [ "$end" -eq 1 ] && [ "$got" -gt 0 ] && [ "$bad" -eq 0 ] && [ "$errs" -eq 0 ]; then
        return 0
    fi
    say "WARN $label: batch output incomplete or malformed (end=$end values=$got read-errors=$errs)"
    return 1
}

run_reads() {
    local pass_list addrdir f batch_no n consec aborted listcur script safename outfile errfile rc parse_ok a
    pass_list=$(batch_pass_list)
    addrdir="$OUT/.batchaddr"
    rm -rf "$addrdir"
    mkdir -p "$addrdir" || return 1
    awk -F"$TAB" -v n="$BATCH" -v d="$addrdir" '{ b = int((FNR - 1) / n) + 1; print $4 > (d "/b" sprintf("%04d", b) ".txt") }' "$PLAN"
    BATCHES_TOTAL=$(ls "$addrdir"/b*.txt 2>/dev/null | wc -l | tr -d '[:space:]')
    BATCHES_RUN=0
    BATCHES_FAILED=0
    batch_no=0
    consec=0
    aborted=0
    for f in "$addrdir"/b*.txt; do
        [ -f "$f" ] || continue
        batch_no=$((batch_no + 1))
        if [ "$aborted" -eq 1 ]; then
            continue
        fi
        n=$(wc -l < "$f" | tr -d '[:space:]')
        listcur=$(awk '{ printf "%s ", $0 }' "$f")
        script=$(batch_script "$pass_list" "$listcur")
        safename=$(printf 'batch-%04d' "$batch_no")
        if ! assert_read_only_script "$script" "batch $batch_no"; then
            say "SAFETY: refusing the run"
            return 2
        fi
        if ! assert_batch_addresses "$script" "$listcur"; then
            say "SAFETY: refusing the run"
            return 2
        fi
        if ! assert_script_addresses "$script"; then
            say "SAFETY: refusing the run"
            return 2
        fi
        printf '%s' "$script" > "$BATCHDIR/$safename.cmd"
        emit_command_block "batch $batch_no" "$script"
        while IFS= read -r a; do
            echo "$a$TAB""A$TAB-$TAB""attempted" >> "$ATTEMPTED"
        done < "$f"
        outfile="$BATCHDIR/$safename.out"
        errfile="$BATCHDIR/$safename.err"
        timeout "$SSH_TIMEOUT" "$ROOT/tools/rsh.sh" "$script" > "$outfile" 2> "$errfile"
        rc=$?
        BATCHES_RUN=$batch_no
        parse_ok=0
        if parse_batch_output "$outfile" "$f" "batch $batch_no"; then
            parse_ok=1
        fi
        if [ "$rc" -eq 0 ] && [ "$parse_ok" -eq 1 ]; then
            say "batch $batch_no: $n addresses, complete (repeat x$REPEAT)"
            consec=0
        else
            BATCHES_FAILED=$((BATCHES_FAILED + 1))
            consec=$((consec + 1))
            say "batch $batch_no: FAILED (rsh.sh rc=$rc, parse_ok=$parse_ok, consecutive failures=$consec)"
            if [ "$consec" -ge "$MAX_FAILED_BATCHES" ]; then
                aborted=1
                say "STOPPED after $consec consecutive failures; remaining batches are NOT attempted"
            fi
        fi
    done
    if [ "$aborted" -eq 1 ] || [ "$BATCHES_FAILED" -gt 0 ]; then
        return 3
    fi
    return 0
}

# ---------------------------------------------------------------------------
# analysis: join reads against the plan, compute stability (repeat passes) and the
# expected-value diff (unknown/dynamic, nonzero, eq, mask, clear, pair).
# ---------------------------------------------------------------------------
count_field() {
    awk -F"$TAB" -v f="$1" -v v="$2" '$f == v { n++ } END { print n + 0 }' "$ANALYSIS"
}

compute_check() {
    local exp=$1 val=$2 rest tok kind num v out check detail pairval
    if [ -z "$val" ] || [ "$val" = "-" ]; then
        printf 'unknown%sno value read' "$TAB"
        return 0
    fi
    v=$((val))
    check=unknown
    detail=
    rest=$exp
    while [ -n "$rest" ]; do
        case $rest in
            *';'*)
                tok=$(printf '%s' "$rest" | cut -d';' -f1)
                rest=$(printf '%s' "$rest" | cut -d';' -f2-)
                ;;
            *)
                tok=$rest
                rest=
                ;;
        esac
        out=
        case $tok in
            unknown|dynamic)
                detail="$detail $tok"
                ;;
            nonzero)
                if [ "$v" -ne 0 ]; then out=pass; else out=fail; fi
                detail="$detail nonzero:$out"
                ;;
            pair)
                pairval=-1
                case $BOOTFLAG_PRE in
                    a) pairval=16 ;;
                    b) pairval=17 ;;
                esac
                if [ "$pairval" -lt 0 ]; then
                    detail="$detail pair:no-bootflag"
                else
                    if [ "$((v & 255))" -eq "$pairval" ]; then out=pass; else out=fail; fi
                    detail="$detail pair:want-0x$(printf '%02x' "$pairval"):$out"
                fi
                ;;
            eq:*|mask:*|clear:*)
                kind=$(printf '%s' "$tok" | cut -d: -f1)
                num=$(printf '%s' "$tok" | cut -d: -f2)
                out=fail
                if [ "$kind" = "eq" ] && [ "$v" -eq "$((num))" ]; then out=pass; fi
                if [ "$kind" = "mask" ] && [ "$((v & num))" -eq "$((num))" ]; then out=pass; fi
                if [ "$kind" = "clear" ] && [ "$((v & num))" -eq 0 ]; then out=pass; fi
                detail="$detail $kind:$out"
                ;;
            *)
                detail="$detail unknown-token:$tok"
                ;;
        esac
        if [ "$out" = "fail" ]; then
            check=fail
        elif [ "$out" = "pass" ] && [ "$check" = "unknown" ]; then
            check=pass
        fi
    done
    detail=$(printf '%s' "$detail" | tr -s ' ' | cut -c2-)
    printf '%s%s%s' "$check" "$TAB" "$detail"
}

analyze() {
    local i grp blk addr spec fld exp note reads val stable status res check detail
    cat "$READS" "$ATTEMPTED" > "$OUT/.reads2.tsv"
    awk -F"$TAB" -v rf="$OUT/.reads2.tsv" -v REPS="$REPEAT" '
    FILENAME == rf {
        if ($2 == "A") { att[$1] = 1; next }
        key = $1 SUBSEP $2
        val[key] = $3
        st[key] = $4
        next
    }
    {
        i = $1; grp = $2; blk = $3; addr = $4
        spec = $5; fld = $6; expt = $7; note = $8
        reads = ""
        value = ""
        got = 0
        errseen = 0
        first = ""
        same = 1
        for (p = 1; p <= REPS; p++) {
            key = addr SUBSEP p
            v = ""
            if (key in val) {
                if (st[key] == "ok") {
                    got++
                    v = val[key]
                    if (first == "") { first = v } else if (v != first) { same = 0 }
                } else {
                    errseen++
                }
            }
            if (p > 1) { reads = reads "," }
            if (v == "") { reads = reads "null" } else { reads = reads "\"" v "\"" }
        }
        if (got == 0) {
            if (addr in att) { status = "error" } else { status = "not-attempted" }
        } else if (got == REPS && errseen == 0) {
            status = "ok"
        } else {
            status = "partial"
        }
        if (REPS > 1) {
            if (got < REPS) { stable = "null" }
            else if (same == 1) { stable = "true" }
            else { stable = "false" }
        } else {
            stable = "null"
        }
        if (value == "" && first != "") { value = first }
        if (value == "") { value = "-" }
        print i FS grp FS blk FS addr FS spec FS fld FS expt FS note FS reads FS value FS stable FS status
    }' "$OUT/.reads2.tsv" "$PLAN" > "$MERGED"
    : > "$ANALYSIS"
    while IFS="$TAB" read -r i grp blk addr spec fld exp note reads val stable status; do
        res=$(compute_check "$exp" "$val")
        check=$(printf '%s' "$res" | cut -d"$TAB" -f1)
        detail=$(printf '%s' "$res" | cut -d"$TAB" -f2)
        echo "$i$TAB$grp$TAB$blk$TAB$addr$TAB$spec$TAB$fld$TAB$exp$TAB$note$TAB$reads$TAB$val$TAB$stable$TAB$status$TAB$check$TAB$detail" >> "$ANALYSIS"
    done < "$MERGED"
}

# ---------------------------------------------------------------------------
# evidence output: TSV + JSON + SHA256SUMS (all under the evidence directory)
# ---------------------------------------------------------------------------
emit_tsv() {
    {
        printf 'index%sgroup%sblock%saddr%sspec%sfield%sexpected%snote%sreads%svalue%sstable%sstatus%scheck%scheck_detail' "$TAB" "$TAB" "$TAB" "$TAB" "$TAB" "$TAB" "$TAB" "$TAB" "$TAB" "$TAB" "$TAB" "$TAB" "$TAB"
        echo
        if [ -s "$ANALYSIS" ]; then
            cat "$ANALYSIS"
        fi
    } > "$OUT/inventory.tsv"
}

json_str() {
    local s
    s=$(sanitize_line "$1")
    s=$(printf '%s' "$s" | tr '"' "'")
    printf '"%s"' "$s"
}

bool_json() {
    if [ "$1" -eq 1 ]; then echo true; else echo false; fi
}

json_array_from_file() {
    local f=$1 el first=1
    echo "["
    if [ -s "$f" ]; then
        while IFS= read -r el; do
            if [ "$first" -eq 1 ]; then first=0; else echo ","; fi
            printf '%s' "$el"
            echo
        done < "$f"
    fi
    echo "]"
}

build_gate_elements() {
    local name status detail
    : > "$OUT/.json-gates"
    [ -f "$GATE_FILE" ] || return 0
    while IFS="$TAB" read -r name status detail; do
        [ -n "$name" ] || continue
        printf '{"name":%s,"status":%s,"detail":%s}' "$(json_str "$name")" "$(json_str "$status")" "$(json_str "$detail")" >> "$OUT/.json-gates"
        echo >> "$OUT/.json-gates"
    done < "$GATE_FILE"
}

build_check_elements() {
    local src=$1 dest=$2 name status detail
    : > "$dest"
    [ -f "$src" ] || return 0
    while IFS="$TAB" read -r name status detail; do
        [ -n "$name" ] || continue
        printf '{"name":%s,"status":%s,"detail":%s}' "$(json_str "$name")" "$(json_str "$status")" "$(json_str "$detail")" >> "$dest"
        echo >> "$dest"
    done < "$src"
}

build_entry_elements() {
    local i grp blk addr spec fld exp note reads val stable status check detail vjson
    : > "$OUT/.json-entries"
    [ -f "$ANALYSIS" ] || return 0
    while IFS="$TAB" read -r i grp blk addr spec fld exp note reads val stable status check detail; do
        [ -n "$i" ] || continue
        if [ -n "$val" ] && [ "$val" != "-" ]; then vjson=$(json_str "$val"); else vjson=null; fi
        printf '{"i":%s,"group":%s,"block":%s,"addr":%s,"spec":%s,"field":%s,"expected":%s,"note":%s,"reads":[%s],"value":%s,"stable":%s,"status":%s,"check":%s,"check_detail":%s}'             "$i" "$(json_str "$grp")" "$(json_str "$blk")" "$(json_str "$addr")" "$(json_str "$spec")" "$(json_str "$fld")" "$(json_str "$exp")" "$(json_str "$note")" "$reads" "$vjson" "$stable" "$(json_str "$status")" "$(json_str "$check")" "$(json_str "$detail")" >> "$OUT/.json-entries"
        echo >> "$OUT/.json-entries"
    done < "$ANALYSIS"
}

build_context_elements() {
    local idx relpath typ status file bytes sha words w first bytes_json
    : > "$OUT/.json-context"
    [ -s "$CONTEXT_IDX" ] || return 0
    while IFS="$TAB" read -r idx relpath typ status file bytes sha; do
        [ -n "$relpath" ] || continue
        words=
        if [ "$typ" = "bin" ] && [ "$status" = "ok" ] && [ -n "$file" ] && [ -f "$CTXDIR/$file" ]; then
            first=1
            for w in $(fold -w 8 "$CTXDIR/$file"); do
                if [ "$first" -eq 1 ]; then
                    words="\"0x$w\""
                    first=0
                else
                    words="$words,\"0x$w\""
                fi
            done
        fi
        case $bytes in
            ''|'-') bytes_json=null ;;
            *) bytes_json=$bytes ;;
        esac
        printf '{"path":%s,"kind":%s,"status":%s,"file":%s,"bytes":%s,"sha256":%s,"words_be32":[%s]}'             "$(json_str "$relpath")" "$(json_str "$typ")" "$(json_str "$status")" "$(json_str "$file")" "$bytes_json" "$(json_str "$sha")" "$words" >> "$OUT/.json-context"
        echo >> "$OUT/.json-context"
    done < "$CONTEXT_IDX"
}

emit_health_object() {
    local f=$1 line key val first=1
    echo "{"
    if [ -f "$f" ]; then
        while IFS= read -r line; do
            case $line in
                *=*) ;;
                *) continue ;;
            esac
            key=$(printf '%s' "$line" | cut -d= -f1)
            val=$(printf '%s' "$line" | cut -d= -f2-)
            [ -n "$key" ] || continue
            if [ "$first" -eq 1 ]; then first=0; else echo ","; fi
            printf '%s:%s' "$(json_str "$key")" "$(json_str "$val")"
            echo
        done < "$f"
    fi
    echo "}"
}

emit_json() {
    local total ok_n partial_n error_n na_n chk_pass chk_fail chk_unk xval dval xlow dlow cross
    total=$(wc -l < "$ANALYSIS" | tr -d '[:space:]')
    ok_n=$(count_field 12 ok)
    partial_n=$(count_field 12 partial)
    error_n=$(count_field 12 error)
    na_n=$(count_field 12 not-attempted)
    chk_pass=$(count_field 13 pass)
    chk_fail=$(count_field 13 fail)
    chk_unk=$(count_field 13 unknown)

    build_gate_elements
    build_check_elements "$HEALTHCHK" "$OUT/.json-hchk-pre"
    build_check_elements "$POSTCHK" "$OUT/.json-hchk-post"
    build_entry_elements
    build_context_elements

    xval=$BOOTREG_PRE
    dval=$(awk -F"$TAB" '$4 == "0x10100c08" { print $10; exit }' "$ANALYSIS" 2>/dev/null)
    cross=unknown
    if [ "$dval" = "-" ]; then dval=; fi
    if [ -n "$xval" ] && [ -n "$dval" ]; then
        xlow=$((xval & 255))
        dlow=$((dval & 255))
        if [ "$xlow" -eq "$dlow" ]; then cross=pass; else cross=fail; fi
    fi

    {
        echo "{"
        printf '"tool":"bench-inventory.sh","tool_version":%s,' "$TOOL_VERSION"
        echo
        printf '"generated_utc":%s,' "$(json_str "$(date -u +%Y-%m-%dT%H:%M:%SZ)")"
        echo
        printf '"mode":%s,"result":%s,"reason":%s,' "$(json_str "$MODE")" "$(json_str "$RESULT")" "$(json_str "$REASON")"
        echo
        printf '"attended":%s,"no_uart":%s,"no_context":%s,' "$(bool_json "$ATTENDED")" "$(bool_json "$NO_UART")" "$(bool_json "$NO_CONTEXT")"
        echo
        printf '"groups":%s,"batch_size":%s,"repeat":%s,"ssh_timeout_s":%s,"connect_timeout_s":%s,' "$(json_str "$SEL_GROUPS")" "$BATCH" "$REPEAT" "$SSH_TIMEOUT" "$CONNECT_TIMEOUT"
        echo
        printf '"planned_reads":%s,"repo_head":%s,"opensource_head":%s,' "$PLAN_COUNT" "$(json_str "$REPO_HEAD")" "$(json_str "$SUB_HEAD")"
        echo
        printf '"host":%s,"target_ssh_host":%s,' "$(json_str "$HOST_ID")" "$(json_str "$TARGET_HOST")"
        echo
        printf '"summary":{"entries_total":%s,"status_ok":%s,"status_partial":%s,"status_error":%s,"status_not_attempted":%s,"checks_pass":%s,"checks_fail":%s,"checks_unknown":%s,"batches_total":%s,"batches_run":%s,"batches_failed":%s},'             "$total" "$ok_n" "$partial_n" "$error_n" "$na_n" "$chk_pass" "$chk_fail" "$chk_unk" "$BATCHES_TOTAL" "$BATCHES_RUN" "$BATCHES_FAILED"
        echo
        printf '"crosschecks":{"boot_reg_sysfs":%s,"boot_reg_devmem":%s,"boot_reg_crosscheck":%s},'             "$(if [ -n "$xval" ]; then json_str "$xval"; else echo null; fi)"             "$(if [ -n "$dval" ]; then json_str "$dval"; else echo null; fi)"             "$(json_str "$cross")"
        echo
        printf '"gates":'
        json_array_from_file "$OUT/.json-gates"
        printf ',\n"health_pre":'
        emit_health_object "$OUT/health-pre.raw"
        printf ',\n"health_post":'
        emit_health_object "$OUT/health-post.raw"
        printf ',\n"health_checks_pre":'
        json_array_from_file "$OUT/.json-hchk-pre"
        printf ',\n"health_checks_post":'
        json_array_from_file "$OUT/.json-hchk-post"
        printf ',\n"context":'
        json_array_from_file "$OUT/.json-context"
        printf ',\n"entries":'
        json_array_from_file "$OUT/.json-entries"
        echo
        echo "}"
    } > "$OUT/inventory.json"
    rm -f "$OUT/.json-gates" "$OUT/.json-hchk-pre" "$OUT/.json-hchk-post" "$OUT/.json-entries" "$OUT/.json-context"
}

write_hashes() {
    ( cd "$OUT" || exit 1; find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS )
}

finish() {
    RESULT=$1
    RC=$2
    REASON=$3
    emit_tsv
    emit_json
    say ""
    hr
    say "RESULT: $RESULT"
    say "reason: $REASON"
    say "evidence: $OUT"
    say "verify: ( cd $OUT && sha256sum -c SHA256SUMS )"
    write_hashes
    exit "$RC"
}

# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
main() {
    local read_rc post_fails total ok_n error_n na_n chk_pass chk_fail
    say "bench-inventory v$TOOL_VERSION - READ-ONLY LSW/PIE/CRG/SYSCTRL register/table inventory"
    say "time (UTC): $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    if ! init_out; then
        echo "error: cannot create a writable evidence directory (try --out DIR)" >&2
        exit 2
    fi
    MODE=inventory
    if [ "$CHECK_ONLY" -eq 1 ]; then MODE='check-only'; fi
    REPO_HEAD=$(git rev-parse --short HEAD 2>/dev/null) || REPO_HEAD=unknown
    SUB_HEAD=$(git -C opensource rev-parse --short HEAD 2>/dev/null) || SUB_HEAD=unknown
    TARGET_HOST=$(printenv ROUTER_HOST 2>/dev/null)
    if [ -z "$TARGET_HOST" ]; then TARGET_HOST=root@192.168.10.1; fi
    HOST_ID=$(id -un)@$(uname -n)
    say "mode: $MODE  groups: $SEL_GROUPS  batch: $BATCH  repeat: $REPEAT  ssh-timeout: $SSH_TIMEOUT s"
    say "repo: $REPO_HEAD  opensource: $SUB_HEAD"
    say "target: $TARGET_HOST via tools/rsh.sh (read-only)"
    say "evidence directory: $OUT"

    emit_allowlist > "$OUT/.allowlist.raw"
    awk -F"$TAB" '{ print $3 }' "$OUT/.allowlist.raw" | sort -u > "$OUT/.allow-addresses"
    ALLOW_ADDR_FILE="$OUT/.allow-addresses"
    filter_plan < "$OUT/.allowlist.raw" > "$OUT/.allowlist.sel"
    if ! validate_selected_plan; then
        finish REFUSED 2 "internal allowlist validation failed; nothing was sent to the device"
    fi
    awk -F"$TAB" 'BEGIN { OFS = FS } { print NR, $0 }' "$OUT/.allowlist.sel" > "$PLAN"
    PLAN_COUNT=$(wc -l < "$PLAN" | tr -d '[:space:]')
    rm -f "$OUT/.allowlist.raw" "$OUT/.allowlist.sel"
    if [ "$PLAN_COUNT" -eq 0 ]; then
        finish REFUSED 2 "the group selection is empty"
    fi
    say "planned reads: $PLAN_COUNT"

    hr
    say "GATES (no device contact until every local gate passes)"
    gate_local
    if [ "$GATE_FAIL" -ne 0 ]; then
        say "REFUSED: $GATE_FAIL local gate(s) failed; the device was NOT contacted"
        finish REFUSED 2 "local precondition failure; no device contact"
    fi

    hr
    say "DEVICE HEALTH (stock system gate)"
    probe_health pre
    if ! eval_health_pre; then
        say "stock-health failures:"
        awk -F"$TAB" '$2 == "FAIL" { print "  FAIL  " $1 " - " $3 }' "$HEALTHCHK"
        say "REFUSED: stock-health gate failed; the device was NOT read"
        finish REFUSED 2 "stock health gate failed; no register read"
    fi
    gate_check stock-health PASS "stock vendor system confirmed (kernel, userspace, wiphys, calibration, slots, selector, read path)"

    if [ "$MODE" = "check-only" ]; then
        hr
        say "CHECK-ONLY: gates and stock health PASS; no registers read"
        finish CHECK-ONLY-PASS 0 "gates and stock health pass (--check-only)"
    fi

    hr
    capture_context

    hr
    say "READS ($PLAN_COUNT allowlisted 32-bit reads, $REPEAT pass(es), batch size $BATCH)"
    run_reads
    read_rc=$?
    if [ "$read_rc" -eq 2 ]; then
        finish REFUSED 2 "internal read-only safety assertion failed; nothing further was sent"
    fi

    hr
    say "POST-RUN HEALTH (single-boot check)"
    probe_health post
    eval_health_post

    hr
    say "ANALYSIS"
    analyze
    total=$(wc -l < "$ANALYSIS" | tr -d '[:space:]')
    ok_n=$(count_field 12 ok)
    error_n=$(count_field 12 error)
    na_n=$(count_field 12 not-attempted)
    chk_pass=$(count_field 13 pass)
    chk_fail=$(count_field 13 fail)
    if [ "$total" -ne "$PLAN_COUNT" ]; then
        say "ANALYSIS FAILED: expected $PLAN_COUNT plan rows, got $total"
        finish PARTIAL 3 "analysis join failed; raw reads are preserved under batches/"
    fi
    say "entries: $total  ok: $ok_n  error: $error_n  not-attempted: $na_n"
    say "expected-value checks: pass: $chk_pass  fail: $chk_fail  unknown: $(count_field 13 unknown)"
    say "batches: total $BATCHES_TOTAL run $BATCHES_RUN failed $BATCHES_FAILED"
    post_fails=$(check_fails "$POSTCHK")
    if ! grep -qF 'post-run health probe answered' "$POSTCHK"; then
        finish PARTIAL 3 "post-run health probe unavailable; single-boot/health proof is incomplete"
    fi
    if [ "$post_fails" -gt 0 ]; then
        finish INVALID 3 "post-run health check failed: the box rebooted or degraded during the reads"
    fi
    if [ "$read_rc" -ne 0 ]; then
        finish PARTIAL 3 "one or more read batches failed; see batches/ and inventory.log"
    fi
    finish COMPLETE 0 "all allowlisted reads completed on one boot; compare expected values with the spec"
}

main "$@"
