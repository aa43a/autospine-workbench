"""Exact-source dense QA for bounded elbow correction; no production authority."""
import math
from ...resolved_project import canonical_sha256
from .elbow_constraints import prepare,solve,ITERATIONS,AREA_BOUNDS,EDGE_LIMIT
from .elbow_alternatives import deform
from .mesh_weights import _area,_rotate,_frames


def local_offsets(context,angle):
    row,bones = context['row'],context['bones']
    target = solve(context,angle)
    base = deform(row['vertices_xy'],row['weights'],bones,angle,'lbs')
    frames = _frames(bones,angle)
    return [[_rotate([p[i]-q[i] for i in (0,1)],-frames[w['bone_id']][1]) for w in weights]
            for p,q,weights in zip(target,base,row['weights'])]


def measure(context):
    row = context['row']
    low,high,edge,offset,locked,inversions = float('inf'),-float('inf'),0.,0.,0.,0
    worst = None
    for angle in range(-90,91):
        points = solve(context,angle)
        base = deform(row['vertices_xy'],row['weights'],context['bones'],angle,'half_angle_auxiliary')
        ratios = [_area(points,t)/a for t,a in zip(row['triangles'],context['areas'])]
        index = min(range(len(ratios)),key=ratios.__getitem__)
        if ratios[index] < low:low,worst = ratios[index],{'angle_degrees':angle,'triangle_index':index}
        high = max(high,max(ratios))
        inversions += sum(r <= 0 for r in ratios)
        edge = max(edge,max(math.dist(points[a],points[b])/length for (a,b),length in zip(context['edges'],context['lengths'])))
        offset = max(offset,max(math.dist(p,q) for p,q in zip(points,base)))
        locked = max(locked,max((math.dist(p,q) for p,q,free in zip(points,base,context['free']) if not free),default=0))
    setup = max(math.dist(p,q) for p,q in zip(solve(context,0),row['vertices_xy']))
    reasons = []
    for failed,reason in ((low < .5,'mesh_area_compression'),(high > 2,'mesh_area_expansion'),
                          (edge > 2,'mesh_edge_stretch'),(inversions > 0,'mesh_triangle_inversion'),
                          (setup > 1e-7,'mesh_setup_mismatch'),(locked > 1e-9,'mesh_locked_vertex_moved'),
                          (offset > context['max_offset']+1e-9,'mesh_correction_budget_exceeded')):
        if failed:reasons.append(reason)
    return {'status':'passed' if not reasons else 'blocked','reason_codes':reasons,
            'min_area_ratio':low,'max_area_ratio':high,'max_edge_stretch':edge,
            'inverted_triangle_samples':inversions,'setup_max_error':setup,
            'locked_max_error':locked,'max_correction_px':offset,'correction_budget_px':context['max_offset'],'worst':worst}


def build_report(mesh,skeleton):
    if mesh.get('profile') != 'joint-plane-three-bone-v2':raise ValueError('elbow_constraints_requires_joint_plane_profile')
    bones = {b['id']:b for b in skeleton['bones']}
    layers = []
    for row in mesh['layers']:
        entry = {'layer_id':row['layer_id'],'status':'not_evaluated','reason_codes':['weighted_mesh_required']}
        if row.get('weights'):
            context = prepare(row,[bones[i['bone_id']] for i in row['weights'][0]])
            entry.update(measure(context))
        layers.append(entry)
    return {'schema':'autospine.elbow-constraint-report/v1','profile':'bounded-area-edge-projection-v1',
            'source_mesh_sha256':canonical_sha256(mesh),'source_skeleton_sha256':canonical_sha256(skeleton),
            'authority':'none','production_authorized':False,'iterations':ITERATIONS,
            'solver_area_bounds':list(AREA_BOUNDS),'solver_edge_limit':EDGE_LIMIT,'probe_range':[-90,90,1],
            'threshold_status':'experimental_uncalibrated','seam_status':'not_evaluated',
            'runtime_status':'not_evaluated','layers':layers}


def validate_report(mesh,skeleton,report):
    if canonical_sha256(build_report(mesh,skeleton)) != canonical_sha256(report):raise ValueError('elbow_constraint_report_mismatch')
    return report
