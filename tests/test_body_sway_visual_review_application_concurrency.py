"""Application-level CAS concurrency tests for P10.3c visual review."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
from threading import Barrier
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for item in (ROOT, SRC):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from autospine_workbench.body_sway_visual_review_address import (  # noqa: E402
    ExactVisualReviewAddress,
)
from autospine_workbench.body_sway_visual_review_application import (  # noqa: E402
    BodySwayVisualReviewApplication,
)
from autospine_workbench.body_sway_visual_review_history import (  # noqa: E402
    BodySwayVisualReviewRevisionConflict,
)
from tests.body_sway_runtime_capture_helpers import (  # noqa: E402
    fake_runtime_profile,
)
from tests.body_sway_visual_review_helpers import (  # noqa: E402
    BodySwayVisualReviewFixture,
    review_rows,
)


class BodySwayVisualReviewApplicationConcurrencyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.fixture = BodySwayVisualReviewFixture(
            Path(self.temporary.name), distinct_images=True
        )
        self.address = ExactVisualReviewAddress(*self.fixture.address)
        self.service = BodySwayVisualReviewApplication(self.fixture.state_root)
        with fake_runtime_profile():
            self.prepared = self.service.prepare(self.address)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def payload(self, *, notes: str) -> dict:
        return {
            "base_revision": 0,
            "candidate_sha256": self.prepared.candidate_sha256,
            "previous_decision_sha256": None,
            "review": {"reviewer_id": "artist-01", "notes": notes},
            "decisions": review_rows(self.prepared.candidate_document),
        }

    def test_identical_concurrent_submissions_converge_to_one_decision(self):
        payload = self.payload(notes="same review")
        barrier = Barrier(2)

        def attempt(_index):
            barrier.wait()
            return self.service.submit(self.address, deepcopy(payload))

        with fake_runtime_profile(), ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, range(2)))
        self.assertEqual(1, sum(not result.reused for result in results))
        self.assertEqual(1, sum(result.reused for result in results))
        self.assertEqual(1, len({result.decision_sha256 for result in results}))
        self.assertEqual({1}, {result.revision for result in results})

    def test_different_concurrent_submissions_have_one_typed_loser(self):
        payloads = [
            self.payload(notes="left review"),
            self.payload(notes="right review"),
        ]
        barrier = Barrier(2)

        def attempt(payload):
            barrier.wait()
            try:
                return self.service.submit(self.address, deepcopy(payload))
            except BodySwayVisualReviewRevisionConflict as exc:
                return exc

        with fake_runtime_profile(), ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, payloads))
        winners = [row for row in results if not isinstance(row, Exception)]
        losers = [row for row in results if isinstance(row, Exception)]
        self.assertEqual(1, len(winners), results)
        self.assertEqual(1, len(losers), results)
        self.assertIsInstance(losers[0], BodySwayVisualReviewRevisionConflict)
        self.assertEqual((1, 1), (
            losers[0].requested_revision, losers[0].current_revision,
        ))
        self.assertEqual(winners[0].decision_sha256, losers[0].current_head)
        with fake_runtime_profile():
            current = self.service.prepare(self.address)
        self.assertEqual(winners[0].decision_sha256,
                         current.history.head_decision_sha256)


if __name__ == "__main__":
    unittest.main()
