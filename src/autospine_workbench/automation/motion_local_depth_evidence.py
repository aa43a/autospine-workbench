"""Immutable supplemental diagnostics; never change candidate readiness."""
from hashlib import sha256
import json
from .animated_store import AnimatedStore
from .storage_io import canonical_bytes, publish_document, read_document, directory
from ..resolved_project import canonical_sha256
from ..targets.character43.local_depth_summary import summarize
from ..targets.character43.depth_triangle_summary import operator_summary


def registered(folder):
    old=folder/'local-depth-evidence.json'
    entries=set(read_document(old)['entries']) if old.exists() else set()
    journal=folder/'local-depth-evidence'
    if journal.exists():
        directory(journal)
        for path in journal.glob('*.json'):
            value=read_document(path)
            if path.stem!=value['digest']:raise ValueError('local_depth_registration_identity')
            entries.add(value['digest'])
            if len(entries)>32:raise ValueError('local_depth_evidence_limit')
    return sorted(entries)


def publish(root, folder, request, artifact, report):
    if (report.get('job_id')!=request['job_id'] or report.get('artifact_sha256')!=artifact
            or report.get('authority')!='none' or report.get('selected') is not False):
        raise ValueError('local_depth_report_identity')
    files=AnimatedStore(root).read(artifact)
    operator_summary(report['records'])  # Validate optional traces before registration.
    value=dict(artifact_sha256=artifact,skeleton_sha256=sha256(files['skeleton.json']).hexdigest(),
        request_sha256=canonical_sha256(request),report=report,causes=summarize(report['records']))
    digest=AnimatedStore(root).publish({'local-depth.json':canonical_bytes(value)})
    entries=registered(folder)
    if digest not in entries and len(entries)>=32:raise ValueError('local_depth_evidence_limit')
    journal=directory(folder/'local-depth-evidence',create=True)
    publish_document(journal/(digest+'.json'),dict(digest=digest),staging=folder/'staging')
    return digest


def read(root, folder, request, artifact, files):
    entries=registered(folder)
    if len(entries)>32:raise ValueError('local_depth_evidence_limit')
    rows=[]
    for digest in entries:
        value=json.loads(AnimatedStore(root).read_file(digest,'local-depth.json'))
        if (value['artifact_sha256']!=artifact or value['request_sha256']!=canonical_sha256(request)
                or value['skeleton_sha256']!=sha256(files['skeleton.json']).hexdigest()):
            raise ValueError('local_depth_evidence_stale')
        report=value['report'];causes=summarize(report['records'])
        if causes!=value['causes']:raise ValueError('local_depth_evidence_summary_mismatch')
        records=[dict(pair=r['pair'],time=r['check']['time'],status=r['check']['status'],
                      counts=r['check'].get('counts'),reason_code=r['check'].get('reason_code'),
                      unavailable_helpers=r['check'].get('sleeve_depth_model',{}).get('unavailable_helpers',{}))
                 for r in report['records'] if r['check']['status'] not in ('no_overlap','uniform_back_proxy','uniform_front_proxy')]
        visible=[]
        for status in ('requires_partition_or_more_depth','unmeasured'):
            visible.extend([r for r in records if r['status']==status][:20])
        rows.append(dict(evidence_sha256=digest,profile=report['profile'],causes=causes,
            triangle_summary=operator_summary(report['records']),
            failure=report.get('failure'),
            requested_sample_times=report.get('requested_sample_times'),
            sleeve_helpers=report.get('sleeve_helpers'),helper_model_scope=report.get('helper_model_scope'),
            interpolation=report['interpolation'],spatial_sampling=report.get('spatial_sampling','whole_triangle_intervals'),
            records=visible,records_truncated=len(records)>len(visible)))
    return dict(profile='motion-local-depth-operator-v1',artifact_sha256=artifact,reports=rows,
        authority='none',selected=False,scope='supplemental_diagnostics_not_readiness_or_visual_acceptance')
