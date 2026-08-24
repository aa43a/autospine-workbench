"""Non-model smoke tests for reviewed-joint coverage in the supplied samples."""

from __future__ import annotations

import shutil
from pathlib import Path
import sys
import tempfile
import unittest


WORKBENCH_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = WORKBENCH_ROOT.parent
AUDIT_ROOT = REPOSITORY_ROOT / "tmp" / "psd_audit" / "results"
TRACKED_OVERRIDE_ROOT = WORKBENCH_ROOT / "workspace" / "overrides"
SRC_ROOT = WORKBENCH_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from autospine_workbench.candidate_provenance import sha256_file  # noqa: E402
from autospine_workbench.pose_evaluation import LIMB_JOINT_IDS, evaluate_pose  # noqa: E402
from autospine_workbench.pose_observations import (  # noqa: E402
    PoseJointObservation,
    PoseObservationSet,
)
from autospine_workbench.project_store import ProjectStore  # noqa: E402
from autospine_workbench.resolved_project import canonical_sha256  # noqa: E402


def _require_samples() -> None:
    for project_id in ("seethrough_output", "seethrough_output_5"):
        if not (AUDIT_ROOT / project_id / "audit.json").is_file():
            raise unittest.SkipTest("supplied See-through audits are not present")
        if not (TRACKED_OVERRIDE_ROOT / f"{project_id}.json").is_file():
            raise unittest.SkipTest("tracked review examples are not present")


def _reference_observations(project: dict, composite: Path) -> PoseObservationSet:
    reviewed = {
        joint["id"]: joint
        for joint in project["resolved"]["skeleton"]["joints"]
        if joint.get("review_state") == "manual_adjusted" and joint["id"] in LIMB_JOINT_IDS
    }
    joints = {
        joint_id: PoseJointObservation(
            float(joint["x"]), float(joint["y"]), 1.0, "unknown"
        )
        for joint_id, joint in reviewed.items()
    }
    return PoseObservationSet(
        project_id=project["id"],
        image_sha256=sha256_file(composite),
        canvas_size=(project["canvas"]["width"], project["canvas"]["height"]),
        detector_id="manual-reference-smoke",
        detector_version="1",
        model_revision="not-a-model-reference-loopback",
        config_sha256=canonical_sha256({"kind": "reference-loopback"}),
        runtime="unittest",
        detected_count=1,
        selected_index=0,
        selection_method="single",
        joints=joints,
        document_sha256=canonical_sha256(
            {
                "kind": "reference-loopback",
                "project_id": project["id"],
                "joints": {
                    joint_id: [observation.x, observation.y]
                    for joint_id, observation in joints.items()
                },
            }
        ),
    )


class ActualPoseReferenceSmokeTests(unittest.TestCase):
    def test_tracked_reviews_form_a_partial_but_evaluable_reference_set(self) -> None:
        _require_samples()
        expected_counts = {"seethrough_output": 12, "seethrough_output_5": 10}
        with tempfile.TemporaryDirectory() as directory:
            state_root = Path(directory)
            override_root = state_root / "overrides"
            override_root.mkdir(parents=True)
            for project_id in expected_counts:
                shutil.copyfile(
                    TRACKED_OVERRIDE_ROOT / f"{project_id}.json",
                    override_root / f"{project_id}.json",
                )
            store = ProjectStore(REPOSITORY_ROOT, state_root=state_root)
            for project_id, expected_count in expected_counts.items():
                with self.subTest(project_id=project_id):
                    project = store.get_project(project_id)
                    report = evaluate_pose(
                        project,
                        _reference_observations(
                            project, store.resolve_asset(project_id, "composite")
                        ),
                    )
                    self.assertEqual(expected_count, report["metrics"]["reference_count"])
                    self.assertEqual(expected_count, report["metrics"]["matched_count"])
                    self.assertEqual(0.0, report["metrics"]["mean_error_px"])
                    self.assertEqual(
                        "as_mapped",
                        report["side_swap_diagnostic"]["lower_error_mapping"],
                    )


if __name__ == "__main__":
    unittest.main()
