"""Capture exact solved shoulder poses as static diagnostic snapshots, not animation."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
from m4_squat_stage_players import stage
from m4_candidate_comparison import run as compare
from m4_experiment_player_export import export
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.targets.character43.affine_pose import sample,matrices
from autospine_workbench.targets.character43.skirt_candidate import inverse


def run(source,probe,output,time):
    receipt=json.loads((source/'report.json').read_bytes());evidence=json.loads((probe/'report.json').read_bytes())
    identity=receipt['candidate_bundle_sha256']
    if evidence['source']!=identity:raise ValueError('shoulder_snapshot_identity')
    records=[r for r in evidence['rows'] if r.get('time')==time]
    if len(records)!=2 or any(r['status']!='feasible_candidate' for r in records):raise ValueError('shoulder_snapshot_unverified_pose')
    files=AnimatedStore(source/'isolated-store').read(identity);original=json.loads(files['skeleton.json'])
    points=sample(original,'external-motion',time)[0];root=next(i for i,b in enumerate(original['bones']) if b['name']=='root')
    rest=matrices(dict(original,animations={'setup':{}}),'setup',0)['root']
    output.mkdir(parents=True,exist_ok=False)
    for label in ('before','after'):
        doc=deepcopy(original);posed=deepcopy(points)
        if label=='after':
            for row in records:posed[row['slot']]=row['points']
        for slot in doc['slots']:
            mesh=doc['skins'][0]['attachments'][slot['name']][slot['attachment']]
            mesh['vertices']=[v for p in posed[slot['name']] for v in (1,root,*inverse(rest,p),1.)]
        doc['animations']={'external-motion':{'bones':{'root':{'rotate':[{'time':0.,'value':0.},{'time':1.,'value':0.}]}}}}
        folder=output/label
        try:stage(doc,files,[0.,1.],folder,identity)
        except ValueError as error:
            # A posed snapshot is deliberately not an axis-aligned source setup.
            # Keep that failed setup comparison; require the actual numeric
            # capture to have completed for this exact snapshot before export.
            if str(error)!='character_runtime_capture_failed':raise
            log=(folder/'capture-1.log').read_text(encoding='utf8')
            if 'character_setup_source_transform_unsupported' not in log:raise
            runtime=json.loads((folder/'runtime/report.json').read_bytes());record=json.loads((folder/'report.json').read_bytes())
            if runtime.get('passed') is not True or runtime['bundle_sha256']!=record['candidate_bundle_sha256']:raise
            record.update(scope='static_posed_snapshot_only_not_setup_validation',setup_source_comparison='unsupported_posed_snapshot',runtime_status='numeric_passed')
            (folder/'report.json').write_text(json.dumps(record),encoding='utf8');export(folder)
    compare(output/'before',output/'after',output/'comparison',f'Alice 肩部 {time:.6f}s 静态姿态对照（不是完整动画）')
    (output/'snapshot-source.json').write_text(json.dumps(dict(source=identity,source_time=time,scope='static_pose_baked_into_setup_not_new_rig_or_animation'),indent=2),encoding='utf8')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('source','probe','output'):p.add_argument(key,type=Path)
    p.add_argument('--time',type=float,required=True);a=p.parse_args();run(a.source,a.probe,a.output,a.time)
