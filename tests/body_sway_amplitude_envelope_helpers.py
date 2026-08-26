"""Integrated P10.4b1 test helpers over exact approved review evidence."""

from __future__ import annotations

from autospine_workbench.body_sway_amplitude_envelope_inputs import (
    require_body_sway_amplitude_envelope_inputs,
)
from autospine_workbench.p10_review_admission_commands import (
    compile_body_sway_review_admission_command,
)
from tests.body_sway_runtime_capture_helpers import fake_runtime_profile


def admitted_envelope_inputs(fixture):
    """Replay a P10ReviewAdmissionFixture into exact envelope inputs."""

    with fake_runtime_profile():
        admitted = compile_body_sway_review_admission_command(
            *fixture.command_args, **fixture.command_kwargs
        )
    preview = admitted._preview_result
    inputs = require_body_sway_amplitude_envelope_inputs(
        admitted._admission, preview._inputs, preview._preview
    )
    return admitted, inputs
