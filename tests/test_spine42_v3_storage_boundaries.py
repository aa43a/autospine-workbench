"""Negative filesystem and mutable-head boundaries for P10.7a storage."""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for item in (ROOT, SRC):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

import autospine_workbench.spine42_v3_bundle_store as store_module  # noqa: E402
from autospine_workbench.spine42_v3_bundle_files import (  # noqa: E402
    NAMESPACE,
    Spine42V3BundleFilesError,
    read_bundle_files,
)
from autospine_workbench.spine42_v3_bundle_integrity import (  # noqa: E402
    Spine42V3BundleIntegrityError,
    Spine42V3BundleSnapshot,
    replay_verified_spine42_v3_bundle,
    verify_spine42_v3_bundle_snapshot,
)
from autospine_workbench.spine42_v3_bundle_reader import (  # noqa: E402
    VerifiedSpine42V3BundleReader,
    VerifiedSpine42V3BundleReaderError,
)
from autospine_workbench.spine42_v3_bundle_store import (  # noqa: E402
    Spine42V3BundleStore,
    Spine42V3BundleStoreError,
)
from autospine_workbench.spine42_v3_pipeline import (  # noqa: E402
    VerifiedSpine42V3Pipeline,
)
from tests.spine42_v3_storage_helpers import (  # noqa: E402
    Spine42V3StorageFixture,
)


