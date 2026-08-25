"""Atomic immutable P3 mesh bundle store tests."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import FrozenInstanceError
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.mesh_bundle_contract import (  # noqa: E402
    build_mesh_bundle_contract,
)
from autospine_workbench.mesh_bundle_store import (  # noqa: E402
    MeshBundleStore,
    MeshBundleStoreError,
    _remove_staging,
)
from tests.test_mesh_bundle_contract import payload_a, payload_noop  # noqa: E402


class StoreFixture:
    def __init__(self, root: Path, payload=None):
        self.state = root / "state"
        self.values = deepcopy(payload or payload_a())
        self.store = MeshBundleStore(self.state)

    def publish(self):
        return self.store.publish(*self.values)

    @property
    def contract(self):
        return build_mesh_bundle_contract(*self.values)


class MeshBundleStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.fixture = StoreFixture(Path(self.temporary.name))

    def test_publish_is_complete_content_addressed_canonical_and_idempotent(self):
        first = self.fixture.publish()
        second = self.fixture.publish()
        contract = self.fixture.contract
        expected = (self.fixture.state / "builds" / contract.project_id /
                    "mesh-rig-ir" / contract.rig_sha256 / contract.bundle_sha256)
        self.assertEqual(first, second)
        self.assertEqual(expected, first.path)
        self.assertEqual(contract.rig_sha256, first.rig_sha256)
        self.assertEqual(contract.bundle_sha256, first.bundle_sha256)
        files = {item.relative_to(first.path).as_posix()
                 for item in first.path.rglob("*") if item.is_file()}
        self.assertEqual(set(contract.inventory), files)
        for name, data in contract.document_bytes.items():
            self.assertEqual(data, (first.path / name).read_bytes())
            self.assertEqual(json.loads(data), json.loads((first.path / name).read_text()))
        for name, data in contract.png_bytes_by_path.items():
            self.assertEqual(data, (first.path / name).read_bytes())
        self.assertFalse((first.path.parent / "latest").exists())
        self.assertFalse((first.path.parent / "latest.json").exists())
        with self.assertRaises(FrozenInstanceError):
            first.path = Path("changed")  # type: ignore[misc]

    def test_publish_does_not_mutate_inputs_and_noop_has_no_png_directories(self):
        before = deepcopy(self.fixture.values)
        self.fixture.publish()
        self.assertEqual(before, self.fixture.values)
        with tempfile.TemporaryDirectory() as directory:
            fixture = StoreFixture(Path(directory), payload_noop())
            published = fixture.publish()
            self.assertEqual(
                {"rig.json", "run-manifest.json", "probes.json", "visuals.json"},
                {item.name for item in published.path.iterdir()},
            )

    def test_concurrent_identical_publication_converges(self):
        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(lambda _index: self.fixture.publish(), range(16)))
        self.assertEqual(1, len(set(results)))
        parent = results[0].path.parent
        self.assertEqual({results[0].bundle_sha256}, {item.name for item in parent.iterdir()})

    def test_existing_missing_extra_or_changed_content_fails_without_repair(self):
        cases = (
            lambda bundle: (bundle / "rig.json").unlink(),
            lambda bundle: (bundle / "extra.bin").write_bytes(b"extra"),
            lambda bundle: (bundle / "weights" / "extra.png").write_bytes(b"extra"),
            lambda bundle: (bundle / "visuals.json").write_bytes(b"{}"),
            lambda bundle: (bundle / "empty").mkdir(),
        )
        for mutate in cases:
            with self.subTest(mutate=mutate), tempfile.TemporaryDirectory() as directory:
                fixture = StoreFixture(Path(directory))
                published = fixture.publish()
                mutate(published.path)
                before = sorted(item.relative_to(published.path).as_posix()
                                for item in published.path.rglob("*"))
                with self.assertRaises(MeshBundleStoreError):
                    fixture.publish()
                after = sorted(item.relative_to(published.path).as_posix()
                               for item in published.path.rglob("*"))
                self.assertEqual(before, after)

    def test_existing_wrong_case_path_is_rejected(self):
        published = self.fixture.publish()
        weights = published.path / "weights"
        intermediate = published.path / "renaming"
        weights.rename(intermediate)
        intermediate.rename(published.path / "WEIGHTS")
        with self.assertRaisesRegex(MeshBundleStoreError, "inventory"):
            self.fixture.publish()

    def test_symlinked_state_or_bundle_entry_is_rejected_when_supported(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            real = root / "real"
            real.mkdir()
            alias = root / "alias"
            try:
                alias.symlink_to(real, target_is_directory=True)
            except OSError:
                self.skipTest("directory symlinks are unavailable")
            fixture = StoreFixture(root)
            fixture.state = alias
            fixture.store = MeshBundleStore(alias)
            with self.assertRaisesRegex(MeshBundleStoreError, "aliased"):
                fixture.publish()
            alias.unlink()

        published = self.fixture.publish()
        weights = published.path / "weights"
        shutil.rmtree(weights)
        outside = Path(self.temporary.name) / "outside"
        outside.mkdir()
        weights.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(MeshBundleStoreError):
            self.fixture.publish()
        self.assertEqual([], list(outside.iterdir()))
        weights.unlink()

    def test_invalid_inputs_do_not_create_publication_state(self):
        self.fixture.values[4]["status"] = "rejected"
        with self.assertRaisesRegex(MeshBundleStoreError, "input is invalid"):
            self.fixture.publish()
        self.assertFalse(self.fixture.state.exists())

    def test_write_failure_leaves_no_bundle_or_staging_directory(self):
        contract = self.fixture.contract
        with patch("autospine_workbench.mesh_bundle_store._write_file",
                   side_effect=OSError("synthetic write failure")):
            with self.assertRaisesRegex(MeshBundleStoreError, "atomically"):
                self.fixture.publish()
        parent = (self.fixture.state / "builds" / contract.project_id /
                  "mesh-rig-ir" / contract.rig_sha256)
        self.assertTrue(parent.is_dir())
        self.assertEqual([], list(parent.iterdir()))

    def test_preexisting_conflicting_address_is_never_overwritten(self):
        contract = self.fixture.contract
        parent = (self.fixture.state / "builds" / contract.project_id /
                  "mesh-rig-ir" / contract.rig_sha256)
        conflict = parent / contract.bundle_sha256
        conflict.mkdir(parents=True)
        marker = conflict / "owner.txt"
        marker.write_text("foreign", encoding="utf-8")
        with self.assertRaises(MeshBundleStoreError):
            self.fixture.publish()
        self.assertEqual("foreign", marker.read_text(encoding="utf-8"))

    def test_staging_cleanup_refuses_wrong_parent_name_alias_and_escape(self):
        parent = Path(self.temporary.name) / "safe-parent"
        parent.mkdir()
        wrong_name = parent / "ordinary"
        wrong_name.mkdir()
        _remove_staging(wrong_name, parent)
        self.assertTrue(wrong_name.exists())

        outside = Path(self.temporary.name) / ".123456789abc.escape"
        outside.mkdir()
        _remove_staging(outside, parent)
        self.assertTrue(outside.exists())

        escaped = parent / ".123456789abc.escape"
        escaped.mkdir()
        fake_destination = Path(self.temporary.name) / "resolved-elsewhere"
        fake_destination.mkdir()
        parent_resolved = parent.resolve(strict=True)
        escaped_resolved = fake_destination.resolve(strict=True)
        with patch.object(Path, "resolve", side_effect=(parent_resolved, escaped_resolved)):
            _remove_staging(escaped, parent)
        self.assertTrue(escaped.exists())

        target = parent / "real-stage"
        target.mkdir()
        alias = parent / ".123456789abc.alias"
        try:
            alias.symlink_to(target, target_is_directory=True)
        except OSError:
            return
        _remove_staging(alias, parent)
        self.assertTrue(alias.exists())
        self.assertTrue(target.exists())
        alias.unlink()


if __name__ == "__main__":
    unittest.main()
