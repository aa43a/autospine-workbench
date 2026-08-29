"""P10.5c current-head, TOCTOU, and zero-write input tests."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
for item in (ROOT, ROOT / "src"):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from autospine_workbench.reviewed_seam_anchor_set_compiler import (
    compile_reviewed_seam_anchor_set,
)
from autospine_workbench.reviewed_seam_anchor_set_inputs import (
    ReviewedSeamAnchorSetInputsError,
    prepare_current_head_reviewed_seam_anchor_set,
    require_reviewed_seam_anchor_set_inputs,
)
from autospine_workbench.seam_anchor_candidates import SeamAnchorCandidates
from autospine_workbench.seam_anchor_review_address import (
    ExactSeamAnchorReviewAddress,
)
from autospine_workbench.seam_anchor_review_application_models import (
    ExactSeamAnchorReviewDecision,
    PreparedSeamAnchorReview,
)
from autospine_workbench.seam_anchor_review_candidate_binding import (
    BoundSeamAnchorReviewCandidate,
)
from autospine_workbench.seam_anchor_review_decision import (
    build_seam_anchor_review_decision,
)
from autospine_workbench.seam_anchor_review_decision_validation import (
    seam_anchor_review_decision_sha256,
)
from autospine_workbench.seam_anchor_review_history_models import (
    SeamAnchorReviewHistoryRow,
    SeamAnchorReviewHistorySnapshot,
)
from autospine_workbench.seam_anchor_review_json import canonical_json_bytes
from tests.p9_v2_helpers import tree
from tests.reviewed_seam_anchor_set_helpers import reviewed_set_inputs
from tests.seam_anchor_review_helpers import seam_review_rows

READY = "reviewed_anchor_set_ready_for_compile"
BLOCKED = "reviewed_anchor_set_blocked"

class _Application:
    def __init__(self, snapshots, exact, calls):
        self.snapshots = list(snapshots)
        self.exact = exact
        self.calls = calls

    def prepare(self, address):
        self.calls.append("prepare")
        return self.snapshots.pop(0)

    def exact_decision(self, address, **identity):
        self.calls.append("decision")
        return self.exact


class _Fixture:
    def __init__(self):
        candidate, decision, self.rig = reviewed_set_inputs()
        self.candidate_document = candidate
        self.decision_document = decision
        self.candidate = SeamAnchorCandidates(
            canonical_json_bytes(candidate).decode("utf-8")
        )
        self.decision_sha = seam_anchor_review_decision_sha256(decision)
        source = candidate["source"]
        self.address = ExactSeamAnchorReviewAddress(
            candidate["project_id"], source["layer_manifest_sha256"],
            source["rig_sha256"], source["bundle_sha256"],
        )
        self.history = self.make_history(
            [(self.decision_sha, READY)]
        )
        self.prepared = self.make_prepared(self.history)
        self.exact = ExactSeamAnchorReviewDecision(
            self.address, self.candidate.sha256, self.decision_sha, 1,
            canonical_json_bytes(decision).decode("utf-8"),
        )
        self.bound = BoundSeamAnchorReviewCandidate(
            self.candidate, canonical_json_bytes(self.rig).decode("utf-8")
        )

    def make_history(self, values):
        rows = tuple(
            SeamAnchorReviewHistoryRow(index, digest, status)
            for index, (digest, status) in enumerate(values, 1)
        )
        return SeamAnchorReviewHistorySnapshot(
            self.address.project_id, self.candidate.sha256, len(rows),
            len(rows), rows[-1].decision_sha256 if rows else None, rows,
        )

    def make_prepared(self, history):
        return PreparedSeamAnchorReview(
            self.address, self.candidate.sha256,
            self.candidate.canonical_bytes.decode("utf-8"), history,
            400, 400,
        )

    def run(self, root, *, snapshots=None, exact=None, bound=None,
            requested_revision=1, requested_decision=None):
        calls = []
        application = _Application(
            snapshots or [self.prepared, self.prepared],
            exact or self.exact, calls,
        )

        def load_candidate(state, address):
            calls.append("load")
            return bound or self.bound

        def compile_set(candidate, decision, rig):
            calls.append("compile")
            return compile_reviewed_seam_anchor_set(candidate, decision, rig)

        result = prepare_current_head_reviewed_seam_anchor_set(
            root, self.address,
            candidate_sha256=self.candidate.sha256,
            revision=requested_revision,
            decision_sha256=requested_decision or self.decision_sha,
            application=application,
            candidate_loader=load_candidate,
            compiler=compile_set,
        )
        return result, calls


class ReviewedSeamAnchorSetInputsTests(unittest.TestCase):
    def setUp(self):
        self.fixture = _Fixture()

    def test_ordered_double_snapshot_is_deterministic_and_zero_write(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            before = tree(root)
            first, calls = self.fixture.run(root)
            second, repeated = self.fixture.run(root)
            self.assertEqual(before, tree(root))
        self.assertEqual(
            ["prepare", "decision", "load", "compile", "prepare"], calls
        )
        self.assertEqual(calls, repeated)
        self.assertEqual(
            first.reviewed_seam_anchor_set_sha256,
            second.reviewed_seam_anchor_set_sha256,
        )
        self.assertEqual(first.canonical_bytes, second.canonical_bytes)
        self.assertEqual({
            "method": "double_snapshot",
            "scope": "compile_time",
            "revision": 1,
            "head_decision_sha256": self.fixture.decision_sha,
            "permanent_authority_claimed": False,
        }, first.head_observation)

    def test_result_and_input_documents_are_frozen_and_copy_isolated(self):
        with tempfile.TemporaryDirectory() as temporary:
            result, _calls = self.fixture.run(Path(temporary))
        leaked_candidate = result.inputs.candidate_document
        leaked_candidate["relationships"].clear()
        leaked_rig = result.inputs.rig_document
        leaked_rig["attachments"].clear()
        leaked_result = result.document
        leaked_result["relationships"].clear()
        leaked_head = result.head_observation
        leaked_head["permanent_authority_claimed"] = True
        self.assertEqual(6, len(result.inputs.candidate_document["relationships"]))
        self.assertTrue(result.inputs.rig_document["attachments"])
        self.assertEqual(6, len(result.document["relationships"]))
        self.assertFalse(result.head_observation["permanent_authority_claimed"])
        with self.assertRaises(FrozenInstanceError):
            result.inputs.review_revision = 2

    def test_head_change_after_pure_compile_is_rejected_as_toctou(self):
        changed_sha = "f" * 64
        changed = self.fixture.make_prepared(self.fixture.make_history([
            (self.fixture.decision_sha, READY), (changed_sha, READY),
        ]))
        calls = []
        application = _Application(
            [self.fixture.prepared, changed], self.fixture.exact, calls
        )

        def load_candidate(_state, _address):
            calls.append("load")
            return self.fixture.bound

        def compile_set(candidate, decision, rig):
            calls.append("compile")
            return compile_reviewed_seam_anchor_set(candidate, decision, rig)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            before = tree(root)
            with self.assertRaises(ReviewedSeamAnchorSetInputsError):
                prepare_current_head_reviewed_seam_anchor_set(
                    root, self.fixture.address,
                    candidate_sha256=self.fixture.candidate.sha256,
                    revision=1, decision_sha256=self.fixture.decision_sha,
                    application=application,
                    candidate_loader=load_candidate, compiler=compile_set,
                )
            self.assertEqual(before, tree(root))
        self.assertEqual(
            ["prepare", "decision", "load", "compile", "prepare"], calls
        )

    def test_old_head_and_blocked_head_fail_before_exact_decision(self):
        old = self.fixture.make_prepared(self.fixture.make_history([
            (self.fixture.decision_sha, READY), ("e" * 64, READY),
        ]))
        blocked = self.fixture.make_prepared(self.fixture.make_history([
            (self.fixture.decision_sha, BLOCKED),
        ]))
        for label, snapshot in (("old", old), ("blocked", blocked)):
            calls = []
            application = _Application([snapshot], self.fixture.exact, calls)
            with self.subTest(label=label), tempfile.TemporaryDirectory() \
                    as temporary, self.assertRaises(
                        ReviewedSeamAnchorSetInputsError
                    ):
                prepare_current_head_reviewed_seam_anchor_set(
                    Path(temporary), self.fixture.address,
                    candidate_sha256=self.fixture.candidate.sha256,
                    revision=1, decision_sha256=self.fixture.decision_sha,
                    application=application,
                )
            self.assertEqual(["prepare"], calls)

    def test_blocked_exact_decision_and_crosswired_p3_fail_closed(self):
        blocked = build_seam_anchor_review_decision(
            self.fixture.candidate_document, self.fixture.rig,
            review={"reviewer_id": "artist-02", "notes": "rejected"},
            decisions=seam_review_rows(
                self.fixture.candidate_document, "reject"
            ),
        ).document
        blocked_sha = seam_anchor_review_decision_sha256(blocked)
        prepared = self.fixture.make_prepared(
            self.fixture.make_history([(blocked_sha, READY)])
        )
        exact = ExactSeamAnchorReviewDecision(
            self.fixture.address, self.fixture.candidate.sha256,
            blocked_sha, 1, canonical_json_bytes(blocked).decode("utf-8"),
        )
        with tempfile.TemporaryDirectory() as temporary, self.assertRaises(
            ReviewedSeamAnchorSetInputsError
        ):
            self.fixture.run(
                Path(temporary), snapshots=[prepared], exact=exact,
                requested_decision=blocked_sha,
            )

        wrong_rig = json.loads(canonical_json_bytes(self.fixture.rig))
        wrong_rig["project_id"] = "crosswired-project"
        wrong_bound = BoundSeamAnchorReviewCandidate(
            self.fixture.candidate,
            canonical_json_bytes(wrong_rig).decode("utf-8"),
        )
        with tempfile.TemporaryDirectory() as temporary, self.assertRaises(
            ReviewedSeamAnchorSetInputsError
        ):
            self.fixture.run(Path(temporary), bound=wrong_bound)

    def test_detached_identity_attack_is_rejected_and_source_has_no_writes(self):
        with tempfile.TemporaryDirectory() as temporary:
            result, _calls = self.fixture.run(Path(temporary))
        attacks = (
            {"candidate_sha256": "b" * 64}, {"review_revision": 2},
            {"decision_sha256": "a" * 64},
            {"address": replace(result.inputs.address,
                                project_id="crosswired-project")},
        )
        for changes in attacks:
            with self.subTest(changes=changes), \
                    self.assertRaises(ReviewedSeamAnchorSetInputsError):
                require_reviewed_seam_anchor_set_inputs(replace(
                    result.inputs, **changes))
        source = Path(
            "src/autospine_workbench/reviewed_seam_anchor_set_inputs.py"
        ).read_text(encoding="utf-8")
        for forbidden in ("publish_", "write_", ".glob(", ".rglob("):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
