"""Bounded protocol and process-isolation tests for P10.4b v2."""

from __future__ import annotations

from io import BytesIO
import json
import os
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (ROOT, SRC):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

import autospine_workbench.p10_safety_analysis_worker_main_v2 as main  # noqa: E402
import autospine_workbench.p10_safety_analysis_worker_process_v2 as process  # noqa: E402
from autospine_workbench.p10_safety_analysis_job_contract_v2 import (  # noqa: E402
    P10SafetyAnalysisRunRequestV2,
)
from autospine_workbench.p10_safety_analysis_job_store_v2 import (  # noqa: E402
    P10SafetyAnalysisJobStoreV2,
)
from autospine_workbench.p10_safety_analysis_worker_protocol_v2 import (  # noqa: E402
    MAX_LINE_BYTES, STAGES, P10SafetyAnalysisWorkerDecoderV2,
    P10SafetyAnalysisWorkerEmitterV2,
    P10SafetyAnalysisWorkerProtocolV2Error,
)
from autospine_workbench.windows_process_job import (  # noqa: E402
    KillOnCloseProcessJob,
)
from tests.p10_safety_analysis_job_v2_test_helpers import (  # noqa: E402
    SHA, completed_capture_job,
)


RUN_ID, JOB_ID = SHA["8"], SHA["9"]


def _result():
    return {
        "authority_scope": "compile_time_snapshot",
        "admission_sha256": SHA["1"],
        "visual_candidate_sha256": SHA["2"], "visual_revision": 1,
        "visual_decision_sha256": SHA["3"],
        "amplitude_sha256": SHA["4"],
        "continuous_sha256": SHA["5"],
        "amplitude_size_bytes": 123, "continuous_size_bytes": 456,
    }


def _success_stream(run_id, job_id):
    output = BytesIO()
    emitter = P10SafetyAnalysisWorkerEmitterV2(output, run_id, job_id)
    emitter.started()
    for stage in STAGES:
        emitter.progress(stage, 0, 1)
        emitter.progress(stage, 1, 1)
    emitter.result(_result())
    return output.getvalue()


class _FakeProcess:
    def __init__(self, stdout=b"", stderr=b"", return_code=0):
        self.stdout, self.stderr = BytesIO(stdout), BytesIO(stderr)
        self.return_code = return_code
        self.pid, self._handle = 123, 456
        self.terminated = self.killed = False

    def poll(self):
        return self.return_code

    def wait(self, timeout=None):
        return self.return_code

    def terminate(self):
        self.terminated = True
        self.return_code = -15

    def kill(self):
        self.killed = True
        self.return_code = -9


class P10SafetyAnalysisWorkerProtocolV2Tests(unittest.TestCase):
    def test_success_stream_is_canonical_ordered_and_bounded(self):
        output = _success_stream(RUN_ID, JOB_ID)
        decoder = P10SafetyAnalysisWorkerDecoderV2(RUN_ID, JOB_ID)
        messages = [decoder.accept(line) for line in output.splitlines()]
        self.assertEqual("started", messages[0]["type"])
        self.assertEqual("result", messages[-1]["type"])
        self.assertEqual(_result(), decoder.terminal_message["result"])
        self.assertTrue(all(len(line) <= MAX_LINE_BYTES
                            for line in output.splitlines()))

    def test_unknown_fields_and_stage_skips_fail_closed(self):
        output = BytesIO()
        emitter = P10SafetyAnalysisWorkerEmitterV2(
            output, RUN_ID, JOB_ID,
        )
        emitter.started()
        emitter.progress("exact_source", 0, 1)
        decoder = P10SafetyAnalysisWorkerDecoderV2(RUN_ID, JOB_ID)
        decoder.accept(output.getvalue().splitlines()[0])
        with self.assertRaises(P10SafetyAnalysisWorkerProtocolV2Error):
            decoder.accept(output.getvalue().splitlines()[1])
        value = json.loads(output.getvalue().splitlines()[0])
        value["extra"] = True
        raw = json.dumps(
            value, sort_keys=True, separators=(",", ":"),
        ).encode()
        with self.assertRaises(P10SafetyAnalysisWorkerProtocolV2Error):
            P10SafetyAnalysisWorkerDecoderV2(RUN_ID, JOB_ID).accept(raw)


