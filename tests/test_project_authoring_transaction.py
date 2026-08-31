"""Concurrency tests for project-level authoring serialization."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import threading
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.project_authoring_transaction import (  # noqa: E402
    project_authoring_transaction,
)


class ProjectAuthoringTransactionTests(unittest.TestCase):
    def test_same_project_waits_until_the_current_transaction_finishes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            started = threading.Event()
            entered = threading.Event()

            def worker():
                started.set()
                with project_authoring_transaction(root, "sample"):
                    entered.set()

            with project_authoring_transaction(root, "sample"):
                thread = threading.Thread(target=worker)
                thread.start()
                self.assertTrue(started.wait(timeout=2))
                self.assertFalse(entered.wait(timeout=0.05))
            self.assertTrue(entered.wait(timeout=2))
            thread.join(timeout=2)
            self.assertFalse(thread.is_alive())

    def test_different_projects_do_not_share_a_lock(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            entered = threading.Event()

            def worker():
                with project_authoring_transaction(root, "sample-b"):
                    entered.set()

            with project_authoring_transaction(root, "sample-a"):
                thread = threading.Thread(target=worker)
                thread.start()
                self.assertTrue(entered.wait(timeout=2))
            thread.join(timeout=2)
            self.assertFalse(thread.is_alive())


if __name__ == "__main__":
    unittest.main()
