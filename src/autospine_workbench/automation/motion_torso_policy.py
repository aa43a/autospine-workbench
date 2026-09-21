"""Explicit optional torso bake; old requests preserve their historical behavior."""
from ..targets.character43.torso_projection_candidate import PROFILE
from ..targets.character43.motion_depth import OVERLAP_PROFILE
from .pipeline_run import PipelineRunError


def select(body,depth_profile):
    if 'torso_projection_profile' not in body:return None
    value=body['torso_projection_profile']
    if value!=PROFILE:raise PipelineRunError('motion_torso_profile_unsupported')
    if depth_profile!=OVERLAP_PROFILE:raise PipelineRunError('motion_torso_requires_overlap_depth')
    return value
