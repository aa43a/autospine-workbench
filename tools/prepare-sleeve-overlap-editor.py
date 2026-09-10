"""Prepare frozen native-editor inspection copies for exact reported overlap peaks."""
import argparse
import hashlib
from pathlib import Path

from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.benchmark.elbow_target_cli import export
from autospine_workbench.manifest_artifacts import require_safe_token
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.safe_input_files import read_real_file, strict_json_object
from autospine_workbench.targets.spine43.inspection_pose import freeze


def prepare(source, diagnostics, output, project):
    require_safe_token(project, 'project')
    root = (source/project).resolve(); destination = (output/project).resolve()
    for protected in (root, (diagnostics/project).resolve()):
        if destination == protected or protected in destination.parents or destination in protected.parents:
            raise ValueError('inspection_output_source')

    def read_report(folder):
        files = list(folder.glob('*.json'))
        if len(files) != 1:
            raise ValueError('inspection_report_inventory')
        report = strict_json_object(read_real_file(files[0], 32 << 20, 'inspection'), 'inspection')
        if files[0].stem != canonical_sha256(report) or report['project_id'] != project:
            raise ValueError('inspection_report_identity')
        if report['authority'] != 'none' or report['production_authorized'] is not False:
            raise ValueError('inspection_authority')
        return report

    source_report = read_report(root)
    diagnostic = read_report(diagnostics/project)
    if (source_report['schema'] != 'autospine.sleeve-export-report/v1'
            or diagnostic['purpose'] != 'sleeve_overlap_diagnostic'
            or diagnostic['source_report_sha256'] != canonical_sha256(source_report)):
        raise ValueError('inspection_source_mismatch')
    records = {(r['layer_id'], r['component_id']): r for r in source_report['records']}
    pending = []; outputs = []
    for row in diagnostic['records']:
        source_row = records[row['layer_id'], row['component_id']]
        if source_row['status'] != 'candidate_exported' or source_row['files'] != row['asset_sha256']:
            raise ValueError('inspection_asset_identity')
        name = row['layer_id']+'-'+row['component_id']; require_safe_token(name, 'region')
        bundle = root/name; assets = {}
        for filename, digest in source_row['files'].items():
            path = bundle/filename
            if bundle.resolve() not in path.resolve().parents:
                raise ValueError('inspection_asset_path')
            raw = read_real_file(path, 128 << 20, 'inspection asset')
            if hashlib.sha256(raw).hexdigest() != digest:
                raise ValueError('inspection_asset_changed')
            assets[filename] = raw
        image = 'images/'+name+'.png'
        if set(assets) != {'skeleton.json', 'skeleton.atlas', image}:
            raise ValueError('inspection_asset_inventory')
        doc = strict_json_object(assets['skeleton.json'], 'skeleton')
        for track in row['tracks']:
            peak = track['visible_peak']
            if peak is None:
                continue
            animation = track['animation']; require_safe_token(animation, 'animation')
            target = destination/name/animation
            frozen, error = freeze(doc, animation, peak['time'])
            frozen['skeleton']['images'] = (target/'images').as_posix()+'/'
            raw = canonical_bytes(frozen)
            receipt = dict(purpose='frozen_overlap_inspection', source_report_sha256=canonical_sha256(source_report),
                           diagnostic_sha256=canonical_sha256(diagnostic), source_files=source_row['files'],
                           animation=animation, source_time=peak['time'], peak=peak,
                           editor_sha256=hashlib.sha256(raw).hexdigest(), max_cpu_pose_error_px=error,
                           authority='none', production_authorized=False, framebuffer_status='not_evaluated')
            pending.extend([(target/'editor.json', raw), (target/image, assets[image]),
                            (target/'source-receipt.json', canonical_bytes(receipt))])
            outputs.append(str(target/'editor.json'))
    for path, raw in pending:
        export(path, raw)
    return outputs


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for flag in ('input', 'diagnostics', 'output'):
        p.add_argument('--'+flag, type=Path, required=True)
    p.add_argument('projects', nargs='+'); args = p.parse_args()
    for project in args.projects:
        for path in prepare(args.input, args.diagnostics, args.output, project):
            print(path, flush=True)


if __name__ == '__main__':
    main()
