#!/bin/sh
# rsh.sh - run a command on the bench box with the project key.
set -eu

ROOT=$(cd "$(dirname "$0")/.." && pwd)
KEY="${ROUTER_SSH_KEY:-$ROOT/.omo-secrets/router_ed25519}"
HOST="${ROUTER_HOST:-root@192.168.10.1}"

[ -f "$KEY" ] || { echo "missing SSH key: $KEY" >&2; exit 1; }

exec ssh -i "$KEY" \
    -o BatchMode=yes \
    -o StrictHostKeyChecking=no \
    -o UserKnownHostsFile=/dev/null \
    -o ConnectTimeout="${ROUTER_CONNECT_TIMEOUT:-10}" \
    "$HOST" "$@"
