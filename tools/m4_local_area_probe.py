"""Probe the unchanged displacement budget at an exact candidate slot/time."""
import argparse
from copy import deepcopy
import json
import math
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.affine_pose import matrices,sample
from autospine_workbench.targets.character43.projected_area_reference import reference
from autospine_workbench.targets.character43.local_area_constraints import refine
from autospine_workbench.targets.spine43.continuous_pose import area


def run(folder,slot,time,output,collar=False):
    receipt=json.loads((folder/'report.json').read_bytes())
    files=AnimatedStore(folder/'isolated-store').read(receipt['candidate_bundle_sha256'])
    document=json.loads(files['skeleton.json']);name='external-motion'
    setup=deepcopy(document);setup['animations'][name]={'bones':{}}
    bare=deepcopy(document);bare['animations'][name].pop('attachments',None)
    base=sample(setup,name,0)[0][slot];initial=sample(document,name,time)[0][slot]
    origin=sample(bare,name,time)[0][slot]
    attachment=document['skins'][0]['attachments'][slot][slot]
    flat=attachment['triangles'];triangles=[flat[i:i+3] for i in range(0,len(flat),3)]
    data=attachment['vertices'];i=0;influences=[]
    while i<len(data):
        count=data[i];i+=1;influences.append([(data[i+4*j],data[i+4*j+3]) for j in range(count)]);i+=4*count
    refs=reference([area(base,t) for t in triangles],triangles,influences,document['bones'],
                   matrices(setup,name,0),matrices(document,name,time))
    correction=json.loads((folder/'correction.json').read_bytes())
    budget=next(r['budget_px'] for r in correction['records'] if r['slot']==slot)
    edges=sorted({tuple(sorted((t[j],t[(j+1)%3]))) for t in triangles for j in range(3)})
    context=dict(row={'triangles':triangles},areas=refs,edges=edges,
                 lengths=[math.dist(base[a],base[b]) for a,b in edges],
                 free=[sum(w>0 for _,w in row)>1 for row in influences],budget=budget)
    proposals=[]
    if collar:
        from autospine_workbench.targets.character43.terminal_joint_collar import propose
        for side in ('l','r'):
            proposal=propose(base,triangles,influences,document['bones'],matrices(setup,name,0),'calf_'+side,'foot_'+side)
            proposals.append(proposal)
            for v in proposal['vertices']:context['free'][v]=True
    corrected,report=refine(context,origin,initial)
    report.update(source_candidate_sha256=receipt['candidate_bundle_sha256'],slot=slot,time=time,
                  maximum_displacement_px=max(math.dist(a,b) for a,b in zip(origin,corrected)),
                  limitation='single_frame_patch_not_animation_or_runtime_validation')
    report['collar_proposals']=proposals
    raw=canonical_bytes(report)
    with output.open('xb') as handle:handle.write(raw)
    print(json.dumps(report))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('folder',type=Path);p.add_argument('slot')
    p.add_argument('time',type=float);p.add_argument('output',type=Path)
    p.add_argument('--collar',action='store_true')
    a=p.parse_args();run(a.folder,a.slot,a.time,a.output,a.collar)
