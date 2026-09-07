"""Dense elbow area diagnostics; experimental thresholds confer no authority."""
from ...resolved_project import canonical_sha256
from .mesh_weights import evaluate_mesh, _area, _deform, _frames


def analyze_area(vertices, triangles, weights, bones):
    basic = evaluate_mesh(vertices, triangles, weights, bones)
    areas = [_area(vertices, t) for t in triangles]
    if any(abs(a) <= 1e-9 for a in areas):
        raise ValueError('mesh_area_degenerate_setup')
    minimum, maximum, worst = float('inf'), -float('inf'), None
    inverted = 0
    worst_fraction = 0.
    for angle in range(-90, 91):
        moved = _deform(weights, _frames(bones, angle))
        ratios = [_area(moved, t)/a for t, a in zip(triangles, areas)]
        index = min(range(len(ratios)), key=ratios.__getitem__)
        if ratios[index] < minimum:
            minimum = ratios[index]
            worst = {'angle_degrees': angle, 'triangle_index': index}
        maximum = max(maximum, max(ratios))
        inverted += sum(r <= 0 for r in ratios)
        fraction = sum(abs(a) for a, r in zip(areas, ratios) if r < .5) / sum(map(abs, areas))
        worst_fraction = max(worst_fraction, fraction)
    reasons = []
    if not basic['passed']:
        reasons.append('mesh_basic_qa_failed')
    if inverted:
        reasons.append('mesh_triangle_inversion')
    if minimum < .5:
        reasons.append('mesh_area_compression')
    if maximum > 2.:
        reasons.append('mesh_area_expansion')
    return {'status': 'blocked' if reasons else 'passed', 'reason_codes': reasons,
            'min_area_ratio': minimum, 'max_area_ratio': maximum,
            'inverted_triangle_samples': inverted,
            'max_compressed_setup_area_fraction': worst_fraction, 'worst': worst}


def build_area_report(mesh, skeleton):
    bones = {b['id']: b for b in skeleton['bones']}
    layers = []
    for row in mesh['layers']:
        result = {'layer_id': row['layer_id']}
        if not row.get('weights'):
            result.update(status='not_evaluated', reason_codes=['weighted_mesh_required'])
        else:
            chain = [bones[i['bone_id']] for i in row['weights'][0]]
            result.update(analyze_area(row['vertices_xy'], row['triangles'], row['weights'], chain))
        layers.append(result)
    return {'schema': 'autospine.mesh-area-report/v1', 'authority': 'none',
            'production_authorized': False, 'profile': 'elbow-area-screen-v1',
            'source_mesh_sha256': canonical_sha256(mesh),
            'source_skeleton_sha256': canonical_sha256(skeleton),
            'probe_range': [-90, 90, 1], 'area_ratio_bounds': [.5, 2.],
            'threshold_status': 'experimental_uncalibrated',
            'seam_status': 'not_evaluated', 'runtime_status': 'not_evaluated', 'layers': layers}


def validate_area_report(mesh, skeleton, document):
    if canonical_sha256(build_area_report(mesh, skeleton)) != canonical_sha256(document):
        raise ValueError('mesh_area_report_mismatch')
    return document
