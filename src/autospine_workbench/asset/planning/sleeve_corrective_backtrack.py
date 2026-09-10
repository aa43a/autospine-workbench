"""Finite corrective-key line search, replayed through the existing dense gate."""
from copy import deepcopy
import math
from .cloth_anchor_correction import interpolate
from .component_distal_guard import gate
from .component_local_solver import metrics
from .component_temporal_qa import passed
from .sleeve_motion_envelope import angles
from .sleeve_helpers import frames
from ..joints.mesh_weights import _deform


def backtrack(row,chain,old,trial):
    if old['drivers']!=trial['drivers'] or old['amplitudes']!=trial['amplitudes']:
        raise ValueError('sleeve_backtrack_motion')
    count=len(row['setup_vertices'])
    previous=old['trial_keys'] if old['correction_selected'] else [[[0.,0.] for _ in range(count)] for _ in range(33)]
    proposed=trial['trial_keys']
    for keys in (previous,proposed):
        if len(keys)!=33 or any(len(key)!=count or any(len(p)!=2 or any(not math.isfinite(v) for v in p) for p in key) for key in keys):
            raise ValueError('sleeve_backtrack_keys')
    bases=[_deform(row['weights'],frames(chain,dict(zip(old['drivers'],angles(old['amplitudes'],tick))))) for tick in range(129)]
    anchors=row['correction_domain']['anchors']
    evidence=[]
    for fraction in (.5,.25,.125):
        keys=[[[a[k]+fraction*(b[k]-a[k]) for k in (0,1)] for a,b in zip(left,right)] for left,right in zip(previous,proposed)]
        qa=[];samples=[];anchor_error=0.
        for tick,base in enumerate(bases):
            delta=interpolate(keys,tick)
            points=[[p[k]+d[k] for k in (0,1)] for p,d in zip(base,delta)]
            qa.append(metrics(row['setup_vertices'],points,row['triangles']))
            anchor_error=max(anchor_error,max((math.dist(base[v],points[v]) for v in anchors),default=0.))
            if tick%4==0:samples.append(dict(old['samples'][tick//4],points=points))
        reasons,gain=gate(old['qa'],qa)
        if anchor_error>1e-7:reasons.append('anchor_displacement')
        setup_error=max(math.dist(p,q) for i in (0,16,32) for p,q in zip(samples[i]['points'],row['setup_vertices']))
        if setup_error>1e-7:reasons.append('setup_displacement')
        failed=sum(not passed(q) for q in qa)
        evidence.append(dict(fraction=fraction,failed_ticks=failed,reason_codes=reasons,improved=gain))
        if reasons or not gain:continue
        result=deepcopy(old)
        result.update(qa=qa,samples=samples,failed_ticks=failed,correction_selected=True,
            trial_qa=qa,trial_keys=keys,trial_failed_ticks=failed,baseline_failed_ticks=old['failed_ticks'],
            reason_codes=['backtracked_nonregression'],anchor_displacement=anchor_error,
            loop_error=max(math.dist(p,q) for p,q in zip(samples[0]['points'],samples[-1]['points'])))
        # Per-key solver receipts from the old track do not describe blended keys.
        result.pop('solver_evidence',None);result.pop('budget_evidence',None)
        result['backtrack']=dict(fraction=fraction,attempts=deepcopy(evidence),budget_rule='convex_combination_of_source_offsets')
        return result,evidence
    return old,evidence
