"""Source-replayed mount candidates; standalone benchmark CLI."""
import argparse
from pathlib import Path
from .artifacts import read_input, read_report, publish_report, export_document
from .rig_planner_cli import read_plan
from .region_binding_cli import sources
from .mount_candidates_view import render
from .mapping_cli import export_html
from ..asset.planning.mount_candidates import build
from ..resolved_project import canonical_sha256


def replay(state, manifest, workspace, plan_sha):
    plan=read_plan(state,manifest,workspace,plan_sha)
    candidate,_,skeleton,composite,images=sources(state,manifest,plan['source_skeleton_sha256'],workspace)
    return build(candidate,skeleton,plan,images),candidate,composite,images


def read_mounts(state, manifest, workspace, digest):
    doc=read_report(state,manifest['dataset_id'],'mount-candidates-v1',digest)
    if replay(state,manifest,workspace,doc['source_plan_sha256'])[0] != doc:
        raise ValueError('mount_replay_mismatch')
    return doc


def main():
    parser=argparse.ArgumentParser(description='Review garment, prop and wing mounting hypotheses')
    for name in ('manifest','workspace','plan','html','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--state-root',type=Path,default=Path('workspace'))
    args=parser.parse_args(); manifest=read_input(args.manifest)
    doc,candidate,composite,images=replay(args.state_root,manifest,args.workspace,canonical_sha256(read_input(args.plan)))
    digest=publish_report(args.state_root,manifest['dataset_id'],'mount-candidates-v1',doc)
    read_mounts(args.state_root,manifest,args.workspace,digest)
    export_document(args.output,doc);export_html(args.html,render(doc,candidate,composite,images))
    print(digest)


if __name__=='__main__': main()
