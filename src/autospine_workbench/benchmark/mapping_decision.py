"""Explicit benchmark mapping review records, without production authority.

This pure compiler validates a caller's review declaration, not their identity
or whether visual inspection happened. Entry points must require an explicit
human submission and recheck source bytes before recording a decision. Consumers
select an exact decision address: later records never silently supersede it.
"""
from copy import deepcopy
import unicodedata

from ..resolved_project import canonical_sha256
from .mapping import validate_mapping_candidate
from .validation import BenchmarkError, require_digest

SCHEMA = "autospine.benchmark-mapping-decision/v1"
REQUEST_SCHEMA = "autospine.benchmark-mapping-review-request/v1"
CHECKS = {"same_character", "coordinate_alignment", "mirror_checked"}
_REQUEST_FIELDS = {"schema", "candidate_sha256", "reviewer", "action", "reason",
                   "checks", "authority"}


def _text(value, maximum):
    if type(value) is not str or not 1 <= len(value) <= maximum or not value.strip() \
            or any(unicodedata.category(char).startswith("C") for char in value):
        raise BenchmarkError("benchmark_mapping_review_text_invalid")


def validate_mapping_review_request(candidate, request):
    """Check a review declaration against an already validated candidate."""
    if type(request) is not dict or set(request) != _REQUEST_FIELDS \
            or request["schema"] != REQUEST_SCHEMA or request["authority"] != "none":
        raise BenchmarkError("benchmark_mapping_review_request_invalid")
    require_digest(request["candidate_sha256"])
    if request["candidate_sha256"] != canonical_sha256(candidate):
        raise BenchmarkError("benchmark_mapping_review_candidate_mismatch")
    if request["action"] not in ("accept", "reject"):
        raise BenchmarkError("benchmark_mapping_review_action_invalid")
    _text(request["reviewer"], 128)
    _text(request["reason"], 2000)
    checks = request["checks"]
    if type(checks) is not dict or set(checks) != CHECKS \
            or any(type(value) is not bool for value in checks.values()):
        raise BenchmarkError("benchmark_mapping_review_checks_invalid")
    if request["action"] == "accept" and not all(checks.values()):
        raise BenchmarkError("benchmark_mapping_review_checks_incomplete")
    return deepcopy(request)


def build_mapping_decision(manifest, candidate, request, *, split="development"):
    """Record an explicit accept/reject declaration without changing its inputs."""
    candidate = validate_mapping_candidate(manifest, candidate, split=split)
    request = validate_mapping_review_request(candidate, request)
    return {
        "schema": SCHEMA,
        "dataset_sha256": candidate["dataset_sha256"],
        "character_id": candidate["character_id"],
        "dataset_split": candidate["dataset_split"],
        "source_candidate_sha256": canonical_sha256(candidate),
        "source_request_sha256": canonical_sha256(request),
        "action": request["action"],
        "mapping_status": "reviewed_accepted" if request["action"] == "accept"
                          else "reviewed_rejected",
        "reviewer": request["reviewer"],
        "reason": request["reason"],
        "checks": deepcopy(request["checks"]),
        "decision_source": "human_explicit",
        "scope": "benchmark_mapping_only",
        "authority": "none",
    }


def validate_mapping_decision(manifest, candidate, request, decision, *, split="development"):
    """Recompile all source-bound fields; reject stale, extra or altered data."""
    expected = build_mapping_decision(manifest, candidate, request, split=split)
    if type(decision) is not dict or canonical_sha256(decision) != canonical_sha256(expected):
        raise BenchmarkError("benchmark_mapping_decision_mismatch")
    return deepcopy(expected)
