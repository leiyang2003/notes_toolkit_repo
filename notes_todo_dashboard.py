#!/usr/bin/env python3
"""Notes Toolkit HTTP API server (file-backed, Google Sign-In auth)."""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen

THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

from notes_app import (
    add_note,
    add_todo,
    all_projects_summary,
    approve_potential,
    complete_todo,
    dismiss_note,
    mark_todo_long_term,
    process_potential_todos,
    project_paths,
    project_state,
    reject_potential,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve Notes Toolkit API.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--process-interval", type=int, default=120, help="Periodic potential processor interval.")
    parser.add_argument("--cors-origins", default="", help="Comma-separated CORS allowlist. Falls back to env CORS_ALLOW_ORIGINS.")
    return parser.parse_args()


def _safe_segment(value: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9._-]+", "_", value.strip())
    return clean.strip("._-") or "anon"


def scoped_project_name(user_id: str, project_name: str) -> str:
    return f"u_{_safe_segment(user_id)}__{project_name.strip()}"


def unscoped_project_name(user_id: str, scoped: str) -> str | None:
    prefix = f"u_{_safe_segment(user_id)}__"
    if not scoped.startswith(prefix):
        return None
    return scoped[len(prefix) :]


def _jwt_payload_unsafe(token: str) -> dict:
    parts = token.split(".")
    if len(parts) < 2:
        return {}
    payload = parts[1]
    payload += "=" * (-len(payload) % 4)
    try:
        raw = base64.urlsafe_b64decode(payload.encode("ascii"))
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return {}


@dataclass(frozen=True)
class AuthUser:
    user_id: str
    email: str
    provider: str


class AuthError(Exception):
    pass


class GoogleVerifier:
    def __init__(self) -> None:
        self.client_id = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
        self.allow_insecure = os.environ.get("ALLOW_INSECURE_GOOGLE", "").strip() == "1"
        self._cache: dict[str, tuple[float, AuthUser]] = {}
        self._lock = threading.Lock()

    def _cache_get(self, token: str) -> AuthUser | None:
        now = datetime.now().timestamp()
        with self._lock:
            item = self._cache.get(token)
            if item is None:
                return None
            exp, user = item
            if exp < now:
                self._cache.pop(token, None)
                return None
            return user

    def _cache_set(self, token: str, user: AuthUser, exp_ts: float) -> None:
        with self._lock:
            self._cache[token] = (exp_ts, user)

    def verify(self, bearer_token: str) -> AuthUser:
        token = bearer_token.strip()
        if not token:
            raise AuthError("Missing Bearer token.")

        cached = self._cache_get(token)
        if cached:
            return cached

        if not self.client_id and not self.allow_insecure:
            raise AuthError("Server auth not configured: set GOOGLE_CLIENT_ID.")

        if self.allow_insecure and not self.client_id:
            payload = _jwt_payload_unsafe(token)
            sub = str(payload.get("sub", "")).strip()
            if not sub:
                raise AuthError("Invalid token payload (missing sub).")
            exp = float(payload.get("exp", datetime.now().timestamp() + 300))
            user = AuthUser(user_id=sub, email=str(payload.get("email", "")), provider="google")
            self._cache_set(token, user, exp)
            return user

        req = Request(
            f"https://oauth2.googleapis.com/tokeninfo?id_token={token}",
            method="GET",
            headers={"Accept": "application/json"},
        )
        try:
            with urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            raise AuthError(f"Google token verification failed: {exc}") from exc

        audience = str(data.get("aud", "")).strip()
        sub = str(data.get("sub", "")).strip()
        if not sub:
            raise AuthError("Invalid Google token: missing sub.")
        if self.client_id and audience != self.client_id:
            raise AuthError("Invalid Google token audience.")
        exp = float(data.get("exp", datetime.now().timestamp() + 300))
        user = AuthUser(
            user_id=sub,
            email=str(data.get("email", "")).strip(),
            provider="google",
        )
        self._cache_set(token, user, exp)
        return user


def run_action(paths, *, action: str, payload: dict, actor: str):
    if action == "add_note":
        return add_note(paths, str(payload.get("text", "")), actor=actor)
    if action == "add_todo":
        return add_todo(paths, str(payload.get("text", "")), actor=actor)
    if action == "approve_potential":
        return approve_potential(paths, int(payload.get("id")), actor=actor)
    if action == "reject_potential":
        return reject_potential(paths, int(payload.get("id")), actor=actor)
    if action == "complete_todo":
        return complete_todo(paths, int(payload.get("id")), actor=actor)
    if action == "mark_long_term_todo":
        return mark_todo_long_term(paths, int(payload.get("id")), actor=actor)
    if action == "dismiss_note":
        return dismiss_note(paths, int(payload.get("id")), actor=actor)
    raise ValueError(f"Unsupported action: {action}")


def user_projects_summary(user_id: str) -> list[dict]:
    prefix = f"u_{_safe_segment(user_id)}__"
    rows = []
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


def user_project_state(user_id: str, project_name: str) -> dict:
    scoped = scoped_project_name(user_id, project_name)
    state = project_state(project_paths(scoped))
    state["project"] = project_name
    state["user_id"] = user_id
    return state


def main() -> int:
    args = parse_args()
    verifier = GoogleVerifier()
    stop_event = threading.Event()
    raw_origins = args.cors_origins.strip() or os.environ.get("CORS_ALLOW_ORIGINS", "").strip()
    cors_allowlist = {item.strip() for item in raw_origins.split(",") if item.strip()}

    def processor_worker() -> None:
        interval = max(10, int(args.process_interval))
        while not stop_event.wait(interval):
            for row in all_projects_summary():
                try:
                    process_potential_todos(project_paths(row["project"]), actor="system", log_writes=True)
                except Exception:
                    continue

    worker = threading.Thread(target=processor_worker, daemon=True)
    worker.start()

    class Handler(BaseHTTPRequestHandler):
        def _origin_allowed(self, origin: str) -> bool:
            if not origin:
                return False
            if "*" in cors_allowlist:
                return True
            return origin in cors_allowlist

        def _apply_cors(self) -> None:
            origin = str(self.headers.get("Origin", "")).strip()
            if self._origin_allowed(origin):
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")
                self.send_header("Access-Control-Allow-Credentials", "true")
                self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

        def _json(self, payload: dict, status: int = 200) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self._apply_cors()
            self.end_headers()
            self.wfile.write(body)

        def _read_json(self) -> dict:
            length = int(self.headers.get("Content-Length", "0") or "0")
            raw = self.rfile.read(length) if length > 0 else b"{}"
            try:
                return json.loads(raw.decode("utf-8")) if raw else {}
            except json.JSONDecodeError as exc:
                raise ValueError("Invalid JSON payload.") from exc

        def _auth(self) -> AuthUser:
            auth = str(self.headers.get("Authorization", "")).strip()
            if not auth.lower().startswith("bearer "):
                raise AuthError("Missing Authorization: Bearer <google_id_token>.")
            token = auth.split(" ", 1)[1].strip()
            return verifier.verify(token)

        def do_OPTIONS(self) -> None:  # noqa: N802
            self.send_response(204)
            self._apply_cors()
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path

            if path == "/health":
                self._json({"ok": True, "time": datetime.now(timezone.utc).isoformat()})
                return

            if path == "/api/projects":
                try:
                    user = self._auth()
                except AuthError as exc:
                    self._json({"ok": False, "message": str(exc)}, status=401)
                    return
                self._json(
                    {
                        "projects": user_projects_summary(user.user_id),
                        "refreshed_at": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z"),
                    }
                )
                return

            if path.startswith("/api/project/") and path.endswith("/state"):
                project_name = unquote(path[len("/api/project/") : -len("/state")]).strip("/")
                if not project_name:
                    self._json({"ok": False, "message": "Project name is required."}, status=400)
                    return
                try:
                    user = self._auth()
                except AuthError as exc:
                    self._json({"ok": False, "message": str(exc)}, status=401)
                    return
                self._json(user_project_state(user.user_id, project_name))
                return

            if path == "/v1/projects":
                try:
                    user = self._auth()
                except AuthError as exc:
                    self._json({"ok": False, "message": str(exc)}, status=401)
                    return
                rows = user_projects_summary(user.user_id)
                self._json({"ok": True, "projects": rows, "user_id": user.user_id})
                return

            if path.startswith("/v1/projects/") and path.endswith("/state"):
                project_name = unquote(path[len("/v1/projects/") : -len("/state")]).strip("/")
                if not project_name:
                    self._json({"ok": False, "message": "Project name is required."}, status=400)
                    return
                try:
                    user = self._auth()
                except AuthError as exc:
                    self._json({"ok": False, "message": str(exc)}, status=401)
                    return
                state = user_project_state(user.user_id, project_name)
                self._json({"ok": True, "state": state})
                return

            self._json({"ok": False, "message": "Not found."}, status=404)

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path
            try:
                payload = self._read_json()
            except ValueError as exc:
                self._json({"ok": False, "message": str(exc)}, status=400)
                return

            if path.startswith("/api/project/") and path.endswith("/actions"):
                project_name = unquote(path[len("/api/project/") : -len("/actions")]).strip("/")
                if not project_name:
                    self._json({"ok": False, "message": "Project name is required."}, status=400)
                    return
                try:
                    user = self._auth()
                except AuthError as exc:
                    self._json({"ok": False, "message": str(exc)}, status=401)
                    return
                action = str(payload.get("action", "")).strip()
                actor = str(payload.get("actor", "web")).strip() or "web"
                scoped = scoped_project_name(user.user_id, project_name)
                paths = project_paths(scoped)
                try:
                    result = run_action(paths, action=action, payload=payload, actor=actor)
                except ValueError as exc:
                    self._json({"ok": False, "message": str(exc)}, status=400)
                    return
                except Exception as exc:
                    self._json({"ok": False, "message": str(exc)}, status=500)
                    return
                if not result.ok:
                    self._json({"ok": False, "message": result.message}, status=400)
                    return
                self._json({"ok": True, "message": result.message, "anchor": result.anchor, "state": user_project_state(user.user_id, project_name)})
                return

            if path.startswith("/v1/projects/") and path.endswith("/actions"):
                project_name = unquote(path[len("/v1/projects/") : -len("/actions")]).strip("/")
                if not project_name:
                    self._json({"ok": False, "message": "Project name is required."}, status=400)
                    return
                try:
                    user = self._auth()
                except AuthError as exc:
                    self._json({"ok": False, "message": str(exc)}, status=401)
                    return
                action = str(payload.get("action", "")).strip()
                actor = str(payload.get("actor", "api")).strip() or "api"
                scoped = scoped_project_name(user.user_id, project_name)
                paths = project_paths(scoped)
                try:
                    result = run_action(paths, action=action, payload=payload, actor=actor)
                except ValueError as exc:
                    self._json({"ok": False, "message": str(exc)}, status=400)
                    return
                except Exception as exc:
                    self._json({"ok": False, "message": str(exc)}, status=500)
                    return
                if not result.ok:
                    self._json({"ok": False, "message": result.message}, status=400)
                    return
                state = user_project_state(user.user_id, project_name)
                self._json(
                    {
                        "ok": True,
                        "message": result.message,
                        "anchor": result.anchor,
                        "state": state,
                    }
                )
                return

            self._json({"ok": False, "message": "Not found."}, status=404)

        def log_message(self, fmt: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Notes API running at http://{args.host}:{args.port}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nNotes API stopped.")
    finally:
        stop_event.set()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
