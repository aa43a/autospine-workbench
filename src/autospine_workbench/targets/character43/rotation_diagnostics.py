"""Sampled direction diagnostics, without rewriting winding or inventing twist."""
import math

PROFILE = 'source-direction-continuity-v1'


def summarize(series, times, minimum_visibility=.2):
    if (len(times) < 2 or any(not math.isfinite(t) for t in times)
            or any(b <= a for a, b in zip(times, times[1:]))):
        raise ValueError('rotation_times_invalid')
    if not 0 < minimum_visibility < 1:
        raise ValueError('rotation_visibility_limit_invalid')
    records = []
    for role, samples in sorted(series.items()):
        if len(samples) != len(times): raise ValueError('rotation_sample_count_invalid')
        angles, visibility, events, runs = [], [], [], []
        previous = None
        run = None
        for i, (dx, dy, length) in enumerate(samples):
            if (not all(math.isfinite(v) for v in (dx, dy, length)) or length < 0
                    or math.hypot(dx, dy) > length + 1e-7):
                raise ValueError('rotation_vector_invalid')
            ratio = math.hypot(dx, dy)/length if length > 1e-12 else 0.
            visibility.append(ratio)
            raw = math.degrees(math.atan2(dy, dx))
            if ratio < minimum_visibility:
                angles.append(None)
                events.append(dict(frame=i, time=times[i], reason='projection_direction_unreliable'))
                previous = None; run = None
                continue
            if previous is None:
                value = raw
                run = dict(start_frame=i, end_frame=i, start_angle=value, end_angle=value)
                runs.append(run)
            else:
                prior_raw, prior_value = previous
                delta = (raw-prior_raw+180) % 360-180
                if abs(abs(delta)-180) < 1e-7:
                    # Endpoints cannot determine the sign or number of half turns.
                    events.append(dict(frame=i, time=times[i], reason='half_turn_direction_ambiguous'))
                    angles.append(None); previous = None; run = None
                    continue
                value = prior_value+delta
                if abs(raw-prior_raw) > 180:
                    events.append(dict(frame=i, time=times[i], reason='angle_branch_crossing',
                                       raw_delta=raw-prior_raw, continuous_delta=delta))
                run.update(end_frame=i, end_angle=value)
            angles.append(value); previous = (raw, value)
        for run in runs:
            run['net_turns'] = (run['end_angle']-run['start_angle'])/360
        records.append(dict(role=role, visibility=visibility, continuous_angles=angles,
                            runs=runs, events=events))
    if not records: raise ValueError('rotation_limbs_missing')
    return dict(profile=PROFILE, authority='none', times=times, records=records,
                minimum_visibility=minimum_visibility,
                scope='sampled_projected_direction_not_source_axial_twist_or_target_local_rotation',
                limitations=['unobserved_between_frame_turns_cannot_be_recovered',
                             'continuity_is_reset_across_projection_degeneracy',
                             'branch_crossing_alone_is_not_a_visual_error',
                             'no_animation_modified'])


def bvh_vectors(bvh, mapping):
    from ...bvh_fk import project_bvh_frames
    projected = project_bvh_frames(bvh, mapping)
    frames = [dict(f.joints) for f in projected.frames]
    series = {}
    for row in mapping['bones']:
        if not row['role'].startswith(('humanoid.arm.', 'humanoid.leg.')): continue
        if row['aim']['kind'] != 'joint': raise ValueError('rotation_joint_aim_required')
        values = []
        for frame in frames:
            a, b = frame[row['joint_name']], frame[row['aim']['joint_name']]
            values.append((b.screen_xy[0]-a.screen_xy[0], b.screen_xy[1]-a.screen_xy[1],
                           math.dist(a.world_xyz, b.world_xyz)))
        series[row['role']] = values
    return series, [f.tick/1_000_000 for f in projected.frames]


def kimodo_vectors(raw, source, mapping):
    from ...kimodo_npz_reader import decode_kimodo_npz
    from ...kimodo_npz_consistency import validate_kimodo_consistency
    from ...kimodo_npz_map_validation import require_kimodo_npz_map
    from ...kimodo_npz_projection import kimodo_frame_ticks
    from ...kimodo_soma77 import SOMA77_INDEX_BY_NAME
    require_kimodo_npz_map(mapping, source=source)
    positions = validate_kimodo_consistency(decode_kimodo_npz(raw, source), source).positions
    axes = [('XYZ'.index(mapping['basis'][key][1]), -1 if mapping['basis'][key][0]=='-' else 1)
            for key in ('screen_x', 'screen_y')]
    series = {}
    for row in mapping['bones']:
        if not row['role'].startswith(('humanoid.arm.', 'humanoid.leg.')): continue
        a, b = (SOMA77_INDEX_BY_NAME[row[k]] for k in ('joint_name', 'aim_joint_name'))
        series[row['role']] = [tuple(sign*(frame[b][axis]-frame[a][axis]) for axis, sign in axes)
                               +(math.dist(frame[a], frame[b]),) for frame in positions]
    return series, [t/1_000_000 for t in kimodo_frame_ticks(source)]
