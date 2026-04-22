import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CLI_PATH = REPO_ROOT / "notes_cli.py"


class NotesCliContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.workdir = Path(self._tmp.name)
        self.vault_root = self.workdir / "vault"
        self.vault_root.mkdir(parents=True, exist_ok=True)
        self.project = "cli_demo"

    def _run(self, *args: str, expect: int = 0) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["NOTES_VAULT_ROOT"] = str(self.vault_root)
        cp = subprocess.run(
            [sys.executable, str(CLI_PATH), *args],
            cwd=str(REPO_ROOT),
            env=env,
            text=True,
            capture_output=True,
        )
        self.assertEqual(cp.returncode, expect, msg=f"stdout={cp.stdout}\nstderr={cp.stderr}")
        return cp

    def test_view_and_note_todo_json_contract(self) -> None:
        note_add = self._run("--project", self.project, "--json", "note", "add", "--text", "Kickoff note")
        note_data = json.loads(note_add.stdout)
        self.assertTrue(note_data["ok"])

        todo_add = self._run("--project", self.project, "--json", "todo", "add", "--text", "Prepare checklist")
        todo_data = json.loads(todo_add.stdout)
        self.assertTrue(todo_data["ok"])

        view = self._run("--project", self.project, "--json", "view", "project")
        state = json.loads(view.stdout)
        self.assertEqual(state["project"], self.project)
        self.assertIn("todos", state)
        self.assertGreaterEqual(state["todo_count"], 1)

    def test_process_and_log_contract(self) -> None:
        self._run("--project", self.project, "note", "add", "--text", "Need to write migration")
        process = self._run("--project", self.project, "--json", "process")
        process_data = json.loads(process.stdout)
        self.assertIn("changed", process_data)
        self.assertIn("promoted_count", process_data)
        self.assertIn("added_count", process_data)

        logs = self._run("--project", self.project, "--json", "log", "show", "--limit", "5")
        rows = json.loads(logs.stdout)
        self.assertIsInstance(rows, list)
        self.assertGreaterEqual(len(rows), 1)
        self.assertIn("action", rows[-1])

    def test_natural_language_entrypoint(self) -> None:
        add_cmd = self._run("add todo ship build", "--project", self.project)
        self.assertIn("Todo added.", add_cmd.stdout)

        bad_cmd = self._run("what is this", "--project", self.project, expect=2)
        self.assertIn("Unsupported command", bad_cmd.stderr)


if __name__ == "__main__":
    unittest.main()
