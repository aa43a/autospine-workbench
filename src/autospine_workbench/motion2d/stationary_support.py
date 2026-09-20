"""Eligibility evidence for preserving near-stationary source ankle positions."""
import math
from ..bvh_fk import project_bvh_frames
from ..bvh_map_validation import bvh_map_sha256


def inspect(bvh, mapping, hypothesis):
    if (hypothesis['source_sha256'] != bvh.source_sha256
            or hypothesis['map_sha256'] != bvh_map_sha256(mapping)):
        raise ValueError('stationary_source_identity_mismatch')
    report = dict(profile='source-bilateral-full-clip-stationarity-v1', eligible=False,
                  source_sha256=bvh.source_sha256, map_sha256=hypothesis['map_sha256'],
                  maximum_drift_ratio=.01, records=[], scope='ankle_stationarity_not_floor_contact')
    projected = project_bvh_frames(bvh, mapping)
    markers = hypothesis['markers']
    if (len(markers) != 2 or {m['limb'] for m in markers} != {'leg.left', 'leg.right'}
            or any(m['start_tick'] != 0 or m['end_tick'] != projected.duration_ticks for m in markers)):
        report['reason'] = 'full_bilateral_support_not_observed'
        return report
    frames = [dict(f.joints) for f in projected.frames]
    length = mapping['root']['reference_length_source_units']
    for foot in hypothesis['derived_contact']['feet']:
        points = [f[foot['foot_joint_name']].world_xyz for f in frames]
        distances = [math.dist(points[0], p)/length for p in points]
        worst = max(range(len(points)), key=distances.__getitem__)
        report['records'].append(dict(limb=foot['limb'], joint=foot['foot_joint_name'],
            maximum_drift_ratio=distances[worst], worst_tick=projected.frames[worst].tick,
            passed=distances[worst] <= .01))
    report['eligible'] = len(report['records']) == 2 and all(r['passed'] for r in report['records'])
    report['reason'] = 'source_ankles_stationary' if report['eligible'] else 'source_ankle_drift_exceeds_limit'
    return report
