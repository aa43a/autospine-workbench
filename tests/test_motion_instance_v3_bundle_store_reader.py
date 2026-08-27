"""Atomic store and exact-address reader tests for v3 bundles."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for item in (ROOT, SRC):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from autospine_workbench.motion_instance_v3_bundle_contract import (  # noqa: E402
    DOCUMENT_NAMES,
)
from autospine_workbench.motion_instance_v3_bundle_files import (  # noqa: E402
    NAMESPACE,
    MotionInstanceV3BundleFilesError,
)
from autospine_workbench.motion_instance_v3_bundle_integrity import (  # noqa: E402
    MotionInstanceV3BundleIntegrityError,
    replay_verified_motion_instance_v3_bundle,
)
from autospine_workbench.motion_instance_v3_bundle_reader import (  # noqa: E402
    VerifiedMotionInstanceV3BundleReader,
    VerifiedMotionInstanceV3BundleReaderError,
)
from autospine_workbench.motion_instance_v3_bundle_store import (  # noqa: E402
    MotionInstanceV3BundleStore,
    MotionInstanceV3BundleStoreError,
)
from tests.body_sway_motion_consumer_helpers import (  # noqa: E402
    patched_probe_replay,
)
from tests.motion_instance_v3_bundle_helpers import (  # noqa: E402
    MotionInstanceV3StorageFixture,
)


class MotionInstanceV3BundleStoreReaderTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.fixture = MotionInstanceV3StorageFixture(Path(temporary.name))
        self.reader = VerifiedMotionInstanceV3BundleReader(
            self.fixture.state_root
        )

    def load(self, *, reviewed=True):
        contract = self.fixture.contract
        kwargs = ({"reviewed_bundle": self.fixture.reviewed_bundle}
                  if reviewed else {})
        with patched_probe_replay(
            self.fixture.probe, self.fixture.identity
        ):
            return self.reader.load(
                contract.project_id,
                contract.motion_instance_v3_sha256,
                contract.bundle_sha256,
                **kwargs,
            )

    def test_publish_is_content_addressed_and_identical_reuse_is_idempotent(self):
        first = self.fixture.publish()
        second = self.fixture.publish()
        contract = self.fixture.contract
        self.assertFalse(first.reused)
        self.assertTrue(second.reused)
        self.assertEqual(first.path, second.path)
        self.assertEqual((
            contract.bundle_sha256,
            contract.motion_instance_v3_sha256,
            NAMESPACE,
            contract.project_id,
            "builds",
        ), (
            first.path.name,
            first.path.parent.name,
            first.path.parent.parent.name,
            first.path.parent.parent.parent.name,
            first.path.parent.parent.parent.parent.name,
        ))
        self.assertEqual(
            contract.document_bytes,
            {path.name: path.read_bytes() for path in first.path.iterdir()},
        )
        self.assertFalse((first.path.parent / "latest").exists())

    def test_reader_replays_all_bytes_and_never_observes_current_heads(self):
        self.fixture.publish()
        with patch(
            "autospine_workbench.body_sway_dynamic_seam_head_checks."
            "require_current_body_sway_dynamic_seam_heads",
            side_effect=AssertionError("current heads observed"),
        ):
            verified = self.load()
        self.assertEqual(DOCUMENT_NAMES, verified.inventory)
        self.assertEqual(self.fixture.contract.identities, verified.identities)
        with patched_probe_replay(
            self.fixture.probe, self.fixture.identity
        ):
            replayed = replay_verified_motion_instance_v3_bundle(
                verified, self.fixture.reviewed_bundle
            )
        self.assertEqual(self.fixture.contract, replayed)
        spoofed = replace(verified, bundle_sha256="f" * 64)
        with patched_probe_replay(
            self.fixture.probe, self.fixture.identity
        ), self.assertRaises(MotionInstanceV3BundleIntegrityError):
            replay_verified_motion_instance_v3_bundle(
                spoofed, self.fixture.reviewed_bundle
            )

    def test_every_document_tamper_and_extra_file_fail_closed(self):
        published = self.fixture.publish()
        for name in DOCUMENT_NAMES:
            with self.subTest(name=name):
                path = published.path / name
                original = path.read_bytes()
                path.write_bytes(original + b"\n")
                try:
                    with self.assertRaises(
                        VerifiedMotionInstanceV3BundleReaderError
                    ):
                        self.load()
                finally:
                    path.write_bytes(original)
        extra = published.path / "latest.json"
        extra.write_bytes(b"{}")
        with self.assertRaisesRegex(
            VerifiedMotionInstanceV3BundleReaderError, "extra"
        ):
            self.load()

    def test_path_traversal_and_wrong_explicit_address_never_fall_back(self):
        published = self.fixture.publish()
        store = MotionInstanceV3BundleStore(self.fixture.state_root)
        with patched_probe_replay(
            self.fixture.probe, self.fixture.identity
        ), self.assertRaises(MotionInstanceV3BundleStoreError):
            store.publish(
                "../escape",
                self.fixture.admission.document,
                self.fixture.motion_instance_v3.document,
                self.fixture.reviewed_bundle,
            )
        self.assertFalse((self.fixture.root / "escape").exists())

        contract = self.fixture.contract
        for project, primary, address in (
            ("../escape", contract.motion_instance_v3_sha256,
             contract.bundle_sha256),
            (contract.project_id, "0" * 64, contract.bundle_sha256),
            (contract.project_id, contract.motion_instance_v3_sha256,
             "0" * 64),
        ):
            with self.subTest(project=project, primary=primary), \
                    self.assertRaises(
                        VerifiedMotionInstanceV3BundleReaderError
                    ):
                self.reader.load(
                    project, primary, address,
                    reviewed_bundle=self.fixture.reviewed_bundle,
                )
        self.assertTrue(published.path.is_dir())

    def test_partial_write_cleans_staging_and_publishes_no_bundle(self):
        contract = self.fixture.contract
        store = MotionInstanceV3BundleStore(self.fixture.state_root)
        import autospine_workbench.motion_instance_v3_bundle_store as module

        real_write = module.write_file
        calls = 0

        def fail_second(path, data):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise MotionInstanceV3BundleFilesError("injected partial write")
            real_write(path, data)

        with patched_probe_replay(
            self.fixture.probe, self.fixture.identity
        ), patch.object(module, "write_file", side_effect=fail_second), \
                self.assertRaises(MotionInstanceV3BundleStoreError):
            store.publish(
                contract.project_id,
                self.fixture.admission.document,
                self.fixture.motion_instance_v3.document,
                self.fixture.reviewed_bundle,
            )
        parent = (
            self.fixture.state_root / "builds" / contract.project_id
            / NAMESPACE / contract.motion_instance_v3_sha256
        )
        self.assertTrue(parent.is_dir())
        self.assertEqual([], list(parent.iterdir()))

    def test_auto_resolves_exact_p9_only_after_run_and_address_validation(self):
        published = self.fixture.publish()
        contract = self.fixture.contract
        with patch(
            "autospine_workbench.motion_instance_v3_bundle_reader."
            "VerifiedReviewedMotionBundleReader"
        ) as p9_reader, patched_probe_replay(
            self.fixture.probe, self.fixture.identity
        ):
            p9_reader.return_value.load.return_value = (
                self.fixture.reviewed_bundle
            )
            verified = self.reader.load(
                contract.project_id,
                contract.motion_instance_v3_sha256,
                contract.bundle_sha256,
            )
        p9_reader.return_value.load.assert_called_once_with(
            contract.project_id,
            contract.motion_instance_v2_sha256,
            contract.reviewed_motion_bundle_sha256,
        )
        self.assertEqual(contract.bundle_sha256, verified.bundle_sha256)

        run_path = published.path / "run-manifest.json"
        run_path.write_bytes(run_path.read_bytes() + b"\n")
        with patch(
            "autospine_workbench.motion_instance_v3_bundle_reader."
            "VerifiedReviewedMotionBundleReader"
        ) as p9_reader, self.assertRaisesRegex(
            VerifiedMotionInstanceV3BundleReaderError, "explicit address"
        ):
            self.reader.load(
                contract.project_id,
                contract.motion_instance_v3_sha256,
                contract.bundle_sha256,
            )
        p9_reader.assert_not_called()


if __name__ == "__main__":
    unittest.main()
