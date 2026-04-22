#!/usr/bin/env bash
set -euo pipefail

export PYENV_VERSION="${PYENV_VERSION:-system}"

notes_toolkit_root() {
  local source="${BASH_SOURCE[0]}"
  while [[ -L "$source" ]]; do
    local dir
    dir="$(cd -P "$(dirname "$source")" && pwd)"
    source="$(readlink "$source")"
    [[ "$source" != /* ]] && source="$dir/$source"
  done
  local script_dir
  script_dir="$(cd -P "$(dirname "$source")" && pwd)"
  (cd "$script_dir/.." && pwd)
}
