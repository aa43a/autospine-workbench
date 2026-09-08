"""Export the exact canonical skeleton, limb candidates, and rebased wing union."""
import argparse
import json
from pathlib import Path
from .artifacts import read_input, read_report, publish_report
from .mesh_storage import read_mesh_report
from .region_binding_cli import sources
from .seam_candidate_hub import bundle_bytes
from .wing_limb_preview import build
from .elbow_target_cli import archive
from ..resolved_project import canonical_sha256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('manifest', 'workspace', 'source', 'limbs', 'ownership', 'output-dir'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--state-root', type=Path, default=Path('workspace'))
    args = parser.parse_args()
    manifest = read_input(args.manifest); dataset = manifest['dataset_id']
    source, donor = read_input(args.source), read_input(args.limbs)
    if args.limbs.stem != canonical_sha256(donor):
        raise ValueError('wing_limb_report_address')
    if read_report(args.state_root, dataset, 'wing-character-previews-v1', canonical_sha256(source)) != source:
        raise ValueError('wing_limb_context_address')
    atlas = read_mesh_report(args.state_root, dataset, canonical_sha256(read_input(args.ownership)))
    if atlas['schema'] != 'autospine.ownership-atlas/v1':
        raise ValueError('wing_limb_ownership_schema')
    print('Replaying canonical skeleton and source identity...', flush=True)
    candidate, _, skeleton, _, _ = sources(args.state_root, manifest, atlas['source_skeleton_sha256'], args.workspace)
    if canonical_sha256(candidate) != source['source_candidate_sha256']:
        raise ValueError('wing_limb_character_source')
    donor_files = bundle_bytes(args.limbs.parent, donor['files'])
    doc = json.loads(donor_files['skeleton.json']); expected = []
    for bone in skeleton['bones']:
        local = bone['setup_local']
        row = dict(name=bone['id'], x=local['x'], y=-local['y'], rotation=-local['rotation_degrees'], length=bone['length'])
        if bone['parent_id'] is not None:
            row['parent'] = bone['parent_id']
        expected.append(row)
    if doc['bones'] != expected:
        raise ValueError('wing_limb_canonical_skeleton')
    report, files = build(source, bundle_bytes(args.source.parent, source['files']), donor, donor_files, atlas)
    files['preview.zip'] = archive(files)
    for name, raw in files.items():
        path = args.output_dir / name
        if path.exists() and path.read_bytes() != raw:
            raise ValueError('wing_limb_existing_changed')
    digest = publish_report(args.state_root, dataset, 'wing-limb-previews-v1', report)
    for name, raw in files.items():
        path = args.output_dir / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)
    print(digest)
    print(f"Attachments: {len(report['regions'])}; limb residual context: {report['limb_residual_context_pixels']}")


if __name__ == '__main__':
    main()
