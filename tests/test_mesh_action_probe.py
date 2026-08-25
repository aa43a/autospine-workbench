"""Deterministic P3 deformation action probe tests."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import math
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.mesh_action_probe import (  # noqa: E402
    BEND_STEP_DEGREES,
    MAX_AREA_RATIO,
    MAX_BEND_DEGREES,
    MAX_EDGE_STRETCH,
    MIN_AREA_RATIO,
    MeshActionProbeError,
    run_mesh_action_probe,
)
from autospine_workbench.mesh_deformation_metrics import (  # noqa: E402
    measure_deformation,
)


PROXIMAL = "thigh.left"
DISTAL = "calf.left"
OFFSET = (100, 50)


def bone(bone_id: str, *, parent=None, x=0.0, y=0.0, length=10.0) -> dict:
    return {
        "id": bone_id,
        "parent": parent,
        "setup": {
            "x": x,
            "y": y,
            "rotation_deg": 0.0,
            "scale_x": 1.0,
            "scale_y": 1.0,
            "length": length,
        },
    }


def bones() -> list[dict]:
    return [
        bone(PROXIMAL, x=OFFSET[0], y=OFFSET[1]),
        bone(DISTAL, parent=PROXIMAL, x=10.0),
    ]


def influence(bone_id: str, weight: float = 1.0) -> dict:
    return {"bone": bone_id, "weight": weight}


def passing_attachment() -> dict:
    return {
        "id": "leg-left",
        "type": "mesh",
        "canvas_offset_xy": list(OFFSET),
        # Vertex zero is the hinge. Both bone transforms leave it fixed, so the
        # entire triangle follows the distal rotation rigidly through +/-135.
        "vertices": [[10, 0], [20, 0], [10, 10]],
        "triangles": [0, 1, 2],
        "weights": [
            [influence(PROXIMAL, 0.5), influence(DISTAL, 0.5)],
            [influence(DISTAL)],
            [influence(DISTAL)],
        ],
    }


def early_failure_attachment() -> dict:
    result = passing_attachment()
    result["vertices"] = [[10, 0], [1000, 0], [1000, 0.001]]
    result["weights"] = [
        [influence(PROXIMAL)],
        [influence(PROXIMAL)],
        [influence(DISTAL)],
    ]
    return result


def run(attachment=None, rig_bones=None, **options):
    return run_mesh_action_probe(
        rig_bones if rig_bones is not None else bones(),
        attachment if attachment is not None else passing_attachment(),
        proximal_bone_id=PROXIMAL,
        distal_bone_id=DISTAL,
        **options,
    )


class PassingActionProbeTests(unittest.TestCase):
    def test_setup_offset_rigid_probes_and_both_full_bends_pass(self) -> None:
        result = run()

        self.assertEqual(((110.0, 50.0), (120.0, 50.0), (110.0, 60.0)), result.setup_canvas_vertices_xy)
        self.assertEqual("passed", result.setup.status)
        self.assertEqual((-90, 90), (result.proximal_negative.angle_deg, result.proximal_positive.angle_deg))
        self.assertEqual("passed", result.proximal_negative.status)
        self.assertEqual("passed", result.proximal_positive.status)
        for direction, sweep, sign in (
            ("negative", result.distal_negative, -1),
            ("positive", result.distal_positive, 1),
        ):
            with self.subTest(direction=direction):
                self.assertEqual(direction, sweep.direction)
                self.assertEqual(MAX_BEND_DEGREES, sweep.max_contiguous_magnitude_deg)
                self.assertIsNone(sweep.first_failure)
                self.assertEqual(MAX_BEND_DEGREES // BEND_STEP_DEGREES, len(sweep.samples))
                self.assertEqual(sign * 5, sweep.samples[0].angle_deg)
                self.assertEqual(sign * 135, sweep.samples[-1].angle_deg)
                self.assertTrue(all(item.status == "passed" for item in sweep.samples))

    def test_result_and_nested_evidence_are_frozen_and_json_is_stable(self) -> None:
        result = run()
        self.assertEqual(result.to_json(), run().to_json())
        self.assertEqual(result.to_dict(), run().to_dict())
        self.assertEqual("autospine-mesh-action-probe", result.to_dict()["format"])
        with self.assertRaises(FrozenInstanceError):
            result.step_degrees = 10  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            result.distal_positive.max_contiguous_magnitude_deg = 0  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            result.setup.metrics.flipped_count = 1  # type: ignore[misc]
        changed = result.to_dict()
        changed["distal_bend"]["positive"]["samples"].clear()
        self.assertEqual(27, len(result.distal_positive.samples))

    def test_mapping_order_weight_order_and_inputs_do_not_change_result(self) -> None:
        rig_bones, attachment = bones(), passing_attachment()
        before = deepcopy((rig_bones, attachment))
        first = run(attachment, rig_bones)
        self.assertEqual(before, (rig_bones, attachment))

        reversed_bones = list(reversed(deepcopy(rig_bones)))
        reversed_attachment = dict(reversed(list(deepcopy(attachment).items())))
        reversed_attachment["weights"][0].reverse()
        reversed_before = deepcopy((reversed_bones, reversed_attachment))
        second = run(reversed_attachment, reversed_bones)
        self.assertEqual(first, second)
        self.assertEqual(reversed_before, (reversed_bones, reversed_attachment))

    def test_probe_pins_metrics_strict_threshold_boundaries(self) -> None:
        calls: list[dict] = []

        def recording(*args, **kwargs):
            calls.append(dict(kwargs))
            return measure_deformation(*args, **kwargs)

        with patch(
            "autospine_workbench.mesh_action_probe.measure_deformation",
            side_effect=recording,
        ):
            result = run()
        expected = {
            "min_area_ratio": MIN_AREA_RATIO,
            "max_area_ratio": MAX_AREA_RATIO,
            "max_edge_stretch": MAX_EDGE_STRETCH,
        }
        self.assertEqual(expected, result.thresholds.to_dict())
        self.assertTrue(calls)
        self.assertTrue(all(call == expected for call in calls))

        setup = ((0.0, 0.0), (4.0, 0.0), (0.0, 3.0))
        triangle = ((0, 1, 2),)
        boundaries = (
            ({"min_area_ratio": 1.0}, "minimum_area_ratio"),
            ({"max_area_ratio": 1.0}, "maximum_area_ratio"),
            ({"max_edge_stretch": 1.0}, "maximum_edge_stretch"),
        )
        for thresholds, reason in boundaries:
            with self.subTest(reason=reason):
                self.assertIn(
                    reason,
                    measure_deformation(setup, setup, triangle, **thresholds).reasons,
                )


class FailingActionProbeTests(unittest.TestCase):
    def test_first_failure_at_five_degrees_caps_continuous_safe_range(self) -> None:
        result = run(early_failure_attachment())

        for sweep, angle in ((result.distal_negative, -5), (result.distal_positive, 5)):
            with self.subTest(angle=angle):
                self.assertEqual(0, sweep.max_contiguous_magnitude_deg)
                self.assertIsNotNone(sweep.first_failure)
                assert sweep.first_failure is not None
                self.assertEqual(angle, sweep.first_failure.angle_deg)
                self.assertEqual("rejected", sweep.first_failure.status)
                self.assertTrue(sweep.first_failure.reasons)
                # The full sweep remains evidence-bearing after the first failure.
                self.assertEqual(27, len(sweep.samples))
                self.assertEqual(135, abs(sweep.samples[-1].angle_deg))

    def test_proximal_rigid_rejection_is_a_hard_error(self) -> None:
        call_count = 0

        def reject_second(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            assessment = measure_deformation(*args, **kwargs)
            if call_count == 2:
                return replace(
                    assessment,
                    status="rejected",
                    reasons=("maximum_edge_stretch",),
                )
            return assessment

        with patch(
            "autospine_workbench.mesh_action_probe.measure_deformation",
            side_effect=reject_second,
        ), self.assertRaisesRegex(MeshActionProbeError, "proximal rigid -90"):
            run()

    def test_invalid_step_empty_mesh_and_non_two_bone_weights_fail(self) -> None:
        for step in (0, -5, 10, 5.0, True):
            with self.subTest(step=step), self.assertRaisesRegex(
                MeshActionProbeError, "pinned 5"
            ):
                run(step_degrees=step)

        empty = passing_attachment()
        empty.update(vertices=[], weights=[])
        with self.assertRaisesRegex(MeshActionProbeError, "non-empty"):
            run(empty)

        one_bone = passing_attachment()
        one_bone["weights"] = [[influence(PROXIMAL)] for _ in one_bone["vertices"]]
        with self.assertRaisesRegex(MeshActionProbeError, "both hinge bones"):
            run(one_bone)

        third = bones() + [bone("other")]
        wrong = passing_attachment()
        wrong["weights"][1] = [influence("other")]
        with self.assertRaisesRegex(MeshActionProbeError, "only the two"):
            run(wrong, third)

    def test_unknown_or_wrong_hierarchy_bones_fail(self) -> None:
        with self.assertRaisesRegex(MeshActionProbeError, "unknown hinge bone"):
            run_mesh_action_probe(
                bones(), passing_attachment(),
                proximal_bone_id="missing", distal_bone_id=DISTAL,
            )

        wrong = bones()
        wrong[1]["parent"] = None
        with self.assertRaisesRegex(MeshActionProbeError, "directly parent"):
            run(rig_bones=wrong)

    def test_influence_fields_bones_weights_and_sums_are_strict(self) -> None:
        exact = passing_attachment()
        exact["weights"][0][0]["unexpected"] = True
        with self.assertRaisesRegex(MeshActionProbeError, "fields must be exact"):
            run(exact)

        duplicate = passing_attachment()
        duplicate["weights"][0] = [
            influence(PROXIMAL, 0.5), influence(PROXIMAL, 0.5),
        ]
        with self.assertRaisesRegex(MeshActionProbeError, "bones must be unique"):
            run(duplicate)

        for invalid in (0.0, -0.1, math.nan, math.inf, True):
            changed = passing_attachment()
            changed["weights"][1][0]["weight"] = invalid
            with self.subTest(invalid=invalid), self.assertRaisesRegex(
                MeshActionProbeError, "finite and positive"
            ):
                run(changed)

        bad_sum = passing_attachment()
        bad_sum["weights"][0] = [
            influence(PROXIMAL, 0.4), influence(DISTAL, 0.5),
        ]
        with self.assertRaisesRegex(MeshActionProbeError, "sum to one"):
            run(bad_sum)

    def test_nan_degenerate_and_bad_topology_fail_closed(self) -> None:
        non_finite = passing_attachment()
        non_finite["vertices"][1][0] = math.nan
        with self.assertRaisesRegex(MeshActionProbeError, "finite"):
            run(non_finite)

        degenerate = passing_attachment()
        degenerate["vertices"] = [[10, 0], [20, 0], [30, 0]]
        with self.assertRaisesRegex(MeshActionProbeError, "positive area"):
            run(degenerate)

        malformed = passing_attachment()
        malformed["triangles"] = [0, 1]
        with self.assertRaisesRegex(MeshActionProbeError, "triples"):
            run(malformed)

        outside = passing_attachment()
        outside["triangles"] = [0, 1, 8]
        with self.assertRaisesRegex(MeshActionProbeError, "outside vertex"):
            run(outside)

    def test_initial_setup_threshold_failure_is_a_hard_error(self) -> None:
        thin = passing_attachment()
        thin["vertices"] = [[0, 0], [1, 0], [1, 0.0001]]
        with self.assertRaisesRegex(MeshActionProbeError, "setup pose failed"):
            run(thin)


if __name__ == "__main__":
    unittest.main()
