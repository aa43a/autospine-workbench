"""Package authored pose changes with fresh whole-character evidence."""
from hashlib import sha256
import json

from ...automation.storage_io import canonical_bytes
from .affine_pose import sample
from .deformation_qa import inspect
from .final_motion_contact import recheck
from .numeric_reference import carry_setup, read, write
from .pose_geometry_patch import compile_patch

PROFILE = 'explicit-pose-geometry-candidate-v1'


def build(files, plan, on_progress=None):
    request = plan['pose_geometry']
    name, slot = request['animation'], request['slot']
    if plan['animation'] != name or plan['slot'] != slot:
        raise ValueError('pose_candidate_scope_mismatch')
    document = json.loads(files['skeleton.json'])
    reference = read(files)
    if reference['skeleton_sha256'] != sha256(files['skeleton.json']).hexdigest():
        raise ValueError('pose_candidate_reference_mismatch')
    if set(document['animations']) != {name} or set(reference['animations']) != {name}:
        raise ValueError('pose_candidate_single_animation_required')
    if len(document['skins']) != 1 or document['skins'][0].get('name') != 'default':
        raise ValueError('pose_candidate_default_skin_required')
    result, patch = compile_patch(document, request)
    # Keep every original reference time, including dense validation samples.
    # Compiler records already include every deform/bone knot and its midpoint.
    # Do not recursively subdivide dense parent samples on every repair generation.
    times = sorted({r['time'] for r in reference['animations'][name]} |
                   {r['time'] for r in patch['records']})
    if len(times) > 4097:
        raise ValueError('pose_candidate_sample_limit')
    output = {n: v for n, v in files.items()
              if n.endswith('.png') or n in ('skeleton.atlas', 'motion-ir.json')}
    output['skeleton.json'] = canonical_bytes(result)
    setup = carry_setup(files, output)
    if setup is None:
        raise ValueError('pose_candidate_setup_required')
    frames = []
    for index, time in enumerate(times):
        if on_progress and index % 32 == 0:
            on_progress(dict(stage='validate', index=index, total=len(times)))
        frames.append(dict(time=time, vertices=sample(result, name, time)[0]))
    output = write(output, dict(skeleton_sha256=sha256(output['skeleton.json']).hexdigest(),
                               animations={name: frames}))
    geometry = inspect(output, setup_vertices=setup)
    evidence = json.loads(files['motion-review.json'])
    contact = recheck(result, name, json.loads(files['motion-ir.json']),
                      json.loads(files['motion-contact.json']), times, evidence['reference_length_px'])
    # Derive a fresh review rather than carrying accepted/selected state forward.
    evidence = dict(status='needs_changes', reference_length_px=evidence['reference_length_px'],
                    geometry_passed=geometry['passed'], runtime_status='not_evaluated',
                    depth_order_status='not_evaluated', contact_status=contact['status'],
                    authority='none', selected=False, production_authorized=False,
                    issues=[i for i in evidence.get('issues', []) if i['stage'] == 'projection'])
    evidence['issues'].append(dict(stage='repair', reason_code='pose_geometry_requires_runtime_and_visual_review'))
    if not geometry['passed']:
        evidence['issues'].append(dict(stage='geometry', reason_code='motion_target_deformation_needs_changes'))
    output.update({'deformation.json': canonical_bytes(geometry),
                   'motion-review.json': canonical_bytes(evidence),
                   'motion-contact.json': canonical_bytes(contact),
                   'parent-motion-review.json': files['motion-review.json'],
                   'pose-geometry-request.json': canonical_bytes(request),
                   'pose-geometry-report.json': canonical_bytes(patch)})
    output['motion-repair.json'] = canonical_bytes(dict(profile=PROFILE, slot=slot, animation=name,
        parent_geometry=json.loads(files['deformation.json']), geometry=geometry,
        unchanged_other_channels=True, authority='none', selected=False, sample_count=len(times),
        scope='sampled_whole_character_not_continuous_or_visual_acceptance'))
    manifest = json.loads(files['character-manifest.json'])
    manifest.update(status='needs_changes', authority='none', selected=False, production_authorized=False,
                    files={n: sha256(v).hexdigest() for n, v in output.items()})
    output['character-manifest.json'] = canonical_bytes(manifest)
    return output, evidence, geometry
