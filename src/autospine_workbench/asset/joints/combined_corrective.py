"""Distal then proximal bounded projection, tested as discrete poses only."""
import math
from .distal_corrective import prepare,project,sample as distal_sample
from .mesh_weights import _rotate,_deform,_area

POSES=((0,0),)+tuple((a,b) for a in (-30,0,30,60,90) for b in (-90,-60,-30,-15,0,15,30,60,90) if (a,b)!=(0,0))+((0,0),)


def sample(context,main_angle,distal_angle):
    if (main_angle,distal_angle) not in POSES:raise ValueError('combined_pose_invalid')
    row,bones=context['row'],context['bones'];distal=distal_sample(context,distal_angle)
    pivot=bones[1]['head_xy'];base=[]
    for vertex,weights in zip(distal['positions'],row['weights']):
        t=weights[1]['weight']+weights[2]['weight'];d=[vertex[k]-pivot[k] for k in (0,1)]
        half,full=_rotate(d,main_angle/2),_rotate(d,main_angle)
        base.append([pivot[k]+(1-t)**2*d[k]+2*t*(1-t)*half[k]+t*t*full[k] for k in (0,1)])
    proximal={**context,'free':[0<w[1]['weight']+w[2]['weight']<1 for w in row['weights']],
              'budget':.1*min(math.dist(b['head_xy'],b['tail_xy']) for b in bones[:2])}
    points=project(proximal,base) if main_angle else distal['positions']
    frames={}
    for i,b in enumerate(bones):
        head=b['head_xy'];rotation=b['world_rotation_degrees']
        if i>=1:
            delta=_rotate([head[k]-pivot[k] for k in (0,1)],main_angle)
            head=[pivot[k]+delta[k] for k in (0,1)];rotation+=main_angle
        if i==2:rotation+=distal_angle
        frames[b['id']]=(head,rotation)
    actual=_deform(row['weights'],frames);offsets=[];modified=[]
    for influences,wanted,old in zip(row['weights'],points,actual):
        delta=[wanted[k]-old[k] for k in (0,1)];local=[];changed=[]
        for influence in influences:
            move=_rotate(delta,-frames[influence['bone_id']][1]);local.append(move)
            changed.append({**influence,'local_xy':[influence['local_xy'][k]+move[k] for k in (0,1)]})
        offsets.append(local);modified.append(changed)
    ratios=[_area(points,t)/area for t,area in zip(row['triangles'],context['areas'])]
    stretch=max(math.dist(points[a],points[b])/length for (a,b),length in zip(context['edges'],context['lengths']))
    reconstruction=max(math.dist(a,b) for a,b in zip(points,_deform(modified,frames)))
    displacement=max(math.dist(a,b) for a,b in zip(points,base))
    fixed=max((math.dist(a,b) for i,(a,b) in enumerate(zip(points,base)) if not proximal['free'][i]),default=0.)
    finite=all(math.isfinite(v) for p in points for v in p)
    passed=finite and min(ratios)>=.5 and max(ratios)<=2 and stretch<=2 and reconstruction<=1e-7 and displacement<=proximal['budget']+1e-7 and fixed<=1e-7
    return {'main_angle':main_angle,'distal_angle':distal_angle,'offsets':offsets,
        'qa':{'passed':passed,'min_area_ratio':min(ratios),'max_area_ratio':max(ratios),'inversions':sum(r<=0 for r in ratios),
              'max_edge_stretch':stretch,'offset_reconstruction_error':reconstruction,'main_projection_displacement_px':displacement,
              'main_fixed_vertex_error':fixed,'distal_stage_passed':distal['qa']['passed']}}


def analyze(row,bones):
    context=prepare(row,bones)
    poses=[sample(context,a,b) for a,b in POSES]
    return {'layer_id':row['layer_id'],'weights':row['weights'],'poses':poses,
            'status':'candidate_requires_review' if all(p['qa']['passed'] for p in poses) else 'blocked'}
