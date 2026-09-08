"""Explicit attachment/track union; conflicting shared transforms fail closed."""
from copy import deepcopy


def merge(base, donor, names):
    if not names or len(names)!=len(set(names)):raise ValueError('limb_selection')
    if base['bones']!=donor['bones']:raise ValueError('limb_skeleton')
    if len(base['animations'])!=1 or len(donor['animations'])!=1:raise ValueError('limb_animation_inventory')
    result=deepcopy(base);a=next(iter(result['animations'].values()));b=next(iter(donor['animations'].values()))
    end=lambda clip:max(k['time'] for track in clip['bones'].values() for keys in track.values() for k in keys)
    if end(a)!=end(b) or end(a)<=0:raise ValueError('limb_duration')
    attachments=result['skins'][0]['attachments'];sources=donor['skins'][0]['attachments']
    for name in names:
        if name in attachments or name not in sources or sources[name][name]['type']!='mesh':raise ValueError('limb_attachment')
        attachments[name]=deepcopy(sources[name])
        slots=[s for s in donor['slots'] if s['name']==name]
        if len(slots)!=1:raise ValueError('limb_slot')
        result['slots'].append(deepcopy(slots[0]))
    for bone,track in b['bones'].items():
        if bone in a['bones'] and a['bones'][bone]!=track:raise ValueError('limb_track_conflict')
        a['bones'][bone]=deepcopy(track)
    tracks=a.setdefault('attachments',{}).setdefault('default',{})
    for name in names:
        if name in tracks:raise ValueError('limb_deform_conflict')
        tracks[name]=deepcopy(b['attachments']['default'][name])
    return result
