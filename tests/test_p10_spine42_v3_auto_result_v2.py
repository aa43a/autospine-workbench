from __future__ import annotations

from pathlib import Path
import sys
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
for item in (ROOT, ROOT / "src"):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from autospine_workbench.p10_spine42_v3_auto_inputs_v2 import (
    P10Spine42V3AutoInputsV2Error,
    load_verified_p10_spine42_v3_motion_v2,
    resolve_p10_spine42_v3_auto_inputs_v2,
)
from autospine_workbench.motion_instance_v3_bundle_contract_v2 import (
    DOCUMENT_NAMES as MOTION_DOCUMENT_NAMES,
)
from autospine_workbench.p10_spine42_v3_job_contract_v2 import (
    DOCUMENT_NAMES as SPINE_DOCUMENT_NAMES,
)
from autospine_workbench.p10_spine42_v3_result_v2 import (
    P10Spine42V3ResultV2Error, read_p10_spine42_v3_result_v2,
)
from autospine_workbench.spine42_v3_export_evidence_v2 import (
    AUTHORITY, RELEASE_GATE,
)
from tests.spine42_v3_v2_helpers import Spine42V3V2Fixture

AUTO = "autospine_workbench.p10_spine42_v3_auto_inputs_v2."
RESULT = "autospine_workbench.p10_spine42_v3_result_v2."


class Spine42V3AutoInputsV2Tests(unittest.TestCase):
    def test_completed_receipt_is_selected_without_exact_bundle_replay(self):
        row = _row()
        with patch(AUTO + "P10MotionInstanceV3JobStoreV2") as store, \
                patch(AUTO + "MotionInstanceV3BundleReaderV2") as reader:
            store.return_value.load.return_value = row
            value = resolve_p10_spine42_v3_auto_inputs_v2("state", *_ids())
        self.assertEqual("project-a", value.project_id)
        self.assertEqual("5" * 64, value.motion_instance_v3_sha256)
        self.assertEqual("6" * 64, value.motion_instance_v3_bundle_sha256)
        reader.assert_not_called()

    def test_cross_wired_or_incomplete_motion_run_fails_closed(self):
        cross = _row()
        cross.request["dynamic_run_id"] = "9" * 64
        for row, code, terminal in (
            (cross, "invalid_upstream", True),
            (_row(status="running"), "source_not_ready", False),
        ):
            with self.subTest(code=code), patch(
                AUTO + "P10MotionInstanceV3JobStoreV2"
            ) as store:
                store.return_value.load.return_value = row
                with self.assertRaises(P10Spine42V3AutoInputsV2Error) as caught:
                    resolve_p10_spine42_v3_auto_inputs_v2("state", *_ids())
                self.assertEqual(code, caught.exception.failure_code)
                self.assertEqual(terminal, caught.exception.terminal)

    def test_invalid_sealed_receipt_fails_before_bundle_read(self):
        row = _row()
        row.events[-1]["result"]["inventory"] = ["wrong.json"]
        with patch(AUTO + "P10MotionInstanceV3JobStoreV2") as store, \
                patch(AUTO + "MotionInstanceV3BundleReaderV2") as reader:
            store.return_value.load.return_value = row
            with self.assertRaises(P10Spine42V3AutoInputsV2Error):
                resolve_p10_spine42_v3_auto_inputs_v2("state", *_ids())
        reader.assert_not_called()

    def test_exact_source_is_read_once_and_bound_to_sealed_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Spine42V3V2Fixture(Path(temporary))
            row = _row_for_bundle(fixture.motion_bundle)
            reader = Mock()
            reader.load.return_value = fixture.motion_bundle
            with patch(AUTO + "P10MotionInstanceV3JobStoreV2") as store, \
                    patch(AUTO + "MotionInstanceV3BundleReaderV2",
                          return_value=reader):
                store.return_value.load.return_value = row
                value = load_verified_p10_spine42_v3_motion_v2(
                    "state", resolve_p10_spine42_v3_auto_inputs_v2(
                        "state", *_ids()
                    ),
                )
            self.assertIs(fixture.motion_bundle, value)
            reader.load.assert_called_once_with(
                fixture.motion_bundle.project_id,
                fixture.motion_bundle.motion_instance_v3_sha256,
                fixture.motion_bundle.bundle_sha256,
            )

    def test_exact_bundle_receipt_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Spine42V3V2Fixture(Path(temporary))
            row = _row_for_bundle(fixture.motion_bundle)
            row.events[-1]["result"]["run_sha256"] = "f" * 64
            reader = Mock()
            reader.load.return_value = fixture.motion_bundle
            with patch(AUTO + "P10MotionInstanceV3JobStoreV2") as store, \
                    patch(AUTO + "MotionInstanceV3BundleReaderV2",
                          return_value=reader), self.assertRaises(
                        P10Spine42V3AutoInputsV2Error
                    ):
                store.return_value.load.return_value = row
                inputs = resolve_p10_spine42_v3_auto_inputs_v2(
                    "state", *_ids()
                )
                load_verified_p10_spine42_v3_motion_v2("state", inputs)

    def test_tampered_exact_bundle_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Spine42V3V2Fixture(Path(temporary))
            row = _row_for_bundle(fixture.motion_bundle)
            extra = fixture.motion_bundle.path / "unexpected.json"
            extra.write_bytes(b"{}")
            with patch(AUTO + "P10MotionInstanceV3JobStoreV2") as store:
                store.return_value.load.return_value = row
                inputs = resolve_p10_spine42_v3_auto_inputs_v2(
                    fixture.state_root, *_ids()
                )
                with self.assertRaises(P10Spine42V3AutoInputsV2Error):
                    load_verified_p10_spine42_v3_motion_v2(
                        fixture.state_root, inputs,
                    )


