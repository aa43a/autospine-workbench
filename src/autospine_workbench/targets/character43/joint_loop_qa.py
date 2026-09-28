"""Separate inherited body seams from newly added channel seams.

The counterfactual keeps the final bind/topology and transformed old deforms,
removing only new helper tracks and restoring old slot alpha channels. Removed
legacy skirt probes stay removed and are reported, never silently restored.
"""
from copy import deepcopy
import math

from ...spine42_draw_order_offsets import apply_spine42_draw_order_offsets
from .affine_pose import sample

LIMITS = dict(position_px=.5, velocity_px_per_second=20., rotation_deg=.25,
              rotation_velocity_deg_per_second=15., scale=.01,
              scale_velocity_per_second=.2, alpha=.01, alpha_velocity_per_second=.5)


def neutral_document(source, result, animation):
    neutral = deepcopy(result)
    old = source['animations'][animation]; new = neutral['animations'][animation]
    old_names = {b['name'] for b in source['bones']}
    added = {b['name'] for b in result['bones']} - old_names
    for name in added:
        new.get('bones', {}).pop(name, None)
    changed_alpha = []
    source_slots = old.get('slots', {})
    for slot, channels in list(new.get('slots', {}).items()):
        original = source_slots.get(slot, {})
        if channels.get('alpha') == original.get('alpha'):
            continue
        changed_alpha.append(slot)
        if 'alpha' in original:
            channels['alpha'] = deepcopy(original['alpha'])
        else:
            channels.pop('alpha', None)
        if not channels:
            del new['slots'][slot]
    changed_existing = [n for n in sorted(old_names)
        if old.get('bones', {}).get(n) != new.get('bones', {}).get(n)]
    return neutral, sorted(added), changed_alpha, changed_existing


def _values(keys, time, fields, default):
    if not keys or time < keys[0].get('time', 0):
        return list(default)
    index = 0
    while index+1 < len(keys) and keys[index+1].get('time', 0) <= time:
        index += 1
    a, b = keys[index], keys[min(index+1, len(keys)-1)]
    ta, tb = a.get('time', 0), b.get('time', 0)
    u = 0 if ta == tb or a.get('curve') == 'stepped' else (time-ta)/(tb-ta)
    if a.get('curve') not in (None, 'stepped'):
        raise ValueError('joint_loop_curve_unsupported')
    return [a.get(f, default[i])+u*(b.get(f, default[i])-a.get(f, default[i])) for i, f in enumerate(fields)]


def _seam(samples, step, *, angular=False):
    a, b, c, d = samples
    delta = [y-x for x, y in zip(a, d, strict=True)]
    if angular:
        delta = [(v+180)%360-180 for v in delta]
    position = math.sqrt(sum(v*v for v in delta))
    velocity = math.sqrt(sum(((d[i]-c[i])-(b[i]-a[i]))**2 for i in range(len(a))))/step
    return position, velocity


def _metric_frames(frames, step):
    rows = []
    if any(set(frame) != set(frames[0]) for frame in frames):
        raise ValueError('joint_loop_slot_inventory_changed')
    for slot, points in frames[0].items():
        if any(len(frame[slot]) != len(points) for frame in frames):
            raise ValueError('joint_loop_topology_changed')
        errors = [_seam([frame[slot][i] for frame in frames], step) for i in range(len(points))]
        position = max((r[0] for r in errors), default=0.)
        velocity = max((r[1] for r in errors), default=0.)
        rows.append(dict(slot=slot, endpoint_error_px=position, velocity_error_px_per_second=velocity,
            passed=position <= LIMITS['position_px'] and velocity <= LIMITS['velocity_px_per_second']))
    return dict(passed=all(r['passed'] for r in rows), records=rows,
                max_endpoint_error_px=max((r['endpoint_error_px'] for r in rows), default=0.),
                max_velocity_error_px_per_second=max((r['velocity_error_px_per_second'] for r in rows), default=0.))


def _alpha(document, animation, slot, times):
    setup = int(slot.get('color', 'ffffffff')[-2:], 16)/255
    tracks = document['animations'][animation].get('slots', {}).get(slot['name'], {})
    if set(tracks) & {'rgba', 'rgba2', 'color', 'twoColor'}:
        return None
    return [_values(tracks.get('alpha', []), t, ('value',), (setup,)) for t in times]


def _order(document, animation, time):
    names = [s['name'] for s in document['slots']]
    current = []
    for key in document['animations'][animation].get('drawOrder', []):
        if key.get('time', 0) <= time:
            current = key.get('offsets', [])
    return list(apply_spine42_draw_order_offsets(names, current))


def _visibility(document, animation, times, step, slots=None):
    rows = []
    for slot in document['slots']:
        if slots is not None and slot['name'] not in slots:
            continue
        values = _alpha(document, animation, slot, times)
        if values is None:
            rows.append(dict(slot=slot['name'], passed=False, reason='combined_color_timeline_unmeasured'))
            continue
        endpoint, velocity = _seam(values, step)
        visible = [v[0] >= 8/255 for v in values]
        rows.append(dict(slot=slot['name'], endpoint_alpha_error=endpoint,
            alpha_velocity_error_per_second=velocity, endpoint_visibility_equal=visible[0] == visible[-1],
            start_alpha=values[0][0], end_alpha=values[-1][0],
            passed=endpoint <= LIMITS['alpha'] and velocity <= LIMITS['alpha_velocity_per_second']
                   and visible[0] == visible[-1]))
    orders = [_order(document, animation, t) for t in (times[0], times[-1])]
    return dict(passed=all(r['passed'] for r in rows) and orders[0] == orders[1], records=rows,
                draw_order_equal=orders[0] == orders[1], start_draw_order=orders[0], end_draw_order=orders[1])


