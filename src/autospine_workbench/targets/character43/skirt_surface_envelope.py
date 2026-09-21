"""Explicit elliptic garment cross-section hypothesis, not observed cloth Z."""
import math

PROFILE='setup-garment-cross-section-depth-envelope-v1-experiment'


def material_offsets(points,triangles,reference_length,*,aspect_range=(.25,.75)):
    if (not math.isfinite(reference_length) or reference_length<=0
            or len(aspect_range)!=2 or not all(math.isfinite(v) for v in aspect_range)
            or not 0<aspect_range[0]<=aspect_range[1]<=1):
        raise ValueError('skirt_surface_parameters_invalid')
    if len(points)>8192 or len(triangles)>49152 or len(triangles)%3:
        raise ValueError('skirt_surface_budget')
    if any(len(p)!=2 or not all(math.isfinite(v) for v in p) for p in points):
        raise ValueError('skirt_surface_points_invalid')
    if any(type(i)is not int or not 0<=i<len(points) for i in triangles):
        raise ValueError('skirt_surface_indices_invalid')
    if len({p[1] for p in points})*len(triangles)>8_000_000:
        raise ValueError('skirt_surface_section_budget')
    spans={};result=[]
    for x,y in points:
        if y not in spans:
            crossings=[]
            for start in range(0,len(triangles),3):
                tri=[points[i] for i in triangles[start:start+3]]
                for a,b in zip(tri,tri[1:]+tri[:1]):
                    if a[1]==b[1]:
                        if y==a[1]:crossings.extend((a[0],b[0]))
                    elif min(a[1],b[1])<=y<=max(a[1],b[1]):
                        crossings.append(a[0]+(b[0]-a[0])*(y-a[1])/(b[1]-a[1]))
            spans[y]=(min(crossings),max(crossings)) if crossings else None
        span=spans[y]
        if span is None or span[1]-span[0]<=1e-8:result.append(None);continue
        center=sum(span)/2;radius=(span[1]-span[0])/2
        height=math.sqrt(max(0,radius**2-(x-center)**2))/reference_length
        result.append([height*aspect_range[0],height*aspect_range[1]])
    return dict(profile=PROFILE,offsets=result,aspect_range=list(aspect_range),
        reference_length_px=reference_length,authority='none',selected=False,
        assumptions=['elliptic_horizontal_sections','fixed_material_depth_shape',
            'declared_aspect_range_not_measured','holes_and_slits_only_resolved_by_alpha_overlap'])


def at(model,anchor_depth,side):
    if not math.isfinite(anchor_depth) or side not in ('front','back'):
        raise ValueError('skirt_surface_anchor_invalid')
    sign=1 if side=='front' else -1
    return [None if row is None else sorted(anchor_depth+sign*v for v in row) for row in model['offsets']]
