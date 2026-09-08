"""Import user projection draft without reverting the corrected wing slot order."""
import argparse
from pathlib import Path
from .artifacts import read_input,read_report,publish_report
from .wing_projection_cli import read_candidate
from .wing_projection_apply import build
from .seam_candidate_hub import bundle_bytes
from .elbow_target_cli import archive
from ..resolved_project import canonical_sha256


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('manifest','source','candidate-source-dir','draft','output-dir'):p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--state-root',type=Path,default=Path('workspace'))
    a=p.parse_args();dataset=read_input(a.manifest)['dataset_id'];source=read_input(a.source);draft=read_input(a.draft)
    if read_report(a.state_root,dataset,'wing-back-order-previews-v1',canonical_sha256(source))!=source:raise ValueError('projection_apply_source_changed')
    candidate=read_candidate(a.state_root,dataset,draft['source_candidate_sha256'],a.candidate_source_dir)
    edge=read_report(a.state_root,dataset,'wing-edge-previews-v1',source['source_edge_preview_sha256'])
    report,files=build(source,bundle_bytes(a.source.parent,source['files']),candidate,edge,draft);files['preview.zip']=archive(files)
    for name,raw in files.items():
        path=a.output_dir/name
        if path.exists() and path.read_bytes()!=raw:raise ValueError('projection_apply_existing_changed')
    publish_report(a.state_root,dataset,'wing-projection-drafts-v1',draft)
    digest=publish_report(a.state_root,dataset,'wing-projection-applied-v1',report)
    for name,raw in files.items():
        path=a.output_dir/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    print(digest);print(report['projection_apply'])


if __name__=='__main__':main()
