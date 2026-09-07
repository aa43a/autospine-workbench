"""Conservative name aliases, audit binding and non-authoritative suggestions."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from autospine_workbench.benchmark.semantic_candidates import (
    SemanticCandidateError, build_semantic_candidates, validate_semantic_candidates,
)


class BenchmarkSemanticCandidateTests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads((ROOT / "docs/benchmark/manifest-frozen-v1.json").read_text("utf-8"))
        self.evidence = json.loads((ROOT / "docs/benchmark/development-audit-2026-09.json").read_text("utf-8"))
        self.record = self.evidence["characters"][0]
        self.cid = self.record["character_id"]
        self.audit = {
            "sha256": self.record["source_psd"]["sha256"],
            "file_size": self.record["source_psd"]["byte_size"],
            "canvas": self.record["canvas"], "pixel_layers": self.record["pixel_layers"],
            "layers": [{**{k: deepcopy(r[k]) for k in ("index", "traversal_index", "name", "bbox")},
                        "kind": "pixel", "visible": True, "empty": False, "alpha_nonzero": 1}
                       for r in self.record["outputs"]["layers"]],
        }

    def build(self):
        return build_semantic_candidates(self.manifest, self.evidence, self.cid, self.audit)

    def rename(self, index, name):
        self.record["outputs"]["layers"][index]["name"] = name
        self.audit["layers"][index]["name"] = name

    def test_deterministic_pure_and_schema(self):
        before = deepcopy((self.manifest, self.evidence, self.audit))
        doc = self.build()
        self.assertEqual(doc, self.build())
        self.assertEqual(doc, validate_semantic_candidates(self.manifest, self.evidence, doc, self.audit))
        self.assertEqual(before, (self.manifest, self.evidence, self.audit))
        self.assertEqual(doc["authority"], "none")
        try:
            from jsonschema import Draft202012Validator
        except ImportError:
            return
        schema = json.loads((ROOT / "schemas/benchmark-semantic-candidates-v1.schema.json").read_text("utf-8"))
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(doc)

    def test_exact_alias_and_raw_side_only(self):
        self.rename(0, " Upper Arm-l ")
        layer = self.build()["layers"][0]
        self.assertEqual(layer["semantic"], "body.arm.upper")
        self.assertEqual(layer["raw_name_side"], "l")
        self.assertEqual(layer["canonical_side"], "unknown")
        self.assertIsNone(layer["confidence"])
        self.assertTrue(layer["review_required"])

    def test_ambiguous_and_unmapped_are_not_face_or_limb(self):
        for name in ("arm", "handwear-r", "legwear", "bottomwear", "eye", "eyebrow-l", "ears", "mouth", "wings"):
            with self.subTest(name=name):
                self.rename(0, name)
                self.assertIsNone(self.build()["layers"][0]["semantic"])

    def test_empty_layer_with_nonempty_bbox_is_retained(self):
        self.audit["layers"][0].update(empty=True, alpha_nonzero=0, visible=False)
        doc = self.build()
        self.assertEqual(len(doc["layers"]), self.record["pixel_layers"])
        layer = doc["layers"][0]
        self.assertIn("empty_layer_review_required", layer["reason_codes"])
        self.assertIn("hidden_layer_review_required", layer["reason_codes"])
        self.assertGreater(layer["bbox"][2] - layer["bbox"][0], 0)

    def test_audit_identity_and_layer_mismatch_fail(self):
        for key, value in (("sha256", "0" * 64), ("file_size", 0), ("canvas", [1, 1])):
            audit = deepcopy(self.audit)
            audit[key] = value
            with self.assertRaises(SemanticCandidateError):
                build_semantic_candidates(self.manifest, self.evidence, self.cid, audit)
        self.audit["layers"][0]["name"] = "tampered"
        with self.assertRaises(SemanticCandidateError):
            self.build()

    def test_observation_types_counts_and_duplicates_fail(self):
        for change in ({"alpha_nonzero": True}, {"empty": True}, {"alpha_nonzero": -1}, {"visible": 1}):
            audit = deepcopy(self.audit)
            audit["layers"][0].update(change)
            with self.assertRaises(SemanticCandidateError):
                build_semantic_candidates(self.manifest, self.evidence, self.cid, audit)
        self.record["outputs"]["layers"][1]["traversal_index"] = 0
        self.audit["layers"][1]["traversal_index"] = 0
        with self.assertRaises(SemanticCandidateError):
            self.build()

    def test_modified_suggestion_and_boolean_integer_alias_fail(self):
        for field, value in (("semantic", "body.foot"), ("index", False), ("confidence", 0.99)):
            doc = self.build()
            doc["layers"][0][field] = value
            with self.assertRaises(SemanticCandidateError):
                validate_semantic_candidates(self.manifest, self.evidence, doc, self.audit)

    def test_manifest_source_and_split_guards(self):
        self.cid = next(r["id"] for r in self.manifest["characters"] if r["dataset_split"] == "holdout")
        with self.assertRaisesRegex(SemanticCandidateError, "semantic_development_only"):
            self.build()
        self.cid = self.record["character_id"]
        self.record["source_png"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(SemanticCandidateError, "semantic_source_mismatch"):
            self.build()


if __name__ == "__main__":
    unittest.main()
