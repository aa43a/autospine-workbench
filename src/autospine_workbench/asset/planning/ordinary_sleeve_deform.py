"""Source-bound sampled world-space corrective candidates, never target admission."""
from copy import deepcopy
import math
from statistics import median
from .ordinary_sleeve_repair_validation import validate as validate_repair
from .ordinary_sleeve import angles
from .ordinary_local_deform import solve
from .component_distal_guard import inventory
from .component_local_solver import metrics
from .component_temporal_qa import passed
from .sleeve_helpers import frames
from ..joints.mesh_weights import _deform
from ...resolved_project import canonical_sha256

SCHEMA = 'autospine.ordinary-sleeve-deform/v1'
PROFILE = 'ordinary-world-delta129-budget-half-median-edge-projection48-v1'


def _protected(mesh, assignments):
    roles = [set() for _ in mesh['vertices_xy']]
    for triangle, item in zip(mesh['triangles'], assignments):
        for i in triangle: roles[i].add(item['role'])
    return [i for i,r in enumerate(roles) if not r or not r <= {'sleeve','cuff'}]


def _track(mesh, chain, base, assignments, budget):
    keys, qa, before, deltas = [], [], [], []
    protected = _protected(mesh, assignments)
    first = last = None
    frozen_ok = protected_ok = True
    maximum = 0.; corrected = 0
    for tick in range(129):
        values = angles(base['amplitudes'],tick)
        points = _deform(mesh['weights'],frames(chain,dict(zip(base['drivers'],values))))
        old = metrics(mesh['vertices_xy'],points,mesh['triangles'])
        # Previously passing samples and exact sine setup keys are immutable.
        selected = points if passed(old) or tick in (0,64,128) else solve(mesh,points,assignments,budget)['points']
        report = metrics(mesh['vertices_xy'],selected,mesh['triangles'])
        before.append(old); qa.append(report)
        offsets = [[q[k]-p[k] for k in (0,1)] for p,q in zip(points,selected)]
        sparse = [dict(vertex_id=i,delta_xy=d) for i,d in enumerate(offsets) if d != [0.,0.]]
        keys.append(dict(tick=tick,time=tick/64,offsets=sparse));deltas.append(offsets)
        maximum = max(maximum,max(math.hypot(*d) for d in offsets))
        corrected += bool(sparse)
        frozen_ok &= not passed(old) or selected == points
        protected_ok &= all(selected[i] == points[i] for i in protected)
        if first is None: first=selected
        last=selected
    adjacent = max(math.dist(a,b) for left,right in zip(deltas,deltas[1:]) for a,b in zip(left,right))
    second = max(math.hypot(*(deltas[t+1][v][k]-2*deltas[t][v][k]+deltas[t-1][v][k] for k in (0,1)))
                 for t in range(1,128) for v in range(len(mesh['vertices_xy'])))
    return dict(bone_id=base['bone_id'],drivers=base['drivers'][:],amplitudes=base['amplitudes'][:],
        keys=keys,before_qa=before,qa=qa,failed_ticks=sum(not passed(q) for q in qa),
        corrected_ticks=corrected,max_offset_px=maximum,max_adjacent_delta_px=adjacent,
        max_second_difference_px=second,loop_error=max(math.dist(a,b) for a,b in zip(first,last)),
        setup_error=max(math.dist(a,b) for a,b in zip(mesh['vertices_xy'],first)),
        setup_exact=first==mesh['vertices_xy'],loop_exact=first==last,
        previously_passed_preserved=frozen_ok,protected_vertices_preserved=protected_ok)


def build(repair, source, draft, skeleton):
    """Validate full repair closure before constructing any pose-only correction."""
    validate_repair(repair,skeleton,source=source,draft=draft)
    labels=inventory(draft['records']);bones={b['id']:b for b in skeleton['bones']}
    records=[]
    for item in repair['records']:
        selected=item['selected_row'];key=(item['layer_id'],item['component_id'])
        row=dict(layer_id=key[0],component_id=key[1],status='blocked',reason_codes=[],tracks=[])
        records.append(row)
        if not selected.get('tracks'):
            row['reason_codes']=selected['reason_codes'][:];continue
        mesh=dict(vertices_xy=deepcopy(selected['setup_vertices']),triangles=deepcopy(selected['triangles']),
                  weights=deepcopy(selected['weights']),bone_ids=selected['bone_ids'][:])
        edges=sorted({tuple(sorted((a,b))) for t in mesh['triangles'] for a,b in zip(t,t[1:]+t[:1])})
        budget=.5*median(math.dist(mesh['vertices_xy'][a],mesh['vertices_xy'][b]) for a,b in edges)
        chain=[bones[b] for b in mesh['bone_ids']]
        tracks=[_track(mesh,chain,t,labels[key]['assignments'],budget) for t in selected['tracks']]
        reasons=[]
        if 'ownership_review_required' in selected['reason_codes']:reasons.append('ownership_review_required')
        if any(t['failed_ticks'] for t in tracks):reasons.append('motion_envelope_geometry_failure')
        if any(t['setup_error']>1e-7 for t in tracks):reasons.append('setup_reconstruction_failure')
        if any(not t['loop_exact'] for t in tracks):reasons.append('loop_failure')
        if any(not t['previously_passed_preserved'] or not t['protected_vertices_preserved'] for t in tracks):
            reasons.append('protected_pose_or_vertex_changed')
        row.update(bone_ids=mesh['bone_ids'],setup_vertices=mesh['vertices_xy'],triangles=mesh['triangles'],
                   weights=mesh['weights'],budget_px=budget,tracks=tracks,
                   status='blocked' if reasons else 'candidate_requires_review',
                   reason_codes=reasons or ['continuous_interpolation_required','runtime_required'])
    return dict(schema=SCHEMA,profile=PROFILE,project_id=repair['project_id'],
        repair_sha256=canonical_sha256(repair),source_sha256=canonical_sha256(source),
        draft_sha256=canonical_sha256(draft),skeleton_sha256=canonical_sha256(skeleton),
        records=records,delta_space='canvas-world-xy-top-left-y-down',authority='none',production_authorized=False,
        continuous_interpolation_status='not_evaluated',runtime_status='not_evaluated')
