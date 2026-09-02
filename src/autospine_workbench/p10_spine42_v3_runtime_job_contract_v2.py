"""Path-free request and event contract for authorized P10.7b v2 jobs."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import json

from .browser_executable_snapshot import BrowserExecutableSnapshot
from .resolved_project import canonical_sha256
from .spine42_contract import SPINE_RUNTIME_PACKAGE, SPINE_RUNTIME_VERSION
from .spine42_runtime_inputs import Spine42RuntimePackage
from .p10_spine42_v3_runtime_job_validation_v2 import (
    EVENT_FORMAT, EVENT_ID_DOMAIN, JOB_ID_DOMAIN, LATE_STAGES,
    PAYLOAD_FIELDS, REQUEST_FORMAT, STAGE_ORDER, STATUSES, TERMINAL,
    P10Spine42V3RuntimeJobValidationV2Error, require_event_document,
    require_request_document,
)


class P10Spine42V3RuntimeJobContractV2Error(ValueError):
    """Raised when a v2 authorization journal value is not exact."""


@dataclass(frozen=True, slots=True)
class P10Spine42V3RuntimeJobRequestV2:
    _canonical_json: str = field(repr=False)

    @classmethod
    def expand(cls, payload: Mapping, *, project_id, clip_id,
               skeleton_json_sha256, spine42_v3_bundle_sha256,
               runtime, browser):
        """Expand a browser payload with server-observed identities.

        The opaque candidate/entry hashes do not grant authority.  A future
        manager must exact-revalidate its catalog entry before calling this
        constructor and again before ``store.create``.
        """
        if type(runtime) is not Spine42RuntimePackage \
                or type(browser) is not BrowserExecutableSnapshot:
            raise P10Spine42V3RuntimeJobContractV2Error(
                "Runtime job environment identity is invalid")
        try:
            row = _object(payload)
            if set(row) != PAYLOAD_FIELDS:
                raise P10Spine42V3RuntimeJobContractV2Error(
                    "Runtime job browser fields are invalid")
            document = {
                "format": REQUEST_FORMAT, "format_version": 2,
                **_copy(row),
                "source": {
                    "project_id": project_id, "clip_id": clip_id,
                    "skeleton_json_sha256": skeleton_json_sha256,
                    "spine42_v3_bundle_sha256": spine42_v3_bundle_sha256,
                },
                "runtime": {
                    "package": SPINE_RUNTIME_PACKAGE,
                    "version": SPINE_RUNTIME_VERSION,
                    "javascript_sha256": runtime.javascript_sha256,
                    "stylesheet_sha256": runtime.stylesheet_sha256,
                    "package_json_sha256": runtime.package_json_sha256,
                    "license_sha256": runtime.license_sha256,
                    "license_file_presence_is_authorization": False,
                },
                "browser": {
                    "family": browser.family,
                    "reported_version": browser.reported_version,
                    "version_output_sha256": browser.version_output_sha256,
                    "executable_sha256": browser.executable_sha256,
                    "size_bytes": browser.size_bytes,
                },
            }
            return cls.from_document(document)
        except P10Spine42V3RuntimeJobContractV2Error:
            raise
        except (TypeError, ValueError) as exc:
            raise P10Spine42V3RuntimeJobContractV2Error(
                "Runtime job browser payload is invalid") from exc

    @classmethod
    def from_document(cls, document):
        try:
            row = _copy(_object(document))
            require_request_document(row)
        except (P10Spine42V3RuntimeJobValidationV2Error,
                TypeError, ValueError) as exc:
            raise P10Spine42V3RuntimeJobContractV2Error(str(exc)) from exc
        return cls(_canonical(row))

    @property
    def document(self):
        return json.loads(self._canonical_json)

    @property
    def canonical_bytes(self):
        return self._canonical_json.encode("utf-8")

    @property
    def job_id(self):
        return canonical_sha256({"domain": JOB_ID_DOMAIN,
                                 "request": self.document})


@dataclass(frozen=True, slots=True)
class P10Spine42V3RuntimeJobEventV2:
    _canonical_json: str = field(repr=False)

    @classmethod
    def build(cls, job_id, sequence, previous_event_sha256, status, stage, *,
              current=0, total=1, failure_code=None, resume_mode=None,
              capture_address=None, result=None):
        payload = {
            "format": EVENT_FORMAT, "format_version": 2,
            "job_id": job_id, "sequence": sequence,
            "previous_event_sha256": previous_event_sha256,
            "status": status, "stage": stage,
            "progress": {"current": current, "total": total},
            "failure_code": failure_code, "resume_mode": resume_mode,
            "capture_address": _copy(capture_address), "result": _copy(result),
        }
        document = dict(payload)
        document["event_sha256"] = canonical_sha256({
            "domain": EVENT_ID_DOMAIN, "event": payload,
        })
        return cls.from_document(document)

    @classmethod
    def from_document(cls, document):
        try:
            row = _copy(_object(document))
            require_event_document(row)
        except (P10Spine42V3RuntimeJobValidationV2Error,
                TypeError, ValueError) as exc:
            raise P10Spine42V3RuntimeJobContractV2Error(str(exc)) from exc
        return cls(_canonical(row))

    @property
    def document(self):
        return json.loads(self._canonical_json)

    @property
    def canonical_bytes(self):
        return self._canonical_json.encode("utf-8")

    @property
    def event_sha256(self):
        return self.document["event_sha256"]

    def public_document(self):
        return self.document


def require_runtime_job_transition_v2(previous, event):
    if type(event) is not P10Spine42V3RuntimeJobEventV2:
        _fail("Runtime job event type is invalid")
    right = event.document
    if previous is None:
        valid = right["sequence"] == 1 and right["status"] == "queued" \
            and right["stage"] == "queued" \
            and right["previous_event_sha256"] is None
    elif type(previous) is not P10Spine42V3RuntimeJobEventV2:
        valid = False
    else:
        left = previous.document
        valid = left["status"] not in TERMINAL \
            and left["job_id"] == right["job_id"] \
            and right["sequence"] == left["sequence"] + 1 \
            and right["previous_event_sha256"] == previous.event_sha256
        if valid and right["status"] == "running":
            old = STAGE_ORDER.index(left["stage"])
            new = STAGE_ORDER.index(right["stage"])
            valid = new == old + 1 or (
                left["status"] == "running"
                and left["stage"] == right["stage"] == "capturing")
            if valid and right["stage"] == "capturing":
                before, after = left["progress"], right["progress"]
                if left["stage"] == "capturing":
                    valid = after["total"] == before["total"] \
                        and after["current"] == before["current"] + 1
                else:
                    valid = after["current"] == 0
            if valid and right["stage"] == "evidence_compiling":
                valid = left["stage"] == "capturing" \
                    and left["progress"]["current"] == left["progress"]["total"]
        elif valid and right["status"] == "completed":
            valid = left["status"] == "running" \
                and left["stage"] == "parent_exact_readback" \
                and right["stage"] == "completed"
        elif valid:
            valid = right["status"] in TERMINAL \
                and right["stage"] == left["stage"] \
                and right["progress"] == left["progress"]
        if valid and left["stage"] in LATE_STAGES \
                and right["stage"] in LATE_STAGES | {"completed"}:
            expected = left["capture_address"]
            actual = right["result"] if right["status"] == "completed" \
                else right["capture_address"]
            valid = expected == actual
    if not valid:
        _fail("Runtime job event transition is invalid")


def require_runtime_job_source_binding_v2(request, event):
    """Bind every capture address to this job's immutable P10.7a source."""
    if type(request) is not P10Spine42V3RuntimeJobRequestV2 \
            or type(event) is not P10Spine42V3RuntimeJobEventV2:
        _fail("Runtime job source binding type is invalid")
    source, row = request.document["source"], event.document
    if row["job_id"] != request.job_id:
        _fail("Runtime job source binding job differs")
    address = row["result"] if row["status"] == "completed" \
        else row["capture_address"]
    if address is not None and any(address[name] != source[name] for name in (
        "project_id", "skeleton_json_sha256", "spine42_v3_bundle_sha256",
    )):
        _fail("Runtime job capture address source differs")


def _object(value):
    if not isinstance(value, Mapping):
        _fail("Runtime job value must be an object")
    return value


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      sort_keys=True, separators=(",", ":"))


def _copy(value):
    return None if value is None else json.loads(_canonical(value))


def _fail(message):
    raise P10Spine42V3RuntimeJobContractV2Error(message)


__all__ = [
    "EVENT_FORMAT", "EVENT_ID_DOMAIN", "JOB_ID_DOMAIN", "LATE_STAGES",
    "P10Spine42V3RuntimeJobContractV2Error",
    "P10Spine42V3RuntimeJobEventV2", "P10Spine42V3RuntimeJobRequestV2",
    "REQUEST_FORMAT", "STAGE_ORDER", "STATUSES", "TERMINAL",
    "require_runtime_job_source_binding_v2", "require_runtime_job_transition_v2",
]
