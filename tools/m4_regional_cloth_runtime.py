"""Capture a cloth diagnostic while retaining the complete parent time grid."""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace
from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.character_capture import capture
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.numeric_reference import read
from m4_corrective_geometry_check import required_times
from m4_runtime_batch_coverage import partition,render_identity
from m4_transverse_batch_validation import prepare,verify_coverage
from m4_experiment_player_export import export


def complete_chunks(times):
    # Two bounded outer groups retain the parent grid without increasing a
    # single capture or existing partition reader's allocation limit.
    if not times or times[0]!=0 or len(times)>32769 or times!=sorted(set(times)):
        raise ValueError('cloth_runtime_complete_grid_invalid')
    chunks=partition(times[:16385],size=1024)
    if len(times)>16385:chunks.extend(partition([0]+times[16385:],size=1024))
    return chunks


def run(source,experiment,parent,output):
    receipt=json.loads((source/'report.json').read_bytes())
    original=AnimatedStore(source/'isolated-store').read(receipt['candidate_bundle_sha256'])
    report=json.loads((experiment/'report.json').read_bytes());raw=(experiment/'skeleton.json').read_bytes()
    full=json.loads(parent.read_bytes());before=json.loads(original['skeleton.json']);after=json.loads(raw)
    if (report['source_candidate']!=receipt['candidate_bundle_sha256'] or
        report['skeleton_sha256']!=sha256(raw).hexdigest() or full['status']!='complete' or
        full['skeleton_sha256']!=sha256(original['skeleton.json']).hexdigest() or
        not any(r['bundle_sha256']==report['source_candidate'] and r['render_identity']==render_identity(original)
                for r in full['batch_records'])):
        raise ValueError('cloth_runtime_source_identity')
    selected={r['slot'] for r in report['rows']};unchanged=[]
    for document in (before,after):
        value=deepcopy(document)
        tracks=value['animations']['external-motion']['attachments']['default']
        for slot in selected:tracks.pop(slot,None)
        unchanged.append(value)
    if unchanged[0]!=unchanged[1]:raise ValueError('cloth_runtime_unselected_changed')
    times=required_times(after,'external-motion',
        [r['time'] for r in read(original)['animations']['external-motion']],report)
    times=sorted(set(times)|set(full['required_times']))
    chunks=complete_chunks(times)
    output.mkdir(parents=True,exist_ok=False);rows=[]
    result=dict(status='running',source_candidate=report['source_candidate'],skeleton_sha256=sha256(raw).hexdigest(),
        parent_report_sha256=sha256(parent.read_bytes()).hexdigest(),required_times=times,rows=rows,
        authority='none',selected=False,production_authorized=False,
        known_coverage_failed_times=sum(bool(r['uncovered']) for r in report['frames']),
        pending_checks=['framebuffer_material_coverage','full_contact_and_depth','visual_review'])
    def save():(output/'report.json').write_bytes(canonical_bytes(result))
    save()
    try:
        for index,chunk in enumerate(chunks):
            folder=output/f'batch-{index:03d}';folder.mkdir()
            print(json.dumps(dict(batch=index,total=len(chunks),stage='geometry',samples=len(chunk))),flush=True)
            files,geometry=prepare(original,raw,chunk)
            (folder/'geometry.json').write_bytes(canonical_bytes(geometry))
            store=AnimatedStore(folder/'isolated-store');digest=store.publish(files)
            local=dict(candidate_bundle_sha256=digest,source_candidate=report['source_candidate'],
                skeleton_sha256=sha256(raw).hexdigest(),geometry_passed=geometry['passed'],
                authority='none',selected=False,production_authorized=False)
            (folder/'report.json').write_bytes(canonical_bytes(local))
            identity=render_identity(files);del files
            captured=capture(SimpleNamespace(workspace_root=Path.cwd().parent),store,digest,folder,
                progress=lambda stage:print(json.dumps(dict(batch=index,stage=stage)),flush=True),
                cancel_requested=lambda:False,storage_reference=True)
            if captured['status']=='unavailable':raise ValueError('cloth_runtime_unavailable')
            runtime=json.loads((folder/'runtime/report.json').read_bytes())
            row=dict(candidate_bundle_sha256=digest,times=chunk,render_identity=identity,
                geometry_passed=geometry['passed'],runtime=runtime,folder=folder.name)
            verify_coverage(chunk,[row],True);rows.append(row);save()
        result.update(status='complete',coverage=verify_coverage(times,rows,True));save()
        export(output/'batch-000')
        print(json.dumps(result['coverage']),flush=True)
    except Exception as exc:
        result.update(status='failed',error=str(exc));save();raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','experiment','parent','output'):p.add_argument(name,type=Path)
    a=p.parse_args();run(a.source,a.experiment,a.parent,a.output)
