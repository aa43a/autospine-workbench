"""Fault injection for authoritative override history commit semantics."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (ROOT, SRC):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from autospine_workbench.override_files import OverrideFileError  # noqa: E402
from autospine_workbench.project_errors import RevisionConflictError  # noqa: E402
from tests.test_project_store import StoreFixture  # noqa: E402


class OverrideCommitRecoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.fixture = StoreFixture(Path(self.temporary.name))
        self.store = self.fixture.store()
        self.files = self.store._override_store._files

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def _request(note: str) -> dict:
        return {
            "base_revision": 0,
            "joint_overrides": {},
            "layer_overrides": {},
            "notes": note,
        }

    def test_first_latest_failure_repairs_from_published_history(self) -> None:
        original = self.files.write_latest
        calls = 0

        def fail_once(destination, document):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise OverrideFileError("injected first latest failure")
            return original(destination, document)

        with patch.object(self.files, "write_latest", side_effect=fail_once):
            saved = self.store.save_overrides(
                "fixture-project", self._request("repair succeeds"),
            )

        project_dir = self.fixture.state / "overrides" / "fixture-project"
        latest = json.loads((project_dir / "latest.json").read_text("utf-8"))
        self.assertEqual(2, calls)
        self.assertEqual(1, saved["revision"])
        self.assertEqual(saved, latest)

    def test_double_latest_failure_returns_definite_committed_revision(self) -> None:
        with patch.object(
            self.files,
            "write_latest",
            side_effect=OverrideFileError("injected persistent latest failure"),
        ) as write_latest:
            saved = self.store.save_overrides(
                "fixture-project", self._request("history is authoritative"),
            )

        project_dir = self.fixture.state / "overrides" / "fixture-project"
        self.assertEqual(2, write_latest.call_count)
        self.assertEqual(1, saved["revision"])
        self.assertFalse((project_dir / "latest.json").exists())
        self.assertTrue((project_dir / "history" / "r000001.json").is_file())
        reloaded = self.fixture.store().get_project("fixture-project")["overrides"]
        self.assertEqual(saved, reloaded)
        with self.assertRaises(RevisionConflictError):
            self.fixture.store().save_overrides(
                "fixture-project", self._request("stale retry"),
            )


if __name__ == "__main__":
    unittest.main()
