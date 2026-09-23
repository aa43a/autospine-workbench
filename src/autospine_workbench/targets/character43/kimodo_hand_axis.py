"""Verified SOMA77 wrist-to-knuckle axes; never inferred palm surface frames."""
import json
import math
from ...kimodo_npz_reader import decode_kimodo_npz
from ...kimodo_npz_consistency import validate_kimodo_consistency
from ...kimodo_npz_map_validation import require_kimodo_npz_map
from ...kimodo_npz_projection import kimodo_frame_ticks
from ...kimodo_soma77 import SOMA77_INDEX_BY_NAME
from .oblique_source import _basis


def extract(bundle):
    if bundle.source_kind!='kimodo_npz':raise ValueError('hand_axis_source_unsupported')
    mapping=json.loads((bundle.path/'map.json').read_bytes());source=bundle.kimodo_source
    require_kimodo_npz_map(mapping,source=source)
    motion=validate_kimodo_consistency(decode_kimodo_npz(bundle.raw_npz,source),source)
    roles={r['role']:r for r in mapping['bones']};chains={};vectors={}
    for side in ('left','right'):
        wrist=side.title()+'Hand';knuckle=wrist+'Middle1'
        if roles.get('humanoid.arm.lower.'+side,{}).get('aim_joint_name')!=wrist:
            raise ValueError('hand_axis_wrist_undeclared')
        role='humanoid.arm.hand.'+side;chains[role]=(wrist,knuckle);vectors[role]=[]
        for frame in motion.positions:
            a,b=(frame[SOMA77_INDEX_BY_NAME[n]] for n in (wrist,knuckle))
            vector=_basis(tuple(y-x for x,y in zip(a,b)),mapping['basis'])
            if not all(math.isfinite(v) for v in vector) or math.hypot(*vector)<=1e-10:
                raise ValueError('hand_axis_degenerate_observation')
            vectors[role].append(vector)
    return dict(profile='soma77-wrist-middle-knuckle-axis-v1-experiment',vectors=vectors,
        times=[t/1e6 for t in kimodo_frame_ticks(source)],chains=chains,authority='none',selected=False,
        identity=dict(raw_npz_sha256=motion.raw_npz_sha256,source_sha256=motion.source_sha256,
                      array_inventory_sha256=motion.array_inventory_sha256),
        assumption='target_hand_axis_matches_wrist_middle_knuckle_not_palm_normal')
