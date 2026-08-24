"""Candidate-set baseline and contract tests."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest


WORKBENCH_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = WORKBENCH_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from autospine_workbench.joint_candidates import AuditBBoxHeuristicProvider  # noqa: E402
from autospine_workbench.artifact_store import (  # noqa: E402
    ArtifactStoreError,
    ImmutableJsonArtifactStore,
)

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover
    Draft202012Validator = None


def project_fixture() -> dict:
    return {
        "id": "sample-a",
        "source": {"sha256": "a" * 64},
        "canvas": {"width": 100, "height": 200},
        "skeleton": {
            "generation": {"method": "audit-bbox-heuristic-v1"},
            "joints": [
                {"id": "elbow.left", "x": 20, "y": 30, "confidence": 0.25, "source": "derived"},
                {"id": "wrist.left", "x": 10, "y": 40, "confidence": 0.8, "source": "layer"},
            ],
        },
    }


class JointCandidateProviderTests(unittest.TestCase):
    def test_baseline_provider_is_deterministic_and_labels_scores_honestly(self) -> None:
        provider = AuditBBoxHeuristicProvider()
        first = provider.analyze(project_fixture())
        second = provider.analyze(project_fixture())
        self.assertEqual(first, second)
        elbow = first["joints"]["elbow.left"]
        self.assertEqual("ambiguous", elbow["observability"])
        self.assertEqual("heuristic", elbow["candidates"][0]["score_kind"])
        self.assertNotIn("confidence", elbow["candidates"][0])
        self.assertEqual("visible", first["joints"]["wrist.left"]["observability"])
        self.assertEqual("manual_required", first["qa"]["status"])

    def test_provider_change_or_input_change_changes_run_identity(self) -> None:
        project = project_fixture()
        baseline = AuditBBoxHeuristicProvider().analyze(project)
        configured = AuditBBoxHeuristicProvider(visible_threshold=0.7).analyze(project)
        project["skeleton"]["joints"][0]["x"] = 21
        changed_input = AuditBBoxHeuristicProvider().analyze(project)
        self.assertNotEqual(baseline["analysis"]["run_sha256"], configured["analysis"]["run_sha256"])
        self.assertNotEqual(baseline["analysis"]["run_sha256"], changed_input["analysis"]["run_sha256"])

    @unittest.skipIf(Draft202012Validator is None, "install the 'test' extra for JSON Schema checks")
    def test_generated_candidate_set_validates_against_schema(self) -> None:
        schema_path = WORKBENCH_ROOT / "schemas" / "joint-candidates-v1.schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(AuditBBoxHeuristicProvider().analyze(project_fixture()))

    def test_analysis_artifacts_are_content_addressed_and_idempotent(self) -> None:
        document = AuditBBoxHeuristicProvider().analyze(project_fixture())
        with tempfile.TemporaryDirectory() as directory:
            store = ImmutableJsonArtifactStore(Path(directory))
            first = store.publish("joint-candidates", "sample-a", document)
            first_bytes = first.path.read_bytes()
            second = store.publish("joint-candidates", "sample-a", document)
            self.assertEqual(first, second)
            self.assertEqual(first_bytes, second.path.read_bytes())
            self.assertEqual(first.sha256, first.path.stem)

    def test_artifact_store_rejects_path_tokens(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = ImmutableJsonArtifactStore(Path(directory))
            with self.assertRaises(ArtifactStoreError):
                store.publish("../outside", "sample-a", {"safe": True})


if __name__ == "__main__":
    unittest.main()
