"""Conservative trajectory-wide gain selection for ONLY the new response.

The root/head/cloth baseline and its existing repair channels are immutable.
This is planar mesh quality protection, not a rendered occlusion assertion.
"""
import math

from .affine_pose import matrices
from .joint_spring import interpolate
from .joint_secondary_clearance import capsules, penetration, compare as compare_clearance


def _area(points, triangle):
    a, b, c = [points[i] for i in triangle]
    return ((b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]))/2


def _metrics(points, triangles, areas, edges, lengths):
    ratios = [_area(points, tri)/area for tri, area in zip(triangles, areas)]
    return min(ratios), max(ratios), max(math.dist(points[a], points[b])/size for (a, b), size in zip(edges, lengths))


def _pose(base, bones, helpers, values):
    result = dict(base)
    for name in helpers:
        bone = bones[name]; parent = result[bone['parent']]
        pa, pb, pc, pd, px, py = parent
        angle = math.radians(bone['rotation']+values[name]); co, si = math.cos(angle), math.sin(angle)
        x, y = bone['x'], bone['y']
        result[name] = (pa*co+pb*si, -pa*si+pb*co, pc*co+pd*si, -pc*si+pd*co,
                        px+pa*x+pb*y, py+pc*x+pd*y)
    return result


def protect(document, baseline, animation, records, ticks, poses, sampler):
    bones = {b['name']: b for b in document['bones']}
    tracks = document['animations'][animation]['bones']
    rest = dict(baseline, animations={'setup': {}}); setup_pose = matrices(rest, 'setup', 0)
    collision_indices = set(range(0, len(ticks), 2)) | {len(ticks)-1}
    proxy_frames = {i: capsules(poses[i]) for i in collision_indices}
    summaries = []
    for record in records:
        slot = record['slot']; mesh = document['skins'][0]['attachments'][slot][slot]
        flat = mesh['triangles']; triangles = [flat[i:i+3] for i in range(0, len(flat), 3)]
        points = sampler(rest, 'setup', 0, slot, transforms=setup_pose)
        areas = [_area(points, tri) for tri in triangles]
        edges = sorted({tuple(sorted((tri[j], tri[(j+1)%3]))) for tri in triangles for j in range(3)})
        lengths = [math.dist(points[a], points[b]) for a, b in edges]
        if any(abs(a) < 1e-10 for a in areas) or any(v < 1e-10 for v in lengths):
            raise ValueError('joint_secondary_setup_degenerate')
        base_metrics = []; base_penetration = {}
        for index, (time, pose) in enumerate(zip(ticks, poses, strict=True)):
            points = sampler(baseline, animation, time, slot, transforms=pose)
            base_metrics.append(_metrics(points, triangles, areas, edges, lengths))
            if index in collision_indices: base_penetration[index] = penetration(points, proxy_frames[index])
        helpers = record['helpers']; values = {}
        for name in helpers:
            keys = tracks[name]['rotate']; times = [k['time'] for k in keys]; offsets = [k['value'] for k in keys]
            values[name] = [interpolate(times, offsets, t) for t in ticks]
        history = []; selected_gain = 0.
        for gain in (1., .5, .25, .125, .0625, .03125, 0.):
            worst = None; failed = 0; minimum = 1.; maximum = stretch = 1.; penetration_peak = 0.; collision_failed = 0
            for index, (time, pose, before) in enumerate(zip(ticks, poses, base_metrics, strict=True)):
                response_pose = _pose(pose, bones, helpers, {n: values[n][index]*gain for n in helpers})
                current = sampler(document, animation, time, slot, transforms=response_pose)
                lo, hi, edge = _metrics(current, triangles, areas, edges, lengths)
                minimum = min(minimum, lo); maximum = max(maximum, hi); stretch = max(stretch, edge)
                # Add safety margin where the baseline has it. Existing baseline
                # failures stay visible; zero new response never hides them.
                limits = (min(.55, before[0]), max(1.9, before[1]), max(1.9, before[2]))
                severity = max(limits[0]-lo, hi-limits[1], edge-limits[2])
                clearance = None
                if index in collision_indices:
                    clearance = compare_clearance(current, base_penetration[index], proxy_frames[index])
                    penetration_peak = max(penetration_peak, clearance['new_penetration_px'])
                    collision_failed += int(not clearance['passed'])
                    severity = max(severity, clearance['new_penetration_px']-clearance['allowed_increase_px'])
                if severity > 1e-7:
                    failed += 1
                    if worst is None or severity > worst['severity']:
                        worst = dict(time=time, severity=severity, min_area_ratio=lo,
                                     max_area_ratio=hi, max_edge_stretch=edge, baseline=list(before), clearance=clearance)
            history.append(dict(gain=gain, failed_samples=failed, min_area_ratio=minimum,
                                max_area_ratio=maximum, max_edge_stretch=stretch, worst=worst,
                                new_proxy_penetration_px=penetration_peak, collision_failed_samples=collision_failed))
            if not failed:
                selected_gain = gain; break
        for name in helpers:
            for key in tracks[name]['rotate']: key['value'] *= selected_gain
        record['requested_peak_response_deg'] = record['peak_response_deg']
        record['effective_gain'] = selected_gain
        record['peak_response_deg'] *= selected_gain
        record['motion_status'] = ('geometry_guard_suppressed' if selected_gain == 0 else
                                  'responding' if record['peak_response_deg'] > 1e-6 else 'static_driver_no_inertia')
        for spring in record['springs']:
            spring['effective_gain'] = selected_gain
            spring['effective_peak_angle_deg'] = spring['peak_angle_deg']*selected_gain
        summary = dict(slot=slot, profile='new-response-only-trajectory-gain-search-v1',
            status='within_headroom' if selected_gain else 'suppressed_for_geometry',
            requested_gain=1., effective_gain=selected_gain, sample_count=len(ticks), history=history,
            original_body_and_deform_unchanged=True, baseline_limits_preserved=True,
            collision=dict(profile='baseline-relative-planar-head-torso-capsules-v1',
                sample_count=len(collision_indices), allowed_added_penetration_px=1.,
                available=any(proxy_frames.values()), original_coverage_preserved=True,
                scope='geometric_vertices_at_60hz_no_alpha_depth_or_clothing_self_collision'))
        record['geometry_guard'] = summary; summaries.append(summary)
    return summaries
