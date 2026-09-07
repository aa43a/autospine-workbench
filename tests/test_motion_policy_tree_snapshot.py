"""Byte snapshots remain strict alongside Windows manager owner locks."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests.motion_policy_preflight_helpers import tree_snapshot
from autospine_workbench.p10_spine42_v3_runtime_manager_owner_lease_v2 import (
    LOCK_NAMESPACE, P10Spine42V3RuntimeManagerOwnerLeaseV2,
)


class MotionPolicyTreeSnapshotTests(unittest.TestCase):
    def test_live_owner_lock_is_stable_and_creation_deletion_are_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            before = tree_snapshot(root)
            with P10Spine42V3RuntimeManagerOwnerLeaseV2(root):
                locked = tree_snapshot(root)
                self.assertNotEqual(before, locked)
                self.assertEqual(locked, tree_snapshot(root))
            self.assertEqual(locked, tree_snapshot(root))
            (root / "jobs" / LOCK_NAMESPACE / "owner.lock").unlink()
            self.assertNotEqual(locked, tree_snapshot(root))

    def test_owner_lock_replacement_and_writes_are_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "jobs" / LOCK_NAMESPACE / "owner.lock"
            path.parent.mkdir(parents=True)
            path.write_bytes(b"\0")
            before = tree_snapshot(root)
            # Build the replacement before deleting the original so the
            # filesystem cannot reuse its identity.
            replacement = root / "replacement"
            replacement.write_bytes(b"\0")
            replacement.replace(path)
            replaced = tree_snapshot(root)
            self.assertNotEqual(before, replaced)
            path.write_bytes(b"changed")
            self.assertNotEqual(replaced, tree_snapshot(root))

    def test_other_unreadable_files_are_not_ignored(self):
        for relative in (
            "artifact.json", "owner.lock", "jobs/other/owner.lock",
            f"jobs/{LOCK_NAMESPACE}/OWNER.lock",
        ):
            with self.subTest(relative=relative), \
                    tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"evidence")
                with patch.object(Path, "read_bytes", side_effect=PermissionError):
                    with self.assertRaises(PermissionError):
                        tree_snapshot(root)
