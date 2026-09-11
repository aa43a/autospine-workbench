"""Finite subframe checks of analytic FK plus linearly interpolated world deltas."""
import math
from statistics import median
from .ordinary_sleeve import angles, MOTIONS, _validate_mesh
from .component_local_solver import metrics
from .component_temporal_qa import passed
from .sleeve_helpers import frames
from ..joints.mesh_weights import _deform

PROFILE = 'analytic-fk-linear-world-delta-substeps4-v1'


def _finite(value):
    return type(value) in (int,float) and math.isfinite(value)


def dense_offsets(keys, vertex_count):
    """Strict sparse key inventory: no sorting, merging or implicit missing keys."""
    if type(vertex_count) is not int or vertex_count < 1 or not isinstance(keys,list) or len(keys)!=129:
        raise ValueError('ordinary_deform_key_inventory')
    dense=[]
    for tick,key in enumerate(keys):
        if (not isinstance(key,dict) or set(key)!={'tick','time','offsets'}
                or type(key['tick']) is not int or key['tick']!=tick
                or not _finite(key['time']) or key['time']!=tick/64
                or not isinstance(key['offsets'],list)):
            raise ValueError('ordinary_deform_key_order')
        row=[[0.,0.] for _ in range(vertex_count)];seen=set()
        for item in key['offsets']:
            if not isinstance(item,dict) or set(item)!={'vertex_id','delta_xy'}:
                raise ValueError('ordinary_deform_offset_invalid')
            i=item['vertex_id'];delta=item['delta_xy']
            if (type(i) is not int or not 0<=i<vertex_count or i in seen
                    or not isinstance(delta,list) or len(delta)!=2 or not all(_finite(v) for v in delta)):
                raise ValueError('ordinary_deform_offset_invalid')
            seen.add(i);row[i]=delta[:]
        dense.append(row)
    return dense


def sample(mesh, chain, track, substeps=4):
    """513 numerical samples do not prove all continuous time or final rendering."""
    if type(substeps) is not int or substeps!=4:
        raise ValueError('ordinary_deform_sampling_profile_invalid')
    _validate_mesh(mesh,chain)
    drivers=[chain[1]['id'],chain[2]['id']]
    motions=dict(MOTIONS)
    if (track.get('drivers')!=drivers or track.get('bone_id') not in motions
            or track.get('amplitudes')!=list(motions[track['bone_id']])):
        raise ValueError('ordinary_deform_sampling_track_invalid')
    count=len(mesh['vertices_xy']);dense=dense_offsets(track['keys'],count)
    qa=[];failed=[];between=[];new=[];deltas=[]
    first=last=None;maximum=0.
    for index in range(513):
        position=index/4;left=min(index//4,127);fraction=position-left
        delta=(dense[index//4] if index%4==0 else
               [[a[k]+(b[k]-a[k])*fraction for k in (0,1)] for a,b in zip(dense[left],dense[left+1])])
        base=_deform(mesh['weights'],frames(chain,dict(zip(drivers,angles(track['amplitudes'],position)))))
        points=[[p[k]+d[k] for k in (0,1)] for p,d in zip(base,delta)]
        if any(not math.isfinite(v) for p in points for v in p):
            raise ValueError('ordinary_deform_sampling_nonfinite')
        report=metrics(mesh['vertices_xy'],points,mesh['triangles']);qa.append(report)
        if not passed(report):
            failed.append(index)
            if index%4:
                between.append(index)
                if passed(metrics(mesh['vertices_xy'],base,mesh['triangles'])):new.append(index)
        deltas.append(delta)
        maximum=max(maximum,max(math.hypot(*d) for d in delta))
        if first is None:first=points
        last=points
    # One cycle has 512 unique subframe positions. Wrap differences include
    # the last-to-first correction velocity change, not just interior keys.
    cycle=deltas[:-1];length=len(cycle)
    step=max(math.dist(cycle[t][v],cycle[(t+1)%length][v]) for t in range(length) for v in range(count))
    second=max(math.hypot(*(cycle[(t+1)%length][v][k]-2*cycle[t][v][k]+cycle[(t-1)%length][v][k]
                           for k in (0,1))) for t in range(length) for v in range(count))
    edges=sorted({tuple(sorted((a,b))) for t in mesh['triangles'] for a,b in zip(t,t[1:]+t[:1])})
    scale=median(math.dist(mesh['vertices_xy'][a],mesh['vertices_xy'][b]) for a,b in edges)
    return dict(profile=PROFILE,substeps=4,sample_count=513,sample_interval_seconds=1/256,
        qa=qa,failed_samples=failed,failed_between_keys=between,new_failed_between_keys=new,
        max_offset_px=maximum,loop_error=max(math.dist(a,b) for a,b in zip(first,last)),
        setup_error=max(math.dist(a,b) for a,b in zip(mesh['vertices_xy'],first)),
        setup_exact=first==mesh['vertices_xy'],loop_exact=first==last,
        max_cyclic_delta_step_px=step,max_cyclic_delta_second_difference_px=second,
        max_cyclic_delta_second_difference_normalized=second/scale,
        median_edge_px=scale,continuous_time_proven=False,runtime_status='not_evaluated')
