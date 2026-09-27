"""Refine frame-between-key failures while preserving the original deform and rig."""
import argparse
from copy import deepcopy
import json
from pathlib import Path

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.affine_pose import sample, matrices
from autospine_workbench.targets.character43.deform_addition import entries, local_delta, add
from autospine_workbench.targets.character43.parent_pose_area_repair import compare, verify_source
from autospine_workbench.asset.planning.component_local_solver import metrics
from autospine_workbench.resolved_project import canonical_sha256


def run(state,job,slot,output):
    if not job.startswith('motion-') or not job[7:].isalnum():raise ValueError('job_invalid')
    result=json.loads((state/'jobs/motion-intake-v1'/job/'result.json').read_bytes())
    parent=result['result']['artifact_sha256'];files=AnimatedStore(state).read(parent)
    doc=json.loads(files['skeleton.json']);name='external-motion'
    rest=dict(doc,animations={'setup':{}});setup=sample(rest,'setup',0)[0][slot]
    mesh=doc['skins'][0]['attachments'][slot][slot];weights=entries(mesh)
    triangles=[mesh['triangles'][i:i+3] for i in range(0,len(mesh['triangles']),3)]
    old=doc['animations'][name].get('attachments',{}).get('default',{}).get(slot,{}).get(slot,{}).get('deform',[])
    times={r['time'] for r in json.loads(files['numeric-reference.json'])['animations'][name]}
    times.update(k.get('time',0) for row in doc['animations'][name]['bones'].values() for keys in row.values() for k in keys)
    times.update(k.get('time',0) for k in old)
    initial_times=sorted(times);history=[];cache={};candidate=None
    for iteration in range(4):
        if len(times)>2049:raise ValueError('interval_repair_sample_budget')
        keys=[];rows=[]
        for t in sorted(times):
            if t not in cache:
                original=sample(doc,name,t)[0][slot];check=metrics(setup,original,triangles)
                corrected=original;row=None
                if check['min_area_ratio']<.52:
                    repair=compare(doc,doc,name,slot,t,protect_setup=True,local_refinement=True)
                    corrected=repair['points']['parent_setup_floor'];q=repair['parent_setup_floor']
                    row=dict(time=t,minimum_area_ratio=q['minimum_setup_ratio'],maximum_shift=q['maximum_shift'],
                             fixed_shift=q['fixed_shift'],setup_failures=q['setup_failures'])
                cache[t]=(dict(time=t,vertices=local_delta(doc,weights,matrices(doc,name,t),original,corrected)),row)
            key,row=cache[t];keys.append(key)
            if row:rows.append(row)
        candidate=deepcopy(doc)
        candidate['animations'][name].setdefault('attachments',{}).setdefault('default',{})[slot]={slot:{
            'deform':add(old,keys,2*sum(len(r) for r in weights))}}
        verify_source(doc,candidate,name,slot)
        ordered=sorted(times);samples=sorted(times|{(a+b)/2 for a,b in zip(ordered,ordered[1:])})
        failures=[]
        for t in samples:
            q=metrics(setup,sample(candidate,name,t)[0][slot],triangles)
            if q['bad_triangles'] or q['max_edge_stretch']>2:failures.append(dict(time=t,**q))
        history.append(dict(iteration=iteration,knots=len(times),samples=len(samples),failures=failures))
        print(json.dumps(dict(iteration=iteration,knots=len(times),samples=len(samples),failures=len(failures))),flush=True)
        extra={r['time'] for r in failures}-times
        if not extra:break
        times.update(extra)
    output.mkdir(parents=True,exist_ok=False)
    report=dict(profile='additive-interval-local-repair-v1-experiment',source_job=job,parent_sha256=parent,
        skeleton_sha256=canonical_sha256(candidate),slot=slot,initial_times=initial_times,validation_times=samples,
        history=history,repairs=rows,selected=False,authority='none',
        local_sampled_geometry_passed=not failures,
        limitations=['selected_attachment_cpu_only','requires_whole_character_runtime_contact_depth_and_visual_validation'])
    (output/'skeleton.json').write_bytes(canonical_bytes(candidate))
    (output/'report.json').write_bytes(canonical_bytes(report))
    print(json.dumps(dict(local_passed=not failures,repairs=len(rows),maximum_shift=max([r['maximum_shift'] for r in rows] or [0]))))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('state',type=Path);p.add_argument('job');p.add_argument('slot');p.add_argument('output',type=Path)
    a=p.parse_args();run(a.state,a.job,a.slot,a.output)
