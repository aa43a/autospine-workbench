"""Bounded single-flight tests for the process-local Preview v2 cache."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
from threading import Event, Lock
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.capture_framing_candidate import (
    CaptureFramingCandidate,
)
from autospine_workbench.idle_behavior_candidates import (
    IdleBehaviorCandidates,
)
from autospine_workbench.idle_behavior_review_address import (
    IdleBehaviorReviewAddress,
)
from autospine_workbench.p10_preview_v2_cache import (
    P10PreviewV2Cache,
    P10PreviewV2CacheKey,
    P10PreviewV2CacheLocator,
    P10PreviewV2CacheRecord,
)
from autospine_workbench.p10_preview_v2_result import (
    P10PreviewV2CommandResult,
)
from autospine_workbench.temporary_body_sway_preview_v2 import (
    TemporaryBodySwayPreviewV2,
)


def _sha(character: str) -> str:
    return character * 64


def _record(token: str = "a") -> P10PreviewV2CacheRecord:
    locator = P10PreviewV2CacheLocator(
        f"state-{token}", f"workspace-{token}", _sha(token), _sha("f"),
    )
    key = P10PreviewV2CacheKey(
        locator, _sha("e"), _sha("d"), _sha("c"), 1,
        _sha("b"), _sha("a"), 1,
    )
    address = IdleBehaviorReviewAddress(
        _sha("9"), f"project-{token}", "motion", "clip",
        _sha("8"), _sha("7"), _sha("6"),
    )
    preview = TemporaryBodySwayPreviewV2("{}", (("preview.json", b"{}"),))
    result = P10PreviewV2CommandResult(
        locator.package_id, f"project-{token}", "clip",
        _sha("5"), _sha("4"), _sha("3"), _sha("2"), 1, 1,
        preview, Path(locator.workspace_root), Path(locator.state_root),
    )
    return P10PreviewV2CacheRecord(
        key, address, IdleBehaviorCandidates("{}"),
        CaptureFramingCandidate("{}"), result,
    )


class P10PreviewV2CacheTests(unittest.TestCase):
    def test_warm_value_is_reused_only_after_validator(self):
        cache = P10PreviewV2Cache()
        value = _record()
        calls = {"compile": 0, "validate": 0}

        def compile_value():
            calls["compile"] += 1
            return value

        def validate(_value):
            calls["validate"] += 1
            return True

        self.assertIs(value, cache.get_or_compile(
            value.key.locator, validate, compile_value,
        ))
        self.assertIs(value, cache.get_or_compile(
            value.key.locator, validate, compile_value,
        ))
        self.assertEqual({"compile": 1, "validate": 1}, calls)

    def test_same_locator_is_single_flight(self):
        cache = P10PreviewV2Cache()
        value = _record()
        started, release = Event(), Event()
        calls = 0
        lock = Lock()

        def compile_value():
            nonlocal calls
            with lock:
                calls += 1
            started.set()
            release.wait(2)
            return value

        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(
                cache.get_or_compile, value.key.locator,
                lambda _value: True, compile_value,
            ) for _index in range(8)]
            self.assertTrue(started.wait(1))
            time.sleep(0.05)
            release.set()
            results = [future.result(2) for future in futures]
        self.assertEqual(1, calls)
        self.assertTrue(all(item is value for item in results))

    def test_failure_is_not_negative_cached(self):
        cache = P10PreviewV2Cache()
        value = _record()
        calls = 0

        def compile_value():
            nonlocal calls
            calls += 1
            if calls == 1:
                raise ValueError("transient")
            return value

        with self.assertRaisesRegex(ValueError, "transient"):
            cache.get_or_compile(
                value.key.locator, lambda _value: True, compile_value,
            )
        self.assertIs(value, cache.get_or_compile(
            value.key.locator, lambda _value: True, compile_value,
        ))
        self.assertEqual(2, calls)

    def test_entry_bound_evicts_least_recent_locator(self):
        cache = P10PreviewV2Cache(capacity=1, byte_capacity=1024)
        first, second = _record("a"), _record("b")
        first_compiles = 0

        def compile_first():
            nonlocal first_compiles
            first_compiles += 1
            return first

        cache.get_or_compile(
            first.key.locator, lambda _value: True, compile_first,
        )
        cache.get_or_compile(
            second.key.locator, lambda _value: True, lambda: second,
        )
        cache.get_or_compile(
            first.key.locator, lambda _value: True, compile_first,
        )
        self.assertEqual(2, first_compiles)


if __name__ == "__main__":
    unittest.main()
