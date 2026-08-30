"""Full-byte invalidation and singleflight tests for P10 replay reuse."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from threading import Barrier, Event


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (ROOT, SRC):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from autospine_workbench.idle_behavior_review_replay_cache import (
    IdleBehaviorReviewReplayCacheError,
    clear_idle_behavior_review_replay_cache,
    load_cached_reviewed_motion_chain,
)
from autospine_workbench.reviewed_motion_bundle_reader import (
    VerifiedReviewedMotionBundleChain,
)


class IdleBehaviorReviewReplayCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.project = "project-a"
        self.instance = "1" * 64
        self.bundle = "2" * 64
        self.paths = self._paths()
        for index, path in enumerate(self.paths):
            path.mkdir(parents=True)
            (path / f"evidence-{index}.bin").write_bytes(b"alpha")
        self._write_address_manifests()
        self.chain = self._chain()
        clear_idle_behavior_review_replay_cache()
        self.addCleanup(clear_idle_behavior_review_replay_cache)

    def _paths(self) -> tuple[Path, ...]:
        builds = self.root / "builds" / self.project
        return (
            builds / "rig-ir" / ("3" * 64) / ("4" * 64),
            builds / "layer-manifests" / ("5" * 64),
            builds / "mesh-rig-ir" / ("6" * 64) / ("7" * 64),
            builds / "ik-targets" / ("8" * 64) / ("9" * 64),
            self.root / "motions" / ("a" * 64) / ("b" * 64),
            builds / "motion-instances" / ("c" * 64) / ("d" * 64),
            builds / "reviewed-motion-instances" / self.instance / self.bundle,
        )

    def _chain(self) -> VerifiedReviewedMotionBundleChain:
        mesh = SimpleNamespace(
            project_id=self.project,
            path=self.paths[2],
            run_manifest={"inputs": {
                "base_rig_sha256": "3" * 64,
                "base_bundle_sha256": "4" * 64,
                "layer_manifest_sha256": "5" * 64,
            }},
        )
        retarget = SimpleNamespace(
            path=self.paths[5],
            source_addresses={
                "p4_profile_sha256": "8" * 64,
                "p4_bundle_sha256": "9" * 64,
                "motion_clip_sha256": "a" * 64,
                "motion_bundle_sha256": "b" * 64,
            },
        )
        reviewed = SimpleNamespace(path=self.paths[6])
        return VerifiedReviewedMotionBundleChain(mesh, retarget, reviewed)

    def _write_address_manifests(self) -> None:
        documents = (
            (self.paths[6] / "run-manifest.json", {"inputs": {
                "p3": {"rig_sha256": "6" * 64,
                       "bundle_sha256": "7" * 64},
                "p5": {"instance_sha256": "c" * 64,
                       "bundle_sha256": "d" * 64},
            }}),
            (self.paths[2] / "run-manifest.json", {"inputs": {
                "base_rig_sha256": "3" * 64,
                "base_bundle_sha256": "4" * 64,
                "layer_manifest_sha256": "5" * 64,
            }}),
            (self.paths[5] / "target-profile.json", {"source": {
                "p4_profile_sha256": "8" * 64,
                "p4_bundle_sha256": "9" * 64,
            }}),
            (self.paths[5] / "instance.json", {"source": {
                "motion_ir_sha256": "a" * 64,
                "motion_bundle_sha256": "b" * 64,
            }}),
        )
        for path, document in documents:
            path.write_text(json.dumps(document), encoding="utf-8")

    def _load(self, loader):
        return self._load_from(self.root, loader)

    def _load_from(self, root, loader):
        return load_cached_reviewed_motion_chain(
            root, self.project, self.instance, self.bundle, loader,
        )

    def test_identical_bytes_reuse_one_exact_replay(self) -> None:
        calls = 0

        def loader():
            nonlocal calls
            calls += 1
            return self.chain

        self.assertIs(self.chain, self._load(loader))
        self.assertIs(self.chain, self._load(loader))
        self.assertEqual(1, calls)

    def test_alias_root_cannot_reuse_real_root_entry(self) -> None:
        calls = 0

        def loader():
            nonlocal calls
            calls += 1
            return self.chain

        self.assertIs(self.chain, self._load(loader))
        alias = self.root / "state-root-alias"
        alias.mkdir()
        path_type = type(self.root)
        original_resolve = path_type.resolve
        from autospine_workbench import idle_behavior_review_byte_seal
        original_alias = idle_behavior_review_byte_seal._is_alias

        def resolve(path, strict=False):
            absolute = Path(os.path.abspath(os.fspath(path)))
            if absolute == alias:
                return self.root
            return original_resolve(path, strict=strict)

        def is_alias(path):
            return Path(path) == alias or original_alias(path)

        with patch.object(path_type, "resolve", resolve), patch.object(
            idle_behavior_review_byte_seal, "_is_alias", side_effect=is_alias,
        ), self.assertRaisesRegex(
            IdleBehaviorReviewReplayCacheError, "root is unsafe"
        ):
            self._load_from(alias, loader)
        self.assertEqual(1, calls)

    def test_same_size_tamper_with_restored_mtime_invalidates(self) -> None:
        target = self.paths[0] / "evidence-0.bin"
        original = target.stat()
        calls = 0

        def loader():
            nonlocal calls
            calls += 1
            if target.read_bytes() != b"alpha":
                raise RuntimeError("exact replay rejected tamper")
            return self.chain

        self._load(loader)
        target.write_bytes(b"omega")
        os.utime(target, ns=(original.st_atime_ns, original.st_mtime_ns))
        with self.assertRaisesRegex(RuntimeError, "rejected tamper"):
            self._load(loader)
        self.assertEqual(2, calls)

    def test_bytes_changed_during_cold_replay_are_not_cached(self) -> None:
        target = self.paths[0] / "evidence-0.bin"

        def loader():
            target.write_bytes(b"omega")
            return self.chain

        with self.assertRaisesRegex(
            IdleBehaviorReviewReplayCacheError,
            "bytes changed during verification",
        ):
            self._load(loader)

    def test_added_or_removed_inventory_invalidates(self) -> None:
        calls = 0

        def loader():
            nonlocal calls
            calls += 1
            if calls > 1:
                raise RuntimeError("full replay required")
            return self.chain

        self._load(loader)
        added = self.paths[1] / "extra.bin"
        added.write_bytes(b"extra")
        with self.assertRaisesRegex(RuntimeError, "full replay required"):
            self._load(loader)
        added.unlink()

        clear_idle_behavior_review_replay_cache()
        calls = 0
        self._load(loader)
        (self.paths[2] / "evidence-2.bin").unlink()
        with self.assertRaisesRegex(RuntimeError, "full replay required"):
            self._load(loader)

    def test_linklike_input_invalidates(self) -> None:
        calls = 0

        def loader():
            nonlocal calls
            calls += 1
            if calls > 1:
                raise RuntimeError("full replay required")
            return self.chain

        self._load(loader)
        target = self.paths[3] / "evidence-3.bin"
        from autospine_workbench import idle_behavior_review_byte_seal
        original = idle_behavior_review_byte_seal._is_alias
        with patch.object(
            idle_behavior_review_byte_seal,
            "_is_alias",
            side_effect=lambda path: Path(path) == target or original(path),
        ), self.assertRaisesRegex(
            RuntimeError, "full replay required"
        ):
            self._load(loader)
        self.assertEqual(2, calls)

    def test_concurrent_misses_are_singleflight(self) -> None:
        calls = 0

        def loader():
            nonlocal calls
            calls += 1
            time.sleep(0.05)
            return self.chain

        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _index: self._load(loader), range(4)))
        self.assertTrue(all(result is self.chain for result in results))
        self.assertEqual(1, calls)

    def test_concurrent_warm_hits_share_one_full_byte_seal(self) -> None:
        self._load(lambda: self.chain)
        from autospine_workbench import idle_behavior_review_replay_cache
        original = idle_behavior_review_replay_cache.seal_exact_directories
        seals = 0

        def seal(*args, **kwargs):
            nonlocal seals
            seals += 1
            time.sleep(0.05)
            return original(*args, **kwargs)

        with patch.object(
            idle_behavior_review_replay_cache,
            "seal_exact_directories",
            side_effect=seal,
        ), ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(
                lambda _index: self._load(lambda: self.chain), range(4),
            ))
        self.assertTrue(all(result is self.chain for result in results))
        self.assertEqual(1, seals)

    def test_clear_during_flight_starts_a_new_generation(self) -> None:
        started = Event()
        release = Event()
        calls = 0

        def loader():
            nonlocal calls
            calls += 1
            if calls == 1:
                started.set()
                self.assertTrue(release.wait(timeout=1))
            return self.chain

        with ThreadPoolExecutor(max_workers=2) as pool:
            old = pool.submit(self._load, loader)
            self.assertTrue(started.wait(timeout=1))
            clear_idle_behavior_review_replay_cache()
            current = pool.submit(self._load, loader)
            self.assertIs(self.chain, current.result(timeout=1))
            release.set()
            self.assertIs(self.chain, old.result(timeout=1))
        self.assertIs(self.chain, self._load(loader))
        self.assertEqual(2, calls)

    def test_different_exact_addresses_do_not_share_a_global_io_lock(self) -> None:
        from autospine_workbench import idle_behavior_review_replay_cache
        barrier = Barrier(2)

        def replay(*_args, **_kwargs):
            barrier.wait(timeout=1)
            return self.chain

        def load(bundle):
            return load_cached_reviewed_motion_chain(
                self.root, self.project, self.instance, bundle,
                lambda: self.chain,
            )

        with patch.object(
            idle_behavior_review_replay_cache,
            "_load_or_reuse",
            side_effect=replay,
        ), ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(load, ("2" * 64, "3" * 64)))
        self.assertTrue(all(result is self.chain for result in results))


if __name__ == "__main__":
    unittest.main()
