"""Reconstruct an exact rejected contact proposal for further candidate checks."""
from copy import deepcopy
from hashlib import sha256
import math
from ...automation.storage_io import canonical_bytes
from ..spine43.continuous_pose import interpolate


def replay(document,name,contact):
    if contact['selected'] or sha256(canonical_bytes(document)).hexdigest()!=contact['input_skeleton_sha256']:
        raise ValueError('support_probe_base_changed')
    attempt=contact['phase_attempt'];rows=attempt['rows']
    if attempt['status']!='candidate' or attempt['profile']!='causal-joint-support-timeline-v1':
        raise ValueError('support_probe_no_complete_proposal')
    if len(rows)<2 or rows[0]['time']!=0 or any(b['time']<=a['time'] for a,b in zip(rows,rows[1:])):
        raise ValueError('support_probe_timeline_invalid')
    doc=deepcopy(document);base=document['animations'][name]['bones'];tracks=doc['animations'][name]['bones']
    tracks['root']['translate']=[]
    names=('thigh_l','calf_l','thigh_r','calf_r')
    for n in names:tracks[n]['rotate']=[]
    root=[dict(time=k['time'],vertices=[k['x'],k['y']]) for k in base['root']['translate']]
    for row in rows:
        t=row['time']
        if len(row['root_shift'])!=2 or not all(math.isfinite(v) for v in [t,*row['root_shift'],*row['angles'].values()]):
            raise ValueError('support_probe_values_invalid')
        xy=interpolate(root,t,'vertices')
        tracks['root']['translate'].append(dict(time=t,x=xy[0]+row['root_shift'][0],y=xy[1]+row['root_shift'][1]))
        for n in names:
            angle=interpolate(base[n]['rotate'],t,'value')+row['angles'][n]
            tracks[n]['rotate'].append(dict(time=t,value=angle))
    return doc


def without_generated_deform(document,name,area_evidence):
    """Remove only the full inventory owned by this motion's area correction."""
    animation=document['animations'][name]
    expected={r['slot'] for r in area_evidence['records']}
    actual=animation.get('attachments',{})
    if set(actual)-{'default'} or set(actual.get('default',{}))!=expected:
        raise ValueError('support_repair_deform_inventory_mismatch')
    for slot,choices in actual.get('default',{}).items():
        if set(choices)!={slot} or set(choices[slot])!={'deform'}:
            raise ValueError('support_repair_deform_inventory_mismatch')
    if animation.get('deform'):raise ValueError('support_repair_legacy_deform')
    result=deepcopy(document);result['animations'][name].pop('attachments',None)
    return result
