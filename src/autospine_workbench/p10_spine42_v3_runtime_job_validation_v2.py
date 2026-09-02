"""Strict validators and literals for P10.7b v2 runtime job journals."""

from __future__ import annotations

from collections.abc import Mapping
import re

from .manifest_artifacts import require_safe_token
from .resolved_project import canonical_sha256
from .spine42_contract import SPINE_RUNTIME_PACKAGE, SPINE_RUNTIME_VERSION

REQUEST_FORMAT = "autospine-p10-spine42-v3-runtime-job-request-v2"
EVENT_FORMAT = "autospine-p10-spine42-v3-runtime-job-event-v2"
JOB_ID_DOMAIN = "autospine-p10-spine42-v3-runtime-job-id/v2"
EVENT_ID_DOMAIN = "autospine-p10-spine42-v3-runtime-job-event-id/v2"
STATUSES = frozenset({
    "queued", "running", "completed", "failed_retryable",
    "interrupted_retryable", "failed_terminal",
})
TERMINAL = frozenset(STATUSES - {"queued", "running"})
STAGE_ORDER = (
    "queued", "exact_source_readback", "runtime_reverified", "capturing",
    "evidence_compiling", "publishing", "parent_exact_readback", "completed",
)
LATE_STAGES = frozenset({"publishing", "parent_exact_readback"})
PAYLOAD_FIELDS = {
    "candidate_id", "entry_sha256", "authorization_id", "retry_of_job_id",
    "explicit_runtime_license_confirmation", "explicit_run_confirmation",
}
DOCUMENT_FIELDS = PAYLOAD_FIELDS | {
    "format", "format_version", "source", "runtime", "browser",
}
EVENT_FIELDS = {
    "format", "format_version", "job_id", "sequence",
    "previous_event_sha256", "status", "stage", "progress", "failure_code",
    "resume_mode", "capture_address", "result", "event_sha256",
}
ADDRESS_FIELDS = {
    "project_id", "skeleton_json_sha256", "spine42_v3_bundle_sha256",
    "capture_bundle_sha256",
}
SHA_PATTERN = re.compile(r"^[0-9a-f]{64}$")
AUTH_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{7,127}$")
FAILURE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class P10Spine42V3RuntimeJobValidationV2Error(ValueError):
    pass


def require_request_document(row):
    if set(row) != DOCUMENT_FIELDS or row.get("format") != REQUEST_FORMAT \
            or type(row.get("format_version")) is not int \
            or row.get("format_version") != 2:
        _fail("Runtime job request contract is invalid")
    for name in ("candidate_id", "entry_sha256"):
        require_sha(row.get(name))
    authorization = row.get("authorization_id")
    if type(authorization) is not str \
            or AUTH_PATTERN.fullmatch(authorization) is None \
            or row.get("explicit_runtime_license_confirmation") is not True \
            or row.get("explicit_run_confirmation") is not True:
        _fail("Runtime job authorization is invalid")
    retry = row.get("retry_of_job_id")
    if retry is not None:
        require_sha(retry)
    source = exact_object(row.get("source"), {
        "project_id", "clip_id", "skeleton_json_sha256",
        "spine42_v3_bundle_sha256",
    })
    require_token(source["project_id"]); require_token(source["clip_id"])
    require_sha(source["skeleton_json_sha256"])
    require_sha(source["spine42_v3_bundle_sha256"])
    runtime = exact_object(row.get("runtime"), {
        "package", "version", "javascript_sha256", "stylesheet_sha256",
        "package_json_sha256", "license_sha256",
        "license_file_presence_is_authorization",
    })
    if runtime["package"] != SPINE_RUNTIME_PACKAGE \
            or runtime["version"] != SPINE_RUNTIME_VERSION \
            or runtime["license_file_presence_is_authorization"] is not False:
        _fail("Runtime job runtime profile is invalid")
    for name in ("javascript_sha256", "stylesheet_sha256",
                 "package_json_sha256", "license_sha256"):
        require_sha(runtime[name])
    browser = exact_object(row.get("browser"), {
        "family", "reported_version", "version_output_sha256",
        "executable_sha256", "size_bytes",
    })
    require_token(browser["family"])
    version = browser["reported_version"]
    if type(version) is not str or not 1 <= len(version) <= 128 \
            or version != version.strip() \
            or any(ord(character) < 32 for character in version):
        _fail("Runtime job browser identity is invalid")
    require_sha(browser["version_output_sha256"])
    require_sha(browser["executable_sha256"])
    if type(browser["size_bytes"]) is not int \
            or not 1 <= browser["size_bytes"] <= 512 * 1024 * 1024:
        _fail("Runtime job browser size is invalid")
    return row


