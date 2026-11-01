#!/usr/bin/env bash
# Start the Rest Brain API in the foreground (extra arguments are passed on, e.g. ./run.sh --port 9000).
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
    echo "Virtual environment missing. Run ./setup.sh first."
    exit 1
fi
exec .venv/bin/python -m brain "$@"
