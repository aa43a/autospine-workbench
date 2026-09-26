"""Freeze the observed leg scope; preflight never runs the repair or grants QA."""
from hashlib import sha256
import json

from .limb_transverse_repair import prepare
from .numeric_reference import read

PROFILE = 'selected-leg-transverse-repair-v1'


def resolve(files, character, slot, animation):
    required = ('skeleton.json', 'numeric-reference.json', 'rig-setup-reference.json',
                'motion-review.json', 'motion-ir.json', 'motion-contact.json')
    if any(k not in files for k in required):
        raise ValueError('motion_transverse_source_missing')
    document = json.loads(files['skeleton.json']); bind = json.loads(character['skeleton.json'])
    if any(document.get(k) != bind.get(k) for k in ('bones', 'slots', 'skins')):
        raise ValueError('motion_transverse_bind_changed')
    digest = sha256(files['skeleton.json']).hexdigest()
    reference = read(files); setup = json.loads(files['rig-setup-reference.json'])
    if any(r.get('skeleton_sha256') != digest for r in (reference, setup)):
        raise ValueError('motion_transverse_reference_changed')
    if set(document['animations']) != {animation} or set(reference['animations']) != {animation}:
        raise ValueError('motion_transverse_animation_unsupported')
    review = json.loads(files['motion-review.json'])
    if review.get('source_pose_fit', {}).get('profile') != 'source-absolute-limb-projection-v1':
        raise ValueError('limb_transverse_source_projection_required')
    if (not document['skins'] or slot not in document['skins'][0]['attachments'] or
            slot not in setup.get('vertices', {})):
        raise ValueError('motion_transverse_slot_missing')
    rows, _, used, times, _ = prepare(document, animation, [slot])
    if not any(used <= {p+'_'+side for p in ('thigh', 'calf', 'foot')} for side in ('l', 'r')):
        raise ValueError('motion_transverse_leg_required')
    if len(rows[slot]) != len(setup['vertices'][slot]):
        raise ValueError('motion_transverse_reference_changed')
    if 'motion-transverse.json' in files:
        applied = json.loads(files['motion-transverse.json'])['transverse']['slots']
        if slot in applied:raise ValueError('motion_transverse_already_applied')
    return dict(profile=PROFILE, slot=slot, animation=animation, bones=sorted(used),
        vertex_count=len(rows[slot]), source_key_count=len(times),
        source_hashes={k: sha256(files[k]).hexdigest() for k in required},
        character_skeleton_sha256=sha256(character['skeleton.json']).hexdigest(),
        policy='transverse-then-additive-dual-area-with-diagnostic-counterexamples-v1',
        authority='none', selected=False, production_authorized=False)
