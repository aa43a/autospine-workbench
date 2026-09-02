"""Real store-boundary tests for exact P10.5d v2 upstream loading."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for item in (ROOT, SRC):
    if str(item) not in sys.path:
        sys.path.insert(0, str(item))

from autospine_workbench.body_sway_amplitude_envelope_profile_v2 import (  # noqa: E402
    amplitude_analyzer_profile_v2,
)
from autospine_workbench.body_sway_continuous_proof_profile_v2 import (  # noqa: E402
    continuous_analyzer_profile_v2,
)
from autospine_workbench.p10_dynamic_seam_inputs_v2 import (  # noqa: E402
    P10DynamicSeamInputsV2Error,
    load_p10_dynamic_seam_inputs_v2,
)
from autospine_workbench.p10_capture_job_contract import (  # noqa: E402
    P10CaptureJobEvent, P10CaptureJobRequest,
)
from autospine_workbench.p10_capture_job_store import (  # noqa: E402
    P10CaptureJobSnapshot,
)
from autospine_workbench.p10_completed_job_snapshot import (  # noqa: E402
    verified_completed_p10_capture_job,
)
from autospine_workbench.p10_safety_analysis_job_contract_v2 import (  # noqa: E402
    P10SafetyAnalysisRunRequestV2,
)
from autospine_workbench.p10_safety_analysis_job_store_v2 import (  # noqa: E402
    P10SafetyAnalysisJobStoreV2,
)
from autospine_workbench.resolved_project import canonical_sha256  # noqa: E402
from tests.p10_safety_analysis_job_v2_test_helpers import SHA  # noqa: E402
from tests.reviewed_seam_anchor_set_bundle_helpers import (  # noqa: E402
    PersistedReviewedSeamAnchorSetFixture,
)


RESULT_VALIDATION = (
    "autospine_workbench.p10_safety_analysis_result_validation_v2."
)


@dataclass(frozen=True)
class _Artifact:
    document: dict

    @property
    def canonical_bytes(self):
        return json.dumps(
            self.document, ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")

    @property
    def sha256(self):
        return canonical_sha256(self.document)


class _Fixture:
    def __init__(self, root: Path) -> None:
        self.seam = PersistedReviewedSeamAnchorSetFixture(
            root, advance=False,
        )
        self.state = self.seam.state
        self.completed = _completed_for_project(
            self.seam.published.project_id,
        )
        self.store = P10SafetyAnalysisJobStoreV2(self.state)
        self.snapshot, self.amplitude, self.continuous = self.add_run(
            format_version=2, attempt=1, previous_run_id=None,
        )

    def add_run(self, *, format_version, attempt, previous_run_id):
        request = P10SafetyAnalysisRunRequestV2.build(
            self.completed, attempt=attempt,
            previous_run_id=previous_run_id,
        )
        snapshot = self.store.create(request)
        amplitude, continuous = _documents(
            snapshot.request.document, format_version,
        )
        sealed = self.store.publish_result(
            snapshot.run_id, _Artifact(amplitude), _Artifact(continuous),
            admission_sha256=SHA["1"],
            visual_candidate_sha256=SHA["2"], visual_revision=1,
            visual_decision_sha256=SHA["3"],
        )
        snapshot = self.store.append(
            snapshot.run_id, "completed", "completed",
            expected_previous=snapshot.head_event_sha256,
            current=1, total=1, result=sealed,
        )
        return snapshot, amplitude, continuous

    def load(self, **changes):
        published = self.seam.published
        arguments = {
            "state_root": self.state,
            "project_id": published.project_id,
            "safety_run_id": self.snapshot.run_id,
            "continuous_proof_sha256": canonical_sha256(self.continuous),
            "reviewed_set_sha256": published.set_sha256,
            "reviewed_set_bundle_sha256": published.bundle_sha256,
        }
        arguments.update(changes)
        return load_p10_dynamic_seam_inputs_v2(**arguments)


def _completed_for_project(project_id):
    request = P10CaptureJobRequest.from_payload({
        "package_id": SHA["1"],
        "client_request_id": "dynamic-seam-input-test",
        "expected_p10_1": {
            "candidate_sha256": SHA["2"],
            "decision_sha256": SHA["3"], "revision": 1,
        },
        "expected_framing": {
            "candidate_sha256": SHA["4"],
            "decision_sha256": SHA["5"], "revision": 1,
        },
        "explicit_runtime_license_confirmation": True,
        "explicit_run_confirmation": True,
    })
    rows = (
        ("queued", {}), ("exact_replay", {}),
        ("preview_compiled", {}), ("runtime_verified", {}),
        ("capturing", {"current": 1, "total": 1}),
        ("sealing", {}),
        ("completed", {"addresses": {
            "project": project_id, "preview": SHA["6"],
            "execution_bundle": SHA["7"], "artifact": SHA["8"],
        }}),
    )
    events, previous = [], None
    for sequence, (status, payload) in enumerate(rows, 1):
        event = P10CaptureJobEvent.build(
            request.job_id, sequence, status,
            previous.event_sha if previous else None, **payload,
        )
        events.append(event)
        previous = event
    public = P10CaptureJobSnapshot(
        request, tuple(events),
    ).public_document()
    return verified_completed_p10_capture_job(public, request.job_id)


def _documents(request, format_version):
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
        "format": "autospine-body-sway-amplitude-envelope-candidate",
        "format_version": format_version,
        "project_id": address["project_id"], "clip_id": "idle",
        "source": {
            "review_admission_v2_sha256": SHA["1"],
            "review_admission_v2": admission,
        },
        "analyzer": amplitude_analyzer_profile_v2(),
    }
    continuous = {
        "format": "autospine-body-sway-continuous-preview-proof",
        "format_version": format_version,
        "project_id": address["project_id"], "clip_id": "idle",
        "source": {
            "amplitude_envelope_candidate_v2_sha256":
                canonical_sha256(amplitude),
            "amplitude_envelope_candidate_v2": amplitude,
        },
        "analyzer": continuous_analyzer_profile_v2(),
    }
    return amplitude, continuous


def _require_v2(document):
    if document.get("format_version") != 2:
        raise ValueError("wrong proof version")


@contextmanager
def _validated_result_documents():
    with patch(
        RESULT_VALIDATION + "require_body_sway_amplitude_envelope_candidate_v2",
        side_effect=_require_v2,
    ), patch(
        RESULT_VALIDATION
        + "require_sealed_body_sway_continuous_preview_proof_v2",
        side_effect=_require_v2,
    ), patch(
        RESULT_VALIDATION
        + "body_sway_amplitude_envelope_candidate_sha256_v2",
        side_effect=canonical_sha256,
    ):
        yield


class P10DynamicSeamInputsV2Tests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.fixture = _Fixture(Path(self.temporary.name))

    def tearDown(self):
        self.temporary.cleanup()

    def test_completed_proof_and_reviewed_bundle_are_exact_read(self):
        with _validated_result_documents():
            loaded = self.fixture.load()
        published = self.fixture.seam.published
        self.assertEqual(self.fixture.continuous, loaded.continuous_proof)
        self.assertEqual(published.set_sha256, loaded.reviewed_set_sha256)
        self.assertEqual(
            published.bundle_sha256, loaded.reviewed_set_bundle_sha256,
        )
        self.assertEqual(
            published.review_revision,
            loaded.reviewed_bundle.review_revision,
        )

    def test_stale_or_crosswired_exact_addresses_fail_closed(self):
        attacks = (
            {"continuous_proof_sha256": "f" * 64},
            {"project_id": "other-project"},
            {"reviewed_set_sha256": "e" * 64},
            {"reviewed_set_bundle_sha256": "d" * 64},
        )
        for changes in attacks:
            with self.subTest(changes=changes), \
                    _validated_result_documents(), self.assertRaises(
                        P10DynamicSeamInputsV2Error
                    ):
                self.fixture.load(**changes)

    def test_v1_result_at_an_exact_completed_address_is_rejected(self):
        first = self.fixture.snapshot
        second, _amplitude, continuous = self.fixture.add_run(
            format_version=1, attempt=2,
            previous_run_id=first.run_id,
        )
        with _validated_result_documents(), self.assertRaises(
            P10DynamicSeamInputsV2Error
        ):
            self.fixture.load(
                safety_run_id=second.run_id,
                continuous_proof_sha256=canonical_sha256(continuous),
            )

    def test_incomplete_run_is_not_an_exact_proof_source(self):
        request = P10SafetyAnalysisRunRequestV2.build(
            self.fixture.completed, attempt=2,
            previous_run_id=self.fixture.snapshot.run_id,
        )
        queued = self.fixture.store.create(request)
        with self.assertRaises(P10DynamicSeamInputsV2Error):
            self.fixture.load(
                safety_run_id=queued.run_id,
                continuous_proof_sha256="c" * 64,
            )


if __name__ == "__main__":
    unittest.main()
