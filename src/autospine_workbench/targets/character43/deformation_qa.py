"""Sampled whole-scene deformation checks for every captured animation and attachment."""
import math
from hashlib import sha256
import json
from .numeric_reference import read as read_reference

PROFILE='character-sampled-deformation-v1'


def inspect(files, *, setup_vertices=None):
    document=json.loads(files['skeleton.json']);reference=read_reference(files)
    if reference['skeleton_sha256']!=sha256(files['skeleton.json']).hexdigest():
        raise ValueError('character_reference_source_mismatch')
    if not reference['animations'] or set(reference['animations'])!=set(document['animations']):raise ValueError('character_animation_inventory')
    attachments=document['skins'][0]['attachments'];rows=[]
    def area(points,t):
        a,b,c=(points[i] for i in t)
        return ((b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]))/2
    for name,frames in reference['animations'].items():
        if len(frames)<2 or frames[0]['time']!=0:raise ValueError('character_reference_setup_missing')
        previous=-1
        for frame in frames:
            if not math.isfinite(frame['time']) or frame['time']<=previous:raise ValueError('character_reference_time_invalid')
            previous=frame['time']
            if set(frame['vertices'])!=set(attachments):raise ValueError('character_reference_slot_inventory')
        for slot,choices in attachments.items():
            flat=choices[slot]['triangles'];base=(setup_vertices if setup_vertices is not None else frames[0]['vertices'])[slot]
            if not flat or len(flat)%3:raise ValueError('character_triangle_inventory')
            triangles=[flat[i:i+3] for i in range(0,len(flat),3)]
            if any(type(v) is not int or v<0 or v>=len(base) for v in flat):raise ValueError('character_triangle_index')
            edges=sorted({tuple(sorted((t[i],t[(i+1)%3]))) for t in triangles for i in range(3)})
            if any(len(p)!=2 or not all(math.isfinite(v) for v in p) for p in base):raise ValueError('character_reference_nonfinite')
            areas=[area(base,t) for t in triangles];lengths=[math.dist(base[a],base[b]) for a,b in edges]
            if any(abs(a)<1e-10 for a in areas) or any(v<1e-10 for v in lengths):raise ValueError('character_setup_degenerate')
            minimum=1.;maximum=1.;stretch=1.;inversions=0;failures=[]
            for index,frame in enumerate(frames):
                points=frame['vertices'][slot]
                if len(points)!=len(base) or any(len(p)!=2 or not all(math.isfinite(v) for v in p) for p in points):
                    raise ValueError('character_reference_nonfinite')
                ratios=[area(points,t)/a for t,a in zip(triangles,areas)]
                s=max(math.dist(points[a],points[b])/length for (a,b),length in zip(edges,lengths))
                inv=sum(v<=0 for v in ratios);lo=min(ratios);hi=max(ratios)
                minimum=min(minimum,lo);maximum=max(maximum,hi);stretch=max(stretch,s);inversions+=inv
                if lo<.5 or hi>2 or s>2:
                    failures.append(dict(frame=index,time=frame['time'],inversions=inv,min_area_ratio=lo,max_area_ratio=hi,max_edge_stretch=s))
            rows.append(dict(animation=name,slot=slot,passed=not failures,sample_count=len(frames),
                             min_area_ratio=minimum,max_area_ratio=maximum,max_edge_stretch=stretch,
                             inversion_samples=inversions,failing_frame_count=len(failures),first_failure=failures[0] if failures else None))
    return dict(schema='autospine.character-deformation-qa/v1',profile=PROFILE,authority='none',production_authorized=False,
                skeleton_sha256=reference['skeleton_sha256'],scope='sampled_geometry_against_rig_setup' if setup_vertices is not None else 'sampled_geometry_only',
                limits=dict(min_area_ratio=.5,max_area_ratio=2,max_edge_stretch=2),
                contact_status='not_evaluated',passed=all(r['passed'] for r in rows),records=rows)
