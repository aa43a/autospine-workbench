"""Build an isolated explicit pose geometry candidate from a version-bound request."""
import argparse
import json
from pathlib import Path

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.automation.storage_io import canonical_bytes
from autospine_workbench.targets.character43.pose_geometry_patch import compile_patch


def run(source, request_path, output, capture=False):
    receipt = json.loads((source/'report.json').read_bytes())
    parent = receipt['candidate_bundle_sha256']
    files = AnimatedStore(source/'isolated-store').read(parent)
    document = json.loads(files['skeleton.json'])
    request = json.loads(request_path.read_bytes())
    candidate, report = compile_patch(document, request)
    report['parent_artifact_sha256'] = parent
    output.mkdir(parents=True, exist_ok=False)
    (output/'request.json').write_bytes(canonical_bytes(request))
    (output/'report.json').write_bytes(canonical_bytes(report))
    (output/'skeleton.json').write_bytes(canonical_bytes(candidate))
    print(json.dumps(dict(sampled_geometry_passed=report['sampled_geometry_passed'],
        authored_point_error_px=report['authored_point_error_px'],
        unchanged_vertex_error_px=report['unchanged_vertex_error_px'],
        outside_interval_error_px=report['outside_interval_error_px'],
        sample_count=len(report['records']))), flush=True)
    if capture:
        from m4_squat_stage_players import stage
        stage(candidate, files, [r['time'] for r in report['records']], output/'candidate', parent)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('request', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--capture', action='store_true')
    args = parser.parse_args()
    run(args.source, args.request, args.output, args.capture)
