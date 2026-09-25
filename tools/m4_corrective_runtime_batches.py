"""Capture all declared corrective times without increasing per-run budgets."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.character_capture import capture
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.numeric_reference import read
from m4_corrective_geometry_check import required_times,prepare
from m4_corrective_runtime_probe import render_inputs
from m4_experiment_player_export import export
from m4_runtime_batch_coverage import partition,render_identity,verify


def run(source,experiment,output):
    if output.exists():raise ValueError('runtime_batches_output_exists')
    receipt=json.loads((source/'report.json').read_bytes())
    original=AnimatedStore(source/'isolated-store').read(receipt['candidate_bundle_sha256'])
    report=json.loads((experiment/'report.json').read_bytes());raw=(experiment/'skeleton.json').read_bytes()
    if report['source_candidate']!=receipt['candidate_bundle_sha256'] or sha256(raw).hexdigest()!=report['skeleton_sha256']:
        raise ValueError('runtime_batches_source_identity')
    times=required_times(json.loads(raw),'external-motion',
        [r['time'] for r in read(original)['animations']['external-motion']],report)
    chunks=partition(times,size=2048);del original
    output.mkdir();batches=[]
    manifest=dict(source_candidate=report['source_candidate'],skeleton_sha256=report['skeleton_sha256'],
        required_times=times,batch_sizes=[len(c) for c in chunks],status='running',authority='none',selected=False)
    (output/'report.json').write_bytes(canonical_bytes(manifest))
    try:
        for index,chunk in enumerate(chunks):
            folder=output/f'batch-{index:03d}';folder.mkdir()
            print(json.dumps({'batch':index,'total':len(chunks),'stage':'prepare','frames':len(chunk)}),flush=True)
            files,evidence=prepare(source,experiment,sample_times=chunk)
            identity=render_identity(files);files=render_inputs(files,evidence)
            print(json.dumps({'batch':index,'stage':'package','total_bytes':sum(map(len,files.values())),
                'largest_file_bytes':max(map(len,files.values()))}),flush=True)
            store=AnimatedStore(folder/'isolated-store');digest=store.publish(files);del files
            batch=dict(candidate_bundle_sha256=digest,source_candidate=report['source_candidate'],
                skeleton_sha256=report['skeleton_sha256'],geometry_passed=evidence['geometry']['passed'],
                render_identity=identity,status='running',authority='none',selected=False)
            (folder/'report.json').write_bytes(canonical_bytes(batch))
            capture(SimpleNamespace(workspace_root=Path.cwd().parent),store,digest,folder,
                progress=lambda stage:print(json.dumps({'batch':index,'stage':stage}),flush=True),
                cancel_requested=lambda:False,storage_reference=True)
            runtime=json.loads((folder/'runtime/report.json').read_bytes())
            batch['status']='complete';(folder/'report.json').write_bytes(canonical_bytes(batch))
            batches.append(dict(bundle_sha256=digest,times=chunk,render_identity=identity,
                geometry_passed=batch['geometry_passed'],runtime=runtime))
            # Validate each captured chunk before advancing; global union is checked below.
            verify(chunk,[batches[-1]])
            manifest.setdefault('batch_records',[]).append(dict(folder=folder.name,bundle_sha256=digest,
                render_identity=identity,frames=len(chunk),start=chunk[0],end=chunk[-1],
                runtime_report_sha256=sha256((folder/'runtime/report.json').read_bytes()).hexdigest()))
            manifest['completed_batches']=index+1;(output/'report.json').write_bytes(canonical_bytes(manifest))
        manifest.update(coverage=verify(times,batches),status='complete')
        (output/'report.json').write_bytes(canonical_bytes(manifest))
        export(output/'batch-000')
        from m4_runtime_batch_player import run as build_player
        build_player(output)
    except Exception as exc:
        manifest.update(status='failed',error=str(exc));(output/'report.json').write_bytes(canonical_bytes(manifest));raise
    print(json.dumps(manifest['coverage']),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for n in ('source','experiment','output'):p.add_argument(n,type=Path)
    a=p.parse_args();run(a.source,a.experiment,a.output)
