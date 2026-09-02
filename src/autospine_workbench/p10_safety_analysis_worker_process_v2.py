"""Launch and monitor the isolated P10.4b v2 Python worker."""
from __future__ import annotations
from dataclasses import dataclass
import os
from pathlib import Path
from queue import Empty, Queue
import subprocess
import sys
import threading
from typing import Any
from .p10_safety_analysis_job_files_v2 import require_run_id
from .p10_safety_analysis_job_store_v2 import P10SafetyAnalysisJobStoreV2
from .p10_safety_analysis_result_store_v2 import (
    P10SafetyAnalysisResultStoreV2, P10SafetyAnalysisResultStoreV2Error,
)
from .p10_safety_analysis_worker_protocol_v2 import (
    MAX_LINE_BYTES, MAX_STDERR_BYTES, MAX_STDOUT_BYTES,
    P10SafetyAnalysisWorkerDecoderV2,
    P10SafetyAnalysisWorkerProtocolV2Error,
)
from .process_tree_cleanup import stop_owned_process_tree
from .windows_process_job import (
    WindowsProcessJobError, attach_kill_on_close_process_job,
)
from .windows_suspended_process import (
    WindowsSuspendedProcessError, resume_suspended_primary_thread,
)
WORKER_MODULE = "autospine_workbench.p10_safety_analysis_worker_main_v2"
POLL_SECONDS = 0.05
TERMINATE_GRACE_SECONDS = 1.0
KILL_GRACE_SECONDS = 1.0
class P10SafetyAnalysisWorkerProcessV2Error(RuntimeError):
    """Raised when the worker process or result cannot be trusted."""
class P10SafetyAnalysisWorkerCancelledV2(
    P10SafetyAnalysisWorkerProcessV2Error
):
    pass
class P10SafetyAnalysisWorkerFailureV2(
    P10SafetyAnalysisWorkerProcessV2Error
):
    def __init__(self, failure_code: str, terminal: bool) -> None:
        super().__init__("P10.4b v2 worker failed closed")
        self.failure_code = failure_code
        self.terminal = terminal
@dataclass(frozen=True, slots=True)
class P10SafetyAnalysisWorkerResultV2:
    result: dict[str, Any]
    amplitude_document: dict[str, Any]
    continuous_document: dict[str, Any]
