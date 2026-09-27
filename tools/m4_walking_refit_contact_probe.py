"""Retest complete calibrated walking candidates; preserve failed geometry."""
import argparse
import json
from hashlib import sha256
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.motion_moving_ankles import check
from autospine_workbench.targets.character43.moving_ankle_candidate import build
from autospine_workbench.targets.character43.source_ankle_targets import targets
from autospine_workbench.targets.character43.affine_pose import matrices, sample
from autospine_workbench.targets.character43.numeric_reference import write as write_reference
from autospine_workbench.targets.character43.deformation_qa import inspect


def run(source, output, artifact_state=Path('workspace')):
    parent = json.loads((source/'report.json').read_text(encoding='utf-8'))
    files = AnimatedStore(artifact_state).read(parent['source_artifact'])
    original = json.loads(files['motion-moving-ankles.json'])
    reference = original['final_check']['limit_px']/.01
    setup = json.loads(files['rig-setup-reference.json'])['vertices']
    summaries = {}
    output.mkdir()
    for label in ('absolute_legs_pelvis_pivot', 'absolute_projection_pelvis_pivot'):
        document = json.loads((source/(label+'.json')).read_text(encoding='utf-8'))
        from autospine_workbench.resolved_project import canonical_sha256
        if canonical_sha256(document) != parent['variants'][label]['skeleton_sha256']:
            raise ValueError('calibrated_candidate_changed')
        name = next(iter(document['animations']))
        pose = matrices(document, name, 0)
        trajectory = targets(parent['source_observation'], [pose['foot_'+s][4:6] for s in ('l','r')], reference)
        times = sorted({k.get('time',0) for row in document['animations'][name]['bones'].values()
                        for keys in row.values() for k in keys})
        candidate, report = build(document, name, trajectory, times, reference)
        report['trajectory'] = trajectory
        report['applied'] = candidate is not None
        report['parent_skeleton_sha256'] = canonical_sha256(document)
        if candidate is not None:
            samples = sorted(set(times)|{(a+b)/2 for a,b in zip(times,times[1:])})
            report['final_check'] = check(candidate, name, report, samples, reference)
            raw = json.dumps(candidate,sort_keys=True,separators=(',',':')).encode()
            frames = [dict(time=t,vertices=sample(candidate,name,t)[0]) for t in samples]
            qa_files = write_reference({'skeleton.json':raw},dict(skeleton_sha256=sha256(raw).hexdigest(),animations={name:frames}))
            geometry = inspect(qa_files,setup_vertices=setup)
            report['geometry'] = geometry
            with (output/(label+'.json')).open('x',encoding='utf-8') as stream:
                json.dump(candidate,stream)
        with (output/(label+'-report.json')).open('x',encoding='utf-8') as stream:
            json.dump(report,stream,indent=2)
        summaries[label] = dict(applied=report['applied'], final_check=report.get('final_check'),
            geometry_passed=report.get('geometry',{}).get('passed'),
            failing_slots=[r['slot'] for r in report.get('geometry',{}).get('records',[]) if not r['passed']])
    print(json.dumps(summaries))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    parser.add_argument('output',type=Path)
    parser.add_argument('--artifact-state',type=Path,default=Path('workspace'))
    args=parser.parse_args()
    run(args.source,args.output,args.artifact_state)
