"""Replay an exact rejected support proposal without adopting it."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.support_proposal_replay import replay
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.character43.numeric_reference import write
from autospine_workbench.targets.character43.deformation_qa import inspect
from autospine_workbench.automation.motion_target_pose import final_times


def run(folder,output):
    receipt=json.loads((folder/'report.json').read_bytes())
    files=AnimatedStore(folder/'isolated-store').read(receipt['candidate_bundle_sha256'])
    contact=json.loads(files['motion-contact.json'])
    attempt=contact['phase_attempt']
    name='external-motion';doc=replay(json.loads(files['skeleton.json']),name,contact)
    times=final_times(doc,name,[r['time'] for r in attempt['rows']]);raw=canonical_bytes(doc)
    trial=write({'skeleton.json':raw},dict(skeleton_sha256=sha256(raw).hexdigest(),
        animations={name:[dict(time=t,vertices=sample(doc,name,t)[0]) for t in times]}))
    setup=json.loads(files['rig-setup-reference.json'])['vertices']
    qa=inspect(trial,setup_vertices=setup)
    from autospine_workbench.targets.character43.projected_area_sampling import inspect as projected
    proxy=projected(doc,name,[r['slot'] for r in qa['records'] if not r['passed']])
    report=dict(profile='rejected-support-geometry-probe-v1',authority='none',selected=False,
        source_candidate_sha256=receipt['candidate_bundle_sha256'],proposal_skeleton_sha256=sha256(raw).hexdigest(),
        sampled_frames=len(times),inversion_samples=sum(r['inversion_samples'] for r in qa['records']),
        failing_records=[r for r in qa['records'] if not r['passed']],
        projected_reference=proxy,
        limitation='proposal_replay_not_runtime_or_visual_acceptance')
    with output.open('xb') as handle:handle.write(canonical_bytes(report))
    print(json.dumps({k:v for k,v in report.items() if k not in ('failing_records','projected_reference')}))
    print(json.dumps(dict(projected_failure_samples=len(proxy['failures']))))
    for row in report['failing_records']:
        print(json.dumps({k:v for k,v in row.items() if k in ('slot','inversion_samples','min_area_ratio','max_area_ratio','max_edge_stretch')}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('folder',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();run(a.folder,a.output)
