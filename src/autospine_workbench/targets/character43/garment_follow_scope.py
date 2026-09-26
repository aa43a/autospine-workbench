"""Resolve one garment from immutable generated-chain declarations, never proximity."""
from hashlib import sha256
import json
import math

from ...automation.motion_target_pose import final_times
from .attachment_root_bake import validate
from .attachment_root_transport import displacements
from .affine_pose import matrices
from .numeric_reference import read

PROFILE = 'selected-declared-garment-follow-v1'
STABLE_TIME_POLICY = 'animation-key-midpoints-preserve-prior-qa-v1'


def resolve(files, character, slot, animation, *, stable_sampling=False):
    if 'motion-garment-follow.json' in files:
        applied = json.loads(files['motion-garment-follow.json']).get('declaration', {})
        if not applied.get('slot') or applied['slot'] == slot:
            raise ValueError('motion_garment_already_applied')
    if 'skirt-trial.json' not in character:
        raise ValueError('motion_garment_declaration_missing')
    if 'motion-torso-projection.json' not in files:
        raise ValueError('motion_garment_torso_required')
    doc, bind = (json.loads(f['skeleton.json']) for f in (files, character))
    if any(doc.get(k) != bind.get(k) for k in ('bones', 'slots', 'skins')):
        raise ValueError('motion_garment_bind_changed')
    reference = read(files)
    digest = sha256(files['skeleton.json']).hexdigest()
    if reference['skeleton_sha256'] != digest:
        raise ValueError('motion_garment_reference_changed')
    if set(doc['animations']) != {animation} or set(reference['animations']) != {animation}:
        raise ValueError('motion_garment_animation_unsupported')
    setup = json.loads(files['rig-setup-reference.json'])
    if setup['skeleton_sha256'] != digest:
        raise ValueError('motion_garment_setup_changed')
    trial = json.loads(character['skirt-trial.json'])
    rows = [r for r in trial['rows'] if r['layer_id'] == slot]
    if trial.get('waist_driver') != 'reviewed-chest-v1' or len(rows) != 1:
        raise ValueError('motion_garment_slot_undeclared')
    roots = [f"{slot}-{chain['id']}_upper" for chain in rows[0]['mesh']['helper_chains']]
    if not roots or len(set(roots)) != len(roots):
        raise ValueError('motion_garment_roots_invalid')
    times = final_times(doc, animation, [] if stable_sampling else [r['time'] for r in reference['animations'][animation]])
    torso = json.loads(files['motion-torso-projection.json'])
    validate(doc, animation, torso, times)
    baseline = matrices(doc, animation, 0)
    if any(root not in baseline for root in roots):
        raise ValueError('motion_garment_roots_invalid')
    descendants = displacements(doc['bones'], baseline, baseline, 'chest', roots)
    affected = set()
    for name, choices in doc['skins'][0]['attachments'].items():
        if set(choices) != {name}:
            raise ValueError('motion_garment_attachment_unsupported')
        mesh = choices[name]; data = mesh.get('vertices', [])
        if mesh.get('type') != 'mesh' or len(data) == len(mesh.get('uvs', [])):
            raise ValueError('motion_garment_attachment_unsupported')
        i = width = 0
        while i < len(data):
            count = data[i]; i += 1
            for _ in range(count):
                index, _, _, weight = data[i:i+4]; i += 4; width += 2
                if weight > 0 and doc['bones'][index]['name'] in descendants:
                    affected.add(name)
        if name == slot:
            keys = doc['animations'][animation].get('attachments', {}).get('default', {}).get(name, {}).get(name, {}).get('deform', [])
            if any('curve' in k or 'offset' in k or len(k.get('vertices', [])) != width
                   or any(not math.isfinite(v) for v in k['vertices']) for k in keys):
                raise ValueError('motion_garment_dense_linear_deform_required')
    if affected != {slot}:
        raise ValueError('motion_garment_shared_or_missing_weights')
    return dict(profile=PROFILE, slot=slot, animation=animation, roots=sorted(roots),
        skeleton_sha256=digest, character_skeleton_sha256=sha256(character['skeleton.json']).hexdigest(),
        declaration_sha256=sha256(character['skirt-trial.json']).hexdigest(),
        torso_sha256=sha256(files['motion-torso-projection.json']).hexdigest(),
        reference_sha256=sha256(files['numeric-reference.json']).hexdigest(),
        bake_sample_count=len(times), authority='none', selected=False,
        **({'time_policy': STABLE_TIME_POLICY} if stable_sampling else {}))