def run_p10_safety_analysis_worker_process_v2(
    run_id: str, job_id: str, state_root: Path, workspace_root: Path,
    *, on_progress=None, cancel_event=None,
) -> P10SafetyAnalysisWorkerResultV2:
    """Run one exact worker and independently validate its staged result."""
    state, workspace = _inputs(
        run_id, job_id, state_root, workspace_root,
        on_progress, cancel_event,
    )
    snapshot = P10SafetyAnalysisJobStoreV2(state).load(run_id)
    if snapshot.status != "running" \
            or snapshot.request.document["job_id"] != job_id:
        raise P10SafetyAnalysisWorkerProcessV2Error(
            "P10.4b v2 worker request is stale"
        )
    if _cancelled(cancel_event):
        raise P10SafetyAnalysisWorkerCancelledV2(
            "P10.4b v2 worker was cancelled"
        )
    command = [
        sys.executable, "-B", "-m", WORKER_MODULE,
        "--run-id", run_id, "--job-id", job_id,
        "--state-root", str(state),
        "--workspace-root", str(workspace),
    ]
    process = process_job = None
    primary_error = None
    readers = []
    try:
        process = subprocess.Popen(
            command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, shell=False,
            cwd=str(Path(__file__).resolve().parents[2]), close_fds=True,
            env=_worker_environment(),
            **_hidden_window_options(),
        )
        process_job = attach_kill_on_close_process_job(process)
        resume_suspended_primary_thread(process)
        if process.stdout is None or process.stderr is None:
            raise P10SafetyAnalysisWorkerProcessV2Error(
                "P10.4b v2 worker pipes are unavailable"
            )
        messages = Queue()
        readers = _reader_threads(process, run_id, messages)
        for reader in readers:
            reader.start()
        terminal = _monitor(
            process, run_id, job_id, messages, readers,
            on_progress, cancel_event,
        )
        return_code = process.wait(timeout=KILL_GRACE_SECONDS)
        if terminal["type"] == "failure":
            if return_code == 0:
                raise P10SafetyAnalysisWorkerProcessV2Error(
                    "P10.4b v2 worker failure exit status differs"
                )
            raise P10SafetyAnalysisWorkerFailureV2(
                terminal["failure_code"], terminal["terminal"],
            )
        if return_code != 0:
            raise P10SafetyAnalysisWorkerProcessV2Error(
                "P10.4b v2 worker result exit status differs"
            )
        amplitude, continuous = P10SafetyAnalysisResultStoreV2(
            state
        ).read_and_validate(
            run_id, snapshot.request.document, terminal["result"],
        )
        return P10SafetyAnalysisWorkerResultV2(
            terminal["result"], amplitude, continuous,
        )
    except P10SafetyAnalysisWorkerProcessV2Error as exc:
        primary_error = exc
        raise
    except P10SafetyAnalysisWorkerProtocolV2Error as exc:
        primary_error = P10SafetyAnalysisWorkerProcessV2Error(
            "P10.4b v2 worker protocol is invalid"
        )
        raise primary_error from exc
    except (OSError, subprocess.SubprocessError) as exc:
        primary_error = P10SafetyAnalysisWorkerProcessV2Error(
            "P10.4b v2 worker could not be started or monitored"
        )
        raise primary_error from exc
    except (WindowsProcessJobError, WindowsSuspendedProcessError) as exc:
        primary_error = P10SafetyAnalysisWorkerProcessV2Error(
            "P10.4b v2 worker process-tree isolation failed"
        )
        raise primary_error from exc
    except P10SafetyAnalysisResultStoreV2Error as exc:
        primary_error = P10SafetyAnalysisWorkerFailureV2(
            "analysis_validation_failed", True,
        )
        raise primary_error from exc
    except Exception as exc:
        primary_error = P10SafetyAnalysisWorkerProcessV2Error(
            "P10.4b v2 staged result validation failed"
        )
        raise primary_error from exc
    finally:
        cleanup = _cleanup(process, process_job, readers)
        if cleanup is not None:
            if primary_error is None:
                raise cleanup
            primary_error.add_note(str(cleanup))
def _reader_threads(process, run_id, messages):
    return [
        threading.Thread(
            target=_pump, args=(process.stdout, "stdout", MAX_STDOUT_BYTES,
                                messages), daemon=True,
            name=f"autospine-p10-safety-v2-stdout-{run_id[:8]}",
        ),
        threading.Thread(
            target=_pump, args=(process.stderr, "stderr", MAX_STDERR_BYTES,
                                messages), daemon=True,
            name=f"autospine-p10-safety-v2-stderr-{run_id[:8]}",
        ),
    ]
def _monitor(process, run_id, job_id, messages, readers,
             callback, cancel_event):
    decoder = P10SafetyAnalysisWorkerDecoderV2(run_id, job_id)
    buffer, ended = b"", set()
    while len(ended) < 2:
        if _cancelled(cancel_event):
            raise P10SafetyAnalysisWorkerCancelledV2(
                "P10.4b v2 worker was cancelled"
            )
        try:
            kind, channel, payload = messages.get(timeout=POLL_SECONDS)
        except Empty:
            if process.poll() is not None and not any(
                reader.is_alive() for reader in readers
            ):
                break
            continue
        if kind == "error" or kind == "overflow":
            raise P10SafetyAnalysisWorkerProcessV2Error(
                "P10.4b v2 worker output is unsafe"
            )
        if kind == "eof":
            ended.add(channel)
            continue
        if channel == "stderr":
            continue
        buffer += payload
        while b"\n" in buffer:
            line, buffer = buffer.split(b"\n", 1)
            message = decoder.accept(line)
            if message["type"] == "progress" and callback is not None:
                callback(
                    message["stage"], message["current"], message["total"],
                )
            if _cancelled(cancel_event):
                raise P10SafetyAnalysisWorkerCancelledV2(
                    "P10.4b v2 worker was cancelled"
                )
        if len(buffer) > MAX_LINE_BYTES:
            raise P10SafetyAnalysisWorkerProcessV2Error(
                "P10.4b v2 worker protocol line is excessive"
            )
    if buffer or decoder.terminal_message is None:
        raise P10SafetyAnalysisWorkerProcessV2Error(
            "P10.4b v2 worker protocol ended incompletely"
        )
    return decoder.terminal_message
