"""Conservative triangle depth envelopes on actual two-mesh alpha overlap."""
import math
import numpy as np
from ..spine43.seam_raster import mask

PROFILE='two-mesh-triangle-depth-envelopes-v1-experiment'


def _field(probe,name,time,rect,intervals):
    slot=probe.slots[name]
    mesh=probe.document['skins'][0]['attachments'][name][slot['attachment']]
    points=probe.positions[time][name]
    if len(intervals)!=len(points) or any(v is not None and
            (len(v)!=2 or not all(math.isfinite(z) for z in v) or v[0]>v[1]) for v in intervals):
        raise ValueError('pair_depth_intervals_invalid')
    x,y,w,h=rect
    low=np.full((h,w),np.inf); high=np.full((h,w),-np.inf)
    unknown=np.zeros((h,w),dtype=bool); covered=np.zeros((h,w),dtype=bool)
    indices=mesh['triangles']
    for i in range(0,len(indices),3):
        tri=indices[i:i+3]; vertices=[points[j] for j in tri]
        left=max(x,math.floor(min(p[0] for p in vertices)))
        right=min(x+w,math.ceil(max(p[0] for p in vertices)))
        top=max(y,math.floor(min(-p[1] for p in vertices)))
        bottom=min(y+h,math.ceil(max(-p[1] for p in vertices)))
        if right<=left or bottom<=top: continue
        area=(right-left)*(bottom-top)
        if area>probe.remaining: raise ValueError('depth_overlap_pixel_budget')
        probe.remaining-=area
        visible=mask(dict(mesh,triangles=tri),points,probe.textures[name],
                     [left,top,right-left,bottom-top])>=8
        region=np.s_[top-y:bottom-y,left-x:right-x]
        covered[region]|=visible
        values=[intervals[j] for j in tri]
        if any(v is None for v in values): unknown[region]|=visible
        else:
            lo=min(v[0] for v in values); hi=max(v[1] for v in values)
            low[region]=np.where(visible,np.minimum(low[region],lo),low[region])
            high[region]=np.where(visible,np.maximum(high[region],hi),high[region])
    return low,high,unknown,covered


def compare(probe,a,b,time,a_intervals,b_intervals,*,margin=.02):
    if not math.isfinite(margin) or margin<=0: raise ValueError('pair_depth_margin_invalid')
    pair=probe.pair(a,b,time)
    result=dict(profile=PROFILE,authority='none',selected=False,time=time,pair=[a,b],
                overlap_pixels=pair['overlap_pixels'],margin=margin,
                scope='sampled_cpu_alpha_and_depth_model_not_surface_truth_or_runtime')
    if not pair['overlap_pixels']: return dict(result,status='no_overlap',counts={})
    al,ah,au,ac=_field(probe,a,time,pair['roi'],a_intervals)
    bl,bh,bu,bc=_field(probe,b,time,pair['roi'],b_intervals)
    common=ac&bc
    if int(common.sum())!=pair['overlap_pixels']: raise ValueError('pair_depth_overlap_mismatch')
    unknown=common&(au|bu); known=common&~unknown
    front=known&(al>bh+margin); back=known&(ah<bl-margin)
    ambiguous=known&~front&~back
    counts={k:int(v.sum()) for k,v in dict(front=front,back=back,unknown=unknown,ambiguous=ambiguous).items()}
    status=('uniform_front_proxy' if counts['front']==pair['overlap_pixels'] else
            'uniform_back_proxy' if counts['back']==pair['overlap_pixels'] else 'requires_partition_or_more_depth')
    return dict(result,status=status,counts=counts,
                unknown_support={a:int((common&au).sum()),b:int((common&bu).sum())})
