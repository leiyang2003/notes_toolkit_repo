from __future__ import annotations

import json
import os
import threading
import time
import uuid
from datetime import datetime

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .auth import AuthError, GoogleOAuthClient, GoogleVerifier, SessionManager, build_session_secret, parse_origin_list
from .repositories import NotesRepository
from .routers.auth_api import router as auth_router
from .routers.health import router as health_router
from .routers.projects import router as project_router
from .services import NotesService, background_processor


def create_app(*, process_interval: int | None = None) -> FastAPI:
    if process_interval is None:
        process_interval = int(os.environ.get("PROCESS_INTERVAL", "120"))

    app = FastAPI(title="notes-toolkit-backend")

    app.state.SESSION_COOKIE = "notes_session"
    app.state.OAUTH_STATE_COOKIE = "notes_oauth_state"
    app.state.OAUTH_NEXT_COOKIE = "notes_oauth_next"

    app.state.verifier = GoogleVerifier()
    app.state.oauth_client = GoogleOAuthClient()
    app.state.session_manager = SessionManager(build_session_secret())
    app.state.repo = NotesRepository()
    app.state.service = NotesService(app.state.repo)

    frontend_origins = parse_origin_list(os.environ.get("FRONTEND_ORIGIN", ""))
    app.state.frontend_origins = frontend_origins
    app.state.frontend_app_url = os.environ.get("FRONTEND_APP_URL", "").strip()

    cookie_secure = os.environ.get("COOKIE_SECURE", "auto").strip().lower() in {"1", "true", "yes", "on"}
    app.state.secure_cookie = cookie_secure
    app.state.session_same_site = (os.environ.get("COOKIE_SAMESITE", "") or "").strip() or "Lax"

    health_payload = {
        "ok": True,
        "service": "notes-toolkit-backend",
        "auth": {
            "google_oauth_configured": app.state.oauth_client.is_configured(),
            "session_cookie": app.state.SESSION_COOKIE,
        },
    }
    if app.state.frontend_app_url:
        health_payload["frontend_app_url"] = app.state.frontend_app_url
    app.state.health_payload = health_payload

    allow_origins = sorted(frontend_origins) if frontend_origins else ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_logging_middleware(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except AuthError as exc:
            response = JSONResponse({"ok": False, "code": exc.code, "message": str(exc)}, status_code=401)
        except Exception as exc:
            response = JSONResponse({"ok": False, "code": "internal_error", "message": str(exc)}, status_code=500)

        latency_ms = int((time.perf_counter() - start) * 1000)
        response.headers["x-request-id"] = request_id
        log_payload = {
            "ts": datetime.utcnow().isoformat() + "Z",
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "latency_ms": latency_ms,
            "user_scope": request.cookies.get(app.state.SESSION_COOKIE, "")[:12] or "anon",
        }
        print(json.dumps(log_payload, ensure_ascii=False))
        return response

    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(project_router)

    stop_flag = threading.Event()
    app.state.stop_flag = stop_flag

    @app.on_event("startup")
    async def on_startup():
        worker = threading.Thread(target=background_processor, args=(stop_flag, process_interval), daemon=True)
        app.state.worker = worker
        worker.start()

    @app.on_event("shutdown")
    async def on_shutdown():
        stop_flag.set()

    return app


app = create_app()
