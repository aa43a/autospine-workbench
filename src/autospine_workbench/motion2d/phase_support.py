"""Interval-local source ankle stability, independent of target correction."""
import math

from ..bvh_fk import project_bvh_frames
from ..bvh_map_validation import bvh_map_sha256

PROFILE = 'source-contact-phase-stationarity-v1'


def inspect(bvh, mapping, hypothesis):
    if (hypothesis['source_sha256'] != bvh.source_sha256
            or hypothesis['map_sha256'] != bvh_map_sha256(mapping)):
        raise ValueError('phase_support_source_identity_mismatch')
    projection = project_bvh_frames(bvh, mapping)
    length = mapping['root']['reference_length_source_units']
    feet = {f['limb']: f['foot_joint_name'] for f in hypothesis.get('derived_contact', {}).get('feet', [])}
    records = []
    for marker in hypothesis['markers']:
        limb, start, end = marker['limb'], marker['start_tick'], marker['end_tick']
        if marker['kind'] != 'contact' or limb not in feet or not 0 <= start < end <= projection.duration_ticks:
            raise ValueError('phase_support_interval_invalid')
        samples = [(frame.tick, dict(frame.joints)[feet[limb]].world_xyz)
                   for frame in projection.frames if start <= frame.tick < end]
        if len(samples) < 2:
            records.append(dict(limb=limb, start_tick=start, end_tick=end, eligible=False,
                                reason='insufficient_interval_samples', samples=len(samples)))
            continue
        # Keep the exact half-open source interval: do not silently shorten it
        # until a moving foot happens to pass a stationarity threshold.
        drift = [math.dist(samples[0][1], point)/length for _, point in samples]
        worst = max(range(len(samples)), key=drift.__getitem__)
        eligible = drift[worst] <= .01
        records.append(dict(limb=limb, joint=feet[limb], start_tick=start, end_tick=end,
            eligible=eligible, reason='source_interval_stationary' if eligible else 'source_interval_drift',
            samples=len(samples), maximum_drift_ratio=drift[worst], worst_tick=samples[worst][0]))
    return dict(profile=PROFILE, authority='none', selected=False, records=records,
                source_sha256=bvh.source_sha256, map_sha256=hypothesis['map_sha256'],
                eligible_intervals=sum(r['eligible'] for r in records),
                maximum_drift_ratio=.01, scope='source_ankle_stability_not_floor_or_target_acceptance')
