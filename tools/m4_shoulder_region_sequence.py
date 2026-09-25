"""Solve a whole source clip with region contacts, then check baked interpolation."""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
import math
from pathlib import Path
from m4_direction_stage_probe import load_stages
from m4_squat_stage_players import stage
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.shoulder_source import contexts
from autospine_workbench.targets.character43.shoulder_contact_regions import prepare_regions,solve
from autospine_workbench.targets.character43.shoulder_region_validation import inspect,resolve_owners
from autospine_workbench.targets.character43.material_affine_frame import fit
from autospine_workbench.targets.character43.torso_projection_candidate import multiply
from autospine_workbench.targets.character43.affine_pose import sample,matrices
from autospine_workbench.targets.character43.deform_addition import entries,local_delta,add
from autospine_workbench.targets.character43.numeric_reference import read


def recheck(source,output):
    receipt=json.loads((source/'report.json').read_bytes());report=json.loads((output/'report.json').read_bytes())
    if receipt['candidate_bundle_sha256']!=report['source']:raise ValueError('shoulder_sequence_recheck_identity')
    files=AnimatedStore(source/'isolated-store').read(report['source']);original,rows=contexts(files)
    trial=json.loads((output/'trial/report.json').read_bytes())
    captured=AnimatedStore(output/'trial/isolated-store').read(trial['candidate_bundle_sha256'])
    doc=json.loads(captured['skeleton.json'])
    if doc!=json.loads((output/'skeleton-trial.json').read_bytes()):raise ValueError('shoulder_sequence_recheck_candidate')
    dense=sorted({r['time'] for r in read(files)['animations']['external-motion']}|set(report['source_times']))
    dense=sorted(set(dense)|{(a+b)/2 for a,b in zip(dense,dense[1:])})
    validation=inspect(original,doc,[(r,prepare_regions(r)) for r in rows],dense)
    evidence=dict(candidate=trial['candidate_bundle_sha256'],source=report['source'],validation=validation)
    (output/'validation-recheck.json').write_bytes(canonical_bytes(evidence))
    print(json.dumps({k:v for k,v in validation.items() if k!='failures'}),flush=True)


def run(source,output,capture,headroom_from=None):
    receipt=json.loads((source/'report.json').read_bytes());identity=receipt['candidate_bundle_sha256']
    _,_,pose,_,_,parent,_=load_stages(receipt['source_job_id'])
    if parent!=receipt['source_candidate_sha256']:raise ValueError('shoulder_sequence_parent')
    files=AnimatedStore(source/'isolated-store').read(identity);original,rows=contexts(files);doc=deepcopy(original)
    prepared=[(row,prepare_regions(row)) for row in rows];owners=resolve_owners(prepared)
    margin=1e-5;headroom_digest=None
    if headroom_from:
        raw=headroom_from.read_bytes();previous_report=json.loads(raw);headroom_digest=sha256(raw).hexdigest()
        if (previous_report['source']!=identity or previous_report['profile']!='shoulder-contact-regions-sequence-v1'
                or previous_report['source_times']!=sorted(set(pose['times'])) or previous_report['solver_failures']
                or previous_report['validation'].get('material_owners')!=owners):
            raise ValueError('shoulder_sequence_headroom_identity')
        ratio=previous_report['validation']['max_region_ratio']
        if not math.isfinite(ratio) or ratio<0:raise ValueError('shoulder_sequence_headroom_ratio')
        margin=max(margin,2*max(0,ratio-1)+1e-5)
        if margin>.05:raise ValueError('shoulder_sequence_headroom_limit')
    name='external-motion';rest=matrices(dict(original,animations={'setup':{}}),'setup',0)['chest']
    records=[];output.mkdir(parents=True,exist_ok=False)
    setup=sample(dict(original,animations={'setup':{}}),'setup',0)[0] if owners is not None else None
    def progress(value):print(json.dumps(value),flush=True)
    times=sorted(set(pose['times']))
    with (output/'solver.jsonl').open('w',encoding='utf8') as log:
        for row,p in prepared:
            slot=row['slot'];influences=entries(doc['skins'][0]['attachments'][slot][slot]);keys=[];previous=None
            for index,time in enumerate(times):
                progress(dict(stage='solve',slot=slot,index=index,total=len(times)))
                sampled=sample(original,name,time)[0];world=sampled[slot];current=matrices(original,name,time)
                contact_frame=current['chest']
                if owners is not None:
                    material,_=fit(setup[owners[slot]],sampled[owners[slot]])
                    contact_frame=multiply(material,rest)
                points,evidence=solve(row,p,rest,contact_frame,world,previous,region_margin=margin)
                previous=(world,points) if evidence['status']=='feasible_candidate' else None
                record=dict(slot=slot,time=time,**evidence);records.append(record);log.write(json.dumps(record)+'\n');log.flush()
                keys.append(dict(time=time,vertices=local_delta(original,influences,current,world,points)))
            target=doc['animations'][name].setdefault('attachments',{}).setdefault('default',{}).setdefault(slot,{}).setdefault(slot,{})
            target['deform']=add(target.get('deform',[]),keys,2*sum(len(r) for r in influences))
    if doc['animations'][name]['bones']!=original['animations'][name]['bones'] or doc['skins']!=original['skins'] or doc['slots']!=original['slots']:
        raise ValueError('shoulder_sequence_bind_or_motion_changed')
    old_times={r['time'] for r in read(files)['animations'][name]};dense=sorted(old_times|set(times))
    dense=sorted(set(dense)|{(a+b)/2 for a,b in zip(dense,dense[1:])})
    validation=inspect(original,doc,prepared,dense,progress)
    report=dict(source=identity,profile='shoulder-contact-regions-sequence-v1',authority='none',selected=False,
        source_times=times,source_reference_frames_preserved=True,solver_failures=[r for r in records if r['status']!='feasible_candidate'],
        validation=validation,region_margin=margin,headroom_source=str(headroom_from) if headroom_from else None,
        headroom_sha256=headroom_digest,scope='sampled_full_clip_not_raster_or_visual_acceptance')
    (output/'report.json').write_bytes(canonical_bytes(report));(output/'skeleton-trial.json').write_bytes(canonical_bytes(doc))
    progress(dict(stage='finished',failures=len(report['solver_failures']),validation={k:v for k,v in validation.items() if k!='failures'}))
    if capture and validation['passed'] and not report['solver_failures']:stage(doc,files,dense,output/'trial',identity)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('output',type=Path);p.add_argument('--capture',action='store_true')
    p.add_argument('--headroom-from',type=Path)
    p.add_argument('--recheck',action='store_true')
    a=p.parse_args()
    if a.recheck:recheck(a.source,a.output)
    else:run(a.source,a.output,a.capture,a.headroom_from)
