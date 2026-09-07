"""Anchor calibration rejects stale evidence and never approves a mapping."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from autospine_workbench.benchmark.mapping import build_mapping_candidate, validate_mapping_candidate
from autospine_workbench.benchmark.mapping_anchors import (
    SCHEMA, fit_mapping_anchors, validate_mapping_anchors, validate_mapping_calibration,
)
from autospine_workbench.benchmark.validation import BenchmarkError
from autospine_workbench.resolved_project import canonical_sha256


class MappingAnchorTests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads((ROOT / "docs/benchmark/manifest-frozen-v1.json").read_text("utf-8"))
        row = next(row for row in self.manifest["characters"] if row["dataset_split"] == "development")
        self.candidate = build_mapping_candidate(self.manifest, row["id"], row["psd_candidates"][0]["source"]["sha256"])
        self.anchors = {"schema": SCHEMA, "authority": "none",
                        "candidate_sha256": canonical_sha256(self.candidate), "anchors": [
                            {"id": str(index), "png": point, "psd": [2 * point[0] + 10, point[1] / 2 + 30]}
                            for index, point in enumerate(([10, 20], [50, 90], [100, 60]))]}

    def test_exact_fit_is_pure_deterministic_and_manifest_valid(self):
        before = deepcopy((self.candidate, self.anchors))
        report = fit_mapping_anchors(self.candidate, self.anchors)
        self.assertEqual(report, fit_mapping_anchors(self.candidate, self.anchors))
        self.assertEqual(report["status"], "needs_review")
        self.assertEqual(report["transform"]["scale"], [2, .5])
        for actual, expected in zip(report["transform"]["translation"], [10, 30]):
            self.assertAlmostEqual(actual, expected)
        self.assertAlmostEqual(report["rmse_px"], 0)
        self.assertEqual(report["fitted_candidate"]["authority"], "none")
        self.assertTrue(report["fitted_candidate"]["review_required"])
        validate_mapping_candidate(self.manifest, report["fitted_candidate"])
        self.assertEqual(before, (self.candidate, self.anchors))

    def test_reflection_and_two_points_remain_review_only(self):
        self.anchors["anchors"] = self.anchors["anchors"][:2]
        for point in self.anchors["anchors"]:
            point["psd"][0] = 500 - point["png"][0]
        report = fit_mapping_anchors(self.candidate, self.anchors)
        self.assertEqual(report["transform"]["scale"][0], -1)
        self.assertIn("underconstrained_validation", report["reason_codes"])
        self.assertEqual(report["status"], "needs_review")

    def test_high_residual_blocks_application_but_retains_diagnostics(self):
        self.anchors["anchors"][1]["psd"][0] += 400
        report = fit_mapping_anchors(self.candidate, self.anchors)
        self.assertEqual(report["status"], "blocked")
        self.assertIn("anchor_residual_high", report["reason_codes"])
        self.assertIsNone(report["fitted_candidate"])
        self.assertGreater(report["max_residual_relative_height"], .03)
        self.assertEqual(len(report["residuals"]), 3)

    def test_degenerate_axis_and_subpixel_span_block(self):
        for span in (0, .5):
            points = deepcopy(self.anchors)
            for index, point in enumerate(points["anchors"]):
                point["png"][0] = 20 + index * span / 2
            report = fit_mapping_anchors(self.candidate, points)
            self.assertEqual(report["reason_codes"], ["anchor_span_insufficient"])
            self.assertIsNone(report["transform"])

    def test_zero_covariance_blocks_singular_transform(self):
        for point, x, target in zip(self.anchors["anchors"], [10, 20, 30], [10, 30, 10]):
            point["png"][0], point["psd"][0] = x, target
        report = fit_mapping_anchors(self.candidate, self.anchors)
        self.assertIn("anchor_transform_singular", report["reason_codes"])

    def test_known_noisy_fit_reports_measured_error_not_confidence(self):
        for point, x, target in zip(self.anchors["anchors"], [10, 20, 30], [10, 30, 20]):
            point["png"][0], point["psd"][0] = x, target
        report = fit_mapping_anchors(self.candidate, self.anchors)
        self.assertEqual(report["transform"]["scale"][0], .5)
        self.assertEqual([row["delta"][0] for row in report["residuals"]], [5, -10, 5])
        self.assertAlmostEqual(report["rmse_px"], 50 ** .5)
        self.assertEqual(report["max_residual_px"], 10)
        self.assertIsNone(report["fitted_candidate"]["confidence"])

    def test_canvas_boundaries_and_maximum_point_count_are_supported(self):
        width, height = self.candidate["png_source"]["canvas"]
        tw, th = self.candidate["psd_source"]["canvas"]
        self.anchors["anchors"] = [{"id": str(i), "png": [width * i / 31, height * i / 31],
                                    "psd": [tw * i / 31, th * i / 31]} for i in range(32)]
        report = fit_mapping_anchors(self.candidate, self.anchors)
        self.assertEqual(report["status"], "needs_review")
        self.assertEqual(len(report["residuals"]), 32)

    def test_invalid_coordinates_ids_counts_and_duplicates_fail(self):
        mutations = [lambda d: d["anchors"].clear(),
                     lambda d: d["anchors"].__imul__(12),
                     lambda d: d["anchors"][0].update(id="bad id"),
                     lambda d: d["anchors"][0].update(id="1"),
                     lambda d: d["anchors"][0].update(png=d["anchors"][1]["png"]),
                     lambda d: d["anchors"][0].update(psd=d["anchors"][1]["psd"])]
        for value in (True, float("nan"), float("inf"), -1, 100001, 10 ** 400):
            mutations.append(lambda d, value=value: d["anchors"][0]["png"].__setitem__(0, value))
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                anchors = deepcopy(self.anchors)
                mutate(anchors)
                with self.assertRaises(BenchmarkError):
                    validate_mapping_anchors(self.candidate, anchors)

    def test_stale_candidate_and_authority_escalation_fail(self):
        for key, value in (("candidate_sha256", "f" * 64), ("authority", "approved"), ("extra", 0)):
            anchors = deepcopy(self.anchors)
            anchors[key] = value
            with self.assertRaises(BenchmarkError):
                validate_mapping_anchors(self.candidate, anchors)

    def test_report_reader_replays_and_rejects_every_derived_change(self):
        report = fit_mapping_anchors(self.candidate, self.anchors)
        self.assertEqual(validate_mapping_calibration(self.candidate, self.anchors, report), report)
        for key, value in (("status", "approved"), ("rmse_px", 1), ("authority", "human"),
                           ("reason_codes", ["override"]), ("algorithm_profile", {}), ("rmse_px", False)):
            edited = deepcopy(report)
            edited[key] = value
            with self.assertRaises(BenchmarkError):
                validate_mapping_calibration(self.candidate, self.anchors, edited)


if __name__ == "__main__":
    unittest.main()
