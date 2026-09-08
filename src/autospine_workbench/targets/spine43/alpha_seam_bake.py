"""Bounded local displacement around candidate alpha contacts; never adoption."""
from copy import deepcopy
import math
from .alpha_seam import analyze,position
from .continuous_pose import world,inspect,interpolate
from .seam_translation import rotation,rotate,influences


def solve(vertices,anchors,deltas,triangles):
    """40 relaxed projections plus adjacency smoothing, 48px support/12px cap."""
    contact=[position(a,vertices) for a in anchors]
    mobility=[max(0.,1-min(math.dist(p,c) for c in contact)/48)**2 for p in vertices]
    moves=[[0.,0.] for _ in vertices]
    neighbors=[set() for _ in vertices]
    for tri in triangles:
        for i in tri:neighbors[i].update(j for j in tri if j!=i)
    for _ in range(40):
        updates=[[0.,0.] for _ in vertices];counts=[0]*len(vertices)
        for anchor,target in zip(anchors,deltas):
            indices,weights=anchor['triangle'],anchor['barycentric']
            actual=[sum(w*moves[i][k] for i,w in zip(indices,weights)) for k in (0,1)]
            denominator=sum(w*w*mobility[i] for i,w in zip(indices,weights))
            if denominator<1e-12:continue
            for i,w in zip(indices,weights):
                for k in (0,1):updates[i][k]+=.5*w*mobility[i]*(target[k]-actual[k])/denominator
                counts[i]+=1
        for i,move in enumerate(moves):
            if counts[i]:
                for k in (0,1):move[k]+=updates[i][k]/counts[i]
                length=math.hypot(*move)
                if length>12:moves[i]=[x*12/length for x in move]
        smooth=[]
        for i,move in enumerate(moves):
            if not neighbors[i] or mobility[i]==0:smooth.append([0.,0.]);continue
            smooth.append([.5*move[k]+.5*sum(moves[j][k] for j in sorted(neighbors[i]))/len(neighbors[i]) for k in (0,1)])
        moves=smooth
    return moves


def bake(source,files):
    if set(source['animations'])!={'continuous-corrective-inspection'}:raise ValueError('alpha_seam_source_invalid')
    return bake_from_report(source,files,analyze(source,files))


def bake_from_report(source,files,baseline):
    """Shared solver; callers retain their own correspondence evidence."""
    doc=deepcopy(source);animation=next(iter(doc['animations'].values()));setup=world(source,0)
    records=[]
    for relation in baseline['relations']:
        driver,follower=relation['driver'],relation['follower']
        if sum(r['follower']==follower for r in baseline['relations'])!=1:continue
        if baseline['boundaries'][driver]['unmapped_pixels'] or baseline['boundaries'][follower]['unmapped_pixels']:continue
        attachment=doc['skins'][0]['attachments'][follower][follower];bone=next(iter(influences(attachment)))
        if len(attachment['vertices'])!=len(setup[follower])*5:raise ValueError('alpha_seam_follower_invalid')
        anchors=[baseline['boundaries'][follower]['samples'][p['follower_sample']] for p in relation['pairs']]
        keys=[];maximum=0.;rotation0=rotation(source,bone,0)
        for frame in range(61):
            time=frame/30;pose=world(source,time);angle=rotation(source,bone,time);targets=[]
            for pair,anchor in zip(relation['pairs'],anchors):
                a=baseline['boundaries'][driver]['samples'][pair['driver_sample']]
                left0,right0=position(a,setup[driver]),position(anchor,setup[follower])
                rest=rotate([right0[k]-left0[k] for k in (0,1)],angle-rotation0)
                left,right=position(a,pose[driver]),position(anchor,pose[follower])
                targets.append([left[k]+rest[k]-right[k] for k in (0,1)])
            flat=attachment['triangles'];triangles=[flat[i:i+3] for i in range(0,len(flat),3)]
            moves=solve(setup[follower],anchors,targets,triangles) if frame not in (0,60) else [[0.,0.] for _ in setup[follower]]
            maximum=max(maximum,max(math.hypot(*m) for m in moves))
            old=animation['attachments']['default'].get(follower,{}).get(follower,{}).get('deform')
            prior=interpolate(old,time,'vertices') if old else [0.]*(len(moves)*2)
            local=[v for move in moves for v in rotate(move,-angle)]
            keys.append({'time':time,'vertices':[a+b for a,b in zip(prior,local)]})
        animation['attachments']['default'][follower]={follower:{'deform':keys}}
        records.append({'driver':driver,'follower':follower,'max_displacement_px':maximum,'review_status':'pending'})
    doc['animations']={'alpha-seam-inspection':animation}
    after=analyze(doc,files);geometry=inspect(doc)
    passed=all(r['passed'] for r in geometry['regions'].values()) and all(r['status']!='blocked' for r in after['relations'])
    return doc,{'before':baseline,'after':after,'geometry':geometry,'constraints':records,
        'status':'candidate_noop' if not records else ('candidate_requires_review' if passed else 'blocked'),
        'authority':'none','profile':'alpha-barycentric-smoothed-projection-v1','displacement_limit_px':12,'support_radius_px':48}
