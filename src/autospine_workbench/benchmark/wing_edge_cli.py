"""Replay the selected-wing package before exporting a reversible edge candidate."""
import argparse
from pathlib import Path
from .artifacts import read_input,read_report,publish_report
from .wing_root_cli import replay
from .wing_spine_preview import verify_report
from .wing_edge_preview import build
from .seam_candidate_hub import bundle_bytes
from .elbow_target_cli import archive
from ..resolved_project import canonical_sha256


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('manifest','workspace','base','output-dir'):p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--state-root',type=Path,default=Path('workspace'))
    a=p.parse_args();manifest=read_input(a.manifest);base=read_input(a.base);dataset=manifest['dataset_id']
    saved=read_report(a.state_root,dataset,'wing-spine-previews-v1',canonical_sha256(base))
    if saved!=base:raise ValueError('wing_edge_base_changed')
    files=bundle_bytes(a.base.parent,base['files']);draft=read_input(a.base.parent/'draft.json')
    roots=read_report(a.state_root,dataset,'wing-roots-v1',base['source_roots_sha256'])
    print('Replaying selected-wing source closure...',flush=True)
    fresh,candidate,images=replay(a.state_root,manifest,a.workspace,roots['source_search_sha256'])
    if fresh!=roots:raise ValueError('wing_root_replay_mismatch')
    verify_report(base,roots,candidate,images,draft)
    print('Building non-growing edge ownership candidate...',flush=True)
    report,outputs=build(base,files);outputs['preview.zip']=archive(outputs)
    for name,raw in outputs.items():
        target=a.output_dir/name
        if target.exists() and target.read_bytes()!=raw:raise ValueError('wing_edge_existing_changed')
    digest=publish_report(a.state_root,dataset,'wing-edge-previews-v1',report)
    for name,raw in outputs.items():
        target=a.output_dir/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
    print(digest);print(report['edge_ownership']['counts'])


if __name__=='__main__':main()
