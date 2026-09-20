"""Extract verified source vectors in the original declared camera basis."""
import json


def _basis(point,basis):
    return tuple((-1 if basis[k][0]=='-' else 1)*point['XYZ'.index(basis[k][1])]
                 for k in ('screen_x','screen_y','depth'))


def extract(bundle):
    mapping=json.loads((bundle.path/'map.json').read_bytes())
    rows=mapping['bones']; basis=mapping['basis']
    vectors={r['role']:[] for r in rows}; roots=[]
    if bundle.source_kind=='bvh':
        from ...bvh_parser import parse_bvh
        from ...bvh_fk import _world_matrices,_origin,_multiply,_translate
        bvh=parse_bvh(bundle.raw_bvh)
        indices={j.name:i for i,j in enumerate(bvh.joints)}
        for frame in bvh.frames:
            matrices=_world_matrices(bvh,frame)
            roots.append(_basis(_origin(matrices[indices[mapping['root']['joint_name']]]),basis))
            for row in rows:
                index=indices[row['joint_name']]; a=_origin(matrices[index]); aim=row['aim']
                b=(_origin(matrices[indices[aim['joint_name']]]) if aim['kind']=='joint' else
                   _origin(_multiply(matrices[index],_translate(bvh.joints[index].end_site_offset))))
                vectors[row['role']].append(_basis(tuple(y-x for x,y in zip(a,b)),basis))
        reference=mapping['root']['reference_length_source_units']
    elif bundle.source_kind=='kimodo_npz':
        from ...kimodo_npz_reader import decode_kimodo_npz
        from ...kimodo_npz_consistency import validate_kimodo_consistency
        from ...kimodo_soma77 import SOMA77_INDEX_BY_NAME
        source=bundle.kimodo_source
        motion=validate_kimodo_consistency(decode_kimodo_npz(bundle.raw_npz,source),source)
        for frame in motion.positions:
            roots.append(_basis(frame[0],basis))
            for row in rows:
                a,b=(frame[SOMA77_INDEX_BY_NAME[row[k]]] for k in ('joint_name','aim_joint_name'))
                vectors[row['role']].append(_basis(tuple(y-x for x,y in zip(a,b)),basis))
        reference=mapping['root']['reference_length_meters']
    else: raise ValueError('oblique_source_kind_unsupported')
    return vectors,roots,reference
