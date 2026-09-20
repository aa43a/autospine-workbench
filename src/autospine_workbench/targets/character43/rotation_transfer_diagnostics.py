"""Compare actual target local rotation with the declared MotionIR transfer."""
import bisect
import math

from .motionir_candidate import ROLES


def _sample(keys, time):
    index = max(0, bisect.bisect_right([k['time'] for k in keys], time)-1)
    a = keys[index]; b = keys[min(index+1, len(keys)-1)]
    fraction = 0 if b['time'] == a['time'] else max(0, min(1, (time-a['time'])/(b['time']-a['time'])))
    return a['value']+fraction*(b['value']-a['value'])


def _validate(keys):
    if (not keys or any(not math.isfinite(k['time']) or not math.isfinite(k['value']) for k in keys)
            or any(b['time'] <= a['time'] for a, b in zip(keys, keys[1:]))
            or any(k.get('curve', 'linear') != 'linear' for k in keys)):
        raise ValueError('rotation_transfer_linear_keys_required')


def compare(motion, skeleton, animation, source_diagnostic):
    tracks = skeleton['animations'][animation].get('bones', {})
    source_rows = {r['role']: r for r in source_diagnostic['records']}
    rows = []
    for track in motion['tracks']:
        if track['property'] != 'rotation' or track['target'] not in source_rows: continue
        if track['interpolation'] != 'linear': raise ValueError('rotation_transfer_source_interpolation')
        role = track['target']; bone = ROLES[role]
        expected = [dict(time=k['tick']/motion['ticks_per_second'], value=-k['value']) for k in track['keys']]
        actual = tracks.get(bone, {}).get('rotate')
        if not actual: raise ValueError('rotation_transfer_target_track_missing:'+bone)
        _validate(expected); _validate(actual)
        if abs(expected[0]['time']-actual[0]['time']) > 1e-6 or abs(expected[-1]['time']-actual[-1]['time']) > 1e-6:
            raise ValueError('rotation_transfer_time_range_mismatch')
        knots = sorted({k['time'] for k in expected+actual})
        times = sorted(set(knots+[(a+b)/2 for a, b in zip(knots, knots[1:])]))
        values = [_sample(actual, t) for t in times]
        baseline = [_sample(expected, t) for t in times]
        errors = [a-b for a,b in zip(values, baseline)]
        variation = max(errors)-min(errors)
        worst = max(range(len(times)), key=lambda i: abs(errors[i]))
        intervals = []
        for i in range(1, len(knots)):
            a,b = knots[i-1:i+1]
            delta = _sample(actual,b)-_sample(actual,a)
            if abs(delta) >= 180:
                intervals.append(dict(start_time=a,end_time=b,delta_deg=delta,
                                      source_delta_deg=_sample(expected,b)-_sample(expected,a)))
        rows.append(dict(role=role, bone=bone, sample_count=len(times),
            maximum_transfer_difference_deg=abs(errors[worst]), maximum_difference_time=times[worst],
            relative_winding_excursion_turns=variation/360,
            extra_turn_suspected=variation >= 360-1e-6,
            large_key_intervals=intervals, source_events=source_rows[role]['events']))
    if not rows: raise ValueError('rotation_transfer_limbs_missing')
    return dict(profile='motionir-target-local-rotation-comparison-v1', authority='none', records=rows,
                limitations=['contact_corrections_can_intentionally_change_local_angles',
                             'source_events_are_temporal_context_not_causal_proof',
                             'no_claim_about_axial_twist_or_rendered_appearance',
                             'linear_tracks_only_no_animation_modified'])
