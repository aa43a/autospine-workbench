"""Replay fixed gap tracks and compare dual-attachment motion compensation."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
from ..resolved_project import canonical_sha256
from ..targets.spine43.continuous_pose import world
from ..targets.spine43.seam_gap_tracks import associate
from ..targets.spine43.seam_gap_transport import compare
from .seam_gap_context_cli import load
from .seam_gap_tracks_cli import compile_report as baseline
from .seam_gap_tracks_view import render


def compile_report(before, after, before_dir, after_dir):
    visuals = []
    old, _ = baseline(before, after, before_dir, after_dir, visual_sink=visuals)
    doc = json.loads(load(after, after_dir, 'skeleton.json'))
    poses = [world(doc, tick/30) for tick in range(61)]; attachments = doc['skins'][0]['attachments']
    report = deepcopy(old); rows = []
    for previous in old['relations']:
        frames = [[] for _ in range(61)]; evidence = []
        for track in previous['tracks']:
            for component in track['components']:
                frames[component['frame']].append(component)
        for frame in frames:
            frame.sort(key=lambda c: int(c['id'].split('-c')[1]))
        names = (previous['driver'], previous['follower'])

        def distance(a, b):
            result = compare(a, b, poses, attachments, names)
            evidence.append(dict(source=a['id'], target=b['id'], **result))
            return result['distance']

        row = associate(frames, distance_fn=distance)
        row.update(driver=names[0], follower=names[1], transport_evidence=evidence,
                   baseline_track_count=len(previous['tracks']))
        if row['pixel_samples'] != previous['pixel_samples']:
            raise ValueError('gap_transport_pixel_conservation')
        rows.append(row)
    report.update(schema='autospine.seam-gap-transport/v1', profile='dual-triangle4-consensus1-residual3-v1',
                  source_tracks_sha256=canonical_sha256(old), relations=rows)
    page = render(report, visuals).replace('轨迹是 3px 邻域关联候选', '轨迹使用双附件局部三角形运动补偿，残差上限 3px').replace(
        '此页没有采用操作。', '两附件预测分歧超过 1px 时拒绝关联；此页没有采用操作。')
    return report, page


def read_transport(saved, before, after, before_dir, after_dir):
    expected, _ = compile_report(before, after, before_dir, after_dir)
    if canonical_sha256(saved) != canonical_sha256(expected):
        raise ValueError('gap_transport_replay_mismatch')
    return saved


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('before','after','before-dir','after-dir','output-dir'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    try:
        report, page = compile_report(json.loads(args.before.read_text()), json.loads(args.after.read_text()), args.before_dir, args.after_dir)
        digest = canonical_sha256(report); args.output_dir.mkdir(parents=True, exist_ok=True)
        target = args.output_dir/(digest+'.json')
        if target.exists() and canonical_sha256(json.loads(target.read_text())) != digest:
            raise ValueError('gap_transport_existing_corrupt')
        target.write_text(json.dumps(report, sort_keys=True, indent=2)+'\n', encoding='utf-8')
        (args.output_dir/'index.html').write_text(page, encoding='utf-8')
        print(json.dumps(dict(artifact_sha256=digest, relations=[dict(driver=r['driver'],before=r['baseline_track_count'],after=len(r['tracks']),longest=max((t['observed_frames'] for t in r['tracks']),default=0)) for r in report['relations']]))); return 0
    except (ValueError, KeyError, TypeError, IndexError, OSError):
        print(json.dumps(dict(status='blocked', reason_code='gap_transport_input_or_replay_failed', authority='none'))); return 1


if __name__ == '__main__':
    raise SystemExit(main())
