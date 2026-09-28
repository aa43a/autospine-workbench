"""Explicit source-pose candidate strategy; omitted fields preserve legacy jobs."""
from .pipeline_run import PipelineRunError
from .motion_target_pose import PROFILE, HIP_PROFILE
from .motion_post_contact import PROFILE as POST_CONTACT_PROFILE
from .motion_post_contact import TIMELINE_PROFILE
from .motion_view_pose import PROFILE as VIEW_PROFILE
from .motion_camera_policy import PROFILE as CAMERA_PROFILE

POST_PROFILES = (POST_CONTACT_PROFILE,TIMELINE_PROFILE)


def select(body):
    if 'pose_profile' not in body:
        return None
    profile=body['pose_profile']
    if profile==CAMERA_PROFILE:
        from .motion_camera_policy import select as select_camera
        return select_camera(body)
    if profile not in (PROFILE,HIP_PROFILE,VIEW_PROFILE,*POST_PROFILES):
        raise PipelineRunError('motion_pose_profile_unsupported')
    if profile == VIEW_PROFILE:
        from ..targets.character43.oblique_target import validate
        if body.get('clip') is not None:
            raise PipelineRunError('motion_view_pose_requires_full_clip')
        try: validate(body.get('projection'))
        except ValueError as exc: raise PipelineRunError('motion_view_pose_requires_explicit_projection') from exc
        return profile
    if any(body.get(k) is not None for k in ('clip','projection','projection_selection','torso_projection_profile')):
        raise PipelineRunError('motion_pose_requires_full_original_view')
    if profile in POST_PROFILES and (body.get('contact_correction') is False or
            body.get('inferred_contact_profile', 'external-phase-contact-auto-v1') != 'external-phase-contact-auto-v1'):
        raise PipelineRunError('motion_post_contact_requires_phase_contact')
    return profile


def prepare(bundle,request):
    profile=select(request)
    if profile is None:return None
    if profile in (VIEW_PROFILE,CAMERA_PROFILE):
        return prepare_inputs(bundle, request)[2]
    from .motion_target_pose import prepare as build
    result = build(bundle,hip_center=profile in (HIP_PROFILE,*POST_PROFILES))
    if profile in POST_PROFILES:
        from ..targets.character43.source_foot_orientation import extract
        result.update(post_contact_profile=profile, foot_observations=extract(bundle))
    return result


def prepare_inputs(bundle, request):
    """Compile one shared camera snapshot for motion and fitted pose evidence."""
    profile = select(request)
    if profile == CAMERA_PROFILE:
        from .motion_camera_policy import select as select_camera
        from .motion_camera_pose import prepare as shared_camera
        select_camera(request,bundle.motion['duration_ticks']/bundle.motion['ticks_per_second'])
        motion,view,pose=shared_camera(bundle,request['projection']['keys'])
    elif profile == VIEW_PROFILE:
        from .motion_view_pose import prepare as shared_view
        motion, view, pose = shared_view(bundle, request['projection']['yaw_degrees'])
    else:
        pose = prepare(bundle, request)
        motion, view = bundle.motion, None
        if request.get('projection') is not None:
            from ..targets.character43.oblique_target import prepare as oblique
            motion, view = oblique(bundle, request['projection'])
    if view is not None and request.get('projection_selection') is not None:
        view['selection'] = request['projection_selection']
        if profile == VIEW_PROFILE:
            from ..resolved_project import canonical_sha256
            pose['view_sha256'] = canonical_sha256(view)
    return motion, view, pose
