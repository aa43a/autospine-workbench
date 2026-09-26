"""Link an isolated deform-only corrective to its exact motion/character baseline."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
from threading import RLock
from types import SimpleNamespace
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.motion_related_candidates import register
from autospine_workbench.automation.motion_related_evidence import inspect
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.resolved_project import canonical_sha256
from m4_motion_cohort import api
from m4_corrective_geometry_check import required_times
from autospine_workbench.targets.character43.numeric_reference import read as reference


def receipt_for(request, original_receipt, original_files, corrected_receipt, files, runtime):
    if (original_receipt['request_sha256']!=canonical_sha256(request)
            or original_receipt['motion_identity']!=request['motion_identity']
            or original_receipt['character_sha256']!=request['character_sha256']):
        raise ValueError('corrective_link_source_identity')
    proof=json.loads(files['corrective-provenance.json'])
    if (proof['skeleton_sha256']!=sha256(files['skeleton.json']).hexdigest()
            or proof.get('partial_time_batch') is True):
        raise ValueError('corrective_link_incomplete_proof')
    before=json.loads(original_files['skeleton.json']);after=json.loads(files['skeleton.json'])
    prior_times=[f['time'] for f in reference(original_files)['animations']['external-motion']]
    required=required_times(after,'external-motion',prior_times,{})
    measured=[f['time'] for f in reference(files)['animations']['external-motion']]
    if not set(required)<=set(measured):raise ValueError('corrective_link_sampling_incomplete')
    selected=proof['selected_slots']
    if not selected or len(set(selected))!=len(selected):raise ValueError('corrective_link_slots_invalid')
    for doc in (before,after):
        tracks=doc['animations']['external-motion']['attachments']['default']
        for slot in selected:
            if slot not in tracks:raise ValueError('corrective_link_slot_missing')
            # Only deform is permitted; preserve all other attachment properties.
            for properties in tracks[slot].values():properties.pop('deform',None)
    if before!=after or original_files['character-manifest.json']!=files['character-manifest.json']:
        raise ValueError('corrective_link_unrelated_change')
    textures={k:v for k,v in original_files.items() if k.endswith('.png') or k=='skeleton.atlas'}
    if textures!={k:v for k,v in files.items() if k.endswith('.png') or k=='skeleton.atlas'}:
        raise ValueError('corrective_link_texture_changed')
    return dict(corrected_receipt,source_identity=request['motion_identity'],sampled_frames=len(runtime['results']),
        source_request_sha256=canonical_sha256(request),source_artifact=original_receipt['candidate_bundle_sha256'],
        link_proof='identical_character_textures_and_bone_motion_only_named_deform_changed',
        selected_slots=selected,remaining_checks=['contact','depth','visual'],
        authority='none',selected=False,production_authorized=False)


def run(state,job,source,corrected,output,do_register=False,contact_audit=None):
    if not re.fullmatch('motion-[a-f0-9]{32}',job):raise ValueError('corrective_link_job_invalid')
    if output.exists():raise ValueError('corrective_link_output_exists')
    read=lambda p:json.loads(p.read_bytes())
    original=read(source/'report.json');final=read(corrected/'report.json')
    source_files=AnimatedStore(source/'isolated-store').read(original['candidate_bundle_sha256'])
    files=AnimatedStore(corrected/'isolated-store').read(final['candidate_bundle_sha256'])
    runtime=read(corrected/'runtime/report.json');request=read(source/'request.json')
    receipt=receipt_for(request,original,source_files,final,files,runtime)
    if contact_audit is not None:
        receipt['contact_audit']=read(contact_audit)
    baseline=read(state/'jobs/motion-intake-v1'/job/'request.json')
    evidence=inspect(baseline,AnimatedStore(state).read(baseline['character_sha256']),files,receipt,runtime)
    result=dict(receipt=receipt,evidence=evidence,registered=False)
    if do_register:
        manager=SimpleNamespace(state_root=state,_lock=RLock(),projects=SimpleNamespace(workspace_root=Path.cwd().parent),
            folder=lambda _:state/'jobs/motion-intake-v1'/job,
            get=lambda _:api('http://127.0.0.1:8918','/api/motions/'+job))
        result.update(registered=True,registration_sha256=register(manager,job,files,receipt,runtime))
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('xb') as handle:handle.write(canonical_bytes(result))
    print(json.dumps(dict(registered=result['registered'],registration=result.get('registration_sha256'),
        candidate=evidence['candidate_sha256'],samples=evidence['sampled_frames'])))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('state',type=Path);p.add_argument('job')
    for name in ('source','corrected','output'):p.add_argument(name,type=Path)
    p.add_argument('--register',action='store_true');p.add_argument('--contact-audit',type=Path);a=p.parse_args()
    run(a.state,a.job,a.source,a.corrected,a.output,a.register,a.contact_audit)
