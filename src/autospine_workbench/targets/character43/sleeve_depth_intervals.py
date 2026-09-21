"""Explicit helper-plane contributions mixed with unchanged skeletal intervals."""
import math
from .weighted_depth_interval import build as body_intervals

PROFILE='mixed-skeletal-and-sleeve-plane-depth-v1-experiment'


def mix(document,mesh,segments,helpers,planes,transforms,*,axis_lengths=None,offsets=()):
    base=body_intervals(document,mesh,segments,axis_lengths=axis_lengths)
    data=mesh['vertices'];cursor=offset=0;rows=[];body=[]
    while cursor<len(data):
        count=data[cursor];cursor+=1;weights=[];cloth=[]
        for _ in range(count):
            index,x,y,w=data[cursor:cursor+4];cursor+=4
            name=document['bones'][index]['name']
            if offsets:
                if offset+2>len(offsets):raise ValueError('sleeve_depth_deform_length')
                ox,oy=offsets[offset:offset+2]
            else:ox=oy=0
            offset+=2
            if w<=0:continue
            if name in helpers:cloth.append((name,x+ox,y+oy,w))
            else:weights.append((index,x,y,w))
        total=sum(v[3] for v in weights);rows.append((total,cloth))
        if total>0:
            body.append(len(weights))
            for i,x,y,w in weights:body.extend((i,x,y,w/total))
        else:body.extend((1,0,0,0,1))  # Ignored for all-helper vertices.
    if offsets and len(offsets)!=offset:raise ValueError('sleeve_depth_deform_length')
    skeletal=body_intervals(document,dict(mesh,vertices=body),segments,axis_lengths=axis_lengths)
    values=list(base['intervals']);recovered=[]
    for vertex,(total,cloth) in enumerate(rows):
        if not cloth:continue
        # Never repair invalid normalization or an unknown non-helper influence.
        if abs(total+sum(v[3] for v in cloth)-1)>1e-6 or (total>0 and skeletal['intervals'][vertex] is None):
            values[vertex]=None;continue
        bounds=[v*total for v in skeletal['intervals'][vertex]] if total>0 else [0.,0.]
        valid=True
        for name,x,y,w in cloth:
            plane=planes.get(name)
            if plane is None:valid=False;break
            a,b,c,d,tx,ty=transforms[name];dx,dy,z0=plane['coefficients']
            z=dx*(tx+a*x+b*y)+dy*(ty+c*x+d*y)+z0
            if not math.isfinite(z):raise ValueError('sleeve_depth_nonfinite')
            bounds=[v+w*z for v in bounds]
        values[vertex]=bounds if valid else None
        if valid and base['intervals'][vertex] is None:recovered.append(vertex)
    return dict(profile=PROFILE,intervals=values,modeled_vertices=recovered,authority='none',selected=False,
        scope='explicit_planar_helper_assumption_not_observed_cloth_depth')


def at(probe,sampler,source_tick,slot,time,segments,helpers,*,axis_lengths=None):
    from .sleeve_depth_plane import at as plane_at
    from .affine_pose import matrices
    from ..spine43.continuous_pose import interpolate
    document=probe.document;name=probe.slots[slot]['attachment']
    mesh=document['skins'][0]['attachments'][slot][name];planes={};unavailable={}
    for helper,parent in helpers.items():
        try:planes[helper]=plane_at(document,probe.animation,time,sampler,source_tick,helper,parent)
        except ValueError as exc:unavailable[helper]=str(exc)
    tracks=document['animations'][probe.animation].get('attachments',{}).get('default',{}).get(slot,{}).get(name,{})
    offsets=interpolate(tracks['deform'],time,'vertices') if tracks.get('deform') else []
    result=mix(document,mesh,segments,helpers,planes,matrices(document,probe.animation,time),
               axis_lengths=axis_lengths,offsets=offsets)
    result.update(helper_planes=planes,unavailable_helpers=unavailable)
    return result
