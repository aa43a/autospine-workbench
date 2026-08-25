"""Analysis artifact read-boundary tests."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.analysis_repository import (  # noqa: E402
    AnalysisArtifactNotFound,
    AnalysisArtifactRepository,
    AnalysisRepositoryError,
)
from autospine_workbench.artifact_store import ImmutableJsonArtifactStore  # noqa: E402
from autospine_workbench.joint_candidates import AuditBBoxHeuristicProvider  # noqa: E402
from tests.test_joint_candidates import project_fixture  # noqa: E402


class AnalysisArtifactRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.state = Path(self.directory.name)
        self.repository = AnalysisArtifactRepository(self.state)
        self.document = AuditBBoxHeuristicProvider().analyze(project_fixture())
        self.published = ImmutableJsonArtifactStore(self.state).publish(
            "joint-candidates", "sample-a", self.document
        )
        self.context = {
            "joint_ids": {"elbow.left", "wrist.left"},
            "layer_ids": set(),
            "canvas_width": 100,
            "canvas_height": 200,
        }

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_list_and_read_return_only_valid_content_addressed_candidates(self) -> None:
        index = self.repository.list_joint_candidates("sample-a", **self.context)
        self.assertEqual(1, index["count"])
        item = index["items"][0]
        self.assertEqual(self.published.sha256, item["artifact_sha256"])
        self.assertEqual({"audit_bbox_heuristic": 2}, item["method_counts"])
        self.assertEqual(
            self.document,
            self.repository.read_joint_candidates(
                "sample-a", self.published.sha256, **self.context
            ),
        )

    def test_unknown_digest_and_project_are_not_found(self) -> None:
        with self.assertRaises(AnalysisArtifactNotFound):
            self.repository.read_joint_candidates("sample-a", "0" * 64, **self.context)
        with self.assertRaises(AnalysisArtifactNotFound):
            self.repository.read_json("../sample-a", "joint-candidates", self.published.sha256)

    def test_tampering_duplicate_keys_and_wrong_project_fail_closed(self) -> None:
        path = self.published.path
        changed = deepcopy(self.document)
        changed["project_id"] = "other-project"
        path.write_text(json.dumps(changed), encoding="utf-8")
        with self.assertRaises(AnalysisRepositoryError):
            self.repository.read_joint_candidates("sample-a", self.published.sha256, **self.context)

        path.write_text('{"project_id":"sample-a","project_id":"sample-a"}', encoding="utf-8")
        with self.assertRaises(AnalysisRepositoryError):
            self.repository.read_json("sample-a", "joint-candidates", self.published.sha256)

    def test_candidate_index_rejects_unmanaged_json_entries(self) -> None:
        unmanaged = self.published.path.parent / "draft.json"
        unmanaged.write_text("{}", encoding="utf-8")

        with self.assertRaises(AnalysisRepositoryError):
            self.repository.list_joint_candidates("sample-a", **self.context)


if __name__ == "__main__":
    unittest.main()
