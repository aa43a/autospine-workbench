"""Calibration CLI retains evidence and never applies blocked transforms."""

from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tests import test_benchmark_mapping_cli as fixture_module
from autospine_workbench.benchmark.artifacts import publish_report
from autospine_workbench.benchmark.mapping_calibration_store import read_mapping_calibration
from autospine_workbench.resolved_project import canonical_sha256


class CalibrationCliTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture_module.MappingCliTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.candidate, _ = self.fixture.prepare()
        # Synthetic correspondences exercise fitting only, never real annotation.
        self.anchors = {"schema": "autospine.benchmark-mapping-anchors/v1", "authority": "none",
                        "candidate_sha256": canonical_sha256(self.candidate), "anchors": [
                            {"id": "a", "png": [10, 10], "psd": [30, 25]},
                            {"id": "b", "png": [50, 100], "psd": [110, 160]},
                            {"id": "c", "png": [100, 50], "psd": [210, 85]}]}
        self.manifest_path = self.root / "manifest.json"
        self.evidence_path = self.root / "evidence.json"
        self.manifest_path.write_text(json.dumps(self.fixture.manifest), encoding="utf-8")
        self.evidence_path.write_text(json.dumps(self.fixture.evidence), encoding="utf-8")

    def invoke(self):
        path = self.root / "anchors.json"
        path.write_text(json.dumps(self.anchors), encoding="utf-8")
        return self.fixture.fixture.invoke(
            "mapping-review", "--manifest", self.manifest_path, "--evidence", self.evidence_path,
            "--workspace", self.root, "--character", self.fixture.psd["path"], "--anchors", path,
            "--calibration-output", self.root / "calibration.json", "--html", self.root / "calibrated.html")

    def test_fit_publishes_exact_closure_and_new_candidate(self):
        code, fitted = self.invoke()
        self.assertEqual(code, 0)
        self.assertEqual(fitted["basis"], "explicit_transform_draft")
        self.assertEqual(fitted["source_to_psd_transform"]["scale"], [2.0, 1.5])
        report = json.loads((self.root / "calibration.json").read_text(encoding="utf-8"))
        self.assertEqual(report["status"], "needs_review")
        self.assertEqual(read_mapping_calibration(self.fixture.fixture.state, self.fixture.manifest,
                                                 canonical_sha256(report)), report)
        self.assertEqual(self.invoke(), (code, fitted))
        self.assertIn("均方根误差", (self.root / "calibrated.html").read_text(encoding="utf-8"))
        self.assertIn("不随下方手动变换更新", (self.root / "calibrated.html").read_text(encoding="utf-8"))

    def test_high_residual_is_diagnostic_not_applied(self):
        self.anchors["anchors"][1]["psd"][0] = 900
        code, report = self.invoke()
        self.assertEqual(code, 2)
        self.assertEqual(report["status"], "blocked")
        self.assertIsNone(report["fitted_candidate"])
        self.assertGreater(report["max_residual_relative_height"], 0.03)
        self.assertIn("继续显示原候选", (self.root / "calibrated.html").read_text(encoding="utf-8"))

    def test_stale_anchors_create_no_output(self):
        self.anchors["candidate_sha256"] = "0" * 64
        code, result = self.invoke()
        self.assertEqual(code, 1)
        self.assertEqual(result["status"], "blocked")
        self.assertFalse((self.root / "calibrated.html").exists())
        self.assertFalse((self.root / "calibration.json").exists())

    def test_report_rehash_cannot_forge_residuals(self):
        self.invoke()
        report = json.loads((self.root / "calibration.json").read_text(encoding="utf-8"))
        forged = deepcopy(report)
        forged["rmse_px"] = 4
        digest = publish_report(self.fixture.fixture.state, self.fixture.manifest["dataset_id"],
                                "mapping-calibrations", forged)
        with self.assertRaises(ValueError):
            read_mapping_calibration(self.fixture.fixture.state, self.fixture.manifest, digest)


if __name__ == "__main__":
    unittest.main()
