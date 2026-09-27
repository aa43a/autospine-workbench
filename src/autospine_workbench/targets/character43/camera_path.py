"""Experimental shared-camera paths; no per-limb view substitution or adoption."""
import math

from ...resolved_project import canonical_sha256
from .oblique_motion import project
from .torso_projection_source import reference_shapes

PROFILE = 'bounded-shared-camera-source-path-v1-experiment'


def plan(vectors, torso_frames, times, *, maximum_speed=60, step=1):
    if (type(step) is not int or step < 1 or 90 % step
            or type(maximum_speed) not in (int, float)
            or not math.isfinite(maximum_speed) or not 0 < maximum_speed <= 90):
        raise ValueError('camera_path_options_invalid')
    if (len(times) < 2 or len(torso_frames) != len(times)
            or any(not math.isfinite(t) or t < 0 for t in times)
            or any(b <= a for a, b in zip(times, times[1:]))):
        raise ValueError('camera_path_times_invalid')
    limbs = {r: values for r, values in vectors.items()
             if r.startswith(('humanoid.arm.', 'humanoid.leg.'))}
    if not limbs:
        raise ValueError('camera_path_limbs_missing')
    for values in limbs.values():
        if (len(values) != len(times) or any(len(p) != 3
                or any(not math.isfinite(v) for v in p) or math.hypot(*p) <= 1e-10
                for p in values)):
            raise ValueError('camera_path_vectors_invalid')
    baseline = {r: math.hypot(*v[0][:2])/math.hypot(*v[0]) for r, v in limbs.items()}
    if any(v < .2 for v in baseline.values()):
        raise ValueError('camera_path_initial_limb_projection_unreliable')
    angles = range(-90, 91, step)
    states = {}
    for yaw in angles:
        torso = reference_shapes([[project(p, yaw) for p in f] for f in torso_frames],
                                 times, torso_frames[0])['records']
        rows = []
        for i, time in enumerate(times):
            visible = {r: math.hypot(*project(v[i], yaw)[:2])/math.hypot(*v[i])
                       for r, v in limbs.items()}
            failed = [r for r, v in visible.items()
                      if v < .2 or not .5 <= v/baseline[r] <= 1.5]
            rows.append(dict(time=time, yaw_degrees=yaw, visibility=visible,
                             torso=torso[i], failed_roles=failed,
                             passed=not failed and not torso[i]['reasons']))
        states[yaw] = rows
    report = dict(profile=PROFILE, authority='none', selected=False,
        input_sha256=canonical_sha256(dict(vectors=vectors, torso_frames=torso_frames, times=times)),
        limits=dict(maximum_speed_deg_per_second=maximum_speed, angular_grid_step=step,
                    minimum_limb_visibility=.2, relative_limb_length=[.5, 1.5]),
        reference='initial_zero_yaw_source_matches_front_artwork',
        scope='shared_camera_source_samples_not_target_geometry_or_runtime_acceptance')
    costs = {0: 0.} if states[0][0]['passed'] else {}
    if not costs:
        return dict(report,status='no_continuous_qualified_path',records=[],
                    failure=dict(frame=0,time=times[0],reason='initial_zero_yaw_unqualified'))
    history = []
    for i in range(1, len(times)):
        dt = times[i]-times[i-1]
        current, parents = {}, {}
        for yaw in angles:
            if not states[yaw][i]['passed']:
                continue
            options = [(cost + dt*(yaw*yaw + .1*((yaw-old)/dt)**2), old)
                       for old, cost in costs.items()
                       if abs(yaw-old) <= maximum_speed*dt + 1e-9]
            if options:
                current[yaw], parents[yaw] = min(options)
        history.append(parents)
        if not current:
            qualified=[y for y in angles if states[y][i]['passed']]
            turn=min((abs(y-old) for y in qualified for old in costs),default=None)
            return dict(report, status='no_continuous_qualified_path', records=[],
                failure=dict(frame=i, time=times[i], reachable_previous_angles=sorted(costs),
                             qualified_angles=qualified,minimum_required_turn_degrees=turn,
                             minimum_required_speed_deg_per_second=None if turn is None else turn/dt))
        costs = current
    yaw = min(costs, key=lambda y: (costs[y], abs(y), y))
    path = [yaw]
    for parents in reversed(history):
        yaw = parents[yaw]
        path.append(yaw)
    path.reverse()
    speeds = [(b-a)/(times[i+1]-times[i]) for i, (a, b) in enumerate(zip(path, path[1:]))]
    return dict(report, status='sampled_path_found', records=[states[y][i] for i, y in enumerate(path)],
        maximum_speed_deg_per_second=max(map(abs, speeds)),
        yaw_range=[min(path), max(path)],
        limitations=['camera_motion_changes_screen_trajectories',
                     'interpolation_between_source_samples_not_verified',
                     'angular_acceleration_not_constrained',
                     'requires_new_target_contact_depth_geometry_and_runtime_checks'])
