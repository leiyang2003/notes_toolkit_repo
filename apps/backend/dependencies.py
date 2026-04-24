from __future__ import annotations

from fastapi import Depends, Request
from fastapi.responses import JSONResponse

from .auth import AuthError


def _read_user(request: Request):
    auth_header = (request.headers.get("Authorization") or "").strip()
    if auth_header.lower().startswith("bearer "):
        token = auth_header.split(" ", 1)[1].strip()
        return request.app.state.verifier.verify(token)

    session_token = request.cookies.get(request.app.state.SESSION_COOKIE, "")
    if session_token:
        return request.app.state.session_manager.verify(session_token)

    raise AuthError("Please sign in with Google first.", code="not_signed_in")


def get_current_user_optional(request: Request):
    try:
        return _read_user(request)
    except Exception:
        return None


def get_current_user_required(request: Request):
    try:
        return _read_user(request)
    except AuthError as exc:
        # FastAPI dependencies should raise; we transform to HTTP response at middleware level by re-raising.
        raise exc
