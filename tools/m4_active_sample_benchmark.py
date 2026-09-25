"""Compare old and current normalization on an immutable real candidate."""
import argparse
import json
from pathlib import Path
import subprocess
from time import perf_counter

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.targets.character43.active_mesh_pose import sample_active
from autospine_workbench.targets.character43.numeric_reference import read


def run(state, artifact, output, baseline='2c2d1a5', all_reference=False):
    source=subprocess.check_output(['git','show',baseline+':src/autospine_workbench/targets/character43/active_mesh_pose.py'],text=True)
    namespace={'__package__':'autospine_workbench.targets.character43'}
    exec(compile(source,'baseline-active-mesh-pose.py','exec'),namespace)
    files=AnimatedStore(state).read(artifact)
    document=json.loads(files['skeleton.json'])
    original=json.dumps(document,sort_keys=True)
    name=next(iter(document['animations']));records=[]
    pairs=([(animation,frame['time']) for animation,frames in read(files)['animations'].items() for frame in frames]
           if all_reference else [(name,time) for time in (.05,.1,.15)])
    for name,time in pairs:
        start=perf_counter();before=namespace['sample_active'](document,name,time);old=perf_counter()-start
        start=perf_counter();after=sample_active(document,name,time);new=perf_counter()-start
        assert before==after,'sample output changed'
        records.append(dict(animation=name,time=time,baseline_seconds=old,current_seconds=new,exact_equal=True))
    assert json.dumps(document,sort_keys=True)==original,'source mutated'
    summary=dict(samples=len(records),exact_equal=True,source_unchanged=True,
                 baseline_seconds=sum(r['baseline_seconds'] for r in records),
                 current_seconds=sum(r['current_seconds'] for r in records))
    result=dict(artifact_sha256=artifact,baseline_revision=baseline,summary=summary,records=records,
                scope=('all_reference_cpu_samples' if all_reference else 'three_cpu_samples')+'_not_runtime_or_visual_acceptance')
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(summary))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--state',type=Path,default=Path('workspace'))
    parser.add_argument('--artifact',required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--baseline',default='2c2d1a5');parser.add_argument('--all-reference',action='store_true')
    args=parser.parse_args();run(args.state,args.artifact,args.output,args.baseline,args.all_reference)
