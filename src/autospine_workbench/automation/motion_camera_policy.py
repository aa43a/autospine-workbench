"""Explicit full-clip camera request; no implicit stationary-foot fallback."""
from ..targets.character43.camera_track import PROFILE, validate
from ..targets.character43.camera_ankle_targets import PROFILE as ANKLE_PROFILE
from .pipeline_run import PipelineRunError


def select(body, duration=None):
    projection=body.get('projection')
    if not isinstance(projection,dict) or projection.get('profile')!=PROFILE:
        raise PipelineRunError('motion_camera_projection_required')
    if set(projection)-{'profile','keys','sampling_profile'} or not {'profile','keys'}<=set(projection):
        raise PipelineRunError('motion_camera_projection_invalid')
    if 'sampling_profile' in projection:
        from ..targets.character43.camera_sampling import PROFILE as SAMPLING
        if projection['sampling_profile']!=SAMPLING:raise PipelineRunError('camera_sampling_profile_unsupported')
    if (body.get('pose_profile')!=PROFILE or body.get('moving_ankle_profile')!=ANKLE_PROFILE
            or body.get('contact_correction',True) is not False):
        raise PipelineRunError('motion_camera_profiles_must_match')
    if any(body.get(k) is not None for k in ('clip','projection_selection','torso_projection_profile')):
        raise PipelineRunError('motion_camera_requires_full_unwarped_clip')
    if body.get('depth_review_profile')=='external-regional-depth-order-v1':
        raise PipelineRunError('motion_camera_regional_depth_not_supported')
    keys=projection['keys']
    # Syntax is checked first; submission/preparation supply exact MotionIR duration.
    if duration is None:
        duration=max([1]+[k.get('time',0) for k in keys if isinstance(k,dict) and type(k.get('time')) in (int,float)]) if isinstance(keys,list) else 1
    try:validate(keys,duration)
    except ValueError as exc:raise PipelineRunError(str(exc)) from exc
    return PROFILE
