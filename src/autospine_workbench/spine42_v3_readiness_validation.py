"""Strict path-free validation for P10.7b readiness reports."""

from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any

from .manifest_artifacts import require_safe_token, require_sha256
from .seam_anchor_review_json import require_bounded_json_tree
from .spine42_v3_raster_review_values import domain_sha256


FORMAT = "autospine-spine42-v3-readiness-report"
FORMAT_VERSION = 1
REPORT_DOMAIN = "autospine-spine42-v3-readiness-report/v1"
CHECKPOINT_IDS = (
    "p3_seam_source", "p9_reviewed_motion",
    "p10_5_reviewed_seam_anchor_set", "p10_6b_motion_instance_v3",
    "p10_7a_spine42_v3", "p10_7b_runtime_capture",
    "p10_7b_raster_review", "p6_setup_regression",
)
STATUSES = {
    "verified", "prerequisite_missing", "review_blocked",
    "metrics_rejected", "source_mismatch",
}
SEMANTICS = {
    "scope": "exact-address-read-only-preflight",
    "current_head_discovery": False,
    "external_stage_execution": False,
    "pure_replay_compilation": True,
    "human_review_substitution": False,
    "p6_setup_raster_comparison_included": False,
    "release_authority": False,
}
AUTHORITY = {
    "state_mutation": False, "latest_selection": False,
    "pipeline_execution": False, "human_decision": False,
    "publish": False, "release": False,
}
RELEASE_GATE = {
    "status": "blocked",
    "reason_codes": [
        "bounded_preflight_not_release_authority",
        "p6_setup_golden_comparison_missing",
    ],
}


class Spine42V3ReadinessValidationError(ValueError):
    """Raised when a readiness report overstates or loses evidence."""


def require_spine42_v3_readiness_report(value: Mapping[str, Any]) -> None:
    """Validate fields, derived states, bounded authority, and self hash."""

    try:
        require_bounded_json_tree(value, max_nodes=250_000, max_depth=32)
        root = _object(value, {
            "format", "format_version", "request_sha256", "samples",
            "summary", "semantics", "authority", "status", "release_gate",
            "readiness_report_sha256",
        }, "report")
        if root["format"] != FORMAT \
                or type(root["format_version"]) is not int \
                or root["format_version"] != FORMAT_VERSION:
            _fail("Readiness report version is invalid")
        require_sha256(root["request_sha256"], "Readiness request")
        samples = root["samples"]
        if type(samples) is not list or not 1 <= len(samples) <= 8:
            _fail("Readiness report sample count is invalid")
        parsed = [_sample(row) for row in samples]
        ids = [row["project_id"] for row in parsed]
        if ids != sorted(ids) or len(ids) != len(set(ids)):
            _fail("Readiness report projects are not unique and ordered")
        expected_summary = _summary(parsed)
        ready = expected_summary["blocked_sample_count"] == 0
        if not _same_json(root["summary"], expected_summary) \
                or not _same_json(root["semantics"], SEMANTICS) \
                or not _same_json(root["authority"], AUTHORITY) \
                or not _same_json(root["release_gate"], RELEASE_GATE) \
                or root["status"] != (
                    "ready_for_p6_setup_comparison" if ready
                    else "blocked_prerequisites_or_review"):
            _fail("Readiness report derived fields are inconsistent")
        body = json.loads(json.dumps(root, sort_keys=True, separators=(",", ":")))
        digest = body.pop("readiness_report_sha256")
        if digest != domain_sha256(REPORT_DOMAIN, body):
            _fail("Readiness report self hash is invalid")
    except Spine42V3ReadinessValidationError:
        raise
    except (KeyError, RuntimeError, TypeError, ValueError) as exc:
        raise Spine42V3ReadinessValidationError(
            "Readiness report validation failed"
        ) from exc


def _same_json(left, right):
    """Compare JSON values without Python's bool/int equality aliasing."""

    options = {"sort_keys": True, "separators": (",", ":")}
    return json.dumps(left, **options) == json.dumps(right, **options)


def _sample(value):
    row = _object(value, {
        "project_id", "checkpoints", "next_action_codes", "status",
    }, "sample")
    require_safe_token(row["project_id"], "Readiness project id")
    checkpoints = row["checkpoints"]
    if type(checkpoints) is not list or len(checkpoints) != len(CHECKPOINT_IDS):
        _fail("Readiness checkpoint inventory is invalid")
    parsed = [_checkpoint(item) for item in checkpoints]
    if tuple(item["checkpoint_id"] for item in parsed) != CHECKPOINT_IDS:
        _fail("Readiness checkpoint order is invalid")
    actions = sorted({
        item["next_action_code"] for item in parsed
        if item["next_action_code"] is not None
    })
    ready = all(item["status"] == "verified" for item in parsed[:-1])
    if parsed[-1] != {
        "checkpoint_id": "p6_setup_regression",
        "status": "prerequisite_missing",
        "reason_codes": ["p6_setup_golden_comparison_not_declared"],
        "next_action_code": "compare_setup_case_with_p6_approved_golden",
        "evidence": {},
    } or row["next_action_codes"] != actions or row["status"] != (
        "ready_for_p6_setup_comparison" if ready else "blocked"):
        _fail("Readiness sample derived state is inconsistent")
    return row


def _checkpoint(value):
    row = _object(value, {
        "checkpoint_id", "status", "reason_codes", "next_action_code",
        "evidence",
    }, "checkpoint")
    require_safe_token(row["checkpoint_id"], "Checkpoint id")
    reasons, action = row["reason_codes"], row["next_action_code"]
    expected_status = _evidence_status(
        row["checkpoint_id"], row["evidence"]
    )
    if row["status"] not in STATUSES or type(reasons) is not list \
            or reasons != sorted(set(reasons)) \
            or (row["status"] == "verified") != (not reasons and action is None) \
            or (expected_status is None and row["status"] == "verified") \
            or (expected_status is not None
                and row["status"] != expected_status):
        _fail("Readiness checkpoint state is invalid")
    for reason in reasons:
        require_safe_token(reason, "Readiness reason code")
    if action is not None:
        require_safe_token(action, "Readiness next action")
    return row


