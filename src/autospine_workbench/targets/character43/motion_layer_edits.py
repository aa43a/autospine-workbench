"""Explicit world-space attachment corrections, baked into isolated deform tracks."""
from copy import deepcopy
import math

from .affine_pose import matrices, sample
from .torso_projection_candidate import inverse, point
from ..spine43.continuous_pose import interpolate

PROFILE = 'slot-world-affine-v1'


class LayerEditError(ValueError):
    """Stable error code plus source-addressed diagnostics for editor and agents."""
    def __init__(self, code, path='', slot=None):
        super().__init__(code)
        self.diagnostics = [dict(severity='error', code=code, path=path, slot=slot,
                                 hint='本次修改未提交；请检查所指图层与属性。')]


def validate(value, document=None):
    try:
        return _validate(value, document)
    except ValueError as error:
        path, slot = '/layer_edits', None
        if isinstance(value, dict) and isinstance(value.get('transforms'), list):
            for index, row in enumerate(value['transforms']):
                try:
                    _validate(dict(profile=PROFILE, transforms=[row], draw_order=[]), document)
                except ValueError:
                    path = f'/layer_edits/transforms/{index}'
                    slot = row.get('slot') if isinstance(row, dict) else None
                    if isinstance(row, dict):
                        for field in ('dx', 'dy', 'rotation', 'scaleX', 'scaleY'):
                            number = row.get(field)
                            low, high = ((.05, 20) if field.startswith('scale') else
                                         (-3600, 3600) if field == 'rotation' else (-4096, 4096))
                            if type(number) not in (int, float) or not math.isfinite(number) or not low <= number <= high:
                                path += '/' + field
                                break
                    break
            else:
                if value.get('draw_order'):
                    path = '/layer_edits/draw_order'
        raise LayerEditError(str(error), path, slot) from error


def _validate(value, document=None):
    if (not isinstance(value, dict) or set(value) != {'profile', 'transforms', 'draw_order'}
            or value['profile'] != PROFILE or not isinstance(value['transforms'], list)
            or not isinstance(value['draw_order'], list) or len(value['transforms']) > 256
            or len(value['draw_order']) > 256):
        raise ValueError('motion_layer_edits_invalid')
    seen = set()
    for row in value['transforms']:
        if (not isinstance(row, dict) or set(row) != {'slot','dx','dy','rotation','scaleX','scaleY'}
                or not isinstance(row['slot'], str) or not row['slot'] or len(row['slot']) > 256
                or row['slot'] in seen):
            raise ValueError('motion_layer_transform_invalid')
        seen.add(row['slot'])
        for key in ('dx','dy','rotation','scaleX','scaleY'):
            number = row[key]
            if type(number) not in (int, float) or not math.isfinite(number):
                raise ValueError('motion_layer_transform_nonfinite')
        if (max(abs(row['dx']),abs(row['dy'])) > 4096 or abs(row['rotation']) > 3600
                or not .05 <= row['scaleX'] <= 20 or not .05 <= row['scaleY'] <= 20):
            raise ValueError('motion_layer_transform_out_of_range')
    order = value['draw_order']
    if any(not isinstance(s, str) or not s or len(s) > 256 for s in order) or len(set(order)) != len(order):
        raise ValueError('motion_layer_order_invalid')
    if document is not None:
        slots = [s['name'] for s in document['slots']]
        if not seen <= set(slots) or (order and set(order) != set(slots)):
            raise ValueError('motion_layer_target_mismatch')
        attachments = document['skins'][0]['attachments']
        for slot in seen:
            choices = attachments.get(slot, {})
            attachment = choices.get(slot, {})
            if (set(choices) != {slot} or attachment.get('type') != 'mesh'
                    or len(attachment.get('vertices', [])) == len(attachment.get('uvs', []))):
                raise ValueError('motion_layer_attachment_unsupported')
    return deepcopy(value)


def edit_impact(edits):
    """Declared review scope, not a claim that incremental execution is enabled."""
    edits = validate(edits)
    transformed = bool(edits['transforms'])
    ordered = bool(edits['draw_order'])
    return dict(slots=[row['slot'] for row in edits['transforms']], geometry=transformed,
                draw_order=ordered, execution='full_build',
                checks=['geometry', 'contact', 'occlusion', 'runtime'] if transformed else
                ['occlusion', 'runtime'] if ordered else [])


