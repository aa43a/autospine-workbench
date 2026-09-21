"""Independent sampled area-proxy checks, including deform interpolation times."""
from copy import deepcopy
from .affine_pose import matrices, sample
from .projected_area_reference import reference
from ..spine43.continuous_pose import area


def inspect(document, name, slots, *, preservation_source=None, repair_support=None):
    if repair_support is not None and preservation_source is None:raise ValueError('repair_support_requires_source')
    if preservation_source is not None:
        if (preservation_source['bones'] != document['bones'] or preservation_source['skins'] != document['skins']
                or preservation_source['animations'][name]['bones'] != document['animations'][name]['bones']
                or preservation_source['animations'][name].get('attachments')):
            raise ValueError('area_preservation_source_mismatch')
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
        original=sample(preservation_source,name,time)[0] if preservation_source is not None else None
        for slot,(triangles,areas,influences) in prepared.items():
            refs=reference(areas,triangles,influences,document['bones'],rest,transform)
            ratios=[area(world[slot],tri)/ref for tri,ref in zip(triangles,refs)]
            deficits=[]
            if original is not None:
                # Independent of solver floor generation, including interpolated poses.
                floors=[max(.5,min(1.,area(original[slot],tri)/ref)) for tri,ref in zip(triangles,refs)]
                if repair_support is not None:
                    seeds=[tri for tri,ref in zip(triangles,refs) if not .5<=area(original[slot],tri)/ref<=2]
                    vertices={v for tri in seeds for v in tri}|set(repair_support[slot])
                    floors=[.5 if vertices.intersection(tri) else f for tri,f in zip(triangles,floors)]
                deficits=[dict(triangle=i,ratio=r,minimum=f) for i,(r,f) in enumerate(zip(ratios,floors)) if r<f-1e-7]
            if min(ratios)<.5 or max(ratios)>2 or deficits:
                failures.append(dict(time=time,slot=slot,min_ratio=min(ratios),max_ratio=max(ratios),
                    inversions=sum(v<=0 for v in ratios),at_key=time in knots))
                if original is not None:failures[-1]['preservation_failures']=deficits
    profile='healthy-area-key-and-midpoint-check-v1-experiment' if preservation_source is not None else 'projected-area-key-and-midpoint-check-v1'
    if repair_support is not None:profile='repair-band-key-and-midpoint-check-v1-experiment'
    return dict(profile=profile,authority='none',
                sampled_frames=len(times),failures=failures,
                limitation='sampled_area_proxy_not_continuous_or_visual_quality_proof')
