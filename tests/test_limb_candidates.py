"""Pose + alpha limb candidate provider tests."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from autospine_workbench.limb_candidates import (  # noqa: E402
    LimbCandidateError,
    PoseAlphaLimbProvider,
)
from autospine_workbench.pose_observations import (  # noqa: E402
    PoseJointObservation,
    PoseObservationSet,
)
from tests.png_helpers import write_rgba  # noqa: E402

try:
    from jsonschema import Draft202012Validator
    import json
except ImportError:  # pragma: no cover
    Draft202012Validator = None


TRANSPARENT = (0, 0, 0, 0)
VISIBLE = (80, 90, 100, 255)


def project_fixture() -> dict:
    layers = [
        {
            "id": "layer-arm-left",
            "canonical_role": "body.hand",
            "side": "left",
            "disposition": "keep",
            "empty": False,
            "bbox": {"x": 10, "y": 20, "width": 20, "height": 20},
        }
    ]
    return {
        "id": "sample-a",
        "source": {"sha256": "a" * 64, "audit_sha256": "b" * 64},
        "canvas": {"width": 100, "height": 100},
        "layers": layers,
        "resolved": {
            "revision": 2,
            "sha256": "c" * 64,
            "layers": layers,
        },
        "skeleton": {
            "joints": [
                {"id": "root", "x": 50, "y": 90, "confidence": 0.8, "source": "derived"},
                {"id": "elbow.left", "x": 20, "y": 25, "confidence": 0.3, "source": "derived"},
                {"id": "wrist.left", "x": 16, "y": 30, "confidence": 0.4, "source": "layer"},
            ]
        },
    }


def observations(*, include_wrist: bool = False) -> PoseObservationSet:
    joints = {
        "elbow.left": PoseJointObservation(8.0, 25.0, 0.8, "visible"),
    }
    if include_wrist:
        joints["wrist.left"] = PoseJointObservation(16.0, 30.0, 0.7, "visible")
    return PoseObservationSet(
        project_id="sample-a",
        image_sha256="d" * 64,
        canvas_size=(100, 100),
        detector_id="fixture-pose",
        detector_version="1",
        model_revision="fixture-revision",
        config_sha256="e" * 64,
        runtime="fixture-runtime",
        detected_count=1,
        selected_index=0,
        selection_method="single",
        joints=joints,
        document_sha256="f" * 64,
    )


class PoseAlphaLimbProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.asset = Path(self.directory.name) / "arm.png"
        rows = [[TRANSPARENT for _ in range(20)] for _ in range(20)]
        for y in range(4, 16):
            for x in range(2, 12):
                rows[y][x] = VISIBLE
        write_rgba(self.asset, rows)

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_pose_is_softly_pulled_to_significant_alpha_and_kept_as_evidence(self) -> None:
        document = PoseAlphaLimbProvider(
            {"layer-arm-left": self.asset}, observations()
        ).analyze(project_fixture())
        elbow = document["joints"]["elbow.left"]
        self.assertEqual("fusion", elbow["candidates"][0]["method"])
        self.assertGreater(elbow["candidates"][0]["xy"][0], 8.0)
        self.assertLess(elbow["candidates"][0]["xy"][0], 12.0)
        self.assertEqual(["layer-arm-left"], elbow["candidates"][0]["source_layer_ids"])
        self.assertEqual("pose", elbow["candidates"][1]["method"])
        self.assertNotIn("confidence", elbow["candidates"][0])
        self.assertIn("HEURISTIC_SCORE_NOT_CALIBRATED", document["qa"]["flags"])
        self.assertIn("MISSING_POSE_OBSERVATION", document["qa"]["flags"])

    def test_same_inputs_are_deterministic_and_asset_change_changes_run(self) -> None:
        provider = PoseAlphaLimbProvider({"layer-arm-left": self.asset}, observations())
        first = provider.analyze(project_fixture())
        second = provider.analyze(project_fixture())
        self.assertEqual(first, second)
        rows = [[TRANSPARENT for _ in range(20)] for _ in range(20)]
        rows[5][5] = VISIBLE
        write_rgba(self.asset, rows)
        changed = PoseAlphaLimbProvider(
            {"layer-arm-left": self.asset}, observations()
        ).analyze(project_fixture())
        self.assertNotEqual(first["analysis"]["run_sha256"], changed["analysis"]["run_sha256"])

    def test_final_decisions_do_not_change_stage_scoped_run_identity(self) -> None:
        first_project = project_fixture()
        first = PoseAlphaLimbProvider(
            {"layer-arm-left": self.asset}, observations()
        ).analyze(first_project)
        changed_project = project_fixture()
        changed_project["resolved"]["sha256"] = "9" * 64
        changed_project["resolved"]["revision"] = 99
        changed_project["resolved"]["joint_decisions"] = {
            "elbow.left": {"action": "accept"}
        }
        changed = PoseAlphaLimbProvider(
            {"layer-arm-left": self.asset}, observations()
        ).analyze(changed_project)
        self.assertEqual(first["analysis"]["run_sha256"], changed["analysis"]["run_sha256"])

        invalid_project = project_fixture()
        invalid_project["resolved"].pop("sha256")
        without_final_hash = PoseAlphaLimbProvider(
            {"layer-arm-left": self.asset}, observations()
        ).analyze(invalid_project)
        self.assertEqual(first["analysis"]["run_sha256"], without_final_hash["analysis"]["run_sha256"])

    def test_effective_layer_semantics_change_stage_scoped_run_identity(self) -> None:
        first = PoseAlphaLimbProvider(
            {"layer-arm-left": self.asset}, observations()
        ).analyze(project_fixture())
        changed_project = project_fixture()
        changed_project["resolved"]["layers"][0]["side"] = "right"
        changed = PoseAlphaLimbProvider(
            {"layer-arm-left": self.asset}, observations()
        ).analyze(changed_project)
        self.assertNotEqual(first["analysis"]["run_sha256"], changed["analysis"]["run_sha256"])

    def test_dimension_mismatch_fails_and_missing_pose_remains_explicit(self) -> None:
        project = project_fixture()
        project["resolved"]["layers"][0]["bbox"]["width"] = 19
        with self.assertRaises(LimbCandidateError):
            PoseAlphaLimbProvider({"layer-arm-left": self.asset}, observations()).analyze(project)
        project = project_fixture()
        document = PoseAlphaLimbProvider(
            {"layer-arm-left": self.asset}, observations()
        ).analyze(project)
        wrist = document["joints"]["wrist.left"]
        self.assertEqual("ambiguous", wrist["observability"])
        self.assertEqual(["MISSING_POSE_OBSERVATION"], wrist["candidates"][0]["qa_flags"])

    @unittest.skipIf(Draft202012Validator is None, "install the 'test' extra")
    def test_output_validates_against_v1_candidate_schema(self) -> None:
        document = PoseAlphaLimbProvider(
            {"layer-arm-left": self.asset}, observations(include_wrist=True)
        ).analyze(project_fixture())
        schema = json.loads(
            (ROOT / "schemas" / "joint-candidates-v1.schema.json").read_text(encoding="utf-8")
        )
        Draft202012Validator(schema).validate(document)


if __name__ == "__main__":
    unittest.main()
