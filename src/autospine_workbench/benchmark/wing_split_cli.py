"""Export source-bound interactive mask drafts without applying a source-layer edit."""
import argparse
from pathlib import Path
from .artifacts import read_input,read_report,publish_report,export_document
from .mapping_cli import export_html
from .seam_candidate_hub import bundle_bytes
from .wing_split_draft import initial,validate
from .wing_split_view import render
from ..resolved_project import canonical_sha256


def read_draft(state,dataset,digest):
    doc=read_report(state,dataset,'wing-split-drafts-v1',digest)
    source=read_report(state,dataset,'wing-edge-previews-v1',doc['source_preview_sha256'])
    return validate(source,doc)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('manifest','source','html','draft-output'):p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--draft',type=Path);p.add_argument('--state-root',type=Path,default=Path('workspace'))
    a=p.parse_args();dataset=read_input(a.manifest)['dataset_id'];source=read_input(a.source)
    exact=read_report(a.state_root,dataset,'wing-edge-previews-v1',canonical_sha256(source))
    if exact!=source:raise ValueError('wing_split_source_changed')
    files=bundle_bytes(a.source.parent,source['files'])
    draft=validate(source,read_input(a.draft)) if a.draft else initial(source)
    page=render(source,files,draft)
    digest=publish_report(a.state_root,dataset,'wing-split-drafts-v1',draft)
    read_draft(a.state_root,dataset,digest)
    export_document(a.draft_output,draft);export_html(a.html,page);print(digest)


if __name__=='__main__':main()
