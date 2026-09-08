"""Conservative crystal-like residual candidates and unique nearby wing mounts."""
import math
from PIL import Image
from .wing_root import components
from .wing_color_ownership import closed_envelope
from .wing_edge_ownership import decode,encode


def analyze(raw,origin,wings,origins):
    donor=decode(raw);w,h=donor.size
    if w*h>8_000_000:raise ValueError('pendant_canvas_budget')
    foreground=set()
    for y in range(h):
        for x in range(w):
            rgba=donor.getpixel((x,y));rgb=rgba[:3]
            if rgba[3]>=8 and (max(rgb)-min(rgb)>=12 or max(rgb)<224):foreground.add((x,y))
    groups=components(foreground);rows=[];masks={};images={}
    if len(groups)>4096:raise ValueError('pendant_component_budget')
    for index,group in enumerate(groups):
        if len(group)<256:continue
        x0=min(x for x,y in group);y0=min(y for x,y in group);x1=max(x for x,y in group)+1;y1=max(y for x,y in group)+1
        if y1-y0<1.2*(x1-x0):continue
        seed=Image.new('RGBA',(w,h))
        for point in group:seed.putpixel(point,(0,0,0,255))
        envelope,_=closed_envelope(seed);name='pendant-'+str(index);masks[name]=envelope
        xs=sorted(x for x,y in group if y==y0);tip=[xs[len(xs)//2]+origin[0],y0+origin[1]]
        rows.append(dict(id=name,seed_pixels=len(group),bbox=[x0+origin[0],y0+origin[1],x1+origin[0],y1+origin[1]],tip_xy=tip))
    wing_pixels={}
    for name,wing_raw in sorted(wings.items()):
        image=decode(wing_raw);ox,oy=origins[name]
        wing_pixels[name]=[(x+ox,y+oy) for y in range(image.height) for x in range(image.width) if image.getpixel((x,y))[3]>=8]
    for row in rows:
        tx,ty=row['tip_xy'];distances=[]
        for name,points in wing_pixels.items():
            if not points:continue
            point=min(points,key=lambda p:((p[0]-tx)**2+(p[1]-ty)**2,p[1],p[0]))
            distances.append(dict(parent=name,distance_px=math.hypot(point[0]-tx,point[1]-ty),nearest_xy=list(point)))
        distances.sort(key=lambda r:(r['distance_px'],r['parent']));margin=distances[1]['distance_px']-distances[0]['distance_px'] if len(distances)>1 else None
        supported=bool(distances and distances[0]['distance_px']<=8 and (margin is None or margin>=8))
        row.update(mount_candidates=distances,margin_px=margin,parent=distances[0]['parent'] if supported else None,
          status='candidate' if supported else 'blocked',reason_code='unique_nearby_wing_tip' if supported else 'mount_unobservable_or_ambiguous')
    residual=donor.copy();assignments={row['id']:Image.new('RGBA',(w,h)) for row in rows};ambiguous=0
    for y in range(h):
        for x in range(w):
            rgba=donor.getpixel((x,y))
            if not rgba[3]:continue
            owners=[name for name,mask in masks.items() if mask[y*w+x]]
            if len(owners)>1:ambiguous+=1;continue
            if len(owners)==1:assignments[owners[0]].putpixel((x,y),rgba);residual.putpixel((x,y),(0,0,0,0))
    reconstructed=residual.copy()
    for row in rows:
        image=assignments[row['id']];reconstructed=Image.alpha_composite(reconstructed,image)
        row['visible_pixels']=sum(image.getpixel((x,y))[3]>0 for y in range(h) for x in range(w))
        x0,y0,x1,y1=row['bbox'];images[row['id']]=encode(image.crop((x0-origin[0],y0-origin[1],x1-origin[0],y1-origin[1])))
    a,b=donor.tobytes(),reconstructed.tobytes()
    if any(a[i+3]!=b[i+3] or (a[i+3] and a[i:i+4]!=b[i:i+4]) for i in range(0,len(a),4)):raise ValueError('pendant_reconstruction')
    count=sum(residual.getpixel((x,y))[3]>0 for y in range(h) for x in range(w))
    report=dict(profile='residual-crystal-unique-tip-v1',foreground=dict(alpha_min=8,chroma_min=12,dark_max_exclusive=224),
      min_seed_pixels=256,min_vertical_aspect=1.2,mount_distance_max_px=8,mount_margin_min_px=8,rows=rows,
      ambiguous_pixels=ambiguous,residual_visible_pixels=count,donor_reconstruction_exact=True,
      authority='none',production_authorized=False)
    return images,encode(residual),report
