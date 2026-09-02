"""Shared exact P10.4a v2 admission fixture with cheap state clones."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace

from autospine_workbench.body_sway_review_admission_inputs_v2 import (
    build_body_sway_review_admission_input_v2,
)
from autospine_workbench.body_sway_review_admission_v2 import (
    compile_body_sway_review_admission_v2,
)
from autospine_workbench.body_sway_visual_review_application_v2 import (
    BodySwayVisualReviewApplicationV2,
)
from autospine_workbench.p10_preview_v2_result import (
    preview_v2_command_result,
)
from autospine_workbench.p10_capture_job_contract import (
    P10CaptureJobEvent, P10CaptureJobRequest,
)
from autospine_workbench.p10_capture_job_store import P10CaptureJobSnapshot
from autospine_workbench.p10_completed_job_snapshot import (
    verified_completed_p10_capture_job,
)
from autospine_workbench.p10_visual_review_v2_context import (
    P10VisualReviewV2Context,
)
from autospine_workbench.p10_visual_review_v2_verified_mount import (
    VerifiedP10VisualReviewV2Mount,
)
from autospine_workbench.project_store import ProjectStore
from tests.body_sway_visual_review_v2_helpers import (
    BodySwayVisualReviewV2Fixture,
    build_visual_review_v2_inputs,
    fake_runtime_profile_v2,
    review_rows_v2,
)


PACKAGE_ID = "a" * 64


@dataclass(frozen=True)
class P10ReviewAdmissionV2State:
    """A copied decision store backed by the fixture's immutable mount."""

    state_root: Path
    store: ProjectStore
    application: BodySwayVisualReviewApplicationV2


class P10ReviewAdmissionV2Fixture:
    """Build expensive preview/capture bytes once and one approved v2 head."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        preview, execution = build_visual_review_v2_inputs(
            self.root / "evidence",
        )
        visual = BodySwayVisualReviewV2Fixture(
            self.root / "published", preview, execution,
        )
        self.state_root = visual.state_root
        self.preview = preview
        self.execution = visual.verified
        self.address = visual.address
        self.store = ProjectStore(
            self.root / "workspace", state_root=self.state_root,
            measure_composite_quality=False,
        )
        result = preview_v2_command_result(
            self.store, PACKAGE_ID, preview,
        )
        self.mount = VerifiedP10VisualReviewV2Mount(
            SimpleNamespace(result=result), visual.verified,
        )
        completed_job = _completed_job(result, self.address)
        self.context = P10VisualReviewV2Context(
            completed_job.job_id, completed_job.package_id,
            self.address, self.mount,
            completed_job.terminal_event_sha256,
            completed_job.terminal_sequence, completed_job,
        )
        self.application = BodySwayVisualReviewApplicationV2(
            self.state_root,
        )
        with fake_runtime_profile_v2():
            initial = self.application.prepare(self.address, self.mount)
            self.approved = self.application.submit(
                self.address, self.mount, self.payload(initial, "approve"),
            )
            self.before = self.application.prepare(self.address, self.mount)
            self.exact = self.application.exact_decision(
                self.address, self.mount,
                candidate_sha256=self.approved.candidate_sha256,
                revision=self.approved.revision,
                decision_sha256=self.approved.decision_sha256,
            )
            self.after = self.application.prepare(self.address, self.mount)
            self.inputs = build_body_sway_review_admission_input_v2(
                self.context, self.before, self.exact,
                self.context, self.after,
                candidate_sha256=self.approved.candidate_sha256,
                revision=self.approved.revision,
                decision_sha256=self.approved.decision_sha256,
            )
            self.admission = compile_body_sway_review_admission_v2(
                self.inputs,
            )

    @staticmethod
    def payload(prepared, action: str) -> dict:
        return {
            "base_revision": prepared.history.current_revision,
            "candidate_sha256": prepared.candidate_sha256,
            "previous_decision_sha256":
                prepared.history.head_decision_sha256,
            "review": {
                "reviewer_id": "p10-v2-admission-test",
                "notes": f"{action} sampled official-runtime evidence",
            },
            "decisions": review_rows_v2(
                prepared.candidate_document, action=action,
            ),
        }

    def copy_state(self, root: Path) -> P10ReviewAdmissionV2State:
        state_root = Path(root) / "state"
        shutil.copytree(self.state_root, state_root)
        store = ProjectStore(
            Path(root) / "workspace", state_root=state_root,
            measure_composite_quality=False,
        )
        return P10ReviewAdmissionV2State(
            state_root, store, BodySwayVisualReviewApplicationV2(state_root),
        )

    def append(self, state: P10ReviewAdmissionV2State, action: str):
        with fake_runtime_profile_v2():
            prepared = state.application.prepare(self.address, self.mount)
            return state.application.submit(
                self.address, self.mount, self.payload(prepared, action),
            )

    def context_with(self, **changes) -> P10VisualReviewV2Context:
        return replace(self.context, **changes)


def build_admission_inputs(fixture, *, context_after=None, after=None):
    """Rebuild from fixture observations, optionally replacing B."""

    return build_body_sway_review_admission_input_v2(
        fixture.context, fixture.before, fixture.exact,
        context_after or fixture.context, after or fixture.after,
        candidate_sha256=fixture.approved.candidate_sha256,
        revision=fixture.approved.revision,
        decision_sha256=fixture.approved.decision_sha256,
    )


def _completed_job(result, address):
    source = result.document["source"]
    request = P10CaptureJobRequest.from_payload({
        "package_id": PACKAGE_ID,
        "client_request_id": "p10-v2-admission-fixture",
        "expected_p10_1": source["current_p10_1_head"],
        "expected_framing": {
            "candidate_sha256": result.capture_framing_candidate_sha256,
            "decision_sha256": result.capture_framing_decision_sha256,
            "revision": result.capture_framing_revision,
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
            "project": address.project_id,
            "preview": address.temporary_preview_v2_sha256,
            "execution_bundle": address.runtime_execution_bundle_sha256,
            "artifact": address.capture_artifact_set_sha256,
        }}),
    )
    events = []
    previous = None
    for sequence, (status, payload) in enumerate(rows, 1):
        event = P10CaptureJobEvent.build(
            request.job_id, sequence, status,
            previous.event_sha if previous else None, **payload,
        )
        events.append(event)
        previous = event
    snapshot = P10CaptureJobSnapshot(request, tuple(events)).public_document()
    return verified_completed_p10_capture_job(snapshot, request.job_id)


_SHARED_TEMPORARY = None
_SHARED_FIXTURE = None


def shared_p10_review_admission_v2_fixture():
    """Lazily share the 14-second immutable evidence build across modules."""

    global _SHARED_TEMPORARY, _SHARED_FIXTURE
    if _SHARED_FIXTURE is None:
        _SHARED_TEMPORARY = tempfile.TemporaryDirectory()
        _SHARED_FIXTURE = P10ReviewAdmissionV2Fixture(
            Path(_SHARED_TEMPORARY.name),
        )
    return _SHARED_FIXTURE


def recursive_keys(value):
    """Return every mapping key in a JSON-like test value."""
    if type(value) is dict:
        result = set(value)
        for item in value.values():
            result.update(recursive_keys(item))
        return result
    if type(value) is list:
        result = set()
        for item in value:
            result.update(recursive_keys(item))
        return result
    return set()
