"""Reconstruct batch coverage from immutable candidates and saved capture reports."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.targets.character43.numeric_reference import read
from m4_runtime_batch_coverage import render_identity,verify


def audit(root):
    manifest=json.loads((root/'report.json').read_bytes())
    records=manifest.get('batch_records',[])
    if manifest['status']!='complete' or len(records)!=len(manifest['batch_sizes']):
        raise ValueError('runtime_batch_audit_incomplete')
    batches=[];cursor=0
    for index,record in enumerate(records):
        if record['folder']!=f'batch-{index:03d}':raise ValueError('runtime_batch_audit_folder')
        folder=root/record['folder'];size=manifest['batch_sizes'][index]
        count=size-(1 if index else 0)
        times=manifest['required_times'][cursor:cursor+count];cursor+=count
        if index:times=[manifest['required_times'][0]]+times
        files=AnimatedStore(folder/'isolated-store').read(record['bundle_sha256'])
        if sha256(files['skeleton.json']).hexdigest()!=manifest['skeleton_sha256']:
            raise ValueError('runtime_batch_audit_skeleton')
        reference=read(files)
        if set(reference['animations'])!={'external-motion'} or [r['time'] for r in reference['animations']['external-motion']]!=times:
            raise ValueError('runtime_batch_audit_reference')
        raw=(folder/'runtime/report.json').read_bytes()
        if sha256(raw).hexdigest()!=record['runtime_report_sha256']:raise ValueError('runtime_batch_audit_report_hash')
        geometry=json.loads((folder/'runtime/deformation.json').read_bytes())
        if geometry['skeleton_sha256']!=manifest['skeleton_sha256']:raise ValueError('runtime_batch_audit_geometry')
        identity=render_identity(files)
        if identity!=record['render_identity']:raise ValueError('runtime_batch_audit_render')
        batches.append(dict(bundle_sha256=record['bundle_sha256'],times=times,render_identity=identity,
            runtime=json.loads(raw),geometry_passed=geometry['passed']))
    result=verify(manifest['required_times'],batches)
    if result!=manifest['coverage']:raise ValueError('runtime_batch_audit_coverage')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);a=p.parse_args()
    print(json.dumps(audit(a.root)),flush=True)
