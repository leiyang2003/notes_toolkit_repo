#!/usr/bin/env python3
"""Potential todo processor (v2 wrapper over notes_app)."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

from notes_app import ProcessResult, process_potential_todos, project_paths


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Process potential todos for project notes.")
    parser.add_argument("--project", default="", help="Project name. Default: current folder name.")
    parser.add_argument("--notes", default="", help="Optional NOTES.md path (legacy compatibility).")
    parser.add_argument("--date", default="", help="Override date section (YYYY-MM-DD).")
    parser.add_argument("--watch", action="store_true", help="Run continuously.")
    parser.add_argument("--interval", type=int, default=120, help="Seconds between runs in watch mode.")
    parser.add_argument("--actor", default="system", help="Actor name for behavior logs.")
    return parser.parse_args()


def infer_project_from_notes(notes_path: Path) -> str:
    # Expected layout: .../notes_vault/<project>/active/NOTES.md
    resolved = notes_path.expanduser().resolve()
    if resolved.name != "NOTES.md":
        return ""
    try:
        if resolved.parent.name == "active":
            return resolved.parent.parent.name
    except Exception:
        return ""
    return ""


def run_once(project: str, date_override: str, actor: str) -> ProcessResult:
    paths = project_paths(project or None)
    return process_potential_todos(paths, date_override=(date_override or None), actor=actor, log_writes=True)


def main() -> int:
    args = parse_args()

    project = (args.project or "").strip()
    if args.notes:
        inferred = infer_project_from_notes(Path(args.notes))
        if inferred:
            project = inferred

    def do_run() -> None:
        result = run_once(project, args.date, args.actor)
        print(
            f"process complete: project={project or '(cwd-default)'} "
            f"changed={result.changed} promoted={result.promoted_count} added={result.added_count}"
        )

    if not args.watch:
        do_run()
        return 0

    print(f"Potential processor watch mode every {max(10, args.interval)}s")
    try:
        while True:
            do_run()
            time.sleep(max(10, args.interval))
    except KeyboardInterrupt:
        print("\nPotential processor stopped.")
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
