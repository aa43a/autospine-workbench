"""Project aggregate conservative depth masks back onto each source triangle."""
import math
from ..spine43.seam_raster import mask


def collect(probe,name,time,rect,masks,callback):
    x,y,w,h=rect;slot=probe.slots[name]
    mesh=probe.document['skins'][0]['attachments'][name][slot['attachment']];points=probe.positions[time][name]
    flat=mesh['triangles']
    for offset in range(0,len(flat),3):
        tri=flat[offset:offset+3];p=[points[i] for i in tri]
        left=max(x,math.floor(min(v[0] for v in p)));right=min(x+w,math.ceil(max(v[0] for v in p)))
        top=max(y,math.floor(min(-v[1] for v in p)));bottom=min(y+h,math.ceil(max(-v[1] for v in p)))
        if right<=left or bottom<=top:continue
        area=(right-left)*(bottom-top)
        if probe.remaining<area:raise ValueError('depth_overlap_pixel_budget')
        probe.remaining-=area
        visible=mask(dict(mesh,triangles=tri),points,probe.textures[name],[left,top,right-left,bottom-top])>=8
        counts={k:int((visible&v[top-y:bottom-y,left-x:right-x]).sum()) for k,v in masks.items()}
        if any(counts.values()):callback(offset//3,counts)
