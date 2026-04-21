#!/usr/bin/env bash
set -euo pipefail

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-${FRONTEND_PORT:-5500}}"
cd /app/frontend 2>/dev/null || cd frontend
exec HOST="$HOST" PORT="$PORT" python3 app.py
