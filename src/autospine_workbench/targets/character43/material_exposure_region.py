"""Raster-scale material provenance; source coverage is evidence, not semantics."""
import numpy as np
from .material_alpha_batch import sample as alpha_sample


def components(pixels):
    remaining=set(map(tuple,pixels));result=[]
    while remaining:
        seed=min(remaining);remaining.remove(seed);pending=[seed];group=[]
        while pending:
            x,y=pending.pop();group.append((x,y))
            for neighbor in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
                if neighbor in remaining:remaining.remove(neighbor);pending.append(neighbor)
        xs,ys=zip(*group)
        result.append(dict(points=len(group),bounds=[min(xs),min(ys),max(xs)+1,max(ys)+1]))
    return sorted(result,key=lambda r:(-r['points'],r['bounds']))


def inspect(limb,rest,posed,limb_alpha,cloth,cloth_rest,cloth_posed,cloth_alpha,limit=200000):
    rest=np.asarray(rest,float);posed=np.asarray(posed,float)
    if rest.shape!=posed.shape or not np.isfinite(posed).all():raise ValueError('exposure_region_points')
    records={}
    for ids in np.asarray(limb['triangles'],int).reshape(-1,3):
        triangle=posed[ids];a,b,c=triangle;matrix=np.column_stack((b-a,c-a))
        if abs(np.linalg.det(matrix))<1e-12:continue
        low=np.floor(triangle.min(0)).astype(int);high=np.ceil(triangle.max(0)).astype(int)
        if np.prod(high-low)>limit:raise ValueError('exposure_region_triangle_budget')
        xx,yy=np.meshgrid(np.arange(low[0],high[0]),np.arange(low[1],high[1]))
        pixels=np.column_stack((xx.ravel(),yy.ravel()));queries=pixels+.5
        w=(queries-a)@np.linalg.inv(matrix).T;weights=np.column_stack((1-w.sum(1),w))
        for pixel,query,weight in zip(pixels,queries,weights):
            if min(weight)<-1e-8:continue
            key=tuple(map(int,pixel));source=weight@rest[ids]
            if key in records:
                if np.linalg.norm(np.asarray(records[key]['source'])-source)>1e-6:records[key]['ambiguous']=True
            else:records[key]=dict(pixel=list(key),world=query.tolist(),source=source.tolist(),ambiguous=False)
            if len(records)>limit:raise ValueError('exposure_region_pixel_budget')
    rows=list(records.values())
    for start in range(0,len(rows),256):
        chunk=rows[start:start+256];world=[r['world'] for r in chunk];source=[r['source'] for r in chunk]
        la=alpha_sample(limb,posed,limb_alpha,world)
        old=alpha_sample(cloth,cloth_rest,cloth_alpha,source)
        current=alpha_sample(cloth,cloth_posed,cloth_alpha,world)
        for r,l,a,b in zip(chunk,la,old,current):
            r.update(limb_alpha=l,source_cloth_alpha=a,current_cloth_alpha=b,
                newly_exposed=not r['ambiguous'] and l>=8 and a>=8 and b<8,
                originally_visible=not r['ambiguous'] and l>=8 and a<8 and b<8)
    return dict(rows=rows,components=components(r['pixel'] for r in rows if r['newly_exposed']),summary=dict(raster_points=len(rows),
        ambiguous_points=sum(r['ambiguous'] for r in rows),
        newly_exposed_points=sum(r['newly_exposed'] for r in rows),
        originally_visible_points=sum(r['originally_visible'] for r in rows)),
        scope='two_attachment_cpu_material_coverage_not_final_framebuffer_or_semantic_proof')
