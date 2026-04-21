#!/usr/bin/env python3
"""Local web dashboard for Notes Toolkit v2 (home + project views)."""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlencode, urlparse
from urllib.request import Request, urlopen

THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

from notes_app import (
    add_note,
    add_todo,
    all_projects_summary,
    append_behavior_log,
    approve_potential,
    complete_todo,
    default_project_name,
    dismiss_note,
    list_projects,
    mark_todo_long_term,
    process_potential_todos,
    project_paths,
    project_state,
    reject_potential,
    snapshot_notes,
)


DATE_HEADING_RE = re.compile(r"^##\s+\d{4}-\d{2}-\d{2}\s*$")


@dataclass(frozen=True)
class AuthUser:
    user_id: str
    email: str


class AuthError(Exception):
    pass


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
            user = AuthUser(user_id=sub, email=str(payload.get("email", "")))
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
        user = AuthUser(user_id=sub, email=str(data.get("email", "")).strip())
        self._cache_set(token, user, exp)
        return user


class GoogleOAuthClient:
    def __init__(self) -> None:
        self.client_id = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
        self.client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()
        self.redirect_uri = os.environ.get("GOOGLE_REDIRECT_URI", "").strip()

    def is_configured(self) -> bool:
        return bool(self.client_id and self.client_secret and self.redirect_uri)

    def build_authorize_url(self, state: str) -> str:
        params = urlencode(
            {
                "client_id": self.client_id,
                "redirect_uri": self.redirect_uri,
                "response_type": "code",
                "scope": "openid email profile",
                "prompt": "select_account",
                "state": state,
            }
        )
        return f"https://accounts.google.com/o/oauth2/v2/auth?{params}"

    def exchange_code_for_id_token(self, code: str) -> str:
        payload = urlencode(
            {
                "code": code,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "redirect_uri": self.redirect_uri,
                "grant_type": "authorization_code",
            }
        ).encode("utf-8")
        req = Request(
            "https://oauth2.googleapis.com/token",
            method="POST",
            data=payload,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        with urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        id_token = str(data.get("id_token", "")).strip()
        if not id_token:
            raise AuthError("Google token exchange missing id_token.")
        return id_token


class SessionManager:
    def __init__(self, secret: str, *, max_age_seconds: int = 14 * 24 * 3600) -> None:
        self.secret = secret.encode("utf-8")
        self.max_age_seconds = max_age_seconds

    def _sign(self, payload_b64: str) -> str:
        sig = hmac.new(self.secret, payload_b64.encode("utf-8"), hashlib.sha256).digest()
        return base64.urlsafe_b64encode(sig).decode("ascii").rstrip("=")

    def issue(self, user: AuthUser) -> str:
        payload = {
            "sub": user.user_id,
            "email": user.email,
            "exp": int(time.time()) + self.max_age_seconds,
        }
        payload_json = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        payload_b64 = base64.urlsafe_b64encode(payload_json).decode("ascii").rstrip("=")
        return f"{payload_b64}.{self._sign(payload_b64)}"

    def verify(self, token: str) -> AuthUser:
        raw = token.strip()
        if "." not in raw:
            raise AuthError("Invalid session token.")
        payload_b64, sig = raw.split(".", 1)
        expected = self._sign(payload_b64)
        if not hmac.compare_digest(sig, expected):
            raise AuthError("Session signature mismatch.")
        payload_raw = base64.urlsafe_b64decode((payload_b64 + "=" * (-len(payload_b64) % 4)).encode("ascii"))
        payload = json.loads(payload_raw.decode("utf-8"))
        exp = int(payload.get("exp", 0))
        if exp <= int(time.time()):
            raise AuthError("Session expired.")
        sub = str(payload.get("sub", "")).strip()
        if not sub:
            raise AuthError("Session missing user id.")
        return AuthUser(user_id=sub, email=str(payload.get("email", "")).strip())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve Notes Toolkit dashboard (home + project).")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--project", default="", help="Initial project. Default: cwd folder name if exists.")
    parser.add_argument("--notes", default="", help="Legacy NOTES.md path. Used only to infer initial project.")
    parser.add_argument("--process-interval", type=int, default=120, help="Background processing interval in seconds.")
    return parser.parse_args()


def pick_initial_project(explicit: str) -> str:
    if explicit.strip():
        return explicit.strip()
    candidate = default_project_name()
    existing = {p.name for p in list_projects(create_root=True)}
    return candidate if candidate in existing else ""


def infer_project_from_notes(notes_path: str) -> str:
    value = (notes_path or "").strip()
    if not value:
        return ""
    path = Path(value).expanduser().resolve()
    if path.name != "NOTES.md":
        return ""
    if path.parent.name == "active":
        return path.parent.parent.name
    # Legacy repo layout: <project>/Notes/NOTES.md should map to the project folder.
    if path.parent.name.lower() == "notes":
        return path.parent.parent.name
    return path.parent.name


def notes_metrics(text: str) -> dict[str, int | str]:
    lines = text.splitlines()
    return {
        "line_count": len(lines),
        "char_count": len(text),
        "date_heading_count": sum(1 for line in lines if DATE_HEADING_RE.match(line)),
        "sha1": hashlib.sha1(text.encode("utf-8")).hexdigest(),
    }


def guard_paths(project) -> tuple[Path, Path]:
    guard_dir = project.archive_dir / "guard"
    return guard_dir / "NOTES.last_good.md", guard_dir / "state.json"


def load_last_good(project) -> tuple[str, dict[str, int | str]] | None:
    last_good_path, state_path = guard_paths(project)
    if not last_good_path.exists():
        return None

    try:
        text = last_good_path.read_text(encoding="utf-8")
    except Exception:
        return None

    metrics = notes_metrics(text)
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
            recorded = str(state.get("sha1", "")).strip()
            if recorded and recorded != metrics["sha1"]:
                return None
        except Exception:
            # Best effort only; continue with computed metrics.
            pass
    return text, metrics


def persist_last_good(project, text: str, metrics: dict[str, int | str]) -> None:
    last_good_path, state_path = guard_paths(project)
    last_good_path.parent.mkdir(parents=True, exist_ok=True)
    last_good_path.write_text(text, encoding="utf-8")
    state = {
        "updated_at": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z"),
        "line_count": int(metrics["line_count"]),
        "char_count": int(metrics["char_count"]),
        "date_heading_count": int(metrics["date_heading_count"]),
        "sha1": str(metrics["sha1"]),
    }
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def should_restore_from_shrink(current: dict[str, int | str], baseline: dict[str, int | str]) -> bool:
    baseline_lines = int(baseline["line_count"])
    baseline_chars = int(baseline["char_count"])
    current_lines = int(current["line_count"])
    current_chars = int(current["char_count"])

    if baseline_lines < 80 or baseline_chars < 3500:
        return False
    if current_lines > 50:
        return False
    if current_lines > baseline_lines * 0.55:
        return False
    if current_chars > baseline_chars * 0.55:
        return False
    return True


