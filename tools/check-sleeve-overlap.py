"""Diagnose self-overlap in exact sleeve exports; does not grant visual admission."""
import argparse
import hashlib
from pathlib import Path

from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.benchmark.elbow_target_cli import export
from autospine_workbench.manifest_artifacts import require_safe_token
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.safe_input_files import read_real_file, strict_json_object
from autospine_workbench.targets.spine43.continuous_pose import world
from autospine_workbench.targets.spine43.sleeve_overlap import analyze, peak_visibility
from autospine_workbench.targets.spine43.seam_raster import texture
from autospine_workbench.asset.planning.sleeve_motion_envelope import MOTIONS


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('projects', nargs='+')
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    paths = [Path(__file__).resolve()] + [repo/'src/autospine_workbench'/p for p in (
        'targets/spine43/sleeve_overlap.py', 'targets/spine43/continuous_pose.py',
        'targets/spine43/sleeve_contact_samples.py', 'targets/spine43/seam_raster.py',
        'asset/planning/sleeve_motion_envelope.py')]
    identity = lambda: {p.relative_to(repo).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    engine = identity()
    for project in args.projects:
        require_safe_token(project, 'project')
        root = (args.input/project).resolve()
        destination = (args.output/project).resolve()
        if root == destination or root in destination.parents or destination in root.parents:
            raise ValueError('sleeve_overlap_output_source')
        reports = list(root.glob('*.json'))
        if len(reports) != 1:
            raise ValueError('sleeve_overlap_report_inventory')
        report = strict_json_object(read_real_file(reports[0], 32 << 20, 'export'), 'export')
        if (reports[0].stem != canonical_sha256(report) or report['schema'] != 'autospine.sleeve-export-report/v1'
                or report['project_id'] != project or report['authority'] != 'none'
                or report['production_authorized'] is not False):
            raise ValueError('sleeve_overlap_source')
        records = []
        for row in report['records']:
            if row['status'] != 'candidate_exported':
                continue
            name = row['layer_id']+'-'+row['component_id']
            require_safe_token(name, 'region')
            bundle = root/name
            assets = {}
            for filename, digest in row['files'].items():
                path = bundle/filename
                if bundle.resolve() not in path.resolve().parents:
                    raise ValueError('sleeve_overlap_asset_path')
                raw = read_real_file(path, 128 << 20, 'overlap asset')
                if hashlib.sha256(raw).hexdigest() != digest:
                    raise ValueError('sleeve_overlap_asset_changed')
                assets[filename] = raw
            if set(assets) != {'skeleton.json', 'skeleton.atlas', 'images/'+name+'.png'}:
                raise ValueError('sleeve_overlap_asset_inventory')
            doc = strict_json_object(assets['skeleton.json'], 'skeleton')
            if set(doc['animations']) != {n for n, _ in MOTIONS}:
                raise ValueError('sleeve_overlap_motion_inventory')
            attachment = doc['skins'][0]['attachments'][name][name]
            flat = attachment['triangles']
            triangles = [flat[i:i+3] for i in range(0, len(flat), 3)]
            setup = world(dict(doc, animations={'setup': {'bones': {}}}), 0)[name]
            animations = {}
            for animation, keys in doc['animations'].items():
                single = dict(doc, animations={animation: keys})
                animations[animation] = [dict(time=i/128, points=world(single, i/128)[name]) for i in range(257)]
            alpha = texture(assets['images/'+name+'.png'])
            result = analyze(triangles, setup, animations, attachment, alpha)
            for track in result['tracks']:
                peak = track['peak']
                points = animations[track['animation']][round(peak['time']*128)]['points']
                peak['software_texture_probe'] = peak_visibility(attachment, points, alpha, peak['triangles'])
            result.update(layer_id=row['layer_id'], component_id=row['component_id'],
                          asset_sha256=row['files'], pose_sha256=canonical_sha256(animations))
            records.append(result)
            print(project, name, 'peak new pair area', max(t['peak']['excess_area_px2'] for t in result['tracks']), flush=True)
        receipt = dict(purpose='sleeve_overlap_diagnostic', project_id=project,
                       source_report_sha256=canonical_sha256(report), records=records, algorithm_files=engine,
                       authority='none', production_authorized=False, framebuffer_status='not_evaluated')
        if identity() != engine:
            raise ValueError('sleeve_overlap_code_changed')
        export(destination/(canonical_sha256(receipt)+'.json'), canonical_bytes(receipt))


if __name__ == '__main__':
    main()
