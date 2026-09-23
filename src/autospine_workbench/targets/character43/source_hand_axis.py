"""Explicit Mixamo wrist-to-middle-knuckle observation, not a inferred palm frame."""
import json
from ...bvh_parser import parse_bvh
from ...bvh_fk import _world_matrices,_origin,bvh_frame_ticks
from .oblique_source import _basis


def extract(bundle):
    if bundle.source_kind=='kimodo_npz':
        from .kimodo_hand_axis import extract as kimodo
        return kimodo(bundle)
    if bundle.source_kind!='bvh':raise ValueError('hand_axis_source_unsupported')
    mapping=json.loads((bundle.path/'map.json').read_bytes())
    if mapping['map_id']!='mixamo-declared-body-v1':raise ValueError('hand_axis_map_unsupported')
    bvh=parse_bvh(bundle.raw_bvh);indices={j.name:i for i,j in enumerate(bvh.joints)}
    roles={r['role']:r for r in mapping['bones']};chains={}
    for side in ('left','right'):
        aim=roles['humanoid.arm.lower.'+side]['aim'];wrist=aim.get('joint_name');expected=side.title()+'Hand'
        if aim['kind']!='joint' or wrist not in (expected,'mixamorig:'+expected):raise ValueError('hand_axis_wrist_undeclared')
        knuckle=wrist+'Middle1'
        if knuckle not in indices or bvh.joints[indices[knuckle]].parent_index!=indices[wrist]:
            raise ValueError('hand_axis_knuckle_missing')
        chains['humanoid.arm.hand.'+side]=(wrist,knuckle)
    vectors={r:[] for r in chains}
    for frame in bvh.frames:
        pose=_world_matrices(bvh,frame)
        for role,(wrist,knuckle) in chains.items():
            a,b=(_origin(pose[indices[n]]) for n in (wrist,knuckle))
            vectors[role].append(_basis(tuple(y-x for x,y in zip(a,b)),mapping['basis']))
    return dict(profile='mixamo-wrist-middle-knuckle-axis-v1-experiment',vectors=vectors,
        times=[t/1e6 for t in bvh_frame_ticks(bvh)],chains=chains,authority='none',
        assumption='target_hand_axis_matches_wrist_middle_knuckle_not_palm_normal')
