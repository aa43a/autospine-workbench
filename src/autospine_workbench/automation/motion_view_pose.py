"""One explicit camera basis for source motion, limb fitting and hip translation."""
from ..motion_validation import motion_ir_sha256
from ..resolved_project import canonical_sha256
from ..targets.character43.oblique_motion import compile_candidate, project
from ..targets.character43.oblique_source import extract
from ..targets.character43.source_hip_centers import extract as hip_centers

PROFILE = 'constant-view-absolute-pose-hip-center-v1-experiment'


def prepare(bundle, yaw, *, post_contact=False):
    if type(post_contact) is not bool:raise ValueError('view_pose_post_contact_invalid')
    vectors, roots, reference = extract(bundle)
    motion, view = compile_candidate(bundle.motion, vectors, roots, reference, yaw,
                                    precision=5 if bundle.source_kind=='kimodo_npz' else 12)
    centers, hip_reference = hip_centers(bundle)
    if hip_reference != reference or len(centers) != len(roots):
        raise ValueError('view_pose_source_frame_mismatch')
    tracks = [t for t in motion['tracks'] if t['property']=='rotation']
    ticks = [k['tick'] for k in tracks[0]['keys']]
    pose = dict(profile=PROFILE, motion_sha256=motion_ir_sha256(motion),
                view_sha256=canonical_sha256(view),
                vectors={role:[project(v,yaw) for v in values] for role,values in vectors.items()},
                hip_centers=[project(c,yaw) for c in centers],source_reference=reference,
                times=[t/motion['ticks_per_second'] for t in ticks],
                source_motion_sha256=motion_ir_sha256(bundle.motion),yaw_degrees=yaw,
                scope='shared_source_camera_not_reconstructed_character_surface')
    if post_contact:
        from .motion_post_contact import PROFILE as POST_PROFILE
        from ..targets.character43.source_foot_orientation import extract as feet
        pose.update(post_contact_profile=POST_PROFILE,foot_observations=feet(bundle,yaw=yaw))
    return motion, view, pose


def validate(pose, motion, view, time_range):
    if (time_range is not None or view is None or pose.get('profile') != PROFILE
            or pose.get('motion_sha256') != motion_ir_sha256(motion)
            or pose.get('view_sha256') != canonical_sha256(view)
            or pose.get('yaw_degrees') != view.get('yaw_degrees')
            or pose.get('source_motion_sha256') != view.get('parent_motion_sha256')):
        raise ValueError('view_pose_identity_or_camera_mismatch')
    if pose.get('post_contact_profile'):
        feet=pose.get('foot_observations',{})
        if feet.get('yaw_degrees',0) != pose['yaw_degrees']:
            raise ValueError('view_pose_foot_camera_mismatch')
