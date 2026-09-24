"""Bake an isolated source-supported overlapping cap experiment at explicit poses."""
import argparse
from copy import deepcopy
import json
import math
from pathlib import Path
import numpy as np
from m4_pose_material_review import transfer
from m4_circular_knee_capacity import section_width
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.targets.character43.active_mesh_pose import sample_active
from autospine_workbench.targets.character43.affine_pose import matrices
from autospine_workbench.targets.character43.deform_addition import entries, local_delta
from autospine_workbench.targets.character43.joint_material_strip import relative
from autospine_workbench.targets.character43.overlapping_joint_caps import split
from autospine_workbench.targets.character43.skirt_candidate import inverse
from autospine_workbench.asset.planning.component_local_solver import metrics


def transform(frame, points):
    a, b, c, d, x, y = frame
    return np.asarray(points)@np.array([[a, c], [b, d]])+[x, y]


def run(source, output):
    scene = json.loads(source.read_bytes()); original = scene['skeleton']
    document = deepcopy(original); name = 'external-motion'; slot = 'layer-004'; side = 'l'
    if original['animations'][name].get('drawOrder') or original['animations'][name].get('slots', {}).get(slot):
        raise ValueError('overlap_probe_selected_slot_timeline')
    setup_doc = dict(original, animations={'setup': {}})
    setup = sample_active(setup_doc, 'setup', 0); rest = matrices(setup_doc, 'setup', 0)
    mesh = original['skins'][0]['attachments'][slot][slot]
    triangles = np.asarray(mesh['triangles']).reshape(-1, 3).tolist()
    center = np.array(rest['calf_'+side][4:]); hip = np.array(rest['thigh_'+side][4:])
    axis = (center-hip)/np.linalg.norm(center-hip)
    radius = section_width(setup['vertices'][slot], mesh['triangles'], center, axis)
    parts = split(setup['vertices'][slot], np.asarray(mesh['uvs']).reshape(-1, 2).tolist(), triangles,
                  center.tolist(), axis.tolist(), radius)
    root_index = next(i for i, b in enumerate(document['bones']) if b['name']=='root')
    old_slot = next(s for s in document['slots'] if s['name']==slot)
    at = document['slots'].index(old_slot)
    new_slots = []
    del document['skins'][0]['attachments'][slot]
    document['animations'][name].get('attachments', {}).get('default', {}).pop(slot, None)
    for i, part in enumerate(parts):
        key = slot+'-cap-'+str(i); part['slot'] = key
        new_slots.append(dict(old_slot, name=key, attachment=key))
        attachment = deepcopy(mesh)
        for field in ('edges', 'hull'):
            attachment.pop(field, None)
        attachment.update(path=mesh.get('path', slot),
                          uvs=np.asarray(part['uvs']).ravel().tolist(),
                          triangles=np.asarray(part['triangles']).ravel().tolist(),
                          vertices=[v for p in part['points'] for v in (1, root_index, *inverse(rest['root'], p), 1.)])
        document['skins'][0]['attachments'][key] = {key: attachment}
        coefficients, covered = transfer(setup['vertices'][slot], np.eye(len(setup['vertices'][slot])),
                                         mesh['triangles'], part['points'])
        if not covered.all():
            raise ValueError('overlap_probe_unmapped_material')
        part['coefficients'] = coefficients
        part['keys'] = []
    # Proximal in front is an explicit diagnostic assumption, not inferred depth.
    document['slots'][at:at+1] = new_slots[::-1]
    times = [0., .233333, .666667, .6981770992279053, .699999988079071,
             .9, .9333335, 1.2000000476837158, 1.8666670322418213]
    records = []
    for time in times:
        pose = sample_active(original, name, time); current = matrices(original, name, time)
        for i, part in enumerate(parts):
            key = part['slot']; points = np.asarray(part['points'])
            bone = ('thigh_' if i==0 else 'calf_')+side
            target = transform(relative(rest[bone], current[bone]), points)
            far_error = None
            if i==1:
                distance = (points-center)@axis
                blend = np.clip((distance-radius)/radius, 0, 1)
                blend = blend*blend*(3-2*blend)
                retained = part['coefficients']@np.asarray(pose['vertices'][slot])
                target = target*(1-blend[:, None])+retained*blend[:, None]
                far_error = float(np.max(np.linalg.norm(target[distance>=2*radius]-retained[distance>=2*radius], axis=1)))
            base = transform(relative(rest['root'], current['root']), points)
            attachment = document['skins'][0]['attachments'][key][key]
            offsets = local_delta(document, entries(attachment), current, base, target)
            part['keys'].append(dict(time=time, vertices=offsets))
            records.append(dict(time=time, slot=key, distal_preservation_error=far_error,
                                **metrics(part['points'], target.tolist(), part['triangles'])))
        print(json.dumps(dict(stage='pose', time=time)), flush=True)
    for part in parts:
        key = part['slot']
        document['animations'][name].setdefault('attachments', {}).setdefault('default', {})[key] = {key: dict(deform=part['keys'])}
    scene['skeleton'] = document; scene['artifact'] = None
    if document['bones'] != original['bones'] or document['animations'][name]['bones'] != original['animations'][name]['bones']:
        raise ValueError('overlap_probe_bones_changed')
    frames = []
    for time in times:
        frame = sample_active(document, name, time)
        before = sample_active(original, name, time)
        for other in before['vertices']:
            if other != slot and (frame['attachments'][other] != before['attachments'][other] or
                                  frame['vertices'][other] != before['vertices'][other]):
                raise ValueError('overlap_probe_unselected_attachment_changed')
        frames.append(dict(time=time, attachments=frame['attachments'], vertices=frame['vertices']))
    report = dict(profile='overlapping-knee-cap-probe-v1', source_sha256=canonical_sha256(original),
                  document_sha256=canonical_sha256(document), times=times, records=records,
                  radius_px=radius, slot=slot, authority='none', selected=False,
                  unselected_attachments_unchanged=True,
                  limitations=['diagnostic_key_poses_only_interpolation_unverified',
                               'proximal_in_front_not_source_depth_inference',
                               'alpha_overlap_and_silhouette_unverified',
                               'distal_preserved_only_at_baked_poses'])
    output.mkdir(parents=True, exist_ok=False)
    for filename, value in [('candidate.json', scene), ('report.json', report),
                            ('active-reference.json', dict(animation=name, frames=frames))]:
        (output/filename).write_text(json.dumps(value, default=lambda v: v.item()), encoding='utf-8')
    print(json.dumps(dict(document=report['document_sha256'], radius=radius,
                         records=len(records), failures=sum(bool(r['bad_triangles']) for r in records))))


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path); parser.add_argument('output', type=Path)
    args = parser.parse_args(); run(args.source, args.output)
