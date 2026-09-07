"""Synthetic human-review mechanics, never real sample approval."""

from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tests import test_benchmark_mapping_cli as fixture_module
from autospine_workbench.benchmark.artifacts import publish_report
from autospine_workbench.benchmark.mapping_decision_store import read_mapping_decision
from autospine_workbench.benchmark.mapping_annotation import validate_annotation_template
from autospine_workbench.resolved_project import canonical_sha256


class MappingDecisionCliTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture_module.MappingCliTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.candidate, _ = self.fixture.prepare()
        self.request = {"schema": "autospine.benchmark-mapping-review-request/v1", "authority": "none",
                        "candidate_sha256": canonical_sha256(self.candidate), "action": "accept",
                        "reviewer": "TEST ONLY", "reason": "Synthetic mechanism test, not sample approval",
                        "checks": {"same_character": True, "coordinate_alignment": True, "mirror_checked": True}}
        for name, value in (("manifest", self.fixture.manifest), ("evidence", self.fixture.evidence),
                            ("candidate", self.candidate)):
            (self.root / (name + ".json")).write_text(json.dumps(value), encoding="utf-8")

    def record(self, confirmed=True):
        (self.root / "request.json").write_text(json.dumps(self.request), encoding="utf-8")
        args = ["record-mapping-review", "--manifest", self.root / "manifest.json", "--evidence",
                self.root / "evidence.json", "--workspace", self.root, "--character", self.fixture.psd["path"],
                "--candidate", self.root / "candidate.json", "--request", self.root / "request.json"]
        if confirmed:
            args.append("--confirm-human-review")
        return self.fixture.fixture.invoke(*args)

    def template(self, decision):
        path = self.root / "decision.json"
        path.write_text(json.dumps(decision), encoding="utf-8")
        return self.fixture.fixture.invoke("annotation-template", "--manifest", self.root / "manifest.json",
                                           "--decision", path)

    def test_confirmation_required_and_no_decision_written(self):
        code, result = self.record(confirmed=False)
        self.assertEqual(code, 1)
        self.assertEqual(result["reason_code"], "benchmark_mapping_human_confirmation_required")
        self.assertFalse(self.fixture.fixture.state.exists())

    def test_accept_exact_read_and_idempotent_pending_template(self):
        code, decision = self.record()
        self.assertEqual(code, 0)
        self.assertEqual(self.record(), (code, decision))
        self.assertEqual(read_mapping_decision(self.fixture.fixture.state, self.fixture.manifest,
                                              canonical_sha256(decision)), decision)
        code, template = self.template(decision)
        self.assertEqual(code, 0)
        self.assertEqual(template["annotation_status"], "pending")
        self.assertEqual(template["layer_semantics"], [])
        self.assertEqual(template["joint_observations"], [])
        validate_annotation_template(self.fixture.manifest, decision, template)
        from jsonschema import Draft202012Validator
        schema = json.loads((ROOT / "schemas/benchmark-annotation-template-v1.schema.json").read_text())
        Draft202012Validator(schema).validate(template)

    def test_rejection_records_but_does_not_admit_annotations(self):
        self.request.update(action="reject")
        self.request["checks"]["coordinate_alignment"] = False
        code, decision = self.record()
        self.assertEqual(code, 0)
        code, result = self.template(decision)
        self.assertEqual(code, 1)
        self.assertEqual(result["reason_code"], "benchmark_annotation_accepted_mapping_required")

    def test_incomplete_checks_stale_request_and_source_drift_fail(self):
        self.request["checks"]["mirror_checked"] = False
        self.assertEqual(self.record()[0], 1)
        self.request["checks"]["mirror_checked"] = True
        self.request["candidate_sha256"] = "0" * 64
        self.assertEqual(self.record()[0], 1)
        self.request["candidate_sha256"] = canonical_sha256(self.candidate)
        path = self.root / self.fixture.psd["path"]
        path.write_bytes(path.read_bytes() + b"tampered")
        self.assertEqual(self.record()[0], 1)
        self.assertFalse(self.fixture.fixture.state.exists())

    def test_rehashing_modified_decision_cannot_forge_acceptance(self):
        self.request["action"] = "reject"
        _, decision = self.record()
        forged = deepcopy(decision)
        forged.update(action="accept", mapping_status="reviewed_accepted")
        digest = publish_report(self.fixture.fixture.state, self.fixture.manifest["dataset_id"],
                                "mapping-decisions", forged)
        with self.assertRaises(ValueError):
            read_mapping_decision(self.fixture.fixture.state, self.fixture.manifest, digest)
        self.assertEqual(self.template(forged)[0], 1)


if __name__ == "__main__":
    unittest.main()
