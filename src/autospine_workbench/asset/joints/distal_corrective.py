"""Bounded distal-joint projection with replayable per-influence offsets."""
import math
from .mesh_weights import _area,_rotate,_deform
from .partition_mesh_qa import evaluate

ANGLES=(-90,-60,-30,-15,0,15,30,60,90)


def prepare(row,bones):
    if len(bones)!=3:raise ValueError('distal_corrective_chain_invalid')
    evaluate(row['vertices_xy'],row['triangles'],row['weights'],bones)
    free=[0<w[2]['weight']<1 for w in row['weights']]
    edges=sorted({tuple(sorted((a,b))) for t in row['triangles'] for a,b in zip(t,t[1:]+t[:1])})
    return {'row':row,'bones':bones,'free':free,'edges':edges,
            'areas':[_area(row['vertices_xy'],t) for t in row['triangles']],
            'lengths':[math.dist(row['vertices_xy'][a],row['vertices_xy'][b]) for a,b in edges],
            'budget':.1*min(math.dist(b['head_xy'],b['tail_xy']) for b in bones[-2:])}


def project(context,base):
    row=context['row'];points=[p[:] for p in base];free=context['free']
    for _ in range(48):
        for tri,area in zip(row['triangles'],context['areas']):
            ratio=_area(points,tri)/area;target=max(.55,min(1.9,ratio))
            if ratio==target:continue
            a,b,c=[points[i] for i in tri]
            gradients=[[(b[1]-c[1])/2,(c[0]-b[0])/2],[(c[1]-a[1])/2,(a[0]-c[0])/2],[(a[1]-b[1])/2,(b[0]-a[0])/2]]
            denominator=sum(sum(v*v for v in g) for i,g in zip(tri,gradients) if free[i])
            if denominator<=1e-18:continue
            scale=(target-ratio)*area/denominator
            for i,g in zip(tri,gradients):
                if free[i]:
                    for axis in (0,1):points[i][axis]+=scale*g[axis]
        for (a,b),length in zip(context['edges'],context['lengths']):
            delta=[points[b][i]-points[a][i] for i in (0,1)];distance=math.hypot(*delta);count=int(free[a])+int(free[b])
            if not count or distance<=1.9*length:continue
            scale=(distance-1.9*length)/distance/count
            for axis in (0,1):
                if free[a]:points[a][axis]+=scale*delta[axis]
                if free[b]:points[b][axis]-=scale*delta[axis]
        for i,(p,origin) in enumerate(zip(points,base)):
            distance=math.dist(p,origin)
            if free[i] and distance>context['budget']:
                points[i]=[origin[k]+(p[k]-origin[k])*context['budget']/distance for k in (0,1)]
    return points


def sample(context,angle):
    if type(angle) is not int or angle not in ANGLES:raise ValueError('distal_corrective_angle_invalid')
    row,bones=context['row'],context['bones'];pivot=bones[2]['head_xy'];base=[]
    for vertex,weights in zip(row['vertices_xy'],row['weights']):
        t=weights[2]['weight'];offset=[vertex[k]-pivot[k] for k in (0,1)]
        half,full=_rotate(offset,angle/2),_rotate(offset,angle)
        base.append([pivot[k]+(1-t)**2*offset[k]+2*t*(1-t)*half[k]+t*t*full[k] for k in (0,1)])
    points=[v[:] for v in row['vertices_xy']] if angle==0 else project(context,base)
    if not all(math.isfinite(v) for p in points for v in p):raise ValueError('distal_corrective_nonfinite')
    frames={b['id']:(b['head_xy'],b['world_rotation_degrees']+(angle if i==2 else 0)) for i,b in enumerate(bones)}
    lbs=_deform(row['weights'],frames);offsets=[];modified=[]
    for influences,wanted,actual in zip(row['weights'],points,lbs):
        delta=[wanted[k]-actual[k] for k in (0,1)];local=[];changed=[]
        for influence in influences:
            move=_rotate(delta,-frames[influence['bone_id']][1]);local.append(move)
            changed.append({**influence,'local_xy':[influence['local_xy'][k]+move[k] for k in (0,1)]})
        offsets.append(local);modified.append(changed)
    error=max(math.dist(p,q) for p,q in zip(points,_deform(modified,frames)))
    ratios=[_area(points,t)/a for t,a in zip(row['triangles'],context['areas'])]
    inversions=sum(r<=0 for r in ratios)
    stretch=max(math.dist(points[a],points[b])/length for (a,b),length in zip(context['edges'],context['lengths']))
    correction=max(math.dist(p,q) for p,q in zip(points,base))
    fixed_error=max((math.dist(p,q) for i,(p,q) in enumerate(zip(points,base)) if not context['free'][i]),default=0.)
    passed=inversions==0 and min(ratios)>=.5 and max(ratios)<=2 and stretch<=2 and error<=1e-7 and fixed_error<=1e-7 and correction<=context['budget']+1e-7
    return {'angle':angle,'positions':points,'baseline_positions':lbs,'offsets':offsets,'qa':{'passed':passed,'inversions':inversions,
            'min_area_ratio':min(ratios),'max_area_ratio':max(ratios),'max_edge_stretch':stretch,
            'projection_displacement_px':correction,'fixed_vertex_error':fixed_error,'offset_reconstruction_error':error}}
