"""Local contact diagnostics over exact mount and binding candidates."""
import argparse
from pathlib import Path
from .artifacts import read_input, read_report, publish_report, export_document
from .mount_candidates_cli import read_mounts
from .region_binding_cli import sources
from .mount_contact_view import render
from .mapping_cli import export_html
from ..asset.planning.mount_contact import build
from ..resolved_project import canonical_sha256


def replay(state,manifest,workspace,digest):
    mounts=read_mounts(state,manifest,workspace,digest)
    plan=read_report(state,manifest['dataset_id'],'rig-plans-v1',mounts['source_plan_sha256'])
    bindings=read_report(state,manifest['dataset_id'],'layer-binding-candidates-v2',plan['source_bindings_sha256'])
    candidate,_,_,_,images=sources(state,manifest,plan['source_skeleton_sha256'],workspace)
    return build(candidate,bindings,plan,mounts,images),candidate,images


def read_contact(state,manifest,workspace,digest):
    doc=read_report(state,manifest['dataset_id'],'mount-contacts-v1',digest)
    if replay(state,manifest,workspace,doc['source_mount_sha256'])[0]!=doc:
        raise ValueError('contact_replay_mismatch')
    return doc


def main():
    p=argparse.ArgumentParser(description='Inspect local alpha contact near candidate mounting anchors')
    for key in ('manifest','workspace','mounts','html','output'):p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--state-root',type=Path,default=Path('workspace'))
    args=p.parse_args();manifest=read_input(args.manifest)
    doc,candidate,images=replay(args.state_root,manifest,args.workspace,canonical_sha256(read_input(args.mounts)))
    digest=publish_report(args.state_root,manifest['dataset_id'],'mount-contacts-v1',doc)
    read_contact(args.state_root,manifest,args.workspace,digest)
    export_document(args.output,doc);export_html(args.html,render(doc,candidate,images));print(digest)


if __name__=='__main__':main()
