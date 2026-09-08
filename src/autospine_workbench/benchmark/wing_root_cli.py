"""Source-replayed inward wing root diagnostics."""
import argparse
from pathlib import Path
from .artifacts import read_input,read_report,publish_report,export_document
from .mount_contact_search_cli import read_search
from .region_binding_cli import sources
from .mapping_cli import export_html
from .wing_root_view import render
from ..asset.planning.wing_root import build
from ..resolved_project import canonical_sha256


def replay(state,manifest,workspace,digest):
    previous=read_search(state,manifest,workspace,digest)
    contacts=read_report(state,manifest['dataset_id'],'mount-contacts-v1',previous['source_contact_sha256'])
    mounts=read_report(state,manifest['dataset_id'],'mount-candidates-v1',contacts['source_mount_sha256'])
    plan=read_report(state,manifest['dataset_id'],'rig-plans-v1',mounts['source_plan_sha256'])
    candidate,_,_,_,images=sources(state,manifest,plan['source_skeleton_sha256'],workspace)
    return build(candidate,mounts,contacts,previous,images),candidate,images


def read_roots(state,manifest,workspace,digest):
    doc=read_report(state,manifest['dataset_id'],'wing-roots-v1',digest)
    if replay(state,manifest,workspace,doc['source_search_sha256'])[0]!=doc:raise ValueError('wing_root_replay_mismatch')
    return doc


def main():
    parser=argparse.ArgumentParser(description='Inspect inward wing roots and projected coverage')
    for key in ('manifest','workspace','search','html','output'):parser.add_argument('--'+key,type=Path,required=True)
    parser.add_argument('--state-root',type=Path,default=Path('workspace'))
    args=parser.parse_args();manifest=read_input(args.manifest)
    doc,candidate,images=replay(args.state_root,manifest,args.workspace,canonical_sha256(read_input(args.search)))
    digest=publish_report(args.state_root,manifest['dataset_id'],'wing-roots-v1',doc)
    read_roots(args.state_root,manifest,args.workspace,digest)
    export_document(args.output,doc);export_html(args.html,render(doc,candidate,images));print(digest)


if __name__=='__main__':main()
