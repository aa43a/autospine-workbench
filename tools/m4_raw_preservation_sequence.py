"""Bake an isolated raw-compression experiment and capture keys plus midpoints."""
import argparse
from copy import deepcopy
import json
from pathlib import Path

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.targets.character43.affine_pose import matrices, sample
from autospine_workbench.targets.character43.deform_addition import entries, local_delta
from autospine_workbench.targets.spine43.continuous_pose import area
from m4_raw_area_preservation_probe import run
from m4_squat_stage_players import stage


def inspect(raw,result,name,slot,times,triangles,setup_areas):
    capture_times=sorted(set(times)|{(a+b)/2 for a,b in zip(times,times[1:])})
    regressions=[]
    for time in capture_times:
        before=sample(raw,name,time)[0][slot];after=sample(result,name,time)[0][slot]
        for index,(tri,reference) in enumerate(zip(triangles,setup_areas)):
            a,b=area(before,tri)/reference,area(after,tri)/reference
            if 0<a<.5 and b<a-1e-7:
                regressions.append(dict(time=time,triangle=index,before=a,after=b,at_key=time in times))
    return capture_times,regressions


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('artifact');parser.add_argument('slot');parser.add_argument('output',type=Path)
    parser.add_argument('--rounds',type=int,choices=range(1,4),default=1)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    files=AnimatedStore(Path('workspace')).read(args.artifact)
    doc=json.loads(files['skeleton.json']);name='external-motion';slot=args.slot
    times=sorted({k['time'] for tracks in doc['animations'][name]['bones'].values() for track in tracks.values() for k in track})
    if not 2<=len(times)<=1025:raise ValueError('sequence_key_limit')
    source_key_count=len(times)
    mesh=doc['skins'][0]['attachments'][slot][slot];owners=entries(mesh)
    result=deepcopy(doc);raw=deepcopy(doc)
    raw['animations'][name].pop('attachments',None);raw['animations'][name].pop('deform',None)
    rows={};keys={};history=[]
    triangles=[mesh['triangles'][i:i+3] for i in range(0,len(mesh['triangles']),3)]
    setup=json.loads(files['rig-setup-reference.json'])['vertices'][slot]
    setup_areas=[area(setup,t) for t in triangles]
    for iteration in range(args.rounds):
        pending=[t for t in times if t not in keys]
        for index,time in enumerate(pending):
            report=run(args.artifact,slot,name,time,files=files,policies=('preserve_raw_compression',))
            points=report['points']
            keys[time]=dict(time=time,vertices=local_delta(doc,owners,matrices(doc,name,time),
                points['raw'],points['preserve_raw_compression']))
            rows[time]=dict(time=time,**report['policies']['preserve_raw_compression'])
            if index%10==0:print(json.dumps(dict(stage='solve',iteration=iteration,completed=index+1,total=len(pending))),flush=True)
        result['animations'][name].setdefault('attachments',{}).setdefault('default',{}).setdefault(slot,{})[slot]={'deform':[keys[t] for t in times]}
        capture_times,regressions=inspect(raw,result,name,slot,times,triangles,setup_areas)
        history.append(dict(iteration=iteration,solved_times=times,samples=len(capture_times),regressions=regressions))
        new={r['time'] for r in regressions if not r['at_key']}-set(times)
        if not new or iteration+1==args.rounds or len(set(times)|new)>1025:break
        times=sorted(set(times)|new)
    unchanged=deepcopy(result)
    unchanged['animations'][name]['attachments']['default'][slot]=deepcopy(doc['animations'][name]['attachments']['default'][slot])
    if unchanged!=doc:raise ValueError('sequence_changed_unrelated_channels')
    report=dict(parent_sha256=args.artifact,slot=slot,authority='none',selected=False,
        unrelated_channels_unchanged=True,
        profile='raw-compression-preservation-sequence-v1-experiment',source_key_count=source_key_count,
        solved_key_count=len(times),history=history,
        sample_count=len(capture_times),records=[rows[t] for t in times],raw_compression_regressions=regressions,
        scope='keys_and_midpoints_not_continuous_or_visual_acceptance')
    (args.output/'probe.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    artifact=stage(result,files,capture_times,args.output/'candidate',args.artifact)
    runtime=json.loads((args.output/'candidate/runtime/report.json').read_bytes())
    geometry=json.loads((args.output/'candidate/runtime/deformation.json').read_bytes())
    if runtime['bundle_sha256']!=artifact:raise ValueError('runtime_identity_mismatch')
    summary=dict(parent=args.artifact,candidate=artifact,source_keys=source_key_count,solved_keys=len(times),samples=len(capture_times),
        runtime_numeric_passed=runtime['passed'],geometry_passed=geometry['passed'],
        raw_compression_regression_count=len(regressions),
        key_regression_count=sum(r['at_key'] for r in regressions),
        failed_slots=[r for r in geometry['records'] if not r['passed']],authority='none',selected=False)
    (args.output/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in summary.items() if k!='failed_slots'}),flush=True)


if __name__=='__main__':main()
