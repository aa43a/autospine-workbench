"""Replay an exact rejected support proposal without adopting it."""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.spine43.continuous_pose import interpolate
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.character43.numeric_reference import write
from autospine_workbench.targets.character43.deformation_qa import inspect
from autospine_workbench.automation.motion_target_pose import final_times


def run(folder,output):
    receipt=json.loads((folder/'report.json').read_bytes())
    files=AnimatedStore(folder/'isolated-store').read(receipt['candidate_bundle_sha256'])
    contact=json.loads(files['motion-contact.json'])
    if contact['selected'] or sha256(files['skeleton.json']).hexdigest()!=contact['input_skeleton_sha256']:
        raise ValueError('support_probe_base_changed')
    attempt=contact['phase_attempt']
    if attempt['status']!='candidate':raise ValueError('support_probe_no_complete_proposal')
    doc=json.loads(files['skeleton.json']);name='external-motion'
    base=deepcopy(doc['animations'][name]['bones']);tracks=doc['animations'][name]['bones']
    tracks['root']['translate']=[]
    names=('thigh_l','calf_l','thigh_r','calf_r')
    for n in names:tracks[n]['rotate']=[]
    root=[dict(time=k['time'],vertices=[k['x'],k['y']]) for k in base['root']['translate']]
    for row in attempt['rows']:
        t=row['time'];xy=interpolate(root,t,'vertices')
        tracks['root']['translate'].append(dict(time=t,x=xy[0]+row['root_shift'][0],y=xy[1]+row['root_shift'][1]))
        for n in names:
            angle=interpolate(base[n]['rotate'],t,'value')+row['angles'][n]
            tracks[n]['rotate'].append(dict(time=t,value=angle))
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
