"""Cross-check report evidence that is not itself an input address."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for item in (ROOT, SRC):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from autospine_workbench.spine42_v3_readiness import (  # noqa: E402
    audit_spine42_v3_readiness,
)
from autospine_workbench.spine42_v3_readiness_binding import (  # noqa: E402
    Spine42V3ReadinessBindingError,
    require_spine42_v3_readiness_report_binding,
)
from autospine_workbench.spine42_v3_readiness_validation import (  # noqa: E402
    Spine42V3ReadinessValidationError,
    require_spine42_v3_readiness_report,
)
from tests.test_spine42_v3_readiness_binding import (  # noqa: E402
    SHA, forge_verified, request, seal,
)
from tests.test_spine42_v3_readiness_manifest import (  # noqa: E402
    full_request,
)


def base_report(value):
    with tempfile.TemporaryDirectory() as temporary:
        return audit_spine42_v3_readiness(value, Path(temporary))


def full_ready_report():
    value, _candidate = full_request()
    request_row = value["samples"][0]
    decision = request_row["raster_review_decision"]
    source = decision["source"]
    clip = decision["clip_id"]
    evidence = [
        {"candidate_sha256": source["candidate_sha256"],
         "relationship_count": 6, "review_required_count": 6,
         "unobservable_count": 0},
        {"clip_id": clip, **request_row["reviewed_motion_address"]},
        {"candidate_sha256": source["candidate_sha256"],
         "decision_sha256": "a" * 64, "review_revision": 1,
         "reviewed_seam_anchor_set_sha256": request_row[
             "reviewed_seam_anchor_set_address"
         ]["reviewed_seam_anchor_set_sha256"],
         "bundle_sha256": request_row[
             "reviewed_seam_anchor_set_address"
         ]["bundle_sha256"]},
        {"clip_id": clip, **request_row["motion_instance_v3_address"]},
        {"clip_id": clip, **request_row["spine42_v3_address"]},
        {"clip_id": clip, **request_row["runtime_capture_address"],
         "raster_metrics_sha256": source["raster_metrics_sha256"],
         "sampled_metrics_passed": True},
        {"candidate_sha256": source["candidate_sha256"],
         "metrics_status": "passed",
         "decision_sha256": decision["decision_sha256"],
         "decision_status": decision["status"]},
    ]
    report = base_report(value)
    for index, row in enumerate(evidence):
        report["samples"][0]["checkpoints"][index].update(
            status="verified", reason_codes=[], next_action_code=None,
            evidence=row,
        )
    return value, seal(report)


class Spine42V3ReadinessCrossBindingTests(unittest.TestCase):
    def test_verified_seam_rejects_unobservable_p3_relationships(self):
        value, report = full_ready_report()
        p3 = report["samples"][0]["checkpoints"][0]["evidence"]
        p3.update(review_required_count=2, unobservable_count=4)
        bad = seal(report)
        require_spine42_v3_readiness_report(bad)
        with self.assertRaises(Spine42V3ReadinessBindingError):
            require_spine42_v3_readiness_report_binding(bad, value)

    def test_verified_seam_revision_is_bounded_by_history_profile(self):
        _value, report = full_ready_report()
        report["samples"][0]["checkpoints"][2]["evidence"][
            "review_revision"
        ] = 65
        bad = seal(report)
        with self.assertRaises(Spine42V3ReadinessValidationError):
            require_spine42_v3_readiness_report(bad)

    def test_runtime_metrics_boolean_must_match_raster_metrics_status(self):
        value, report = full_ready_report()
        require_spine42_v3_readiness_report_binding(report, value)
        bad = deepcopy(report)
        bad["samples"][0]["checkpoints"][5]["evidence"][
            "sampled_metrics_passed"
        ] = False
        bad = seal(bad)
        require_spine42_v3_readiness_report(bad)
        with self.assertRaises(Spine42V3ReadinessBindingError):
            require_spine42_v3_readiness_report_binding(bad, value)

    def test_raster_decision_clip_must_match_the_verified_pipeline_clip(self):
        value, report = full_ready_report()
        bad = deepcopy(report)
        for index in (1, 3, 4, 5):
            bad["samples"][0]["checkpoints"][index]["evidence"][
                "clip_id"
            ] = "different-clip"
        bad = seal(bad)
        require_spine42_v3_readiness_report(bad)
        with self.assertRaises(Spine42V3ReadinessBindingError):
            require_spine42_v3_readiness_report_binding(bad, value)

    def test_pending_seam_count_must_equal_the_p3_candidate_count(self):
        value = request()
        report = forge_verified(base_report(value), (0,))
        seam = report["samples"][0]["checkpoints"][2]
        seam.update(
            status="prerequisite_missing",
            reason_codes=["reviewed_seam_anchor_set_address_not_declared"],
            next_action_code="complete_review_and_declare_reviewed_seam_anchor_set",
            evidence={"candidate_sha256": SHA["candidate"],
                      "unobservable_count": 0},
        )
        report = seal(report)
        require_spine42_v3_readiness_report_binding(report, value)
        seam = report["samples"][0]["checkpoints"][2]
        seam.update(
            status="review_blocked",
            reason_codes=["seam_relationships_unobservable"],
            next_action_code=(
                "repair_layer_semantics_or_define_explicit_partial_seam_contract"
            ),
            evidence={"candidate_sha256": SHA["candidate"],
                      "unobservable_count": 1},
        )
        bad = seal(report)
        require_spine42_v3_readiness_report(bad)
        with self.assertRaises(Spine42V3ReadinessBindingError):
            require_spine42_v3_readiness_report_binding(bad, value)

    def test_p3_relationship_counts_are_semantically_closed(self):
        report = forge_verified(base_report(request()), (0,))
        evidence = report["samples"][0]["checkpoints"][0]["evidence"]
        evidence.update(relationship_count=7, review_required_count=7)
        report = seal(report)
        with self.assertRaises(Spine42V3ReadinessValidationError):
            require_spine42_v3_readiness_report(report)


if __name__ == "__main__":
    unittest.main()
