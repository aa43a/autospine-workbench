"""Real 20-PNG/12-PSD intake, explicit frozen split and immutable storage."""
from collections import Counter
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from autospine_workbench.benchmark.manifest import import_inventory, freeze_split
from autospine_workbench.benchmark.store import BenchmarkManifestStore
from autospine_workbench.benchmark.validation import BenchmarkError, validate_benchmark_manifest
from autospine_workbench.resolved_project import canonical_sha256


def inventory_fixture():
    return json.loads((ROOT / "docs/benchmark/inventory-2026-09.json").read_text(encoding="utf-8"))


def split_fixture(manifest):
    labels = ["development"] * 3 + ["visible"] * 4 + ["holdout"] * 3 + ["reserve"] * 10
    return {row["id"]: label for row, label in zip(manifest["characters"], labels)}


class BenchmarkManifestTests(unittest.TestCase):
    def setUp(self):
        self.inventory = inventory_fixture()
        self.manifest = import_inventory(self.inventory)

    def test_real_inventory_keeps_twenty_sources_and_twelve_candidate_psds(self):
        self.assertEqual(self.manifest["source_inventory_sha256"], canonical_sha256(self.inventory))
        self.assertEqual(len(self.manifest["characters"]), 20)
        candidates = [candidate for row in self.manifest["characters"] for candidate in row["psd_candidates"]]
        self.assertEqual(len(candidates), 12)
        self.assertEqual(sum(bool(row["psd_candidates"]) for row in self.manifest["characters"]), 11)
        self.assertEqual({row["source"]["sha256"] for row in self.manifest["characters"]},
                         {row["sha256"] for row in self.inventory["png_assets"]})
        self.assertEqual({row["source"]["sha256"] for row in candidates},
                         {row["sha256"] for row in self.inventory["psd_assets"]})
        self.assertTrue(all(candidate["mapping"]["status"] == "candidate" for candidate in candidates))

    def test_intake_does_not_invent_groundtruth_rights_or_alpha_annotations(self):
        self.assertEqual(self.manifest["authority"], "none")
        self.assertEqual(self.manifest["split_status"], "unassigned")
        for row in self.manifest["characters"]:
            self.assertEqual(row["annotation_status"], "pending")
            self.assertEqual(row["dataset_split"], "unassigned")
            self.assertIsNone(row["complexity"])
            self.assertIsNone(row["rights"])
            self.assertEqual(row["reviewed_joints"], {})
            self.assertEqual(row["complexity_tags"], [])
            self.assertNotIn("alpha_nonzero_bbox", row["source"])

    def test_import_and_freeze_are_deterministic_without_mutating_inputs(self):
        before = deepcopy(self.inventory)
        first = import_inventory(dict(reversed(list(self.inventory.items()))))
        self.assertEqual(first, self.manifest)
        assignment = split_fixture(self.manifest)
        frozen = freeze_split(self.manifest, assignment)
        self.assertEqual(frozen, freeze_split(self.manifest, dict(reversed(list(assignment.items())))))
        self.assertEqual(self.inventory, before)
        self.assertEqual(self.manifest["split_status"], "unassigned")

    def test_explicit_split_freeze_groups_variants_with_their_source(self):
        frozen = freeze_split(self.manifest, split_fixture(self.manifest))
        self.assertEqual(Counter(row["dataset_split"] for row in frozen["characters"]),
                         {"development": 3, "visible": 4, "holdout": 3, "reserve": 10})
        variants = next(row for row in frozen["characters"] if len(row["psd_candidates"]) == 2)
        self.assertEqual({candidate["source"]["path"] for candidate in variants["psd_candidates"]},
                         {"yaomeng.psd", "yaomeng1.psd"})
        for candidate in variants["psd_candidates"]:
            self.assertEqual(candidate["dataset_split"], variants["dataset_split"])
            self.assertEqual(candidate["mapping"]["status"], "candidate")

    def test_frozen_split_can_replay_but_cannot_change(self):
        assignment = split_fixture(self.manifest)
        frozen = freeze_split(self.manifest, assignment)
        self.assertEqual(freeze_split(frozen, assignment), frozen)
        ids = list(assignment)
        assignment[ids[0]], assignment[ids[9]] = assignment[ids[9]], assignment[ids[0]]
        with self.assertRaises(BenchmarkError) as caught:
            freeze_split(frozen, assignment)
        self.assertEqual(caught.exception.reason_code, "benchmark_split_frozen")

    def test_split_cardinality_missing_character_and_variant_divergence_fail(self):
        mapping = split_fixture(self.manifest)
        for invalid in ({}, {**mapping, "not-a-character": "reserve"},
                        {key: "holdout" for key in mapping}):
            with self.subTest(invalid=invalid), self.assertRaises(BenchmarkError):
                freeze_split(self.manifest, invalid)
        frozen = freeze_split(self.manifest, mapping)
        row = next(row for row in frozen["characters"] if row["psd_candidates"])
        row["psd_candidates"][0]["dataset_split"] = "unassigned"
        with self.assertRaises(BenchmarkError):
            validate_benchmark_manifest(frozen)

    def test_candidate_approval_unknown_source_and_nonfinite_inventory_fail(self):
        invalid = deepcopy(self.inventory)
        invalid["psd_assets"][0]["source_mapping"]["status"] = "approved"
        with self.assertRaises(BenchmarkError):
            import_inventory(invalid)
        invalid = deepcopy(self.inventory)
        invalid["psd_assets"][0]["source_mapping"]["png_path"] = "png/missing.png"
        with self.assertRaises(BenchmarkError):
            import_inventory(invalid)
        invalid = deepcopy(self.inventory)
        invalid["png_assets"][0]["alpha_range"][0] = float("nan")
        with self.assertRaises(BenchmarkError):
            import_inventory(invalid)

    def test_duplicate_paths_hashes_and_character_identity_fail(self):
        for key in ("path", "sha256"):
            invalid = deepcopy(self.inventory)
            invalid["png_assets"][1][key] = invalid["png_assets"][0][key]
            with self.subTest(key=key), self.assertRaises(BenchmarkError):
                import_inventory(invalid)
        invalid = deepcopy(self.manifest)
        invalid["characters"][0]["id"] = invalid["characters"][1]["id"]
        with self.assertRaises(BenchmarkError):
            validate_benchmark_manifest(invalid)

    def test_schema_agrees_on_source_paths_annotations_and_split_shapes(self):
        try:
            from jsonschema import Draft202012Validator
        except ImportError:
            self.skipTest("jsonschema unavailable")
        schema = json.loads((ROOT / "schemas/benchmark-manifest-v1.schema.json").read_text())
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        validator.validate(self.manifest)
        validator.validate(freeze_split(self.manifest, split_fixture(self.manifest)))
        mutations = []
        for path in ("/tmp/image.png", "../image.png", "png/../image.png", "C:/image.png",
                     "png\\image.png", "png/CON.png", "png/dir./image.png", "png//image.png"):
            invalid = deepcopy(self.manifest)
            invalid["characters"][0]["source"]["path"] = path
            mutations.append(invalid)
        for key, value in (("complexity", "simple"), ("rights", {"usage": "internal_test"}),
                           ("annotation_status", "approved"), ("reviewed_joints", {"hip.left": [1, 2]})):
            invalid = deepcopy(self.manifest)
            invalid["characters"][0][key] = value
            mutations.append(invalid)
        mutations.extend([{**self.manifest, "authority": "approved"}, {**self.manifest, "split_status": "frozen"}])
        for invalid in mutations:
            self.assertTrue(list(validator.iter_errors(invalid)))
            with self.assertRaises(BenchmarkError):
                validate_benchmark_manifest(invalid)

    def test_store_preserves_pending_and_frozen_content_addresses(self):
        with tempfile.TemporaryDirectory() as directory:
            store = BenchmarkManifestStore(directory)
            pending_sha = store.publish(self.manifest)
            frozen = freeze_split(self.manifest, split_fixture(self.manifest))
            frozen_sha = store.publish(frozen)
            self.assertNotEqual(pending_sha, frozen_sha)
            self.assertEqual(store.publish(frozen), frozen_sha)
            self.assertEqual(store.load(self.manifest["dataset_id"], pending_sha), self.manifest)
            self.assertEqual(store.load(frozen["dataset_id"], frozen_sha), frozen)
            folder = store.root / self.manifest["dataset_id"] / "manifests"
            self.assertEqual(len(list(folder.iterdir())), 2)
            loaded = store.load(frozen["dataset_id"], frozen_sha)
            loaded["characters"].clear()
            self.assertEqual(store.load(frozen["dataset_id"], frozen_sha), frozen)

    def test_store_tamper_noncanonical_and_missing_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            store = BenchmarkManifestStore(directory)
            sha = store.publish(self.manifest)
            path = store.root / self.manifest["dataset_id"] / "manifests" / f"{sha}.json"
            canonical = path.read_bytes()
            for data in (canonical + b" ", b"{}", canonical.replace(b'"pending"', b'"approved"')):
                path.write_bytes(data)
                with self.assertRaises(BenchmarkError):
                    store.load(self.manifest["dataset_id"], sha)
                with self.assertRaises(BenchmarkError):
                    store.publish(self.manifest)
                self.assertEqual(path.read_bytes(), data)
            path.unlink()
            with self.assertRaises(BenchmarkError):
                store.load(self.manifest["dataset_id"], sha)

    def test_store_rejects_hardlinks_case_aliases_and_unsafe_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            store = BenchmarkManifestStore(directory)
            sha = store.publish(self.manifest)
            path = store.root / self.manifest["dataset_id"] / "manifests" / f"{sha}.json"
            os.link(path, Path(directory) / "alias.json")
            with self.assertRaises(BenchmarkError):
                store.load(self.manifest["dataset_id"], sha)
            for dataset_id in ("../escape", "CON", self.manifest["dataset_id"].upper()):
                with self.subTest(dataset_id=dataset_id), self.assertRaises(BenchmarkError):
                    store.load(dataset_id, sha)


if __name__ == "__main__":
    unittest.main()
