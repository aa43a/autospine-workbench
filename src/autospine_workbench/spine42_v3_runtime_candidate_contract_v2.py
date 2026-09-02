"""Canonical, path-free P10.7b v2 runtime candidate entries."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import json
import re

from .manifest_artifacts import require_safe_token
from .p10_spine42_v3_job_contract_v2 import DOCUMENT_NAMES
from .p10_spine42_v3_job_v2 import P10Spine42V3JobSnapshotV2
from .resolved_project import canonical_sha256

CANDIDATE_FORMAT = "autospine-p10-spine42-v3-runtime-candidate-v2"
CANDIDATE_ID_DOMAIN = "autospine-p10-spine42-v3-runtime-candidate-id/v2"
ENTRY_ID_DOMAIN = "autospine-p10-spine42-v3-runtime-entry-id/v2"
_SHA = re.compile(r"^[0-9a-f]{64}$")
_UPSTREAM = ("job_id", "safety_run_id", "dynamic_run_id", "motion_run_id")
_OUTPUT = {
    "project_id", "clip_id", "skeleton_json_sha256", "bundle_sha256",
    "run_document_sha256", "report_sha256", "inventory", "reused",
}


class Spine42V3RuntimeCandidateContractV2Error(ValueError):
    """Raised when a candidate entry is not the exact v2 contract."""


@dataclass(frozen=True, slots=True)
class Spine42V3RuntimeCandidateV2:
    """One immutable completion plus a separately sealed head assertion."""

    _canonical_json: str = field(repr=False)

    @classmethod
    def from_completed_head(cls, row):
        if type(row) is not P10Spine42V3JobSnapshotV2 \
                or row.status != "completed" or not row.events:
            _fail("Runtime candidate is not a completed P10.7a v2 head")
        request, output = row.request, row.events[-1].get("result")
        completion = {
            "spine_run_id": row.run_id,
            "spine_head_event_sha256": row.head_sha256,
            "attempt": request["attempt"],
            "upstream": {key: request[key] for key in _UPSTREAM},
            "project_id": request["project_id"],
            "clip_id": output.get("clip_id") if type(output) is dict else None,
            "motion_source": {
                "motion_instance_v3_sha256":
                    request["motion_instance_v3_sha256"],
                "motion_instance_v3_bundle_sha256":
                    request["motion_instance_v3_bundle_sha256"],
            },
            "output": _copy(output),
        }
        candidate_id = canonical_sha256({
            "domain": CANDIDATE_ID_DOMAIN, "completion": completion,
        })
        current_head = {
            "spine_run_id": row.run_id,
            "spine_head_event_sha256": row.head_sha256,
            "attempt": request["attempt"], "status": "completed",
        }
        eligibility = {
            "candidate_id": candidate_id, "current_head": current_head,
            "eligible": True,
        }
        document = {
            "format": CANDIDATE_FORMAT, "format_version": 2,
            "candidate_id": candidate_id,
            "entry_sha256": canonical_sha256({
                "domain": ENTRY_ID_DOMAIN, "eligibility": eligibility,
            }),
            "completion": completion, "current_head": current_head,
            "eligible": True, "runner_execution_authorized": False,
            "publication_authorized": False,
        }
        return cls.from_document(document)

    @classmethod
    def from_document(cls, document):
        try:
            row = _copy(_object(document))
            _require_document(row)
        except Spine42V3RuntimeCandidateContractV2Error:
            raise
        except (KeyError, TypeError, ValueError) as exc:
            raise Spine42V3RuntimeCandidateContractV2Error(
                "Runtime candidate contract is invalid") from exc
        return cls(_canonical(row))

    @property
    def document(self):
        return json.loads(self._canonical_json)

    @property
    def candidate_id(self):
        return self.document["candidate_id"]

    @property
    def entry_sha256(self):
        return self.document["entry_sha256"]

    @property
    def spine_run_id(self):
        return self.document["completion"]["spine_run_id"]

    def public_document(self):
        return self.document


def _require_document(row):
    fields = {
        "format", "format_version", "candidate_id", "entry_sha256",
        "completion", "current_head", "eligible",
        "runner_execution_authorized", "publication_authorized",
    }
    if set(row) != fields or type(row.get("format")) is not str \
            or row.get("format") != CANDIDATE_FORMAT \
            or type(row.get("format_version")) is not int \
            or row.get("format_version") != 2 \
            or row.get("eligible") is not True \
            or row.get("runner_execution_authorized") is not False \
            or row.get("publication_authorized") is not False:
        _fail("Runtime candidate contract is invalid")
    completion = _object(row["completion"])
    if set(completion) != {
        "spine_run_id", "spine_head_event_sha256", "attempt", "upstream",
        "project_id", "clip_id", "motion_source", "output",
    }:
        _fail("Runtime candidate completion is invalid")
    _sha(completion["spine_run_id"]); _sha(
        completion["spine_head_event_sha256"])
    if type(completion["attempt"]) is not int \
            or not 1 <= completion["attempt"] <= 10_000:
        _fail("Runtime candidate attempt is invalid")
    upstream = _object(completion["upstream"])
    if set(upstream) != set(_UPSTREAM):
        _fail("Runtime candidate upstream is invalid")
    for value in upstream.values():
        _sha(value)
    _token(completion["project_id"]); _token(completion["clip_id"])
    source = _object(completion["motion_source"])
    if set(source) != {
        "motion_instance_v3_sha256", "motion_instance_v3_bundle_sha256",
    }:
        _fail("Runtime candidate motion source is invalid")
    for value in source.values():
        _sha(value)
    _require_output(completion["output"], completion)
    candidate_id = canonical_sha256({
        "domain": CANDIDATE_ID_DOMAIN, "completion": completion,
    })
    if row.get("candidate_id") != candidate_id:
        _fail("Runtime candidate identity differs")
    head = _object(row["current_head"])
    if set(head) != {
        "spine_run_id", "spine_head_event_sha256", "attempt", "status",
    } or type(head.get("attempt")) is not int \
            or type(head.get("status")) is not str or head != {
        "spine_run_id": completion["spine_run_id"],
        "spine_head_event_sha256": completion["spine_head_event_sha256"],
        "attempt": completion["attempt"], "status": "completed",
    }:
        _fail("Runtime candidate current head differs")
    eligibility = {
        "candidate_id": candidate_id, "current_head": head,
        "eligible": True,
    }
    if row.get("entry_sha256") != canonical_sha256({
        "domain": ENTRY_ID_DOMAIN, "eligibility": eligibility,
    }):
        _fail("Runtime candidate entry identity differs")


def _require_output(output, completion):
    output = _object(output)
    if set(output) != _OUTPUT \
            or output.get("project_id") != completion["project_id"] \
            or output.get("clip_id") != completion["clip_id"] \
            or output.get("inventory") != list(DOCUMENT_NAMES) \
            or type(output.get("reused")) is not bool:
        _fail("Runtime candidate output is invalid")
    for key in ("skeleton_json_sha256", "bundle_sha256",
                "run_document_sha256", "report_sha256"):
        _sha(output.get(key))


def _object(value):
    if not isinstance(value, Mapping):
        _fail("Runtime candidate value must be an object")
    return value


def _sha(value):
    if type(value) is not str or _SHA.fullmatch(value) is None:
        _fail("Runtime candidate SHA-256 is invalid")


def _token(value):
    try:
        require_safe_token(value, "Runtime candidate token")
    except Exception as exc:
        raise Spine42V3RuntimeCandidateContractV2Error(
            "Runtime candidate token is invalid") from exc


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False,
                      sort_keys=True, separators=(",", ":"))


def _copy(value):
    return json.loads(_canonical(value))


def _fail(message):
    raise Spine42V3RuntimeCandidateContractV2Error(message)


__all__ = [
    "CANDIDATE_FORMAT", "CANDIDATE_ID_DOMAIN", "ENTRY_ID_DOMAIN",
    "Spine42V3RuntimeCandidateContractV2Error",
    "Spine42V3RuntimeCandidateV2",
]
