"""Probe source recovery at exact attributed poses; never publish a candidate."""
import argparse
from copy import deepcopy
import json
import math
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.targets.character43.affine_pose import matrices, sample
from autospine_workbench.targets.character43.support_proposal_replay import without_generated_deform
from autospine_workbench.targets.character43.projected_area_reference import reference
from autospine_workbench.targets.character43.area_preservation import from_pose
from autospine_workbench.targets.character43.area_source_relaxation import relax
from autospine_workbench.targets.spine43.continuous_pose import area


def run(reports):
    output=[]
    for report in reports:
        files=AnimatedStore('workspace').read(report['candidate'])
        doc=json.loads(files['skeleton.json']);name='external-motion'
        evidence=json.loads(files['motion-review.json'])['post_contact_repair']['correction']
        bare=without_generated_deform(doc,name,evidence)
        setup=json.loads(files['rig-setup-reference.json'])['vertices']
        rest=deepcopy(doc);rest['animations']={name:{'bones':{}}}
        for row in report['rows']:
            slot=row['slot'];time=row['time'];mesh=doc['skins'][0]['attachments'][slot][slot]
            data=mesh['vertices'];owners=[];i=0
            while i<len(data):
                count=data[i];i+=1
                owners.append([(data[i+4*j],data[i+4*j+3]) for j in range(count)]);i+=4*count
            flat=mesh['triangles'];triangles=[flat[i:i+3] for i in range(0,len(flat),3)];base=setup[slot]
            areas=[area(base,t) for t in triangles]
            refs=reference(areas,triangles,owners,doc['bones'],matrices(rest,name,0),matrices(doc,name,time))
            initial=sample(doc,name,time)[0][slot];source=sample(bare,name,time)[0][slot]
            record=next(r for r in evidence['records'] if r['slot']==slot)
            collar={v for c in record.get('terminal_collars',[]) for v in c['vertices']}
            floors=from_pose(source,triangles,refs)
            for index in record['fixed_repair_band']:floors[index]=.5
            edges=sorted({tuple(sorted((t[j],t[(j+1)%3]))) for t in triangles for j in range(3)})
            context=dict(row={'triangles':triangles},areas=refs,minimum_ratios=floors,edges=edges,
                lengths=[math.dist(base[a],base[b]) for a,b in edges],budget=record['budget_px'],
                free=[sum(w>0 for _,w in o)>1 or v in collar for v,o in enumerate(owners)])
            margins=evidence['refinement'][-1].get('solver_margins',{}).get(slot)
            if margins is not None:context['solver_margins']=margins
            corrected,check=relax(context,source,initial)
            index=row['triangle'];triangle=triangles[index]
            before=area(initial,triangle)/areas[index]
            if abs(before-row['setup_area_ratio'])>1e-10:raise ValueError('attributed_pose_changed')
            ratios=[area(corrected,t)/r for t,r in zip(triangles,refs)]
            # Diagnose a small simultaneous recovery of the target triangle.
            trial=deepcopy(corrected)
            group=[v for v in triangle if context['free'][v]]
            for v in group:trial[v]=[a+(b-a)/16 for a,b in zip(corrected[v],source[v])]
            from autospine_workbench.targets.character43.interpolation_area_margin import targets
            lower=[max(f,min(.55,area(initial,t)/r)) for f,t,r in zip(targets(context),triangles,refs)]
            blockers=[dict(triangle=i,ratio=area(trial,t)/r,minimum=f)
                      for i,(t,r,f) in enumerate(zip(triangles,refs,lower))
                      if set(group).intersection(t) and area(trial,t)/r<f-1e-7]
            result=dict(candidate=report['candidate'],character=report.get('character'),slot=slot,time=time,
                triangle=index,before=before,after=area(corrected,triangle)/areas[index],
                source=area(source,triangle)/areas[index],minimum_projected=min(ratios),
                maximum_projected=max(ratios),report=check,
                target_recovery_lower_bound_blockers=blockers)
            output.append(result);print(json.dumps(result),flush=True)
    return output


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input',type=Path);parser.add_argument('output',type=Path)
    args=parser.parse_args()
    result=run(json.loads(args.input.read_bytes()))
    with args.output.open('x',encoding='utf-8') as handle:json.dump(result,handle,indent=2)
