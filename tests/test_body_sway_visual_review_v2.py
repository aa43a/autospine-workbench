"""P10.3c v2 exact execution, human decision, and history tests."""

from __future__ import annotations

from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
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

from autospine_workbench.body_sway_visual_review_application_v2 import (  # noqa: E402
    BodySwayVisualReviewApplicationV2,
    BodySwayVisualReviewApplicationV2Error,
)
from autospine_workbench.body_sway_visual_review_address_v2 import (  # noqa: E402
    ExactVisualReviewAddressV2,
)
from autospine_workbench.body_sway_visual_review_candidate_v2 import (  # noqa: E402
    BodySwayVisualReviewCandidateV2,
    compile_body_sway_visual_review_candidate_v2,
)
from autospine_workbench.body_sway_visual_review_candidate_validation import (  # noqa: E402
    BodySwayVisualReviewCandidateValidationError,
    require_body_sway_visual_review_candidate,
)
from autospine_workbench.body_sway_visual_review_candidate_validation_v2 import (  # noqa: E402
    BodySwayVisualReviewCandidateV2ValidationError,
    require_body_sway_visual_review_candidate_v2,
)
from autospine_workbench.body_sway_visual_review_decision_v2 import (  # noqa: E402
    BodySwayVisualReviewDecisionV2Error,
    build_body_sway_visual_review_decision_v2,
)
from autospine_workbench.body_sway_visual_review_decision_validation import (  # noqa: E402
    BodySwayVisualReviewDecisionValidationError,
    require_body_sway_visual_review_decision,
)
from autospine_workbench.body_sway_visual_review_errors_v2 import (  # noqa: E402
    BodySwayVisualReviewRevisionV2Conflict,
)
from autospine_workbench.body_sway_visual_review_profile import (  # noqa: E402
    CANDIDATE_NAMESPACE as V1_CANDIDATE_NAMESPACE,
    DECISION_NAMESPACE as V1_DECISION_NAMESPACE,
)
from autospine_workbench.body_sway_visual_review_profile_v2 import (  # noqa: E402
    CANDIDATE_NAMESPACE, DECISION_NAMESPACE,
)
from autospine_workbench.body_sway_visual_review_verified_head_v2 import (  # noqa: E402
    read_body_sway_visual_review_verified_head_v2,
)
from autospine_workbench.p10_preview_v2_commands import (  # noqa: E402
    P10PreviewV2CommandError,
)
from tests.body_sway_visual_review_v2_helpers import (  # noqa: E402
    BodySwayVisualReviewV2Fixture, build_visual_review_v2_inputs,
    fake_runtime_profile_v2, review_rows_v2,
)


