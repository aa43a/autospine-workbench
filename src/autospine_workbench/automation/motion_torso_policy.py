"""Explicit optional torso bake; old requests preserve their historical behavior."""
from ..targets.character43.torso_projection_candidate import PROFILE
from ..targets.character43.torso_projection_profile import REFERENCE_PROFILE
from ..targets.character43.motion_depth import OVERLAP_PROFILE
from ..targets.character43.motion_depth_overlap import SPARSE_DEPTH_PROFILE
from .pipeline_run import PipelineRunError


def select(body,depth_profile):
    if 'torso_projection_profile' not in body:return None
    value=body['torso_projection_profile']
    if value not in (PROFILE,REFERENCE_PROFILE):raise PipelineRunError('motion_torso_profile_unsupported')
    if value==REFERENCE_PROFILE:
        from ..targets.character43.oblique_target import validate
        try:validate(body.get('projection'))
        except ValueError as exc:raise PipelineRunError('motion_torso_reference_requires_projection') from exc
    if depth_profile not in (OVERLAP_PROFILE,SPARSE_DEPTH_PROFILE):raise PipelineRunError('motion_torso_requires_overlap_depth')
    return value
