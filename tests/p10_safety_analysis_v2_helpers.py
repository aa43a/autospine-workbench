"""Shared exact P10.4b v2 compiler fixture."""

from __future__ import annotations

from types import SimpleNamespace

from autospine_workbench.body_sway_amplitude_envelope_v2 import (
    compile_body_sway_amplitude_envelope_candidate_v2,
)
from autospine_workbench.body_sway_continuous_proof_v2 import (
    compile_body_sway_continuous_preview_proof_v2,
)
from autospine_workbench.body_sway_preview_projection_v2 import (
    compile_body_sway_preview_projection_v2,
)
from autospine_workbench.body_sway_review_admission_consumer_v2 import (
    CurrentBodySwayReviewAdmissionV2,
)
from autospine_workbench.p10_review_admission_v2_commands import _result
from autospine_workbench.p10_safety_analysis_source_v2 import (
    P10SafetyAnalysisSourceV2,
)
from tests.p10_review_admission_v2_helpers import (
    shared_p10_review_admission_v2_fixture,
)


class P10SafetyAnalysisV2Fixture:
    def __init__(self) -> None:
        fixture = shared_p10_review_admission_v2_fixture()
        command = _result(fixture.inputs, fixture.admission)
        self.admission = CurrentBodySwayReviewAdmissionV2(
            command.admission_sha256, command,
        )
        self.source = P10SafetyAnalysisSourceV2(
            fixture.context.package_id,
            SimpleNamespace(result=fixture.preview_result),
            fixture.preview_inputs,
            compile_body_sway_preview_projection_v2(fixture.preview_inputs),
            fixture.mesh_bundle,
        )
        self.amplitude = compile_body_sway_amplitude_envelope_candidate_v2(
            self.admission, self.source,
        )
        self.continuous = compile_body_sway_continuous_preview_proof_v2(
            self.amplitude, self.source,
        )


_SHARED = None


def shared_p10_safety_analysis_v2_fixture():
    global _SHARED
    if _SHARED is None:
        _SHARED = P10SafetyAnalysisV2Fixture()
    return _SHARED

