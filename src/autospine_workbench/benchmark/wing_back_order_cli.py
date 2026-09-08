"""Publish an independent local wing-back order candidate with exact source identity."""
import argparse
from pathlib import Path
from .artifacts import read_input,read_report,publish_report
from .seam_candidate_hub import bundle_bytes
from .elbow_target_cli import archive
from .wing_back_order import build
from ..resolved_project import canonical_sha256


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('manifest','source','output-dir'):p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--state-root',type=Path,default=Path('workspace'))
    a=p.parse_args();dataset=read_input(a.manifest)['dataset_id'];source=read_input(a.source)
    if read_report(a.state_root,dataset,'wing-split-previews-v1',canonical_sha256(source))!=source:raise ValueError('back_order_source_changed')
    report,files=build(source,bundle_bytes(a.source.parent,source['files']));files['preview.zip']=archive(files)
    for name,raw in files.items():
        path=a.output_dir/name
        if path.exists() and path.read_bytes()!=raw:raise ValueError('back_order_output_changed')
    digest=publish_report(a.state_root,dataset,'wing-back-order-previews-v1',report)
    for name,raw in files.items():
        path=a.output_dir/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    print(digest);print(report['slot_order_change'])


if __name__=='__main__':main()
