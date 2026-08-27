"""P10.7b sampled raster-review contract and exact-command tests."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for item in (ROOT, SRC):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from autospine_workbench.p10_spine42_v3_raster_review_commands import (  # noqa: E402
    P10Spine42V3RasterReviewCommandError,
    prepare_spine42_v3_raster_review_command,
    submit_spine42_v3_raster_review_command,
)
from autospine_workbench.resolved_project import canonical_sha256  # noqa: E402
from autospine_workbench.spine42_v3_raster_review import (  # noqa: E402
    Spine42V3RasterReviewError,
    build_spine42_v3_raster_review_decision,
    compile_spine42_v3_raster_review_candidate,
    require_spine42_v3_raster_review_candidate,
    require_spine42_v3_raster_review_decision,
)
from autospine_workbench.spine42_v3_raster_review_validation import (  # noqa: E402
    domain_sha256,
)
from autospine_workbench.spine42_v3_runtime_profile import (  # noqa: E402
    METRICS_HASH_DOMAIN,
)
from tests.test_spine42_v3_runtime_evidence_store import _evidence  # noqa: E402

CAPTURE_SHA = "a" * 64


def _candidate():
    evidence = _evidence()
    return evidence, compile_spine42_v3_raster_review_candidate(
        evidence.manifest, evidence.metrics,
        capture_bundle_sha256=CAPTURE_SHA,
    )


def _rehash(value, field, domain):
    value.pop(field, None)
    value[field] = domain_sha256(domain, value)


def _decisions(candidate, action="approve"):
    note = "not visible" if action != "approve" else ""
    cases = [{
        "case_id": row["case_id"], "evidence_sha256": row["evidence_sha256"],
        "action": action, "notes": note,
    } for row in candidate["cases"]]
    attachments = [{
        "attachment_key": row["attachment_key"],
        "evidence_sha256": row["evidence_sha256"],
        "action": action, "notes": note,
    } for row in candidate["attachments"]]
    return cases, attachments


def _decision(candidate, previous=None):
    cases, attachments = _decisions(candidate)
    return build_spine42_v3_raster_review_decision(
        candidate, reviewer_id="operator-1", notes="sampled only",
        case_decisions=cases, attachment_decisions=attachments,
        previous_decision=previous,
    )


class Spine42V3RasterReviewTests(unittest.TestCase):
    def test_candidate_is_deterministic_and_fixed_fields_fail_after_rehash(self):
        evidence, candidate = _candidate()
        repeated = compile_spine42_v3_raster_review_candidate(
            evidence.manifest, evidence.metrics,
            capture_bundle_sha256=CAPTURE_SHA,
        )
        self.assertEqual(candidate, repeated)
        require_spine42_v3_raster_review_candidate(candidate)
        for field, key, elevated in (
            ("semantics", "continuous_time_safety_claimed", True),
            ("authority", "release_authority", True),
            ("release_gate", "status", "open"),
        ):
            forged = deepcopy(candidate)
            forged[field][key] = elevated
            _rehash(
                forged, "candidate_sha256",
                "autospine-spine42-v3-raster-review-candidate/v1",
            )
            with self.subTest(field=field), self.assertRaises(
                Spine42V3RasterReviewError
            ):
                require_spine42_v3_raster_review_candidate(forged)

    def test_manifest_plan_metric_and_attachment_rows_are_exact(self):
        evidence, _candidate_value = _candidate()
        manifest, metrics = evidence.manifest, evidence.metrics
        manifest["artifacts"][0]["case_id"] = "wrong"
        with self.assertRaisesRegex(Spine42V3RasterReviewError, "binding"):
            compile_spine42_v3_raster_review_candidate(
                manifest, metrics, capture_bundle_sha256=CAPTURE_SHA
            )

        manifest, metrics = evidence.manifest, evidence.metrics
        metrics["cases"][0]["attachment_isolates"][0][
            "attachment_id"
        ] = "wrong"
        body = deepcopy(metrics)
        body.pop("raster_metrics_sha256")
        digest = canonical_sha256({"domain": METRICS_HASH_DOMAIN, **body})
        metrics["raster_metrics_sha256"] = digest
        manifest["source"]["raster_metrics_sha256"] = digest
        with self.assertRaisesRegex(Spine42V3RasterReviewError, "binding"):
            compile_spine42_v3_raster_review_candidate(
                manifest, metrics, capture_bundle_sha256=CAPTURE_SHA
            )

    def test_decision_is_exhaustive_ordered_and_never_grants_release(self):
        _evidence_value, candidate = _candidate()
        cases, attachments = _decisions(candidate)
        decision = build_spine42_v3_raster_review_decision(
            candidate, reviewer_id="operator-1", notes="",
            case_decisions=list(reversed(cases)),
            attachment_decisions=list(reversed(attachments)),
        )
        self.assertEqual(
            [row["case_id"] for row in candidate["cases"]],
            [row["case_id"] for row in decision["case_decisions"]],
        )
        self.assertTrue(decision["claims"]["sampled_raster_visual_quality"])
        self.assertFalse(decision["claims"]["continuous_runtime_raster_safety"])
        self.assertFalse(decision["claims"]["release_authority"])
        self.assertEqual("blocked", decision["release_gate"]["status"])
        with self.assertRaises(Spine42V3RasterReviewError):
            build_spine42_v3_raster_review_decision(
                candidate, reviewer_id="operator-1", notes="",
                case_decisions=cases[:-1], attachment_decisions=attachments,
            )
        forged = deepcopy(decision)
        forged["claims"]["continuous_runtime_raster_safety"] = True
        _rehash(
            forged, "decision_sha256",
            "autospine-spine42-v3-raster-review-decision/v1",
        )
        with self.assertRaises(Spine42V3RasterReviewError):
            require_spine42_v3_raster_review_decision(
                forged, candidate=candidate
            )

    def test_revision_requires_exact_immediate_supersession(self):
        _evidence_value, candidate = _candidate()
        first, second = _decision(candidate), None
        second = _decision(candidate, first)
        self.assertEqual(2, second["review"]["revision"])
        self.assertEqual(
            first["decision_sha256"],
            second["review"]["supersedes_decision_sha256"],
        )
        require_spine42_v3_raster_review_decision(
            second, candidate=candidate, previous_decision=first
        )
        forged = deepcopy(second)
        forged["review"]["supersedes_decision_sha256"] = "b" * 64
        _rehash(
            forged, "decision_sha256",
            "autospine-spine42-v3-raster-review-decision/v1",
        )
        with self.assertRaisesRegex(Spine42V3RasterReviewError, "supersession"):
            require_spine42_v3_raster_review_decision(
                forged, candidate=candidate, previous_decision=first
            )

    def test_submit_replays_exact_capture_candidate_before_human_input(self):
        evidence, candidate = _candidate()
        capture = SimpleNamespace(
            evidence=evidence, capture_bundle_sha256=CAPTURE_SHA,
            project_id=evidence.project_id,
        )
        upstream = SimpleNamespace(
            project_id=evidence.project_id, clip_id=evidence.clip_id,
            skeleton_json_sha256=evidence.skeleton_json_sha256,
            bundle_sha256=evidence.spine42_v3_bundle_sha256,
            run_document_sha256=evidence.run_document_sha256,
        )
        cases, attachments = _decisions(candidate)
        review = {
            "reviewer_id": "operator-1", "notes": "sampled only",
            "case_decisions": cases, "attachment_decisions": attachments,
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidate_path, review_path = root / "candidate.json", root / "review.json"
            candidate_path.write_text(json.dumps(candidate), encoding="utf-8")
            review_path.write_text(json.dumps(review), encoding="utf-8")
            with patch(
                "autospine_workbench.p10_spine42_v3_raster_review_commands."
                "VerifiedSpine42V3RuntimeReader.load", return_value=capture,
            ), patch(
                "autospine_workbench.p10_spine42_v3_raster_review_commands."
                "VerifiedSpine42V3BundleReader.load", return_value=upstream,
            ):
                prepared = prepare_spine42_v3_raster_review_command(
                    root, evidence.project_id,
                    spine42_v3_bundle_sha256=evidence.spine42_v3_bundle_sha256,
                    capture_bundle_sha256=CAPTURE_SHA,
                )
                self.assertEqual(candidate, prepared.document)
                result = submit_spine42_v3_raster_review_command(
                    root, evidence.project_id, candidate_path, review_path,
                    spine42_v3_bundle_sha256=evidence.spine42_v3_bundle_sha256,
                    capture_bundle_sha256=CAPTURE_SHA,
                )
                self.assertEqual("sampled_raster_approved", result.status)
                forged = deepcopy(candidate)
                forged["source"]["runtime_capture_manifest_sha256"] = "b" * 64
                _rehash(
                    forged, "candidate_sha256",
                    "autospine-spine42-v3-raster-review-candidate/v1",
                )
                candidate_path.write_text(json.dumps(forged), encoding="utf-8")
                with self.assertRaisesRegex(
                    P10Spine42V3RasterReviewCommandError, "exact evidence replay"
                ):
                    submit_spine42_v3_raster_review_command(
                        root, evidence.project_id, candidate_path, review_path,
                        spine42_v3_bundle_sha256=evidence.spine42_v3_bundle_sha256,
                        capture_bundle_sha256=CAPTURE_SHA,
                    )


if __name__ == "__main__":
    unittest.main()