class Spine42V3StorageBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.fixture = Spine42V3StorageFixture(Path(cls.temporary.name))

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    @staticmethod
    def _compile(fixture):
        source = fixture.published_v3
        with fixture.replay_gate():
            return VerifiedSpine42V3Pipeline(fixture.state_root).build(
                fixture.project_id,
                source.motion_instance_v3_sha256,
                source.bundle_sha256,
            )

    @staticmethod
    def _publish(fixture, *, observations=None):
        source = fixture.published_v3
        with fixture.compile_gate(observations=observations):
            return Spine42V3BundleStore(fixture.state_root).publish(
                fixture.project_id,
                source.motion_instance_v3_sha256,
                source.bundle_sha256,
            )

    def test_store_head_drift_fails_before_publication(self):
        observed = self.fixture.observation
        drifted = SimpleNamespace(
            identity=observed.identity,
            canonical_bytes=observed.canonical_bytes + b"drift",
        )
        namespace = (
            self.fixture.state_root / "builds" / self.fixture.project_id
            / NAMESPACE
        )
        before = _tree_snapshot(namespace)
        with self.assertRaises(Spine42V3BundleStoreError):
            self._publish(self.fixture, observations=(observed, drifted))
        self.assertEqual(before, _tree_snapshot(namespace))

    def test_pure_replay_rejects_forged_exposed_identity(self):
        published = self._publish(self.fixture)
        verified = verify_spine42_v3_bundle_snapshot(
            Spine42V3BundleSnapshot(
                published.path, read_bundle_files(published.path)
            ),
            expected_project_id=self.fixture.project_id,
            expected_skeleton_json_sha256=published.skeleton_json_sha256,
            expected_bundle_sha256=published.bundle_sha256,
        )
        self.assertEqual(
            published.bundle_sha256,
            replay_verified_spine42_v3_bundle(verified).bundle_sha256,
        )
        with self.assertRaises(Spine42V3BundleIntegrityError):
            replay_verified_spine42_v3_bundle(replace(
                verified, p3_rig_sha256="f" * 64
            ))

    def test_copied_snapshot_tamper_extra_and_wrong_case_fail_closed(self):
        published = self._publish(self.fixture)
        documents = {
            path.name: path.read_bytes() for path in published.path.iterdir()
        }
        with tempfile.TemporaryDirectory() as temporary:
            copy = Path(temporary)
            for name, data in documents.items():
                (copy / name).write_bytes(data)
            target = copy / "run-manifest.json"
            target.write_bytes(target.read_bytes() + b" ")
            with self.assertRaises(Spine42V3BundleIntegrityError):
                verify_spine42_v3_bundle_snapshot(
                    Spine42V3BundleSnapshot(copy, read_bundle_files(copy)),
                    expected_project_id=self.fixture.project_id,
                    expected_skeleton_json_sha256=
                        published.skeleton_json_sha256,
                    expected_bundle_sha256=published.bundle_sha256,
                    require_address_path=False,
                )
            target.write_bytes(documents[target.name])
            (copy / "extra.json").write_bytes(b"{}")
            with self.assertRaises(Spine42V3BundleFilesError):
                read_bundle_files(copy)
            (copy / "extra.json").unlink()
            atlas = copy / "skeleton.atlas"
            atlas.rename(copy / "Skeleton.atlas")
            with self.assertRaises(Spine42V3BundleFilesError):
                read_bundle_files(copy)

    def test_partial_write_is_cleaned_without_publishing_a_bundle(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Spine42V3StorageFixture(Path(temporary))
            compiled = self._compile(fixture)
            real_write = store_module.write_file
            calls = 0

            def fail_second(path, data):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise Spine42V3BundleFilesError("injected partial write")
                real_write(path, data)

            with patch.object(
                store_module, "write_file", side_effect=fail_second
            ), self.assertRaises(Spine42V3BundleStoreError):
                self._publish(fixture)
            parent = (
                fixture.state_root / "builds" / fixture.project_id
                / NAMESPACE / compiled.skeleton_json_sha256
            )
            self.assertTrue(parent.is_dir())
            self.assertEqual([], list(parent.iterdir()))

    def test_parent_sync_failure_never_returns_success(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Spine42V3StorageFixture(Path(temporary))
            compiled = self._compile(fixture)
            with patch.object(
                store_module, "sync_directory",
                side_effect=(None, OSError("injected parent sync failure")),
            ) as sync, self.assertRaises(Spine42V3BundleStoreError):
                self._publish(fixture)
            self.assertEqual(2, sync.call_count)
            destination = (
                fixture.state_root / "builds" / fixture.project_id
                / NAMESPACE / compiled.skeleton_json_sha256
                / compiled.bundle_sha256
            )
            self.assertTrue(destination.is_dir())
            run = json.loads((destination / "run-manifest.json").read_bytes())
            self.assertFalse(run["authority"]["release_authority"])
            self.assertEqual("blocked", run["release_gate"]["status"])

    def test_postpublish_head_drift_leaves_only_non_authoritative_cache(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Spine42V3StorageFixture(Path(temporary))
            compiled = self._compile(fixture)
            observed = fixture.observation
            drifted = SimpleNamespace(
                identity=observed.identity,
                canonical_bytes=observed.canonical_bytes + b"drift",
            )
            with self.assertRaises(Spine42V3BundleStoreError):
                self._publish(
                    fixture, observations=(observed, observed, drifted)
                )
            destination = (
                fixture.state_root / "builds" / fixture.project_id
                / NAMESPACE / compiled.skeleton_json_sha256
                / compiled.bundle_sha256
            )
            self.assertTrue(destination.is_dir())
            report = json.loads(
                (destination / "export-report.json").read_bytes()
            )
            self.assertFalse(report["authority"]["release_authority"])
            self.assertEqual("blocked", report["release_gate"]["status"])

    def test_reader_rejects_path_traversal_without_fallback(self):
        published = self._publish(self.fixture)
        with self.fixture.replay_gate(), self.assertRaises(
            VerifiedSpine42V3BundleReaderError
        ):
            VerifiedSpine42V3BundleReader(self.fixture.state_root).load(
                "../escape",
                published.skeleton_json_sha256,
                published.bundle_sha256,
            )
        self.assertFalse((self.fixture.root / "escape").exists())


def _tree_snapshot(root: Path) -> tuple[tuple[str, bool, bytes], ...]:
    if not root.exists():
        return ()
    return tuple(
        (
            path.relative_to(root).as_posix(),
            path.is_dir(),
            b"" if path.is_dir() else path.read_bytes(),
        )
        for path in sorted(root.rglob("*"))
    )


if __name__ == "__main__":
    unittest.main()
