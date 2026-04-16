#!/usr/bin/env python3
"""Backward-compatible entrypoint for notes toolkit todo watcher."""

from __future__ import annotations

import runpy
from pathlib import Path

TARGET = Path(__file__).resolve().parent.parent / "notes_todo_agent.py"
runpy.run_path(str(TARGET), run_name="__main__")
