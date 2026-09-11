"""Independent target interpolation fidelity and geometry at 513 fixed times."""
from copy import deepcopy
import math
from statistics import median
from ...asset.planning.ordinary_deform_sampling import dense_offsets
from ...asset.planning.ordinary_sleeve import angles
from ...asset.planning.sleeve_helpers import frames
from ...asset.planning.component_local_solver import metrics
from ...asset.planning.component_temporal_qa import passed
from ...asset.joints.mesh_weights import _deform
from .continuous_pose import world

PROFILE = 'linear129-local-deform-quarter513-edge-percent1-v1'


def inspect(doc, row, skeleton):
    lookup = {b['id']:b for b in skeleton['bones']}; chain = [lookup[b] for b in row['bone_ids']]
    name = row['layer_id']+'-'+row['component_id']; count = len(row['weights'])
    if set(doc['animations'])!={t['bone_id'] for t in row['tracks']}:
        raise ValueError('ordinary_target_animation_inventory')
    influence_size = 2*sum(len(entries) for entries in row['weights'])
    for track in row['tracks']:
        animation = doc['animations'][track['bone_id']]
        keys = animation['attachments']['default'][name][name]['deform']
        if len(keys)!=129: raise ValueError('ordinary_target_key_inventory')
        for tick,key in enumerate(keys):
            if (set(key)!={'time','vertices'} or key['time']!=tick/64
                    or len(key['vertices'])!=influence_size
                    or any(type(v) not in (int,float) or not math.isfinite(v) for v in key['vertices'])):
                raise ValueError('ordinary_target_deform_inventory')
    edges = {tuple(sorted((a,b))) for t in row['triangles'] for a,b in zip(t,t[1:]+t[:1])}
    scale = median(math.dist(row['setup_vertices'][a],row['setup_vertices'][b]) for a,b in edges)
    checks = []
    for track in row['tracks']:
        probe = deepcopy(doc); probe['animations'] = {track['bone_id']:doc['animations'][track['bone_id']]}
        dense = dense_offsets(track['keys'],count); errors = []; encoding = []; failures = []
        first = last = None
        for index in range(513):
            tick = index/4; left = min(index//4,127); fraction = tick-left
            actual = [[x,-y] for x,y in world(probe,tick/64)[name]]
            if len(actual)!=count or any(not math.isfinite(v) for p in actual for v in p):
                raise ValueError('ordinary_target_vertex_inventory')
            delta = [[a[k]+(b[k]-a[k])*fraction for k in (0,1)] for a,b in zip(dense[left],dense[left+1])]
            analytic = angles(track['amplitudes'],tick)
            a,b = angles(track['amplitudes'],left),angles(track['amplitudes'],left+1)
            linear = [x+(y-x)*fraction for x,y in zip(a,b)]
            for values,result in ((analytic,errors),(linear,encoding)):
                base = _deform(row['weights'],frames(chain,dict(zip(track['drivers'],values))))
                expected = [[p[k]+d[k] for k in (0,1)] for p,d in zip(base,delta)]
                result.append(max(math.dist(p,q) for p,q in zip(actual,expected)))
            if not passed(metrics(row['setup_vertices'],actual,row['triangles'])): failures.append(index)
            if first is None: first=actual
            last=actual
        key_error = max(errors[::4]); between = max(e for i,e in enumerate(errors) if i%4)
        setup = max(math.dist(p,q) for p,q in zip(first,row['setup_vertices']))
        loop = max(math.dist(p,q) for p,q in zip(first,last))
        reasons = []
        if failures: reasons.append('target_geometry_failure')
        if key_error>1e-7 or setup>1e-7: reasons.append('target_key_reconstruction_failure')
        if between>scale*.01: reasons.append('target_interpolation_fidelity_failure')
        if loop>1e-7: reasons.append('target_loop_failure')
        checks.append(dict(bone_id=track['bone_id'],sample_count=513,failed_samples=failures,
            key_error_px=key_error,between_key_error_px=between,local_encoding_error_px=max(encoding),
            setup_error_px=setup,loop_error_px=loop,passed=not reasons,reason_codes=reasons))
    return dict(profile=PROFILE,median_edge_px=scale,between_key_tolerance_px=scale*.01,
                key_tolerance_px=1e-7,checks=checks,passed=all(t['passed'] for t in checks))
