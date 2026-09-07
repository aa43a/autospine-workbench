"""Explicit source-bound semantic review; never production authorization.

Callers validate candidate closure and source bytes before invoking this compiler.
A declaration records what the named reviewer submitted, not authenticated identity.
"""
from copy import deepcopy
import unicodedata

from ..resolved_project import canonical_sha256
from .semantic_draft import validate_semantic_draft
from .validation import BenchmarkError

SCHEMA = "autospine.benchmark-semantic-decision/v1"
REQUEST_SCHEMA = "autospine.benchmark-semantic-review-request/v1"
CHECKS = {"layer_identity", "semantics_checked", "sides_checked"}
PAIRED_SEMANTICS = {"body.arm.upper", "body.arm.lower", "body.hand",
                    "body.leg.upper", "body.leg.lower", "body.foot"}


def _text(value, maximum):
    if type(value) is not str or not value.strip() or len(value) > maximum \
            or any(unicodedata.category(char).startswith("C") for char in value):
        raise BenchmarkError("benchmark_semantic_review_text_invalid")


def validate_semantic_review_request(candidate, draft, request):
    validate_semantic_draft(candidate, draft)
    fields = {"schema", "candidate_sha256", "draft_sha256", "authority", "reviewer",
              "action", "reason", "checks"}
    if type(request) is not dict or set(request) != fields \
            or request["schema"] != REQUEST_SCHEMA or request["authority"] != "none":
        raise BenchmarkError("benchmark_semantic_review_request_invalid")
    if request["candidate_sha256"] != canonical_sha256(candidate) \
            or request["draft_sha256"] != canonical_sha256(draft):
        raise BenchmarkError("benchmark_semantic_review_source_mismatch")
    if request["action"] not in ("accept", "reject"):
        raise BenchmarkError("benchmark_semantic_review_action_invalid")
    _text(request["reviewer"], 128)
    _text(request["reason"], 2000)
    checks = request["checks"]
    if type(checks) is not dict or set(checks) != CHECKS \
            or any(type(value) is not bool for value in checks.values()):
        raise BenchmarkError("benchmark_semantic_review_checks_invalid")
    if request["action"] == "accept":
        if not all(checks.values()):
            raise BenchmarkError("benchmark_semantic_review_checks_incomplete")
        _require_complete(candidate, draft)
    return deepcopy(request)


def _require_complete(candidate, draft):
    layers = {row["layer_id"]: row for row in candidate["layers"]}
    for row in draft["records"]:
        if row["disposition"] == "undecided":
            raise BenchmarkError("benchmark_semantic_review_layer_undecided")
        if row["disposition"] == "exclude":
            if not row["notes"].strip():
                raise BenchmarkError("benchmark_semantic_review_exclusion_reason_required")
            continue
        if layers[row["layer_id"]]["observed"]["empty"]:
            raise BenchmarkError("benchmark_semantic_review_empty_layer_included")
        if row["semantic"] is None:
            raise BenchmarkError("benchmark_semantic_review_semantic_required")
        if row["semantic"] in PAIRED_SEMANTICS and row["side"] == "unknown":
            raise BenchmarkError("benchmark_semantic_review_side_required")


def build_semantic_decision(candidate, draft, request):
    request = validate_semantic_review_request(candidate, draft, request)
    return {
        "schema": SCHEMA,
        "source_candidate_sha256": canonical_sha256(candidate),
        "source_draft_sha256": canonical_sha256(draft),
        "source_request_sha256": canonical_sha256(request),
        "action": request["action"],
        "semantic_status": "reviewed_accepted" if request["action"] == "accept" else "reviewed_rejected",
        "reviewer": request["reviewer"], "reason": request["reason"],
        "checks": deepcopy(request["checks"]), "decision_source": "human_explicit",
        "scope": "benchmark_semantics_only", "authority": "none",
    }


def validate_semantic_decision(candidate, draft, request, decision):
    expected = build_semantic_decision(candidate, draft, request)
    if type(decision) is not dict or canonical_sha256(decision) != canonical_sha256(expected):
        raise BenchmarkError("benchmark_semantic_decision_mismatch")
    return deepcopy(expected)
