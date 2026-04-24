from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from packages.contracts.python import ActionRequest

from ..dependencies import get_current_user_required

router = APIRouter()


@router.post("/api/init")
def api_init(payload: dict, request: Request, user=Depends(get_current_user_required)):
    project_name = str(payload.get("project_name", "home")).strip() or "home"
    service = request.app.state.service
    return service.ensure_first_project(user, project_name)


@router.get("/api/project/{project_name}/state")
def api_project_state(project_name: str, request: Request, user=Depends(get_current_user_required)):
    if not project_name.strip():
        return JSONResponse({"ok": False, "code": "project_required", "message": "Project name is required."}, status_code=400)

    try:
        return request.app.state.repo.user_project_state(user.user_id, project_name)
    except Exception as exc:
        return JSONResponse({"ok": False, "code": "state_failed", "message": str(exc)}, status_code=500)


@router.post("/api/project/{project_name}/actions")
def api_project_actions(project_name: str, body: ActionRequest, request: Request, user=Depends(get_current_user_required)):
    if not project_name.strip():
        return JSONResponse({"ok": False, "code": "project_required", "message": "Project name is required."}, status_code=400)

    service = request.app.state.service
    result = service.run_action(
        user,
        project_name,
        body.action,
        (body.actor or "web").strip() or "web",
        item_id=body.id,
        text=body.text,
        instruction=body.instruction,
    )

    if not result.ok:
        status = 400 if result.code in {"unsupported_action", "action_failed", "note_not_found", "todo_not_found", "ai_suggest_failed"} else 500
        return JSONResponse({"ok": False, "code": result.code or "action_failed", "message": result.message}, status_code=status)

    return result.payload or {"ok": True, "message": result.message}
