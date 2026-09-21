"""Create an isolated torso-shape candidate from an exact existing motion job."""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import subprocess

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes,read_document
from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.targets.character43.motion_rotation_status import build as verify_source
from autospine_workbench.targets.character43.torso_projection_source import anchors,shapes
from autospine_workbench.targets.character43.torso_projection_candidate import build
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.character43.numeric_reference import write
from autospine_workbench.targets.character43.deformation_qa import inspect
from autospine_workbench.targets.character43.runtime_storage_reference import build as storage
from autospine_workbench.automation.sleeve_capture_environment import discover
from m4_motion_cohort import api


def run(job,output,capture=False):
    current=api('http://127.0.0.1:8918','/api/motions/'+job)
    if current.get('kind')!='adapt' or current['status']!='succeeded': raise ValueError('completed_candidate_required')
    request=read_document(Path('workspace/jobs/motion-intake-v1')/job/'request.json')
    identity=request['motion_identity']; artifact=current['result']['artifact_sha256']
    files=AnimatedStore(Path('workspace')).read(artifact)
    bundle=VerifiedMotionBundleReader(Path('workspace')).load(identity['clip_sha256'],identity['bundle_sha256'])
    verify_source(files,artifact,bundle,request)
    observed,ticks=anchors(bundle,request.get('projection',{}).get('yaw_degrees',0))
    report=shapes(observed,[t/1e6 for t in ticks])
    clip=request.get('clip')
    if clip:
        start,end=clip['start_frame'],clip['end_frame']; origin=ticks[start]/1e6
        report['records']=[dict(r,time=r['time']-origin) for r in report['records'][start:end+1]]
        report['source_clip']=clip
    document=json.loads(files['skeleton.json']); animation='external-motion'
    candidate,receipt=build(document,animation,report)
    receipt.update(job_id=job,source_artifact_sha256=artifact,motion_identity=identity,
                   source_skeleton_sha256=sha256(files['skeleton.json']).hexdigest())
    output.mkdir(parents=True,exist_ok=True)
    if candidate is None:
        (output/'report.json').write_bytes(canonical_bytes(receipt))
        print(json.dumps(dict(status=receipt['status'],failures=len(receipt['failures']))),flush=True)
        return
    if {k:v for k,v in candidate.items() if k!='animations'}!={k:v for k,v in document.items() if k!='animations'}:
        raise ValueError('torso_setup_changed')
    raw=canonical_bytes(candidate); digest=sha256(raw).hexdigest()
    times=sorted({r['time'] for r in report['records']} |
        {k['time'] for slots in candidate['animations'][animation].get('attachments',{}).values()
         for choices in slots.values() for props in choices.values() for keys in props.values() for k in keys})
    times=sorted(set(times)|{(a+b)/2 for a,b in zip(times,times[1:])})
    reference=dict(skeleton_sha256=digest,animations={animation:[dict(time=t,vertices=sample(candidate,animation,t)[0]) for t in times]})
    isolated={n:data for n,data in files.items() if n.endswith('.png') or n=='skeleton.atlas'}
    isolated.update({'skeleton.json':raw,'character-manifest.json':canonical_bytes(dict(authority='none',
        production_authorized=False,source_artifact_sha256=artifact,scope=receipt['scope']))})
    isolated=write(isolated,reference)
    setup=deepcopy(document);setup['animations']={animation:{'bones':{}}}
    qa=inspect(isolated,setup_vertices=sample(setup,animation,0)[0])
    receipt.update(skeleton_sha256=digest,geometry_passed=qa['passed'],runtime_status='not_evaluated',
                   contact_status='not_evaluated',depth_status='not_evaluated')
    (output/'skeleton.json').write_bytes(raw);(output/'deformation.json').write_bytes(canonical_bytes(qa))
    store=AnimatedStore(output/'isolated-store');address=store.publish(isolated)
    receipt['candidate_bundle_sha256']=address
    if capture:
        options=discover(Path.cwd().parent)
        if not options:raise ValueError('official_capture_environment_missing')
        storage_path=output/'storage.json';storage_path.write_bytes(canonical_bytes(storage(isolated)))
        command=['node','tools/capture-character-runtime.mjs',str((store.root/address).resolve()),
            str((output/'runtime').resolve()),options[1],options[3],'1','{}',str(storage_path.resolve())]
        (output/'report.json').write_bytes(canonical_bytes(receipt))
        with (output/'capture.log').open('wb') as log:
            result=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,timeout=600,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        receipt['runtime_status']='captured' if result.returncode==0 else 'capture_failed'
    (output/'report.json').write_bytes(canonical_bytes(receipt))
    print(json.dumps(dict(geometry=qa['passed'],runtime=receipt['runtime_status'],
        frames=len(times),changed_slots=receipt['changed_slots'],max_displacement=receipt['maximum_influence_displacement_px'])),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('job');parser.add_argument('output',type=Path);parser.add_argument('--capture',action='store_true')
    args=parser.parse_args();run(args.job,args.output,args.capture)
