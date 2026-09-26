"""Exercise the workbench builder and official CPU vertices; never open a browser."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.character43.garment_follow_scope import resolve
from autospine_workbench.targets.character43.garment_follow_candidate import build
from autospine_workbench.targets.character43.runtime_storage_reference import f32


def run(args):
    args.output.mkdir(parents=True, exist_ok=False); rows=[]
    runtime_digest=sha256(args.runtime.read_bytes()).hexdigest()
    for source in args.sources:
        request=json.loads((source/'request.json').read_bytes())
        receipt=json.loads((source/'report.json').read_bytes())
        character=AnimatedStore(args.state).read(request['character_sha256'])
        files=AnimatedStore(source/'isolated-store').read(receipt['candidate_bundle_sha256'])
        for declaration in json.loads(character['skirt-trial.json'])['rows']:
            slot=declaration['layer_id']; name='external-motion'
            scope=dict(resolve(files,character,slot,name),character_sha256=request['character_sha256'])
            plan=dict(slot=slot,animation=name,garment_follow=scope)
            folder=args.output/(source.name+'-'+slot);folder.mkdir()
            last=None
            def progress(value):
                nonlocal last
                if value['stage']!=last:
                    print(json.dumps(dict(source=source.name,slot=slot,**value)),flush=True);last=value['stage']
            output,evidence,geometry=build(files,character,plan,progress)
            store=AnimatedStore(args.output/'isolated-store');digest=store.publish(output)
            assert store.read(digest)==output
            (folder/'skeleton.json').write_bytes(output['skeleton.json'])
            document=json.loads(output['skeleton.json']);report=json.loads(output['motion-repair.json'])
            end=json.loads(files['motion-torso-projection.json'])['source']['records'][-1]['time']
            samples=[dict(time=f32(end*i/128),vertices={slot:sample(document,name,f32(end*i/128))[0][slot]}) for i in range(129)]
            fixture=dict(source_candidate=receipt['candidate_bundle_sha256'],runtime_sha256=runtime_digest,
                skeleton_sha256=sha256(output['skeleton.json']).hexdigest(),skeleton=document,
                atlas=output['skeleton.atlas'].decode(),animation=name,samples=samples,
                reference_bundle=str((store.root/digest).resolve()),reference_frames=report['sample_count'])
            (folder/'numeric-fixture.json').write_bytes(canonical_bytes(fixture))
            checked=subprocess.run([str(args.node),str(Path(__file__).with_name('check-corrective-numeric.mjs')),
                str(folder/'numeric-fixture.json'),str(args.runtime)],check=True,capture_output=True,text=True,timeout=120)
            numeric=json.loads(checked.stdout);(folder/'official-numeric.json').write_bytes(canonical_bytes(numeric))
            value=dict(source=source.name,slot=slot,parent_artifact=receipt['candidate_bundle_sha256'],
                artifact_sha256=digest,skeleton_sha256=fixture['skeleton_sha256'],
                candidate_bytes=sum(map(len,output.values())),candidate_files=len(output),
                before=report['parent_geometry'],after=geometry,garment_follow=report['garment_follow'],
                official_cpu=numeric,contact_status=evidence['contact_status'],
                gpu_status='not_run',visual_status='not_reviewed',authority='none',selected=False)
            (folder/'report.json').write_bytes(canonical_bytes(value));rows.append(value)
            (args.output/'summary.json').write_bytes(canonical_bytes(dict(rows=rows,authority='none',selected=False)))
            print(json.dumps(dict(source=source.name,slot=slot,stage='done',artifact=digest,
                selected_geometry=[r for r in geometry['records'] if r['slot']==slot],
                failed=[r['slot'] for r in geometry['records'] if not r['passed']],
                cpu_maximum=numeric['maximum_error_px'])),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('state','output','node','runtime'):p.add_argument(name,type=Path)
    p.add_argument('sources',nargs='+',type=Path)
    run(p.parse_args())
