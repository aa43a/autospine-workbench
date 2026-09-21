"""Independent sampled area-proxy checks, including deform interpolation times."""
from copy import deepcopy
from .affine_pose import matrices, sample
from .projected_area_reference import reference
from ..spine43.continuous_pose import area


def inspect(document, name, slots):
    setup=deepcopy(document);setup['animations']={name:{'bones':{}}}
    base=sample(setup,name,0)[0];rest=matrices(setup,name,0)
    animation=document['animations'][name]
    knots={k['time'] for tracks in animation['bones'].values() for keys in tracks.values() for k in keys}
    knots.update(k['time'] for skin in animation.get('attachments',{}).values() for choices in skin.values()
                 for tracks in choices.values() for keys in tracks.values() for k in keys)
    knots=sorted(knots);times=sorted(set(knots)|{(a+b)/2 for a,b in zip(knots,knots[1:])})
    prepared={}
    for slot in slots:
        attachment=document['skins'][0]['attachments'][slot][slot];data=attachment['vertices']
        i=0;influences=[]
        while i<len(data):
            n=data[i];i+=1;influences.append([(data[i+4*j],data[i+4*j+3]) for j in range(n)]);i+=4*n
        flat=attachment['triangles'];triangles=[flat[i:i+3] for i in range(0,len(flat),3)]
        prepared[slot]=(triangles,[area(base[slot],t) for t in triangles],influences)
    failures=[]
    for time in times:
        world=sample(document,name,time)[0];transform=matrices(document,name,time)
        for slot,(triangles,areas,influences) in prepared.items():
            refs=reference(areas,triangles,influences,document['bones'],rest,transform)
            ratios=[area(world[slot],tri)/ref for tri,ref in zip(triangles,refs)]
            if min(ratios)<.5 or max(ratios)>2:
                failures.append(dict(time=time,slot=slot,min_ratio=min(ratios),max_ratio=max(ratios),
                    inversions=sum(v<=0 for v in ratios),at_key=time in knots))
    return dict(profile='projected-area-key-and-midpoint-check-v1',authority='none',
                sampled_frames=len(times),failures=failures,
                limitation='sampled_area_proxy_not_continuous_or_visual_quality_proof')
