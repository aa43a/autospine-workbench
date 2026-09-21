"""Single-frame proximal-ring feasibility experiment; does not publish motion."""
import argparse
from copy import deepcopy
import json
import math
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.targets.character43.affine_pose import sample,matrices
from autospine_workbench.targets.character43.projected_area_reference import reference
from autospine_workbench.targets.character43.local_area_constraints import refine
from autospine_workbench.targets.spine43.continuous_pose import area


def run(folder,output):
    receipt=json.loads((folder/'report.json').read_bytes())
    files=AnimatedStore(folder/'isolated-store').read(receipt['candidate_bundle_sha256'])
    doc=json.loads(files['skeleton.json']);name='external-motion'
    correction=json.loads((folder/'correction.json').read_bytes())
    worst=min(correction['refinement'][-1]['check']['failures'],key=lambda r:r['min_ratio'])
    slot,time=worst['slot'],worst['time'];row=next(r for r in correction['records'] if r['slot']==slot)
    bare=deepcopy(doc);bare['animations'][name].pop('attachments',None)
    rest=deepcopy(bare);rest['animations'][name]={'bones':{}}
    setup=json.loads(files['rig-setup-reference.json'])['vertices'][slot]
    base=sample(bare,name,time)[0][slot];initial=sample(doc,name,time)[0][slot]
    mesh=doc['skins'][0]['attachments'][slot][slot];data=mesh['vertices'];i=0;owners=[]
    while i<len(data):
        n=data[i];i+=1;owners.append([(data[i+4*j],data[i+4*j+3]) for j in range(n)]);i+=4*n
    flat=mesh['triangles'];tri=[flat[i:i+3] for i in range(0,len(flat),3)]
    edges=sorted({tuple(sorted((t[i],t[(i+1)%3]))) for t in tri for i in range(3)})
    free=[sum(w>0 for _,w in entries)>1 for entries in owners];added=set()
    for collar in row['terminal_collars']:
        seeds=set(collar['vertices']);neighbors={v for t in tri if seeds.intersection(t) for v in t}
        for v in seeds:free[v]=True
        for v in neighbors-seeds:
            names={doc['bones'][i]['name'] for i,w in owners[v] if w>0}
            if names=={collar['parent']} and not free[v]:added.add(v);free[v]=True
    refs=reference([area(setup,t) for t in tri],tri,owners,doc['bones'],matrices(rest,name,0),matrices(doc,name,time))
    context=dict(row={'triangles':tri},areas=refs,edges=edges,
        lengths=[math.dist(setup[a],setup[b]) for a,b in edges],free=free,budget=row['budget_px'])
    points,report=refine(context,base,initial,analytic=True)
    report.update(candidate_sha256=receipt['candidate_bundle_sha256'],slot=slot,time=time,
        added_proximal_vertices=sorted(added),scope='single_frame_proximal_ring_experiment_not_motion_adoption',
        maximum_displacement=max(math.dist(a,b) for a,b in zip(base,points)))
    with output.open('x',encoding='utf-8') as f:json.dump(report,f,indent=2)
    print(json.dumps(report))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('folder',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();run(a.folder,a.output)
