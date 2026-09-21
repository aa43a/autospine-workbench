"""Locate signed-area failures without changing motion or correction authority."""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.spine43.continuous_pose import area


def run(folder,output):
    receipt=json.loads((folder/'report.json').read_bytes())
    files=AnimatedStore(folder/'isolated-store').read(receipt['candidate_bundle_sha256'])
    document=json.loads(files['skeleton.json']);name='external-motion'
    correction=json.loads((folder/'correction.json').read_bytes())
    failures=correction['refinement'][-1]['check']['failures']
    worst=min(failures,key=lambda r:r['min_ratio']);slot=worst['slot'];time=worst['time']
    setup=json.loads(files['rig-setup-reference.json'])['vertices'][slot]
    actual=sample(document,name,time)[0][slot]
    bare=deepcopy(document);bare['animations'][name].pop('attachments',None)
    base=sample(bare,name,time)[0][slot]
    a=document['skins'][0]['attachments'][slot][slot];data=a['vertices'];i=0;owners=[]
    while i<len(data):
        count=data[i];i+=1;owners.append([(document['bones'][data[i+4*j]]['name'],data[i+4*j+3]) for j in range(count) if data[i+4*j+3]>0]);i+=4*count
    evidence=next(r for r in correction['records'] if r['slot']==slot)
    collar={v for r in evidence.get('terminal_collars',[]) for v in r['vertices']}
    rows=[]
    for j in range(0,len(a['triangles']),3):
        tri=a['triangles'][j:j+3];ratio=area(actual,tri)/area(setup,tri)
        if ratio>0:continue
        vertices=[dict(index=v,setup=setup[v],before_correction=base[v],after_correction=actual[v],
                       influences=owners[v],movable=len(owners[v])>1 or v in collar) for v in tri]
        before_ratio=area(base,tri)/area(setup,tri)
        rows.append(dict(triangle=j//3,area_ratio=ratio,before_correction_area_ratio=before_ratio,
                         newly_inverted=before_ratio>0,vertices=vertices))
    value=dict(profile='pose-failure-localization-v1',authority='none',selected=False,
        candidate_bundle_sha256=receipt['candidate_bundle_sha256'],skeleton_sha256=sha256(files['skeleton.json']).hexdigest(),
        slot=slot,time=time,budget_px=evidence['budget_px'],worst_projected_sample=worst,
        inverted_triangles=rows,scope='diagnostic_not_proof_of_cause_or_feasibility')
    with output.open('x',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,indent=2)
    print(json.dumps(dict(slot=slot,time=time,triangles=[r['triangle'] for r in rows],
        owners=sorted({n for r in rows for v in r['vertices'] for n,w in v['influences']}))))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('folder',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();run(a.folder,a.output)
