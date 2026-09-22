"""Measure final bone axes against observed source projections, without adoption."""
import math

from .affine_pose import matrices
from .motionir_candidate import ROLES
from .oblique_motion import project


def audit(document, name, vectors, times, *, yaw=0):
    if (len(times) < 2 or any(not math.isfinite(t) or t < 0 for t in times)
            or any(b <= a for a, b in zip(times, times[1:]))):
        raise ValueError('direction_audit_times_invalid')
    if not math.isfinite(yaw) or not -90 <= yaw <= 90:
        raise ValueError('direction_audit_yaw_invalid')
    selected = {r: v for r, v in vectors.items()
                if r.startswith(('humanoid.arm.', 'humanoid.leg.')) and r in ROLES}
    if not selected:
        raise ValueError('direction_audit_limbs_missing')
    for values in selected.values():
        if len(values) != len(times) or any(len(v) != 3 or not all(math.isfinite(x) for x in v) for v in values):
            raise ValueError('direction_audit_vectors_invalid')
    poses = [matrices(document, name, t) for t in times]
    records = []
    for role, values in selected.items():
        bone = ROLES[role]
        frames = []
        for i, (time, vector) in enumerate(zip(times, values)):
            x, y, z = project(vector, yaw)
            length = math.hypot(x, y, z)
            visibility = math.hypot(x, y) / length if length else 0
            m = poses[i][bone]
            observable = visibility >= .2 and math.hypot(m[0], m[2]) > 1e-12
            source = math.degrees(math.atan2(-y, x)) if math.hypot(x, y) > 1e-12 else None
            target = math.degrees(math.atan2(m[2], m[0])) if math.hypot(m[0], m[2]) > 1e-12 else None
            error = abs((target-source+180) % 360-180) if observable else None
            frames.append(dict(time=time, visibility=visibility, source_angle=source,
                               target_angle=target, reliable=observable, error_deg=error))
        reliable = [f for f in frames if f['reliable']]
        steps = []
        for a, b in zip(frames, frames[1:]):
            if not a['reliable'] or not b['reliable']:
                continue
            source_step = (b['source_angle']-a['source_angle']+180) % 360-180
            target_step = (b['target_angle']-a['target_angle']+180) % 360-180
            steps.append(dict(time=b['time'], source_step_deg=source_step,
                              target_step_deg=target_step,
                              excess_step_deg=abs(target_step-source_step)))
        records.append(dict(role=role, bone=bone, samples=len(frames),
            reliable_samples=len(reliable), unreliable_times=[f['time'] for f in frames if not f['reliable']],
            worst_direction=max(reliable, key=lambda f:f['error_deg']) if reliable else None,
            worst_step=max(steps, key=lambda f:f['excess_step_deg']) if steps else None))
    return dict(profile='final-source-direction-audit-v1', authority='none', records=records,
        scope='sampled_world_bone_axes_not_mesh_or_depth_or_visual_acceptance',
        limitations=['source_sample_grid_not_continuous_time',
                     'unreliable_projection_excluded_not_passed',
                     'shortest_angle_steps_do_not_measure_full_turns'])
