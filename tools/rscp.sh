#!/bin/sh
# rscp.sh - copy to or from the bench box with the project key.
set -eu

ROOT=$(cd "$(dirname "$0")/.." && pwd)
KEY="${ROUTER_SSH_KEY:-$ROOT/.omo-secrets/router_ed25519}"

[ -f "$KEY" ] || { echo "missing SSH key: $KEY" >&2; exit 1; }

exec scp -O -i "$KEY" \
    -o BatchMode=yes \
    -o StrictHostKeyChecking=no \
    -o UserKnownHostsFile=/dev/null \
    "$@"