def warp(p, row, pivot):
    angle = math.radians(row['rotation']); c, s = math.cos(angle), math.sin(angle)
    x, y = (p[0]-pivot[0])*row['scaleX'], (p[1]-pivot[1])*row['scaleY']
    return [pivot[0]+row['dx']+c*x-s*y, pivot[1]+row['dy']+s*x+c*y]


def apply(document, animation, edits, times):
    """Keep setup/rig bytes intact; sampled deform reproduces world-space affine."""
    edits = validate(edits, document)
    result = deepcopy(document)
    output = result['animations'][animation]
    if edits['draw_order']:
        slots = [s['name'] for s in document['slots']]
        output['drawOrder'] = [dict(time=0, offsets=[dict(slot=s, offset=edits['draw_order'].index(s)-i)
                                                   for i,s in enumerate(slots)])]
    rows = edits['transforms']
    report = dict(profile=PROFILE, edits=edits, edit_impact=edit_impact(edits), authority='none', pivots={},
                  interpolation_tolerance_px=.25, interpolation_max_error_px=0,
                  status='sampled_candidate_requires_visual_review')
    if not rows:
        return result, report, times
    if document['animations'][animation].get('slots'):
        raise ValueError('motion_layer_attachment_timeline_unsupported')
    setup = deepcopy(document); setup['animations'] = {animation: {'bones': {}}}
    points = sample(setup, animation, 0)[0]
    pivots = {r['slot']: [(min(p[k] for p in points[r['slot']])+max(p[k] for p in points[r['slot']]))/2
                           for k in (0,1)] for r in rows}
    report['pivots'] = pivots
    duration = max(times)
    count = max(1, math.ceil(duration*60))
    from .moving_ankle_candidate import synthetic_sample_times
    source = document['animations'][animation]
    events = {k['time'] for tracks in source.get('bones',{}).values() for keys in tracks.values() for k in keys}
    events.update(k['time'] for skin in source.get('attachments',{}).values() for slots in skin.values()
                  for tracks in slots.values() for keys in tracks.values() for k in keys)
    grid, aliases = synthetic_sample_times(sorted(events), [*times, *(duration*i/count for i in range(count+1))])
    report['synthetic_time_aliases'] = aliases
    if len(grid) > 4097:
        raise ValueError('motion_layer_sample_limit')
    for row in rows:
        slot = row['slot']; data = document['skins'][0]['attachments'][slot][slot]['vertices']
        old_keys = document['animations'][animation].get('attachments',{}).get('default',{}).get(slot,{}).get(slot,{}).get('deform')
        keys = []
        for time in grid:
            transforms = matrices(document,animation,time)
            previous = interpolate(old_keys,time,'vertices') if old_keys else []
            offsets=[]; i=j=0
            while i < len(data):
                n=data[i]; i+=1
                for _ in range(n):
                    index,x,y,_weight=data[i:i+4]; i+=4
                    dx,dy=previous[j:j+2] if previous else (0,0); j+=2
                    matrix=transforms[document['bones'][index]['name']]
                    desired=warp(point(matrix,x+dx,y+dy),row,pivots[slot])
                    nx,ny=point(inverse(matrix),*desired)
                    offsets.extend((nx-x,ny-y))
            keys.append(dict(time=time,vertices=offsets))
        output.setdefault('attachments',{}).setdefault('default',{}).setdefault(slot,{}).setdefault(slot,{})['deform']=keys
    # Midpoint validation prevents accepting interpolation errors between authored keys.
    check_times=[(a+b)/2 for a,b in zip(grid,grid[1:])]
    for time in check_times:
        before=sample(document,animation,time)[0]; after=sample(result,animation,time)[0]
        for row in rows:
            slot=row['slot']
            error=max(math.dist(warp(p,row,pivots[slot]),q) for p,q in zip(before[slot],after[slot]))
            report['interpolation_max_error_px']=max(report['interpolation_max_error_px'],error)
    if report['interpolation_max_error_px'] > report['interpolation_tolerance_px']:
        raise ValueError('motion_layer_interpolation_error')
    report.update(sample_count=len(grid), midpoint_checks=len(check_times),
                  limitation='sampled_interpolation_not_continuous_proof; contact_and_occlusion_require_review')
    return result, report, grid
