"""Official-runtime and human raster checkpoints for readiness auditing."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .spine42_v3_raster_review import (
    compile_spine42_v3_raster_review_candidate,
    require_spine42_v3_raster_review_decision,
)
from .spine42_v3_runtime_reader import VerifiedSpine42V3RuntimeReader


_FAILURES = (KeyError, OSError, RuntimeError, TypeError, ValueError)


def audit_runtime_and_raster(
    sample: Mapping[str, Any], state_root: Path, context: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Replay one declared capture, then bind its embedded human decision."""

    capture = _capture(sample, state_root, context)
    return capture, _raster(sample, context)


def _capture(sample, root, context):
    address = sample["runtime_capture_address"]
    if address is None:
        return _missing(
            "p10_7b_runtime_capture", "runtime_capture_address_not_declared",
            "run_authorized_official_spine42_runtime_capture",
        )
    spine = context.get("spine")
    if spine is None:
        return _missing(
            "p10_7b_runtime_capture", "spine42_v3_not_verified",
            "verify_spine42_v3_bundle",
        )
    if address["spine42_v3_bundle_sha256"] != spine.bundle_sha256:
        return _mismatch(
            "p10_7b_runtime_capture", "runtime_capture_spine_source_cross_wired"
        )
    try:
        value = VerifiedSpine42V3RuntimeReader(root).load(
            sample["project_id"], address["spine42_v3_bundle_sha256"],
            address["capture_bundle_sha256"],
        )
        evidence = value.evidence
        if (evidence.skeleton_json_sha256, evidence.spine42_v3_bundle_sha256,
            evidence.run_document_sha256) != (
                spine.skeleton_json_sha256, spine.bundle_sha256,
                spine.run_document_sha256):
            raise ValueError("Runtime capture/P10.7a cross-wire")
        context["capture"] = value
        return _checkpoint(
            "p10_7b_runtime_capture", "verified", (), None,
            {"clip_id": evidence.clip_id,
             "spine42_v3_bundle_sha256": value.spine42_v3_bundle_sha256,
             "capture_bundle_sha256": value.capture_bundle_sha256,
             "raster_metrics_sha256": evidence.raster_metrics_sha256,
             "sampled_metrics_passed": evidence.metrics["summary"][
                 "all_sampled_cases_passed"]},
        )
    except _FAILURES:
        return _mismatch(
            "p10_7b_runtime_capture", "exact_runtime_capture_replay_failed"
        )


def _raster(sample, context):
    capture = context.get("capture")
    if capture is None:
        return _missing(
            "p10_7b_raster_review", "runtime_capture_not_verified",
            "verify_official_runtime_capture",
        )
    try:
        candidate = compile_spine42_v3_raster_review_candidate(
            capture.evidence.manifest, capture.evidence.metrics,
            capture_bundle_sha256=capture.capture_bundle_sha256,
        )
        metrics_status = candidate["metrics_status"]
        decision = sample["raster_review_decision"]
        evidence = {
            "candidate_sha256": candidate["candidate_sha256"],
            "metrics_status": metrics_status,
        }
        if decision is None:
            if metrics_status == "rejected":
                return _checkpoint(
                    "p10_7b_raster_review", "metrics_rejected",
                    ("sampled_raster_metrics_rejected",),
                    "repair_runtime_raster_metrics_before_human_approval",
                    evidence,
                )
            return _checkpoint(
                "p10_7b_raster_review", "review_blocked",
                ("human_sampled_raster_review_missing",),
                "complete_exhaustive_human_sampled_raster_review", evidence,
            )
        require_spine42_v3_raster_review_decision(
            decision, candidate=candidate
        )
        evidence.update(
            decision_sha256=decision["decision_sha256"],
            decision_status=decision["status"],
        )
        if metrics_status == "rejected":
            return _checkpoint(
                "p10_7b_raster_review", "metrics_rejected",
                ("sampled_raster_metrics_rejected",),
                "repair_runtime_raster_metrics_before_human_approval",
                evidence,
            )
        if decision["status"] != "sampled_raster_approved":
            return _checkpoint(
                "p10_7b_raster_review", "review_blocked",
                ("human_sampled_raster_review_not_approved",),
                "revise_exhaustive_human_sampled_raster_review", evidence,
            )
        return _checkpoint(
            "p10_7b_raster_review", "verified", (), None, evidence
        )
    except _FAILURES:
        return _mismatch(
            "p10_7b_raster_review", "raster_review_decision_replay_failed"
        )


def _checkpoint(identifier, status, reasons, action, evidence=None):
    return {
        "checkpoint_id": identifier,
        "status": status,
        "reason_codes": list(reasons),
        "next_action_code": action,
        "evidence": evidence or {},
    }


def _missing(identifier, reason, action):
    return _checkpoint(identifier, "prerequisite_missing", (reason,), action)


def _mismatch(identifier, reason):
    return _checkpoint(
        identifier, "source_mismatch", (reason,),
        f"repair_{identifier}_exact_address",
    )


__all__ = ["audit_runtime_and_raster"]
