"""Compile body, expressions and secondary motion into one portable Spine animation."""
from copy import deepcopy
from hashlib import sha256
import json
import struct

from ...automation.storage_io import canonical_bytes
from ...resolved_project import canonical_sha256
from .affine_pose import sample
from .joint_animation_config import normalize, PROFILE
from .numeric_reference import read, write


def _setup(document, animation):
    rest = deepcopy(document)
    rest['animations'] = {animation: {}}
    return sample(rest, animation, 0)[0]


def build(files, config, *, camera_keys=None, on_progress=None, parent_review=None):
    from . import joint_face, joint_secondary
    from .deformation_qa import inspect
    from .joint_animation_qa import geometry_report, compare
    from .joint_loop_qa import inspect as inspect_loop
    source = json.loads(files['skeleton.json'])
    reference = read(files)
    if reference['skeleton_sha256'] != sha256(files['skeleton.json']).hexdigest():
        raise ValueError('joint_animation_reference_mismatch')
    if len(source['animations']) != 1 or len(source['skins']) != 1:
        raise ValueError('joint_animation_single_animation_required')
    animation = next(iter(source['animations']))
    old_times = [row['time'] for row in reference['animations'][animation]]
    duration = old_times[-1]
    config = normalize(config, duration)
    def progress(stage):
        if on_progress:
            on_progress(stage)
    progress('joint_inventory')
    face_inventory = joint_face.inventory(files, source)
    secondary_inventory = joint_secondary.inventory(files, source)
    # Prior numeric reference points are QA probes, not new authoring keys.
    from .joint_spring import grid
    times = grid(duration, 60)
    progress('joint_face')
    document, updates, face_report = joint_face.apply(files, source, animation, config['face'], times)
    face_inventory['parts'].extend(deepcopy(face_report.get('generated_templates', [])))
    times = sorted(set(times) | set(face_report.get('sample_times', [])))
    progress('joint_secondary')
    document, secondary_report = joint_secondary.apply(files, document, animation,
        dict(hair=config['hair'], cloth=config['cloth'], objects=config['objects'], loop=config['loop']), times, camera_keys=camera_keys)
    # Check key midpoints for the added helper tracks, without recursively refining old QA grids.
    new_bones = {b['name'] for b in document['bones']} - {b['name'] for b in source['bones']}
    extra = {k.get('time',0) for n,t in document['animations'][animation].get('bones',{}).items()
             if n in new_bones for keys in t.values() for k in keys}
    ordered = sorted(extra)
    union = sorted(set(old_times) | set(times) | extra | {(a+b)/2 for a,b in zip(ordered,ordered[1:])})
    times = sorted({struct.pack('<f', t):t for t in union}.values())
    if len(times) > 4097:
        raise ValueError('joint_animation_sample_limit')
    progress('joint_validate')
    output = {n:v for n,v in files.items() if n not in ('character-manifest.json', 'deformation.json',
        'rig-setup-reference.json', 'numeric-reference.json') and not n.startswith('numeric-reference/')}
    output.update(updates)
    output['skeleton.json'] = canonical_bytes(document)
    editor = json.loads(output['editor/skeleton.json']) if 'editor/skeleton.json' in output else deepcopy(document)
    for field in ('bones', 'slots', 'skins', 'animations'):
        editor[field] = deepcopy(document[field])
    editor.setdefault('skeleton', {})['images'] = './images/'
    output['editor/skeleton.json'] = canonical_bytes(editor)
    for name, raw in list(output.items()):
        if name.startswith('images/'):
            output['editor/'+name] = raw
    digest = sha256(output['skeleton.json']).hexdigest()
    setup = _setup(document, animation)
    output['rig-setup-reference.json'] = canonical_bytes(dict(skeleton_sha256=digest, time=0, vertices=setup))
    frames = []
    for index, time in enumerate(times):
        if index % 64 == 0:
            progress('joint_validate')
        frames.append(dict(time=time, vertices=sample(document, animation, time)[0]))
    output = write(output, dict(skeleton_sha256=digest, animations={animation:frames}), compressed=True)
    raw_geometry = inspect(output, setup_vertices=setup)
    geometry = geometry_report(raw_geometry, face_inventory, config['face']['enabled'],
        face_report=face_report, source_geometry=json.loads(files['deformation.json']))
    before = source['skins'][0]['attachments']; after = document['skins'][0]['attachments']
    affected = {slot for slot in after if before.get(slot) != after[slot]}
    preservation = compare(source, document, animation, times, affected)
    loop = inspect_loop(source, document, animation, duration, config['loop'],
                        face_report=face_report, secondary_report=secondary_report)
    report = dict(schema='autospine.joint-animation/v1', profile=PROFILE,
        animation=animation, duration=duration, config=config, config_sha256=canonical_sha256(config),
        parent_skeleton_sha256=sha256(files['skeleton.json']).hexdigest(), skeleton_sha256=digest,
        inventory=dict(face=face_inventory, **secondary_inventory), face=face_report, secondary=secondary_report,
        sample_count=len(times), affected_slots=sorted(affected), preservation=preservation, loop=loop,
        authority='none', selected=False, production_authorized=False, visual_status='needs_review')
    output['joint-animation.json'] = canonical_bytes(report)
    output['generic-deformation.json'] = canonical_bytes(raw_geometry)
    output['deformation.json'] = canonical_bytes(geometry)
    parent_raw = files.get('motion-review.json') or (canonical_bytes(parent_review) if parent_review else None)
    if parent_raw is None:
        raise ValueError('joint_animation_parent_evidence_required')
    output['parent-motion-review.json'] = parent_raw
    # Previous repairs remain provenance, never current-candidate geometry proof.
    for name in ('motion-repair.json', 'motion-repair-provenance.json', 'motion-torso-projection.json',
                 'motion-moving-ankles.json', 'motion-layer-edits.json'):
        if name in output:
            output['parent-'+name] = output.pop(name)
    evidence = json.loads(parent_raw)
    inherited = deepcopy(evidence.get('issues', []))
    inherited_context = dict(source_review_sha256=sha256(parent_raw).hexdigest(),
        source_skeleton_sha256=sha256(files['skeleton.json']).hexdigest(), issue_count=len(inherited))
    evidence.update(status='needs_review' if geometry['passed'] else 'needs_changes',
        geometry_passed=geometry['passed'], runtime_status='not_evaluated', depth_order_status='not_evaluated',
        joint_profile=PROFILE, inherited_issue_context=inherited_context, issues=deepcopy(inherited),
        authority='none', selected=False, production_authorized=False)
    if not geometry['passed']:
        evidence['issues'].append(dict(stage='geometry', reason_code='joint_animation_deformation_needs_changes'))
    if loop['status'] == 'needs_changes':
        evidence['issues'].append(dict(stage='joint_loop', reason_code='joint_animation_loop_needs_changes'))
    if secondary_report.get('status') in ('blocked', 'partial'):
        evidence['issues'].append(dict(stage='joint_secondary', reason_code='joint_secondary_channel_incomplete'))
    if config['face']['enabled'] and face_report.get('missing'):
        evidence['issues'].append(dict(stage='joint_face', reason_code='joint_face_material_incomplete',
                                      missing=face_report['missing']))
    from .final_motion_contact import recheck
    contact = recheck(document, animation, json.loads(files['motion-ir.json']),
        json.loads(files['motion-contact.json']), times, evidence['reference_length_px'])
    evidence['contact_status'] = contact['status']
    output['motion-contact.json'] = canonical_bytes(contact)
    output['motion-review.json'] = canonical_bytes(evidence)
    manifest = json.loads(files['character-manifest.json'])
    manifest.update(status=evidence['status'], authority='none', selected=False, production_authorized=False,
                    joint_animation_profile=PROFILE, files={n:sha256(v).hexdigest() for n,v in output.items()})
    output['character-manifest.json'] = canonical_bytes(manifest)
    return output, evidence, geometry
