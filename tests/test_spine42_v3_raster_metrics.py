"""Pure P10.7b PNG-byte attachment raster metric tests."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.png_rgba import RgbaImage, encode_rgba_png  # noqa: E402
from autospine_workbench.resolved_project import canonical_sha256  # noqa: E402
from autospine_workbench.spine42_v3_raster_metrics import (  # noqa: E402
    Spine42V3RasterMetricsError,
    canonical_spine42_v3_raster_metrics_bytes,
    compute_spine42_v3_raster_metrics,
    spine42_v3_raster_metrics_sha256,
)
from autospine_workbench.spine42_v3_runtime_plan import (  # noqa: E402
    PLAN_FORMAT,
)
from autospine_workbench.spine42_v3_runtime_profile import (  # noqa: E402
    PLAN_HASH_DOMAIN,
    spine42_v3_runtime_profile_sha256,
)


WIDTH = HEIGHT = 4


def _artifact(artifact_id, kind, slot=None, attachment=None):
    return {
        "artifact_id": artifact_id,
        "path": f"{artifact_id}.png",
        "kind": kind,
        "case_id": "setup",
        "slot_id": slot,
        "attachment_id": attachment,
        "background": "#20242aff" if kind == "opaque_composite" else "#00000000",
    }


def _plan():
    attachments = [
        {"ordinal": 0, "slot_id": "slot-a", "attachment_id": "part-a"},
        {"ordinal": 1, "slot_id": "slot-b", "attachment_id": "part-b"},
    ]
    artifacts = [
        _artifact("case-000.opaque", "opaque_composite"),
        _artifact("case-000.alpha", "transparent_composite"),
        _artifact("case-000.isolate-00", "attachment_isolate", "slot-a", "part-a"),
        _artifact("case-000.isolate-01", "attachment_isolate", "slot-b", "part-b"),
    ]
    body = {
        "format": PLAN_FORMAT,
        "format_version": 1,
        "profile_sha256": spine42_v3_runtime_profile_sha256(),
        "source": {
            "project_id": "sample", "clip_id": "idle",
            "skeleton_json_sha256": "1" * 64, "bundle_sha256": "2" * 64,
        },
        "runtime": {},
        "capture": {
            "viewport": {"width": WIDTH, "height": HEIGHT},
            "device_pixel_ratio": 1,
        },
        "sampled_scope": {
            "kind": "bounded-discrete-samples-only",
            "sampled_ticks": [0], "continuous_time_safety_claimed": False,
            "unsampled_ticks_covered": False,
        },
        "attachments": attachments,
        "cases": [{
            "case_id": "setup", "ordinal": 0, "animation": None,
            "tick": 0, "time_seconds": 0.0,
            "selection_reasons": ["setup"],
            "artifact_ids": [row["artifact_id"] for row in artifacts],
        }],
        "artifacts": artifacts,
    }
    return {
        **body,
        "capture_plan_sha256": canonical_sha256({
            "domain": PLAN_HASH_DOMAIN, **body,
        }),
    }


def _png(alpha_positions, *, opaque=False, alpha_value=255):
    pixels = bytearray(WIDTH * HEIGHT * 4)
    for index in range(WIDTH * HEIGHT):
        pixels[index * 4:index * 4 + 3] = b"\x10\x20\x30"
        if opaque or index in alpha_positions:
            pixels[index * 4 + 3] = 255 if opaque else alpha_value
    return encode_rgba_png(RgbaImage(WIDTH, HEIGHT, bytes(pixels)))


def _passing_artifacts():
    return {
        "case-000.opaque": _png(set(), opaque=True),
        "case-000.alpha": _png({5, 10}, alpha_value=1),
        "case-000.isolate-00": _png({5}, alpha_value=1),
        "case-000.isolate-01": _png({10}, alpha_value=1),
    }


def _rehash(plan):
    body = deepcopy(plan)
    body.pop("capture_plan_sha256", None)
    plan["capture_plan_sha256"] = canonical_sha256({
        "domain": PLAN_HASH_DOMAIN, **body,
    })


class Spine42V3RasterMetricsTests(unittest.TestCase):
    def test_binary_or_matches_transparent_composite_at_alpha_one(self):
        first = compute_spine42_v3_raster_metrics(
            _plan(), _passing_artifacts()
        )
        second = compute_spine42_v3_raster_metrics(
            _plan(), _passing_artifacts()
        )

        self.assertEqual(first, second)
        self.assertTrue(first["summary"]["all_sampled_cases_passed"])
        case = first["cases"][0]
        self.assertEqual(0, case["missing_pixels"])
        self.assertEqual(0, case["extra_pixels"])
        self.assertEqual(0, case["xor_pixels"])
        self.assertEqual(0, case["boundary_xor_pixels"])
        self.assertEqual(0, case["clipped_boundary_pixels"])
        self.assertTrue(all(
            row["nonempty"] for row in case["attachment_isolates"]
        ))
        self.assertEqual(
            first["raster_metrics_sha256"],
            spine42_v3_raster_metrics_sha256(first),
        )
        self.assertFalse(first["semantics"]["continuous_time_safety_claimed"])
        self.assertFalse(first["semantics"]["human_visual_approval_claimed"])

    def test_missing_extra_xor_and_boundary_are_recomputed_from_png_bytes(self):
        artifacts = _passing_artifacts()
        artifacts["case-000.alpha"] = _png({5})
        artifacts["case-000.isolate-00"] = _png({6})
        result = compute_spine42_v3_raster_metrics(_plan(), artifacts)
        case = result["cases"][0]

        self.assertEqual(1, case["missing_pixels"])
        self.assertEqual(2, case["extra_pixels"])
        self.assertEqual(3, case["xor_pixels"])
        self.assertGreater(case["boundary_xor_pixels"], 0)
        self.assertFalse(case["passed"])
        self.assertIn(
            "isolate_union_differs_from_transparent_composite",
            case["reason_codes"],
        )

    def test_clipped_empty_and_nonopaque_failures_are_explicit(self):
        artifacts = _passing_artifacts()
        artifacts["case-000.alpha"] = _png({0})
        artifacts["case-000.isolate-00"] = _png({0})
        artifacts["case-000.isolate-01"] = _png(set())
        artifacts["case-000.opaque"] = _png({0})
        case = compute_spine42_v3_raster_metrics(
            _plan(), artifacts
        )["cases"][0]

        self.assertEqual(1, case["clipped_boundary_pixels"])
        self.assertFalse(case["attachment_isolates"][1]["nonempty"])
        self.assertGreater(case["opaque_composite_nonopaque_pixels"], 0)
        self.assertEqual({
            "transparent_composite_touches_capture_boundary",
            "attachment_isolate_is_empty",
            "opaque_composite_has_nonopaque_pixels",
        }, set(case["reason_codes"]))

    def test_png_inventory_dimensions_and_types_are_strict(self):
        cases = []
        missing = _passing_artifacts()
        missing.pop("case-000.alpha")
        cases.append(missing)
        extra = _passing_artifacts()
        extra["extra"] = _png(set())
        cases.append(extra)
        nonbytes = _passing_artifacts()
        nonbytes["case-000.alpha"] = bytearray(nonbytes["case-000.alpha"])
        cases.append(nonbytes)
        wrong_size = _passing_artifacts()
        wrong_size["case-000.alpha"] = encode_rgba_png(
            RgbaImage(3, 4, bytes(3 * 4 * 4))
        )
        cases.append(wrong_size)
        for index, invalid in enumerate(cases):
            with self.subTest(index=index), self.assertRaises(
                Spine42V3RasterMetricsError
            ):
                compute_spine42_v3_raster_metrics(_plan(), invalid)

    def test_plan_artifact_binding_and_metrics_hash_tamper_fail(self):
        plan = _plan()
        plan["artifacts"][0]["path"] = "renamed.png"
        _rehash(plan)
        with self.assertRaisesRegex(
            Spine42V3RasterMetricsError, "artifact row"
        ):
            compute_spine42_v3_raster_metrics(plan, _passing_artifacts())

        metrics = compute_spine42_v3_raster_metrics(
            _plan(), _passing_artifacts()
        )
        self.assertEqual(
            canonical_spine42_v3_raster_metrics_bytes(metrics),
            canonical_spine42_v3_raster_metrics_bytes(deepcopy(metrics)),
        )
        metrics["cases"][0]["missing_pixels"] = 1
        with self.assertRaisesRegex(Spine42V3RasterMetricsError, "digest"):
            spine42_v3_raster_metrics_sha256(metrics)


if __name__ == "__main__":
    unittest.main()
