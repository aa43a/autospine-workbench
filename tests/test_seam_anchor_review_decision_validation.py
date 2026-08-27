"""Detached attack tests for P10.5b seam decisions."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import unittest

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - optional test dependency
    Draft202012Validator = None

from autospine_workbench.seam_anchor_review_decision import (
    build_seam_anchor_review_decision,
)
from autospine_workbench.seam_anchor_review_decision_validation import (
    SeamAnchorReviewDecisionValidationError,
    require_seam_anchor_review_decision,
    seam_anchor_review_decision_sha256,
)
from tests.seam_anchor_review_helpers import (
    review_candidate_and_rig,
    seam_review_rows,
)


ROOT = Path(__file__).resolve().parents[1]


class SeamAnchorReviewDecisionValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.candidate, cls.rig = review_candidate_and_rig()
        cls.valid = build_seam_anchor_review_decision(
            cls.candidate, cls.rig,
            review={"reviewer_id": "artist", "notes": "done"},
            decisions=seam_review_rows(cls.candidate),
        ).document

    def assert_invalid(self, mutate, *, bound=False):
        value = deepcopy(self.valid)
        mutate(value)
        with self.assertRaises(SeamAnchorReviewDecisionValidationError):
            require_seam_anchor_review_decision(
                value,
                candidates=self.candidate if bound else None,
                rig=self.rig if bound else None,
            )

    def test_detached_shape_derived_fields_and_digest_are_strict(self):
        require_seam_anchor_review_decision(self.valid)
        self.assertEqual(64, len(seam_anchor_review_decision_sha256(self.valid)))
        cases = (
            lambda row: row.__setitem__("extra", True),
            lambda row: row["semantics"].__setitem__("publishable", True),
            lambda row: row.__setitem__("status", "reviewed_anchor_set_blocked"),
            lambda row: row["summary"].__setitem__("accept_count", 5),
            lambda row: row["release_gate"].__setitem__("status", "ready"),
            lambda row: row["decisions"].reverse(),
            lambda row: row["decisions"][0].__setitem__(
                "relationship_id", "seam.unknown.left"
            ),
        )
        for mutate in cases:
            with self.subTest(mutate=mutate):
                self.assert_invalid(mutate)

    def test_candidate_bound_validation_rejects_resealed_crosswires(self):
        cases = (
            lambda row: row["source"].__setitem__(
                "seam_anchor_candidate_sha256", "a" * 64
            ),
            lambda row: row["decisions"][0].__setitem__(
                "relationship_evidence_sha256", "b" * 64
            ),
            lambda row: row["decisions"][0].__setitem__(
                "option_evidence_sha256", "c" * 64
            ),
            lambda row: row["decisions"][0]["anchors"][0]["parent"]
            .__setitem__("attachment_id", "pelvis"),
        )
        for mutate in cases:
            with self.subTest(mutate=mutate):
                self.assert_invalid(mutate, bound=True)

    def test_container_subclasses_fail_before_custom_iteration(self):
        class LyingDict(dict):
            def __iter__(self):
                raise AssertionError("must not iterate")

        with self.assertRaises(SeamAnchorReviewDecisionValidationError):
            require_seam_anchor_review_decision(LyingDict(self.valid))

    def test_schema_pins_format_relationship_order_and_semantics(self):
        schema = json.loads((
            ROOT / "schemas" / "seam-anchor-review-decision-v1.schema.json"
        ).read_text(encoding="utf-8"))
        self.assertEqual(
            "autospine-seam-anchor-review-decision",
            schema["properties"]["format"]["const"],
        )
        self.assertEqual(
            self.valid["semantics"],
            schema["properties"]["semantics"]["const"],
        )

    @unittest.skipIf(Draft202012Validator is None, "jsonschema is optional")
    def test_json_schema_accepts_output_and_rejects_reordered_rows(self):
        schema = json.loads((
            ROOT / "schemas" / "seam-anchor-review-decision-v1.schema.json"
        ).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        validator.validate(self.valid)
        blocked = build_seam_anchor_review_decision(
            self.candidate, self.rig,
            review={"reviewer_id": "artist", "notes": "blocked"},
            decisions=seam_review_rows(self.candidate, "reject"),
        ).document
        validator.validate(blocked)
        reordered = deepcopy(self.valid)
        reordered["decisions"].reverse()
        self.assertTrue(list(validator.iter_errors(reordered)))


if __name__ == "__main__":
    unittest.main()
