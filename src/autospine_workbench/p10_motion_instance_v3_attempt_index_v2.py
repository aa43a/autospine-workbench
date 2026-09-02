"""Rebuildable O(1) latest-attempt pointer for P10.6b v2."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import tempfile

from .p10_capture_job_store import _exact_directory, _read
from .resolved_project import canonical_sha256
from .safe_input_files import strict_json_object
from .spine42_bundle_files import (
    existing_exact_child, require_real_directory, sync_directory,
)

NAMESPACE = "body-sway-motion-instance-v3-latest-v2"
FORMAT = "autospine-p10-motion-instance-v3-latest-v2"
_SHA = re.compile(r"^[0-9a-f]{64}$")


class P10MotionInstanceV3AttemptIndexV2Error(RuntimeError):
    pass


def read_motion_instance_v3_latest_v2(
    state_root, job_id, safety_run_id, dynamic_run_id,
):
    parent = _parent(state_root, create=False)
    if parent is None:
        return None
    path = parent / f"{_key(job_id, safety_run_id, dynamic_run_id)}.json"
    if not path.is_file():
        return None
    value = strict_json_object(_read(path, 4096), "P10.6b v2 latest index")
    _require(value, job_id, safety_run_id, dynamic_run_id)
    return value


def write_motion_instance_v3_latest_v2(state_root, request, run_id):
    value = {
        "format": FORMAT, "format_version": 2,
        "job_id": request["job_id"],
        "safety_run_id": request["safety_run_id"],
        "dynamic_run_id": request["dynamic_run_id"],
        "attempt": request["attempt"], "run_id": run_id,
        "previous_run_id": request["previous_run_id"],
    }
    _require(value, value["job_id"], value["safety_run_id"],
             value["dynamic_run_id"])
    parent = _parent(state_root, create=True)
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    temporary = None
    try:
        descriptor, name = tempfile.mkstemp(
            prefix=".latest-", suffix=".tmp", dir=parent,
        )
        temporary = Path(name)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, parent / f"{_key(value['job_id'], value['safety_run_id'], value['dynamic_run_id'])}.json")
        sync_directory(parent)
    except Exception as exc:
        raise P10MotionInstanceV3AttemptIndexV2Error(
            "P10.6b v2 latest index could not be replaced"
        ) from exc
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def _parent(state_root, *, create):
    root = require_real_directory(Path(state_root), "P10.6b v2 state root")
    if not create:
        jobs = existing_exact_child(root, "jobs")
        if jobs is None:
            return None
        found = existing_exact_child(
            require_real_directory(jobs, "P10.6b v2 jobs"), NAMESPACE,
        )
        return None if found is None else require_real_directory(
            found, "P10.6b v2 latest index",
        )
    jobs = _exact_directory(root, "jobs", create=True)
    return _exact_directory(jobs, NAMESPACE, create=True)


def _key(job_id, safety_run_id, dynamic_run_id):
    return canonical_sha256({
        "domain": "autospine-p10-motion-instance-v3-latest/v2",
        "job_id": job_id, "safety_run_id": safety_run_id,
        "dynamic_run_id": dynamic_run_id,
    })


def _require(value, job_id, safety_run_id, dynamic_run_id):
    expected = {
        "format", "format_version", "job_id", "safety_run_id",
        "dynamic_run_id", "attempt", "run_id", "previous_run_id",
    }
    if type(value) is not dict or set(value) != expected \
            or value.get("format") != FORMAT \
            or value.get("format_version") != 2 \
            or value.get("job_id") != job_id \
            or value.get("safety_run_id") != safety_run_id \
            or value.get("dynamic_run_id") != dynamic_run_id \
            or any(_SHA.fullmatch(str(value.get(key))) is None for key in (
                "job_id", "safety_run_id", "dynamic_run_id", "run_id",
            )) or type(value.get("attempt")) is not int \
            or not 1 <= value["attempt"] <= 10_000 \
            or (value["attempt"] == 1) != (
                value.get("previous_run_id") is None
            ) or value.get("previous_run_id") is not None \
            and _SHA.fullmatch(str(value["previous_run_id"])) is None:
        raise P10MotionInstanceV3AttemptIndexV2Error(
            "P10.6b v2 latest index is invalid"
        )


__all__ = [
    "P10MotionInstanceV3AttemptIndexV2Error",
    "read_motion_instance_v3_latest_v2",
    "write_motion_instance_v3_latest_v2",
]
