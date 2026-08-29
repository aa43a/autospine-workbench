"""Tests for the reusable exact-address immutable bundle filesystem."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.immutable_bundle_fs import (  # noqa: E402
    ImmutableBundleFSError,
    ImmutableThreeFileBundleFS,
    framed_bundle_sha256,
)
from autospine_workbench import immutable_bundle_publish  # noqa: E402

NAMES = ("evidence.json", "run.json", "summary.json")
PRIMARY = "a" * 64


class ImmutableBundleFSTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "state"
        self.files = {
            "evidence.json": b'{"evidence":1}\n',
            "run.json": b'{"run":1}\n',
            "summary.json": b'{"summary":1}\n',
        }
        self.store = ImmutableThreeFileBundleFS(
            self.root, namespace="camera-motion", domain="camera-motion/v1",
            ordered_names=NAMES, max_file_bytes=100, max_total_bytes=200,
        )
        self.address = self.store.address(self.files)

    def test_address_is_domain_order_name_length_and_byte_separated(self) -> None:
        baseline = framed_bundle_sha256("one", NAMES, self.files)
        self.assertEqual(baseline, framed_bundle_sha256("one", NAMES, self.files))
        self.assertNotEqual(baseline, framed_bundle_sha256("two", NAMES, self.files))
        self.assertNotEqual(
            baseline, framed_bundle_sha256("one", tuple(reversed(NAMES)), self.files),
        )
        renamed = dict(self.files)
        renamed["evidence-v2.json"] = renamed.pop("evidence.json")
        self.assertNotEqual(baseline, framed_bundle_sha256(
            "one", ("evidence-v2.json", *NAMES[1:]), renamed,
        ))
        boundary_a = {**self.files, NAMES[0]: b"ab", NAMES[1]: b"c"}
        boundary_b = {**self.files, NAMES[0]: b"a", NAMES[1]: b"bc"}
        self.assertNotEqual(
            framed_bundle_sha256("one", NAMES, boundary_a),
            framed_bundle_sha256("one", NAMES, boundary_b),
        )

    def test_publish_read_and_identical_reuse_are_exact(self) -> None:
        first = self.store.publish(PRIMARY, self.address, self.files)
        second = self.store.publish(PRIMARY, self.address, self.files)
        self.assertFalse(first.reused)
        self.assertTrue(second.reused)
        self.assertEqual(self.store.exact_path(PRIMARY, self.address), first.path)
        self.assertEqual(set(NAMES), {path.name for path in first.path.iterdir()})
        snapshot = self.store.read(PRIMARY, self.address)
        self.assertEqual(tuple(self.files[name] for name in NAMES), snapshot.payloads)
        self.assertEqual(self.files[NAMES[1]], snapshot.file_bytes(NAMES[1]))
        self.assertFalse((first.path.parent / "latest").exists())

    def test_concurrent_publication_converges_to_one_exact_directory(self) -> None:
        with ThreadPoolExecutor(max_workers=6) as executor:
            results = list(executor.map(
                lambda _: self.store.publish(PRIMARY, self.address, self.files),
                range(12),
            ))
        self.assertEqual({self.store.exact_path(PRIMARY, self.address)}, {
            result.path for result in results
        })
        self.assertEqual({self.address}, {
            child.name for child in results[0].path.parent.iterdir()
        })

    def test_partial_write_failure_removes_stage_and_publishes_nothing(self) -> None:
        original = immutable_bundle_publish._write
        calls = 0

        def fail_after_first_file(path: Path, data: bytes) -> None:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("injected write failure")
            original(path, data)

        with patch.object(
            immutable_bundle_publish, "_write", fail_after_first_file,
        ), self.assertRaises(ImmutableBundleFSError):
            self.store.publish(PRIMARY, self.address, self.files)
        parent = self.root / "camera-motion" / PRIMARY
        self.assertTrue(parent.is_dir())
        self.assertEqual([], list(parent.iterdir()))
        self.assertFalse(self.store.exact_path(PRIMARY, self.address).exists())

    def test_bad_addresses_inventory_bytes_and_limits_fail_closed(self) -> None:
        with self.assertRaises(ImmutableBundleFSError):
            self.store.publish(PRIMARY, "b" * 64, self.files)
        with self.assertRaises(ImmutableBundleFSError):
            self.store.read(PRIMARY.upper(), self.address)
        with self.assertRaises(ImmutableBundleFSError):
            self.store.address({**self.files, "extra": b"x"})
        tiny = ImmutableThreeFileBundleFS(
            self.root / "tiny", namespace="n", domain="d", ordered_names=NAMES,
            max_file_bytes=4, max_total_bytes=10,
        )
        with self.assertRaisesRegex(ImmutableBundleFSError, "byte limit"):
            tiny.address(self.files)

        published = self.store.publish(PRIMARY, self.address, self.files)
        (published.path / NAMES[0]).write_bytes(b"changed")
        with self.assertRaises(ImmutableBundleFSError):
            self.store.read(PRIMARY, self.address)
        with self.assertRaises(ImmutableBundleFSError):
            self.store.publish(PRIMARY, self.address, self.files)

    def test_missing_extra_directory_and_wrong_case_are_rejected(self) -> None:
        for mutate in (
            lambda path: (path / NAMES[0]).unlink(),
            lambda path: (path / "extra.json").write_bytes(b"{}"),
            lambda path: (path / NAMES[0]).unlink() or (path / NAMES[0]).mkdir(),
            self._wrong_case,
        ):
            with self.subTest(mutate=mutate), tempfile.TemporaryDirectory() as directory:
                store = ImmutableThreeFileBundleFS(
                    Path(directory) / "state", namespace="camera-motion",
                    domain="camera-motion/v1", ordered_names=NAMES,
                    max_file_bytes=100, max_total_bytes=200,
                )
                address = store.address(self.files)
                path = store.publish(PRIMARY, address, self.files).path
                mutate(path)
                with self.assertRaises(ImmutableBundleFSError):
                    store.read(PRIMARY, address)

    def test_symlinked_root_or_file_is_rejected_when_supported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            real = base / "real"
            real.mkdir()
            alias = base / "alias"
            try:
                alias.symlink_to(real, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"directory symlink unavailable: {exc}")
            store = ImmutableThreeFileBundleFS(
                alias, namespace="n", domain="d", ordered_names=NAMES,
                max_file_bytes=100, max_total_bytes=200,
            )
            with self.assertRaisesRegex(ImmutableBundleFSError, "aliased"):
                store.publish(PRIMARY, store.address(self.files), self.files)
            alias.unlink()

        path = self.store.publish(PRIMARY, self.address, self.files).path
        target = path.parent / "outside"
        target.write_bytes(self.files[NAMES[0]])
        victim = path / NAMES[0]
        victim.unlink()
        try:
            os.symlink(target, victim)
        except OSError as exc:
            self.skipTest(f"file symlink unavailable: {exc}")
        with self.assertRaises(ImmutableBundleFSError):
            self.store.read(PRIMARY, self.address)

    def test_symlinked_root_ancestor_is_rejected_when_supported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            real = base / "real"
            real.mkdir()
            alias = base / "alias"
            try:
                alias.symlink_to(real, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"directory symlink unavailable: {exc}")
            store = ImmutableThreeFileBundleFS(
                alias / "state", namespace="n", domain="d",
                ordered_names=NAMES, max_file_bytes=100,
                max_total_bytes=200,
            )
            with self.assertRaisesRegex(ImmutableBundleFSError, "alias"):
                store.publish(PRIMARY, store.address(self.files), self.files)
            alias.unlink()

    @staticmethod
    def _wrong_case(path: Path) -> None:
        original = path / NAMES[0]
        temporary = path / "temporary"
        original.rename(temporary)
        temporary.rename(path / NAMES[0].upper())


if __name__ == "__main__":
    unittest.main()
