"""Integrated exact P10.4b2 proof fixtures."""

from __future__ import annotations

from autospine_workbench.body_sway_amplitude_envelope import (
    compile_body_sway_amplitude_envelope_candidate,
)
from autospine_workbench.body_sway_continuous_proof_inputs import (
    require_body_sway_continuous_proof_inputs,
)
from tests.body_sway_amplitude_envelope_helpers import admitted_envelope_inputs


def admitted_continuous_proof_inputs(fixture):
    """Build the exact P10.4b1 result and bind its complete preview source."""

    _admission, amplitude_inputs = admitted_envelope_inputs(fixture)
    candidate = compile_body_sway_amplitude_envelope_candidate(
        amplitude_inputs
    )
    return require_body_sway_continuous_proof_inputs(
        candidate, amplitude_inputs
    )
