"""Probe tracks shared by viewer and temporal diagnostics."""
from ..joints.mesh_weights import _rotate, _deform


def _poses(mesh, skeleton):
    bones = {b['id']: b for b in skeleton['bones']}
    chain = [bones[b] for b in mesh['bone_ids']]
    result = []
    for probe in mesh['qa']['probes']:
        name, angle = probe['id'].rsplit('_', 1)
        index = mesh['bone_ids'].index(name); pivot = chain[index]['head_xy']
        frames = {}
        for i, bone in enumerate(chain):
            head, rotation = bone['head_xy'], bone['world_rotation_degrees']
            if i >= index:
                delta = _rotate([head[k]-pivot[k] for k in (0,1)], float(angle))
                head = [pivot[k]+delta[k] for k in (0,1)]; rotation += float(angle)
            frames[bone['id']] = head, rotation
        moved = _deform(mesh['weights'], frames)
        result.append(dict(id=probe['id'], points=moved, qa=probe))
    return result


def tracks(mesh, skeleton, corrected=None):
    poses = _poses(mesh, skeleton)
    overrides = {p['id'].removeprefix('试验 '): p['points'] for p in corrected or []}
    result = []
    for bone in mesh['bone_ids']:
        group = [p for p in poses if p['id'].rsplit('_',1)[0] == bone]
        group.sort(key=lambda p: float(p['id'].rsplit('_',1)[1]))
        result.append(dict(bone_id=bone, ids=[p['id'] for p in group],
                           angles=[float(p['id'].rsplit('_',1)[1]) for p in group],
                           original=[p['points'] for p in group],
                           corrected=[overrides.get(p['id'],p['points']) for p in group]))
    return result
