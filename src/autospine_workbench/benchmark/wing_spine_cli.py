"""Replay wing source closure and export an immutable selected-root Spine preview."""
import argparse
from pathlib import Path
from .artifacts import read_input,read_report,publish_report
from .wing_root_cli import replay
from .wing_root_draft import validate
from .wing_spine_preview import build
from .elbow_target_cli import archive


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('manifest','workspace','draft','output-dir'):
        parser.add_argument('--'+key,type=Path,required=True)
    parser.add_argument('--state-root',type=Path,default=Path('workspace'))
    args=parser.parse_args();manifest=read_input(args.manifest);draft=read_input(args.draft)
    state=args.state_root;dataset=manifest['dataset_id']
    print('Replaying source closure...',flush=True)
    roots=read_report(state,dataset,'wing-roots-v1',draft['source_roots_sha256'])
    fresh,candidate,images=replay(state,manifest,args.workspace,roots['source_search_sha256'])
    if fresh!=roots:raise ValueError('wing_root_replay_mismatch')
    draft=validate(roots,draft)
    print('Building selected wing hinges...',flush=True)
    report,files=build(roots,candidate,images,draft)
    files['preview.zip']=archive(files)
    # Check every existing output before publishing any output in this folder.
    for name,raw in files.items():
        path=args.output_dir/name
        if path.exists() and path.read_bytes()!=raw:raise ValueError('wing_export_existing_changed')
    publish_report(state,dataset,'wing-root-drafts-v1',draft)
    digest=publish_report(state,dataset,'wing-spine-previews-v1',report)
    for name,raw in files.items():
        path=args.output_dir/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
    print(digest)


if __name__=='__main__':main()
