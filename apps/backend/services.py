from __future__ import annotations

from dataclasses import dataclass

from notes_app import (
    add_note,
    add_todo,
    approve_potential,
    complete_todo,
    dismiss_note,
    edit_note,
    edit_todo,
    mark_todo_long_term,
    mark_todo_short_term,
    process_potential_todos,
    list_projects,
    project_paths,
    reject_potential,
    suggest_text_edit_with_ai,
)
from packages.contracts.python import ActionType

from .auth import AuthUser
from .repositories import NotesRepository, scoped_project_name


@dataclass(frozen=True)
class ServiceResult:
    ok: bool
    message: str
    code: str = ""
    payload: dict | None = None


class NotesService:
    def __init__(self, repo: NotesRepository) -> None:
        self.repo = repo

    def ensure_first_project(self, user: AuthUser, project_name: str) -> dict:
        existing = self.repo.user_projects_summary(user.user_id)
        initialized = len(existing) == 0
        project_paths(scoped_project_name(user.user_id, project_name), create=True)
        return {
            "ok": True,
            "initialized": initialized,
            "project": project_name,
            "state": self.repo.user_project_state(user.user_id, project_name),
        }

    def create_project(self, user: AuthUser, project_name: str) -> dict:
        existing = self.repo.user_projects_summary(user.user_id)
        if any(str(item.get("project", "")) == project_name for item in existing):
            return {"ok": False, "code": "project_exists", "message": f"Project '{project_name}' already exists."}
        project_paths(scoped_project_name(user.user_id, project_name), create=True)
        return {
            "ok": True,
            "project": project_name,
            "state": self.repo.user_project_state(user.user_id, project_name),
        }

    def run_action(self, user: AuthUser, project_name: str, action: ActionType, actor: str, *, item_id: int | None, text: str | None, instruction: str | None) -> ServiceResult:
        paths = self.repo.scoped_paths(user.user_id, project_name)

        try:
            if action == ActionType.ADD_NOTE:
                result = add_note(paths, str(text or ""), actor=actor)
            elif action == ActionType.ADD_TODO:
                result = add_todo(paths, str(text or ""), actor=actor)
            elif action == ActionType.APPROVE_POTENTIAL:
                result = approve_potential(paths, int(item_id), actor=actor)
            elif action == ActionType.REJECT_POTENTIAL:
                result = reject_potential(paths, int(item_id), actor=actor)
            elif action == ActionType.COMPLETE_TODO:
                result = complete_todo(paths, int(item_id), actor=actor)
            elif action == ActionType.MARK_LONG_TERM_TODO:
                result = mark_todo_long_term(paths, int(item_id), actor=actor)
            elif action == ActionType.MARK_SHORT_TERM_TODO:
                result = mark_todo_short_term(paths, int(item_id), actor=actor)
            elif action == ActionType.DISMISS_NOTE:
                result = dismiss_note(paths, int(item_id), actor=actor)
            elif action == ActionType.EDIT_NOTE:
                result = edit_note(paths, int(item_id), str(text or ""), actor=actor)
            elif action == ActionType.EDIT_TODO:
                result = edit_todo(paths, int(item_id), str(text or ""), actor=actor)
            elif action == ActionType.AI_SUGGEST_EDIT_NOTE:
                target = self.repo.find_note_by_id(user.user_id, project_name, int(item_id))
                if target is None:
                    return ServiceResult(ok=False, message=f"Note #{item_id} not found.", code="note_not_found")
                ok, suggestion = suggest_text_edit_with_ai(target["text"], str(instruction or ""), kind="note")
                if not ok:
                    return ServiceResult(ok=False, message=suggestion, code="ai_suggest_failed")
                return ServiceResult(ok=True, message="ok", payload={
                    "ok": True,
                    "kind": "note",
                    "id": int(item_id),
                    "original_text": target["text"],
                    "edited_text": suggestion,
                })
            elif action == ActionType.AI_SUGGEST_EDIT_TODO:
                target = self.repo.find_todo_by_id(user.user_id, project_name, int(item_id))
                if target is None:
                    return ServiceResult(ok=False, message=f"Todo #{item_id} not found.", code="todo_not_found")
                ok, suggestion = suggest_text_edit_with_ai(target["text"], str(instruction or ""), kind="todo")
                if not ok:
                    return ServiceResult(ok=False, message=suggestion, code="ai_suggest_failed")
                return ServiceResult(ok=True, message="ok", payload={
                    "ok": True,
                    "kind": "todo",
                    "id": int(item_id),
                    "original_text": target["text"],
                    "edited_text": suggestion,
                })
            else:
                return ServiceResult(ok=False, message=f"Unsupported action: {action}", code="unsupported_action")
        except Exception as exc:
            return ServiceResult(ok=False, message=str(exc), code="action_exception")

        if not result.ok:
            return ServiceResult(ok=False, message=result.message, code="action_failed")

        return ServiceResult(
            ok=True,
            message=result.message,
            payload={
                "ok": True,
                "message": result.message,
                "anchor": result.anchor,
                "state": self.repo.user_project_state(user.user_id, project_name),
            },
        )


def background_processor(stop_flag, interval_seconds: int = 120) -> None:
    interval = max(10, int(interval_seconds))
    while not stop_flag.wait(interval):
        for proj in list_projects(create_root=True):
            try:
                process_potential_todos(proj, actor="system", log_writes=True)
            except Exception:
                continue
