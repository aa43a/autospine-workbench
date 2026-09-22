"""Apply reusable shoulder boundary correction to an exact captured motion candidate."""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.character_capture import capture
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.shoulder_boundary_candidate import generate
from autospine_workbench.targets.character43.shoulder_boundary_adaptive import generate as adapt
from autospine_workbench.targets.character43.numeric_reference import read
from m4_experiment_player_export import export
from m4_reach_shoulder_verify import without_deforms


def run(source,output):
    receipt=json.loads((source/'report.json').read_bytes());parent=receipt['candidate_bundle_sha256']
    runtime=json.loads((source/'runtime/report.json').read_bytes())
    if runtime['bundle_sha256']!=parent or runtime['passed'] is not True:
        raise ValueError('motion_shoulder_source_capture_mismatch')
    files=AnimatedStore(source/'isolated-store').read(parent)
    output.mkdir(parents=True,exist_ok=False);store=AnimatedStore(output/'isolated-store')
    progress=lambda s:print(json.dumps(dict(stage=s)),flush=True)
    candidate,report=generate(files,parent,progress=progress)
    trial=store.publish(candidate)
    return finish(files,parent,receipt,candidate,report,trial,output,store,progress)


def finish(files,parent,receipt,candidate,report,trial,output,store,progress):
    if report['status']=='blocked':
        try:candidate,report=adapt(files,parent,candidate,trial,progress=progress)
        except ValueError as error:
            if str(error)!='shoulder_adaptive_sample_budget':raise
            report=dict(report,adaptive_failure=str(error),status='blocked',adaptive_trial_sha256=trial)
    before,after=[json.loads(f['skeleton.json']) for f in (files,candidate)]
    if any(before[k]!=after[k] for k in ('bones','slots','skins')):
        raise ValueError('motion_shoulder_bind_changed')
    for name,animation in before['animations'].items():
        if without_deforms(animation)!=without_deforms(after['animations'][name]):
            raise ValueError('motion_shoulder_motion_changed')
    if any(candidate[n]!=raw for n,raw in files.items() if n.endswith(('.png','.atlas'))):
        raise ValueError('motion_shoulder_art_changed')
    old,new=read(files),read(candidate)
    for name,frames in old['animations'].items():
        if {f['time'] for f in frames}-{f['time'] for f in new['animations'][name]}:
            raise ValueError('motion_shoulder_sample_loss')
    artifact=store.publish(candidate)
    report.update(candidate_bundle_sha256=artifact,source_candidate_sha256=parent,
                  source_job_id=receipt['source_job_id'],source_sample_times_preserved=True,
                  non_deform_motion_and_art_unchanged=True)
    (output/'report.json').write_bytes(canonical_bytes(report))
    try:
        result=capture(SimpleNamespace(workspace_root=Path.cwd().parent),store,artifact,output,
                       progress=progress,cancel_requested=lambda:False,storage_reference=True)
    except ValueError as error:
        report.update(runtime_status='capture_failed',runtime_failure=str(error))
        (output/'report.json').write_bytes(canonical_bytes(report))
        raise
    report['runtime_status']=result['status'];(output/'report.json').write_bytes(canonical_bytes(report))
    export(output)
    print(json.dumps({k:v for k,v in report.items() if k!='records'}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();run(a.source,a.output)