def _pump(stream, channel, limit, messages):
    total = 0
    try:
        while True:
            chunk = getattr(stream, "read1", stream.read)(4096)
            if not chunk:
                messages.put(("eof", channel, None))
                return
            total += len(chunk)
            if total > limit:
                messages.put(("overflow", channel, None))
                return
            messages.put(("data", channel, chunk))
    except (OSError, ValueError):
        messages.put(("error", channel, None))
def _inputs(run_id, job_id, state_root, workspace_root, callback, cancel):
    try:
        require_run_id(run_id)
        require_run_id(job_id)
        if callback is not None and not callable(callback) \
                or cancel is not None \
                and not callable(getattr(cancel, "is_set", None)):
            raise ValueError("callbacks")
        state = Path(state_root).resolve(strict=True)
        workspace = Path(workspace_root).resolve(strict=True)
        if not state.is_dir() or not workspace.is_dir():
            raise ValueError("directories")
        return state, workspace
    except Exception as exc:
        raise P10SafetyAnalysisWorkerProcessV2Error(
            "P10.4b v2 worker inputs are invalid"
        ) from exc


def _cancelled(event) -> bool:
    return bool(event is not None and event.is_set())
def _cleanup(process, process_job, readers):
    if process is None:
        return None
    try:
        stop_owned_process_tree(
            process, process_job, TERMINATE_GRACE_SECONDS,
            KILL_GRACE_SECONDS,
        )
        for stream in (process.stdout, process.stderr):
            if stream is not None:
                stream.close()
        for reader in readers:
            if reader.is_alive():
                reader.join(KILL_GRACE_SECONDS)
        if any(reader.is_alive() for reader in readers):
            raise WindowsProcessJobError("Worker output reader did not stop")
        return None
    except (OSError, WindowsProcessJobError) as exc:
        return P10SafetyAnalysisWorkerProcessV2Error(
            "P10.4b v2 worker process-tree cleanup failed"
        )
def _hidden_window_options() -> dict[str, Any]:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) \
        | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    options: dict[str, Any] = {}
    if os.name == "nt":
        flags |= getattr(subprocess, "CREATE_SUSPENDED", 0x00000004)
        flags |= getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0x00004000)
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = subprocess.SW_HIDE
        options["startupinfo"] = startup
    options["creationflags"] = flags
    return options
def _worker_environment():
    environment = os.environ.copy()
    source = str(Path(__file__).resolve().parents[1])
    environment["PYTHONPATH"] = source
    environment["PYTHONNOUSERSITE"] = "1"
    environment["PYTHONSAFEPATH"] = "1"
    for name in ("PYTHONHOME", "PYTHONINSPECT", "PYTHONSTARTUP"):
        environment.pop(name, None)
    return environment
__all__ = [
    "P10SafetyAnalysisWorkerCancelledV2",
    "P10SafetyAnalysisWorkerFailureV2",
    "P10SafetyAnalysisWorkerProcessV2Error",
    "P10SafetyAnalysisWorkerResultV2",
    "run_p10_safety_analysis_worker_process_v2",
]
