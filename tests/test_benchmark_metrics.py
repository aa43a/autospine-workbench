"""Benchmark denominators, measured percentiles and explicit audit accuracy."""

from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from autospine_workbench.benchmark.manifest import freeze_split, import_inventory
from autospine_workbench.benchmark.metrics import (
    BenchmarkMetricsError, build_metrics, validate_metrics, validate_observations,
)
from autospine_workbench.resolved_project import canonical_sha256

try:
    from jsonschema import Draft202012Validator
except ImportError:
    Draft202012Validator = None


class BenchmarkMetricsTests(unittest.TestCase):
    def setUp(self):
        inventory = json.loads((ROOT / "docs/benchmark/inventory-2026-09.json").read_text(encoding="utf-8"))
        self.unassigned = import_inventory(inventory)
        labels = ["development"] * 3 + ["visible"] * 4 + ["holdout"] * 3 + ["reserve"] * 10
        self.manifest = freeze_split(self.unassigned, {
            row["id"]: split for row, split in zip(self.unassigned["characters"], labels)
        })
        self.observations = self.empty(self.manifest)

    @staticmethod
    def empty(manifest):
        return {"schema": "autospine.benchmark-observations/v1", "dataset_sha256": canonical_sha256(manifest),
                "code_commit": "a" * 40, "profile": "production_review", "target_version": "4.3.26",
                "authority": "none", "records": []}

    def record(self, index, status="succeeded", **kwargs):
        row = self.manifest["characters"][index]
        return {"character_id": row["id"], "source_sha256": row["source"]["sha256"],
                "status": status, "reason_code": None, "review_seconds": None,
                "auto_adoption_audit": None, **kwargs}

    def test_empty_records_keep_all_twenty_and_unknown_measurements(self):
        result = build_metrics(self.manifest, self.observations)
        self.assertEqual(result["readiness"], "ready")
        for key, expected in (("overall", 20), ("primary", 10), ("reserve", 10)):
            group = result[key]
            self.assertEqual(group["total_characters"], expected)
            self.assertEqual(group["missing_observations"], expected)
            self.assertEqual(group["recorded_characters"], 0)
            self.assertEqual(group["status_counts"], {"succeeded": 0, "blocked": 0, "failed": 0, "not_run": expected})
            self.assertEqual(group["completion_rate"], 0)
            self.assertEqual(group["review_seconds"], {"count": 0, "p50": None, "p90": None})
            self.assertEqual(group["auto_adoption"], {"adopted": None, "checked": None, "correct": None, "accuracy": None, "coverage": None})
        self.assertEqual([result["by_split"][split]["total_characters"]
                          for split in ("development", "visible", "holdout", "reserve")], [3, 4, 3, 10])

    def test_partial_observations_use_complete_primary_denominator_and_weighted_accuracy(self):
        self.observations["records"] = [
            self.record(0, review_seconds=0, auto_adoption_audit={"adopted": 10, "checked": 1, "correct": 1}),
            self.record(1, review_seconds=10),
            self.record(2, "blocked", reason_code="joint_unobservable", review_seconds=20),
            self.record(3, "failed", reason_code="mesh_topology_failure", review_seconds=30,
                        auto_adoption_audit={"adopted": 100, "checked": 99, "correct": 97}),
            self.record(10, review_seconds=999, auto_adoption_audit={"adopted": 1000, "checked": 1000, "correct": 0}),
        ]
        result = build_metrics(self.manifest, self.observations)
        primary = result["primary"]
        self.assertEqual(primary["status_counts"], {"succeeded": 2, "blocked": 1, "failed": 1, "not_run": 6})
        self.assertEqual(primary["completion_rate"], .2)
        self.assertEqual(primary["recorded_characters"], 4)
        self.assertEqual(primary["missing_observations"], 6)
        self.assertEqual(primary["failure_reasons"], {"joint_unobservable": 1, "mesh_topology_failure": 1})
        self.assertEqual(primary["review_seconds"], {"count": 4, "p50": 15, "p90": 27})
        self.assertEqual(primary["auto_adoption"], {"adopted": 110, "checked": 100, "correct": 98, "accuracy": .98, "coverage": None})
        self.assertEqual(result["reserve"]["auto_adoption"]["accuracy"], 0)
        self.assertEqual(result["overall"]["completion_rate"], .15)
        self.assertEqual(result["by_split"]["visible"]["completion_rate"], 0)

    def test_zero_checked_is_unknown_accuracy_and_unrun_records_have_no_outcomes(self):
        self.observations["records"] = [self.record(0, auto_adoption_audit={"adopted": 20, "checked": 0, "correct": 0}), self.record(1, "not_run")]
        group = build_metrics(self.manifest, self.observations)["primary"]
        self.assertIsNone(group["auto_adoption"]["accuracy"])
        self.assertIsNone(group["auto_adoption"]["coverage"])
        self.assertEqual(group["status_counts"]["not_run"], 9)
        self.assertEqual(group["recorded_characters"], 2)
        self.assertEqual(group["missing_observations"], 8)

    def test_unfrozen_dataset_has_no_primary_or_completion_claim(self):
        observations = self.empty(self.unassigned)
        observations["records"] = [self.record(0)]
        result = build_metrics(self.unassigned, observations)
        self.assertEqual(result["readiness"], "not_ready")
        self.assertIsNone(result["primary"])
        self.assertIsNone(result["reserve"])
        self.assertIsNone(result["overall"]["completion_rate"])
        self.assertEqual(result["by_split"]["unassigned"]["total_characters"], 20)
        self.assertTrue(all(group["completion_rate"] is None for group in result["by_split"].values()))

    def test_deterministic_pure_output_exactly_binds_inputs_and_rejects_forged_denominator(self):
        original_manifest, original_observations = deepcopy(self.manifest), deepcopy(self.observations)
        report = build_metrics(self.manifest, self.observations)
        self.assertEqual(report, build_metrics(self.manifest, self.observations))
        self.assertEqual(report["observations_sha256"], canonical_sha256(self.observations))
        self.assertEqual((self.manifest, self.observations), (original_manifest, original_observations))
        self.assertEqual(validate_metrics(self.manifest, self.observations, report), report)
        report["primary"]["completion_rate"] = 1
        with self.assertRaises(BenchmarkMetricsError):
            validate_metrics(self.manifest, self.observations, report)

    def test_wrong_sources_unknown_characters_and_duplicate_records_fail_closed(self):
        record = self.record(0)
        for records in ([record, record], [dict(record, source_sha256="f" * 64)],
                        [dict(record, character_id="character-" + "f" * 16)]):
            with self.subTest(records=records), self.assertRaises(BenchmarkMetricsError):
                build_metrics(self.manifest, {**self.observations, "records": records})
        with self.assertRaises(BenchmarkMetricsError):
            build_metrics(self.manifest, {**self.observations, "dataset_sha256": "f" * 64})

    def test_illegal_numeric_values_counts_and_fake_not_run_outcomes_are_rejected(self):
        invalid = [dict(review_seconds=value) for value in (-1, float("nan"), float("inf"), -float("inf"), True, "3")]
        invalid += [dict(auto_adoption_audit=value) for value in (
            {"adopted": -1, "checked": 0, "correct": 0}, {"adopted": 1, "checked": 2, "correct": 1},
            {"adopted": 2, "checked": 1, "correct": 2}, {"adopted": True, "checked": 0, "correct": 0},
            {"adopted": 1, "checked": 0.0, "correct": 0}, {"adopted": 1, "checked": 0},
        )]
        invalid += [{"status": "not_run", "review_seconds": 0}, {"status": "not_run", "auto_adoption_audit": {"adopted": 0, "checked": 0, "correct": 0}}]
        for changes in invalid:
            with self.subTest(changes=changes), self.assertRaises(BenchmarkMetricsError):
                build_metrics(self.manifest, {**self.observations, "records": [self.record(0, **changes)]})

    def test_metadata_and_reason_contracts_are_strict(self):
        for changes in ({"code_commit": "unknown"}, {"target_version": "4.4"}, {"profile": "manual_review"},
                        {"authority": "release"}, {"unknown": True}, {"records": [self.record(0, "failed")]},
                        {"records": [self.record(0, reason_code="unexpected_failure")]},
                        {"records": [self.record(0, "running")]},
                        {"records": [self.record(0, "blocked", reason_code="../private")]},
                        {"records": [dict(self.record(0), unexpected=True)]}):
            with self.subTest(changes=changes), self.assertRaises(BenchmarkMetricsError):
                validate_observations(self.manifest, {**self.observations, **changes})

    @unittest.skipUnless(Draft202012Validator, "jsonschema optional dependency unavailable")
    def test_real_generated_observations_and_reports_match_both_schemas(self):
        documents = {"observations": self.observations, "metrics": build_metrics(self.manifest, self.observations)}
        for kind, document in documents.items():
            with self.subTest(kind=kind):
                schema = json.loads((ROOT / f"schemas/benchmark-{kind}-v1.schema.json").read_text())
                Draft202012Validator.check_schema(schema)
                validator = Draft202012Validator(schema)
                validator.validate(document)
                self.assertFalse(validator.is_valid({**document, "extra": True}))


if __name__ == "__main__":
    unittest.main()
