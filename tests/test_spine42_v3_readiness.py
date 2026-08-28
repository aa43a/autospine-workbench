"""Readiness report invariants and bounded runtime checkpoint tests."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for item in (ROOT, SRC):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from autospine_workbench.spine42_v3_readiness import (  # noqa: E402
    audit_spine42_v3_readiness,
)
from autospine_workbench.spine42_v3_readiness_runtime import (  # noqa: E402
    audit_runtime_and_raster,
)
from autospine_workbench.spine42_v3_readiness_stages import (  # noqa: E402
    audit_spine42_v3_sample,
)
from autospine_workbench.spine42_v3_readiness_validation import (  # noqa: E402
    REPORT_DOMAIN,
    Spine42V3ReadinessValidationError,
    require_spine42_v3_readiness_report,
)
from autospine_workbench.spine42_v3_raster_review_values import (  # noqa: E402
    domain_sha256,
)


SHA = {name: digit * 64 for name, digit in zip((
    "manifest", "rig", "p3", "p9", "p9b", "seam", "seamb", "v3",
    "v3b", "skeleton", "spine", "capture", "metrics", "candidate",
    "decision", "run",
), "123456789abcdef0", strict=True)}


def request():
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


def runtime_sample(decision=None):
    return {
        "project_id": "sample-a",
        "runtime_capture_address": {
            "spine42_v3_bundle_sha256": SHA["spine"],
            "capture_bundle_sha256": SHA["capture"],
        },
        "raster_review_decision": decision,
    }


def runtime_context(passed=True):
    spine = SimpleNamespace(
        bundle_sha256=SHA["spine"], skeleton_json_sha256=SHA["skeleton"],
        run_document_sha256=SHA["run"],
    )
    evidence = SimpleNamespace(
        clip_id="clip", skeleton_json_sha256=SHA["skeleton"],
        spine42_v3_bundle_sha256=SHA["spine"],
        run_document_sha256=SHA["run"],
        raster_metrics_sha256=SHA["metrics"], manifest={},
        metrics={"summary": {"all_sampled_cases_passed": passed}},
    )
    capture = SimpleNamespace(
        evidence=evidence, spine42_v3_bundle_sha256=SHA["spine"],
        capture_bundle_sha256=SHA["capture"],
    )
    return {"spine": spine}, capture


def candidate(passed=True):
    return {
        "candidate_sha256": SHA["candidate"],
        "metrics_status": "passed" if passed else "rejected",
    }


class Spine42V3ReadinessReportTests(unittest.TestCase):
    def test_same_request_and_state_produce_same_self_validating_report(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = audit_spine42_v3_readiness(request(), root)
            second = audit_spine42_v3_readiness(request(), root)
        self.assertEqual(first, second)
        require_spine42_v3_readiness_report(first)
        self.assertEqual("blocked_prerequisites_or_review", first["status"])
        self.assertEqual("source_mismatch", first["samples"][0][
            "checkpoints"
        ][0]["status"])

    def test_report_tampering_cannot_elevate_authority_or_status(self):
        with tempfile.TemporaryDirectory() as temporary:
            report = audit_spine42_v3_readiness(
                request(), Path(temporary)
            )
        variants = []
        for mutate in (
            lambda row: row["authority"].update(release=True),
            lambda row: row["authority"].update(release=0),
            lambda row: row["semantics"].update(
                pure_replay_compilation=1),
            lambda row: row["summary"].update(sample_count=True),
            lambda row: row.update(format_version=True),
            lambda row: row.update(status="ready_for_p6_setup_comparison"),
            lambda row: row["samples"][0]["checkpoints"][0].update(
                status="verified", reason_codes=[], next_action_code=None),
            lambda row: row["samples"][0]["checkpoints"][0].update(
                evidence={"private_path": r"C:\private\state"}),
            lambda row: row.update(readiness_report_sha256="f" * 64),
        ):
            bad = deepcopy(report)
            mutate(bad)
            if bad["readiness_report_sha256"] != "f" * 64:
                body = deepcopy(bad)
                body.pop("readiness_report_sha256")
                bad["readiness_report_sha256"] = domain_sha256(
                    REPORT_DOMAIN, body
                )
            variants.append(bad)
        for bad in variants:
            with self.assertRaises(Spine42V3ReadinessValidationError):
                require_spine42_v3_readiness_report(bad)

    @patch(
        "autospine_workbench.seam_anchor_review_history_snapshot."
        "snapshot_seam_anchor_review_history",
        side_effect=AssertionError("mutable review history was observed"),
    )
    @patch(
        "autospine_workbench.spine42_v3_readiness_stages."
        "load_bound_seam_anchor_review_candidate",
    )
    def test_null_seam_address_never_observes_mutable_review_head(
        self, load_candidate, history_snapshot,
    ):
        candidate = SimpleNamespace(
            sha256=SHA["candidate"],
            document={"summary": {
                "relationship_count": 6,
                "review_required_count": 6,
                "unobservable_count": 0,
            }},
        )
        load_candidate.return_value = SimpleNamespace(candidates=candidate)
        result = audit_spine42_v3_sample(
            request()["samples"][0], Path("state")
        )
        history_snapshot.assert_not_called()
        self.assertNotIn(
            "current_review_revision", result["checkpoints"][0]["evidence"]
        )
        seam = result["checkpoints"][2]
        self.assertEqual("prerequisite_missing", seam["status"])
        self.assertEqual(
            ["reviewed_seam_anchor_set_address_not_declared"],
            seam["reason_codes"],
        )


class Spine42V3ReadinessRuntimeTests(unittest.TestCase):
    @patch("autospine_workbench.spine42_v3_readiness_runtime."
           "compile_spine42_v3_raster_review_candidate")
    @patch("autospine_workbench.spine42_v3_readiness_runtime."
           "VerifiedSpine42V3RuntimeReader")
    def test_exact_passed_capture_and_human_approval_verify_bounded_rows(
        self, reader_type, compile_candidate,
    ):
        context, capture = runtime_context()
        reader_type.return_value.load.return_value = capture
        compile_candidate.return_value = candidate()
        decision = {
            "decision_sha256": SHA["decision"],
            "status": "sampled_raster_approved",
        }
        with patch(
            "autospine_workbench.spine42_v3_readiness_runtime."
            "require_spine42_v3_raster_review_decision"
        ) as validate:
            capture_row, review_row = audit_runtime_and_raster(
                runtime_sample(decision), Path("state"), context
            )
        self.assertEqual("verified", capture_row["status"])
        self.assertEqual("verified", review_row["status"])
        validate.assert_called_once_with(decision, candidate=candidate())

    @patch("autospine_workbench.spine42_v3_readiness_runtime."
           "compile_spine42_v3_raster_review_candidate")
    @patch("autospine_workbench.spine42_v3_readiness_runtime."
           "VerifiedSpine42V3RuntimeReader")
    def test_rejected_metrics_cannot_become_human_approved(
        self, reader_type, compile_candidate,
    ):
        context, capture = runtime_context(False)
        reader_type.return_value.load.return_value = capture
        compile_candidate.return_value = candidate(False)
        capture_row, review_row = audit_runtime_and_raster(
            runtime_sample(), Path("state"), context
        )
        self.assertEqual("verified", capture_row["status"])
        self.assertEqual("metrics_rejected", review_row["status"])
        self.assertEqual(
            "repair_runtime_raster_metrics_before_human_approval",
            review_row["next_action_code"],
        )

    def test_cross_wired_capture_is_rejected_without_reader_call(self):
        context, _capture = runtime_context()
        sample = runtime_sample()
        sample["runtime_capture_address"][
            "spine42_v3_bundle_sha256"
        ] = "f" * 64
        with patch(
            "autospine_workbench.spine42_v3_readiness_runtime."
            "VerifiedSpine42V3RuntimeReader"
        ) as reader_type:
            capture_row, review_row = audit_runtime_and_raster(
                sample, Path("state"), context
            )
        reader_type.assert_not_called()
        self.assertEqual("source_mismatch", capture_row["status"])
        self.assertEqual("prerequisite_missing", review_row["status"])


if __name__ == "__main__":
    unittest.main()
