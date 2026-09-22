"""Bounded per-triangle ordinary clipping experiment; never an adoption decision."""
import argparse
from copy import deepcopy
from pathlib import Path
import numpy as np
from autospine_workbench.targets.character43.depth_partition_compact import compact
from m4_halfplane_clips import rectangles


def build(document, report, arm, body):
    candidate = deepcopy(document)
    if report.get('side') != 'front' or report['arm'] != arm:
        raise ValueError('triangle_clip_field_identity')
    if len(candidate['skins']) != 1 or candidate['skins'][0]['name'] != 'default':
        raise ValueError('triangle_clip_skin')
    for animation in candidate['animations'].values():
        if animation.get('drawOrder') or arm in animation.get('slots', {}):
            raise ValueError('triangle_clip_existing_timeline')
    slots = {slot['name']: slot for slot in candidate['slots']}
    if arm not in slots or body not in slots or list(slots).index(arm) >= list(slots).index(body):
        raise ValueError('triangle_clip_slot_order')
    if any(name.startswith('m4-tri-') for name in slots):
        raise ValueError('triangle_clip_collision')
    attachments = candidate['skins'][0]['attachments']
    original = slots[arm]
    mesh = attachments[arm][original['attachment']]
    if mesh.get('type') != 'mesh':
        raise ValueError('triangle_clip_mesh')
    triangles = np.asarray(mesh['triangles']).reshape(-1, 3)
    rows = report['rows']; times = [r['time'] for r in rows]
    if not times or times[0] != 0 or not np.isfinite(times).all() or np.any(np.diff(times) <= 0):
        raise ValueError('triangle_clip_times')
    values = np.asarray([r['depth_values'] for r in rows], dtype=float)
    points = np.asarray([r['vertices'] for r in rows], dtype=float)
    count = len(mesh['uvs']) // 2
    if values.shape != (len(rows), count) or points.shape != (len(rows), count, 2):
        raise ValueError('triangle_clip_field_shape')
    if not np.isfinite(values).all() or not np.isfinite(points).all():
        raise ValueError('triangle_clip_nonfinite')
    front = (values[:, triangles] >= 0).all(axis=(0, 2))
    back = (values[:, triangles] < 0).all(axis=(0, 2))
    dynamic = np.flatnonzero(~(front | back))
    if len(dynamic) > 128:
        raise ValueError('triangle_clip_dynamic_budget')
    bone = 'm4-tri-world'
    if any(b['name'] == bone for b in candidate['bones']):
        raise ValueError('triangle_clip_bone_collision')
    candidate['bones'].append(dict(name=bone, x=0, y=0, rotation=0))
    output = dict(front=[], back=[]); regions = []

    def part(name, indices, side, clips=None):
        copied = dict(deepcopy(mesh), path=mesh.get('path', original['attachment']),
                      triangles=indices.flatten().tolist())
        for key in ('hull', 'edges'): copied.pop(key, None)
        attachments[name] = {name: copied}; regions.append(dict(slot=name))
        for animation in candidate['animations'].values():
            tracks = animation.setdefault('attachments', {}).setdefault('default', {})
            if arm in tracks:
                tracks[name] = {name: deepcopy(tracks[arm][original['attachment']])}
        if clips is not None:
            clip = name + '-clip'; setup = np.asarray(clips[0]).flatten()
            attachments[clip] = {clip: dict(type='clipping', end=name, vertexCount=4,
                                          vertices=setup.tolist(), inverse=False)}
            tracks = candidate['animations']['external-motion']['attachments']['default']
            tracks[clip] = {clip: dict(deform=[dict(time=time, vertices=(np.asarray(q).flatten()-setup).tolist())
                                             for time, q in zip(times, clips)])}
            output[side].append(dict(name=clip, bone=bone, attachment=clip))
        output[side].append(dict(original, name=name, attachment=name))

    for side, selected in [('front', front), ('back', back)]:
        if selected.any(): part('m4-tri-'+side+'-static', triangles[selected], side)
    for index in dynamic:
        tri = triangles[index]
        quads = [rectangles(p[tri], v[tri]) for p, v in zip(points, values)]
        for side in ('back', 'front'):
            part(f'm4-tri-{side}-{index:04d}', triangles[index:index+1], side, [q[side] for q in quads])
    candidate['slots'] = []
    for slot in document['slots']:
        candidate['slots'].extend(output['back'] if slot['name'] == arm else [deepcopy(slot)])
        if slot['name'] == body: candidate['slots'].extend(output['front'])
    del attachments[arm]
    for animation in candidate['animations'].values():
        animation.get('attachments', {}).get('default', {}).pop(arm, None)
    candidate, _ = compact(candidate, dict(regions=regions))
    return candidate


if __name__ == '__main__':
    from m4_clip_candidate import run
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'field', 'output'): parser.add_argument(name, type=Path)
    parser.add_argument('--arm', required=True); parser.add_argument('--body', required=True)
    args = parser.parse_args()
    run(args.source, args.field, args.output, args.arm, args.body, candidate_builder=build)
