"""Exact framebuffer stage for the retained sleeve workflow."""
import hashlib
import json
import subprocess
import sys
from .sleeve_workflow import checkpoint
from .sleeve_capture_environment import identity,node_executable
from .storage_io import read_document
from ..resolved_project import canonical_sha256
from ..targets.spine43.sleeve_framebuffer import summarize
from ..targets.spine43.sleeve_overlap_framebuffer import summaries as overlap_summaries
from .sleeve_motion_inventory import checked_names,evidence_schema


def checked_summary(path,root,project,record,expected,repo):
    raw=path.read_bytes();doc=json.loads(raw)
    if path.stem!=hashlib.sha256(raw).hexdigest() or doc['project_id']!=project:
        raise ValueError('sleeve_capture_receipt')
    if (doc['layer_id'],doc['component_id'])!=(record['layer_id'],record['component_id']):raise ValueError('sleeve_capture_region')
    source_paths=list((root/'spine'/project).glob('*.json'))
    if len(source_paths)!=1:raise ValueError('sleeve_capture_source_inventory')
    source=read_document(source_paths[0]);sha=canonical_sha256(source)
    if doc['source_sha256']!=sha:raise ValueError('sleeve_capture_source')
    regions=[r for r in source['records'] if (r['layer_id'],r['component_id'])==(record['layer_id'],record['component_id'])]
    if len(regions)!=1 or doc['asset_sha256']!=regions[0]['files']:raise ValueError('sleeve_capture_assets')
    if doc.get('schema')!=evidence_schema(source,'sleeve-framebuffer'):raise ValueError('sleeve_capture_schema')
    checked_names(source,regions[0],doc)
    bundle=root/'spine'/project/(record['layer_id']+'-'+record['component_id'])
    if doc['reference_sha256']!=hashlib.sha256((bundle/'numeric-reference.json').read_bytes()).hexdigest():raise ValueError('sleeve_capture_reference')
    for key,filename in [('harness_sha256','sleeve-framebuffer.js'),('tool_sha256','capture-sleeve-runtime.mjs')]:
        if doc[key]!=hashlib.sha256((repo/'tools'/filename).read_bytes()).hexdigest():raise ValueError('sleeve_capture_code')
    if doc['runtime_sha256']!=expected['runtime']['dist/iife/spine-webgl.js']:raise ValueError('sleeve_capture_runtime')
    def evidence(stage,digest):
        paths=list((root/stage/project).glob('*.json'))
        if len(paths)!=1 or paths[0].stem!=digest:raise ValueError('sleeve_capture_evidence')
        value=read_document(paths[0])
        if canonical_sha256(value)!=digest:raise ValueError('sleeve_capture_evidence')
        match=[r for r in value['records'] if (r['layer_id'],r['component_id'])==(record['layer_id'],record['component_id'])]
        if len(match)!=1 or match[0]['asset_sha256']!=doc['asset_sha256']:raise ValueError('sleeve_capture_evidence')
        checked_names(source,regions[0],match[0])
        return match[0]
    result=summarize(doc,evidence('contacts',doc['contact_sha256']))
    overlap=doc['overlap'];rows=overlap_summaries(overlap,evidence('overlap',overlap['source_sha256']))
    if overlap['hook_sha256']!=hashlib.sha256((repo/'tools/sleeve-overlap-framebuffer.js').read_bytes()).hexdigest():raise ValueError('sleeve_capture_code')
    images=doc['captures']+[i for c in overlap['captures'] for i in c['images']]
    images += [c['context'] for c in overlap['captures'] if c.get('context')]
    for image in images:
        file=path.parent/image['file']
        if file.resolve().parent!=path.parent.resolve() or hashlib.sha256(file.read_bytes()).hexdigest()!=image['sha256']:
            raise ValueError('sleeve_capture_image')
    result.update(report_sha256=path.stem,backend=doc['render_backend'],
        overlap_peak_pairs=len(rows),overlap_affected_peaks=sum(r['excess_pixels']>0 for r in rows),
        overlap_peak_pixels=max([0]+[r['peak_pixels'] for r in rows]),overlap_status='needs_review')
    return result


def run(repo,root,project,dependencies,browser,expected,report,assert_current):
    output=root/'framebuffer';selected=[r for r in report['records'] if r['download']]
    if not selected:return report
    if identity(dependencies,browser)!=expected:raise ValueError('sleeve_capture_environment_changed')
    def execute():
        if identity(dependencies,browser)!=expected:raise ValueError('sleeve_capture_environment_changed')
        print('framebuffer: running',flush=True)
        argv=[node_executable(),str(repo/'tools/capture-sleeve-runtime.mjs'),str(root/'spine'),str(root/'contacts'),str(output),
            str(dependencies),str(browser),project,'--overlap',str(root/'overlap')]
        with (root/'logs/framebuffer.log').open('wb') as log:
            result=subprocess.run(argv,cwd=repo,stdout=log,stderr=subprocess.STDOUT,timeout=1800)
        if result.returncode:raise ValueError('sleeve_capture_execution_failed')
        result=subprocess.run([sys.executable,str(repo/'tools/review-sleeve-framebuffer.py'),'--input',str(output),
            '--contacts',str(root/'contacts'),'--overlap',str(root/'overlap')],cwd=repo,capture_output=True,timeout=180)
        if result.returncode:raise ValueError('sleeve_capture_review_failed')
        assert_current()
        if identity(dependencies,browser)!=expected:raise ValueError('sleeve_capture_environment_changed')
    step=checkpoint(root,'framebuffer',canonical_sha256(dict(run=report['run_id'],environment=expected)),output,execute)
    for record in selected:
        paths=list((output/project/(record['layer_id']+'-'+record['component_id'])).glob('*.json'))
        if len(paths)!=1:raise ValueError('sleeve_capture_inventory')
        record['official_framebuffer']=checked_summary(paths[0],root,project,record,expected,repo)
        if record['official_framebuffer']['failed_samples']:
            record.update(status='blocked',reason_code='official_framebuffer_contact_failure',download=None)
    report['steps'].append(step);report['framebuffer_review']='framebuffer/index.html'
    if identity(dependencies,browser)!=expected:raise ValueError('sleeve_capture_environment_changed')
    print('framebuffer: '+('cached' if step['cached'] else 'succeeded'),flush=True)
    return report
