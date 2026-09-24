"""Sampled geometry uses each active attachment's own rest mesh and topology."""
import math
from .active_mesh_pose import sample_active
from ...asset.planning.component_local_solver import metrics

PROFILE='character-active-attachment-deformation-v1'


def inspect(document, reference):
    rows={}; hidden=[]
    for animation,frames in reference['animations'].items():
        if len(frames)<2 or frames[0]['time']!=0:
            raise ValueError('character_reference_setup_missing')
        previous=-1
        for index,frame in enumerate(frames):
            time=frame['time']
            if type(time) not in (int,float) or not math.isfinite(time) or time<=previous:
                raise ValueError('character_reference_time_invalid')
            previous=time
            active=sample_active(document,animation,time)
            if frame.get('attachments')!=active['attachments']:
                raise ValueError('character_reference_active_attachment_mismatch')
            if set(frame['vertices'])!=set(active['vertices']):
                raise ValueError('character_reference_slot_inventory')
            for slot,name in active['attachments'].items():
                if name is None:
                    hidden.append(dict(animation=animation,slot=slot,time=time))
                    continue
                base=active['setup_vertices'][slot]; points=frame['vertices'][slot]
                if len(points)!=len(base) or any(len(p)!=2 or not all(math.isfinite(v) for v in p) for p in points):
                    raise ValueError('character_reference_nonfinite')
                flat=active['triangles'][slot]
                if not flat or len(flat)%3 or any(type(v) is not int or not 0<=v<len(base) for v in flat):
                    raise ValueError('character_triangle_inventory')
                triangles=[flat[i:i+3] for i in range(0,len(flat),3)]
                try:
                    quality=metrics(base,points,triangles)
                except ZeroDivisionError as exc:
                    raise ValueError('character_setup_degenerate') from exc
                key=(animation,slot,name)
                row=rows.setdefault(key,dict(animation=animation,slot=slot,attachment=name,
                    passed=True,sample_count=0,min_area_ratio=1.,max_area_ratio=1.,
                    max_edge_stretch=1.,inversion_samples=0,failing_frame_count=0,first_failure=None))
                row['sample_count']+=1
                row['min_area_ratio']=min(row['min_area_ratio'],quality['min_area_ratio'])
                row['max_area_ratio']=max(row['max_area_ratio'],quality['max_area_ratio'])
                row['max_edge_stretch']=max(row['max_edge_stretch'],quality['max_edge_stretch'])
                row['inversion_samples']+=quality['inversions']
                if quality['bad_triangles'] or quality['max_edge_stretch']>2:
                    row['passed']=False;row['failing_frame_count']+=1
                    if row['first_failure'] is None:
                        row['first_failure']=dict(frame=index,time=time,attachment=name,**quality)
    return dict(schema='autospine.character-deformation-qa/v1',profile=PROFILE,
        authority='none',production_authorized=False,skeleton_sha256=reference['skeleton_sha256'],
        scope='sampled_geometry_against_active_attachment_setup',
        limits=dict(min_area_ratio=.5,max_area_ratio=2,max_edge_stretch=2),
        contact_status='not_evaluated',transition_status='not_evaluated',
        passed=bool(rows) and all(r['passed'] for r in rows.values()),records=list(rows.values()),
        hidden_samples=hidden)
