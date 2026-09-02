from __future__ import annotations

from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
for item in (ROOT, ROOT / "src"):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from autospine_workbench.body_sway_dynamic_seam_evidence_profile_v2 import (
    CERTIFIED_STATUS,
)
from autospine_workbench.p10_motion_instance_v3_auto_inputs_v2 import (
    P10MotionInstanceV3AutoInputsV2Error,
    resolve_p10_motion_instance_v3_auto_inputs_v2,
)


MODULE = "autospine_workbench.p10_motion_instance_v3_auto_inputs_v2."


class MotionInstanceV3AutoInputsV2Tests(unittest.TestCase):
    def test_completed_url_bound_run_supplies_project_and_both_hashes(self):
        store = SimpleNamespace(load=lambda _run: _row())
        with patch(MODULE + "P10DynamicSeamJobStoreV2",
                   return_value=store):
            value = resolve_p10_motion_instance_v3_auto_inputs_v2(
                "state", "1" * 64, "2" * 64, "3" * 64,
            )
        self.assertEqual("project-a", value.project_id)
        self.assertEqual("4" * 64, value.dynamic_seam_probe_sha256)
        self.assertEqual("5" * 64, value.dynamic_seam_bundle_sha256)
        self.assertEqual("3" * 64, value.dynamic_run_id)

    def test_crosswire_incomplete_and_uncertified_fail_closed(self):
        attacks = (
            _row(job_id="9" * 64),
            _row(status="running"),
            _row(probe_status="indeterminate"),
            _row(project_result="project-b"),
        )
        for row in attacks:
            store = SimpleNamespace(load=lambda _run, row=row: row)
            with self.subTest(status=row.status), patch(
                MODULE + "P10DynamicSeamJobStoreV2", return_value=store,
            ), self.assertRaises(P10MotionInstanceV3AutoInputsV2Error):
                resolve_p10_motion_instance_v3_auto_inputs_v2(
                    "state", "1" * 64, "2" * 64, "3" * 64,
                )


def _row(*, job_id=None, status="completed", probe_status=None,
         project_result="project-a"):
    request = {
        "job_id": job_id or "1" * 64, "safety_run_id": "2" * 64,
        "project_id": "project-a",
    }
    result = {
        "project_id": project_result, "probe_sha256": "4" * 64,
        "bundle_sha256": "5" * 64,
        "probe_status": probe_status or CERTIFIED_STATUS,
    }
    return SimpleNamespace(
        request=request, status=status, events=({"result": result},),
    )


if __name__ == "__main__":
    unittest.main()
