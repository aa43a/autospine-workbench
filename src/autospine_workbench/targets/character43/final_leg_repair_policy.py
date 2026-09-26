"""Freeze an automatic local solver choice from the actual final limb candidate."""
from hashlib import sha256
import json

from ...resolved_project import canonical_sha256

PROFILE = 'selected-final-leg-dual-area-v1'


def select(files, slot, animation):
    review = json.loads(files['motion-review.json'])
    if review.get('source_pose_fit', {}).get('profile') != 'source-absolute-limb-projection-v1':
        return None
    failed = [r for r in json.loads(files['deformation.json'])['records']
              if r['slot'] == slot and r['animation'] == animation and r['passed'] is False]
    if not failed: return None
    document = json.loads(files['skeleton.json'])
    if len(document['skins']) != 1 or document['skins'][0]['name'] != 'default': return None
    choices = document['skins'][0]['attachments'].get(slot, {})
    if set(choices) != {slot}: return None
    mesh = choices[slot]; data = mesh.get('vertices', [])
    if mesh.get('type') != 'mesh' or len(data) == len(mesh.get('uvs', [])): return None
    i = 0; used = set()
    while i < len(data):
        count = data[i]; i += 1
        for _ in range(count):
            index, _, _, weight = data[i:i+4]; i += 4
            if weight > 0: used.add(document['bones'][index]['name'])
    if not any({'thigh_'+side, 'calf_'+side} <= used <=
               {'thigh_'+side, 'calf_'+side, 'foot_'+side} for side in ('l', 'r')):
        return None
    digest = sha256(files['skeleton.json']).hexdigest()
    setup = json.loads(files['rig-setup-reference.json'])
    if setup['skeleton_sha256'] != digest:
        raise ValueError('motion_final_leg_setup_changed')
    return dict(profile=PROFILE, skeleton_sha256=digest, mesh_sha256=canonical_sha256(mesh),
        setup_sha256=sha256(files['rig-setup-reference.json']).hexdigest(), bones=sorted(used),
        scope='final_bone_pose_fixed_single_bone_vertices_budget10_dual_area',
        authority='none', selected=False)


def verify(files, plan):
    if plan.get('local_solver') != select(files, plan['slot'], plan['animation']):
        raise ValueError('motion_final_leg_scope_changed')


def execution_profile(plan, legacy):
    if plan.get('local_solver') is None: return legacy
    if plan.get('action') != 'local_repair' or plan['local_solver'].get('profile') != PROFILE:
        raise ValueError('motion_local_solver_profile_invalid')
    return PROFILE
