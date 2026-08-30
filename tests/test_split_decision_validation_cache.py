"""Exact-input and concurrency tests for stored split validation reuse."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import sys
import tempfile
import time
from threading import Event
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.split_decision_validation_cache import (
    SplitDecisionValidationCache,
    SplitDecisionValidationCacheKey,
    split_decision_validation_cache_key,
)


class SplitDecisionValidationCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.project = "project-a"
        self.preview_sha = "a" * 64
        self.manifest_sha = "b" * 64
        self.preview = (
            self.root / "analysis" / self.project / "split-previews"
            / f"{self.preview_sha}.json"
        )
        self.manifest = (
            self.root / "builds" / self.project / "layer-manifests"
            / self.manifest_sha
        )
        self.source = self.root / "source.png"
        self.preview.parent.mkdir(parents=True)
        self.manifest.mkdir(parents=True)
        self.preview.write_bytes(b"preview-a")
        (self.manifest / "manifest.json").write_bytes(b"manifest-a")
        self.source.write_bytes(b"source-a")
        self.decisions = {
            "layer-a": {
                "action": "accept",
                "split_artifact_sha256": self.preview_sha,
                "analysis": {"layer_manifest_sha256": self.manifest_sha},
            }
        }
        self.resolved = {
            "project_id": self.project,
            "sha256": "c" * 64,
            "layers": [],
        }

    def key(self):
        return split_decision_validation_cache_key(
            self.root, self.project, self.decisions, self.resolved,
            {"layer-a": self.source},
        )

    def test_key_binds_full_source_preview_and_manifest_bytes(self) -> None:
        baseline = self.key()

        metadata = self.source.stat()
        self.source.write_bytes(b"source-b")
        os.utime(
            self.source,
            ns=(metadata.st_atime_ns, metadata.st_mtime_ns),
        )
        source_changed = self.key()
        self.assertNotEqual(
            baseline.evidence_sha256, source_changed.evidence_sha256,
        )

        self.source.write_bytes(b"source-a")
        preview_baseline = self.key()
        self.preview.write_bytes(b"preview-b")
        self.assertNotEqual(
            preview_baseline.evidence_sha256, self.key().evidence_sha256,
        )

        self.preview.write_bytes(b"preview-a")
        manifest_baseline = self.key()
        (self.manifest / "extra.bin").write_bytes(b"added")
        self.assertNotEqual(
            manifest_baseline.evidence_sha256, self.key().evidence_sha256,
        )

    def test_key_binds_context_root_and_runtime(self) -> None:
        baseline = self.key()
        changed = dict(self.resolved)
        changed["sha256"] = "d" * 64
        other_context = split_decision_validation_cache_key(
            self.root, self.project, self.decisions, changed,
            {"layer-a": self.source},
        )
        self.assertNotEqual(
            baseline.decision_context_sha256,
            other_context.decision_context_sha256,
        )
        from autospine_workbench import split_decision_binder
        original = split_decision_binder.SplitDecisionBinder._binding_is_current
        with patch.object(
            split_decision_binder.SplitDecisionBinder,
            "_binding_is_current",
            lambda *args, **kwargs: original(*args, **kwargs),
        ):
            patched = self.key()
        self.assertNotEqual(
            baseline.algorithm_runtime_sha256,
            patched.algorithm_runtime_sha256,
        )

    def test_cached_values_are_isolated_and_failures_are_not_cached(self) -> None:
        cache = SplitDecisionValidationCache()
        key = SplitDecisionValidationCacheKey(
            str(self.root), self.project, "1" * 64, "2" * 64, "3" * 64,
        )
        calls = 0

        def validator():
            nonlocal calls
            calls += 1
            return {"layer-a": {"binding_status": "current"}}

        first = cache.get_or_validate(key, validator)
        first["layer-a"]["binding_status"] = "tampered"
        second = cache.get_or_validate(key, validator)
        self.assertEqual("current", second["layer-a"]["binding_status"])
        self.assertEqual(1, calls)

        failing_key = SplitDecisionValidationCacheKey(
            str(self.root), self.project, "4" * 64, "5" * 64, "6" * 64,
        )
        failures = 0

        def fail():
            nonlocal failures
            failures += 1
            raise RuntimeError("invalid evidence")

        for _index in range(2):
            with self.assertRaisesRegex(RuntimeError, "invalid evidence"):
                cache.get_or_validate(failing_key, fail)
        self.assertEqual(2, failures)

    def test_concurrent_misses_are_singleflight(self) -> None:
        cache = SplitDecisionValidationCache()
        key = SplitDecisionValidationCacheKey(
            str(self.root), self.project, "7" * 64, "8" * 64, "9" * 64,
        )
        calls = 0

        def validator():
            nonlocal calls
            calls += 1
            time.sleep(0.05)
            return {"layer-a": {"binding_status": "current"}}

        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(
                lambda _index: cache.get_or_validate(key, validator),
                range(8),
            ))
        self.assertEqual(1, calls)
        self.assertTrue(all(
            row["layer-a"]["binding_status"] == "current"
            for row in results
        ))

    def test_clear_during_flight_starts_a_new_generation(self) -> None:
        cache = SplitDecisionValidationCache()
        key = SplitDecisionValidationCacheKey(
            str(self.root), self.project, "a" * 64, "b" * 64, "c" * 64,
        )
        started = Event()
        release = Event()
        calls = 0

        def validator():
            nonlocal calls
            calls += 1
            version = calls
            if version == 1:
                started.set()
                self.assertTrue(release.wait(timeout=1))
            return {"layer-a": {"version": version}}

        with ThreadPoolExecutor(max_workers=2) as pool:
            old = pool.submit(cache.get_or_validate, key, validator)
            self.assertTrue(started.wait(timeout=1))
            cache.clear()
            current = pool.submit(cache.get_or_validate, key, validator)
            self.assertEqual(2, current.result(timeout=1)["layer-a"]["version"])
            release.set()
            self.assertEqual(1, old.result(timeout=1)["layer-a"]["version"])
        self.assertEqual(2, cache.get_or_validate(key, validator)["layer-a"]["version"])
        self.assertEqual(2, calls)


if __name__ == "__main__":
    unittest.main()
