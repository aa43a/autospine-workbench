"""Below-normal isolated process launcher for P10.5d v2."""

from __future__ import annotations

import json
from pathlib import Path
from queue import Empty, Queue
import subprocess
import sys
import threading

from .p10_safety_analysis_worker_process_v2 import (
    _hidden_window_options, _worker_environment,
)
from .process_tree_cleanup import stop_owned_process_tree
from .windows_process_job import attach_kill_on_close_process_job
from .windows_suspended_process import resume_suspended_primary_thread


class P10DynamicSeamWorkerV2Error(RuntimeError):
    def __init__(self, code="worker_process_failed", terminal=False):
        super().__init__("P10.5d v2 isolated worker failed closed")
        self.failure_code, self.terminal = code, terminal


def run_p10_dynamic_seam_worker_v2(
    run_id, state_root, workspace_root, *, on_progress=None,
    cancel_event=None,
):
    command = [
        sys.executable, "-B", "-m",
        "autospine_workbench.p10_dynamic_seam_worker_main_v2",
        "--run-id", run_id, "--state-root", str(Path(state_root)),
        "--workspace-root", str(Path(workspace_root)),
    ]
    process = job = reader = None
    primary_error = None
    try:
        process = subprocess.Popen(
            command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, shell=False,
            cwd=str(Path(__file__).resolve().parents[2]), close_fds=True,
            env=_worker_environment(), **_hidden_window_options(),
        )
        job = attach_kill_on_close_process_job(process)
        resume_suspended_primary_thread(process)
        if process.stdout is None:
            raise P10DynamicSeamWorkerV2Error()
        messages = Queue()
        reader = threading.Thread(
            target=_pump, args=(process.stdout, messages), daemon=True,
            name=f"autospine-p10-seam-v2-{run_id[:8]}",
        )
        reader.start()
        total_bytes, started, terminal = 0, False, None
        while True:
            if cancel_event is not None and cancel_event.is_set():
                raise P10DynamicSeamWorkerV2Error("manager_closed", False)
            try:
                raw = messages.get(timeout=0.05)
            except Empty:
                if process.poll() is not None and not reader.is_alive():
                    break
                continue
            if raw is None:
                break
            total_bytes += len(raw)
            if len(raw) > 4096 or total_bytes > 2 * 1024 * 1024:
                raise P10DynamicSeamWorkerV2Error()
            message = _message(raw, run_id)
            kind = message["type"]
            if kind == "started" and not started and terminal is None:
                started = True
            elif kind == "progress" and started and terminal is None:
                current, total = message.get("current"), message.get("total")
                if type(current) is not int or type(total) is not int \
                        or not 0 <= current <= total <= 1_000_000:
                    raise P10DynamicSeamWorkerV2Error()
                if on_progress is not None:
                    on_progress(message.get("stage"), current, total)
            elif kind in {"result", "failure"} and started \
                    and terminal is None:
                terminal = message
            else:
                raise P10DynamicSeamWorkerV2Error()
        code = process.wait(timeout=1)
        if terminal is None:
            raise P10DynamicSeamWorkerV2Error()
        if terminal["type"] == "failure":
            raise P10DynamicSeamWorkerV2Error(
                terminal.get("failure_code", "compile_failed"),
                bool(terminal.get("terminal")),
            )
        if code != 0 or set(terminal) != {
            "protocol", "type", "run_id", "result"
        } or type(terminal["result"]) is not dict:
            raise P10DynamicSeamWorkerV2Error()
        return terminal["result"]
    except P10DynamicSeamWorkerV2Error as exc:
        primary_error = exc
        raise
    except Exception as exc:
        primary_error = P10DynamicSeamWorkerV2Error()
        raise primary_error from exc
    finally:
        cleanup_error = _cleanup(process, job, reader)
        if cleanup_error is not None:
            if primary_error is None:
                raise cleanup_error
            primary_error.add_note(str(cleanup_error))


def _message(raw, run_id):
    try:
        value = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise P10DynamicSeamWorkerV2Error() from exc
    canonical = json.dumps(value, sort_keys=True,
                           separators=(",", ":")).encode()
    if canonical != raw.rstrip(b"\n") or type(value) is not dict \
            or value.get("protocol") \
                != "autospine-p10-dynamic-seam-worker/v2" \
            or value.get("run_id") != run_id:
        raise P10DynamicSeamWorkerV2Error()
    return value


def _pump(stream, messages):
    try:
        while True:
            raw = stream.readline(4097)
            messages.put(raw if raw else None)
            if not raw:
                return
    except Exception:
        messages.put(None)


def _cleanup(process, job, reader):
    if process is None:
        return None
    try:
        stop_owned_process_tree(process, job, 1.0, 1.0)
        if process.stdout is not None:
            process.stdout.close()
        if reader is not None and reader.is_alive():
            reader.join(1.0)
        if reader is not None and reader.is_alive():
            raise RuntimeError("P10.5d worker output reader did not stop")
        return None
    except Exception as exc:
        return P10DynamicSeamWorkerV2Error("worker_cleanup_failed", False)


__all__ = ["P10DynamicSeamWorkerV2Error",
           "run_p10_dynamic_seam_worker_v2"]
