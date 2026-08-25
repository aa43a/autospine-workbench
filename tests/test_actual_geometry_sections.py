"""Non-pixel-exact P1 geometry checks on the supplied See-through samples."""

from __future__ import annotations

import json
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

from autospine_workbench.alpha_evidence_document import (  # noqa: E402
    build_alpha_geometry_evidence,
)
from autospine_workbench.candidate_provenance import sha256_file  # noqa: E402
from autospine_workbench.limb_evidence_layers import load_limb_evidence  # noqa: E402
from autospine_workbench.limb_geometry_sections import (  # noqa: E402
    analyze_geometry_sections,
)
from autospine_workbench.pose_observations import (  # noqa: E402
    PoseJointObservation,
    PoseObservationSet,
)
from autospine_workbench.project_store import ProjectStore  # noqa: E402
from autospine_workbench.resolved_project import canonical_sha256  # noqa: E402


PROJECT_IDS = ("seethrough_output", "seethrough_output_5")
CONFIG = {
    "alpha_threshold": 8,
    "component_min_area": 16,
    "component_min_ratio": 0.001,
}
LIMB_JOINTS = {"shoulder", "elbow", "wrist", "hip", "knee", "ankle"}


def _require_samples() -> None:
    for project_id in PROJECT_IDS:
        if not (AUDIT_ROOT / project_id / "audit.json").is_file():
            raise unittest.SkipTest("supplied See-through audits are not present")


def _diagnostic_prior(project: dict, composite: Path) -> PoseObservationSet:
    """Use setup joints as a reproducible prior, never as a model-accuracy claim."""

    joints = {
        item["id"]: PoseJointObservation(
            float(item["x"]), float(item["y"]), 1.0, "visible"
        )
        for item in project["resolved"]["skeleton"]["joints"]
        if item["id"].split(".", 1)[0] in LIMB_JOINTS
    }
    identity = canonical_sha256(
        {
            "kind": "real-sample-geometry-diagnostic-prior",
            "project_id": project["id"],
            "joints": {
                joint_id: [joint.x, joint.y]
                for joint_id, joint in sorted(joints.items())
            },
        }
    )
    return PoseObservationSet(
        project_id=project["id"],
        image_sha256=sha256_file(composite, "composite"),
        canvas_size=(project["canvas"]["width"], project["canvas"]["height"]),
        detector_id="diagnostic-setup-prior",
        detector_version="1",
        model_revision="not-a-model-accuracy-measurement",
        config_sha256=canonical_sha256({"kind": "setup-prior"}),
        runtime="unittest",
        detected_count=1,
        selected_index=0,
        selection_method="single",
        joints=joints,
        document_sha256=identity,
    )


def _analyze(store: ProjectStore, project_id: str):
    project = store.get_project(project_id)
    canvas = (project["canvas"]["width"], project["canvas"]["height"])
    assets = {
        layer["id"]: store.resolve_asset(project_id, "layer", layer["id"])
        for layer in project["layers"]
    }
    evidence = load_limb_evidence(
        project, assets, canvas, CONFIG, include_contact_roles=True
    )
    observations = _diagnostic_prior(
        project, store.resolve_asset(project_id, "composite")
    )
    sections = analyze_geometry_sections(evidence, observations, canvas, CONFIG)
    document = build_alpha_geometry_evidence(
        project, evidence, observations, sections, config=CONFIG
    )
    return sections, document


class ActualGeometrySectionTests(unittest.TestCase):
    def test_real_samples_preserve_reviewable_geometry_invariants(self) -> None:
        _require_samples()
        started = time.perf_counter()
        with tempfile.TemporaryDirectory() as state_root:
            store = ProjectStore(REPOSITORY_ROOT, state_root=Path(state_root))
            first, first_document = _analyze(store, PROJECT_IDS[0])
            second, second_document = _analyze(store, PROJECT_IDS[1])
        self.assertLess(time.perf_counter() - started, 5.0)

        # The artifact builder validates the complete alpha-evidence contract.
        self.assertEqual("autospine-alpha-geometry-evidence", first_document["format"])
        self.assertEqual("autospine-alpha-geometry-evidence", second_document["format"])
        json.dumps(first.to_dict(), allow_nan=False, sort_keys=True)
        copied = first.to_dict()
        copied["paths"].clear()
        self.assertTrue(first.paths, "to_dict() must not expose mutable internals")

        shoulder_contacts = [
            item for item in first.contacts if item["relation"] == "torso_arm"
        ]
        shoulder_sides = [item["joint_id"] for item in shoulder_contacts]
        self.assertGreaterEqual(len(shoulder_contacts), 5)
        self.assertGreaterEqual(shoulder_sides.count("shoulder.left"), 2)
        self.assertGreaterEqual(shoulder_sides.count("shoulder.right"), 2)
        self.assertIn("SHOULDER_MULTIPLE_CONTACT_LOBES_RETAINED", first.qa_flags)

        self.assertFalse(
            any(item["relation"] == "pelvis_leg" for item in first.contacts)
        )
        self.assertIn("PELVIS_LEG_OVERLAP_TOO_DEEP", first.qa_flags)
        ankle_contacts = [
            item for item in first.contacts if item["relation"] == "leg_foot"
        ]
        self.assertEqual(2, len(ankle_contacts))
        self.assertEqual(
            {"ankle.left", "ankle.right"},
            {item["joint_id"] for item in ankle_contacts},
        )
        self.assertEqual(2, len({item["contact_id"] for item in ankle_contacts}))

        leg_paths = [item for item in first.paths if item["limb_id"].startswith("leg.")]
        self.assertEqual(2, len(leg_paths))
        for side in ("left", "right"):
            for joint in ("hip", "knee", "ankle"):
                self.assertEqual("merged", first.observability[f"{joint}.{side}"]["status"])
                self.assertIn(
                    "BILATERAL_FUSED_COMPONENT",
                    first.observability[f"{joint}.{side}"]["flags"],
                )

        self.assertFalse(any(item["limb_id"].startswith("leg.") for item in second.paths))
        self.assertFalse(
            any(item["relation"] in {"pelvis_leg", "leg_foot"} for item in second.contacts)
        )
        self.assertTrue(any(item["relation"] == "torso_arm" for item in second.contacts))
        for flag in (
            "NO_LEG_SEMANTIC_LAYER",
            "PELVIS_LEG_EDGE_UNOBSERVABLE",
            "LEG_FOOT_EDGE_UNOBSERVABLE",
            "PELVIS_FOOT_SHORTCUT_FORBIDDEN",
        ):
            self.assertIn(flag, second.qa_flags)


if __name__ == "__main__":
    unittest.main()
