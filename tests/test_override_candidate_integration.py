"""End-to-end candidate decision, history, and resolved snapshot tests."""

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

from autospine_workbench.artifact_store import ImmutableJsonArtifactStore  # noqa: E402
from autospine_workbench.joint_candidates import AuditBBoxHeuristicProvider  # noqa: E402
from autospine_workbench.project_store import ProjectStateError  # noqa: E402
from tests.test_project_store import StoreFixture  # noqa: E402


class CandidateDecisionIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.fixture = StoreFixture(Path(self.directory.name))
        self.store = self.fixture.store()

    def tearDown(self) -> None:
        self.directory.cleanup()

    def _publish_candidates(self) -> tuple[dict, object]:
        document = AuditBBoxHeuristicProvider().analyze(self.store.get_project("fixture-project"))
        published = ImmutableJsonArtifactStore(self.fixture.state).publish(
            "joint-candidates", "fixture-project", document
        )
        return document, published

    def test_accept_is_derived_bound_and_reconstructable_from_history(self) -> None:
        document, published = self._publish_candidates()
        project = self.store.get_project("fixture-project")
        chosen_joint = "root"
        chosen = document["joints"][chosen_joint]["candidates"][0]
        manual = {
            joint["id"]: {"x": joint["x"], "y": joint["y"], "reason": "manual fixture"}
            for joint in project["skeleton"]["joints"]
            if joint["id"] != chosen_joint
        }
        saved = self.store.save_overrides(
            "fixture-project",
            {
                "schema_version": "autospine-workbench.override/v2",
                "base_revision": 0,
                "joint_overrides": manual,
                "joint_decisions": {
                    chosen_joint: {
                        "action": "accept",
                        "candidate_artifact_sha256": published.sha256,
                        "candidate_id": chosen["candidate_id"],
                    }
                },
                "layer_overrides": {},
                "notes": "candidate-bound review",
            },
        )

        bound = saved["joint_decisions"][chosen_joint]
        self.assertEqual(chosen["xy"], bound["final_xy"])
        self.assertEqual(document["analysis"]["provider"], bound["analysis"]["provider"])
        resolved = self.fixture.store().get_project("fixture-project")["resolved"]
        effective = {item["id"]: item for item in resolved["skeleton"]["joints"]}
        self.assertEqual("candidate_accepted", effective[chosen_joint]["review_state"])
        self.assertEqual([], resolved["qa"]["unresolved_joint_ids"])
        self.assertEqual(published.sha256, resolved["inputs"]["candidate_analyses"][0]["candidate_artifact_sha256"])

        history = self.fixture.state / "overrides" / "fixture-project" / "history" / "r000001.json"
        persisted = json.loads(history.read_text(encoding="utf-8"))
        self.assertEqual(bound, persisted["joint_decisions"][chosen_joint])
        self.assertEqual(resolved, self.fixture.store().get_project("fixture-project")["resolved"])

    def test_repointing_stored_accept_to_changed_artifact_fails_closed(self) -> None:
        document, published = self._publish_candidates()
        chosen_joint = "root"
        chosen = document["joints"][chosen_joint]["candidates"][0]
        self.store.save_overrides(
            "fixture-project",
            {
                "base_revision": 0,
                "joint_overrides": {},
                "joint_decisions": {
                    chosen_joint: {
                        "action": "accept",
                        "candidate_artifact_sha256": published.sha256,
                        "candidate_id": chosen["candidate_id"],
                    }
                },
                "layer_overrides": {},
                "notes": "first algorithm output",
            },
        )
        changed = deepcopy(document)
        changed["joints"][chosen_joint]["candidates"][0]["xy"][0] += 1
        changed_artifact = ImmutableJsonArtifactStore(self.fixture.state).publish(
            "joint-candidates", "fixture-project", changed
        )
        self.assertNotEqual(published.sha256, changed_artifact.sha256)

        latest = self.fixture.state / "overrides" / "fixture-project" / "latest.json"
        stored = json.loads(latest.read_text(encoding="utf-8"))
        stored["joint_decisions"][chosen_joint]["candidate_artifact_sha256"] = changed_artifact.sha256
        latest.write_text(json.dumps(stored), encoding="utf-8")
        with self.assertRaises(ProjectStateError):
            self.fixture.store().get_project("fixture-project")


if __name__ == "__main__":
    unittest.main()
