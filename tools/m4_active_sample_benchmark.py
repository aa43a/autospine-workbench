"""Compare old and current normalization on an immutable real candidate."""
import argparse
import json
from pathlib import Path
import subprocess
from time import perf_counter

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.targets.character43.active_mesh_pose import sample_active


def run(state, artifact, output):
    source=subprocess.check_output(['git','show','2c2d1a5:src/autospine_workbench/targets/character43/active_mesh_pose.py'],text=True)
    namespace={'__package__':'autospine_workbench.targets.character43'}
    exec(compile(source,'baseline-active-mesh-pose.py','exec'),namespace)
    document=json.loads(AnimatedStore(state).read(artifact)['skeleton.json'])
    name=next(iter(document['animations']));records=[]
    for time in (.05,.1,.15):
        start=perf_counter();before=namespace['sample_active'](document,name,time);old=perf_counter()-start
        start=perf_counter();after=sample_active(document,name,time);new=perf_counter()-start
        assert before==after,'sample output changed'
        records.append(dict(time=time,baseline_seconds=old,current_seconds=new,exact_equal=True))
    result=dict(artifact_sha256=artifact,animation=name,records=records,
                scope='three_cpu_samples_not_full_runtime_or_visual_acceptance')
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--state',type=Path,default=Path('workspace'))
    parser.add_argument('--artifact',required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();run(args.state,args.artifact,args.output)