def should_update_baseline(current: dict[str, int | str], baseline: dict[str, int | str] | None) -> bool:
    if baseline is None:
        return True

    if str(current["sha1"]) == str(baseline["sha1"]):
        return False

    current_lines = int(current["line_count"])
    current_chars = int(current["char_count"])
    baseline_lines = int(baseline["line_count"])
    baseline_chars = int(baseline["char_count"])

    if current_lines >= baseline_lines:
        return True
    if current_chars >= baseline_chars:
        return True

    line_ratio = current_lines / max(1, baseline_lines)
    char_ratio = current_chars / max(1, baseline_chars)
    return line_ratio >= 0.85 and char_ratio >= 0.85


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


def _parse_origin_list(raw: str) -> set[str]:
    values = set()
    for part in (raw or "").split(","):
        origin = part.strip().rstrip("/")
        if origin:
            values.add(origin)
    return values


def build_html(initial_project: str) -> str:
    init_json = json.dumps(initial_project, ensure_ascii=False)
    template = """<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Notes Toolkit Dashboard</title>
  <style>
    :root {{
      --bg: #fffbe6;
      --panel: #fffef3;
      --line: #eadfb0;
      --ink: #2f2a1f;
      --muted: #6f674f;
      --accent: #1f6feb;
      --ok: #157347;
      --warn: #b54708;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: linear-gradient(170deg, #fffdf0 0%, #fff4bf 100%);
      color: var(--ink);
      font-family: "Avenir Next", "Segoe UI", sans-serif;
    }}
    .wrap {{ max-width: 1160px; margin: 20px auto; padding: 0 14px; }}
    .header {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 14px;
      box-shadow: 0 6px 20px rgba(42, 57, 80, 0.08);
    }}
    .header h1 {{ margin: 0 0 8px; font-size: 22px; }}
    .meta {{ margin: 0; color: var(--muted); font-size: 13px; }}
    .toolbar {{ margin-top: 10px; display: flex; gap: 8px; flex-wrap: wrap; }}
    button {{
      border: 1px solid var(--line);
      background: #fff;
      border-radius: 9px;
      padding: 7px 10px;
      cursor: pointer;
      font-size: 13px;
    }}
    button.primary {{ background: #eaf2ff; border-color: #b8d0ff; color: #0b4db5; }}
    .grid {{ margin-top: 14px; display: grid; gap: 12px; grid-template-columns: 1fr 1fr; }}
    .top-grid {{ grid-column: 1 / -1; display: grid; gap: 12px; grid-template-columns: 1fr 1fr; align-items: stretch; }}
    .right-stack {{ display: grid; gap: 12px; grid-template-rows: 1fr 1fr; height: 100%; min-height: 0; }}
    .card {{ background: var(--panel); border: 1px solid var(--line); border-radius: 12px; padding: 12px; }}
    .stack-card {{ display: flex; flex-direction: column; min-height: 0; }}
    .stack-card .list {{ min-height: 0; overflow: auto; }}
    .title {{ margin: 0 0 8px; font-size: 15px; font-weight: 700; }}
    .list {{ display: grid; gap: 7px; }}
    .row {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 8px;
      font-size: 13px;
      display: flex;
      justify-content: space-between;
      gap: 8px;
      align-items: flex-start;
    }}
    .row-main {{ min-width: 0; flex: 1; }}
    .row-text {{ white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
    .project-row {{ display: flex; justify-content: space-between; gap: 8px; align-items: center; }}
    .todo-complete {{ flex: 0 0 auto; display: flex; align-items: center; }}
    .todo-check {{ width: 18px; height: 18px; cursor: pointer; }}
    .todo-row {{ align-items: flex-start; }}
    .todo-left {{ flex: 0 0 auto; padding-top: 2px; }}
    .todo-main {{ min-width: 0; flex: 1; }}
    .todo-head {{ display: flex; align-items: baseline; gap: 8px; min-width: 0; }}
    .todo-brief {{ min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
    .todo-seeall {{
      border: none;
      background: transparent;
      color: #0b4db5;
      font-size: 12px;
      padding: 0;
      cursor: pointer;
      flex: 0 0 auto;
      min-width: 52px;
      text-align: right;
    }}
    .todo-full {{ margin-top: 6px; font-size: 12px; line-height: 1.4; white-space: normal; }}
    .todo-footer {{ margin-top: 6px; display: flex; justify-content: flex-end; }}
    .hidden-inline {{ display: none; }}
    .notes-row .todo-brief {{ font-weight: 500; }}
    .recovered-row {{
      background: linear-gradient(180deg, #fffdf6 0%, #fff6d9 100%);
      border-color: #d9c27a;
    }}
    .notes-meta {{ margin-top: 4px; }}
    .potential-actions {{ display: flex; gap: 6px; flex: 0 0 auto; }}
    .icon-btn {{
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      width: 28px;
      height: 28px;
      padding: 0;
      font-size: 14px;
      line-height: 1;
      cursor: pointer;
    }}
    .icon-btn.accept {{ color: var(--ok); }}
    .icon-btn.reject {{ color: #b42318; }}
    .icon-btn.longterm {{ color: #0b4db5; font-weight: 700; }}
    .muted {{ color: var(--muted); font-size: 12px; }}
    .id {{ color: #0b4db5; font-weight: 700; }}
    .status-pending {{ color: var(--warn); }}
    .status-promoted, .status-done {{ color: var(--ok); }}
    .forms {{ display: grid; gap: 8px; }}
    .inline {{ display: flex; gap: 8px; flex-wrap: wrap; }}
    input[type=\"text\"], input[type=\"number\"] {{
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 7px;
      min-width: 180px;
      font-size: 13px;
    }}
    .full {{ grid-column: 1 / -1; }}
    .hidden {{ display: none; }}
    @media (max-width: 900px) {{
      .grid {{ grid-template-columns: 1fr; }}
      .top-grid {{ grid-template-columns: 1fr; }}
      .right-stack {{ grid-template-rows: auto auto; height: auto; }}
    }}
  </style>
</head>
<body>
  <div class=\"wrap\">
    <div class=\"header\">
      <h1>Notes Toolkit Dashboard</h1>
      <p id=\"meta\" class=\"meta\">Loading...</p>
      <div class=\"toolbar\" style=\"margin-top:8px; border-top:1px dashed var(--line); padding-top:8px;\">
        <button id=\"btn-google-login\">Google Login (Redirect)</button>
        <button id=\"btn-google-logout\">Logout</button>
        <span id=\"auth-label\" class=\"muted\">Not signed in</span>
      </div>
      <div class=\"toolbar\">
        <button id=\"btn-global\" class=\"primary\">Global View</button>
        <button id=\"btn-project\">Current Project</button>
        <button id=\"btn-refresh\">Refresh</button>
        <button id=\"btn-notes\">Notes</button>
        <span id=\"current-project\" class=\"muted\"></span>
      </div>
    </div>

    <div id=\"home-view\" class=\"grid\">
      <section class=\"card full\">
        <h2 class=\"title\">Projects</h2>
        <div id=\"project-list\" class=\"list\"></div>
      </section>
    </div>

    <div id=\"project-view\" class=\"grid hidden\">
      <div class=\"top-grid\">
        <section id=\"open-todos-card\" class=\"card\">
          <h2 class=\"title\">Open Todos <span id=\"todo-count\" class=\"muted\"></span></h2>
          <div id=\"todo-list\" class=\"list\"></div>
        </section>

        <div class=\"right-stack\">
          <section class=\"card stack-card\">
            <h2 class=\"title\">Potential <span id=\"pending-count\" class=\"muted\"></span></h2>
            <div id=\"potential-list\" class=\"list\"></div>
          </section>
          <section class=\"card stack-card\">
            <h2 class=\"title\">Long-term Todos <span id=\"long-term-count\" class=\"muted\"></span></h2>
            <div id=\"long-term-list\" class=\"list\"></div>
          </section>
        </div>
      </div>

      <section id=\"notes-card\" class=\"card full hidden\">
        <h2 class=\"title\">Notes Entries <span id=\"notes-count\" class=\"muted\"></span></h2>
        <div id=\"notes-list\" class=\"list\"></div>
      </section>

      <section class=\"card full\">
        <h2 class=\"title\">Actions</h2>
        <div class=\"forms\">
          <div class=\"inline\">
            <input id=\"note-input\" type=\"text\" placeholder=\"add note text\" />
            <button id=\"add-note\">Add Note</button>
          </div>
          <div class=\"inline\">
            <input id=\"todo-input\" type=\"text\" placeholder=\"add todo text\" />
            <button id=\"add-todo\">Add Todo</button>
          </div>
          <div class=\"inline\">
            <input id=\"approve-id\" type=\"number\" min=\"1\" placeholder=\"pending id\" />
            <button id=\"approve-potential\">Approve Potential</button>
            <button id=\"reject-potential\">Reject Potential</button>
          </div>
          <div class=\"inline\">
            <input id=\"complete-id\" type=\"number\" min=\"1\" placeholder=\"todo id\" />
            <button id=\"complete-todo\">Complete Todo</button>
          </div>
        </div>
      </section>
    </div>
  </div>

  <script>
    const initialProject = {init_json};
    const meta = document.getElementById("meta");
    const currentProjectLabel = document.getElementById("current-project");
    const homeView = document.getElementById("home-view");
    const projectView = document.getElementById("project-view");
    const projectList = document.getElementById("project-list");
    const openTodosCard = document.getElementById("open-todos-card");
    const todoList = document.getElementById("todo-list");
    const potentialList = document.getElementById("potential-list");
    const longTermList = document.getElementById("long-term-list");
    const notesCard = document.getElementById("notes-card");
    const notesList = document.getElementById("notes-list");
    const notesCount = document.getElementById("notes-count");
    const todoCount = document.getElementById("todo-count");
    const pendingCount = document.getElementById("pending-count");
    const longTermCount = document.getElementById("long-term-count");

    function readStoredProject() {{
      try {{
        return localStorage.getItem("notes_dashboard_last_project") || "";
      }} catch (_err) {{
        return "";
      }}
    }}

    function writeStoredProject(projectName) {{
      try {{
        if (projectName) {{
          localStorage.setItem("notes_dashboard_last_project", projectName);
        }}
      }} catch (_err) {{
        // Storage access can fail in strict browser modes; ignore.
      }}
    }}

    const storedProject = readStoredProject();
    let currentProject = "";
    let lastProject = initialProject || storedProject || "";
    let notesVisible = false;
    let refreshInFlight = false;
    const expandedTodoKeys = new Set();
    const expandedNoteKeys = new Set();
    const AUTO_REFRESH_MS = 2000;
    let signedIn = false;
    let signedInEmail = "";
    const authLabel = document.getElementById("auth-label");

    function updateAuthLabel() {{
      if (!signedIn) {{
        authLabel.textContent = "Not signed in";
        return;
      }}
      authLabel.textContent = `Signed in: ${{signedInEmail || "user"}}`;
    }}

    function initGoogleAuth() {{
      document.getElementById("btn-google-login").addEventListener("click", () => {{
        const next = `${{window.location.pathname}}${{window.location.search}}`;
        window.location.href = `/auth/google/login?next=${{encodeURIComponent(next)}}`;
      }});

      document.getElementById("btn-google-logout").addEventListener("click", async () => {{
        await fetch("/auth/logout", {{
          method: "POST",
          cache: "no-store",
          credentials: "same-origin",
        }});
        signedIn = false;
        signedInEmail = "";
        updateAuthLabel();
        meta.textContent = "Signed out.";
        await loadHome().catch(() => null);
      }});

      updateAuthLabel();
    }}

    function esc(s) {{
      return String(s)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;");
    }}

    function escapeRegExp(s) {{
      return String(s).replace(/[.*+?^${{}}()|[\\]\\\\]/g, "\\\\$&");
    }}

    function boldImportantNouns(text) {{
      const englishPhrases = [
        "knowledge base",
        "game cards",
        "game card",
        "game mode",
        "first sentence",
        "source of truth",
        "vector db",
        "to-do tracking",
      ];
      const englishWords = [
        "character",
        "characters",
        "persona",
        "personas",
        "profile",
        "friend",
        "hitmap",
        "intro",
        "voice",
        "voices",
        "latency",
        "memory",
        "memories",
        "vector",
        "database",
        "performance",
        "pipeline",
        "schema",
        "specification",
        "dashboard",
        "script",
        "scripts",
        "deploy",
        "deployment",
        "asset",
        "assets",
        "layout",
        "workflow",
        "config",
        "telegram",
        "quality",
        "cards",
        "card",
      ];
      const chineseTerms = [
        "角色",
        "角色卡",
        "知识库",
        "游戏卡",
        "人设",
        "用户",
        "主人公",
        "服饰",
        "声音",
        "引子",
        "关系",
        "朋友",
        "场景",
        "延迟",
        "性能",
        "记忆",
        "向量库",
        "部署",
        "脚本",
        "看板",
      ];
      const knownNames = ["zoe", "fei", "lebing", "乐冰", "美咲", "小萌", "Zoe", "Fei"];
      const capitalizedStopWords = new Set([
        "add",
        "need",
        "create",
        "recreate",
        "design",
        "optimize",
        "update",
        "please",
        "game",
        "mode",
        "for",
        "with",
        "and",
      ]);

      let out = esc(text || "");
      const wrapStrong = (value) => `<strong>${{value}}</strong>`;
      const replaceOutsideStrong = (input, pattern, replacer) => {{
        return String(input)
          .split(/(<strong>.*?<\\/strong>)/g)
          .map((seg) => (seg.startsWith("<strong>") ? seg : seg.replace(pattern, replacer)))
          .join("");
      }};

      englishPhrases
        .slice()
        .sort((a, b) => b.length - a.length)
        .forEach((phrase) => {{
          const re = new RegExp(`\\\\b(${{escapeRegExp(phrase)}})\\\\b`, "gi");
          out = replaceOutsideStrong(out, re, (m) => wrapStrong(m));
        }});

      englishWords.forEach((word) => {{
        const re = new RegExp(`\\\\b(${{escapeRegExp(word)}})\\\\b`, "gi");
        out = replaceOutsideStrong(out, re, (m) => wrapStrong(m));
      }});

      chineseTerms.forEach((term) => {{
        const re = new RegExp(escapeRegExp(term), "g");
        out = replaceOutsideStrong(out, re, (m) => wrapStrong(m));
      }});

      knownNames.forEach((name) => {{
        if (/^[A-Za-z]/.test(name)) {{
          const re = new RegExp(`\\\\b(${{escapeRegExp(name)}})\\\\b`, "gi");
          out = replaceOutsideStrong(out, re, (m) => wrapStrong(m));
          return;
        }}
        const re = new RegExp(escapeRegExp(name), "g");
        out = replaceOutsideStrong(out, re, (m) => wrapStrong(m));
      }});

      out = replaceOutsideStrong(
        out,
        /\\b([A-Za-z][A-Za-z0-9_-]{1,24})'s\\b/g,
        (full, token) => `${{wrapStrong(token)}}'s`
      );

      out = replaceOutsideStrong(out, /\\b([A-Z][a-z]{2,24})\\b/g, (full, token) => {{
        const lower = token.toLowerCase();
        if (capitalizedStopWords.has(lower)) {{
          return full;
        }}
        return wrapStrong(token);
      }});

      out = replaceOutsideStrong(
        out,
        /([\\u4e00-\\u9fff]{2,4})(?=的(?:朋友|同学|同事|角色|人设|Profile|profile))/g,
        (m, token) => wrapStrong(token)
      );

      out = replaceOutsideStrong(
        out,
        /([\\u4e00-\\u9fff]{2,4})(?=要的Profile)/g,
        (m, token) => wrapStrong(token)
      );

      return out;
    }}

    function stripTodoMeta(text) {{
      return String(text || "")
        .replace(/\\[\\d{{4}}-\\d{{2}}-\\d{{2}}\\s+\\d{{2}}:\\d{{2}}\\s+\\([^\\]]+\\)\\]\\s*/g, "")
        .replace(/^\\[(?:RECOVERED|REOPENED)[^\\]]*\\]\\s*/i, "")
        .replace(/^-\\s*\\[(?: |x|X)\\]\\s*/g, "")
        .replace(/\\s+/g, " ")
        .trim();
    }}

    function summarizeTodo(text, maxLen = 60) {{
      const full = stripTodoMeta(text);
      if (full.length <= maxLen) return {{ brief: full, full }};
      return {{ brief: `${{full.slice(0, maxLen).trimEnd()}}...`, full }};
    }}

    function stripNoteMeta(text) {{
      return String(text || "")
        .replace(/^\\[\\d{{4}}-\\d{{2}}-\\d{{2}}\\s+\\d{{2}}:\\d{{2}}\\s+\\([^\\]]+\\)\\]\\s*/g, "")
        .replace(/^\\[(?:RECOVERED|REOPENED)[^\\]]*\\]\\s*/i, "")
        .replace(/\\s+/g, " ")
        .trim();
    }}

    function isRecoveredEntry(text) {{
      const withoutTs = String(text || "")
        .replace(/^\\[\\d{{4}}-\\d{{2}}-\\d{{2}}\\s+\\d{{2}}:\\d{{2}}\\s+\\([^\\]]+\\)\\]\\s*/g, "")
        .trim();
      return /^\\[(?:RECOVERED|REOPENED)\\b/i.test(withoutTs);
    }}

    function todoKey(todo) {{
      return `${{currentProject}}::todo::${{todo.line_no || 0}}::${{todo.text || ""}}`;
    }}

    function noteKey(note) {{
      return `${{currentProject}}::note::${{note.line_no || 0}}::${{note.text || ""}}`;
    }}

    function summarizeText(text, maxLen = 80) {{
      const full = String(text || "").trim();
      if (full.length <= maxLen) return {{ brief: full, full }};
      return {{ brief: `${{full.slice(0, maxLen).trimEnd()}}...`, full }};
    }}

    function setTooltip(_node, _text) {{
      // Hover tooltip display is intentionally disabled.
    }}

    function setToolbarState(isHome) {{
      const globalBtn = document.getElementById("btn-global");
      const projectBtn = document.getElementById("btn-project");
      const notesBtn = document.getElementById("btn-notes");
      globalBtn.classList.toggle("primary", isHome);
      projectBtn.classList.toggle("primary", !isHome);
      projectBtn.disabled = !lastProject;
      notesBtn.classList.toggle("primary", !isHome && notesVisible);
      notesBtn.disabled = isHome || !lastProject;
    }}

    function applyNotesVisibility() {{
      notesCard.classList.toggle("hidden", !notesVisible);
    }}

    function renderNotesEntries(entries) {{
      notesCount.textContent = `(${entries.length})`;
      notesList.innerHTML = "";
      if (!entries.length) {{
        emptyNode(notesList, "No note entries found.");
        return;
      }}

      entries.forEach((n) => {{
        const prepared = summarizeText(stripNoteMeta(n.text), 90);
        const row = document.createElement("div");
        row.className = "row todo-row notes-row";
        if (isRecoveredEntry(n.text)) {{
          row.classList.add("recovered-row");
        }}
        setTooltip(row, n.text);
        const left = document.createElement("label");
        left.className = "todo-left";
        left.title = `Hide note #${{n.id}}`;
        left.innerHTML = `<input type="checkbox" class="todo-check" aria-label="Hide note #${{n.id}}" />`;
        left.querySelector("input").addEventListener("change", (ev) => {{
          if (!ev.target.checked) return;
          ev.target.disabled = true;
          runAction("dismiss_note", {{ id: n.id }});
        }});

        const right = document.createElement("div");
        right.className = "todo-main";
        right.innerHTML = `
          <div class="todo-head">
            <span class="id">#${{n.id}}</span>
            <span class="todo-brief">${{boldImportantNouns(prepared.brief || "(empty)")}}</span>
            <button type="button" class="todo-seeall">See all</button>
          </div>
          <div class="todo-full hidden-inline">${{boldImportantNouns(prepared.full || "(empty)")}}</div>
          <div class="muted notes-meta">section: ${{esc(n.section || "-")}} | line: ${{n.line_no}}</div>
        `;

        const seeAllBtn = right.querySelector(".todo-seeall");
        const fullNode = right.querySelector(".todo-full");
        const key = noteKey(n);
        if (expandedNoteKeys.has(key)) {{
          fullNode.classList.remove("hidden-inline");
          seeAllBtn.textContent = "See less";
        }}
        seeAllBtn.addEventListener("click", () => {{
          const hidden = fullNode.classList.toggle("hidden-inline");
          seeAllBtn.textContent = hidden ? "See all" : "See less";
          if (hidden) {{
            expandedNoteKeys.delete(key);
          }} else {{
            expandedNoteKeys.add(key);
          }}
        }});
        row.appendChild(left);
        row.appendChild(right);
        notesList.appendChild(row);
      }});
    }}

    function renderTodoRows(targetList, todos, emptyText, options = {{}}) {{
      const allowLongTermButton = Boolean(options.allowLongTermButton);
      targetList.innerHTML = "";
      if (!todos.length) {{
        emptyNode(targetList, emptyText);
        return;
      }}

      todos.forEach((t) => {{
        const summary = summarizeTodo(t.text);
        const row = document.createElement("div");
        row.className = "row todo-row";
        if (isRecoveredEntry(t.text)) {{
          row.classList.add("recovered-row");
        }}

        const left = document.createElement("label");
        left.className = "todo-left";
        left.innerHTML = `<input type="checkbox" class="todo-check" aria-label="Complete todo #${{t.id}}" />`;
        left.querySelector("input").addEventListener("change", (ev) => {{
          if (!ev.target.checked) return;
          ev.target.disabled = true;
          runAction("complete_todo", {{ id: t.id }});
        }});

        const right = document.createElement("div");
        right.className = "todo-main";
        right.innerHTML = `
          <div class="todo-head">
            <span class="id">#${{t.id}}</span>
            <span class="todo-brief">${{boldImportantNouns(summary.brief || "(empty)")}}</span>
            <button type="button" class="todo-seeall">See all</button>
          </div>
          <div class="todo-full hidden-inline">${{boldImportantNouns(summary.full || "(empty)")}}</div>
          ${{allowLongTermButton ? `<div class="todo-footer hidden-inline"><button type="button" class="icon-btn longterm todo-longterm" aria-label="Mark todo #${{t.id}} as long-term" title="Mark as long-term">L</button></div>` : ""}}
        `;
        const seeAllBtn = right.querySelector(".todo-seeall");
        const fullNode = right.querySelector(".todo-full");
        const footerNode = right.querySelector(".todo-footer");
        const longTermBtn = right.querySelector(".todo-longterm");
        const key = todoKey(t);
        if (expandedTodoKeys.has(key)) {{
          fullNode.classList.remove("hidden-inline");
          seeAllBtn.textContent = "See less";
          if (footerNode) {{
            footerNode.classList.remove("hidden-inline");
          }}
        }}
        seeAllBtn.addEventListener("click", () => {{
          const hidden = fullNode.classList.toggle("hidden-inline");
          seeAllBtn.textContent = hidden ? "See all" : "See less";
          if (footerNode) {{
            footerNode.classList.toggle("hidden-inline", hidden);
          }}
          if (hidden) {{
            expandedTodoKeys.delete(key);
          }} else {{
            expandedTodoKeys.add(key);
          }}
        }});
        if (longTermBtn) {{
          longTermBtn.addEventListener("click", () => {{
            longTermBtn.disabled = true;
            runAction("mark_long_term_todo", {{ id: t.id }});
          }});
        }}

        row.appendChild(left);
        row.appendChild(right);
        targetList.appendChild(row);
      }});
    }}

    function emptyNode(node, text) {{
      node.innerHTML = "";
      const div = document.createElement("div");
      div.className = "row muted";
      div.textContent = text;
      node.appendChild(div);
    }}

    async function apiGet(url) {{
      const res = await fetch(url, {{ cache: "no-store", credentials: "same-origin" }});
      if (!res.ok) {{
        const data = await res.json().catch(() => ({{}}));
        throw new Error(data.message || `${{res.status}} ${{res.statusText}}`);
      }}
      return await res.json();
    }}

    async function apiPost(url, body) {{
      const res = await fetch(url, {{
        method: "POST",
        credentials: "same-origin",
        headers: {{ "Content-Type": "application/json" }},
        body: JSON.stringify(body),
      }});
      const data = await res.json().catch(() => ({{ ok: false, message: "Invalid response" }}));
      if (!res.ok || data.ok === false) throw new Error(data.message || `${{res.status}} ${{res.statusText}}`);
      return data;
    }}

    async function refreshSession() {{
      const data = await apiGet("/api/session");
      signedIn = Boolean(data.logged_in);
      signedInEmail = String(data.email || "");
      updateAuthLabel();
      return signedIn;
    }}

    async function ensureFirstLoginInitialized() {{
      try {{
        const data = await apiPost("/api/init", {{ project_name: "home" }});
        if (data.initialized) {{
          meta.textContent = `Initialized first project: ${{data.project}}`;
        }}
      }} catch (err) {{
        meta.textContent = `Init check failed: ${{err.message || err}}`;
      }}
    }}

    async function refreshActiveView() {{
      if (refreshInFlight || document.hidden || !signedIn) return;
      refreshInFlight = true;
      try {{
        if (currentProject) {{
          await loadProject(currentProject);
        }} else {{
          await loadHome();
        }}
      }} catch (err) {{
        meta.textContent = err.message || String(err);
      }} finally {{
        refreshInFlight = false;
      }}
    }}

    async function loadHome() {{
      currentProject = "";
      notesVisible = false;
      currentProjectLabel.textContent = "Home View";
      setToolbarState(true);
      applyNotesVisibility();
      homeView.classList.remove("hidden");
      projectView.classList.add("hidden");

      const data = await apiGet("/api/projects");
      meta.textContent = `Projects: ${{data.projects.length}} | Updated: ${{data.refreshed_at}}`;

      projectList.innerHTML = "";
      if (!data.projects.length) {{
        emptyNode(projectList, "No projects found.");
        return;
      }}

      data.projects.forEach((p) => {{
        const row = document.createElement("div");
        row.className = "row project-row";
        setTooltip(row, `project=${{p.project}} todo=${{p.todo_count}} pending=${{p.potential_pending_count}} last=${{p.last_activity || "-"}}`);
        row.innerHTML = `
          <div>
            <div><strong>${{esc(p.project)}}</strong></div>
            <div class="muted">todo=${{p.todo_count}}, pending=${{p.potential_pending_count}}, last=${{esc(p.last_activity || "-")}}</div>
          </div>
          <button data-project="${{esc(p.project)}}">Open</button>
        `;
        row.querySelector("button").addEventListener("click", () => loadProject(p.project));
        projectList.appendChild(row);
      }});
    }}

    async function loadProject(projectName) {{
      currentProject = projectName;
      lastProject = projectName;
      writeStoredProject(projectName);
      currentProjectLabel.textContent = `Project: ${{projectName}}`;
      setToolbarState(false);
      applyNotesVisibility();
      homeView.classList.add("hidden");
      projectView.classList.remove("hidden");

      const data = await apiGet(`/api/project/${{encodeURIComponent(projectName)}}/state`);
      meta.textContent = `Updated: ${{data.updated_at}} | notes: ${{data.notes_path}}`;
      const longTermTodos = Array.isArray(data.long_term_todos) ? data.long_term_todos : [];
      const longTermTodoIds = new Set(longTermTodos.map((item) => item.id));
      const openTodos = Array.isArray(data.todos) ? data.todos.filter((item) => !longTermTodoIds.has(item.id)) : [];
      todoCount.textContent = `(${openTodos.length})`;
      pendingCount.textContent = `(${data.potential_pending_count})`;
      longTermCount.textContent = `(${longTermTodos.length})`;
      renderNotesEntries(Array.isArray(data.notes) ? data.notes : []);

      renderTodoRows(todoList, openTodos, "No open todos.", {{ allowLongTermButton: true }});
      renderTodoRows(longTermList, longTermTodos, "No long-term todos.");

      potentialList.innerHTML = "";
      const pending = data.potentials.filter((p) => p.status === "pending");
      if (!pending.length) {{
        emptyNode(potentialList, "No pending potential items.");
      }} else {{
        pending.forEach((p, idx) => {{
          const pendingId = idx + 1;
          const row = document.createElement("div");
          row.className = "row";
          setTooltip(row, p.text);
          row.innerHTML = `
            <div class="potential-actions">
              <button type="button" class="icon-btn accept" aria-label="Approve potential #${{pendingId}}">&#10003;</button>
              <button type="button" class="icon-btn reject" aria-label="Reject potential #${{pendingId}}">&#10005;</button>
            </div>
            <div class="row-main">
              <div class="row-text"><span class="id">#${{pendingId}}</span> <span class="status-pending">[pending]</span> ${{esc(p.text)}}</div>
              <div class="muted">${{esc(p.timestamp)}}</div>
            </div>
          `;
          const approveBtn = row.querySelector(".icon-btn.accept");
          const rejectBtn = row.querySelector(".icon-btn.reject");
          approveBtn.addEventListener("click", () => {{
            approveBtn.disabled = true;
            rejectBtn.disabled = true;
            runAction("approve_potential", {{ id: pendingId }});
          }});
          rejectBtn.addEventListener("click", () => {{
            approveBtn.disabled = true;
            rejectBtn.disabled = true;
            runAction("reject_potential", {{ id: pendingId }});
          }});
          potentialList.appendChild(row);
        }});
      }}

    }}

    async function runAction(action, payload) {{
      if (!currentProject) return;
      try {{
        await apiPost(`/api/project/${{encodeURIComponent(currentProject)}}/actions`, {{ action, ...payload }});
        await loadProject(currentProject);
      }} catch (err) {{
        alert(`Action failed: ${{err.message || err}}`);
      }}
    }}

    document.getElementById("btn-global").addEventListener("click", () => loadHome().catch((e) => (meta.textContent = e.message)));
    document.getElementById("btn-project").addEventListener("click", () => {{
      if (!lastProject) return;
      loadProject(lastProject).catch((e) => (meta.textContent = e.message));
    }});
    document.getElementById("btn-refresh").addEventListener("click", () => (currentProject ? loadProject(currentProject) : loadHome()).catch((e) => (meta.textContent = e.message)));
    document.getElementById("btn-notes").addEventListener("click", () => {{
      const targetProject = currentProject || lastProject;
      if (!targetProject) {{
        meta.textContent = "Open a project first to view Notes entries.";
        return;
      }}
      const ensureLoaded = currentProject
        ? Promise.resolve()
        : loadProject(targetProject).catch((e) => {{
            meta.textContent = e.message || String(e);
          }});
      ensureLoaded.then(() => {{
        notesVisible = true;
        setToolbarState(false);
        applyNotesVisibility();
        notesCard.scrollIntoView({{ behavior: "smooth", block: "start" }});
      }});
    }});

    document.getElementById("add-note").addEventListener("click", () => {{
      const value = document.getElementById("note-input").value.trim();
      if (!value) return;
      runAction("add_note", {{ text: value }});
      document.getElementById("note-input").value = "";
    }});

    document.getElementById("add-todo").addEventListener("click", () => {{
      const value = document.getElementById("todo-input").value.trim();
      if (!value) return;
      runAction("add_todo", {{ text: value }});
      document.getElementById("todo-input").value = "";
    }});

    document.getElementById("approve-potential").addEventListener("click", () => {{
      const id = parseInt(document.getElementById("approve-id").value, 10);
      if (!id) return;
      runAction("approve_potential", {{ id }});
    }});

    document.getElementById("reject-potential").addEventListener("click", () => {{
      const id = parseInt(document.getElementById("approve-id").value, 10);
      if (!id) return;
      runAction("reject_potential", {{ id }});
    }});

    document.getElementById("complete-todo").addEventListener("click", () => {{
      const id = parseInt(document.getElementById("complete-id").value, 10);
      if (!id) return;
      runAction("complete_todo", {{ id }});
    }});

    async function init() {{
      const params = new URLSearchParams(window.location.search);
      if (params.get("auth_error")) {{
        meta.textContent = `Google auth failed: ${{params.get("auth_error")}}`;
      }} else {{
        meta.textContent = "Please sign in with Google to load dashboard data.";
      }}
      try {{
        const ok = await refreshSession();
        if (ok) {{
          await ensureFirstLoginInitialized();
          await refreshActiveView();
        }}
      }} catch (_err) {{
        // keep signed-out state on startup
      }}
      setInterval(refreshActiveView, AUTO_REFRESH_MS);
    }}

    initGoogleAuth();
    init();
  </script>
</body>
</html>
"""
    template = template.replace("{{", "{").replace("}}", "}")
    return template.replace("{init_json}", init_json)


