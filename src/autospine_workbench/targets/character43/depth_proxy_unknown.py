"""Attribute unknown depth to actual weighted triangles in opaque overlap."""
from collections import defaultdict
from .mesh_depth_proxy import vertex_depths
from ..spine43.seam_raster import mask


def inspect(probe, arm, other, time, segments, *, axis_lengths=None):
    pair = probe.pair(arm,other,time)
    report = dict(profile='overlap-depth-unknown-causes-v1', time=time, pair=[arm,other],
                  authority='none', selected=False, causes=[], overlap_pixels=pair['overlap_pixels'],
                  scope='conservative_triangle_support_causes_may_share_pixels')
    if not pair['overlap_pixels']: return report
    rect=pair['roi']; area=rect[2]*rect[3]
    attachments={n:probe.document['skins'][0]['attachments'][n][probe.slots[n]['attachment']] for n in (arm,other)}
    mesh=attachments[arm]
    values=vertex_depths(probe.document,mesh,segments,endpoint_caps=True,axis_lengths=axis_lengths)
    def raster(name,attachment):
        if area>probe.remaining: raise ValueError('depth_overlap_pixel_budget')
        probe.remaining-=area
        return mask(attachment,probe.positions[time][name],probe.textures[name],rect)>=8
    common=raster(arm,mesh)&raster(other,attachments[other])
    data=mesh['vertices']; cursor=0; causes=[]
    for value in values:
        count=data[cursor]; cursor+=1; rows=[]; total=0
        for _ in range(count):
            index,x,y,weight=data[cursor:cursor+4]; cursor+=4; total+=weight
            if weight<=0: continue
            bone=probe.document['bones'][index]; name=bone['name']; length=(axis_lengths or {}).get(name,bone.get('length',0))
            reason=('missing_segment' if name not in segments else 'nonpositive_length' if length<=0 else
                    'outside_quarter_cap' if not -.25*length<=x<=1.25*length else None)
            if reason: rows.append(dict(bone=name,reason=reason,x_ratio=x/length if length>0 else None,weight=weight))
        if value is None and abs(total-1)>1e-6:
            rows.append(dict(bone='all',reason='unnormalized_weights',x_ratio=None,weight=total))
        causes.append(rows if value is None else [])
    grouped=defaultdict(set); details=defaultdict(dict); flat=mesh['triangles']
    for i in range(0,len(flat),3):
        for vertex in flat[i:i+3]:
            for cause in causes[vertex]:
                key=(cause['bone'],cause['reason'])
                grouped[key].add(i//3); details[key][vertex]=dict(vertex=vertex,**cause)
    for key,triangles in sorted(grouped.items()):
        subset=dict(mesh,triangles=[v for t in sorted(triangles) for v in flat[3*t:3*t+3]])
        pixels=int((raster(arm,subset)&common).sum())
        if pixels:
            report['causes'].append(dict(bone=key[0],reason=key[1],overlap_pixels=pixels,
                supporting_triangles=sorted(triangles),supporting_vertices=list(details[key].values())))
    return report
