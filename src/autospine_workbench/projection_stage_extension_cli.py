"""Registration and dispatch for P9/P10 projection-stage extensions."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .p9_bundle_cli import add_p9_bundle_subcommands, dispatch_p9_bundle_command
from .p9_policy_cli import add_p9_policy_subcommands, dispatch_p9_policy_command
from .p9_readonly_cli import add_p9_readonly_subcommands, dispatch_p9_readonly_command
from .p9_review_draft_cli import (
    add_p9_review_draft_subcommand,
    dispatch_p9_review_draft_command,
)
from .p9_v2_cli import add_p9_v2_subcommands, dispatch_p9_v2_command
from .p10_amplitude_envelope_cli import (
    add_p10_amplitude_envelope_subcommands,
    dispatch_p10_amplitude_envelope_command,
)
from .p10_candidate_cli import (
    add_p10_candidate_subcommands,
    dispatch_p10_candidate_command,
)
from .p10_continuous_proof_cli import (
    add_p10_continuous_proof_subcommands,
    dispatch_p10_continuous_proof_command,
)
from .p10_decision_cli import (
    add_p10_decision_subcommands,
    dispatch_p10_decision_command,
)
from .p10_dynamic_seam_stage_cli import (
    add_p10_dynamic_seam_subcommands,
    dispatch_p10_dynamic_seam_command,
)
from .p10_motion_consumer_admission_stage_cli import (
    add_p10_motion_consumer_admission_subcommands,
    dispatch_p10_motion_consumer_admission_command,
)
from .p10_motion_instance_v3_stage_cli import (
    add_p10_motion_instance_v3_subcommands,
    dispatch_p10_motion_instance_v3_command,
)
from .p10_preview_cli import add_p10_preview_subcommands, dispatch_p10_preview_command
from .p10_probe_cli import add_p10_probe_subcommands, dispatch_p10_probe_command
from .p10_review_admission_cli import (
    add_p10_review_admission_subcommands,
    dispatch_p10_review_admission_command,
)
from .p10_review_admission_v2_cli import (
    add_p10_review_admission_v2_subcommands,
    dispatch_p10_review_admission_v2_command,
)
from .p10_runtime_capture_cli import (
    add_p10_runtime_capture_subcommands,
    dispatch_p10_runtime_capture_command,
)
from .p10_safety_analysis_v2_cli import (
    add_p10_safety_analysis_v2_subcommands,
    dispatch_p10_safety_analysis_v2_command,
)
from .p10_spine42_v3_stage_cli import (
    add_p10_spine42_v3_subcommands,
    dispatch_p10_spine42_v3_command,
)
from .p10_spine42_v3_raster_review_cli import (
    add_p10_spine42_v3_raster_review_subcommands,
    dispatch_p10_spine42_v3_raster_review_command,
)
from .p10_spine42_v3_readiness_cli import (
    add_p10_spine42_v3_readiness_subcommands,
    dispatch_p10_spine42_v3_readiness_command,
)
from .p10_spine42_v3_runtime_cli import (
    add_p10_spine42_v3_runtime_subcommands,
    dispatch_p10_spine42_v3_runtime_command,
)
from .p10_spine42_v3_setup_regression_cli import (
    add_p10_spine42_v3_setup_regression_subcommands,
    dispatch_p10_spine42_v3_setup_regression_command,
)
from .p10_visual_review_cli import (
    add_p10_visual_review_subcommands,
    dispatch_p10_visual_review_command,
)
from .seam_anchor_candidate_cli import (
    add_seam_anchor_candidate_subcommands,
)
from .seam_anchor_review_cli import (
    add_seam_anchor_review_subcommands,
)


def add_projection_stage_extension_subcommands(
    subparsers: Any,
    state_root: Path,
) -> None:
    """Register the ordered P9/P10 command families."""

    for register in _STATE_ROOT_REGISTRARS:
        register(subparsers, state_root)
        if register is add_p10_candidate_subcommands:
            add_p10_decision_subcommands(subparsers)


def dispatch_projection_stage_extension_command(args) -> int | None:
    """Dispatch the first P9/P10 family that recognizes ``args``."""

    for dispatch in _DISPATCHERS:
        status = dispatch(args)
        if status is not None:
            return status
    return None


_STATE_ROOT_REGISTRARS = (
    add_p9_readonly_subcommands,
    add_p9_review_draft_subcommand,
    add_p9_policy_subcommands,
    add_p9_v2_subcommands,
    add_p9_bundle_subcommands,
    add_p10_candidate_subcommands,
    add_p10_probe_subcommands,
    add_p10_preview_subcommands,
    add_p10_runtime_capture_subcommands,
    add_p10_visual_review_subcommands,
    add_p10_review_admission_subcommands,
    add_p10_review_admission_v2_subcommands,
    add_p10_safety_analysis_v2_subcommands,
    add_p10_amplitude_envelope_subcommands,
    add_p10_continuous_proof_subcommands,
    add_p10_dynamic_seam_subcommands,
    add_p10_motion_consumer_admission_subcommands,
    add_p10_motion_instance_v3_subcommands,
    add_p10_spine42_v3_subcommands,
    add_p10_spine42_v3_runtime_subcommands,
    add_p10_spine42_v3_raster_review_subcommands,
    add_p10_spine42_v3_readiness_subcommands,
    add_p10_spine42_v3_setup_regression_subcommands,
    add_seam_anchor_candidate_subcommands,
    add_seam_anchor_review_subcommands,
)

_DISPATCHERS = (
    dispatch_p9_review_draft_command,
    dispatch_p9_readonly_command,
    dispatch_p9_policy_command,
    dispatch_p9_v2_command,
    dispatch_p9_bundle_command,
    dispatch_p10_candidate_command,
    dispatch_p10_decision_command,
    dispatch_p10_probe_command,
    dispatch_p10_preview_command,
    dispatch_p10_runtime_capture_command,
    dispatch_p10_visual_review_command,
    dispatch_p10_review_admission_command,
    dispatch_p10_review_admission_v2_command,
    dispatch_p10_safety_analysis_v2_command,
    dispatch_p10_amplitude_envelope_command,
    dispatch_p10_continuous_proof_command,
    dispatch_p10_dynamic_seam_command,
    dispatch_p10_motion_consumer_admission_command,
    dispatch_p10_motion_instance_v3_command,
    dispatch_p10_spine42_v3_command,
    dispatch_p10_spine42_v3_runtime_command,
    dispatch_p10_spine42_v3_raster_review_command,
    dispatch_p10_spine42_v3_readiness_command,
    dispatch_p10_spine42_v3_setup_regression_command,
)


__all__ = [
    "add_projection_stage_extension_subcommands",
    "dispatch_projection_stage_extension_command",
]
