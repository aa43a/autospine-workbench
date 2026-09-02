from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
for item in (ROOT, ROOT / "src"):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from autospine_workbench.motion_instance_v3_bundle_contract_v2 import (
    DOCUMENT_NAMES,
)
from autospine_workbench.motion_instance_v3_bundle_run_v2 import AUTHORITY
from autospine_workbench.p10_motion_instance_v3_result_v2 import (
    P10MotionInstanceV3ResultV2Error,
    read_p10_motion_instance_v3_result_v2,
)
from tests.motion_instance_v3_bundle_v2_helpers import (
    MotionInstanceV3BundleV2Fixture,
)


class MotionInstanceV3ResultV2Tests(unittest.TestCase):
    def test_result_exactly_replays_disk_and_projects_blocked_authority(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = MotionInstanceV3BundleV2Fixture(Path(temporary))
            published = fixture.publish()
            row = _row(fixture, published)
            with fixture.historical_replay(), _reviewed(fixture):
                value = read_p10_motion_instance_v3_result_v2(
                    fixture.state_root, row,
                )
        self.assertEqual("passed", value["verification"]["status"])
        self.assertEqual(AUTHORITY, value["authority"])
        self.assertEqual("blocked", value["release_gate"]["status"])
        self.assertFalse(value["release_authority_granted"])
        self.assertNotIn("path", repr(value).lower())

    def test_real_bundle_file_tamper_makes_result_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = MotionInstanceV3BundleV2Fixture(Path(temporary))
            published = fixture.publish()
            row = _row(fixture, published)
            target = published.path / DOCUMENT_NAMES[1]
            target.write_bytes(target.read_bytes() + b"\n")
            with fixture.historical_replay(), _reviewed(fixture), \
                    self.assertRaises(
                P10MotionInstanceV3ResultV2Error,
            ):
                read_p10_motion_instance_v3_result_v2(
                    fixture.state_root, row,
                )

    def test_new_production_and_test_files_stay_within_limits(self):
        production = (
            "p10_motion_instance_v3_auto_inputs_v2.py",
            "p10_motion_instance_v3_job_contract_v2.py",
            "p10_motion_instance_v3_attempt_index_v2.py",
            "p10_motion_instance_v3_job_v2.py",
            "p10_motion_instance_v3_manager_v2.py",
            "p10_motion_instance_v3_result_v2.py",
            "p10_motion_instance_v3_v2_routes.py",
        )
        for name in production:
            lines = (ROOT / "src" / "autospine_workbench" / name).read_text(
                encoding="utf-8"
            ).splitlines()
            self.assertLessEqual(len(lines), 300, name)
        for path in ROOT.joinpath("tests").glob(
            "test_p10_motion_instance_v3_*v2.py"
        ):
            self.assertLessEqual(
                len(path.read_text(encoding="utf-8").splitlines()), 400,
                path.name,
            )


class _Row:
    def __init__(self, fixture, published):
        self.request = {
            "job_id": "1" * 64, "safety_run_id": "2" * 64,
            "dynamic_run_id": "3" * 64,
            "project_id": fixture.contract.project_id,
        }
        self.run_id = "4" * 64
        self.events = ({"result": {
            "project_id": fixture.contract.project_id,
            "clip_id": fixture.contract.clip_id,
            "motion_instance_v3_sha256":
                published.motion_instance_v3_sha256,
            "bundle_sha256": published.bundle_sha256,
            "run_sha256": published.run_sha256,
            "inventory": list(DOCUMENT_NAMES), "reused": published.reused,
        }},)

    def public_document(self):
        return {"run_id": self.run_id, "status": "completed"}


def _row(fixture, published):
    return _Row(fixture, published)


def _reviewed(fixture):
    return patch(
        "autospine_workbench.motion_instance_v3_bundle_reader_v2."
        "VerifiedReviewedMotionBundleReader.load",
        return_value=fixture.reviewed,
    )


if __name__ == "__main__":
    unittest.main()
