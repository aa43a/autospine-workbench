"""Build identity-aware numeric references for isolated pose variants."""
import argparse
import json
from pathlib import Path

from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.targets.character43.active_mesh_pose import sample_active
from autospine_workbench.asset.planning.component_local_solver import metrics


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('scene', type=Path)
    parser.add_argument('variant_report', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    scene = json.loads(args.scene.read_bytes())
    report = json.loads(args.variant_report.read_bytes())
    document = scene['skeleton']
    if canonical_sha256(document) != report['output_sha256']:
        raise ValueError('active_pose_probe_source_mismatch')
    start, end = report['runtime_interval']
    # Interval-local numerical coverage, including exact switch boundaries.
    times = sorted(set([0., start, end, max(0, start-1e-4), start+1e-4,
                        end-1e-4, end+1e-4] + [i/120 for i in range(int((end+.1)*120)+1)]))
    frames = []
    for time in times:
        frame = sample_active(document, report['animation'], time)
        geometry = {}
        for slot, flat in frame['triangles'].items():
            triangles = [flat[i:i+3] for i in range(0, len(flat), 3)]
            geometry[slot] = metrics(frame['setup_vertices'][slot], frame['vertices'][slot], triangles)
        frames.append(dict(time=time, attachments=frame['attachments'], vertices=frame['vertices'], geometry=geometry))
    result = dict(document_sha256=report['output_sha256'], animation=report['animation'],
        frames=frames, authority='none', selected=False,
        scope='interval_local_active_attachment_geometry_not_full_clip_acceptance')
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream)
    print(json.dumps(dict(frames=len(frames),geometry_failed_frames=sum(
        any(r['bad_triangles'] or r['max_edge_stretch']>2 for r in f['geometry'].values()) for f in frames))))


if __name__ == '__main__':
    main()
