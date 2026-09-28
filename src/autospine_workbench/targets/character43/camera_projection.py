"""One camera snapshot for source directions, root displacement and hip centers.

Inputs are in the verified MotionIR map basis (screen X, screen Y, depth).
This module does not infer missing character surfaces or repair singular poses.
"""
import math
from ...resolved_project import canonical_sha256
from .camera_track import PROFILE, validate, at_times, sample
from .oblique_motion import project


def prepare(vectors, roots, centers, times, reference, keys, duration):
    keys = validate(keys, duration)
    yaws = at_times(keys, times, duration)
    if (type(reference) not in (int, float) or not math.isfinite(reference) or reference <= 0
            or not isinstance(vectors, dict) or not vectors):
        raise ValueError('camera_spatial_input_invalid')
    for samples in [roots, centers, *vectors.values()]:
        if (not isinstance(samples, (list, tuple)) or len(samples) != len(times)
                or any(not isinstance(p, (list, tuple)) or len(p) != 3
                       or any(type(v) not in (int, float) or not math.isfinite(v) for v in p)
                       for p in samples)):
            raise ValueError('camera_spatial_samples_invalid')
    if any(not isinstance(role, str) or not role for role in vectors):
        raise ValueError('camera_role_invalid')
    # Orbit the source's initial root, not the world origin. A source translated
    # in the 3D scene must produce identical projected motion and camera depth.
    pivot = roots[0]
    positions = lambda values: [project(tuple(v-p for v, p in zip(point, pivot)), yaw)
                                for point, yaw in zip(values, yaws)]
    projected = {role: [project(point, yaw) for point, yaw in zip(values, yaws)]
                 for role, values in vectors.items()}
    issues = []
    visibility = {}
    for role, values in projected.items():
        ratios = []
        for index, point in enumerate(values):
            length = math.sqrt(sum(v*v for v in point))
            if length <= reference*1e-12:
                raise ValueError('camera_source_segment_zero:'+role)
            ratio = math.hypot(*point[:2])/length
            ratios.append(ratio)
            if ratio < .2:
                issues.append(dict(role=role, frame=index, time=times[index], yaw=yaws[index],
                    visibility=ratio, reason='camera_direction_unobservable' if ratio <= 1e-6
                    else 'camera_direction_unreliable'))
        visibility[role] = ratios
    surfaces = []
    for index, yaw in enumerate(yaws):
        angle = (yaw+180) % 360-180
        if abs(angle) > 60:
            surfaces.append(dict(frame=index, time=times[index], yaw=yaw,
                reason='rear_surface_not_provided' if abs(angle) > 90 else 'side_surface_not_verified'))
    temporal = []
    for first,last in zip(times,times[1:]):
        # Include interior key turns: matching interval endpoints do not prove
        # that the camera stayed still between two sparse source samples.
        knots=[first]+[k['time'] for k in keys if first<k['time']<last]+[last]
        angles=[sample(keys,t) for t in knots]
        travel=sum(abs(b-a) for a,b in zip(angles,angles[1:]))
        if travel>15:
            temporal.append(dict(start=first,end=last,angular_travel=travel,
                                 reason='camera_sampling_insufficient'))
    if times[-1]!=duration:
        temporal.append(dict(start=times[-1],end=duration,reason='camera_end_not_sampled'))
    inputs = dict(vectors=vectors, roots=roots, hip_centers=centers, times=times,
                  reference=reference, keys=keys, duration=duration)
    result = dict(profile=PROFILE, keys=keys, times=list(times), yaw_degrees=yaws,
        vectors=projected, roots=positions(roots), hip_centers=positions(centers),
        reference=reference, visibility=visibility, issues=issues, surface_issues=surfaces,
        temporal_issues=temporal,maximum_sample_angular_travel=15,
        pivot_policy='initial_source_root', input_sha256=canonical_sha256(inputs),
        authority='none', scope='source_camera_projection_not_character_surface')
    result['projection_sha256'] = canonical_sha256(result)
    return result
