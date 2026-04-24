from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse

router = APIRouter()


@router.get("/")
def root(request: Request):
    frontend_app_url = request.app.state.frontend_app_url
    if frontend_app_url:
        raw_query = request.url.query
        location = frontend_app_url.rstrip("/") + "/"
        if raw_query:
            location = f"{location}?{raw_query}"
        return RedirectResponse(location, status_code=302)
    return JSONResponse(request.app.state.health_payload)


@router.get("/health")
def health(request: Request):
    return JSONResponse(request.app.state.health_payload)


@router.get("/project/{path:path}")
def project_path(path: str, request: Request):
    frontend_app_url = request.app.state.frontend_app_url
    if frontend_app_url:
        raw_query = request.url.query
        location = frontend_app_url.rstrip("/") + f"/project/{path}"
        if raw_query:
            location = f"{location}?{raw_query}"
        return RedirectResponse(location, status_code=302)
    return JSONResponse(request.app.state.health_payload)
