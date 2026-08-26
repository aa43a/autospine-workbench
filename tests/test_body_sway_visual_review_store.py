"""Write-once P10.3c candidate and decision history store tests."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (ROOT, SRC):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from autospine_workbench.body_sway_runtime_capture_reader import (  # noqa: E402
    VerifiedBodySwayRuntimeCapture,
    VerifiedBodySwayRuntimeCaptureReader,
)
from autospine_workbench.body_sway_runtime_capture import (  # noqa: E402
    BodySwayRuntimeCapture,
)
from autospine_workbench.body_sway_visual_review_candidate import (  # noqa: E402
    compile_body_sway_visual_review_candidate,
)
from autospine_workbench.body_sway_visual_review_decision import (  # noqa: E402
    BodySwayVisualReviewDecision,
    build_body_sway_visual_review_decision,
)
from autospine_workbench.body_sway_visual_review_history import (  # noqa: E402
    BodySwayVisualReviewRevisionConflict,
)
from autospine_workbench.body_sway_visual_review_errors import (  # noqa: E402
    BodySwayVisualReviewHistoryError,
    BodySwayVisualReviewStoreError as ExplicitVisualReviewStoreError,
)
from autospine_workbench.body_sway_visual_review_store import (  # noqa: E402
    CANDIDATE_NAMESPACE,
    DECISION_NAMESPACE,
    BodySwayVisualReviewStore,
    BodySwayVisualReviewStoreError,
)
from autospine_workbench.body_sway_visual_review_store_files import (  # noqa: E402
    publish_document,
)
from tests.body_sway_runtime_capture_helpers import (  # noqa: E402
    fake_runtime_profile,
)
from tests.body_sway_visual_review_helpers import (  # noqa: E402
    BodySwayVisualReviewFixture,
    review_rows,
)


class BodySwayVisualReviewStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.runtime_profile = fake_runtime_profile()
        self.runtime_profile.__enter__()
        self.fixture = BodySwayVisualReviewFixture(self.root)
        self.capture = VerifiedBodySwayRuntimeCaptureReader(
            self.fixture.state_root
        ).load(*self.fixture.address)
        self.candidate = compile_body_sway_visual_review_candidate(
            self.capture
        )
        self.decision = build_body_sway_visual_review_decision(
            self.candidate.document,
            review={"reviewer_id": "artist-01", "notes": "reviewed"},
            decisions=review_rows(self.candidate.document),
        )
        self.store = BodySwayVisualReviewStore(self.fixture.state_root)

    def test_public_store_error_hierarchy_has_stable_named_types(self):
        self.assertIs(BodySwayVisualReviewStoreError,
                      ExplicitVisualReviewStoreError)
        self.assertEqual("BodySwayVisualReviewStoreError",
                         BodySwayVisualReviewStoreError.__name__)
        self.assertTrue(issubclass(
            BodySwayVisualReviewRevisionConflict,
            BodySwayVisualReviewHistoryError,
        ))
        self.assertTrue(issubclass(
            BodySwayVisualReviewRevisionConflict,
            BodySwayVisualReviewStoreError,
        ))
    def tearDown(self) -> None:
        try:
            self.runtime_profile.__exit__(None, None, None)
        finally:
            self.temporary.cleanup()

    def test_publish_and_exact_load_have_no_latest_or_overwrite(self) -> None:
        first = self.store.publish_candidate(self.candidate, self.capture)
        second = self.store.publish_candidate(self.candidate, self.capture)
        loaded = self.store.load_candidate(
            self.capture.capture.document["project_id"],
            self.capture.bundle_sha256,
            self.candidate.sha256,
            capture=self.capture,
        )
        self.assertFalse(first.reused)
        self.assertTrue(second.reused)
        self.assertEqual(self.candidate.canonical_bytes, loaded.canonical_bytes)
        self.assertEqual(
            CANDIDATE_NAMESPACE,
            first.path.parents[1].name,
        )
        self.assertFalse((first.path.parent / "latest.json").exists())

        published = self.store.publish_decision(
            self.decision, candidates=self.candidate, capture=self.capture
        )
        recovered = self.store.load_decision(
            self.candidate.document["project_id"],
            self.candidate.sha256,
            self.decision.sha256,
            candidates=self.candidate,
            capture=self.capture,
        )
        self.assertEqual(self.decision.canonical_bytes,
                         recovered.canonical_bytes)
        self.assertEqual(DECISION_NAMESPACE, published.path.parents[1].name)

    def test_history_snapshot_is_zero_write_then_reports_ordered_head(self):
        before = {
            path.relative_to(self.fixture.state_root): path.read_bytes()
            for path in self.fixture.state_root.rglob("*") if path.is_file()
        }
        empty = self.store.snapshot_history(
            candidates=self.candidate, capture=self.capture
        )
        after = {
            path.relative_to(self.fixture.state_root): path.read_bytes()
            for path in self.fixture.state_root.rglob("*") if path.is_file()
        }
        self.assertEqual(before, after)
        self.assertEqual((0, 0, None, ()), (
            empty.revision_count, empty.current_revision,
            empty.head_decision_sha256, empty.rows,
        ))
        self.assertEqual(self.candidate.document["project_id"], empty.project_id)
        self.assertEqual(self.candidate.sha256, empty.candidate_sha256)

        self.store.publish_candidate(self.candidate, self.capture)
        self.store.publish_decision(
            self.decision, candidates=self.candidate, capture=self.capture
        )
        snapshot = self.store.snapshot_history(
            candidates=self.candidate, capture=self.capture
        )
        self.assertEqual(1, snapshot.revision_count)
        self.assertEqual(self.decision.sha256, snapshot.head_decision_sha256)
        self.assertEqual(
            (1, self.decision.sha256, "sampled_visual_approved"),
            (snapshot.rows[0].revision, snapshot.rows[0].decision_sha256,
             snapshot.rows[0].status),
        )

    def test_jump_conflict_is_structured_and_creates_no_decision_parent(self):
        self.store.publish_candidate(self.candidate, self.capture)
        jumped = build_body_sway_visual_review_decision(
            self.candidate.document,
            review={"reviewer_id": "artist-02", "notes": "jump"},
            decisions=review_rows(self.candidate.document),
            previous_decision=self.decision.document,
        )
        decision_parent = (
            self.fixture.state_root / "builds"
            / self.candidate.document["project_id"] / DECISION_NAMESPACE
            / self.candidate.sha256
        )
        with self.assertRaises(BodySwayVisualReviewRevisionConflict) as raised:
            self.store.publish_decision(
                jumped, candidates=self.candidate, capture=self.capture
            )
        conflict = raised.exception
        self.assertEqual((2, 0), (
            conflict.requested_revision, conflict.current_revision
        ))
        self.assertEqual((self.decision.sha256, None), (
            conflict.requested_head, conflict.current_head
        ))
        self.assertFalse(decision_parent.exists())

        malformed = BodySwayVisualReviewDecision(
            self.decision.canonical_bytes.decode("utf-8") + " "
        )
        with self.assertRaises(BodySwayVisualReviewStoreError):
            self.store.publish_decision(
                malformed, candidates=self.candidate, capture=self.capture
            )
        self.assertFalse(decision_parent.exists())

    def test_concurrent_publication_converges_to_one_immutable_file(self) -> None:
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(
                lambda _index: self.store.publish_candidate(
                    self.candidate, self.capture
                ),
                range(16),
            ))
        self.assertEqual(1, len({result.path for result in results}))
        self.assertEqual(1, sum(not result.reused for result in results))

    def test_superseding_decision_appends_and_requires_exact_previous(self) -> None:
        self.store.publish_candidate(self.candidate, self.capture)
        first = self.store.publish_decision(
            self.decision, candidates=self.candidate, capture=self.capture
        )
        rows = review_rows(self.candidate.document)
        rows[0]["action"] = "reject"
        rows[0]["notes"] = "visible seam"
        second_value = build_body_sway_visual_review_decision(
            self.candidate.document,
            review={"reviewer_id": "artist-01", "notes": "second pass"},
            decisions=rows,
            previous_decision=self.decision.document,
        )
        second = self.store.publish_decision(
            second_value,
            candidates=self.candidate,
            capture=self.capture,
        )
        self.assertNotEqual(first.path, second.path)
        self.assertTrue(first.path.is_file())
        self.assertTrue(second.path.is_file())

        reused = self.store.publish_decision(
            second_value, candidates=self.candidate, capture=self.capture
        )
        self.assertTrue(reused.reused)
        revisions = first.path.parent / "revisions"
        self.assertEqual(
            {"r000001.json", "r000002.json"},
            {path.name for path in revisions.iterdir()},
        )

    def test_decision_requires_published_candidate_and_predecessor(self) -> None:
        with self.assertRaises(BodySwayVisualReviewStoreError):
            self.store.publish_decision(
                self.decision, candidates=self.candidate, capture=self.capture
            )
        self.store.publish_candidate(self.candidate, self.capture)
        rows = review_rows(self.candidate.document)
        rows[0]["action"] = "reject"
        rows[0]["notes"] = "seam"
        second = build_body_sway_visual_review_decision(
            self.candidate.document,
            review={"reviewer_id": "artist-01", "notes": "second"},
            decisions=rows,
            previous_decision=self.decision.document,
        )
        with self.assertRaises(BodySwayVisualReviewStoreError):
            self.store.publish_decision(
                second,
                candidates=self.candidate,
                capture=self.capture,
            )

    def test_tamper_wrong_address_and_forged_value_fail_closed(self) -> None:
        published = self.store.publish_candidate(self.candidate, self.capture)
        published.path.write_bytes(published.path.read_bytes() + b" ")
        with self.assertRaises(BodySwayVisualReviewStoreError):
            self.store.load_candidate(
                self.candidate.document["project_id"],
                self.capture.bundle_sha256,
                self.candidate.sha256,
                capture=self.capture,
            )

        forged = BodySwayVisualReviewDecision(
            self.decision.canonical_bytes.decode("utf-8") + " "
        )
        with self.assertRaises(BodySwayVisualReviewStoreError):
            self.store.publish_decision(
                forged, candidates=self.candidate, capture=self.capture
            )

        with self.assertRaises(BodySwayVisualReviewStoreError):
            self.store.load_decision(
                self.candidate.document["project_id"],
                self.candidate.sha256,
                "a" * 64,
                candidates=self.candidate,
                capture=self.capture,
            )
    def test_candidate_boundaries_replay_store_and_reject_forged_verified(self):
        relative = self.capture.path.relative_to(self.fixture.state_root)
        forged_path = VerifiedBodySwayRuntimeCapture(
            self.root / "foreign" / relative,
            self.capture.capture,
            self.capture.bundle_sha256,
        )
        captures = list(self.capture.capture.capture_bytes.items())
        name, payload = captures[0]
        captures[0] = (name, payload[:-1] + bytes([payload[-1] ^ 1]))
        forged_bytes = VerifiedBodySwayRuntimeCapture(
            self.capture.path,
            BodySwayRuntimeCapture(
                self.capture.capture.canonical_bytes.decode("utf-8"),
                tuple(captures),
            ),
            self.capture.bundle_sha256,
        )
        for forged in (forged_path, forged_bytes):
            with self.subTest(forged=forged), self.assertRaises(
                BodySwayVisualReviewStoreError
            ):
                self.store.publish_candidate(self.candidate, forged)

        absent_store = BodySwayVisualReviewStore(self.root / "absent-state")
        with self.assertRaises(BodySwayVisualReviewStoreError):
            absent_store.publish_candidate(self.candidate, self.capture)
        self.assertFalse((self.root / "absent-state").exists())

    def test_competing_initial_revisions_have_one_linear_winner(self) -> None:
        self.store.publish_candidate(self.candidate, self.capture)
        alternate = build_body_sway_visual_review_decision(
            self.candidate.document,
            review={"reviewer_id": "artist-02", "notes": "alternate"},
            decisions=review_rows(self.candidate.document),
        )

        def attempt(value):
            try:
                return self.store.publish_decision(
                    value, candidates=self.candidate, capture=self.capture
                )
            except BodySwayVisualReviewStoreError as exc:
                return exc

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, (self.decision, alternate)))
        winners = [result for result in results
                   if not isinstance(result, Exception)]
        losers = [result for result in results if isinstance(result, Exception)]
        self.assertEqual(1, len(winners), results)
        self.assertIsInstance(losers[0], BodySwayVisualReviewRevisionConflict)
        self.assertEqual((1, 1), (
            losers[0].requested_revision, losers[0].current_revision
        ))
        self.assertEqual(winners[0].sha256, losers[0].current_head)
        revisions = winners[0].path.parent / "revisions"
        self.assertEqual(
            {"r000001.json"}, {path.name for path in revisions.iterdir()}
        )
        loser = alternate if winners[0].sha256 == self.decision.sha256 \
            else self.decision
        publish_document(winners[0].path.parent, loser.sha256,
                         loser.canonical_bytes)
        with self.assertRaises(BodySwayVisualReviewStoreError):
            self.store.load_decision(
                self.candidate.document["project_id"],
                self.candidate.sha256,
                loser.sha256,
                candidates=self.candidate,
                capture=self.capture,
            )
    def test_competing_same_predecessor_revisions_have_one_winner(self) -> None:
        self.store.publish_candidate(self.candidate, self.capture)
        first = self.store.publish_decision(
            self.decision, candidates=self.candidate, capture=self.capture
        )
        rows = review_rows(self.candidate.document)
        rows[0]["action"] = "reject"
        rows[0]["notes"] = "visible seam"
        revisions = [
            build_body_sway_visual_review_decision(
                self.candidate.document,
                review={"reviewer_id": f"artist-0{index}", "notes": note},
                decisions=rows,
                previous_decision=self.decision.document,
            )
            for index, note in ((2, "left seam"), (3, "right seam"))
        ]

        def attempt(value):
            try:
                return self.store.publish_decision(
                    value, candidates=self.candidate, capture=self.capture
                )
            except BodySwayVisualReviewStoreError as exc:
                return exc

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, revisions))
        winners = [result for result in results
                   if not isinstance(result, Exception)]
        losers = [result for result in results if isinstance(result, Exception)]
        self.assertEqual(1, len(winners), results)
        self.assertIsInstance(losers[0], BodySwayVisualReviewRevisionConflict)
        self.assertEqual((2, 2), (
            losers[0].requested_revision, losers[0].current_revision
        ))
        self.assertEqual(winners[0].sha256, losers[0].current_head)
        self.assertTrue(first.path.is_file())
        recovered = self.store.load_decision(
            self.candidate.document["project_id"],
            self.candidate.sha256,
            winners[0].sha256,
            candidates=self.candidate,
            capture=self.capture,
        )
        self.assertEqual(winners[0].sha256, recovered.sha256)

    def test_revision_slot_tamper_and_extra_inventory_fail_closed(self) -> None:
        self.store.publish_candidate(self.candidate, self.capture)
        published = self.store.publish_decision(
            self.decision, candidates=self.candidate, capture=self.capture
        )
        revisions = published.path.parent / "revisions"
        slot = revisions / "r000001.json"
        slot.write_bytes(slot.read_bytes() + b" ")
        with self.assertRaises(BodySwayVisualReviewStoreError):
            self.store.load_decision(
                self.candidate.document["project_id"],
                self.candidate.sha256,
                self.decision.sha256,
                candidates=self.candidate,
                capture=self.capture,
            )
        with self.assertRaises(BodySwayVisualReviewStoreError):
            self.store.snapshot_history(
                candidates=self.candidate, capture=self.capture
            )
        slot.write_bytes(self.decision.canonical_bytes)
        (revisions / "foreign.json").write_bytes(b"{}")
        with self.assertRaises(BodySwayVisualReviewStoreError):
            self.store.load_decision(
                self.candidate.document["project_id"],
                self.candidate.sha256,
                self.decision.sha256,
                candidates=self.candidate,
                capture=self.capture,
            )

        (revisions / "foreign.json").unlink()
        wrong_case = revisions / "R000001.JSON"
        slot.rename(wrong_case)
        with self.assertRaises(BodySwayVisualReviewStoreError):
            self.store.load_decision(
                self.candidate.document["project_id"],
                self.candidate.sha256,
                self.decision.sha256,
                candidates=self.candidate,
                capture=self.capture,
            )
        wrong_case.rename(slot)

        slot.unlink()
        try:
            slot.symlink_to(published.path)
        except OSError:
            slot.write_bytes(self.decision.canonical_bytes)
            return
        with self.assertRaises(BodySwayVisualReviewStoreError):
            self.store.load_decision(
                self.candidate.document["project_id"],
                self.candidate.sha256,
                self.decision.sha256,
                candidates=self.candidate,
                capture=self.capture,
            )

    def test_decision_load_rejects_non_address_inputs_before_lookup(self) -> None:
        self.store.publish_candidate(self.candidate, self.capture)
        self.store.publish_decision(
            self.decision, candidates=self.candidate, capture=self.capture
        )
        values = [
            (
                "../escape",
                self.candidate.sha256,
                self.decision.sha256,
            ),
            (
                self.candidate.document["project_id"],
                "latest",
                self.decision.sha256,
            ),
            (
                self.candidate.document["project_id"],
                self.candidate.sha256,
                "latest",
            ),
        ]
        for project, candidate_sha, decision_sha in values:
            with self.subTest(values=(project, candidate_sha, decision_sha)), \
                    self.assertRaises(BodySwayVisualReviewStoreError):
                self.store.load_decision(
                    project,
                    candidate_sha,
                    decision_sha,
                    candidates=self.candidate,
                    capture=self.capture,
                )

if __name__ == "__main__":
    unittest.main()
