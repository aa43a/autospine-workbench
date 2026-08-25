"""Filesystem boundary tests for exact P5 retarget bundles."""

from __future__ import annotations

import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import autospine_workbench.motion_retarget_bundle_reader as reader_module  # noqa: E402
from autospine_workbench.motion_retarget_bundle_reader import (  # noqa: E402
    VerifiedMotionRetargetBundleReader,
    VerifiedMotionRetargetBundleReaderError,
)
from tests.test_motion_retarget_bundle_integrity import (  # noqa: E402
    RetargetBundleFixture,
)


class MotionRetargetBundleReaderTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.fixture = RetargetBundleFixture(Path(self.temporary.name))
        self.reader = VerifiedMotionRetargetBundleReader(
            self.fixture.pipeline.state
        )

    def load(self):
        contract = self.fixture.contract
        return self.reader.load(
            contract.project_id, contract.instance_sha256,
            contract.bundle_sha256,
        )

    def test_exact_bundle_reads_five_files_once_in_contract_order(self):
        with self.fixture.patched_pipeline(), patch(
            "autospine_workbench.motion_retarget_bundle_reader._read_snapshot",
            wraps=reader_module._read_snapshot,
        ) as read:
            verified = self.load()
        self.assertEqual(self.fixture.contract.inventory, verified.inventory)
        self.assertEqual(
            list(self.fixture.contract.inventory),
            [call.args[2] for call in read.call_args_list],
        )
        self.assertEqual(5, read.call_count)

    def test_invalid_missing_extra_and_case_mismatched_paths_fail(self):
        contract = self.fixture.contract
        with self.assertRaises(VerifiedMotionRetargetBundleReaderError):
            self.reader.load("../bad", contract.instance_sha256,
                             contract.bundle_sha256)
        extra = self.fixture.directory / "latest.json"
        extra.write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(
            VerifiedMotionRetargetBundleReaderError, "unexpected"
        ):
            self.load()
        extra.unlink()
        missing = self.fixture.directory / contract.inventory[0]
        missing.unlink()
        with self.assertRaisesRegex(
            VerifiedMotionRetargetBundleReaderError, "missing"
        ):
            self.load()

        other = RetargetBundleFixture(Path(self.temporary.name) / "case")
        project_path = other.pipeline.state / "builds" / other.contract.project_id
        wrong = project_path.with_name(other.contract.project_id.upper())
        project_path.rename(wrong)
        exact_reader = VerifiedMotionRetargetBundleReader(other.pipeline.state)
        with self.assertRaisesRegex(
            VerifiedMotionRetargetBundleReaderError, "case-mismatched"
        ):
            exact_reader.load(
                other.contract.project_id, other.contract.instance_sha256,
                other.contract.bundle_sha256,
            )

    def test_symlink_reparse_and_alias_root_are_rejected(self):
        link = self.fixture.directory / "alias.json"
        try:
            os.symlink(self.fixture.directory / "instance.json", link)
        except (NotImplementedError, OSError):
            pass
        else:
            with self.assertRaisesRegex(
                VerifiedMotionRetargetBundleReaderError, "alias"
            ):
                self.load()

        fake = Mock()
        fake.lstat.return_value = Mock(
            st_mode=stat.S_IFREG,
            st_file_attributes=getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400),
        )
        fake.is_junction.return_value = False
        self.assertTrue(reader_module._is_alias(fake))
        fake.lstat.return_value.st_file_attributes = 0
        fake.is_junction.return_value = True
        self.assertTrue(reader_module._is_alias(fake))
        with patch(
            "autospine_workbench.motion_retarget_bundle_reader._is_alias",
            side_effect=lambda path: path == self.fixture.pipeline.state,
        ), self.assertRaisesRegex(
            VerifiedMotionRetargetBundleReaderError, "state root is aliased"
        ):
            self.load()

    def test_resource_limit_is_enforced_before_integrity_pipeline(self):
        limits = list(reader_module._LIMITS)
        limits[0] = len(
            self.fixture.contract.document_bytes["target-profile.json"]
        ) - 1
        with self.fixture.patched_pipeline() as pipeline, patch.object(
            reader_module, "_LIMITS", tuple(limits)
        ), self.assertRaisesRegex(
            VerifiedMotionRetargetBundleReaderError, "byte limit"
        ):
            self.load()
        pipeline.return_value.build.assert_not_called()

    def test_noncanonical_and_pipeline_failure_are_wrapped(self):
        target = self.fixture.directory / "target-profile.json"
        target.write_bytes(target.read_bytes() + b"\n")
        with self.fixture.patched_pipeline() as pipeline, self.assertRaises(
            VerifiedMotionRetargetBundleReaderError
        ):
            self.load()
        pipeline.return_value.build.assert_not_called()

        fresh = RetargetBundleFixture(Path(self.temporary.name) / "failure")
        exact_reader = VerifiedMotionRetargetBundleReader(fresh.pipeline.state)
        with fresh.patched_pipeline() as pipeline:
            pipeline.return_value.build.side_effect = RuntimeError("upstream tamper")
            with self.assertRaisesRegex(
                VerifiedMotionRetargetBundleReaderError, "upstream tamper"
            ):
                exact_reader.load(
                    fresh.contract.project_id, fresh.contract.instance_sha256,
                    fresh.contract.bundle_sha256,
                )


if __name__ == "__main__":
    unittest.main()
