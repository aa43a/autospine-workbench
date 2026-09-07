"""Mapping intake binds exact sources and refuses protected or stale inputs."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tests import test_benchmark_cli as fixture_module
from autospine_workbench.benchmark.manifest import import_inventory, freeze_split
from autospine_workbench.benchmark.split_proposal import propose_split
from autospine_workbench.benchmark.mapping_cli import prepare_review, export_html
from autospine_workbench.resolved_project import canonical_sha256


class MappingCliTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture_module.BenchmarkCliTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        manifest = import_inventory(self.fixture.inventory)
        self.manifest = freeze_split(manifest, propose_split(manifest)["assignment"])
        self.row = next(row for row in self.manifest["characters"] if row["dataset_split"] == "development")
        self.psd = self.row["psd_candidates"][0]["source"]
        import struct
        raw = b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", *self.psd["canvas"])
        (self.root / "composite.png").write_bytes(raw)
        self.evidence = {"schema": "autospine.development-audit-evidence/v1", "authority": "none",
                         "benchmark_manifest_sha256": canonical_sha256(self.manifest), "characters": [{
                             "character_id": self.row["id"], "dataset_split": "development",
                             "source_png": self.row["source"], "source_psd": self.psd,
                             "outputs": {"composite": {"path": "composite.png", "byte_size": len(raw),
                                                         "sha256": hashlib.sha256(raw).hexdigest()}}}]}

    def prepare(self, **kwargs):
        return prepare_review(self.manifest, self.evidence, self.root, self.psd["path"], **kwargs)

    def test_exact_candidate_replay_and_adjusted_draft(self):
        candidate, html = self.prepare()
        self.assertEqual(candidate["authority"], "none")
        self.assertIn("data:image/png;base64,", html)
        self.assertEqual(self.prepare(), (candidate, html))
        draft = deepcopy(candidate)
        draft["basis"] = "explicit_transform_draft"
        draft["source_to_psd_transform"]["translation"] = [12, -15]
        loaded, _ = self.prepare(draft=draft)
        self.assertEqual(loaded, draft)

    def test_source_and_composite_drift_fail(self):
        for name in (self.row["source"]["path"], self.psd["path"], "composite.png"):
            path = self.root / name
            raw = path.read_bytes()
            path.write_bytes(raw + b"changed")
            with self.assertRaisesRegex(ValueError, "source_changed"):
                self.prepare()
            path.write_bytes(raw)

    def test_stale_and_traversing_evidence_fail(self):
        self.evidence["benchmark_manifest_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "evidence_mismatch"):
            self.prepare()
        self.evidence["benchmark_manifest_sha256"] = canonical_sha256(self.manifest)
        self.evidence["characters"][0]["outputs"]["composite"]["path"] = "../outside.png"
        with self.assertRaisesRegex(ValueError, "path_invalid"):
            self.prepare()

    def test_malformed_evidence_returns_structured_cli_error(self):
        manifest = self.root / "manifest.json"
        evidence = self.root / "evidence.json"
        manifest.write_text(json.dumps(self.manifest), encoding="utf-8")
        for records in ([None], {}, None, [True]):
            self.evidence["characters"] = records
            evidence.write_text(json.dumps(self.evidence), encoding="utf-8")
            code, result = self.fixture.invoke("mapping-review", "--manifest", manifest, "--evidence", evidence,
                                                "--workspace", self.root, "--character", self.psd["path"],
                                                "--html", self.root / "invalid.html")
            self.assertEqual(code, 1)
            self.assertEqual(result["reason_code"], "benchmark_mapping_evidence_mismatch")
            self.assertFalse((self.root / "invalid.html").exists())

    def test_holdout_rejected_before_any_asset_read(self):
        row = next(row for row in self.manifest["characters"] if row["dataset_split"] == "holdout")
        with patch("autospine_workbench.benchmark.mapping_cli.read_real_file") as reader:
            with self.assertRaisesRegex(ValueError, "selection_ambiguous_or_unavailable"):
                prepare_review(self.manifest, self.evidence, self.root, row["id"])
            reader.assert_not_called()

    def test_foreign_evidence_draft_rejected(self):
        candidate, _ = self.prepare()
        candidate["evidence"]["composite_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "draft_mismatch"):
            self.prepare(draft=candidate)

    def test_immutable_html_export_and_cli(self):
        page = self.root / "review.html"
        export_html(page, "original")
        export_html(page, "original")
        with self.assertRaisesRegex(ValueError, "output_exists"):
            export_html(page, "different")
        self.assertEqual(page.read_text(), "original")
        manifest = self.root / "manifest.json"
        evidence = self.root / "evidence.json"
        manifest.write_text(json.dumps(self.manifest), encoding="utf-8")
        evidence.write_text(json.dumps(self.evidence), encoding="utf-8")
        code, candidate = self.fixture.invoke("mapping-review", "--manifest", manifest, "--evidence", evidence,
                                              "--workspace", self.root, "--character", self.psd["path"],
                                              "--html", self.root / "new.html")
        self.assertEqual(code, 0)
        self.assertEqual(candidate["authority"], "none")


if __name__ == "__main__":
    unittest.main()
