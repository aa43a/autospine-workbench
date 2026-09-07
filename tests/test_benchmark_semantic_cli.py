"""Layer evidence verification and recoverable, non-authoritative annotation."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from tests import test_benchmark_mapping_cli as fixture_module
from autospine_workbench.benchmark.semantic_cli import load_semantic_inputs, read_semantic_candidate
from autospine_workbench.benchmark.semantic_draft import build_semantic_draft, validate_semantic_draft
from autospine_workbench.benchmark.artifacts import publish_report
from autospine_workbench.resolved_project import canonical_sha256


class SemanticCliTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture_module.MappingCliTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.manifest = self.fixture.manifest
        self.evidence = self.fixture.evidence
        self.evidence.update(scope="development_only", dataset_id=self.manifest["dataset_id"])
        record = self.evidence["characters"][0]
        record.update(authority="none", canvas=self.fixture.psd["canvas"], pixel_layers=3)
        layers, observations = [], []
        for index, name in enumerate(("back hair", "handwear-l", "headwear")):
            bbox = [0, 0, 8, 8]
            raw = b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", 8, 8) + name.encode()
            image = self.write_asset(f"layer-{index}.png", raw)
            row = {"index": index, "traversal_index": index, "name": name, "bbox": bbox, "image": image}
            layers.append(row)
            observations.append({key: value for key, value in row.items() if key != "image"} |
                                {"kind": "pixel", "empty": index == 2, "visible": index != 2,
                                 "alpha_nonzero": 0 if index == 2 else 20})
        self.audit = {"sha256": self.fixture.psd["sha256"], "file_size": self.fixture.psd["byte_size"],
                      "canvas": self.fixture.psd["canvas"], "pixel_layers": 3, "layers": observations}
        record["outputs"].update(layers=layers, audit=self.write_asset("audit.json", json.dumps(self.audit).encode()))

    def write_asset(self, name, raw):
        (self.root / name).write_bytes(raw)
        return {"path": name, "byte_size": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}

    def load(self):
        return load_semantic_inputs(self.manifest, self.evidence, self.root, self.fixture.psd["path"])

    def invoke(self, draft=None):
        for name, value in (("manifest", self.manifest), ("evidence", self.evidence)):
            (self.root / (name + ".json")).write_text(json.dumps(value), encoding="utf-8")
        args = ["semantic-review", "--manifest", self.root / "manifest.json", "--evidence", self.root / "evidence.json",
                "--workspace", self.root, "--character", self.fixture.psd["path"], "--html", self.root / "semantic.html"]
        if draft is not None:
            (self.root / "draft.json").write_text(json.dumps(draft), encoding="utf-8")
            args += ["--draft", self.root / "draft.json"]
        return self.fixture.fixture.invoke(*args)

    def test_cli_flow_stores_replayable_candidate_without_adopting_suggestions(self):
        code, candidate = self.invoke()
        self.assertEqual(code, 0)
        self.assertEqual(candidate["layers"][0]["semantic"], "hair.back")
        self.assertIsNone(candidate["layers"][1]["semantic"])
        self.assertTrue(candidate["layers"][2]["observed"]["empty"])
        self.assertEqual(read_semantic_candidate(self.fixture.fixture.state, self.manifest,
                                               canonical_sha256(candidate)), candidate)
        draft = build_semantic_draft(candidate)
        self.assertTrue(all(row["semantic"] is None and row["disposition"] == "undecided" for row in draft["records"]))

    def test_source_layer_and_audit_bytes_are_all_checked(self):
        for name in ("layer-0.png", "audit.json"):
            path = self.root / name
            raw = path.read_bytes()
            path.write_bytes(raw + b"tamper")
            with self.assertRaisesRegex(ValueError, "source_changed"):
                self.load()
            path.write_bytes(raw)

    def test_holdout_is_not_opened(self):
        held = next(row for row in self.manifest["characters"] if row["dataset_split"] == "holdout")
        with patch("autospine_workbench.benchmark.mapping_cli.read_real_file") as reader:
            with self.assertRaises(ValueError):
                load_semantic_inputs(self.manifest, self.evidence, self.root, held["id"])
            reader.assert_not_called()

    def test_draft_restores_but_rejects_unknown_stale_duplicate_or_fake_authority(self):
        candidate = self.load()[0]
        draft = build_semantic_draft(candidate)
        draft["records"][0].update(semantic="hair.back", side="bilateral", disposition="include", notes="TEST ONLY")
        self.assertEqual(self.invoke(draft)[0], 0)
        for edit in (lambda d: d.update(authority="human"), lambda d: d.update(candidate_sha256="0" * 64),
                     lambda d: d["records"][0].update(semantic="invented.role"),
                     lambda d: d["records"][1].update(layer_id=d["records"][0]["layer_id"])):
            changed = deepcopy(draft)
            edit(changed)
            with self.assertRaises(ValueError):
                validate_semantic_draft(candidate, changed)
        from jsonschema import Draft202012Validator
        schema = json.loads((ROOT / "schemas/benchmark-semantic-draft-v1.schema.json").read_text())
        Draft202012Validator(schema).validate(draft)
        invalid = deepcopy(draft)
        invalid["candidate_sha256"] += "\n"
        self.assertFalse(Draft202012Validator(schema).is_valid(invalid))

    def test_rehashed_suggestion_tamper_is_rejected(self):
        _, candidate = self.invoke()
        candidate["layers"][1]["semantic"] = "body.arm.upper"
        digest = publish_report(self.fixture.fixture.state, self.manifest["dataset_id"], "semantic-candidates", candidate)
        with self.assertRaises(ValueError):
            read_semantic_candidate(self.fixture.fixture.state, self.manifest, digest)


if __name__ == "__main__":
    unittest.main()
