from __future__ import annotations

import re
from datetime import datetime

from notes_app import all_projects_summary, list_open_todos, parse_note_entries, project_paths, project_state


def safe_segment(value: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9._-]+", "_", value.strip())
    return clean.strip("._-") or "anon"


def scoped_project_name(user_id: str, project_name: str) -> str:
    return f"u_{safe_segment(user_id)}__{project_name.strip()}"


def unscoped_project_name(user_id: str, scoped: str) -> str | None:
    prefix = f"u_{safe_segment(user_id)}__"
    if not scoped.startswith(prefix):
        return None
    return scoped[len(prefix) :]


class NotesRepository:
    def user_projects_summary(self, user_id: str) -> list[dict]:
        prefix = f"u_{safe_segment(user_id)}__"
        rows: list[dict] = []
        for item in all_projects_summary():
            scoped = str(item.get("project", ""))
            if not scoped.startswith(prefix):
                continue
            name = unscoped_project_name(user_id, scoped)
            if not name:
                continue
            row = dict(item)
            row["project"] = name
            rows.append(row)
        return rows

    def user_project_state(self, user_id: str, project_name: str) -> dict:
        scoped = scoped_project_name(user_id, project_name)
        state = project_state(project_paths(scoped))
        state["project"] = project_name
        state["user_id"] = user_id
        return state

    def scoped_paths(self, user_id: str, project_name: str):
        return project_paths(scoped_project_name(user_id, project_name))

    def now_string(self) -> str:
        return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")

    def find_note_by_id(self, user_id: str, project_name: str, note_id: int) -> dict | None:
        paths = self.scoped_paths(user_id, project_name)
        notes = parse_note_entries(paths.notes_path)
        return next((item for item in notes if int(item["id"]) == note_id), None)

    def find_todo_by_id(self, user_id: str, project_name: str, todo_id: int) -> dict | None:
        paths = self.scoped_paths(user_id, project_name)
        todos = list_open_todos(paths)
        return next((item for item in todos if int(item["id"]) == todo_id), None)
