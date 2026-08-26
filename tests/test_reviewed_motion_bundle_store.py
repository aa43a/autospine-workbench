"""Atomic publication tests for ReviewedMotionBundle v1."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from autospine_workbench.reviewed_motion_bundle_store import (  # noqa: E402
    ReviewedMotionBundleStore,
    ReviewedMotionBundleStoreError,
)
from tests.reviewed_motion_bundle_helpers import (  # noqa: E402
    ReviewedMotionStorageFixture,
)


class ReviewedMotionBundleStoreTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.fixture = ReviewedMotionStorageFixture(Path(temporary.name))

    def test_publish_has_explicit_address_and_exact_reuse(self):
        first = self.fixture.publish()
        second = self.fixture.publish()
        contract = self.fixture.contract
        self.assertFalse(first.reused)
        self.assertTrue(second.reused)
        self.assertEqual(first.path, second.path)
        self.assertEqual(
            (
                contract.bundle_sha256,
                contract.motion_instance_v2_sha256,
                "reviewed-motion-instances",
                contract.project_id,
                "builds",
            ),
            (
                first.path.name,
                first.path.parent.name,
                first.path.parent.parent.name,
                first.path.parent.parent.parent.name,
                first.path.parent.parent.parent.parent.name,
            ),
        )
        self.assertEqual(
            contract.document_bytes,
            {path.name: path.read_bytes() for path in first.path.iterdir()},
        )

    def test_concurrent_publish_is_write_once_and_reuses_exact_bytes(self):
        with ThreadPoolExecutor(max_workers=4) as executor:
            published = list(executor.map(
                lambda _index: self.fixture.publish(), range(4)
            ))
        self.assertEqual(1, sum(not item.reused for item in published))
        self.assertEqual(3, sum(item.reused for item in published))
        self.assertEqual(1, len({item.path for item in published}))
        self.assertEqual(
            self.fixture.contract.document_bytes,
            {
                path.name: path.read_bytes()
                for path in published[0].path.iterdir()
            },
        )

    def test_invalid_input_makes_zero_writes(self):
        documents = list(deepcopy(self.fixture.documents))
        documents[4]["tracks"][0]["keys"][0]["value"] += 0.5
        store = ReviewedMotionBundleStore(self.fixture.state_root)
        with self.assertRaises(ReviewedMotionBundleStoreError):
            store.publish(
                self.fixture.mesh.project_id,
                *documents,
                self.fixture.mesh,
                self.fixture.retarget,
            )
        self.assertFalse(self.fixture.state_root.exists())

    def test_existing_tamper_is_never_overwritten_or_reused(self):
        published = self.fixture.publish()
        target = published.path / "reviewed-motion-policy.json"
        target.write_bytes(target.read_bytes() + b"\n")
        tampered = target.read_bytes()
        with self.assertRaises(ReviewedMotionBundleStoreError):
            self.fixture.publish()
        self.assertEqual(tampered, target.read_bytes())

    def test_failed_rename_cleans_only_its_staging_directory(self):
        with patch(
            "autospine_workbench.reviewed_motion_bundle_store.os.rename",
            side_effect=OSError("injected rename failure"),
        ), self.assertRaises(ReviewedMotionBundleStoreError):
            self.fixture.publish()
        contract = self.fixture.contract
        parent = (
            self.fixture.state_root / "builds" / contract.project_id
            / "reviewed-motion-instances"
            / contract.motion_instance_v2_sha256
        )
        self.assertTrue(parent.is_dir())
        self.assertEqual([], list(parent.iterdir()))


if __name__ == "__main__":
    unittest.main()
