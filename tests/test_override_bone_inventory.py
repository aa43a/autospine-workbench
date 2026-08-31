"""Project bone-inventory guards for ordinary layer override persistence."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


WORKBENCH_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = WORKBENCH_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from autospine_workbench.contracts import ContractValidationError  # noqa: E402
from autospine_workbench.project_store import (  # noqa: E402
    ProjectStateError,
    RevisionConflictError,
)
from tests.test_project_store import StoreFixture  # noqa: E402


class OverrideBoneInventoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.fixture = StoreFixture(Path(self.temporary.name))
        self.store = self.fixture.store()
        project = self.store.get_project("fixture-project")
        self.layer_id = project["layers"][0]["id"]
        self.bone_id = "upper-arm.left"
        self.assertIn(
            self.bone_id,
            {row["id"] for row in project["skeleton"]["bones"]},
        )
        self.override_root = (
            self.fixture.state / "overrides" / "fixture-project"
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _payload(self, revision: int, bone_id: str) -> dict:
        return {
            "base_revision": revision,
            "joint_overrides": {},
            "layer_overrides": {
                self.layer_id: {"candidate_bone": bone_id},
            },
            "notes": "bone inventory guard",
        }

    def _persisted_bytes(self) -> dict[str, bytes]:
        if not self.override_root.exists():
            return {}
        return {
            path.relative_to(self.override_root).as_posix(): path.read_bytes()
            for path in self.override_root.rglob("*")
            if path.is_file()
        }

    def test_legal_project_bone_persists_and_round_trips(self) -> None:
        saved = self.store.save_overrides(
            "fixture-project", self._payload(0, self.bone_id)
        )

        self.assertEqual(1, saved["revision"])
        self.assertEqual(
            self.bone_id,
            saved["layer_overrides"][self.layer_id]["candidate_bone"],
        )
        reloaded = self.fixture.store().get_project("fixture-project")["overrides"]
        self.assertEqual(saved, reloaded)
        self.assertTrue(
            (self.override_root / "history" / "r000001.json").is_file()
        )

    def test_unknown_bone_is_rejected_before_revision_or_history_write(self) -> None:
        before = self._persisted_bytes()

        with self.assertRaises(ContractValidationError) as caught:
            self.store.save_overrides(
                "fixture-project", self._payload(0, "invented-bone")
            )

        self.assertEqual(before, self._persisted_bytes())
        self.assertIn(
            (f"$.layer_overrides.{self.layer_id}.candidate_bone", "unknown_id"),
            {(issue.path, issue.code) for issue in caught.exception.issues},
        )

    def test_unknown_bone_and_stale_cas_leave_existing_head_byte_exact(self) -> None:
        self.store.save_overrides(
            "fixture-project", self._payload(0, self.bone_id)
        )
        before = self._persisted_bytes()

        with self.assertRaises(ContractValidationError):
            self.store.save_overrides(
                "fixture-project", self._payload(1, "invented-bone")
            )
        self.assertEqual(before, self._persisted_bytes())

        with self.assertRaises(RevisionConflictError):
            self.store.save_overrides(
                "fixture-project", self._payload(0, self.bone_id)
            )
        self.assertEqual(before, self._persisted_bytes())

    def test_unknown_bone_in_persisted_history_fails_closed(self) -> None:
        self.store.save_overrides(
            "fixture-project", self._payload(0, self.bone_id)
        )
        for path in (
            self.override_root / "history" / "r000001.json",
            self.override_root / "latest.json",
        ):
            document = json.loads(path.read_text(encoding="utf-8"))
            document["layer_overrides"][self.layer_id][
                "candidate_bone"
            ] = "invented-bone"
            path.write_text(json.dumps(document), encoding="utf-8")

        with self.assertRaisesRegex(ProjectStateError, "unknown bone id"):
            self.fixture.store().get_project("fixture-project")


if __name__ == "__main__":
    unittest.main()
