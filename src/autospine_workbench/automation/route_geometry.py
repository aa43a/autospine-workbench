"""Bounded alpha/arm geometry evidence; never chooses a workflow or adopts a rig."""
import math
import hashlib
from ..png_rgba import decode_rgba_png, RgbaPngError

GRID = 64
ALPHA = 8
OFF_AXIS = .20
MIN_BROAD_RATIO = .15


def eligible(layer):
    role = layer.get('canonical_role', '')
    name = layer.get('name', '').lower()
    return (not layer.get('empty') and layer.get('disposition') != 'exclude'
            and (role in ('body.hand', 'body.arm', 'body.arm.upper', 'body.arm.lower', 'wear.sleeve')
                 or 'handwear' in name or 'sleeve' in name or '袖' in name))


def eligible_layers(project):
    return [layer for layer in project['resolved']['layers'] if eligible(layer)]


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _distance(p, a, b):
    dx, dy = b[0]-a[0], b[1]-a[1]
    t = max(0., min(1., ((p[0]-a[0])*dx+(p[1]-a[1])*dy)/(dx*dx+dy*dy)))
    return math.hypot(p[0]-a[0]-t*dx, p[1]-a[1]-t*dy)


def _components(active):
    remaining = set(active); sizes = []
    while remaining:
        seed = min(remaining); remaining.remove(seed); todo = [seed]; size = 0
        while todo:
            x, y = todo.pop(); size += 1
            for q in ((x-1, y), (x+1, y), (x, y-1), (x, y+1)):
                if q in remaining:
                    remaining.remove(q); todo.append(q)
        sizes.append(size)
    return sorted(sizes, reverse=True)


def analyze(project, images):
    """Accept get_project output and immutable layer PNG bytes, not asset paths.

    Sampling uses fixed normalized crop-cell centers, so translating/scaling
    the canvas and bones together preserves normalized geometry. Connectivity
    is a coarse sampled hint, not a substitute for full alpha partitioning.
    """
    resolved = project['resolved']
    joints = {j['id']: j for j in resolved.get('skeleton', {}).get('joints', [])}
    rows = []
    for layer in resolved['layers']:
        if not eligible(layer): continue
        side = layer.get('side', 'unknown')
        row = dict(layer_id=layer['id'], side=side, classification='insufficient_evidence',
                   reason_codes=[], joint_evidence=[], geometry=None, connectivity=None)
        rows.append(row); reasons = row['reason_codes']
        if side not in ('left', 'right'):
            reasons.append('character_side_unknown'); continue
        points = []
        for kind in ('shoulder', 'elbow', 'wrist'):
            joint = joints.get(f'{kind}.{side}', {})
            valid = all(_finite(joint.get(k)) for k in ('x', 'y'))
            row['joint_evidence'].append(dict(joint_id=f'{kind}.{side}', finite=valid,
                source=joint.get('source', 'missing'), review_state=joint.get('review_state', 'unreviewed'),
                decision_kind=joint.get('decision_kind'),
                manual_override=joint.get('decision_kind') == 'manual_absolute'
                    or joint.get('review_state') == 'manual_adjusted'))
            if valid: points.append([joint['x'], joint['y']])
        if len(points) != 3:
            reasons.append('arm_joint_missing_or_nonfinite'); continue
        lengths = [math.dist(points[i], points[i+1]) for i in (0, 1)]
        if min(lengths) <= 0 or not _finite(sum(lengths)):
            reasons.append('arm_segment_degenerate'); continue
        if any(j['review_state'] == 'unreviewed' for j in row['joint_evidence']):
            reasons.append('arm_joints_unreviewed')
        bbox = layer.get('bbox', {})
        if (not all(_finite(bbox.get(k)) for k in ('x', 'y', 'width', 'height'))
                or min(bbox['width'], bbox['height']) <= 0):
            reasons.append('layer_bbox_invalid'); continue
        raw = images.get(layer['id'])
        if raw is None:
            reasons.append('layer_image_missing'); continue
        try:
            image = decode_rgba_png(raw)
        except (RgbaPngError, ValueError):
            reasons.append('layer_image_invalid'); continue
        row['image_sha256'] = hashlib.sha256(raw).hexdigest()
        # Layer assets are cropped PNGs; refusing mismatched extents avoids
        # silently repeating the prior canvas/crop offset rendering bug.
        if (image.width, image.height) != (bbox['width'], bbox['height']):
            reasons.append('layer_image_bbox_mismatch'); continue
        active = set(); distances = []
        for y in range(GRID):
            for x in range(GRID):
                u, v = (x+.5)/GRID, (y+.5)/GRID
                px, py = min(image.width-1, int(u*image.width)), min(image.height-1, int(v*image.height))
                if image.pixels[4*(py*image.width+px)+3] < ALPHA: continue
                active.add((x, y))
                p = [bbox['x']+u*bbox['width'], bbox['y']+v*bbox['height']]
                distances.append(min(_distance(p, points[0], points[1]), _distance(p, points[1], points[2])))
        if not active:
            reasons.append('alpha_sampling_empty'); continue
        span = sum(lengths); distances.sort()
        normalized = [d/span for d in distances]
        ratio = sum(d > OFF_AXIS for d in normalized)/len(normalized)
        sizes = _components(active)
        major = sum(n/len(active) >= .10 for n in sizes)
        row['connectivity'] = dict(sampled_component_count=len(sizes), significant_component_count=major,
                                   largest_component_ratio=sizes[0]/len(active), sampling='normalized-grid64-4-connected')
        row['geometry'] = dict(arm_length_px=span, sample_count=len(active), sample_limit=GRID*GRID,
            distance_median_px=distances[len(distances)//2], distance_p90_px=distances[int((len(distances)-1)*.9)],
            normalized_distance_median=normalized[len(normalized)//2],
            normalized_distance_p90=normalized[int((len(normalized)-1)*.9)], off_axis_ratio=ratio,
            off_axis_threshold=OFF_AXIS, broad_ratio_threshold=MIN_BROAD_RATIO)
        if major >= 2 and sizes[0]/len(active) < .80:
            reasons.append('alpha_severely_disconnected')
        elif len(sizes) > 1:
            reasons.append('alpha_separated_regions_hint')
        row['classification'] = 'broad_off_axis_shape' if ratio >= MIN_BROAD_RATIO else 'no_broad_shape_evidence'
        reasons.append('semantic_review_required' if ratio >= MIN_BROAD_RATIO else 'narrow_shape_not_sleeveless_proof')
        if any(code in reasons for code in ('alpha_severely_disconnected', 'arm_joints_unreviewed')):
            row['classification'] = 'insufficient_evidence'
    return dict(schema='autospine.route-geometry-evidence/v1', profile='alpha-grid64-arm-distance-v1',
                project_id=project.get('id', resolved.get('project_id')),
                source_sha256=resolved.get('sha256'), records=rows, authority='none', production_authorized=False)
