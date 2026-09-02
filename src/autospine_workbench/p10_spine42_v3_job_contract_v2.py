"""Canonical append-only request/event contract for automatic P10.7a v2."""

from __future__ import annotations

import json
import re

from .manifest_artifacts import require_safe_token
from .p10_spine42_v3_auto_inputs_v2 import P10Spine42V3AutoInputsV2
from .resolved_project import canonical_sha256

REQUEST_FORMAT = "autospine-p10-spine42-v3-job-request-v2"
EVENT_FORMAT = "autospine-p10-spine42-v3-job-event-v2"
DOCUMENT_NAMES = (
    "skeleton.json", "skeleton.atlas", "skeleton.png",
    "run-manifest.json", "export-report.json",
)
ACTIVE = {"queued", "running"}
TERMINAL = {"completed", "failed_retryable", "failed_terminal"}
STAGE_ORDER = (
    "queued", "exact_motion_instance", "source_adapter", "spine_adapter",
    "publication", "parent_exact_readback", "completed", "failed",
)
STAGES = set(STAGE_ORDER)
_SHA = re.compile(r"^[0-9a-f]{64}$")
_TOKEN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class P10Spine42V3JobV2Error(RuntimeError):
    pass


def request_document(inputs, attempt, previous):
    if type(inputs) is not P10Spine42V3AutoInputsV2 \
            or type(attempt) is not int or not 1 <= attempt <= 10_000 \
            or (attempt == 1) != (previous is None):
        raise P10Spine42V3JobV2Error("P10.7a v2 request is invalid")
    value = {
        "format": REQUEST_FORMAT, "format_version": 2,
        **inputs.identity, "attempt": attempt, "previous_run_id": previous,
    }
    require_request(value)
    return value


def require_request(value):
    expected = {
        "format", "format_version", "job_id", "safety_run_id",
        "dynamic_run_id", "motion_run_id", "project_id",
        "motion_instance_v3_sha256", "motion_instance_v3_bundle_sha256",
        "attempt", "previous_run_id",
    }
    sha_fields = (
        "job_id", "safety_run_id", "dynamic_run_id", "motion_run_id",
        "motion_instance_v3_sha256", "motion_instance_v3_bundle_sha256",
    )
    if type(value) is not dict or set(value) != expected \
            or value.get("format") != REQUEST_FORMAT \
            or value.get("format_version") != 2 \
            or any(_SHA.fullmatch(str(value.get(key))) is None
                   for key in sha_fields) \
            or type(value.get("attempt")) is not int \
            or not 1 <= value["attempt"] <= 10_000 \
            or (value["attempt"] == 1) != (
                value.get("previous_run_id") is None
            ) or value.get("previous_run_id") is not None \
            and _SHA.fullmatch(str(value["previous_run_id"])) is None:
        raise P10Spine42V3JobV2Error(
            "P10.7a v2 request contract is invalid"
        )
    try:
        require_safe_token(value["project_id"], "P10.7a v2 project id")
    except Exception as exc:
        raise P10Spine42V3JobV2Error(
            "P10.7a v2 request token is invalid"
        ) from exc


def require_event(value, run_id, sequence):
    fields = {
        "format", "format_version", "run_id", "sequence",
        "previous_event_sha256", "status", "stage", "progress",
        "failure_code", "result", "event_sha256",
    }
    progress = value.get("progress") if type(value) is dict else None
    if type(value) is not dict or set(value) != fields \
            or value.get("format") != EVENT_FORMAT \
            or value.get("format_version") != 2 \
            or value.get("run_id") != run_id \
            or value.get("sequence") != sequence \
            or value.get("status") not in ACTIVE | TERMINAL \
            or value.get("stage") not in STAGES \
            or type(progress) is not dict \
            or set(progress) != {"current", "total"} \
            or type(progress.get("current")) is not int \
            or type(progress.get("total")) is not int \
            or not 0 <= progress["current"] <= progress["total"] \
            or not 1 <= progress["total"] <= 100 \
            or canonical_sha256({
                "domain": "autospine-p10-spine42-v3-job-event/v2",
                "event": {key: item for key, item in value.items()
                          if key != "event_sha256"},
            }) != value.get("event_sha256"):
        raise P10Spine42V3JobV2Error(
            "P10.7a v2 event contract is invalid"
        )
    _require_status_payload(value, progress)


def _require_status_payload(value, progress):
    status, result = value["status"], value["result"]
    if status == "completed":
        expected = {
            "project_id", "clip_id", "skeleton_json_sha256",
            "bundle_sha256", "run_document_sha256", "report_sha256",
            "inventory", "reused",
        }
        valid = value["stage"] == "completed" \
            and progress == {"current": 1, "total": 1} \
            and type(result) is dict and set(result) == expected \
            and value["failure_code"] is None \
            and all(_SHA.fullmatch(str(result.get(key))) for key in (
                "skeleton_json_sha256", "bundle_sha256",
                "run_document_sha256", "report_sha256",
            )) and result.get("inventory") == list(DOCUMENT_NAMES) \
            and type(result.get("reused")) is bool
        if valid:
            try:
                require_safe_token(result["project_id"],
                                   "P10.7a v2 result project id")
                require_safe_token(result["clip_id"],
                                   "P10.7a v2 result clip id")
            except Exception:
                valid = False
    elif status in {"failed_retryable", "failed_terminal"}:
        valid = result is None and value["stage"] == "failed" \
            and _TOKEN.fullmatch(str(value["failure_code"])) is not None
    else:
        valid = value["failure_code"] is None and result is None \
            and (status != "queued" or value["stage"] == "queued") \
            and (status != "running" or value["stage"] not in {
                "queued", "completed", "failed",
            })
    if not valid:
        raise P10Spine42V3JobV2Error(
            "P10.7a v2 event payload is invalid"
        )


def require_transition(left, right):
    if left is None:
        valid = right["status"] == "queued" \
            and right["previous_event_sha256"] is None
    else:
        allowed = {
            "queued": ACTIVE | TERMINAL, "running": {"running"} | TERMINAL,
            "completed": set(), "failed_retryable": set(),
            "failed_terminal": set(),
        }[left["status"]]
        valid = right["status"] in allowed \
            and right["previous_event_sha256"] == left["event_sha256"]
        if valid and left["status"] == right["status"] == "running":
            old = STAGE_ORDER.index(left["stage"])
            new = STAGE_ORDER.index(right["stage"])
            valid = new in {old, old + 1} and (new != old or (
                left["progress"]["total"] == right["progress"]["total"]
                and left["progress"]["current"]
                <= right["progress"]["current"]))
    if not valid:
        raise P10Spine42V3JobV2Error(
            "P10.7a v2 event transition is invalid"
        )


def run_id(request):
    return canonical_sha256({
        "domain": "autospine-p10-spine42-v3-job-run/v2",
        "request": request,
    })


def require_sha(value):
    if type(value) is not str or _SHA.fullmatch(value) is None:
        raise P10Spine42V3JobV2Error("P10.7a v2 address is invalid")


def canonical_bytes(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      sort_keys=True, separators=(",", ":")).encode()


__all__ = [
    "ACTIVE", "DOCUMENT_NAMES", "EVENT_FORMAT", "P10Spine42V3JobV2Error",
    "REQUEST_FORMAT", "STAGE_ORDER", "TERMINAL", "canonical_bytes",
    "request_document", "require_event", "require_request", "require_sha",
    "require_transition", "run_id",
]
