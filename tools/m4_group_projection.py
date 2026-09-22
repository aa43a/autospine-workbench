"""Inspect exact imported source bundles without rebuilding character candidates."""
import argparse
import json
from pathlib import Path
from urllib.request import urlopen

from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.targets.character43.oblique_source import extract
from autospine_workbench.targets.character43.group_projection import compare


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('source_job')
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    if not args.source_job.startswith('motion-') or not args.source_job[7:].isalnum():
        raise ValueError('invalid_source_job')
    with urlopen('http://127.0.0.1:8918/api/motions/'+args.source_job, timeout=120) as response:
        job = json.load(response)
    identity = job['result']['motion']
    bundle = VerifiedMotionBundleReader(Path('workspace')).load(identity['clip_sha256'], identity['bundle_sha256'])
    vectors, _, _ = extract(bundle)
    tracks = [t for t in bundle.motion['tracks'] if t['property'] == 'rotation']
    ticks = [k['tick'] for k in tracks[0]['keys']]
    if any([k['tick'] for k in track['keys']] != ticks for track in tracks):
        raise ValueError('source_ticks_mismatch')
    report = compare(vectors, [t/bundle.motion['ticks_per_second'] for t in ticks])
    report.update(source_job=args.source_job, source_identity=identity)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    from autospine_workbench.targets.character43.group_projection_pose import source_segments, pose
    from m4_group_projection_view import render
    segments = source_segments(bundle)
    # Both signs remain visible, never silently select one from a tied score.
    modes = {'original': {}}
    for sign in (-90, 90):
        modes[f'侧向 {sign}°（长度评分分组）'] = {
            row['group']: sign if sign in row['best_visibility_yaws'] else 0
            for row in report['records']}
    variants = {name: [pose(segments, i, planes) for i in range(len(ticks))]
                for name, planes in modes.items()}
    from autospine_workbench.targets.character43.group_projection_constraints import preserve_ankles, measure
    original = variants['original']
    report['endpoint_constraints'] = []
    for name, frames in list(variants.items()):
        if name == 'original': continue
        for sign in (-1, 1):
            checked = [preserve_ankles(a, b, sign) for a, b in zip(original, frames)]
            label = name+f' · 保持源脚踝，膝分支 {sign}'
            variants[label] = [item[0] for item in checked]
            report['endpoint_constraints'].append(dict(variant=label,
                failures=[dict(frame=i, time=report['times'][i], **failure)
                          for i, item in enumerate(checked) for failure in item[1]]))
    report['endpoint_metrics'] = {name: measure(original, frames, report['times'])
                                  for name, frames in variants.items()}
    args.output.write_text(json.dumps(report, ensure_ascii=False), encoding='utf-8')
    args.output.with_suffix('.html').write_text(render(report['times'], variants,
        report['endpoint_constraints'], report['endpoint_metrics']), encoding='utf-8')
    print(json.dumps([dict(group=r['group'], best=r['best_visibility_yaws'],
        scores=[(a['yaw_degrees'], a['collapsed_samples'], a['minimum_visibility'])
                for a in r['alternatives']]) for r in report['records']]))


if __name__ == '__main__':
    main()