class BodySwayVisualReviewV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shared = tempfile.TemporaryDirectory()
        cls.preview, cls.execution = build_visual_review_v2_inputs(
            Path(cls.shared.name),
        )

    @classmethod
    def tearDownClass(cls):
        cls.shared.cleanup()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.fixture = BodySwayVisualReviewV2Fixture(
            Path(self.temporary.name), self.preview, self.execution,
        )
        self.service = BodySwayVisualReviewApplicationV2(
            self.fixture.state_root,
        )

    def tearDown(self):
        self.temporary.cleanup()

    def current(self):
        return fake_runtime_profile_v2(), patch(
            "autospine_workbench.body_sway_visual_review_application_v2."
            "require_exact_preview_v2_for_mount",
            return_value=self.fixture.preview,
        )

    def prepare(self):
        runtime, preview = self.current()
        with runtime, preview:
            return self.service.prepare(self.fixture.address, object())

    def payload(self, prepared, *, action="approve"):
        return {
            "base_revision": prepared.history.current_revision,
            "candidate_sha256": prepared.candidate_sha256,
            "previous_decision_sha256": prepared.history.head_decision_sha256,
            "review": {"reviewer_id": "artist-01", "notes": "full review"},
            "decisions": review_rows_v2(
                prepared.candidate_document, action=action,
            ),
        }

    def submit(self, payload):
        runtime, preview = self.current()
        with runtime, preview:
            return self.service.submit(self.fixture.address, object(), payload)

    def test_candidate_is_deterministic_exact_and_version_isolated(self):
        with fake_runtime_profile_v2():
            first = compile_body_sway_visual_review_candidate_v2(
                self.fixture.verified, self.fixture.preview,
            )
            second = compile_body_sway_visual_review_candidate_v2(
                self.fixture.verified, self.fixture.preview,
            )
        self.assertEqual(first.canonical_bytes, second.canonical_bytes)
        source = first.document["source"]
        self.assertEqual(2, first.document["format_version"])
        self.assertEqual(self.fixture.address.runtime_execution_bundle_sha256,
                         source["runtime_execution_bundle_sha256"])
        self.assertEqual(self.fixture.address.capture_artifact_set_sha256,
                         source["capture_artifact_set_sha256"])
        self.assertEqual(self.fixture.preview.document["source"]
                         ["current_p10_1_head"], source["current_p10_1_head"])
        with self.assertRaises(BodySwayVisualReviewCandidateValidationError):
            require_body_sway_visual_review_candidate(first.document)

    def test_exact_binding_rejects_detached_current_head_tamper(self):
        with fake_runtime_profile_v2():
            candidate = compile_body_sway_visual_review_candidate_v2(
                self.fixture.verified, self.fixture.preview,
            )
        changed = candidate.document
        changed["source"]["current_p10_1_head"]["revision"] += 1
        require_body_sway_visual_review_candidate_v2(changed)
        with fake_runtime_profile_v2(), self.assertRaises(
            BodySwayVisualReviewCandidateV2ValidationError,
        ):
            require_body_sway_visual_review_candidate_v2(
                changed, execution=self.fixture.verified,
                preview=self.fixture.preview,
            )

    def test_decision_requires_explicit_exhaustive_human_choices(self):
        with fake_runtime_profile_v2():
            candidate = compile_body_sway_visual_review_candidate_v2(
                self.fixture.verified, self.fixture.preview,
            ).document
        decision = build_body_sway_visual_review_decision_v2(
            candidate, review={"reviewer_id": "artist", "notes": "checked"},
            decisions=review_rows_v2(candidate),
        )
        self.assertEqual((2, "human", "sampled_visual_approved"), (
            decision.document["format_version"],
            decision.document["review"]["method"],
            decision.document["status"],
        ))
        with self.assertRaises(BodySwayVisualReviewDecisionValidationError):
            require_body_sway_visual_review_decision(decision.document)
        with self.assertRaises(BodySwayVisualReviewDecisionV2Error):
            build_body_sway_visual_review_decision_v2(
                candidate,
                review={"reviewer_id": "artist", "notes": "checked"},
                decisions=review_rows_v2(candidate)[:-1],
            )
        with self.assertRaises(BodySwayVisualReviewDecisionV2Error):
            build_body_sway_visual_review_decision_v2(
                candidate,
                review={"reviewer_id": "artist", "notes": "checked"},
                decisions=[],
            )

    def test_prepare_is_read_only_and_image_is_exact(self):
        before = _tree(self.fixture.state_root)
        prepared = self.prepare()
        self.assertEqual(before, _tree(self.fixture.state_root))
        self.assertEqual((0, None), (
            prepared.history.current_revision,
            prepared.history.head_decision_sha256,
        ))
        self.assertNotIn("path", _keys(prepared.candidate_document))
        row = prepared.candidate_document["cases"][0]
        runtime, preview = self.current()
        with runtime, preview:
            image = self.service.image_evidence(
                self.fixture.address, object(),
                candidate_sha256=prepared.candidate_sha256,
                case_id=row["case_id"],
                png_sha256=row["image"]["png_sha256"],
            )
        self.assertEqual((640, 640), (image.width, image.height))
        self.assertEqual(row["evidence_sha256"], image.evidence_sha256)

    def test_submit_retry_revision_and_verified_head_are_append_only(self):
        initial = self.prepare()
        payload = self.payload(initial)
        first = self.submit(payload)
        repeated = self.submit(payload)
        self.assertEqual(first.decision_sha256, repeated.decision_sha256)
        self.assertEqual((1, False, True), (
            first.revision, first.reused, repeated.reused,
        ))
        current = self.prepare()
        second = self.submit(self.payload(current, action="reject"))
        self.assertEqual((2, "sampled_visual_rejected", "blocked"), (
            second.revision, second.status, second.release_gate_status,
        ))
        with fake_runtime_profile_v2():
            candidate = compile_body_sway_visual_review_candidate_v2(
                self.fixture.verified, self.fixture.preview,
            )
            head = read_body_sway_visual_review_verified_head_v2(
                self.fixture.state_root, candidate, self.fixture.verified,
                self.fixture.preview,
            )
        self.assertEqual(second.decision_sha256,
                         head.snapshot.head_decision_sha256)
        self.assertEqual(2, head.decision.document["review"]["revision"])

    def test_stale_revision_conflicts_and_namespaces_never_alias_v1(self):
        prepared = self.prepare()
        payload = self.payload(prepared)
        self.submit(payload)
        stale = deepcopy(payload)
        stale["review"]["notes"] = "different bytes"
        with self.assertRaises(BodySwayVisualReviewRevisionV2Conflict):
            self.submit(stale)
        build = self.fixture.state_root / "builds" \
            / self.fixture.address.project_id
        self.assertTrue((build / CANDIDATE_NAMESPACE).is_dir())
        self.assertTrue((build / DECISION_NAMESPACE).is_dir())
        self.assertFalse((build / V1_CANDIDATE_NAMESPACE).exists())
        self.assertFalse((build / V1_DECISION_NAMESPACE).exists())
        self.assertFalse(any(path.name == "latest"
                             for path in build.rglob("*")))

    def test_exact_decision_and_wrong_image_identity_fail_closed(self):
        prepared = self.prepare()
        submitted = self.submit(self.payload(prepared))
        runtime, preview = self.current()
        with runtime, preview:
            exact = self.service.exact_decision(
                self.fixture.address, object(),
                candidate_sha256=prepared.candidate_sha256,
                revision=1, decision_sha256=submitted.decision_sha256,
            )
        self.assertEqual(submitted.decision_sha256, exact.decision_sha256)
        cases = prepared.candidate_document["cases"]
        runtime, preview = self.current()
        with runtime, preview, self.assertRaises(
            BodySwayVisualReviewApplicationV2Error,
        ):
            self.service.image_evidence(
                self.fixture.address, object(),
                candidate_sha256=prepared.candidate_sha256,
                case_id=cases[0]["case_id"],
                png_sha256=cases[1]["image"]["png_sha256"],
            )

    def test_four_part_address_and_concurrent_head_fail_closed(self):
        values = list(self.fixture.address.reader_arguments)
        replacements = ("other-project", "1" * 64, "2" * 64, "3" * 64)
        for index, replacement in enumerate(replacements):
            changed = list(values)
            changed[index] = replacement
            runtime, preview = self.current()
            with self.subTest(index=index), runtime, preview, self.assertRaises(
                BodySwayVisualReviewApplicationV2Error,
            ):
                self.service.prepare(
                    ExactVisualReviewAddressV2(*changed), object(),
                )
        prepared = self.prepare()
        first = self.payload(prepared)
        second = deepcopy(first)
        second["review"]["notes"] = "competing human review"

        def attempt(payload):
            try:
                return self.service.submit(
                    self.fixture.address, object(), payload,
                )
            except BodySwayVisualReviewRevisionV2Conflict as exc:
                return exc

        runtime, preview = self.current()
        with runtime, preview, ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, (first, second)))
        self.assertEqual(1, sum(
            isinstance(item, BodySwayVisualReviewRevisionV2Conflict)
            for item in results
        ))
        self.assertEqual(1, self.prepare().history.current_revision)

    def test_mount_replay_head_drift_is_zero_write(self):
        prepared = self.prepare()
        payload = self.payload(prepared)
        before = _tree(self.fixture.state_root)
        runtime, _preview = self.current()
        with runtime, patch(
            "autospine_workbench.body_sway_visual_review_application_v2."
            "require_exact_preview_v2_for_mount",
            side_effect=P10PreviewV2CommandError("head drift"),
        ), self.assertRaises(BodySwayVisualReviewApplicationV2Error):
            self.service.submit(self.fixture.address, object(), payload)
        self.assertEqual(before, _tree(self.fixture.state_root))


def _tree(root):
    return tuple((path.relative_to(root).as_posix(), path.is_dir(),
                  b"" if path.is_dir() else path.read_bytes())
                 for path in sorted(root.rglob("*")))


def _keys(value):
    if isinstance(value, dict):
        return set(value).union(*(_keys(item) for item in value.values()))
    if isinstance(value, list):
        return set().union(*(_keys(item) for item in value)) if value else set()
    return set()


if __name__ == "__main__":
    unittest.main()
