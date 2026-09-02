"""Fixed child entry for CPU-heavy automatic P10.5d v2 compilation."""

from __future__ import annotations

from contextlib import redirect_stdout
import json
from pathlib import Path
import sys

from .p10_capture_job_store import P10CaptureJobStore
from .p10_dynamic_seam_commands_v2 import (
    compile_body_sway_dynamic_seam_probe_v2_command,
)
from .p10_dynamic_seam_job_v2 import P10DynamicSeamJobStoreV2
from .project_store import ProjectStore


class _Jobs:
    def __init__(self, state_root):
        self._store = P10CaptureJobStore(state_root)

    def get(self, job_id):
        return self._store.load(job_id).public_document()


def run_worker(run_id, state_root, workspace_root, *, stream=None):
    """Publish only the three immutable bundle files; never write events."""

    output = stream or sys.stdout.buffer
    try:
        state, workspace = Path(state_root), Path(workspace_root)
        snapshot = P10DynamicSeamJobStoreV2(state).load(run_id)
        request = snapshot.request
        if snapshot.status != "running":
            raise RuntimeError("stale request")
        _emit(output, "started", run_id)
        with redirect_stdout(sys.stderr):
            result = compile_body_sway_dynamic_seam_probe_v2_command(
                _Jobs(state), ProjectStore(workspace, state_root=state),
                request["project_id"], request["safety_run_id"],
                continuous_proof_sha256=
                    request["continuous_proof_sha256"],
                reviewed_set_sha256=request["reviewed_set_sha256"],
                reviewed_set_bundle_sha256=
                    request["reviewed_set_bundle_sha256"],
                on_progress=lambda stage, current, total: _emit(
                    output, "progress", run_id, stage=stage,
                    current=current, total=total,
                ),
            )
        document = result.document
        _emit(output, "result", run_id, result={
            "project_id": result.project_id,
            "clip_id": result.clip_id,
            "probe_sha256": result.probe_sha256,
            "bundle_sha256": result.bundle_sha256,
            "source_set_sha256": document["source_set_sha256"],
            "source_document_sha256":
                document["source_document_sha256"],
            "probe_status": document["probe_status"],
        })
        return 0
    except Exception:
        try:
            _emit(output, "failure", run_id,
                  failure_code="compile_failed", terminal=False)
        except Exception:
            pass
        return 2


def _emit(stream, kind, run_id, **fields):
    raw = json.dumps({"protocol": "autospine-p10-dynamic-seam-worker/v2",
                      "type": kind, "run_id": run_id, **fields},
                     sort_keys=True, separators=(",", ":")).encode() + b"\n"
    if len(raw) > 4096:
        raise RuntimeError("worker message excessive")
    stream.write(raw)
    stream.flush()


def main(argv=None):
    values = list(sys.argv[1:] if argv is None else argv)
    if len(values) != 6 or values[0] != "--run-id" \
            or values[2] != "--state-root" \
            or values[4] != "--workspace-root":
        return 64
    return run_worker(values[1], Path(values[3]), Path(values[5]))


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main", "run_worker"]
