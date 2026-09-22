"""Explicit source-pose candidate strategy; omitted fields preserve legacy jobs."""
from .pipeline_run import PipelineRunError
from .motion_target_pose import PROFILE, HIP_PROFILE


def select(body):
    if 'pose_profile' not in body:
        return None
    profile=body['pose_profile']
    if profile not in (PROFILE,HIP_PROFILE):
        raise PipelineRunError('motion_pose_profile_unsupported')
    if any(body.get(k) is not None for k in ('clip','projection','projection_selection','torso_projection_profile')):
        raise PipelineRunError('motion_pose_requires_full_original_view')
    return profile


def prepare(bundle,request):
    profile=select(request)
    if profile is None:return None
    from .motion_target_pose import prepare as build
    return build(bundle,hip_center=profile==HIP_PROFILE)
