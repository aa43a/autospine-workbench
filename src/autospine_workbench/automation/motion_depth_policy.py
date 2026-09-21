"""Explicit depth strategy selection, independent of historical task defaults."""
from ..targets.character43.motion_depth import PROFILE as LEGACY, OVERLAP_PROFILE
from ..targets.character43.regional_depth_profile import PROFILE as REGIONAL
from .pipeline_run import PipelineRunError


def select(body, source):
    value = body.get('depth_review_profile', OVERLAP_PROFILE)
    if value not in (LEGACY, OVERLAP_PROFILE, REGIONAL):
        raise PipelineRunError('motion_depth_profile_unsupported')
    if value == REGIONAL and source.get('format') not in ('bvh', 'fbx'):
        raise PipelineRunError('regional_depth_bvh_required')
    return value
