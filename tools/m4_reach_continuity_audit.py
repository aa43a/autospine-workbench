"""Recheck exact Reach candidates; separate angle branch labels from actual motion."""
import argparse
from hashlib import sha256
import json
import math
from pathlib import Path

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.targets.character43.affine_pose import matrices


def inspect(document, animation, *, rate=240):
    if type(rate) is not int or not 1 <= rate <= 1000:
        raise ValueError('audit_rate_invalid')
    tracks = document['animations'][animation].get('bones', {})
    knots = {0.0}
    for track in tracks.values():
        for keys in track.values():
            times = [key.get('time', 0) for key in keys]
            if any(not math.isfinite(t) or t < 0 for t in times) or any(
                    b <= a for a, b in zip(times, times[1:])):
                raise ValueError('audit_times_invalid')
            if any(key.get('curve') not in (None, 'stepped') for key in keys):
                raise ValueError('audit_curve_unsupported')
            knots.update(times)
    duration = max(knots)
    if duration > 60:
        raise ValueError('audit_duration_limit')
    times = sorted(knots | {i/rate for i in range(math.ceil(duration*rate))}
                   | {(a+b)/2 for a,b in zip(sorted(knots), sorted(knots)[1:])})
    names = [b['name'] for b in document['bones']
             if b['name'].startswith(('upperarm_', 'forearm_', 'hand_'))]
    if not names:
        raise ValueError('audit_arm_bones_missing')
    poses = [matrices(document, animation, t) for t in times]
    rows = []
    for name in names:
        angles = [math.degrees(math.atan2(p[name][2], p[name][0])) for p in poses]
        steps = []
        for i, (a,b) in enumerate(zip(angles, angles[1:])):
            signed = (b-a+180) % 360-180
            steps.append(dict(start=times[i], end=times[i+1],
                              degrees=abs(signed), wrapped_label_delta=b-a))
        keys = tracks.get(name, {}).get('rotate', [])
        raw = [dict(start=a.get('time', 0), end=b.get('time', 0),
                    degrees=abs(b['value']-a['value'])) for a,b in zip(keys, keys[1:])]
        rows.append(dict(bone=name, maximum_local_key_step=max(raw, key=lambda x:x['degrees'], default=None),
                         maximum_world_sample_step=max(steps, key=lambda x:x['degrees'], default=None),
                         local_half_turn_intervals=[r for r in raw if r['degrees'] >= 180],
                         world_label_wraps=[r for r in steps if abs(r['wrapped_label_delta']) > 180]))
    return dict(authority='none', selected=False, rate=rate, sample_count=len(times), duration=duration,
                scope='sampled_affine_bone_motion_not_texture_occlusion_or_visual_acceptance', rows=rows)


def run(root, output):
    results = []
    for index in range(3):
        folder = root/str(index)
        report = json.loads((folder/'report.json').read_bytes())
        digest = report['candidate_bundle_sha256']
        files = AnimatedStore(folder/'isolated-store').read(digest)
        result = inspect(json.loads(files['skeleton.json']), 'external-motion')
        result.update(index=index, candidate=digest, skeleton_sha256=sha256(files['skeleton.json']).hexdigest(),
                      source_identity=report['source_identity'])
        results.append(result)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as stream:
        json.dump(dict(profile='reach-affine-continuity-audit-v1', authority='none', selected=False,
                       rows=results), stream, ensure_ascii=False, indent=2)
    for result in results:
        print(json.dumps(dict(index=result['index'], samples=result['sample_count'], rows=result['rows'])))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    run(args.root, args.output)
