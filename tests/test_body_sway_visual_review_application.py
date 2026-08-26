"""Shared application-service tests for exact P10.3c visual review."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for item in (ROOT, SRC):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from autospine_workbench.body_sway_visual_review_address import (  # noqa: E402
    ExactVisualReviewAddress,
    ExactVisualReviewAddressError,
)
from autospine_workbench.body_sway_visual_review_application import (  # noqa: E402
    BodySwayVisualReviewApplication,
    BodySwayVisualReviewApplicationError,
)
from autospine_workbench.body_sway_visual_review_history import (  # noqa: E402
    BodySwayVisualReviewRevisionConflict,
)
from autospine_workbench.body_sway_visual_review_submission import (  # noqa: E402
    BodySwayVisualReviewSubmissionError,
    require_body_sway_visual_review_submission,
)
from tests.body_sway_runtime_capture_helpers import (  # noqa: E402
    fake_runtime_profile,
)
from tests.body_sway_visual_review_helpers import (  # noqa: E402
    BodySwayVisualReviewFixture,
    review_rows,
)


class BodySwayVisualReviewApplicationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.fixture = BodySwayVisualReviewFixture(
            self.root, distinct_images=True
        )
        self.address = ExactVisualReviewAddress(*self.fixture.address)
        self.service = BodySwayVisualReviewApplication(
            self.fixture.state_root
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def prepare(self):
        with fake_runtime_profile():
            return self.service.prepare(self.address)

    def payload(self, prepared, *, action="approve") -> dict:
        return {
            "base_revision": prepared.history.current_revision,
            "candidate_sha256": prepared.candidate_sha256,
            "previous_decision_sha256":
                prepared.history.head_decision_sha256,
            "review": {"reviewer_id": "artist-01", "notes": "full review"},
            "decisions": review_rows(
                prepared.candidate_document, action=action
            ),
        }

    def test_prepare_is_read_only_and_returns_exact_bounded_history(self):
        before = _complete_tree(self.fixture.state_root)
        first = self.prepare()
        second = self.prepare()
        self.assertEqual(before, _complete_tree(self.fixture.state_root))
        self.assertEqual(first.candidate_sha256, second.candidate_sha256)
        self.assertEqual(self.address, first.address)
        self.assertEqual("candidate_only", first.candidate_document["status"])
        self.assertEqual((0, None, ()), (
            first.history.current_revision,
            first.history.head_decision_sha256,
            first.history.rows,
        ))
        self.assertNotIn("path", _recursive_keys(first.candidate_document))

    def test_image_uses_authoritative_case_path_and_rejects_crosswire(self):
        prepared = self.prepare()
        cases = prepared.candidate_document["cases"]
        first, second = cases[0], cases[1]
        with fake_runtime_profile():
            image = self.service.image_evidence(
                self.address,
                candidate_sha256=prepared.candidate_sha256,
                case_id=first["case_id"],
                png_sha256=first["image"]["png_sha256"],
            )
        self.assertEqual((640, 640), (image.width, image.height))
        self.assertEqual(first["evidence_sha256"], image.evidence_sha256)
        self.assertEqual(first["image"]["size_bytes"], len(image.png_bytes))
        with fake_runtime_profile(), self.assertRaises(
            BodySwayVisualReviewApplicationError
        ):
            self.service.image_evidence(
                self.address,
                candidate_sha256=prepared.candidate_sha256,
                case_id=first["case_id"],
                png_sha256=second["image"]["png_sha256"],
            )

    def test_initial_submit_retry_and_stale_conflict_are_authoritative(self):
        prepared = self.prepare()
        payload = self.payload(prepared)
        with fake_runtime_profile():
            first = self.service.submit(self.address, payload)
            repeated = self.service.submit(self.address, payload)
        self.assertEqual(1, first.revision)
        self.assertFalse(first.reused)
        self.assertTrue(repeated.reused)
        self.assertEqual(first.decision_sha256, repeated.decision_sha256)
        self.assertEqual("sampled_visual_approved", first.status)
        self.assertEqual("blocked", first.release_gate_status)

        stale = deepcopy(payload)
        stale["review"]["notes"] = "different stale revision"
        with fake_runtime_profile(), self.assertRaises(
            BodySwayVisualReviewRevisionConflict
        ) as raised:
            self.service.submit(self.address, stale)
        self.assertEqual((1, 1), (
            raised.exception.requested_revision,
            raised.exception.current_revision,
        ))

    def test_second_revision_and_rejection_never_open_release_gate(self):
        prepared = self.prepare()
        with fake_runtime_profile():
            first = self.service.submit(
                self.address, self.payload(prepared)
            )
        current = self.prepare()
        rejected = self.payload(current, action="reject")
        with fake_runtime_profile():
            second = self.service.submit(self.address, rejected)
        self.assertEqual((2, "sampled_visual_rejected", "blocked"), (
            second.revision, second.status, second.release_gate_status,
        ))
        self.assertEqual(first.decision_sha256,
                         rejected["previous_decision_sha256"])
        self.assertIn(
            "sampled_visual_review_rejected",
            second.release_gate_reason_codes,
        )

    def test_exact_decision_requires_both_revision_and_digest(self):
        prepared = self.prepare()
        with fake_runtime_profile():
            submitted = self.service.submit(
                self.address, self.payload(prepared)
            )
            loaded = self.service.exact_decision(
                self.address,
                candidate_sha256=prepared.candidate_sha256,
                revision=1,
                decision_sha256=submitted.decision_sha256,
            )
        self.assertEqual(1, loaded.revision)
        self.assertEqual(submitted.decision_sha256, loaded.decision_sha256)
        self.assertEqual("sampled_visual_approved",
                         loaded.decision_document["status"])
        with fake_runtime_profile(), self.assertRaises(
            BodySwayVisualReviewApplicationError
        ):
            self.service.exact_decision(
                self.address,
                candidate_sha256=prepared.candidate_sha256,
                revision=2,
                decision_sha256=submitted.decision_sha256,
            )

    def test_submission_rejects_extra_nonfinite_duplicate_and_base_mismatch(self):
        prepared = self.prepare()
        valid = self.payload(prepared)
        normalized = require_body_sway_visual_review_submission(valid)
        self.assertEqual(0, normalized.base_revision)
        self.assertIsNone(normalized.previous_decision_sha256)
        mutations = []
        extra = deepcopy(valid)
        extra["revision"] = 1
        mutations.append(extra)
        nonfinite = deepcopy(valid)
        nonfinite["decisions"][0]["notes"] = float("nan")
        mutations.append(nonfinite)
        duplicate = deepcopy(valid)
        duplicate["decisions"][1] = deepcopy(duplicate["decisions"][0])
        mutations.append(duplicate)
        predecessor = deepcopy(valid)
        predecessor["previous_decision_sha256"] = "a" * 64
        mutations.append(predecessor)
        for value in mutations:
            with self.subTest(value=value), self.assertRaises(
                BodySwayVisualReviewSubmissionError
            ):
                require_body_sway_visual_review_submission(value)
        with patch(
            "autospine_workbench.body_sway_visual_review_submission."
            "MAX_VISUAL_REVIEW_DOCUMENT_BYTES",
            1,
        ), self.assertRaises(BodySwayVisualReviewSubmissionError):
            require_body_sway_visual_review_submission(valid)

    def test_address_rejects_unsafe_project_and_non_lowercase_digest(self):
        values = list(self.fixture.address)
        for index, invalid in ((0, "../sample"), (1, values[1].upper())):
            changed = list(values)
            changed[index] = invalid
            with self.subTest(index=index), self.assertRaises(
                ExactVisualReviewAddressError
            ):
                ExactVisualReviewAddress(*changed)


def _complete_tree(root: Path) -> tuple[tuple[str, str, bytes], ...]:
    rows = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        rows.append((relative, "directory", b"")) if path.is_dir() \
            else rows.append((relative, "file", path.read_bytes()))
    return tuple(rows)


def _recursive_keys(value) -> set[str]:
    if type(value) is dict:
        keys = set(value)
        for item in value.values():
            keys.update(_recursive_keys(item))
        return keys
    if type(value) is list:
        keys = set()
        for item in value:
            keys.update(_recursive_keys(item))
        return keys
    return set()


if __name__ == "__main__":
    unittest.main()
