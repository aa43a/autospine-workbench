"""Audit exact failed poses for hard area bounds under the existing repair freedom."""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.character43.triangle_area_feasibility import inspect
from autospine_workbench.targets.spine43.continuous_pose import area


def run(folder, output):
    report=json.loads((folder/'report.json').read_bytes())
    identity=report['candidate_bundle_sha256']
    files=AnimatedStore(folder/'isolated-store').read(identity)
    attribution=json.loads((folder/'area-attribution.json').read_bytes())
    setup=json.loads(files['rig-setup-reference.json'])
    if attribution['candidate']!=identity or setup['skeleton_sha256']!=sha256(files['skeleton.json']).hexdigest():
        raise ValueError('area_feasibility_candidate_mismatch')
    doc=json.loads(files['skeleton.json']);name='external-motion'
    bare=deepcopy(doc);bare['animations'][name].pop('attachments',None)
    correction=json.loads((folder/'correction.json').read_bytes())
    rows=[]
    for target in attribution['rows']:
        slot=target['slot'];time=target['time']
        mesh=doc['skins'][0]['attachments'][slot][slot];flat=mesh['triangles']
        triangles=[flat[i:i+3] for i in range(0,len(flat),3)]
        data=mesh['vertices'];owners=[];i=0
        while i<len(data):
            n=data[i];i+=1;owners.append([(data[i+4*j],data[i+4*j+3]) for j in range(n)]);i+=4*n
        source=sample(bare,name,time)[0][slot]
        record=next(r for r in correction['records'] if r['slot']==slot)
        free=[sum(w>0 for _,w in entries)>1 for entries in owners]
        for collar in record.get('terminal_collars',[]):
            for v in collar['vertices']:free[v]=True
        result=inspect(source,triangles,[area(setup['vertices'][slot],t) for t in triangles],free,record['budget_px'])
        blocked=[dict(r,vertices=triangles[r['triangle']],
            bones=sorted({doc['bones'][b]['name'] for v in triangles[r['triangle']] for b,w in owners[v] if w>0}))
            for r in result['rows'] if r['impossible']]
        row=dict(slot=slot,time=time,target_triangle=target['triangle'],
            target_bound=result['rows'][target['triangle']],triangle_count=len(triangles),
            fixed_triangle_count=sum(r['free_vertices']==0 for r in result['rows']),
            impossible_count=len(blocked),impossible=blocked,budget_px=record['budget_px'])
        rows.append(row)
        print(json.dumps({k:v for k,v in row.items() if k!='impossible'}),flush=True)
    result=dict(profile='fixed-freedom-area-feasibility-v1',candidate=identity,authority='none',
        selected=False,scope='existing_bones_weights_fixed_mask_budget_only_not_all_possible_rigs',rows=rows)
    with output.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('folder',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();run(a.folder,a.output)
