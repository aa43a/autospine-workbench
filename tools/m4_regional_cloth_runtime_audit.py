"""Audit stored cloth capture files, rather than trusting progress summaries."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.targets.character43.numeric_reference import read
from m4_corrective_geometry_check import required_times
from m4_regional_cloth_runtime import complete_chunks
from m4_runtime_batch_coverage import render_identity
from m4_transverse_batch_validation import verify_coverage


def audit(source,experiment,parent,output,partial=False):
    manifest=json.loads((output/'report.json').read_bytes())
    parent_raw=parent.read_bytes();full=json.loads(parent_raw)
    source_receipt=json.loads((source/'report.json').read_bytes())
    original=AnimatedStore(source/'isolated-store').read(source_receipt['candidate_bundle_sha256'])
    diagnostic=json.loads((experiment/'report.json').read_bytes())
    raw=(experiment/'skeleton.json').read_bytes();digest=sha256(raw).hexdigest()
    expected=required_times(json.loads(raw),'external-motion',
        [f['time'] for f in read(original)['animations']['external-motion']],diagnostic)
    expected=sorted(set(expected)|set(full['required_times']))
    if (manifest['status']!='complete' and not partial or
        manifest['source_candidate']!=source_receipt['candidate_bundle_sha256'] or
        diagnostic['source_candidate']!=manifest['source_candidate'] or
        manifest['skeleton_sha256']!=digest or diagnostic['skeleton_sha256']!=digest or
        manifest['parent_report_sha256']!=sha256(parent_raw).hexdigest() or
        full['skeleton_sha256']!=sha256(original['skeleton.json']).hexdigest() or
        manifest['required_times']!=expected or manifest['authority']!='none' or
        manifest['selected'] is not False or manifest['production_authorized'] is not False):
        raise ValueError('cloth_audit_identity')
    chunks=complete_chunks(expected);rows=manifest['rows']
    if len(rows)>len(chunks) or not partial and len(rows)!=len(chunks):
        raise ValueError('cloth_audit_count')
    identity=render_identity(dict(original,**{'skeleton.json':raw}))
    for i,row in enumerate(rows):
        if row['folder']!=f'batch-{i:03d}' or row['times']!=chunks[i]:
            raise ValueError('cloth_audit_time_grid')
        folder=output/row['folder']
        files=AnimatedStore(folder/'isolated-store').read(row['candidate_bundle_sha256'])
        reference=read(files);geometry=json.loads((folder/'geometry.json').read_bytes())
        observed=json.loads((folder/'runtime/report.json').read_bytes())
        if (files['skeleton.json']!=raw or render_identity(files)!=identity or row['render_identity']!=identity or
            reference['skeleton_sha256']!=digest or set(reference['animations'])!={'external-motion'} or
            [f['time'] for f in reference['animations']['external-motion']]!=chunks[i] or
            geometry!=json.loads(files['deformation.json']) or geometry['skeleton_sha256']!=digest or
            geometry['passed']!=row['geometry_passed'] or
            any(r['sample_count']!=len(chunks[i]) for r in geometry['records']) or observed!=row['runtime']):
            raise ValueError('cloth_audit_saved_evidence')
        verify_coverage(chunks[i],[row],True)
    if len(rows)==len(chunks):
        coverage=verify_coverage(expected,rows,True)
        if manifest.get('coverage')!=coverage:raise ValueError('cloth_audit_coverage')
    else:coverage=None
    return dict(status=manifest['status'],audited_batches=len(rows),total_batches=len(chunks),
        complete=coverage is not None,coverage=coverage,authority='none',selected=False)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','experiment','parent','output'):p.add_argument(name,type=Path)
    p.add_argument('--partial',action='store_true')
    a=p.parse_args();print(json.dumps(audit(a.source,a.experiment,a.parent,a.output,a.partial)))
