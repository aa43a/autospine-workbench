"""Semantic contact assignment and alpha-evidence contract tests."""

from __future__ import annotations

from pathlib import Path
import sys
import tempfile
from types import MappingProxyType
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.alpha_evidence_validation import (  # noqa: E402
    require_valid_alpha_geometry_evidence,
)
from autospine_workbench.alpha_geometry import analyze_alpha_png  # noqa: E402
from autospine_workbench.limb_contact_evidence import analyze_limb_contacts  # noqa: E402
from autospine_workbench.limb_evidence_layers import LimbEvidenceSet  # noqa: E402
from autospine_workbench.pose_observations import (  # noqa: E402
    PoseJointObservation,
    PoseObservationSet,
)
from autospine_workbench.resolved_project import canonical_sha256  # noqa: E402
from tests.png_helpers import write_rgba  # noqa: E402


TRANSPARENT = (0, 0, 0, 0)
VISIBLE = (30, 50, 70, 255)
CANVAS = (80, 80)


class LimbContactEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)

    def test_shoulder_lobes_are_retained_and_pose_assigned_without_screen_x(self) -> None:
        lobes = ((5, 8, 8, 8), (34, 8, 8, 8), (62, 8, 8, 8))
        evidence = self._evidence(
            ("arm", "body.hand", "bilateral", lobes, None),
            ("torso", "body.torso", "center", lobes, None),
        )
        pose = self._pose(shoulder_left=(66, 12), shoulder_right=(9, 12))

        first = analyze_limb_contacts(evidence, pose, CANVAS, {})
        second = analyze_limb_contacts(evidence, pose, CANVAS, {})

        self.assertEqual(first, second)
        self.assertEqual(3, len(first.contacts))
        self.assertEqual(sorted(item["contact_id"] for item in first.contacts),
                         [item["contact_id"] for item in first.contacts])
        left = [item for item in first.contacts if item["joint_id"] == "shoulder.left"]
        right = [item for item in first.contacts if item["joint_id"] == "shoulder.right"]
        self.assertTrue(any(item["representative_xy"][0] > 60 for item in left))
        self.assertTrue(any(item["representative_xy"][0] < 15 for item in right))
        left_ids = set(first.joint_contact_ids["shoulder.left"])
        right_ids = set(first.joint_contact_ids["shoulder.right"])
        self.assertFalse(left_ids & right_ids)
        self.assertIn("SHOULDER_MULTIPLE_CONTACT_LOBES_RETAINED", first.qa_flags)
        self._assert_contract_valid(evidence, first)

    def test_pelvis_leg_warns_at_ten_percent_and_rejects_at_twenty_five(self) -> None:
        ambiguous = self._evidence(
            ("leg", "body.leg", "left", ((10, 10, 10, 40),), None),
            ("pelvis", "body.pelvis", "center", ((10, 10, 10, 4),), None),
        )
        pose = self._pose(hip_left=(14, 12))
        warned = analyze_limb_contacts(ambiguous, pose, CANVAS, {})

        self.assertEqual(1, len(warned.contacts))
        self.assertIn("PELVIS_LEG_CONTACT_AMBIGUOUS", warned.contacts[0]["flags"])
        self.assertIn("PELVIS_LEG_CONTACT_AMBIGUOUS", warned.qa_flags)

        rejected = self._evidence(
            ("leg", "body.leg", "left", ((10, 10, 10, 40),), None),
            ("pelvis", "body.pelvis", "center", ((10, 10, 10, 10),), None),
        )
        blocked = analyze_limb_contacts(rejected, pose, CANVAS, {})
        self.assertEqual([], blocked.contacts)
        self.assertIn("PELVIS_LEG_OVERLAP_TOO_DEEP", blocked.qa_flags)
        self.assertIn("PELVIS_LEG_OVERLAP_TOO_DEEP", blocked.joint_flags["hip.left"])

    def test_missing_leg_forbids_pelvis_foot_shortcut(self) -> None:
        same = ((20, 20, 12, 12),)
        evidence = self._evidence(
            ("foot", "body.foot", "bilateral", same, None),
            ("pelvis", "body.pelvis", "center", same, None),
        )
        result = analyze_limb_contacts(evidence, self._pose(), CANVAS, {})

        self.assertEqual([], result.contacts)
        expected = {
            "PELVIS_LEG_EDGE_UNOBSERVABLE",
            "LEG_FOOT_EDGE_UNOBSERVABLE",
            "PELVIS_FOOT_SHORTCUT_FORBIDDEN",
        }
        self.assertTrue(expected.issubset(result.qa_flags))

    def test_two_leg_foot_lobes_use_distinct_pose_nearest_sites(self) -> None:
        lobes = ((7, 55, 8, 8), (60, 55, 8, 8))
        evidence = self._evidence(
            ("foot", "body.foot", "bilateral", lobes, None),
            ("leg", "body.leg", "bilateral", lobes, None),
        )
        pose = self._pose(ankle_left=(64, 59), ankle_right=(11, 59))
        result = analyze_limb_contacts(evidence, pose, CANVAS, {})

        contacts = [item for item in result.contacts if item["relation"] == "leg_foot"]
        self.assertEqual(2, len(contacts))
        by_joint = {item["joint_id"]: item for item in contacts}
        self.assertGreater(by_joint["ankle.left"]["representative_xy"][0], 55)
        self.assertLess(by_joint["ankle.right"]["representative_xy"][0], 20)
        refs = result.joint_contact_ids
        self.assertNotEqual(refs["ankle.left"], refs["ankle.right"])

    def test_invalid_canvas_or_contact_config_fails_loudly(self) -> None:
        evidence = self._evidence()
        with self.assertRaises(ValueError):
            analyze_limb_contacts(evidence, self._pose(), (0, 80), {})
        with self.assertRaises(ValueError):
            analyze_limb_contacts(
                evidence, self._pose(), CANVAS, {"contact_max_gap_ratio": float("nan")}
            )
        removed = (
            "contact_assigned_max_ratio",
            "contact_anchor_max_ratio",
            "contact_error_radius_ratio",
            "pelvis_leg_anchor_max_ratio",
        )
        for setting in removed:
            with self.subTest(setting=setting), self.assertRaisesRegex(
                ValueError, "unsupported contact geometry settings"
            ):
                analyze_limb_contacts(evidence, self._pose(), CANVAS, {setting: 0.1})

    def _evidence(self, *specs) -> LimbEvidenceSet:
        geometries = {}
        layers = {}
        for layer_id, role, side, rectangles, bbox in specs:
            rows = [[TRANSPARENT for _ in range(CANVAS[0])] for _ in range(CANVAS[1])]
            for x, y, width, height in rectangles:
                for row in range(y, y + height):
                    for column in range(x, x + width):
                        rows[row][column] = VISIBLE
            path = Path(self.directory.name) / f"{layer_id}.png"
            write_rgba(path, rows)
            geometries[layer_id] = analyze_alpha_png(path)
            layers[layer_id] = {
                "id": layer_id,
                "canonical_role": role,
                "side": side,
                "disposition": "keep",
                "empty": False,
                "bbox": bbox or {"x": 0, "y": 0, "width": 80, "height": 80},
            }
        return LimbEvidenceSet(
            effective_layers=tuple(layers[key] for key in sorted(layers)),
            identity_summaries=(),
            geometries=MappingProxyType(geometries),
            layers_by_id=MappingProxyType(layers),
            flags=frozenset(),
        )

    def _pose(self, **points) -> PoseObservationSet:
        defaults = {
            f"{joint}_{side}": (20 if side == "left" else 60, 20)
            for joint in ("shoulder", "hip", "ankle") for side in ("left", "right")
        }
        defaults.update(points)
        joints = {
            key.replace("_", "."): PoseJointObservation(float(x), float(y), 0.9, "visible")
            for key, (x, y) in defaults.items()
        }
        return PoseObservationSet(
            project_id="fixture", image_sha256="a" * 64, canvas_size=CANVAS,
            detector_id="fixture", detector_version="1", model_revision="r1",
            config_sha256="b" * 64, runtime="test", detected_count=1,
            selected_index=0, selection_method="single", joints=joints,
            document_sha256="c" * 64,
        )

    def _assert_contract_valid(self, evidence, sections) -> None:
        layers = []
        for layer_id in sorted(evidence.geometries):
            geometry = evidence.geometries[layer_id]
            layer = evidence.layers_by_id[layer_id]
            layers.append({
                "layer_id": layer_id, "raster_sha256": "d" * 64,
                "canonical_role": layer["canonical_role"], "side": layer["side"],
                "disposition": "keep", "alpha_threshold": geometry.threshold,
                "foreground_area": geometry.foreground_area,
                "components": [{"component_id": item.component_id, "area": item.area,
                                "bbox_xywh": list(item.bbox_xywh)}
                               for item in geometry.components],
            })
        source = {"base_project_sha256": "e" * 64, "source_image_sha256": "f" * 64}
        input_sha = canonical_sha256({"project_id": "fixture", "source": source, "layers": layers})
        analysis = {"provider": "fixture", "provider_version": "1",
                    "input_sha256": input_sha, "config_sha256": "1" * 64}
        analysis["run_sha256"] = canonical_sha256(analysis)
        joint_ids = {item["joint_id"] for item in sections.contacts}
        observability = {
            joint_id: {"status": "ambiguous", "path_ids": [],
                       "contact_ids": sections.joint_contact_ids[joint_id],
                       "flags": sections.joint_flags.get(joint_id, [])}
            for joint_id in sorted(joint_ids)
        }
        document = {
            "format": "autospine-alpha-geometry-evidence", "format_version": 1,
            "project_id": "fixture", "source": source, "analysis": analysis,
            "coordinate_system": {"origin": "top_left", "x_axis": "right",
                                  "y_axis": "down", "units": "pixel",
                                  "side_naming": "character_side"},
            "layers": layers, "paths": [], "contacts": sections.contacts,
            "observability": observability,
            "qa": {"status": "manual_required", "flags": sorted(sections.qa_flags)},
        }
        require_valid_alpha_geometry_evidence(
            document, project_id="fixture", joint_ids=joint_ids,
            layer_ids=set(evidence.geometries), canvas_width=80, canvas_height=80,
        )


if __name__ == "__main__":
    unittest.main()
