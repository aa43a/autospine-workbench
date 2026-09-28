"""Moving foot observations during camera orbit, distinct from screen foot lock."""
from ...resolved_project import canonical_sha256
from .camera_track import at_times, validate
from .oblique_motion import project
from .oblique_source import extract as source_vectors
from .source_ankle_targets import extract as source_ankles

PROFILE = 'continuous-camera-ankle-displacement-v1'


def extract(bundle, keys):
    source = source_ankles(bundle)
    _, roots, reference = source_vectors(bundle)
    times = source['times']; duration = bundle.motion['duration_ticks']/bundle.motion['ticks_per_second']
    keys = validate(keys, duration)
    yaws = at_times(keys, times, duration)
    if (times[-1] != duration or len(roots) != len(times)
            or reference != source['source_reference_length']):
        raise ValueError('camera_ankle_source_mismatch')
    pivot = roots[0]
    relative = [[tuple(v-p for v,p in zip(point,pivot)) for point in frame] for frame in source['points']]
    # Orbit around exactly the pose solver's initial source root. Subtracting
    # each foot's own initial position before rotating would hide stance width.
    points = [[project(point,yaw) for point in frame] for frame,yaw in zip(relative,yaws)]
    frozen = [[project(point,yaws[0]) for point in frame] for frame in relative]
    camera_displacement = [[[v-f for v,f in zip(p,q)] for p,q in zip(frame,base)]
                           for frame,base in zip(points,frozen)]
    result = dict(profile=PROFILE, source_bundle_sha256=bundle.bundle_sha256,
        motion_sha256=bundle.clip_sha256, keys=keys, track_sha256=canonical_sha256(keys),
        times=times, yaw_degrees=yaws, source_reference_length=reference, points=points,
        frozen_camera_points=frozen, camera_displacement=camera_displacement,
        pivot_policy='initial_source_root', authority='none',
        scope='projected_ankle_tracking_not_stationary_screen_contact',
        limitations=['does_not_prove_floor_or_sole_contact'])
    result['observation_sha256'] = canonical_sha256(result)
    return result
