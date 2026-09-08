"""Replay source layers and export wing candidates in whole-character context."""
import argparse
from pathlib import Path
from .artifacts import read_input, read_report, publish_report
from .wing_root_cli import replay
from .wing_character_preview import build
from .seam_candidate_hub import bundle_bytes
from .elbow_target_cli import archive
from ..resolved_project import canonical_sha256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('manifest', 'workspace', 'source', 'output-dir'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--state-root', type=Path, default=Path('workspace'))
    args = parser.parse_args()
    manifest, source = read_input(args.manifest), read_input(args.source)
    dataset = manifest['dataset_id']
    saved = read_report(args.state_root, dataset, 'wing-pendant-previews-v1', canonical_sha256(source))
    if saved != source:
        raise ValueError('wing_context_source_changed')
    roots = read_report(args.state_root, dataset, 'wing-roots-v1', source['source_roots_sha256'])
    print('Replaying exact source layers...', flush=True)
    fresh, candidate, images = replay(args.state_root, manifest, args.workspace, roots['source_search_sha256'])
    if fresh != roots:
        raise ValueError('wing_context_roots_changed')
    report, files = build(source, bundle_bytes(args.source.parent, source['files']), roots, candidate, images)
    files['preview.zip'] = archive(files)
    for name, raw in files.items():
        path = args.output_dir / name
        if path.exists() and path.read_bytes() != raw:
            raise ValueError('wing_context_existing_changed')
    digest = publish_report(args.state_root, dataset, 'wing-character-previews-v1', report)
    for name, raw in files.items():
        path = args.output_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    print(digest)
    print(f"Source layers: {len(report['context_layers'])}; rigid context: {report['context_layer_count']}")


if __name__ == '__main__':
    main()
