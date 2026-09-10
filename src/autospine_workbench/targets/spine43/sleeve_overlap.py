"""Pairwise mesh overlap diagnostics, independent of texture/GPU visibility."""
import math


def cross(a, b, c):
    return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])


def intersection_area(first, second):
    """Clip a triangle against a triangle; shared edges have zero area."""
    polygon = [list(p) for p in first]
    orientation = 1 if cross(*second) >= 0 else -1
    for a, b in zip(second, second[1:]+second[:1]):
        source, polygon = polygon, []
        if not source:
            break
        previous = source[-1]
        before = orientation*cross(a, b, previous)
        for current in source:
            after = orientation*cross(a, b, current)
            if (before >= 0) != (after >= 0):
                u = before/(before-after)
                polygon.append([previous[k]+u*(current[k]-previous[k]) for k in (0, 1)])
            if after >= 0:
                polygon.append(current)
            previous, before = current, after
    if len(polygon) < 3:
        return 0.
    # Translate to avoid cancellation for canvas coordinates far from the origin.
    return abs(sum(cross(polygon[0], polygon[i], polygon[i+1])
                   for i in range(1, len(polygon)-1)))/2


def overlaps(triangles, vertices):
    import numpy as np
    points = np.asarray(vertices, dtype=float)
    indices = np.asarray(triangles)
    if (points.ndim != 2 or points.shape[1] != 2 or not np.isfinite(points).all()
            or indices.ndim != 2 or indices.shape[1] != 3
            or indices.dtype.kind not in 'iu' or indices.min() < 0 or indices.max() >= len(points)):
        raise ValueError('sleeve_overlap_geometry')
    polygons = points[indices]
    lo, hi = polygons.min(axis=1), polygons.max(axis=1)
    result = {}
    for i in range(len(polygons)):
        # Strict bbox intersection excludes mere edge/corner contact.
        candidates = np.flatnonzero(np.all(hi[i] > lo, axis=1) & np.all(hi > lo[i], axis=1))
        for j in candidates:
            if j <= i:
                continue
            area = intersection_area(polygons[i].tolist(), polygons[j].tolist())
            if area > 1e-8:
                result[i, int(j)] = area
    return result


def analyze(triangles, setup, animations, attachment=None, alpha=None):
    """Report newly intersecting material pairs without calling them visible failures."""
    baseline = overlaps(triangles, setup)
    baseline_pixels = {pair: peak_visibility(attachment, setup, alpha, pair)['dual_alpha8_pixels']
                       for pair in baseline} if attachment is not None else {}
    tracks = []
    for name, frames in sorted(animations.items()):
        peak = None
        affected = 0
        count = 0
        visible_frames = 0
        visible_peak = None
        tested_pairs = 0
        for frame in frames:
            count += 1
            if not math.isfinite(frame['time']):
                raise ValueError('sleeve_overlap_time')
            pairs = overlaps(triangles, frame['points'])
            if attachment is not None:
                frame_visible = False
                for pair in sorted(pairs):
                    probe = peak_visibility(attachment, frame['points'], alpha, pair)
                    tested_pairs += 1
                    excess = max(0, probe['dual_alpha8_pixels']-baseline_pixels.get(pair, 0))
                    frame_visible |= excess > 0
                    if excess and (visible_peak is None or excess > visible_peak['excess_pair_pixels']):
                        visible_peak = dict(time=frame['time'], triangles=list(pair),
                                            excess_pair_pixels=excess, setup_pair_pixels=baseline_pixels.get(pair, 0), **probe)
                visible_frames += frame_visible
            increased = [(max(0., area-baseline.get(pair, 0.)), pair, area)
                         for pair, area in pairs.items()]
            delta, pair, area = max(increased, default=(0., None, 0.))
            affected += delta > 1e-6
            if peak is None or delta > peak['excess_area_px2']:
                peak = dict(time=frame['time'], triangles=list(pair) if pair else None,
                            area_px2=area, setup_area_px2=baseline.get(pair, 0.), excess_area_px2=delta)
        tracks.append(dict(animation=name, frames=count, frames_with_increased_overlap=affected, peak=peak,
                           tested_pair_frames=tested_pairs, frames_with_increased_dual_alpha8=visible_frames,
                           visible_peak=visible_peak))
    return dict(profile='pairwise-triangle-overlap-v2', tracks=tracks,
                setup_overlapping_pairs=len(baseline), setup_pairwise_area_px2=sum(baseline.values()),
                status='diagnostic_only', texture_visibility='native_centers_all_intersecting_pairs' if attachment is not None else 'not_evaluated',
                framebuffer_status='not_evaluated',
                authority='none', production_authorized=False)


def peak_visibility(attachment, vertices, alpha, pair):
    """Inspect native centers for a pair; this is software double coverage, not GPU blending."""
    from .sleeve_contact_samples import coverage
    if pair is None:
        return dict(tested_pixels=0, dual_alpha8_pixels=0, max_min_alpha=None)
    flat = attachment['triangles']
    triangles = [flat[3*i:3*i+3] for i in pair]
    bounds = []
    for tri in triangles:
        p = [(vertices[i][0], -vertices[i][1]) for i in tri]
        bounds.append((min(x for x, y in p), min(y for x, y in p), max(x for x, y in p), max(y for x, y in p)))
    x0, y0 = (math.floor(max(b[k] for b in bounds)) for k in (0, 1))
    x1, y1 = (math.ceil(min(b[k] for b in bounds)) for k in (2, 3))
    if max(0, x1-x0)*max(0, y1-y0) > 1000000:
        raise ValueError('sleeve_overlap_roi_limit')
    locations = [[x+.5, y+.5] for y in range(y0, y1) for x in range(x0, x1)]
    first, second = [coverage(dict(attachment, triangles=t), vertices, alpha, locations) for t in triangles]
    dual = [min(a, b) for a, b in zip(first, second)]
    return dict(tested_pixels=len(dual), dual_alpha8_pixels=sum(a >= 8 for a in dual),
                max_min_alpha=max(dual, default=None), scope='pair_bbox_native_centers')
