"""Fixed R3-S motion range and combined FK/cloth-key validation."""
from copy import deepcopy
import math
from .cloth_anchor_solver import solve
from .cloth_anchor_correction import interpolate
from .sleeve_helpers import frames
from .component_local_solver import metrics
from .component_distal_guard import gate
from .component_temporal_qa import passed
from ..joints.mesh_weights import _deform,_rotate
from ...resolved_project import canonical_sha256

MOTIONS=(('forearm',(30,0,0)),('hand',(0,30,0)),('cloth',(0,0,10)),
         ('combined_pp',(30,30,10)),('combined_pm',(30,30,-10)),
         ('combined_mp',(30,-30,10)),('combined_mm',(30,-30,-10)))


def angles(amplitudes,tick):
    if not 0<=tick<=128:raise ValueError('sleeve_motion_tick')
    phase=0. if tick in (0,64,128) else math.sin(2*math.pi*tick/128)
    return [amplitude*phase for amplitude in amplitudes]


def track(row,chain,name,amplitudes,*,key_seeds=None):
    drivers=[chain[1]['id'],chain[2]['id'],chain[3]['id']]
    setup=row['setup_vertices'];tri=row['triangles'];weights=row['weights']
    anchors=sorted({v for e in row['interface_root']['edges'] for v in e})
    domain=row.get('correction_domain');free=row['cloth_vertices']
    if domain:anchors=domain['anchors'];free=domain['free_vertices']
    budget=.15*math.dist(chain[1]['head_xy'],chain[1]['tail_xy'])
    keys=[];budget_evidence=[];solver_evidence=[]
    if key_seeds is not None and (len(key_seeds)!=33 or any(len(key)!=len(setup)
            or any(len(p)!=2 or any(not math.isfinite(v) for v in p) for p in key) for key in key_seeds)):
        raise ValueError('sleeve_key_seeds')
    for tick in range(0,129,4):
        base=_deform(weights,frames(chain,dict(zip(drivers,angles(amplitudes,tick)))))
        active_budget=budget
        if domain and domain.get('budget_policy') in ('one-free-area-bound-cap50-v1','area-edge-displacement-bound-cap50-v1'):
            from .sleeve_boundary_budget import estimate
            active_budget,evidence=estimate(setup,tri,base,set(free)-set(anchors),budget,
                include_edges=domain['budget_policy']=='area-edge-displacement-bound-cap50-v1',
                headroom=domain.get('budget_headroom',0.))
            if 'support_mesh' in row:
                coarse=row['support_mesh']['coarse_constraints'];count=len(coarse['vertices_xy'])
                inherited,coarse_evidence=estimate(coarse['vertices_xy'],coarse['triangles'],base[:count],coarse['free_vertices'],budget)
                active_budget=max(active_budget,inherited);evidence.update(budget_px=active_budget,coarse_evidence=coarse_evidence)
            budget_evidence.append(evidence)
        if domain and domain.get('solver_profile')=='joint-area-edge-sparse200-v1':
            from .cloth_joint_solver import solve as solve_joint
            seed=None if key_seeds is None or tick in (0,64,128) else [[p[k]+d[k] for k in (0,1)] for p,d in zip(base,key_seeds[tick//4])]
            corrected,solver_info=solve_joint(setup,tri,base,free,anchors,active_budget,seed=seed);solver_evidence.append(solver_info)
        else:corrected,_=solve(setup,tri,base,free,anchors,active_budget)
        keys.append([[b[k]-a[k] for k in (0,1)] for a,b in zip(base,corrected)])
    before=[];after=[];samples=[];raw_samples=[];anchor_error=0.
    for tick in range(129):
        values=angles(amplitudes,tick);transforms=frames(chain,dict(zip(drivers,values)))
        base=_deform(weights,transforms);delta=interpolate(keys,tick)
        points=[[p[k]+d[k] for k in (0,1)] for p,d in zip(base,delta)]
        before.append(metrics(setup,base,tri));after.append(metrics(setup,points,tri))
        anchor_error=max(anchor_error,max((math.dist(base[i],points[i]) for i in anchors),default=0.))
        if tick%4==0:
            bones=[]
            for b in chain:
                head,rotation=transforms[b['id']];tail=_rotate([math.dist(b['head_xy'],b['tail_xy']),0],rotation)
                bones.append(dict(id=b['id'],head_xy=head,tail_xy=[head[k]+tail[k] for k in (0,1)]))
            sample=dict(angle=values[next(i for i,v in enumerate(amplitudes) if v)],angles=values,bones=bones)
            samples.append(dict(sample,points=points));raw_samples.append(dict(sample,points=base))
    reasons,gain=gate(before,after);selected=not reasons and gain
    qa=after if selected else before
    result=dict(bone_id=name,angle_range=[-max(map(abs,amplitudes)),max(map(abs,amplitudes))],
        drivers=drivers,amplitudes=list(amplitudes),qa=qa,samples=samples if selected else raw_samples,
        failed_ticks=sum(not passed(q) for q in qa),correction_selected=selected,
        reason_codes=reasons or ['sampled_improvement' if selected else 'no_sampled_gain'],
        baseline_failed_ticks=sum(not passed(q) for q in before),trial_failed_ticks=sum(not passed(q) for q in after),
        trial_qa=after,trial_keys=keys,anchor_displacement=anchor_error,
        loop_error=max(math.dist(a,b) for a,b in zip(samples[0]['points'],samples[-1]['points'])))
    if budget_evidence:result['budget_evidence']=budget_evidence
    if solver_evidence:result['solver_evidence']=solver_evidence
    return result


def build(source,skeleton,domains=None):
    if (source.get('schema')!='autospine.cloth-anchor-correction/v1'
            or source.get('skeleton_sha256')!=canonical_sha256(skeleton)
            or source.get('authority')!='none' or source.get('production_authorized') is not False):
        raise ValueError('sleeve_envelope_source_mismatch')
    bones={b['id']:b for b in skeleton['bones']};rows=[]
    for original in source['records']:
        row=deepcopy(original)
        if 'helper' not in row:rows.append(row);continue
        if domains is not None:row['correction_domain']=deepcopy(domains[row['layer_id'],row['component_id']])
        if not row['interface_root']['edges']:
            row.pop('tracks',None);row['status']='blocked';row['reason_codes']=['missing_interface'];rows.append(row);continue
        parent=bones[row['helper']['parent_id']]
        chain=[bones[parent['parent_id']],parent,bones[row['tracks'][1]['bone_id']],row['helper']]
        row['tracks']=[track(row,chain,name,amplitudes) for name,amplitudes in MOTIONS]
        row['motion_envelope']=dict(geometry_pass=all(t['failed_ticks']==0 for t in row['tracks']),
            anchor_displacement=max(t['anchor_displacement'] for t in row['tracks']),
            alpha_contact_status='not_evaluated',combined_sampling='four_sign_pairs_synchronized_sine',
            full_angle_volume_proven=False)
        row['status']='blocked';row['reason_codes']=['runtime_and_alpha_contact_required']
        if row['setup_error']>1e-7:row['reason_codes'].append('setup_reconstruction_failure')
        if row['weight_sum_error']>1e-9:row['reason_codes'].append('weight_sum_failure')
        if any(t['loop_error']>1e-7 or t['anchor_displacement']>1e-7 for t in row['tracks']):
            row['reason_codes'].append('loop_or_anchor_failure')
        if not row['motion_envelope']['geometry_pass']:row['reason_codes'].append('motion_envelope_geometry_failure')
        rows.append(row)
    return dict(schema='autospine.sleeve-motion-envelope/v1',profile='garment-connection-ring1-sine129-v1' if domains is not None else 'forearm30-hand30-cloth10-sine129-v1',
        project_id=source['project_id'],source_sha256=canonical_sha256(source),skeleton_sha256=canonical_sha256(skeleton),
        records=rows,authority='none',production_authorized=False,runtime_status='not_evaluated')
