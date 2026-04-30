from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from packages.contracts.python import ActionRequest

from ..dependencies import get_current_user_required

router = APIRouter()

def _validate_project_name(raw_value: object) -> tuple[bool, str]:
    project_name = str(raw_value or "").strip()
    if not project_name:
        return False, "Project name is required."
    if len(project_name) > 80:
        return False, "Project name must be at most 80 characters."
    if any(ch in project_name for ch in ("/", "\\", "\x00")):
        return False, "Project name contains invalid characters."
    return True, project_name


@router.post("/api/init")
def api_init(payload: dict, request: Request, user=Depends(get_current_user_required)):
    ok, project_name = _validate_project_name(payload.get("project_name", "home"))
    if not ok:
        return JSONResponse({"ok": False, "code": "project_invalid", "message": project_name}, status_code=400)
    service = request.app.state.service
    return service.ensure_first_project(user, project_name)

@router.post("/api/projects")
def api_create_project(payload: dict, request: Request, user=Depends(get_current_user_required)):
    ok, project_name = _validate_project_name(payload.get("project_name", ""))
    if not ok:
        return JSONResponse({"ok": False, "code": "project_invalid", "message": project_name}, status_code=400)

    service = request.app.state.service
    result = service.create_project(user, project_name)
    if not result.get("ok"):
        status = 409 if result.get("code") == "project_exists" else 400
        return JSONResponse(result, status_code=status)
    return result


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
