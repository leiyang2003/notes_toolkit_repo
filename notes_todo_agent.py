#!/usr/bin/env python3
"""Todo watcher for a project (v2, vault-aware)."""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

from notes_app import parse_checklist_items, process_potential_todos, project_paths


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Watch project notes and display open todos.")
    parser.add_argument("--notes", default="", help="Optional explicit NOTES.md path.")
    parser.add_argument("--project", default="", help="Project name. Default: current folder name.")
    parser.add_argument("--interval", type=float, default=1.0, help="Refresh polling interval.")
    parser.add_argument("--process-interval", type=int, default=120, help="Periodic processor interval in seconds.")
    parser.add_argument("--once", action="store_true", help="Render once and exit.")
    parser.add_argument("--no-clear", action="store_true", help="Do not clear terminal between refreshes.")
    parser.add_argument("--include-placeholders", action="store_true")
    parser.add_argument("--output-file", default="", help="Optional snapshot file path.")
    return parser.parse_args()


def infer_project_from_notes(notes_path: Path) -> str:
    resolved = notes_path.expanduser().resolve()
    if resolved.name == "NOTES.md" and resolved.parent.name == "active":
        return resolved.parent.parent.name
    return ""


def render(notes_path: Path, todos: list[dict[str, Any]], *, clear_screen: bool) -> None:
    if clear_screen:
        sys.stdout.write("\033[2J\033[H")
    now = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    print(f"Todo Agent | {now}")
    print(f"Watching: {notes_path}")
    print(f"Open to-dos: {len(todos)}")
    print("-" * 72)
    if not todos:
        print("No unchecked to-dos found.")
    else:
        for idx, item in enumerate(todos, start=1):
            print(f"{idx}. {item['text']}")
            print(f"   section: {item['section']}")
            print(f"   line: {item['line_no']}")
    print("-" * 72)
    print("Press Ctrl+C to stop.")
    sys.stdout.flush()


def write_snapshot(path: Path, notes_path: Path, todos: list[dict[str, Any]]) -> None:
    now = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    lines = [
        "# Live To-do Snapshot",
        "",
        f"- Generated: {now}",
        f"- Source: {notes_path}",
        f"- Open to-dos: {len(todos)}",
        "",
    ]
    if not todos:
        lines.append("- No unchecked to-dos found.")
    else:
        for idx, item in enumerate(todos, start=1):
            lines.append(f"{idx}. {item['text']}")
            lines.append(f"   - section: `{item['section']}`")
            lines.append(f"   - line: `{item['line_no']}`")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def signature(path: Path) -> tuple[int, int]:
    stat = path.stat()
    return stat.st_mtime_ns, stat.st_size


def main() -> int:
    args = parse_args()

    project = (args.project or "").strip()
    notes_path: Path
    if args.notes:
        notes_path = Path(args.notes).expanduser().resolve()
        inferred = infer_project_from_notes(notes_path)
        if inferred and not project:
            project = inferred
    else:
        notes_path = project_paths(project or None).notes_path

    if not notes_path.exists():
        print(f"Error: notes file not found: {notes_path}", file=sys.stderr)
        return 1

    output_path = Path(args.output_file).expanduser().resolve() if args.output_file else None

    process_project = project_paths(project or None)
    last_process_ts = 0.0

    def refresh() -> None:
        items = parse_checklist_items(notes_path, include_placeholders=args.include_placeholders)
        todos = [item for item in items if not item["completed"]]
        render(notes_path, todos, clear_screen=not args.no_clear)
        if output_path:
            write_snapshot(output_path, notes_path, todos)

    try:
        refresh()
        if args.once:
            return 0

        last = signature(notes_path)
        while True:
            time.sleep(max(0.2, args.interval))

            now = time.time()
            if now - last_process_ts >= max(10, args.process_interval):
                process_potential_todos(process_project, actor="system", log_writes=True)
                last_process_ts = now

            if not notes_path.exists():
                print(f"\nWaiting for notes file to reappear: {notes_path}")
                continue
            sig = signature(notes_path)
            if sig != last:
                last = sig
                refresh()
    except KeyboardInterrupt:
        print("\nTodo Agent stopped.")
        return 0
    except OSError as exc:
        print(f"File access error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
