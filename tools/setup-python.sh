#!/bin/sh
# setup-python.sh - create the repo venv and install the tool dependencies.
set -eu

ROOT=$(cd "$(dirname "$0")/.." && pwd)
VENV="$ROOT/.provision-venv"

if [ ! -x "$VENV/bin/python" ]; then
    python3 -m venv "$VENV"
fi

"$VENV/bin/pip" install -r "$ROOT/tools/requirements.txt"
"$VENV/bin/python" -c "import Crypto, jwt, paho.mqtt, passlib; print('deps ok')"
