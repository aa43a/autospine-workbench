"""Recoverable R3-S candidate workflow using existing source-bound compilers."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from .storage_io import directory,publish_document,read_document
from ..resolved_project import canonical_sha256
from ..motion_instance_v3_staging_cleanup import is_alias


def inventory(root):
    root=directory(root);files={}
    for path in sorted(root.rglob('*')):
        if is_alias(path):raise ValueError('sleeve_output_alias')
        if path.is_dir():directory(path)
        if path.is_file():files[path.relative_to(root).as_posix()]=hashlib.sha256(path.read_bytes()).hexdigest()
    return files


def checkpoint(root,step,signature,output,execute):
    receipts=directory(root/'receipts',create=True);receipt=receipts/(step+'.json')
    if receipt.exists():
        saved=read_document(receipt)
        if saved['signature']!=signature or saved['files']!=inventory(output):raise ValueError('sleeve_cached_output_changed')
        return dict(id=step,status='succeeded',cached=True)
    execute()
    files=inventory(output)
    if not files:raise ValueError('sleeve_step_outputs_missing')
    record=dict(signature=signature,files=files)
    if not publish_document(receipt,record,staging=root/'.staging'):raise ValueError('sleeve_checkpoint_conflict')
    return dict(id=step,status='succeeded',cached=False)


def steps(repo,draft_root,root,project,state,workspace):
    shared=['--state-root',str(state),'--workspace',str(workspace)]
    result=[]
    def add(name,script,input_name,flags=()):
        source=draft_root if input_name is None else root/input_name
        output=root/name
        argv=[sys.executable,str(repo/'tools'/script),'--input',str(source),'--output',str(output),*flags,*shared,project]
        result.append((name,output,argv))
    add('weights','build-sleeve-weights.py',None)
    add('root','build-sleeve-helpers.py','weights',['--root-transition'])
    add('interface','build-sleeve-helpers.py','root',['--interface-root'])
    add('anchors','build-sleeve-helpers.py','interface',['--multi-anchor'])
    add('motion','build-sleeve-helpers.py','anchors',['--motion-envelope'])
    add('connection','build-sleeve-helpers.py','anchors',['--motion-envelope','--connection-domain','--baseline-envelope',str(root/'motion')])
    add('boundary','build-sleeve-helpers.py','anchors',['--motion-envelope','--connection-domain','--boundary-budget','--baseline-envelope',str(root/'connection')])
    add('cuff','build-sleeve-helpers.py','anchors',['--motion-envelope','--connection-domain','--boundary-budget','--cuff-harmonic','--edge-budget','--baseline-envelope',str(root/'boundary')])
    add('repair','repair-sleeve-candidate.py','cuff')
    add('spine','export-sleeve-spine.py','repair')
    result.append(('contacts',root/'contacts',[sys.executable,str(repo/'tools/check-sleeve-contacts.py'),
        '--input',str(root/'spine'),'--output',str(root/'contacts'),'--state-root',str(state),project]))
    result.append(('overlap',root/'overlap',[sys.executable,str(repo/'tools/check-sleeve-overlap.py'),
        '--input',str(root/'spine'),'--output',str(root/'overlap'),project]))
    return result


def code_identity(repo):
    paths=list((repo/'src'/'autospine_workbench').rglob('*.py'))
    paths += [repo/'tools'/name for name in ('build-sleeve-weights.py','build-sleeve-helpers.py','export-sleeve-spine.py','run-sleeve-workflow.py','verify-sleeve-core.mjs','check-sleeve-contacts.py','check-sleeve-overlap.py')]
    paths += [repo/'tools'/name for name in ('capture-sleeve-runtime.mjs','sleeve-framebuffer.js','sleeve-overlap-framebuffer.js','review-sleeve-framebuffer.py')]
    paths += [repo/'tools'/name for name in ('repair-sleeve-candidate.py','solve-retained-sleeve.py')]
    return canonical_sha256({p.relative_to(repo).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)})


def execute_steps(repo,root,plan,signature,assert_current):
    progress=[];logs=directory(root/'logs',create=True)
    for name,output,argv in plan:
        assert_current();print(f'{name}: running',flush=True)
        def execute():
            env=dict(os.environ);env['PYTHONPATH']=str(repo/'src')
            with (logs/(name+'.log')).open('wb') as log:
                completed=subprocess.run(argv,cwd=repo,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=1800)
            if completed.returncode:raise ValueError('sleeve_stage_failed_'+name)
            assert_current()
        result=checkpoint(root,name,signature,output,execute);progress.append(result)
        print(f'{name}: '+('cached' if result['cached'] else 'succeeded'),flush=True)
    return progress


def summarize(root,project,run_id,progress):
    reports=list((root/'spine'/project).glob('*.json'))
    if len(reports)!=1:raise ValueError('sleeve_export_report_ambiguous')
    report=json.loads(reports[0].read_bytes());records=[]
    contact_rows={}
    if any(s['id']=='contacts' for s in progress):
        from .sleeve_contact_step import summaries
        contact_rows=summaries(root,project,report)
    overlap_rows={}
    if any(s['id']=='overlap' for s in progress):
        from .sleeve_overlap_step import summaries as overlap_summaries
        overlap_rows=overlap_summaries(root,project,report)
    for row in report['records']:
        records.append(dict(layer_id=row['layer_id'],component_id=row['component_id'],status=row['status'],
            reason_code=row['reason_code'],download=(f"spine/{project}/{row['layer_id']}-{row['component_id']}/candidate.zip"
            if row['status']=='candidate_exported' else None)))
        key=row['layer_id'],row['component_id']
        if key in contact_rows:records[-1]['software_contact']=contact_rows[key]
        if key in overlap_rows:records[-1]['software_overlap']=overlap_rows[key]
    return dict(schema='autospine.sleeve-workflow/v1',run_id=run_id,project_id=project,status='needs_review',
        steps=progress,records=records,runtime_status='not_evaluated',alpha_contact_status='not_evaluated',
        authority='none',production_authorized=False)
