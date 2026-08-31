from __future__ import annotations

from copy import deepcopy
import json
import math
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (ROOT, SRC):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from autospine_workbench.dynamic_viewport_fit import (
    DynamicViewportFit,
    DynamicViewportFitError,
    compile_dynamic_viewport_fit,
    require_exact_dynamic_viewport_fit,
)
from autospine_workbench.dynamic_viewport_fit_validation import (
    DynamicViewportFitValidationError,
    dynamic_viewport_fit_sha256,
    require_dynamic_viewport_fit,
)

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - optional test dependency
    Draft202012Validator = None


ROOT = Path(__file__).resolve().parents[1]


class DynamicViewportFitTests(unittest.TestCase):
    def test_sampled_geometry_fits_overflow_without_structural_failure(self):
        result = compile_dynamic_viewport_fit(
            sampled_geometry=_samples(),
            output_viewport={"width": 640, "height": 480},
            margin_px=20,
        )
        self.assertIsInstance(result, DynamicViewportFit)
        document = result.document
        self.assertEqual(
            {"min_xy": [-100.0, -50.0], "max_xy": [1100.0, 700.0],
             "size": [1200.0, 750.0], "center_xy": [500.0, 325.0]},
            document["motion_envelope"],
        )
        self.assertEqual(0.5, document["transform"]["uniform_scale"])
        self.assertEqual([70.0, 77.5], document["transform"]["translation_xy"])
        self.assertEqual("fitted", document["fit_status"])
        self.assertFalse(document["semantics"][
            "source_canvas_overflow_is_rig_structural_failure"
        ])
        self.assertEqual("none", document["semantics"]["authority"])
        self.assertEqual("blocked", document["release_gate"]["status"])

    def test_generic_bounds_allow_scale_up_and_asymmetric_margin(self):
        result = compile_dynamic_viewport_fit(
            point_bounds={"min_xy": [10, 20], "max_xy": [110, 70]},
            output_viewport={"width": 400, "height": 300},
            margin_px={"left": 20, "right": 20, "top": 30, "bottom": 10},
        )
        document = result.document
        self.assertEqual("point_bounds", document["source"]["kind"])
        self.assertEqual(3.6, document["transform"]["uniform_scale"])
        self.assertEqual([-16.0, -2.0], document["transform"]["translation_xy"])
        self.assertEqual([20.0, 70.0], document["fitted_envelope"]["min_xy"])
        self.assertEqual([380.0, 250.0], document["fitted_envelope"]["max_xy"])

    def test_input_order_is_canonical_and_result_is_detached(self):
        first = _samples()
        second = list(reversed(deepcopy(first)))
        for sample in second:
            sample["attachments"].reverse()
        left = compile_dynamic_viewport_fit(
            sampled_geometry=first,
            output_viewport={"width": 640, "height": 480}, margin_px=20,
        )
        right = compile_dynamic_viewport_fit(
            sampled_geometry=second,
            output_viewport={"width": 640, "height": 480}, margin_px=20,
        )
        self.assertEqual(left.sha256, right.sha256)
        first[0]["attachments"][0]["posed_vertices_xy"][0][0] = 999
        self.assertEqual(-100.0, left.document["motion_envelope"]["min_xy"][0])
        detached = left.document
        detached["fit_status"] = "indeterminate"
        self.assertEqual("fitted", left.document["fit_status"])

    def test_degenerate_point_and_line_remain_finite(self):
        point = compile_dynamic_viewport_fit(
            point_bounds={"min_xy": [8, -3], "max_xy": [8, -3]},
            output_viewport={"width": 200, "height": 100}, margin_px=10,
        ).document
        self.assertEqual(1.0, point["transform"]["uniform_scale"])
        self.assertEqual([92.0, 53.0], point["transform"]["translation_xy"])
        line = compile_dynamic_viewport_fit(
            point_bounds={"min_xy": [0, 0], "max_xy": [0, 40]},
            output_viewport={"width": 200, "height": 100}, margin_px=10,
        ).document
        self.assertEqual(2.0, line["transform"]["uniform_scale"])
        self.assertTrue(all(math.isfinite(value) for value in (
            line["transform"]["uniform_scale"],
            *line["transform"]["translation_xy"],
        )))

    def test_bounded_extreme_envelope_still_fits(self):
        document = compile_dynamic_viewport_fit(
            point_bounds={
                "min_xy": [-1_000_000_000, -1_000_000_000],
                "max_xy": [1_000_000_000, 1_000_000_000],
            },
            output_viewport={"width": 1, "height": 1},
        ).document
        self.assertEqual(0.0000000005, document["transform"]["uniform_scale"])
        self.assertEqual("fitted", document["fit_status"])
        self.assertEqual([0.0, 0.0], document["fitted_envelope"]["min_xy"])
        self.assertEqual([1.0, 1.0], document["fitted_envelope"]["max_xy"])

    def test_malformed_nonfinite_and_ambiguous_inputs_fail_closed(self):
        cases = [
            {"sampled_geometry": _samples(), "point_bounds": {
                "min_xy": [0, 0], "max_xy": [1, 1],
            }},
            {"point_bounds": {"min_xy": [2, 0], "max_xy": [1, 1]}},
            {"point_bounds": {"min_xy": [0, 0], "max_xy": [float("nan"), 1]}},
        ]
        for kwargs in cases:
            with self.subTest(kwargs=kwargs), self.assertRaises(DynamicViewportFitError):
                compile_dynamic_viewport_fit(
                    **kwargs, output_viewport={"width": 100, "height": 100},
                )
        duplicate = _samples()
        duplicate[1]["tick"] = duplicate[0]["tick"]
        with self.assertRaisesRegex(DynamicViewportFitError, "unique"):
            compile_dynamic_viewport_fit(
                sampled_geometry=duplicate,
                output_viewport={"width": 100, "height": 100},
            )
        with self.assertRaisesRegex(DynamicViewportFitError, "margin"):
            compile_dynamic_viewport_fit(
                point_bounds={"min_xy": [0, 0], "max_xy": [1, 1]},
                output_viewport={"width": 100, "height": 100}, margin_px=50,
            )

    def test_validator_hash_and_exact_replay_reject_tampering(self):
        kwargs = {
            "point_bounds": {"min_xy": [-20, 10], "max_xy": [180, 210]},
            "output_viewport": {"width": 320, "height": 240},
            "margin_px": 12,
        }
        result = compile_dynamic_viewport_fit(**kwargs)
        require_dynamic_viewport_fit(result.document)
        self.assertEqual(result.sha256, dynamic_viewport_fit_sha256(result.document))
        self.assertEqual(result.sha256, require_exact_dynamic_viewport_fit(
            result.document, **kwargs,
        ))
        for mutate in (
            lambda row: row["transform"].__setitem__("uniform_scale", 2.0),
            lambda row: row["semantics"].__setitem__(
                "source_canvas_overflow_is_rig_structural_failure", True,
            ),
            lambda row: row["source"].__setitem__("sample_count", 1),
            lambda row: row.__setitem__("unexpected", True),
        ):
            changed = result.document
            mutate(changed)
            with self.subTest(changed=changed), self.assertRaises(
                DynamicViewportFitValidationError
            ):
                require_dynamic_viewport_fit(changed)
        changed = result.document
        changed["source"]["evidence_sha256"] = "0" * 64
        require_dynamic_viewport_fit(changed)
        with self.assertRaisesRegex(DynamicViewportFitError, "exact replay"):
            require_exact_dynamic_viewport_fit(changed, **kwargs)

    @unittest.skipIf(Draft202012Validator is None, "jsonschema is optional")
    def test_json_schema_accepts_candidate_and_rejects_authority(self):
        schema = json.loads((
            ROOT / "schemas" / "dynamic-viewport-fit-v1.schema.json"
        ).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        document = compile_dynamic_viewport_fit(
            sampled_geometry=_samples(),
            output_viewport={"width": 640, "height": 480}, margin_px=20,
        ).document
        validator.validate(document)
        document["semantics"]["authority"] = "human"
        self.assertFalse(validator.is_valid(document))

    def test_new_production_files_stay_below_300_lines(self):
        for name in (
            "dynamic_viewport_fit.py", "dynamic_viewport_fit_inputs.py",
            "dynamic_viewport_fit_validation.py",
        ):
            lines = (ROOT / "src" / "autospine_workbench" / name).read_text(
                encoding="utf-8"
            ).splitlines()
            self.assertLessEqual(len(lines), 300, name)


def _samples():
    return [
        {
            "tick": 20,
            "attachments": [
                {"attachment_id": "layer-body",
                 "posed_vertices_xy": [[50, 60], [1100, 700]]},
                {"attachment_id": "layer-hair",
                 "posed_vertices_xy": [[0, -50], [300, 100]]},
            ],
        },
        {
            "tick": 0,
            "attachments": [
                {"attachment_id": "layer-body",
                 "posed_vertices_xy": [[-100, 0], [900, 600]]},
            ],
        },
    ]


if __name__ == "__main__":
    unittest.main()
