"""Candidate decision evidence-binding tests."""

from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from autospine_workbench.artifact_store import ImmutableJsonArtifactStore  # noqa: E402
from autospine_workbench.candidate_decisions import (  # noqa: E402
    CandidateDecisionBinder,
    CandidateDecisionError,
)
from autospine_workbench.joint_candidates import AuditBBoxHeuristicProvider  # noqa: E402
from tests.test_joint_candidates import project_fixture  # noqa: E402


class CandidateDecisionBinderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.state_root = Path(self.temporary.name)
        self.document = AuditBBoxHeuristicProvider().analyze(project_fixture())
        self.published = ImmutableJsonArtifactStore(self.state_root).publish(
            "joint-candidates", "sample-a", self.document
        )
        self.binder = CandidateDecisionBinder(self.state_root)
        self.options = {
            "joint_ids": {"elbow.left", "wrist.left"},
            "layer_ids": set(),
            "canvas_width": 100,
            "canvas_height": 200,
        }
        self.elbow_id = self.document["joints"]["elbow.left"]["candidates"][0]["candidate_id"]
        self.wrist_id = self.document["joints"]["wrist.left"]["candidates"][0]["candidate_id"]

    def decision(self, **changes) -> dict:
        item = {
            "action": "accept",
            "candidate_artifact_sha256": self.published.sha256,
            "candidate_id": self.elbow_id,
        }
        item.update(changes)
        return {"elbow.left": item}

    def assert_error(self, code: str, decisions: dict) -> CandidateDecisionError:
        with self.assertRaises(CandidateDecisionError) as raised:
            self.binder.bind("sample-a", decisions, **self.options)
        self.assertEqual(code, raised.exception.issues[0].code)
        self.assertEqual(code, raised.exception.as_validation_issues()[0].code)
        return raised.exception

    def test_accept_derives_coordinate_and_provenance_from_artifact(self) -> None:
        bound = self.binder.bind("sample-a", self.decision(), **self.options)
        item = bound["elbow.left"]
        self.assertEqual([20.0, 30.0], item["final_xy"])
        self.assertEqual(self.document["analysis"]["provider"], item["analysis"]["provider"])
        self.assertEqual(
            self.document["source"]["base_project_sha256"], item["analysis"]["input_sha256"]
        )
        self.assert_error("derived_field", self.decision(final_xy=[90, 90]))
        reasoned = self.binder.bind("sample-a", self.decision(reason="looks correct"), **self.options)
        self.assertEqual("looks correct", reasoned["elbow.left"]["reason"])

    def test_actions_have_canonical_distinct_shapes_and_sorted_keys(self) -> None:
        decisions = {
            "wrist.left": {
                "action": "unobservable",
                "candidate_artifact_sha256": self.published.sha256,
                "reason": "hidden by sleeve",
            },
            "elbow.left": {
                "action": "adjust",
                "candidate_artifact_sha256": self.published.sha256,
                "candidate_id": self.elbow_id,
                "final_xy": [22, 31],
                "reason": "reviewed pivot",
            },
        }
        bound = self.binder.bind("sample-a", decisions, **self.options)
        self.assertEqual(["elbow.left", "wrist.left"], list(bound))
        self.assertEqual([22.0, 31.0], bound["elbow.left"]["final_xy"])
        self.assertNotIn("candidate_id", bound["wrist.left"])
        self.assertNotIn("final_xy", bound["wrist.left"])
        decisions["elbow.left"]["final_xy"] = [101, 31]
        with self.assertRaises(CandidateDecisionError) as raised:
            self.binder.bind("sample-a", decisions, **self.options)
        self.assertEqual("bounds", raised.exception.issues[0].code)

    def test_missing_and_tampered_artifacts_fail_closed(self) -> None:
        self.assert_error(
            "artifact_missing",
            self.decision(candidate_artifact_sha256="f" * 64),
        )
        original = self.published.path.read_text(encoding="utf-8")
        self.published.path.write_text(
            original.replace("{", '{"format":"autospine-joint-candidates",', 1),
            encoding="utf-8",
        )
        self.assert_error("duplicate_key", self.decision())
        self.published.path.write_text(original, encoding="utf-8")
        changed = copy.deepcopy(self.document)
        changed["joints"]["elbow.left"]["candidates"][0]["xy"] = [21, 30]
        self.published.path.write_text(
            json.dumps(changed, ensure_ascii=False, sort_keys=True), encoding="utf-8"
        )
        self.assert_error("content_address_mismatch", self.decision())

    def test_wrong_project_and_wrong_joint_are_rejected(self) -> None:
        wrong_project = copy.deepcopy(self.document)
        wrong_project["project_id"] = "sample-b"
        published = ImmutableJsonArtifactStore(self.state_root).publish(
            "joint-candidates", "sample-a", wrong_project
        )
        self.assert_error(
            "wrong_project",
            self.decision(candidate_artifact_sha256=published.sha256),
        )
        self.assert_error("wrong_joint", self.decision(candidate_id=self.wrist_id))

    def test_changed_candidate_with_same_run_and_id_invalidates_stored_accept(self) -> None:
        stored = self.binder.bind("sample-a", self.decision(), **self.options)
        changed = copy.deepcopy(self.document)
        changed["joints"]["elbow.left"]["candidates"][0]["xy"] = [24, 35]
        published = ImmutableJsonArtifactStore(self.state_root).publish(
            "joint-candidates", "sample-a", changed
        )
        stored["elbow.left"]["candidate_artifact_sha256"] = published.sha256
        with self.assertRaises(CandidateDecisionError) as raised:
            self.binder.bind("sample-a", stored, stored=True, **self.options)
        self.assertEqual("derived_mismatch", raised.exception.issues[0].code)

    def test_stored_provenance_must_match_artifact(self) -> None:
        stored = self.binder.bind("sample-a", self.decision(), **self.options)
        stored["elbow.left"]["analysis"]["provider"] = "substituted"
        with self.assertRaises(CandidateDecisionError) as raised:
            self.binder.bind("sample-a", stored, stored=True, **self.options)
        self.assertEqual("provenance_mismatch", raised.exception.issues[0].code)


if __name__ == "__main__":
    unittest.main()
