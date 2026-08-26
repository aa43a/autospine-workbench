"""Exhaustive P10.3c human visual decision contract tests."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (ROOT, SRC):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

try:
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover - optional test dependency
    Draft202012Validator = None

from autospine_workbench.body_sway_runtime_capture_reader import (  # noqa: E402
    VerifiedBodySwayRuntimeCaptureReader,
)
from autospine_workbench.body_sway_visual_review_candidate import (  # noqa: E402
    compile_body_sway_visual_review_candidate,
)
from autospine_workbench.body_sway_visual_review_decision import (  # noqa: E402
    BodySwayVisualReviewDecisionError,
    build_body_sway_visual_review_decision,
)
from autospine_workbench.body_sway_visual_review_decision_validation import (  # noqa: E402
    BodySwayVisualReviewDecisionValidationError,
    require_body_sway_visual_review_decision,
)
from tests.body_sway_runtime_capture_helpers import (  # noqa: E402
    fake_runtime_profile,
)
from tests.body_sway_visual_review_helpers import (  # noqa: E402
    BodySwayVisualReviewFixture,
    review_rows,
)


class BodySwayVisualReviewDecisionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        fixture = BodySwayVisualReviewFixture(self.root)
        with fake_runtime_profile():
            capture = VerifiedBodySwayRuntimeCaptureReader(
                fixture.state_root
            ).load(*fixture.address)
            self.candidate = compile_body_sway_visual_review_candidate(capture)
        self.review = {
            "reviewer_id": "artist-01",
            "notes": "checked all sampled poses at full resolution",
        }

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def build(self, rows=None, previous=None):
        return build_body_sway_visual_review_decision(
            self.candidate.document,
            review=self.review,
            decisions=rows or review_rows(self.candidate.document),
            previous_decision=(previous.document if previous else None),
        )

    def test_all_approve_derives_sampled_approval_but_never_release(self) -> None:
        decision = self.build()
        document = decision.document
        self.assertEqual("sampled_visual_approved", document["status"])
        self.assertEqual("blocked", document["release_gate"]["status"])
        self.assertFalse(document["semantics"]["publishable"])
        self.assertFalse(document["semantics"]["release_authority"])
        self.assertFalse(document["semantics"]["safe_range_claimed"])
        self.assertEqual(
            "shape-and-internal-compiler-seals-only",
            document["semantics"]["detached_validation_scope"],
        )
        self.assertTrue(document["semantics"]["exact_source_replay_required"])
        self.assertEqual(1, document["review"]["revision"])
        self.assertIsNone(document["review"]["supersedes_decision_sha256"])

    def test_reject_or_unobservable_derives_rejected_status(self) -> None:
        for action in ("reject", "unobservable"):
            with self.subTest(action=action):
                rows = review_rows(self.candidate.document)
                rows[1]["action"] = action
                rows[1]["notes"] = f"{action} because the limb is hidden"
                document = self.build(rows).document
                self.assertEqual("sampled_visual_rejected", document["status"])
                self.assertIn(
                    "sampled_visual_review_rejected",
                    document["release_gate"]["reason_codes"],
                )

    def test_decisions_cover_exactly_all_cases_and_evidence(self) -> None:
        rows = review_rows(self.candidate.document)
        invalid = (
            rows[:-1],
            rows + [deepcopy(rows[0])],
            [*rows[:-1], {**rows[-1], "case_id": "unknown-case"}],
            [{**rows[0], "evidence_sha256": "a" * 64}, *rows[1:]],
            list(reversed(rows)),
        )
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(
                BodySwayVisualReviewDecisionError
            ):
                self.build(value)

    def test_rejection_requires_notes_and_unknown_fields_are_forbidden(self) -> None:
        rows = review_rows(self.candidate.document)
        rows[0]["action"] = "reject"
        rows[0]["notes"] = " "
        with self.assertRaises(BodySwayVisualReviewDecisionError):
            self.build(rows)
        rows[0]["notes"] = "visible tear"
        rows[0]["extra"] = True
        with self.assertRaises(BodySwayVisualReviewDecisionError):
            self.build(rows)

    def test_non_mapping_decision_row_is_normalized_to_domain_error(self) -> None:
        rows = review_rows(self.candidate.document)
        rows[0] = 3
        with self.assertRaises(BodySwayVisualReviewDecisionError):
            self.build(rows)

    def test_superseding_is_explicit_linear_and_deterministic(self) -> None:
        first = self.build()
        changed = review_rows(self.candidate.document)
        changed[0]["action"] = "reject"
        changed[0]["notes"] = "found a shoulder seam"
        second = self.build(changed, previous=first)
        repeated = self.build(changed, previous=first)

        self.assertEqual(second.sha256, repeated.sha256)
        self.assertEqual(2, second.document["review"]["revision"])
        self.assertEqual(
            first.sha256,
            second.document["review"]["supersedes_decision_sha256"],
        )
        forged = deepcopy(second.document)
        forged["review"]["supersedes_decision_sha256"] = "a" * 64
        with self.assertRaises(BodySwayVisualReviewDecisionValidationError):
            require_body_sway_visual_review_decision(
                forged,
                candidates=self.candidate.document,
                previous_decision=first.document,
            )

        foreign = deepcopy(first.document)
        foreign["source"]["runtime_capture_bundle_sha256"] = "a" * 64
        with self.assertRaises(BodySwayVisualReviewDecisionValidationError):
            require_body_sway_visual_review_decision(
                second.document,
                candidates=self.candidate.document,
                previous_decision=foreign,
            )

    @unittest.skipIf(Draft202012Validator is None, "jsonschema is optional")
    def test_json_schema_accepts_initial_and_superseding_decisions(self) -> None:
        schema = json.loads((
            ROOT / "schemas" / "body-sway-visual-review-decision-v1.schema.json"
        ).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        first = self.build()
        validator.validate(first.document)
        validator.validate(self.build(previous=first).document)
        invalid = first.document
        invalid["decisions"][0]["action"] = "reject"
        invalid["decisions"][0]["notes"] = " \t\n"
        self.assertFalse(validator.is_valid(invalid))


if __name__ == "__main__":
    unittest.main()
