from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse

from ..auth import append_query, create_oauth_state, safe_next_url, unquote_cookie
from ..dependencies import get_current_user_optional, get_current_user_required

router = APIRouter()


@router.get("/auth/google/login")
def google_login(request: Request):
    oauth_client = request.app.state.oauth_client
    if not oauth_client.is_configured():
        return JSONResponse(
            {
                "ok": False,
                "message": "Google OAuth is not configured. Set GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, and GOOGLE_REDIRECT_URI.",
                "code": "oauth_not_configured",
            },
            status_code=500,
        )

    state = create_oauth_state()
    next_url = safe_next_url(request.query_params.get("next", "/"), allow_origins=request.app.state.frontend_origins)
    response = RedirectResponse(oauth_client.build_authorize_url(state), status_code=302)
    response.set_cookie(
        key=request.app.state.OAUTH_STATE_COOKIE,
        value=state,
        max_age=600,
        httponly=True,
        samesite="lax",
        secure=request.app.state.secure_cookie,
    )
    response.set_cookie(
        key=request.app.state.OAUTH_NEXT_COOKIE,
        value=quote(next_url, safe=""),
        max_age=600,
        httponly=True,
        samesite="lax",
        secure=request.app.state.secure_cookie,
    )
    return response


@router.get("/auth/google/callback")
def google_callback(request: Request):
    verifier = request.app.state.verifier
    oauth_client = request.app.state.oauth_client
    session_manager = request.app.state.session_manager

    returned_state = (request.query_params.get("state") or "").strip()
    expected_state = request.cookies.get(request.app.state.OAUTH_STATE_COOKIE, "")
    code = (request.query_params.get("code") or "").strip()
    next_url = safe_next_url(
        unquote_cookie(request.cookies.get(request.app.state.OAUTH_NEXT_COOKIE, "")),
        allow_origins=request.app.state.frontend_origins,
    )

    if (request.query_params.get("error") or "").strip():
        return RedirectResponse(append_query(next_url, "auth_error", "oauth_denied"), status_code=302)
    if not returned_state or returned_state != expected_state:
        return RedirectResponse(append_query(next_url, "auth_error", "state_mismatch"), status_code=302)
    if not code:
        return RedirectResponse(append_query(next_url, "auth_error", "missing_code"), status_code=302)

    try:
        id_token = oauth_client.exchange_code_for_id_token(code)
        user = verifier.verify(id_token)
    except Exception:
        return RedirectResponse(append_query(next_url, "auth_error", "token_exchange_failed"), status_code=302)

    response = RedirectResponse(next_url, status_code=302)
    response.set_cookie(
        key=request.app.state.SESSION_COOKIE,
        value=session_manager.issue(user),
        max_age=session_manager.max_age_seconds,
        httponly=True,
        samesite=request.app.state.session_same_site,
        secure=request.app.state.secure_cookie,
    )
    response.delete_cookie(request.app.state.OAUTH_STATE_COOKIE)
    response.delete_cookie(request.app.state.OAUTH_NEXT_COOKIE)
    return response


@router.post("/auth/logout")
def logout(request: Request):
    response = JSONResponse({"ok": True})
    response.delete_cookie(request.app.state.SESSION_COOKIE)
    response.delete_cookie(request.app.state.OAUTH_STATE_COOKIE)
    response.delete_cookie(request.app.state.OAUTH_NEXT_COOKIE)
    return response


@router.get("/api/session")
def api_session(user=Depends(get_current_user_optional)):
    if user is None:
        return {"ok": True, "logged_in": False, "email": ""}
    return {"ok": True, "logged_in": True, "email": user.email, "user_id": user.user_id}


@router.get("/api/projects")
def api_projects(request: Request, user=Depends(get_current_user_required)):
    repo = request.app.state.repo
    return {
        "ok": True,
        "projects": repo.user_projects_summary(user.user_id),
        "refreshed_at": repo.now_string(),
    }
