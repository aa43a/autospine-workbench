"""Atomic Spine 4.2 bundle store and strict reader tests."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.spine42_bundle_contract import (  # noqa: E402
    DOCUMENT_NAMES,
    build_spine42_bundle_contract,
)
from autospine_workbench.spine42_bundle_integrity import (  # noqa: E402
    Spine42BundleIntegrityError,
    Spine42BundleSnapshot,
    VerifiedSpine42BundleReader,
    verify_spine42_bundle_snapshot,
)
from autospine_workbench.spine42_bundle_store import (  # noqa: E402
    Spine42BundleStore,
    Spine42BundleStoreError,
)
from tests.spine42_bundle_helpers import build_args, bundle_inputs  # noqa: E402


class Spine42BundleStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.values = bundle_inputs(motion=True)
        self.contract = build_spine42_bundle_contract(
            *build_args(self.values), p5_source=self.values["p5_source"]
        )

    def store(self, name="state"):
        return Spine42BundleStore(self.root / name)

    def publish(self, store=None):
        return (store or self.store()).publish(
            *build_args(self.values), p5_source=self.values["p5_source"]
        )

    def test_publish_reuse_reader_and_exact_path(self):
        store = self.store()
        first = self.publish(store)
        second = self.publish(store)
        expected = (
            self.root / "state" / "builds" / self.contract.project_id /
            "spine42" / self.contract.skeleton_json_sha256 /
            self.contract.bundle_sha256
        )
        self.assertEqual(expected, first.path)
        self.assertFalse(first.reused)
        self.assertTrue(second.reused)
        self.assertEqual(set(DOCUMENT_NAMES), {item.name for item in expected.iterdir()})
        self.assertFalse((expected.parent / "latest").exists())
        self.assertFalse((expected.parent / "latest.json").exists())

        verified = VerifiedSpine42BundleReader(self.root / "state").load(
            self.contract.project_id, self.contract.skeleton_json_sha256,
            self.contract.bundle_sha256,
        )
        self.assertEqual(self.contract.bundle_sha256, verified.bundle_sha256)
        self.assertEqual(DOCUMENT_NAMES, verified.inventory)
        self.assertEqual(self.values["source_image_sha256s"],
                         verified.source_image_sha256s)
        verified.skeleton_json.clear()
        verified.document_bytes.clear()
        self.assertTrue(verified.skeleton_json)
        self.assertEqual(DOCUMENT_NAMES, verified.inventory)
        with self.assertRaises(FrozenInstanceError):
            first.path = Path("changed")  # type: ignore[misc]

    def test_concurrent_publication_converges_once(self):
        store = self.store("concurrent")
        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(lambda _index: self.publish(store), range(16)))
        self.assertEqual(1, len({result.path for result in results}))
        self.assertEqual(1, sum(not result.reused for result in results))
        self.assertEqual(
            {self.contract.bundle_sha256},
            {item.name for item in results[0].path.parent.iterdir()},
        )

    def test_missing_extra_tampered_and_nonregular_fail_closed(self):
        mutations = (
            lambda root: (root / "skeleton.json").unlink(),
            lambda root: (root / "extra.json").write_bytes(b"{}"),
            lambda root: (root / "run-manifest.json").write_bytes(b"{}"),
            lambda root: (root / "directory").mkdir(),
        )
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                store = self.store(f"tamper-{index}")
                published = self.publish(store)
                mutate(published.path)
                before = sorted(item.name for item in published.path.iterdir())
                with self.assertRaises(Spine42BundleStoreError):
                    self.publish(store)
                self.assertEqual(before,
                                 sorted(item.name for item in published.path.iterdir()))

    def test_case_alias_hierarchy_and_symlink_are_rejected(self):
        store = self.store("case-file")
        published = self.publish(store)
        source = published.path / "skeleton.json"
        middle = published.path / "renaming"
        source.rename(middle)
        middle.rename(published.path / "SKELETON.JSON")
        with self.assertRaises(Spine42BundleStoreError):
            self.publish(store)

        store = self.store("case-path")
        published = self.publish(store)
        spine = published.path.parents[1]
        middle = spine.parent / "renaming"
        spine.rename(middle)
        middle.rename(spine.parent / "SPINE42")
        with self.assertRaisesRegex(Spine42BundleStoreError, "atomically"):
            self.publish(store)

        real = self.root / "real"
        real.mkdir()
        alias = self.root / "alias"
        try:
            alias.symlink_to(real, target_is_directory=True)
        except OSError:
            return
        try:
            with self.assertRaises(Spine42BundleStoreError):
                Spine42BundleStore(alias).publish(
                    *build_args(self.values), p5_source=self.values["p5_source"]
                )
        finally:
            alias.unlink()

    def test_reader_rejects_tamper_wrong_address_and_extra_file(self):
        published = self.publish()
        reader = VerifiedSpine42BundleReader(self.root / "state")
        with self.assertRaises(Spine42BundleIntegrityError):
            reader.load(
                self.contract.project_id, "f" * 64, self.contract.bundle_sha256
            )
        (published.path / "extra").write_bytes(b"x")
        with self.assertRaises(Spine42BundleIntegrityError):
            reader.load(
                self.contract.project_id, self.contract.skeleton_json_sha256,
                self.contract.bundle_sha256,
            )

    def test_snapshot_inventory_tamper_and_path_escape_fail(self):
        published = self.publish()
        items = tuple(
            (name, (published.path / name).read_bytes()) for name in DOCUMENT_NAMES
        )
        kwargs = {
            "state_root": self.root / "state",
            "expected_project_id": self.contract.project_id,
            "expected_skeleton_json_sha256": self.contract.skeleton_json_sha256,
            "expected_bundle_sha256": self.contract.bundle_sha256,
        }
        verified = verify_spine42_bundle_snapshot(
            Spine42BundleSnapshot(published.path, items), **kwargs
        )
        self.assertEqual(self.contract.run_identity_sha256,
                         verified.run_identity_sha256)

        changed = list(items)
        changed[0] = (changed[0][0], changed[0][1] + b"\n")
        with self.assertRaises(Spine42BundleIntegrityError):
            verify_spine42_bundle_snapshot(
                Spine42BundleSnapshot(published.path, tuple(changed)), **kwargs
            )
        swapped = list(items)
        swapped[0], swapped[1] = swapped[1], swapped[0]
        with self.assertRaisesRegex(Spine42BundleIntegrityError, "inventory"):
            verify_spine42_bundle_snapshot(
                Spine42BundleSnapshot(published.path, tuple(swapped)), **kwargs
            )
        outside = self.root / "outside"
        outside.mkdir()
        with self.assertRaises(Spine42BundleIntegrityError):
            verify_spine42_bundle_snapshot(
                replace(Spine42BundleSnapshot(published.path, items), directory=outside),
                **kwargs,
            )

    def test_conflicting_address_is_never_overwritten(self):
        parent = (
            self.root / "conflict" / "builds" / self.contract.project_id /
            "spine42" / self.contract.skeleton_json_sha256
        )
        destination = parent / self.contract.bundle_sha256
        destination.mkdir(parents=True)
        marker = destination / "owner.txt"
        marker.write_text("foreign", encoding="utf-8")
        with self.assertRaises(Spine42BundleStoreError):
            self.publish(self.store("conflict"))
        self.assertEqual("foreign", marker.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
