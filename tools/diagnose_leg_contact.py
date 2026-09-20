"""Test bounded affine leg rotations on stable source contact intervals.

This reports endpoint solutions only, never exports or adopts a target animation.
"""
import argparse
from copy import deepcopy
from hashlib import sha256
import json
import math
from pathlib import Path
from urllib.request import urlopen

from autospine_workbench.automation.animated_store import AnimatedStore
from autospine_workbench.bvh_parser import parse_bvh
from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.motion2d.phase_support import inspect
from autospine_workbench.targets.character43.affine_leg_ik import solve
from autospine_workbench.targets.character43.affine_pose import matrices
from autospine_workbench.targets.character43.contact_phase_candidate import build
from autospine_workbench.targets.character43.numeric_reference import read
from autospine_workbench.targets.spine43.continuous_pose import interpolate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('artifact_sha256')
    parser.add_argument('source_job_id')
    parser.add_argument('output', type=Path)
    parser.add_argument('--state-root', type=Path, default=Path('workspace'))
    args = parser.parse_args()
    if not args.source_job_id.startswith('motion-') or not args.source_job_id[7:].isalnum():
        parser.error('invalid source job')
    with urlopen('http://127.0.0.1:8918/api/motions/'+args.source_job_id, timeout=180) as response:
        job = json.load(response)
    identity = job['result']['motion']
    bundle = VerifiedMotionBundleReader(args.state_root).load(identity['clip_sha256'], identity['bundle_sha256'])
    files = AnimatedStore(args.state_root).read(args.artifact_sha256)
    contact = json.loads(files['motion-contact.json'])
    support = inspect(parse_bvh(bundle.raw_bvh), bundle.bvh_map, contact['hypothesis'])
    motion = json.loads(files['motion-ir.json'])
    if motion['markers']:
        parser.error('original source labels must not be replaced')
    eligible = {(r['limb'], r['start_tick'], r['end_tick']) for r in support['records'] if r['eligible']}
    motion['markers'] = [m for m in contact['hypothesis']['markers']
                         if (m['limb'], m['start_tick'], m['end_tick']) in eligible]
    if not motion['markers']:
        parser.error('no stable source intervals')
    name = 'external-motion'
    original = json.loads(files['skeleton.json'])
    times = [r['time'] for r in read(files)['animations'][name]]
    length = contact['before']['drift_limit_px']*100
    _, phase = build(original, name, motion, times, length, release_seconds=.25)
    experiments = []
    for root_enabled in (False, True):
        doc = deepcopy(original)
        keys = doc['animations'][name]['bones']['root']['translate']
        correction_rows, output = [], []
        for row in phase['rows']:
            v = row['correction'] if root_enabled else [0, 0]
            norm = math.hypot(*v)
            scale = min(1, .15*length/norm) if norm else 1
            shift = [scale*x for x in v]
            base = interpolate([dict(time=k['time'], vertices=[k['x'], k['y']]) for k in keys], row['time'], 'vertices')
            output.append(dict(time=row['time'], x=base[0]+shift[0], y=base[1]+shift[1]))
            correction_rows.append(dict(time=row['time'], shift=shift))
        doc['animations'][name]['bones']['root']['translate'] = output
        records = []
        for marker in motion['markers']:
            side = 'l' if marker['limb'] == 'leg.left' else 'r'
            start, end = (marker[k]/motion['ticks_per_second'] for k in ('start_tick', 'end_tick'))
            anchor = matrices(doc, name, start)['foot_'+side][4:6]
            samples = []
            for row in phase['rows']:
                if start <= row['time'] < end:
                    solved = solve(doc, name, row['time'], 'thigh_'+side, 'calf_'+side, 'foot_'+side, anchor)
                    samples.append(dict(time=row['time'], **solved))
            records.append(dict(limb=marker['limb'], start=start, end=end, anchor=anchor, samples=samples,
                unresolved_samples=sum(r['solution'] is None for r in samples)))
        speed = max((math.dist(a['shift'], b['shift'])/(b['time']-a['time'])
                     for a, b in zip(correction_rows, correction_rows[1:])), default=0.)
        experiments.append(dict(root_enabled=root_enabled, intervals=records,
            root_speed_px_per_second=speed, root_speed_limit_px_per_second=2*length,
            root_speed_passed=speed <= 2*length,
            unresolved_samples=sum(r['unresolved_samples'] for r in records)))
    report = dict(profile='source-qualified-affine-leg-diagnostic-v1', selected=False, authority='none',
        input_artifact_sha256=args.artifact_sha256, input_motion_sha256=sha256(files['motion-ir.json']).hexdigest(),
        source_job_id=args.source_job_id, motion_identity=identity, source_support=support,
        experiments=experiments, limits=dict(root_ratio=.15, rotation_degrees=30, release_seconds=.25),
        validation='endpoint_search_only_no_temporal_geometry_or_runtime_acceptance')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps([dict(root_enabled=r['root_enabled'], unresolved_samples=r['unresolved_samples'],
                          root_speed_passed=r['root_speed_passed']) for r in experiments]))


if __name__ == '__main__':
    main()
