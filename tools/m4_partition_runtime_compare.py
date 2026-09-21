"""Official Runtime before/after capture for an unchanged-order render partition."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import numpy as np
from PIL import Image
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.automation.sleeve_capture_environment import discover
from autospine_workbench.targets.character43.numeric_reference import write
from autospine_workbench.targets.character43.runtime_storage_reference import build as storage
from autospine_workbench.targets.character43.affine_pose import sample


def run(folder,allow_order_change=False):
    receipt=json.loads((folder/'report.json').read_bytes());raw=(folder/'skeleton.json').read_bytes()
    if sha256(raw).hexdigest()!=receipt['skeleton_sha256']:raise ValueError('partition_capture_skeleton')
    source=AnimatedStore(Path('workspace')).read(receipt['source_artifact_sha256'])
    depth=json.loads(source['motion-depth.json']);times=set()
    for pair in depth['pairs']:
        ticks=[r['tick'] for r in pair['samples']]
        times.update(t/1e6 for t in ticks)
        times.update((a+b)/2e6 for a,b in zip(ticks,ticks[1:]))
    times=sorted(times)
    if len(times)!=receipt['sampled_frames'] or not 1<=len(times)<=512:raise ValueError('partition_capture_times')
    if allow_order_change:
        if receipt.get('profile')!='stable-sampled-region-order-experiment-v1':raise ValueError('order_capture_profile')
        times=sorted(set(times)|{(a+b)/2 for a,b in zip(times,times[1:])})
    scope='sampled_order_candidate_render_comparison_not_visual_acceptance' if allow_order_change else 'unchanged_order_equivalence_not_depth_order_acceptance'
    env=discover(Path.cwd().parent)
    if not env:raise ValueError('official_capture_environment_missing')
    captures={};bundles={}
    for label,skeleton in [('before',source['skeleton.json']),('after',raw)]:
        document=json.loads(skeleton);output=folder/label;output.mkdir(parents=True,exist_ok=True)
        files={n:v for n,v in source.items() if n.endswith('.png') or n=='skeleton.atlas'}
        files['skeleton.json']=skeleton
        files['character-manifest.json']=canonical_bytes(dict(authority='none',production_authorized=False,
            source_artifact_sha256=receipt['source_artifact_sha256'],scope=scope))
        files=write(files,dict(skeleton_sha256=sha256(skeleton).hexdigest(),animations={'external-motion':[
            dict(time=t,vertices=sample(document,'external-motion',t)[0]) for t in times]}))
        store=AnimatedStore(folder/'isolated-store');digest=store.publish(files);bundles[label]=digest
        storage_path=output/'storage.json';storage_path.write_bytes(canonical_bytes(storage(files)))
        command=['node','tools/capture-character-runtime.mjs',str((store.root/digest).resolve()),
                 str((output/'runtime').resolve()),env[1],env[3],'1','{}',str(storage_path.resolve())]
        with (output/'capture.log').open('wb') as log:
            process=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,timeout=300,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if process.returncode:raise ValueError('partition_official_capture_failed:'+label)
        capture=json.loads((output/'runtime/report.json').read_bytes())
        if not capture['passed'] or capture['bundle_sha256']!=digest:raise ValueError('partition_capture_identity')
        if [r['time'] for r in capture['results']]!=times:raise ValueError('partition_capture_time_identity')
        captures[label]=capture
        print(json.dumps(dict(captured=label,frames=len(times))),flush=True)
    for key in ('left','bottom','width','height'):
        if captures['before']['info'][key]!=captures['after']['info'][key]:raise ValueError('partition_capture_camera')
    comparisons=[]
    for index,time in enumerate(times):
        images=[]
        for label in ('before','after'):
            frame=next(r for r in captures[label]['screenshots'] if r['index']==index)
            path=folder/label/'runtime'/frame['file']
            if sha256(path.read_bytes()).hexdigest()!=frame['sha256']:raise ValueError('partition_frame_identity')
            with Image.open(path) as image:images.append(np.asarray(image.convert('RGBA'),dtype=np.int16))
        delta=np.abs(images[0]-images[1])
        comparisons.append(dict(time=time,changed_pixels=int(np.any(delta,axis=2).sum()),max_channel_delta=int(delta.max())))
    report=dict(profile='official-region-order-render-comparison-v1' if allow_order_change else 'official-render-partition-equivalence-v1',source_artifact_sha256=receipt['source_artifact_sha256'],
        partition_receipt_sha256=sha256((folder/'report.json').read_bytes()).hexdigest(),bundles=bundles,
        frames=comparisons,pixel_identical=all(r['changed_pixels']==0 for r in comparisons),
        runtime_max_error_px={k:max(r['max_error_px'] for r in v['results']) for k,v in captures.items()},
        authority='none',selected=False,scope=scope)
    (folder/'runtime-comparison.json').write_bytes(canonical_bytes(report))
    print(json.dumps({k:v for k,v in report.items() if k!='frames'}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('folder',type=Path)
    parser.add_argument('--allow-order-change',action='store_true')
    args=parser.parse_args();run(args.folder,args.allow_order_change)
