"""Atomic immutable storage tests for exact-address P4 IK bundles."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import FrozenInstanceError
import json
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

from autospine_workbench.ik_bundle_contract import (  # noqa: E402
    build_ik_bundle_contract,
)
from autospine_workbench.ik_bundle_store import (  # noqa: E402
    IkBundleStore,
    IkBundleStoreError,
    _remove_staging,
)
from autospine_workbench.ik_probe_report import build_ik_probe_report  # noqa: E402
from tests.test_ik_probe_report import profile_fixture  # noqa: E402


class StoreFixture:
    def __init__(self, root: Path):
        self.state = root / "state"
        profile = profile_fixture()
        self.values = (
            profile["project_id"], profile,
            build_ik_probe_report(profile).document,
        )
        self.store = IkBundleStore(self.state)

    @property
    def contract(self):
        return build_ik_bundle_contract(*self.values)

    def publish(self):
        return self.store.publish(*self.values)


class IkBundleStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.fixture = StoreFixture(Path(self.temporary.name))

    def test_publication_is_exact_canonical_idempotent_and_has_no_latest(self):
        before = deepcopy(self.fixture.values)
        first = self.fixture.publish()
        with patch(
            "autospine_workbench.ik_bundle_store._write_file",
            side_effect=AssertionError("existing exact bytes must be reused"),
        ):
            second = self.fixture.publish()
        contract = self.fixture.contract
        expected = (
            self.fixture.state / "builds" / contract.project_id /
            "ik-targets" / contract.profile_sha256 / contract.bundle_sha256
        )
        self.assertEqual(first, second)
        self.assertEqual(expected, first.path)
        self.assertEqual(contract.profile_sha256, first.profile_sha256)
        self.assertEqual(contract.bundle_sha256, first.bundle_sha256)
        self.assertEqual({"profile.json", "probes.json"}, {
            item.name for item in first.path.iterdir()
        })
        for name, data in contract.document_bytes.items():
            self.assertEqual(data, (first.path / name).read_bytes())
            self.assertEqual(json.loads(data), json.loads((first.path / name).read_text()))
        self.assertEqual(before, self.fixture.values)
        self.assertFalse((first.path.parent / "latest").exists())
        self.assertFalse((first.path.parent / "latest.json").exists())
        with self.assertRaises(FrozenInstanceError):
            first.path = Path("changed")  # type: ignore[misc]

    def test_concurrent_identical_publication_converges_to_one_bundle(self):
        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(lambda _index: self.fixture.publish(), range(16)))
        self.assertEqual(1, len(set(results)))
        parent = results[0].path.parent
        self.assertEqual({results[0].bundle_sha256}, {
            item.name for item in parent.iterdir()
        })

    def test_existing_missing_extra_changed_or_wrong_case_fails_without_repair(self):
        mutations = (
            lambda bundle: (bundle / "profile.json").unlink(),
            lambda bundle: (bundle / "extra.json").write_bytes(b"{}"),
            lambda bundle: (bundle / "probes.json").write_bytes(b"{}"),
            lambda bundle: (bundle / "empty").mkdir(),
            self._wrong_case_profile,
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate), tempfile.TemporaryDirectory() as directory:
                fixture = StoreFixture(Path(directory))
                published = fixture.publish()
                mutate(published.path)
                before = self._tree(published.path)
                with self.assertRaises(IkBundleStoreError):
                    fixture.publish()
                self.assertEqual(before, self._tree(published.path))

    def test_case_mismatched_hierarchy_and_preexisting_conflict_are_rejected(self):
        published = self.fixture.publish()
        ik_targets = published.path.parent.parent
        temporary = ik_targets.parent / "renaming"
        ik_targets.rename(temporary)
        temporary.rename(ik_targets.parent / "IK-TARGETS")
        with self.assertRaisesRegex(IkBundleStoreError, "aliased"):
            self.fixture.publish()

        with tempfile.TemporaryDirectory() as directory:
            fixture = StoreFixture(Path(directory))
            contract = fixture.contract
            conflict = (
                fixture.state / "builds" / contract.project_id / "ik-targets" /
                contract.profile_sha256 / contract.bundle_sha256
            )
            conflict.mkdir(parents=True)
            marker = conflict / "owner.txt"
            marker.write_text("foreign", encoding="utf-8")
            with self.assertRaises(IkBundleStoreError):
                fixture.publish()
            self.assertEqual("foreign", marker.read_text(encoding="utf-8"))

    def test_symlinked_state_or_bundle_file_is_rejected_when_supported(self):
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
                fixture = StoreFixture(root)
                fixture.state = alias
                fixture.store = IkBundleStore(alias)
                with self.assertRaisesRegex(IkBundleStoreError, "aliased"):
                    fixture.publish()
                alias.unlink()

        published = self.fixture.publish()
        profile = published.path / "profile.json"
        outside = Path(self.temporary.name) / "outside.json"
        outside.write_bytes(profile.read_bytes())
        profile.unlink()
        try:
            profile.symlink_to(outside)
        except OSError:
            profile.write_bytes(outside.read_bytes())
            return
        with self.assertRaises(IkBundleStoreError):
            self.fixture.publish()
        self.assertEqual(outside.read_bytes(), profile.read_bytes())
        profile.unlink()

    def test_junction_or_reparse_state_is_rejected_before_publication(self):
        junction = getattr(Path, "is_junction", None)
        if not callable(junction):
            self.skipTest("Path.is_junction is unavailable")
        with patch.object(Path, "is_junction", return_value=True):
            with self.assertRaisesRegex(IkBundleStoreError, "aliased"):
                self.fixture.publish()

    def test_invalid_input_creates_no_state_and_write_failure_leaves_no_stage(self):
        self.fixture.values[1]["handles"][0]["extra"] = True
        with self.assertRaisesRegex(IkBundleStoreError, "input is invalid"):
            self.fixture.publish()
        self.assertFalse(self.fixture.state.exists())

        with tempfile.TemporaryDirectory() as directory:
            fixture = StoreFixture(Path(directory))
            contract = fixture.contract
            with patch(
                "autospine_workbench.ik_bundle_store._write_file",
                side_effect=OSError("synthetic write failure"),
            ):
                with self.assertRaisesRegex(IkBundleStoreError, "atomically"):
                    fixture.publish()
            parent = (
                fixture.state / "builds" / contract.project_id / "ik-targets" /
                contract.profile_sha256
            )
            self.assertTrue(parent.is_dir())
            self.assertEqual([], list(parent.iterdir()))

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
        with patch.object(
            Path, "resolve",
            side_effect=(parent.resolve(strict=True), fake_destination.resolve(strict=True)),
        ):
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

    @staticmethod
    def _wrong_case_profile(bundle):
        source = bundle / "profile.json"
        temporary = bundle / "renaming"
        source.rename(temporary)
        temporary.rename(bundle / "PROFILE.JSON")

    @staticmethod
    def _tree(root):
        return {
            item.relative_to(root).as_posix(): (
                item.read_bytes() if item.is_file() else None
            )
            for item in root.rglob("*")
        }


if __name__ == "__main__":
    unittest.main()
