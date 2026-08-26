"""Integrated exact-chain fixture shared by P10.3 preview tests."""

from __future__ import annotations

from pathlib import Path

from autospine_workbench.body_sway_probe_inputs import (
    require_body_sway_probe_inputs,
)
from autospine_workbench.body_sway_probe_report import (
    compile_body_sway_probe_report,
)
from autospine_workbench.body_sway_preview_inputs import (
    require_body_sway_preview_inputs,
)
from autospine_workbench.idle_behavior_candidates import (
    compile_idle_behavior_candidates,
)
from autospine_workbench.idle_behavior_decision import (
    build_idle_behavior_decision,
)
from autospine_workbench.p10_exact_chain import load_p10_exact_chain
from tests.idle_behavior_decision_helpers import (
    adjust_decision,
    completed_review,
)
from tests.p10_candidate_helpers import P10PersistedFixture


class BodySwayPreviewFixture:
    """Build one persisted exact chain through accepted P10.2 evidence."""

    def __init__(self, root: Path) -> None:
        self.persisted = P10PersistedFixture(Path(root))
        source = self.persisted
        self.chain = load_p10_exact_chain(
            source.state, source.mesh.project_id, **source.command_kwargs
        )
        self.candidates = compile_idle_behavior_candidates(
            self.chain.manifest,
            self.chain.mesh_bundle,
            self.chain.retarget_bundle,
            self.chain.reviewed_contract,
        ).document
        self.decision = build_idle_behavior_decision(
            self.candidates,
            review=completed_review(),
            decisions=[adjust_decision(self.candidates)],
        ).document
        self.probe_inputs = require_body_sway_probe_inputs(
            self.chain.manifest,
            self.candidates,
            self.decision,
            self.chain.mesh_bundle,
            self.chain.retarget_bundle,
            self.chain.reviewed_contract,
        )
        self.report = compile_body_sway_probe_report(self.probe_inputs)
        self.preview_inputs = require_body_sway_preview_inputs(
            self.probe_inputs, self.report.document
        )
