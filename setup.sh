#!/usr/bin/env bash
# One-time setup on Linux/macOS: creates .venv and installs the dependencies.
set -e
cd "$(dirname "$0")"
PY=${PYTHON:-python3}
if [ ! -x .venv/bin/python ]; then
    "$PY" -m venv .venv || { echo "Python 3.12+ with venv is required (Ubuntu: sudo apt install python3-venv)"; exit 1; }
fi
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
[ -f .env ] || { cp .env.example .env; echo "Created .env - set BRAIN_USERNAME and BRAIN_PASSWORD in it."; }
if ! command -v agy >/dev/null 2>&1 && [ ! -x "$HOME/.local/bin/agy" ]; then
    echo
    echo "NOTE: AGY CLI not found. Install it, then run 'agy' once and sign in."
    echo "      If it is not on PATH, set BRAIN_AGY in .env."
fi
echo
echo "Done. Start with:  pm2 start ecosystem.config.js   (or ./run.sh)"
