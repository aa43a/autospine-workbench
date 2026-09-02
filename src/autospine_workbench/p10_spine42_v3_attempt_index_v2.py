"""Rebuildable O(1) latest-attempt pointer for automatic P10.7a v2."""

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

NAMESPACE = "body-sway-spine42-v3-latest-v2"
FORMAT = "autospine-p10-spine42-v3-latest-v2"
_SHA = re.compile(r"^[0-9a-f]{64}$")
_ID_FIELDS = ("job_id", "safety_run_id", "dynamic_run_id", "motion_run_id")


class P10Spine42V3AttemptIndexV2Error(RuntimeError):
    pass


def read_spine42_v3_latest_v2(
    state_root, job_id, safety_run_id, dynamic_run_id, motion_run_id,
):
    ids = (job_id, safety_run_id, dynamic_run_id, motion_run_id)
    parent = _parent(state_root, create=False)
    if parent is None:
        return None
    path = parent / f"{_key(*ids)}.json"
    if not path.is_file():
        return None
    value = strict_json_object(_read(path, 4096), "P10.7a v2 latest index")
    _require(value, *ids)
    return value


def write_spine42_v3_latest_v2(state_root, request, run_id):
    value = {
        "format": FORMAT, "format_version": 2,
        **{key: request[key] for key in _ID_FIELDS},
        "attempt": request["attempt"], "run_id": run_id,
        "previous_run_id": request["previous_run_id"],
    }
    ids = tuple(value[key] for key in _ID_FIELDS)
    _require(value, *ids)
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
        os.replace(temporary, parent / f"{_key(*ids)}.json")
        sync_directory(parent)
    except Exception as exc:
        raise P10Spine42V3AttemptIndexV2Error(
            "P10.7a v2 latest index could not be replaced"
        ) from exc
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def _parent(state_root, *, create):
    root = require_real_directory(Path(state_root), "P10.7a v2 state root")
    if not create:
        jobs = existing_exact_child(root, "jobs")
        if jobs is None:
            return None
        found = existing_exact_child(
            require_real_directory(jobs, "P10.7a v2 jobs"), NAMESPACE,
        )
        return None if found is None else require_real_directory(
            found, "P10.7a v2 latest index",
        )
    jobs = _exact_directory(root, "jobs", create=True)
    return _exact_directory(jobs, NAMESPACE, create=True)


def _key(job_id, safety_run_id, dynamic_run_id, motion_run_id):
    return canonical_sha256({
        "domain": "autospine-p10-spine42-v3-latest/v2",
        "job_id": job_id, "safety_run_id": safety_run_id,
        "dynamic_run_id": dynamic_run_id, "motion_run_id": motion_run_id,
    })


def _require(value, job_id, safety_run_id, dynamic_run_id, motion_run_id):
    expected = {
        "format", "format_version", *_ID_FIELDS,
        "attempt", "run_id", "previous_run_id",
    }
    ids = dict(zip(_ID_FIELDS, (
        job_id, safety_run_id, dynamic_run_id, motion_run_id,
    )))
    if type(value) is not dict or set(value) != expected \
            or value.get("format") != FORMAT \
            or value.get("format_version") != 2 \
            or any(value.get(key) != expected_value
                   for key, expected_value in ids.items()) \
            or any(_SHA.fullmatch(str(value.get(key))) is None
                   for key in (*_ID_FIELDS, "run_id")) \
            or type(value.get("attempt")) is not int \
            or not 1 <= value["attempt"] <= 10_000 \
            or (value["attempt"] == 1) != (
                value.get("previous_run_id") is None
            ) or value.get("previous_run_id") is not None \
            and _SHA.fullmatch(str(value["previous_run_id"])) is None:
        raise P10Spine42V3AttemptIndexV2Error(
            "P10.7a v2 latest index is invalid"
        )


__all__ = [
    "P10Spine42V3AttemptIndexV2Error", "read_spine42_v3_latest_v2",
    "write_spine42_v3_latest_v2",
]
