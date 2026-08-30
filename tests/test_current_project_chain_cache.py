"""Bounded exact-key and single-flight current-chain cache tests."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
from threading import Event, Lock
import tempfile
import time
import unittest
from unittest.mock import patch
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


from autospine_workbench.current_project_chain_cache import (
    CurrentProjectChainCache,
    CurrentProjectChainCacheKey,
    current_manifest_algorithm_runtime_sha256,
    current_project_chain_cache_key,
)


def _key(index: int = 0) -> CurrentProjectChainCacheKey:
    chars = "abcdef0123456789"
    return CurrentProjectChainCacheKey(
        f"project-{index}",
        chars[index] * 64,
        chars[index + 1] * 64,
        chars[index + 2] * 64,
    )


class CurrentProjectChainCacheTests(unittest.TestCase):
    def test_concurrent_same_key_compiles_once(self) -> None:
        cache = CurrentProjectChainCache()
        entered, release = Event(), Event()
        calls = 0
        lock = Lock()

        def compiler():
            nonlocal calls
            with lock:
                calls += 1
            entered.set()
            if not release.wait(timeout=5):
                raise AssertionError("compiler was not released")
            return "d" * 64

        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = [
                pool.submit(cache.get_or_compile, _key(), compiler)
                for _index in range(8)
            ]
            self.assertTrue(entered.wait(timeout=5))
            time.sleep(0.05)
            release.set()
            values = [future.result(timeout=5) for future in futures]
        self.assertEqual(["d" * 64] * 8, values)
        self.assertEqual(1, calls)

    def test_different_keys_do_not_share_compiler_lock(self) -> None:
        cache = CurrentProjectChainCache()
        entered, release = Event(), Event()

        def slow():
            entered.set()
            if not release.wait(timeout=5):
                raise AssertionError("slow compiler was not released")
            return "d" * 64

        with ThreadPoolExecutor(max_workers=2) as pool:
            slow_future = pool.submit(cache.get_or_compile, _key(0), slow)
            self.assertTrue(entered.wait(timeout=5))
            fast_future = pool.submit(
                cache.get_or_compile, _key(1), lambda: "e" * 64,
            )
            self.assertEqual("e" * 64, fast_future.result(timeout=1))
            release.set()
            self.assertEqual("d" * 64, slow_future.result(timeout=5))

    def test_failure_is_not_negative_cached_and_waiters_are_released(self) -> None:
        cache = CurrentProjectChainCache()
        entered, release = Event(), Event()
        calls = 0
        lock = Lock()

        def compiler():
            nonlocal calls
            with lock:
                calls += 1
            entered.set()
            if not release.wait(timeout=5):
                raise AssertionError("compiler was not released")
            raise RuntimeError("synthetic failure")

        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = [
                pool.submit(cache.get_or_compile, _key(), compiler)
                for _index in range(4)
            ]
            self.assertTrue(entered.wait(timeout=5))
            time.sleep(0.05)
            release.set()
            for future in futures:
                with self.assertRaisesRegex(RuntimeError, "synthetic"):
                    future.result(timeout=5)
        self.assertEqual(1, calls)
        self.assertEqual(
            "f" * 64,
            cache.get_or_compile(_key(), lambda: "f" * 64),
        )

    def test_lru_capacity_is_bounded(self) -> None:
        cache = CurrentProjectChainCache(capacity=2)
        calls = []

        def load(index):
            calls.append(index)
            return f"{index:x}" * 64

        for index in (0, 1, 0, 2, 1):
            cache.get_or_compile(
                _key(index), lambda index=index: load(index),
            )
        self.assertEqual([0, 1, 2, 1], calls)

    def test_key_rehashes_same_size_content_with_restored_mtime(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "layer.png"
            path.write_bytes(b"alpha")
            stat = path.stat()
            first = current_project_chain_cache_key(
                "sample", "a" * 64, {"layer": path},
            )
            path.write_bytes(b"omega")
            os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
            second = current_project_chain_cache_key(
                "sample", "a" * 64, {"layer": path},
            )
        self.assertNotEqual(
            first.source_raster_set_sha256,
            second.source_raster_set_sha256,
        )
        self.assertNotEqual(
            first.input_identity_sha256,
            second.input_identity_sha256,
        )

    def test_key_binds_project_resolved_and_algorithm_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "layer.png"
            path.write_bytes(b"alpha")
            baseline = current_project_chain_cache_key(
                "sample", "a" * 64, {"layer": path},
            )
            other_project = current_project_chain_cache_key(
                "other", "a" * 64, {"layer": path},
            )
            other_resolved = current_project_chain_cache_key(
                "sample", "b" * 64, {"layer": path},
            )
        self.assertNotEqual(
            baseline.input_identity_sha256,
            other_project.input_identity_sha256,
        )
        self.assertNotEqual(
            baseline.input_identity_sha256,
            other_resolved.input_identity_sha256,
        )

    def test_live_algorithm_monkeypatch_changes_identity(self) -> None:
        from autospine_workbench import layer_manifest

        original = layer_manifest._deform_class
        baseline = current_manifest_algorithm_runtime_sha256()
        with patch.object(
            layer_manifest, "_deform_class", side_effect=original,
        ):
            patched = current_manifest_algorithm_runtime_sha256()
        self.assertNotEqual(baseline, patched)
        self.assertEqual(
            baseline, current_manifest_algorithm_runtime_sha256(),
        )


if __name__ == "__main__":
    unittest.main()
