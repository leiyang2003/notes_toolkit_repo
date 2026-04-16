#!/usr/bin/env bash
set -euo pipefail

TARGET_BIN_DIR="${1:-$HOME/.local/bin}"

for cmd in notes notes-todo-watch notes-todo-dashboard notes-todo-process; do
  if [[ -e "$TARGET_BIN_DIR/$cmd" || -L "$TARGET_BIN_DIR/$cmd" ]]; then
    rm -f "$TARGET_BIN_DIR/$cmd"
    echo "removed: $TARGET_BIN_DIR/$cmd"
  fi
done

echo "Uninstall complete."
