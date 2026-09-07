"""Two-second diagnostic loop with linear per-influence corrective keys."""
import math
from copy import deepcopy
from ...resolved_project import canonical_sha256
from .elbow_constraints import prepare,solve
from .elbow_constraint_report import local_offsets
from .mesh_weights import _frames,_deform,_area


def angle_at(frame):
    section = frame/15
    if section <= 1:return section*90
    if section <= 3:return 180-section*90
    return section*90-360


def replay(row,bones,first,second,fraction):
    weights = deepcopy(row['weights'])
    for influences,a,b in zip(weights,first['offsets'],second['offsets']):
        for influence,p,q in zip(influences,a,b):
            influence['local_xy'] = [v+x+(y-x)*fraction for v,x,y in zip(influence['local_xy'],p,q)]
    angle = first['angle']+(second['angle']-first['angle'])*fraction
    return _deform(weights,_frames(bones,angle))


def bake_layer(row,bones):
    context = prepare(row,bones)
    frames = [{'angle':angle_at(i),'offsets':local_offsets(context,angle_at(i))} for i in range(61)]
    low,high,edge,error,inversions = float('inf'),-float('inf'),0.,0.,0
    for tick in range(241):
        index,fraction = min(tick//4,59),(tick%4)/4 if tick < 240 else 1.
        points = replay(row,bones,frames[index],frames[index+1],fraction)
        exact = solve(context,angle_at(tick/4))
        error = max(error,max(math.dist(p,q) for p,q in zip(points,exact)))
        ratios = [_area(points,t)/a for t,a in zip(row['triangles'],context['areas'])]
        low,high = min(low,min(ratios)),max(high,max(ratios))
        inversions += sum(r <= 0 for r in ratios)
        edge = max(edge,max(math.dist(points[a],points[b])/length for (a,b),length in zip(context['edges'],context['lengths'])))
    start = replay(row,bones,frames[0],frames[1],0)
    end = replay(row,bones,frames[-2],frames[-1],1)
    loop = max(math.dist(p,q) for p,q in zip(start,end))
    setup = max(math.dist(p,q) for p,q in zip(start,row['vertices_xy']))
    reasons = []
    for failed,reason in ((low < .5,'mesh_area_compression'),(high > 2,'mesh_area_expansion'),
                          (edge > 2,'mesh_edge_stretch'),(inversions > 0,'mesh_triangle_inversion'),
                          (error > .5,'corrective_interpolation_error'),(loop > 1e-7,'loop_mismatch'),
                          (setup > 1e-7,'mesh_setup_mismatch')):
        if failed:reasons.append(reason)
    return {'layer_id':row['layer_id'],'status':'blocked' if reasons else 'passed','reason_codes':reasons,
            'frames':frames,'qa':{'min_area_ratio':low,'max_area_ratio':high,'max_edge_stretch':edge,
            'inverted_triangle_samples':inversions,'max_interpolation_error_px':error,
            'loop_max_error':loop,'setup_max_error':setup}}


def build_bake(mesh,skeleton):
    if mesh.get('profile')!='joint-plane-three-bone-v2':raise ValueError('elbow_bake_requires_joint_plane_profile')
    bones = {b['id']:b for b in skeleton['bones']}
    layers = [bake_layer(row,[bones[w['bone_id']] for w in row['weights'][0]]) if row.get('weights') else
              {'layer_id':row['layer_id'],'status':'not_evaluated','reason_codes':['weighted_mesh_required'],'frames':[],'qa':None}
              for row in mesh['layers']]
    return {'schema':'autospine.elbow-bake/v1','profile':'bounded-elbow-loop-30fps-v1',
            'authority':'none','production_authorized':False,'source_mesh_sha256':canonical_sha256(mesh),
            'source_skeleton_sha256':canonical_sha256(skeleton),'fps':30,'duration':2,
            'interpolation':'linear_local_offsets_and_angle','qa_sample_fps':120,
            'seam_status':'not_evaluated','runtime_status':'not_evaluated','layers':layers}


def validate_bake(mesh,skeleton,document):
    if canonical_sha256(build_bake(mesh,skeleton))!=canonical_sha256(document):raise ValueError('elbow_bake_mismatch')
    return document
