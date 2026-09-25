"""Package an order-only candidate without reusing obsolete QA or identities."""
from copy import deepcopy
from hashlib import sha256
import json

from ...automation.storage_io import canonical_bytes
from ...resolved_project import canonical_sha256
from .region_order_candidate import build as order_scene, PROFILE
from .numeric_reference import read, write
from .deformation_qa import inspect
from .depth_partition_compact import compact


def build(files, plan, on_progress=None):
    document = json.loads(files['skeleton.json'])
    reference = read(files)
    setup = json.loads(files['rig-setup-reference.json'])
    source_digest = sha256(files['skeleton.json']).hexdigest()
    if any(r['skeleton_sha256'] != source_digest for r in (reference, setup)):
        raise ValueError('region_order_source_identity')
    name, slot, selection = plan['animation'], plan['slot'], plan['region_order']
    if (set(document['animations']) != {name} or len(document['skins']) != 1
            or document['skins'][0].get('name') != 'default'):
        raise ValueError('region_order_animation_or_skin_unsupported')
    mesh = document['skins'][0]['attachments'][slot][slot]
    if canonical_sha256(mesh) != selection['mesh_sha256']:
        raise ValueError('region_order_mesh_changed')
    options = dict(animation=name, interval=selection['interval']) if 'interval' in selection else {}
    if 'interval' in selection and selection['interval'] is None:
        raise ValueError('region_order_interval_invalid')
    result, report = order_scene(document, slot, selection['triangles'],
                                 selection['reference_slot'], selection['side'], **options)
    result, report = compact(result, report)
    old_slots = set(document['skins'][0]['attachments'])
    def remap(vertices):
        if set(vertices) != old_slots:
            raise ValueError('region_order_reference_inventory')
        values = deepcopy(vertices)
        points = values.pop(slot)
        for region in report['regions']:
            values[region['slot']] = [deepcopy(points[i]) for i in region['source_vertex_indices']]
        return values
    setup['vertices'] = remap(setup['vertices'])
    # All weights, transforms and deform tracks are identical. Remap the exact
    # stored reference rather than re-sampling with a less capable CPU parser.
    frames = reference['animations'][name]
    if not 2 <= len(frames) <= 4097:
        raise ValueError('region_order_sample_limit')
    for index, frame in enumerate(frames):
        if on_progress and index % 32 == 0:
            on_progress(dict(stage='region_order_validate', index=index, total=len(frames)))
        frame['vertices'] = remap(frame['vertices'])
    output = {n: v for n, v in files.items()
              if n.endswith('.png') or n in ('skeleton.atlas', 'motion-ir.json')}
    output['skeleton.json'] = canonical_bytes(result)
    digest = sha256(output['skeleton.json']).hexdigest()
    setup['skeleton_sha256'] = reference['skeleton_sha256'] = digest
    output['rig-setup-reference.json'] = canonical_bytes(setup)
    output = write(output, reference)
    geometry = inspect(output, setup_vertices=setup['vertices'])
    output['deformation.json'] = canonical_bytes(geometry)
    evidence = json.loads(files['motion-review.json'])
    from .final_motion_contact import recheck
    contact = recheck(result, name, json.loads(files['motion-ir.json']),
                      json.loads(files['motion-contact.json']),
                      [f['time'] for f in frames], evidence['reference_length_px'])
    evidence.update(status='needs_changes', geometry_passed=geometry['passed'],
                    runtime_status='not_evaluated', depth_order_status='not_evaluated',
                    contact_status=contact['status'], authority='none')
    # Painter order cannot resolve contact/material failures. Keep unresolved
    # issues visible; their old slot/triangle locations belong to parent evidence,
    # not the newly split mesh. Fresh geometry remains a separate measurement.
    evidence['issues'] = list(evidence.get('issues', []))
    evidence['inherited_issue_context'] = dict(
        source_skeleton_sha256=source_digest,
        source_review_sha256=sha256(files['motion-review.json']).hexdigest(),
        source_review_file='parent-motion-review.json',
        issue_count=len(evidence['issues']),
        location_scope='parent_candidate_not_current_partition',
        resolution_status='unresolved_not_cleared_by_order_edit')
    evidence['issues'].append(dict(stage='repair', reason_code='motion_region_order_requires_visual_review'))
    if not geometry['passed']:
        evidence['issues'].append(dict(stage='geometry', reason_code='motion_target_deformation_needs_changes'))
    for key in ('area_repair', 'post_contact_repair'):
        evidence.pop(key, None)
    output['motion-review.json'] = canonical_bytes(evidence)
    output['motion-contact.json'] = canonical_bytes(contact)
    output['parent-motion-review.json'] = files['motion-review.json']
    output['motion-repair.json'] = canonical_bytes(dict(profile=report['profile'], slot=slot,
        animation=name, region_order=report, geometry=geometry,
        parent_geometry=json.loads(files['deformation.json']), sample_count=len(frames),
        source_skeleton_sha256=source_digest, authority='none', selected=False))
    manifest = json.loads(files['character-manifest.json'])
    manifest.update(status='needs_changes', authority='none', production_authorized=False,
                    files={n: sha256(v).hexdigest() for n, v in output.items()})
    output['character-manifest.json'] = canonical_bytes(manifest)
    return output, evidence, geometry
