"""Merge consecutive compatible traces without changing triangle draw order."""
from hashlib import sha256
from .depth_partition_trace import labels


def merge(a,b):
    if len(a)!=len(b) or any(c not in 'FBMAUN' for c in a+b):
        raise ValueError('depth_coalesce_signature')
    output=[]
    for left,right in zip(a,b):
        if left==right:output.append(left)
        elif left=='N':output.append(right)
        elif right=='N':output.append(left)
        else:return None
    return ''.join(output)


def coalesced_labels(triangle_count,samples):
    original,trace=labels(triangle_count,samples)
    signatures=[trace['groups'][name] for name in original]
    runs=[]
    for index,signature in enumerate(signatures):
        combined=merge(runs[-1]['signature'],signature) if runs else None
        if combined is None:runs.append(dict(start=index,end=index+1,signature=signature))
        else:runs[-1].update(end=index+1,signature=combined)
    result=[];groups={}
    for run in runs:
        name='depth-'+sha256(run['signature'].encode()).hexdigest()
        result.extend([name]*(run['end']-run['start']));groups[name]=run['signature']
    return result,dict(trace,profile='consecutive-compatible-depth-signatures-v1',groups=groups,
        source_signature_sha256=sha256('\n'.join(signatures).encode()).hexdigest(),
        original_runs=1+sum(a!=b for a,b in zip(original,original[1:])),coalesced_runs=len(runs),
        rule='only_no_sampled_overlap_is_wildcard_unknown_margin_and_mixed_remain_explicit',
        scope='sampled_compatible_render_groups_not_continuous_order_or_visual_acceptance')
