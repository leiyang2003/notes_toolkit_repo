# Notes Toolkit

Standalone notes/todo toolkit package extracted for a separate repository.

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
- Optional compatibility wrappers:
  - `legacy_scripts/todo_dashboard.py`
  - `legacy_scripts/todo_agent.py`
  - `legacy_scripts/potential_todo_processor.py`

## Data Layout

- Vault root (default): `~/Documents/notes_vault`
- Per project files:
  - `active/NOTES.md`
  - `archive/TODO_DONE.md`
  - `archive/log.md`

You can override vault root with:

```bash
export NOTES_VAULT_ROOT="/your/path/notes_vault"
```

## Install commands

```bash
cd notes_toolkit_repo
./install.sh
```

Default link target is `~/.local/bin`.

If needed, add this to your shell profile:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

## Quick usage

```bash
notes view home
notes view project
notes note add --text "example note"
notes todo add --text "example todo"
notes-todo-dashboard --port 8765
```

## Create a new GitHub repo from this folder

```bash
cd notes_toolkit_repo
git init
git add .
git commit -m "Initial import of notes toolkit"
git branch -M main
git remote add origin <your-repo-url>
git push -u origin main
```