def _evidence_status(identifier, value):
    if type(value) is not dict:
        _fail("Readiness checkpoint evidence is invalid")
    if not value:
        return None
    if identifier == "p3_seam_source":
        _exact(value, {
            "candidate_sha256", "relationship_count",
            "review_required_count", "unobservable_count",
        })
        _sha_fields(value, ("candidate_sha256",))
        _integer_fields(value, (
            "relationship_count", "review_required_count",
            "unobservable_count",
        ))
        if value["relationship_count"] != 6 \
                or value["relationship_count"] != value["review_required_count"] \
                + value["unobservable_count"]:
            _fail("Readiness P3 relationship counts are inconsistent")
        return "verified"
    if identifier == "p9_reviewed_motion":
        _exact(value, {"clip_id", "motion_instance_v2_sha256", "bundle_sha256"})
        require_safe_token(value["clip_id"], "Readiness clip id")
        _sha_fields(value, ("motion_instance_v2_sha256", "bundle_sha256"))
        return "verified"
    if identifier == "p10_5_reviewed_seam_anchor_set":
        return _seam_evidence_status(value)
    if identifier == "p10_6b_motion_instance_v3":
        _exact(value, {"clip_id", "motion_instance_v3_sha256", "bundle_sha256"})
        require_safe_token(value["clip_id"], "Readiness clip id")
        _sha_fields(value, ("motion_instance_v3_sha256", "bundle_sha256"))
        return "verified"
    if identifier == "p10_7a_spine42_v3":
        _exact(value, {"clip_id", "skeleton_json_sha256", "bundle_sha256"})
        require_safe_token(value["clip_id"], "Readiness clip id")
        _sha_fields(value, ("skeleton_json_sha256", "bundle_sha256"))
        return "verified"
    if identifier == "p10_7b_runtime_capture":
        _exact(value, {
            "clip_id", "spine42_v3_bundle_sha256", "capture_bundle_sha256",
            "raster_metrics_sha256", "sampled_metrics_passed",
        })
        require_safe_token(value["clip_id"], "Readiness clip id")
        _sha_fields(value, (
            "spine42_v3_bundle_sha256", "capture_bundle_sha256",
            "raster_metrics_sha256",
        ))
        if type(value["sampled_metrics_passed"]) is not bool:
            _fail("Readiness runtime evidence is invalid")
        return "verified"
    if identifier == "p10_7b_raster_review":
        return _raster_evidence_status(value)
    _fail("Readiness checkpoint cannot contain evidence")


def _seam_evidence_status(value):
    verified = {
        "candidate_sha256", "decision_sha256", "review_revision",
        "reviewed_seam_anchor_set_sha256", "bundle_sha256",
    }
    if set(value) == verified:
        _sha_fields(value, verified - {"review_revision"})
        _integer_fields(value, ("review_revision",), minimum=1, maximum=64)
        return "verified"
    fields = {"candidate_sha256", "unobservable_count"}
    if set(value) != fields:
        _fail("Readiness seam evidence fields are invalid")
    _sha_fields(value, ("candidate_sha256",))
    _integer_fields(value, ("unobservable_count",))
    return (
        "review_blocked" if value["unobservable_count"] > 0
        else "prerequisite_missing"
    )


def _raster_evidence_status(value):
    base = {"candidate_sha256", "metrics_status"}
    decided = base | {"decision_sha256", "decision_status"}
    if set(value) not in (base, decided):
        _fail("Readiness raster evidence fields are invalid")
    require_sha256(value["candidate_sha256"], "Raster candidate")
    if value["metrics_status"] not in {"passed", "rejected"}:
        _fail("Readiness raster metrics status is invalid")
    if set(value) == decided:
        require_sha256(value["decision_sha256"], "Raster decision")
        if value["decision_status"] not in {
            "sampled_raster_approved", "sampled_raster_rejected",
        }:
            _fail("Readiness raster decision status is invalid")
    if value["metrics_status"] == "rejected":
        return "metrics_rejected"
    if value.get("decision_status") == "sampled_raster_approved":
        return "verified"
    return "review_blocked"


def _exact(value, fields):
    if set(value) != fields:
        _fail("Readiness checkpoint evidence fields are invalid")


def _sha_fields(value, fields):
    for field in fields:
        require_sha256(value[field], f"Readiness evidence {field}")


def _integer_fields(value, fields, *, minimum=0, maximum=1_000_000):
    for field in fields:
        if type(value[field]) is not int or not minimum <= value[field] <= maximum:
            _fail("Readiness evidence integer is invalid")


def _summary(samples):
    counts = {name: 0 for name in sorted(STATUSES)}
    for sample in samples:
        for checkpoint in sample["checkpoints"]:
            counts[checkpoint["status"]] += 1
    ready = sum(row["status"] == "ready_for_p6_setup_comparison" for row in samples)
    return {
        "sample_count": len(samples),
        "ready_for_p6_setup_comparison_count": ready,
        "blocked_sample_count": len(samples) - ready,
        "checkpoint_status_counts": counts,
    }


def _object(value, fields, label):
    if type(value) is not dict or set(value) != fields:
        _fail(f"Readiness {label} fields are invalid")
    return value


def _fail(message):
    raise Spine42V3ReadinessValidationError(message)


__all__ = [
    "Spine42V3ReadinessValidationError",
    "require_spine42_v3_readiness_report",
]
