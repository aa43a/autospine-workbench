"""Offline entry for the source-bound worker diagnostic, with optional midpoints."""
import argparse
import json
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import read_document
from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.targets.character43.local_depth_analysis import analyze
from m4_motion_cohort import api


def run(job,output,*,midpoints=False,pixelwise=False):
    task=api('http://127.0.0.1:8918','/api/motions/'+job)
    if task['status']!='succeeded' or task.get('kind')!='adapt':raise ValueError('completed_target_required')
    request=read_document(Path('workspace/jobs/motion-intake-v1')/job/'request.json')
    artifact=task['result']['artifact_sha256'];files=AnimatedStore(Path('workspace')).read(artifact)
    identity=request['motion_identity']
    bundle=VerifiedMotionBundleReader(Path('workspace')).load(identity['clip_sha256'],identity['bundle_sha256'])
    result=analyze(files,artifact,bundle,request,midpoints=midpoints,pixelwise=pixelwise)
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('records','hand_mesh_axes','causes')}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('job');parser.add_argument('output',type=Path)
    parser.add_argument('--midpoints',action='store_true');parser.add_argument('--pixelwise',action='store_true')
    args=parser.parse_args();run(args.job,args.output,midpoints=args.midpoints,pixelwise=args.pixelwise)
