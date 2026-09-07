"""No-SHA benchmark intake, partition, source drift and empty-evaluation CLI."""

from contextlib import redirect_stdout
from copy import deepcopy
import hashlib
from io import StringIO
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from autospine_workbench.benchmark.__main__ import main
from autospine_workbench.benchmark.artifacts import read_report
from autospine_workbench.benchmark.source_files import verify_sources
from autospine_workbench.benchmark.manifest import import_inventory

class BenchmarkCliTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.state = self.root / "state"
        self.inventory = json.loads((ROOT / "docs/benchmark/inventory-2026-09.json").read_text(encoding="utf-8"))
        for row in self.inventory["png_assets"] + self.inventory["psd_assets"]:
            width, height = row["canvas"]
            header = (b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", width, height)) \
                if row["path"].endswith(".png") else b"8BPS\x00\x01" + b"\0" * 8 + struct.pack(">II", height, width)
            # These fixtures exercise identity/header validation, not PNG raster approval.
            raw = header + row["path"].encode("utf-8")
            path = self.root / row["path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
            row["sha256"] = hashlib.sha256(raw).hexdigest()
            row["byte_size"] = len(raw)
        self.input = self.root / "inventory.json"
        self.input.write_text(json.dumps(self.inventory), encoding="utf-8")

    def invoke(self, *args):
        out = StringIO()
        with redirect_stdout(out):
            code = main(["--state-root", str(self.state), *map(str, args)])
        value = json.loads(out.getvalue())
        self.assertNotIn(str(self.state), out.getvalue())
        return code, value

    def intake(self):
        manifest = self.root / "manifest.json"
        code, value = self.invoke("intake", "--inventory", self.input, "--workspace", self.root, "--output", manifest)
        self.assertEqual(code, 0, value)
        return manifest

    def test_realistic_inventory_to_frozen_split_and_honest_empty_metrics(self):
        manifest = self.intake()
        proposal = self.root / "split.json"
        code, value = self.invoke("propose-split", "--manifest", manifest,
            "--development-source", "png/爱丽丝.png", "--output", proposal)
        self.assertEqual(code, 0, value)
        frozen = self.root / "frozen.json"
        self.assertEqual(self.invoke("freeze-split", "--manifest", manifest,
            "--proposal", proposal, "--output", frozen)[0], 0)
        rows = json.loads(frozen.read_text(encoding="utf-8"))["characters"]
        alice = next(row for row in rows if row["source"]["path"] == "png/爱丽丝.png")
        self.assertEqual(alice["dataset_split"], "development")
        self.assertEqual([row["dataset_split"] for row in rows].count("holdout"), 3)
        observations = self.root / "observations.json"
        self.assertEqual(self.invoke("observations-template", "--manifest", frozen,
            "--code-commit", "a" * 40, "--output", observations)[0], 0)
        code, report = self.invoke("metrics", "--manifest", frozen, "--observations", observations)
        self.assertEqual(code, 0, report)
        self.assertEqual(report["authority"], "none")
        self.assertEqual(report["primary"]["total_characters"], 10)
        self.assertIsNone(report["primary"]["auto_adoption"]["accuracy"])
        self.assertEqual(report["primary"]["completion_rate"], 0)

    def test_intake_verifies_all_source_bytes_before_publishing_manifest(self):
        path = self.root / self.inventory["psd_assets"][0]["path"]
        path.write_bytes(b"changed")
        code, report = self.invoke("intake", "--inventory", self.input, "--workspace", self.root)
        self.assertEqual(code, 2)
        self.assertEqual(report["status"], "blocked")
        self.assertEqual(report["counts"], {"total": 32, "verified": 31})
        self.assertFalse((self.state / "benchmarks/touhou-20-v1/manifests").exists())

    def test_freeze_rejects_proposal_bound_to_other_manifest(self):
        manifest = self.intake()
        proposal = self.root / "stale.json"
        self.assertEqual(self.invoke("propose-split", "--manifest", manifest, "--output", proposal)[0], 0)
        data = json.loads(proposal.read_text(encoding="utf-8"))
        data["dataset_sha256"] = "f" * 64
        proposal.write_text(json.dumps(data), encoding="utf-8")
        output = self.root / "must-not-exist.json"
        code, result = self.invoke("freeze-split", "--manifest", manifest, "--proposal", proposal, "--output", output)
        self.assertEqual(code, 1)
        self.assertEqual(result["reason_code"], "benchmark_split_source_mismatch")
        self.assertFalse(output.exists())

    def test_source_canvas_drift_and_missing_file_are_not_successes(self):
        data = deepcopy(self.inventory)
        data["png_assets"][0]["canvas"][0] += 1
        manifest = import_inventory(data)
        (self.root / data["png_assets"][1]["path"]).unlink()
        report = verify_sources(manifest, self.root)
        reasons = [row["reason_code"] for row in report["files"]]
        self.assertIn("source_canvas_changed", reasons)
        self.assertIn("source_unavailable", reasons)
        self.assertEqual(report["rigging_evaluation"], "not_run")

    def test_outputs_are_immutable_and_reports_are_content_addressed(self):
        manifest = self.intake()
        before = manifest.read_bytes()
        self.intake()
        self.assertEqual(manifest.read_bytes(), before)
        code, report = self.invoke("verify-sources", "--manifest", manifest, "--workspace", self.root)
        self.assertEqual(code, 0)
        from autospine_workbench.resolved_project import canonical_sha256
        digest = canonical_sha256(report)
        self.assertEqual(read_report(self.state, "touhou-20-v1", "source-verifications", digest), report)
        manifest.write_bytes(b"user content")
        code, result = self.invoke("intake", "--inventory", self.input, "--workspace", self.root, "--output", manifest)
        self.assertEqual(code, 1)
        self.assertEqual(result["reason_code"], "benchmark_output_exists")
        self.assertEqual(manifest.read_bytes(), b"user content")

    def test_input_batch_does_not_open_holdout_or_promote_analysis_to_outcome(self):
        from autospine_workbench.benchmark.input_batch import lint_inputs
        from autospine_workbench.benchmark.manifest import freeze_split
        from autospine_workbench.benchmark.split_proposal import propose_split
        from autospine_workbench.benchmark import input_batch

        manifest = import_inventory(self.inventory)
        manifest = freeze_split(manifest, propose_split(manifest)["assignment"])
        expected = {self.root / row["source"]["path"] for row in manifest["characters"]
                    if row["dataset_split"] == "development"}
        analyze = lambda raw: {"canvas": list(struct.unpack(">II", raw[16:24])), "quality": "warning"}
        with patch.object(input_batch, "read_real_file", wraps=input_batch.read_real_file) as read, \
                patch.object(input_batch, "analyze_input_image", side_effect=analyze):
            report = lint_inputs(manifest, self.root)
        self.assertEqual({call.args[0] for call in read.call_args_list}, expected)
        self.assertEqual(len(report["records"]), 3)
        self.assertEqual(report["rigging_evaluation"], "not_run")
        self.assertEqual(report["annotation_effect"], "none")
        self.assertTrue(all(row["annotation_status"] == "pending" for row in manifest["characters"]))