def _local_channels(document, animation, added, times, step):
    rows = []
    props = {'translate': (('x', 'y'), (0., 0.), 'position_px', 'velocity_px_per_second'),
             'rotate': (('value',), (0.,), 'rotation_deg', 'rotation_velocity_deg_per_second'),
             'scale': (('x', 'y'), (1., 1.), 'scale', 'scale_velocity_per_second'),
             'shear': (('x', 'y'), (0., 0.), 'rotation_deg', 'rotation_velocity_deg_per_second')}
    for bone in added:
        tracks = document['animations'][animation].get('bones', {}).get(bone, {})
        for name, keys in tracks.items():
            if name not in props:
                rows.append(dict(bone=bone, channel=name, passed=False, reason='channel_unmeasured'))
                continue
            fields, default, position_limit, velocity_limit = props[name]
            values = [_values(keys, t, fields, default) for t in times]
            endpoint, velocity = _seam(values, step, angular=name in ('rotate', 'shear'))
            rows.append(dict(bone=bone, channel=name, endpoint_error=endpoint, velocity_error=velocity,
                start=values[0], end=values[-1], endpoint_limit=LIMITS[position_limit],
                velocity_limit=LIMITS[velocity_limit],
                passed=endpoint <= LIMITS[position_limit] and velocity <= LIMITS[velocity_limit]))
    return dict(passed=all(r['passed'] for r in rows), records=rows,
                scope='new_helper_local_transform_channels_independent_of_parent_body_pose')


def inspect(source, result, animation, duration, requested, *, face_report=None, secondary_report=None):
    if type(duration) not in (int, float) or not math.isfinite(duration) or duration <= 0:
        raise ValueError('joint_loop_duration')
    if type(requested) is not bool:
        raise ValueError('joint_loop_requested')
    step = min(1/120, duration/4)
    times = [0., step, duration-step, duration]
    neutral, added, changed_alpha, changed_existing = neutral_document(source, result, animation)
    sources = [sample(source, animation, t)[0] for t in times]
    results = [sample(result, animation, t)[0] for t in times]
    baselines = [sample(neutral, animation, t)[0] for t in times]
    increments = [{slot: [[v[i]-b[i] for i in (0, 1)]
        for v, b in zip(points, baseline[slot], strict=True)] for slot, points in current.items()}
        for current, baseline in zip(results, baselines, strict=True)]
    body, overall = _metric_frames(sources, step), _metric_frames(results, step)
    baseline, increment = _metric_frames(baselines, step), _metric_frames(increments, step)
    local = _local_channels(result, animation, added, times, step)
    body_visibility = _visibility(source, animation, times, step)
    overall_visibility = _visibility(result, animation, times, step)
    # New alpha is separately checked. Body draw-order is already part of overall.
    effect_visibility = _visibility(result, animation, times, step, set(changed_alpha))
    effect_alpha_passed = all(r['passed'] for r in effect_visibility['records'])
    body_passed = body['passed'] and body_visibility['passed']
    effect_passed = increment['passed'] and local['passed'] and effect_alpha_passed
    passed = body_passed and effect_passed and overall['passed'] and overall_visibility['passed']
    replaced = list((secondary_report or {}).get('probe_tracks_replaced', []))
    limitations = ['numeric_endpoint_and_one_sided_velocity_not_visual_loop_acceptance',
                  'increment_world_space_includes_parent_pose_difference_when_body_is_not_looping']
    if not body_passed:
        limitations.append('original_body_is_not_loop_ready_joint_effects_do_not_remove_this_limit')
    if replaced:
        limitations.append('identified_legacy_auxiliary_probes_removed_not_restored_in_counterfactual')
    return dict(profile='joint-loop-channel-isolation-v1', requested=requested,
        status=('passed' if passed else 'needs_changes') if requested else 'not_requested',
        measured_passed=passed, duration=duration, sample_times=times, difference_step_seconds=step,
        limits=deepcopy(LIMITS), source_body=dict(**body, visibility=body_visibility, loop_ready=body_passed),
        neutral_joint=baseline, added_effects=dict(passed=effect_passed, world_increment=increment,
            local_helpers=local, face_alpha=dict(passed=effect_alpha_passed, records=effect_visibility['records']),
            new_helper_bones=added, changed_alpha_slots=changed_alpha),
        overall=dict(**overall, visibility=overall_visibility),
        max_endpoint_error_px=overall['max_endpoint_error_px'],
        max_velocity_error_px_per_second=overall['max_velocity_error_px_per_second'],
        changed_existing_aux_tracks=changed_existing, probe_tracks_replaced=replaced,
        neutralization='same_final_topology_and_old_deforms_without_new_helper_or_alpha_tracks',
        comparison='each_slot_increment_and_each_local_channel_never_reduction_in_whole_character_maximum',
        limitations=limitations, authority='none', visual_status='not_evaluated')
