"""Request-aware anti-forgery tests for readiness reports."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for item in (ROOT, SRC):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from autospine_workbench.p10_spine42_v3_readiness_commands import (  # noqa: E402
    P10Spine42V3ReadinessCommandError,
    audit_body_sway_spine42_v3_readiness_command,
)
from autospine_workbench.spine42_v3_readiness import (  # noqa: E402
    audit_spine42_v3_readiness,
)
from autospine_workbench.spine42_v3_readiness_binding import (  # noqa: E402
    Spine42V3ReadinessBindingError,
    require_spine42_v3_readiness_report_binding,
)
from autospine_workbench.spine42_v3_readiness_manifest import (  # noqa: E402
    canonical_spine42_v3_readiness_request_bytes,
)
from autospine_workbench.spine42_v3_readiness_validation import (  # noqa: E402
    REPORT_DOMAIN, STATUSES, require_spine42_v3_readiness_report,
)
from autospine_workbench.spine42_v3_raster_review_values import (  # noqa: E402
    domain_sha256,
)


SHA = {name: digit * 64 for name, digit in zip((
    "manifest", "rig", "p3", "p9", "p9b", "seam", "seamb", "motion",
    "motionb", "skeleton", "spine", "capture", "candidate", "decision",
    "metrics",
), "123456789abcdef", strict=True)}


def request() -> dict:
    return {
        "format": "autospine-spine42-v3-readiness-request",
        "format_version": 1,
        "samples": [{
            "project_id": "sample-a",
            "layer_manifest_sha256": SHA["manifest"],
            "p3_rig_sha256": SHA["rig"],
            "p3_bundle_sha256": SHA["p3"],
            "reviewed_motion_address": None,
            "reviewed_seam_anchor_set_address": None,
            "motion_instance_v3_address": None,
            "spine42_v3_address": None,
            "runtime_capture_address": None,
            "raster_review_decision": None,
        }],
    }


def addressed_request(*, through: str) -> dict:
    value = request()
    row = value["samples"][0]
    row["reviewed_motion_address"] = {
        "motion_instance_v2_sha256": SHA["p9"],
        "bundle_sha256": SHA["p9b"],
    }
    if through == "p9":
        return value
    row["reviewed_seam_anchor_set_address"] = {
        "reviewed_seam_anchor_set_sha256": SHA["seam"],
        "bundle_sha256": SHA["seamb"],
    }
    row["motion_instance_v3_address"] = {
        "motion_instance_v3_sha256": SHA["motion"],
        "bundle_sha256": SHA["motionb"],
    }
    if through == "motion":
        return value
    row["spine42_v3_address"] = {
        "skeleton_json_sha256": SHA["skeleton"],
        "bundle_sha256": SHA["spine"],
    }
    row["runtime_capture_address"] = {
        "spine42_v3_bundle_sha256": SHA["spine"],
        "capture_bundle_sha256": SHA["capture"],
    }
    return value


def verified_evidence() -> list[dict]:
    return [
        {"candidate_sha256": SHA["candidate"], "relationship_count": 6,
         "review_required_count": 6, "unobservable_count": 0},
        {"clip_id": "clip", "motion_instance_v2_sha256": SHA["p9"],
         "bundle_sha256": SHA["p9b"]},
        {"candidate_sha256": SHA["candidate"],
         "decision_sha256": SHA["decision"], "review_revision": 1,
         "reviewed_seam_anchor_set_sha256": SHA["seam"],
         "bundle_sha256": SHA["seamb"]},
        {"clip_id": "clip", "motion_instance_v3_sha256": SHA["motion"],
         "bundle_sha256": SHA["motionb"]},
        {"clip_id": "clip", "skeleton_json_sha256": SHA["skeleton"],
         "bundle_sha256": SHA["spine"]},
        {"clip_id": "clip", "spine42_v3_bundle_sha256": SHA["spine"],
         "capture_bundle_sha256": SHA["capture"],
         "raster_metrics_sha256": SHA["metrics"],
         "sampled_metrics_passed": True},
        {"candidate_sha256": SHA["candidate"], "metrics_status": "passed",
         "decision_sha256": SHA["decision"],
         "decision_status": "sampled_raster_approved"},
    ]


def forge_verified(report: dict, indices=range(7)) -> dict:
    result = deepcopy(report)
    for index in indices:
        result["samples"][0]["checkpoints"][index].update(
            status="verified", reason_codes=[], next_action_code=None,
            evidence=deepcopy(verified_evidence()[index]),
        )
    return seal(result)


def seal(report: dict) -> dict:
    result = deepcopy(report)
    for sample in result["samples"]:
        sample["next_action_codes"] = sorted({
            row["next_action_code"] for row in sample["checkpoints"]
            if row["next_action_code"] is not None
        })
        ready = all(
            row["status"] == "verified" for row in sample["checkpoints"][:-1]
        )
        sample["status"] = "ready_for_p6_setup_comparison" if ready else "blocked"
    counts = {name: 0 for name in sorted(STATUSES)}
    for sample in result["samples"]:
        for row in sample["checkpoints"]:
            counts[row["status"]] += 1
    ready_count = sum(
        row["status"] == "ready_for_p6_setup_comparison"
        for row in result["samples"]
    )
    result["summary"] = {
        "sample_count": len(result["samples"]),
        "ready_for_p6_setup_comparison_count": ready_count,
        "blocked_sample_count": len(result["samples"]) - ready_count,
        "checkpoint_status_counts": counts,
    }
    result["status"] = (
        "ready_for_p6_setup_comparison" if ready_count == len(result["samples"])
        else "blocked_prerequisites_or_review"
    )
    result.pop("readiness_report_sha256", None)
    result["readiness_report_sha256"] = domain_sha256(REPORT_DOMAIN, result)
    return result


class Spine42V3ReadinessBindingTests(unittest.TestCase):
    def base_report(self, value):
        with tempfile.TemporaryDirectory() as temporary:
            return audit_spine42_v3_readiness(value, Path(temporary))

    def test_all_null_request_cannot_be_forged_ready_at_command_boundary(self):
        value = request()
        forged = forge_verified(self.base_report(value))
        require_spine42_v3_readiness_report(forged)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = root / "request.json"
            manifest.write_bytes(
                canonical_spine42_v3_readiness_request_bytes(value)
            )
            with self.assertRaises(P10Spine42V3ReadinessCommandError):
                audit_body_sway_spine42_v3_readiness_command(
                    root / "state", manifest,
                    evaluator=Mock(return_value=forged),
                )

    def test_verified_p9_evidence_must_equal_declared_address(self):
        value = addressed_request(through="p9")
        report = forge_verified(self.base_report(value), (1,))
        require_spine42_v3_readiness_report_binding(report, value)
        bad = deepcopy(report)
        bad["samples"][0]["checkpoints"][1]["evidence"][
            "bundle_sha256"
        ] = "0" * 64
        bad = seal(bad)
        require_spine42_v3_readiness_report(bad)
        with self.assertRaises(Spine42V3ReadinessBindingError):
            require_spine42_v3_readiness_report_binding(bad, value)

    def test_verified_motion_requires_verified_p9_and_seam(self):
        value = addressed_request(through="motion")
        report = forge_verified(self.base_report(value), (3,))
        require_spine42_v3_readiness_report(report)
        with self.assertRaises(Spine42V3ReadinessBindingError):
            require_spine42_v3_readiness_report_binding(report, value)

    def test_invented_p9_failure_variant_is_rejected(self):
        value = request()
        report = self.base_report(value)
        report["samples"][0]["checkpoints"][1].update(
            status="metrics_rejected", reason_codes=["invented_reason"],
            next_action_code="invented_action",
        )
        report = seal(report)
        require_spine42_v3_readiness_report(report)
        with self.assertRaises(Spine42V3ReadinessBindingError):
            require_spine42_v3_readiness_report_binding(report, value)

    def test_raster_verified_requires_a_declared_human_decision(self):
        value = addressed_request(through="capture")
        report = forge_verified(self.base_report(value))
        require_spine42_v3_readiness_report(report)
        with self.assertRaises(Spine42V3ReadinessBindingError):
            require_spine42_v3_readiness_report_binding(report, value)


if __name__ == "__main__":
    unittest.main()
