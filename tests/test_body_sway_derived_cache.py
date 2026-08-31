"""Bounded, exact-key, single-flight P10.2 derived cache tests."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
from pathlib import Path
from threading import Barrier, Event, Lock
import tempfile
import time
import unittest
from unittest.mock import PropertyMock, patch
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (ROOT, SRC):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from autospine_workbench.body_sway_canvas_adjustment_candidates import (
    BodySwayCanvasAdjustmentCandidates,
)
from autospine_workbench.body_sway_derived_cache import (
    MIN_BYTE_CAPACITY,
    BodySwayDerivedCache,
    BodySwayDerivedCacheKey,
    BodySwayDerivedResult,
    body_sway_derived_cache_key,
)
from autospine_workbench.body_sway_probe_report import BodySwayProbeReport
from autospine_workbench.dynamic_viewport_fit import DynamicViewportFit
from autospine_workbench.idle_behavior_review_address import (
    IdleBehaviorReviewAddress,
)
from autospine_workbench.idle_behavior_review_head import (
    IdleBehaviorReviewHead,
)
from autospine_workbench.idle_behavior_review_history import (
    IdleBehaviorReviewHistorySnapshot,
)
from autospine_workbench.region_rebind_candidates import (
    RegionRebindCandidateArtifact,
)


def _canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _address(index: int = 0) -> IdleBehaviorReviewAddress:
    chars = "abcdef0123456789"
    return IdleBehaviorReviewAddress(
        chars[index] * 64, f"project-{index}", f"motion-{index}",
        f"clip-{index}", chars[index + 1] * 64,
        chars[index + 2] * 64, chars[index + 3] * 64,
    )


def _key(index: int = 0) -> BodySwayDerivedCacheKey:
    chars = "abcdef0123456789"
    return BodySwayDerivedCacheKey(
        f"C:/state/{index}", _address(index), chars[index + 4] * 64,
        index + 1, chars[index + 5] * 64,
        chars[index + 6] * 64, chars[index + 7] * 64,
        chars[index + 8] * 64, chars[index + 9] * 64,
    )


def _result(marker: int) -> BodySwayDerivedResult:
    report = BodySwayProbeReport(_canonical({"report": marker}))
    adjustment = BodySwayCanvasAdjustmentCandidates(
        _canonical({"adjustment": marker}), report,
    )
    return BodySwayDerivedResult.freeze(
        adjustment, {"nested": {"marker": marker}},
        DynamicViewportFit(_canonical({"viewport": marker})),
        (RegionRebindCandidateArtifact(_canonical({"rebind": marker})),),
    )


class BodySwayDerivedCacheTests(unittest.TestCase):
    def test_eight_concurrent_requests_compile_once(self):
        cache = BodySwayDerivedCache()
        key = _key()
        workers = 8
        barrier = Barrier(workers)
        entered, release = Event(), Event()
        counter_lock = Lock()
        calls = 0

        def compiler():
            nonlocal calls
            with counter_lock:
                calls += 1
            entered.set()
            if not release.wait(timeout=5):
                raise AssertionError("compiler was not released")
            return _result(1)

        def request(_index):
            barrier.wait(timeout=5)
            return cache.get_or_compile(key, compiler)

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(request, index) for index in range(workers)]
            self.assertTrue(entered.wait(timeout=5))
            time.sleep(0.05)
            release.set()
            values = [future.result(timeout=5) for future in futures]
        self.assertEqual(1, calls)
        self.assertTrue(all(value.preview == values[0].preview
                            for value in values))

    def test_different_keys_do_not_share_a_compiler_lock(self):
        cache = BodySwayDerivedCache()
        entered, release = Event(), Event()

        def slow():
            entered.set()
            if not release.wait(timeout=5):
                raise AssertionError("slow compiler was not released")
            return _result(0)

        with ThreadPoolExecutor(max_workers=2) as pool:
            slow_future = pool.submit(cache.get_or_compile, _key(0), slow)
            self.assertTrue(entered.wait(timeout=5))
            fast_future = pool.submit(
                cache.get_or_compile, _key(1), lambda: _result(1),
            )
            self.assertEqual(1, fast_future.result(timeout=1).preview[
                "nested"
            ]["marker"])
            release.set()
            slow_future.result(timeout=5)

    def test_failure_is_not_negative_cached_and_waiters_are_released(self):
        cache = BodySwayDerivedCache()
        workers = 8
        barrier = Barrier(workers)
        entered, release = Event(), Event()
        counter_lock = Lock()
        calls = 0

        def compiler():
            nonlocal calls
            with counter_lock:
                calls += 1
            entered.set()
            if not release.wait(timeout=5):
                raise AssertionError("failing compiler was not released")
            raise RuntimeError("synthetic compiler failure")

        def request(_index):
            barrier.wait(timeout=5)
            return cache.get_or_compile(_key(), compiler)

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(request, index) for index in range(workers)]
            self.assertTrue(entered.wait(timeout=5))
            time.sleep(0.05)
            release.set()
            for future in futures:
                with self.assertRaisesRegex(RuntimeError, "synthetic"):
                    future.result(timeout=5)
        self.assertEqual(1, calls)
        value = cache.get_or_compile(_key(), lambda: _result(2))
        self.assertEqual(2, value.preview["nested"]["marker"])

    def test_lru_and_oversize_results_remain_bounded(self):
        cache = BodySwayDerivedCache(capacity=4)
        calls = []

        def load(index):
            calls.append(index)
            return _result(index)

        for index in (0, 1, 2, 3, 0, 4, 1):
            cache.get_or_compile(_key(index), lambda index=index: load(index))
        self.assertEqual([0, 1, 2, 3, 4, 1], calls)

        oversize = BodySwayDerivedCache(byte_capacity=MIN_BYTE_CAPACITY)
        oversize_calls = 0

        def load_oversize():
            nonlocal oversize_calls
            oversize_calls += 1
            return _result(9)

        with patch.object(
            BodySwayDerivedResult, "cache_weight_bytes",
            new_callable=PropertyMock,
            return_value=MIN_BYTE_CAPACITY + 1,
        ):
            oversize.get_or_compile(_key(), load_oversize)
            oversize.get_or_compile(_key(), load_oversize)
        self.assertEqual(2, oversize_calls)

    def test_returned_documents_cannot_pollute_resident_value(self):
        cache = BodySwayDerivedCache()
        first = cache.get_or_compile(_key(), lambda: _result(3))
        preview = first.preview
        preview["nested"]["marker"] = 99
        adjustment = first.canvas_adjustment.document
        adjustment["adjustment"] = 99
        viewport = first.dynamic_viewport.document
        viewport["viewport"] = 99
        rebind = first.rebind_candidates[0].document
        rebind["rebind"] = 99

        second = cache.get_or_compile(
            _key(), lambda: self.fail("resident result was not reused"),
        )
        self.assertEqual(3, second.preview["nested"]["marker"])
        self.assertEqual(3, second.canvas_adjustment.document["adjustment"])
        self.assertEqual(3, second.dynamic_viewport.document["viewport"])
        self.assertEqual(3, second.rebind_candidates[0].document["rebind"])

    def test_key_separates_root_address_head_candidate_and_profiles(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            other_root = root / "other"
            other_root.mkdir()
            head = IdleBehaviorReviewHead(
                IdleBehaviorReviewHistorySnapshot(1, "d" * 64, ()), None,
            )
            base = body_sway_derived_cache_key(
                root, _address(), "c" * 64, head,
            )
            self.assertNotEqual(base, body_sway_derived_cache_key(
                other_root, _address(), "c" * 64, head,
            ))
            self.assertNotEqual(base, body_sway_derived_cache_key(
                root, _address(1), "c" * 64, head,
            ))
            self.assertNotEqual(base, body_sway_derived_cache_key(
                root, _address(), "b" * 64, head,
            ))
            changed_head = replace(
                head,
                snapshot=IdleBehaviorReviewHistorySnapshot(
                    2, "e" * 64, (),
                ),
            )
            self.assertNotEqual(base, body_sway_derived_cache_key(
                root, _address(), "c" * 64, changed_head,
            ))
            with patch(
                "autospine_workbench.body_sway_derived_cache."
                "body_sway_probe_profile",
                return_value={"id": "changed"},
            ):
                changed_profile = body_sway_derived_cache_key(
                    root, _address(), "c" * 64, head,
                )
            self.assertNotEqual(base, changed_profile)
            with patch(
                "autospine_workbench.body_sway_derived_cache."
                "dynamic_viewport_fit_profile",
                return_value={"id": "changed"},
            ):
                changed_viewport = body_sway_derived_cache_key(
                    root, _address(), "c" * 64, head,
                )
            self.assertNotEqual(base, changed_viewport)
            with patch(
                "autospine_workbench.body_sway_derived_cache."
                "region_rebind_analyzer_profile",
                return_value={"id": "changed"},
            ):
                changed_rebind = body_sway_derived_cache_key(
                    root, _address(), "c" * 64, head,
                )
            self.assertNotEqual(base, changed_rebind)


if __name__ == "__main__":
    unittest.main()
