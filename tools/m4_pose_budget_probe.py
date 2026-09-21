"""Check exact uncorrected poses against the local solver's fixed mask and budget."""
import argparse
from copy import deepcopy
import json
from pathlib import Path

from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.character43.area_budget_bounds import inspect
from autospine_workbench.targets.spine43.continuous_pose import area


def run(probe, corrected, output):
    document=json.loads((probe/'skeleton.json').read_bytes())
    receipt=json.loads((probe/'report.json').read_bytes())
    if canonical_sha256(document)!=receipt['output_sha256']:
        raise ValueError('pose_budget_source_identity')
    report=json.loads((corrected/'correction.json').read_bytes())
    animation,=document['animations']
    setup=deepcopy(document);setup['animations']={animation:{'bones':{}}}
    base=sample(setup,animation,0)[0];records=[]
    for row in report['records']:
        slot=row['slot']; attachment=document['skins'][0]['attachments'][slot][slot]
        data=attachment['vertices'];i=0;free=[]
        while i<len(data):
            count=data[i];i+=1;free.append(sum(data[i+4*j+3]>0 for j in range(count))>1);i+=4*count
        triangles=[attachment['triangles'][i:i+3] for i in range(0,len(attachment['triangles']),3)]
        areas=[area(base[slot],t) for t in triangles];frames=[]
        for solver in row['solver_samples']:
            time=solver['time'];points=sample(document,animation,time)[0][slot]
            check=inspect(points,triangles,areas,free,row['budget_px'])
            if check['witnesses']:
                frames.append(dict(time=time,witnesses=check['witnesses']))
        records.append(dict(slot=slot,tested_frames=len(row['solver_samples']),budget_px=row['budget_px'],
            infeasible_frames=len(frames),witness_frames=frames))
    result=dict(profile='source-pose-fixed-budget-probe-v1',authority='none',selected=False,
        source_skeleton_sha256=receipt['output_sha256'],correction_sha256=canonical_sha256(report),records=records,
        limitation='absence_of_individual_counterexample_does_not_prove_joint_feasibility')
    with output.open('x',encoding='utf-8') as handle:json.dump(result,handle,indent=2)
    print(json.dumps([dict(slot=r['slot'],infeasible_frames=r['infeasible_frames'],tested_frames=r['tested_frames']) for r in records]))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('probe','corrected','output'):parser.add_argument(name,type=Path)
    args=parser.parse_args();run(args.probe,args.corrected,args.output)
