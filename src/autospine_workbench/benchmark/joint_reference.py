"""Explicit independent benchmark annotations confer no production authority."""
from copy import deepcopy
import unicodedata

from ..resolved_project import canonical_sha256
from .joint_draft import validate_joint_draft

SCHEMA = "autospine.benchmark-joint-reference/v1"
REQUEST_SCHEMA = "autospine.benchmark-joint-reference-request/v1"


def validate_joint_reference_request(candidate, draft, request):
    """Validate a supplied human request; never infer it from a model candidate."""
    validated = validate_joint_draft(candidate, draft)
    keys = {"schema", "candidate_sha256", "draft_sha256", "reviewer", "decision",
            "independent_annotation", "authority"}
    if type(request) is not dict or set(request) != keys \
            or request["schema"] != REQUEST_SCHEMA or request["authority"] != "none" \
            or request["decision"] != "accept" or request["independent_annotation"] is not True \
            or request["candidate_sha256"] != canonical_sha256(candidate) \
            or request["draft_sha256"] != canonical_sha256(draft):
        raise ValueError("benchmark_joint_reference_request_invalid")
    reviewer = request["reviewer"]
    if type(reviewer) is not str or not 1 <= len(reviewer) <= 120 or reviewer != reviewer.strip() \
            or any(unicodedata.category(char).startswith("C") for char in reviewer):
        raise ValueError("benchmark_joint_reference_reviewer_invalid")
    if not any(row["status"] == "observed" for row in validated["records"]):
        raise ValueError("benchmark_joint_reference_observation_required")
    return deepcopy(request)


def build_joint_reference(candidate, draft, request):
    """Retain unmarked/unobservable records exactly; independence is attested."""
    validated = validate_joint_reference_request(candidate, draft, request)
    return {"schema": SCHEMA, "authority": "none", "scope": "benchmark_only",
            "source_candidate_sha256": canonical_sha256(candidate),
            "source_draft_sha256": canonical_sha256(draft),
            "source_request_sha256": canonical_sha256(request),
            "records": deepcopy(draft["records"]), "reviewer": validated["reviewer"],
            "independent_annotation": True}


def validate_joint_reference(candidate, draft, request, document):
    """Replay the exact accepted draft/request closure before reading reference."""
    expected = build_joint_reference(candidate, draft, request)
    if type(document) is not dict or document != expected \
            or canonical_sha256(document) != canonical_sha256(expected):
        raise ValueError("benchmark_joint_reference_mismatch")
    return deepcopy(expected)
