"""Atomic immutable P5 motion-retarget bundle store tests."""

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

from autospine_workbench.motion_bundle_reader import (  # noqa: E402
    VerifiedMotionBundleReader,
)
from autospine_workbench.motion_bundle_store import MotionBundleStore  # noqa: E402
from autospine_workbench.motion_mesh_regression import (  # noqa: E402
    build_motion_mesh_regression,
)
from autospine_workbench.motion_retarget_bundle_contract import (  # noqa: E402
    build_motion_retarget_bundle_contract,
)
from autospine_workbench.motion_retarget_bundle_store import (  # noqa: E402
    MotionRetargetBundleStore,
    MotionRetargetBundleStoreError,
    _remove_staging,
)
from autospine_workbench.motion_retarget_compiler import (  # noqa: E402
    compile_motion_instance,
)
from autospine_workbench.motion_retarget_report import (  # noqa: E402
    build_motion_retarget_report,
)
from tests.test_motion_bundle_contract import payload  # noqa: E402
from tests.test_motion_mesh_regression import exact_mesh_and_target  # noqa: E402


def documents(root: Path):
    mesh, profile = exact_mesh_and_target(converted=False)
    motion_store = MotionBundleStore(root / "motion-source")
    published = motion_store.publish(*payload("idle"))
    motion = VerifiedMotionBundleReader(root / "motion-source").load(
        published.clip_sha256, published.bundle_sha256,
    )
    retargeted = compile_motion_instance(motion, profile)
    report = build_motion_retarget_report(motion, profile, retargeted)
    mesh_report = build_motion_mesh_regression(
        retargeted.instance, profile.document, mesh,
    )
    return [
        profile.document["project_id"], profile.document,
        retargeted.instance, retargeted.run, report.document,
        mesh_report.document,
    ]


class MotionRetargetBundleStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.values = documents(self.root)
        self.contract = build_motion_retarget_bundle_contract(*self.values)

    def store(self, name="state"):
        return MotionRetargetBundleStore(self.root / name)

    def test_publish_reuse_is_exact_content_addressed_and_has_no_alias(self):
        store = self.store()
        first = store.publish(*self.values)
        second = store.publish(*self.values)
        expected = (
            self.root / "state" / "builds" / self.contract.project_id /
            "motion-instances" / self.contract.instance_sha256 /
            self.contract.bundle_sha256
        )
        self.assertEqual(expected, first.path)
        self.assertFalse(first.reused)
        self.assertTrue(second.reused)
        self.assertEqual(first.path, second.path)
        self.assertEqual(self.contract.bundle_sha256, first.bundle_sha256)
        self.assertEqual(self.contract.instance_sha256, first.instance_sha256)
        self.assertEqual(
            set(self.contract.inventory),
            {item.name for item in first.path.iterdir()},
        )
        for name, data in self.contract.document_bytes.items():
            self.assertEqual(data, (first.path / name).read_bytes())
            self.assertEqual(json.loads(data), json.loads((first.path / name).read_text()))
        self.assertFalse((first.path.parent / "latest").exists())
        self.assertFalse((first.path.parent / "latest.json").exists())
        with self.assertRaises(FrozenInstanceError):
            first.path = Path("changed")  # type: ignore[misc]

    def test_concurrent_identical_publication_converges(self):
        store = self.store("concurrent")
        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(
                lambda _index: store.publish(*self.values), range(16),
            ))
        self.assertEqual(1, len({result.path for result in results}))
        self.assertEqual(1, sum(not result.reused for result in results))
        parent = results[0].path.parent
        self.assertEqual(
            {self.contract.bundle_sha256},
            {item.name for item in parent.iterdir()},
        )

    def test_missing_extra_tampered_and_nonregular_inventory_fail_closed(self):
        mutations = (
            lambda root: (root / "instance.json").unlink(),
            lambda root: (root / "extra.json").write_bytes(b"{}"),
            lambda root: (root / "retarget-report.json").write_bytes(b"{}"),
            lambda root: (root / "directory").mkdir(),
        )
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                store = self.store(f"tamper-{index}")
                published = store.publish(*self.values)
                mutate(published.path)
                before = sorted(item.name for item in published.path.iterdir())
                with self.assertRaises(MotionRetargetBundleStoreError):
                    store.publish(*self.values)
                self.assertEqual(
                    before, sorted(item.name for item in published.path.iterdir())
                )

    def test_wrong_case_inventory_and_hierarchy_are_rejected(self):
        store = self.store("case-file")
        published = store.publish(*self.values)
        source = published.path / "instance.json"
        middle = published.path / "renaming"
        source.rename(middle)
        middle.rename(published.path / "INSTANCE.JSON")
        with self.assertRaises(MotionRetargetBundleStoreError):
            store.publish(*self.values)

        store = self.store("case-path")
        published = store.publish(*self.values)
        instances = published.path.parents[1]
        middle = instances.parent / "renaming"
        instances.rename(middle)
        middle.rename(instances.parent / "MOTION-INSTANCES")
        with self.assertRaisesRegex(MotionRetargetBundleStoreError, "aliased"):
            store.publish(*self.values)

    def test_symlinked_state_and_file_are_rejected_when_supported(self):
        real = self.root / "real-state"
        real.mkdir()
        alias = self.root / "alias-state"
        try:
            alias.symlink_to(real, target_is_directory=True)
        except OSError:
            self.skipTest("directory symlinks are unavailable")
        with self.assertRaisesRegex(MotionRetargetBundleStoreError, "aliased"):
            MotionRetargetBundleStore(alias).publish(*self.values)
        alias.unlink()

        store = self.store("file-alias")
        published = store.publish(*self.values)
        target = published.path / "instance.json"
        outside = self.root / "outside.json"
        outside.write_bytes(target.read_bytes())
        target.unlink()
        try:
            target.symlink_to(outside)
        except OSError:
            self.skipTest("file symlinks are unavailable")
        with self.assertRaises(MotionRetargetBundleStoreError):
            store.publish(*self.values)
        self.assertEqual(self.contract.document_bytes["instance.json"], outside.read_bytes())

    def test_cross_project_and_failed_mesh_create_no_publication_state(self):
        cross = self.store("cross-project")
        wrong = deepcopy(self.values)
        wrong[0] = "other-project"
        with self.assertRaisesRegex(MotionRetargetBundleStoreError, "input is invalid"):
            cross.publish(*wrong)
        self.assertFalse((self.root / "cross-project").exists())

        failed = self.store("failed-mesh")
        wrong = deepcopy(self.values)
        wrong[-1]["status"] = "rejected"
        with self.assertRaisesRegex(MotionRetargetBundleStoreError, "input is invalid"):
            failed.publish(*wrong)
        self.assertFalse((self.root / "failed-mesh").exists())

    def test_write_failure_cleans_staging_and_does_not_publish(self):
        store = self.store("write-failure")
        with patch(
            "autospine_workbench.motion_retarget_bundle_store._write_file",
            side_effect=OSError("synthetic write failure"),
        ):
            with self.assertRaisesRegex(MotionRetargetBundleStoreError, "atomically"):
                store.publish(*self.values)
        parent = (
            self.root / "write-failure" / "builds" /
            self.contract.project_id / "motion-instances" /
            self.contract.instance_sha256
        )
        self.assertTrue(parent.is_dir())
        self.assertEqual([], list(parent.iterdir()))

    def test_conflicting_address_is_never_overwritten(self):
        store = self.store("conflict")
        parent = (
            self.root / "conflict" / "builds" / self.contract.project_id /
            "motion-instances" / self.contract.instance_sha256
        )
        conflict = parent / self.contract.bundle_sha256
        conflict.mkdir(parents=True)
        marker = conflict / "owner.txt"
        marker.write_text("foreign", encoding="utf-8")
        with self.assertRaises(MotionRetargetBundleStoreError):
            store.publish(*self.values)
        self.assertEqual("foreign", marker.read_text(encoding="utf-8"))

    def test_staging_cleanup_refuses_wrong_parent_name_alias_and_escape(self):
        parent = self.root / "safe-parent"
        parent.mkdir()
        ordinary = parent / "ordinary"
        ordinary.mkdir()
        _remove_staging(ordinary, parent)
        self.assertTrue(ordinary.exists())

        outside = self.root / ".123456789abc.escape"
        outside.mkdir()
        _remove_staging(outside, parent)
        self.assertTrue(outside.exists())

        escaped = parent / ".123456789abc.escape"
        escaped.mkdir()
        elsewhere = self.root / "elsewhere"
        elsewhere.mkdir()
        with patch.object(
            Path, "resolve",
            side_effect=(parent.resolve(strict=True), elsewhere.resolve(strict=True)),
        ):
            _remove_staging(escaped, parent)
        self.assertTrue(escaped.exists())

        target = parent / "target"
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
