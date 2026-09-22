"""Explicit source-pose candidate strategy; omitted fields preserve legacy jobs."""
from .pipeline_run import PipelineRunError
from .motion_target_pose import PROFILE, HIP_PROFILE
from .motion_post_contact import PROFILE as POST_CONTACT_PROFILE


def select(body):
    if 'pose_profile' not in body:
        return None
    profile=body['pose_profile']
    if profile not in (PROFILE,HIP_PROFILE,POST_CONTACT_PROFILE):
        raise PipelineRunError('motion_pose_profile_unsupported')
    if any(body.get(k) is not None for k in ('clip','projection','projection_selection','torso_projection_profile')):
        raise PipelineRunError('motion_pose_requires_full_original_view')
    if profile == POST_CONTACT_PROFILE and (body.get('contact_correction') is False or
            body.get('inferred_contact_profile', 'external-phase-contact-auto-v1') != 'external-phase-contact-auto-v1'):
        raise PipelineRunError('motion_post_contact_requires_phase_contact')
    return profile


def prepare(bundle,request):
    profile=select(request)
    if profile is None:return None
    from .motion_target_pose import prepare as build
    result = build(bundle,hip_center=profile in (HIP_PROFILE,POST_CONTACT_PROFILE))
    if profile == POST_CONTACT_PROFILE:
        from ..targets.character43.source_foot_orientation import extract
        result.update(post_contact_profile=POST_CONTACT_PROFILE, foot_observations=extract(bundle))
    return result
