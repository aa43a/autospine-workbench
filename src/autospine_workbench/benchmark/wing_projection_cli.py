"""Produce source-bound back-projection groups and an unselected review draft."""
import argparse
from pathlib import Path
from .artifacts import read_input,read_report,publish_report,export_document
from .mapping_cli import export_html
from .seam_candidate_hub import bundle_bytes
from .wing_projection_groups import build,initial,validate
from .wing_projection_view import render
from ..resolved_project import canonical_sha256


def read_candidate(state,dataset,digest,source_folder):
    doc=read_report(state,dataset,'wing-projection-groups-v1',digest)
    source=read_report(state,dataset,'wing-split-previews-v1',doc['source_preview_sha256'])
    edge=read_report(state,dataset,'wing-edge-previews-v1',source['source_edge_preview_sha256'])
    expected=build(source,bundle_bytes(source_folder,source['files']),edge)
    if expected!=doc:raise ValueError('projection_replay')
    return doc


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('manifest','source','html','output','draft-output'):p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--draft',type=Path);p.add_argument('--state-root',type=Path,default=Path('workspace'))
    a=p.parse_args();dataset=read_input(a.manifest)['dataset_id'];source=read_input(a.source)
    if read_report(a.state_root,dataset,'wing-split-previews-v1',canonical_sha256(source))!=source:raise ValueError('projection_source_changed')
    edge=read_report(a.state_root,dataset,'wing-edge-previews-v1',source['source_edge_preview_sha256'])
    files=bundle_bytes(a.source.parent,source['files']);candidate=build(source,files,edge)
    draft=validate(candidate,edge,read_input(a.draft)) if a.draft else initial(candidate)
    digest=publish_report(a.state_root,dataset,'wing-projection-groups-v1',candidate)
    read_candidate(a.state_root,dataset,digest,a.source.parent)
    publish_report(a.state_root,dataset,'wing-projection-drafts-v1',draft)
    export_document(a.output,candidate);export_document(a.draft_output,draft)
    export_html(a.html,render(candidate,draft,source,files));print(digest)
    print([(g['id'],g['pixel_count']) for g in candidate['groups']])


if __name__=='__main__':main()
