"""Non-pixel-exact limb provider smoke tests on the two supplied audits."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import time
import unittest


WORKBENCH_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = WORKBENCH_ROOT.parent
AUDIT_ROOT = REPOSITORY_ROOT / "tmp" / "psd_audit" / "results"
SRC_ROOT = WORKBENCH_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from autospine_workbench.candidate_provenance import sha256_file  # noqa: E402
from autospine_workbench.candidate_validation import require_valid_candidate_document  # noqa: E402
from autospine_workbench.limb_candidates import PoseAlphaLimbProvider  # noqa: E402
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


def _observations(project: dict, composite: Path) -> PoseObservationSet:
    joints = {
        item["id"]: PoseJointObservation(float(item["x"]), float(item["y"]), 0.75, "visible")
        for item in project["skeleton"]["joints"]
        if item["id"].split(".", 1)[0] in {"shoulder", "elbow", "wrist", "hip", "knee", "ankle"}
    }
    identity = canonical_sha256(
        {"kind": "real-sample-smoke-prior", "project": project["id"], "joints": sorted(joints)}
    )
    return PoseObservationSet(
        project_id=project["id"],
        image_sha256=sha256_file(composite),
        canvas_size=(project["canvas"]["width"], project["canvas"]["height"]),
        detector_id="test-smoke-prior",
        detector_version="1",
        model_revision="not-a-model-bbox-smoke-only",
        config_sha256=canonical_sha256({}),
        runtime="unittest",
        detected_count=1,
        selected_index=0,
        selection_method="single",
        joints=joints,
        document_sha256=identity,
    )


class ActualLimbCandidateSmokeTests(unittest.TestCase):
    def test_real_layers_produce_auditable_not_claimed_accurate_candidates(self) -> None:
        _require_samples()
        with tempfile.TemporaryDirectory() as state_root:
            store = ProjectStore(REPOSITORY_ROOT, state_root=Path(state_root))
            started = time.perf_counter()
            documents = {}
            for project_id in ("seethrough_output", "seethrough_output_5"):
                project = store.get_project(project_id)
                assets = {
                    layer["id"]: store.resolve_asset(project_id, "layer", layer["id"])
                    for layer in project["layers"]
                }
                provider = PoseAlphaLimbProvider(
                    assets,
                    _observations(project, store.resolve_asset(project_id, "composite")),
                )
                document = provider.analyze(project)
                require_valid_candidate_document(
                    document,
                    joint_ids={item["id"] for item in project["skeleton"]["joints"]},
                    layer_ids={item["id"] for item in project["layers"]},
                    canvas_width=project["canvas"]["width"],
                    canvas_height=project["canvas"]["height"],
                )
                documents[project_id] = document
        self.assertLess(time.perf_counter() - started, 5.0)
        first_flags = set(documents["seethrough_output"]["qa"]["flags"])
        self.assertIn("BILATERAL_FUSED_COMPONENT", first_flags)
        second = documents["seethrough_output_5"]
        self.assertIn("NO_LEG_SEMANTIC_LAYER", second["qa"]["flags"])
        self.assertIn(
            "NO_RELEVANT_ALPHA_LAYER",
            second["joints"]["knee.left"]["candidates"][0]["qa_flags"],
        )
        self.assertEqual("occluded", second["joints"]["hip.left"]["observability"])


if __name__ == "__main__":
    unittest.main()
