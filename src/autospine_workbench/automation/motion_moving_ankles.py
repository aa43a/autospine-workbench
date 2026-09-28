"""Explicit moving-source ankle stage; retains failed inputs and source identity."""
import math
from ..resolved_project import canonical_sha256
from ..motion_validation import motion_ir_sha256
from ..targets.character43.affine_pose import matrices
from ..targets.character43.source_ankle_targets import targets
from ..targets.character43.moving_ankle_candidate import build
from ..targets.spine43.continuous_pose import interpolate


def apply(document, name, motion, observation, times, reference, *, bundle_sha256, oblique=None, clip_bounds=None):
    expected_motion = oblique['parent_motion_sha256'] if oblique else motion_ir_sha256(motion)
    from ..targets.character43.camera_track import PROFILE as CAMERA_PROFILE
    from ..targets.character43.camera_ankle_targets import PROFILE as CAMERA_ANKLES
    camera=oblique is not None and oblique.get('profile')==CAMERA_PROFILE
    yaw = oblique.get('yaw_degrees',0) if oblique else 0
    view_matches=(observation.get('keys')==oblique.get('keys') and observation.get('sampling_profile')==oblique.get('sampling_profile') and
                  canonical_sha256({k:v for k,v in observation.items() if k!='observation_sha256'})==observation.get('observation_sha256')) if camera else observation.get('yaw_degrees')==yaw
    if (clip_bounds is not None or observation.get('source_bundle_sha256') != bundle_sha256
            or observation.get('motion_sha256') != expected_motion
            or not view_matches
            or observation.get('profile') != (CAMERA_ANKLES if camera else 'source-ankle-displacement-v1')
            or not observation.get('times')
            or observation['times'][-1] != motion['duration_ticks']/motion['ticks_per_second']):
        raise ValueError('moving_ankle_source_identity_or_time_mismatch')
    initial = matrices(document, name, 0)
    trajectory = targets(observation, [initial['foot_'+s][4:6] for s in ('l', 'r')], reference)
    candidate, report = build(document, name, trajectory, times, reference)
    report.update(input_skeleton_sha256=canonical_sha256(document),
                  source_observation=observation, trajectory=trajectory)
    report['applied'] = candidate is not None
    return document if candidate is None else candidate, report


def check(document, name, report, times, reference):
    """Measure actual final FK, including inserted interpolation samples."""
    trajectory = report['trajectory']
    if (not 2 <= len(times) <= 4097 or times[0] != 0
            or not math.isclose(times[-1], trajectory[-1]['time'], rel_tol=0, abs_tol=1e-6)
            or any(not math.isfinite(t) for t in times)
            or any(b <= a for a, b in zip(times, times[1:]))
            or not math.isfinite(reference) or reference <= 0):
        raise ValueError('moving_ankle_final_times_invalid')
    feet = [[dict(time=r['time'], vertices=r['targets'][s]) for r in trajectory] for s in (0, 1)]
    worst = dict(error_px=0, time=0, side='l')
    for t in times:
        pose = matrices(document, name, t)
        for i, side in enumerate(('l', 'r')):
            error = math.dist(pose['foot_'+side][4:6], interpolate(feet[i], t, 'vertices'))
            if error > worst['error_px']:
                worst = dict(error_px=error, time=t, side=side)
    return dict(passed=worst['error_px'] <= reference*.01, worst=worst, samples=len(times),
                limit_px=reference*.01, skeleton_sha256=canonical_sha256(document),
                scope='moving_ankle_tracking_not_stationary_contact_or_visual_acceptance')
