#!/usr/bin/env bash
# Start API using the venv Python; supports Windows- and POSIX-style venvs.
set -euo pipefail

if [[ -x ".venv/Scripts/python" ]]; then
  PY="./.venv/Scripts/python"   # Windows venv
elif [[ -x ".venv/bin/python" ]]; then
  PY="./.venv/bin/python"       # POSIX venv (WSL/macOS/Linux)
else
  echo "[ERROR] venv python not found. Create venv first." >&2
  exit 1
fi

exec "$PY" -m uvicorn app.main:app --reload --port 8000