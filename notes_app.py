#!/usr/bin/env python3
"""Shared core for Notes Toolkit v2 (vault, actions, state, behavior log)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Shanghai")

DATE_HEADING_RE = re.compile(r"^##\s+(\d{4}-\d{2}-\d{2})\s*$")
SECTION_HEADING_RE = re.compile(r"^###\s+(.*\S)\s*$")
TIMESTAMP_NOTE_RE = re.compile(
    r"^\s*-\s*(?!\[[ xX]\])\[(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}\s+\(Asia/Shanghai\))\]\s*(.+?)\s*$"
)
CHECKBOX_RE = re.compile(r"^\s*-\s*\[( |x|X)\]\s*(.+)\s*$")
LOOSE_TODO_RE = re.compile(r"^\s*-\s*(?:to\s*do|todo)\s*:?\s*(.+?)\s*$", re.IGNORECASE)
POTENTIAL_RE = re.compile(
    r"^\s*-\s*\[(pending|approve|promoted|rejected)\]\s*"
    r"\[(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}\s+\(Asia/Shanghai\))\]\s*(.+?)\s*$",
    re.IGNORECASE,
)
TIMESTAMP_PREFIX_RE = re.compile(r"^\[\d{4}-\d{2}-\d{2}[^\]]*\]\s*")
HIDDEN_NOTE_RE = re.compile(r"^\[hidden\]\s*", re.IGNORECASE)
LONG_TERM_PREFIX_RE = re.compile(r"^\[LT\]\s*", re.IGNORECASE)
ACTION_START_RE = re.compile(
    r"^(i\s+)?(need to|have to|must|should|plan to|remember to|go to|buy|visit|call|schedule)\b",
    re.IGNORECASE,
)
LONG_TERM_HINT_RE = re.compile(
    r"(?:\[LT\]|\blong[- ]?term\b|\bsomeday\b|\bbacklog\b|\broadmap\b|\blater\b|长期|长期性|长期任务|长期待办)",
    re.IGNORECASE,
)
LOG_ROW_RE = re.compile(r"^\|\s*(\d+)\s*\|")

SKIP_SECTIONS = {"Bugs / Follow-ups", "Potential To Do", "Session Handoff"}


@dataclass(frozen=True)
class ProjectPaths:
    name: str
    root: Path
    active_dir: Path
    archive_dir: Path
    notes_path: Path
    done_path: Path
    log_path: Path


@dataclass(frozen=True)
class SectionRange:
    heading_idx: int
    start_idx: int
    end_idx: int


@dataclass(frozen=True)
class ActionResult:
    ok: bool
    message: str
    anchor: str = ""


@dataclass(frozen=True)
class ProcessResult:
    changed: bool
    promoted_count: int
    added_count: int
    anchor: str = ""


def now_ts() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M (Asia/Shanghai)")


def now_iso() -> str:
    return datetime.now(TZ).isoformat()


def today_date() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d")


def vault_root() -> Path:
    raw = (
        Path(__import__("os").environ["NOTES_VAULT_ROOT"]).expanduser()
        if "NOTES_VAULT_ROOT" in __import__("os").environ
        else Path.home() / "Documents" / "notes_vault"
    )
    return raw.resolve()


def default_project_name(cwd: Optional[Path] = None) -> str:
    source = (cwd or Path.cwd()).resolve()
    return source.name


def project_paths(project: Optional[str] = None, *, create: bool = True, cwd: Optional[Path] = None) -> ProjectPaths:
    name = (project or default_project_name(cwd)).strip()
    if not name:
        raise ValueError("Project name is empty.")
    root = vault_root() / name
    active = root / "active"
    archive = root / "archive"
    notes = active / "NOTES.md"
    done = archive / "TODO_DONE.md"
    log = archive / "log.md"
    paths = ProjectPaths(name=name, root=root, active_dir=active, archive_dir=archive, notes_path=notes, done_path=done, log_path=log)
    if create:
        ensure_project(paths)
    return paths


def list_projects(*, create_root: bool = True) -> list[ProjectPaths]:
    root = vault_root()
    if create_root:
        root.mkdir(parents=True, exist_ok=True)
    if not root.exists():
        return []
    projects: list[ProjectPaths] = []
    for child in sorted(p for p in root.iterdir() if p.is_dir()):
        projects.append(project_paths(child.name, create=True))
    return projects


def _default_notes_template() -> str:
    d = today_date()
    return (
        "# Project Notes\n\n"
        "## How To Use\n"
        "- Add a new dated section each day.\n"
        "- Use `add note ...` and `add todo ...` via notes toolkit.\n\n"
        "---\n\n"
        f"## {d}\n\n"
        "### Focus Today\n"
        f"- [{now_ts()}] \n\n"
        "### Changes Made\n"
        f"- [{now_ts()}] Initialized notes for this project.\n\n"
        "### Bugs / Follow-ups\n"
        "\n"
        "### Potential To Do\n"
        "- Status guide: `[pending]` -> `[approve]` to promote, `[rejected]` to ignore.\n\n"
        "### Session Handoff\n"
        f"- Done: [{now_ts()}] \n"
        f"- Blocked: [{now_ts()}] \n"
        f"- Next: [{now_ts()}] \n"
    )


def _default_done_template(project: str) -> str:
    return (
        f"# Completed Todos ({project})\n\n"
        "Append-only archive for completed real todos.\n\n"
    )


def _default_log_template(project: str) -> str:
    return (
        f"# Behavior Log ({project})\n\n"
        "Append-only log of write operations for recovery and audit.\n\n"
        "| id | timestamp | project | actor | action | target | status | before_summary | after_summary | notes_anchor | error |\n"
        "|---|---|---|---|---|---|---|---|---|---|---|\n"
    )


def ensure_project(paths: ProjectPaths) -> None:
    paths.active_dir.mkdir(parents=True, exist_ok=True)
    paths.archive_dir.mkdir(parents=True, exist_ok=True)
    if not paths.notes_path.exists():
        paths.notes_path.write_text(_default_notes_template(), encoding="utf-8")
    if not paths.done_path.exists():
        paths.done_path.write_text(_default_done_template(paths.name), encoding="utf-8")
    if not paths.log_path.exists():
        paths.log_path.write_text(_default_log_template(paths.name), encoding="utf-8")


def snapshot_notes(path: Path, *, reason: str = "") -> Optional[Path]:
    if not path.exists():
        return None
    if path.name != "NOTES.md" or path.parent.name != "active":
        return None

    snapshots_dir = path.parent.parent / "archive" / "snapshots"
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(TZ).strftime("%Y%m%d_%H%M%S")
    safe_reason = re.sub(r"[^a-z0-9_-]+", "_", (reason or "").lower()).strip("_")
    if safe_reason:
        safe_reason = safe_reason[:24]
        snap_name = f"NOTES.{ts}.{safe_reason}.md"
    else:
        snap_name = f"NOTES.{ts}.md"

    snap_path = snapshots_dir / snap_name
    snap_path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")

    # Keep the latest 200 snapshots to avoid unbounded growth.
    keep = 200
    snapshots = sorted(snapshots_dir.glob("NOTES.*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in snapshots[keep:]:
        try:
            old.unlink()
        except OSError:
            continue

    return snap_path


def read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def write_lines(path: Path, lines: list[str], *, snapshot_reason: str = "") -> None:
    snapshot_notes(path, reason=snapshot_reason or "write")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def normalize_text(text: str) -> str:
    cleaned = TIMESTAMP_PREFIX_RE.sub("", text.strip())
    cleaned = LONG_TERM_PREFIX_RE.sub("", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip().lower()
    return cleaned


def summarize_task(text: str, max_len: int = 120) -> str:
    short = TIMESTAMP_PREFIX_RE.sub("", text.strip())
    short = re.sub(r"\s+", " ", short).strip()
    if not short:
        short = "(empty)"
    if len(short) <= max_len:
        return short
    return short[: max_len - 1].rstrip() + "…"


def _preserve_timestamp_prefix(old_content: str, new_content: str) -> str:
    old_match = TIMESTAMP_PREFIX_RE.match((old_content or "").strip())
    if not old_match:
        return new_content
    if TIMESTAMP_PREFIX_RE.match((new_content or "").strip()):
        return new_content
    return f"{old_match.group(0)}{new_content}".strip()


def find_day_block(lines: list[str], date_str: str) -> Optional[tuple[int, int]]:
    day_start: Optional[int] = None
    for idx, line in enumerate(lines):
        match = DATE_HEADING_RE.match(line)
        if match and match.group(1) == date_str:
            day_start = idx
            break
    if day_start is None:
        return None

    day_end = len(lines)
    for idx in range(day_start + 1, len(lines)):
        if DATE_HEADING_RE.match(lines[idx]):
            day_end = idx
            break
    return day_start, day_end


def find_section(lines: list[str], block_start: int, block_end: int, title: str) -> Optional[SectionRange]:
    heading_idx: Optional[int] = None
    for idx in range(block_start + 1, block_end):
        match = SECTION_HEADING_RE.match(lines[idx])
        if match and match.group(1) == title:
            heading_idx = idx
            break
    if heading_idx is None:
        return None

    end_idx = block_end
    for idx in range(heading_idx + 1, block_end):
        if SECTION_HEADING_RE.match(lines[idx]):
            end_idx = idx
            break

    return SectionRange(heading_idx=heading_idx, start_idx=heading_idx + 1, end_idx=end_idx)


def ensure_day_block(lines: list[str], date_str: str) -> tuple[list[str], tuple[int, int]]:
    block = find_day_block(lines, date_str)
    if block:
        return lines, block

    if lines and lines[-1].strip() != "":
        lines.append("")
    lines.extend(
        [
            "---",
            "",
            f"## {date_str}",
            "",
            "### Focus Today",
            f"- [{now_ts()}] ",
            "",
            "### Changes Made",
            f"- [{now_ts()}] ",
            "",
            "### Bugs / Follow-ups",
            "",
            "### Potential To Do",
            "- Status guide: `[pending]` -> `[approve]` to promote, `[rejected]` to ignore.",
            "",
            "### Session Handoff",
            f"- Done: [{now_ts()}] ",
            f"- Blocked: [{now_ts()}] ",
            f"- Next: [{now_ts()}] ",
            "",
        ]
    )
    block = find_day_block(lines, date_str)
    if block is None:
        raise RuntimeError("Failed to create day block.")
    return lines, block


def ensure_section(lines: list[str], day_start: int, day_end: int, title: str, *, helper: Optional[str] = None) -> tuple[list[str], SectionRange]:
    found = find_section(lines, day_start, day_end, title)
    if found:
        return lines, found

    insert_idx = day_end
    handoff = find_section(lines, day_start, day_end, "Session Handoff")
    if handoff:
        insert_idx = handoff.heading_idx

    section_lines = [f"### {title}"]
    if helper:
        section_lines.append(helper)
    section_lines.append("")

    lines = lines[:insert_idx] + section_lines + lines[insert_idx:]
    block = find_day_block(lines, lines[day_start].replace("##", "").strip())
    if block is None:
        raise RuntimeError("Failed to refresh day block.")
    found = find_section(lines, block[0], block[1], title)
    if found is None:
        raise RuntimeError(f"Failed to create section: {title}")
    return lines, found


def insert_line_in_section(lines: list[str], section: SectionRange, line: str) -> tuple[list[str], int]:
    insert_at = section.end_idx
    while insert_at > section.start_idx and lines[insert_at - 1].strip() == "":
        insert_at -= 1
    lines = lines[:insert_at] + [line] + lines[insert_at:]
    return lines, insert_at + 1


def parse_checklist_items(notes_path: Path, include_placeholders: bool = False) -> list[dict[str, Any]]:
    placeholder_re = re.compile(r"YYYY-MM-DD|HH:mm")
    heading_re = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")

    items: list[dict[str, Any]] = []
    heading_stack: list[str] = []
    lines = read_lines(notes_path)
    for line_no, line in enumerate(lines, start=1):
        heading_match = heading_re.match(line)
        if heading_match:
            level = len(heading_match.group(1))
            heading_text = heading_match.group(2).strip()
            while len(heading_stack) >= level:
                heading_stack.pop()
            heading_stack.append(heading_text)
            continue

        match = CHECKBOX_RE.match(line)
        loose_match = LOOSE_TODO_RE.match(line) if not match else None
        if not match and not loose_match:
            continue

        checked_mark = match.group(1) if match else " "
        task_text = (match.group(2) if match else loose_match.group(1)).strip() or "(empty to-do)"
        if not include_placeholders and placeholder_re.search(task_text):
            continue

        section = " > ".join(heading_stack) if heading_stack else "(no section)"
        items.append(
            {
                "line_no": line_no,
                "section": section,
                "text": task_text,
                "summary": summarize_task(task_text),
                "completed": checked_mark.lower() == "x",
            }
        )
    return items


def parse_potential_items(notes_path: Path) -> list[dict[str, Any]]:
    lines = read_lines(notes_path)
    items: list[dict[str, Any]] = []
    current_date = ""
    for idx, line in enumerate(lines, start=1):
        date_match = DATE_HEADING_RE.match(line)
        if date_match:
            current_date = date_match.group(1)
            continue

        match = POTENTIAL_RE.match(line)
        if not match:
            continue

        items.append(
            {
                "id": len(items) + 1,
                "line_no": idx,
                "date": current_date,
                "status": match.group(1).lower(),
                "timestamp": match.group(2),
                "text": match.group(3).strip(),
            }
        )
    return items


def parse_note_entries(notes_path: Path) -> list[dict[str, Any]]:
    lines = read_lines(notes_path)
    items: list[dict[str, Any]] = []
    current_date = ""
    current_section = ""
    in_day_block = False

    for idx, line in enumerate(lines, start=1):
        date_match = DATE_HEADING_RE.match(line)
        if date_match:
            current_date = date_match.group(1)
            in_day_block = True
            current_section = ""
            continue

        if line.startswith("## "):
            in_day_block = False
            current_date = ""
            current_section = ""
            continue

        section_match = SECTION_HEADING_RE.match(line)
        if section_match:
            current_section = section_match.group(1).strip()
            continue

        if not in_day_block:
            continue

        stripped = line.strip()
        if not stripped.startswith("- "):
            continue
        if CHECKBOX_RE.match(line):
            continue
        if POTENTIAL_RE.match(line):
            continue
        if current_section in SKIP_SECTIONS:
            continue

        text = stripped[2:].strip()
        if not text:
            continue
        if HIDDEN_NOTE_RE.match(text):
            continue

        items.append(
            {
                "id": len(items) + 1,
                "line_no": idx,
                "date": current_date,
                "section": current_section,
                "text": text,
            }
        )

    return items


def parse_done_items(done_path: Path) -> list[dict[str, Any]]:
    if not done_path.exists():
        return []
    items: list[dict[str, Any]] = []
    line_re = re.compile(r"^\s*-\s*\[(.+?)\]\s*(.+)$")
    for idx, line in enumerate(read_lines(done_path), start=1):
        m = line_re.match(line)
        if not m:
            continue
        items.append({"line_no": idx, "timestamp": m.group(1), "text": m.group(2), "summary": summarize_task(m.group(2))})
    return items


def is_actionable(text: str) -> bool:
    lowered = text.lower().strip()
    if not lowered or lowered.endswith("?"):
        return False
    if ACTION_START_RE.search(lowered):
        return True
    return "todo" in lowered or "to do" in lowered


def is_long_term_todo(text: str) -> bool:
    raw = TIMESTAMP_PREFIX_RE.sub("", (text or "").strip())
    return bool(LONG_TERM_HINT_RE.search(raw))


def _escape_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").strip()


def _parse_log_rows(log_path: Path) -> list[dict[str, str]]:
    if not log_path.exists():
        return []
    rows: list[dict[str, str]] = []
    for line in read_lines(log_path):
        if not line.strip().startswith("|"):
            continue
        if line.strip().startswith("|---") or line.strip().startswith("| id "):
            continue
        cells = [
            c.strip().replace("\\|", "|")
            for c in re.split(r"(?<!\\)\|", line.strip().strip("|"))
        ]
        if len(cells) < 11:
            continue
        rows.append(
            {
                "id": cells[0],
                "timestamp": cells[1],
                "project": cells[2],
                "actor": cells[3],
                "action": cells[4],
                "target": cells[5],
                "status": cells[6],
                "before_summary": cells[7],
                "after_summary": cells[8],
                "notes_anchor": cells[9],
                "error": cells[10],
            }
        )
    return rows


def append_behavior_log(
    paths: ProjectPaths,
    *,
    actor: str,
    action: str,
    target: str,
    status: str,
    before_summary: str,
    after_summary: str,
    notes_anchor: str,
    error: str = "",
) -> str:
    ensure_project(paths)
    rows = _parse_log_rows(paths.log_path)
    next_id = 1
    if rows:
        try:
            next_id = max(int(item["id"]) for item in rows) + 1
        except ValueError:
            next_id = len(rows) + 1

    row = (
        f"| {next_id:06d} | {now_iso()} | {_escape_cell(paths.name)} | {_escape_cell(actor)} | {_escape_cell(action)} | "
        f"{_escape_cell(target)} | {_escape_cell(status)} | {_escape_cell(before_summary)} | {_escape_cell(after_summary)} | "
        f"{_escape_cell(notes_anchor)} | {_escape_cell(error)} |"
    )

    with paths.log_path.open("a", encoding="utf-8") as fh:
        fh.write(row + "\n")
    return f"{next_id:06d}"


def behavior_log_rows(paths: ProjectPaths) -> list[dict[str, str]]:
    ensure_project(paths)
    return _parse_log_rows(paths.log_path)


def process_potential_todos(
    paths: ProjectPaths,
    *,
    date_override: Optional[str] = None,
    actor: str = "system",
    log_writes: bool = True,
) -> ProcessResult:
    notes_path = paths.notes_path
    original = notes_path.read_text(encoding="utf-8")
    lines = original.splitlines()
    date_str = date_override or today_date()

    lines, (day_start, day_end) = ensure_day_block(lines, date_str)
    lines, bugs = ensure_section(lines, day_start, day_end, "Bugs / Follow-ups")
    lines, potential = ensure_section(
        lines,
        day_start,
        day_end,
        "Potential To Do",
        helper="- Status guide: `[pending]` -> `[approve]` to promote, `[rejected]` to ignore.",
    )

    block = find_day_block(lines, date_str)
    if block is None:
        raise RuntimeError("Day block missing during processing.")
    day_start, day_end = block
    bugs = find_section(lines, day_start, day_end, "Bugs / Follow-ups")
    potential = find_section(lines, day_start, day_end, "Potential To Do")
    if bugs is None or potential is None:
        raise RuntimeError("Required sections missing in process flow.")

    current_potential: list[dict[str, str]] = []
    for idx in range(potential.start_idx, potential.end_idx):
        match = POTENTIAL_RE.match(lines[idx])
        if not match:
            continue
        status = match.group(1).lower()
        text = match.group(3).strip()
        if status == "pending" and not is_actionable(text):
            continue
        current_potential.append(
            {
                "status": status,
                "timestamp": match.group(2),
                "text": text,
            }
        )

    todo_norms: set[str] = set()
    for idx in range(bugs.start_idx, bugs.end_idx):
        match = CHECKBOX_RE.match(lines[idx])
        if match:
            todo_norms.add(normalize_text(match.group(2)))
            continue
        loose_match = LOOSE_TODO_RE.match(lines[idx])
        if loose_match:
            todo_norms.add(normalize_text(loose_match.group(1)))

    promoted_count = 0
    for item in current_potential:
        if item["status"] != "approve":
            continue
        norm = normalize_text(item["text"])
        if norm not in todo_norms:
            todo_line = f"- [ ] [{now_ts()}] {item['text']}"
            lines, _ = insert_line_in_section(lines, bugs, todo_line)
            promoted_count += 1
            todo_norms.add(norm)
            block = find_day_block(lines, date_str)
            if block is None:
                continue
            bugs = find_section(lines, block[0], block[1], "Bugs / Follow-ups") or bugs
        item["status"] = "promoted"

    candidates: list[str] = []
    current_section = ""
    for idx in range(day_start + 1, day_end):
        section_match = SECTION_HEADING_RE.match(lines[idx])
        if section_match:
            current_section = section_match.group(1)
            continue
        if current_section in SKIP_SECTIONS:
            continue
        note_match = TIMESTAMP_NOTE_RE.match(lines[idx])
        if not note_match:
            continue
        text = note_match.group(2).strip()
        if is_actionable(text):
            candidates.append(text)

    existing_norms = {normalize_text(item["text"]) for item in current_potential}
    added_count = 0
    for text in candidates:
        norm = normalize_text(text)
        if norm in existing_norms or norm in todo_norms:
            continue
        current_potential.append({"status": "pending", "timestamp": now_ts(), "text": text})
        existing_norms.add(norm)
        added_count += 1

    # Section indices may shift after todo insertions above, so resolve again
    # before rewriting Potential To Do content.
    block = find_day_block(lines, date_str)
    if block is None:
        raise RuntimeError("Day block missing during potential rewrite.")
    potential = find_section(lines, block[0], block[1], "Potential To Do")
    if potential is None:
        raise RuntimeError("Potential section missing during potential rewrite.")

    potential_lines = [
        "- Status guide: `[pending]` -> `[approve]` to promote, `[rejected]` to ignore.",
        "",
    ]
    for item in current_potential:
        potential_lines.append(f"- [{item['status']}] [{item['timestamp']}] {item['text']}")
    if potential_lines[-1] != "":
        potential_lines.append("")

    lines = lines[: potential.start_idx] + potential_lines + lines[potential.end_idx :]
    updated = "\n".join(lines) + "\n"

    if updated == original:
        return ProcessResult(changed=False, promoted_count=0, added_count=0, anchor="")

    write_lines(paths.notes_path, lines, snapshot_reason="process_potential")
    anchor = f"active/NOTES.md:{(potential.heading_idx + 1) if potential else 1}"
    if log_writes:
        append_behavior_log(
            paths,
            actor=actor,
            action="process_potential",
            target=date_str,
            status="done",
            before_summary=f"pending/promote scan for {date_str}",
            after_summary=f"promoted={promoted_count}, added={added_count}",
            notes_anchor=anchor,
        )
    return ProcessResult(changed=True, promoted_count=promoted_count, added_count=added_count, anchor=anchor)


def add_note(paths: ProjectPaths, text: str, *, actor: str = "user") -> ActionResult:
    if not text.strip():
        message = "Note text is empty."
        append_behavior_log(
            paths,
            actor=actor,
            action="add_note",
            target="Changes Made",
            status="failed",
            before_summary="-",
            after_summary="-",
            notes_anchor="active/NOTES.md",
            error=message,
        )
        return ActionResult(ok=False, message=message)
    lines = read_lines(paths.notes_path)
    date_str = today_date()
    lines, (day_start, day_end) = ensure_day_block(lines, date_str)
    lines, section = ensure_section(lines, day_start, day_end, "Changes Made")
    line = f"- [{now_ts()}] {text.strip()}"
    lines, line_no = insert_line_in_section(lines, section, line)
    write_lines(paths.notes_path, lines, snapshot_reason="add_note")

    anchor = f"active/NOTES.md:{line_no}"
    append_behavior_log(
        paths,
        actor=actor,
        action="add_note",
        target="Changes Made",
        status="done",
        before_summary="-",
        after_summary=summarize_task(line),
        notes_anchor=anchor,
    )
    process_potential_todos(paths, actor="system", log_writes=True)
    return ActionResult(ok=True, message="Note added.", anchor=anchor)


def add_todo(paths: ProjectPaths, text: str, *, actor: str = "user") -> ActionResult:
    if not text.strip():
        message = "Todo text is empty."
        append_behavior_log(
            paths,
            actor=actor,
            action="add_todo",
            target="Bugs / Follow-ups",
            status="failed",
            before_summary="-",
            after_summary="-",
            notes_anchor="active/NOTES.md",
            error=message,
        )
        return ActionResult(ok=False, message=message)
    lines = read_lines(paths.notes_path)
    date_str = today_date()
    lines, (day_start, day_end) = ensure_day_block(lines, date_str)
    lines, section = ensure_section(lines, day_start, day_end, "Bugs / Follow-ups")
    line = f"- [ ] [{now_ts()}] {text.strip()}"
    lines, line_no = insert_line_in_section(lines, section, line)
    write_lines(paths.notes_path, lines, snapshot_reason="add_todo")

    anchor = f"active/NOTES.md:{line_no}"
    append_behavior_log(
        paths,
        actor=actor,
        action="add_todo",
        target="Bugs / Follow-ups",
        status="done",
        before_summary="-",
        after_summary=summarize_task(line),
        notes_anchor=anchor,
    )
    process_potential_todos(paths, actor="system", log_writes=True)
    return ActionResult(ok=True, message="Todo added.", anchor=anchor)


def dismiss_note(paths: ProjectPaths, note_id: int, *, actor: str = "user") -> ActionResult:
    notes = parse_note_entries(paths.notes_path)
    target = next((item for item in notes if item["id"] == note_id), None)
    if target is None:
        message = f"Note #{note_id} not found."
        append_behavior_log(
            paths,
            actor=actor,
            action="dismiss_note",
            target=f"note#{note_id}",
            status="failed",
            before_summary="-",
            after_summary="-",
            notes_anchor="active/NOTES.md",
            error=message,
        )
        return ActionResult(ok=False, message=message)

    lines = read_lines(paths.notes_path)
    idx = target["line_no"] - 1
    if idx < 0 or idx >= len(lines):
        message = "Note line is out of range."
        append_behavior_log(
            paths,
            actor=actor,
            action="dismiss_note",
            target=f"note#{note_id}",
            status="failed",
            before_summary="-",
            after_summary="-",
            notes_anchor="active/NOTES.md",
            error=message,
        )
        return ActionResult(ok=False, message=message)

    old_line = lines[idx]
    if not old_line.lstrip().startswith("- "):
        message = "Target line is not a note bullet."
        append_behavior_log(
            paths,
            actor=actor,
            action="dismiss_note",
            target=f"note#{note_id}",
            status="failed",
            before_summary="-",
            after_summary="-",
            notes_anchor="active/NOTES.md",
            error=message,
        )
        return ActionResult(ok=False, message=message)

    new_line = re.sub(r"^(\s*-\s*)", r"\1[hidden] ", old_line, count=1)
    lines[idx] = new_line
    write_lines(paths.notes_path, lines, snapshot_reason="dismiss_note")

    anchor = f"active/NOTES.md:{target['line_no']}"
    append_behavior_log(
        paths,
        actor=actor,
        action="dismiss_note",
        target=f"note#{note_id}",
        status="done",
        before_summary=summarize_task(old_line),
        after_summary=summarize_task(new_line),
        notes_anchor=anchor,
    )
    return ActionResult(ok=True, message=f"Note #{note_id} dismissed.", anchor=anchor)


def edit_note(paths: ProjectPaths, note_id: int, text: str, *, actor: str = "user") -> ActionResult:
    new_text = (text or "").strip()
    if not new_text:
        message = "Note text is empty."
        append_behavior_log(
            paths,
            actor=actor,
            action="edit_note",
            target=f"note#{note_id}",
            status="failed",
            before_summary="-",
            after_summary="-",
            notes_anchor="active/NOTES.md",
            error=message,
        )
        return ActionResult(ok=False, message=message)

    notes = parse_note_entries(paths.notes_path)
    target = next((item for item in notes if item["id"] == note_id), None)
    if target is None:
        message = f"Note #{note_id} not found."
        append_behavior_log(
            paths,
            actor=actor,
            action="edit_note",
            target=f"note#{note_id}",
            status="failed",
            before_summary="-",
            after_summary="-",
            notes_anchor="active/NOTES.md",
            error=message,
        )
        return ActionResult(ok=False, message=message)

    lines = read_lines(paths.notes_path)
    idx = target["line_no"] - 1
    if idx < 0 or idx >= len(lines):
        message = "Note line is out of range."
        append_behavior_log(
            paths,
            actor=actor,
            action="edit_note",
            target=f"note#{note_id}",
            status="failed",
            before_summary="-",
            after_summary="-",
            notes_anchor="active/NOTES.md",
            error=message,
        )
        return ActionResult(ok=False, message=message)

    old_line = lines[idx]
    if not old_line.lstrip().startswith("- ") or CHECKBOX_RE.match(old_line):
        message = "Target line is not an editable note entry."
        append_behavior_log(
            paths,
            actor=actor,
            action="edit_note",
            target=f"note#{note_id}",
            status="failed",
            before_summary=summarize_task(old_line),
            after_summary="-",
            notes_anchor=f"active/NOTES.md:{target['line_no']}",
            error=message,
        )
        return ActionResult(ok=False, message=message)

    old_content = old_line.strip()[2:].strip()
    content_with_prefix = _preserve_timestamp_prefix(old_content, new_text)
    new_line = re.sub(r"^(\s*-\s*)(.+?)\s*$", lambda m: f"{m.group(1)}{content_with_prefix}", old_line, count=1)
    lines[idx] = new_line
    write_lines(paths.notes_path, lines, snapshot_reason="edit_note")

    anchor = f"active/NOTES.md:{target['line_no']}"
    append_behavior_log(
        paths,
        actor=actor,
        action="edit_note",
        target=f"note#{note_id}",
        status="done",
        before_summary=summarize_task(old_line),
        after_summary=summarize_task(new_line),
        notes_anchor=anchor,
    )
    process_potential_todos(paths, actor="system", log_writes=True)
    return ActionResult(ok=True, message=f"Note #{note_id} updated.", anchor=anchor)


def edit_todo(paths: ProjectPaths, todo_id: int, text: str, *, actor: str = "user") -> ActionResult:
    new_text = (text or "").strip()
    if not new_text:
        message = "Todo text is empty."
        append_behavior_log(
            paths,
            actor=actor,
            action="edit_todo",
            target=f"todo#{todo_id}",
            status="failed",
            before_summary="-",
            after_summary="-",
            notes_anchor="active/NOTES.md",
            error=message,
        )
        return ActionResult(ok=False, message=message)

    todos = list_open_todos(paths)
    target = next((item for item in todos if item["id"] == todo_id), None)
    if target is None:
        message = f"Todo #{todo_id} not found."
        append_behavior_log(
            paths,
            actor=actor,
            action="edit_todo",
            target=f"todo#{todo_id}",
            status="failed",
            before_summary="-",
            after_summary="-",
            notes_anchor="active/NOTES.md",
            error=message,
        )
        return ActionResult(ok=False, message=message)

    lines = read_lines(paths.notes_path)
    idx = target["line_no"] - 1
    if idx < 0 or idx >= len(lines):
        message = "Todo line is out of range."
        append_behavior_log(
            paths,
            actor=actor,
            action="edit_todo",
            target=f"todo#{todo_id}",
            status="failed",
            before_summary="-",
            after_summary="-",
            notes_anchor="active/NOTES.md",
            error=message,
        )
        return ActionResult(ok=False, message=message)

    old_line = lines[idx]
    match = CHECKBOX_RE.match(old_line)
    if not match:
        message = "Todo line format is invalid."
        append_behavior_log(
            paths,
            actor=actor,
            action="edit_todo",
            target=f"todo#{todo_id}",
            status="failed",
            before_summary=summarize_task(old_line),
            after_summary="-",
            notes_anchor=f"active/NOTES.md:{target['line_no']}",
            error=message,
        )
        return ActionResult(ok=False, message=message)

    old_content = (match.group(2) or "").strip()
    content_with_prefix = _preserve_timestamp_prefix(old_content, new_text)
    if is_long_term_todo(old_content) and not LONG_TERM_PREFIX_RE.match(content_with_prefix):
        content_with_prefix = f"[LT] {content_with_prefix}".strip()

    new_line = re.sub(
        r"^(\s*-\s*\[[ xX]\]\s*)(.+?)\s*$",
        lambda m: f"{m.group(1)}{content_with_prefix}",
        old_line,
        count=1,
    )
    lines[idx] = new_line
    write_lines(paths.notes_path, lines, snapshot_reason="edit_todo")

    anchor = f"active/NOTES.md:{target['line_no']}"
    append_behavior_log(
        paths,
        actor=actor,
        action="edit_todo",
        target=f"todo#{todo_id}",
        status="done",
        before_summary=summarize_task(old_line),
        after_summary=summarize_task(new_line),
        notes_anchor=anchor,
    )
    process_potential_todos(paths, actor="system", log_writes=True)
    return ActionResult(ok=True, message=f"Todo #{todo_id} updated.", anchor=anchor)


def list_open_todos(paths: ProjectPaths) -> list[dict[str, Any]]:
    items = parse_checklist_items(paths.notes_path, include_placeholders=False)
    open_items = [item for item in items if not item["completed"]]
    for idx, item in enumerate(open_items, start=1):
        item["id"] = idx
    return open_items


def list_long_term_todos(paths: ProjectPaths) -> list[dict[str, Any]]:
    todos = list_open_todos(paths)
    return [item for item in todos if is_long_term_todo(item["text"])]


def complete_todo(paths: ProjectPaths, todo_id: int, *, actor: str = "user") -> ActionResult:
    todos = list_open_todos(paths)
    target = next((item for item in todos if item["id"] == todo_id), None)
    if target is None:
        message = f"Todo #{todo_id} not found."
        append_behavior_log(
            paths,
            actor=actor,
            action="complete_todo",
            target=f"todo#{todo_id}",
            status="failed",
            before_summary="-",
            after_summary="-",
            notes_anchor="active/NOTES.md",
            error=message,
        )
        return ActionResult(ok=False, message=message)

    lines = read_lines(paths.notes_path)
    idx = target["line_no"] - 1
    if idx < 0 or idx >= len(lines):
        message = "Todo line is out of range."
        append_behavior_log(
            paths,
            actor=actor,
            action="complete_todo",
            target=f"todo#{todo_id}",
            status="failed",
            before_summary="-",
            after_summary="-",
            notes_anchor="active/NOTES.md",
            error=message,
        )
        return ActionResult(ok=False, message=message)
    removed_line = lines.pop(idx)
    write_lines(paths.notes_path, lines, snapshot_reason="complete_todo")

    archive_line = f"- [{now_ts()}] {removed_line}"
    with paths.done_path.open("a", encoding="utf-8") as fh:
        fh.write(archive_line + "\n")

    anchor = f"active/NOTES.md:{target['line_no']},archive/TODO_DONE.md"
    append_behavior_log(
        paths,
        actor=actor,
        action="complete_todo",
        target=f"todo#{todo_id}",
        status="done",
        before_summary=summarize_task(removed_line),
        after_summary=summarize_task(archive_line),
        notes_anchor=anchor,
    )
    process_potential_todos(paths, actor="system", log_writes=True)
    return ActionResult(ok=True, message=f"Todo #{todo_id} completed.", anchor=anchor)


def mark_todo_long_term(paths: ProjectPaths, todo_id: int, *, actor: str = "user") -> ActionResult:
    todos = list_open_todos(paths)
    target = next((item for item in todos if item["id"] == todo_id), None)
    if target is None:
        message = f"Todo #{todo_id} not found."
        append_behavior_log(
            paths,
            actor=actor,
            action="mark_long_term_todo",
            target=f"todo#{todo_id}",
            status="failed",
            before_summary="-",
            after_summary="-",
            notes_anchor="active/NOTES.md",
            error=message,
        )
        return ActionResult(ok=False, message=message)

    lines = read_lines(paths.notes_path)
    idx = target["line_no"] - 1
    if idx < 0 or idx >= len(lines):
        message = "Todo line is out of range."
        append_behavior_log(
            paths,
            actor=actor,
            action="mark_long_term_todo",
            target=f"todo#{todo_id}",
            status="failed",
            before_summary="-",
            after_summary="-",
            notes_anchor="active/NOTES.md",
            error=message,
        )
        return ActionResult(ok=False, message=message)

    old_line = lines[idx]
    match = CHECKBOX_RE.match(old_line)
    if not match:
        message = "Todo line format is invalid."
        append_behavior_log(
            paths,
            actor=actor,
            action="mark_long_term_todo",
            target=f"todo#{todo_id}",
            status="failed",
            before_summary=summarize_task(old_line),
            after_summary="-",
            notes_anchor=f"active/NOTES.md:{target['line_no']}",
            error=message,
        )
        return ActionResult(ok=False, message=message)

    content = (match.group(2) or "").strip()
    anchor = f"active/NOTES.md:{target['line_no']}"
    if is_long_term_todo(content):
        append_behavior_log(
            paths,
            actor=actor,
            action="mark_long_term_todo",
            target=f"todo#{todo_id}",
            status="done",
            before_summary=summarize_task(old_line),
            after_summary=summarize_task(old_line),
            notes_anchor=anchor,
        )
        return ActionResult(ok=True, message=f"Todo #{todo_id} is already long-term.", anchor=anchor)

    new_line = re.sub(
        r"^(\s*-\s*\[[ xX]\]\s*)(.+?)\s*$",
        lambda m: f"{m.group(1)}[LT] {m.group(2).strip()}",
        old_line,
        count=1,
    )
    lines[idx] = new_line
    write_lines(paths.notes_path, lines, snapshot_reason="mark_todo_long_term")

    append_behavior_log(
        paths,
        actor=actor,
        action="mark_long_term_todo",
        target=f"todo#{todo_id}",
        status="done",
        before_summary=summarize_task(old_line),
        after_summary=summarize_task(new_line),
        notes_anchor=anchor,
    )
    process_potential_todos(paths, actor="system", log_writes=True)
    return ActionResult(ok=True, message=f"Todo #{todo_id} marked as long-term.", anchor=anchor)


def mark_todo_short_term(paths: ProjectPaths, todo_id: int, *, actor: str = "user") -> ActionResult:
    todos = list_open_todos(paths)
    target = next((item for item in todos if item["id"] == todo_id), None)
    if target is None:
        message = f"Todo #{todo_id} not found."
        append_behavior_log(
            paths,
            actor=actor,
            action="mark_short_term_todo",
            target=f"todo#{todo_id}",
            status="failed",
            before_summary="-",
            after_summary="-",
            notes_anchor="active/NOTES.md",
            error=message,
        )
        return ActionResult(ok=False, message=message)

    lines = read_lines(paths.notes_path)
    idx = target["line_no"] - 1
    if idx < 0 or idx >= len(lines):
        message = "Todo line is out of range."
        append_behavior_log(
            paths,
            actor=actor,
            action="mark_short_term_todo",
            target=f"todo#{todo_id}",
            status="failed",
            before_summary="-",
            after_summary="-",
            notes_anchor="active/NOTES.md",
            error=message,
        )
        return ActionResult(ok=False, message=message)

    old_line = lines[idx]
    match = CHECKBOX_RE.match(old_line)
    if not match:
        message = "Todo line format is invalid."
        append_behavior_log(
            paths,
            actor=actor,
            action="mark_short_term_todo",
            target=f"todo#{todo_id}",
            status="failed",
            before_summary=summarize_task(old_line),
            after_summary="-",
            notes_anchor=f"active/NOTES.md:{target['line_no']}",
            error=message,
        )
        return ActionResult(ok=False, message=message)

    content = (match.group(2) or "").strip()
    anchor = f"active/NOTES.md:{target['line_no']}"
    short_term_content = re.sub(r"^\[LT\]\s*", "", content, flags=re.IGNORECASE).strip()
    if short_term_content == content:
        append_behavior_log(
            paths,
            actor=actor,
            action="mark_short_term_todo",
            target=f"todo#{todo_id}",
            status="done",
            before_summary=summarize_task(old_line),
            after_summary=summarize_task(old_line),
            notes_anchor=anchor,
        )
        return ActionResult(ok=True, message=f"Todo #{todo_id} has no [LT] marker.", anchor=anchor)

    new_line = re.sub(
        r"^(\s*-\s*\[[ xX]\]\s*)(.+?)\s*$",
        lambda m: f"{m.group(1)}{short_term_content}",
        old_line,
        count=1,
    )
    lines[idx] = new_line
    write_lines(paths.notes_path, lines, snapshot_reason="mark_todo_short_term")

    append_behavior_log(
        paths,
        actor=actor,
        action="mark_short_term_todo",
        target=f"todo#{todo_id}",
        status="done",
        before_summary=summarize_task(old_line),
        after_summary=summarize_task(new_line),
        notes_anchor=anchor,
    )
    process_potential_todos(paths, actor="system", log_writes=True)
    return ActionResult(ok=True, message=f"Todo #{todo_id} moved back to open todos.", anchor=anchor)


def list_pending_potentials(paths: ProjectPaths) -> list[dict[str, Any]]:
    items = parse_potential_items(paths.notes_path)
    pending = [item for item in items if item["status"] == "pending"]
    for idx, item in enumerate(pending, start=1):
        item["id"] = idx
    return pending


def approve_potential(paths: ProjectPaths, potential_id: int, *, actor: str = "user") -> ActionResult:
    pending = list_pending_potentials(paths)
    target = next((item for item in pending if item["id"] == potential_id), None)
    if target is None:
        message = f"Potential #{potential_id} not found."
        append_behavior_log(
            paths,
            actor=actor,
            action="approve_potential",
            target=f"potential#{potential_id}",
            status="failed",
            before_summary="-",
            after_summary="-",
            notes_anchor="active/NOTES.md",
            error=message,
        )
        return ActionResult(ok=False, message=message)

    lines = read_lines(paths.notes_path)
    idx = target["line_no"] - 1
    if idx < 0 or idx >= len(lines):
        message = "Potential line is out of range."
        append_behavior_log(
            paths,
            actor=actor,
            action="approve_potential",
            target=f"potential#{potential_id}",
            status="failed",
            before_summary="-",
            after_summary="-",
            notes_anchor="active/NOTES.md",
            error=message,
        )
        return ActionResult(ok=False, message=message)

    current_line = lines[idx]
    lines[idx] = re.sub(r"\[pending\]", "[approve]", current_line, count=1, flags=re.IGNORECASE)
    write_lines(paths.notes_path, lines, snapshot_reason="approve_potential")

    result = process_potential_todos(paths, date_override=target["date"] or today_date(), actor="system", log_writes=True)

    anchor = f"active/NOTES.md:{target['line_no']}"
    append_behavior_log(
        paths,
        actor=actor,
        action="approve_potential",
        target=f"potential#{potential_id}",
        status="done",
        before_summary=summarize_task(current_line),
        after_summary=f"promoted text={summarize_task(target['text'])}; process_changed={result.changed}",
        notes_anchor=anchor,
    )
    return ActionResult(ok=True, message=f"Potential #{potential_id} approved and promoted.", anchor=anchor)


def reject_potential(paths: ProjectPaths, potential_id: int, *, actor: str = "user") -> ActionResult:
    pending = list_pending_potentials(paths)
    target = next((item for item in pending if item["id"] == potential_id), None)
    if target is None:
        message = f"Potential #{potential_id} not found."
        append_behavior_log(
            paths,
            actor=actor,
            action="reject_potential",
            target=f"potential#{potential_id}",
            status="failed",
            before_summary="-",
            after_summary="-",
            notes_anchor="active/NOTES.md",
            error=message,
        )
        return ActionResult(ok=False, message=message)

    lines = read_lines(paths.notes_path)
    idx = target["line_no"] - 1
    if idx < 0 or idx >= len(lines):
        message = "Potential line is out of range."
        append_behavior_log(
            paths,
            actor=actor,
            action="reject_potential",
            target=f"potential#{potential_id}",
            status="failed",
            before_summary="-",
            after_summary="-",
            notes_anchor="active/NOTES.md",
            error=message,
        )
        return ActionResult(ok=False, message=message)

    old_line = lines[idx]
    lines[idx] = re.sub(r"\[pending\]", "[rejected]", old_line, count=1, flags=re.IGNORECASE)
    write_lines(paths.notes_path, lines, snapshot_reason="reject_potential")

    anchor = f"active/NOTES.md:{target['line_no']}"
    append_behavior_log(
        paths,
        actor=actor,
        action="reject_potential",
        target=f"potential#{potential_id}",
        status="done",
        before_summary=summarize_task(old_line),
        after_summary=summarize_task(lines[idx]),
        notes_anchor=anchor,
    )
    process_potential_todos(paths, actor="system", log_writes=True)
    return ActionResult(ok=True, message=f"Potential #{potential_id} rejected.", anchor=anchor)


def project_state(paths: ProjectPaths) -> dict[str, Any]:
    notes = parse_note_entries(paths.notes_path)
    todos = list_open_todos(paths)
    long_term_todos = [item for item in todos if is_long_term_todo(item["text"])]
    potentials = parse_potential_items(paths.notes_path)
    done = parse_done_items(paths.done_path)
    logs = behavior_log_rows(paths)
    return {
        "project": paths.name,
        "notes_path": str(paths.notes_path),
        "notes_count": len(notes),
        "todo_count": len(todos),
        "long_term_todo_count": len(long_term_todos),
        "potential_pending_count": len([p for p in potentials if p["status"] == "pending"]),
        "notes": notes,
        "todos": todos,
        "long_term_todos": long_term_todos,
        "potentials": potentials,
        "done": done,
        "logs": logs[-20:],
        "updated_at": datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S %Z"),
    }


def all_projects_summary() -> list[dict[str, Any]]:
    projects = list_projects(create_root=True)
    rows: list[dict[str, Any]] = []
    for paths in projects:
        state = project_state(paths)
        last_mtime = max(
            paths.notes_path.stat().st_mtime if paths.notes_path.exists() else 0,
            paths.done_path.stat().st_mtime if paths.done_path.exists() else 0,
            paths.log_path.stat().st_mtime if paths.log_path.exists() else 0,
        )
        rows.append(
            {
                "project": paths.name,
                "todo_count": state["todo_count"],
                "potential_pending_count": state["potential_pending_count"],
                "last_activity": datetime.fromtimestamp(last_mtime, TZ).strftime("%Y-%m-%d %H:%M:%S") if last_mtime else "",
            }
        )
    return rows


def restore_log_entry(paths: ProjectPaths, entry_id: str, *, actor: str = "user") -> ActionResult:
    entries = behavior_log_rows(paths)
    target = next((item for item in entries if item["id"] == str(entry_id).zfill(6)), None)
    if target is None:
        message = f"Log entry {entry_id} not found."
        append_behavior_log(
            paths,
            actor=actor,
            action="restore",
            target=f"entry:{str(entry_id).zfill(6)}",
            status="failed",
            before_summary="-",
            after_summary="-",
            notes_anchor="archive/log.md",
            error=message,
        )
        return ActionResult(ok=False, message=message)

    action = target["action"]
    if action == "add_note" or action == "add_todo":
        lines = read_lines(paths.notes_path)
        needle = target["after_summary"]
        removed = False
        for idx, line in enumerate(lines):
            if needle and needle in summarize_task(line, max_len=200):
                lines.pop(idx)
                removed = True
                break
        if not removed:
            message = f"Could not locate line for restore of {action}."
            append_behavior_log(
                paths,
                actor=actor,
                action="restore",
                target=f"entry:{target['id']}",
                status="failed",
                before_summary=f"restore {action}",
                after_summary="-",
                notes_anchor="active/NOTES.md",
                error=message,
            )
            return ActionResult(ok=False, message=message)
        write_lines(paths.notes_path, lines, snapshot_reason="restore_add_remove")
        append_behavior_log(
            paths,
            actor=actor,
            action="restore",
            target=f"entry:{target['id']}",
            status="done",
            before_summary=f"restore {action}",
            after_summary="removed added line",
            notes_anchor="active/NOTES.md",
        )
        return ActionResult(ok=True, message=f"Restored entry {target['id']}.")

    if action == "complete_todo":
        # Re-add archived todo into today's Bugs / Follow-ups and remove archive line.
        archive_lines = read_lines(paths.done_path)
        needle = target["after_summary"]
        removed_idx = None
        for idx, line in enumerate(archive_lines):
            if needle and needle in summarize_task(line, max_len=220):
                removed_idx = idx
                break
        if removed_idx is not None:
            archive_lines.pop(removed_idx)
            write_lines(paths.done_path, archive_lines)

        lines = read_lines(paths.notes_path)
        date_str = today_date()
        lines, (day_start, day_end) = ensure_day_block(lines, date_str)
        lines, section = ensure_section(lines, day_start, day_end, "Bugs / Follow-ups")
        todo_text = target["before_summary"]
        restored = f"- [ ] [{now_ts()}] RESTORED {todo_text}"
        lines, line_no = insert_line_in_section(lines, section, restored)
        write_lines(paths.notes_path, lines, snapshot_reason="restore_complete_todo")

        append_behavior_log(
            paths,
            actor=actor,
            action="restore",
            target=f"entry:{target['id']}",
            status="done",
            before_summary=f"restore {action}",
            after_summary=summarize_task(restored),
            notes_anchor=f"active/NOTES.md:{line_no}",
        )
        return ActionResult(ok=True, message=f"Restored entry {target['id']}.")

    if action == "approve_potential":
        lines = read_lines(paths.notes_path)
        text_hint = target["after_summary"]
        # remove one TODO line containing hinted text and revert first promoted potential to pending.
        removed_todo = False
        for idx, line in enumerate(lines):
            if CHECKBOX_RE.match(line) and text_hint and summarize_task(line, max_len=220) in text_hint:
                lines.pop(idx)
                removed_todo = True
                break
        reverted = False
        for idx, line in enumerate(lines):
            if POTENTIAL_RE.match(line) and "[promoted]" in line:
                lines[idx] = line.replace("[promoted]", "[pending]", 1)
                reverted = True
                break
        if not removed_todo and not reverted:
            message = "Could not safely restore approve_potential entry."
            append_behavior_log(
                paths,
                actor=actor,
                action="restore",
                target=f"entry:{target['id']}",
                status="failed",
                before_summary="restore approve_potential",
                after_summary="-",
                notes_anchor="active/NOTES.md",
                error=message,
            )
            return ActionResult(ok=False, message=message)
        write_lines(paths.notes_path, lines, snapshot_reason="restore_approve_potential")
        append_behavior_log(
            paths,
            actor=actor,
            action="restore",
            target=f"entry:{target['id']}",
            status="done",
            before_summary="restore approve_potential",
            after_summary="reverted promoted + removed todo where possible",
            notes_anchor="active/NOTES.md",
        )
        return ActionResult(ok=True, message=f"Restored entry {target['id']} (best-effort).")

    message = f"Restore for action '{action}' is not supported yet."
    append_behavior_log(
        paths,
        actor=actor,
        action="restore",
        target=f"entry:{target['id']}",
        status="failed",
        before_summary=f"restore {action}",
        after_summary="-",
        notes_anchor="archive/log.md",
        error=message,
    )
    return ActionResult(ok=False, message=message)


def parse_natural_command(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        return {"kind": "unknown", "error": "Empty command."}

    patterns = [
        (r"^add\s+note\s+(.+)$", "add_note"),
        (r"^add\s+todo\s+(.+)$", "add_todo"),
        (r"^approve\s+potential\s+#?(\d+)$", "approve_potential"),
        (r"^reject\s+potential\s+#?(\d+)$", "reject_potential"),
        (r"^complete\s+todo\s+#?(\d+)$", "complete_todo"),
        (r"^view\s+home$", "view_home"),
        (r"^view\s+project\s+(.+)$", "view_project"),
    ]

    for pattern, kind in patterns:
        m = re.match(pattern, raw, flags=re.IGNORECASE)
        if not m:
            continue
        value = m.group(1).strip() if m.groups() else ""
        return {"kind": kind, "value": value}

    return {"kind": "unknown", "error": f"Unsupported command: {raw}"}


def format_project_view(state: dict[str, Any]) -> str:
    lines = [
        f"Project: {state['project']}",
        f"Notes: {state['notes_path']}",
        f"Open todos: {state['todo_count']}",
        f"Pending potential: {state['potential_pending_count']}",
        "",
        "Todos:",
    ]
    if not state["todos"]:
        lines.append("- (none)")
    else:
        for item in state["todos"]:
            lines.append(f"- #{item['id']} {item['text']} (line {item['line_no']})")

    lines.extend(["", "Pending Potential:"])
    pendings = [item for item in state["potentials"] if item["status"] == "pending"]
    if not pendings:
        lines.append("- (none)")
    else:
        for idx, item in enumerate(pendings, start=1):
            lines.append(f"- #{idx} {item['text']} [{item['timestamp']}] (line {item['line_no']})")
    return "\n".join(lines)


def format_home_view(rows: list[dict[str, Any]]) -> str:
    lines = ["Projects Home", ""]
    if not rows:
        lines.append("- (no projects found in notes_vault)")
        return "\n".join(lines)
    for row in rows:
        lines.append(
            f"- {row['project']}: todos={row['todo_count']}, pending_potential={row['potential_pending_count']}, last_activity={row['last_activity']}"
        )
    return "\n".join(lines)
