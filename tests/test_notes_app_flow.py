import os
import tempfile
import unittest
from pathlib import Path

from notes_app import (
    add_note,
    add_todo,
    approve_potential,
    complete_todo,
    edit_note,
    edit_todo,
    mark_todo_long_term,
    process_potential_todos,
    project_paths,
    project_state,
    reject_potential,
    restore_log_entry,
)


class NotesAppFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._old_cwd = os.getcwd()
        self.addCleanup(lambda: os.chdir(self._old_cwd))

        self.workdir = Path(self._tmp.name)
        self.vault_root = self.workdir / "vault"
        self.vault_root.mkdir(parents=True, exist_ok=True)
        os.environ["NOTES_VAULT_ROOT"] = str(self.vault_root)

        self.project_dir = self.workdir / "sandbox_project"
        self.project_dir.mkdir(parents=True, exist_ok=True)
        os.chdir(self.project_dir)

        self.paths = project_paths("demo")

    def test_todo_complete_and_restore_round_trip(self) -> None:
        add_result = add_todo(self.paths, "Write contract tests", actor="tester")
        self.assertTrue(add_result.ok)

        state_after_add = project_state(self.paths)
        self.assertEqual(state_after_add["todo_count"], 1)

        done_result = complete_todo(self.paths, 1, actor="tester")
        self.assertTrue(done_result.ok)
        state_after_done = project_state(self.paths)
        self.assertEqual(state_after_done["todo_count"], 0)
        self.assertGreaterEqual(len(state_after_done["done"]), 1)

        complete_entry = next((row for row in reversed(state_after_done["logs"]) if row["action"] == "complete_todo"), None)
        self.assertIsNotNone(complete_entry)

        restore_result = restore_log_entry(self.paths, complete_entry["id"], actor="tester")
        self.assertTrue(restore_result.ok)

        state_after_restore = project_state(self.paths)
        self.assertEqual(state_after_restore["todo_count"], 1)

    def test_potential_approve_and_reject_flow(self) -> None:
        note_one = add_note(self.paths, "Need to call supplier", actor="tester")
        self.assertTrue(note_one.ok)

        processed = process_potential_todos(self.paths, actor="tester", log_writes=True)
        self.assertIn(processed.changed, {True, False})

        state_one = project_state(self.paths)
        self.assertGreaterEqual(state_one["potential_pending_count"], 1)

        approve = approve_potential(self.paths, 1, actor="tester")
        self.assertTrue(approve.ok)

        state_two = project_state(self.paths)
        self.assertGreaterEqual(state_two["todo_count"], 1)

        note_two = add_note(self.paths, "Need to send follow-up email", actor="tester")
        self.assertTrue(note_two.ok)
        process_potential_todos(self.paths, actor="tester", log_writes=True)

        state_three = project_state(self.paths)
        pending_items = [item for item in state_three["potentials"] if item["status"] == "pending"]
        self.assertGreaterEqual(len(pending_items), 1)

        reject = reject_potential(self.paths, 1, actor="tester")
        self.assertTrue(reject.ok)

        state_four = project_state(self.paths)
        statuses = {item["status"] for item in state_four["potentials"]}
        self.assertIn("rejected", statuses)

    def test_mark_long_term_does_not_recreate_pending_potential(self) -> None:
        note = add_note(self.paths, "Need to call supplier", actor="tester")
        self.assertTrue(note.ok)

        approve = approve_potential(self.paths, 1, actor="tester")
        self.assertTrue(approve.ok)

        state_before = project_state(self.paths)
        pending_before = len([item for item in state_before["potentials"] if item["status"] == "pending"])
        promoted_before = len([item for item in state_before["potentials"] if item["status"] == "promoted"])
        self.assertGreaterEqual(promoted_before, 1)

        mark = mark_todo_long_term(self.paths, 1, actor="tester")
        self.assertTrue(mark.ok)

        state_after = project_state(self.paths)
        pending_after = len([item for item in state_after["potentials"] if item["status"] == "pending"])
        promoted_after = len([item for item in state_after["potentials"] if item["status"] == "promoted"])
        self.assertEqual(pending_after, pending_before)
        self.assertGreaterEqual(promoted_after, promoted_before)

    def test_edit_note_and_todo_persist_changes(self) -> None:
        note = add_note(self.paths, "Need to call supplier", actor="tester")
        self.assertTrue(note.ok)
        state_with_note = project_state(self.paths)
        note_target = next((item for item in state_with_note["notes"] if "Need to call supplier" in item["text"]), None)
        self.assertIsNotNone(note_target)

        note_edit = edit_note(self.paths, int(note_target["id"]), "Need to call supplier tomorrow", actor="tester")
        self.assertTrue(note_edit.ok)
        state_after_note_edit = project_state(self.paths)
        self.assertTrue(any("Need to call supplier tomorrow" in item["text"] for item in state_after_note_edit["notes"]))

        todo = add_todo(self.paths, "Need to draft roadmap", actor="tester")
        self.assertTrue(todo.ok)
        marked = mark_todo_long_term(self.paths, 1, actor="tester")
        self.assertTrue(marked.ok)

        todo_edit = edit_todo(self.paths, 1, "Draft roadmap v2", actor="tester")
        self.assertTrue(todo_edit.ok)
        state_after_todo_edit = project_state(self.paths)
        self.assertTrue(any("[LT]" in item["text"] and "Draft roadmap v2" in item["text"] for item in state_after_todo_edit["todos"]))


if __name__ == "__main__":
    unittest.main()
