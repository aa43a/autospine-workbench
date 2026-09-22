"""Build a separately stored shoulder transition experiment and check all source times."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.automation.character_capture import capture
from autospine_workbench.targets.character43.shoulder_axis_transition import propose
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.character43.numeric_reference import write
from autospine_workbench.targets.character43.deformation_qa import inspect


def run(artifact, output, capture_runtime=False):
    files = AnimatedStore(Path('workspace')).read(artifact)
    document = json.loads(files['skeleton.json']); name = 'external-motion'
    candidate, report = propose(document)
    if not report['records']:
        raise ValueError('shoulder_probe_no_eligible_vertices')
    setup, _ = sample(dict(document, animations={'setup': {}}), 'setup', 0)
    times = sorted({k['time'] for tracks in candidate['animations'][name]['bones'].values()
                    for keys in tracks.values() for k in keys})
    if not times or len(times) > 4096:
        raise ValueError('shoulder_probe_time_budget')
    times = sorted(set(times + [(a+b)/2 for a,b in zip(times,times[1:])]))
    raw = canonical_bytes(candidate); digest = sha256(raw).hexdigest()
    selected = {n:v for n,v in files.items() if n.endswith('.png') or n in ('skeleton.atlas','character-manifest.json')}
    manifest=json.loads(selected['character-manifest.json'])
    manifest.update(profile=report['profile'],source_candidate_sha256=artifact,authority='none',production_authorized=False)
    selected['character-manifest.json']=canonical_bytes(manifest)
    selected['shoulder-transition.json']=canonical_bytes(dict(report,source_candidate_sha256=artifact))
    selected['skeleton.json'] = raw
    selected['rig-setup-reference.json'] = canonical_bytes(dict(skeleton_sha256=digest, vertices=setup, time=0))
    selected = write(selected, dict(skeleton_sha256=digest, animations={name:[
        dict(time=t,vertices=sample(candidate,name,t)[0]) for t in times]}))
    qa = inspect(selected,setup_vertices=setup)
    original=write(dict(selected,**{'skeleton.json':files['skeleton.json']}),
        dict(skeleton_sha256=sha256(files['skeleton.json']).hexdigest(),animations={name:[
            dict(time=t,vertices=sample(document,name,t)[0]) for t in times]}))
    before=inspect(original,setup_vertices=setup)
    changed={r['slot'] for r in report['records']}
    report['baseline_changed_slot_geometry']=[r for r in before['records'] if r['slot'] in changed]
    report['changed_slot_geometry_passed']=all(r['passed'] for r in qa['records'] if r['slot'] in changed)
    report['status']='candidate_requires_review' if report['changed_slot_geometry_passed'] else 'rejected_geometry'
    output.mkdir(parents=True,exist_ok=False)
    store = AnimatedStore(output/'isolated-store'); target = store.publish(selected)
    report.update(source_candidate_sha256=artifact,candidate_bundle_sha256=target,
                  sampled_frames=len(times),geometry=qa,contact_status='not_evaluated',runtime_status='not_evaluated')
    if capture_runtime:
        result = capture(SimpleNamespace(workspace_root=Path.cwd().parent),store,target,output,
                         progress=lambda s:print(s,flush=True),cancel_requested=lambda:False,storage_reference=True)
        report['runtime_status'] = result['status']
    (output/'report.json').write_bytes(canonical_bytes(report))
    print(json.dumps(dict(candidate=target,frames=len(times),changed=[(r['slot'],len(r['changed'])) for r in report['records']],
        geometry_passed=qa['passed'],runtime_status=report['runtime_status'])),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact');p.add_argument('output',type=Path)
    p.add_argument('--capture',action='store_true');a=p.parse_args();run(a.artifact,a.output,a.capture)
