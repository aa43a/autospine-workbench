"""Bounded per-attachment re-solve; preserve all other animation and rig data."""
from copy import deepcopy
from hashlib import sha256
import json

from ...automation.storage_io import canonical_bytes
from .affine_area_repair import repair
from .affine_pose import sample
from .deformation_qa import inspect
from .numeric_reference import read, write, carry_setup


def build(files, plan, on_progress=None):
    slot, name = plan['slot'], plan['animation']
    final_leg = plan.get('local_solver') is not None
    if final_leg:
        from .final_leg_repair_policy import verify
        verify(files, plan)
    document = json.loads(files['skeleton.json'])
    reference = read(files)
    if reference['skeleton_sha256'] != sha256(files['skeleton.json']).hexdigest():
        raise ValueError('motion_repair_reference_mismatch')
    if len(document['skins']) != 1 or document['skins'][0]['name'] != 'default':
        raise ValueError('motion_repair_skin_unsupported')
    mesh = document['skins'][0]['attachments'][slot][slot]
    if mesh.get('type') != 'mesh' or len(mesh['vertices']) == len(mesh['uvs']):
        raise ValueError('motion_repair_weighted_mesh_required')
    if set(document['animations']) != {name}:
        raise ValueError('motion_repair_single_animation_required')
    setup = json.loads(files['rig-setup-reference.json'])
    if setup['skeleton_sha256'] != reference['skeleton_sha256']:
        raise ValueError('motion_repair_setup_mismatch')
    isolated = deepcopy(document)
    isolated['slots'] = [s for s in document['slots'] if s['name'] == slot]
    isolated['skins'][0]['attachments'] = {slot: deepcopy(document['skins'][0]['attachments'][slot])}
    # Only solver input is stripped; original channels are retained in output.
    isolated['animations'][name] = {'bones': deepcopy(document['animations'][name]['bones'])}
    if final_leg:
        from .projected_area_adaptive import build as adaptive
        solved, solver = adaptive(isolated, name, {slot:setup['vertices'][slot]},
            temporal=True, dual_floor=True, progress=on_progress)
    else:
        solved, solver = repair(isolated, name, samples=129, convergent=True,
            setup_vertices={slot: setup['vertices'][slot]}, progress=on_progress)
    tracks = solved['animations'][name].get('attachments',{}).get('default',{}).get(slot)
    if tracks is None:
        raise ValueError('motion_repair_no_corrective_generated')
    result = deepcopy(document)
    # Existing 4.3 deform is replaced for this slot only; ambiguous legacy layout is rejected.
    if document['animations'][name].get('deform'):
        raise ValueError('motion_repair_legacy_deform_unsupported')
    result['animations'][name].setdefault('attachments',{}).setdefault('default',{}).setdefault(slot,{}).setdefault(slot,{})['deform'] = tracks[slot]['deform']
    restored = deepcopy(result)
    old = document['animations'][name].get('attachments',{}).get('default',{}).get(slot)
    if old is None:
        del restored['animations'][name]['attachments']['default'][slot]
        if not restored['animations'][name]['attachments']['default']:
            del restored['animations'][name]['attachments']['default']
        if not restored['animations'][name]['attachments']:
            del restored['animations'][name]['attachments']
    else:
        restored['animations'][name]['attachments']['default'][slot] = old
    if restored != document:
        raise ValueError('motion_repair_unrelated_channels_changed')
    keys = [k['time'] for k in tracks[slot]['deform']]
    times = sorted({f['time'] for f in reference['animations'][name]} | set(keys)
                   | {(a+b)/2 for a,b in zip(keys,keys[1:])})
    if len(times) > 4097:
        raise ValueError('motion_repair_sample_limit')
    if final_leg:
        from ...automation.motion_target_pose import final_times
        # Quarter-key intervals match the final-pose experiment. Subdivide actual
        # animation keys, never recursively subdivide a preceding QA-only grid.
        key_midpoints = final_times(result, name, [])
        times = sorted(set(final_times(result, name, key_midpoints)) |
                       {f['time'] for f in reference['animations'][name]})
        if len(times) > 4097:
            raise ValueError('motion_repair_sample_limit')
    output = {n:v for n,v in files.items() if n.endswith('.png') or n in ('skeleton.atlas','motion-ir.json')}
    if final_leg and 'motion-torso-projection.json' in files:
        # Bone motion and torso deform are unchanged; keep the declared driver.
        output['motion-torso-projection.json'] = files['motion-torso-projection.json']
    output['skeleton.json'] = canonical_bytes(result)
    digest = sha256(output['skeleton.json']).hexdigest()
    carry_setup(files, output)
    frames = []
    for index,time in enumerate(times):
        if on_progress and index%32 == 0:on_progress(dict(stage='validate',index=index,total=len(times)))
        frames.append(dict(time=time,vertices=sample(result,name,time)[0]))
    output = write(output, dict(skeleton_sha256=digest,animations={name:frames}), compressed=final_leg)
    geometry = inspect(output,setup_vertices=setup['vertices'])
    output['deformation.json'] = canonical_bytes(geometry)
    evidence = json.loads(files['motion-review.json'])
    from .final_motion_contact import recheck
    contact = recheck(result,name,json.loads(files['motion-ir.json']),
                      json.loads(files['motion-contact.json']),times,evidence['reference_length_px'])
    evidence.update(status='needs_changes', geometry_passed=geometry['passed'],
                    runtime_status='not_evaluated', depth_order_status='not_evaluated',
                    contact_status=contact['status'], authority='none', selected=False, production_authorized=False)
    evidence['issues'] = [i for i in evidence.get('issues',[]) if i['stage']=='projection']
    evidence['issues'].append(dict(stage='repair',reason_code='motion_repair_requires_visual_and_depth_revalidation'))
    if not geometry['passed']:
        evidence['issues'].append(dict(stage='geometry',reason_code='motion_target_deformation_needs_changes'))
    for key in ('area_repair','post_contact_repair'):
        evidence.pop(key,None)
    # Prior projection facts refer to unchanged bones; overlap/contact findings are not reissued.
    output['motion-review.json'] = canonical_bytes(evidence)
    output['motion-contact.json'] = canonical_bytes(contact)
    output['parent-motion-review.json'] = files['motion-review.json']
    summary = dict(profile='selected-attachment-area-repair-v1',slot=slot,animation=name,
        solver=solver,unchanged_other_channels=True,authority='none',selected=False,
        parent_geometry=json.loads(files['deformation.json']),geometry=geometry,
        sample_count=len(times),scope='sampled_local_candidate_not_continuous_or_visual_acceptance')
    if final_leg:
        from .final_leg_repair_policy import PROFILE
        baseline = write(dict(files), dict(skeleton_sha256=sha256(files['skeleton.json']).hexdigest(),
            animations={name:[dict(time=t,vertices=sample(document,name,t)[0]) for t in times]}), compressed=True)
        summary.update(profile=PROFILE, local_solver=plan['local_solver'],
            parent_geometry=inspect(baseline,setup_vertices=setup['vertices']),
            scope='same_grid_final_leg_candidate_not_continuous_or_visual_acceptance')
    output['motion-repair.json'] = canonical_bytes(summary)
    manifest = json.loads(files['character-manifest.json'])
    manifest.update(status='needs_changes',authority='none',selected=False,production_authorized=False,
                    files={n:sha256(v).hexdigest() for n,v in output.items()})
    output['character-manifest.json'] = canonical_bytes(manifest)
    return output, evidence, geometry
