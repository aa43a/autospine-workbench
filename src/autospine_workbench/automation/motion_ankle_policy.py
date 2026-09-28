"""Versioned moving-ankle request; never silently combines stationary locks."""
from .pipeline_run import PipelineRunError

PROFILE = 'moving-source-ankle-timeline-v1'


def select(body):
    if 'moving_ankle_profile' not in body:
        return None
    from .motion_camera_policy import ANKLE_PROFILE,select as select_camera
    if body['moving_ankle_profile']==ANKLE_PROFILE:
        select_camera(body)
        return ANKLE_PROFILE
    if body['moving_ankle_profile'] != PROFILE:
        raise PipelineRunError('motion_moving_ankle_profile_unsupported')
    if body.get('contact_correction', True) is not False:
        raise PipelineRunError('motion_moving_ankle_requires_contact_measurement_only')
    if body.get('clip') is not None:
        raise PipelineRunError('motion_moving_ankle_requires_full_clip')
    if body.get('pose_profile') in ('source-pose-post-contact-margin-v1', 'source-pose-post-contact-timeline-v2'):
        raise PipelineRunError('motion_moving_ankle_conflicts_with_post_contact')
    return PROFILE


def prepare(bundle, request):
    if select(request) is None:
        return None
    from .motion_camera_policy import ANKLE_PROFILE
    if request['moving_ankle_profile']==ANKLE_PROFILE:
        from ..targets.character43.camera_ankle_targets import extract
        return extract(bundle,request['projection']['keys'])
    from ..targets.character43.source_ankle_targets import extract
    return extract(bundle, (request.get('projection') or {}).get('yaw_degrees', 0))
