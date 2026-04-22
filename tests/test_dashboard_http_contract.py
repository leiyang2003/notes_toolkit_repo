import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


REPO_ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = REPO_ROOT / "notes_todo_dashboard.py"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class DashboardHttpContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.workdir = Path(self._tmp.name)
        self.vault_root = self.workdir / "vault"
        self.vault_root.mkdir(parents=True, exist_ok=True)

        try:
            self.port = _free_port()
        except PermissionError as exc:
            self.skipTest(f"Socket bind not permitted in current environment: {exc}")
        env = os.environ.copy()
        env["NOTES_VAULT_ROOT"] = str(self.vault_root)
        env["ALLOW_INSECURE_GOOGLE"] = "1"
        env.pop("GOOGLE_CLIENT_ID", None)
        env.pop("GOOGLE_CLIENT_SECRET", None)
        env.pop("GOOGLE_REDIRECT_URI", None)

        self.proc = subprocess.Popen(
            [
                sys.executable,
                str(SERVER_PATH),
                "--host",
                "127.0.0.1",
                "--port",
                str(self.port),
                "--process-interval",
                "3600",
            ],
            cwd=str(REPO_ROOT),
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        self.addCleanup(self._stop_proc)
        self._wait_until_ready()

    def _stop_proc(self) -> None:
        if self.proc.poll() is not None:
            return
        self.proc.terminate()
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()

    def _base(self, path: str) -> str:
        return f"http://127.0.0.1:{self.port}{path}"

    def _wait_until_ready(self) -> None:
        deadline = time.time() + 15
        while time.time() < deadline:
            try:
                with urlopen(self._base("/"), timeout=1.5) as resp:
                    if resp.status == 200:
                        return
            except Exception:
                time.sleep(0.2)
        raise AssertionError("Server failed to start within timeout.")

    def _json_get(self, path: str) -> tuple[int, dict]:
        req = Request(self._base(path), method="GET")
        try:
            with urlopen(req, timeout=5) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except HTTPError as exc:
            body = exc.read().decode("utf-8")
            data = json.loads(body) if body else {}
            return exc.code, data

    def _json_post(self, path: str, payload: object, raw: bool = False) -> tuple[int, dict]:
        if raw:
            data = payload
        else:
            data = json.dumps(payload).encode("utf-8")
        req = Request(
            self._base(path),
            method="POST",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urlopen(req, timeout=5) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except HTTPError as exc:
            body = exc.read().decode("utf-8")
            return exc.code, (json.loads(body) if body else {})

    def test_health_and_session_contract(self) -> None:
        code, health = self._json_get("/")
        self.assertEqual(code, 200)
        self.assertTrue(health["ok"])
        self.assertEqual(health["service"], "notes-toolkit-backend")
        self.assertIn("auth", health)

        code, session = self._json_get("/api/session")
        self.assertEqual(code, 200)
        self.assertTrue(session["ok"])
        self.assertFalse(session["logged_in"])

    def test_unauthorized_api_contract(self) -> None:
        code, projects = self._json_get("/api/projects")
        self.assertEqual(code, 401)
        self.assertFalse(projects["ok"])
        self.assertIn("message", projects)

        code, init = self._json_post("/api/init", {"project_name": "home"})
        self.assertEqual(code, 401)
        self.assertFalse(init["ok"])

        code, action = self._json_post("/api/project/demo/actions", {"action": "add_note", "text": "x"})
        self.assertEqual(code, 401)
        self.assertFalse(action["ok"])

    def test_google_login_without_oauth_config(self) -> None:
        code, body = self._json_get("/auth/google/login")
        self.assertEqual(code, 500)
        self.assertFalse(body["ok"])
        self.assertIn("Google OAuth is not configured", body["message"])


if __name__ == "__main__":
    unittest.main()
