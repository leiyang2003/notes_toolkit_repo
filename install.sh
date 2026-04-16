#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="$SCRIPT_DIR/bin"
TARGET_BIN_DIR="${1:-$HOME/.local/bin}"

mkdir -p "$TARGET_BIN_DIR"

for cmd in notes notes-todo-watch notes-todo-dashboard notes-todo-process; do
  ln -snf "$BIN_DIR/$cmd" "$TARGET_BIN_DIR/$cmd"
  echo "linked: $TARGET_BIN_DIR/$cmd -> $BIN_DIR/$cmd"
done

if [[ ":$PATH:" != *":$TARGET_BIN_DIR:"* ]]; then
  echo
  echo "Add this to your shell profile (~/.zshrc or ~/.bashrc):"
  echo "export PATH=\"$TARGET_BIN_DIR:\$PATH\""
fi

echo
echo "Install complete."
