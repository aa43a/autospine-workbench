"""Persisted digest and cross-layer binding tests for P10.4b v2."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for candidate in (ROOT, SRC):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from autospine_workbench.p10_safety_analysis_job_contract_v2 import (  # noqa: E402
    P10SafetyAnalysisRunRequestV2,
)
from autospine_workbench.body_sway_amplitude_envelope_profile_v2 import (  # noqa: E402
    amplitude_analyzer_profile_v2,
)
from autospine_workbench.body_sway_continuous_proof_profile_v2 import (  # noqa: E402
    continuous_analyzer_profile_v2,
)
from autospine_workbench.p10_safety_analysis_job_store_v2 import (  # noqa: E402
    P10SafetyAnalysisJobStoreV2,
    P10SafetyAnalysisJobStoreV2Error,
)
from autospine_workbench.p10_safety_analysis_result_validation_v2 import (  # noqa: E402
    P10SafetyAnalysisResultValidationV2Error,
    require_p10_safety_analysis_result_documents_v2,
    require_p10_safety_analysis_result_v2,
)
from autospine_workbench.resolved_project import canonical_sha256  # noqa: E402
from tests.p10_safety_analysis_job_v2_test_helpers import (  # noqa: E402
    SHA,
    completed_capture_job,
)


@dataclass(frozen=True)
class _Artifact:
    document: dict

    @property
    def canonical_bytes(self):
        return json.dumps(
            self.document, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")

    @property
    def sha256(self):
        return canonical_sha256(self.document)


class P10SafetyAnalysisResultV2Tests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.state = Path(self.temporary.name)
        self.completed = completed_capture_job()
        self.store = P10SafetyAnalysisJobStoreV2(self.state)
        request = P10SafetyAnalysisRunRequestV2.build(
            self.completed, attempt=1, previous_run_id=None,
        )
        self.snapshot = self.store.create(request)

    def tearDown(self):
        self.temporary.cleanup()

    def test_result_validator_rejects_visual_and_candidate_crosswire(self):
        amplitude, continuous, sealed = _bound_documents(self.snapshot)
        snapshot = _completed_snapshot(self.snapshot, sealed)
        with patch(
            "autospine_workbench.p10_safety_analysis_result_validation_v2."
            "require_body_sway_amplitude_envelope_candidate_v2",
        ), patch(
            "autospine_workbench.p10_safety_analysis_result_validation_v2."
            "require_sealed_body_sway_continuous_preview_proof_v2",
        ), patch(
            "autospine_workbench.p10_safety_analysis_result_validation_v2."
            "body_sway_amplitude_envelope_candidate_sha256_v2",
            return_value=continuous["source"][
                "amplitude_envelope_candidate_v2_sha256"
            ],
        ):
            require_p10_safety_analysis_result_v2(
                snapshot, amplitude, continuous,
            )
            tampered = json.loads(json.dumps(amplitude))
            tampered["source"]["review_admission_v2"]["source"][
                "visual_review"
            ]["revision"] = 2
            continuous_tampered = json.loads(json.dumps(continuous))
            continuous_tampered["source"][
                "amplitude_envelope_candidate_v2"
            ] = tampered
            with self.assertRaises(P10SafetyAnalysisResultValidationV2Error):
                require_p10_safety_analysis_result_v2(
                    snapshot, tampered, continuous_tampered,
                )
            detached = json.loads(json.dumps(continuous))
            detached["source"][
                "amplitude_envelope_candidate_v2_sha256"
            ] = SHA["9"]
            with self.assertRaises(P10SafetyAnalysisResultValidationV2Error):
                require_p10_safety_analysis_result_v2(
                    snapshot, amplitude, detached,
                )

    def test_store_read_result_rechecks_digest_and_size(self):
        amplitude = _Artifact({"format": "amplitude", "value": 1})
        continuous = _Artifact({"format": "continuous", "value": 2})
        sealed = self.store.publish_result(
            self.snapshot.run_id, amplitude, continuous,
            admission_sha256=SHA["1"],
            visual_candidate_sha256=SHA["2"], visual_revision=1,
            visual_decision_sha256=SHA["3"],
        )
        snapshot = self.store.append(
            self.snapshot.run_id, "completed", "completed",
            expected_previous=self.snapshot.head_event_sha256,
            current=1, total=1, result=sealed,
        )
        with patch(
            "autospine_workbench.p10_safety_analysis_result_store_v2."
            "require_p10_safety_analysis_result_documents_v2",
        ):
            self.assertEqual(
                (amplitude.document, continuous.document),
                self.store.read_result(snapshot.run_id),
            )
            directory = self.store._run_directory(
                snapshot.run_id, create=False,
            )
            (directory / "continuous.json").write_text(
                '{"format":"continuous","value":3}', encoding="utf-8",
            )
            with self.assertRaises(P10SafetyAnalysisJobStoreV2Error):
                self.store.read_result(snapshot.run_id)

    def test_worker_staged_result_is_verified_before_completion(self):
        amplitude = _Artifact({"format": "amplitude", "value": 1})
        continuous = _Artifact({"format": "continuous", "value": 2})
        sealed = self.store.publish_result(
            self.snapshot.run_id, amplitude, continuous,
            admission_sha256=SHA["1"],
            visual_candidate_sha256=SHA["2"], visual_revision=1,
            visual_decision_sha256=SHA["3"],
        )
        with patch(
            "autospine_workbench.p10_safety_analysis_result_store_v2."
            "require_p10_safety_analysis_result_documents_v2",
        ):
            self.assertEqual(
                (amplitude.document, continuous.document),
                self.store.verify_staged_result(
                    self.snapshot.run_id, sealed,
                ),
            )
            forged = dict(sealed)
            forged["continuous_sha256"] = SHA["9"]
            with self.assertRaises(P10SafetyAnalysisJobStoreV2Error):
                self.store.verify_staged_result(
                    self.snapshot.run_id, forged,
                )

    def test_result_rejects_request_analyzer_identity_drift(self):
        amplitude, continuous, sealed = _bound_documents(self.snapshot)
        request = self.snapshot.request.document
        request["analyzers_sha256"] = SHA["9"]
        with patch(
            "autospine_workbench.p10_safety_analysis_result_validation_v2."
            "require_body_sway_amplitude_envelope_candidate_v2",
        ), patch(
            "autospine_workbench.p10_safety_analysis_result_validation_v2."
            "require_sealed_body_sway_continuous_preview_proof_v2",
        ), self.assertRaises(P10SafetyAnalysisResultValidationV2Error):
            require_p10_safety_analysis_result_documents_v2(
                request, sealed, amplitude, continuous,
            )


def _bound_documents(snapshot):
    request = snapshot.request.document
    address = request["capture_address"]
    visual = {
        "candidate_v2_sha256": SHA["2"], "revision": 1,
        "decision_v2_sha256": SHA["3"],
        "head_decision_v2_sha256": SHA["3"],
    }
    admission = {
        "project_id": address["project_id"],
        "source": {
            "job": {
                "job_id": request["job_id"],
                "package_id": request["package_id"],
                "terminal_event_sha256": request["terminal_event_sha256"],
                "terminal_sequence": request["terminal_sequence"],
            },
            "evidence": {
                "temporary_preview_v2_sha256":
                    address["temporary_preview_v2_sha256"],
                "runtime_execution_bundle_sha256":
                    address["runtime_execution_bundle_sha256"],
                "capture_artifact_set_sha256":
                    address["capture_artifact_set_sha256"],
            },
            "visual_review": visual,
        },
    }
    amplitude = {
        "source": {
            "review_admission_v2_sha256": SHA["1"],
            "review_admission_v2": admission,
        },
        "analyzer": amplitude_analyzer_profile_v2(),
    }
    candidate_sha = canonical_sha256(amplitude)
    continuous = {
        "source": {
            "amplitude_envelope_candidate_v2": amplitude,
            "amplitude_envelope_candidate_v2_sha256": candidate_sha,
        },
        "analyzer": continuous_analyzer_profile_v2(),
    }
    sealed = {
        "authority_scope": "compile_time_snapshot",
        "admission_sha256": SHA["1"],
        "visual_candidate_sha256": SHA["2"], "visual_revision": 1,
        "visual_decision_sha256": SHA["3"],
        "amplitude_sha256": candidate_sha,
        "continuous_sha256": canonical_sha256(continuous),
        "amplitude_size_bytes": 1, "continuous_size_bytes": 1,
    }
    return amplitude, continuous, sealed


def _completed_snapshot(snapshot, sealed):
    event = snapshot.events[-1].build(
        snapshot.run_id, 2, snapshot.head_event_sha256,
        "completed", "completed", current=1, total=1, result=sealed,
    )
    return type(snapshot)(snapshot.request, snapshot.events + (event,))


if __name__ == "__main__":
    unittest.main()
