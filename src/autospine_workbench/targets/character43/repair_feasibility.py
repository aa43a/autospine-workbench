"""Necessary fixed-vertex counterexamples for the declared local repair policy."""
from copy import deepcopy
from hashlib import sha256
import json
import math

from .affine_pose import sample, matrices
from .deform_addition import entries
from .numeric_reference import read
from .triangle_shape_evidence import build as shape_evidence
from ..spine43.continuous_pose import area


def inspect(files, artifact):
    document=json.loads(files['skeleton.json']);reference=read(files)
    setup=json.loads(files['rig-setup-reference.json'])
    digest=sha256(files['skeleton.json']).hexdigest()
    if reference['skeleton_sha256']!=digest or setup['skeleton_sha256']!=digest:
        raise ValueError('motion_repair_feasibility_identity')
    qa=json.loads(files['deformation.json'])
    if qa['skeleton_sha256']!=digest:
        raise ValueError('motion_repair_feasibility_identity')
    rows=[]
    for record in qa['records']:
        if record['passed']:continue
        slot,name=record['slot'],record['animation']
        mesh=document['skins'][0]['attachments'][slot][slot]
        if len(mesh['vertices'])==len(mesh['uvs']):
            rows.append(dict(slot=slot,animation=name,status='unsupported_unweighted',counterexample_count=None));continue
        owners=entries(mesh)
        free=[sum(w>0 for _,w in row)>1 for row in owners]
        triangles=[mesh['triangles'][i:i+3] for i in range(0,len(mesh['triangles']),3)]
        fixed=[i for i,tri in enumerate(triangles) if all(not free[v] for v in tri)]
        times=[f['time'] for f in reference['animations'][name]]
        if len(times)*len(triangles)>20_000_000:
            raise ValueError('motion_repair_feasibility_sample_limit')
        source=deepcopy(document)
        source['skins'][0]['attachments']={slot:deepcopy(document['skins'][0]['attachments'][slot])}
        source['slots']=[s for s in document['slots'] if s['name']==slot]
        source['animations']={name:{'bones':deepcopy(document['animations'][name]['bones'])}}
        areas={i:area(setup['vertices'][slot],triangles[i]) for i in fixed}
        if any(abs(a)<1e-10 for a in areas.values()):raise ValueError('motion_repair_feasibility_degenerate')
        failures=[];unique=set();samples=0;worst=None;single=set();cross=set()
        for time in times:
            if not fixed:break
            points=sample(source,name,time)[0][slot]
            bad=[]
            for index in fixed:
                ratio=area(points,triangles[index])/areas[index]
                if not math.isfinite(ratio):raise ValueError('motion_repair_feasibility_nonfinite')
                if .5<=ratio<=2:continue
                bad.append(index);unique.add(index)
                bones={document['bones'][bone]['name'] for vertex in triangles[index] for bone,weight in owners[vertex] if weight>0}
                (single if len(bones)==1 else cross).add(index)
                event=dict(time=time,triangle=index,setup_ratio=ratio,bones=sorted(bones))
                severity=max(.5-ratio,ratio-2)
                if worst is None or severity>worst[0]:worst=(severity,event)
            if bad:
                samples+=1
                if len(failures)<20:failures.append(dict(time=time,triangle_count=len(bad)))
        if worst:
            event=worst[1];tri=triangles[event['triangle']];time=event['time']
            rest=deepcopy(source);rest['animations']={name:{'bones':{}}}
            selected=deepcopy(source)
            selected['animations']={name:deepcopy(document['animations'][name])}
            actual=sample(selected,name,time)[0][slot]
            raw=sample(source,name,time)[0][slot]
            event['shape_evidence']=shape_evidence(
                [setup['vertices'][slot][v] for v in tri],
                [actual[v] for v in tri],[raw[v] for v in tri],
                [owners[v] for v in tri],document['bones'],
                matrices(rest,name,0),matrices(document,name,time))
        rows.append(dict(slot=slot,animation=name,
            status='fixed_vertex_counterexample' if unique else 'no_fixed_vertex_counterexample',
            counterexample_count=len(unique),fixed_triangles=len(fixed),failed_times=samples,
            sampled_times=len(times),single_bone_triangles=len(single),cross_bone_triangles=len(cross),
            first_failures=failures,worst=worst[1] if worst else None,
            complete_repair_impossible_under_policy=bool(unique)))
    return dict(profile='mixed-vertices-fixed-single-bone-feasibility-v1',artifact_sha256=artifact,
        skeleton_sha256=digest,rows=rows,authority='none',selected=False,
        scope='necessary_fixed_vertex_counterexamples_not_general_infeasibility_or_visual_failure')
