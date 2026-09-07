"""Synthetic annotation workflows; no real human decisions or joint labels."""

from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from tests import test_benchmark_semantic_cli as fixture_module
from autospine_workbench.benchmark.annotation_cli import read_joint_draft, read_semantic_decision
from autospine_workbench.benchmark.artifacts import publish_report
from autospine_workbench.benchmark.semantic_draft import build_semantic_draft
from autospine_workbench.resolved_project import canonical_sha256


class AnnotationCliTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture_module.SemanticCliTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.candidate = self.fixture.load()[0]
        self.state = self.fixture.fixture.fixture.state
        for name, value in (("manifest", self.fixture.manifest), ("evidence", self.fixture.evidence),
                            ("candidate", self.candidate)):
            (self.root / (name + ".json")).write_text(json.dumps(value), encoding="utf-8")
        self.common = ["--manifest", self.root / "manifest.json", "--evidence", self.root / "evidence.json",
                       "--workspace", self.root, "--character", self.fixture.fixture.psd["path"]]

    def invoke(self, command, *args):
        return self.fixture.fixture.fixture.invoke(command, *self.common, *args)

    def test_joint_draft_initially_unmarked_then_restorable(self):
        code, draft = self.invoke("joint-review", "--html", self.root / "joints.html")
        self.assertEqual(code, 0)
        self.assertTrue(all(row["status"] == "unmarked" and row["position"] is None for row in draft["records"]))
        self.assertEqual(read_joint_draft(self.state, self.fixture.manifest, canonical_sha256(draft)), draft)
        draft["records"][0].update(status="observed", position=[50, 60])
        path = self.root / "joints.json"
        path.write_text(json.dumps(draft), encoding="utf-8")
        self.assertEqual(self.invoke("joint-review", "--draft", path, "--html", self.root / "edited.html"), (0, draft))

    def test_joint_wrong_source_fails_without_page(self):
        _, draft = self.invoke("joint-review", "--html", self.root / "joints.html")
        draft["candidate_sha256"] = "0" * 64
        path = self.root / "invalid.json"
        path.write_text(json.dumps(draft), encoding="utf-8")
        code, _ = self.invoke("joint-review", "--draft", path, "--html", self.root / "invalid.html")
        self.assertEqual(code, 1)
        self.assertFalse((self.root / "invalid.html").exists())

    def review_inputs(self):
        draft = build_semantic_draft(self.candidate)
        for row in draft["records"]:
            row.update(disposition="exclude", notes="TEST ONLY excluded synthetic fixture")
        draft["records"][0].update(disposition="include", semantic="hair.back", side="bilateral")
        request = {"schema": "autospine.benchmark-semantic-review-request/v1", "authority": "none",
                   "candidate_sha256": canonical_sha256(self.candidate), "draft_sha256": canonical_sha256(draft),
                   "reviewer": "TEST ONLY", "action": "accept", "reason": "Synthetic review mechanics only",
                   "checks": {"layer_identity": True, "semantics_checked": True, "sides_checked": True}}
        for name, value in (("draft", draft), ("request", request)):
            (self.root / (name + ".json")).write_text(json.dumps(value), encoding="utf-8")
        return draft, request, ["--candidate", self.root / "candidate.json", "--draft", self.root / "draft.json",
                                "--request", self.root / "request.json"]

    def test_explicit_semantic_acceptance_replays_and_cannot_be_rehashed_into_other_result(self):
        _, _, args = self.review_inputs()
        self.assertEqual(self.invoke("record-semantic-review", *args)[0], 1)
        self.assertFalse(self.state.exists())
        code, decision = self.invoke("record-semantic-review", *args, "--confirm-human-review")
        self.assertEqual(code, 0)
        self.assertEqual(read_semantic_decision(self.state, self.fixture.manifest, canonical_sha256(decision)), decision)
        forged = deepcopy(decision)
        forged["reviewer"] = "FORGED"
        digest = publish_report(self.state, self.fixture.manifest["dataset_id"], "semantic-decisions", forged)
        with self.assertRaises(ValueError):
            read_semantic_decision(self.state, self.fixture.manifest, digest)

    def test_semantic_changed_draft_or_source_is_not_accepted(self):
        draft, _, args = self.review_inputs()
        draft["records"][0]["semantic"] = "hair.front"
        (self.root / "draft.json").write_text(json.dumps(draft), encoding="utf-8")
        self.assertEqual(self.invoke("record-semantic-review", *args, "--confirm-human-review")[0], 1)
        self.assertFalse(self.state.exists())


if __name__ == "__main__":
    unittest.main()
