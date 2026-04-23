# Notes Toolkit

Split frontend/backend Notes Toolkit with Google OAuth redirect login and per-user local-file storage.

## Included

- Core logic:
  - `notes_app.py`
  - `notes_cli.py`
  - `notes_todo_dashboard.py`
  - `notes_todo_agent.py`
  - `notes_potential_todo_processor.py`
- Launchers:
  - `bin/notes`
  - `bin/notes-todo-dashboard`
  - `bin/notes-todo-watch`
  - `bin/notes-todo-process`

## Auth model

- Frontend is dynamic service: `frontend/app.py` (serves `frontend/index.html` with runtime config).
- Backend is API/Auth service: `notes_todo_dashboard.py`.
- Backend root behavior:
  - `GET /health` returns backend health JSON.
  - `GET /` redirects to `FRONTEND_APP_URL` when configured (otherwise returns health JSON).
- Login flow is server-side OAuth:
  - Frontend redirects to `/auth/google/login`.
  - Backend handles `/auth/google/callback`, then sets session cookie.
- Backend scopes data by user:
  - project folder = `u_<google_sub>__<project_name>`

## Data Layout

- Vault root (default): `~/Documents/notes_vault`
- Per scoped project files:
  - `active/NOTES.md`
  - `archive/TODO_DONE.md`
  - `archive/log.md`

Override vault root:

```bash
export NOTES_VAULT_ROOT="/your/path/notes_vault"
```

## Actionable 判定（GPT）

- `add note` 后，系统会在扫描 Potential To Do 时优先使用 GPT 判定该 note 是否是可执行待办。
- 需要配置：

```bash
export OPENAI_API_KEY="<your-openai-api-key>"
```

- 可选配置：
  - `NOTES_ACTIONABLE_MODEL`（默认 `gpt-4o-mini`）
  - `NOTES_ACTIONABLE_TIMEOUT_SEC`（默认 `8`）
  - `NOTES_ACTIONABLE_USE_LLM`（默认 `1`，可设 `0` 关闭并退回本地规则）
  - `OPENAI_RESPONSES_URL`（默认 `https://api.openai.com/v1/responses`）

## Local run (split)

1) Start backend:

```bash
export GOOGLE_CLIENT_ID="<your-google-oauth-client-id>"
export GOOGLE_CLIENT_SECRET="<your-google-oauth-client-secret>"
export GOOGLE_REDIRECT_URI="http://127.0.0.1:8765/auth/google/callback"
export FRONTEND_ORIGIN="http://127.0.0.1:5500"
export FRONTEND_APP_URL="http://127.0.0.1:5500"
export COOKIE_SAMESITE="Lax"
python3 notes_todo_dashboard.py --host 127.0.0.1 --port 8765
```

2) Start frontend dynamic server:

```bash
export BACKEND_BASE_URL="http://127.0.0.1:8765"
HOST=127.0.0.1 PORT=5500 python3 frontend/app.py
```

3) Open:

`http://127.0.0.1:5500`

4) In UI:

- Set backend URL to `http://127.0.0.1:8765`
- Click `Google Login (Redirect)`
- Complete Google authorization and return

## Render deployment (split frontend/backend)

### Backend service (this repo root)

Use existing `render.yaml` service `notes-dashboard`.

Required env vars:

- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `GOOGLE_REDIRECT_URI=https://<backend-domain>/auth/google/callback`
- `SESSION_SECRET=<random-long-string>`
- `FRONTEND_ORIGIN=https://<frontend-domain>`
- `FRONTEND_APP_URL=https://<frontend-domain>`
- `COOKIE_SAMESITE=None`（当前后端是不同域名时建议使用；同站点/同域可用 `Lax`）
- `COOKIE_SECURE=true`

Persistent disk:

- mount `/data` (already set)
- `NOTES_VAULT_ROOT=/data/notes_vault`

### Frontend service

Deploy `frontend/Dockerfile` as a separate Render web service.

Frontend env vars:

- `BACKEND_BASE_URL=https://<backend-domain>`

After deploy:

- Open frontend URL
- Login through Google redirect

### Required Google OAuth config

In Google Cloud Console (OAuth client):

- Add your callback URL to **Authorized redirect URIs**:
  - `https://<backend-domain>/auth/google/callback`
  - `GOOGLE_REDIRECT_URI` must exactly match one configured redirect URI.

## Install command wrappers

```bash
./install.sh
```
