"""Atomic immutable storage tests for built-in MotionIR bundles."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.motion_bundle_contract import (  # noqa: E402
    build_motion_bundle_contract,
)
from autospine_workbench.motion_bundle_store import (  # noqa: E402
    MotionBundleStore,
    MotionBundleStoreError,
    _remove_staging,
)
from tests.test_motion_bundle_contract import payload, reverse_keys  # noqa: E402


class StoreFixture:
    def __init__(self, root: Path, clip_id: str = "idle") -> None:
        self.state = root / "state"
        self.values = payload(clip_id)
        self.store = MotionBundleStore(self.state)

    @property
    def contract(self):
        return build_motion_bundle_contract(*self.values)

    def publish(self):
        return self.store.publish(*self.values)


class MotionBundleStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.fixture = StoreFixture(Path(self.temporary.name))

    def test_exact_path_canonical_identity_idempotency_and_no_aliases(self) -> None:
        before = deepcopy(self.fixture.values)
        first = self.fixture.publish()
        reordered = tuple(reverse_keys(value) for value in self.fixture.values)
        second = self.fixture.store.publish(*reordered)
        contract = self.fixture.contract
        expected = (
            self.fixture.state / "motions" / contract.clip_sha256 /
            contract.bundle_sha256
        )
        self.assertEqual(expected, first.path)
        self.assertEqual(expected, second.path)
        self.assertFalse(first.reused)
        self.assertTrue(second.reused)
        self.assertEqual(contract.clip_id, first.clip_id)
        self.assertEqual(contract.clip_sha256, first.clip_sha256)
        self.assertEqual(contract.run_sha256, first.run_sha256)
        self.assertEqual(contract.bundle_sha256, first.bundle_sha256)
        self.assertEqual({"motion.json", "run-manifest.json"}, {
            item.name for item in first.path.iterdir()
        })
        for name, data in contract.document_bytes.items():
            self.assertEqual(data, (first.path / name).read_bytes())
            self.assertEqual(json.loads(data), json.loads((first.path / name).read_text()))
        self.assertEqual(before, self.fixture.values)
        self.assertFalse((first.path.parent / "latest").exists())
        self.assertFalse((first.path.parent / "latest.json").exists())
        with self.assertRaises(FrozenInstanceError):
            first.reused = True  # type: ignore[misc]

    def test_distinct_builtins_have_distinct_content_addresses(self) -> None:
        idle = self.fixture.publish()
        wave = StoreFixture(Path(self.temporary.name), "wave.left").publish()
        self.assertNotEqual(idle.clip_sha256, wave.clip_sha256)
        self.assertNotEqual(idle.bundle_sha256, wave.bundle_sha256)
        self.assertNotEqual(idle.path.parent, wave.path.parent)

    def test_concurrent_identical_publication_converges_without_residue(self) -> None:
        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(lambda _index: self.fixture.publish(), range(16)))
        identity = {(item.path, item.clip_id, item.clip_sha256, item.run_sha256,
                     item.bundle_sha256) for item in results}
        self.assertEqual(1, len(identity))
        self.assertEqual(1, sum(not item.reused for item in results))
        self.assertEqual({results[0].bundle_sha256}, {
            item.name for item in results[0].path.parent.iterdir()
        })

    def test_existing_missing_extra_changed_case_or_directory_fails_closed(self) -> None:
        mutations = (
            lambda bundle: (bundle / "motion.json").unlink(),
            lambda bundle: (bundle / "extra.json").write_bytes(b"{}"),
            lambda bundle: (bundle / "run-manifest.json").write_bytes(b"{}"),
            lambda bundle: (bundle / "extra").mkdir(),
            self._wrong_case_motion,
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate), tempfile.TemporaryDirectory() as directory:
                fixture = StoreFixture(Path(directory))
                published = fixture.publish()
                mutate(published.path)
                before = self._tree(published.path)
                with self.assertRaises(MotionBundleStoreError):
                    fixture.publish()
                self.assertEqual(before, self._tree(published.path))

    def test_case_mismatched_hierarchy_and_preexisting_target_are_rejected(self) -> None:
        published = self.fixture.publish()
        motions = published.path.parent.parent
        temporary = motions.parent / "renaming"
        motions.rename(temporary)
        temporary.rename(motions.parent / "MOTIONS")
        with self.assertRaisesRegex(MotionBundleStoreError, "aliased"):
            self.fixture.publish()

        with tempfile.TemporaryDirectory() as directory:
            fixture = StoreFixture(Path(directory))
            contract = fixture.contract
            conflict = (
                fixture.state / "motions" / contract.clip_sha256 /
                contract.bundle_sha256
            )
            conflict.mkdir(parents=True)
            marker = conflict / "owner.txt"
            marker.write_text("foreign", encoding="utf-8")
            with self.assertRaises(MotionBundleStoreError):
                fixture.publish()
            self.assertEqual("foreign", marker.read_text(encoding="utf-8"))

    def test_state_ancestor_and_target_symlinks_are_rejected_when_supported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            real = root / "real"
            real.mkdir()
            alias = root / "alias"
            try:
                alias.symlink_to(real, target_is_directory=True)
            except OSError:
                alias = None
            if alias is not None:
                fixture = StoreFixture(alias)
                with self.assertRaisesRegex(MotionBundleStoreError, "aliased"):
                    fixture.publish()
                alias.unlink()

        published = self.fixture.publish()
        outside = Path(self.temporary.name) / "outside-bundle"
        published.path.rename(outside)
        try:
            published.path.symlink_to(outside, target_is_directory=True)
        except OSError:
            outside.rename(published.path)
            return
        before = self._tree(outside)
        with self.assertRaisesRegex(MotionBundleStoreError, "aliased"):
            self.fixture.publish()
        self.assertEqual(before, self._tree(outside))
        published.path.unlink()

    def test_junction_or_reparse_ancestor_is_rejected(self) -> None:
        junction = getattr(Path, "is_junction", None)
        if not callable(junction):
            self.skipTest("Path.is_junction is unavailable")
        with patch.object(Path, "is_junction", return_value=True):
            with self.assertRaisesRegex(MotionBundleStoreError, "aliased"):
                self.fixture.publish()

    def test_invalid_identity_or_resource_creates_no_state(self) -> None:
        self.fixture.values[0]["tracks"][0]["keys"][1]["value"] = -999.0
        with self.assertRaisesRegex(MotionBundleStoreError, "input is invalid"):
            self.fixture.publish()
        self.assertFalse(self.fixture.state.exists())

        with tempfile.TemporaryDirectory() as directory:
            fixture = StoreFixture(Path(directory))
            with patch(
                "autospine_workbench.motion_bundle_contract.MAX_TOTAL_DOCUMENT_BYTES", 1,
            ):
                with self.assertRaisesRegex(MotionBundleStoreError, "input is invalid"):
                    fixture.publish()
            self.assertFalse(fixture.state.exists())

    def test_write_failure_cleans_staging(self) -> None:
        contract = self.fixture.contract
        with patch(
            "autospine_workbench.motion_bundle_store._write_file",
            side_effect=OSError("synthetic write failure"),
        ), self.assertRaises(MotionBundleStoreError):
            self.fixture.publish()
        parent = self.fixture.state / "motions" / contract.clip_sha256
        self.assertTrue(parent.is_dir())
        self.assertEqual([], list(parent.iterdir()))

    def test_publication_builds_one_semantic_contract(self) -> None:
        real = build_motion_bundle_contract
        with patch(
            "autospine_workbench.motion_bundle_store.build_motion_bundle_contract",
            wraps=real,
        ) as build:
            self.fixture.publish()
        self.assertEqual(1, build.call_count)

    def test_rename_failure_without_winner_cleans_staging(self) -> None:
        contract = self.fixture.contract
        with patch(
            "autospine_workbench.motion_bundle_store.os.rename",
            side_effect=OSError("synthetic rename failure"),
        ):
            with self.assertRaisesRegex(MotionBundleStoreError, "atomically"):
                self.fixture.publish()
        parent = self.fixture.state / "motions" / contract.clip_sha256
        self.assertEqual([], list(parent.iterdir()))

    def test_staging_cleanup_refuses_wrong_parent_name_alias_and_escape(self) -> None:
        parent = Path(self.temporary.name) / "safe-parent"
        parent.mkdir()
        wrong = parent / "ordinary"
        wrong.mkdir()
        _remove_staging(wrong, parent)
        self.assertTrue(wrong.exists())

        outside = Path(self.temporary.name) / ".123456789abc.escape"
        outside.mkdir()
        _remove_staging(outside, parent)
        self.assertTrue(outside.exists())

        escaped = parent / ".123456789abc.escape"
        escaped.mkdir()
        elsewhere = Path(self.temporary.name) / "elsewhere"
        elsewhere.mkdir()
        with patch.object(
            Path, "resolve",
            side_effect=(elsewhere.resolve(strict=True), parent.resolve(strict=True)),
        ):
            _remove_staging(escaped, parent)
        self.assertTrue(escaped.exists())

    @staticmethod
    def _wrong_case_motion(bundle: Path) -> None:
        source = bundle / "motion.json"
        temporary = bundle / "renaming"
        source.rename(temporary)
        temporary.rename(bundle / "MOTION.JSON")

    @staticmethod
    def _tree(root: Path):
        return {
            item.relative_to(root).as_posix(): (
                item.read_bytes() if item.is_file() else None
            )
            for item in root.rglob("*")
        }


if __name__ == "__main__":
    unittest.main()
