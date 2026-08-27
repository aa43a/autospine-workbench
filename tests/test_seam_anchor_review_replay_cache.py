"""Bounded single-flight replay cache tests for P10.5b review."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from threading import Barrier, Event, Lock
import tempfile
import unittest
from unittest.mock import patch

from autospine_workbench.mesh_source_images import (
    VerifiedAttachmentImage,
    VerifiedMeshSource,
)
from autospine_workbench.seam_anchor_candidates import SeamAnchorCandidates
from autospine_workbench.seam_anchor_review_address import (
    ExactSeamAnchorReviewAddress,
)
from autospine_workbench.seam_anchor_review_application import (
    SeamAnchorReviewApplication,
)
from autospine_workbench.seam_anchor_review_candidate_binding import (
    BoundSeamAnchorReviewCandidate,
    load_bound_seam_anchor_review_candidate,
)
from autospine_workbench.seam_anchor_review_replay_cache import (
    SeamAnchorReviewReplayCache,
    SeamAnchorReviewReplayCacheError,
)
from tests.p10_candidate_helpers import P10PersistedFixture
from tests.seam_anchor_review_helpers import seam_review_rows


def _address(index: int = 0) -> ExactSeamAnchorReviewAddress:
    characters = "abcdef0123456789"
    return ExactSeamAnchorReviewAddress(
        f"project-{index}", characters[index] * 64,
        characters[index + 1] * 64, characters[index + 2] * 64,
    )


def _bound(address: ExactSeamAnchorReviewAddress, payload_bytes: int = 0):
    candidate = SeamAnchorCandidates(json.dumps(
        {"project_id": address.project_id, "payload": "x" * payload_bytes},
        separators=(",", ":"),
    ))
    return BoundSeamAnchorReviewCandidate(
        candidate, json.dumps({"project_id": address.project_id})
    )


def _source(
    root: Path, address: ExactSeamAnchorReviewAddress, payload_bytes: int = 0,
):
    images = () if payload_bytes == 0 else (VerifiedAttachmentImage(
        "attachment", "layers/attachment.png", "f" * 64, 1, 1,
        b"x" * payload_bytes,
    ),)
    return VerifiedMeshSource(
        root / address.project_id, address.project_id,
        address.p3_rig_sha256, address.p3_bundle_sha256,
        "d" * 64, "e" * 64, "{}", images,
    )


class SeamAnchorReviewReplayCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _single_flight(self, invoke, target, return_value):
        worker_count = 18
        barrier = Barrier(worker_count)
        entered, release = Event(), Event()
        calls = 0
        counter_lock = Lock()

        def loader(*_args):
            nonlocal calls
            with counter_lock:
                calls += 1
            entered.set()
            if not release.wait(timeout=5):
                raise AssertionError("single-flight loader was not released")
            return return_value

        def request(_index):
            barrier.wait(timeout=5)
            return invoke()

        with patch(target, side_effect=loader), \
                ThreadPoolExecutor(max_workers=worker_count) as pool:
            futures = [pool.submit(request, index)
                       for index in range(worker_count)]
            self.assertTrue(entered.wait(timeout=5))
            release.set()
            values = [future.result(timeout=5) for future in futures]
        self.assertEqual(1, calls)
        self.assertTrue(all(value is values[0] for value in values))

    def test_candidate_and_source_first_load_are_single_flight(self):
        address = _address()
        cache = SeamAnchorReviewReplayCache(self.root)
        candidate_target = (
            "autospine_workbench.seam_anchor_review_replay_cache."
            "load_bound_seam_anchor_review_candidate"
        )
        self._single_flight(
            lambda: cache.load_candidate(address), candidate_target,
            _bound(address),
        )

        source_target = (
            "autospine_workbench.seam_anchor_review_replay_cache."
            "VerifiedMeshSourceReader.load"
        )
        self._single_flight(
            lambda: cache.load_source(address), source_target,
            _source(self.root, address),
        )

    def test_exact_addresses_are_isolated_and_lru_evicted(self):
        addresses = [_address(index) for index in range(3)]
        by_mesh = {row.mesh_reader_arguments: row for row in addresses}
        cache = SeamAnchorReviewReplayCache(
            self.root, candidate_capacity=2, source_capacity=2
        )
        candidate_calls = []
        source_calls = []

        def candidate_loader(_root, address):
            candidate_calls.append(address)
            return _bound(address)

        def source_loader(*arguments):
            source_calls.append(arguments)
            address = by_mesh[arguments]
            return _source(self.root, address)

        sequence = (
            addresses[0], addresses[1], addresses[0], addresses[2],
            addresses[0], addresses[1],
        )
        with patch(
            "autospine_workbench.seam_anchor_review_replay_cache."
            "load_bound_seam_anchor_review_candidate",
            side_effect=candidate_loader,
        ), patch(
            "autospine_workbench.seam_anchor_review_replay_cache."
            "VerifiedMeshSourceReader.load", side_effect=source_loader,
        ):
            candidate_values = [cache.load_candidate(row) for row in sequence]
            source_values = [cache.load_source(row) for row in sequence]

        expected = [addresses[0], addresses[1], addresses[2], addresses[1]]
        self.assertEqual(expected, candidate_calls)
        self.assertEqual(
            [row.mesh_reader_arguments for row in expected], source_calls
        )
        self.assertIs(candidate_values[0], candidate_values[2])
        self.assertIs(source_values[0], source_values[2])

    def test_failed_or_untyped_load_is_not_cached(self):
        address = _address()
        cache = SeamAnchorReviewReplayCache(self.root)
        with patch(
            "autospine_workbench.seam_anchor_review_replay_cache."
            "load_bound_seam_anchor_review_candidate",
            side_effect=[RuntimeError("invalid"), object(), _bound(address)],
        ) as loader:
            with self.assertRaises(RuntimeError):
                cache.load_candidate(address)
            with self.assertRaises(SeamAnchorReviewReplayCacheError):
                cache.load_candidate(address)
            value = cache.load_candidate(address)
            self.assertIs(value, cache.load_candidate(address))
        self.assertEqual(3, loader.call_count)

    def test_candidate_and_source_byte_budgets_evict_lru_values(self):
        first_address, second_address = _address(0), _address(1)
        first_candidate = _bound(first_address, 100)
        second_candidate = _bound(second_address, 100)
        candidate_budget = max(
            first_candidate.cache_weight_bytes,
            second_candidate.cache_weight_bytes,
        )
        candidate_cache = SeamAnchorReviewReplayCache(
            self.root, candidate_capacity=4,
            candidate_byte_capacity=candidate_budget,
        )
        candidates = {
            first_address: first_candidate,
            second_address: second_candidate,
        }
        with patch(
            "autospine_workbench.seam_anchor_review_replay_cache."
            "load_bound_seam_anchor_review_candidate",
            side_effect=lambda _root, address: candidates[address],
        ) as loader:
            for address in (first_address, second_address, first_address):
                candidate_cache.load_candidate(address)
        self.assertEqual(3, loader.call_count)

        first_source = _source(self.root, first_address, 100)
        second_source = _source(self.root, second_address, 100)
        source_budget = max(
            first_source.cache_weight_bytes, second_source.cache_weight_bytes
        )
        source_cache = SeamAnchorReviewReplayCache(
            self.root, source_capacity=4,
            source_byte_capacity=source_budget,
        )
        sources = {
            first_address.mesh_reader_arguments: first_source,
            second_address.mesh_reader_arguments: second_source,
        }
        with patch(
            "autospine_workbench.seam_anchor_review_replay_cache."
            "VerifiedMeshSourceReader.load",
            side_effect=lambda *arguments: sources[arguments],
        ) as loader:
            for address in (first_address, second_address, first_address):
                source_cache.load_source(address)
        self.assertEqual(3, loader.call_count)


class SeamAnchorReviewCachedApplicationTests(unittest.TestCase):
    def test_candidate_replay_is_cached_but_history_remains_fresh(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = P10PersistedFixture(Path(directory))
            address = ExactSeamAnchorReviewAddress(
                fixture.mesh.project_id, fixture.layer_manifest_sha256,
                fixture.mesh.rig_sha256, fixture.mesh.bundle_sha256,
            )
            cache = SeamAnchorReviewReplayCache(fixture.state)
            service = SeamAnchorReviewApplication(
                fixture.state, replay_cache=cache
            )
            with patch(
                "autospine_workbench.seam_anchor_review_replay_cache."
                "load_bound_seam_anchor_review_candidate",
                wraps=load_bound_seam_anchor_review_candidate,
            ) as replay:
                prepared = service.prepare(address)
                payload = {
                    "base_revision": 0,
                    "candidate_sha256": prepared.candidate_sha256,
                    "previous_decision_sha256": None,
                    "review": {
                        "reviewer_id": "cache-test", "notes": "fresh"
                    },
                    "decisions": seam_review_rows(
                        prepared.candidate_document, "accept"
                    ),
                }
                submitted = SeamAnchorReviewApplication(
                    fixture.state
                ).submit(address, payload)
                current = service.prepare(address)

            self.assertEqual(1, replay.call_count)
            self.assertEqual(1, submitted.revision)
            self.assertEqual(1, current.history.current_revision)
            self.assertEqual(
                submitted.decision_sha256,
                current.history.head_decision_sha256,
            )


if __name__ == "__main__":
    unittest.main()
