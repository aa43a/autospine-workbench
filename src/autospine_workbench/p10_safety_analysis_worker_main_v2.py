"""Fixed subprocess entry for CPU-heavy P10.4b v2 analysis."""

from __future__ import annotations

from contextlib import redirect_stdout
from pathlib import Path
import os
import sys

from .p10_capture_job_store import P10CaptureJobStore
from .p10_safety_analysis_job_files_v2 import require_run_id
from .p10_safety_analysis_job_store_v2 import P10SafetyAnalysisJobStoreV2
from .p10_safety_analysis_result_store_v2 import (
    P10SafetyAnalysisResultStoreV2,
)
from .p10_safety_analysis_result_v2 import require_compiled_result
from .p10_safety_analysis_v2_commands import (
    P10SafetyAnalysisV2CommandError,
    compile_p10_safety_analysis_v2_for_job,
)
from .p10_safety_analysis_worker_protocol_v2 import (
    P10SafetyAnalysisWorkerEmitterV2,
)
from .project_store import ProjectStore


EXIT_OK = 0
EXIT_FAILURE = 2
EXIT_INTERNAL = 3
EXIT_USAGE = 64


class _ReadOnlyCaptureJobs:
    def __init__(self, state_root: Path) -> None:
        self._store = P10CaptureJobStore(state_root)

    def get(self, job_id: str):
        return self._store.load(job_id).public_document()


def run_p10_safety_analysis_worker_v2(
    run_id: str, job_id: str, state_root: Path, workspace_root: Path,
    *, protocol_stream=None,
) -> int:
    """Compile/publish artifacts; never append the parent's event journal."""

    output = protocol_stream or sys.stdout.buffer
    emitter = None
    try:
        require_run_id(run_id)
        require_run_id(job_id)
        state = _absolute_directory(state_root, "state root")
        workspace = _absolute_directory(workspace_root, "workspace root")
        emitter = P10SafetyAnalysisWorkerEmitterV2(output, run_id, job_id)
        emitter.started()
        with redirect_stdout(sys.stderr):
            job_store = P10SafetyAnalysisJobStoreV2(state)
            snapshot = job_store.load(run_id)
            request = snapshot.request.document
            if snapshot.status != "running" or request["job_id"] != job_id:
                raise P10SafetyAnalysisV2CommandError(
                    "Worker request is stale", failure_code="source_changed",
                )
            projects = ProjectStore(workspace, state_root=state)
            result = compile_p10_safety_analysis_v2_for_job(
                _ReadOnlyCaptureJobs(state), projects, job_id,
                on_progress=emitter.progress,
            )
            require_compiled_result(request, result)
            metadata = P10SafetyAnalysisResultStoreV2(state).publish(
                run_id, result._amplitude, result._continuous,
                admission_sha256=result.admission_sha256,
                visual_candidate_sha256=
                    result._admission._result.visual_candidate_sha256,
                visual_revision=result._admission._result.visual_revision,
                visual_decision_sha256=
                    result._admission._result.visual_decision_sha256,
            )
        emitter.result(metadata)
        return EXIT_OK
    except P10SafetyAnalysisV2CommandError as exc:
        _emit_failure(emitter, exc.failure_code, exc.terminal)
        return EXIT_FAILURE
    except Exception:
        _emit_failure(emitter, "analysis_failed", False)
        return EXIT_INTERNAL


def main(argv=None) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    parsed = _parse_fixed_arguments(values)
    if parsed is None:
        return EXIT_USAGE
    return run_p10_safety_analysis_worker_v2(*parsed)


def _parse_fixed_arguments(values):
    if len(values) != 8 or values[0] != "--run-id" \
            or values[2] != "--job-id" \
            or values[4] != "--state-root" \
            or values[6] != "--workspace-root":
        return None
    return values[1], values[3], Path(values[5]), Path(values[7])


def _absolute_directory(value, label):
    try:
        path = Path(os.path.abspath(os.fspath(value)))
        if not path.is_absolute() or not path.is_dir():
            raise ValueError(label)
        return path
    except (OSError, TypeError, ValueError) as exc:
        raise P10SafetyAnalysisV2CommandError(
            f"Worker {label} is invalid", failure_code="invalid_request",
        ) from exc


def _emit_failure(emitter, code, terminal) -> None:
    if emitter is None:
        return
    try:
        emitter.failure(code, terminal)
    except Exception:
        pass


if __name__ == "__main__":  # pragma: no cover - exercised as a module
    raise SystemExit(main())


__all__ = [
    "EXIT_FAILURE", "EXIT_INTERNAL", "EXIT_OK", "EXIT_USAGE", "main",
    "run_p10_safety_analysis_worker_v2",
]
