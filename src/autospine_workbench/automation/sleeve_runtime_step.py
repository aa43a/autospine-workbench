"""Source-bound official core verification in a separate resumable output stage."""
import hashlib
import json
import math
from pathlib import Path
import subprocess
from .sleeve_workflow import inventory,checkpoint
from .storage_io import directory
from .sleeve_capture_environment import node_executable,node_identity
from ..resolved_project import canonical_sha256


def identity(core):
    core=directory(core);package=json.loads((core/'package.json').read_bytes())
    if package.get('name')!='@esotericsoftware/spine-core' or package.get('version')!='4.3.13':raise ValueError('sleeve_runtime_version')
    files=inventory(core)
    return dict(package=package['name'],version=package['version'],files=files,node=node_identity())


def validate(report,bundle,expected):
    digest=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
    if (report.get('runtime_package')!=expected['package'] or report.get('runtime_version')!=expected['version']
            or report.get('scope')!='official_core_vertices_only' or report.get('authority')!='none'
            or report.get('production_authorized') is not False):raise ValueError('sleeve_runtime_report_identity')
    runtime_files={k:v for k,v in expected['files'].items() if k.startswith('dist/') and k.endswith('.js')}
    if report['runtime_files']!=runtime_files:raise ValueError('sleeve_runtime_code_changed')
    for key,name in [('skeleton_sha256','skeleton.json'),('atlas_sha256','skeleton.atlas'),('reference_sha256','numeric-reference.json')]:
        if report[key]!=digest(bundle/name):raise ValueError('sleeve_runtime_source_changed')
    reference=json.loads((bundle/'numeric-reference.json').read_bytes())['animations']
    rows=report['results']
    if len(rows)!=len(reference) or {r['animation'] for r in rows}!=set(reference):raise ValueError('sleeve_runtime_inventory')
    passed=True
    for row in rows:
        error=row['max_error_px']
        if row['frames']!=len(reference[row['animation']]) or not isinstance(error,(int,float)) or not math.isfinite(error) or error<0:
            raise ValueError('sleeve_runtime_samples')
        actual=error<=.001
        if row['passed'] is not actual:raise ValueError('sleeve_runtime_result_mismatch')
        passed &= actual
    if report['passed'] is not passed:raise ValueError('sleeve_runtime_result_mismatch')
    return passed


def run(repo,root,project,core,expected,summary,assert_current):
    output=directory(root/'runtime'/project,create=True)
    signature=canonical_sha256(dict(run_id=summary['run_id'],runtime=expected))
    selected=[r for r in summary['records'] if r['download']]
    def execute():
        if identity(core)!=expected:raise ValueError('sleeve_runtime_code_changed')
        for row in selected:
            name=row['layer_id']+'-'+row['component_id'];bundle=root/Path(row['download']).parent
            command=[node_executable(),str(repo/'tools/verify-sleeve-core.mjs'),str(bundle),str(core),str(output/(name+'.json'))]
            result=subprocess.run(command,cwd=repo,capture_output=True,text=True,timeout=180)
            if result.returncode not in (0,1) or not (output/(name+'.json')).is_file():raise ValueError('sleeve_runtime_execution_failed')
            checked=validate(json.loads((output/(name+'.json')).read_bytes()),bundle,expected)
            if (result.returncode==0)!=checked:raise ValueError('sleeve_runtime_exit_mismatch')
            assert_current()
        if not selected:(output/'empty.json').write_text('{"status":"no_admitted_regions"}',encoding='utf-8')
        if identity(core)!=expected:raise ValueError('sleeve_runtime_code_changed')
    step=checkpoint(root,'runtime',signature,output,execute)
    all_passed=bool(selected)
    for row in selected:
        name=row['layer_id']+'-'+row['component_id'];path=output/(name+'.json')
        passed=validate(json.loads(path.read_bytes()),root/Path(row['download']).parent,expected);all_passed &= passed
        row.update(runtime_status='core_passed' if passed else 'core_failed',runtime_report=path.relative_to(root).as_posix())
        if not passed:row.update(status='blocked',reason_code='official_core_numeric_failure',download=None)
    summary['steps'].append(step);summary['runtime_status']='core_passed' if all_passed else 'core_incomplete'
    return summary
