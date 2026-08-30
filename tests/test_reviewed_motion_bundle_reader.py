"""Secure exact-reader tests for ReviewedMotionBundle v1."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import os
import stat
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import autospine_workbench.reviewed_motion_bundle_files as files_module  # noqa: E402
import autospine_workbench.reviewed_motion_bundle_integrity as integrity_module  # noqa: E402
from autospine_workbench.reviewed_motion_bundle_contract import (  # noqa: E402
    DOCUMENT_NAMES,
)
from autospine_workbench.reviewed_motion_bundle_reader import (  # noqa: E402
    VerifiedReviewedMotionBundleReader,
    VerifiedReviewedMotionBundleReaderError,
)
from autospine_workbench.reviewed_motion_bundle_integrity import (  # noqa: E402
    ReviewedMotionBundleIntegrityError,
    ReviewedMotionBundleSnapshot,
    replay_verified_reviewed_motion_bundle,
    verify_reviewed_motion_bundle_snapshot,
)
from tests.reviewed_motion_bundle_helpers import (  # noqa: E402
    ReviewedMotionStorageFixture,
)


class ReviewedMotionBundleReaderTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.fixture = ReviewedMotionStorageFixture(Path(temporary.name))
        self.published = self.fixture.publish()
        self.reader = VerifiedReviewedMotionBundleReader(
            self.fixture.state_root
        )

    def load(self, **kwargs):
        contract = self.fixture.contract
        defaults = {
            "mesh_bundle": self.fixture.mesh,
            "retarget_bundle": self.fixture.retarget,
        }
        defaults.update(kwargs)
        return self.reader.load(
            contract.project_id,
            contract.motion_instance_v2_sha256,
            contract.bundle_sha256,
            **defaults,
        )

    def test_reads_fixed_six_file_inventory_once_in_contract_order(self):
        with patch(
            "autospine_workbench.reviewed_motion_bundle_files.read_real_file",
            wraps=files_module.read_real_file,
        ) as read:
            verified = self.load()
        self.assertEqual(DOCUMENT_NAMES, verified.inventory)
        self.assertEqual(list(DOCUMENT_NAMES), [
            call.args[2] for call in read.call_args_list
        ])
        self.assertEqual(6, read.call_count)
        isolated = verified.document_bytes
        isolated[DOCUMENT_NAMES[0]] = b"changed"
        self.assertNotEqual(isolated, verified.document_bytes)

    def test_public_replay_rebuilds_exact_contract_and_rejects_spoof(self):
        verified = self.load()
        replayed = replay_verified_reviewed_motion_bundle(
            verified, self.fixture.mesh, self.fixture.retarget
        )
        self.assertEqual(self.fixture.contract, replayed)
        spoofed = replace(verified, bundle_sha256="f" * 64)
        with self.assertRaisesRegex(
            ReviewedMotionBundleIntegrityError, "differs from its P9 replay"
        ):
            replay_verified_reviewed_motion_bundle(
                spoofed, self.fixture.mesh, self.fixture.retarget
            )

    def test_reader_performs_zero_writes_and_has_no_latest_fallback(self):
        before = sorted(
            path.relative_to(self.fixture.state_root).as_posix()
            for path in self.fixture.state_root.rglob("*")
        )
        self.load()
        after = sorted(
            path.relative_to(self.fixture.state_root).as_posix()
            for path in self.fixture.state_root.rglob("*")
        )
        self.assertEqual(before, after)
        contract = self.fixture.contract
        with self.assertRaises(VerifiedReviewedMotionBundleReaderError):
            self.reader.load(
                contract.project_id,
                "0" * 64,
                contract.bundle_sha256,
                mesh_bundle=self.fixture.mesh,
                retarget_bundle=self.fixture.retarget,
            )
        self.assertEqual(before, sorted(
            path.relative_to(self.fixture.state_root).as_posix()
            for path in self.fixture.state_root.rglob("*")
        ))

    def test_every_document_tamper_fails_closed(self):
        for name in DOCUMENT_NAMES:
            with self.subTest(name=name):
                path = self.published.path / name
                original = path.read_bytes()
                path.write_bytes(original + b"\n")
                try:
                    with self.assertRaises(
                        VerifiedReviewedMotionBundleReaderError
                    ):
                        self.load()
                finally:
                    path.write_bytes(original)

    def test_missing_extra_wrong_case_and_symlink_are_rejected(self):
        extra = self.published.path / "latest.json"
        extra.write_bytes(b"{}")
        with self.assertRaisesRegex(
            VerifiedReviewedMotionBundleReaderError, "extra"
        ):
            self.load()
        extra.unlink()

        target = self.published.path / DOCUMENT_NAMES[0]
        original = target.read_bytes()
        target.unlink()
        try:
            with self.assertRaisesRegex(
                VerifiedReviewedMotionBundleReaderError, "missing"
            ):
                self.load()
        finally:
            target.write_bytes(original)

        temporary = self.published.path / "temporary-name"
        wrong_case = self.published.path / DOCUMENT_NAMES[0].upper()
        target.rename(temporary)
        temporary.rename(wrong_case)
        try:
            with self.assertRaisesRegex(
                VerifiedReviewedMotionBundleReaderError, "wrong-case"
            ):
                self.load()
        finally:
            wrong_case.rename(temporary)
            temporary.rename(target)

        link = self.published.path / "alias.json"
        try:
            os.symlink(target, link)
        except (NotImplementedError, OSError):
            pass
        else:
            try:
                with self.assertRaisesRegex(
                    VerifiedReviewedMotionBundleReaderError, "alias"
                ):
                    self.load()
            finally:
                link.unlink()

    def test_junction_and_reparse_detection_is_fail_closed(self):
        fake = Mock()
        fake.lstat.return_value = Mock(
            st_mode=stat.S_IFREG,
            st_file_attributes=getattr(
                stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400
            ),
        )
        fake.is_junction.return_value = False
        self.assertTrue(files_module.is_alias(fake))
        fake.lstat.return_value.st_file_attributes = 0
        fake.is_junction.return_value = True
        self.assertTrue(files_module.is_alias(fake))

    def test_per_file_limit_stops_before_semantic_rebuild(self):
        limits = list(files_module.DOCUMENT_LIMITS)
        limits[0] = len(
            self.fixture.contract.document_bytes[DOCUMENT_NAMES[0]]
        ) - 1
        with patch.object(files_module, "DOCUMENT_LIMITS", tuple(limits)), patch(
            "autospine_workbench.reviewed_motion_bundle_reader."
            "verify_reviewed_motion_bundle_snapshot"
        ) as verify, self.assertRaisesRegex(
            VerifiedReviewedMotionBundleReaderError, "unsafe"
        ):
            self.load()
        verify.assert_not_called()

    def test_pure_snapshot_boundary_rechecks_limits_before_json(self):
        items = tuple(self.fixture.contract.document_bytes.items())
        limits = list(integrity_module.DOCUMENT_LIMITS)
        limits[0] = len(items[0][1]) - 1
        snapshot = ReviewedMotionBundleSnapshot(self.published.path, items)
        with patch.object(
            integrity_module, "DOCUMENT_LIMITS", tuple(limits)
        ), patch.object(
            integrity_module, "strict_json_object"
        ) as decode, self.assertRaisesRegex(
            ReviewedMotionBundleIntegrityError, "snapshot byte limit"
        ):
            verify_reviewed_motion_bundle_snapshot(
                snapshot,
                expected_project_id=self.fixture.contract.project_id,
                expected_motion_instance_v2_sha256=(
                    self.fixture.contract.motion_instance_v2_sha256
                ),
                expected_bundle_sha256=self.fixture.contract.bundle_sha256,
                mesh_bundle=self.fixture.mesh,
                retarget_bundle=self.fixture.retarget,
            )
        decode.assert_not_called()
        total = sum(len(data) for _name, data in items)
        with patch.object(
            integrity_module, "MAX_TOTAL_DOCUMENT_BYTES", total - 1
        ), patch.object(
            integrity_module, "strict_json_object"
        ) as decode, self.assertRaisesRegex(
            ReviewedMotionBundleIntegrityError, "total byte limit"
        ):
            verify_reviewed_motion_bundle_snapshot(
                snapshot,
                expected_project_id=self.fixture.contract.project_id,
                expected_motion_instance_v2_sha256=(
                    self.fixture.contract.motion_instance_v2_sha256
                ),
                expected_bundle_sha256=self.fixture.contract.bundle_sha256,
                mesh_bundle=self.fixture.mesh,
                retarget_bundle=self.fixture.retarget,
            )
        decode.assert_not_called()

    def test_reader_enforces_state_root_containment_before_snapshot(self):
        with patch(
            "autospine_workbench.reviewed_motion_bundle_files._require_within",
            side_effect=files_module.ReviewedMotionBundleFilesError(
                "escaped state root"
            ),
        ), patch(
            "autospine_workbench.reviewed_motion_bundle_reader.read_bundle_files"
        ) as read, self.assertRaisesRegex(
            VerifiedReviewedMotionBundleReaderError, "escaped state root"
        ):
            self.load()
        read.assert_not_called()

    def test_toctou_metadata_change_is_rejected_before_integrity(self):
        real_fstat = os.fstat
        count = 0

        def changing_fstat(descriptor):
            nonlocal count
            count += 1
            value = real_fstat(descriptor)
            if count != 2:
                return value
            return SimpleNamespace(
                st_mode=value.st_mode,
                st_size=value.st_size,
                st_mtime_ns=value.st_mtime_ns + 1,
                st_dev=value.st_dev,
                st_ino=value.st_ino,
            )

        with patch(
            "autospine_workbench.safe_input_files.os.fstat",
            side_effect=changing_fstat,
        ), patch(
            "autospine_workbench.reviewed_motion_bundle_reader."
            "verify_reviewed_motion_bundle_snapshot"
        ) as verify, self.assertRaisesRegex(
            VerifiedReviewedMotionBundleReaderError, "unsafe"
        ):
            self.load()
        verify.assert_not_called()

    def test_auto_resolves_exact_p3_p5_addresses_from_run(self):
        contract = self.fixture.contract
        run = contract.document_bytes["run-manifest.json"]
        import json
        inputs = json.loads(run)["inputs"]
        with patch(
            "autospine_workbench.reviewed_motion_bundle_reader."
            "VerifiedMeshBundleReader"
        ) as mesh_reader, patch(
            "autospine_workbench.reviewed_motion_bundle_reader."
            "VerifiedMotionRetargetBundleReader"
        ) as p5_reader:
            mesh_reader.return_value.load.return_value = self.fixture.mesh
            p5_reader.return_value.load.return_value = self.fixture.retarget
            verified = self.reader.load(
                contract.project_id,
                contract.motion_instance_v2_sha256,
                contract.bundle_sha256,
            )
        mesh_reader.return_value.load.assert_called_once_with(
            contract.project_id,
            inputs["p3"]["rig_sha256"],
            inputs["p3"]["bundle_sha256"],
        )
        p5_reader.return_value.load.assert_called_once_with(
            contract.project_id,
            inputs["p5"]["instance_sha256"],
            inputs["p5"]["bundle_sha256"],
            mesh_bundle=self.fixture.mesh,
        )
        self.assertEqual(contract.bundle_sha256, verified.bundle_sha256)

    def test_tampered_run_is_not_used_to_resolve_upstreams(self):
        path = self.published.path / "run-manifest.json"
        path.write_bytes(path.read_bytes() + b"\n")
        with patch(
            "autospine_workbench.reviewed_motion_bundle_reader."
            "VerifiedMeshBundleReader"
        ) as mesh_reader, patch(
            "autospine_workbench.reviewed_motion_bundle_reader."
            "VerifiedMotionRetargetBundleReader"
        ) as p5_reader, self.assertRaisesRegex(
            VerifiedReviewedMotionBundleReaderError, "explicit address"
        ):
            contract = self.fixture.contract
            self.reader.load(
                contract.project_id,
                contract.motion_instance_v2_sha256,
                contract.bundle_sha256,
            )
        mesh_reader.assert_not_called()
        p5_reader.assert_not_called()

    def test_partial_or_spoofed_upstream_is_rejected(self):
        with self.assertRaisesRegex(
            VerifiedReviewedMotionBundleReaderError, "Both exact"
        ):
            self.load(retarget_bundle=None)
        spoofed = replace(
            self.fixture.retarget, bundle_sha256="f" * 64
        )
        with self.assertRaises(VerifiedReviewedMotionBundleReaderError):
            self.load(retarget_bundle=spoofed)


if __name__ == "__main__":
    unittest.main()
