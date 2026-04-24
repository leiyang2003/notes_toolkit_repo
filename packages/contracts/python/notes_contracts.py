from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class ActionType(str, Enum):
    ADD_NOTE = "add_note"
    ADD_TODO = "add_todo"
    APPROVE_POTENTIAL = "approve_potential"
    REJECT_POTENTIAL = "reject_potential"
    COMPLETE_TODO = "complete_todo"
    MARK_LONG_TERM_TODO = "mark_long_term_todo"
    MARK_SHORT_TERM_TODO = "mark_short_term_todo"
    DISMISS_NOTE = "dismiss_note"
    EDIT_NOTE = "edit_note"
    EDIT_TODO = "edit_todo"
    AI_SUGGEST_EDIT_NOTE = "ai_suggest_edit_note"
    AI_SUGGEST_EDIT_TODO = "ai_suggest_edit_todo"


class ActionRequest(BaseModel):
    action: ActionType
    actor: str = "web"
    id: int | None = None
    text: str | None = None
    instruction: str | None = None


class ActionSuccessResponse(BaseModel):
    ok: Literal[True] = True
    message: str
    anchor: str = ""
    state: dict = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    ok: Literal[False] = False
    code: str
    message: str
