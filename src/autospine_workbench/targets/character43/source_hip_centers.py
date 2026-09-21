"""Hip-center observations in the verified source's declared camera basis."""
import json
from .oblique_source import _basis


def extract(bundle):
    mapping=json.loads((bundle.path/'map.json').read_bytes())
    roles={r['role']:r['joint_name'] for r in mapping['bones']}
    names=[roles['humanoid.leg.upper.'+s] for s in ('left','right')]
    if bundle.source_kind=='bvh':
        from ...bvh_parser import parse_bvh
        from ...bvh_fk import _world_matrices,_origin
        source=parse_bvh(bundle.raw_bvh);lookup={j.name:i for i,j in enumerate(source.joints)}
        points=[]
        for frame in source.frames:
            pose=_world_matrices(source,frame)
            points.append([_origin(pose[lookup[n]]) for n in names])
        reference=mapping['root']['reference_length_source_units']
    elif bundle.source_kind=='kimodo_npz':
        from ...kimodo_npz_reader import decode_kimodo_npz
        from ...kimodo_npz_consistency import validate_kimodo_consistency
        from ...kimodo_soma77 import SOMA77_INDEX_BY_NAME
        source=validate_kimodo_consistency(decode_kimodo_npz(bundle.raw_npz,bundle.kimodo_source),bundle.kimodo_source)
        points=[[frame[SOMA77_INDEX_BY_NAME[n]] for n in names] for frame in source.positions]
        reference=mapping['root']['reference_length_meters']
    else:raise ValueError('source_hip_kind_unsupported')
    return [_basis(tuple((a+b)/2 for a,b in zip(*pair)),mapping['basis']) for pair in points],reference
