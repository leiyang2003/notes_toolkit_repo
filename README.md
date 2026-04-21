# Notes Toolkit

Single-service Notes Toolkit dashboard (frontend and backend in one app), with Google Sign-In and Render deployment support.

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

- Frontend is embedded in `notes_todo_dashboard.py` (not separated).
- User signs in with Google in the page.
- Frontend sends `Authorization: Bearer <google_id_token>` to API.
- Backend verifies Google token and scopes data by user:
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

## Local run

1) Start dashboard server:

```bash
export GOOGLE_CLIENT_ID="<your-google-oauth-client-id>"
python3 notes_todo_dashboard.py --host 127.0.0.1 --port 8765
```

2) Open:

`http://127.0.0.1:8765`

3) In UI:

- Enter `Google Client ID`
- Click `Init Google Sign-In`
- Sign in, then use dashboard as usual

## Render deployment (single service)

This repo includes:

- `Dockerfile`
- `scripts/run_server.sh`
- `render.yaml`

### Deploy via Blueprint

1. Push this branch to GitHub.
2. In Render: `New` -> `Blueprint` -> select this repository.
3. Render creates web service `notes-dashboard`.
4. In service env vars, set:
   - `GOOGLE_CLIENT_ID=<your-google-oauth-client-id>`
5. Ensure persistent disk is attached at `/data` (already in `render.yaml`).

### Required Google OAuth config

In Google Cloud Console (OAuth client):

- Add your Render app domain to **Authorized JavaScript origins**.

### Runtime env vars

- `PORT` (injected by Render)
- `HOST=0.0.0.0`
- `NOTES_VAULT_ROOT=/data/notes_vault`
- `PROCESS_INTERVAL=120`
- `GOOGLE_CLIENT_ID=<...>`

## Install command wrappers

```bash
./install.sh
```
