"""Parameterized, deterministic two-bone weight tests."""

from __future__ import annotations

import json
import math
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.two_bone_weights import (  # noqa: E402
    UINT16_MAX,
    TwoBoneWeightError,
    build_two_bone_weights,
    require_direct_child,
    to_rigir_weights,
)


STRAIGHT_VERTICES = (
    (0, 0),
    (24, 0),
    (32, 0),
    (40, 0),
    (48, 0),
    (56, 0),
    (80, 0),
)


def build_straight(vertices=STRAIGHT_VERTICES, **changes):
    values = {
        "proximal_bone_id": "upper",
        "distal_bone_id": "lower",
        "proximal_origin_xy": (0, 0),
        "proximal_endpoint_xy": (40, 0),
        "distal_origin_xy": (40, 0),
        "distal_endpoint_xy": (80, 0),
        "grid_step_px": 8,
        "blend_fraction": 0.20,
    }
    values.update(changes)
    return build_two_bone_weights(vertices, **values)


class TwoBoneWeightGeometryTests(unittest.TestCase):
    def test_straight_chain_has_all_classes_and_pinned_smoothstep_values(self) -> None:
        weights = build_straight()

        self.assertEqual(16.0, weights.half_band_px)
        self.assertEqual((0, 0, 0, 0, 1, 1, 1), weights.segment_indices)
        self.assertEqual(
            (0, 0, 10240, 32768, 55295, UINT16_MAX, UINT16_MAX),
            weights.distal_weights_u16,
        )
        self.assertEqual(
            tuple(float(value) for value in (0, 24, 32, 40, 48, 56, 80)),
            weights.arc_lengths_px,
        )

    def test_mirrored_chain_produces_identical_directed_weights(self) -> None:
        mirrored = build_two_bone_weights(
            tuple((80 - x, y) for x, y in STRAIGHT_VERTICES),
            proximal_bone_id="upper",
            distal_bone_id="lower",
            proximal_origin_xy=(80, 0),
            proximal_endpoint_xy=(40, 0),
            distal_origin_xy=(40, 0),
            distal_endpoint_xy=(0, 0),
        )
        self.assertEqual(
            build_straight().distal_weights_u16,
            mirrored.distal_weights_u16,
        )
        self.assertEqual(build_straight().arc_lengths_px, mirrored.arc_lengths_px)

    def test_setup_bent_chain_uses_two_segment_arc_length(self) -> None:
        vertices = (
            (0, 0), (24, 0), (32, 0), (40, 0),
            (40, 8), (40, 16), (40, 40),
        )
        result = build_two_bone_weights(
            vertices,
            proximal_bone_id="upper",
            distal_bone_id="lower",
            proximal_origin_xy=(0, 0),
            proximal_endpoint_xy=(40, 0),
            distal_origin_xy=(40, 0),
            distal_endpoint_xy=(40, 40),
        )
        self.assertEqual(build_straight().distal_weights_u16, result.distal_weights_u16)
        self.assertEqual((0, 0, 0, 0, 1, 1, 1), result.segment_indices)

    def test_equal_distance_tie_chooses_proximal_segment_stably(self) -> None:
        vertices = (
            (0, 0), (24, 0), (32, 0), (32, 8),
            (40, 0), (40, 8), (40, 16), (40, 40),
        )
        result = build_two_bone_weights(
            vertices,
            proximal_bone_id="upper",
            distal_bone_id="lower",
            proximal_origin_xy=(0, 0),
            proximal_endpoint_xy=(40, 0),
            distal_origin_xy=(40, 0),
            distal_endpoint_xy=(40, 40),
        )
        self.assertEqual(0, result.segment_indices[3])
        self.assertEqual(32.0, result.arc_lengths_px[3])

    def test_chain_endpoints_quantize_to_exclusive_influences(self) -> None:
        result = build_straight()
        rigir = to_rigir_weights(result)

        self.assertEqual(0, result.distal_weights_u16[0])
        self.assertEqual(UINT16_MAX, result.distal_weights_u16[-1])
        self.assertEqual([{"bone": "upper", "weight": 1.0}], rigir[0])
        self.assertEqual([{"bone": "lower", "weight": 1.0}], rigir[-1])


class TwoBoneWeightContractTests(unittest.TestCase):
    def test_round_half_up_and_rigir_canonical_sums(self) -> None:
        result = build_straight()
        self.assertEqual(32768, result.distal_weights_u16[3])

        rigir = to_rigir_weights(result)
        for influences in rigir:
            self.assertTrue(all(item["weight"] > 0 for item in influences))
            self.assertEqual(1.0, sum(item["weight"] for item in influences))
        blended = rigir[3]
        self.assertEqual("upper", blended[0]["bone"])
        self.assertEqual(32767 / UINT16_MAX, blended[0]["weight"])
        self.assertEqual(1.0 - blended[0]["weight"], blended[1]["weight"])

    def test_repeated_input_is_value_and_json_deterministic(self) -> None:
        first = build_straight()
        second = build_straight()
        self.assertEqual(first, second)
        serialize = lambda value: json.dumps(  # noqa: E731
            value, ensure_ascii=True, sort_keys=True, separators=(",", ":")
        )
        self.assertEqual(serialize(to_rigir_weights(first)), serialize(to_rigir_weights(second)))

    def test_direct_child_hierarchy_check_is_separate_and_fail_closed(self) -> None:
        bones = [
            {"id": "root", "parent": None},
            {"id": "upper", "parent": "root"},
            {"id": "lower", "parent": "upper"},
        ]
        require_direct_child(
            bones, proximal_bone_id="upper", distal_bone_id="lower"
        )
        for changed, message in (
            ([*bones[:2], {"id": "lower", "parent": "root"}], "direct child"),
            (bones[:2], "missing bone"),
            ([*bones, {"id": "lower", "parent": "upper"}], "duplicate"),
        ):
            with self.subTest(message=message), self.assertRaisesRegex(
                TwoBoneWeightError, message
            ):
                require_direct_child(
                    changed, proximal_bone_id="upper", distal_bone_id="lower"
                )

    def test_invalid_chain_geometry_and_parameters_fail_closed(self) -> None:
        cases = (
            ({"distal_origin_xy": (40.001, 0)}, "equal distal origin"),
            ({"proximal_endpoint_xy": (0, 0), "distal_origin_xy": (0, 0)}, "length"),
            ({"grid_step_px": 20}, "45 percent"),
            ({"blend_fraction": 0}, "blend fraction"),
            ({"proximal_bone_id": "lower"}, "must differ"),
            ({"proximal_bone_id": "unsafe id"}, "id is invalid"),
            ({"distal_bone_id": "a" * 129}, "id is invalid"),
        )
        for changes, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(
                TwoBoneWeightError, message
            ):
                build_straight(**changes)
        with self.assertRaisesRegex(TwoBoneWeightError, "finite numbers"):
            build_straight(((0, math.nan), *STRAIGHT_VERTICES[1:]))

    def test_missing_weight_class_or_two_grid_blend_span_fails_closed(self) -> None:
        with self.assertRaisesRegex(TwoBoneWeightError, "proximal-only"):
            build_straight(((32, 0), (40, 0), (48, 0)))
        with self.assertRaisesRegex(TwoBoneWeightError, "two grid steps"):
            build_straight(((0, 0), (24, 0), (40, 0), (56, 0), (80, 0)))

    def test_non_object_conversion_is_rejected(self) -> None:
        with self.assertRaisesRegex(TwoBoneWeightError, "TwoBoneWeights"):
            to_rigir_weights(None)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
