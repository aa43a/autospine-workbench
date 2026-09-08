"""Export or restore a source-bound wing-root review draft and geometry preview."""
import argparse
from pathlib import Path
from .artifacts import read_input,read_report,publish_report,export_document
from .wing_root_cli import read_roots
from .wing_root_draft import initial,validate
from .wing_root_review_view import render
from .region_binding_cli import sources
from .mapping_cli import export_html
from ..resolved_project import canonical_sha256


def read_draft(state,manifest,workspace,digest):
    doc=read_report(state,manifest['dataset_id'],'wing-root-drafts-v1',digest)
    roots=read_roots(state,manifest,workspace,doc['source_roots_sha256'])
    return validate(roots,doc)


def main():
    p=argparse.ArgumentParser(description='Choose wing roots and inspect reversible chest-follow geometry')
    for key in ('manifest','workspace','roots','html','draft-output'):p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--draft',type=Path)
    p.add_argument('--state-root',type=Path,default=Path('workspace'))
    args=p.parse_args();manifest=read_input(args.manifest);state=args.state_root;dataset=manifest['dataset_id']
    roots=read_roots(state,manifest,args.workspace,canonical_sha256(read_input(args.roots)))
    previous=read_report(state,dataset,'mount-contact-search-v1',roots['source_search_sha256'])
    contacts=read_report(state,dataset,'mount-contacts-v1',previous['source_contact_sha256'])
    mounts=read_report(state,dataset,'mount-candidates-v1',contacts['source_mount_sha256'])
    plan=read_report(state,dataset,'rig-plans-v1',mounts['source_plan_sha256'])
    candidate,_,_,_,images=sources(state,manifest,plan['source_skeleton_sha256'],args.workspace)
    draft=validate(roots,read_input(args.draft)) if args.draft else initial(roots)
    html=render(roots,candidate,images,draft)
    digest=publish_report(state,dataset,'wing-root-drafts-v1',draft)
    read_draft(state,manifest,args.workspace,digest)
    export_document(args.draft_output,draft);export_html(args.html,html);print(digest)


if __name__=='__main__':main()
