#!/usr/bin/env python3
"""Unified CLI for Notes Toolkit v2."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

from notes_app import (
    add_note,
    add_todo,
    all_projects_summary,
    approve_potential,
    behavior_log_rows,
    complete_todo,
    format_home_view,
    format_project_view,
    parse_natural_command,
    process_potential_todos,
    project_paths,
    project_state,
    reject_potential,
    restore_log_entry,
)


def _print_json(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _project(args: argparse.Namespace) -> str | None:
    value = getattr(args, "project", None)
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Notes Toolkit v2 command interface")
    parser.add_argument("--project", help="Project name. Default: current folder name.")
    parser.add_argument("--json", action="store_true", help="Print JSON output when applicable.")
    parser.add_argument("--actor", default="user", help="Actor name for behavior logs.")

    sub = parser.add_subparsers(dest="cmd")

    view = sub.add_parser("view", help="View home or project state")
    view.add_argument("target", choices=["home", "project"], nargs="?", default="project")
    view.add_argument("project_name", nargs="?", default="")

    note = sub.add_parser("note", help="Note operations")
    note_sub = note.add_subparsers(dest="note_cmd", required=True)
    note_add = note_sub.add_parser("add", help="Add note")
    note_add.add_argument("--text", required=True)

    todo = sub.add_parser("todo", help="Todo operations")
    todo_sub = todo.add_subparsers(dest="todo_cmd", required=True)
    todo_add = todo_sub.add_parser("add", help="Add todo")
    todo_add.add_argument("--text", required=True)
    todo_list = todo_sub.add_parser("list", help="List open todos")
    todo_complete = todo_sub.add_parser("complete", help="Complete todo by id")
    todo_complete.add_argument("--id", type=int, required=True)

    potential = sub.add_parser("potential", help="Potential todo operations")
    potential_sub = potential.add_subparsers(dest="potential_cmd", required=True)
    potential_list = potential_sub.add_parser("list", help="List potential items")
    potential_list.add_argument("--status", choices=["pending", "approve", "promoted", "rejected"], default="")
    potential_approve = potential_sub.add_parser("approve", help="Approve pending potential by id")
    potential_approve.add_argument("--id", type=int, required=True)
    potential_reject = potential_sub.add_parser("reject", help="Reject pending potential by id")
    potential_reject.add_argument("--id", type=int, required=True)

    log = sub.add_parser("log", help="Behavior log operations")
    log_sub = log.add_subparsers(dest="log_cmd", required=True)
    log_show = log_sub.add_parser("show", help="Show behavior log")
    log_show.add_argument("--limit", type=int, default=30)
    log_restore = log_sub.add_parser("restore", help="Restore change by log entry id")
    log_restore.add_argument("--id", required=True)

    process = sub.add_parser("process", help="Run potential-todo processor")
    process.add_argument("--date", default="", help="Optional YYYY-MM-DD")

    return parser


def run_natural(raw_args: list[str], *, default_project: str | None, json_mode: bool, actor: str) -> int:
    text = " ".join(raw_args).strip()
    parsed = parse_natural_command(text)
    kind = parsed.get("kind")

    if kind == "unknown":
        print(parsed.get("error", "Unsupported command."), file=sys.stderr)
        return 2

    if kind == "view_home":
        rows = all_projects_summary()
        if json_mode:
            _print_json(rows)
        else:
            print(format_home_view(rows))
        return 0

    if kind == "view_project":
        paths = project_paths(parsed.get("value") or default_project)
        state = project_state(paths)
        if json_mode:
            _print_json(state)
        else:
            print(format_project_view(state))
        return 0

    paths = project_paths(default_project)

    if kind == "add_note":
        result = add_note(paths, parsed.get("value", ""), actor=actor)
    elif kind == "add_todo":
        result = add_todo(paths, parsed.get("value", ""), actor=actor)
    elif kind == "approve_potential":
        result = approve_potential(paths, int(parsed.get("value", "0")), actor=actor)
    elif kind == "reject_potential":
        result = reject_potential(paths, int(parsed.get("value", "0")), actor=actor)
    elif kind == "complete_todo":
        result = complete_todo(paths, int(parsed.get("value", "0")), actor=actor)
    else:
        print(f"Unsupported command: {text}", file=sys.stderr)
        return 2

    if json_mode:
        _print_json(result.__dict__)
    else:
        print(result.message)
    return 0 if result.ok else 1


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    # Natural-language mode when first token isn't a known subcommand/flag.
    known = {"view", "note", "todo", "potential", "log", "process"}
    if argv and not argv[0].startswith("-") and argv[0] not in known:
        # Extract simple global flags from prefix.
        json_mode = "--json" in argv
        actor = "user"
        if "--actor" in argv:
            idx = argv.index("--actor")
            if idx + 1 < len(argv):
                actor = argv[idx + 1]
                del argv[idx : idx + 2]
        project = None
        if "--project" in argv:
            idx = argv.index("--project")
            if idx + 1 < len(argv):
                project = argv[idx + 1]
                del argv[idx : idx + 2]
        argv = [item for item in argv if item != "--json"]
        return run_natural(argv, default_project=project, json_mode=json_mode, actor=actor)

    parser = build_parser()
    args = parser.parse_args(argv)

    project = _project(args)
    actor = str(args.actor).strip() or "user"

    if args.cmd in {None, "view"}:
        target = getattr(args, "target", "project")
        if target == "home":
            rows = all_projects_summary()
            if args.json:
                _print_json(rows)
            else:
                print(format_home_view(rows))
            return 0

        selected = (getattr(args, "project_name", "") or "").strip() or project
        paths = project_paths(selected)
        state = project_state(paths)
        if args.json:
            _print_json(state)
        else:
            print(format_project_view(state))
        return 0

    paths = project_paths(project)

    if args.cmd == "note" and args.note_cmd == "add":
        result = add_note(paths, args.text, actor=actor)
        if args.json:
            _print_json(result.__dict__)
        else:
            print(result.message)
        return 0 if result.ok else 1

    if args.cmd == "todo":
        if args.todo_cmd == "add":
            result = add_todo(paths, args.text, actor=actor)
            if args.json:
                _print_json(result.__dict__)
            else:
                print(result.message)
            return 0 if result.ok else 1
        if args.todo_cmd == "list":
            todos = project_state(paths)["todos"]
            if args.json:
                _print_json(todos)
            else:
                if not todos:
                    print("No open todos.")
                for item in todos:
                    print(f"#{item['id']} {item['text']} (line {item['line_no']})")
            return 0
        if args.todo_cmd == "complete":
            result = complete_todo(paths, args.id, actor=actor)
            if args.json:
                _print_json(result.__dict__)
            else:
                print(result.message)
            return 0 if result.ok else 1

    if args.cmd == "potential":
        potentials = project_state(paths)["potentials"]
        if args.potential_cmd == "list":
            if args.status:
                potentials = [item for item in potentials if item.get("status") == args.status]
            if args.json:
                _print_json(potentials)
            else:
                if not potentials:
                    print("No potential items.")
                pending_idx = 0
                for item in potentials:
                    display_id = "-"
                    if item["status"] == "pending":
                        pending_idx += 1
                        display_id = str(pending_idx)
                    print(f"#{display_id} [{item['status']}] {item['text']} ({item['timestamp']})")
            return 0
        if args.potential_cmd == "approve":
            result = approve_potential(paths, args.id, actor=actor)
            if args.json:
                _print_json(result.__dict__)
            else:
                print(result.message)
            return 0 if result.ok else 1
        if args.potential_cmd == "reject":
            result = reject_potential(paths, args.id, actor=actor)
            if args.json:
                _print_json(result.__dict__)
            else:
                print(result.message)
            return 0 if result.ok else 1

    if args.cmd == "log":
        if args.log_cmd == "show":
            rows = behavior_log_rows(paths)
            rows = rows[-max(1, args.limit) :]
            if args.json:
                _print_json(rows)
            else:
                if not rows:
                    print("No behavior log entries.")
                for row in rows:
                    print(
                        f"{row['id']} {row['timestamp']} {row['action']} {row['status']} "
                        f"target={row['target']} anchor={row['notes_anchor']}"
                    )
            return 0
        if args.log_cmd == "restore":
            result = restore_log_entry(paths, args.id, actor=actor)
            if args.json:
                _print_json(result.__dict__)
            else:
                print(result.message)
            return 0 if result.ok else 1

    if args.cmd == "process":
        result = process_potential_todos(paths, date_override=(args.date or None), actor=actor, log_writes=True)
        payload = {
            "changed": result.changed,
            "promoted_count": result.promoted_count,
            "added_count": result.added_count,
            "anchor": result.anchor,
        }
        if args.json:
            _print_json(payload)
        else:
            print(f"process complete: changed={result.changed}, promoted={result.promoted_count}, added={result.added_count}")
        return 0

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
