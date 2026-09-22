"""Compose explicit source-view torso projection with an exact reach shoulder candidate."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.automation.character_capture import capture
from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.targets.character43.torso_projection_source import anchors,reference_shapes
from autospine_workbench.targets.character43.torso_projection_candidate import build
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.character43.numeric_reference import write,read
from autospine_workbench.targets.character43.torso_projection_validation import contact_preservation
from autospine_workbench.targets.character43.deformation_qa import inspect
from m4_experiment_player_export import export


def run(root,output,index):
    output.mkdir(parents=True,exist_ok=False)
    old=json.loads((root/str(index)/'report.json').read_bytes())
    pose=json.loads((root.parent/str(index)/'yaw-45/pose/report.json').read_bytes())
    files=AnimatedStore(root/str(index)/'isolated-store').read(old['candidate_bundle_sha256'])
    identity=pose['source_identity'];bundle=VerifiedMotionBundleReader(Path('workspace')).load(identity['clip_sha256'],identity['bundle_sha256'])
    frames,ticks=anchors(bundle,pose['fixed_source_yaw_deg']);reference,_=anchors(bundle,0)
    source=reference_shapes(frames,[t/1e6 for t in ticks],reference[0])
    doc=json.loads(files['skeleton.json']);candidate,report=build(doc,'external-motion',source)
    report.update(applied=candidate is not None,source_candidate_sha256=old['candidate_bundle_sha256'],source_identity=identity,
                  yaw_degrees=pose['fixed_source_yaw_deg'],reference_source_yaw=0,
                  reference_assumption='source_initial_zero_yaw_matches_front_artwork',
                  runtime_status='not_evaluated',contact_status='not_evaluated',depth_status='not_evaluated')
    if candidate is None:
        (output/'report.json').write_bytes(canonical_bytes(report));print(report['status']);return
    if {k:v for k,v in doc.items() if k!='animations'}!={k:v for k,v in candidate.items() if k!='animations'}:
        raise ValueError('torso_reference_setup_changed')
    anim=candidate['animations']['external-motion']
    knots=sorted({k['time'] for tracks in anim['bones'].values() for keys in tracks.values() for k in keys}|
        {k['time'] for slots in anim.get('attachments',{}).values() for choices in slots.values() for props in choices.values() for keys in props.values() for k in keys})
    prior=read(files)
    if prior['skeleton_sha256']!=sha256(files['skeleton.json']).hexdigest():raise ValueError('torso_reference_source_reference_mismatch')
    prior_times={r['time'] for r in prior['animations']['external-motion']}
    times=sorted(set(knots)|{(a+b)/2 for a,b in zip(knots,knots[1:])}|prior_times)
    if len(times)>2049:raise ValueError('torso_reference_sample_limit')
    raw=canonical_bytes(candidate)
    isolated={n:v for n,v in files.items() if n.endswith('.png') or n in ('skeleton.atlas','character-manifest.json')}
    isolated['skeleton.json']=raw
    isolated=write(isolated,dict(skeleton_sha256=sha256(raw).hexdigest(),animations={'external-motion':[
        dict(time=t,vertices=sample(candidate,'external-motion',t)[0]) for t in times]}))
    setup=sample(dict(doc,animations={'setup':{}}),'setup',0)[0]
    qa=inspect(isolated,setup_vertices=setup)
    isolated['rig-setup-reference.json']=canonical_bytes(dict(time=0,vertices=setup,skeleton_sha256=sha256(raw).hexdigest()))
    isolated['motion-torso-reference.json']=canonical_bytes(report)
    store=AnimatedStore(output/'isolated-store');digest=store.publish(isolated)
    report.update(candidate_bundle_sha256=digest,geometry_passed=qa['passed'],sampled_frames=len(times),
                  retained_source_check_times=len(prior_times),contact_preservation=contact_preservation(doc,candidate,'external-motion',times))
    (output/'deformation.json').write_bytes(canonical_bytes(qa));(output/'report.json').write_bytes(canonical_bytes(report))
    print(json.dumps(dict(stage='geometry',passed=qa['passed'],frames=len(times))),flush=True)
    result=capture(SimpleNamespace(workspace_root=Path.cwd().parent),store,digest,output,
                   progress=lambda s:print(s,flush=True),cancel_requested=lambda:False,storage_reference=True)
    report['runtime_status']=result['status'];(output/'report.json').write_bytes(canonical_bytes(report))
    export(output)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('root',type=Path);p.add_argument('output',type=Path)
    p.add_argument('--index',type=int,default=0);a=p.parse_args();run(a.root,a.output,a.index)
