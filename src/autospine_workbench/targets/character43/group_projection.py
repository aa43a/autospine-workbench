"""Read-only fixed limb-plane comparison; never changes source or draw depth."""
import math

from ...resolved_project import canonical_sha256
from .oblique_motion import project
from .projection_diagnostics import summarize

PROFILE = 'fixed-limb-plane-comparison-v1-experiment'


def compare(vectors, times):
    groups = {}
    for limb in ('arm', 'leg'):
        for side in ('left', 'right'):
            roles = [f'humanoid.{limb}.{part}.{side}' for part in ('upper', 'lower')]
            if any(role not in vectors for role in roles):
                raise ValueError('group_projection_required_limb_missing')
            groups[f'{limb}.{side}'] = roles
    for role in sum(groups.values(), []):
        values = vectors[role]
        if len(values) != len(times) or any(len(v) != 3 or
                not all(math.isfinite(x) for x in v) or math.dist(v, (0, 0, 0)) <= 1e-10
                for v in values):
            raise ValueError('group_projection_source_vector_invalid')
    records = []
    for group, roles in groups.items():
        alternatives = []
        for yaw in (0, -90, 90):
            series = {role: [math.hypot(*project(v, yaw)[:2])/math.dist(v, (0, 0, 0))
                            for v in vectors[role]] for role in roles}
            diagnostic = summarize(series, times)
            angle_records = []
            for role in roles:
                angles, previous, jumps = [], None, []
                for i, v in enumerate(vectors[role]):
                    x, y, _ = project(v, yaw)
                    if series[role][i] < .2:
                        angles.append(None)
                        previous = None  # Do not unwrap across unobservable intervals.
                        continue
                    angle = math.degrees(math.atan2(y, x))
                    if previous is not None:
                        delta = (angle-previous+180) % 360-180
                        if abs(delta) >= 90:
                            jumps.append(dict(frame=i, time=times[i], delta_degrees=delta))
                        angle = previous+delta
                    angles.append(angle)
                    previous = angle
                angle_records.append(dict(role=role, angles=angles, large_sample_steps=jumps))
            alternatives.append(dict(yaw_degrees=yaw, diagnostic=diagnostic, angles=angle_records,
                minimum_visibility=min(min(v) for v in series.values()),
                collapsed_samples=sum(v < .2 for values in series.values() for v in values)))
        # Rank diagnostics only. Opposite side views tie in visibility but not direction;
        # a score cannot decide which bend/handedness is visually appropriate.
        best = min((a['collapsed_samples'], -a['minimum_visibility']) for a in alternatives)
        records.append(dict(group=group, alternatives=alternatives,
            best_visibility_yaws=[a['yaw_degrees'] for a in alternatives
                if (a['collapsed_samples'], -a['minimum_visibility']) == best]))
    return dict(profile=PROFILE, authority='none', selected=False,
        input_sha256=canonical_sha256(dict(vectors=vectors, times=times)), times=times,
        records=records, scope='source_direction_diagnostics_not_target_pose_or_acceptance',
        limitations=['side_sign_requires_bend_and_handedness_evidence',
                    'shared_attachment_anchors_not_yet_solved',
                    'original_3d_depth_must_not_be_replaced_by_mixed_plane_depth'])
