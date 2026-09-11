"""Bounded mixed-weight area projection; fixed vertices and source weights stay intact."""
from copy import deepcopy
import math
from ...asset.joints.distal_corrective import project
from ..spine43.continuous_pose import world,area,interpolate
from .wave_motion import pose


def repair(document,slots,checkpoint=lambda:None):
    if len(document['animations'])!=1:raise ValueError('character_repair_animation_inventory')
    result=deepcopy(document);animation=next(iter(result['animations'].values()))
    if animation.get('attachments'):raise ValueError('character_repair_existing_deform')
    if any(set(t)!={'rotate'} for t in animation['bones'].values()):raise ValueError('character_repair_motion_unsupported')
    setup=world(document,0);bones=document['bones'];evidence=[]
    for slot in sorted(slots):
        attachment=result['skins'][0]['attachments'][slot][slot];data=attachment['vertices'];influences=[];i=0
        while i<len(data):
            count=data[i];i+=1;entries=[]
            for _ in range(count):
                index,x,y,w=data[i:i+4];i+=4;entries.append((index,w))
            if abs(sum(w for _,w in entries)-1)>1e-6:raise ValueError('character_repair_weight_sum')
            influences.append(entries)
        used={index for entries in influences for index,w in entries if w>0};names={bones[i]['name'] for i in used}
        links=[b for b in bones if b['name'] in names and b.get('parent') in names]
        if len(used)>3 or len(links)!=len(used)-1:raise ValueError('character_repair_chain_unsupported')
        lengths=[math.hypot(b['x'],b['y']) for b in links]
        if not lengths or min(lengths)<1e-8:raise ValueError('character_repair_chain_degenerate')
        budget=.1*min(lengths);points=setup[slot];flat=attachment['triangles'];triangles=[flat[i:i+3] for i in range(0,len(flat),3)]
        edges=sorted({tuple(sorted((t[i],t[(i+1)%3]))) for t in triangles for i in range(3)})
        areas=[area(points,t) for t in triangles]
        free=[sum(w>0 for _,w in entries)>1 for entries in influences]
        context=dict(row={'triangles':triangles},areas=areas,edges=edges,lengths=[math.dist(points[a],points[b]) for a,b in edges],free=free,budget=budget)
        keys=[];maximum=0.;changed=0
        for tick in range(129):
            if tick%16==0:checkpoint()
            time=tick/64;base=world(document,time)[slot]
            ratios=[area(base,t)/a for t,a in zip(triangles,areas)]
            corrected=project(context,base) if min(ratios)<.55 or max(ratios)>1.9 else base
            rotations={n:interpolate(t['rotate'],time,'value') for n,t in animation['bones'].items() if t.get('rotate')}
            transforms=pose(bones,rotations);offsets=[]
            for index,(old,new,entries) in enumerate(zip(base,corrected,influences)):
                distance=math.dist(old,new)
                if distance>budget+1e-7 or (not free[index] and distance>1e-7):raise ValueError('character_repair_budget_exceeded')
                maximum=max(maximum,distance);changed+=distance>1e-8
                dx,dy=new[0]-old[0],new[1]-old[1]
                for bone,_ in entries:
                    angle=math.radians(-transforms[bones[bone]['name']][2])
                    offsets.extend([dx*math.cos(angle)-dy*math.sin(angle),dx*math.sin(angle)+dy*math.cos(angle)])
            keys.append(dict(time=time,vertices=offsets))
        animation.setdefault('attachments',{}).setdefault('default',{})[slot]={slot:{'deform':keys}}
        evidence.append(dict(slot=slot,budget_px=budget,max_displacement_px=maximum,changed_vertex_samples=changed,
                             fixed_vertices=sum(not f for f in free),sample_count=129))
    return result,dict(profile='mixed-weight-area-budget10-v1',authority='none',production_authorized=False,
                       scope='sampled_local_geometry_candidate',records=evidence,contact_status='not_evaluated')
