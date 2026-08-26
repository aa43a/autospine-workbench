"""Tests for P9.1 reviewed heading evidence compilation."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.heading_evidence import (  # noqa: E402
    HeadingEvidenceError,
    compile_heading_evidence,
)
from autospine_workbench.heading_evidence_validation import (  # noqa: E402
    HeadingEvidenceValidationError,
    heading_evidence_sha256,
    require_heading_evidence,
)
from autospine_workbench.kimodo_policy_evidence import (  # noqa: E402
    compile_kimodo_policy_evidence,
)
from tests.test_kimodo_policy_evidence import _bundles  # noqa: E402
from tests.test_kimodo_policy_map_validation import policy_document  # noqa: E402

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover
    Draft202012Validator = None


class HeadingEvidenceTests(unittest.TestCase):
    def test_complete_evidence_is_deterministic_review_only_and_crosschecked(self):
        with tempfile.TemporaryDirectory() as temporary:
            p7, p8 = _bundles(Path(temporary))
            raw = compile_kimodo_policy_evidence(p7, p8).document
            policy = policy_document(p7.kimodo_map, p8.camera)
            first = compile_heading_evidence(raw, policy, p7, p8)
            second = compile_heading_evidence(raw, policy, p7, p8)
            self.assertEqual(first.canonical_bytes, second.canonical_bytes)
            self.assertEqual(first.sha256, heading_evidence_sha256(first.document))
            document = first.document
            require_heading_evidence(document)
            self._schema(document)
            self.assertEqual("available", document["status"])
            self.assertEqual([0.0, 0.0, 1.0], document["frames"][0]["world_direction_xyz"])
            self.assertEqual(0.0, document["frames"][0]["unwrapped_yaw_deg"])
            self.assertEqual(0.0, document["summary"]["maximum_root_forward_angle_error_deg"])
            self.assertFalse(document["policy"]["candidate_emitted"])
            self.assertFalse(document["policy"]["runtime_timeline_emitted"])

    def test_core_evidence_stays_explicitly_unavailable(self):
        with tempfile.TemporaryDirectory() as temporary:
            p7, p8 = _bundles(Path(temporary), inventory="core-v1")
            raw = compile_kimodo_policy_evidence(p7, p8).document
            document = compile_heading_evidence(
                raw, policy_document(p7.kimodo_map, p8.camera), p7, p8
            ).document
            require_heading_evidence(document)
            self._schema(document)
            self.assertEqual("unavailable", document["status"])
            self.assertEqual([], document["frames"])
            self.assertEqual(
                "source_heading_unavailable", document["summary"]["reason_code"]
            )

    def test_rejects_stale_raw_evidence_and_stale_policy_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            p7, p8 = _bundles(Path(temporary))
            raw = compile_kimodo_policy_evidence(p7, p8).document
            policy = policy_document(p7.kimodo_map, p8.camera)
            changed = deepcopy(raw)
            changed["signals"]["foot_contact_channels"]["channels"][0]["values"][0] = False
            with self.assertRaises(HeadingEvidenceError):
                compile_heading_evidence(changed, policy, p7, p8)
            policy["source"]["camera_sha256"] = "0" * 64
            with self.assertRaises(HeadingEvidenceError):
                compile_heading_evidence(raw, policy, p7, p8)

    def test_validator_rejects_mapped_math_unwrap_and_runtime_guessing(self):
        with tempfile.TemporaryDirectory() as temporary:
            p7, p8 = _bundles(Path(temporary))
            raw = compile_kimodo_policy_evidence(p7, p8).document
            baseline = compile_heading_evidence(
                raw, policy_document(p7.kimodo_map, p8.camera), p7, p8
            ).document
            mutations = (
                lambda value: value["frames"][0].update(camera_depth_component=0.5),
                lambda value: value["frames"][1].update(unwrapped_yaw_deg=30.0),
                lambda value: value["policy"].update(runtime_timeline_emitted=True),
                lambda value: value["frames"][0].update(
                    root_forward_camera_depth_component=0.5
                ),
                lambda value: value["frames"][0].update(
                    root_forward_angle_error_deg=1.0
                ),
                lambda value: value["policy"]["crosscheck"].update(
                    maximum_angle_error_deg=-1.0
                ),
            )
            for mutate in mutations:
                candidate = deepcopy(baseline)
                mutate(candidate)
                with self.subTest(candidate=candidate), self.assertRaises(
                    HeadingEvidenceValidationError
                ):
                    require_heading_evidence(candidate)

    def test_policy_tolerance_cannot_hide_root_forward_mismatch(self):
        with tempfile.TemporaryDirectory() as temporary:
            p7, p8 = _bundles(Path(temporary))
            raw = compile_kimodo_policy_evidence(p7, p8).document
            policy = policy_document(p7.kimodo_map, p8.camera)
            policy["heading"]["components"] = [
                {"index": 0, "source_axis": "+Z"},
                {"index": 1, "source_axis": "+X"},
            ]
            policy["heading"]["root_local_forward_axis"] = "+Z"
            policy["heading"]["crosscheck"]["maximum_angle_error_deg"] = 5.0
            with self.assertRaisesRegex(HeadingEvidenceError, "crosscheck"):
                compile_heading_evidence(raw, policy, p7, p8)

    def _schema(self, document: dict) -> None:
        if Draft202012Validator is None:
            self.skipTest("jsonschema optional test dependency is unavailable")
        schema = json.loads(
            (ROOT / "schemas" / "heading-evidence-v1.schema.json").read_text(
                encoding="utf-8"
            )
        )
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(document)


if __name__ == "__main__":
    unittest.main()
