"""Immutable authorization, subject, and retry bindings for P10.7b v2."""

from __future__ import annotations

from .p10_spine42_v3_runtime_job_contract_v2 import (
    P10Spine42V3RuntimeJobRequestV2,
)
from .p10_spine42_v3_runtime_job_files_v2 import (
    canonical_bytes, namespace, optional_json, publish_json, read_json,
)
from .resolved_project import canonical_sha256

AUTHORIZATION_NAMESPACE = "body-sway-spine42-v3-runtime-authorizations-v2"
SUBJECT_NAMESPACE = "body-sway-spine42-v3-runtime-subjects-v2"
RETRY_NAMESPACE = "body-sway-spine42-v3-runtime-retries-v2"
_AUTH_KEY_DOMAIN = "autospine-p10-spine42-v3-runtime-authorization-key/v2"
_SUBJECT_DOMAIN = "autospine-p10-spine42-v3-runtime-subject/v2"
_BINDING_FORMAT = "autospine-p10-spine42-v3-runtime-job-binding-v2"


class P10Spine42V3RuntimeJobBindingV2Error(RuntimeError):
    pass


class P10Spine42V3RuntimeJobBindingConflictV2(
    P10Spine42V3RuntimeJobBindingV2Error
):
    pass


def bind_runtime_job_attempt_v2(root, request, load_job):
    """Validate a retry and atomically bind its immutable identifiers."""
    if type(request) is not P10Spine42V3RuntimeJobRequestV2:
        raise P10Spine42V3RuntimeJobBindingV2Error(
            "Runtime job binding request is invalid")
    _validate_retry(request, load_job)
    authorization = _authorization_spec(request)
    subject = _subject_spec(request)
    auth_current = _read_spec(root, authorization, optional=True)
    subject_current = _read_spec(root, subject, optional=True)
    if auth_current is not None and not _same_spec(
        auth_current, authorization[2]
    ):
        raise P10Spine42V3RuntimeJobBindingConflictV2(
            "Runtime job immutable binding conflicts")
    if subject_current is not None and not _same_spec(
        subject_current, subject[2]
    ):
        raise P10Spine42V3RuntimeJobBindingConflictV2(
            "Runtime job immutable binding conflicts")
    if auth_current is None and subject_current is not None:
        raise P10Spine42V3RuntimeJobBindingConflictV2(
            "Runtime job binding history is incomplete")
    _create_spec(root, authorization, auth_current)
    _create_spec(root, subject, subject_current)


def verify_runtime_job_bindings_v2(root, request):
    """Require every binding to exist exactly; verification never repairs."""
    for spec in (_authorization_spec(request), _subject_spec(request)):
        if not _same_spec(_read_spec(root, spec, optional=False), spec[2]):
            raise P10Spine42V3RuntimeJobBindingConflictV2(
                "Runtime job immutable binding conflicts")


def runtime_job_subject_v2(request):
    row = request.document
    return {"candidate_id": row["candidate_id"],
            "entry_sha256": row["entry_sha256"], "source": row["source"]}


def require_runtime_job_retry_chain_v2(snapshot, load_job):
    """Replay the bounded predecessor chain without mutable latest state."""
    seen, current = {snapshot.job_id}, snapshot
    while current.request.document["retry_of_job_id"] is not None:
        previous_id = current.request.document["retry_of_job_id"]
        if previous_id in seen or len(seen) >= 10_000:
            raise P10Spine42V3RuntimeJobBindingV2Error(
                "Runtime job retry chain is invalid")
        previous = load_job(previous_id)
        if previous.status not in {
            "failed_retryable", "interrupted_retryable",
        } or previous.head["resume_mode"] != "new_authorization" \
                or runtime_job_subject_v2(previous.request) \
                != runtime_job_subject_v2(current.request) \
                or previous.request.document["authorization_id"] \
                == current.request.document["authorization_id"]:
            raise P10Spine42V3RuntimeJobBindingV2Error(
                "Runtime job retry chain is invalid")
        seen.add(previous_id)
        current = previous


def _validate_retry(request, load_job):
    row, prior_id = request.document, request.document["retry_of_job_id"]
    if prior_id is None:
        return
    prior = load_job(prior_id)
    if prior.status not in {"failed_retryable", "interrupted_retryable"} \
            or prior.head["resume_mode"] != "new_authorization" \
            or prior.request.document["authorization_id"] == row["authorization_id"] \
            or runtime_job_subject_v2(prior.request) != runtime_job_subject_v2(request):
        raise P10Spine42V3RuntimeJobBindingConflictV2(
            "Runtime job retry predecessor is invalid")


def _authorization_spec(request):
    authorization = request.document["authorization_id"]
    key = canonical_sha256({"domain": _AUTH_KEY_DOMAIN,
                            "authorization_id": authorization})
    expected = _binding("authorization", key, request.job_id, {
        "authorization_id": authorization,
    })
    return AUTHORIZATION_NAMESPACE, f"{key}.json", expected


def _subject_spec(request):
    prior = request.document["retry_of_job_id"]
    subject = canonical_sha256({
        "domain": _SUBJECT_DOMAIN, "subject": runtime_job_subject_v2(request),
    })
    if prior is None:
        expected = _binding("subject_root", subject, request.job_id, {
            "subject_sha256": subject,
        })
        return SUBJECT_NAMESPACE, f"{subject}.json", expected
    else:
        expected = _binding("retry", prior, request.job_id, {
            "previous_job_id": prior, "subject_sha256": subject,
        })
        return RETRY_NAMESPACE, f"{prior}.json", expected


def _read_spec(root, spec, *, optional):
    namespace_name, name, _ = spec
    parent = namespace(root, namespace_name, create=optional)
    return optional_json(parent, name) if optional else read_json(parent, name)


def _create_spec(root, spec, current):
    namespace_name, name, expected = spec
    parent = namespace(root, namespace_name, create=True)
    if current is None:
        publish_json(parent, name, expected)
        current = read_json(parent, name)
    if not _same_spec(current, expected):
        raise P10Spine42V3RuntimeJobBindingConflictV2(
            "Runtime job immutable binding conflicts")


def _same_spec(current, expected):
    return type(current.get("format_version")) is int \
        and canonical_bytes(current) == canonical_bytes(expected)


def _binding(kind, key, job_id, values):
    return {"format": _BINDING_FORMAT, "format_version": 2,
            "kind": kind, "key_sha256": key, "job_id": job_id, **values}


__all__ = [
    "AUTHORIZATION_NAMESPACE", "P10Spine42V3RuntimeJobBindingConflictV2",
    "P10Spine42V3RuntimeJobBindingV2Error", "bind_runtime_job_attempt_v2",
    "require_runtime_job_retry_chain_v2", "runtime_job_subject_v2",
    "verify_runtime_job_bindings_v2",
]