def require_event_document(row):
    if set(row) != EVENT_FIELDS or row.get("format") != EVENT_FORMAT \
            or type(row.get("format_version")) is not int \
            or row.get("format_version") != 2:
        _fail("Runtime job event contract is invalid")
    require_sha(row.get("job_id")); require_optional_sha(
        row.get("previous_event_sha256"))
    require_sha(row.get("event_sha256"))
    if type(row.get("sequence")) is not int \
            or not 1 <= row["sequence"] <= 10_000 \
            or type(row.get("status")) is not str \
            or row["status"] not in STATUSES \
            or type(row.get("stage")) is not str \
            or row["stage"] not in STAGE_ORDER:
        _fail("Runtime job event state is invalid")
    progress = exact_object(row.get("progress"), {"current", "total"})
    if type(progress["current"]) is not int \
            or type(progress["total"]) is not int \
            or not 0 <= progress["current"] <= progress["total"] \
            or not 1 <= progress["total"] <= 2_000:
        _fail("Runtime job progress is invalid")
    address = row.get("capture_address")
    if row["stage"] in LATE_STAGES:
        require_capture_address(address)
    elif address is not None:
        _fail("Runtime job capture address is premature")
    _require_status(row, progress, address)
    payload = {key: value for key, value in row.items()
               if key != "event_sha256"}
    if row["event_sha256"] != canonical_sha256({
        "domain": EVENT_ID_DOMAIN, "event": payload,
    }):
        _fail("Runtime job event seal is invalid")
    return row


def _require_status(row, progress, address):
    status = row["status"]
    if status in {"queued", "running"}:
        if row["failure_code"] is not None \
                or row["resume_mode"] is not None \
                or row["result"] is not None:
            _fail("Active runtime job event overclaims authority")
        if (status == "queued" and row["stage"] != "queued") \
                or (status == "running" and row["stage"] in {
                    "queued", "completed",
                }):
            _fail("Active runtime job stage is invalid")
    elif status == "completed":
        if row["stage"] != "completed" \
                or progress != {"current": 1, "total": 1} \
                or row["failure_code"] is not None \
                or row["resume_mode"] is not None or address is not None:
            _fail("Completed runtime job event is invalid")
        require_capture_address(row["result"])
    else:
        if row["stage"] == "completed":
            _fail("Failed runtime job stage is invalid")
        failure = row.get("failure_code")
        if type(failure) is not str \
                or FAILURE_PATTERN.fullmatch(failure) is None \
                or row["result"] is not None:
            _fail("Failed runtime job event is invalid")
        if status in {"failed_retryable", "interrupted_retryable"}:
            if row["resume_mode"] != "new_authorization":
                _fail("Retryable runtime job recovery mode is invalid")
        elif row["resume_mode"] is not None:
            _fail("Terminal runtime job cannot declare recovery")


def require_capture_address(value):
    row = exact_object(value, ADDRESS_FIELDS)
    require_token(row["project_id"])
    for name in ADDRESS_FIELDS - {"project_id"}:
        require_sha(row[name])
    return row


def exact_object(value, fields):
    if not isinstance(value, Mapping) or set(value) != fields:
        _fail("Runtime job object fields are invalid")
    return value


def require_sha(value):
    if type(value) is not str or SHA_PATTERN.fullmatch(value) is None:
        _fail("Runtime job SHA-256 is invalid")
    return value


def require_optional_sha(value):
    if value is not None:
        require_sha(value)


def require_token(value):
    try:
        return require_safe_token(value, "Runtime job token")
    except Exception as exc:
        raise P10Spine42V3RuntimeJobValidationV2Error(
            "Runtime job token is invalid") from exc


def _fail(message):
    raise P10Spine42V3RuntimeJobValidationV2Error(message)


__all__ = [
    "ADDRESS_FIELDS", "AUTH_PATTERN", "EVENT_FORMAT", "EVENT_ID_DOMAIN",
    "JOB_ID_DOMAIN", "LATE_STAGES", "PAYLOAD_FIELDS", "REQUEST_FORMAT",
    "SHA_PATTERN", "STAGE_ORDER", "STATUSES", "TERMINAL",
    "P10Spine42V3RuntimeJobValidationV2Error", "require_capture_address",
    "require_event_document", "require_request_document", "require_sha",
]
