"""Inspect, apply, or undo evidence-based compact-foot candidates on a current project."""
import argparse
import json
from pathlib import Path

from autospine_workbench.project_store import ProjectStore
from autospine_workbench.automation.animated_inputs import load_inputs
from autospine_workbench.automation.simple_binding_policy import propose
from autospine_workbench.automation.simple_binding_adoption import apply, undo
from autospine_workbench.benchmark.artifacts import export_document


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project')
    parser.add_argument('--action',choices=['inspect','apply','undo'],default='inspect')
    parser.add_argument('--decision',help='Decision returned by apply; required for undo')
    parser.add_argument('--output',type=Path,help='Write an immutable inspection or operation report')
    parser.add_argument('--workspace',type=Path,default=Path('..'))
    parser.add_argument('--state-root',type=Path,default=Path('workspace'))
    args=parser.parse_args()
    if args.action=='undo' and not args.decision:parser.error('undo requires --decision')
    store=ProjectStore(args.workspace.resolve(),args.state_root.resolve())
    with load_inputs(store,args.project) as source:
        key=source.source_addresses['input_identity_sha256']
        result=propose(source) if args.action=='inspect' else None
    if args.action=='apply':result=apply(store,args.project,key)
    if args.action=='undo':result=undo(store,args.project,args.decision,key)
    if args.output:export_document(args.output,result)
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
