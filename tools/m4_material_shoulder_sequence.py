"""Bake source-frame shoulder candidates using verified actual material frames."""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.affine_pose import sample,matrices
from autospine_workbench.targets.character43.shoulder_source import contexts
from autospine_workbench.targets.character43.shoulder_contact_regions import prepare_regions,solve
from autospine_workbench.targets.character43.shoulder_region_validation import resolve_owners,inspect
from autospine_workbench.targets.character43.material_affine_frame import fit
from autospine_workbench.targets.character43.torso_projection_candidate import multiply
from autospine_workbench.targets.character43.deform_addition import entries,local_delta,value,runtime_union_times
from autospine_workbench.targets.character43.numeric_reference import read
from autospine_workbench.targets.character43.runtime_storage_reference import f32


def load(folder):
    receipt=json.loads((folder/'report.json').read_bytes())
    return receipt,AnimatedStore(folder/'isolated-store').read(receipt['candidate_bundle_sha256'])


def run(source,motion_source,output):
    if output.exists():raise ValueError('material_shoulder_output_exists')
    receipt,files=load(source);motion_receipt,motion_files=load(motion_source)
    doc,rows=contexts(files);motion_doc=json.loads(motion_files['skeleton.json']);name='external-motion'
    if (doc['bones']!=motion_doc['bones'] or
            doc['animations'][name]['bones']!=motion_doc['animations'][name]['bones']):
        raise ValueError('material_shoulder_motion_identity_mismatch')
    motion=json.loads(motion_files['motion-ir.json'])
    source_times=sorted({key['tick']/motion['ticks_per_second'] for track in motion['tracks'] for key in track['keys']})
    if not 2<=len(source_times)<=512 or source_times[0]!=0:
        raise ValueError('material_shoulder_source_sample_bound')
    times=sorted({f32(t) for t in source_times});candidate=deepcopy(doc)
    prepared=[(r,prepare_regions(r)) for r in rows];owners=resolve_owners(prepared)
    if owners is None:raise ValueError('material_shoulder_owner_required')
    setup=sample(dict(doc,animations={'setup':{}}),'setup',0)[0]
    rest=matrices(dict(doc,animations={'setup':{}}),'setup',0)['chest']
    output.mkdir(parents=True,exist_ok=False);records=[]
    with (output/'solver.jsonl').open('w',encoding='utf-8') as log:
        for row,p in prepared:
            slot=row['slot'];influences=entries(doc['skins'][0]['attachments'][slot][slot]);keys=[]
            for index,time in enumerate(times):
                world=sample(doc,name,time)[0];transforms=matrices(doc,name,time)
                material,_=fit(setup[owners[slot]],world[owners[slot]])
                points,evidence=solve(row,p,rest,multiply(material,rest),world[slot],harmonic_seed=True)
                record=dict(slot=slot,time=time,**evidence);records.append(record)
                log.write(json.dumps(record)+'\n');log.flush()
                print(json.dumps(dict(slot=slot,index=index,total=len(times),status=evidence['status'])),flush=True)
                keys.append(dict(time=time,vertices=local_delta(doc,influences,transforms,world[slot],points)))
            old=doc['animations'][name].get('attachments',{}).get('default',{}).get(slot,{}).get(slot,{}).get('deform',[])
            bake_times=runtime_union_times(old,keys);size=2*sum(len(r) for r in influences)
            baked=[dict(time=t,vertices=[a+b for a,b in zip(value(old,t,size),value(keys,t,size))]) for t in bake_times]
            candidate['animations'][name].setdefault('attachments',{}).setdefault('default',{})[slot]={slot:{'deform':baked}}
    raw=canonical_bytes(candidate);(output/'skeleton.json').write_bytes(raw)
    report=dict(source_candidate=receipt['candidate_bundle_sha256'],skeleton_sha256=sha256(raw).hexdigest(),
        motion_source_candidate=motion_receipt['candidate_bundle_sha256'],source_times=source_times,
        rows=[dict(slot=row['slot']) for row,p in prepared],material_owners=owners,
        solver_failures=[r for r in records if r['status']!='feasible_candidate'],authority='none',selected=False,
        scope='full_source_frame_trial_requires_dense_validation_and_runtime',
        solver_worktree_sha256=sha256(Path('src/autospine_workbench/targets/character43/boundary_shape_feasible.py').read_bytes()).hexdigest())
    (output/'report.json').write_bytes(canonical_bytes(report))
    dense=sorted({r['time'] for r in read(files)['animations'][name]}|set(source_times)|set(times))
    dense=sorted(set(dense)|{(a+b)/2 for a,b in zip(dense,dense[1:])})
    if len(dense)>16385:raise ValueError('material_shoulder_validation_sample_bound')
    validation=inspect(doc,candidate,prepared,dense,lambda s:print(json.dumps(s),flush=True))
    report['validation']=validation;(output/'report.json').write_bytes(canonical_bytes(report))
    print(json.dumps(dict(solver_failures=len(report['solver_failures']),passed=validation['passed'],frames=len(dense))),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('source','motion_source','output'):p.add_argument(name,type=Path)
    a=p.parse_args();run(a.source,a.motion_source,a.output)
