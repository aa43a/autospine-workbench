"""Integrated exact P10.2b/P10.3 v2 fixture shared by focused tests."""

from __future__ import annotations

from pathlib import Path

from autospine_workbench.body_sway_probe_inputs import (
    require_body_sway_probe_inputs,
)
from autospine_workbench.body_sway_probe_report import (
    compile_body_sway_probe_report,
)
from autospine_workbench.body_sway_preview_inputs_v2 import (
    require_body_sway_preview_inputs_v2,
)
from autospine_workbench.body_sway_remediation_analysis import (
    compile_body_sway_remediation_analysis,
)
from autospine_workbench.capture_framing_candidate import (
    compile_capture_framing_candidate,
)
from autospine_workbench.capture_framing_decision import (
    build_capture_framing_decision,
)
from autospine_workbench.capture_framing_history import (
    load_capture_framing_head,
    publish_capture_framing_decision,
    snapshot_capture_framing_history,
)
from autospine_workbench.idle_behavior_candidates import (
    compile_idle_behavior_candidates,
)
from autospine_workbench.idle_behavior_decision import (
    build_idle_behavior_decision,
)
from autospine_workbench.idle_behavior_review_head import (
    read_idle_behavior_review_head,
)
from autospine_workbench.idle_behavior_review_store import (
    IdleBehaviorReviewStore,
)
from tests.idle_behavior_decision_helpers import (
    adjust_decision,
    completed_review,
)
from tests.idle_behavior_helpers import IdleBehaviorFixture


PACKAGE_ID = "9" * 64


class PreviewV2Fixture:
    def __init__(self, root: Path, *, action: str = "accept") -> None:
        self.fixture = IdleBehaviorFixture(root)
        self.candidates = compile_idle_behavior_candidates(
            self.fixture.manifest, self.fixture.mesh,
            self.fixture.retarget, self.fixture.reviewed,
        ).document
        self.p10_decision = build_idle_behavior_decision(
            self.candidates, review=completed_review(),
            decisions=[adjust_decision(self.candidates)],
        )
        self.inputs = require_body_sway_probe_inputs(
            self.fixture.manifest, self.candidates,
            self.p10_decision.document, self.fixture.mesh,
            self.fixture.retarget, self.fixture.reviewed,
        )
        self.state = root / "state"
        self.state.mkdir()
        IdleBehaviorReviewStore(self.state).publish(
            self.p10_decision, self.candidates,
            base_revision=0, previous_decision_sha256=None,
        )
        self.report = compile_body_sway_probe_report(self.inputs)
        remediation = compile_body_sway_remediation_analysis(
            self.inputs, self.report,
        )
        self.candidate = compile_capture_framing_candidate(
            self.inputs, self.report, remediation.dynamic_viewport,
            read_idle_behavior_review_head(self.state, self.candidates),
            package_id=PACKAGE_ID,
        )
        self.framing_decision = self._decision(action)
        publish_capture_framing_decision(
            self.state, self.framing_decision, self.candidate,
            base_revision=0, previous_decision_sha256=None,
        )

    def _decision(self, action, *, revision=1, previous=None):
        return build_capture_framing_decision(
            self.candidate, action=action,
            world_viewport=(
                self.candidate.document["proposed_world_viewport"]
                if action == "adjust" else None
            ),
            reason_code={
                "accept": "human-approved-automatic-capture-framing-v1",
                "adjust": "human-adjusted-capture-framing-v1",
                "reject": "human-rejected-capture-framing-v1",
                "unobservable":
                    "human-marked-capture-framing-unobservable-v1",
            }[action],
            revision=revision,
            supersedes_decision_sha256=(
                None if previous is None else previous.sha256
            ),
            previous_decision=previous,
        )

    def current(self):
        decision = load_capture_framing_head(self.state, self.candidate)
        history = snapshot_capture_framing_history(
            self.state, self.candidate,
        )
        return decision, history

    def admit(self, *, report=None, candidate=None, decision=None, history=None):
        current_decision, current_history = self.current()
        return require_body_sway_preview_inputs_v2(
            self.inputs, report or self.report,
            candidate or self.candidate,
            decision or current_decision,
            history or current_history,
            state_root=self.state, package_id=PACKAGE_ID,
        )