class P10SafetyAnalysisWorkerMainV2Tests(unittest.TestCase):
    def test_capture_reader_returns_the_strict_public_mapping(self):
        snapshot, store = Mock(), Mock()
        snapshot.public_document.return_value = {"job_id": JOB_ID}
        store.load.return_value = snapshot
        with patch.object(
            main, "P10CaptureJobStore", return_value=store,
        ):
            value = main._ReadOnlyCaptureJobs(Path("state")).get(JOB_ID)
        self.assertEqual({"job_id": JOB_ID}, value)
        snapshot.public_document.assert_called_once_with()

    def test_child_publishes_artifacts_but_never_appends_events(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = BytesIO()
            snapshot = SimpleNamespace(
                status="running",
                request=SimpleNamespace(document={"job_id": JOB_ID}),
            )
            store = Mock()
            store.load.return_value = snapshot
            compiled = SimpleNamespace(
                admission_sha256=SHA["1"],
                _amplitude=object(), _continuous=object(),
                _admission=SimpleNamespace(_result=SimpleNamespace(
                    visual_candidate_sha256=SHA["2"], visual_revision=1,
                    visual_decision_sha256=SHA["3"],
                )),
            )
            result_store = Mock()
            result_store.publish.return_value = _result()
            def compile_with_progress(*_args, **kwargs):
                for stage in STAGES:
                    kwargs["on_progress"](stage, 0, 1)
                    kwargs["on_progress"](stage, 1, 1)
                return compiled
            with patch.object(
                main, "P10SafetyAnalysisJobStoreV2", return_value=store,
            ), patch.object(
                main, "ProjectStore", return_value=Mock(),
            ), patch.object(
                main, "_ReadOnlyCaptureJobs", return_value=Mock(),
            ), patch.object(
                main, "compile_p10_safety_analysis_v2_for_job",
                side_effect=compile_with_progress,
            ) as compile_, patch.object(
                main, "require_compiled_result",
            ), patch.object(
                main, "P10SafetyAnalysisResultStoreV2",
                return_value=result_store,
            ):
                code = main.run_p10_safety_analysis_worker_v2(
                    RUN_ID, JOB_ID, root, root,
                    protocol_stream=output,
                )
            self.assertEqual(main.EXIT_OK, code)
            store.append.assert_not_called()
            result_store.publish.assert_called_once()
            self.assertIsNotNone(compile_.call_args.kwargs["on_progress"])
            decoder = P10SafetyAnalysisWorkerDecoderV2(RUN_ID, JOB_ID)
            for line in output.getvalue().splitlines():
                decoder.accept(line)
            self.assertEqual("result", decoder.terminal_message["type"])


class P10SafetyAnalysisWorkerProcessV2Tests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        completed = completed_capture_job()
        self.job_id = completed.job_id
        request = P10SafetyAnalysisRunRequestV2.build(
            completed, attempt=1, previous_run_id=None,
        )
        store = P10SafetyAnalysisJobStoreV2(self.root)
        queued = store.create(request)
        self.snapshot = store.append(
            queued.run_id, "running", "review_admission",
            expected_previous=queued.head_event_sha256,
        )

    def tearDown(self):
        self.temporary.cleanup()

    def test_exact_module_command_and_parent_result_validation(self):
        run_id = self.snapshot.run_id
        fake = _FakeProcess(_success_stream(run_id, self.job_id))
        verified = ({"amplitude": True}, {"continuous": True})
        result_store = Mock()
        result_store.read_and_validate.return_value = verified
        progress = []
        with self._boundaries(fake, result_store) as launch, patch.object(
            process, "Queue", wraps=process.Queue,
        ) as queue_factory:
            value = process.run_p10_safety_analysis_worker_process_v2(
                run_id, self.job_id, self.root, self.root,
                on_progress=lambda *row: progress.append(row),
            )
        queue_factory.assert_called_once_with()
        command = launch.call_args.args[0]
        self.assertEqual(sys.executable, command[0])
        self.assertEqual(["-B", "-m", process.WORKER_MODULE], command[1:4])
        self.assertFalse(launch.call_args.kwargs["shell"])
        environment = launch.call_args.kwargs["env"]
        self.assertEqual(str(SRC), environment["PYTHONPATH"])
        self.assertEqual("1", environment["PYTHONNOUSERSITE"])
        self.assertEqual("1", environment["PYTHONSAFEPATH"])
        if os.name == "nt":
            self.assertTrue(
                launch.call_args.kwargs["creationflags"] & 0x00004000,
            )
        self.assertEqual(_result(), value.result)
        self.assertEqual(verified[0], value.amplitude_document)
        self.assertEqual(len(STAGES) * 2, len(progress))
        result_store.read_and_validate.assert_called_once_with(
            run_id, self.snapshot.request.document, _result(),
        )

    def test_cancellation_terminates_the_owned_process(self):
        run_id = self.snapshot.run_id
        fake = _FakeProcess(_success_stream(run_id, self.job_id),
                            return_code=None)
        cancelled = threading.Event()
        with self._boundaries(fake, Mock()), self.assertRaises(
            process.P10SafetyAnalysisWorkerCancelledV2,
        ):
            process.run_p10_safety_analysis_worker_process_v2(
                run_id, self.job_id, self.root, self.root,
                on_progress=lambda *_: cancelled.set(),
                cancel_event=cancelled,
            )
        self.assertTrue(fake.terminated or fake.killed)

    def test_protocol_failure_still_joins_started_output_readers(self):
        fake = _FakeProcess(b"{}\n", return_code=None)
        with self._boundaries(fake, Mock()), patch.object(
            process, "_cleanup", wraps=process._cleanup,
        ) as cleanup, self.assertRaises(
            process.P10SafetyAnalysisWorkerProcessV2Error,
        ):
            process.run_p10_safety_analysis_worker_process_v2(
                self.snapshot.run_id, self.job_id, self.root, self.root,
            )
        readers = cleanup.call_args.args[2]
        self.assertEqual(2, len(readers))
        self.assertFalse(any(reader.is_alive() for reader in readers))

    def test_output_pump_prefers_non_filling_buffered_read(self):
        class Stream:
            def __init__(self):
                self.values = iter((b"progress\n", b""))

            def read1(self, size):
                self.assert_size = size
                return next(self.values)

            def read(self, _size):
                raise AssertionError("filling read must not delay progress")

        stream, messages = Stream(), process.Queue()
        process._pump(stream, "stdout", 64, messages)
        self.assertEqual(4096, stream.assert_size)
        self.assertEqual(("data", "stdout", b"progress\n"), messages.get())
        self.assertEqual(("eof", "stdout", None), messages.get())

    def test_output_pump_falls_back_to_plain_read(self):
        class Stream:
            def __init__(self):
                self.values = iter((b"result\n", b""))

            def read(self, size):
                self.assert_size = size
                return next(self.values)

        stream, messages = Stream(), process.Queue()
        process._pump(stream, "stdout", 64, messages)
        self.assertEqual(4096, stream.assert_size)
        self.assertEqual(("data", "stdout", b"result\n"), messages.get())
        self.assertEqual(("eof", "stdout", None), messages.get())

    def test_worker_environment_does_not_inherit_python_injection(self):
        inherited = {
            "PYTHONPATH": "E:/untrusted", "PYTHONHOME": "E:/wrong",
            "PYTHONINSPECT": "1", "PYTHONSTARTUP": "E:/startup.py",
        }
        with patch.dict(os.environ, inherited):
            environment = process._worker_environment()
        self.assertEqual(str(SRC), environment["PYTHONPATH"])
        self.assertTrue(all(name not in environment for name in (
            "PYTHONHOME", "PYTHONINSPECT", "PYTHONSTARTUP",
        )))

    def test_parent_staged_validation_failure_is_terminal(self):
        fake = _FakeProcess(_success_stream(
            self.snapshot.run_id, self.job_id,
        ))
        result_store = Mock()
        result_store.read_and_validate.side_effect = \
            process.P10SafetyAnalysisResultStoreV2Error("invalid")
        with self._boundaries(fake, result_store), self.assertRaises(
            process.P10SafetyAnalysisWorkerFailureV2,
        ) as raised:
            process.run_p10_safety_analysis_worker_process_v2(
                self.snapshot.run_id, self.job_id, self.root, self.root,
            )
        self.assertEqual(
            "analysis_validation_failed", raised.exception.failure_code,
        )
        self.assertTrue(raised.exception.terminal)

    def _boundaries(self, fake, result_store):
        class Boundaries:
            def __enter__(inner):
                inner.patches = (
                    patch.object(process.subprocess, "Popen",
                                 return_value=fake),
                    patch.object(
                        process, "attach_kill_on_close_process_job",
                        return_value=KillOnCloseProcessJob(None, None),
                    ),
                    patch.object(process, "resume_suspended_primary_thread"),
                    patch.object(
                        process, "P10SafetyAnalysisResultStoreV2",
                        return_value=result_store,
                    ),
                )
                values = [item.start() for item in inner.patches]
                return values[0]

            def __exit__(inner, kind, value, traceback):
                for item in reversed(inner.patches):
                    item.stop()
        return Boundaries()


if __name__ == "__main__":
    unittest.main()
