"""Bundle-level tests for geometry-bound limb joint candidates."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.alpha_evidence_validation import (  # noqa: E402
    require_valid_alpha_geometry_evidence,
)
from autospine_workbench.candidate_validation import (  # noqa: E402
    require_valid_candidate_document,
)
from autospine_workbench.pose_geometry_limb_provider import (  # noqa: E402
    PoseGeometryLimbProvider,
)
from autospine_workbench.pose_observations import (  # noqa: E402
    PoseJointObservation,
    PoseObservationSet,
)
from autospine_workbench.resolved_project import canonical_sha256  # noqa: E402
from tests.png_helpers import write_rgba  # noqa: E402


CANVAS = (80, 80)
TRANSPARENT = (0, 0, 0, 0)
VISIBLE = (70, 80, 90, 255)
JOINT_POINTS = {
    "shoulder.left": (15, 10), "elbow.left": (15, 40), "wrist.left": (15, 70),
    "shoulder.right": (65, 10), "elbow.right": (65, 40), "wrist.right": (65, 70),
    "hip.left": (55, 25), "knee.left": (55, 45), "ankle.left": (55, 65),
    "hip.right": (70, 25), "knee.right": (70, 45), "ankle.right": (70, 65),
}


def _layer(layer_id: str, role: str, side: str) -> dict:
    return {
        "id": layer_id,
        "canonical_role": role,
        "side": side,
        "disposition": "keep",
        "empty": False,
        "bbox": {"x": 0, "y": 0, "width": 80, "height": 80},
    }


def _project() -> dict:
    layers = [
        _layer("hand-left", "body.hand", "left"),
        _layer("torso", "body.torso", "center"),
        _layer("leg-left", "body.leg", "left"),
        _layer("pelvis", "body.pelvis", "center"),
    ]
    joints = [
        {"id": joint_id, "x": xy[0], "y": xy[1], "confidence": 0.6, "source": "fixture"}
        for joint_id, xy in sorted(JOINT_POINTS.items())
    ]
    return {
        "id": "geometry-fixture",
        "source": {"sha256": "a" * 64, "audit_sha256": "b" * 64},
        "canvas": {"width": 80, "height": 80},
        "layers": layers,
        "skeleton": {"joints": joints},
        "resolved": {"revision": 1, "layers": layers, "skeleton": {"joints": joints}},
    }


def _observations() -> PoseObservationSet:
    return PoseObservationSet(
        project_id="geometry-fixture",
        image_sha256="a" * 64,
        canvas_size=CANVAS,
        detector_id="fixture-pose",
        detector_version="1",
        model_revision="fixture",
        config_sha256="c" * 64,
        runtime="unittest",
        detected_count=1,
        selected_index=0,
        selection_method="single",
        joints={
            joint_id: PoseJointObservation(float(x), float(y), 0.8, "visible")
            for joint_id, (x, y) in JOINT_POINTS.items()
        },
        document_sha256="d" * 64,
    )


class _CandidateV2(PoseGeometryLimbProvider):
    provider_version = "2"


class _GeometryV2(PoseGeometryLimbProvider):
    geometry_provider_version = "2"


class PoseGeometryLimbProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.project = _project()
        self.pose = _observations()
        self.pixels = {
            "hand-left": {(x, y) for x in range(10, 21) for y in range(5, 76)},
            "torso": {(x, y) for x in range(18, 46) for y in range(5, 21)},
            "leg-left": {(x, y) for x in range(50, 60) for y in range(20, 70)},
            "pelvis": {(x, y) for x in range(50, 60) for y in range(20, 40)},
        }
        self.assets = {
            layer_id: Path(self.directory.name) / f"{layer_id}.png"
            for layer_id in self.pixels
        }
        for layer_id in self.pixels:
            self._write(layer_id)

    def _write(self, layer_id: str) -> None:
        rows = [[TRANSPARENT for _ in range(80)] for _ in range(80)]
        for x, y in self.pixels[layer_id]:
            rows[y][x] = VISIBLE
        write_rgba(self.assets[layer_id], rows)

    def _validate(self, bundle) -> None:
        joint_ids = set(JOINT_POINTS)
        layer_ids = set(self.assets)
        require_valid_alpha_geometry_evidence(
            bundle.geometry_document,
            project_id=self.project["id"],
            joint_ids=joint_ids,
            layer_ids=layer_ids,
            canvas_width=80,
            canvas_height=80,
        )
        require_valid_candidate_document(
            bundle.joint_candidate_document,
            joint_ids=joint_ids,
            layer_ids=layer_ids,
            canvas_width=80,
            canvas_height=80,
        )

    def test_bundle_is_deterministic_valid_and_geometry_bound(self) -> None:
        provider = PoseGeometryLimbProvider(self.assets, self.pose)
        first, second = provider.analyze(self.project), provider.analyze(self.project)
        self.assertEqual(first, second)
        self._validate(first)
        geometry_sha = canonical_sha256(first.geometry_document)
        run_prefix = first.joint_candidate_document["analysis"]["run_sha256"][:12]

        elbow = first.joint_candidate_document["joints"]["elbow.left"]
        self.assertTrue({"pose", "fusion", "medial_axis"}.issubset(
            {item["method"] for item in elbow["candidates"]}
        ))
        fusion = next(item for item in elbow["candidates"] if item["method"] == "fusion")
        self.assertIn(
            f"alpha-geometry-evidence:{geometry_sha}#layers/hand-left/components/0",
            {item.get("source_ref") for item in fusion["evidence"]},
        )
        shoulder = first.joint_candidate_document["joints"]["shoulder.left"]
        self.assertIn("contact", {item["method"] for item in shoulder["candidates"]})
        for joint in first.joint_candidate_document["joints"].values():
            for candidate in joint["candidates"]:
                self.assertIn(run_prefix, candidate["candidate_id"])
                self.assertEqual("heuristic", candidate["score_kind"])
                if candidate["method"] in {"medial_axis", "contact"}:
                    self.assertTrue(all(
                        item["source_ref"].startswith(
                            f"alpha-geometry-evidence:{geometry_sha}#"
                        )
                        for item in candidate["evidence"]
                    ))
        copied = first.to_dict()
        copied["geometry_document"]["paths"].clear()
        self.assertTrue(first.geometry_document["paths"])

    def test_candidate_and_geometry_algorithm_versions_change_only_downstream_identity(self) -> None:
        original = PoseGeometryLimbProvider(self.assets, self.pose).analyze(self.project)
        candidate_v2 = _CandidateV2(self.assets, self.pose).analyze(self.project)
        geometry_v2 = _GeometryV2(self.assets, self.pose).analyze(self.project)
        self.assertEqual(original.geometry_document, candidate_v2.geometry_document)
        self.assertNotEqual(
            original.joint_candidate_document["analysis"]["run_sha256"],
            candidate_v2.joint_candidate_document["analysis"]["run_sha256"],
        )
        self.assertNotEqual(
            canonical_sha256(original.geometry_document),
            canonical_sha256(geometry_v2.geometry_document),
        )
        self.assertNotEqual(
            original.joint_candidate_document["analysis"]["run_sha256"],
            geometry_v2.joint_candidate_document["analysis"]["run_sha256"],
        )

        self.pixels["leg-left"].add((49, 45))
        self._write("leg-left")
        changed = PoseGeometryLimbProvider(self.assets, self.pose).analyze(self.project)
        self.assertNotEqual(
            canonical_sha256(original.geometry_document),
            canonical_sha256(changed.geometry_document),
        )
        self.assertNotEqual(
            original.joint_candidate_document["source"]["base_project_sha256"],
            changed.joint_candidate_document["source"]["base_project_sha256"],
        )
        self.assertNotEqual(
            original.joint_candidate_document["analysis"]["run_sha256"],
            changed.joint_candidate_document["analysis"]["run_sha256"],
        )

    def test_unavailable_paths_and_rejected_hip_contacts_create_no_candidates(self) -> None:
        bundle = PoseGeometryLimbProvider(
            self.assets, self.pose, geometry_overrides={"max_raster_pixels": 100}
        ).analyze(self.project)
        self._validate(bundle)
        self.assertTrue(any(
            item["status"] == "unavailable" for item in bundle.geometry_document["paths"]
        ))
        all_candidates = [
            candidate
            for joint in bundle.joint_candidate_document["joints"].values()
            for candidate in joint["candidates"]
        ]
        self.assertNotIn("medial_axis", {item["method"] for item in all_candidates})
        self.assertFalse(any(
            item["relation"] == "pelvis_leg"
            for item in bundle.geometry_document["contacts"]
        ))
        for side in ("left", "right"):
            hip = bundle.joint_candidate_document["joints"][f"hip.{side}"]
            self.assertNotIn("contact", {item["method"] for item in hip["candidates"]})


if __name__ == "__main__":
    unittest.main()
