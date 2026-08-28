"""Draft 2020-12 schema coverage for P10.7b readiness documents."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for item in (ROOT, SRC):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

try:
    from jsonschema import Draft202012Validator
    from jsonschema.exceptions import ValidationError
except ImportError:  # pragma: no cover - optional developer dependency
    Draft202012Validator = None
    ValidationError = Exception

from autospine_workbench.spine42_v3_readiness import (  # noqa: E402
    audit_spine42_v3_readiness,
)
from autospine_workbench.spine42_v3_readiness_manifest import (  # noqa: E402
    require_spine42_v3_readiness_request,
)


SHA = {name: digit * 64 for name, digit in zip((
    "manifest", "rig", "p3", "motion", "motion_bundle", "seam",
    "seam_bundle", "v3", "v3_bundle", "skeleton", "spine", "capture",
), "123456789abc", strict=True)}


def request(*, addressed: bool = False) -> dict:
    row = {
        "project_id": "sample-a",
        "layer_manifest_sha256": SHA["manifest"],
        "p3_rig_sha256": SHA["rig"],
        "p3_bundle_sha256": SHA["p3"],
        "reviewed_motion_address": None,
        "reviewed_seam_anchor_set_address": None,
        "motion_instance_v3_address": None,
        "spine42_v3_address": None,
        "runtime_capture_address": None,
        "raster_review_decision": None,
    }
    if addressed:
        row.update(
            reviewed_motion_address={
                "motion_instance_v2_sha256": SHA["motion"],
                "bundle_sha256": SHA["motion_bundle"],
            },
            reviewed_seam_anchor_set_address={
                "reviewed_seam_anchor_set_sha256": SHA["seam"],
                "bundle_sha256": SHA["seam_bundle"],
            },
            motion_instance_v3_address={
                "motion_instance_v3_sha256": SHA["v3"],
                "bundle_sha256": SHA["v3_bundle"],
            },
            spine42_v3_address={
                "skeleton_json_sha256": SHA["skeleton"],
                "bundle_sha256": SHA["spine"],
            },
            runtime_capture_address={
                "spine42_v3_bundle_sha256": SHA["spine"],
                "capture_bundle_sha256": SHA["capture"],
            },
        )
    return {
        "format": "autospine-spine42-v3-readiness-request",
        "format_version": 1,
        "samples": [row],
    }


@unittest.skipIf(Draft202012Validator is None, "jsonschema is not installed")
class Spine42V3ReadinessSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.request_schema = json.loads((
            ROOT / "schemas" / "spine42-v3-readiness-request-v1.schema.json"
        ).read_text(encoding="utf-8"))
        cls.report_schema = json.loads((
            ROOT / "schemas" / "spine42-v3-readiness-report-v1.schema.json"
        ).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(cls.request_schema)
        Draft202012Validator.check_schema(cls.report_schema)
        cls.request_validator = Draft202012Validator(cls.request_schema)
        cls.report_validator = Draft202012Validator(cls.report_schema)

    def test_actual_required_requests_and_audit_report_validate(self):
        minimal = require_spine42_v3_readiness_request(request())
        addressed = require_spine42_v3_readiness_request(request(addressed=True))
        self.request_validator.validate(minimal)
        self.request_validator.validate(addressed)
        with tempfile.TemporaryDirectory() as temporary:
            report = audit_spine42_v3_readiness(minimal, Path(temporary))
        self.report_validator.validate(report)

    def test_request_rejects_extra_fields_and_non_lowercase_sha(self):
        extra_root = request()
        extra_root["extra"] = False
        extra_sample = request()
        extra_sample["samples"][0]["extra"] = None
        extra_address = request(addressed=True)
        extra_address["samples"][0]["reviewed_motion_address"]["extra"] = "a" * 64
        uppercase_sha = request()
        uppercase_sha["samples"][0]["p3_rig_sha256"] = "A" * 64
        for bad in (extra_root, extra_sample, extra_address, uppercase_sha):
            with self.subTest(document=bad), self.assertRaises(ValidationError):
                self.request_validator.validate(bad)

    def test_report_rejects_extra_status_authority_and_checkpoint_reorder(self):
        validated = require_spine42_v3_readiness_request(request())
        with tempfile.TemporaryDirectory() as temporary:
            report = audit_spine42_v3_readiness(validated, Path(temporary))
        variants = []
        extra = deepcopy(report)
        extra["extra"] = False
        variants.append(extra)
        status = deepcopy(report)
        status["samples"][0]["checkpoints"][0]["status"] = "unknown"
        variants.append(status)
        authority = deepcopy(report)
        authority["authority"]["release"] = True
        variants.append(authority)
        release_gate = deepcopy(report)
        release_gate["release_gate"]["status"] = "open"
        variants.append(release_gate)
        reordered = deepcopy(report)
        reordered["samples"][0]["checkpoints"][0:2] = reversed(
            reordered["samples"][0]["checkpoints"][0:2]
        )
        variants.append(reordered)
        for bad in variants:
            with self.subTest(document=bad), self.assertRaises(ValidationError):
                self.report_validator.validate(bad)

    def test_descriptions_delegate_non_structural_invariants(self):
        request_description = self.request_schema["description"]
        report_description = self.report_schema["description"]
        for term in ("dependency", "canonical", "self-hash", "semantic validator"):
            self.assertIn(term, request_description)
        for term in ("canonical", "self-hash", "semantic validator"):
            self.assertIn(term, report_description)

    def test_report_evidence_and_semantics_shapes_are_exact(self):
        definitions = self.report_schema["$defs"]
        expected = {
            "p3Evidence": {
                "candidate_sha256", "relationship_count",
                "review_required_count", "unobservable_count",
            },
            "seamPendingEvidence": {
                "candidate_sha256", "unobservable_count",
            },
        }
        for name, fields in expected.items():
            with self.subTest(definition=name):
                definition = definitions[name]
                self.assertFalse(definition["additionalProperties"])
                self.assertEqual(set(definition["required"]), fields)
                self.assertEqual(set(definition["properties"]), fields)

        semantics = definitions["semantics"]
        semantic_fields = {
            "scope", "current_head_discovery", "external_stage_execution",
            "pure_replay_compilation", "human_review_substitution",
            "p6_setup_raster_comparison_included", "release_authority",
        }
        self.assertFalse(semantics["additionalProperties"])
        self.assertEqual(set(semantics["required"]), semantic_fields)
        self.assertEqual(set(semantics["properties"]), semantic_fields)
        self.assertNotIn("compiler_execution", semantics["properties"])
        self.assertEqual(
            semantics["properties"]["pure_replay_compilation"],
            {"const": True},
        )

    def test_report_rejects_non_six_relationships_and_revision_over_cap(self):
        validated = require_spine42_v3_readiness_request(request())
        with tempfile.TemporaryDirectory() as temporary:
            report = audit_spine42_v3_readiness(validated, Path(temporary))

        wrong_relationship_count = deepcopy(report)
        wrong_relationship_count["samples"][0]["checkpoints"][0]["evidence"] = {
            "candidate_sha256": "a" * 64,
            "relationship_count": 5,
            "review_required_count": 5,
            "unobservable_count": 0,
        }
        revision_over_cap = deepcopy(report)
        revision_over_cap["samples"][0]["checkpoints"][2]["evidence"] = {
            "candidate_sha256": "a" * 64,
            "decision_sha256": "b" * 64,
            "review_revision": 65,
            "reviewed_seam_anchor_set_sha256": "c" * 64,
            "bundle_sha256": "d" * 64,
        }

        for bad in (wrong_relationship_count, revision_over_cap):
            with self.subTest(document=bad), self.assertRaises(ValidationError):
                self.report_validator.validate(bad)


if __name__ == "__main__":
    unittest.main()
