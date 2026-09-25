"""Compare verified source projections without selecting or accepting a target view."""
import argparse
import json
import math
from pathlib import Path

from autospine_workbench.motion_bundle_reader import VerifiedMotionBundleReader
from autospine_workbench.resolved_project import canonical_sha256
from autospine_workbench.targets.character43.oblique_source import extract
from autospine_workbench.targets.character43.oblique_motion import project


def scan(vectors, yaws):
    limbs = {k: v for k, v in vectors.items()
             if k.startswith(('humanoid.arm.', 'humanoid.leg.'))}
    if not limbs or any(not points for points in limbs.values()):
        raise ValueError('view_scan_limbs_missing')
    if len({len(points) for points in limbs.values()}) != 1:
        raise ValueError('view_scan_samples_mismatch')
    result = []
    for yaw in yaws:
        if not math.isfinite(yaw) or not -90 <= yaw <= 90:
            raise ValueError('view_scan_yaw_invalid')
        rows = []
        for role, points in sorted(limbs.items()):
            ratios, angles = [], []
            for point in points:
                if len(point) != 3 or any(not math.isfinite(v) for v in point):
                    raise ValueError('view_scan_vector_invalid')
                length = math.sqrt(sum(v*v for v in point))
                if length <= 1e-12:
                    raise ValueError('view_scan_zero_length')
                x, y, _ = project(point, yaw)
                visible = math.hypot(x, y)
                ratios.append(visible / length)
                angles.append(math.degrees(math.atan2(y, x)) if visible > length*1e-6 else None)
            jumps = [abs((b-a+180) % 360-180) for a, b in zip(angles, angles[1:])
                     if a is not None and b is not None]
            index = min(range(len(ratios)), key=ratios.__getitem__)
            rows.append(dict(role=role, minimum_visibility=ratios[index], minimum_frame=index,
                             collapsed_samples=sum(v < .2 for v in ratios),
                             undefined_direction_samples=sum(a is None for a in angles),
                             max_adjacent_angle_degrees=max(jumps, default=None)))
        result.append(dict(yaw_degrees=yaw, records=rows))
    return result


def run(state, request_path, output):
    request = json.loads(request_path.read_bytes())
    identity = request['motion_identity']
    bundle = VerifiedMotionBundleReader(state).load(identity['clip_sha256'], identity['bundle_sha256'])
    vectors, _, _ = extract(bundle)
    from autospine_workbench.targets.character43.torso_projection_source import anchors, reference_shapes
    front, ticks = anchors(bundle, 0)
    candidates = scan(vectors, range(-90, 91, 5))
    for candidate in candidates:
        frames = [[project(point, candidate['yaw_degrees']) for point in frame] for frame in front]
        torso = reference_shapes(frames, [tick/1e6 for tick in ticks], front[0])
        rows = torso['records']
        candidate['torso'] = dict(source_supported=all(not row['reasons'] for row in rows),
                                 minimum_width_ratio=min(row['transverse'] for row in rows),
                                 maximum_width_ratio=max(row['transverse'] for row in rows),
                                 reasons=sorted({reason for row in rows for reason in row['reasons']}),
                                 limits=torso['limits'])
    report = dict(schema='autospine.source-view-scan/v1', motion_identity=identity,
                  request_sha256=canonical_sha256(request),
                  spatial_vectors_sha256=canonical_sha256(vectors),
                  candidates=candidates, authority='none', selected=False,
                  scope='source_samples_only_not_target_geometry_contact_or_visual_acceptance',
                  limitations=['view_change_requires_matching_character_artwork_and_occlusion',
                               'adjacent_angle_is_not_angular_velocity_or_interpolation_validation'])
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for name in ('state', 'request', 'output'):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    run(args.state, args.request, args.output)
