"""Publish an exact uploaded split draft and a separate reversible Spine candidate."""
import argparse
from pathlib import Path
from .artifacts import read_input,read_report,publish_report
from .wing_split_draft import validate
from .wing_split_preview import build
from .seam_candidate_hub import bundle_bytes
from .elbow_target_cli import archive
from ..resolved_project import canonical_sha256


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('manifest','source','draft','output-dir'):p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--state-root',type=Path,default=Path('workspace'))
    a=p.parse_args();dataset=read_input(a.manifest)['dataset_id'];source=read_input(a.source)
    if read_report(a.state_root,dataset,'wing-edge-previews-v1',canonical_sha256(source))!=source:raise ValueError('wing_split_source_changed')
    files=bundle_bytes(a.source.parent,source['files']);draft=validate(source,read_input(a.draft))
    report,outputs=build(source,files,draft);outputs['preview.zip']=archive(outputs)
    for name,raw in outputs.items():
        path=a.output_dir/name
        if path.exists() and path.read_bytes()!=raw:raise ValueError('wing_split_output_changed')
    publish_report(a.state_root,dataset,'wing-split-drafts-v1',draft)
    digest=publish_report(a.state_root,dataset,'wing-split-previews-v1',report)
    for name,raw in outputs.items():
        path=a.output_dir/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    print(digest);print(report['split_counts'])


if __name__=='__main__':main()
