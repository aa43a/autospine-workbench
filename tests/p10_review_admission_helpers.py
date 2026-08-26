"""Integrated exact P10.4a preview, capture, and review fixture."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path

from autospine_workbench.body_sway_runtime_capture import (
    compile_body_sway_runtime_capture,
)
from autospine_workbench.body_sway_runtime_capture_collector import (
    BodySwayRuntimeCaptureCollector,
)
from autospine_workbench.body_sway_runtime_capture_store import (
    BodySwayRuntimeCaptureStore,
)
from autospine_workbench.body_sway_visual_review_address import (
    ExactVisualReviewAddress,
)
from autospine_workbench.body_sway_visual_review_application import (
    BodySwayVisualReviewApplication,
)
from autospine_workbench.body_sway_visual_review_candidate_validation import (
    body_sway_visual_review_candidate_sha256,
)
from autospine_workbench.body_sway_visual_review_decision_validation import (
    body_sway_visual_review_decision_sha256,
    visual_review_decision_source,
)
from autospine_workbench.body_sway_visual_review_profile import (
    body_sway_case_evidence_sha256,
)
from autospine_workbench.browser_executable_snapshot import (
    BrowserExecutableSnapshot,
)
from tests.body_sway_runtime_capture_helpers import (
    RuntimeCaptureFixture,
    capture_png,
    fake_runtime_profile,
)
from tests.body_sway_visual_review_helpers import review_rows
from tests.p10_decision_command_helpers import write_json


class P10ReviewAdmissionFixture:
    """Publish one exact approved visual head over persisted P10 evidence."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        runtime = RuntimeCaptureFixture(self.root)
        self.preview_fixture = runtime.preview_fixture
        self.preview = runtime.preview
        self.state_root = self.preview_fixture.persisted.state
        inputs = self.root / "admission-inputs"
        inputs.mkdir()
        self.candidates_path = write_json(
            inputs / "candidates.json", self.preview_fixture.candidates
        )
        self.decision_path = write_json(
            inputs / "decision.json", self.preview_fixture.decision
        )
        self.probe_report_path = write_json(
            inputs / "probe-report.json", self.preview_fixture.report.document
        )
        with fake_runtime_profile():
            collector = BodySwayRuntimeCaptureCollector(runtime.sessions)
            for index, case_id in enumerate(collector.case_ids):
                collector.record_capture(
                    case_id,
                    capture_png(pixel=(30 + index, 50, 70, 255)),
                    device_pixel_ratio=1,
                )
            browser = BrowserExecutableSnapshot(
                path=str(self.root / "chromium.exe"),
                family="chromium",
                reported_version="128.0.6613.0",
                version_output_sha256=hashlib.sha256(
                    b"Chromium 128.0.6613.0\n"
                ).hexdigest(),
                executable_sha256="b" * 64,
                size_bytes=4096,
            )
            capture = compile_body_sway_runtime_capture(
                self.preview, runtime.runtime, runtime.sessions,
                collector.snapshot(), browser,
            )
            published = BodySwayRuntimeCaptureStore(
                self.state_root
            ).publish(capture)
            self.address = ExactVisualReviewAddress(
                published.project_id,
                published.temporary_preview_sha256,
                published.bundle_sha256,
                published.artifact_set_sha256,
            )
            self.application = BodySwayVisualReviewApplication(self.state_root)
            prepared = self.application.prepare(self.address)
            self.approved = self.application.submit(
                self.address, self.payload(prepared, "approve")
            )
        self.visual_candidate_sha256 = prepared.candidate_sha256

    @property
    def command_kwargs(self) -> dict:
        return {
            **self.preview_fixture.persisted.command_kwargs,
            "temporary_preview_sha256": self.address.temporary_preview_sha256,
            "runtime_capture_bundle_sha256":
                self.address.runtime_capture_bundle_sha256,
            "capture_artifact_set_sha256":
                self.address.capture_artifact_set_sha256,
            "visual_candidate_sha256": self.visual_candidate_sha256,
            "visual_revision": self.approved.revision,
            "visual_decision_sha256": self.approved.decision_sha256,
        }

    def payload(self, prepared, action: str) -> dict:
        return {
            "base_revision": prepared.history.current_revision,
            "candidate_sha256": prepared.candidate_sha256,
            "previous_decision_sha256":
                prepared.history.head_decision_sha256,
            "review": {
                "reviewer_id": "p10-admission-reviewer",
                "notes": f"{action} every sampled still",
            },
            "decisions": review_rows(
                prepared.candidate_document, action=action
            ),
        }

    def append(self, action: str):
        with fake_runtime_profile():
            prepared = self.application.prepare(self.address)
            return self.application.submit(
                self.address, self.payload(prepared, action)
            )

    @property
    def command_args(self) -> tuple:
        return (
            self.state_root,
            self.address.project_id,
            self.candidates_path,
            self.decision_path,
            self.probe_report_path,
        )


def forge_capture_detached_admission_input(inputs):
    """Build a self-sealed candidate/decision/history detached from capture."""

    public = inputs.candidate_document
    case = public["cases"][0]
    image = case["image"]
    image["png_sha256"] = "0" * 64
    path = f"captures/{case['case_id']}.png"
    captured_case = {
        "case_id": case["case_id"],
        "animation": case["animation"],
        "tick": case["tick"],
        "time_seconds": case["time_seconds"],
        "image_path": path,
        "png_sha256": image["png_sha256"],
    }
    artifact = {
        "path": path,
        "role": "official-runtime-capture",
        "case_id": case["case_id"],
        "sha256": image["png_sha256"],
        "size_bytes": image["size_bytes"],
        "width": image["width"],
        "height": image["height"],
    }
    case["evidence_sha256"] = body_sway_case_evidence_sha256(
        captured_case, artifact
    )
    full_candidate = deepcopy(public)
    for row in full_candidate["cases"]:
        row["image"]["path"] = f"captures/{row['case_id']}.png"
    candidate_sha = body_sway_visual_review_candidate_sha256(full_candidate)
    decision = inputs.decision_document
    decision["source"] = visual_review_decision_source(full_candidate)
    decision["decisions"][0]["evidence_sha256"] = case[
        "evidence_sha256"
    ]
    decision_sha = body_sway_visual_review_decision_sha256(decision)
    history = replace(
        inputs.history_before,
        candidate_sha256=candidate_sha,
        head_decision_sha256=decision_sha,
        rows=tuple(
            replace(row, decision_sha256=decision_sha)
            for row in inputs.history_before.rows
        ),
    )
    return replace(
        inputs,
        visual_candidate_sha256=candidate_sha,
        visual_decision_sha256=decision_sha,
        history_before=history,
        history_after=history,
        _candidate_json=_canonical(public),
        _decision_json=_canonical(decision),
    )


def _canonical(value) -> str:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False,
        sort_keys=True, separators=(",", ":"),
    )
