"""Whole-clip attachment deform fallback; never an adoption decision."""
from copy import deepcopy


def build(reference, candidate, followers):
    if not followers or len(set(followers))!=len(followers): raise ValueError('fallback_selection')
    if len(reference['animations'])!=1 or len(candidate['animations'])!=1: raise ValueError('fallback_animation_count')
    a=next(iter(reference['animations'].values())); b=next(iter(candidate['animations'].values()))
    for key in ('bones','slots','skins'):
        if reference.get(key)!=candidate.get(key): raise ValueError('fallback_rig_identity')
    if a.get('bones')!=b.get('bones'): raise ValueError('fallback_bone_motion')
    result=deepcopy(candidate);animation=next(iter(result['animations'].values()))
    for follower in followers:
        source=a['attachments']['default'].get(follower)
        if source is None or follower not in animation['attachments']['default']: raise ValueError('fallback_attachment_missing')
        animation['attachments']['default'][follower]=deepcopy(source)
    return result
