"""Source skeleton experiments with common shoulder/hip anchors, not skinning."""
import json
import math

from .oblique_source import _basis, extract
from .oblique_motion import project


def source_segments(bundle):
    mapping = json.loads((bundle.path/'map.json').read_bytes())
    vectors, _, _ = extract(bundle)
    rows, basis = mapping['bones'], mapping['basis']
    origins = {row['role']: [] for row in rows}
    if bundle.source_kind == 'bvh':
        from ...bvh_parser import parse_bvh
        from ...bvh_fk import _world_matrices, _origin
        bvh = parse_bvh(bundle.raw_bvh)
        indices = {j.name: i for i, j in enumerate(bvh.joints)}
        for frame in bvh.frames:
            matrices = _world_matrices(bvh, frame)
            for row in rows:
                origins[row['role']].append(_basis(_origin(matrices[indices[row['joint_name']]]), basis))
    elif bundle.source_kind == 'kimodo_npz':
        from ...kimodo_npz_reader import decode_kimodo_npz
        from ...kimodo_npz_consistency import validate_kimodo_consistency
        from ...kimodo_soma77 import SOMA77_INDEX_BY_NAME
        data = validate_kimodo_consistency(decode_kimodo_npz(bundle.raw_npz, bundle.kimodo_source), bundle.kimodo_source)
        for frame in data.positions:
            for row in rows:
                origins[row['role']].append(_basis(frame[SOMA77_INDEX_BY_NAME[row['joint_name']]], basis))
    else:
        raise ValueError('group_pose_source_unsupported')
    return {role: list(zip(origins[role], values)) for role, values in vectors.items()}


def pose(segments, frame, planes):
    allowed = {f'{limb}.{side}' for limb in ('arm', 'leg') for side in ('left', 'right')}
    if set(planes)-allowed or any(yaw not in (0, -90, 90) for yaw in planes.values()):
        raise ValueError('group_pose_planes_invalid')
    result = {}
    for role, values in segments.items():
        origin, vector = values[frame]
        result[role] = dict(start=list(origin[:2]), end=[origin[i]+vector[i] for i in (0, 1)],
                            source_depth=[origin[2], origin[2]+vector[2]])
    for group, yaw in planes.items():
        limb, side = group.split('.')
        roles = [f'humanoid.{limb}.{part}.{side}' for part in ('upper', 'lower')]
        if any(role not in segments for role in roles):
            raise ValueError('group_pose_chain_missing')
        upper_origin, upper_vector = segments[roles[0]][frame]
        lower_origin, _ = segments[roles[1]][frame]
        if math.dist([upper_origin[i]+upper_vector[i] for i in range(3)], lower_origin) > 1e-6:
            raise ValueError('group_pose_source_chain_disconnected')
        anchor = list(upper_origin[:2])
        for role in roles:
            _, vector = segments[role][frame]
            projected = project(vector, yaw)
            end = [anchor[i]+projected[i] for i in (0, 1)]
            result[role].update(start=anchor, end=end)
            anchor = end
        # Distal hand/foot segments follow the moved endpoint, in the same plane.
        distal = f'humanoid.{limb}.{"hand" if limb == "arm" else "foot"}.{side}'
        if distal in segments:
            projected = project(segments[distal][frame][1], yaw)
            result[distal].update(start=anchor, end=[anchor[i]+projected[i] for i in (0, 1)])
    return result
