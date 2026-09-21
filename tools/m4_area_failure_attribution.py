"""Explain worst setup-area failures using exact transforms, without changing gates."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.targets.character43.numeric_reference import read
from autospine_workbench.targets.character43.affine_pose import matrices,sample
from autospine_workbench.targets.character43.projected_area_reference import reference
from autospine_workbench.targets.spine43.continuous_pose import area


def run(folder,output):
    report=json.loads((folder/'report.json').read_bytes())
    files=AnimatedStore(folder/'isolated-store').read(report['candidate_bundle_sha256'])
    doc=json.loads(files['skeleton.json']);name='external-motion'
    frames=read(files)['animations'][name];setup=json.loads(files['rig-setup-reference.json'])['vertices']
    rest=deepcopy(doc);rest['animations']={name:{'bones':{}}};rest_pose=matrices(rest,name,0)
    bare=deepcopy(doc);bare['animations'][name].pop('attachments',None)
    qa=json.loads((folder/'deformation.json').read_bytes());rows=[]
    for failure in qa['records']:
        if failure['passed']:continue
        slot=failure['slot'];mesh=doc['skins'][0]['attachments'][slot][slot]
        flat=mesh['triangles'];tri=[flat[i:i+3] for i in range(0,len(flat),3)];areas=[area(setup[slot],t) for t in tri]
        ratio,frame,index=min((area(f['vertices'][slot],t)/a,i,j) for i,f in enumerate(frames) for j,(t,a) in enumerate(zip(tri,areas)))
        t=frames[frame]['time'];data=mesh['vertices'];owners=[];i=0
        while i<len(data):
            n=data[i];i+=1;owners.append([(data[i+4*j],data[i+4*j+3]) for j in range(n)]);i+=4*n
        names={doc['bones'][b]['name'] for v in tri[index] for b,w in owners[v] if w>0}
        refs=reference(areas,tri,owners,doc['bones'],rest_pose,matrices(doc,name,t))
        before=area(sample(bare,name,t)[0][slot],tri[index])/areas[index]
        rows.append(dict(slot=slot,time=t,triangle=index,bones=sorted(names),setup_area_ratio=ratio,
            before_correction_ratio=before,projection_reference_factor=refs[index]/areas[index],
            ratio_to_projected_reference=ratio/(refs[index]/areas[index]),
            classification='single_bone_projection' if len(names)==1 and abs(ratio-before)<1e-7 else 'mixed_or_corrected_area',
            original_failure=failure))
    result=dict(profile='setup-area-failure-attribution-v1',candidate=report['candidate_bundle_sha256'],
        authority='none',selected=False,rows=rows,scope='worst_triangle_per_failing_slot_not_visual_acceptance',
        geometry_passed=qa['passed'],limits_unchanged=True)
    with output.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2)
    print(json.dumps(result))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('folder',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();run(a.folder,a.output)