class Spine42V3ResultV2Tests(unittest.TestCase):
    def test_every_projection_exactly_replays_five_file_bundle(self):
        row = _completed_row()
        command = _command()
        with patch(
            RESULT + "verify_body_sway_spine42_v3_v2_command",
            return_value=command,
        ) as verify:
            first = read_p10_spine42_v3_result_v2("state", row)
            second = read_p10_spine42_v3_result_v2("state", row)
        self.assertEqual("completed", first["status"])
        self.assertEqual(list(SPINE_DOCUMENT_NAMES), first["inventory"])
        self.assertEqual(False, first["authority"]["official_runtime_loaded"])
        self.assertEqual(first, second)
        self.assertEqual(2, verify.call_count)

    def test_changed_reader_payload_or_path_fails_closed(self):
        for mutation in ("inventory", "path"):
            command = _command()
            if mutation == "inventory":
                command.document["inventory"] = list(
                    reversed(SPINE_DOCUMENT_NAMES)
                )
            else:
                command.document["output_path"] = "C:/private"
            with self.subTest(mutation=mutation), patch(
                RESULT + "verify_body_sway_spine42_v3_v2_command",
                return_value=command,
            ), self.assertRaises(P10Spine42V3ResultV2Error):
                read_p10_spine42_v3_result_v2("state", _completed_row())


def _ids():
    return "1" * 64, "2" * 64, "3" * 64, "4" * 64


def _row(status="completed"):
    result = {
        "project_id": "project-a", "clip_id": "idle",
        "motion_instance_v3_sha256": "5" * 64,
        "bundle_sha256": "6" * 64, "run_sha256": "7" * 64,
        "inventory": list(MOTION_DOCUMENT_NAMES), "reused": False,
    } if status == "completed" else None
    return SimpleNamespace(
        run_id="4" * 64,
        status=status,
        request={
            "job_id": "1" * 64, "safety_run_id": "2" * 64,
            "dynamic_run_id": "3" * 64, "project_id": "project-a",
        },
        events=[{"result": result}],
    )


def _row_for_bundle(bundle):
    row = _row()
    row.request["project_id"] = bundle.project_id
    row.events[-1]["result"] = {
        "project_id": bundle.project_id, "clip_id": bundle.clip_id,
        "motion_instance_v3_sha256": bundle.motion_instance_v3_sha256,
        "bundle_sha256": bundle.bundle_sha256,
        "run_sha256": bundle.run_sha256,
        "inventory": list(bundle.inventory), "reused": False,
    }
    return row


def _sealed():
    return {
        "project_id": "project-a", "clip_id": "idle",
        "skeleton_json_sha256": "7" * 64, "bundle_sha256": "8" * 64,
        "run_document_sha256": "9" * 64, "report_sha256": "a" * 64,
        "inventory": list(SPINE_DOCUMENT_NAMES), "reused": False,
    }


def _completed_row():
    row = _row()
    row.request["motion_run_id"] = "4" * 64
    row.events = ({"result": _sealed()},)
    row.public_document = lambda: {"run_id": "b" * 64,
                                   "status": "completed"}
    return row


def _command():
    document = {
        "project_id": "project-a", "inventory": list(SPINE_DOCUMENT_NAMES),
        "authority": dict(AUTHORITY),
        "release_gate": {
            "status": RELEASE_GATE["status"],
            "reason_codes": list(RELEASE_GATE["reason_codes"]),
        },
        "verification": {"status": "passed", "exact_readback": True},
    }
    return SimpleNamespace(
        mode="verified", project_id="project-a", clip_id="idle",
        skeleton_json_sha256="7" * 64, bundle_sha256="8" * 64,
        run_document_sha256="9" * 64, report_sha256="a" * 64,
        inventory=SPINE_DOCUMENT_NAMES, document=document,
    )


if __name__ == "__main__":
    unittest.main()
