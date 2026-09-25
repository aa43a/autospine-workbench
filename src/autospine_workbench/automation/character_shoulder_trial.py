"""Retire implicit shoulder pinning while preserving historical recipes."""

from .character_build_options import valid_regions
from .pipeline_run import PipelineRunError


def validate(regions):
    if regions is not None and not valid_regions(regions):
        raise PipelineRunError('shoulder_region_selection_invalid')


def apply_selected(manager, request, result, *, progress=lambda stage: None,
                   cancel_requested=lambda: False):
    regions = request.get('shoulder_regions')
    validate(regions)
    if regions is None:
        return result
    if cancel_requested():
        raise PipelineRunError('character_build_canceled')
    # A selected shoulder does not establish a sewn seam. Historical recipes
    # remain readable, but cannot reactivate pin/adaptive/temporal constraints.
    return dict(result, shoulder_trial=dict(
        region_ids=list(regions), source_artifact_sha256=result['artifact_sha256'],
        status='not_applied', reason_code='shoulder_boundary_constraint_retired',
        contact_policy='sliding_overlap_no_boundary_pin', included_in_candidate=False,
        attempts=[], authority='none', selected=False, visual_contact_status='not_evaluated'))
