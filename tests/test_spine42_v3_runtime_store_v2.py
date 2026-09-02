"""Atomic publication tests for P10.7b v2 runtime evidence."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
for item in (ROOT, ROOT / "src"):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

import autospine_workbench.spine42_v3_runtime_store_v2 as subject  # noqa: E402
from autospine_workbench.spine42_v3_runtime_evidence_v2 import (  # noqa: E402
    FIXED_NAMES, MANIFEST_NAME,
)
from autospine_workbench.spine42_v3_runtime_store_v2 import (  # noqa: E402
    Spine42V3RuntimeStoreV2, Spine42V3RuntimeStoreV2Error,
)
from tests.spine42_v3_runtime_storage_v2_helpers import (  # noqa: E402
    RuntimeStorageV2Fixture, publication_path,
)


class Spine42V3RuntimeStoreV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        cls.fixture = RuntimeStorageV2Fixture(cls.root / "fixture")

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_publish_reuse_exact_four_part_address_and_inventory(self):
        state = self.root / "publish"
        store = Spine42V3RuntimeStoreV2(state)
        snapshots = []
        real_snapshot = subject._snapshot_spine42_v3_runtime_bundle_v2

        def detached_snapshot(*args, **kwargs):
            bundle = real_snapshot(*args, **kwargs)
            snapshots.append(bundle)
            return bundle

        with patch.object(
            subject, "_snapshot_spine42_v3_runtime_bundle_v2",
            side_effect=detached_snapshot,
        ), self.fixture.profile():
            first = store.publish(self.fixture.evidence)
            second = store.publish(self.fixture.evidence)
        expected = publication_path(state, self.fixture.bundle)
        self.assertEqual(expected, first.path)
        self.assertFalse(first.reused)
        self.assertTrue(second.reused)
        self.assertTrue(snapshots)
        self.assertTrue(all(
            type(item) is type(self.fixture.bundle) for item in snapshots
        ))
        self.assertEqual(first.path, second.path)
        self.assertEqual(
            set(FIXED_NAMES) | {"captures"},
            {item.name for item in expected.iterdir()},
        )
        capture_names = {
            Path(name).name for name, _raw in self.fixture.bundle.file_items
            if name.startswith("captures/")
        }
        self.assertEqual(
            capture_names,
            {item.name for item in (expected / "captures").iterdir()},
        )

    def test_invalid_or_forged_input_creates_no_state(self):
        for index, value in enumerate(({}, replace(self.fixture.evidence))):
            state = self.root / f"invalid-{index}"
            with self.subTest(index=index), self.assertRaises(
                Spine42V3RuntimeStoreV2Error,
            ):
                Spine42V3RuntimeStoreV2(state).publish(value)
            self.assertFalse(state.exists())

    def test_concurrent_publishers_converge_without_overwrite(self):
        store = Spine42V3RuntimeStoreV2(self.root / "concurrent")
        with self.fixture.profile(), ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(
                lambda _index: store.publish(self.fixture.evidence), range(12),
            ))
        self.assertEqual(1, len({result.path for result in results}))
        self.assertEqual(1, sum(not result.reused for result in results))

    def test_corrupt_collision_is_never_reused_or_overwritten(self):
        state = self.root / "collision"
        store = Spine42V3RuntimeStoreV2(state)
        with self.fixture.profile():
            published = store.publish(self.fixture.evidence)
        manifest = published.path / MANIFEST_NAME
        corrupt = manifest.read_bytes() + b" "
        manifest.write_bytes(corrupt)
        with self.fixture.profile(), self.assertRaises(
            Spine42V3RuntimeStoreV2Error,
        ):
            store.publish(self.fixture.evidence)
        self.assertEqual(corrupt, manifest.read_bytes())

    def test_write_failure_removes_same_parent_staging(self):
        state = self.root / "write-failure"
        calls, real_write = 0, subject.write_file

        def fail_second(path, data):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("injected write failure")
            return real_write(path, data)

        with patch.object(subject, "write_file", side_effect=fail_second), \
                self.fixture.profile(), self.assertRaises(
                    Spine42V3RuntimeStoreV2Error,
                ):
            Spine42V3RuntimeStoreV2(state).publish(self.fixture.evidence)
        parent = publication_path(state, self.fixture.bundle).parent
        self.assertTrue(parent.is_dir())
        self.assertFalse(any(item.name.startswith(".") for item in parent.iterdir()))

    def test_parent_sync_failure_is_not_reported_as_success(self):
        state = self.root / "sync-failure"
        with patch.object(
            subject, "sync_directory",
            side_effect=(None, None, OSError("injected parent sync failure")),
        ) as sync, self.fixture.profile(), self.assertRaises(
            Spine42V3RuntimeStoreV2Error,
        ):
            Spine42V3RuntimeStoreV2(state).publish(self.fixture.evidence)
        self.assertEqual(3, sync.call_count)
        self.assertTrue(publication_path(state, self.fixture.bundle).is_dir())


if __name__ == "__main__":
    unittest.main()