def main() -> int:
    args = parse_args()
    verifier = GoogleVerifier()
    oauth_client = GoogleOAuthClient()
    session_secret = os.environ.get("SESSION_SECRET", "").strip()
    if not session_secret:
        session_secret = hashlib.sha256(
            f"{os.getpid()}-{datetime.now(timezone.utc).isoformat()}".encode("utf-8")
        ).hexdigest()
    session_manager = SessionManager(session_secret)
    frontend_origins = _parse_origin_list(os.environ.get("FRONTEND_ORIGIN", ""))
    frontend_app_url = os.environ.get("FRONTEND_APP_URL", "").strip()
    inferred = infer_project_from_notes(args.notes)
    initial_project = pick_initial_project(args.project or inferred)

    stop_event = threading.Event()

    def processor_worker() -> None:
        interval = max(10, args.process_interval)
        last_notes_sig: dict[str, tuple[int, int]] = {}
        last_good_cache: dict[str, tuple[str, dict[str, int | str]]] = {}
        while not stop_event.wait(interval):
            for proj in list_projects(create_root=True):
                try:
                    if proj.notes_path.exists():
                        current_text = proj.notes_path.read_text(encoding="utf-8")
                        current_metrics = notes_metrics(current_text)
                        baseline = last_good_cache.get(proj.name)
                        if baseline is None:
                            loaded = load_last_good(proj)
                            if loaded:
                                baseline = loaded
                                last_good_cache[proj.name] = loaded

                        if baseline and should_restore_from_shrink(current_metrics, baseline[1]):
                            shrunk_metrics = current_metrics
                            snapshot_notes(proj.notes_path, reason="guard_detected_shrink")
                            guard_dir = proj.archive_dir / "guard"
                            guard_dir.mkdir(parents=True, exist_ok=True)
                            bad_name = datetime.now().astimezone().strftime("NOTES.bad.%Y%m%d_%H%M%S.md")
                            (guard_dir / bad_name).write_text(current_text, encoding="utf-8")

                            restored_text = baseline[0]
                            proj.notes_path.write_text(restored_text, encoding="utf-8")
                            current_text = restored_text
                            current_metrics = notes_metrics(current_text)
                            append_behavior_log(
                                proj,
                                actor="system",
                                action="guard_restore",
                                target="notes_shrink",
                                status="done",
                                before_summary=(
                                    f"lines={shrunk_metrics['line_count']} chars={shrunk_metrics['char_count']} "
                                    f"(detected corrupted snapshot in {bad_name})"
                                ),
                                after_summary=(
                                    f"restored last_good lines={current_metrics['line_count']} "
                                    f"chars={current_metrics['char_count']}"
                                ),
                                notes_anchor="active/NOTES.md",
                            )

                        stat = proj.notes_path.stat()
                        sig = (stat.st_mtime_ns, stat.st_size)
                        previous = last_notes_sig.get(proj.name)
                        if previous != sig:
                            snapshot_notes(proj.notes_path, reason="dashboard_guard")
                            last_notes_sig[proj.name] = sig

                        baseline_metrics = baseline[1] if baseline else None
                        if should_update_baseline(current_metrics, baseline_metrics):
                            persist_last_good(proj, current_text, current_metrics)
                            last_good_cache[proj.name] = (current_text, current_metrics)
                    process_potential_todos(proj, actor="system", log_writes=True)
                except Exception:
                    continue

    worker = threading.Thread(target=processor_worker, daemon=True)
    worker.start()

    class Handler(BaseHTTPRequestHandler):
        SESSION_COOKIE = "notes_session"
        OAUTH_STATE_COOKIE = "notes_oauth_state"
        OAUTH_NEXT_COOKIE = "notes_oauth_next"

        def _secure_cookie(self) -> bool:
            mode = os.environ.get("COOKIE_SECURE", "auto").strip().lower()
            if mode in {"1", "true", "yes", "on"}:
                return True
            if mode in {"0", "false", "no", "off"}:
                return False
            return "https" in str(self.headers.get("X-Forwarded-Proto", "")).lower()

        def _cookies(self) -> SimpleCookie:
            jar = SimpleCookie()
            jar.load(str(self.headers.get("Cookie", "")))
            return jar

        def _get_cookie(self, name: str) -> str:
            jar = self._cookies()
            morsel = jar.get(name)
            return str(morsel.value) if morsel else ""

        def _cookie_header(
            self,
            name: str,
            value: str,
            *,
            max_age: int | None = None,
            http_only: bool = True,
            same_site: str | None = None,
        ) -> str:
            chosen_same_site = (same_site or os.environ.get("COOKIE_SAMESITE", "Lax")).strip() or "Lax"
            parts = [f"{name}={value}", "Path=/", f"SameSite={chosen_same_site}"]
            if http_only:
                parts.append("HttpOnly")
            if self._secure_cookie():
                parts.append("Secure")
            if max_age is not None:
                parts.append(f"Max-Age={max_age}")
            return "; ".join(parts)

        def _clear_cookie_headers(self, name: str, *, http_only: bool = True) -> list[tuple[str, str]]:
            # Clear across common SameSite/Secure combinations to handle legacy cookies.
            configured = (os.environ.get("COOKIE_SAMESITE", "Lax").strip() or "Lax").capitalize()
            same_sites = [configured, "Lax", "None"]
            headers: list[tuple[str, str]] = []
            seen: set[tuple[str, bool]] = set()
            for same_site in same_sites:
                key = (same_site, same_site == "None")
                if key in seen:
                    continue
                seen.add(key)
                secure_options = [True] if same_site == "None" else [True, False]
                for secure in secure_options:
                    parts = [
                        f"{name}=",
                        "Path=/",
                        f"SameSite={same_site}",
                        "Expires=Thu, 01 Jan 1970 00:00:00 GMT",
                        "Max-Age=0",
                    ]
                    if http_only:
                        parts.append("HttpOnly")
                    if secure:
                        parts.append("Secure")
                    headers.append(("Set-Cookie", "; ".join(parts)))
            return headers

        def _allow_origin(self, origin: str) -> bool:
            cleaned = (origin or "").strip().rstrip("/")
            if not cleaned:
                return False
            if frontend_origins:
                return cleaned in frontend_origins
            host = str(self.headers.get("Host", "")).strip()
            scheme = "https" if self._secure_cookie() else "http"
            same_origin = f"{scheme}://{host}".rstrip("/")
            return cleaned == same_origin

        def _cors_headers(self) -> list[tuple[str, str]]:
            origin = str(self.headers.get("Origin", "")).strip().rstrip("/")
            if self._allow_origin(origin):
                return [
                    ("Access-Control-Allow-Origin", origin),
                    ("Access-Control-Allow-Credentials", "true"),
                    ("Vary", "Origin"),
                ]
            return []

        def _safe_next_url(self, raw: str) -> str:
            value = (raw or "").strip()
            if value.startswith("/") and not value.startswith("//"):
                return value
            parsed = urlparse(value)
            if parsed.scheme in {"http", "https"} and parsed.netloc:
                origin = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
                if self._allow_origin(origin):
                    return value
            return "/"

        def _append_query(self, url: str, key: str, value: str) -> str:
            sep = "&" if "?" in url else "?"
            return f"{url}{sep}{key}={quote(value, safe='')}"

        def _auth(self) -> AuthUser:
            auth = str(self.headers.get("Authorization", "")).strip()
            if auth.lower().startswith("bearer "):
                token = auth.split(" ", 1)[1].strip()
                return verifier.verify(token)
            session_token = self._get_cookie(self.SESSION_COOKIE)
            if session_token:
                return session_manager.verify(session_token)
            raise AuthError("Please sign in with Google first.")

        def _user_projects_summary(self, user_id: str) -> list[dict]:
            prefix = f"u_{_safe_segment(user_id)}__"
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

        def _user_project_state(self, user_id: str, project_name: str) -> dict:
            scoped = scoped_project_name(user_id, project_name)
            state = project_state(project_paths(scoped))
            state["project"] = project_name
            state["user_id"] = user_id
            return state

        def _write_json(
            self,
            payload: dict,
            *,
            status: int = 200,
            extra_headers: list[tuple[str, str]] | None = None,
        ) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            for key, value in self._cors_headers():
                self.send_header(key, value)
            if extra_headers:
                for key, value in extra_headers:
                    self.send_header(key, value)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _redirect(self, location: str, *, extra_headers: list[tuple[str, str]] | None = None) -> None:
            self.send_response(302)
            if extra_headers:
                for key, value in extra_headers:
                    self.send_header(key, value)
            self.send_header("Location", location)
            self.end_headers()

        def do_OPTIONS(self) -> None:  # noqa: N802
            self.send_response(204)
            for key, value in self._cors_headers():
                self.send_header(key, value)
            self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type,Authorization")
            self.send_header("Access-Control-Max-Age", "600")
            self.end_headers()

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path
            query = parse_qs(parsed.query)

            if path == "/auth/google/login":
                if not oauth_client.is_configured():
                    self._write_json(
                        {
                            "ok": False,
                            "message": (
                                "Google OAuth is not configured. Set GOOGLE_CLIENT_ID, "
                                "GOOGLE_CLIENT_SECRET, and GOOGLE_REDIRECT_URI."
                            ),
                        },
                        status=500,
                    )
                    return
                state = secrets.token_urlsafe(24)
                next_url = self._safe_next_url((query.get("next") or ["/"])[0])
                headers = [
                    ("Set-Cookie", self._cookie_header(self.OAUTH_STATE_COOKIE, state, max_age=600)),
                    (
                        "Set-Cookie",
                        self._cookie_header(self.OAUTH_NEXT_COOKIE, quote(next_url, safe=""), max_age=600),
                    ),
                ]
                self._redirect(oauth_client.build_authorize_url(state), extra_headers=headers)
                return

            if path == "/auth/google/callback":
                returned_state = str((query.get("state") or [""])[0]).strip()
                expected_state = self._get_cookie(self.OAUTH_STATE_COOKIE)
                code = str((query.get("code") or [""])[0]).strip()
                next_url = self._safe_next_url(unquote(self._get_cookie(self.OAUTH_NEXT_COOKIE)))
                if str((query.get("error") or [""])[0]).strip():
                    self._redirect(self._append_query(next_url, "auth_error", "oauth_denied"))
                    return
                if not returned_state or returned_state != expected_state:
                    self._redirect(self._append_query(next_url, "auth_error", "state_mismatch"))
                    return
                if not code:
                    self._redirect(self._append_query(next_url, "auth_error", "missing_code"))
                    return
                try:
                    id_token = oauth_client.exchange_code_for_id_token(code)
                    user = verifier.verify(id_token)
                except Exception:
                    self._redirect(self._append_query(next_url, "auth_error", "token_exchange_failed"))
                    return
                session_token = session_manager.issue(user)
                headers = [
                    (
                        "Set-Cookie",
                        self._cookie_header(self.SESSION_COOKIE, session_token, max_age=session_manager.max_age_seconds),
                    ),
                ]
                headers.extend(self._clear_cookie_headers(self.OAUTH_STATE_COOKIE))
                headers.extend(self._clear_cookie_headers(self.OAUTH_NEXT_COOKIE))
                self._redirect(next_url, extra_headers=headers)
                return

            if path == "/":
                payload: dict[str, object] = {
                    "ok": True,
                    "service": "notes-toolkit-backend",
                    "auth": {
                        "google_oauth_configured": oauth_client.is_configured(),
                        "session_cookie": self.SESSION_COOKIE,
                    },
                }
                if frontend_app_url:
                    payload["frontend_app_url"] = frontend_app_url
                self._write_json(payload)
                return

            if path.startswith("/project/"):
                target = frontend_app_url or "/"
                self._redirect(target)
                return

            if path == "/api/session":
                try:
                    user = self._auth()
                    self._write_json({"ok": True, "logged_in": True, "email": user.email, "user_id": user.user_id})
                except AuthError:
                    self._write_json({"ok": True, "logged_in": False, "email": ""})
                return

            if path == "/api/projects":
                try:
                    user = self._auth()
                except AuthError as exc:
                    self._write_json({"ok": False, "message": str(exc)}, status=401)
                    return
                self._write_json(
                    {
                        "projects": self._user_projects_summary(user.user_id),
                        "refreshed_at": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z"),
                    }
                )
                return

            if path.startswith("/api/project/") and path.endswith("/state"):
                project_name = unquote(path[len("/api/project/") : -len("/state")]).strip("/")
                if not project_name:
                    self._write_json({"ok": False, "message": "Project name is required."}, status=400)
                    return
                try:
                    user = self._auth()
                except AuthError as exc:
                    self._write_json({"ok": False, "message": str(exc)}, status=401)
                    return
                try:
                    state = self._user_project_state(user.user_id, project_name)
                except Exception as exc:
                    self._write_json({"ok": False, "message": str(exc)}, status=500)
                    return
                self._write_json(state)
                return

            self.send_response(404)
            self.end_headers()

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path

            if path == "/auth/logout":
                self._write_json(
                    {"ok": True},
                    extra_headers=(
                        self._clear_cookie_headers(self.SESSION_COOKIE)
                        + self._clear_cookie_headers(self.OAUTH_STATE_COOKIE)
                        + self._clear_cookie_headers(self.OAUTH_NEXT_COOKIE)
                    ),
                )
                return

            if path == "/api/init":
                try:
                    user = self._auth()
                except AuthError as exc:
                    self._write_json({"ok": False, "message": str(exc)}, status=401)
                    return
                length = int(self.headers.get("Content-Length", "0") or "0")
                raw = self.rfile.read(length) if length > 0 else b"{}"
                try:
                    payload = json.loads(raw.decode("utf-8")) if raw else {}
                except json.JSONDecodeError:
                    self._write_json({"ok": False, "message": "Invalid JSON payload."}, status=400)
                    return
                project_name = str(payload.get("project_name", "home")).strip() or "home"
                existing = self._user_projects_summary(user.user_id)
                initialized = len(existing) == 0
                scoped_project = scoped_project_name(user.user_id, project_name)
                project_paths(scoped_project, create=True)
                self._write_json(
                    {
                        "ok": True,
                        "initialized": initialized,
                        "project": project_name,
                        "state": self._user_project_state(user.user_id, project_name),
                    }
                )
                return

            if not (path.startswith("/api/project/") and path.endswith("/actions")):
                self.send_response(404)
                self.end_headers()
                return

            project_name = unquote(path[len("/api/project/") : -len("/actions")]).strip("/")
            if not project_name:
                self._write_json({"ok": False, "message": "Project name is required."}, status=400)
                return
            try:
                user = self._auth()
            except AuthError as exc:
                self._write_json({"ok": False, "message": str(exc)}, status=401)
                return

            length = int(self.headers.get("Content-Length", "0") or "0")
            raw = self.rfile.read(length) if length > 0 else b"{}"
            try:
                payload = json.loads(raw.decode("utf-8")) if raw else {}
            except json.JSONDecodeError:
                self._write_json({"ok": False, "message": "Invalid JSON payload."}, status=400)
                return

            action = str(payload.get("action", "")).strip()
            actor = str(payload.get("actor", "web")).strip() or "web"

            scoped_project = scoped_project_name(user.user_id, project_name)
            paths = project_paths(scoped_project)
            try:
                if action == "add_note":
                    result = add_note(paths, str(payload.get("text", "")), actor=actor)
                elif action == "add_todo":
                    result = add_todo(paths, str(payload.get("text", "")), actor=actor)
                elif action == "approve_potential":
                    result = approve_potential(paths, int(payload.get("id")), actor=actor)
                elif action == "reject_potential":
                    result = reject_potential(paths, int(payload.get("id")), actor=actor)
                elif action == "complete_todo":
                    result = complete_todo(paths, int(payload.get("id")), actor=actor)
                elif action == "mark_long_term_todo":
                    result = mark_todo_long_term(paths, int(payload.get("id")), actor=actor)
                elif action == "dismiss_note":
                    result = dismiss_note(paths, int(payload.get("id")), actor=actor)
                else:
                    self._write_json({"ok": False, "message": f"Unsupported action: {action}"}, status=400)
                    return
            except Exception as exc:
                self._write_json({"ok": False, "message": str(exc)}, status=500)
                return

            if not result.ok:
                self._write_json({"ok": False, "message": result.message}, status=400)
                return

            self._write_json(
                {
                    "ok": True,
                    "message": result.message,
                    "anchor": result.anchor,
                    "state": self._user_project_state(user.user_id, project_name),
                }
            )

        def log_message(self, fmt: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Notes dashboard running at http://{args.host}:{args.port}")
    if initial_project:
        print(f"Initial project: {initial_project}")
    else:
        print("Initial view: Home")
    print("Press Ctrl+C to stop.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nNotes dashboard stopped.")
    finally:
        stop_event.set()
        server.server_close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
