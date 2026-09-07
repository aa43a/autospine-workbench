"""Mapping hypotheses bind immutable sources without granting approval."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from autospine_workbench.benchmark.mapping import (
    build_mapping_candidate, inverse_transform_point, transform_point,
    validate_mapping_candidate,
)
from autospine_workbench.benchmark.validation import BenchmarkError


class BenchmarkMappingTests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads((ROOT / "docs/benchmark/manifest-frozen-v1.json").read_text("utf-8"))
        self.row = next(row for row in self.manifest["characters"]
                        if row["dataset_split"] == "development")
        self.psd = self.row["psd_candidates"][0]["source"]

    def build(self, **kwargs):
        return build_mapping_candidate(self.manifest, self.row["id"], self.psd["sha256"], **kwargs)

    def test_canvas_hypothesis_is_deterministic_non_authoritative_and_pure(self):
        before = deepcopy(self.manifest)
        candidate = self.build()
        self.assertEqual(candidate, self.build())
        self.assertEqual(candidate["basis"], "canvas_fit_hypothesis")
        self.assertIsNone(candidate["confidence"])
        self.assertIs(candidate["review_required"], True)
        self.assertEqual(candidate["authority"], "none")
        self.assertEqual(transform_point(candidate["source_to_psd_transform"],
                                        self.row["source"]["canvas"]), self.psd["canvas"])
        self.assertEqual(before, self.manifest)
        candidate["png_source"]["canvas"][0] = 1
        self.assertEqual(before, self.manifest)

    def test_sources_canvas_and_identity_cannot_be_rebound(self):
        for source, field, value in (("png_source", "sha256", "f" * 64),
                                     ("png_source", "canvas", [1, 1]),
                                     ("psd_source", "canvas", [1, 1]),
                                     ("psd_source", "sha256", "f" * 64)):
            with self.subTest(source=source, field=field):
                candidate = self.build()
                candidate[source][field] = value
                with self.assertRaises(BenchmarkError):
                    validate_mapping_candidate(self.manifest, candidate)

    def test_stale_manifest_unknown_character_and_unfrozen_fail(self):
        candidate = self.build()
        candidate["dataset_sha256"] = "f" * 64
        with self.assertRaises(BenchmarkError):
            validate_mapping_candidate(self.manifest, candidate)
        with self.assertRaises(BenchmarkError):
            build_mapping_candidate(self.manifest, "unknown", self.psd["sha256"])
        manifest = json.loads((ROOT / "docs/benchmark/manifest-pending-v1.json").read_text("utf-8"))
        with self.assertRaises(BenchmarkError):
            build_mapping_candidate(manifest, self.row["id"], self.psd["sha256"])

    def test_non_development_requires_explicit_split(self):
        row = next(row for row in self.manifest["characters"]
                   if row["dataset_split"] == "holdout")
        psd = row["psd_candidates"][0]["source"]["sha256"]
        with self.assertRaises(BenchmarkError):
            build_mapping_candidate(self.manifest, row["id"], psd)
        candidate = build_mapping_candidate(self.manifest, row["id"], psd, split="holdout")
        with self.assertRaises(BenchmarkError):
            validate_mapping_candidate(self.manifest, candidate)
        self.assertEqual(validate_mapping_candidate(self.manifest, candidate, split="holdout"), candidate)

    def test_custom_translation_reflection_and_inverse_roundtrip(self):
        transform = {"scale": [-1.5, 2.25], "translation": [1280, -14],
                     "coordinate_system": "pixel_top_left_y_down"}
        candidate = self.build(transform=transform)
        self.assertEqual(candidate["basis"], "explicit_transform_draft")
        for point in ([0, 0], [123.25, 48.5], [-5, 17]):
            restored = inverse_transform_point(transform, transform_point(transform, point))
            for actual, expected in zip(restored, point):
                self.assertAlmostEqual(actual, expected)

    def test_nonfinite_singular_boolean_and_overflow_transforms_fail(self):
        for value in (0, False, float("nan"), float("inf"), 1e308, 5e-324, 10 ** 400):
            with self.subTest(value=repr(value)):
                transform = {"scale": [value, 1], "translation": [0, 0],
                             "coordinate_system": "pixel_top_left_y_down"}
                with self.assertRaises(BenchmarkError):
                    self.build(transform=transform)
        transform = self.build()["source_to_psd_transform"]
        transform["translation"] = [0, float("nan")]
        with self.assertRaises(BenchmarkError):
            self.build(transform=transform)

    def test_authority_confidence_and_hypothesis_relabel_fail(self):
        for field, value in (("authority", "approved"), ("confidence", 0.99),
                             ("review_required", 1), ("review_required", False),
                             ("basis", "observed")):
            candidate = self.build()
            candidate[field] = value
            with self.assertRaises(BenchmarkError):
                validate_mapping_candidate(self.manifest, candidate)
        candidate = self.build()
        candidate["source_to_psd_transform"]["translation"] = [1, 0]
        with self.assertRaises(BenchmarkError):
            validate_mapping_candidate(self.manifest, candidate)

    def test_optional_evidence_is_digest_bound_and_strict(self):
        evidence = {"audit_evidence_sha256": "a" * 64, "composite_sha256": "b" * 64}
        self.assertEqual(self.build(evidence=evidence)["evidence"], evidence)
        for invalid in ({}, {**evidence, "approved": True},
                        {**evidence, "composite_sha256": "bad"}):
            with self.assertRaises(BenchmarkError):
                self.build(evidence=invalid)

    def test_schema_accepts_default_and_mirrored_draft(self):
        try:
            import jsonschema
        except ImportError:
            self.skipTest("Optional JSON Schema test dependency unavailable")
        schema = json.loads((ROOT / "schemas/benchmark-mapping-candidate-v1.schema.json").read_text("utf-8"))
        jsonschema.Draft202012Validator.check_schema(schema)
        validator = jsonschema.Draft202012Validator(schema)
        validator.validate(self.build())
        candidate = self.build(transform={"scale": [-1, 1], "translation": [1280, 0],
                                          "coordinate_system": "pixel_top_left_y_down"})
        validator.validate(candidate)
        candidate["source_to_psd_transform"]["scale"][0] = 0
        self.assertTrue(list(validator.iter_errors(candidate)))


if __name__ == "__main__":
    unittest.main()
