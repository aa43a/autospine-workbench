"""Bounded and single-flight P10.3c v2 image snapshot cache tests."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
from pathlib import Path
import sys
import tempfile
from threading import Event, Lock
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for item in (ROOT, SRC):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from autospine_workbench.body_sway_visual_review_address_v2 import (  # noqa: E402
    ExactVisualReviewAddressV2,
)
from autospine_workbench.body_sway_visual_review_application_models_v2 import (  # noqa: E402
    BodySwayVisualReviewImageV2,
)
from autospine_workbench.p10_visual_review_v2_image_cache import (  # noqa: E402
    P10VisualReviewV2ImageCacheError,
    P10VisualReviewV2ImageCacheKey,
    P10VisualReviewV2ImageCacheNotFound,
    P10VisualReviewV2ImageReplayCache,
)


SHA = lambda value: value * 64


class P10VisualReviewV2ImageCacheTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.address = ExactVisualReviewAddressV2(
            "project-a", SHA("1"), SHA("2"), SHA("3"),
        )
        self.key = P10VisualReviewV2ImageCacheKey(
            SHA("4"), SHA("5"), self.address, SHA("6"),
        )

    def tearDown(self):
        self.temporary.cleanup()

    def test_same_candidate_is_single_flight_and_each_image_is_exact(self):
        cache = P10VisualReviewV2ImageReplayCache(self.root)
        gate, lock = Event(), Lock()
        calls = 0

        def loader():
            nonlocal calls
            with lock:
                calls += 1
            gate.wait(2)
            return snapshot(self.key.candidate_sha256)

        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(
                cache.image, self.key, case_id="case-a",
                png_sha256=digest(b"A"), loader=loader,
            )
            second = pool.submit(
                cache.image, self.key, case_id="case-b",
                png_sha256=digest(b"B"), loader=loader,
            )
            gate.set()
            self.assertEqual((b"A", b"B"), (
                first.result().png_bytes, second.result().png_bytes,
            ))
        self.assertEqual(1, calls)
        again = cache.image(
            self.key, case_id="case-a", png_sha256=digest(b"A"),
            loader=lambda: self.fail("cache hit reloaded snapshot"),
        )
        self.assertEqual(b"A", again.png_bytes)

    def test_cross_wired_or_corrupt_images_fail_closed(self):
        cache = P10VisualReviewV2ImageReplayCache(self.root)
        cache.image(
            self.key, case_id="case-a", png_sha256=digest(b"A"),
            loader=lambda: snapshot(self.key.candidate_sha256),
        )
        with self.assertRaises(P10VisualReviewV2ImageCacheNotFound):
            cache.image(
                self.key, case_id="missing", png_sha256=digest(b"A"),
                loader=lambda: (),
            )
        with self.assertRaises(P10VisualReviewV2ImageCacheNotFound):
            cache.image(
                self.key, case_id="case-a", png_sha256=digest(b"B"),
                loader=lambda: (),
            )
        bad = BodySwayVisualReviewImageV2(
            self.key.candidate_sha256, "case-a", SHA("7"),
            digest(b"A"), 1, 640, 640, b"B",
        )
        fresh = P10VisualReviewV2ImageReplayCache(self.root)
        with self.assertRaises(P10VisualReviewV2ImageCacheError):
            fresh.image(
                self.key, case_id="case-a", png_sha256=digest(b"A"),
                loader=lambda: (bad,),
            )

    def test_failures_are_not_cached_and_lru_eviction_is_bounded(self):
        cache = P10VisualReviewV2ImageReplayCache(self.root, capacity=1)
        attempts = 0

        def flaky():
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("transient")
            return snapshot(self.key.candidate_sha256)

        with self.assertRaises(RuntimeError):
            cache.image(
                self.key, case_id="case-a", png_sha256=digest(b"A"),
                loader=flaky,
            )
        cache.image(
            self.key, case_id="case-a", png_sha256=digest(b"A"),
            loader=flaky,
        )
        self.assertEqual(2, attempts)

        second_key = P10VisualReviewV2ImageCacheKey(
            SHA("8"), SHA("9"), self.address, SHA("a"),
        )
        cache.image(
            second_key, case_id="case-a", png_sha256=digest(b"A"),
            loader=lambda: snapshot(second_key.candidate_sha256),
        )
        reloaded = 0

        def reload_first():
            nonlocal reloaded
            reloaded += 1
            return snapshot(self.key.candidate_sha256)

        cache.image(
            self.key, case_id="case-a", png_sha256=digest(b"A"),
            loader=reload_first,
        )
        self.assertEqual(1, reloaded)

    def test_failed_flight_wakes_waiters_then_allows_a_clean_retry(self):
        cache = P10VisualReviewV2ImageReplayCache(self.root)
        gate, started = Event(), Event()

        def fail():
            started.set()
            gate.wait(2)
            raise RuntimeError("failed leader")

        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(
                cache.image, self.key, case_id="case-a",
                png_sha256=digest(b"A"), loader=fail,
            )
            started.wait(2)
            second = pool.submit(
                cache.image, self.key, case_id="case-b",
                png_sha256=digest(b"B"), loader=fail,
            )
            gate.set()
            for result in (first, second):
                with self.assertRaises(RuntimeError):
                    result.result()
        recovered = cache.image(
            self.key, case_id="case-a", png_sha256=digest(b"A"),
            loader=lambda: snapshot(self.key.candidate_sha256),
        )
        self.assertEqual(b"A", recovered.png_bytes)

    def test_overweight_snapshot_is_shared_but_not_retained(self):
        cache = P10VisualReviewV2ImageReplayCache(
            self.root, byte_capacity=1,
        )
        calls = 0

        def loader():
            nonlocal calls
            calls += 1
            return snapshot(self.key.candidate_sha256)

        for _index in range(2):
            cache.image(
                self.key, case_id="case-a", png_sha256=digest(b"A"),
                loader=loader,
            )
        self.assertEqual(2, calls)

    def test_cache_is_bound_to_its_exact_state_root(self):
        cache = P10VisualReviewV2ImageReplayCache(self.root)
        self.assertTrue(cache.owns_state_root(self.root))
        other = self.root / "other"
        other.mkdir()
        self.assertFalse(cache.owns_state_root(other))


def snapshot(candidate):
    return tuple(image(candidate, case_id, raw) for case_id, raw in (
        ("case-a", b"A"), ("case-b", b"B"),
    ))


def image(candidate, case_id, raw):
    return BodySwayVisualReviewImageV2(
        candidate, case_id, SHA("7"), digest(raw), len(raw),
        640, 640, raw,
    )


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


if __name__ == "__main__":
    unittest.main()
