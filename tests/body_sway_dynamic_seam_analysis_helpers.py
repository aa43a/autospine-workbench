"""Small exact backend fixtures for P10.5d high-level analysis tests."""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
from copy import deepcopy
from unittest.mock import patch

from autospine_workbench.body_sway_dynamic_seam_interval import (
    BodySwayDynamicSeamIntervalProof,
)
from autospine_workbench.body_sway_dynamic_seam_interval_results import (
    BodySwayDynamicSeamPairProof,
    BodySwayDynamicSeamRelationshipProof,
)
from tests.body_sway_dynamic_seam_interval_helpers import full_sample
from tests.body_sway_dynamic_seam_locator_helpers import reviewed_set


ANALYSIS = "autospine_workbench.body_sway_dynamic_seam_analysis."
COMPILER = "autospine_workbench.body_sway_dynamic_seam."


class FixedSampler:
    def __init__(self, context):
        self._context = context

    def sample(self, tick):
        return full_sample(self._context, tick=tick)


def admitted_source(rig, *, ticks=(0, 1), upstream_certified=True):
    return {
        "source_set_sha256": "a" * 64,
        "body_sway_continuous_preview_proof": {
            "project_id": "fixture-project",
            "clip_id": "idle",
            "status": (
                "continuous_preview_model_structural_certified"
                if upstream_certified else "indeterminate"
            ),
            "source": {
                "amplitude_envelope_candidate": {
                    "timing": {},
                    "reviewed_selection": {"parameters": {
                        "cycles": 1,
                        "per_bone_amplitude_deg": {},
                        "per_bone_phase_fraction": {},
                    }},
                },
                "motion_instance_v2": {"tracks": []},
                "preview_projection": {"sample_ticks": list(ticks)},
                "rig_ir": deepcopy(rig),
                "target_profile": {},
            },
        },
        "reviewed_seam_anchor_set": reviewed_set(rig),
    }


def certified_proof(
    locators, left_tick, right_tick, *, boxes=1, depth=0, value=0.5,
):
    relationships = tuple(
        BodySwayDynamicSeamRelationshipProof(
            relationship.relationship_id,
            tuple(BodySwayDynamicSeamPairProof(pair.pair_id, float(value))
                  for pair in relationship.anchors),
            float(value),
        )
        for relationship in locators.relationships
    )
    return BodySwayDynamicSeamIntervalProof(
        left_tick=left_tick,
        right_tick=right_tick,
        status="continuous_anchor_proximity_certified",
        reason_codes=(),
        relationships=relationships,
        max_squared_distance_upper_px2=float(value),
        threshold_squared_px2=4.0,
        evaluated_box_count=boxes,
        certified_terminal_box_count=(boxes + 1) // 2,
        indeterminate_terminal_box_count=0,
        maximum_depth_reached=depth,
        relationship_count=len(relationships),
        pair_count=sum(len(row.anchors)
                       for row in locators.relationships),
    )


@contextmanager
def patched_pipeline(source, context, locators, *, driver=None):
    """Patch only source admission/orchestration around an exact backend."""

    detached = lambda _value: deepcopy(source)
    with ExitStack() as stack:
        source_admission = stack.enter_context(patch(
            ANALYSIS + "require_body_sway_dynamic_seam_source",
            side_effect=detached,
        ))
        compiler_admission = stack.enter_context(patch(
            COMPILER + "require_body_sway_dynamic_seam_source",
            side_effect=detached,
        ))
        stack.enter_context(patch(
            ANALYSIS + "prepare_body_sway_sampler",
            return_value=FixedSampler(context),
        ))
        stack.enter_context(patch(
            ANALYSIS + "prepare_body_sway_geometry_context",
            return_value=context,
        ))
        stack.enter_context(patch(
            ANALYSIS + "prepare_body_sway_dynamic_seam_locators",
            return_value=locators,
        ))
        driver_mock = None
        if driver is not None:
            driver_mock = stack.enter_context(patch(
                ANALYSIS
                + "prove_body_sway_dynamic_seam_sampled_linear_segment",
                side_effect=driver,
            ))
        yield source_admission, compiler_admission, driver_mock
