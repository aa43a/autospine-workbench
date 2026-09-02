from __future__ import annotations

from io import BytesIO
import json
import subprocess
import threading
import unittest
from unittest.mock import MagicMock, patch

from autospine_workbench.p10_dynamic_seam_worker_process_v2 import (
    P10DynamicSeamWorkerV2Error, _message,
    run_p10_dynamic_seam_worker_v2,
)
from autospine_workbench.p10_safety_analysis_worker_process_v2 import (
    _hidden_window_options,
)


class WorkerV2Tests(unittest.TestCase):
    def test_protocol_rejects_wrong_run_and_noncanonical_json(self):
        with self.assertRaises(P10DynamicSeamWorkerV2Error):
            _message(_raw("b" * 64), "a" * 64)
        with self.assertRaises(P10DynamicSeamWorkerV2Error):
            _message(b'{"type": "started"}\n', "a" * 64)

    def test_windows_launcher_requests_below_normal_priority(self):
        options = _hidden_window_options()
        if hasattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS"):
            self.assertTrue(
                options["creationflags"]
                & subprocess.BELOW_NORMAL_PRIORITY_CLASS
            )

    def test_parent_validates_result_protocol_and_cleans_process_tree(self):
        run_id = "a" * 64
        result = {"project_id": "p", "clip_id": "c",
                  "probe_sha256": "1" * 64, "bundle_sha256": "2" * 64,
                  "source_set_sha256": "3" * 64,
                  "source_document_sha256": "4" * 64,
                  "probe_status": "compiled"}
        stream = BytesIO(_raw(run_id) + _raw(run_id, "result", result=result))
        process = MagicMock(stdout=stream)
        process.poll.return_value = 0
        process.wait.return_value = 0
        with patch(_POPEN, return_value=process), \
                patch(_ATTACH, return_value=object()), \
                patch(_RESUME), patch(_CLEANUP) as cleanup:
            value = run_p10_dynamic_seam_worker_v2(
                run_id, ".", ".",
            )
        self.assertEqual(value, result)
        cleanup.assert_called_once()
        self.assertFalse(any(
            thread.name.startswith("autospine-p10-seam-v2-")
            and thread.is_alive() for thread in threading.enumerate()
        ))

    def test_malformed_child_output_still_kills_owned_tree(self):
        process = MagicMock(stdout=BytesIO(b"not-json\n"))
        process.poll.return_value = 0
        with patch(_POPEN, return_value=process), \
                patch(_ATTACH, return_value=object()), \
                patch(_RESUME), patch(_CLEANUP) as cleanup, \
                self.assertRaises(P10DynamicSeamWorkerV2Error):
            run_p10_dynamic_seam_worker_v2("a" * 64, ".", ".")
        cleanup.assert_called_once()
        self.assertFalse(any(
            thread.name.startswith("autospine-p10-seam-v2-")
            and thread.is_alive() for thread in threading.enumerate()
        ))

    def test_cleanup_failure_cannot_turn_valid_result_into_success(self):
        run_id = "a" * 64
        result = {"project_id": "p", "clip_id": "c",
                  "probe_sha256": "1" * 64, "bundle_sha256": "2" * 64,
                  "source_set_sha256": "3" * 64,
                  "source_document_sha256": "4" * 64,
                  "probe_status": "compiled"}
        process = MagicMock(stdout=BytesIO(
            _raw(run_id) + _raw(run_id, "result", result=result)
        ))
        process.poll.return_value = process.wait.return_value = 0
        with patch(_POPEN, return_value=process), \
                patch(_ATTACH, return_value=object()), patch(_RESUME), \
                patch(_CLEANUP, side_effect=RuntimeError("cleanup")), \
                self.assertRaises(P10DynamicSeamWorkerV2Error):
            run_p10_dynamic_seam_worker_v2(run_id, ".", ".")


def _raw(run_id, kind="started", **fields):
    return json.dumps({
        "protocol": "autospine-p10-dynamic-seam-worker/v2",
        "type": kind, "run_id": run_id, **fields,
    }, sort_keys=True, separators=(",", ":")).encode() + b"\n"


_MODULE = "autospine_workbench.p10_dynamic_seam_worker_process_v2."
_POPEN, _ATTACH = _MODULE + "subprocess.Popen", _MODULE + "attach_kill_on_close_process_job"
_RESUME, _CLEANUP = _MODULE + "resume_suspended_primary_thread", _MODULE + "stop_owned_process_tree"


if __name__ == "__main__":
    unittest.main()
