"""Exercise automatic final-leg repair with real assets and official CPU vertices."""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.final_leg_repair_policy import select
from autospine_workbench.targets.character43.selected_attachment_repair import build
from autospine_workbench.targets.character43.fixed_area_feasibility import FixedAreaInfeasible
from autospine_workbench.targets.character43.affine_pose import sample
from autospine_workbench.targets.character43.numeric_reference import read
from autospine_workbench.targets.character43.runtime_storage_reference import f32


def run(args):
    args.output.mkdir(parents=True,exist_ok=False)
    receipt=json.loads((args.source/'report.json').read_bytes())
    files=AnimatedStore(args.source/'isolated-store').read(receipt['candidate_bundle_sha256'])
    store=AnimatedStore(args.output/'isolated-store');rows=[];name='external-motion'
    for slot in args.slots:
        folder=args.output/slot;folder.mkdir();builder=build
        if slot==args.garment_slot:
            from autospine_workbench.targets.character43.garment_follow_scope import resolve
            from autospine_workbench.targets.character43.garment_follow_candidate import build as garment_build
            request=json.loads((args.source/'request.json').read_bytes())
            character=AnimatedStore(args.garment_state).read(request['character_sha256'])
            scope=resolve(files,character,slot,name,stable_sampling=True)
            builder=lambda f,p,progress:garment_build(f,character,p,progress)
        else:scope=select(files,slot,name)
        if scope is None:
            rows.append(dict(slot=slot,status='strategy_not_applicable',candidate_generated=False))
            continue
        plan=dict(action='local_repair',slot=slot,animation=name,local_solver=scope)
        if slot==args.garment_slot:plan=dict(action='garment_follow',slot=slot,animation=name,garment_follow=scope)
        last=None
        def progress(value):
            nonlocal last
            if value['stage']!=last:
                print(json.dumps({'slot':slot,**value}),flush=True);last=value['stage']
        try:output,evidence,geometry=builder(files,plan,progress)
        except FixedAreaInfeasible as error:
            (folder/'fixed-counterexamples.json').write_bytes(canonical_bytes(error.report))
            rows.append(dict(slot=slot,status=error.report['status'],candidate_generated=False,
                failure_observations=len(error.report['failures']),fixed_triangles=error.report['fixed_triangles']))
            continue
        digest=store.publish(output);assert store.read(digest)==output
        (folder/'skeleton.json').write_bytes(output['skeleton.json'])
        document=json.loads(output['skeleton.json']);report=json.loads(output['motion-repair.json'])
        end=read(output)['animations'][name][-1]['time']
        times=[f32(end*i/128) for i in range(129)]
        checked_slots=[r['slot'] for r in rows if r['status']=='candidate']+[slot] if args.sequence else [slot]
        fixture=dict(source_candidate=receipt['candidate_bundle_sha256'],runtime_sha256=sha256(args.runtime.read_bytes()).hexdigest(),
            skeleton_sha256=sha256(output['skeleton.json']).hexdigest(),skeleton=document,
            atlas=output['skeleton.atlas'].decode(),animation=name,
            samples=[dict(time=t,vertices={s:p for s,p in sample(document,name,t)[0].items() if s in checked_slots}) for t in times],
            reference_bundle=str((store.root/digest).resolve()),reference_frames=report['sample_count'])
        (folder/'numeric-fixture.json').write_bytes(canonical_bytes(fixture))
        checked=subprocess.run([str(args.node),str(Path(__file__).with_name('check-corrective-numeric.mjs')),
            str(folder/'numeric-fixture.json'),str(args.runtime)],check=True,capture_output=True,text=True,timeout=120)
        numeric=json.loads(checked.stdout);(folder/'official-numeric.json').write_bytes(canonical_bytes(numeric))
        value=dict(slot=slot,status='candidate',artifact_sha256=digest,skeleton_sha256=fixture['skeleton_sha256'],
            strategy=scope,before=report['parent_geometry'],after=geometry,official_cpu=numeric,
            contact_status=evidence['contact_status'],sample_count=report['sample_count'],
            candidate_bytes=sum(map(len,output.values())),checked_slots=checked_slots,gpu_status='not_run',visual_status='not_reviewed',
            authority='none',selected=False)
        (folder/'report.json').write_bytes(canonical_bytes(value));rows.append(value)
        (args.output/'progress.json').write_bytes(canonical_bytes(dict(rows=rows,complete=False)))
        print(json.dumps(dict(slot=slot,stage='done',artifact=digest,maximum_error_px=numeric['maximum_error_px'])),flush=True)
        if args.sequence:files=deepcopy(output)
    result=dict(parent_artifact=receipt['candidate_bundle_sha256'],source=str(args.source),sequence=args.sequence,
                rows=rows,authority='none',selected=False,scope='builder_and_cpu_validation_not_gpu_or_visual_acceptance')
    (args.output/'summary.json').write_bytes(canonical_bytes(result))
    print(json.dumps(dict(stage='complete',rows=[dict(slot=r['slot'],status=r['status']) for r in rows])),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','output','node','runtime'):p.add_argument(name,type=Path)
    p.add_argument('slots',nargs='+');p.add_argument('--sequence',action='store_true')
    p.add_argument('--garment-slot');p.add_argument('--garment-state',type=Path)
    args=p.parse_args()
    if args.garment_slot and (not args.garment_state or not args.sequence):p.error('garment step requires state and sequence')
    run(args)
