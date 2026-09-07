"""Synthetic declarations never claim real benchmark ground truth."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from autospine_workbench.benchmark.mapping import build_mapping_candidate
from autospine_workbench.benchmark.mapping_decision import (
    REQUEST_SCHEMA, build_mapping_decision, validate_mapping_decision,
)
from autospine_workbench.benchmark.validation import BenchmarkError
from autospine_workbench.resolved_project import canonical_sha256


class BenchmarkMappingDecisionTests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads((ROOT / "docs/benchmark/manifest-frozen-v1.json").read_text("utf-8"))
        row = next(row for row in self.manifest["characters"] if row["dataset_split"] == "development")
        self.candidate = build_mapping_candidate(self.manifest, row["id"],
                                                 row["psd_candidates"][0]["source"]["sha256"])
        self.request = {"schema": REQUEST_SCHEMA, "candidate_sha256": canonical_sha256(self.candidate),
                        "reviewer": "TEST-ONLY", "action": "accept", "reason": "Synthetic fixture",
                        "checks": {"same_character": True, "coordinate_alignment": True,
                                   "mirror_checked": True}, "authority": "none"}

    def build(self):
        return build_mapping_decision(self.manifest, self.candidate, self.request)

    def test_deterministic_source_bound_pure_and_no_production_authority(self):
        before = deepcopy((self.manifest, self.candidate, self.request))
        decision = self.build()
        self.assertEqual(decision, self.build())
        self.assertEqual(decision["source_request_sha256"], canonical_sha256(self.request))
        self.assertEqual(decision["source_candidate_sha256"], canonical_sha256(self.candidate))
        self.assertEqual(decision["scope"], "benchmark_mapping_only")
        self.assertEqual(decision["authority"], "none")
        self.assertEqual(decision["mapping_status"], "reviewed_accepted")
        self.assertEqual(validate_mapping_decision(self.manifest, self.candidate, self.request, decision), decision)
        decision["checks"]["same_character"] = False
        self.assertEqual(before, (self.manifest, self.candidate, self.request))

    def test_reject_can_record_failed_checks_but_requires_reason(self):
        self.request["action"] = "reject"
        self.request["checks"]["coordinate_alignment"] = False
        self.assertEqual(self.build()["mapping_status"], "reviewed_rejected")
        self.request["reason"] = " "
        with self.assertRaises(BenchmarkError):
            self.build()

    def test_accept_requires_all_checks_and_actual_booleans(self):
        for value in (False, 1, 0, None, "true", []):
            with self.subTest(value=value):
                self.request["checks"]["mirror_checked"] = value
                with self.assertRaises(BenchmarkError):
                    self.build()

    def test_stale_candidate_transform_or_manifest_fail(self):
        self.candidate["basis"] = "explicit_transform_draft"
        self.candidate["source_to_psd_transform"]["translation"][0] = 2
        with self.assertRaisesRegex(BenchmarkError, "candidate_mismatch"):
            self.build()
        self.request["candidate_sha256"] = canonical_sha256(self.candidate)
        self.manifest["dataset_id"] = "different-dataset"
        with self.assertRaises(BenchmarkError):
            self.build()

    def test_input_contract_rejects_missing_extra_authority_and_invalid_action(self):
        original = deepcopy(self.request)
        mutations = [{**original, "authority": "approved"}, {**original, "action": "revoke"},
                     {**original, "extra": True}, {**original, "candidate_sha256": "f" * 64},
                     {key: value for key, value in original.items() if key != "reviewer"}]
        for request in mutations:
            self.request = request
            with self.assertRaises(BenchmarkError):
                self.build()

    def test_text_limits_control_characters_and_unicode(self):
        for field, values in (("reviewer", ["", "  ", 1, "x" * 129, "a\x00b", "a\u202eb"]),
                              ("reason", [None, " ", "x" * 2001, "a\nb", "\ud800"])):
            original = self.request[field]
            for value in values:
                self.request[field] = value
                with self.assertRaises(BenchmarkError):
                    self.build()
            self.request[field] = original
        self.request["reviewer"] = "测试复核人"
        self.assertEqual(self.build()["reviewer"], "测试复核人")

    def test_exact_recompilation_rejects_altered_or_extra_decision_fields(self):
        original = self.build()
        for field, value in (("authority", "production"), ("scope", "rigging"),
                              ("decision_source", "policy_auto"), ("source_request_sha256", "f" * 64),
                              ("reason", "changed"), ("mapping_status", "reviewed_rejected"),
                              ("extra", None), ("checks", {key: 1 for key in self.request["checks"]})):
            decision = {**original, field: value}
            with self.assertRaises(BenchmarkError):
                validate_mapping_decision(self.manifest, self.candidate, self.request, decision)

    def test_holdout_requires_explicit_split(self):
        row = next(row for row in self.manifest["characters"] if row["dataset_split"] == "holdout")
        candidate = build_mapping_candidate(self.manifest, row["id"],
                                           row["psd_candidates"][0]["source"]["sha256"], split="holdout")
        request = {**self.request, "candidate_sha256": canonical_sha256(candidate)}
        with self.assertRaises(BenchmarkError):
            build_mapping_decision(self.manifest, candidate, request)
        decision = build_mapping_decision(self.manifest, candidate, request, split="holdout")
        self.assertEqual(decision["dataset_split"], "holdout")

    def test_json_schemas_match_acceptance_and_rejection_structure(self):
        try:
            from jsonschema import Draft202012Validator
        except ImportError:
            self.skipTest("Optional test dependency jsonschema is unavailable")
        validators = {}
        for kind in ("decision", "review-request"):
            schema = json.loads((ROOT / f"schemas/benchmark-mapping-{kind}-v1.schema.json").read_text("utf-8"))
            Draft202012Validator.check_schema(schema)
            validators[kind] = Draft202012Validator(schema)
        for action in ("accept", "reject"):
            self.request["action"] = action
            self.request["checks"]["same_character"] = action == "accept"
            validators["review-request"].validate(self.request)
            validators["decision"].validate(self.build())
        self.request["action"] = "accept"
        self.assertTrue(list(validators["review-request"].iter_errors(self.request)))
        self.request["checks"]["same_character"] = True
        decision = self.build()
        decision["mapping_status"] = "reviewed_rejected"
        self.assertTrue(list(validators["decision"].iter_errors(decision)))


if __name__ == "__main__":
    unittest.main()
