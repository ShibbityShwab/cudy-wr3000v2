#!/usr/bin/env bash
# fire.sh - one entry point for the kernel fire lane.
#
# usage:
#   tools/fire.sh list
#   tools/fire.sh latest
#   tools/fire.sh guard
#   tools/fire.sh run <phase> --detach [--dry-run]
#   tools/fire.sh status <phase>
#   tools/fire.sh verdict
#   tools/fire.sh broker [--slice <path>] [--lab] [--dry-run]
#
# The per-phase scripts stay in build/linux-kbuild and are gitignored. This
# dispatcher is the stable entry point and the only one that may run detached.

set -uo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
KB="$ROOT/build/linux-kbuild"
KEY="${ROUTER_SSH_KEY:-$ROOT/.omo-secrets/router_ed25519}"
HOST="${ROUTER_HOST:-root@192.168.10.1}"
BDINFO="${BDINFO:-$ROOT/dumps/router-20261108/bdinfo.bin}"

usage() {
    sed -n '3,13p' "$0" | sed 's/^# \{0,1\}//'
}

phase_script() {
    local p=${1#phase}
    p=${p%.sh}
    printf '%s/run-phase%s.sh\n' "$KB" "$p"
}

cmd_list() {
    find "$KB" -maxdepth 1 -name 'run-phase*.sh' -printf '%f\n' 2>/dev/null \
        | sed 's/^run-phase//; s/\.sh$//' | sort -V
}

cmd_latest() {
    ls -t "$KB"/luofu-slice-phase*.bin 2>/dev/null | head -1
}

cmd_guard() {
    "$ROOT/tools/check-init-shadow.sh"
}

cmd_run() {
    local phase="" detach=0 dry=0
    while [ $# -gt 0 ]; do
        case "$1" in
            --detach) detach=1 ;;
            --dry-run) dry=1 ;;
            -*) echo "unknown option: $1" >&2; exit 2 ;;
            *) phase=$1 ;;
        esac
        shift
    done
    [ -n "$phase" ] || { echo "usage: fire.sh run <phase> --detach [--dry-run]" >&2; exit 2; }
    local script
    script=$(phase_script "$phase")
    [ -f "$script" ] || { echo "no such phase script: $script" >&2; exit 2; }
    local tag=${phase#phase}
    local log="$KB/fire-phase${tag}.out.log"
    local pidfile="$KB/fire-phase${tag}.pid"
    if [ "$dry" -eq 1 ]; then
        echo "would run: bash $script"
        echo "log: $log"
        return 0
    fi
    cmd_guard || exit 1
    if [ "$detach" -ne 1 ]; then
        echo "refusing to run in the foreground; pass --detach" >&2
        exit 2
    fi
    : > "$log"
    setsid bash "$script" >>"$log" 2>&1 </dev/null &
    echo $! > "$pidfile"
    echo "detached pid $(cat "$pidfile")"
    echo "wrapper log $log"
    echo "script log  $KB/fire-phase${tag}.log"
}

cmd_status() {
    local phase=${1:-}
    [ -n "$phase" ] || { echo "usage: fire.sh status <phase>" >&2; exit 2; }
    local tag=${phase#phase}
    local pidfile="$KB/fire-phase${tag}.pid"
    local log="$KB/fire-phase${tag}.out.log"
    if [ -f "$pidfile" ] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
        echo "running: pid $(cat "$pidfile")"
    else
        echo "not running"
    fi
    for f in "$KB/fire-phase${tag}.log" "$log"; do
        [ -f "$f" ] || continue
        echo "--- $f"
        tail -n 40 "$f"
    done
}

cmd_verdict() {
    [ -f "$KEY" ] || { echo "missing SSH key: $KEY" >&2; exit 1; }
    ssh -i "$KEY" -o BatchMode=yes -o StrictHostKeyChecking=no \
        -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10 "$HOST" \
        'for c in C04 C18 C1C C70 C88 C90 C94 C98 C9C; do printf "%s=" $c; devmem 0x10100$c 32; done'
}

cmd_broker() {
    local slice="" stage=fire dry=0
    while [ $# -gt 0 ]; do
        case "$1" in
            --slice) slice=$2; shift ;;
            --lab) stage=lab ;;
            --dry-run) dry=1 ;;
            *) echo "unknown option: $1" >&2; exit 2 ;;
        esac
        shift
    done
    if [ -n "$slice" ]; then
        export SLICE="$slice"
    fi
    local args=(--bdinfo "$BDINFO" --stage "$stage")
    if [ "$dry" -eq 1 ]; then
        local chosen=${SLICE:-$(cmd_latest)}
        echo "SLICE=${chosen:-<none>} $ROOT/tools/box-provision.sh ${args[*]}"
        return 0
    fi
    "$ROOT/tools/box-provision.sh" "${args[@]}"
}

cmd=${1:-}
[ $# -gt 0 ] && shift
case "$cmd" in
    list) cmd_list ;;
    latest) cmd_latest ;;
    guard) cmd_guard ;;
    run) cmd_run "$@" ;;
    status) cmd_status "$@" ;;
    verdict) cmd_verdict ;;
    broker) cmd_broker "$@" ;;
    *) usage; exit 2 ;;
esac
