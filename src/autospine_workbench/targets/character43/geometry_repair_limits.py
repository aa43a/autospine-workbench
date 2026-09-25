"""Locate area failures a mixed-weight-only corrective cannot move."""
from copy import deepcopy
from hashlib import sha256
import json
from .numeric_reference import read
from ..spine43.continuous_pose import area


def annotate(files,geometry,setup):
    digest=sha256(files['skeleton.json']).hexdigest();reference=read(files)
    if geometry['skeleton_sha256']!=digest or reference['skeleton_sha256']!=digest:
        raise ValueError('geometry_repair_limit_identity')
    result=deepcopy(geometry)
    if setup is None:return result
    document=json.loads(files['skeleton.json'])
    if any('attachment' in tracks for motion in document['animations'].values()
           for tracks in motion.get('slots',{}).values()):return result
    for row in result['records']:
        if row['passed']:continue
        slot=row['slot'];mesh=document['skins'][0]['attachments'][slot][slot]
        data=mesh['vertices'];cursor=0;fixed=[]
        while cursor<len(data):
            count=data[cursor];cursor+=1
            if type(count) is not int or count<1 or cursor+4*count>len(data):
                raise ValueError('geometry_repair_limit_weight_inventory')
            fixed.append(sum(data[cursor+4*j+3]>0 for j in range(count))==1);cursor+=4*count
        if len(fixed)!=len(setup[slot]):raise ValueError('geometry_repair_limit_vertex_inventory')
        flat=mesh['triangles'];triangles=[flat[i:i+3] for i in range(0,len(flat),3)]
        ids=[i for i,t in enumerate(triangles) if all(fixed[v] for v in t)]
        bases={i:area(setup[slot],triangles[i]) for i in ids}
        first={};count=0;worst=None
        for frame in reference['animations'][row['animation']]:
            for i in ids:
                ratio=area(frame['vertices'][slot],triangles[i])/bases[i]
                if .5<=ratio<=2:continue
                event=dict(time=frame['time'],triangle=i,area_ratio=ratio)
                first.setdefault(i,event);count+=1
                severity=max(.5-ratio,ratio-2)
                if worst is None or severity>worst[0]:worst=(severity,event)
        if count:
            row['repair_limit']=dict(status='fixed_vertex_area_counterexample',
                policy='single_influence_vertices_held_fixed',triangle_count=len(first),
                sample_observations=count,first=min(first.values(),key=lambda r:r['time']),
                worst=worst[1],locations=list(first.values())[:20],locations_truncated=len(first)>20,
                scope='cannot_repair_without_changing_fixed_vertex_policy_not_proof_of_missing_artwork',
                authority='none',selected=False)
    return result
