"""Resolve only generated float32 time aliases, with a linear-curve error bound."""
from copy import deepcopy
import math
from .deform_addition import value
from .runtime_storage_reference import f32, stored_document

PROFILE = 'generated-deform-float32-alias-repair-v1'


def normalize(document, original, name, slot, *, tolerance=1e-4):
    if not math.isfinite(tolerance) or not 0 < tolerance <= 1e-4:
        raise ValueError('deform_time_alias_tolerance')
    stored_document(original)  # Never silently repair an already invalid source.
    result = deepcopy(document)
    props = result['animations'][name].get('attachments', {}).get('default', {}).get(slot, {}).get(slot, {})
    keys = props.get('deform', [])
    if not keys:
        stored_document(result)
        return result, dict(profile=PROFILE, collisions=0, maximum_local_error=0., rows=[],
                            tolerance=tolerance, authority='none', selected=False)
    if (set(props) != {'deform'} or keys[0]['time'] != 0
            or any(set(k) != {'time','vertices'} for k in keys)
            or any(b['time'] <= a['time'] for a,b in zip(keys,keys[1:]))):
        raise ValueError('deform_time_alias_dense_linear_required')
    size = len(keys[0]['vertices'])
    if (size == 0 or size % 2 or any(len(k['vertices']) != size or
            not math.isfinite(k['time']) or any(not math.isfinite(v) for v in k['vertices']) for k in keys)):
        raise ValueError('deform_time_alias_values')
    prior = original['animations'][name].get('attachments', {}).get('default', {}).get(slot, {}).get(slot, {}).get('deform', [])
    original_times = {f32(k['time']):k['time'] for k in prior}
    groups = {}
    for key in keys:groups.setdefault(f32(key['time']), []).append(key)
    output = []; rows = []
    for stored, group in groups.items():
        if len(group) == 1:
            output.append(deepcopy(group[0])); continue
        time = original_times.get(stored, stored)
        # Keep the interval endpoints exact; do not extend/shorten the clip.
        if group[0] is keys[0]:time = keys[0]['time']
        if group[-1] is keys[-1]:time = keys[-1]['time']
        output.append(dict(time=time, vertices=value(keys,time,size)))
        rows.append(dict(input_times=[k['time'] for k in group], output_time=time, stored_time=stored))
    times = sorted({k['time'] for k in keys+output}); maximum = 0.
    for time in times:
        before = value(keys,time,size); after = value(output,time,size)
        maximum = max(maximum, *(math.hypot(before[i]-after[i],before[i+1]-after[i+1]) for i in range(0,size,2)))
    # Difference of dense linear curves is linear between union breakpoints;
    # the Euclidean norm is convex, so endpoint maxima bound every local offset.
    if maximum > tolerance:raise ValueError('deform_time_alias_error_limit')
    props['deform'] = output
    stored_document(result)
    return result, dict(profile=PROFILE, input_keys=len(keys), output_keys=len(output),
        collisions=len(keys)-len(output), maximum_local_error=maximum, tolerance=tolerance,
        rows=rows, authority='none', selected=False,
        scope='continuous_local_offset_bound_not_world_geometry_or_visual_acceptance')
