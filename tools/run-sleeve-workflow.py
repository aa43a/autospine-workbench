"""Rebuild the retained sleeve candidate chain without manual artifact addresses."""
import argparse
import json
import re
import subprocess
from pathlib import Path
from autospine_workbench.project_store import ProjectStore
from autospine_workbench.automation.animated_inputs import load_inputs
from autospine_workbench.automation.pipeline_lease import execution_lease
from autospine_workbench.automation.sleeve_workflow import steps,code_identity,execute_steps,summarize
from autospine_workbench.automation.sleeve_workflow_review import render
from autospine_workbench.automation.storage_io import directory,canonical_bytes
from autospine_workbench.benchmark.artifacts import read_input
from autospine_workbench.benchmark.elbow_target_cli import export
from autospine_workbench.manifest_artifacts import require_safe_token
from autospine_workbench.resolved_project import canonical_sha256


def main():
    repo=Path(__file__).resolve().parents[1];p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('projects',nargs='+');p.add_argument('--draft-root',type=Path,default=repo.parent/'tmp/r3a-sleeve-reviewed-v2')
    p.add_argument('--output',type=Path,default=repo.parent/'tmp/r3s-workflow')
    p.add_argument('--state-root',type=Path,default=repo/'workspace');p.add_argument('--workspace',type=Path,default=repo.parent)
    p.add_argument('--runtime-core',type=Path,help='Installed official spine-core package; no downloads')
    a=p.parse_args();store=ProjectStore(a.workspace.resolve(),a.state_root.resolve());engine=code_identity(repo)
    runtime=None
    if a.runtime_core:
        from autospine_workbench.automation.sleeve_runtime_step import identity
        runtime=identity(a.runtime_core.resolve())
    for project in a.projects:
        require_safe_token(project,'project');draft=read_input(a.draft_root/project/'draft.json')
        if draft['project_id']!=project:raise ValueError('sleeve_workflow_project_mismatch')
        with load_inputs(store,project) as inputs:
            signature=canonical_sha256(dict(profile='retained-sleeve-chain-v4',project_id=project,draft_sha256=canonical_sha256(draft),
                skeleton_sha256=canonical_sha256(inputs.skeleton),source_addresses=inputs.source_addresses,engine=engine,runtime=runtime))
            run_id='run-'+signature;root=directory(a.output.resolve()/project/run_id,create=True)
            with execution_lease(store.state_root,run_id):
                snapshot=root/'inputs';export(snapshot/project/'draft.json',canonical_bytes(draft))
                def assert_snapshot():
                    inputs.assert_current()
                    if code_identity(repo)!=engine:raise ValueError('sleeve_workflow_engine_changed')
                progress=execute_steps(repo,root,steps(repo,snapshot,root,project,a.state_root.resolve(),a.workspace.resolve()),signature,assert_snapshot)
                report=summarize(root,project,run_id,progress)
                if runtime:
                    from autospine_workbench.automation.sleeve_runtime_step import run as verify_runtime
                    report=verify_runtime(repo,root,project,a.runtime_core.resolve(),runtime,report,assert_snapshot)
                export(root/(canonical_sha256(report)+'.json'),canonical_bytes(report))
                # View is derived, not an identity/authority document.
                (root/'index.html').write_text(render(report),encoding='utf-8')
                print(json.dumps(dict(project_id=project,status=report['status'],review=str(root/'index.html'))),flush=True)


if __name__=='__main__':
    try:main()
    except (ValueError,OSError,subprocess.TimeoutExpired) as exc:
        reason=str(exc) if re.fullmatch(r'sleeve_[a-z_]+',str(exc)) else 'sleeve_workflow_failed'
        print(json.dumps(dict(status='failed',reason_code=reason)),flush=True);raise SystemExit(1)
