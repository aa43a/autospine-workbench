"""Fresh ankle/contact measurements for a proven deform-only corrective."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.motion_moving_ankles import check
from autospine_workbench.automation.motion_related_evidence import inspect
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.targets.character43.final_motion_contact import for_candidate
from autospine_workbench.targets.character43.numeric_reference import read as reference
from m4_register_corrective_candidate import receipt_for


def measure(source, files, artifact, runtime):
    before=json.loads(source['skeleton.json'])
    report=json.loads(source['motion-moving-ankles.json'])
    if report['final_check']['skeleton_sha256']!=canonical_sha256(before):
        raise ValueError('corrective_contact_source_skeleton_mismatch')
    # This wrapper may measure only the already-proven deform-only relation.
    document=json.loads(files['skeleton.json'])
    if document['bones']!=before['bones'] or document['animations']['external-motion']['bones']!=before['animations']['external-motion']['bones']:
        raise ValueError('corrective_contact_bone_motion_changed')
    inputs=dict(files)
    for name in ('motion-ir.json','motion-contact.json','motion-review.json'):
        inputs[name]=source[name]
    contact=for_candidate(inputs,artifact,runtime)
    times=[f['time'] for f in reference(files)['animations']['external-motion']]
    length=json.loads(source['motion-review.json'])['reference_length_px']
    moving=check(document,'external-motion',report,times,length)
    return dict(profile='corrective-contact-audit-v1',artifact_sha256=artifact,
        source_skeleton_sha256=sha256(source['skeleton.json']).hexdigest(),
        source_trajectory_sha256=canonical_sha256(report['trajectory']),
        source_contact_sha256=sha256(source['motion-contact.json']).hexdigest(),
        moving_ankles=moving,contact=contact,remaining_checks=['depth','visual','mesh_sole_contact'],
        authority='none',selected=False,production_authorized=False,
        scope='fresh_cpu_bone_proxy_not_deformed_mesh_sole_or_visual_acceptance')


def run(state, source, corrected, output):
    if output.exists():raise ValueError('corrective_contact_output_exists')
    read=lambda p:json.loads(p.read_bytes())
    original=read(source/'report.json');final=read(corrected/'report.json')
    old=AnimatedStore(source/'isolated-store').read(original['candidate_bundle_sha256'])
    files=AnimatedStore(corrected/'isolated-store').read(final['candidate_bundle_sha256'])
    request=read(source/'request.json');runtime=read(corrected/'runtime/report.json')
    receipt=receipt_for(request,original,old,final,files,runtime)
    inspect(request,AnimatedStore(state).read(request['character_sha256']),files,receipt,runtime)
    result=measure(old,files,final['candidate_bundle_sha256'],runtime)
    result['runtime_report_sha256']=canonical_sha256(runtime)
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('xb') as f:f.write(canonical_bytes(result))
    print(json.dumps(dict(samples=result['moving_ankles']['samples'],
        moving=result['moving_ankles'],contact_status=result['contact']['status'],
        drift=result['contact']['after']['max_drift_px'])))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('state','source','corrected','output'):p.add_argument(name,type=Path)
    a=p.parse_args();run(a.state,a.source,a.corrected,a.output)
