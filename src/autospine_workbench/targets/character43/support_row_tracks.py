"""Apply explicit support rows to a pristine source-fit bone timeline."""
from copy import deepcopy
import math
from ..spine43.continuous_pose import interpolate


def apply(document, name, rows):
    names = ('thigh_l','calf_l','thigh_r','calf_r')
    if len(rows)<2 or any(not math.isfinite(r['time']) for r in rows) or any(b['time']<=a['time'] for a,b in zip(rows,rows[1:])):
        raise ValueError('support_row_times_invalid')
    for row in rows:
        if len(row['root_shift'])!=2 or set(row['angles'])!=set(names) or not all(math.isfinite(v) for v in [*row['root_shift'],*row['angles'].values()]):
            raise ValueError('support_row_values_invalid')
    doc = deepcopy(document)
    source = document['animations'][name]['bones']; tracks = doc['animations'][name]['bones']
    root = [dict(time=k['time'],vertices=[k['x'],k['y']]) for k in source['root']['translate']]
    tracks['root']['translate'] = []
    for n in names: tracks[n]['rotate'] = []
    for row in rows:
        t = row['time']; xy = interpolate(root,t,'vertices')
        tracks['root']['translate'].append(dict(time=t,x=xy[0]+row['root_shift'][0],y=xy[1]+row['root_shift'][1]))
        for n in names:
            value = interpolate(source[n]['rotate'],t,'value')+row['angles'][n]
            tracks[n]['rotate'].append(dict(time=t,value=value))
    return doc
