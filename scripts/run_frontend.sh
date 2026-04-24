#!/usr/bin/env bash
set -euo pipefail

PORT="${PORT:-${FRONTEND_PORT:-5500}}"
cd /app/frontend 2>/dev/null || cd frontend
if [ ! -d node_modules ]; then
  npm install
fi
exec PORT="$PORT" npm run dev
