"""Bind every readiness checkpoint to one strict request row."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .spine42_v3_readiness_manifest import (
    require_spine42_v3_readiness_request,
    spine42_v3_readiness_request_sha256,
)
from .spine42_v3_readiness_validation import (
    require_spine42_v3_readiness_report,
)


_MISMATCHES = {
    "p9_reviewed_motion": "exact_reviewed_motion_replay_failed",
    "p10_5_reviewed_seam_anchor_set":
        "exact_reviewed_seam_anchor_set_replay_failed",
    "p10_6b_motion_instance_v3": "exact_motion_instance_v3_replay_failed",
    "p10_7a_spine42_v3": "exact_spine42_v3_replay_failed",
    "p10_7b_runtime_capture": "exact_runtime_capture_replay_failed",
    "p10_7b_raster_review": "raster_review_decision_replay_failed",
}


class Spine42V3ReadinessBindingError(ValueError):
    """Raised when a structurally valid report is not request-bound."""


def require_spine42_v3_readiness_report_binding(
    report: Mapping[str, Any], request: Mapping[str, Any],
) -> None:
    """Reject invented stage states and evidence from undeclared addresses."""

    try:
        request = require_spine42_v3_readiness_request(request)
        require_spine42_v3_readiness_report(report)
        if report["request_sha256"] != \
                spine42_v3_readiness_request_sha256(request):
            _fail("Readiness report request identity differs")
        report_rows = report["samples"]
        if [row["project_id"] for row in report_rows] != [
            row["project_id"] for row in request["samples"]
        ]:
            _fail("Readiness report project inventory differs")
        for request_row, report_row in zip(
            request["samples"], report_rows, strict=True,
        ):
            _sample(request_row, report_row)
    except Spine42V3ReadinessBindingError:
        raise
    except (KeyError, RuntimeError, TypeError, ValueError) as exc:
        raise Spine42V3ReadinessBindingError(
            "Readiness report binding validation failed"
        ) from exc


def _sample(request, report):
    checkpoints = report["checkpoints"]
    p3, p9, seam, motion, spine, capture, raster, _p6 = checkpoints
    _p3(p3)
    _p9(p9, request["reviewed_motion_address"])
    _seam(seam, p3, request["reviewed_seam_anchor_set_address"])
    _motion(
        motion, request["motion_instance_v3_address"], p9, seam,
    )
    _spine(spine, request["spine42_v3_address"], motion)
    _capture(capture, request["runtime_capture_address"], spine)
    _raster(raster, request["raster_review_decision"], capture)
    clips = [
        row["evidence"]["clip_id"] for row in (p9, motion, spine, capture)
        if row["status"] == "verified"
    ]
    if len(set(clips)) > 1:
        _fail("Readiness verified clip identities differ")


def _p3(row):
    if row["status"] == "verified":
        return
    _expect_empty(
        row, "source_mismatch", "exact_p3_or_manifest_replay_failed",
        "repair_exact_p3_source_address",
    )


def _p9(row, address):
    if address is None:
        _expect_empty(
            row, "prerequisite_missing",
            "exact_reviewed_motion_address_not_declared",
            "provide_exact_reviewed_motion_after_real_kimodo_p7_p8_p9_review",
        )
    elif row["status"] == "verified":
        _match(row, address, {
            "motion_instance_v2_sha256": "motion_instance_v2_sha256",
            "bundle_sha256": "bundle_sha256",
        })
    else:
        _expect_mismatch(row, "p9_reviewed_motion")


def _seam(row, p3, address):
    if p3["status"] != "verified":
        _expect_empty(
            row, "prerequisite_missing", "p3_seam_source_not_verified",
            "repair_exact_p3_source_address",
        )
        return
    if address is None:
        evidence = row["evidence"]
        if evidence.get("candidate_sha256") != \
                p3["evidence"]["candidate_sha256"] \
                or evidence.get("unobservable_count") != \
                p3["evidence"]["unobservable_count"]:
            _fail("Readiness seam candidate differs from P3")
        if evidence.get("unobservable_count", 0) > 0:
            _expect(
                row, "review_blocked", "seam_relationships_unobservable",
                "repair_layer_semantics_or_define_explicit_partial_seam_contract",
            )
        else:
            _expect(
                row, "prerequisite_missing",
                "reviewed_seam_anchor_set_address_not_declared",
                "complete_review_and_declare_reviewed_seam_anchor_set",
            )
    elif row["status"] == "verified":
        if p3["evidence"]["unobservable_count"] != 0:
            _fail("Readiness reviewed seam has unobservable P3 relationships")
        _match(row, address, {
            "reviewed_seam_anchor_set_sha256":
                "reviewed_seam_anchor_set_sha256",
            "bundle_sha256": "bundle_sha256",
        })
        if row["evidence"]["candidate_sha256"] != \
                p3["evidence"]["candidate_sha256"]:
            _fail("Readiness reviewed seam candidate differs from P3")
    else:
        _expect_mismatch(row, "p10_5_reviewed_seam_anchor_set")


def _motion(row, address, p9, seam):
    if address is None:
        _expect_empty(
            row, "prerequisite_missing",
            "motion_instance_v3_address_not_declared",
            "complete_p10_0_through_p10_6_and_declare_motion_instance_v3",
        )
    elif p9["status"] != "verified" or seam["status"] != "verified":
        _expect_empty(
            row, "prerequisite_missing",
            "motion_instance_v3_upstream_not_verified",
            "verify_p9_and_reviewed_seam_anchor_set",
        )
    elif row["status"] == "verified":
        _match(row, address, {
            "motion_instance_v3_sha256": "motion_instance_v3_sha256",
            "bundle_sha256": "bundle_sha256",
        })
    else:
        _expect_mismatch(row, "p10_6b_motion_instance_v3")


def _spine(row, address, motion):
    if address is None:
        _expect_empty(
            row, "prerequisite_missing", "spine42_v3_address_not_declared",
            "compile_and_declare_spine42_v3_bundle",
        )
    elif motion["status"] != "verified":
        _expect_empty(
            row, "prerequisite_missing", "motion_instance_v3_not_verified",
            "verify_motion_instance_v3",
        )
    elif row["status"] == "verified":
        _match(row, address, {
            "skeleton_json_sha256": "skeleton_json_sha256",
            "bundle_sha256": "bundle_sha256",
        })
    else:
        _expect_mismatch(row, "p10_7a_spine42_v3")


def _capture(row, address, spine):
    if address is None:
        _expect_empty(
            row, "prerequisite_missing",
            "runtime_capture_address_not_declared",
            "run_authorized_official_spine42_runtime_capture",
        )
    elif spine["status"] != "verified":
        _expect_empty(
            row, "prerequisite_missing", "spine42_v3_not_verified",
            "verify_spine42_v3_bundle",
        )
    elif row["status"] == "verified":
        _match(row, address, {
            "spine42_v3_bundle_sha256": "spine42_v3_bundle_sha256",
            "capture_bundle_sha256": "capture_bundle_sha256",
        })
    else:
        _expect_mismatch(row, "p10_7b_runtime_capture")


def _raster(row, decision, capture):
    if capture["status"] != "verified":
        _expect_empty(
            row, "prerequisite_missing", "runtime_capture_not_verified",
            "verify_official_runtime_capture",
        )
        return
    if row["status"] == "source_mismatch":
        _expect_mismatch(row, "p10_7b_raster_review")
        return
    evidence = row["evidence"]
    if (evidence["metrics_status"] == "passed") is not \
            capture["evidence"]["sampled_metrics_passed"]:
        _fail("Readiness raster metrics differ from runtime capture")
    if decision is None:
        if "decision_sha256" in evidence or row["status"] == "verified":
            _fail("Readiness raster approval has no declared decision")
        if evidence["metrics_status"] == "rejected":
            _expect(
                row, "metrics_rejected", "sampled_raster_metrics_rejected",
                "repair_runtime_raster_metrics_before_human_approval",
            )
        else:
            _expect(
                row, "review_blocked", "human_sampled_raster_review_missing",
                "complete_exhaustive_human_sampled_raster_review",
            )
        return
    source = decision["source"]
    if decision["clip_id"] != capture["evidence"]["clip_id"] \
            or evidence.get("candidate_sha256") != source["candidate_sha256"] \
            or evidence.get("decision_sha256") != decision["decision_sha256"] \
            or evidence.get("decision_status") != decision["status"] \
            or capture["evidence"]["raster_metrics_sha256"] != \
            source["raster_metrics_sha256"]:
        _fail("Readiness raster evidence differs from its decision")
    if row["status"] == "verified" and (
        decision["status"] != "sampled_raster_approved"
        or evidence["metrics_status"] != "passed"
    ):
        _fail("Readiness raster approval dependencies are incomplete")
    if evidence["metrics_status"] == "rejected":
        _expect(
            row, "metrics_rejected", "sampled_raster_metrics_rejected",
            "repair_runtime_raster_metrics_before_human_approval",
        )
    elif decision["status"] != "sampled_raster_approved":
        _expect(
            row, "review_blocked",
            "human_sampled_raster_review_not_approved",
            "revise_exhaustive_human_sampled_raster_review",
        )


def _match(row, address, fields):
    for evidence_field, address_field in fields.items():
        if row["evidence"].get(evidence_field) != address[address_field]:
            _fail("Readiness verified evidence differs from its address")


def _expect_mismatch(row, identifier):
    _expect_empty(
        row, "source_mismatch", _MISMATCHES[identifier],
        f"repair_{identifier}_exact_address",
    )


def _expect_empty(row, status, reason, action):
    _expect(row, status, reason, action)
    if row["evidence"]:
        _fail("Readiness failed checkpoint cannot contain evidence")


def _expect(row, status, reason, action):
    if row["status"] != status or row["reason_codes"] != [reason] \
            or row["next_action_code"] != action:
        _fail("Readiness checkpoint state is not an allowed variant")


def _fail(message):
    raise Spine42V3ReadinessBindingError(message)


__all__ = [
    "Spine42V3ReadinessBindingError",
    "require_spine42_v3_readiness_report_binding",
]
