"""Small real-store fixtures for P10.7b v2 candidate tests."""

from __future__ import annotations

from pathlib import Path
import json

from autospine_workbench.p10_spine42_v3_auto_inputs_v2 import (
    P10Spine42V3AutoInputsV2,
)
from autospine_workbench.p10_spine42_v3_job_contract_v2 import DOCUMENT_NAMES
from autospine_workbench.p10_spine42_v3_job_contract_v2 import (
    canonical_bytes, run_id,
)
from autospine_workbench.p10_spine42_v3_job_v2 import NAMESPACE
from autospine_workbench.resolved_project import canonical_sha256


def sha(character):
    return character * 64


def inputs(*, upstream="1234", project="sample", source="56"):
    return P10Spine42V3AutoInputsV2(
        *(sha(character) for character in upstream), project,
        *(sha(character) for character in source),
    )


def result(*, project="sample", clip="idle", output="789a"):
    values = [sha(character) for character in output]
    return {
        "project_id": project, "clip_id": clip,
        "skeleton_json_sha256": values[0],
        "bundle_sha256": values[1],
        "run_document_sha256": values[2],
        "report_sha256": values[3],
        "inventory": list(DOCUMENT_NAMES), "reused": False,
    }


def complete(store, row, *, project="sample", clip="idle", output="789a"):
    for stage, current in (
        ("exact_motion_instance", 0), ("source_adapter", 0),
        ("spine_adapter", 0), ("publication", 1),
        ("parent_exact_readback", 0),
    ):
        row = store.append(
            row.run_id, "running", stage,
            expected_previous=row.head_sha256, current=current, total=1,
        )
    return store.append(
        row.run_id, "completed", "completed",
        expected_previous=row.head_sha256, current=1, total=1,
        result=result(project=project, clip=clip, output=output),
    )


def fail_retryable(store, row):
    return store.append(
        row.run_id, "failed_retryable", "failed",
        expected_previous=row.head_sha256, failure_code="probe_failed",
    )


def tree_snapshot(root):
    root = Path(root)
    rows = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            rows.append((relative, "alias", None))
        elif path.is_file():
            rows.append((relative, "file", path.read_bytes()))
        elif path.is_dir():
            rows.append((relative, "directory", None))
        else:
            rows.append((relative, "other", None))
    return tuple(rows)


def write_request_only(root, document):
    identifier = run_id(document)
    directory = Path(root) / "jobs" / NAMESPACE / identifier
    (directory / "events").mkdir(parents=True)
    (directory / "request.json").write_bytes(canonical_bytes(document))
    return identifier


def rewrite_run(root, row, *, request_change=None, event_change=None):
    request = json.loads(json.dumps(row.request))
    if request_change is not None:
        request_change(request)
    identifier = run_id(request)
    old = Path(root) / "jobs" / NAMESPACE / row.run_id
    directory = old if identifier == row.run_id else old.rename(
        old.parent / identifier)
    (directory / "request.json").write_bytes(canonical_bytes(request))
    previous = None
    for position, source in enumerate(row.events, 1):
        event = json.loads(json.dumps(source))
        event["run_id"] = identifier
        event["previous_event_sha256"] = previous
        if event_change is not None:
            event_change(event, position)
        payload = {key: value for key, value in event.items()
                   if key != "event_sha256"}
        event["event_sha256"] = canonical_sha256({
            "domain": "autospine-p10-spine42-v3-job-event/v2",
            "event": payload,
        })
        previous = event["event_sha256"]
        (directory / "events" / f"{position:06d}.json").write_bytes(
            canonical_bytes(event))
    return identifier


def contains_path_key(value):
    if isinstance(value, dict):
        return any(
            key == "path" or key.endswith("_path") or contains_path_key(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(contains_path_key(item) for item in value)
    return False
