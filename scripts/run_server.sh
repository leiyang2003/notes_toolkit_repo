#!/usr/bin/env bash
set -euo pipefail

PORT="${PORT:-8080}"
HOST="${HOST:-0.0.0.0}"
PROCESS_INTERVAL="${PROCESS_INTERVAL:-120}"
CORS_ALLOW_ORIGINS="${CORS_ALLOW_ORIGINS:-}"

# Defaults for containerized deployment.
export NOTES_VAULT_ROOT="${NOTES_VAULT_ROOT:-/data/notes_vault}"
mkdir -p "$NOTES_VAULT_ROOT"

exec python3 /app/notes_todo_dashboard.py \
  --host "$HOST" \
  --port "$PORT" \
  --process-interval "$PROCESS_INTERVAL" \
  --cors-origins "$CORS_ALLOW_ORIGINS"
