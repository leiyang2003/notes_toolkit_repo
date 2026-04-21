# Notes Toolkit (Render Deployment Version)

This repository is now simplified to:

- Backend API: Python (`notes_todo_dashboard.py`)
- Frontend: static HTML (`frontend/index.html`) with UI/interaction kept close to previous dashboard
- Storage: file-based notes in persistent disk/volume
- Auth: Google Sign-In ID token (one Google `sub` = one notes directory)

## Architecture

- Frontend and backend are separated.
- Backend validates Google ID token via Google tokeninfo API.
- User data is isolated by directory:
  - `u_<google_sub>__<project_name>`
- Notes are directly edited in files:
  - `active/NOTES.md`
  - `archive/TODO_DONE.md`
  - `archive/log.md`

## Backend API

All API endpoints require:

- `Authorization: Bearer <google_id_token>`

Endpoints:

- `GET /health`
- `GET /api/projects`
- `GET /api/project/{project}/state`
- `POST /api/project/{project}/actions`
- `GET /v1/projects`
- `GET /v1/projects/{project}/state`
- `POST /v1/projects/{project}/actions`

Supported actions in `POST /actions` JSON body:

- `{"action":"add_note","text":"..."}`
- `{"action":"add_todo","text":"..."}`
- `{"action":"complete_todo","id":1}`
- `{"action":"approve_potential","id":1}`
- `{"action":"reject_potential","id":1}`
- `{"action":"mark_long_term_todo","id":1}`
- `{"action":"dismiss_note","id":1}`

## Local Run

```bash
export GOOGLE_CLIENT_ID="<your-google-oauth-client-id>"
export CORS_ALLOW_ORIGINS="http://localhost:3000"
export NOTES_VAULT_ROOT="$HOME/Documents/notes_vault"
python3 notes_todo_dashboard.py --host 0.0.0.0 --port 8765
```

Open frontend:

```bash
python3 -m http.server 3000 --directory frontend
```

Then visit `http://localhost:3000`.

The frontend keeps the original dashboard layout and interactions, but now:

- It is served as a separate static site.
- It includes a Google Sign-In entry.
- It sends Bearer token to backend API.

## Render One-Click Deployment

This repo includes [`render.yaml`](/Users/chenyifei/Documents/GitHub/notes_toolkit_repo/render.yaml) with:

- `notes-backend` (Docker web service)
- `notes-frontend` (static site)
- persistent disk mounted to `/data`

### Steps

1. Push this branch to GitHub.
2. In Render: `New` -> `Blueprint` -> select this repo.
3. Render creates both services from `render.yaml`.
4. In backend service, set env var:
   - `GOOGLE_CLIENT_ID=<your-google-oauth-client-id>`
5. Update backend `CORS_ALLOW_ORIGINS` to your frontend Render domain.
6. In Google Cloud Console:
   - Configure OAuth client
   - Add frontend Render domain to authorized JavaScript origins

### Data Persistence

`NOTES_VAULT_ROOT` defaults to `/data/notes_vault` in container.
Because `/data` is a Render persistent disk, notes survive restarts/deploys.

## Docker

Backend Docker image uses:

- [`Dockerfile`](/Users/chenyifei/Documents/GitHub/notes_toolkit_repo/Dockerfile)
- [`scripts/run_server.sh`](/Users/chenyifei/Documents/GitHub/notes_toolkit_repo/scripts/run_server.sh)

Run locally:

```bash
docker build -t notes-api .
docker run --rm -p 8080:8080 \
  -e GOOGLE_CLIENT_ID="<your-client-id>" \
  -e CORS_ALLOW_ORIGINS="http://localhost:3000" \
  -v "$(pwd)/.data:/data" \
  notes-api
```
