"""Recheck saved transverse batches against immutable inputs and actual output files."""
import argparse
from hashlib import sha256
import json
from pathlib import Path

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.targets.character43.numeric_reference import read
from m4_runtime_batch_coverage import partition, render_identity
from m4_transverse_batch_validation import verify_diagnostic, verify_coverage


def audit(state_root, probe, output):
    manifest = json.loads((output/'report.json').read_bytes())
    receipt_raw = (probe/'report.json').read_bytes(); receipt = json.loads(receipt_raw)
    raw = (probe/'solved-diagnostic.json').read_bytes()
    times = json.loads((probe/'validation-times.json').read_bytes())
    original = AnimatedStore(state_root).read(receipt['parent_artifact_sha256'])
    verify_diagnostic(original, raw, receipt, times)
    if (manifest['status'] != 'complete' or manifest['probe_sha256'] != sha256(receipt_raw).hexdigest()
            or manifest['parent_artifact_sha256'] != receipt['parent_artifact_sha256']
            or manifest['skeleton_sha256'] != receipt['skeleton_sha256']
            or manifest['required_times'] != times or manifest.get('authority') != 'none'
            or manifest.get('selected') is not False or manifest.get('production_authorized') is not False):
        raise ValueError('transverse_batch_audit_source')
    chunks = partition(times, size=1024)
    if len(manifest['rows']) != len(chunks):raise ValueError('transverse_batch_audit_count')
    rows = []; runtime = manifest['coverage']['runtime_status'] == 'passed'
    for index, (record, chunk) in enumerate(zip(manifest['rows'], chunks)):
        if record['folder'] != f'batch-{index:03d}' or record['times'] != chunk:
            raise ValueError('transverse_batch_audit_time_grid')
        folder = output/record['folder']
        files = AnimatedStore(folder/'isolated-store').read(record['candidate_bundle_sha256'])
        reference = read(files)
        if (files['skeleton.json'] != raw or render_identity(files) != record['render_identity']
                or reference['skeleton_sha256'] != receipt['skeleton_sha256']
                or set(reference['animations']) != {'external-motion'}
                or [f['time'] for f in reference['animations']['external-motion']] != chunk):
            raise ValueError('transverse_batch_audit_reference')
        geometry_raw = (folder/'geometry.json').read_bytes(); geometry = json.loads(geometry_raw)
        if (sha256(geometry_raw).hexdigest() != record['geometry_sha256']
                or geometry['times'] != chunk or geometry['geometry'] != json.loads(files['deformation.json'])
                or geometry['geometry']['passed'] != record['geometry_passed']
                or geometry['geometry']['skeleton_sha256'] != receipt['skeleton_sha256']
                or geometry['parent_geometry']['skeleton_sha256'] != sha256(original['skeleton.json']).hexdigest()
                or any(r['sample_count'] != len(chunk) for key in ('geometry','parent_geometry')
                       for r in geometry[key]['records'])):
            raise ValueError('transverse_batch_audit_geometry')
        row = dict(record)
        if runtime:
            observed = json.loads((folder/'runtime/report.json').read_bytes())
            if observed != record['runtime']:
                raise ValueError('transverse_batch_audit_runtime')
            row['runtime'] = observed
        rows.append(row)
    result = verify_coverage(times, rows, runtime)
    if result != manifest['coverage']:raise ValueError('transverse_batch_audit_coverage')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('state_root','probe','output'):parser.add_argument(name, type=Path)
    args = parser.parse_args(); print(json.dumps(audit(args.state_root,args.probe,args.output)))
