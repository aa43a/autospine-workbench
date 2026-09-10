"""Create local Spine editor copies with explicit image paths; never alter candidates."""
import argparse
import hashlib
import json
from pathlib import Path

from autospine_workbench.benchmark.elbow_target_cli import export
from autospine_workbench.manifest_artifacts import require_safe_token
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.safe_input_files import read_real_file, strict_json_object


def prepare(source, output, project):
    require_safe_token(project, 'project')
    root = (source / project).resolve()
    destination = (output / project).resolve()
    if destination == root or root in destination.parents or destination in root.parents:
        raise ValueError('editor_output_overlaps_source')
    reports = list(root.glob('*.json'))
    if len(reports) != 1:
        raise ValueError('editor_export_inventory')
    report = strict_json_object(read_real_file(reports[0], 32 << 20, 'export'), 'export')
    if (reports[0].stem != canonical_sha256(report)
            or report['schema'] != 'autospine.sleeve-export-report/v1'
            or report['project_id'] != project or report['authority'] != 'none'
            or report['production_authorized'] is not False):
        raise ValueError('editor_export_source')
    pending = []
    for row in report['records']:
        if row['status'] != 'candidate_exported':
            continue
        name = row['layer_id'] + '-' + row['component_id']
        require_safe_token(name, 'region')
        bundle = root / name
        assets = {}
        for filename, digest in row['files'].items():
            path = bundle / filename
            if bundle.resolve() not in path.resolve().parents:
                raise ValueError('editor_asset_path')
            raw = read_real_file(path, 128 << 20, 'editor source')
            if hashlib.sha256(raw).hexdigest() != digest:
                raise ValueError('editor_asset_changed')
            assets[filename] = raw
        image_name = 'images/' + name + '.png'
        if set(assets) != {'skeleton.json', 'skeleton.atlas', image_name}:
            raise ValueError('editor_asset_inventory')
        doc = strict_json_object(assets['skeleton.json'], 'skeleton')
        doc['skeleton']['images'] = (destination / name / 'images').as_posix() + '/'
        encode = lambda value: json.dumps(value, sort_keys=True, ensure_ascii=False,
                                          allow_nan=False, indent=2).encode('utf-8')
        editor = encode(doc)
        receipt = dict(source_report_sha256=canonical_sha256(report), source_files=row['files'],
                       editor_json_sha256=hashlib.sha256(editor).hexdigest(),
                       changes=['skeleton.images'], authority='none', production_authorized=False,
                       purpose='local_editor_inspection', runtime_evidence_transferred=False)
        pending.extend([(destination / name / 'editor.json', editor),
                        (destination / name / image_name, assets[image_name]),
                        (destination / name / 'source-receipt.json', encode(receipt))])
    for path, data in pending:
        export(path, data)
    return [str(path) for path, _ in pending if path.name == 'editor.json']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('projects', nargs='+')
    args = parser.parse_args()
    for project in args.projects:
        print(json.dumps(prepare(args.input, args.output, project)), flush=True)


if __name__ == '__main__':
    main()
