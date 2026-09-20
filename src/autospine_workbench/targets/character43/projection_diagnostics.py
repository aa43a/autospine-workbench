"""Locate limb foreshortening in verified source motion without changing it."""
import math


def summarize(series, times):
    if len(times) < 2 or any(not math.isfinite(t) for t in times) or any(b <= a for a, b in zip(times, times[1:])):
        raise ValueError('projection_diagnostic_times_invalid')
    rows = []
    for role, values in sorted(series.items()):
        if len(values) != len(times) or any(not math.isfinite(v) or v < 0 or v > 1+1e-8 for v in values):
            raise ValueError('projection_diagnostic_ratios_invalid')
        baseline = values[0]
        relative = [v / baseline for v in values] if baseline > 1e-8 else None
        collapsed = [i for i, v in enumerate(values) if v < .2]
        outside = [i for i, v in enumerate(relative or []) if v < .5 or v > 1.5]
        failures = []
        for name, indices in [('projected_segment_below_20_percent', collapsed),
                               ('relative_length_outside_half_to_one_and_half', outside)]:
            groups = []
            for i in indices:
                if groups and i == groups[-1][-1]+1:
                    groups[-1].append(i)
                else:
                    groups.append([i])
            failures.extend(dict(reason=name, start_frame=g[0], end_frame=g[-1],
                start_time=times[g[0]], end_time=times[g[-1]], sample_count=len(g)) for g in groups)
        minimum = min(range(len(values)), key=values.__getitem__)
        rows.append(dict(role=role, baseline_visibility=baseline, baseline_collapsed=baseline < .2,
            minimum_visibility=values[minimum], minimum_frame=minimum, minimum_time=times[minimum],
            visibility=values, relative_length=relative, intervals=failures,
            passed=not collapsed and not outside))
    if not rows:
        raise ValueError('projection_diagnostic_limbs_missing')
    return dict(schema='autospine.source-projection-diagnostics/v1', authority='none',
        profile='source-limb-foreshortening-v1', times=times, records=rows,
        passed=all(row['passed'] for row in rows),
        scope='source_sampled_projection_not_target_geometry_or_visibility',
        limits=dict(minimum_visibility=.2, minimum_relative_length=.5, maximum_relative_length=1.5))


def bvh_series(bvh, mapping):
    from ...bvh_fk import project_bvh_frames
    projected = project_bvh_frames(bvh, mapping)
    series = {}
    frames = [dict(frame.joints) for frame in projected.frames]
    for row in mapping['bones']:
        if not row['role'].startswith(('humanoid.arm.', 'humanoid.leg.')):
            continue
        if row['aim']['kind'] != 'joint':
            raise ValueError('character_length_joint_aim_required')
        values = []
        for frame in frames:
            a, b = frame[row['joint_name']], frame[row['aim']['joint_name']]
            length = math.dist(a.world_xyz, b.world_xyz)
            values.append(math.dist(a.screen_xy, b.screen_xy)/length if length > 1e-8 else 0.)
        series[row['role']] = values
    return series, [f.tick/1_000_000 for f in projected.frames]


def kimodo_series(raw, source, mapping):
    from ...kimodo_npz_reader import decode_kimodo_npz
    from ...kimodo_npz_consistency import validate_kimodo_consistency
    from ...kimodo_npz_map_validation import require_kimodo_npz_map
    from ...kimodo_npz_projection import kimodo_frame_ticks
    from ...kimodo_soma77 import SOMA77_INDEX_BY_NAME
    require_kimodo_npz_map(mapping, source=source)
    validated = validate_kimodo_consistency(decode_kimodo_npz(raw, source), source)
    axes = ['XYZ'.index(mapping['basis'][key][1]) for key in ('screen_x', 'screen_y')]
    series = {}
    for row in mapping['bones']:
        if not row['role'].startswith(('humanoid.arm.', 'humanoid.leg.')):
            continue
        a, b = (SOMA77_INDEX_BY_NAME[row[k]] for k in ('joint_name', 'aim_joint_name'))
        values = []
        for frame in validated.positions:
            length = math.dist(frame[a], frame[b])
            visible = math.sqrt(sum((frame[a][i]-frame[b][i])**2 for i in axes))
            values.append(visible/length if length > 1e-8 else 0.)
        series[row['role']] = values
    return series, [t/1_000_000 for t in kimodo_frame_ticks(source)]
