# Notes Toolkit

A two-service Notes Toolkit:

- `apps/backend`: FastAPI backend (auth, session, project state, actions).
- `frontend`: Next.js App Router frontend (login + workspace UI).
- `packages/contracts`: shared action/API contracts (Python + web constants).

The data format is unchanged: files are still stored in the same vault layout.

## Architecture

- Frontend runtime: pure Next.js (`frontend/`), no static HTML template injection.
- Backend runtime: pure FastAPI (`notes_todo_dashboard.py` starts `apps.backend.main:create_app`).
- Auth: Google OAuth redirect + cookie session.
- Storage: local file repository in `NOTES_VAULT_ROOT`.

## Data layout

Default vault root: `~/Documents/notes_vault`

Per project:

- `active/NOTES.md`
- `archive/TODO_DONE.md`
- `archive/log.md`

Override vault root:

```bash
export NOTES_VAULT_ROOT="/your/path/notes_vault"
```

## Local development

### 1) Start backend

```bash
export GOOGLE_CLIENT_ID="<google-client-id>"
export GOOGLE_CLIENT_SECRET="<google-client-secret>"
export GOOGLE_REDIRECT_URI="http://127.0.0.1:8765/auth/google/callback"
export FRONTEND_ORIGIN="http://127.0.0.1:5500"
export FRONTEND_APP_URL="http://127.0.0.1:5500"
export COOKIE_SAMESITE="Lax"
export NOTES_VAULT_ROOT="$PWD/.notes_vault"

python3 -m pip install -r requirements.txt
python3 notes_todo_dashboard.py --host 127.0.0.1 --port 8765
```

### 2) Start frontend

```bash
cd frontend
npm install
BACKEND_BASE_URL="http://127.0.0.1:8765" PORT=5500 npm run dev
```

### 3) Open app

- Frontend: `http://127.0.0.1:5500`
- Backend health: `http://127.0.0.1:8765/health`

## Backend API summary

- `GET /health`
- `GET /api/session`
- `GET /api/projects`
- `POST /api/init`
- `GET /api/project/{project}/state`
- `POST /api/project/{project}/actions`
- `GET /auth/google/login`
- `GET /auth/google/callback`
- `POST /auth/logout`

## Actions

Action names are shared in `packages/contracts`:

- `add_note`
- `add_todo`
- `approve_potential`
- `reject_potential`
- `complete_todo`
- `mark_long_term_todo`
- `mark_short_term_todo`
- `dismiss_note`
- `edit_note`
- `edit_todo`
- `ai_suggest_edit_note`
- `ai_suggest_edit_todo`

## Render deployment

`render.yaml` defines two web services:

- `notes-dashboard` (backend Dockerfile at repo root)
- `notes-frontend-web` (frontend Dockerfile)

Required backend env vars:

- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `GOOGLE_REDIRECT_URI`
- `SESSION_SECRET`
- `FRONTEND_ORIGIN`
- `FRONTEND_APP_URL`

Recommended cookie settings for cross-site deployment:

- `COOKIE_SAMESITE=None`
- `COOKIE_SECURE=true`
